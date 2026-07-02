"""Schema + round-trip tests for the Issue #287 PR A wall-clock Metadata fields.

Four new optional fields land on ``Metadata`` at schema ``0.10.9-phase4.6``:

- ``tier2_wall_clock_seconds: float | None = None``
- ``form4_wall_clock_seconds: float | None = None``
- ``osap_wall_clock_seconds: float | None = None``
- ``cross_source_wall_clock_seconds: float | None = None``

All four follow the PATCH-bump "add optional field, default None" contract
(SKILL.md Rule: additive optional → PATCH) so legacy metadata.json files
(pre-0.10.9) deserialize cleanly.

Coverage policy (AGENTS.md §Testing): "add a test when a new contract is
added to the output schema" — this file satisfies that policy for the four
wall-clock fields.

Orchestrator-harness tests (Tests 3/4/5)
-----------------------------------------
Tests 3, 4, and 5 drive ``run_weekly_compute`` through a minimal harness
that stubs all network-touching functions while letting the real wiring
logic run.  The shared ``_run_orchestrator`` helper (see below) applies:

- ``QR_SKIP_SEC_HEALTH=1`` — bypasses the EDGAR health probe.
- ``QR_SKIP_DECAY_MONITOR=1`` — bypasses the IC-decay monitor write.
- ``QR_SKIP_CROSS_SOURCE=1`` — bypasses yfinance market-cap / exchange
  cross-source fetches in Step 8 (pure cache-read, no network).
- ``_fetch_prices_one`` (``compute.orchestrator.prices``), ``_fundamentals_one``
  (``compute.orchestrator.fundamentals``), ``_history_one``
  (``compute.orchestrator.history``) patched to return minimal synthetic
  data so the pipeline does not abort at the MIN_VALID_TICKERS /
  MIN_FUNDAMENTALS_COVERAGE gates.
- ``compute.config.MIN_VALID_TICKERS`` and ``compute.config.MIN_FUNDAMENTALS_COVERAGE``
  lowered to 0 so a 1-ticker run is accepted.
- ``compute.config.DATA_DIR`` redirected to ``tmp_path`` so no real JSON is
  written to the frontend directory.

With these stubs the orchestrator completes in < 2 seconds with zero real
network calls (EDGAR / yfinance / SEC health — all bypassed or gracefully
degraded via the production try/except paths).
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.output.schemas import Metadata
from compute.scoring.eight_k_events import ItemFlag
from compute.scoring.tier2 import Tier2Result

# ---------------------------------------------------------------------------
# Canonical minimal payload for the 7 required Metadata fields.
# Adapted from the existing test_schema_phase4h2._legacy_0_9_0_metadata_payload
# pattern — keeps the fixture minimal and self-documenting.
# ---------------------------------------------------------------------------

def _base_metadata_payload() -> dict:
    """A minimal Metadata payload with only the 7 required fields set.

    No wall-clock fields included — lets each test layer in exactly what
    it needs to verify, following the synthetic-fixture pattern used
    throughout tests/test_output/.
    """
    return {
        "version": "0.10.9-phase4.6",
        "last_update_utc": "2026-05-28T22:00:00Z",
        "next_update_utc": "2026-06-04T22:00:00Z",
        "universe": "sp500",
        "universe_size": 502,
        "compute_run_id": "local",
        "git_commit": "a" * 40,
    }


# ---------------------------------------------------------------------------
# Orchestrator harness — shared helper for Tests 3/4/5.
# ---------------------------------------------------------------------------

# A 252-bar price series with a single 'Close' column.  Minimal but enough
# for the pillar-scoring layer to compute momentum / beta without raising.
_HARNESS_DATES = pd.date_range("2024-01-01", periods=252, freq="B")
_HARNESS_PRICES = pd.DataFrame({"Close": np.full(252, 100.0)}, index=_HARNESS_DATES)

# Minimal FundamentalsSnapshot with all required fields present.
_HARNESS_SNAP = FundamentalsSnapshot(
    ticker="TST",
    cik="0000000001",
    net_income=50.0,
    stockholders_equity=100.0,
    shares_outstanding=10.0,
    eps_diluted=5.0,
    ebitda=50.0,
    long_term_debt=20.0,
    short_term_debt=5.0,
    cash=10.0,
    goodwill=0.0,
    intangibles_net=0.0,
    latest_period_end=date(2025, 12, 31),
    latest_filed_date=date(2026, 2, 14),
)

# 1-row synthetic universe — all required columns present.
_HARNESS_UNIVERSE = pd.DataFrame([{
    "ticker": "TST",
    "name": "Test Corp",
    "sector": "Technology",
    "sub_industry": "Software",
    "cik": "0000000001",
    "cohort": "sp500",
}])

# Minimal Tier2Result for the tier2 success test.
_MINIMAL_TIER2 = Tier2Result(
    going_concern_disclosure=False,
    non_reliance_flag=ItemFlag(
        fired=False, filing_date=None, filing_url=None, raw_item_text=None
    ),
    auditor_change_flag=ItemFlag(
        fired=False, filing_date=None, filing_url=None, raw_item_text=None
    ),
    fetch_succeeded=True,
)


def _fake_fetch_prices_one(row: pd.Series) -> dict:
    """Stub for compute.main._fetch_prices_one — returns minimal valid data."""
    return {
        "ticker": row["ticker"],
        "name": row["name"],
        "sector": row["sector"],
        "industry": row.get("sub_industry"),
        "cik": row.get("cik"),
        "cohort": row.get("cohort", "sp500"),
        "current_price": 100.0,
        "price_change_1d_pct": 0.5,
        "_prices": _HARNESS_PRICES,
    }


def _run_orchestrator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    extra_env: dict[str, str] | None = None,
    extra_patches: list | None = None,
) -> dict:
    """Run ``run_weekly_compute`` with the minimal stub harness.

    Returns the ``metadata.json`` payload as a dict so tests can
    assert on the wall-clock fields without re-importing Metadata
    (keeps the test portable if the schema evolves).

    Parameters
    ----------
    tmp_path:
        pytest ``tmp_path`` fixture — receives all JSON writes.
    monkeypatch:
        pytest ``monkeypatch`` fixture — used for env vars only.
    extra_env:
        Additional ``os.environ`` entries layered on top of the
        standard harness env vars (e.g. ``{"FORM4_FETCH_SKIP": "1"}``).
    extra_patches:
        Additional ``unittest.mock.patch`` objects already *started*
        by the caller.  The helper does NOT start or stop them —
        the caller is responsible for that lifecycle.  Pass ``None``
        to use only the standard harness patches.

    Notes
    -----
    The standard harness env vars are set via ``monkeypatch.setenv``
    (auto-restored after each test):

    - ``QR_SKIP_SEC_HEALTH=1``    — no EDGAR health probe
    - ``QR_SKIP_DECAY_MONITOR=1`` — no IC-decay JSON write
    - ``QR_SKIP_CROSS_SOURCE=1``  — no yfinance market-cap / exchange fetches
    """
    # Apply standard env vars through monkeypatch (auto-cleaned after test).
    for key, val in {
        "QR_SKIP_SEC_HEALTH": "1",
        "QR_SKIP_DECAY_MONITOR": "1",
        "QR_SKIP_CROSS_SOURCE": "1",
        **(extra_env or {}),
    }.items():
        monkeypatch.setenv(key, val)

    # ``compute.main`` import is deferred into the patch stack so the
    # module-level ``get_sp500_constituents`` symbols are resolved AFTER
    # the patches are applied.  ``_fetch_prices_one`` now lives in
    # ``compute.orchestrator.prices`` (PR #259-R2) — patch it there so
    # the call inside ``fetch_all_prices`` is intercepted correctly.
    with (
        patch("compute.orchestrator.prices._fetch_prices_one", side_effect=_fake_fetch_prices_one),
        patch("compute.orchestrator.fundamentals._fundamentals_one", return_value=(_HARNESS_SNAP, 0.1)),
        patch("compute.orchestrator.history._history_one", return_value=(pd.DataFrame(), 0.1)),
        patch("compute.main.get_sp500_constituents", return_value=_HARNESS_UNIVERSE),
        patch("compute.main.fetch_spy_benchmark", return_value=None),
        patch("compute.main.fetch_benchmarks", return_value={}),
        patch("compute.main.write_benchmarks_json", return_value=(None, None)),
        patch("compute.main.fetch_dow30_constituents", return_value=set()),
        patch("compute.main.fetch_ndx_constituents", return_value=set()),
        patch("compute.config.MIN_VALID_TICKERS", 0),
        patch("compute.config.MIN_FUNDAMENTALS_COVERAGE", 0.0),
        patch("compute.config.DATA_DIR", tmp_path),
        patch("compute.main.config.DATA_DIR", tmp_path),
    ):
        from compute.main import run_weekly_compute

        run_weekly_compute()

    meta_path = tmp_path / "metadata.json"
    assert meta_path.exists(), "metadata.json was not written by run_weekly_compute"
    return json.loads(meta_path.read_text())


# ---------------------------------------------------------------------------
# Test 1 — happy path: all four wall-clock fields populated, round-trip intact
# ---------------------------------------------------------------------------

def test_wall_clock_fields_exist_on_metadata_with_floats():
    """Issue #287 PR A — all four wall-clock fields accept floats and
    survive a model_dump(mode='json') round-trip with exact value
    preservation.

    Invariant: the fields are plain ``float | None`` with no coercion or
    truncation — the exact float written to disk is what the operator
    sees in metadata.json.
    """
    payload = _base_metadata_payload()
    payload["tier2_wall_clock_seconds"] = 123.4
    payload["form4_wall_clock_seconds"] = 45.6
    payload["osap_wall_clock_seconds"] = 7.8
    payload["cross_source_wall_clock_seconds"] = 901.2

    meta = Metadata.model_validate(payload)

    assert meta.tier2_wall_clock_seconds == 123.4
    assert meta.form4_wall_clock_seconds == 45.6
    assert meta.osap_wall_clock_seconds == 7.8
    assert meta.cross_source_wall_clock_seconds == 901.2

    # Round-trip through JSON serialisation — what gets written to
    # frontend/public/data/metadata.json must be identical.
    serialised = meta.model_dump(mode="json")
    assert serialised["tier2_wall_clock_seconds"] == 123.4
    assert serialised["form4_wall_clock_seconds"] == 45.6
    assert serialised["osap_wall_clock_seconds"] == 7.8
    assert serialised["cross_source_wall_clock_seconds"] == 901.2

    # Restore via model_validate and verify structural equality.
    restored = Metadata.model_validate(serialised)
    assert restored.tier2_wall_clock_seconds == meta.tier2_wall_clock_seconds
    assert restored.form4_wall_clock_seconds == meta.form4_wall_clock_seconds
    assert restored.osap_wall_clock_seconds == meta.osap_wall_clock_seconds
    assert restored.cross_source_wall_clock_seconds == meta.cross_source_wall_clock_seconds


# ---------------------------------------------------------------------------
# Test 2 — optional-field contract: omitting all four fields → all None
# ---------------------------------------------------------------------------

def test_wall_clock_fields_optional_default_none():
    """Issue #287 PR A — the four wall-clock fields are optional with
    ``= None`` defaults.  A Metadata constructed without supplying them
    raises no ValidationError and serialises all four as ``None``.

    This is the PATCH-bump backward-compat guarantee: a legacy
    metadata.json (pre-0.10.9) deserialises cleanly with the new fields
    silently defaulting to None — identical semantics to every prior
    Phase-4h additive-optional field (osap_signals_missing_from_dataset,
    loss_avoidance_size_invariant_firing_count, etc.).
    """
    payload = _base_metadata_payload()
    # Deliberately omit all four wall-clock fields — simulates a legacy
    # snapshot or any cron run where the fields were not yet written.
    assert "tier2_wall_clock_seconds" not in payload
    assert "form4_wall_clock_seconds" not in payload
    assert "osap_wall_clock_seconds" not in payload
    assert "cross_source_wall_clock_seconds" not in payload

    # Must not raise ValidationError.
    meta = Metadata.model_validate(payload)

    assert meta.tier2_wall_clock_seconds is None
    assert meta.form4_wall_clock_seconds is None
    assert meta.osap_wall_clock_seconds is None
    assert meta.cross_source_wall_clock_seconds is None

    # Serialisation must carry None explicitly (not omit the keys) so the
    # JSON contract is stable regardless of whether the field was populated.
    serialised = meta.model_dump(mode="json")
    assert "tier2_wall_clock_seconds" in serialised
    assert serialised["tier2_wall_clock_seconds"] is None
    assert "form4_wall_clock_seconds" in serialised
    assert serialised["form4_wall_clock_seconds"] is None
    assert "osap_wall_clock_seconds" in serialised
    assert serialised["osap_wall_clock_seconds"] is None
    assert "cross_source_wall_clock_seconds" in serialised
    assert serialised["cross_source_wall_clock_seconds"] is None


# ---------------------------------------------------------------------------
# Tests 3/4/5 — orchestrator wiring (offline; no @pytest.mark.network)
# ---------------------------------------------------------------------------
# All three tests drive ``run_weekly_compute`` with the _run_orchestrator
# harness defined above.  The harness runs in < 2 s with zero live network
# calls; every external call site degrades gracefully to None via the
# production try/except paths (portable-graceful-degradation-try-except
# convention, CLAUDE.md).
#
# Test 3 — FORM4_FETCH_SKIP=1 → form4_wall_clock_seconds is None
# Test 4 — fetch_osap_returns raises RuntimeError → osap_wall_clock_seconds is None
# Test 5 — fetch_tier2_for_ticker returns valid Tier2Result → tier2_wall_clock_seconds float
# ---------------------------------------------------------------------------


def test_form4_wall_clock_none_when_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invariant: ``form4_wall_clock_seconds`` is ``None`` in the written
    ``metadata.json`` when ``FORM4_FETCH_SKIP=1``.

    ``FORM4_FETCH_SKIP=1`` causes the ``run_weekly_compute`` Form-4 fetch
    loop to be skipped entirely (the ``else`` branch at main.py line ~1150
    is never entered).  The local variable ``form4_wall_clock_seconds`` is
    initialised to ``None`` at line ~1128 and is never reassigned on the
    skip path, so it propagates to ``Metadata(form4_wall_clock_seconds=...)``
    and into ``metadata.json``.

    This is the Issue #287 PR A "skip-path semantics" contract: every
    wall-clock field is ``None`` when its corresponding loop did not run.
    """
    meta = _run_orchestrator(
        tmp_path,
        monkeypatch,
        extra_env={"FORM4_FETCH_SKIP": "1"},
    )
    assert meta["form4_wall_clock_seconds"] is None


