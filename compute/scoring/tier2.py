"""Tier-2 event-defense orchestrator (Phase 3d Step 5).

Composes the Tier-2 defenses into a single per-ticker call.

PR 3d ships only **Defense #8** (going-concern phrase scan). Defenses
#9 (8-K Item 4.02 hard veto) and #10 (8-K Item 4.01 auditor change)
are **DEFERRED to Phase 4** following three workflow_dispatch
timeouts (#12, #13, #14) on cold-cache runs. The 8-K parsing path
adds ~5-15 min per cold run — combined with PR 3c's existing ~12 min
and a healed fundamentals stage at ~10 min, the run was running too
close to the workflow timeout cliff.

The 8-K-related fields in :class:`Tier2Result` are preserved
(``non_reliance_flag`` / ``auditor_change_flag``) but always emit the
empty :class:`ItemFlag` (``fired=False``, all metadata None) until
Phase 4 re-enables the underlying fetch. Schema is unchanged; the
display dict in :func:`tier2_events_dict` keeps the same 5 fields.

Active in PR 3d:

- :func:`compute.scoring.going_concern.scan_going_concern`
  (Defense #8 — annotate-only, 10-K text scan)

Deferred to Phase 4 (see issue tracker):

- :func:`compute.scoring.eight_k_events.check_non_reliance`
  (Defense #9 — HARD VETO, 8-K Item 4.02)
- :func:`compute.scoring.eight_k_events.check_auditor_change`
  (Defense #10 — annotate-only, 8-K Item 4.01)

The orchestrator is still the canonical place to fetch Tier-2 data
once per ticker per compute run. With Defense #8 only, it drives:

1. ``StockDetail.tier2_events`` (display payload — going_concern only)
2. The ``non_reliance_by_ticker`` inject for
   :func:`compute.scoring.risk_overlay.compute_risk_flags` is now
   always an empty dict — Defense #9 contributes zero to the active
   veto layer until Phase 4. Existing 3 vetoes (altman / sloan / NSI)
   stay live.

Failure semantics
-----------------

The 10-K text fetch can fail (network, rate-limit, identity-not-set).
On failure the result is :class:`Tier2Result` with
``going_concern_disclosure=False`` and ``fetch_succeeded=False``.
``Metadata.tier2_coverage_pct`` aggregates the success rate.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date

from compute.ingest.filing_text import fetch_latest_10k_text
from compute.scoring.eight_k_events import (
    ItemFlag,
    check_auditor_change,
    check_non_reliance,
    fetch_recent_8k_filings,
)
from compute.scoring.going_concern import scan_going_concern

# PR 4g (2026-05-15) re-enabled 8-K Defenses #9 / #10. The PR 3d
# rationale for deferral (filing.text() perf hot spot + SEC API
# throttling timeouts on cold-cache runs) was addressed by:
#   - PR 3d Part 1 perf hotfixes (commit 226840d filing.html(),
#     12ad7ff regex-on-HTML 8-K extraction, tenacity retry tightened
#     to stop_after_delay(30) | attempt(2), 45s per-stock timeout)
#   - PR 4a workflow cache restore — `edgar_8k` cache now persists
#     between runs (was being dropped each CI run)
#   - PR 4f daily Mon-Fri cron — 24h recovery window instead of 7d
# Production observability post-flip is via `tier2_coverage_pct` in
# metadata.json + the workflow latency log. If 8-K fetch ever pushes
# the run beyond the 90-min timeout, the kill-switch is the
# QR_SKIP_TIER2 env var (already wired below). Pre-cache off-cycle
# workflow remains an option for further perf headroom (issue #14
# §1) but is no longer a blocker.
_EIGHT_K_DEFENSES_ENABLED = True

logger = logging.getLogger(__name__)


def _empty_flag() -> ItemFlag:
    """Convenience for the 'fetch failed / nothing fired' return shape."""
    return ItemFlag(fired=False, filing_date=None, filing_url=None, raw_item_text=None)


@dataclass(frozen=True)
class Tier2Result:
    """Result of orchestrating all 3 Tier-2 defenses for one ticker.

    Attributes
    ----------
    going_concern_disclosure:
        True iff at least one LM-dictionary phrase fired in the most
        recent 10-K's narrative text. False on fetch failure or clean
        text.
    non_reliance_flag:
        ``ItemFlag`` from :func:`check_non_reliance`. ``fired=True``
        means an Item 4.02 disclosure within trailing 365 days; this
        is the Defense #9 hard-veto signal.
    auditor_change_flag:
        ``ItemFlag`` from :func:`check_auditor_change`. ``fired=True``
        means an Item 4.01 disclosure within trailing 730 days;
        Defense #10 annotate-only.
    fetch_succeeded:
        True iff **both** underlying fetches (10-K text + 8-K filing
        list) returned data. False when either failed (network /
        rate-limit / missing identity / ticker-not-found). The ticker
        is still scoreable but won't count toward
        ``Metadata.tier2_coverage_pct``.
    """

    going_concern_disclosure: bool
    non_reliance_flag: ItemFlag
    auditor_change_flag: ItemFlag
    fetch_succeeded: bool


def fetch_tier2_for_ticker(
    ticker: str,
    *,
    asof: date | None = None,
) -> Tier2Result:
    """Fetch + compute all 3 Tier-2 defenses for a single ticker.

    Parameters
    ----------
    ticker:
        Stock ticker. Passed through to all underlying fetchers.
    asof:
        Optional reference date for the 8-K lookback windows. Default
        is ``None`` which means "today" (deferred to the underlying
        ``check_*`` functions). Tests pass an explicit date for
        determinism.

    Returns
    -------
    Tier2Result
        Frozen dataclass. Failure semantics documented in the class
        docstring + module docstring.

    The orchestrator catches every exception per fetch so one bad
    ticker can never crash the whole compute run. Per-ticker logging
    surfaces failure causes in the workflow log without aborting.
    """
    # Operational kill-switch — if QR_SKIP_TIER2 is set, return the
    # empty result without touching SEC EDGAR. Useful when the user
    # wants a fast compute run (e.g., a UI dry-run or a sanity-check
    # workflow) and is willing to skip the going-concern annotate
    # flag. The veto layer is unaffected because all Tier-2 vetoes
    # are currently deferred (_EIGHT_K_DEFENSES_ENABLED=False), and
    # the annotate-only going-concern flag has a 10.8% FP rate
    # anyway (issue #16). Cuts ~10-15 min off a cold-cache run.
    if os.environ.get("QR_SKIP_TIER2"):
        return Tier2Result(
            going_concern_disclosure=False,
            non_reliance_flag=_empty_flag(),
            auditor_change_flag=_empty_flag(),
            fetch_succeeded=False,
        )

    # --- 10-K text + going-concern phrase scan (Defense #8) ---
    text: str | None = None
    text_fetch_ok = False
    try:
        text = fetch_latest_10k_text(ticker)
        text_fetch_ok = text is not None
    except Exception as e:  # noqa: BLE001
        logger.warning("tier2: 10-K fetch raised for %s: %s", ticker, e)
        text = None
    going_concern = scan_going_concern(text) if text else False

    # --- 8-K Defenses #9 + #10 — DEFERRED to Phase 4 (see module docstring) ---
    # Wiring kept skip-able via a single feature flag so Phase 4 can
    # re-enable without further changes here. When disabled, both flags
    # emit the canonical empty ItemFlag and tier2_coverage_pct's
    # success criterion collapses to "10-K text fetched OK".
    if _EIGHT_K_DEFENSES_ENABLED:
        from compute import config
        eight_k_fetch_ok = False
        try:
            filings = fetch_recent_8k_filings(
                ticker, lookback_days=config.EIGHT_K_LOOKBACK_DAYS_ANNOTATE
            )
            eight_k_fetch_ok = filings is not None
        except Exception as e:  # noqa: BLE001
            logger.warning("tier2: 8-K fetch raised for %s: %s", ticker, e)
            filings = None
            eight_k_fetch_ok = False

        if eight_k_fetch_ok:
            try:
                non_reliance_flag = check_non_reliance(ticker, asof=asof, filings=filings)
            except Exception as e:  # noqa: BLE001
                logger.warning("tier2: check_non_reliance raised for %s: %s", ticker, e)
                non_reliance_flag = _empty_flag()
            try:
                auditor_change_flag = check_auditor_change(
                    ticker, asof=asof, filings=filings
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("tier2: check_auditor_change raised for %s: %s", ticker, e)
                auditor_change_flag = _empty_flag()
        else:
            non_reliance_flag = _empty_flag()
            auditor_change_flag = _empty_flag()
        fetch_succeeded = text_fetch_ok and eight_k_fetch_ok
    else:
        non_reliance_flag = _empty_flag()
        auditor_change_flag = _empty_flag()
        # With 8-K deferred, "fetched all the data we expect" = "10-K text OK".
        fetch_succeeded = text_fetch_ok

    return Tier2Result(
        going_concern_disclosure=going_concern,
        non_reliance_flag=non_reliance_flag,
        auditor_change_flag=auditor_change_flag,
        fetch_succeeded=fetch_succeeded,
    )


def tier2_events_dict(result: Tier2Result) -> dict:
    """Build the JSON-serializable display dict for ``StockDetail.tier2_events``.

    Shape mirrors :class:`frontend.lib.types.Tier2Events` exactly:

    - ``going_concern_disclosure`` (bool)
    - ``non_reliance_filing`` (bool)
    - ``auditor_change`` (bool)
    - ``latest_8k_filing_date`` (str | None) — most recent 8-K date
      across both flags. When both fire, prefers ``non_reliance_flag``
      (the hard-veto signal is more important to surface).
    - ``latest_8k_filing_url`` (str | None) — URL of that filing.
    """
    # Prefer the non-reliance filing when both fired (hard veto > annotate).
    if result.non_reliance_flag.fired:
        latest_date = result.non_reliance_flag.filing_date
        latest_url = result.non_reliance_flag.filing_url
    elif result.auditor_change_flag.fired:
        latest_date = result.auditor_change_flag.filing_date
        latest_url = result.auditor_change_flag.filing_url
    else:
        latest_date = None
        latest_url = None
    return {
        "going_concern_disclosure": result.going_concern_disclosure,
        "non_reliance_filing": result.non_reliance_flag.fired,
        "auditor_change": result.auditor_change_flag.fired,
        "latest_8k_filing_date": latest_date,
        "latest_8k_filing_url": latest_url,
    }


def coverage_pct(results: dict[str, Tier2Result]) -> float | None:
    """Compute Metadata.tier2_coverage_pct from a dict of per-ticker results.

    Returns
    -------
    float | None
        Percentage of tickers (0.0–100.0) where ``fetch_succeeded`` was
        True, rounded to 2 decimal places. Returns ``None`` when the
        results dict is empty (avoids ZeroDivisionError + matches the
        "we didn't try" semantics of a missing universe).
    """
    if not results:
        return None
    successful = sum(1 for r in results.values() if r.fetch_succeeded)
    return round(100.0 * successful / len(results), 2)


__all__ = [
    "Tier2Result",
    "coverage_pct",
    "fetch_tier2_for_ticker",
    "tier2_events_dict",
]
