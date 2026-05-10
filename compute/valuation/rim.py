"""Residual Income Model (RIM) fair-price method.

Penman 2013 (*Financial Statement Analysis and Security Valuation*, 5e §5)
gives the canonical RIM formula:

    V_0 = B_0 + Σ_{t=1..N} [(ROE_t − Ke) × B_{t−1}] / (1 + Ke)^t   + TV/(1+Ke)^N

We ship the **conservative** variant: zero terminal value beyond year ``N``.
Penman's terminal-RIM extensions (a perpetuity continuing residual income
or a fade-to-zero) introduce a long-horizon assumption that's empirically
very fragile; truncating at the explicit forecast period is the
practitioner's "show me, don't tell me" stance and aligns with the
defense-layer principle (annotate-and-veto, never overclaim).

Simplifying assumption: **constant ROE** (= ``avg_3y_roe``) across the
forecast horizon, full-retention book accumulation:

    B_t = B_{t−1} × (1 + ROE)

Full retention (no dividend cash-out) makes book grow faster than reality
for high-payout stocks. This is **conservative for fair price**: a
high-payout firm's intrinsic value is lower than what RIM with full
retention would suggest, but the over-statement is bounded by the
combined skip gates (we already require ROE > Ke before computing).
Phase 4+ may extend with payout_ratio as data becomes available.

**Critical input choice — TBVPS, NOT BVPS_reported**: this is the
**OPPOSITE** of the P/B multiples method (Step 4.3) and intentional.

- P/B is **peer-relative** — the peer median is computed from reported
  book equity across all peers, so consistent treatment requires
  reported BVPS on both sides of the multiplication.
- RIM is **single-stock** — there's no peer comparison; the model
  needs a starting-equity base ``B_0``. Using tangible book gives the
  most conservative starting base by writing off goodwill +
  identifiable intangibles upfront. Acquisition-heavy firms with large
  unrecoverable goodwill on the balance sheet would otherwise overstate
  V_0 by the post-amortization carrying value.

Per the kickoff §B2 RIM applicability rule: skip when
``avg_3y_roe ≤ cost_of_equity`` (value-trap risk). The applicability
gate (Step 4.1) emits the exact reason
``value_trap_risk_roe_below_cost_of_equity`` so Step 5 ensemble can
append a corresponding warning to ``valuation_warnings``.
"""

from __future__ import annotations

import math

from compute import config
from compute.valuation.applicability import (
    LagStatus,
    MethodApplicability,
    check_rim_applicability,
)

# Module-local stable identifier for the defensive book-overflow guard.
# NOT in the public SKIP_REASONS taxonomy — same pattern as Step 4.2's
# _POST_GATE_PRODUCT_NON_POSITIVE. Step 5 ensemble may log it as an
# internal-error signal rather than a user-facing reason.
_RIM_BOOK_OVERFLOW = "rim_book_value_overflow"

# Defensive cap on book value during iterative compounding. ROE values
# >100% for many years can blow past float64 range; we surface a clean
# skip rather than emit infinity. Threshold chosen to comfortably exceed
# any plausible 5-year compound (3^5 ≈ 243 from a starting base of
# millions still leaves multiple orders of magnitude of headroom).
_BOOK_OVERFLOW_THRESHOLD = 1e15


def rim_fair_price(
    *,
    tangible_book_value_per_share: float | None,
    avg_3y_roe: float | None,
    cost_of_equity: float = config.COST_OF_EQUITY,
    forecast_years: int = config.RIM_FORECAST_YEARS,
    lag_status: LagStatus,
) -> tuple[float | None, MethodApplicability]:
    """Compute RIM fair price per share for one ticker.

    Parameters
    ----------
    tangible_book_value_per_share : float | None
        ``B_0`` — initial book equity per share (TBVPS, not reported).
        ``None`` or non-positive triggers an applicability skip.
    avg_3y_roe : float | None
        Trailing 3-fiscal-year average ROE (decimal — 0.15 = 15%). Held
        constant across the forecast horizon. ``None`` or ``≤ Ke``
        triggers ``value_trap_risk_roe_below_cost_of_equity``.
    cost_of_equity : float
        ``Ke`` — discount rate for residual income. Default
        :data:`config.COST_OF_EQUITY` (0.10). Phase 7 may pass per-sector
        Ke estimates.
    forecast_years : int
        ``N`` — explicit forecast horizon. Default
        :data:`config.RIM_FORECAST_YEARS` (5). No terminal value is
        computed beyond ``N``.
    lag_status : LagStatus
        Filing freshness. ``"hard"`` triggers a skip;
        ``"soft"``/``"unknown"`` are permissive.

    Returns
    -------
    tuple[float | None, MethodApplicability]
        ``(V_0, applicability)``. If applicability fails, the float is
        None and the reason explains why. The defensive overflow guard
        emits ``rim_book_value_overflow`` (module-local identifier).
    """
    app = check_rim_applicability(
        avg_3y_roe=avg_3y_roe,
        tbvps=tangible_book_value_per_share,
        lag_status=lag_status,
        cost_of_equity=cost_of_equity,
    )
    if not app.applicable:
        return (None, app)

    # Applicability gate guarantees: tbvps > 0; avg_3y_roe > Ke; lag != hard.
    book = float(tangible_book_value_per_share)  # type: ignore[arg-type]
    roe = float(avg_3y_roe)  # type: ignore[arg-type]
    ke = float(cost_of_equity)
    spread = roe - ke

    pv_residual_total = 0.0
    for t in range(1, forecast_years + 1):
        residual_income = spread * book
        discount_factor = (1.0 + ke) ** t
        pv_residual_total += residual_income / discount_factor

        # Update book for next iteration: B_t = B_{t-1} × (1 + ROE).
        book = book * (1.0 + roe)

        # Defensive overflow guard. Plausible inputs (ROE up to ~200%)
        # over the default 5y horizon stay comfortably finite; this only
        # fires on pathological combinations or future regression in the
        # gate logic.
        if not math.isfinite(book) or book > _BOOK_OVERFLOW_THRESHOLD:
            return (
                None,
                MethodApplicability(
                    applicable=False,
                    reason=_RIM_BOOK_OVERFLOW,
                ),
            )

    v_0 = float(tangible_book_value_per_share) + pv_residual_total  # type: ignore[arg-type]
    return (v_0, MethodApplicability(applicable=True, reason=None))
