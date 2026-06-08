"""Deterministic AI-pick selection + inverse-volatility weighting (Phase 7.0).

Pure functions (no I/O) so the "fair pick" is reproducible and unit-testable
offline. The forward pick runs every cron (populating ``StockSummary.suggested_weight``
in a later PR); the point-in-time backfill reuses the SAME functions per
historical rebalance date.

Selection rule
--------------
Highest ``composite_score``, EXCLUDING the 7 active rank-gate VETOES
(annotate-only flags do NOT exclude — annotate-before-veto). NO sector cap
(removed 2026-06-06, user decision): the basket is the top-``count`` eligible
names by composite, so it can concentrate in a single sector — a deliberate
concentrated-factor construct (the composite already does sector-relative +
neutralized scoring, so picks stay merit-based; the concentration is surfaced in
the UI + disclaimer, never silent). Total order tiebreak:
``composite_score_adjusted`` desc (nets the manipulation index) then ``ticker``
asc (reproducibility).

Weighting rule
--------------
Inverse-volatility: ``w_i ∝ 1/σ_i`` (σ = trailing daily-return stdev), capped at
``MAX_WEIGHT`` and renormalized to sum 1.

Why inverse-vol (methodology-scientist RATIFY 2026-06-04):
- Asness-Frazzini-Pedersen 2012 *FAJ* "Leverage Aversion and Risk Parity"
  (unlevered RP = inverse-vol, weights rescaled to sum 1; higher Sharpe than
  cap-weight) + the within-equity extension Frazzini-Pedersen 2014 *JFE* "Betting
  Against Beta".
- DeMiguel-Garlappi-Uppal 2009 *RFS* "Optimal Versus Naive Diversification" —
  1/N is the hard out-of-sample baseline; inverse-vol avoids the covariance
  estimation error that sinks Markowitz/NCO, so it is the defensible v1 middle.
- NOT composite-proportional: ``composite_score`` is an ORDINAL percentile rank,
  not a cardinal expected return — weighting proportional to it is a Stevens
  scale-type error (and would let the score drive capital allocation the way
  Rule 16 forbids it from driving rank-suppression).

The 35% cap + 90d window are gut-feel calibrations (disclosed). The cap only
binds for ``count >= 4`` (at N=2 it floors below equal-weight and collapses to
1/N; at N=3 it barely binds) — a documented, intended concentration guard for
the larger-basket regime, inert-to-degenerate below.
"""
from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

# The 7 active rank-gate VETOES (compute/scoring/recommendation.py +
# risk_overlay.py). A stock carrying any of these is EXCLUDED from the auto-pick;
# the ~26 annotate-only flags do not exclude (annotate-before-veto). Keep in
# sync with the headline veto count in CLAUDE.md §Phase status.
ACTIVE_VETO_FLAGS: frozenset[str] = frozenset(
    {
        "altman_distress",
        "sloan_accruals_top_decile",
        "net_issuance_top_decile",
        "non_reliance_filing",
        "beneish_manipulation_veto",
        "dechow_manipulation_veto",
        "data_quality_input_corruption",
    }
)

MIN_PICKS: int = 1
MAX_PICKS: int = 20  # 1-20 holding-count ladder (was 10; backtest-only — the
# live forward compute / Top-5 does NOT import this). Drives the backtest's
# by_count[1..MAX_PICKS] + the home slider's max via meta.max_holdings.
MAX_WEIGHT: float = 0.35  # single-name concentration cap (gut-feel; disclosed)
# NOTE: the 2-per-sector diversification cap (MAX_PER_SECTOR / MIN_COUNT_FOR_SECTOR_CAP)
# was REMOVED 2026-06-06 (user decision) — the basket now concentrates by composite
# alone. inverse-vol + MAX_WEIGHT bound single-NAME risk; single-SECTOR concentration
# is intentional + disclosed (methodology-scientist APPROVED 2026-06-06).
SIGMA_WINDOW_DAYS: int = 90  # trailing daily-return stdev window


@dataclass(frozen=True)
class PickCandidate:
    """The minimal per-stock view the pick rule reads — all fields already on
    ``StockSummary`` / rankings.json, so the pick uses ONLY ranking+detail data."""

    ticker: str
    composite_score: float
    sector: str
    risk_flags: tuple[str, ...] = field(default_factory=tuple)
    composite_score_adjusted: float | None = None


