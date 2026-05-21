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


def _aggregate_methods(
    methods: dict[str, FairPriceMethodResult],
    current_price: float,
) -> tuple[
    dict[str, float | None], list[str]
]:
    """Aggregate per-method results into median/max/low/high/mos_pct.

    Returns (aggregates, extreme_warnings) where aggregates is a dict
    with keys ``median``, ``max``, ``low``, ``high``, ``mos_pct``. The
    median includes ALL applicable values (robust by construction);
    the max EXCLUDES outliers (a 5× DCF shouldn't anchor user
    expectations of upside).

    MoS sign convention: positive when median > current_price (i.e.,
    intrinsic value above market = potential undervaluation). Returns
    None when current_price is non-positive or median is None.
    """
    outlier_names, extreme_warnings = _classify_outliers(methods, current_price)

    applicable_values: list[float] = []
    non_outlier_values: list[float] = []
    for name in METHOD_NAMES:
        r = methods.get(name)
        if r is None or not r.applicable or r.value is None:
            continue
        applicable_values.append(float(r.value))
        if name not in outlier_names:
            non_outlier_values.append(float(r.value))

    if not applicable_values:
        aggregates = {
            "median": None,
            "max": None,
            "low": None,
            "high": None,
            "mos_pct": None,
        }
        return (aggregates, extreme_warnings)

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
    return (aggregates, extreme_warnings)


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
) -> tuple[EnsembleResult, list[str]]:
    """Compute fair-price ensemble for one ticker.

    Returns ``(EnsembleResult, risk_flags_to_append)``. The
    ``risk_flags_to_append`` list contains ONLY new flags from this
    function (specifically ``stale_filing_hard`` when filing is
    hard-stale). The caller (Step 7 in compute/main.py) merges these
    into the existing risk_flags from compute_risk_flags.

    Defense application order:

    1. Defense #3 stale filing — hard-stale short-circuits to all-null
       methods + risk_flag. Soft-stale annotates valuation_warnings.
    2. Defense #2 goodwill_heavy — annotates valuation_warnings.
    3. Per-method computation (6 methods).
    4. Defense #4 outlier guard — annotates valuation_warnings;
       outlier methods excluded from max but kept in median.
    5. RIM value_trap_risk — annotates valuation_warnings if RIM
       skipped on ROE<Ke.
    """
    lag_status: LagStatus = stale_filing_status(filing_lag_days_value)

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

    rim_value, rim_app = rim_fair_price(
        tangible_book_value_per_share=tbvps,
        avg_3y_roe=avg_3y_roe,  # type: ignore[arg-type]
        lag_status=lag_status,
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
    # If ANY applicable method produced a value above the per-share ceiling,
    # the underlying snapshot is corrupted (typically shares_outstanding
    # ingested with the wrong unit — see issue tracker for the Phase-3
    # fundamentals follow-up). Null all 6 methods + surface a single
    # warning rather than ship nonsense to the UI. No risk_flag is
    # appended: data quality is an upstream-ingest concern, not a
    # ranking veto.
    if _has_corrupt_input(methods):
        return (_data_quality_corrupt_result(methods), [])

    # Defense #4 outlier guard + aggregation.
    aggregates, extreme_warnings = _aggregate_methods(methods, current_price)
    valuation_warnings.extend(extreme_warnings)

    # Issue #177 — extreme_estimate_majority annotate. The median is a
    # 50% trimmed estimator over 6 methods, so it tolerates ⌊5/2⌋ = 2
    # outliers before degrading (Huber 1981 §1.4 breakdown-point). When
    # ≥ EXTREME_MAJORITY_THRESHOLD of the 6 fire extreme_*_estimate, the
    # median has passed its breakdown point and collapses toward the
    # low-cluster — Damodaran 2019 Ch. 18 calls for discarding methods
    # whose inputs fall outside their domain in this case. Annotate-only
    # this PR per Rule 16 + portable-annotate-before-veto; the actual
    # median-exclusion + ``fair_price.methods_excluded_from_median``
    # field lands in a follow-up PR after ≥ 1 cron's firing-rate
    # observation (per methodology-scientist Mode B, 2026-05-21).
    if len(extreme_warnings) >= config.EXTREME_MAJORITY_THRESHOLD:
        valuation_warnings.append("extreme_estimate_majority")

    # RIM value_trap_risk warning.
    if (
        not rim_app.applicable
        and rim_app.reason == "value_trap_risk_roe_below_cost_of_equity"
    ):
        valuation_warnings.append("value_trap_risk")

    return (
        EnsembleResult(
            methods=methods,
            median=aggregates["median"],
            max=aggregates["max"],
            low=aggregates["low"],
            high=aggregates["high"],
            mos_pct=aggregates["mos_pct"],
            valuation_warnings=valuation_warnings,
            valuation_methods_applicable=_count_applicable_non_outliers(
                methods, extreme_warnings
            ),
        ),
        [],
    )


def _has_corrupt_input(methods: dict[str, FairPriceMethodResult]) -> bool:
    """True if any applicable method produced a value > the data-quality
    ceiling (config.FAIR_PRICE_DATA_QUALITY_CEILING).

    Strict ``>`` so a method computing exactly the ceiling does NOT trip
    the guard. Skipped methods (applicable=False) and missing values
    are pass-through.
    """
    ceiling = config.FAIR_PRICE_DATA_QUALITY_CEILING
    for r in methods.values():
        if r.applicable and r.value is not None and r.value > ceiling:
            return True
    return False


def _data_quality_corrupt_result(
    methods: dict[str, FairPriceMethodResult],
) -> EnsembleResult:
    """Build the all-null EnsembleResult returned when the data-quality
    sanity guard fires.

    Each method becomes ``applicable=False`` with reason
    ``data_quality_input_corruption``. ``tier_used`` is preserved from
    the original computation so the JSON still tells the operator which
    peer tier the multiples methods consulted before the guard fired
    (useful for upstream-bug triage).
    """
    nulled: dict[str, FairPriceMethodResult] = {
        name: FairPriceMethodResult(
            value=None,
            applicable=False,
            reason="data_quality_input_corruption",
            tier_used=r.tier_used,
        )
        for name, r in methods.items()
    }
    return EnsembleResult(
        methods=nulled,
        median=None,
        max=None,
        low=None,
        high=None,
        mos_pct=None,
        valuation_warnings=["data_quality_input_corruption"],
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
    }


__all__ = [
    "EnsembleResult",
    "FairPriceMethodResult",
    "METHOD_NAMES",
    "compute_fair_price_ensemble",
    "ensemble_result_to_dict",
    "filing_lag_days",  # re-exported for caller convenience
]
