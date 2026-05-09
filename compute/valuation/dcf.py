"""Two-stage Discounted Cash Flow (DCF) fair-price method.

Standard practitioner two-stage model:

- **Stage 1 (explicit forecast, default 5 years)**: project a *normalized*
  FCF flat across the horizon — no per-year growth assumption. This is
  the conservative-for-fair-price stance: a 5-year flat-FCF DCF anchors
  on what the firm has actually demonstrated, not on the forward growth
  story the market is pricing in.

- **Stage 2 (Gordon Growth terminal)**: ``TV = FCF × (1 + g) / (WACC − g)``,
  discounted to PV at year ``N``. The terminal value typically dominates
  total intrinsic value (often 60-80% of EV per Damodaran), which is
  why the terminal-g constraint (Defense #5) is the most consequential
  input gate in this module.

Defense #5 — terminal-g constraint (per kickoff §B4):

    g ≤ min(config.TERMINAL_GROWTH = 0.03, WACC − 0.01)

Both caps must hold. The 0.03 long-run nominal-GDP cap is the Damodaran
practitioner default (no firm grows faster than the economy in
perpetuity); the 100bp buffer below WACC is mathematical safety
(g approaching WACC sends TV → ∞). When the user-supplied
``terminal_growth`` exceeds either cap, the function emits
``terminal_g_unsafe_g_too_close_to_wacc`` and returns no value.

FCF normalization choice: **median of positive trailing-5y values**.

- *Median* (not mean) for robustness against one-off outliers (a
  COVID-year writeoff or a one-time tax benefit shouldn't anchor the
  next 5 years of forecasts).
- *Positive only* — non-positive FCF years are excluded from the
  normalization (the applicability gate ensures the broader median
  is positive, so this filter is a refinement, not a relaxation).

Net-debt is **mandatory**: enterprise → equity → per-share conversion
demands ``net_debt = total_debt − cash``. ``net_debt = None`` triggers
``dcf_net_debt_unknown`` (we won't silently coerce to zero — for
leveraged firms that materially overstates equity per share).

Sector exclusions (from Step 4.1 applicability gate):

- **Financials**: cash flows from operations are dominated by reserve
  releases and loan-loss provisioning, not real economic FCF. Use
  RIM + multiples instead.
- **Utilities**: regulated returns + special-purpose-vehicle accounting
  make Gordon-growth terminal unreliable. Use RIM + multiples instead.
"""

from __future__ import annotations

import math
import statistics

from compute import config
from compute.valuation.applicability import (
    LagStatus,
    MethodApplicability,
    check_dcf_applicability,
)

# Module-local stable identifier for the defensive "no valid FCF after gate"
# branch. Mathematically unreachable: the gate guarantees the trailing-5y
# median is > 0, so the positives-only sub-filter must yield ≥ 1 positive
# value (any non-positive median would have failed the gate). Kept as
# runtime safety per Step 4.2's _POST_GATE_PRODUCT_NON_POSITIVE pattern;
# NOT in the public SKIP_REASONS taxonomy.
_DCF_NO_VALID_FCF_POST_GATE = "dcf_no_valid_fcf_post_gate"

# 100bp buffer below WACC (Defense #5 math safety).
_WACC_TERMINAL_BUFFER = 0.01