def is_eligible(risk_flags: Iterable[str] | None) -> bool:
    """True when the stock carries NO active rank-gate veto (annotate flags OK)."""
    return not (ACTIVE_VETO_FLAGS & set(risk_flags or ()))


def select_picks(candidates: Sequence[PickCandidate], count: int) -> list[str]:
    """Return the ordered ``count`` AI-picked tickers (deterministic + fair).

    composite desc -> drop the active rank-gate vetoes -> take the top ``count``
    (clamped to ``[MIN_PICKS, MAX_PICKS]``). NO sector cap (removed 2026-06-06):
    the basket is purely the highest-composite eligible names, so it can
    concentrate in one sector — that concentration is surfaced in the UI +
    disclaimer, never silently constrained. Tiebreak: ``composite_score_adjusted``
    desc (nets the manipulation index) then ``ticker`` asc.
    """
    count = max(MIN_PICKS, min(MAX_PICKS, count))
    eligible = [c for c in candidates if is_eligible(c.risk_flags)]
    eligible.sort(
        key=lambda c: (
            -c.composite_score,
            -(
                c.composite_score_adjusted
                if c.composite_score_adjusted is not None
                else c.composite_score
            ),
            c.ticker,
        )
    )
    return [c.ticker for c in eligible[:count]]


def inverse_vol_weights(
    sigmas: dict[str, float], cap: float = MAX_WEIGHT
) -> dict[str, float]:
    """Inverse-volatility weights, capped at ``cap``, renormalized to sum 1.0.

    ``w_i ∝ 1/σ_i``. Names with non-positive / non-finite σ are dropped (an
    undefined vol can't be risk-weighted). The cap is applied iteratively:
    over-cap names pin at ``cap`` and the residual redistributes pro-rata across
    the uncapped names until none exceeds the cap. When the cap is mechanically
    infeasible (``N * cap < 1``, e.g. cap 0.35 with N < 3) it degrades to equal
    weight — the closest feasible point; the COUNT slider owns the 1-name
    concentration warning. Returns ``{}`` when no name has a usable σ.
    """
    usable = {
        t: float(s)
        for t, s in sigmas.items()
        if isinstance(s, (int, float)) and math.isfinite(float(s)) and float(s) > 0
    }
    if not usable:
        return {}
    n = len(usable)
    if n * cap < 1.0 - 1e-12:  # cap infeasible → equal weight
        return {t: 1.0 / n for t in usable}

    raw = {t: 1.0 / s for t, s in usable.items()}
    pinned: set[str] = set()
    weights: dict[str, float] = {}
    # Pin over-cap names PERMANENTLY and redistribute only across the still-free
    # names — a previously-capped name must not absorb residual on a later pass
    # (that oscillates back above the cap). Converges in <= n passes: the mean
    # weight 1/n <= cap whenever the cap is feasible, so not all names can pin.
    for _ in range(n + 1):
        free = [t for t in usable if t not in pinned]
        free_raw_total = sum(raw[t] for t in free)
        remaining = 1.0 - len(pinned) * cap
        weights = {t: cap for t in pinned}
        for t in free:
            weights[t] = (
                raw[t] / free_raw_total * remaining if free_raw_total > 0 else 0.0
            )
        newly = [t for t in free if weights[t] > cap + 1e-12]
        if not newly:
            break
        pinned.update(newly)

    s = sum(weights.values())
    return {t: v / s for t, v in weights.items()} if s > 0 else {}


def trailing_return_sigma(
    closes: Sequence[float | None], window: int = SIGMA_WINDOW_DAYS
) -> float | None:
    """Sample stdev of the trailing ``window`` daily simple returns.

    Reads a close series (ascending by date, the ``benchmarks.json`` / stock-
    history convention), drops null / non-positive prices, takes the last
    ``window + 1`` closes, and returns the sample stdev (ddof=1) of the simple
    returns. ``None`` when fewer than 2 returns survive (can't estimate vol).
    """
    vals = [
        float(c)
        for c in closes
        if c is not None and math.isfinite(float(c)) and float(c) > 0
    ]
    if len(vals) < 3:
        return None
    tail = vals[-(window + 1):]
    rets = [(tail[i] / tail[i - 1]) - 1.0 for i in range(1, len(tail))]
    if len(rets) < 2:
        return None
    return statistics.stdev(rets)
