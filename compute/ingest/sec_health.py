"""SEC EDGAR API health probe.

A single cheap GET against `data.sec.gov/submissions/CIK*.json` for a
known-stable ticker (Apple, CIK 0000320193). If the response is slow
or non-200, the weekly compute should abort early rather than burn
~30-90 minutes against a degraded SEC EDGAR.

The PR-3d incident playbook documented this as
``/tmp/issue_drafts/issue_fundamentals_resilience_phase4.md`` §d. This
module is the implementation.

Severity ladder (decided at the call site):

- ``< 5s``       → healthy; proceed
- ``5-15s``      → throttled but functional; log warning + proceed
- ``> 15s``      → degraded; abort with clear reschedule message
- non-200 / network error → degraded; abort

The probe uses ``requests`` (already a project dependency) directly
rather than edgartools so we stay close to the wire and don't go
through edgartools' own retry/backoff layers. The check should reflect
"is SEC reachable AT ALL right now", not "is edgartools happy".
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

# AAPL — Apple Inc. The companyfacts payload here is ~5 MB; we use
# the lighter submissions endpoint instead (~400 KB). The CIK is
# stable since 1980, so we don't need to look it up dynamically.
_HEALTH_PROBE_CIK = "0000320193"
_HEALTH_PROBE_URL = f"https://data.sec.gov/submissions/CIK{_HEALTH_PROBE_CIK}.json"

# Latency thresholds. These match the docstring's severity ladder.
_HEALTHY_MAX_SECONDS = 5.0
_DEGRADED_MIN_SECONDS = 15.0

# Hard cap so the probe itself doesn't hang the compute startup if
# SEC is completely down. Larger than the degraded threshold so the
# caller can distinguish "slow but reachable" from "unreachable".
_PROBE_TIMEOUT_SECONDS = 20.0


class SecApiHealth:
    """Three-state enum for the probe outcome."""

    HEALTHY = "healthy"
    THROTTLED = "throttled"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class SecApiProbeResult:
    """Single-probe result. Returned by ``probe_sec_api``."""

    state: str
    latency_seconds: float
    http_status: int | None
    error: str | None


def probe_sec_api(*, user_agent: str | None = None) -> SecApiProbeResult:
    """Probe data.sec.gov once with a hard timeout.

    Parameters
    ----------
    user_agent:
        Optional override. When None, reads ``EDGAR_USER_AGENT`` from
        the environment (the same env var the rest of the ingest
        layer requires). The User-Agent header is mandatory — SEC
        EDGAR returns 403 without it.

    Returns
    -------
    SecApiProbeResult
        Always returns. Never raises. The caller decides whether to
        abort the compute run based on ``state`` + ``latency_seconds``.
    """
    ua = user_agent if user_agent is not None else os.environ.get("EDGAR_USER_AGENT")
    if not ua:
        return SecApiProbeResult(
            state=SecApiHealth.DEGRADED,
            latency_seconds=0.0,
            http_status=None,
            error="EDGAR_USER_AGENT not set",
        )

    start = time.perf_counter()
    try:
        response = requests.get(
            _HEALTH_PROBE_URL,
            headers={"User-Agent": ua, "Accept": "application/json"},
            timeout=_PROBE_TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        elapsed = time.perf_counter() - start
        return SecApiProbeResult(
            state=SecApiHealth.DEGRADED,
            latency_seconds=elapsed,
            http_status=None,
            error=str(e),
        )

    elapsed = time.perf_counter() - start

    if response.status_code != 200:
        return SecApiProbeResult(
            state=SecApiHealth.DEGRADED,
            latency_seconds=elapsed,
            http_status=response.status_code,
            error=f"HTTP {response.status_code}",
        )

    if elapsed >= _DEGRADED_MIN_SECONDS:
        state = SecApiHealth.DEGRADED
    elif elapsed >= _HEALTHY_MAX_SECONDS:
        state = SecApiHealth.THROTTLED
    else:
        state = SecApiHealth.HEALTHY

    return SecApiProbeResult(
        state=state,
        latency_seconds=elapsed,
        http_status=200,
        error=None,
    )


def assert_sec_api_usable() -> SecApiProbeResult:
    """Probe SEC + log + return. Raises ``RuntimeError`` if degraded.

    Used at the top of ``compute.main.run_weekly_compute`` to abort
    early when SEC EDGAR is unusable. A degraded probe means the
    weekly compute would burn the full 90-min workflow timeout for
    ~0% coverage; better to fail fast with a clear log line and
    let the operator reschedule.

    Skips the check entirely when ``QR_SKIP_SEC_HEALTH=1`` so the
    operator can force a run-through (e.g., for testing the compute
    pipeline against synthetic-cache data with no SEC dependency).
    """
    if os.environ.get("QR_SKIP_SEC_HEALTH"):
        logger.info("SEC API health check skipped (QR_SKIP_SEC_HEALTH set)")
        return SecApiProbeResult(
            state=SecApiHealth.HEALTHY,
            latency_seconds=0.0,
            http_status=None,
            error="skipped",
        )

    result = probe_sec_api()

    if result.state == SecApiHealth.HEALTHY:
        logger.info(
            "SEC API health: ✓ healthy (%.2fs latency, HTTP %s)",
            result.latency_seconds,
            result.http_status,
        )
        return result

    if result.state == SecApiHealth.THROTTLED:
        logger.warning(
            "SEC API health: ⚠ throttled (%.2fs latency) — proceeding but "
            "expect degraded fundamentals_latency_p95",
            result.latency_seconds,
        )
        return result

    # Degraded — abort with a clear message. The caller (run_weekly_compute)
    # catches RuntimeError and returns a non-zero exit so the workflow
    # ends quickly instead of running to timeout.
    msg = (
        f"SEC API health: ✗ degraded — {result.error or 'high latency'} "
        f"(latency={result.latency_seconds:.2f}s, http={result.http_status}). "
        "Aborting compute run; reschedule when SEC EDGAR recovers."
    )
    logger.error(msg)
    raise RuntimeError(msg)
