"""Pre-loop membership-map builder + per-ticker loop for the weekly compute
orchestrator.

Extracted from ``compute.main`` as part of PR #259-R7a
(``build_ticker_membership_maps``) and PR #259-R7b (``run_per_ticker_loop`` +
``PerTickerLoopResult`` — the FINAL sub-slice of the incremental refactor of
``run_weekly_compute``, issue #259). The logic here is a PURE CODE MOVE — no
behaviour change, no reordering of effects, same dict keys, same iteration
order, same exception handling, same log text/levels. Output is
byte-identical to the inline block(s) each function replaces.

R7a — ``build_ticker_membership_maps``
---------------------------------------
This is the block that runs BEFORE the main per-ticker loop (Step 8) to
pre-compute three universe-level lookup maps the loop then reads on every
iteration. It is NOT the per-ticker loop itself — that is R7b, below.

Public surface (R7a)
---------------------
``build_ticker_membership_maps(df, snapshots, *, dow30, ndx)``
    Build and return the 3-tuple ``(multi_class_flagged_tickers,
    cohort_by_ticker, memberships_by_ticker)`` consumed by the per-ticker
    loop and the Metadata assembly downstream.

What stays in ``compute.main`` (R7a)
--------------------------------------
``multi_class_aggregate_shares_suspected_count: int = 0`` — this is a
per-ticker LOOP counter initialised immediately after the original inline
block (incremented later, inside the per-ticker loop, whenever a ticker is
found in ``multi_class_flagged_tickers``). It is NOT part of this
map-building step. ``run_weekly_compute`` still calls
``build_ticker_membership_maps`` itself (this call site is UNCHANGED by
R7b) and then passes its 3-tuple result into ``run_per_ticker_loop`` as
plain keyword inputs — R7b's function does not re-invoke
``build_ticker_membership_maps``.

Internal (not returned, R7a)
------------------------------
``cik_by_ticker`` and ``market_cap_by_ticker`` are intermediate maps used
ONLY to build the CIK-collision detector input and the Russell-1000-proxy
market-cap input. Nothing downstream of the original inline block (the
main per-ticker loop, Metadata assembly, or anywhere else in
``compute.main``) reads either dict directly — both are now fully
internal to this module.

Byte-identical guarantee (R7a)
-------------------------------
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

R7b — ``run_per_ticker_loop`` / ``PerTickerLoopResult``
---------------------------------------------------------
The Step-8 combined per-ticker loop (fair-price ensemble + price-history
write + ``StockSummary`` + ``StockDetail``) PLUS its immediately-preceding
accumulator/counter inits — the single largest block in
``run_weekly_compute``. Moved here VERBATIM: every statement, in the same
order, with the same log lines and the same exception handling as the
inline block it replaces.

Two ``compute.main`` helpers used both INSIDE this loop and OUTSIDE it are
NOT moved — they stay defined in ``compute.main`` and are INJECTED as
callables instead:

* ``_filing_lag`` also drives the Step-6b stale-filing pre-scan (a
  different block, upstream of Step 8) and is directly imported by
  ``tests/test_main.py`` as ``compute.main._filing_lag``.
* ``_build_raw_metrics`` is directly imported by ``tests/test_main.py``
  and ``tests/test_ingest/test_issue374_ratifyb.py`` as
  ``compute.main._build_raw_metrics``.

Moving either would either break those test imports (if not re-exported)
or require ``compute.orchestrator.per_ticker`` to import back FROM
``compute.main`` — a layering inversion with real circular-import risk
(``compute.main`` imports this module at module load; the reverse import
would need ``_filing_lag`` / ``_build_raw_metrics`` to already exist in
``compute.main``'s partially-initialised namespace, which they don't at
that point since they're defined later in the file). Instead, both stay
put in ``compute.main`` and are passed in as the ``filing_lag_fn`` /
``build_raw_metrics_fn`` keyword parameters — the two original call
expressions are otherwise untouched (same positional / keyword arguments,
same call sites, same order; only the callable's *name* changed to match
the parameter it now is).

``_build_data_quality`` and ``_pillar_scores_to_schema`` have no such
external dependency (nothing outside the old inline block imported them
directly) — both moved here in full, verbatim, as module-private helpers.

Public surface (R7b)
---------------------
``run_per_ticker_loop(...)`` (all keyword-only parameters)
    Run the Step-8 per-ticker loop and return a :class:`PerTickerLoopResult`
    with every accumulator the original inline block's downstream code
    (the ``Metadata`` constructor, the post-loop diagnostic blocks, and the
    Step-13.5 warehouse ``all_details`` consumer) reads after the loop.

Byte-identical guarantee (R7b)
--------------------------------
* Every init statement, loop statement, and post-loop wall-clock/log
  statement from the original inline block is reproduced VERBATIM — same
  order, same conditionals, same exception handling, same log text. The
  only textual changes anywhere in the moved ~950 lines are the 3 call
  sites renamed to use the injected ``filing_lag_fn`` /
  ``build_raw_metrics_fn`` parameters instead of the module-global
  ``_filing_lag`` / ``_build_raw_metrics`` names (2 + 1 occurrences
  respectively) — same function objects, same arguments, same call order.
* Smells #5 (the ~20 ``valuation_warnings.append`` dedup-then-append
  sites) and #8 (the double ``check_rim_applicability`` call, once with
  the flat Ke and once with the sector Ke) were DELIBERATELY left
  untouched by R7b — that was a pure code move, not a consolidation.

Follow-up cleanup (#259 smell5-8 cleanup, post-R7b)
-----------------------------------------------------
A later, purely-local readability pass addressed the SAFE parts of both
smells with zero behaviour change (verified by the same byte-identical
proof R7b used — the full offline test suite, whose ``run_weekly_compute``
harness drives this loop):

* Smell #5 — every ``if "X" not in valuation_warnings:
  valuation_warnings.append("X")`` site (and its counter-coupled
  variants) now goes through :class:`WarningEmitter`, a tiny wrapper
  around the SAME per-ticker ``valuation_warnings`` list constructed at
  its usual place (``valuation_warnings = list(ensemble.valuation_warnings)``
  when a snapshot exists, ``[]`` otherwise). ``emitter.add(flag)`` performs
  the identical two-step "append iff not already present" the inline
  pattern did, in the same order, and returns whether it was a NEW
  append. Sites where the ORIGINAL counter increment lived inside the
  same ``if <cond> and "X" not in valuation_warnings:`` guard (so it only
  fired on a genuinely new append) now read
  ``if <cond> and emitter.add("X"): count += 1``. Sites where the counter
  incremented on every firing of ``<cond>`` REGARDLESS of dedup outcome
  (``cross_source_disagreement_count``, ``multi_class_aggregate_shares_suspected_count``,
  ``insider_sell_cluster_firing_count``, ``c_suite_unusual_sell_firing_count``,
  ``value_trap_risk_two_factor_shadow_count``) keep the increment tied to
  ``<cond>`` exactly as before, with a plain ``emitter.add("X")`` call
  alongside it (not gating the count on the emitter's return value) — the
  two coupling shapes are NOT interchangeable and this pass preserves
  each site's original shape.
* Smell #8 — the two ``check_rim_applicability`` calls (flat Ke /
  ``_rim_flat`` vs sector Ke / ``_rim_sector``) are UNCHANGED — issue #67
  needs both for the flat-vs-sector delta measurement. Only the
  IDENTICAL 3-line "if the RIM skip reason is the value-trap-risk one:
  bump the scalar counter + bump the per-sector dict" block that used to
  follow EACH call is now the shared ``_tally_value_trap`` helper. The
  DEEPER redundancy — ``_rim_sector`` re-deriving inputs
  ``compute_fair_price_ensemble`` already computed internally for its own
  RIM-applicability check — is intentionally NOT addressed: fixing that
  would mean changing ``compute_fair_price_ensemble``'s return signature
  (a ``compute/valuation/`` change), which is out of scope for this
  ``compute/orchestrator/`` -only cleanup and carries real byte-identity
  risk of its own.
* Accumulators/counters read only WITHIN the original inline block
  (``detail_count``, ``history_count``, ``fair_price_count``,
  ``_pays_dividend_by_ticker``, ``_payout_ratio_by_ticker``, the internal
  ``_cross_source_wc_start`` wall-clock marker) stay local to this
  function — they are NOT part of :class:`PerTickerLoopResult` because
  nothing in ``compute.main`` reads them after the loop returns (confirmed
  by grepping every name for post-loop references before this refactor).
"""

from __future__ import annotations

import logging
import math
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from compute import config
from compute.ingest.cross_source import (
    BUCKET_KEYS as CROSS_SOURCE_BUCKET_KEYS,
)
from compute.ingest.cross_source import (
    bucket_delta as cross_source_bucket_delta,
)
from compute.ingest.cross_source import (
    country_for_exchange,
    exchange_name,
    fetch_yfinance_dividend,
    fetch_yfinance_exchange,
    fetch_yfinance_market_cap,
    fetch_yfinance_sector,
    fetch_yfinance_security_type,
    fetch_yfinance_shares_outstanding,
    map_yfinance_sector_to_gics,
)
from compute.ingest.cross_source import (
    validate_market_cap as cross_source_validate_market_cap,
)
from compute.ingest.fundamentals import ALL_METRIC_KEYS, FundamentalsSnapshot
from compute.ingest.universe import derive_index_memberships
from compute.output.schemas import (
    DataQuality,
    PillarScores,
    RawMetrics,
    StockDetail,
    StockSummary,
)
from compute.output.writer import write_stock_detail, write_stock_history
from compute.scoring.beneish import BeneishResult
from compute.scoring.cost_of_equity import get_cost_of_equity
from compute.scoring.dechow_f import DechowResult
from compute.scoring.earnings_quality import (
    check_accruals_momentum,
    check_loss_avoidance,
    check_loss_avoidance_size_invariant,
)
from compute.scoring.eight_k_events import get_non_reliance_filing_dates
from compute.scoring.form4_insider import fetch_recent_form4
from compute.scoring.form4_signals import (
    count_10b5_1_filtered_transactions,
    detect_c_suite_unusual_sell,
    detect_insider_sell_cluster,
)
from compute.scoring.loss_chance import derive_loss_chance
from compute.scoring.manipulation_index import (
    compute_adjusted_composite,
    compute_manipulation_index,
    manipulation_components,
)
from compute.scoring.multi_class_shares import (
    detect_multi_class_aggregate_shares_suspected,
)
from compute.scoring.recommendation import derive_recommendation
from compute.scoring.rem import REMResult
from compute.scoring.restatement_filings import (
    check_late_filing,
    check_restatement_history,
    compute_high_confidence_restatement,
    get_amendment_filing_dates,
)
from compute.scoring.risk_overlay import (
    PostSplitResult,
    _snapshot_has_no_usable_fundamentals,
    check_share_count_extraction_missing,
)
from compute.scoring.tier2 import Tier2Result, tier2_events_dict
from compute.valuation.applicability import (
    MethodApplicability,
    check_rim_applicability,
    stale_filing_status,
)
from compute.valuation.ensemble import (
    EnsembleResult,
    compute_fair_price_ensemble,
    ensemble_result_to_dict,
)
from compute.valuation.tangible_book import tangible_book_value_per_share