def test_osap_wall_clock_none_on_pipeline_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invariant: ``osap_wall_clock_seconds`` is ``None`` when
    ``fetch_osap_returns`` raises ``RuntimeError``.

    The OSAP block in ``run_weekly_compute`` (main.py ~line 1612) begins
    with ``osap_wall_clock_seconds: float | None = None``, starts the
    wall-clock, then calls ``fetch_osap_returns`` inside a try block.
    If that call raises, the outer ``except Exception`` resets
    ``osap_wall_clock_seconds = None`` (main.py ~line 1776).

    The harness injects a fake ``compute.ingest.osap`` module into
    ``sys.modules`` so the deferred import inside the try block succeeds
    but ``fetch_osap_returns`` immediately raises ``RuntimeError("Simulated
    OSAP failure")``.  The except branch fires, leaving the field ``None``
    in the written ``metadata.json``.

    Distinct from the "ImportError" case (openassetpricing not installed):
    both are caught by the same ``except Exception`` and produce the same
    ``None`` outcome; this test uses an explicit ``RuntimeError`` so the
    invariant is clear regardless of the test environment's optional extras.
    """
    # Build a fake compute.ingest.osap module whose fetch_osap_returns raises.
    fake_osap = MagicMock()
    fake_osap.fetch_osap_returns = MagicMock(
        side_effect=RuntimeError("Simulated OSAP failure")
    )
    # compute.ingest.osap imports openassetpricing at module load, which is
    # not available in the base install.  Pre-populate sys.modules so the
    # deferred "from compute.ingest.osap import fetch_osap_returns" succeeds
    # with our stub instead of raising ImportError.
    monkeypatch.setitem(sys.modules, "openassetpricing", MagicMock())
    monkeypatch.setitem(sys.modules, "compute.ingest.osap", fake_osap)

    meta = _run_orchestrator(
        tmp_path,
        monkeypatch,
        extra_env={"FORM4_FETCH_SKIP": "1"},
    )
    assert meta["osap_wall_clock_seconds"] is None


def test_tier2_wall_clock_populated_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invariant: ``tier2_wall_clock_seconds`` is a ``float`` (not ``None``)
    when ``fetch_tier2_for_ticker`` returns a valid ``Tier2Result``.

    The Step-4b Tier-2 fetch loop now lives in
    ``compute.orchestrator.tier2.fetch_all_tier2`` (extracted from
    ``compute.main`` as part of PR #259-R5). It starts a wall-clock
    marker, runs the ``ThreadPoolExecutor`` loop that calls
    ``fetch_tier2_for_ticker`` per ticker, and assigns
    ``tier2_wall_clock_seconds = round(time.monotonic() - _tier2_wc_start, 1)``
    immediately after the executor exits. ``compute.main`` calls
    ``fetch_all_tier2(df)`` once and unpacks the returned tuple.

    ``fetch_tier2_for_ticker`` is patched at the
    ``compute.orchestrator.tier2`` module level (it is imported there as a
    module-level name, not deferred) to return a minimal ``Tier2Result``
    with ``fetch_succeeded=True``.  Because the executor succeeds and the
    outer try does not raise, the end-marker assignment fires and the
    field carries a non-negative float in the written ``metadata.json``.
    """
    with patch(
        "compute.orchestrator.tier2.fetch_tier2_for_ticker",
        side_effect=lambda ticker, **kw: _MINIMAL_TIER2,
    ):
        meta = _run_orchestrator(
            tmp_path,
            monkeypatch,
            extra_env={"FORM4_FETCH_SKIP": "1"},
        )

    tier2_wc = meta["tier2_wall_clock_seconds"]
    assert tier2_wc is not None, (
        "tier2_wall_clock_seconds must be a float when fetch_tier2_for_ticker "
        "returns a valid Tier2Result (happy-path wiring, main.py ~line 1430)"
    )
    assert isinstance(tier2_wc, float), (
        f"Expected float, got {type(tier2_wc).__name__}: {tier2_wc!r}"
    )