def dcf_fair_price(
    *,
    sector: str | None,
    fcf_5y: list[float | None],
    shares_outstanding: float | None,
    net_debt: float | None,
    lag_status: LagStatus,
    wacc: float = config.DISCOUNT_RATE,
    terminal_growth: float = config.TERMINAL_GROWTH,
    forecast_years: int = config.DCF_FORECAST_YEARS,
) -> tuple[float | None, MethodApplicability]:
    """Compute two-stage DCF fair price per share.

    Parameters
    ----------
    sector : str | None
        GICS level-1. ``Financials`` and ``Utilities`` are excluded by
        the applicability gate.
    fcf_5y : list[float | None]
        Most-recent 5 fiscal years of free cash flow (any unit, but
        consistent with ``net_debt``). The applicability gate requires
        the median (over non-None entries) to be positive; this function
        further filters to positives-only for the normalization anchor.
    shares_outstanding : float | None
        Diluted shares outstanding for per-share conversion.
    net_debt : float | None
        ``total_debt − cash``. **Required**: ``None`` triggers a skip
        (we won't silently zero it, since leverage materially affects
        equity per share). Negative values (cash exceeds debt) are
        valid and increase per-share fair value.
    lag_status : LagStatus
        Filing freshness. ``"hard"`` triggers a skip;
        ``"soft"``/``"unknown"`` are permissive.
    wacc : float
        Weighted-average cost of capital. Default
        :data:`config.DISCOUNT_RATE` (0.10). Phase 7 may pass per-sector
        WACC estimates.
    terminal_growth : float
        Gordon-growth terminal rate. Default
        :data:`config.TERMINAL_GROWTH` (0.03). Hard-capped per Defense #5
        at ``min(config.TERMINAL_GROWTH, wacc − 0.01)``.
    forecast_years : int
        Stage-1 explicit forecast horizon. Default
        :data:`config.DCF_FORECAST_YEARS` (5).

    Returns
    -------
    tuple[float | None, MethodApplicability]
        ``(fair_price_per_share, applicability)``. If applicability
        fails, the float is None and the reason explains why.
    """
    app = check_dcf_applicability(
        sector=sector,
        fcf_5y=fcf_5y,
        shares_outstanding=shares_outstanding,
        lag_status=lag_status,
    )
    if not app.applicable:
        return (None, app)

    # Defense #5 — terminal-g constraint validated against BOTH caps.
    # The 0.03 long-run nominal-GDP cap (config.TERMINAL_GROWTH) and the
    # 100bp WACC math-safety buffer must both hold. User-supplied
    # terminal_growth above either cap triggers a skip.
    g_safe_cap = min(config.TERMINAL_GROWTH, wacc - _WACC_TERMINAL_BUFFER)
    if terminal_growth > g_safe_cap:
        return (
            None,
            MethodApplicability(
                applicable=False,
                reason="terminal_g_unsafe_g_too_close_to_wacc",
            ),
        )

    # Net-debt is mandatory (gate doesn't check it because Step 4.1's
    # check_dcf_applicability is shared with future use cases that may
    # not need net_debt; this is the DCF-specific add-on).
    if net_debt is None:
        return (
            None,
            MethodApplicability(
                applicable=False,
                reason="dcf_net_debt_unknown",
            ),
        )

    # Normalize FCF: median of positives only. Defensive empty-check is
    # mathematically unreachable given the gate passed (the gate's
    # median > 0 implies at least one positive value), but kept for
    # runtime safety against a future regression in the gate logic.
    valid_fcf = [float(f) for f in fcf_5y if f is not None and f > 0]
    if not valid_fcf:
        return (
            None,
            MethodApplicability(
                applicable=False,
                reason=_DCF_NO_VALID_FCF_POST_GATE,
            ),
        )
    fcf_normalized = float(statistics.median(valid_fcf))

    # Stage 1: discount the flat FCF anchor over the explicit forecast.
    stage1_pv = 0.0
    for t in range(1, forecast_years + 1):
        stage1_pv += fcf_normalized / ((1.0 + wacc) ** t)

    # Stage 2: Gordon Growth terminal, then PV to year 0.
    terminal_value = fcf_normalized * (1.0 + terminal_growth) / (wacc - terminal_growth)
    stage2_pv = terminal_value / ((1.0 + wacc) ** forecast_years)

    enterprise_value = stage1_pv + stage2_pv

    # Defensive: NaN/inf protection on intermediate math.
    if not math.isfinite(enterprise_value):
        return (
            None,
            MethodApplicability(
                applicable=False,
                reason=_DCF_NO_VALID_FCF_POST_GATE,
            ),
        )

    equity_value = enterprise_value - float(net_debt)
    if equity_value <= 0:
        return (
            None,
            MethodApplicability(
                applicable=False,
                reason="dcf_negative_equity_post_debt",
            ),
        )

    fair_per_share = equity_value / float(shares_outstanding)  # type: ignore[arg-type]
    return (fair_per_share, MethodApplicability(applicable=True, reason=None))
