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
    ``StockSummary`` / rankings.json, so the pick uses ONLY ranking+detail data.

    ``recommendation`` / ``mos_pct`` / ``loss_chance_pct`` (added Phase 7 PR-1)
    feed the high-conviction gate (``is_high_conviction``). They are OPTIONAL and
    default ``None`` so existing callers (and the veto-only ``select_picks``) are
    untouched — PR-1 only OBSERVES the gate (counts eligible names per rebalance);
    PR-2 wires it into selection once the per-rebalance count clears DEFAULT_COUNT."""

    ticker: str
    composite_score: float
    sector: str
    risk_flags: tuple[str, ...] = field(default_factory=tuple)
    composite_score_adjusted: float | None = None
    recommendation: str | None = None  # "bullish"/"lean_bullish"/"neutral"/"cautious"
    mos_pct: float | None = None  # margin of safety % (>0 = trading below fair value)
    loss_chance_pct: float | None = None  # heuristic loss-chance % in [5, 95]


# High-conviction selection gate (methodology-scientist RATIFY-WITH-CONDITION
# 2026-06-08). A candidate is high-conviction iff it clears the existing 7-veto
# gate AND is Strong-Buy/Buy-rated AND trades below fair value (MoS > 0) AND
# meets the composite floor AND its loss-chance is below the ceiling. Thresholds
# reuse the production recommendation rubric (ratified 2026-05-14) where possible:
#   - recommendation set = {bullish, lean_bullish} (= the UI's Strong Buy / Buy)
#   - MoS > 0: strict undervaluation (Graham-Dodd margin of safety; ~top 30% of
#     the S&P 500 — p50 MoS ≈ −25%, p75 ≈ +12.5%). Stricter than the rubric's
#     −10% bullish floor by design — it is the price-discipline overlay.
#   - composite ≥ 50 (= recommendation.LEAN_BULLISH_COMPOSITE_MIN; redundant with
#     the recommendation gate but kept explicit per the user's score requirement)
#   - loss-chance ≤ 45 (below the universe median ≈ 49 — "better-than-average
#     odds"; the one genuinely new threshold, additive via its MoS+flag inputs,
#     gut-feel pending the Mode B post-cron binding check, methodology C4)
# None-handling is FAIL-CLOSED: a missing recommendation / MoS / loss-chance can
# never be "high conviction" (the conservative direction for a concentrated book).
HIGH_CONVICTION_RECOMMENDATIONS: frozenset[str] = frozenset({"bullish", "lean_bullish"})
HIGH_CONVICTION_COMPOSITE_MIN: float = 50.0
HIGH_CONVICTION_LOSS_CHANCE_MAX: float = 45.0


def is_eligible(risk_flags: Iterable[str] | None) -> bool:
    """True when the stock carries NO active rank-gate veto (annotate flags OK)."""
    return not (ACTIVE_VETO_FLAGS & set(risk_flags or ()))


def is_high_conviction(c: PickCandidate) -> bool:
    """True when ``c`` clears the full high-conviction gate (Strong Buy/Buy +
    MoS > 0 + composite ≥ 50 + loss-chance ≤ 45 + no active veto).

    PR-1 uses this ONLY to COUNT eligible names per rebalance (observability-
    before-wiring) — ``select_picks`` still gates on ``is_eligible`` alone until
    PR-2. Fail-closed on any missing input (methodology-scientist 2026-06-08)."""
    if not is_eligible(c.risk_flags):
        return False
    if c.recommendation not in HIGH_CONVICTION_RECOMMENDATIONS:
        return False
    if c.mos_pct is None or c.mos_pct <= 0.0:
        return False
    if c.composite_score < HIGH_CONVICTION_COMPOSITE_MIN:
        return False
    if c.loss_chance_pct is None or c.loss_chance_pct > HIGH_CONVICTION_LOSS_CHANCE_MAX:
        return False
    return True


# Dual-class share pairs where BOTH tickers sit in the S&P 500 — the SAME issuer
# listed twice. The AI pick must hold a company ONCE, never burn two basket slots
# on one issuer: the A/C classes share fundamentals → near-identical composites →
# both would otherwise rank adjacent and BOTH get picked (the GOOG+GOOGL bug).
# Each ticker maps to one canonical issuer key; select_picks keeps one slot per
# key, EMITS the canonical class (the map value), and skips its sibling — so the
# basket shows the same ticker every rebalance (no GOOG<->GOOGL cross-quarter
# churn from the two near-equal composites flipping rank). Verified against the live
# universe 2026-06-08 (only these 3 pairs have both classes in the index — BF/UA/
# LEN have just one). Extend if a new both-classes-in-index pair appears.
_DUAL_CLASS_GROUP: dict[str, str] = {
    "GOOG": "GOOGL", "GOOGL": "GOOGL",  # Alphabet (Class C / Class A)
    "FOX": "FOXA", "FOXA": "FOXA",       # Fox Corp (Class B / Class A)
    "NWS": "NWSA", "NWSA": "NWSA",       # News Corp (Class B / Class A)
}


def _company_key(ticker: str) -> str:
    """Collapse dual-class tickers to one issuer key; others map to themselves."""
    return _DUAL_CLASS_GROUP.get(ticker, ticker)


def select_picks(
    candidates: Sequence[PickCandidate],
    count: int | None,
    *,
    gate: str = "veto_only",
) -> list[str]:
    """Return the ordered AI-picked tickers (deterministic + fair).

    ``count`` controls how many tickers to return:

    * ``int`` — take at most this many, clamped to ``[MIN_PICKS, MAX_PICKS]``
      (legacy behaviour; the by_count 1-20 ladder and the per-rebalance ``picks``
      prefix both use this path).
    * ``None`` — return ALL eligible deduplicated tickers in composite-desc order,
      skipping the ``[MIN_PICKS, MAX_PICKS]`` clamp entirely.  This is the
      *uncapped domain* needed by the adaptive/band uncap (2026-06-11 user
      decision: the band book may hold ALL names scoring >= 65 without a hard
      ceiling — cap removed per the 2026-06-11 uncap ratification; in-sample max
      raw 13 / max book 15 over 40 rebalances; A2 spike tripwire re-pointed to
      full pool with raw >= 25 single-rebalance -> reopen, registered #130).
      The caller is responsible for slicing when a bounded prefix is needed
      (e.g. ``full_order = select_picks(candidates, count=None, gate=gate);
      picks = full_order[:MAX_PICKS]``).

    ``gate`` selects the eligibility filter: ``"veto_only"`` (default) drops only the
    7 active rank-gate vetoes (``is_eligible``); ``"high_conviction"`` ALSO requires
    Strong Buy/Buy + MoS>0 + composite>=50 + loss-chance<=45 (``is_high_conviction``,
    Phase 7 PR-2 — needs ``recommendation``/``mos_pct``/``loss_chance_pct`` populated;
    the backfill replays them point-in-time). Sell-eviction is implicit: a name that
    decays out of the gate at a rebalance is simply not re-selected (the basket is
    rebuilt from scratch every quarter).

    composite desc -> drop the active rank-gate vetoes -> dedup dual-class issuers
    -> take the top ``count`` (clamped to ``[MIN_PICKS, MAX_PICKS]`` when count is
    an int; uncapped when count is None). NO sector cap (removed 2026-06-06): the
    basket is purely the highest-composite eligible NAMES (one ticker per issuer),
    so it can concentrate in one sector — that concentration is surfaced in the UI +
    disclaimer, never silently constrained.
    Tiebreak: ``composite_score_adjusted`` desc (nets the manipulation index) then
    ``ticker`` asc. Dual-class (GOOG/GOOGL, FOX/FOXA, NWS/NWSA) collapses to ONE
    slot per issuer, CANONICALIZED to a fixed class (the ``_DUAL_CLASS_GROUP``
    value, e.g. GOOGL) so the issuer is represented by the SAME ticker every
    rebalance — the two classes' near-equal composites otherwise flip which ranks
    higher quarter to quarter, churning the basket GOOG<->GOOGL for the SAME
    company (spurious turnover). Falls back to the held class only if the canonical
    class is itself ineligible (e.g. vetoed or out of the high-conviction gate).
    """
    if count is not None:
        count = max(MIN_PICKS, min(MAX_PICKS, count))
    if gate == "high_conviction":
        eligible = [c for c in candidates if is_high_conviction(c)]
    else:
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
    eligible_tickers = {c.ticker for c in eligible}
    out: list[str] = []
    seen_issuers: set[str] = set()
    for c in eligible:
        key = _company_key(c.ticker)
        if key in seen_issuers:  # this issuer already has a slot (sibling class seen)
            continue
        seen_issuers.add(key)
        # Canonical class (stable across quarters) when eligible; else the held one.
        out.append(key if key in eligible_tickers else c.ticker)
        if count is not None and len(out) >= count:
            break
    return out


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


# ── Proposal C-2 — MoS conviction tilt (shadow / observability-first) ────────
# Constants for the MoS-conviction tilt function below.
# ``MOS_TILT_KAPPA`` is a **Tier-2 gut-feel calibration** (disclosed).
# Flip-gate (future PR): re-derive κ from the observed z(mos) distribution
# on real cron data; confirm clip-bind rate ≤ ~5%; verify MAX_WEIGHT holds
# post-renorm on every rebalance leg; OOS turnover check.
MOS_TILT_KAPPA: float = 0.25
MOS_TILT_CLIP_LO: float = 0.5
MOS_TILT_CLIP_HI: float = 1.5


def mos_conviction_tilt(
    base_weights: dict[str, float],
    mos_by_ticker: dict[str, float | None],
    *,
    kappa: float = MOS_TILT_KAPPA,
    cap: float = MAX_WEIGHT,
) -> dict[str, float]:
    """Tilt inverse-vol weights toward higher-MoS holdings (Proposal C-2, SHADOW).

    Computes a MoS-conviction multiplier for each holding in the book, scales
    the base inverse-vol weights by that multiplier, renormalizes to sum 1.0,
    and re-caps at ``cap`` using the SAME iterative pin-and-redistribute
    routine used by ``inverse_vol_weights`` — NOT a naive clip-and-renorm
    (which can re-breach the cap).

    Tilt formula
    ------------
    1. Book-relative z-score: ``z_i = (mos_i − μ) / σ`` where μ and σ are the
       mean and stdev of ``mos_pct`` over the **held book** (only names in
       ``base_weights``), not the full universe.  ``mos_i is None → z_i = 0``
       (neutral — the position receives no tilt, neither up nor down).
    2. Multiplier: ``m_i = clip(1 + κ·z_i, MOS_TILT_CLIP_LO, MOS_TILT_CLIP_HI)``.
    3. Provisional weight: ``w'_i = base_weights[i] · m_i``.
    4. Renormalize: ``w''_i = w'_i / Σ w'``.
    5. Re-cap at ``cap`` using the iterative pin-and-redistribute routine
       (converges in ≤ n passes, same as ``inverse_vol_weights``).

    Methodology citations
    ---------------------
    - Graham-Dodd "Security Analysis" (1934/1940 eds.) margin-of-safety
      doctrine: a stock trading BELOW its intrinsic value provides a safety
      margin that both reduces downside and creates an asymmetric return
      profile.  ``mos_pct > 0`` signals the market price is below the
      ensemble fair-value estimate; tilting toward higher MoS is a
      price-discipline overlay on top of the composite ranking.
    - Stevens 1946 "On the Theory of Scales of Measurement" (*Science* 103):
      ``mos_pct`` is a **ratio-scale** cardinal quantity (% deviation from fair
      value — has a natural zero and meaningful ratios), so z-scoring and linear
      arithmetic on it are admissible.  This is the key distinction from
      ``composite_score`` (an ordinal percentile rank — Stevens ordinal scale,
      cardinal operations on it are a scale-type error per the module-level
      docstring and Rule 16).  The MoS tilt is permitted precisely because
      MoS is ratio-scale; any composite-proportional tilt is still forbidden.

    Identity guards (test-pinnable)
    --------------------------------
    - σ_mos == 0 (all holdings have the same MoS) → all z_i = 0 → all m_i = 1
      → renorm is identity → returns ``base_weights`` unchanged.
    - All mos values are ``None`` → all z_i = 0 → same identity path.
    - Single-name book (n=1) → stdev undefined (ddof=1 requires ≥ 2 points);
      treated as σ=0 → identity.
    - Empty ``base_weights`` → returns ``{}`` immediately.

    SHADOW / observability-first (Rule 18)
    ----------------------------------------
    This function is NEVER called on the live NAV path.  The backfill script
    invokes it AFTER ``band_weights_map = inverse_vol_weights(...)`` and emits
    the tilted weights as ``rebalances[].mos_tilted_weights`` for diagnostics
    only.  ``band_weights_map`` and all NAV math remain byte-identical.
    Defense layer UNCHANGED at 36.  Rankings / scores / flags unaffected.

    Parameters
    ----------
    base_weights:
        Inverse-vol weights from ``inverse_vol_weights`` (sum 1.0, keys = book).
    mos_by_ticker:
        Per-ticker ``mos_pct`` (% margin of safety; positive = undervalued).
        Keys need not cover the full book — missing keys are treated as ``None``.
    kappa:
        Tilt strength (gut-feel Tier-2, κ=0.25 → a 1σ-high-MoS name gets a
        25% weight boost before renorm; 2σ clips at MOS_TILT_CLIP_HI=1.5×).
    cap:
        Single-name concentration cap (inherits ``MAX_WEIGHT=0.35``).
    """
    if not base_weights:
        return {}

    tickers = list(base_weights.keys())
    n = len(tickers)

    # Collect valid (non-None) MoS values for the book members.
    mos_vals: list[float] = [
        float(mos_by_ticker[t])
        for t in tickers
        if mos_by_ticker.get(t) is not None
    ]

    # Identity guard: σ=0 / all-None / 1-name → no tilt (test-pinnable).
    if len(mos_vals) < 2:
        return dict(base_weights)

    mu = statistics.mean(mos_vals)
    sigma = statistics.stdev(mos_vals)  # sample stdev (ddof=1)

    if sigma == 0.0:
        # All non-None MoS values are equal → z_i = 0 everywhere → identity.
        return dict(base_weights)

    # Compute per-ticker multipliers and provisional weights.
    provisional: dict[str, float] = {}
    for t in tickers:
        mos_val = mos_by_ticker.get(t)
        z = (float(mos_val) - mu) / sigma if mos_val is not None else 0.0
        m = max(MOS_TILT_CLIP_LO, min(MOS_TILT_CLIP_HI, 1.0 + kappa * z))
        provisional[t] = base_weights[t] * m

    # Renormalize provisional weights to sum 1.0.
    total = sum(provisional.values())
    if total <= 0.0:
        return dict(base_weights)  # degenerate (shouldn't happen; guard)
    renormed = {t: v / total for t, v in provisional.items()}

    # Re-cap at ``cap`` using the iterative pin-and-redistribute routine
    # (reuses the SAME logic as ``inverse_vol_weights`` :277-290).
    # Pinned names stay at ``cap``; residual redistributes pro-rata over
    # the free names until none exceeds the cap.  Converges in ≤ n passes.
    if n * cap < 1.0 - 1e-12:
        # Cap infeasible (shouldn't happen for a valid portfolio) → equal wt.
        return {t: 1.0 / n for t in tickers}

    pinned: set[str] = set()
    weights: dict[str, float] = {}
    raw_renormed = renormed  # use renormed values as the "raw" input
    for _ in range(n + 1):
        free = [t for t in tickers if t not in pinned]
        free_raw_total = sum(raw_renormed[t] for t in free)
        remaining = 1.0 - len(pinned) * cap
        weights = {t: cap for t in pinned}
        for t in free:
            weights[t] = (
                raw_renormed[t] / free_raw_total * remaining
                if free_raw_total > 0
                else 0.0
            )
        newly = [t for t in free if weights[t] > cap + 1e-12]
        if not newly:
            break
        pinned.update(newly)

    s = sum(weights.values())
    return {t: v / s for t, v in weights.items()} if s > 0 else dict(base_weights)


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
