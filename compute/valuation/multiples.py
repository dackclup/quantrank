"""Sector P/E + P/B + EV/EBITDA fair-price methods (multiples).

Three methods share the same peer-tier walk for cross-sectional median
computation: try sub-industry → industry → sector → broad ex Financials/
Utilities, taking the first tier with at least ``MULTIPLES_MIN_PEERS=8``
valid peers. Each tier reports its peer count back so Step 5 ensemble
can surface the choice in ``StockDetail.fair_price.methods.<method>.tier_used``.

Per-tier processing:

1. Filter out the **target ticker itself** from any peer set — comparing
   a stock to itself is a circular definition.
2. Filter peer values that are ``None`` or non-positive (P/E with
   negative EPS isn't a meaningful peer; the corresponding stock might
   itself be skipped by its own applicability gate).
3. **Winsorize at 5th/95th percentile** to limit the influence of
   outliers (a rumored-takeover small-cap with P/E 200 shouldn't dominate
   the sector median for the rest of its industry).
4. Take the median of the winsorized survivors.

Per-method math (fair price per share):

- **P/E**:        ``EPS_TTM × peer_PE_median``
- **P/B**:        ``BVPS_reported × peer_PB_median`` (NOT TBVPS — peer
                  comparability; Step 4.1 documents the rationale)
- **EV/EBITDA**:  ``(EBITDA_TTM × peer_EV/EBITDA − net_debt) / shares``
                  where ``net_debt = total_debt − cash``. Returns
                  ``ev_ebitda_negative_equity_post_debt`` if equity value
                  is negative after the debt subtraction (high-leverage
                  edge case), and ``ev_ebitda_net_debt_unknown`` if
                  ``net_debt`` itself is missing (the upstream caller
                  couldn't compute total_debt − cash from the snapshot).

The cross-sectional peer-tier walk is implemented in
:func:`compute_peer_medians`, which is a **pure** function: it takes
precomputed ``tickers_by_tier`` and ``metric_values`` dicts and walks
the hierarchy. It does NOT fetch data, does NOT classify GICS sectors —
Step 5 ensemble owns that orchestration.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from enum import StrEnum

from compute import config
from compute.valuation.applicability import (
    LagStatus,
    MethodApplicability,
    check_multiples_ev_ebitda_applicability,
    check_multiples_pb_applicability,
    check_multiples_pe_applicability,
)


class PeerTierUsed(StrEnum):
    """Which tier the peer median was computed from.

    Walked in priority order; first tier with ≥ MULTIPLES_MIN_PEERS valid
    peers wins. ``INSUFFICIENT`` indicates all 4 tiers failed.
    """

    SUB_INDUSTRY = "sub_industry"
    INDUSTRY = "industry"
    SECTOR = "sector"
    BROAD_EX_FIN_UTIL = "broad_ex_financials_utilities"
    INSUFFICIENT = "insufficient_peers"


@dataclass(frozen=True)
class PeerMedian:
    """Result of a peer-median walk for one (target, metric) pair.

    Attributes
    ----------
    median : float | None
        Winsorized peer median; ``None`` if all 4 tiers had < min peers.
    tier_used : PeerTierUsed
        The tier whose peer set produced the median; or ``INSUFFICIENT``.
    peer_count : int
        Number of valid peers in the chosen tier (or 0 if INSUFFICIENT).
    tier_thresholds_tried : tuple[tuple[PeerTierUsed, int], ...]
        Per-tier (tier, peer_count) audit trail. Step 5/UI may surface this
        for transparency on which tiers were too small.
    """

    median: float | None
    tier_used: PeerTierUsed
    peer_count: int
    tier_thresholds_tried: tuple[tuple[PeerTierUsed, int], ...]


# Internal: tiers walked in priority order.
_TIER_WALK_ORDER: tuple[PeerTierUsed, ...] = (
    PeerTierUsed.SUB_INDUSTRY,
    PeerTierUsed.INDUSTRY,
    PeerTierUsed.SECTOR,
    PeerTierUsed.BROAD_EX_FIN_UTIL,
)


def _linear_percentile(sorted_values: list[float], p: float) -> float:
    """Numpy-default linear interpolation percentile.

    ``p`` is in [0, 1]. ``sorted_values`` is a non-empty pre-sorted list.
    Uses interpolation between the two surrounding points; matches
    numpy.percentile default behavior.
    """
    n = len(sorted_values)
    if n == 0:
        raise ValueError("empty input to _linear_percentile")
    if n == 1:
        return float(sorted_values[0])
    rank = p * (n - 1)
    lo = int(rank)
    hi = min(lo + 1, n - 1)
    frac = rank - lo
    return float(sorted_values[lo]) + frac * (
        float(sorted_values[hi]) - float(sorted_values[lo])
    )


def _winsorize_5_95(values: list[float]) -> list[float]:
    """Clip values to the [5th percentile, 95th percentile] band.

    Empty input → empty output. Single-element input is returned as-is
    (percentiles are degenerate). For ≥2 values, computes 5th and 95th
    percentile via linear interpolation and clips each value.
    """
    if not values:
        return []
    sorted_v = sorted(values)
    p_low = _linear_percentile(sorted_v, 0.05)
    p_high = _linear_percentile(sorted_v, 0.95)
    return [max(p_low, min(p_high, float(v))) for v in values]


def _filter_valid_metric(
    tickers: list[str],
    metric_values: dict[str, float | None],
    target_ticker: str,
) -> list[float]:
    """Return positive finite metric values for peers ≠ target_ticker.

    Skips ``target_ticker`` (self-comparison would be circular) and any
    peer whose metric is missing, NaN, or non-positive.
    """
    out: list[float] = []
    for t in tickers:
        if t == target_ticker:
            continue
        v = metric_values.get(t)
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(f) or f <= 0.0:
            continue
        out.append(f)
    return out


def compute_peer_medians(
    *,
    tickers_by_tier: dict[PeerTierUsed, list[str]],
    metric_values: dict[str, float | None],
    target_ticker: str,
    min_peers: int = config.MULTIPLES_MIN_PEERS,
) -> PeerMedian:
    """Walk the 4-tier hierarchy and return the first tier with ≥ ``min_peers``.

    Within each tier:

    1. Exclude the target ticker.
    2. Filter to positive finite metric values.
    3. If ≥ ``min_peers`` survivors → winsorize at 5/95 and take median.
    4. Otherwise record the count and fall through to the next tier.

    If all 4 tiers fail, return ``median=None`` with
    ``tier_used=PeerTierUsed.INSUFFICIENT`` and the audit trail.
    """
    tier_audit: list[tuple[PeerTierUsed, int]] = []

    for tier in _TIER_WALK_ORDER:
        tickers = tickers_by_tier.get(tier, [])
        peer_values = _filter_valid_metric(tickers, metric_values, target_ticker)
        peer_count = len(peer_values)
        tier_audit.append((tier, peer_count))
        if peer_count >= min_peers:
            winsorized = _winsorize_5_95(peer_values)
            median_v = float(statistics.median(winsorized))
            return PeerMedian(
                median=median_v,
                tier_used=tier,
                peer_count=peer_count,
                tier_thresholds_tried=tuple(tier_audit),
            )

    return PeerMedian(
        median=None,
        tier_used=PeerTierUsed.INSUFFICIENT,
        peer_count=0,
        tier_thresholds_tried=tuple(tier_audit),
    )


def _insufficient_peers(tier: PeerTierUsed) -> MethodApplicability | None:
    """Common gate: if peer-tier walk landed at INSUFFICIENT, skip with
    the dedicated reason rather than the generic missing-peer reason.

    Returns ``None`` when the tier is acceptable (caller falls through).
    """
    if tier == PeerTierUsed.INSUFFICIENT:
        return MethodApplicability(
            applicable=False,
            reason="insufficient_peers_all_tiers",
        )
    return None


def multiples_pe_fair_price(
    *,
    eps_ttm: float | None,
    peer_pe_median: float | None,
    peer_tier_used: PeerTierUsed,
    lag_status: LagStatus,
) -> tuple[float | None, MethodApplicability]:
    """Sector-multiple P/E fair price: ``EPS_TTM × peer_PE_median``.

    The peer median is precomputed by Step 5 ensemble via
    :func:`compute_peer_medians`. This function only multiplies and
    enforces gates. ``peer_tier_used == INSUFFICIENT`` short-circuits
    with the dedicated reason; other tier values are passed through.
    """
    short = _insufficient_peers(peer_tier_used)
    if short is not None:
        return (None, short)

    app = check_multiples_pe_applicability(
        eps_ttm=eps_ttm,
        peer_pe_median=peer_pe_median,
        lag_status=lag_status,
    )
    if not app.applicable:
        return (None, app)

    fair = float(eps_ttm) * float(peer_pe_median)  # type: ignore[arg-type]
    return (fair, MethodApplicability(applicable=True, reason=None))


def multiples_pb_fair_price(
    *,
    bvps_reported: float | None,
    peer_pb_median: float | None,
    peer_tier_used: PeerTierUsed,
    lag_status: LagStatus,
) -> tuple[float | None, MethodApplicability]:
    """Sector-multiple P/B fair price: ``BVPS_reported × peer_PB_median``.

    Uses **reported** BVPS, not TBVPS — peers report on book equity, so
    consistent treatment is required for an unbiased multiple. The
    "goodwill_heavy" annotation (Step 5) is the orthogonal way to surface
    that one stock's reported BVPS is overstated by acquisition accounting.
    """
    short = _insufficient_peers(peer_tier_used)
    if short is not None:
        return (None, short)

    app = check_multiples_pb_applicability(
        bvps_reported=bvps_reported,
        peer_pb_median=peer_pb_median,
        lag_status=lag_status,
    )
    if not app.applicable:
        return (None, app)

    fair = float(bvps_reported) * float(peer_pb_median)  # type: ignore[arg-type]
    return (fair, MethodApplicability(applicable=True, reason=None))


def multiples_ev_ebitda_fair_price(
    *,
    sector: str | None,
    ebitda_ttm: float | None,
    peer_ev_ebitda_median: float | None,
    peer_tier_used: PeerTierUsed,
    net_debt: float | None,
    shares_outstanding: float | None,
    lag_status: LagStatus,
) -> tuple[float | None, MethodApplicability]:
    """Sector-multiple EV/EBITDA fair equity-per-share.

    Math:

        EV          = EBITDA × peer_EV/EBITDA
        equity      = EV − net_debt
        fair/share  = equity / shares

    Skips when:

    - ``peer_tier_used == INSUFFICIENT`` → ``insufficient_peers_all_tiers``
    - Standard applicability fail (Financials sector / non-positive
      EBITDA / non-positive peer / hard-stale)
    - ``net_debt`` is None → ``ev_ebitda_net_debt_unknown`` (we can't
      reliably value equity without it)
    - ``shares_outstanding`` is None or 0 → ``missing_shares_outstanding``
    - ``equity_value`` is negative post-debt-subtraction →
      ``ev_ebitda_negative_equity_post_debt``
    """
    short = _insufficient_peers(peer_tier_used)
    if short is not None:
        return (None, short)

    app = check_multiples_ev_ebitda_applicability(
        sector=sector,
        ebitda_ttm=ebitda_ttm,
        peer_ev_ebitda_median=peer_ev_ebitda_median,
        lag_status=lag_status,
    )
    if not app.applicable:
        return (None, app)

    if net_debt is None:
        return (
            None,
            MethodApplicability(
                applicable=False,
                reason="ev_ebitda_net_debt_unknown",
            ),
        )

    if shares_outstanding is None or shares_outstanding <= 0:
        return (
            None,
            MethodApplicability(
                applicable=False,
                reason="missing_shares_outstanding",
            ),
        )

    enterprise_value = float(ebitda_ttm) * float(peer_ev_ebitda_median)  # type: ignore[arg-type]
    equity_value = enterprise_value - float(net_debt)
    if equity_value <= 0:
        return (
            None,
            MethodApplicability(
                applicable=False,
                reason="ev_ebitda_negative_equity_post_debt",
            ),
        )

    fair = equity_value / float(shares_outstanding)
    return (fair, MethodApplicability(applicable=True, reason=None))