logger = logging.getLogger(__name__)


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


def _build_data_quality(
    snapshot: FundamentalsSnapshot | None,
    today: datetime,
    imputed_pillars: list[str],
) -> DataQuality:
    if snapshot is None:
        return DataQuality(
            missing_metrics=list(ALL_METRIC_KEYS),
            imputed_metrics=imputed_pillars,
        )
    filing_lag: int | None = None
    if snapshot.latest_filed_date is not None:
        filing_lag = (today.date() - snapshot.latest_filed_date).days
    return DataQuality(
        missing_metrics=snapshot.missing_fields(),
        imputed_metrics=imputed_pillars,
        filing_lag_days=filing_lag,
        latest_period_end=str(snapshot.latest_period_end)
        if snapshot.latest_period_end
        else None,
        latest_filed_date=str(snapshot.latest_filed_date)
        if snapshot.latest_filed_date
        else None,
    )


def _pillar_scores_to_schema(row: pd.Series) -> PillarScores:
    """Convert a one-ticker pillar score row into a PillarScores model.

    Rounds to 2 decimals; null pillars (sentiment, ml) stay None.
    """
    def r(v):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return None
        return round(float(v), 2)

    return PillarScores(
        quality=r(row.get("quality")),
        value=r(row.get("value")),
        growth=r(row.get("growth")),
        momentum=r(row.get("momentum")),
        health=r(row.get("health")),
        profitability=r(row.get("profitability")),
        technical=r(row.get("technical")),
        risk=r(row.get("risk")),
        sentiment=None,
        ml=None,
    )


@dataclass(frozen=True)
class PerTickerLoopResult:
    """The Step-8 per-ticker loop's accumulators, read by ``compute.main``
    after the loop returns.

    Every field name matches the local variable name the original inline
    block used — INCLUDING the leading-underscore "internal accumulator"
    names (e.g. ``_cs_yf_market_cap_by_ticker``). ``compute.main`` rebinds
    each field straight back to a local of the identical name
    (``_cs_yf_market_cap_by_ticker = result._cs_yf_market_cap_by_ticker``),
    so every downstream consumer (the post-loop diagnostic blocks, the
    ``Metadata`` constructor, the Step-13.5 warehouse writer) is unchanged.

    NOT included here (and NOT part of the return contract): accumulators
    read only WITHIN the loop / its immediate post-loop wall-clock block —
    ``detail_count``, ``history_count``, ``fair_price_count``,
    ``_pays_dividend_by_ticker``, ``_payout_ratio_by_ticker`` — nothing in
    ``compute.main`` reads these after the function returns.
    """

    # Issue #287 PR A — Step 8 wall-clock (cross_source umbrella); feeds
    # Metadata.cross_source_wall_clock_seconds.
    cross_source_wall_clock_seconds: float | None
    # The ranking rows + the Step-13.5 warehouse accumulator.
    summaries: list[StockSummary]
    all_details: list[StockDetail]
    # Phase 4b — Metadata.loss_avoidance_size_invariant_firing_count.
    loss_avoidance_size_invariant_firing_count: int
    # Issue #176 — Metadata.share_count_extraction_missing_count.
    share_count_extraction_missing_count: int
    # 0.10.22-phase8pilot — Metadata.fundamentals_unavailable_count.
    fundamentals_unavailable_count: int
    # S&P 1500 Slice 4 — Metadata.low_liquidity_annotate_count.
    low_liquidity_annotate_count: int
    # Issue #177 — Metadata.extreme_estimate_majority_count.
    extreme_estimate_majority_count: int
    # Issue #587 — Metadata.extreme_estimate_majority_lowapp_count.
    extreme_estimate_majority_lowapp_count: int
    # Issue #248 PR2a — Metadata.cross_source_disagreement_count /
    # .cross_source_delta_histogram.
    cross_source_disagreement_count: int
    cross_source_delta_histogram: dict[str, int]
    # Also feeds compute_cross_source_corruption_shadow() post-loop.
    cross_source_delta_by_ticker: dict[str, float | None]
    # PR-1 cross-source corruption shadow side-channel — also feeds
    # compute_cross_source_corruption_shadow() post-loop.
    _cs_yf_market_cap_by_ticker: dict[str, float | None]
    _cs_yf_shares_by_ticker: dict[str, float | None]
    # Issue #177 PR-A — feeds the post-loop median_trim_delta_count
    # blast-radius computation.
    _median_trimmed_by_ticker: dict[str, float]
    # PR-A2 — feeds Metadata.exchange_coverage_pct / .country_coverage_pct.
    exchange_by_ticker: dict[str, str | None]
    country_by_ticker: dict[str, str | None]
    # Dividend signal PR-1 — feeds Metadata.dividend_coverage_pct.
    _dividend_yield_pct_by_ticker: dict[str, float | None]
    # Security-type signal PR-1 — feeds Metadata.security_type_coverage_pct.
    _security_type_by_ticker: dict[str, str | None]
    # Phase 9.4 PR-1 — feeds Metadata.broad_universe_sector_resolved_pct
    # (aggregated ONLY on the broad_investable_us path in compute.main).
    _yf_sector_resolved_by_ticker: dict[str, str | None]
    # Issue #67 — Metadata.value_trap_risk_count_{without,with}_sector_coe
    # (+ the two per-sector breakdown dicts, Q3 cohort-audit visibility).
    value_trap_risk_count_without_sector_coe: int
    value_trap_risk_count_with_sector_coe: int
    # 0.10.32-phase8pilot two-factor shadow counter (now also a structural
    # cross-check of the LIVE two-factor gate per 0.10.34-phase8pilot).
    value_trap_risk_two_factor_shadow_count: int
    value_trap_risk_count_without_sector_coe_by_sector: dict[str, int]
    value_trap_risk_count_with_sector_coe_by_sector: dict[str, int]
    # Phase 4.5e PR 3 — Metadata.insider_sell_cluster_firing_count /
    # .c_suite_unusual_sell_firing_count.
    insider_sell_cluster_firing_count: int
    c_suite_unusual_sell_firing_count: int
    # Phase 4.5e PR 4-eq — Metadata.form4_rule10b5_one_excluded_count.
    form4_rule10b5_one_excluded_count: int
    # Issue #261 — Metadata.multi_class_aggregate_shares_suspected_count.
    multi_class_aggregate_shares_suspected_count: int


class WarningEmitter:
    """Append-with-dedup wrapper around a per-ticker ``valuation_warnings``
    list — the #259 smell-#5 cleanup.

    Consolidates the ~20 ``if "X" not in valuation_warnings:
    valuation_warnings.append("X")`` sites inside :func:`run_per_ticker_loop`
    into a single ``emitter.add("X")`` call. Wraps (never copies) the exact
    list object passed to its constructor, so every later read of
    ``valuation_warnings`` in the same loop iteration — the
    ``StockSummary``/``StockDetail`` construction, the
    ``manipulation_triple_flag`` membership check, ``derive_recommendation``,
    ``derive_loss_chance``, ``compute_manipulation_index`` — sees the exact
    same, in-place-mutated list it always did. This class changes nothing
    about WHERE or WHEN ``valuation_warnings`` is built, reset, or consumed
    — only how each append site is spelled.

    Byte-identical by construction: :meth:`add` performs the exact same two
    operations the pattern it replaces did, in the same order —
    ``if flag not in warnings: warnings.append(flag)`` — so append ORDER is
    untouched (still simple list-append order, first-fired-wins), and
    returns whether a NEW append happened, mirroring the original
    ``"X" not in valuation_warnings`` guard exactly. That return value lets
    counter-coupled call sites whose ORIGINAL counter increment was gated
    by the same dedup check (i.e. only fired on a genuinely new append)
    write ``if <cond> and emitter.add("X"): count += 1`` with no behaviour
    change. Sites whose original counter incremented on every firing of
    ``<cond>`` regardless of dedup outcome do NOT use the return value —
    see the module docstring's "Follow-up cleanup" section.
    """

    __slots__ = ("_warnings",)

    def __init__(self, warnings: list[str]) -> None:
        self._warnings = warnings

    def add(self, flag: str) -> bool:
        """Append ``flag`` to the wrapped list iff not already present.

        Returns True iff this call performed a NEW append (mirrors
        ``if flag not in warnings: warnings.append(flag)`` exactly — same
        check, same order, same mutation).
        """
        if flag not in self._warnings:
            self._warnings.append(flag)
            return True
        return False


def _tally_value_trap(
    rim_result: MethodApplicability,
    sector: str,
    by_sector: dict[str, int],
) -> bool:
    """Issue #67 dual-count tally — the #259 smell-#8 local cleanup.

    Factors out the IDENTICAL 3-line "value-trap-risk skip? bump the
    per-sector dict" block that otherwise appears twice in
    :func:`run_per_ticker_loop` — once after the flat-Ke ``_rim_flat``
    ``check_rim_applicability`` call and once after the sector-Ke
    ``_rim_sector`` call. Those two calls themselves are NOT merged here
    (and must not be — issue #67's flat-vs-sector delta measurement
    needs both; see the caller's comment + the module docstring's
    "Follow-up cleanup" section for why the DEEPER redundancy between
    ``_rim_sector`` and ``compute_fair_price_ensemble``'s internal RIM
    check is intentionally out of scope for this pass).

    Returns True iff ``rim_result`` is the specific
    ``"value_trap_risk_roe_below_cost_of_equity"`` non-applicability
    reason, incrementing ``by_sector[sector]`` as a side effect exactly
    like the inline block did. Does NOT touch the universe-wide scalar
    counter (``value_trap_risk_count_{without,with}_sector_coe``) — the
    caller increments that itself, gated on this function's return value,
    so the two increments stay in lockstep exactly as the original single
    ``if`` block guaranteed.
    """
    if (
        not rim_result.applicable
        and rim_result.reason == "value_trap_risk_roe_below_cost_of_equity"
    ):
        by_sector[sector] = by_sector.get(sector, 0) + 1
        return True
    return False


