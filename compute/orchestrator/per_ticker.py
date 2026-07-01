"""Pre-loop membership-map builder for the weekly compute orchestrator.

Extracted from ``compute.main`` as part of PR #259-R7a (first sub-slice of
the final slice, R7, of the incremental refactor of ``run_weekly_compute``).
The logic here is a PURE CODE MOVE — no behaviour change, no reordering of
effects, same dict keys, same iteration order. Output is byte-identical to
the inline block it replaces.

This is the block that runs BEFORE the main per-ticker loop (Step 8) to
pre-compute three universe-level lookup maps the loop then reads on every
iteration. It is NOT the per-ticker loop itself — that is R7b, a later
sub-slice.

Public surface
--------------
``build_ticker_membership_maps(df, snapshots, *, dow30, ndx)``
    Build and return the 3-tuple ``(multi_class_flagged_tickers,
    cohort_by_ticker, memberships_by_ticker)`` consumed by the per-ticker
    loop and the Metadata assembly downstream.

What stays in ``compute.main``
-------------------------------
``multi_class_aggregate_shares_suspected_count: int = 0`` — this is a
per-ticker LOOP counter initialised immediately after the original inline
block (incremented later, inside the per-ticker loop, whenever a ticker is
found in ``multi_class_flagged_tickers``). It is NOT part of this
map-building step and stays at its original position in
``run_weekly_compute``, directly after the call to
``build_ticker_membership_maps``.

Internal (not returned)
------------------------
``cik_by_ticker`` and ``market_cap_by_ticker`` are intermediate maps used
ONLY to build the CIK-collision detector input and the Russell-1000-proxy
market-cap input. Nothing downstream of the original inline block (the
main per-ticker loop, Metadata assembly, or anywhere else in
``compute.main``) reads either dict directly — both are now fully
internal to this module.

Byte-identical guarantee
------------------------
* ``cik_by_ticker`` / ``market_cap_by_ticker`` are built by iterating
  ``df.iterrows()`` in the same order, with the same ``snapshots.get(t)``
  lookup and the same ``current_price * shares_outstanding`` computation
  (``None`` propagation preserved exactly: a missing snapshot nulls both
  maps for that ticker; a present snapshot with ``shares_outstanding is
  None`` nulls only ``market_cap_by_ticker``).
* ``multi_class_flagged_tickers`` is
  ``detect_multi_class_aggregate_shares_suspected(cik_by_ticker,
  market_cap_by_ticker)`` — same call, same argument order.
* ``cohort_by_ticker`` is the same dict-comprehension over
  ``df.iterrows()`` (``str(r["ticker"]) -> str(r.get("cohort",
  "sp500"))``).
* ``memberships_by_ticker`` is the same dict-comprehension over
  ``cohort_by_ticker.items()``, calling ``derive_index_memberships`` with
  the same keyword arguments in the same order (``cohort``, ``dow30``,
  ``ndx``, ``market_cap=market_cap_by_ticker.get(ticker)``).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from compute.ingest.universe import derive_index_memberships
from compute.scoring.multi_class_shares import (
    detect_multi_class_aggregate_shares_suspected,
)


def build_ticker_membership_maps(
    df: pd.DataFrame,
    snapshots: dict[str, Any],
    *,
    dow30: set[str],
    ndx: set[str],
) -> tuple[set[str], dict[str, str], dict[str, list[str]]]:
    """Build the 3 universe-level lookup maps consumed by the per-ticker loop.

    Runs BEFORE the per-ticker loop so each ticker's annotate emit is a
    simple ``ticker in flagged_set`` membership test and each ticker's
    ``index_membership``/``index_memberships`` write is a simple dict
    lookup — the detector and the membership derivation both need the
    FULL universe upfront (universe-level scans, not per-ticker checks).

    Parameters
    ----------
    df:
        Universe DataFrame with at least ``ticker``, ``current_price``,
        and (on the sp500/sp900/sp1500 paths) ``cohort`` columns.
        Iterated via ``df.iterrows()``.
    snapshots:
        Mapping of ticker -> ``FundamentalsSnapshot | None`` (the dict
        built by ``compute.orchestrator.fundamentals.fetch_all_fundamentals``).
        A ``None`` value means no fundamentals snapshot was built for
        that ticker (e.g. the live SEC fetch failed).
    dow30:
        Set of DOW 30 tickers (may be empty on fetch failure).
    ndx:
        Set of NDX 100 tickers (may be empty on fetch failure).

    Returns
    -------
    multi_class_flagged_tickers : set[str]
        Issue #261 (0.10.5-phase4.5e) — CIK-collision set. Tickers with
        missing snapshots / shares fall out of the detector's inputs; the
        detector returns an empty set if no CIK collisions are observable
        on the available data (graceful degradation, no exception path).
    cohort_by_ticker : dict[str, str]
        Phase 8 pilot PR 3a — cohort-by-ticker lookup for
        ``index_membership``. Defaults to ``"sp500"`` so any ticker
        absent from ``df`` (e.g. post-price-fail drop) stays safe.
    memberships_by_ticker : dict[str, list[str]]
        0.10.23-phase8pilot — multi-index membership lookup, built once
        from ``cohort_by_ticker`` + the pre-fetched Dow30/NDX sets. Runs
        on the sp500, sp900, and sp1500 paths alike (Dow/NDX are sp500
        subsets; sp400/sp600 tickers simply won't appear in ``dow30``/
        ``ndx``).
    """
    # Issue #261 (0.10.5-phase4.5e) — pre-compute the CIK-collision set
    # BEFORE the per-ticker loop so each ticker's annotate emit is a
    # simple `ticker in flagged_set` membership test. The detector
    # needs the FULL universe upfront (it's a universe-level scan, not
    # a per-ticker check). cik_by_ticker is sourced from the already-
    # built `snapshots` dict; market_cap_by_ticker mirrors the
    # `_build_raw_metrics` line 319 computation (price × shares).
    # Tickers with missing snapshots / shares fall out of both maps —
    # the detector returns an empty set if no CIK collisions are
    # observable on the available data (graceful degradation, no
    # exception path).
    cik_by_ticker: dict[str, str | None] = {}
    market_cap_by_ticker: dict[str, float | None] = {}
    for _, r in df.iterrows():
        t = str(r["ticker"])
        s = snapshots.get(t)
        if s is None:
            cik_by_ticker[t] = None
            market_cap_by_ticker[t] = None
            continue
        cik_by_ticker[t] = s.cik
        market_cap_by_ticker[t] = (
            float(r["current_price"]) * s.shares_outstanding
            if s.shares_outstanding is not None
            else None
        )
    multi_class_flagged_tickers: set[str] = (
        detect_multi_class_aggregate_shares_suspected(
            cik_by_ticker, market_cap_by_ticker
        )
    )
    # Phase 8 pilot PR 3a — cohort-by-ticker lookup for index_membership.
    # Built once from df (which carries "cohort" from _fetch_prices_one);
    # defaults to "sp500" so any ticker absent from df (e.g. post-price-fail
    # drop) stays safe. The column is unconditionally present on both the
    # sp500 and sp900 paths (added in the universe-load seam above).
    cohort_by_ticker: dict[str, str] = {
        str(r["ticker"]): str(r.get("cohort", "sp500"))
        for _, r in df.iterrows()
    }
    # Multi-index membership (0.10.23-phase8pilot) — build memberships_by_ticker
    # ONCE from the cohort_by_ticker dict + the pre-fetched Dow30/NDX sets.
    # Runs on both sp500 and sp900 paths (Dow/NDX are sp500 subsets; sp400
    # tickers simply won't appear in _dow30_tickers/_ndx_tickers).
    #
    # Russell 1000 proxy: market_cap_by_ticker is already built above
    # (the CIK-collision pre-compute block earlier in this function) as
    # price × shares_outstanding for every ticker with a non-None snapshot.
    # We pass it here so derive_index_memberships can apply the Russell 1000
    # proxy rule (cap present + positive → "russell1000" tag) without any
    # additional fetch.  Tickers with None cap (missing snapshot /
    # shares_outstanding) simply do not get the tag.
    memberships_by_ticker: dict[str, list[str]] = {
        ticker: derive_index_memberships(
            ticker,
            cohort=cohort,
            dow30=dow30,
            ndx=ndx,
            market_cap=market_cap_by_ticker.get(ticker),
        )
        for ticker, cohort in cohort_by_ticker.items()
    }
    return multi_class_flagged_tickers, cohort_by_ticker, memberships_by_ticker
