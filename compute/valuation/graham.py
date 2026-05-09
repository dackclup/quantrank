"""Graham Number fair-price method (defense-aware variant).

Graham (1949) proposed ``Fair = √(22.5 × EPS × BVPS)`` as a conservative
intrinsic-value floor for defensive investors. The 22.5 multiplier is the
canonical product of his maximum-acceptable P/E (15) and P/B (1.5).

This module's variant differs from ``compute.features.value.graham_number``
in **two intentional ways** per the PR-3c kickoff §B2 + the Defense
Playbook §PR 3c #2:

1. **Tangible BVPS** instead of reported BVPS. Tangible book nets
   goodwill + identifiable intangibles, which is the conservative
   practitioner default for the fair-price *anchor* (Penman 2013;
   Damodaran). The Value pillar's reported-BVPS Graham is intentionally
   kept fast-TTM for cross-sectional ranking.

2. **EPS_3y_avg** instead of EPS_TTM. Graham's stated input is
   "average earnings per share over the past 3 years" — using the
   trailing-twelve-month figure overshoots in cyclical peaks and
   undershoots in troughs. The Value pillar uses TTM EPS for ranking
   responsiveness; the fair-price anchor uses 3y average for stability.

The function returns ``(fair_value, MethodApplicability)`` per the
unified contract for all 6 fair-price methods (Step 4.x). When
applicability fails, the float is ``None`` and the applicability carries
the reason; when applicability passes the float is the Graham number.

Cross-reference: ``compute/features/value.py::graham_number`` (pillar
fast-TTM variant) — kept side-by-side intentionally so the stock detail
UI (Phase 3d) can surface the divergence between the two anchors.
"""

from __future__ import annotations

import math

from compute.valuation.applicability import (
    LagStatus,
    MethodApplicability,
    check_graham_applicability,
)

# Internal stable identifier for the unreachable-but-defensive
# post-gate math sanity check. NOT included in SKIP_REASONS because
# the applicability gate is comprehensive — this branch fires only on
# a genuine programming error in upstream gates. Step 5 ensemble may
# log it as an internal-error signal rather than a user-facing reason.
_POST_GATE_PRODUCT_NON_POSITIVE = "graham_product_non_positive_post_gate"

# Graham's canonical multiplier: max P/E (15) × max P/B (1.5).
# NOT a tuning knob; do NOT relocate to config.
_GRAHAM_MULTIPLIER = 22.5


def graham_fair_price(
    *,
    eps_3y_avg: float | None,
    tangible_book_value_per_share: float | None,
    lag_status: LagStatus,
) -> tuple[float | None, MethodApplicability]:
    """Compute the Graham number for one ticker.

    Parameters
    ----------
    eps_3y_avg : float | None
        Trailing 3-fiscal-year average diluted EPS. ``None`` or
        non-positive triggers an applicability skip.
    tangible_book_value_per_share : float | None
        TBVPS from
        :func:`compute.valuation.tangible_book.tangible_book_value_per_share`.
        ``None`` or non-positive triggers an applicability skip.
    lag_status : LagStatus
        Filing freshness from
        :func:`compute.valuation.applicability.stale_filing_status`.
        ``"hard"`` triggers a skip; ``"soft"``/``"unknown"`` are
        permissive (Step 5 ensemble may apply additional treatment).

    Returns
    -------
    tuple[float | None, MethodApplicability]
        ``(fair_value, applicability)``. If ``applicability.applicable``
        is False the float is None and the reason explains why.

    Examples
    --------
    >>> # Synthetic: EPS=$2, TBVPS=$10 → √(22.5 × 2 × 10) = √450 ≈ 21.21
    >>> graham_fair_price(eps_3y_avg=2.0,
    ...                   tangible_book_value_per_share=10.0,
    ...                   lag_status="fresh")
    (21.213203435596427, MethodApplicability(applicable=True, reason=None))
    """
    app = check_graham_applicability(
        eps_3y_avg=eps_3y_avg,
        tbvps=tangible_book_value_per_share,
        lag_status=lag_status,
    )
    if not app.applicable:
        return (None, app)

    # Defensive: applicability gate guarantees both inputs strictly
    # positive and finite, so this branch is mathematically unreachable.
    # We keep it as runtime safety in case of a future regression in the
    # gate logic — better to surface a nominal skip than crash on
    # math.sqrt of a negative.
    product = (
        _GRAHAM_MULTIPLIER
        * float(eps_3y_avg)  # type: ignore[arg-type]
        * float(tangible_book_value_per_share)  # type: ignore[arg-type]
    )
    if product <= 0 or not math.isfinite(product):
        return (
            None,
            MethodApplicability(
                applicable=False,
                reason=_POST_GATE_PRODUCT_NON_POSITIVE,
            ),
        )

    fair_value = math.sqrt(product)
    return (fair_value, MethodApplicability(applicable=True, reason=None))
