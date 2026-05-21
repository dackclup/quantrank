"""Applicability gates for fair-price methods + stale-filing primitives.

Pure-function module — no I/O, no globals, no imports beyond ``compute.config``
+ stdlib + typing. Each ``check_*_applicability`` function takes keyword-only
arguments (the dependencies that method actually needs) and returns a
:class:`MethodApplicability` with a stable snake_case ``reason`` string when
the method is skipped. Step 5 ensemble pattern-matches on those strings to
populate ``StockDetail.fair_price.methods.<method>.reason`` and (for the
stale-filing case) to append flags to ``valuation_warnings`` /
``risk_flags``.

The taxonomy of reason identifiers is defined in :data:`SKIP_REASONS` below.
Adding new reasons is permitted; renaming existing ones is a breaking change
to the JSON output (Step 5 string-matches them).

Stale-filing primitives (``filing_lag_days``, ``stale_filing_status``)
implement Defense #3 from the kickoff §B4 — hard-stale (>180d) skips the
method entirely; soft-stale (>120d) is annotated by Step 5. ``unknown``
(no filing date available) is permissive here — the method runs — but Step
5 may apply additional treatment.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import median
from typing import Literal

from compute import config

# Stable identifiers — any rename breaks the JSON contract surfaced via
# StockDetail.fair_price.methods.<method>.reason.
SKIP_REASONS: tuple[str, ...] = (
    "sector_excluded_financials",
    "sector_excluded_utilities",
    "non_positive_fcf_5y_median",
    "missing_shares_outstanding",
    "non_positive_eps_3y_avg",
    "non_positive_or_missing_tangible_book",
    "value_trap_risk_roe_below_cost_of_equity",
    # Issue #11 fix — distinguish "missing input data" from "real value
    # trap signal". Pre-2026-05-21, a ticker with no 3y stockholders_equity
    # history would skip RIM under value_trap_risk_roe_below_cost_of_equity,
    # which caused the ensemble layer to append a spurious value_trap_risk
    # warning. Now those tickers skip under insufficient_history_for_roe
    # (which is NOT a value-trap signal — it just means RIM can't compute).
    "insufficient_history_for_roe",
    "non_positive_or_missing_eps_ttm",
    "missing_or_non_positive_peer_pe",
    "non_positive_or_missing_bvps",
    "missing_or_non_positive_peer_pb",
    "non_positive_or_missing_ebitda",
    "missing_or_non_positive_peer_ev_ebitda",
    "stale_filing_hard",
    # Step 4.3 additions (multiples.py emits; applicability gates do not):
    "ev_ebitda_negative_equity_post_debt",
    "ev_ebitda_net_debt_unknown",
    "insufficient_peers_all_tiers",
    # Step 4.5 additions (dcf.py emits; applicability gates do not):
    "terminal_g_unsafe_g_too_close_to_wacc",
    "dcf_net_debt_unknown",
    "dcf_negative_equity_post_debt",
    # Step 7.5 — data-quality sanity guard. Applied at the ensemble layer
    # AFTER all 6 methods compute; nulls every method when any value
    # exceeds config.FAIR_PRICE_DATA_QUALITY_CEILING (typically caused
    # by upstream shares_outstanding ingestion bugs).
    "data_quality_input_corruption",
    # PR 3d Tier-2 event defenses. These identifiers also appear in
    # StockDetail.tier2_events (display-side) and risk_flags (only
    # non_reliance_filing — hard veto). They are tracked here for the
    # JSON contract / reason-taxonomy completeness check.
    "going_concern_disclosure",   # Defense #8 — 10-K text scan, annotate-only
    "non_reliance_filing",        # Defense #9 — 8-K Item 4.02, HARD VETO
    "auditor_change",             # Defense #10 — 8-K Item 4.01, annotate-only
)

LagStatus = Literal["fresh", "soft", "hard", "unknown"]


@dataclass(frozen=True)
class MethodApplicability:
    """Applicability decision for a single fair-price method.

    Attributes
    ----------
    applicable : bool
        True iff the method's preconditions are met and it should be invoked.
    reason : str | None
        Stable snake_case identifier explaining the skip; None when
        ``applicable`` is True. Drawn from :data:`SKIP_REASONS`.
    """

    applicable: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.applicable and self.reason is not None:
            raise ValueError("reason must be None when applicable=True")
        if not self.applicable and self.reason is None:
            raise ValueError("reason is required when applicable=False")


_APPLICABLE = MethodApplicability(applicable=True, reason=None)


def _skip(reason: str) -> MethodApplicability:
    return MethodApplicability(applicable=False, reason=reason)


# -- Stale-filing primitives ---------------------------------------------------

def filing_lag_days(filing_date: date | None, asof: date) -> int | None:
    """Days between ``asof`` and ``filing_date`` (positive → filing is older).

    Returns ``None`` when ``filing_date`` is missing. Negative results
    (filing_date in the future relative to asof) are returned as-is — the
    caller may interpret as "fresh" via :func:`stale_filing_status`.
    """
    if filing_date is None:
        return None
    return (asof - filing_date).days


def stale_filing_status(lag_days: int | None) -> LagStatus:
    """Map filing lag to a discrete status.

    Boundary semantics use strict ``>``, so a stock filed exactly
    ``FILING_STALE_SOFT_DAYS`` ago (default 120) is still ``fresh``, and one
    filed exactly ``FILING_STALE_HARD_DAYS`` ago (default 180) is ``soft``.

    Returns
    -------
    "fresh"   — lag ≤ FILING_STALE_SOFT_DAYS
    "soft"    — FILING_STALE_SOFT_DAYS < lag ≤ FILING_STALE_HARD_DAYS
    "hard"    — lag > FILING_STALE_HARD_DAYS
    "unknown" — lag is None
    """
    if lag_days is None:
        return "unknown"
    if lag_days > config.FILING_STALE_HARD_DAYS:
        return "hard"
    if lag_days > config.FILING_STALE_SOFT_DAYS:
        return "soft"
    return "fresh"


def _is_hard_stale(lag_status: LagStatus) -> bool:
    return lag_status == "hard"


def _finite_positive(x: float | None) -> bool:
    """True iff x is a finite, strictly-positive float."""
    if x is None:
        return False
    try:
        v = float(x)
    except (TypeError, ValueError):
        return False
    if v != v:  # NaN
        return False
    if v <= 0.0:
        return False
    return True


# -- Per-method applicability gates -------------------------------------------

def check_dcf_applicability(
    *,
    sector: str | None,
    fcf_5y: list[float | None],
    shares_outstanding: float | None,
    lag_status: LagStatus,
) -> MethodApplicability:
    """DCF: skip Financials & Utilities; require positive median 5y FCF +
    shares outstanding + non-hard-stale filing.

    Sector exclusions apply because (a) Financials' free cash flow is
    structurally distorted by capital regulation and loan-loss provisioning,
    and (b) Utilities' rate-base regulation makes terminal-growth-via-WACC
    DCF unreliable (Damodaran practitioner default). Both sectors are
    handled instead by RIM + multiples.
    """
    if sector == "Financials":
        return _skip("sector_excluded_financials")
    if sector == "Utilities":
        return _skip("sector_excluded_utilities")

    finite_fcf = [float(v) for v in fcf_5y if v is not None]
    if not finite_fcf or median(finite_fcf) <= 0:
        return _skip("non_positive_fcf_5y_median")

    if not _finite_positive(shares_outstanding):
        return _skip("missing_shares_outstanding")

    if _is_hard_stale(lag_status):
        return _skip("stale_filing_hard")

    return _APPLICABLE


def check_graham_applicability(
    *,
    eps_3y_avg: float | None,
    tbvps: float | None,
    lag_status: LagStatus,
) -> MethodApplicability:
    """Graham: requires positive EPS_3y_avg + positive Tangible BVPS.

    Graham (1949) requires both inputs strictly positive — the formula
    ``√(22.5 × EPS × BVPS)`` is undefined for non-positive EPS or BVPS.
    Note ``tbvps`` here is the **tangible** BVPS from
    :func:`compute.valuation.tangible_book.tangible_book_value_per_share`
    (Step 3), NOT the reported BVPS used by the Value pillar's fast-TTM
    Graham implementation in ``compute.features.value``.
    """
    if not _finite_positive(eps_3y_avg):
        return _skip("non_positive_eps_3y_avg")
    if not _finite_positive(tbvps):
        return _skip("non_positive_or_missing_tangible_book")
    if _is_hard_stale(lag_status):
        return _skip("stale_filing_hard")
    return _APPLICABLE


def check_rim_applicability(
    *,
    avg_3y_roe: float | None,
    tbvps: float | None,
    lag_status: LagStatus,
    cost_of_equity: float = config.COST_OF_EQUITY,
) -> MethodApplicability:
    """RIM: any sector OK (book equity meaningful for Financials & Utilities),
    but ROE must exceed cost of equity (else value_trap_risk).

    The ROE-vs-Ke gate is the canonical Penman 2013 RIM condition: a firm
    earning < cost of capital destroys value with each marginal investment,
    so its terminal-residual-income-based fair value is fictitious. The
    skip reason is exactly ``value_trap_risk_roe_below_cost_of_equity`` so
    Step 5 ensemble can append the corresponding warning.

    Issue #11 fix: ``avg_3y_roe is None`` skips under the distinct
    ``insufficient_history_for_roe`` reason — the ensemble does NOT
    append the spurious ``value_trap_risk`` warning for those cases.
    "Missing input" is not the same signal as "real value trap"
    (firm has structurally low ROE).
    """
    if avg_3y_roe is None:
        return _skip("insufficient_history_for_roe")
    if float(avg_3y_roe) <= float(cost_of_equity):
        return _skip("value_trap_risk_roe_below_cost_of_equity")
    if not _finite_positive(tbvps):
        return _skip("non_positive_or_missing_tangible_book")
    if _is_hard_stale(lag_status):
        return _skip("stale_filing_hard")
    return _APPLICABLE


def check_multiples_pe_applicability(
    *,
    eps_ttm: float | None,
    peer_pe_median: float | None,
    lag_status: LagStatus,
) -> MethodApplicability:
    """Sector P/E multiple: requires positive trailing EPS + positive peer median."""
    if not _finite_positive(eps_ttm):
        return _skip("non_positive_or_missing_eps_ttm")
    if not _finite_positive(peer_pe_median):
        return _skip("missing_or_non_positive_peer_pe")
    if _is_hard_stale(lag_status):
        return _skip("stale_filing_hard")
    return _APPLICABLE


def check_multiples_pb_applicability(
    *,
    bvps_reported: float | None,
    peer_pb_median: float | None,
    lag_status: LagStatus,
) -> MethodApplicability:
    """Sector P/B multiple: requires positive **reported** BVPS + positive peer median.

    P/B explicitly uses ``BVPS_reported`` (not Tangible BVPS) because the
    peer-median P/B is computed against reported book equity across all
    peers. Mixing tangible-equity into one stock's denominator while peers
    use reported equity would silently bias the multiple downward; consistent
    treatment matters more than the goodwill-netting refinement here. The
    "goodwill-heavy" annotation (Step 5) is the orthogonal way users see
    when reported BVPS is overstated by acquisition accounting.
    """
    if not _finite_positive(bvps_reported):
        return _skip("non_positive_or_missing_bvps")
    if not _finite_positive(peer_pb_median):
        return _skip("missing_or_non_positive_peer_pb")
    if _is_hard_stale(lag_status):
        return _skip("stale_filing_hard")
    return _APPLICABLE


def check_multiples_ev_ebitda_applicability(
    *,
    sector: str | None,
    ebitda_ttm: float | None,
    peer_ev_ebitda_median: float | None,
    lag_status: LagStatus,
) -> MethodApplicability:
    """EV/EBITDA multiple: skip Financials (no meaningful EBITDA for banks),
    require positive trailing EBITDA + positive peer median.

    Per kickoff §B2, only Financials is excluded for EV/EBITDA — Utilities
    DO have meaningful EBITDA (regulated cap-ex shows up in D&A but the
    operating-income line above it is a real cash measure).
    """
    if sector == "Financials":
        return _skip("sector_excluded_financials")
    if not _finite_positive(ebitda_ttm):
        return _skip("non_positive_or_missing_ebitda")
    if not _finite_positive(peer_ev_ebitda_median):
        return _skip("missing_or_non_positive_peer_ev_ebitda")
    if _is_hard_stale(lag_status):
        return _skip("stale_filing_hard")
    return _APPLICABLE
