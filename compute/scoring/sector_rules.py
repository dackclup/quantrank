"""Sector exclusion rules for sector-relative pillar metrics.

Defense #6 (PR 3c) extends Greenblatt 2005's Magic Formula exclusion
pattern (Financials + Utilities — for which EBIT/EV is meaningless
because the balance sheet is reserves+regulated capital, not productive
working capital) to **all Quality pillar metrics** that depend on EBIT,
gross profit, or invested capital.

The pattern: certain accounting concepts simply don't translate across
sectors — a bank's "gross profit" is net interest income (a totally
different economic quantity from a manufacturer's revenue minus COGS),
and a utility's regulated cap-ex distorts EBIT-based ROIC. Forcing
these metrics through cross-sectional ranking creates spurious quality
scores that drive composite-rank artifacts.

This module is the **single source of truth** for sector exclusions.
Pillar wrappers in ``compute.scoring.pillars`` consult
:func:`is_metric_excluded_for_sector` and replace the metric value with
NaN when the rule fires; the existing pillar-aggregation logic already
handles NaN gracefully (per SKILL.md Rule 7: pillar averages skip NaN
metrics; if ≥50% of a pillar's metrics are NaN, the pillar itself goes
to neutral 50.0).

Note that the **fair-price layer** (``compute.valuation.applicability``)
applies its OWN sector gates — those are intentional duplicates at a
different layer (per-method applicability for fair_price; per-metric
exclusion for pillar score). Both must independently honor the same
sector taxonomy.

Phase 4 will introduce REIT FFO/AFFO substitutes for the Quality pillar
on Real Estate stocks (currently filed as a post-PR-3c-merge issue).
For PR-3c, Real Estate retains the existing Magic Formula exclusion but
no new exclusions are added — REITs DO have meaningful gross profit
and ROIC; the special metric is FFO, not the absence of EBIT.
"""

from __future__ import annotations

# Stable canonical names for sector-blacklisted metrics. Pillar wrappers
# look up these strings (NOT the per-pillar metric_dict keys); the
# wrapper translates between them when applying gates. This keeps the
# blacklist semantically stable even if pillar metric keys are renamed.
SECTOR_BLACKLIST: dict[str, frozenset[str]] = {
    # Existing pattern (Magic Formula composite — kept for forward
    # compatibility; PR-3c does not yet implement a Magic Formula
    # composite, but Phase 4 may).
    "magic_formula": frozenset({"Financials", "Utilities", "Real Estate"}),
    # Existing per-metric: revenue/total_assets is meaningless for banks
    # (their "assets" are loans + securities, not productive capital).
    "asset_turnover": frozenset({"Financials"}),
    # Defense #6 additions (PR 3c) — extending Greenblatt 2005's logic
    # to EBIT-based and gross-profit-based metrics:
    #
    # - EBIT-based ROIC: Financials' EBIT is dominated by net interest
    #   income (not productive operating income); Utilities' EBIT is
    #   regulated to a fixed return on rate base, not market-driven.
    "ebit_based_roic": frozenset({"Financials", "Utilities"}),
    # - Gross profitability (Novy-Marx 2013): "gross profit" for banks
    #   is net interest income — a totally different economic concept
    #   that shouldn't share a percentile distribution with manufacturers.
    "gross_profitability": frozenset({"Financials"}),
    # - EV/EBITDA pillar metric: same EBITDA-meaningless argument as
    #   the fair-price applicability gate (compute.valuation.applicability
    #   .check_multiples_ev_ebitda_applicability), applied at the pillar
    #   layer. Two layers, both honor the same sector taxonomy.
    "ev_ebitda_multiple": frozenset({"Financials"}),
}


def is_metric_excluded_for_sector(
    *,
    metric: str,
    sector: str | None,
) -> bool:
    """Return True if ``metric`` should be NaN for ``sector``.

    Returns False (compute the metric normally) when:

    - ``sector`` is None (no sector info → don't second-guess)
    - ``metric`` is not in :data:`SECTOR_BLACKLIST` (no rule for it)
    - the sector is not in this metric's blacklist

    Examples
    --------
    >>> is_metric_excluded_for_sector(metric="ebit_based_roic",
    ...                               sector="Financials")
    True
    >>> is_metric_excluded_for_sector(metric="ebit_based_roic",
    ...                               sector="Information Technology")
    False
    >>> is_metric_excluded_for_sector(metric="some_random_metric",
    ...                               sector="Financials")
    False
    """
    if sector is None:
        return False
    blacklist = SECTOR_BLACKLIST.get(metric, frozenset())
    return sector in blacklist


__all__ = [
    "SECTOR_BLACKLIST",
    "is_metric_excluded_for_sector",
]