def run_per_ticker_loop(
    *,
    df: pd.DataFrame,
    snapshots: dict[str, FundamentalsSnapshot | None],
    pillar_df: pd.DataFrame,
    risk_flags: dict[str, list[str]],
    beneish_results: dict[str, BeneishResult],
    dechow_results: dict[str, DechowResult],
    rem_results: dict[str, REMResult],
    post_split_results: dict[str, PostSplitResult],
    tier2_results: dict[str, Tier2Result],
    histories: dict[str, pd.DataFrame],
    historical_metrics: dict[str, dict[str, float | list[float] | None]],
    universe_metrics: dict[str, dict[str, float | None]],
    by_sector: dict[str, list[str]],
    by_sub_industry: dict[str, list[str]],
    broad_ex_fin_util: list[str],
    adv_by_ticker: dict[str, float | None],
    prices_by_ticker: dict[str, pd.DataFrame],
    imputed_by_ticker: dict[str, list[str]],
    sector_pillar_baselines: dict[str, dict],
    form4_diagnostics: dict[str, dict],
    osap_signal_map: dict[str, dict[str, float] | None],
    composite_osap_adjusted: pd.Series,
    cohort_by_ticker: dict[str, str],
    memberships_by_ticker: dict[str, list[str]],
    multi_class_flagged_tickers: set[str],
    entered: set[str],
    exited: set[str],
    asof_date: date,
    now: datetime,
    filing_lag_fn: Callable[[FundamentalsSnapshot | None, date], int | None],
    build_raw_metrics_fn: Callable[..., RawMetrics],
) -> PerTickerLoopResult:
    """Run the Step-8 combined per-ticker loop: fair-price ensemble +
    price-history write + ``StockSummary`` + ``StockDetail``.

    Single pass so per-ticker outputs stay synchronized (e.g. ``has_history``
    reflects the actual write result; ensemble warnings flow into both the
    summary and the detail consistently). See the module docstring's "R7b"
    section for the byte-identical guarantee and the ``filing_lag_fn`` /
    ``build_raw_metrics_fn`` injection rationale.

    Parameters
    ----------
    df:
        Ranked universe DataFrame (post Step-6 sort/rank assignment).
        Iterated via ``df.iterrows()``.
    snapshots:
        Ticker -> ``FundamentalsSnapshot | None`` (Step 2).
    pillar_df:
        Per-ticker pillar-score DataFrame (post ``neutralize_pillar_scores``).
    risk_flags:
        Ticker -> list of active ``risk_flags`` from ``compute_risk_flags``
        (Step 5). MUTATED in place — the ensemble's ``extra_flags`` (e.g. a
        Tier-1 defense flag) are merged into this dict during the loop, and
        ``post_split_share_lag_unreconciled`` / other pre-existing flags are
        read back within the same and later iterations. Nothing in
        ``compute.main`` reads ``risk_flags`` again after this function
        returns, so it is not part of :class:`PerTickerLoopResult` — the
        mutation is visible to the caller purely because dicts are passed
        by reference.
    beneish_results, dechow_results:
        Ticker -> cached ``compute_beneish`` / ``compute_dechow_f`` results
        (pre-computed in Step 5, ahead of the risk-flag pass).
    rem_results:
        Ticker -> ``compute_rem_flags`` result (Roychowdhury 2006 REM).
    post_split_results:
        Ticker -> Step-3b post-split share-lag detection result (``tier``
        0/1/2). Only present for tickers a recent-split scan matched.
    tier2_results:
        Ticker -> Step-4b Tier-2 event-defense result (going-concern /
        non-reliance / auditor-change).
    histories:
        Ticker -> annual-history DataFrame (Step 3).
    historical_metrics:
        Ticker -> ``{eps_3y_avg, avg_3y_roe, fcf_5y}`` (Step 5b).
    universe_metrics:
        Ticker -> ``{pe_ttm, pb_reported, ev_ebitda_ttm}`` peer-comparable
        ratios (Step 5b) — feeds both the fair-price ensemble's peer walk
        and the two-factor ``value_trap_risk`` sector-median P/E check.
    by_sector, by_sub_industry, broad_ex_fin_util:
        Peer groupings (Step 5b) for the fair-price ensemble's tiered
        panel walk.
    adv_by_ticker:
        Ticker -> trailing-30d mean dollar volume (Step 1); drives the
        ``low_liquidity`` annotate.
    prices_by_ticker:
        Ticker -> OHLCV DataFrame (Step 1) — sliced for the price-history
        JSON write; no new fetches.
    imputed_by_ticker:
        Ticker -> list of pillar names that were NaN-imputed
        (``neutralize_pillar_scores``) — feeds ``DataQuality.imputed_metrics``.
    sector_pillar_baselines:
        Sector -> per-sector pillar-median dict (Step 5c) for the
        stock-detail baseline overlay.
    form4_diagnostics:
        Ticker -> Form-4 fetch diagnostic dict (``fetch_status``,
        ``insider_count``, ...). Only tickers with ``fetch_status == "ok"``
        are consulted for the insider-cluster annotates (the pre-merge-
        prod-sim ``FORM4_FETCH_SKIP`` gate).
    osap_signal_map:
        Ticker -> OSAP per-signal value dict (Phase 4h), or ``None``.
    composite_osap_adjusted:
        Composite score blended with the accepted OSAP signals (indexed by
        ticker) — read for ``StockDetail.osap_blended_score`` only.
    cohort_by_ticker:
        Ticker -> ``"sp500" | "sp400" | "sp600"`` (from
        ``build_ticker_membership_maps``) for ``index_membership``.
    memberships_by_ticker:
        Ticker -> list of index tags (from ``build_ticker_membership_maps``)
        for ``index_memberships``.
    multi_class_flagged_tickers:
        CIK-collision set (from ``build_ticker_membership_maps``) driving
        the ``multi_class_aggregate_shares_suspected`` annotate.
    entered, exited:
        Step-7 Top-5 rotation sets — drive ``entered_top5`` / ``exited_top5``.
    asof_date:
        The run's as-of ``date`` (hoisted before Step 6b in
        ``compute.main``) — passed to every filing-lookback helper.
    now:
        The run's as-of ``datetime`` (UTC) — passed to
        ``_build_data_quality`` for the filing-lag display field.
    filing_lag_fn:
        ``compute.main._filing_lag`` injected as a callable. Kept in
        ``compute.main`` (used both here and by the separate Step-6b
        stale-filing pre-scan, and directly imported by
        ``tests/test_main.py``) rather than moved — see the module
        docstring's "R7b" section.
    build_raw_metrics_fn:
        ``compute.main._build_raw_metrics`` injected as a callable. Kept in
        ``compute.main`` for the same reason (also directly imported by
        ``tests/test_main.py`` and ``tests/test_ingest/test_issue374_ratifyb.py``).

    Returns
    -------
    PerTickerLoopResult
        Every accumulator ``compute.main`` reads after the loop. See that
        dataclass's docstring for the full field list + what feeds what.
    """
    # Step 8 — combined per-ticker loop: fair-price ensemble + price history
    # write + StockSummary + StockDetail. Single pass so per-ticker outputs
    # stay synchronized (e.g., has_history reflects the actual write result;
    # ensemble warnings flow into both summary and detail consistently).
    # Issue #287 PR A — wall-clock for the entire Step 8 loop. Documented
    # limitation: this includes fair-price ensemble + manipulation_index
    # + StockDetail write — not just the cross_source_validate_market_cap
    # sub-call. On cold-cache cross-source (502 × 2-8s serial yfinance.info
    # = 17-67 min) the sub-call dominates; on warm cache the other Step 8
    # work (~50s total) dominates.
    _cross_source_wc_start = time.monotonic()
    cross_source_wall_clock_seconds: float | None = None
    summaries: list[StockSummary] = []
    all_details: list[StockDetail] = []  # Step 13.5 warehouse accumulator
    detail_count = 0
    history_count = 0
    fair_price_count = 0
    # Phase 4b — observability surface for the new Roychowdhury 2006
    # size-invariant loss-avoidance annotate. Counter increments inside
    # the per-ticker loop when the flag is appended to valuation_warnings;
    # written to Metadata.loss_avoidance_size_invariant_firing_count so
    # the next cron's firing rate is visible without grepping per-stock
    # JSONs (Rule 18 observability-before-wiring).
    loss_avoidance_size_invariant_firing_count: int = 0
    # Issue #176 — same Rule 18 observability surface for the new
    # ``share_count_extraction_missing`` annotate. Counter increments
    # inside the per-ticker loop when the flag is appended to
    # valuation_warnings; written to
    # Metadata.share_count_extraction_missing_count so the universe-
    # wide firing rate of the STZ-style partial-XBRL-extraction pattern
    # is visible at-a-glance from the next cron without grepping
    # per-stock JSONs.
    share_count_extraction_missing_count: int = 0
    # OZK/PBF flip-blocker (0.10.22-phase8pilot) — Rule 18 observability
    # surface for the new ``fundamentals_unavailable`` direct veto. Counter
    # increments when ``snap is None`` (complete EDGAR ingest failure) inside
    # the per-ticker loop. Written to Metadata.fundamentals_unavailable_count
    # so a non-zero value on a production sp500 cron is immediately visible
    # as a data-pipeline health signal without grepping per-stock JSONs.
    fundamentals_unavailable_count: int = 0
    # S&P 1500 Slice 4 — ADV liquidity backstop (defense layer 36,
    # 0.10.29-phase8pilot, Rule 18 observability-before-wiring).
    # Counter increments inside the per-ticker loop when the
    # ``low_liquidity`` annotate fires (``average_dollar_volume is not None
    # and average_dollar_volume < config.ADV_FLOOR_USD``). Written to
    # Metadata.low_liquidity_annotate_count so the universe-wide firing
    # rate is visible from the first cron without grepping per-stock JSONs.
    # Expected base rate for S&P 900: near-zero (large-caps all clear
    # $5M/day comfortably); the counter is designed for S&P 1500 small-cap
    # exposure where thinly-traded names may appear.
    low_liquidity_annotate_count: int = 0
    # Issue #177 — same Rule 18 observability surface for the new
    # ``extreme_estimate_majority`` annotate. The flag itself is
    # appended by ``compute.valuation.ensemble`` when ≥
    # ``config.EXTREME_MAJORITY_THRESHOLD`` of the 6 methods fire
    # Defense #4 outlier guard; this counter increments here when the
    # flag is observed on the ensemble's ``valuation_warnings`` list.
    # Written to Metadata.extreme_estimate_majority_count so the next
    # cron's firing rate (gates the follow-up median-exclusion PR per
    # methodology-scientist Mode B 2026-05-21) is visible at-a-glance.
    extreme_estimate_majority_count: int = 0
    # Issue #587 (0.10.32-phase8pilot) — Rule 18 delta counter for the
    # low-applicability floor recalibration. Counts tickers that fire
    # ``extreme_estimate_majority`` via the new low-applicability floor ONLY
    # (n_applicable ≤ LOWAPP_MAX AND n_extreme ≥ LOWAPP_MIN AND strict-majority)
    # but would NOT have fired under the old 3-of-6 baseline rule. This is
    # the delta population (pre-measured: 16 tickers on cron 8c89a5af0).
    # Relies on EnsembleResult.extreme_majority_lowapp set in the ensemble.
    extreme_estimate_majority_lowapp_count: int = 0
    # Issue #248 PR2a (0.10.3-phase4.5e) — Rule 18 observability for the
    # cross-source market-cap validator. Counter + histogram + per-ticker
    # delta all populated from the validator's tuple-return refactor
    # (`compute/ingest/cross_source.validate_market_cap` now returns
    # ``(disagreement: bool, delta: float | None)``). Histogram buckets
    # init to zero across all 9 keys so the schema-snapshot key set is
    # stable even on a no-fire run.
    cross_source_disagreement_count: int = 0
    cross_source_delta_histogram: dict[str, int] = {
        key: 0 for key in CROSS_SOURCE_BUCKET_KEYS
    }
    cross_source_delta_by_ticker: dict[str, float | None] = {}
    # PR-1 cross-source corruption shadow — per-ticker yfinance data collected
    # as a zero-cost side-channel in the Step 8 loop.  Both values are already
    # in the 24h on-disk cache from the validate_market_cap + Step 3b calls
    # earlier this run (pure cache reads at this point — no new network call).
    # Consumed after the loop by compute_cross_source_corruption_shadow().
    _cs_yf_market_cap_by_ticker: dict[str, float | None] = {}
    _cs_yf_shares_by_ticker: dict[str, float | None] = {}
    # Issue #177 PR-A (0.10.24-phase8pilot) — per-ticker shadow trimmed
    # median cache. Populated in the Step 8 per-ticker loop alongside the
    # ensemble computation; consumed after the loop to compute the
    # universe-wide blast-radius metric ``median_trim_delta_count``. Only
    # entries where ensemble.median_trimmed is not None are stored.
    _median_trimmed_by_ticker: dict[str, float] = {}
    # PR-A2 — listing-metadata wiring (StockDetail.exchange / .country).
    # Display-mapped exchange name + derived country, one entry per ticker
    # iterated in Step 8. Skip-safe: fetch_yfinance_exchange honors
    # QR_SKIP_CROSS_SOURCE internally (returns None on cold simulate cache).
    exchange_by_ticker: dict[str, str | None] = {}
    country_by_ticker: dict[str, str | None] = {}
    # Dividend signal PR-1 (roadmap item #5 / 7a, 0.10.27-phase8pilot,
    # Rule 18 observability-first) — per-ticker dividend data collected as
    # a zero-cost side-channel in the Step 8 loop.  All three fields derive
    # from a pure cache-read off the ``yfinance_info/<ticker>.json`` file
    # already populated by ``fetch_yfinance_market_cap`` earlier in the
    # same ticker iteration.  No new network round-trips.
    # Post-loop: aggregate ``dividend_coverage_pct`` from the non-None
    # ``dividend_yield_pct`` values across all tickers.
    _dividend_yield_pct_by_ticker: dict[str, float | None] = {}
    _pays_dividend_by_ticker: dict[str, bool | None] = {}
    _payout_ratio_by_ticker: dict[str, float | None] = {}
    # Security-type signal PR-1 (roadmap item #5 / 7b, 0.10.30-phase8pilot,
    # Rule 18 observability-first) — per-ticker security_type label collected
    # as a zero-cost side-channel in the Step 8 loop.  Derives from a pure
    # cache-read off ``yfinance_info/<ticker>.json``; the ``quote_type`` key
    # is written during ``fetch_yfinance_exchange``'s live fast_info call
    # (earlier in the same ticker iteration — no new network round-trips).
    # Post-loop: aggregate ``security_type_coverage_pct`` from the non-None
    # values (same formula as ``dividend_coverage_pct`` / ``exchange_coverage_pct``).
    _security_type_by_ticker: dict[str, str | None] = {}
    # Phase 9.4 PR-1 sector-resolution coverage canary (observability-only,
    # Rule 18) — per-ticker GICS-mapped sector collected as a zero-cost
    # side-channel in the Step 8 loop.  Derives from a pure cache-read off
    # ``yfinance_info/<ticker>.json`` (populated by ``fetch_yfinance_market_cap``
    # earlier in the same ticker iteration) followed by
    # ``map_yfinance_sector_to_gics``.  Collected on EVERY universe path
    # (zero-cost — no new network round-trip) but only AGGREGATED into a
    # ``Metadata`` field on the ``broad_investable_us`` ranked path in
    # ``compute.main`` — see that module's Phase 9.4 PR-1 canary comment for
    # the full Rule-18 constraint (this dict is NEVER used to set a scored
    # ticker's ``sector`` field, never read by scoring/composite/pillar/
    # veto/fair-price/select_picks).
    _yf_sector_resolved_by_ticker: dict[str, str | None] = {}
    # Issue #67 — Rule 18 observability surface for sector-adjusted CoE.
    # Both counts are computed on EVERY cron regardless of USE_SECTOR_COE
    # so the delta (flat-10% vs per-sector) is observable before the flag
    # is flipped.  ``_without_sector_coe`` = baseline (ROE ≤ flat 0.10);
    # ``_with_sector_coe`` = count under SECTOR_COST_OF_EQUITY dict lookup.
    # See compute/scoring/cost_of_equity.py for the Damodaran 2019 table.
    value_trap_risk_count_without_sector_coe: int = 0
    value_trap_risk_count_with_sector_coe: int = 0
    # Two-factor value_trap_risk shadow counter (0.10.32-phase8pilot, Rule 18).
    # Shadow gate: fires iff (a) live ROE≤Ke fires AND (b) eps_ttm > 0 AND
    # (c) ticker P/E < sector-peer median P/E.  Live warnings are UNCHANGED.
    value_trap_risk_two_factor_shadow_count: int = 0
    # Issue #67 follow-up (0.10.10-phase4.6) — per-sector breakdown of the
    # same counts, keyed by GICS sector name. Methodology-scientist Q2
    # verdict 2026-05-28 (deferred from PR #294) requested this for
    # Q3 2026-08-19 quarterly cohort audit visibility — confirms the
    # Damodaran 2019 Ch. 8.4 shape (lower-Ke sectors drop flags, higher-
    # Ke sectors gain flags) before ≥ 12 cron weeks of post-flip data
    # accumulate. The delta is computed below at Metadata-construction
    # time as `_without - _with` per sector.
    value_trap_risk_count_without_sector_coe_by_sector: dict[str, int] = {}
    value_trap_risk_count_with_sector_coe_by_sector: dict[str, int] = {}
    # Phase 4.5e PR 3 — Rule 18 observability for the new Form-4 annotates.
    # Counters increment inside the per-ticker loop when the flag is
    # appended to valuation_warnings; written to
    # Metadata.insider_sell_cluster_firing_count +
    # Metadata.c_suite_unusual_sell_firing_count so the first cron with
    # the flags wired shows the universe-wide firing rate at-a-glance.
    # Gates the methodology-scientist Q3 2026-08-19 cohort-acceptance
    # check that may promote INSIDER_SELL_CLUSTER_WEIGHT from 5.0 → 10.0.
    insider_sell_cluster_firing_count: int = 0
    c_suite_unusual_sell_firing_count: int = 0
    # Phase 4.5e PR 4-eq — Rule 18 observability for the 10b5-1
    # contamination filter applied in _is_opportunistic_sell. Counts
    # the universe-wide total of transactions excluded by the filter
    # (would have been opportunistic absent the gate) — the empirical
    # lever for the methodology-scientist Q3 2026-08-19 cohort-
    # acceptance check (issue #130). Expected delta vs PR #222 baseline:
    # -30% to -45% on insider_sell_cluster_firing_count per
    # Jagolinzer 2009 §3.2 + SEC 2022 economic analysis.
    form4_rule10b5_one_excluded_count: int = 0
    multi_class_aggregate_shares_suspected_count: int = 0
    for _, r in df.iterrows():
        ticker = str(r["ticker"])
        snap = snapshots.get(ticker)
        current_price = float(r["current_price"])
        sector = str(r["sector"])
        sub_industry_raw = r.get("industry")
        sub_industry = (
            str(sub_industry_raw)
            if sub_industry_raw is not None and pd.notna(sub_industry_raw)
            else None
        )
        pillar_row = pillar_df.loc[ticker] if ticker in pillar_df.index else pd.Series(dtype=float)

        # OZK/PBF flip-blocker (0.10.22-phase8pilot) — Rule 18 counter for
        # the ``fundamentals_unavailable`` direct veto.  Extended from the
        # original snap-is-None-only check to also count the "empty-snap"
        # case (FDXF fix): snap is NOT None but ALL 34 tracked metrics are
        # null (EDGAR returned a Company object but the filer has no
        # financial history yet).  Both cases fire the flag in
        # compute_risk_flags; the counter must agree so
        # Metadata.fundamentals_unavailable_count reflects the true
        # universe-wide "no usable fundamentals" count (OZK + FDXF = 2 on
        # the #107 sp900 run).
        if snap is None or _snapshot_has_no_usable_fundamentals(snap):
            fundamentals_unavailable_count += 1

        # Fair-price ensemble (skipped when snapshot is missing — without
        # fundamentals there's no input to any of the 6 methods).
        ensemble: EnsembleResult | None = None
        ensemble_dict: dict | None = None
        valuation_warnings: list[str] = []
        tbvps_value: float | None = None
        if snap is not None:
            tbvps_value = tangible_book_value_per_share(snap)
            sub_panel = (
                [t for t in by_sub_industry.get(sub_industry, []) if t != ticker]
                if sub_industry is not None
                else []
            )
            sector_panel = [t for t in by_sector.get(sector, []) if t != ticker]
            broad_panel = [t for t in broad_ex_fin_util if t != ticker]
            tier_panel = {
                "sub_industry": sub_panel,
                "industry": [],  # GICS level-2 not parsed; falls through to sector
                "sector": sector_panel,
                "broad": broad_panel,
            }
            peer_panels = {
                "pe": tier_panel,
                "pb": tier_panel,
                "ev_ebitda": tier_panel,
            }
            ensemble, extra_flags = compute_fair_price_ensemble(
                ticker=ticker,
                snap=snap,
                sector=sector,
                sub_industry=sub_industry,
                industry=None,
                current_price=current_price,
                filing_lag_days_value=filing_lag_fn(snap, asof_date),
                peer_panels=peer_panels,
                universe_metrics=universe_metrics,
                historical_metrics=historical_metrics,
            )
            ensemble_dict = ensemble_result_to_dict(ensemble)
            valuation_warnings = list(ensemble.valuation_warnings)
            # Issue #177 PR-A — cache shadow trimmed median for the
            # post-loop blast-radius computation (median_trim_delta_count).
            if ensemble.median_trimmed is not None:
                _median_trimmed_by_ticker[ticker] = ensemble.median_trimmed
            if extra_flags:
                merged = list(risk_flags.get(ticker, []))
                for f in extra_flags:
                    if f not in merged:
                        merged.append(f)
                risk_flags[ticker] = merged
            if ensemble.median is not None or ensemble.max is not None:
                fair_price_count += 1

        # #259 smell-#5 cleanup — wrap the per-ticker valuation_warnings
        # list (just settled above to either [] or the ensemble-seeded
        # list) in a WarningEmitter so every dedup-then-append site below
        # can call emitter.add(flag) instead of repeating "flag not in
        # valuation_warnings: valuation_warnings.append(flag)". MUST be
        # constructed HERE, after the `if snap is not None:` block above,
        # not before it: valuation_warnings is REBOUND (not mutated) to a
        # NEW list object at `valuation_warnings = list(ensemble.valuation_warnings)`
        # when a snapshot exists, so an emitter built earlier would wrap a
        # stale list once that rebind happens. Wrapping the settled,
        # already-seeded list means every emitter.add() dedup check below
        # correctly accounts for any warnings compute_fair_price_ensemble
        # already emitted — exactly what the original per-site
        # "flag not in valuation_warnings" checks tested against.
        emitter = WarningEmitter(valuation_warnings)

        # Issue #262 (2026-05-26) — writer-parity for the input-level
        # ``data_quality_input_corruption`` veto. When the veto fires
        # in ``risk_flags`` (input-level corruption per
        # ``compute/scoring/risk_overlay.py::_data_quality_input_corruption``:
        # TBVPS > $10K/share / TTM revenue < $50M / |NI| > |revenue|),
        # ALSO append the parallel ``valuation_output_anomalous``
        # annotate to ``valuation_warnings`` so the UI surface
        # (``FairPriceCard.tsx``) renders the explanation chip for the
        # all-null fair-price ensemble. Closes the veto-only-cohort
        # UI explainability gap surfaced by methodology-scientist
        # Mode B 2026-05-26 — 4 tickers (MTB / CPT / MRNA / HBAN on
        # the 2026-05-23 cron #3) carried the veto but had no UI
        # annotate because the ensemble-layer Site-2 check didn't
        # additionally fire. Composite rank UNCHANGED — the veto
        # surface already handles Top-5 suppression; this only adds
        # the annotate for UI parity.
        if "data_quality_input_corruption" in risk_flags.get(ticker, []):
            emitter.add("valuation_output_anomalous")

        # Post-split share-lag defense (defense layer 35).
        #
        # Tier-1 ANNOTATE (post_split_results tier==1, NOT in risk_flags):
        #   shares were already corrected in Step 3b; add a transparency
        #   valuation_warning so the UI surface shows the adjustment.
        #   Tier-1 is routed through valuation_warnings ONLY — routing it
        #   through risk_flags was a double-penalty bug (PR-2 fix 2026-06-18):
        #   the Step-7 Top-5 rotation skips any ticker with non-empty
        #   risk_flags, so a Tier-1-corrected stock (data IS correct) was
        #   being silently excluded from entered_top5.  All other annotates
        #   in the defense layer use valuation_warnings for the same reason.
        #
        # Tier-2 VETO (post_split_share_lag_unreconciled in risk_flags):
        #   the fair-price ensemble is nulled — same contract as DQIC
        #   (computed but untrustworthy because we couldn't determine the
        #   correct share count).  Append valuation_output_anomalous for
        #   UI parity (FairPriceCard.tsx renders the explanation chip).
        _ticker_flags = set(risk_flags.get(ticker) or [])
        _psr_for_ticker = post_split_results.get(ticker)
        if _psr_for_ticker is not None and _psr_for_ticker.tier == 1:
            # Emit the canonical flag key so flagLabel('post_split_share_lag')
            # resolves to 'Post-split share count adjusted' on the FairPriceCard.
            # The structured key is the only valuation_warnings entry for this
            # path — free-text ratio/date detail was removed (#552) because it
            # produced an unregistered, unparseable literal that rendered as a
            # duplicate "Pending Edgar Refresh" chip via flagLabel()'s Title-Case
            # fallback.  A structured post_split_event field is the future path
            # for surfacing that detail (not this PR).
            emitter.add("post_split_share_lag")
        if "post_split_share_lag_unreconciled" in _ticker_flags:
            # Null the ensemble (unreconciled split → fair price untrustworthy).
            ensemble = None
            ensemble_dict = None
            emitter.add("valuation_output_anomalous")

        # Beneish M-score (PR 3e.1 ANNOTATE at M > -2.22 + PR 4.5a.2
        # soft-veto promotion at M > -1.78). The active-veto path is
        # already wired into ``risk_flags`` above via
        # ``beneish_m_scores`` injection; this block keeps the
        # ``beneish_high`` annotate (M > -2.22 band) on
        # `valuation_warnings` and the numeric m_score on StockDetail
        # for transparency. Cached from the pre-compute pass to avoid
        # recomputing the 8-ratio model twice per ticker.
        beneish_result = beneish_results[ticker]
        if beneish_result.is_high:
            emitter.add("beneish_high")

        # Dechow F-score (PR 3e.2 ANNOTATE at F > 2.45 + PR 4.5a.3
        # soft-veto promotion at F > 3.0). Active-veto path is wired
        # into ``risk_flags`` above via ``dechow_f_scores`` injection;
        # this block keeps the ``dechow_high`` annotate (F > 2.45 band)
        # on `valuation_warnings`. Cached from pre-compute pass.
        dechow_result = dechow_results[ticker]
        if dechow_result.is_high:
            emitter.add("dechow_high")

        # PR 4.5a.3 — `manipulation_triple_flag` joint-gate badge.
        # Fires when Sloan (cross-sectional or sector-relative)
        # AND Beneish annotate AND Dechow annotate all fire on the
        # SAME ticker. Rare but high-confidence — typically 0-3
        # tickers per universe. UI-only badge in `valuation_warnings`;
        # does NOT add a third veto on top of the individual vetoes
        # already doing that work. Per PR #86 plan §4.5a.3.
        ticker_risk = set(risk_flags.get(ticker) or [])
        if (
            "sloan_accruals_top_decile" in ticker_risk
            and "beneish_high" in valuation_warnings
            and "dechow_high" in valuation_warnings
        ):
            emitter.add("manipulation_triple_flag")

        # Cross-source market-cap validator (PR 4b §1 + PR2a Issue #248
        # tuple-return refactor 0.10.3). Compares SEC-derived market cap
        # (shares × current_price) vs yfinance .info marketCap. Delta > 5%
        # surfaces as ``cross_source_disagreement`` annotate. Catches
        # yfinance scraper drift (pre-split share counts, intraday vs EOD,
        # M&A ticker rotation) AND multi-class XBRL extraction failures
        # (V/Visa Class A-only, FOXA, NWS/NWSA — issue #248). The delta
        # is now ALSO recorded per-ticker (StockDetail.cross_source_delta)
        # and aggregated into a universe histogram
        # (Metadata.cross_source_delta_histogram) for PR2b severe-threshold
        # calibration per methodology-scientist Mode B verdict 2026-05-25.
        disagreement, csd_delta = cross_source_validate_market_cap(
            ticker=ticker,
            snap=snap,
            current_price=current_price,
        )
        cross_source_delta_by_ticker[ticker] = csd_delta
        cross_source_delta_histogram[cross_source_bucket_delta(csd_delta)] += 1
        if disagreement:
            # OUTSIDE-count: the counter is tied to `disagreement`, NOT the
            # dedup — do NOT fold into `if disagreement and emitter.add(...)`
            # (that would suppress the count on an ensemble-seeded flag). See
            # the module docstring "Follow-up cleanup" note.
            cross_source_disagreement_count += 1
            emitter.add("cross_source_disagreement")

        # PR-1 cross-source corruption shadow — cache-read side-channel.
        # Both fetch_yfinance_market_cap and fetch_yfinance_shares_outstanding
        # are pure cache reads at this point (the cache was already primed
        # either by Step 3b or by the validate_market_cap call above which
        # calls fetch_yfinance_market_cap internally).  No new network call.
        _cs_yf_market_cap_by_ticker[ticker] = fetch_yfinance_market_cap(ticker)
        _cs_yf_shares_by_ticker[ticker] = fetch_yfinance_shares_outstanding(ticker)

        # PR-A2 — listing metadata (display-only; no scoring/ranking impact).
        # Piggybacks the cross_source yfinance loop; skip-safe via
        # QR_SKIP_CROSS_SOURCE inside fetch_yfinance_exchange.
        exchange_code = fetch_yfinance_exchange(ticker)
        exchange_by_ticker[ticker] = exchange_name(exchange_code)
        country_by_ticker[ticker] = country_for_exchange(exchange_code)

        # Dividend signal PR-1 (roadmap item #5 / 7a, 0.10.27-phase8pilot,
        # Rule 18 observability-first) — pure cache-read; no new network call.
        # The ``yfinance_info/<ticker>.json`` cache was already populated
        # (with dividend_yield_pct + payout_ratio) by ``fetch_yfinance_market_cap``
        # earlier in this loop iteration.  Wrapped in try/except so any
        # unexpected failure is non-fatal — fields remain None and the cron
        # continues unchanged.  Rankings/scores/vetoes are NOT touched.
        try:
            _dy_pct, _pays_div, _pr = fetch_yfinance_dividend(ticker)
        except Exception as _div_exc:  # noqa: BLE001
            logger.debug(
                "fetch_yfinance_dividend failed for %s (non-fatal): %s",
                ticker, _div_exc,
            )
            _dy_pct, _pays_div, _pr = None, None, None
        _dividend_yield_pct_by_ticker[ticker] = _dy_pct
        _pays_dividend_by_ticker[ticker] = _pays_div
        _payout_ratio_by_ticker[ticker] = _pr

        # Security-type signal PR-1 (roadmap item #5 / 7b, 0.10.30-phase8pilot,
        # Rule 18 observability-first) — pure cache-read; no new network call.
        # The ``yfinance_info/<ticker>.json`` cache was already populated
        # (with quote_type) by ``fetch_yfinance_exchange`` earlier in this
        # loop iteration.  Wrapped in try/except so any unexpected failure
        # is non-fatal — field remains None and the cron continues unchanged.
        # Rankings/scores/vetoes are NOT touched.
        try:
            _sec_type = fetch_yfinance_security_type(ticker)
        except Exception as _sec_type_exc:  # noqa: BLE001
            logger.debug(
                "fetch_yfinance_security_type failed for %s (non-fatal): %s",
                ticker, _sec_type_exc,
            )
            _sec_type = None
        _security_type_by_ticker[ticker] = _sec_type

        # Phase 9.4 PR-1 sector-resolution coverage canary (observability-
        # only, Rule 18) — pure cache-read; no new network call. The
        # ``yfinance_info/<ticker>.json`` cache was already populated (with
        # ``sector``) by ``fetch_yfinance_market_cap`` earlier in this loop
        # iteration. Wrapped in try/except so any unexpected failure is
        # non-fatal — field remains None and the cron continues unchanged.
        # Stores the GICS-MAPPED value (or None if unmapped/absent) — the
        # scored ticker's ``sector`` column is NOT touched here or anywhere
        # else this PR (see compute/main.py's Phase 9.4 PR-1 canary comment).
        try:
            _yf_sector_resolved_by_ticker[ticker] = map_yfinance_sector_to_gics(
                fetch_yfinance_sector(ticker)
            )
        except Exception as _sector_exc:  # noqa: BLE001
            logger.debug(
                "fetch_yfinance_sector failed for %s (non-fatal): %s",
                ticker, _sector_exc,
            )
            _yf_sector_resolved_by_ticker[ticker] = None

        # Issue #261 — multi_class_aggregate_shares_suspected annotate.
        # CIK-collision detector (precomputed before this loop) flags
        # tickers from multi-class issuers where the SEC companyfacts
        # API returns the AGGREGATE share count rather than the per-
        # class breakdown — the GOOG/GOOGL overcount pattern (opposite
        # direction to the PR #257 allowlist which corrects undercount
        # via per-filing XBRL dimensional sum). Annotate-only —
        # composite rank unchanged; surfaces the structural pattern
        # for Q3 2026-08-19 quarterly-audit cohort visibility while
        # PR-B (reverse-allowlist per-class XBRL extraction) lands as
        # the structural fix.
        if ticker in multi_class_flagged_tickers:
            # OUTSIDE-count: counter tied to the membership test, NOT the dedup
            # — keep the plain `emitter.add(...)`; do NOT fold into the `and
            # emitter.add(...)` guard (module docstring "Follow-up cleanup").
            multi_class_aggregate_shares_suspected_count += 1
            emitter.add("multi_class_aggregate_shares_suspected")

        # PR 4.5b §1 — restatement_history annotate. 10-K/A or 10-Q/A
        # filings in the trailing 5 years from SEC EDGAR. Hennes-Leone-
        # Miller 2008 *TAR* — restating firms see -9% abnormal return
        # on announcement; recurrent restaters compound the effect.
        # ANNOTATE-only (sector-agnostic base rate, no veto).
        restatement_result = check_restatement_history(ticker, asof=asof_date)
        if restatement_result.fired:
            emitter.add("restatement_history")

        # Epic #150 Phase 2.2 — restatement_high_confidence annotate.
        # Co-occurrence of a 10-K/A or 10-Q/A amendment with an 8-K
        # Item 4.02 (non-reliance) filing within 90 days. Hennes-Leone-
        # Miller 2008 *TAR* "irregularity" signature — PPV ~70% vs
        # bare `restatement_history`'s ~30%. Annotate path (lands in
        # `valuation_warnings`, not `risk_flags`): composite-rank
        # source stays raw composite per SKILL.md Rule 16, but the
        # flag contributes to `manipulation_index` (delta +3.0 on top
        # of bare flag's +5.0 → 8.0 total when both fire), which
        # feeds the 10-pt-max soft penalty into `composite_score_adjusted`
        # on the detail-page Manipulation Risk card. Existing
        # `restatement_history` semantics + weight unchanged in this
        # PR (Phase 2.2 follow-up will decide whether to retire the
        # bare flag after a cohort acceptance check).
        amendment_dates = get_amendment_filing_dates(ticker, asof=asof_date)
        non_reliance_dates = get_non_reliance_filing_dates(ticker, asof=asof_date)
        high_conf_result = compute_high_confidence_restatement(
            amendment_dates, non_reliance_dates
        )
        if high_conf_result.fired:
            emitter.add("restatement_high_confidence")

        # PR 4.5b §2 — late_filing_notification annotate. SEC Form
        # 12b-25 (NT 10-K / NT 10-Q) within the trailing 365 days.
        # Bartov-Lai-Yeung 2002 *JAR* — late filers see -5-7%
        # abnormal returns. ANNOTATE-only.
        late_filing_result = check_late_filing(ticker, asof=asof_date)
        if late_filing_result.fired:
            emitter.add("late_filing_notification")

        # PR 4.5c — Roychowdhury 2006 REM. `rem_suspect` annotate
        # fires when 2 of 3 abnormal proxies (CFO, production,
        # discretionary expenses) sit in their respective worst
        # decile within sector. Results pre-computed above; this is
        # just the per-ticker append. Catches REAL manipulation —
        # cutting R&D, channel stuffing, deferring maintenance —
        # invisible to Sloan/Beneish/Dechow accrual targets.
        rem_result = rem_results.get(ticker)
        if rem_result is not None and rem_result.fired:
            emitter.add("rem_suspect")

        # PR 4.5d §1 — accruals_momentum_high annotate.
        # Δ(TATA = (NI − CFO)/TA) over trailing 3 fiscal years.
        # Threshold +0.05 ≈ Beneish 1999 ΔM > +0.5 via the β_TATA
        # coefficient. Catches manipulation gathering steam — the
        # snapshot-only Sloan + Beneish flags miss the trajectory.
        accruals_mom = check_accruals_momentum(snap, histories.get(ticker))
        if accruals_mom.fired:
            emitter.add("accruals_momentum_high")

        # PR 4.5d §2 — loss_avoidance_pattern annotate.
        # Burgstahler-Dichev 1997 *JAE* kink at zero. 3+ consecutive
        # fiscal years of tiny-positive NI (∈ [0, $50M]) OR tiny-
        # positive EPS (∈ [0, $0.50]) = managers shading reported
        # earnings just enough to clear the loss threshold. (Phase
        # 2.4 of epic #150 rescaled the bands 10× for S&P 500 scale.)
        loss_avoid = check_loss_avoidance(snap, histories.get(ticker))
        if loss_avoid.fired:
            emitter.add("loss_avoidance_pattern")

        # Phase 4b — loss_avoidance_pattern_size_invariant annotate.
        # Roychowdhury 2006 *JAE* §5.2 suspect-firm definition:
        # NI / TotalAssets ∈ [0, 0.005] for 3+ consecutive fiscal years.
        # Size-invariant sibling of the absolute-$ variant above; catches
        # chronically thin-margin large caps the BD 1997 dollar band misses.
        loss_avoid_si = check_loss_avoidance_size_invariant(
            snap, histories.get(ticker)
        )
        if loss_avoid_si.fired and emitter.add(
            "loss_avoidance_pattern_size_invariant"
        ):
            loss_avoidance_size_invariant_firing_count += 1

        # Issue #176 — share_count_extraction_missing annotate.
        # Fires when the snapshot has revenue + total_assets but
        # shares_outstanding is None (STZ 2026-05-14 pattern). Annotate-
        # only — distinct from the data_quality_input_corruption veto,
        # which keeps its shares_outstanding=None silence contract per
        # issue #18 / test_D3.
        if check_share_count_extraction_missing(snap) and emitter.add(
            "share_count_extraction_missing"
        ):
            share_count_extraction_missing_count += 1

        # S&P 1500 Slice 4 — low_liquidity ANNOTATE (defense layer 36,
        # ANNOTATE-ONLY per Rule 16 / ``portable-annotate-before-veto``).
        #
        # Fires when the trailing-30-day mean dollar volume (close × volume)
        # is known AND below the $5M ADV floor (config.ADV_FLOOR_USD).
        # Academic anchor: Amihud 2002 *J. Financial Markets* §2 — sub-$5M
        # names sit in the bottom decile of the US-equity illiquidity measure;
        # microstructure noise dominates any fundamental signal at this scale.
        #
        # ANNOTATE-ONLY invariants (enforced by this placement in
        # ``valuation_warnings``, NOT ``risk_flags``):
        #   - Does NOT set ``cautious`` (recommendation unchanged).
        #   - Does NOT suppress Top-5 badge.
        #   - Does NOT null fair-price or change the composite score.
        # Veto promotion is gated on ≥ 1 cron of firing-rate data +
        # methodology ratification (WORKFLOW.md §8.6 "Liquidity backstop").
        _ticker_adv = adv_by_ticker.get(ticker)
        if (
            _ticker_adv is not None
            and _ticker_adv < config.ADV_FLOOR_USD
            and emitter.add("low_liquidity")
        ):
            low_liquidity_annotate_count += 1

        # Issue #177 — extreme_estimate_majority annotate count.
        # The flag is appended by ``compute.valuation.ensemble`` when
        # ≥ config.EXTREME_MAJORITY_THRESHOLD of the 6 methods fire
        # Defense #4; we just count here so the universe-wide firing
        # rate is surfaced on Metadata for the next cron's audit (gates
        # the follow-up median-exclusion PR).
        if "extreme_estimate_majority" in valuation_warnings:
            extreme_estimate_majority_count += 1
        # Issue #587 — low-applicability floor delta counter.
        # Increments only when the annotate fired via the new floor AND
        # NOT the old 3-of-6 baseline. Relies on ensemble.extreme_majority_lowapp
        # set by _extreme_majority_fires() in the ensemble module.
        if ensemble is not None and ensemble.extreme_majority_lowapp:
            extreme_estimate_majority_lowapp_count += 1

        # Phase 4.5e PR 3 — Form-4 insider-cluster annotates.
        #
        # The per-ticker `fetch_recent_form4` is gated on PR 2's
        # diagnostic dict — we ONLY consult the cache when PR 2's fetch
        # loop above confirmed a populated entry (``fetch_status="ok"``).
        # This is critical for pre-merge-prod-sim which sets
        # ``FORM4_FETCH_SKIP=1`` to skip PR 2's bulk loop (cache is
        # cold; 502 × per-filing HTTP would exceed the 45-min CI cap —
        # confirmed by the 2026-05-23 cancellation on PR #222
        # workflow_run 26330610740). Without the gate,
        # ``fetch_recent_form4`` would cache-miss → fall through to a
        # live SEC fetch in the scoring loop and reproduce the same
        # blast radius PR 2 was carved out to avoid.
        #
        # On the weekly cron (compute-rankings.yml, no FORM4_FETCH_SKIP),
        # the diagnostic check is essentially free (dict lookup) and
        # all 502 tickers normally pass — the fast-path runs the
        # predicates over the full universe.
        #
        # Annotate-only per Rule 16 + portable-annotate-before-veto:
        # composite rank unchanged; only ``manipulation_index`` +
        # ``composite_score_adjusted`` soft penalty is impacted.
        _form4_diag = form4_diagnostics.get(ticker)
        if _form4_diag and _form4_diag.get("fetch_status") == "ok":
            _form4_txns = fetch_recent_form4(ticker)
            # OUTSIDE-count (both below): counters tied to the detector fire,
            # NOT the dedup — plain `emitter.add(...)` then unconditional
            # increment; do NOT fold into `and emitter.add(...)` (module
            # docstring "Follow-up cleanup").
            if detect_insider_sell_cluster(_form4_txns, asof_date):
                emitter.add("insider_sell_cluster")
                insider_sell_cluster_firing_count += 1
            if detect_c_suite_unusual_sell(_form4_txns, asof_date):
                emitter.add("c_suite_unusual_sell")
                c_suite_unusual_sell_firing_count += 1
            # PR 4-eq Rule 18 diagnostic — sum the count of transactions
            # excluded by the 10b5-1 filter (within the 30d cluster window
            # only) so the universe-wide contamination-eliminated metric
            # is visible on metadata.json for the Q3 cohort audit.
            form4_rule10b5_one_excluded_count += (
                count_10b5_1_filtered_transactions(_form4_txns, asof_date)
            )

        # Issue #67 — Rule 18 dual-count for sector-adjusted CoE delta.
        # We call check_rim_applicability twice — once with the flat 0.10
        # baseline and once with the per-sector Ke — so the universe-wide
        # delta is visible in Metadata on every cron regardless of the
        # USE_SECTOR_COE flag.  The per-ticker inputs (avg_3y_roe, tbvps,
        # lag_status) are already computed above; we just reuse them here.
        # This is a read-only measurement pass — no risk_flags or
        # valuation_warnings are modified by these calls.
        _hist_67 = historical_metrics.get(ticker, {})
        _avg_roe_67 = _hist_67.get("avg_3y_roe")
        _tbvps_67 = tangible_book_value_per_share(snap) if snap is not None else None
        _lag_67 = filing_lag_fn(snap, asof_date)
        _lag_status_67 = stale_filing_status(_lag_67)
        _rim_flat = check_rim_applicability(
            avg_3y_roe=_avg_roe_67,
            tbvps=_tbvps_67,
            lag_status=_lag_status_67,
            cost_of_equity=config.COST_OF_EQUITY,
        )
        # #259 smell-#8 cleanup — the two check_rim_applicability calls
        # (flat Ke here, sector Ke below) stay separate per issue #67's
        # flat-vs-sector delta measurement; only the repeated "value-trap
        # skip? bump scalar + per-sector dict" 3-line block is factored
        # into _tally_value_trap. See that helper's docstring for the
        # DEEPER redundancy this pass intentionally does NOT address.
        if _tally_value_trap(
            _rim_flat, sector, value_trap_risk_count_without_sector_coe_by_sector
        ):
            value_trap_risk_count_without_sector_coe += 1
        _rim_sector = check_rim_applicability(
            avg_3y_roe=_avg_roe_67,
            tbvps=_tbvps_67,
            lag_status=_lag_status_67,
            cost_of_equity=get_cost_of_equity(sector),
        )
        if _tally_value_trap(
            _rim_sector, sector, value_trap_risk_count_with_sector_coe_by_sector
        ):
            value_trap_risk_count_with_sector_coe += 1

        # Two-factor value_trap_risk LIVE gate (issue #586 PR-2, 0.10.34-phase8pilot).
        # FLIPPED from SHADOW to LIVE: the first sp1500 cron confirmed
        # value_trap_risk_two_factor_shadow_count = 155 (10.3% of 1504),
        # squarely in the methodology-ratified 5-12% LSV band.  Acceptance
        # gate cleared; the two-factor gate is now the live emission.
        #
        # The warning is emitted HERE (main.py), NOT in ensemble.py, because
        # the P/E cross-sectional comparison requires sector_panel +
        # universe_metrics which are only in scope in this per-ticker loop.
        # ensemble.py no longer appends "value_trap_risk" (PR-2 change).
        #
        # Gate (identical to the former shadow gate):
        #   (a) live ROE≤Ke skip fires (reuses _rim_sector from above, same
        #       sector Ke as the live path post-USE_SECTOR_COE flip)
        #   (b) eps_ttm > 0 (positive earnings, P/E defined)
        #   (c) ticker P/E < sector-peer median P/E from universe_metrics
        # Loss-making firms (eps_ttm ≤ 0) are EXEMPT — does NOT emit.
        #
        # value_trap_risk_two_factor_shadow_count is kept for one additional
        # cron as a structural cross-check (it now equals the live count);
        # documented in Metadata.value_trap_risk_two_factor_shadow_count docstring.
        #
        # RIPPLE: value_trap_risk feeds VALUE_TRAP_PENALTY into derive_loss_chance
        # (scoring/loss_chance.py), so the ~393 stocks that DROP out of the firing
        # set under the two-factor gate also LOSE that loss-chance penalty — their
        # displayed loss_chance_pct shifts down this cron. Intended + rank-neutral
        # (loss_chance_pct is display-derived; composite_score is passed in
        # pre-computed and is unaffected). A post-cron stock-detail-auditor should
        # treat this one-time loss_chance_pct shift as the expected flip effect,
        # NOT data drift.
        if (
            not _rim_sector.applicable
            and _rim_sector.reason == "value_trap_risk_roe_below_cost_of_equity"
            and snap is not None
        ):
            # Derive eps_ttm exactly as the ensemble does (NI_TTM / shares_out).
            _vtr_eps_ttm: float | None = None
            if (
                snap.net_income is not None
                and snap.shares_outstanding is not None
                and snap.shares_outstanding > 0
                and snap.net_income > 0
            ):
                _vtr_eps_ttm = snap.net_income / snap.shares_outstanding

            if _vtr_eps_ttm is not None and _vtr_eps_ttm > 0 and current_price > 0:
                _vtr_pe_ttm = current_price / _vtr_eps_ttm
                # Sector-peer median P/E: all tickers in the same sector panel
                # (excluding the target ticker itself) with a positive P/E.
                # Uses universe_metrics (same dict that feeds the multiples_pe
                # peer walk in compute_fair_price_ensemble).
                # NOTE: sector_panel is only defined when snap is not None (the
                # enclosing if-block). We are inside that block so it is in scope.
                _vtr_sector_pe_values: list[float] = [
                    float(universe_metrics[t]["pe_ttm"])
                    for t in sector_panel
                    if t in universe_metrics
                    and universe_metrics[t].get("pe_ttm") is not None
                    and universe_metrics[t]["pe_ttm"] > 0  # type: ignore[operator]
                ]
                if _vtr_sector_pe_values:
                    _vtr_sector_median_pe = statistics.median(_vtr_sector_pe_values)
                    if _vtr_pe_ttm < _vtr_sector_median_pe:
                        # Live emission — two-factor gate satisfied.
                        # OUTSIDE-count: shadow counter tied to the P/E gate,
                        # NOT the dedup — plain `emitter.add(...)`; do NOT fold
                        # into `and emitter.add(...)` (module docstring
                        # "Follow-up cleanup").
                        emitter.add("value_trap_risk")
                        # Shadow counter now equals the live count; kept for one
                        # more cron as a structural cross-check.
                        value_trap_risk_two_factor_shadow_count += 1

        # Price history JSON (sliced from already-fetched prices, no new
        # fetches per Step 5 spec).
        prices_df = prices_by_ticker.get(ticker)
        has_history = False
        if prices_df is not None:
            has_history = write_stock_history(
                ticker=ticker,
                prices_df=prices_df,
                output_dir=config.DATA_DIR,
            )
            if has_history:
                history_count += 1

        # PR 4d — recommendation tier (Option B locked: bullish / lean_bullish
        # / neutral / cautious). Deterministic derivation from composite +
        # risk_flags + valuation_warnings + MoS. See
        # `compute/scoring/recommendation.py` for the rubric.
        recommendation = derive_recommendation(
            composite_score=float(r["composite_score"]),
            risk_flags=risk_flags.get(ticker, []),
            valuation_warnings=valuation_warnings,
            mos_pct=ensemble.mos_pct if ensemble is not None else None,
        )

        # PR 4e — Loss Chance % heuristic (Option D locked: "Loss Chance %"
        # label + small italic "heuristic" qualifier in the UI). Pure
        # combiner over composite + risk_flags + valuation_warnings + MoS.
        # Returns None when MoS unavailable (no ensemble) — frontend
        # renders em-dash placeholder. See `compute/scoring/loss_chance.py`.
        loss_chance_pct = derive_loss_chance(
            composite_score=float(r["composite_score"]),
            risk_flags=risk_flags.get(ticker, []),
            valuation_warnings=valuation_warnings,
            mos_pct=ensemble.mos_pct if ensemble is not None else None,
        )

        # PR 4.5f — manipulation_index rollup + soft composite penalty.
        # Rank stays the raw composite per SKILL.md Rule 16 ("composite
        # rank unchanged"); composite_score_adjusted is informational.
        m_index = compute_manipulation_index(
            risk_flags=risk_flags.get(ticker, []),
            valuation_warnings=valuation_warnings,
        )
        composite_adj = compute_adjusted_composite(
            composite_score=float(r["composite_score"]),
            manipulation_index=m_index,
        )
        m_components = manipulation_components(
            risk_flags=risk_flags.get(ticker, []),
            valuation_warnings=valuation_warnings,
        )

        summaries.append(
            StockSummary(
                rank=int(r["rank"]),
                ticker=ticker,
                name=str(r["name"]),
                sector=sector,
                composite_score=round(float(r["composite_score"]), 2),
                current_price=round(current_price, 4),
                fair_price=ensemble.median if ensemble is not None else None,
                max_fair_price=ensemble.max if ensemble is not None else None,
                margin_of_safety_pct=ensemble.mos_pct if ensemble is not None else None,
                pillar_scores=_pillar_scores_to_schema(pillar_row),
                risk_flags=risk_flags.get(ticker, []),
                valuation_warnings=valuation_warnings,
                recommendation=recommendation,
                loss_chance_pct=loss_chance_pct,
                price_change_1d_pct=(
                    round(float(r["price_change_1d_pct"]), 4)
                    if r.get("price_change_1d_pct") is not None
                    and not math.isnan(float(r["price_change_1d_pct"]))
                    else None
                ),
                manipulation_index=m_index,
                composite_score_adjusted=composite_adj,
                entered_top5=ticker in entered,
                exited_top5=ticker in exited,
                # Phase 8 pilot PR 3a — index membership from cohort column.
                index_membership=cohort_by_ticker.get(ticker, "sp500"),
                # Multi-index membership (0.10.23-phase8pilot) — cohort + Dow30/NDX overlap.
                index_memberships=memberships_by_ticker.get(
                    ticker, [cohort_by_ticker.get(ticker, "sp500")]
                ),
            )
        )

        _psr_for_raw = post_split_results.get(ticker)
        raw_metrics = build_raw_metrics_fn(
            snap,
            current_price,
            shares_outstanding_pre_split_raw=(
                _psr_for_raw.edgar_shares
                if _psr_for_raw is not None and _psr_for_raw.tier == 1
                else None
            ),
        )
        imputed = imputed_by_ticker.get(ticker, [])
        tier2_result = tier2_results.get(ticker)
        tier2_dict = tier2_events_dict(tier2_result) if tier2_result is not None else None
        detail = StockDetail(
            ticker=ticker,
            name=str(r["name"]),
            sector=sector,
            industry=sub_industry,
            exchange=exchange_by_ticker.get(ticker),
            country=country_by_ticker.get(ticker),
            market_cap=raw_metrics.market_cap,
            current_price=round(current_price, 4),
            rank=int(r["rank"]),
            composite_score=round(float(r["composite_score"]), 2),
            pillar_scores=_pillar_scores_to_schema(pillar_row),
            raw_metrics=raw_metrics,
            fair_price=ensemble_dict,
            data_quality=_build_data_quality(snap, now, imputed),
            risk_flags=risk_flags.get(ticker, []),
            valuation_warnings=valuation_warnings,
            has_history=has_history,
            tangible_book_value=tbvps_value,
            tier2_events=tier2_dict,
            pillar_baseline=sector_pillar_baselines.get(sector),
            beneish_m_score=beneish_result.m_score,
            dechow_f_score=dechow_result.f_score,
            recommendation=recommendation,
            loss_chance_pct=loss_chance_pct,
            price_change_1d_pct=(
                round(float(r["price_change_1d_pct"]), 4)
                if r.get("price_change_1d_pct") is not None
                and not math.isnan(float(r["price_change_1d_pct"]))
                else None
            ),
            manipulation_index=m_index,
            composite_score_adjusted=composite_adj,
            manipulation_components=m_components,
            valuation_methods_applicable=(
                ensemble.valuation_methods_applicable if ensemble is not None else None
            ),
            osap_signals=osap_signal_map.get(ticker),
            osap_blended_score=(
                round(float(composite_osap_adjusted[ticker]), 2)
                if ticker in composite_osap_adjusted.index
                and not pd.isna(composite_osap_adjusted[ticker])
                else None
            ),
            entered_top5=ticker in entered,
            exited_top5=ticker in exited,
            # Phase 8 pilot PR 3a — index membership from cohort column.
            index_membership=cohort_by_ticker.get(ticker, "sp500"),
            # Multi-index membership (0.10.23-phase8pilot) — cohort + Dow30/NDX overlap.
            index_memberships=memberships_by_ticker.get(
                ticker, [cohort_by_ticker.get(ticker, "sp500")]
            ),
            form4_diagnostics=form4_diagnostics.get(ticker),
            cross_source_delta=cross_source_delta_by_ticker.get(ticker),
            # Dividend signal PR-1 (roadmap item #5 / 7a, 0.10.27-phase8pilot).
            # Display-only; does NOT influence composite score / risk_flags /
            # recommendation / any defense flag.  All three default to None
            # so legacy consumers are unaffected.
            dividend_yield_pct=_dividend_yield_pct_by_ticker.get(ticker),
            pays_dividend=_pays_dividend_by_ticker.get(ticker),
            payout_ratio=_payout_ratio_by_ticker.get(ticker),
            # S&P 1500 Slice 4 — ADV liquidity backstop (defense layer 36,
            # 0.10.29-phase8pilot, ANNOTATE-ONLY per Rule 16). Display-only
            # diagnostic; does NOT influence composite score / risk_flags /
            # recommendation / Top-5 eligibility. None when price DataFrame
            # was unavailable or missing Close/Volume column (graceful
            # degradation per Rule 18).
            average_dollar_volume=adv_by_ticker.get(ticker),
            # Security-type signal PR-1 (roadmap item #5 / 7b, 0.10.30-phase8pilot,
            # Rule 18 observability-first). Display-only; does NOT influence
            # composite score / risk_flags / recommendation / any defense flag.
            # Defaults to None so legacy consumers are unaffected.
            security_type=_security_type_by_ticker.get(ticker),
        )
        write_stock_detail(detail, config.DATA_DIR)
        all_details.append(detail)  # Step 13.5 warehouse accumulator
        detail_count += 1

    # Issue #287 PR A — wall-clock end marker for Step 8 (cross_source umbrella).
    cross_source_wall_clock_seconds = round(
        time.monotonic() - _cross_source_wc_start, 1
    )
    logger.info(
        "Wrote %d stock detail JSON files; %d with fair_price; %d with price history; "
        "Step 8 wall_clock=%ss",
        detail_count,
        fair_price_count,
        history_count,
        cross_source_wall_clock_seconds,
    )

    return PerTickerLoopResult(
        cross_source_wall_clock_seconds=cross_source_wall_clock_seconds,
        summaries=summaries,
        all_details=all_details,
        loss_avoidance_size_invariant_firing_count=loss_avoidance_size_invariant_firing_count,
        share_count_extraction_missing_count=share_count_extraction_missing_count,
        fundamentals_unavailable_count=fundamentals_unavailable_count,
        low_liquidity_annotate_count=low_liquidity_annotate_count,
        extreme_estimate_majority_count=extreme_estimate_majority_count,
        extreme_estimate_majority_lowapp_count=extreme_estimate_majority_lowapp_count,
        cross_source_disagreement_count=cross_source_disagreement_count,
        cross_source_delta_histogram=cross_source_delta_histogram,
        cross_source_delta_by_ticker=cross_source_delta_by_ticker,
        _cs_yf_market_cap_by_ticker=_cs_yf_market_cap_by_ticker,
        _cs_yf_shares_by_ticker=_cs_yf_shares_by_ticker,
        _median_trimmed_by_ticker=_median_trimmed_by_ticker,
        exchange_by_ticker=exchange_by_ticker,
        country_by_ticker=country_by_ticker,
        _dividend_yield_pct_by_ticker=_dividend_yield_pct_by_ticker,
        _security_type_by_ticker=_security_type_by_ticker,
        _yf_sector_resolved_by_ticker=_yf_sector_resolved_by_ticker,
        value_trap_risk_count_without_sector_coe=value_trap_risk_count_without_sector_coe,
        value_trap_risk_count_with_sector_coe=value_trap_risk_count_with_sector_coe,
        value_trap_risk_two_factor_shadow_count=value_trap_risk_two_factor_shadow_count,
        value_trap_risk_count_without_sector_coe_by_sector=value_trap_risk_count_without_sector_coe_by_sector,
        value_trap_risk_count_with_sector_coe_by_sector=value_trap_risk_count_with_sector_coe_by_sector,
        insider_sell_cluster_firing_count=insider_sell_cluster_firing_count,
        c_suite_unusual_sell_firing_count=c_suite_unusual_sell_firing_count,
        form4_rule10b5_one_excluded_count=form4_rule10b5_one_excluded_count,
        multi_class_aggregate_shares_suspected_count=multi_class_aggregate_shares_suspected_count,
    )
