"""Fair-price ensemble — orchestrates the 6 valuation methods + applies
Defense #2 (goodwill_heavy annotation), Defense #3 (stale-filing
hard/soft handling), Defense #4 (multi-method outlier guard at 5×/0.2×).

The ensemble is the user-facing point where dispersion-aware aggregation
happens: a single ticker may produce e.g. Graham=$28 / DCF=$117 /
RIM=$208 / Multiples=$160 (the AAPL spot-check pattern from Steps
4.2-4.5). Naïve mean would land at ~$128 (meaningless under that
spread); the ensemble's **median + max + outlier-aware aggregation**
preserves the central tendency while reporting both the conservative
floor and an "if the optimistic methods are right" upper bound.

This module is a **pure function** — no I/O, no globals. Step 7
(compute/main.py wire-up) builds the ``peer_panels``, ``universe_metrics``,
and ``historical_metrics`` dicts cross-sectionally before the per-ticker
loop, then passes them in.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from compute import config
from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.scoring.cost_of_equity import get_cost_of_equity
from compute.valuation.applicability import (
    LagStatus,
    MethodApplicability,
    filing_lag_days,
    stale_filing_status,
)
from compute.valuation.dcf import dcf_fair_price
from compute.valuation.graham import graham_fair_price
from compute.valuation.multiples import (
    PeerTierUsed,
    compute_peer_medians,
    multiples_ev_ebitda_fair_price,
    multiples_pb_fair_price,
    multiples_pe_fair_price,
)
from compute.valuation.rim import rim_fair_price
from compute.valuation.tangible_book import (
    goodwill_heavy_flag,
    tangible_book_value_per_share,
)

# Method names — exact string keys surfaced in StockDetail.fair_price.methods.
METHOD_NAMES: tuple[str, ...] = (
    "graham",
    "multiples_pe",
    "multiples_pb",
    "multiples_ev_ebitda",
    "rim",
    "dcf",
)

# Mapping from peer_panels string keys to PeerTierUsed enum values.
_TIER_KEY_MAP: dict[str, PeerTierUsed] = {
    "sub_industry": PeerTierUsed.SUB_INDUSTRY,
    "industry": PeerTierUsed.INDUSTRY,
    "sector": PeerTierUsed.SECTOR,
    "broad": PeerTierUsed.BROAD_EX_FIN_UTIL,
}


@dataclass(frozen=True)
class FairPriceMethodResult:
    """Per-method result surfaced in StockDetail.fair_price.methods.<name>."""

    value: float | None
    applicable: bool
    reason: str | None
    tier_used: str | None = None  # multiples only; None for graham/rim/dcf


@dataclass(frozen=True)
class EnsembleResult:
    """Top-level fair_price object for StockDetail."""

    methods: dict[str, FairPriceMethodResult]
    median: float | None
    max: float | None
    low: float | None
    high: float | None
    mos_pct: float | None
    valuation_warnings: list[str] = field(default_factory=list)
    # Epic #150 Phase 2.1 (issue #150) — positive-framed count of
    # valuation methods that produced a non-outlier applicable estimate
    # for this ticker. Inverse of the count of ``extreme_*_estimate``
    # warnings emitted; surfaces the method-applicability signal
    # explicitly so downstream consumers (UI, filtering, audits)
    # don't have to derive it from the warning list. Always in
    # ``[0, len(METHOD_NAMES)]``; ``0`` means every method either
    # skipped or produced an outlier estimate.
    valuation_methods_applicable: int = 0
    # Issue #587 (0.10.32-phase8pilot) — signals whether the
    # ``extreme_estimate_majority`` annotate fired via the low-applicability
    # floor (n_applicable ≤ EXTREME_MAJORITY_LOWAPP_MAX) rather than the
    # baseline 3-of-6 rule. False (or True only alongside
    # ``extreme_estimate_majority`` in valuation_warnings) is the annotate-
    # only path — this boolean is the per-ticker signal that main.py
    # aggregates into ``Metadata.extreme_estimate_majority_lowapp_count``.
    # Always False when ``extreme_estimate_majority`` did not fire.
    extreme_majority_lowapp: bool = False
    # Issue #177 PR-A (0.10.24-phase8pilot) — shadow two-regime trimmed
    # median (DIAGNOSTIC-ONLY; does NOT feed mos_pct or any live path).
    # Huber 1981 §1.4 breakdown-point: the even-n median of 6 methods
    # = mean of the 3rd+4th order statistics; even a MINORITY of 2
    # garbage-low values drags it (FFIV: −23.6% → +18.1% if trimmed).
    # At MAJORITY-extreme the median collapses (APP: −1257%).
    # The shadow trim reuses _classify_outliers' SYMMETRIC extreme-flag
    # set (trims extreme-HIGH and extreme-LOW equally per Huber symmetry).
    # See _aggregate_methods for the unified two-regime implementation.
    # This field is None when < 2 non-extreme survivors remain (majority
    # collapse — unreliable to report any estimate).
    median_trimmed: float | None = None
    # Names of methods the trim would exclude from median_trimmed.
    # Empty when n_extreme == 0 (no-op) or when median_trimmed is None.
    methods_excluded_from_median: list[str] = field(default_factory=list)


def _all_methods_skipped(reason: str) -> dict[str, FairPriceMethodResult]:
    """Build a 6-method dict where every method is skipped with `reason`.

    Used for the Defense #3 hard-stale early return — when filing is
    too stale, every fair-price estimate is null so the user-facing
    JSON shows a consistent "all unavailable" state with one reason.
    """
    return {
        name: FairPriceMethodResult(
            value=None, applicable=False, reason=reason, tier_used=None
        )
        for name in METHOD_NAMES
    }


def _classify_outliers(
    methods: dict[str, FairPriceMethodResult],
    current_price: float,
) -> tuple[set[str], list[str]]:
    """Identify outlier method names per Defense #4.

    A method is an outlier if its applicable value is > 5× current_price
    OR < 0.2× current_price (strict inequality on both bounds — exact
    boundary 0.2× and 5× are NOT outliers).

    Returns (outlier_method_names, extreme_warnings_in_method_order).
    """
    if not math.isfinite(current_price) or current_price <= 0:
        return (set(), [])

    high_cap = config.EXTREME_ESTIMATE_HIGH * current_price
    low_floor = config.EXTREME_ESTIMATE_LOW * current_price

    outliers: set[str] = set()
    warnings: list[str] = []
    for name in METHOD_NAMES:
        r = methods.get(name)
        if r is None or not r.applicable or r.value is None:
            continue
        v = float(r.value)
        if v > high_cap or v < low_floor:
            outliers.add(name)
            warnings.append(f"extreme_{name}_estimate")
    return (outliers, warnings)


def _count_applicable_non_outliers(
    methods: dict[str, FairPriceMethodResult],
    extreme_warnings: list[str],
) -> int:
    """Count methods that produced an applicable, non-outlier estimate.

    Epic #150 Phase 2.1 (issue #150) — the positive-framed inverse of
    ``extreme_*_estimate`` warning count. ``extreme_warnings`` is the
    list already produced by :func:`_classify_outliers` (avoids
    recomputing the outlier set), and the result lands in
    :class:`EnsembleResult.valuation_methods_applicable`.
    """
    outlier_names = {
        w[len("extreme_"):-len("_estimate")]
        for w in extreme_warnings
        if w.startswith("extreme_") and w.endswith("_estimate")
    }
    return sum(
        1
        for name, r in methods.items()
        if r.applicable and r.value is not None and name not in outlier_names
    )


def _extreme_majority_fires(n_extreme: int, n_applicable: int) -> bool:
    """Determine whether ``extreme_estimate_majority`` should fire.

    Issue #587 (0.10.32-phase8pilot) — RE-BASE-WITH-FLOOR recalibration.
    Methodology-scientist ratified. Annotate-only per Rule 16.

    Two firing branches (OR logic):

    **Baseline (3-of-6 rule):** ``n_extreme >= EXTREME_MAJORITY_THRESHOLD``
      The ensemble's median tolerates ⌊5/2⌋ = 2 outliers before degrading
      (Huber 1981 §1.4 breakdown-point). When 3+ of the 6 methods are
      extreme, the median has passed its breakdown point.

    **Low-applicability floor:** ``n_applicable <= EXTREME_MAJORITY_LOWAPP_MAX
      AND n_extreme >= EXTREME_MAJORITY_LOWAPP_MIN
      AND n_extreme > n_applicable - n_extreme``
      In the low-applicability regime (≤ 3 methods applicable — the S&P 1500
      small-cap tail), fire when a *strict majority* of applicable methods
      are extreme AND at least 2 are extreme. The ``n_extreme >= 2`` floor
      kills the 1-of-2 false-positive (one extreme of two applicable is not
      an n=2-median breakdown event — Huber 1981 §1.4 provenance tier).
      The ``n_applicable <= 3`` ceiling confines new behaviour to the
      low-applicability tail so S&P 500 tickers (5-6 applicable) are
      byte-identical.

    ``n_applicable`` = total count of methods with ``applicable == True``
    AND ``value is not None`` (includes outliers). This is NOT the same as
    ``valuation_methods_applicable`` (which counts only non-outlier
    survivors).

    Callable standalone so test-engineer can pin the predicate directly
    without constructing a full ensemble fixture.

    Precondition (guaranteed by the call site, not enforced here):
    ``n_extreme <= n_applicable`` — the extreme count is a subset of the
    applicable-with-value methods. The degenerate ``n_extreme > n_applicable``
    is unreachable from production and would spuriously satisfy the
    strict-majority test; do not call this helper with such inputs.
    """
    # Baseline 3-of-6 rule (unchanged from Issue #177).
    if n_extreme >= config.EXTREME_MAJORITY_THRESHOLD:
        return True
    # Low-applicability floor (Issue #587 RE-BASE-WITH-FLOOR).
    if (
        n_applicable <= config.EXTREME_MAJORITY_LOWAPP_MAX
        and n_extreme >= config.EXTREME_MAJORITY_LOWAPP_MIN
        and n_extreme > n_applicable - n_extreme
    ):
        return True
    return False


def _aggregate_methods(
    methods: dict[str, FairPriceMethodResult],
    current_price: float,
) -> tuple[
    dict[str, float | None], list[str], float | None, list[str]
]:
    """Aggregate per-method results into median/max/low/high/mos_pct.

    Returns (aggregates, extreme_warnings, median_trimmed,
    methods_excluded_from_median) where aggregates is a dict with keys
    ``median``, ``max``, ``low``, ``high``, ``mos_pct``. The live
    ``median`` includes ALL applicable values (robust by construction);
    the max EXCLUDES outliers (a 5× DCF shouldn't anchor user
    expectations of upside).

    The SHADOW ``median_trimmed`` implements the ratified two-regime trim
    rule (Issue #177 + Huber 1981 §1.4 breakdown-point; PR-A diagnostic-
    first — median_trimmed does NOT yet feed mos_pct):
      - n_extreme == 0          → median_trimmed = median (no-op)
      - len(survivors) >= 2     → median_trimmed = median(survivors)
      - len(survivors) < 2      → median_trimmed = None (majority collapse)
    The trim is inherently SYMMETRIC because it reuses _classify_outliers
    which flags both extreme-HIGH (v > 5× price) and extreme-LOW
    (v < 0.2× price) methods equally — satisfying methodology's hard
    symmetry guard at the logic level.

    MoS sign convention: positive when median > current_price (i.e.,
    intrinsic value above market = potential undervaluation). Returns
    None when current_price is non-positive or median is None.
    """
    outlier_names, extreme_warnings = _classify_outliers(methods, current_price)

    applicable_values: list[float] = []
    non_outlier_values: list[float] = []
    excluded_method_names: list[str] = []
    for name in METHOD_NAMES:
        r = methods.get(name)
        if r is None or not r.applicable or r.value is None:
            continue
        applicable_values.append(float(r.value))
        if name not in outlier_names:
            non_outlier_values.append(float(r.value))
        else:
            excluded_method_names.append(name)

    if not applicable_values:
        aggregates = {
            "median": None,
            "max": None,
            "low": None,
            "high": None,
            "mos_pct": None,
        }
        return (aggregates, extreme_warnings, None, [])

    median_v = float(statistics.median(applicable_values))
    max_v = max(non_outlier_values) if non_outlier_values else None
    low_v = min(applicable_values)
    high_v = max(applicable_values)

    if current_price > 0 and median_v > 0:
        mos_pct = (median_v - current_price) / median_v * 100.0
    else:
        mos_pct = None

    aggregates = {
        "median": median_v,
        "max": max_v,
        "low": low_v,
        "high": high_v,
        "mos_pct": mos_pct,
    }

    # Shadow two-regime trimmed median (Issue #177 PR-A, diagnostic-only).
    # Reuses the already-computed outlier_names + non_outlier_values —
    # no second call to _classify_outliers. BYTE-IDENTICAL to the live
    # median path because median_trimmed is a NEW field, not a replacement.
    n_extreme = len(outlier_names)
    if n_extreme == 0:
        # No-op regime: trim changes nothing.
        median_trimmed: float | None = median_v
        methods_excluded_from_median: list[str] = []
    elif len(non_outlier_values) >= 2:
        # Minority OR majority-with-≥2-survivors: trim to non-extreme subset.
        median_trimmed = float(statistics.median(non_outlier_values))
        methods_excluded_from_median = excluded_method_names
    else:
        # < 2 survivors (majority collapse): unreliable — emit None.
        median_trimmed = None
        methods_excluded_from_median = excluded_method_names

    return (aggregates, extreme_warnings, median_trimmed, methods_excluded_from_median)


def _convert_peer_panel(
    panel_str: dict[str, list[str]] | None,
) -> dict[PeerTierUsed, list[str]]:
    """Convert string-keyed peer panel to PeerTierUsed-enum-keyed."""
    if not panel_str:
        return {}
    return {
        _TIER_KEY_MAP[k]: v
        for k, v in panel_str.items()
        if k in _TIER_KEY_MAP
    }


def _net_debt(snap: FundamentalsSnapshot) -> float | None:
    """Compute net_debt = (long_term + short_term debt) − cash.

    Returns None only if BOTH debt fields are missing AND cash is missing.
    Treats individual missing values as 0 since most public-company
    filings include long-term debt + cash even if short-term is sparse.
    """
    if (
        snap.long_term_debt is None
        and snap.short_term_debt is None
        and snap.cash is None
    ):
        return None
    long_term = float(snap.long_term_debt) if snap.long_term_debt is not None else 0.0
    short_term = float(snap.short_term_debt) if snap.short_term_debt is not None else 0.0
    cash = float(snap.cash) if snap.cash is not None else 0.0
    return (long_term + short_term) - cash


def _bvps_reported(snap: FundamentalsSnapshot) -> float | None:
    """Reported book value per share = stockholders_equity / shares."""
    if snap.stockholders_equity is None:
        return None
    if snap.shares_outstanding in (None, 0):
        return None
    return float(snap.stockholders_equity) / float(snap.shares_outstanding)


def compute_fair_price_ensemble(
    *,
    ticker: str,
    snap: FundamentalsSnapshot,
    sector: str | None,
    sub_industry: str | None,  # noqa: ARG001  (informational; used by caller-built peer_panels)
    industry: str | None,  # noqa: ARG001  (informational; used by caller-built peer_panels)
    current_price: float,
    filing_lag_days_value: int | None,
    peer_panels: dict[str, dict[str, list[str]]],
    universe_metrics: dict[str, dict[str, float | None]],
    historical_metrics: dict[str, dict[str, float | list[float] | None]],
    hard_stale_days: int | None = None,
) -> tuple[EnsembleResult, list[str]]:
    """Compute fair-price ensemble for one ticker.

    ``hard_stale_days`` overrides Defense #3's hard-stale ceiling (default
    ``config.FILING_STALE_HARD_DAYS`` = 180). The live path passes nothing; the
    Phase 7 PIT backtest passes the annual-aware ``BACKTEST_HARD_STALE_DAYS``
    (455) so a once-a-year 10-K is not auto-nulled (methodology-scientist C2).

    Returns ``(EnsembleResult, risk_flags_to_append)``. The
    ``risk_flags_to_append`` list contains ONLY new flags from this
    function (specifically ``stale_filing_hard`` when filing is
    hard-stale). The caller (the Step-8 per-ticker loop in
    compute/main.py) merges these into the existing risk_flags from
    compute_risk_flags. NOTE: ``stale_filing_hard`` is ALSO injected into
    risk_flags by a dedicated pre-Step-7 lag scan so the Top-5 rotation
    veto check sees it (issue #309); this Step-8 merge is idempotent
    (deduped by the caller) and remains the source for tickers the
    pre-scan may not cover.

    Defense application order:

    1. Defense #3 stale filing — hard-stale short-circuits to all-null
       methods + risk_flag. Soft-stale annotates valuation_warnings.
    2. Defense #2 goodwill_heavy — annotates valuation_warnings.
    3. Per-method computation (6 methods).
    4. Defense #4 outlier guard — annotates valuation_warnings;
       outlier methods excluded from max but kept in median.
    5. RIM value_trap_risk — MOVED to compute/main.py (Step 8 per-ticker
       loop, PR-2 #586).  Two-factor LSV gate requires sector-peer P/E
       context not available in this pure-function layer.  This step is
       a no-op: no "value_trap_risk" append happens here.
    """
    lag_status: LagStatus = stale_filing_status(filing_lag_days_value, hard_days=hard_stale_days)

    # Defense #3 hard-stale: short-circuit. All methods skip with the
    # canonical reason; risk_flag returned for caller to merge.
    if lag_status == "hard":
        return (
            EnsembleResult(
                methods=_all_methods_skipped("stale_filing_hard"),
                median=None,
                max=None,
                low=None,
                high=None,
                mos_pct=None,
                valuation_warnings=[],
            ),
            ["stale_filing_hard"],
        )

    valuation_warnings: list[str] = []

    # Soft-stale annotation — methods still compute.
    if lag_status == "soft":
        valuation_warnings.append("stale_filing_soft")

    # Defense #2: tangible book + goodwill_heavy annotation.
    tbvps = tangible_book_value_per_share(snap)
    if goodwill_heavy_flag(snap, tbvps):
        valuation_warnings.append("goodwill_heavy")

    # Per-method input wiring.
    hist = historical_metrics.get(ticker, {})
    eps_3y_avg = hist.get("eps_3y_avg")
    avg_3y_roe = hist.get("avg_3y_roe")
    fcf_5y_raw = hist.get("fcf_5y", []) or []
    fcf_5y: list[float | None] = list(fcf_5y_raw) if isinstance(fcf_5y_raw, list) else []  # type: ignore[arg-type]

    bvps_reported = _bvps_reported(snap)
    net_debt = _net_debt(snap)

    # Peer medians — built from caller's peer_panels + universe_metrics.
    pe_values = {t: m.get("pe_ttm") for t, m in universe_metrics.items()}
    pb_values = {t: m.get("pb_reported") for t, m in universe_metrics.items()}
    ev_ebitda_values = {t: m.get("ev_ebitda_ttm") for t, m in universe_metrics.items()}

    peer_pe = compute_peer_medians(
        tickers_by_tier=_convert_peer_panel(peer_panels.get("pe")),
        metric_values=pe_values,
        target_ticker=ticker,
    )
    peer_pb = compute_peer_medians(
        tickers_by_tier=_convert_peer_panel(peer_panels.get("pb")),
        metric_values=pb_values,
        target_ticker=ticker,
    )
    peer_ev_ebitda = compute_peer_medians(
        tickers_by_tier=_convert_peer_panel(peer_panels.get("ev_ebitda")),
        metric_values=ev_ebitda_values,
        target_ticker=ticker,
    )

    # Method calls (6 of them).
    g_value, g_app = graham_fair_price(
        eps_3y_avg=eps_3y_avg,  # type: ignore[arg-type]
        tangible_book_value_per_share=tbvps,
        lag_status=lag_status,
    )

    # Derive TTM EPS from NI_TTM / shares_outstanding instead of using
    # snap.eps_diluted directly. Audit #6 found that snap.eps_diluted comes
    # from edgartools' normalized snake_case API and returns the latest
    # single-period EPS (quarterly / YTD / annual depending on filer cadence)
    # — not TTM. This makes multiples_pe_fair_price 2-8× off for ~88% of
    # the S&P 500 universe. Same fix as compute/features/value.py::pe_ratio.
    eps_ttm: float | None = None
    if (
        snap.net_income is not None
        and snap.shares_outstanding is not None
        and snap.shares_outstanding > 0
        and snap.net_income > 0
    ):
        eps_ttm = snap.net_income / snap.shares_outstanding

    pe_value, pe_app = multiples_pe_fair_price(
        eps_ttm=eps_ttm,
        peer_pe_median=peer_pe.median,
        peer_tier_used=peer_pe.tier_used,
        lag_status=lag_status,
    )

    pb_value, pb_app = multiples_pb_fair_price(
        bvps_reported=bvps_reported,
        peer_pb_median=peer_pb.median,
        peer_tier_used=peer_pb.tier_used,
        lag_status=lag_status,
    )

    ev_value, ev_app = multiples_ev_ebitda_fair_price(
        sector=sector,
        ebitda_ttm=snap.ebitda,
        peer_ev_ebitda_median=peer_ev_ebitda.median,
        peer_tier_used=peer_ev_ebitda.tier_used,
        net_debt=net_debt,
        shares_outstanding=snap.shares_outstanding,
        lag_status=lag_status,
    )

    # Issue #67 — sector-adjusted cost of equity (Damodaran 2019 Table 8.4).
    # When USE_SECTOR_COE is True the per-GICS Ke from cost_of_equity.py
    # is used instead of the flat COST_OF_EQUITY = 0.10 constant.
    # Default False — data-collection PR per Rule 18; production behaviour
    # unchanged until the flip PR lands after ≥ 1 cron's delta-flag-count.
    rim_cost_of_equity = (
        get_cost_of_equity(sector)
        if config.USE_SECTOR_COE
        else config.COST_OF_EQUITY
    )
    rim_value, rim_app = rim_fair_price(
        tangible_book_value_per_share=tbvps,
        avg_3y_roe=avg_3y_roe,  # type: ignore[arg-type]
        lag_status=lag_status,
        cost_of_equity=rim_cost_of_equity,
    )

    dcf_value, dcf_app = dcf_fair_price(
        sector=sector,
        fcf_5y=fcf_5y,
        shares_outstanding=snap.shares_outstanding,
        net_debt=net_debt,
        lag_status=lag_status,
    )

    methods: dict[str, FairPriceMethodResult] = {
        "graham": _wrap(g_value, g_app, tier_used=None),
        "multiples_pe": _wrap(
            pe_value, pe_app, tier_used=_tier_str(peer_pe.tier_used, pe_app)
        ),
        "multiples_pb": _wrap(
            pb_value, pb_app, tier_used=_tier_str(peer_pb.tier_used, pb_app)
        ),
        "multiples_ev_ebitda": _wrap(
            ev_value, ev_app, tier_used=_tier_str(peer_ev_ebitda.tier_used, ev_app)
        ),
        "rim": _wrap(rim_value, rim_app, tier_used=None),
        "dcf": _wrap(dcf_value, dcf_app, tier_used=None),
    }

    # Step 4.5 — Data-quality sanity sweep (Defense #7).
    # Issue #289 (2026-05-28, methodology-scientist Mode B verdict Option C):
    # Site-2 output-level data-quality ceiling DELETED. The Site-2 trigger
    # that lived here was a defense-in-depth layer that turned out to be
    # structurally redundant with Defense #4 (per-method `extreme_*_estimate`
    # outlier guard) and Issue #177's `extreme_estimate_majority` annotate
    # (Huber 1981 §1.4 breakdown-point check). Site-1
    # (`compute/scoring/risk_overlay.py::_data_quality_input_corruption`)
    # catches the upstream units-bug class via TBVPS / revenue / NI patterns
    # at the source — defending at the corruption source per Penman 2013
    # §7.4 + Damodaran 2019 Ch. 18, not at downstream output magnitude
    # (Site-2 conflated input-corruption Type A with high-per-share-magnitude
    # Type C: out-of-distribution but valid).
    #
    # The empirical false-positive that justified retirement: NVR (~2.7M low
    # share count, $458 EPS, $6,098 price) — `multiples_pe = sector_PE × EPS
    # ≈ 22× × $458.86 ≈ $10,094` tripped the $10K ceiling. All 6 methods got
    # blocked → `/stock/NVR` rendered empty fair-price section despite
    # legitimate inputs and a 65% MoS signal. PPV on 2026-05-28 cron #69:
    # 0/1 = 0% (the only firing was the false positive).
    #
    # `config.FAIR_PRICE_DATA_QUALITY_CEILING` remains active for Site-1.
    # The writer-parity emit in `compute/main.py` preserves the UI
    # explanation chip for the Site-1 veto cohort (MTB / CPT / MRNA / HBAN
    # per PR #265) so the `valuation_output_anomalous` annotate's UI
    # surface continues to render — it just no longer fires from this
    # Site-2 path. Dead-code helpers `_has_corrupt_input` +
    # `_data_quality_corrupt_result` removed in this PR after cron Run #71
    # (2026-05-28 08:44 UTC) confirmed no Site-2 regression on NVR cohort.

    # Defense #4 outlier guard + aggregation.
    # Returns 4-tuple: (aggregates, extreme_warnings, median_trimmed,
    # methods_excluded_from_median). The trimmed fields are shadow/
    # diagnostic only — they do NOT alter the live median or mos_pct.
    aggregates, extreme_warnings, median_trimmed, methods_excluded_from_median = (
        _aggregate_methods(methods, current_price)
    )
    valuation_warnings.extend(extreme_warnings)

    # Issue #177 / #587 — extreme_estimate_majority annotate.
    # Issue #177: The median is a 50% trimmed estimator over 6 methods,
    # so it tolerates ⌊5/2⌋ = 2 outliers before degrading (Huber 1981
    # §1.4 breakdown-point). When ≥ EXTREME_MAJORITY_THRESHOLD of the 6
    # fire extreme_*_estimate, the median has passed its breakdown point —
    # Damodaran 2019 Ch. 18 calls for discarding methods whose inputs fall
    # outside their domain. Annotate-only per Rule 16 + portable-annotate-
    # before-veto.
    #
    # Issue #587 RE-BASE-WITH-FLOOR (0.10.32-phase8pilot): the S&P 1500
    # small-cap cutover exposed a false-negative dead-zone — tickers with
    # ≤ 3 applicable methods can have a strict majority extreme without
    # reaching 3-of-6. The low-applicability floor fires when n_applicable
    # ≤ EXTREME_MAJORITY_LOWAPP_MAX (3) AND n_extreme ≥
    # EXTREME_MAJORITY_LOWAPP_MIN (2) AND n_extreme > n_applicable −
    # n_extreme (strict majority). Methodology-scientist ratified.
    # Defense layer UNCHANGED at 36 (annotate-only, no new flag).
    #
    # n_applicable_total = total methods with applicable=True AND value
    # is not None INCLUDING outliers. = n_extreme + non-outlier-applicable.
    # Computed here so _extreme_majority_fires() has the full denominator.
    n_applicable_non_outlier = _count_applicable_non_outliers(methods, extreme_warnings)
    _n_extreme = len(extreme_warnings)
    n_applicable_total = _n_extreme + n_applicable_non_outlier

    extreme_majority_lowapp: bool = False
    if _extreme_majority_fires(_n_extreme, n_applicable_total):
        valuation_warnings.append("extreme_estimate_majority")
        # Track whether this fire came exclusively from the low-applicability
        # floor (not the baseline 3-of-6 rule). Used by main.py to populate
        # Metadata.extreme_estimate_majority_lowapp_count (Rule-18 counter).
        if _n_extreme < config.EXTREME_MAJORITY_THRESHOLD:
            extreme_majority_lowapp = True

    # RIM value_trap_risk warning.
    # FLIPPED to the two-factor LSV gate (issue #586 PR-2, 0.10.34-phase8pilot).
    # The single-leg gate (ROE≤Ke alone) was the legacy behaviour; the live
    # emission now requires BOTH legs:
    #   (a) RIM skips under avg_3y_roe <= Ke (Penman 2013 value-trap condition)
    #   AND (b) eps_ttm > 0 AND ticker P/E < sector-peer median P/E
    #           (LSV 1994 "Contrarian Investment" §3 cheap-relative-to-peers leg)
    # Loss-making / undefined-P/E firms are EXEMPT (leg b cannot fire when
    # eps_ttm <= 0).
    # The emission is now handled in compute/main.py (Step 8 per-ticker loop),
    # where sector_panel + universe_metrics are already in scope from the
    # two-factor shadow gate block that shipped in PR-1.  This function no
    # longer appends "value_trap_risk" — the ensemble layer is the wrong place
    # for a cross-sectional P/E comparison that requires sector-peer context.

    n_applicable = n_applicable_non_outlier

    # EQH-class guard: when every applicable method is an outlier (or no
    # method applied at all), valuation_methods_applicable == 0 means there
    # is no trustworthy point estimate.  Emitting the outlier-derived median
    # and MoS would produce absurd display values (e.g. −2942%).  Null both
    # fields to align with the existing Tier-1 "null on corrupt inputs"
    # philosophy (CLAUDE.md §Valuation) and with median_trimmed (which is
    # already None in this case — < 2 non-extreme survivors).
    # All other fields (per-method values, extreme_* warnings,
    # valuation_methods_applicable itself, low/high/max) are preserved
    # unchanged so the UI can still surface the individual method outputs
    # and their extreme-estimate annotations.
    if n_applicable == 0:
        aggregates = dict(aggregates)  # copy so we don't mutate the caller's dict
        aggregates["median"] = None
        aggregates["mos_pct"] = None

    return (
        EnsembleResult(
            methods=methods,
            median=aggregates["median"],
            max=aggregates["max"],
            low=aggregates["low"],
            high=aggregates["high"],
            mos_pct=aggregates["mos_pct"],
            valuation_warnings=valuation_warnings,
            valuation_methods_applicable=n_applicable,
            extreme_majority_lowapp=extreme_majority_lowapp,
            # Issue #177 PR-A — shadow trimmed fields (diagnostic-only).
            # median_trimmed and methods_excluded_from_median are written to
            # the per-stock JSON for post-cron audit but do NOT feed mos_pct
            # or any live scoring path (byte-identical live behavior).
            median_trimmed=median_trimmed,
            methods_excluded_from_median=methods_excluded_from_median,
        ),
        [],
    )


def _wrap(
    value: float | None,
    app: MethodApplicability,
    *,
    tier_used: str | None,
) -> FairPriceMethodResult:
    """Build a FairPriceMethodResult from a method's (value, app) tuple."""
    return FairPriceMethodResult(
        value=value,
        applicable=app.applicable,
        reason=app.reason,
        tier_used=tier_used,
    )


def _tier_str(
    tier: PeerTierUsed | None,
    app: MethodApplicability,
) -> str | None:
    """Return tier_used as string when method applicable; None otherwise.

    Multiples methods carry the peer-tier audit forward into the JSON
    contract; non-multiples methods always have tier_used=None. When a
    multiples method is skipped, tier_used is also None (no useful tier
    info for the user).
    """
    if not app.applicable or tier is None:
        return None
    return tier.value


def ensemble_result_to_dict(r: EnsembleResult) -> dict:
    """Convert :class:`EnsembleResult` to a JSON-serializable dict.

    Output shape exactly mirrors the ``FairPriceEnsemble`` type in
    ``frontend/lib/types.ts`` so the dict can be stored directly in
    ``StockDetail.fair_price``. The dict re-emits ``valuation_warnings``
    inside the ensemble payload (the same list ALSO surfaces at top
    level on ``StockDetail.valuation_warnings`` for ranking-table
    consumption); this duplication is intentional — the inner copy is
    used by the detail page's fair-price card without requiring the
    parent StockDetail context.
    """
    return {
        "methods": {
            name: {
                "value": result.value,
                "applicable": result.applicable,
                "reason": result.reason,
                "tier_used": result.tier_used,
            }
            for name, result in r.methods.items()
        },
        "median": r.median,
        "max": r.max,
        "low": r.low,
        "high": r.high,
        "mos_pct": r.mos_pct,
        "valuation_warnings": list(r.valuation_warnings),
        "valuation_methods_applicable": r.valuation_methods_applicable,
        # Issue #177 PR-A — shadow trimmed median diagnostics (OBSERVABILITY).
        # Does NOT alter live behavior. median_trimmed is None on majority
        # collapse (< 2 non-extreme survivors); methods_excluded_from_median
        # is empty when n_extreme == 0 (no-op trim).
        "median_trimmed": r.median_trimmed,
        "methods_excluded_from_median": list(r.methods_excluded_from_median),
    }


__all__ = [
    "EnsembleResult",
    "FairPriceMethodResult",
    "METHOD_NAMES",
    "_extreme_majority_fires",  # exported for direct test-pinning (issue #587)
    "compute_fair_price_ensemble",
    "ensemble_result_to_dict",
    "filing_lag_days",  # re-exported for caller convenience
]
