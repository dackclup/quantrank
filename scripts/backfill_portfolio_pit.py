"""Phase 7.0 PR-2c — point-in-time portfolio backtest backfill with veto-layer replay.

Reconstructs the AI-pick rule's HISTORICAL performance honestly. At each
quarterly rebalance date ``T`` over the backtest window it:

  1. survivorship-corrects the universe via ``members_at(T)``;
  2. rebuilds each name's fundamentals **point-in-time** — annual 10-K facts with
     ``filing_date <= T`` only (``pit_fundamentals``), the two methodology-
     mandated guardrails being (a) the *history* frame fed to the growth/quality
     pillars is filed<=T, and (b) ``current_price`` is the price ON T;
  3. re-scores the existing 8-pillar composite (frozen ``PHASE3_EFFECTIVE_WEIGHTS``);
  4. replays the 6 accounting-based active vetoes **point-in-time** against the PIT
     cross-section at T (Phase 7.0c). ``non_reliance_filing`` is EXCLUDED from the
     replay (no 8-K Item-4.02 history in the loaded PIT data — see
     ``meta.vetoes_not_replayed``); replayed veto state drives ``select_picks`` as in
     the live rule, and vetoed candidates are recorded in
     ``rebalances[i].vetoed_pick_candidates``;
  5. picks + weights via ``compute.portfolio.weights`` (composite rank,
     inverse-volatility weights, NO sector cap);
  6. builds a daily gross + net NAV (``compute.portfolio.backtest``) vs the
     benchmark index series.
  7. exports per-rebalance supplementary fields: ``full_ranked`` (top-40 by
     composite), ``mos_pct`` on each holding, ``sector_weights_by_count``,
     ``high_conviction_count``.

Methodology (ratified 2026-06-04, Option A): this is a **point-in-time PROXY**
of the forward rule — fundamental pillars use ANNUAL (not the live TTM) basis,
GICS sectors are assumed stable from today, and survivorship is corrected via
the membership ledger. See ``meta.disclaimer`` in the output.

**Veto replay scope (Phase 7.0c):**
  * Six of the seven active vetoes are replayed PIT:
      - ``data_quality_input_corruption`` — snapshot-only (TBVPS / revenue patterns)
      - ``altman_distress`` — Altman Z″ from PIT balance-sheet snapshot
      - ``sloan_accruals_top_decile`` — (NI−CFO)/TA, cross-section at T
      - ``net_issuance_top_decile`` — ln(shares_t/shares_{t-12m}), within-sector at T
      - ``beneish_manipulation_veto`` — 8-ratio M-score from PIT snapshot + history
      - ``dechow_manipulation_veto`` — F-score from PIT snapshot + history
  * ``non_reliance_filing`` is NOT replayed: the 8-K Item-4.02 filing history is
    not present in the pre-loaded PIT data and fetching it per-name per-rebalance
    would add EDGAR network calls not budgeted for the backfill step. Disclosed via
    ``meta.vetoes_not_replayed``.
  * When all six accounting vetoes replay cleanly, ``meta.veto_layer_replayed`` is
    ``true`` (the primary Phase 5 entry-gate metric). ``non_reliance_filing``
    appearing in ``meta.vetoes_not_replayed`` is expected and does NOT suppress the
    flag.

**Run** (CI ``workflow_dispatch`` — needs warm price + fundamentals_history
caches; the dev sandbox has neither, so this script is CI-validated, not
locally-run): ``python -m scripts.backfill_portfolio_pit [--start YYYY-MM-DD]``.
"""

from __future__ import annotations

import argparse
import bisect
import dataclasses
import logging
import statistics
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from compute import config
from compute.ingest.fundamentals import FundamentalsSnapshot, fetch_fundamentals_history
from compute.ingest.historical_8k import item402_filings_for, item402_parquet_row_count
from compute.ingest.historical_sector import historical_sector_parquet_stats, sector_at
from compute.ingest.historical_universe import _ACTION_REMOVE, list_known_events, members_at
from compute.ingest.prices import fetch_prices
from compute.ingest.universe import get_sp500_constituents
from compute.main import (  # noqa: E402 — live cross-section builders reused; see PR-1 note
    _build_historical_metrics,
    _build_peer_groupings,
    _build_universe_metrics,
)
from compute.output.writer import write_backtest_pit_json
from compute.portfolio.backtest import (
    DEFAULT_COST_BPS_PER_SIDE,
    align_benchmark_nav,
    build_portfolio_nav,
    quarterly_rebalance_dates,
)
from compute.portfolio.pit_fundamentals import pit_history_rows, pit_snapshot_fields
from compute.portfolio.weights import (
    HIGH_CONVICTION_COMPOSITE_MIN,
    HIGH_CONVICTION_LOSS_CHANCE_MAX,
    HIGH_CONVICTION_RECOMMENDATIONS,
    MAX_PICKS,
    PickCandidate,
    inverse_vol_weights,
    is_high_conviction,
    select_picks,
    trailing_return_sigma,
)
from compute.scoring.beneish import compute_beneish
from compute.scoring.composite import compute_composite, neutralize_pillar_scores
from compute.scoring.dechow_f import compute_dechow_f
from compute.scoring.eight_k_events import check_non_reliance
from compute.scoring.loss_chance import derive_loss_chance
from compute.scoring.pillars import TickerInputs, compute_all_pillars
from compute.scoring.recommendation import derive_recommendation
from compute.scoring.restatement_filings import fetch_amendments
from compute.scoring.risk_overlay import compute_risk_flags
from compute.validation.basket_rule_validation import (
    BASKET_RULE_N_TRIALS,
    compute_basket_rule_validation,
    compute_grid_pbo,
    compute_holdout,
)
from compute.valuation.ensemble import compute_fair_price_ensemble

logger = logging.getLogger(__name__)

# Canonical backtest start — FIXED, never run-date-relative.
#
# Anchored to the survivorship membership ledger's Track-B coverage start
# (data/sp500_membership_historical.csv Track B begins 2016-01-04) plus a
# ~5-month buffer so the sigma lookback for the FIRST rebalance (2016-08-14)
# has a full 90-trading-day window of price history before it.
#
# WHY FIXED: the previous default was ``today - 10y`` (rolling).  With a rolling
# start the cron artifact's window slides forward one day per run, so around
# Aug 2026 the canonical first rebalance (2016-08-14) silently drops off the
# left edge and all rebalance NAVs, IC stats, and band-tenure counts quietly
# shift.  A fixed constant eliminates that drift entirely.
#
# Changing this value requires:
#   1. A ledger-coverage check (``scripts/verify_membership_ledger.py``) to
#      confirm Track-B data exists for the new start date.
#   2. Methodology-scientist sign-off (any change to the window extent affects
#      the in-sample record used for the adaptive-rule pre-registration).
BACKTEST_CANONICAL_START: date = date(2016, 6, 1)

# Sigma lookback buffer used when fetching prices for the backfill.
# 90 trading days ≈ 130 calendar days; 185 adds a further margin so the
# first rebalance's trailing-sigma window is fully populated even after
# non-trading gaps (holidays, early-history sparse data).
#
# Consistency with compute.config.PRICES_FETCH_START: the fixed price floor
# used by the live compute's fetch_prices is defined as
#   BACKTEST_CANONICAL_START - timedelta(days=_SIGMA_LOOKBACK_BUFFER_DAYS)
#   = date(2016, 6, 1) - timedelta(days=185)
#   = date(2015, 11, 29)
# which equals compute.config.PRICES_FETCH_START exactly.  The backfill's
# _price_floor (start - 185d) == PRICES_FETCH_START when start ==
# BACKTEST_CANONICAL_START — so on a warm cache from the live cron, the
# backfill's depth-check (fetch_prices min_start=_price_floor) is a no-op
# because the cache already satisfies the floor.  Do NOT import compute.config
# here to verify this at runtime — scripts may import compute, never the
# reverse (layering invariant).  The equality is maintained by construction
# and guarded by the A5 pin in tests/test_ingest/test_prices_min_start.py.
_SIGMA_LOOKBACK_BUFFER_DAYS: int = 185

# The slider's default landing position. The artifact carries a NAV per holding
# count N=1..MAX_PICKS (the 1-20 slider re-runs the backtest line), so this is the
# count shown before the user touches the slider — not a cap.
DEFAULT_COUNT = 5
CONSERVATIVE_COST_BPS = 25.0  # the "show the cost band" second net line
BENCHMARKS_JSON = "portfolio/benchmarks.json"

# Adaptive-book rule: the AI sizes its own basket each rebalance by holding EVERY
# high-conviction pick whose composite_score >= ADAPTIVE_COMPOSITE_MIN, subject to
# a floor of ADAPTIVE_MIN_PICKS. NO ceiling (uncap ratified 2026-06-11 — see below).
# Provenance: EMPIRICAL-IN-SAMPLE (grid-swept {55,60,65,70} x {1,3,5} floors, 40
# rebalances 2016-08..2026-05 on the veto-replayed artifact; NOT literature-anchored,
# NOT a canonical TIERS boundary). Structural corroboration: monotone dose-response
# 55->60->65 in the full window AND both halves (Patton-Timmermann 2010 MR-test
# logic); the >=70 cliff has a known mechanism (0-8-name concentration books) and
# floor 5 de-fangs it (Evans-Archer 1968 / Elton-Gruber 1977 — the 1->5 leg removes
# ~80% of idiosyncratic variance); the rule's mean count (8.0) lands on the
# independent fixed-N sweet spot (N=8-14). Expect roughly HALF the in-sample edge
# forward (McLean-Pontiff 2016 decay + in-sample-selection haircut).
# Uncap record (user decision 2026-06-11): the MAX_PICKS ceiling is REMOVED from
# the band/adaptive domain. U1 regen-diff finding (uncapped `3dbe4798` vs capped
# `4bfcdb32`): the cap was inert as a COUNT clamp on the FRESH leg (max raw 13)
# but BOUND as a rank-slice membership test on the CARRY leg — 12/40 rebalances
# differ (a tenured [55,65) name competes for top-20 against the whole HC pool;
# first instance BF-B 2016-11-14). Max book is domain-specific: 15 capped /
# 16 uncapped. No replacement ceiling. A2 gate re-pointed to the full
# deduped pool (was: raw count from select_picks[:MAX_PICKS] prefix; now: full
# full_order pool, more responsive to a genuine inflation signal). NEW A2-S spike
# tripwire: raw >= 25 in a SINGLE rebalance -> reopen immediately (vs the original
# A2 >= 18 in 2 consecutive rebalances, which remains). Both registered on issue #130.
# Forward acceptance gates (pre-registered; evaluated at quarterly cohort audits):
#   A1 score-drought: raw pre-floor count < 5 in >= 3 of any 4 consecutive
#      rebalances -> reopen threshold (candidate 60).
#   A2 inflation: raw count >= 18 in 2 consecutive rebalances -> reopen.
#   A2-S spike: raw count >= 25 in ANY single rebalance -> reopen immediately.
#   B  relative gate @ 8th live rebalance: adaptive net NAV trails BOTH
#      by_count[8] AND SPY -> reopen (fallback = quasi-fixed-N=8, NOT a higher floor).
#   C  freeze lock: no grid re-sweeps on refreshed artifacts until A/A2-S or B fires.
# methodology-scientist RATIFY 2026-06-11 (conditions C1 provenance comment = this
# block; C2 test pin in tests/test_portfolio; C3 gate registration on issue #130).
# RATIFY-AMENDED-WITH-CONDITIONS (uncap, Mode B re-entry) 2026-06-11: the U1
# regen diff was NON-EMPTY (carry-leg domain widening, 12/40 rebalances) — the
# change is recorded as a POST-RESULTS PROTOCOL AMENDMENT V55.0 -> V55.1, not a
# defect-erasure. U11 re-verification vs the no-band counterfactual (uncapped
# domain): turnover -35.8% / CAGR +0.33pp / beats +4 — all three V55 criteria
# pass a fortiori. U10 reads: H2 zero consecutive >0.50 pairs under BOTH domains;
# H3 trailing-4 mean book exceeds the >14 wire IN-SAMPLE under BOTH domains
# (capped 14.25 max, 4 windows 2018; uncapped 14.75 max, 5 windows 2017-11..2018)
# — pre-existing finding, recorded NOT recalibrated (H-C lock), Q3 2026-08-19
# cohort-audit agenda. Capped-vs-uncapped scoreboard (U1 outcome, claim-
# quarantined per U8 — never marketed): CAGR 22.4 -> 23.0 / turnover 2.324 ->
# 2.251 / beats 30/40 both / maxDD -31.4% both. A2 re-pointed to full pool +
# A2-S spike tripwire raw >= 25 -> reopen; +1 multiplicity charged (U9);
# reopen criteria U13 registered on #130.
ADAPTIVE_COMPOSITE_MIN: float = 65.0
ADAPTIVE_MIN_PICKS: int = 5

# Hysteresis hold-band (V55.1 carry domain, amended 2026-06-11): an incumbent that
# entered via >= ADAPTIVE_COMPOSITE_MIN stays in the book while composite >=
# ADAPTIVE_HOLD_BAND_MIN AND it remains HC-eligible (un-vetoed, in the FULL deduped
# HC pool). Retention is INDEPENDENT of rank vs MAX_PICKS or any other name's
# score (the V55.0 top-20-slice exit was an undesigned interaction with the
# display-ladder constant; see the amendment record below). Force-sell on
# HC-ineligibility OR composite < ADAPTIVE_HOLD_BAND_MIN.
# C0 strict tenure: band rights accrue ONLY to names that entered via
# >= ADAPTIVE_COMPOSITE_MIN. Floor-pads (names added to reach ADAPTIVE_MIN_PICKS)
# get NO tenure. Re-entry after a force-sell requires >= ADAPTIVE_COMPOSITE_MIN again.
# Tier: EMPIRICAL-IN-SAMPLE, THEORY-ANCHORED.
#   Theory: Constantinides 1986 JPE (no-trade region with transaction costs) ·
#   Davis-Norman 1990 (viscosity solution to the no-trade band) ·
#   Garleanu-Pedersen 2013 JF (partial-adjustment / hold-band dynamics) ·
#   Novy-Marx-Velikov 2016 RFS (buy/hold spread implementation cost) ·
#   FTSE Russell reconstitution banding (1% AUM buffer — structural precedent).
# Pre-registration record (issue #130):
#   Grid exhausted: {60, 55}; criteria C1 turnover -30%, C2 CAGR >= -0.5pp,
#   C3 beats >= -2q; denominator = 40 legs incl. final partial.
#   V60 FAIL recorded: turnover -27.7% / CAGR -0.8pp (fails C2).
#   V55 PASS: turnover -33.8% / CAGR -0.27pp / beats +3 / maxDD -31.4% vs -32.0%.
#   Strict-C0 re-run: identical to V55; per-half: growth x2.89->x3.35 / x2.57->x2.17,
#   beats 15/20->17/20 / 11/20->12/20.
#   AMENDMENT V55.0 -> V55.1 (2026-06-11, post-results): the row above was measured
#   under the V55.0 SLICE carry domain (incumbent also had to hold a top-20 rank).
#   The carry domain was amended rank-free after the U1 regen diff exposed the
#   slice as an undesigned exit channel (12/40 rebalances). V55.1 re-verification
#   (U11): turnover -35.8% / CAGR +0.33pp / beats +4 vs the same no-band
#   counterfactual — criteria pass under both protocols; both rows retained.
# CLAIM DISCIPLINE: the band is a TURNOVER / implementation-cost device only — never
# market the beat/maxDD deltas as band benefits (within-noise). The capped-vs-
# uncapped deltas (+0.6pp CAGR / -3.1% turnover) are equally quarantined: recorded
# as the U1 outcome, never marketed (U8).
# Forward acceptance gates (pre-registered; evaluated at quarterly cohort audits):
#   H1 realized turnover reduction >= 15% vs no-band counterfactual @ >= 4 live
#      rebalances.
#   H2 carry-cohort health: carry weight-share > 50% for 2 consecutive rebalances
#      OR carry lags fresh cohort > 5pp/q avg over 4 OR any carried name -30% in a
#      quarter while in the 55-64 corridor -> reopen.
#   H3 trailing-4 mean book > 14 -> reopen.
#   H-B @ 8th live banded rebalance: trails BOTH no-band counterfactual AND SPY ->
#      revert to un-banded (single-constant flip).
#   H-C freeze lock on 55: no re-sweeps; no second hysteresis DOF without fresh
#      pre-registration.
# methodology-scientist RATIFY-WITH-CONDITIONS 2026-06-11 (C0 strict tenure
# verified; C1 = this block; C2 pins in tests/test_portfolio; C3 artifact contract
# in the per-rebalance band_* exports + meta.adaptive_rule.hold_band_min).
ADAPTIVE_HOLD_BAND_MIN: float = 55.0

# Phase 7.0c: +veto-replay suffix marks artifacts where veto_layer_replayed=True.
# Prior artifacts (veto_layer_replayed=False) carry the plain "phase3-effective-weights"
# version so callers can distinguish the two datasets unambiguously.
RULE_VERSION = "phase3-effective-weights+veto-replay+hold-band-55+uncapped"

# 12-config grid for the score-once-apply-many validation.
#
# Design (ratified): at each rebalance T the composite cross-section is computed ONCE
# (config-independent). The 12 configs ONLY differ in how ``_band_book`` selects from
# that cross-section (composite_min threshold + min_picks floor). Threading separate
# tenure sets per config prevents the FOOTGUN of leaking carry-state across configs:
# a name tenured under cmin=55 MUST NOT pollute cmin=70's tenure (they are independent
# hysteresis rules with different entry thresholds). Each config key is ``f"{cmin}_{floor}"``.
_GRID_CONFIGS: list[tuple[int, int]] = [
    (cmin, floor) for cmin in (55, 60, 65, 70) for floor in (1, 3, 5)
]
_GRID_CONFIG_KEYS: list[str] = [f"{cmin}_{floor}" for cmin, floor in _GRID_CONFIGS]

# methodology-scientist RATIFY 2026-06-08 (Option B, condition C2): the backtest has
# ANNUAL 10-K data only, so the live 180d hard-stale gate (config.FILING_STALE_HARD_DAYS)
# would null the fair-price ensemble ~3 of 4 quarters. Relax the hard-stale ceiling to
# 455d FOR THE BACKTEST PIT PATH ONLY (= the SEC 75-day large-accelerated 10-K filing
# deadline + 365 + a 15d buffer = the worst-case LEGITIMATE 10-K-to-next-10-K gap; a
# genuinely skipped annual cycle is older than this and still nulls). Threaded via
# compute_fair_price_ensemble(hard_stale_days=...) — the live path NEVER sets it (keeps
# config's 180d). Provenance: GUT-FEEL-WITH-SEC-DEADLINE-RATIONALE.
BACKTEST_HARD_STALE_DAYS = 455

# The six accounting vetoes replayed point-in-time (Phase 7.0c). All derive from the
# already-loaded PIT snapshot + PIT history — no additional EDGAR fetching required.
_VETOES_REPLAYED: tuple[str, ...] = (
    "data_quality_input_corruption",
    "altman_distress",
    "sloan_accruals_top_decile",
    "net_issuance_top_decile",
    "beneish_manipulation_veto",
    "dechow_manipulation_veto",
)

# non_reliance_filing is excluded from replay: it requires 8-K Item-4.02 filing
# history from EDGAR that is NOT part of the pre-loaded PIT fundamentals data.
# Fetching it per-name per-rebalance would add O(N_picked × N_rebalances) EDGAR
# calls beyond the restatement-canary amendment fetch that already runs per-picked-
# name. The flag is a real-time check (trailing 365d), and its historical filings
# index is not available in the warm fundamentals/price caches that the backfill
# relies on. This exclusion is honest: the live rule does enforce it; the backtest
# is a proxy that cannot fully replay it point-in-time.
_VETOES_NOT_REPLAYED: tuple[dict[str, str], ...] = (
    {"name": "non_reliance_filing", "reason": "no_8k_history_in_pit_data"},
)

# Maximum number of top-composite names exported per rebalance as full_ranked.
# 40 dicts × ~5 fields × ~15 bytes/field (JSON keys + values) ≈ 3-4 KB per rebalance;
# 40 rebalances ≈ 120-160 KB — still well under ~2 MB total (negligible vs the NAV series).
_FULL_RANKED_LIMIT = 40

# Method caveats only. The result-dependent in-sample lead/lag sentence (vs SPY) is
# computed from the ACTUAL NAV and appended in run_backfill so the disclaimer can never
# contradict the line shown (methodology-scientist: the old "upper bound" tail implied a
# win and misframed a losing default).
DISCLAIMER_BASE = (
    "Illustrative backtest, not investment advice. This is a point-in-time PROXY "
    "of QuantRank's ranking rule, not a replay of the live composite: at each "
    "historical rebalance it re-runs the current frozen 8-pillar weights using only "
    "data filed on or before that date, but fundamental pillars use ANNUAL (10-K) "
    "figures in place of the live trailing-twelve-month basis, GICS sectors are "
    "assumed stable from today, and survivorship is corrected via the point-in-time "
    "membership ledger. The basket holds ONLY high-conviction names — Strong Buy / "
    "Buy rated, undervalued (margin of safety > 0), composite >= 50 and loss-chance "
    "<= 45 — taking the top names by composite among those (a name that decays out "
    "of the gate is dropped at the next rebalance). The recommendation + 6-method "
    "valuation layer is replayed point-in-time, with the fair-value staleness gate "
    "widened to ~15 months for the once-a-year 10-K cadence (vs the live 180-day "
    "gate). Six of the seven active accounting vetoes (Altman distress, Sloan "
    "accruals, net issuance, Beneish manipulation, Dechow F-score, and data-quality "
    "corruption) are replayed point-in-time against the PIT cross-section; "
    "non_reliance_filing (8-K Item 4.02) coverage is stated in "
    "meta.vetoes_replayed / meta.vetoes_not_replayed. "
    "Net figures charge a modeled per-side spread cost (10-25 bps on turnover) but "
    "are gross of additional market-impact slippage. "
    "The adaptive AI-pick book sizes itself each rebalance: it holds ALL "
    "high-conviction picks with composite score >= 65 (no ceiling), with a floor of "
    "5 names, so holding count varies by quarter (uncap ratified 2026-06-11 — "
    "in-sample max book 16 over 40 rebalances; the former cap never bound fresh "
    "entries (max raw 13) and its carry-leg rank-slice exit was removed as the "
    "V55.0 -> V55.1 protocol amendment; A2-S spike tripwire: raw >= 25 in a single "
    "rebalance triggers reopening, registered #130; forward acceptance gates "
    "pre-registered). Incumbents are retained while scoring "
    ">= 55 to reduce turnover (V55 hysteresis band ratified 2026-06-11; the band is "
    "a turnover/implementation-cost device — no performance claims). "
    "SELECTION FOOTPRINT: the adaptive rule's thresholds (composite_min=65 / "
    "hold_band=55 / floor 5 / uncapped) were grid-swept IN-SAMPLE on the same 40-leg "
    "window shown as the track record; the adaptive book's lead over the best fixed-N "
    "basket is approximately +127.7pp (~16% of total return) and is a tuning artifact "
    "until confirmed on a fresh out-of-sample window. "
    "McLean-Pontiff (2016) is cited for decay of PUBLISHED factors; this rule was "
    "never published, so the relevant haircut is the out-of-sample decay term plus the "
    "in-sample-selection penalty above, not the ~32% post-publication figure. "
    "The Deflated Sharpe Ratio (n_trials=15, quarterly) is the primary inferential "
    "gate; the DSR result is stored in meta.validation on the next artifact rerun."
)

_SNAPSHOT_FIELDS = {f.name for f in dataclasses.fields(FundamentalsSnapshot)}


def _annual_rows(history: pd.DataFrame | None) -> list[dict]:
    """Cached annual-history DataFrame -> plain rows for the pure PIT selectors.

    ISO-stringifies the date columns so the (pandas-free) ``pit_fundamentals``
    helpers can compare ``filing_date <= T`` lexically.
    """
    if history is None or len(history) == 0:
        return []
    rows: list[dict] = []
    for r in history.itertuples(index=False):
        fd = getattr(r, "filing_date", None)
        rows.append(
            {
                "metric": getattr(r, "metric", None),
                "fiscal_year": getattr(r, "fiscal_year", None),
                "value": getattr(r, "value", None),
                "filing_date": fd.isoformat() if hasattr(fd, "isoformat") else fd,
                "form_type": getattr(r, "form_type", None),
            }
        )
    return rows


def _pit_snapshot(ticker: str, cik: str, rows: list[dict], as_of: str) -> FundamentalsSnapshot:
    fields = {k: v for k, v in pit_snapshot_fields(rows, as_of).items() if k in _SNAPSHOT_FIELDS}
    return FundamentalsSnapshot(ticker=ticker, cik=cik, **fields)


def _pit_filing_lag(rows: list[dict], as_of: str, as_of_date: date) -> int | None:
    """Days from the latest 10-K filed on/before ``as_of`` (annual PIT staleness).

    The PIT snapshot (``pit_snapshot_fields``) returns only metric values, not the
    filing date, so Defense #3's lag is computed here from the SAME eligible rows
    (``form_type == "10-K"`` AND ``filing_date <= as_of``). ``None`` when no 10-K is
    public at ``as_of`` — the ensemble then reads freshness as "unknown" (NOT
    hard-stale), which is the existing behavior for a name with no filing date."""
    fds = [
        r["filing_date"]
        for r in rows
        if r.get("form_type") == "10-K"
        and isinstance(r.get("filing_date"), str)
        and r["filing_date"] <= as_of
    ]
    if not fds:
        return None
    return (as_of_date - date.fromisoformat(max(fds))).days


def _price_at(prices: pd.DataFrame, as_of_ts: pd.Timestamp) -> float | None:
    """GUARDRAIL 2 — the close on the latest trading day on or before ``as_of``."""
    if prices is None or len(prices) == 0:
        return None
    col = "Adj Close" if "Adj Close" in prices.columns else "Close"
    sliced = prices.loc[:as_of_ts, col]
    if len(sliced) == 0:
        return None
    val = sliced.iloc[-1]
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return f if f == f and f > 0 else None


def _pit_fiscal_year_at(rows: list[dict], as_of: str) -> int | None:
    """Fiscal year of the most-recent 10-K filed on or before ``as_of``.

    Returns the ``fiscal_year`` integer from the highest-FY eligible 10-K row
    (same eligibility as ``pit_snapshot_fields``), or ``None`` when no 10-K is
    public at ``as_of``. Used by ``_restatement_at_risk`` to narrow the
    amendment fiscal-year gate (FIX 1 — restatement period-map refinement).
    """
    best_fy: int | None = None
    best_fd: str = ""
    for row in rows:
        if row.get("form_type") != "10-K":
            continue
        fd = row.get("filing_date")
        if not isinstance(fd, str) or fd > as_of:
            continue
        try:
            fy = int(row["fiscal_year"])  # type: ignore[arg-type]
        except (KeyError, TypeError, ValueError):
            continue
        if best_fy is None or (fy, fd) > (best_fy, best_fd):
            best_fy = fy
            best_fd = fd
    return best_fy


def _restatement_at_risk(
    amendments: list[dict] | None,
    as_of: str,
    *,
    pit_fiscal_year: int | None = None,
) -> bool:
    """True if the name filed a relevant 10-K/A or 10-Q/A AFTER ``as_of``.

    Re-sourced (methodology-scientist 2026-06-05) from the SAME EDGAR filings-index
    feed the live ``restatement_history`` flag uses (``fetch_amendments`` →
    ``company.get_filings``), NOT the companyfacts-XBRL annual-fact scan it used
    before — that scan only saw amendments that re-filed a pulled annual XBRL concept,
    so it systematically under-counted partial / non-financial amendments and reported
    a misleading 0.0%. This is a CONSERVATIVE look-ahead-contamination canary: a
    post-as-of amendment means the cached companyfacts data the backtest read at T may
    silently reflect that later restatement.

    **Period-map refinement (FIX 1 — 2026-06-13):** When ``pit_fiscal_year`` is
    supplied (the fiscal year of the 10-K that actually fed the PIT score at T),
    only amendments whose ``filing_date <= {pit_fiscal_year + 2}-12-31`` are counted.
    The rationale: a 10-K/A or 10-Q/A that amends fiscal year FY is nearly always
    filed within 2 calendar years of FY-end (i.e. before Dec 31 of FY+2); an
    amendment filed well beyond that window almost certainly targets a later fiscal
    year that did NOT feed the PIT score. The 2-year ceiling is conservative (most
    amendments land within 12-18 months) and eliminates the dominant over-count case
    (amendments filed 5-10 years after the PIT fiscal year). Residual imprecision:
    (a) for non-Dec-31 fiscal-year-ends the ceiling is an approximation (the actual
    FYE is not stored in the filings-index cache); (b) multi-year restatements filed
    beyond 2 years are missed. Both effects are documented; the disclosure is "upper
    bound on contamination for the PIT 10-K's fiscal year ± 2 calendar years".

    When ``pit_fiscal_year`` is None (no eligible 10-K found at T), the function
    falls back to the original conservative behaviour (any post-as-of amendment
    counts) so the signal does not silently disappear for tickers with sparse data.

    ``None`` (fetch failed / no EDGAR identity) is treated as "unresolved", NOT
    at-risk (the caller counts those separately).
    """
    if not amendments:
        return False
    # Period-map ceiling: only amendments plausibly targeting the PIT fiscal year.
    # Ceiling = Dec 31 of (pit_fiscal_year + 2) — 2-year window after FY end.
    # Fallback to None (= no ceiling, original behaviour) when PIT FY is unknown.
    fy_ceiling: str | None = (
        f"{pit_fiscal_year + 2}-12-31" if pit_fiscal_year is not None else None
    )
    for f in amendments:
        fd = f.get("filing_date")
        if not isinstance(fd, str):
            continue
        if fd <= as_of:
            continue  # not post-as-of: irrelevant
        if fy_ceiling is not None and fd > fy_ceiling:
            continue  # beyond the 2-year FY window: almost certainly a later FY
        return True
    return False


def _resolve_cik_for_removed_ticker(ticker: str) -> str | None:
    """Resolve a real CIK for a historically-removed ticker via edgartools.

    Guards the ``Company('')`` gotcha (CLAUDE.md §Gotchas): calling
    ``Company('')`` / ``Company(<empty>)`` with an EDGAR identity set
    resolves silently to an ARBITRARY company rather than raising — any
    subsequent history fetch then returns the WRONG company's data.

    Returns the 10-digit zero-padded CIK string when the ticker resolves to
    a real entity, or ``None`` when the CIK cannot be determined (caller
    must skip that ticker rather than proceeding with an empty or wrong CIK).

    Callers: the backfill removed-ticker pre-fetch loop only.  In-universe
    current tickers are handled by ``cik_by_ticker`` from ``get_sp500_constituents``
    (those CIKs come from the Wikipedia scrape, not from this path).
    """
    try:
        from edgar import Company  # local import — avoid top-level dependency change

        company = Company(ticker)
        raw_cik = getattr(company, "cik", None)
        if raw_cik is None:
            logger.warning(
                "backfill: removed ticker %s CIK resolved to None — skipping",
                ticker,
            )
            return None
        cik_str = str(raw_cik).strip().lstrip("0") or ""
        if not cik_str:
            logger.warning(
                "backfill: removed ticker %s CIK is blank after stripping — skipping "
                "(Company('') gotcha guard)",
                ticker,
            )
            return None
        # Zero-pad to 10 digits — canonical form used by edgartools.
        return cik_str.zfill(10)
    except Exception as exc:  # noqa: BLE001 — any resolution failure = skip
        logger.warning(
            "backfill: CIK resolution failed for removed ticker %s: %s — skipping",
            ticker,
            exc,
        )
        return None


def _insample_lag_clause(nav: dict, start: date, end: date) -> str:
    """Result-dependent honesty sentence appended to the disclaimer.

    States how the ADAPTIVE NET line (the actual headline series) actually did vs SPY
    in-sample, computed from the produced NAV so the disclaimer can never claim a win
    the chart contradicts (methodology-scientist 2026-06-05). Falls back to the
    default-count line when the adaptive series is unavailable, then to a generic
    caveat. The clause MUST describe the SAME series as the headline number — the
    adaptive series IS the home-page hero, so the honesty sentence must match it.
    """
    # Primary: describe the ADAPTIVE series (the home-page headline).
    adaptive_net: list = nav.get("adaptive", {}).get("net") or []
    spy = nav.get("benchmark", {}).get("spy") or []
    p_adp = next((v for v in reversed(adaptive_net) if v is not None), None)
    s = next((v for v in reversed(spy) if v is not None), None)

    if p_adp is not None and s is not None:
        verb = "underperformed" if p_adp < s - 0.5 else "outperformed" if p_adp > s + 0.5 else "tracked"
        return (
            f" In this {start.year}-{end.year} sample the adaptive AI-pick net"
            f" line {verb} the S&P 500 ({p_adp:.0f} vs {s:.0f}, both rebased to 100 at"
            f" the start). The adaptive rule's thresholds were selected IN-SAMPLE on this"
            f" same window — the out-of-sample edge is unknown until confirmed on a fresh"
            f" window not used during threshold selection. A factor-tilted,"
            f" sector-CONCENTRATED book (no per-sector cap) carries higher single-sector"
            f" risk and can diverge from a cap-weighted index, in either direction, for"
            f" long stretches. Any in-sample edge is concentration- and regime-driven —"
            f" past performance, even favorable, does not predict future results."
        )

    # Fallback: use the default-count line when adaptive is unavailable.
    series = nav.get("by_count", {}).get(str(DEFAULT_COUNT), {})
    net_fallback: list = series.get("net") or []
    p_fallback = next((v for v in reversed(net_fallback) if v is not None), None)
    if p_fallback is not None and s is not None:
        verb = "underperformed" if p_fallback < s - 0.5 else "outperformed" if p_fallback > s + 0.5 else "tracked"
        return (
            f" In this {start.year}-{end.year} sample the default {DEFAULT_COUNT}-holding net"
            f" line {verb} the S&P 500 ({p_fallback:.0f} vs {s:.0f}, both rebased to 100 at the start):"
            f" a factor-tilted, sector-CONCENTRATED book (no per-sector cap — it can hold many"
            f" names in one sector) carries higher single-sector risk and can diverge from a"
            f" cap-weighted index, in either direction, for long stretches. Any in-sample edge"
            f" is concentration- and regime-driven —"
            f" past performance, even favorable, does not predict future results; read the full"
            f" 1-{MAX_PICKS} holding-count ladder, not any single line."
        )

    return (
        " Past performance, even favorable, does not predict future results; read the"
        " full holding-count ladder, not any single line."
    )


def _compute_pit_risk_flags(
    snapshots: dict[str, FundamentalsSnapshot | None],
    pit_histories: dict[str, pd.DataFrame | None],
    sectors: dict[str, str],
    rebalance_date: date,
    beneish_scores: dict[str, float | None],
    dechow_scores: dict[str, float | None],
    non_reliance_by_ticker: dict[str, bool] | None = None,
) -> dict[str, list[str]]:
    """Compute the accounting-based active vetoes against the PIT cross-section.

    Six vetoes are always replayed (accounting-based, no additional EDGAR calls).
    The seventh (non_reliance_filing) is replayed when ``non_reliance_by_ticker``
    is provided (i.e. the pit_item402_history.parquet is present); otherwise it
    defaults to all-False (excluded, preserving prior behavior).

    Sloan + NSI cross-sections are computed against the live cohort AT THIS
    REBALANCE, not today's universe, so the within-sector decile thresholds are
    PIT-correct.

    ``beneish_scores`` and ``dechow_scores`` are pre-computed per-ticker before
    calling this function (to avoid recomputing inside compute_risk_flags which
    doesn't call those scorers directly — it only applies thresholds via the
    inject paths).
    """
    # When the item402 parquet is absent, fall back to all-False for the veto
    # (preserves byte-identical backtest output vs the pre-parquet state).
    nr_map = non_reliance_by_ticker if non_reliance_by_ticker is not None else {t: False for t in snapshots}
    return compute_risk_flags(
        snapshots=snapshots,
        histories={t: h for t, h in pit_histories.items() if h is not None},
        sectors=sectors,
        today=rebalance_date,  # PIT: NSI lookback anchors to T, not today
        non_reliance_by_ticker=nr_map,
        beneish_m_scores=beneish_scores,
        dechow_f_scores=dechow_scores,
    )


def _sector_weights_by_count(
    weights_by_count: dict[int, dict[str, float]],
    sector_by_ticker: dict[str, str],
) -> dict[str, dict[str, float]]:
    """Aggregate per-ticker weights into sector-weight maps for each count N.

    Returns ``{str(N): {sector: total_weight}}``. Sectors with zero weight in a
    given count are omitted (saves space). Weights round to 4 dp (2 dp is too coarse
    for small portfolios; 4 dp matches the inverse-vol weight precision needs).

    Accumulate RAW floats per sector; round ONCE per sector at the end. Rounding
    on each ADD would introduce per-step rounding error and make Σ = 1 ± n_sectors×5e-5
    instead of ≤ 1 ulp drift before the single final round.
    """
    out: dict[str, dict[str, float]] = {}
    for n, wmap in weights_by_count.items():
        raw: dict[str, float] = {}
        for ticker, w in wmap.items():
            s = sector_by_ticker.get(ticker, "Unknown")
            raw[s] = raw.get(s, 0.0) + w
        by_sector = {s: round(v, 4) for s, v in raw.items()}
        if by_sector:
            out[str(n)] = by_sector
    return out


def _adaptive_count(
    scores: list[float],
    available_counts: list[int],
    composite_min: float = ADAPTIVE_COMPOSITE_MIN,
    min_picks: int = ADAPTIVE_MIN_PICKS,
) -> tuple[int, int]:
    """``(raw, final)`` adaptive-book counts for one rebalance.

    ``raw`` = #{score >= composite_min} in the FULL deduped eligible pool
    (all scores passed in, INCLUSIVE boundary — a pick scoring exactly 65.0 is in
    the book at the default threshold). Post-uncap (2026-06-11), ``scores`` covers
    the full ``full_order`` list (not just ``picks[:MAX_PICKS]``), so ``raw`` is the
    uncensored pool size. The A1/A2/A2-S acceptance gates read this raw count.

    ``final`` (LEGACY / analytics only) = raw floored at
    ``min(min_picks, len(scores))``, then clamped to the largest available
    weights count <= it — falling back to the smallest available when none is (the
    sigma-coverage degradation path; gate A1 monitors the final count for exactly
    this reason). ``final`` keys into ``weights_by_count`` for the per-count ladder
    and is retained for the per-rebalance ``adaptive_count`` export (analytics), but
    it is NOT the authoritative book size. ``band_held_count`` is the authoritative
    band-book size (uncapped). C2 test pin:
    tests/test_portfolio/test_backfill_integration.py.

    Default values (``composite_min=ADAPTIVE_COMPOSITE_MIN``,
    ``min_picks=ADAPTIVE_MIN_PICKS``) make every existing call site byte-identical
    to the pre-refactor behaviour — the 12-config grid passes explicit overrides.
    """
    raw = sum(1 for s in scores if s >= composite_min)
    final = max(raw, min(min_picks, len(scores)))
    avail = sorted(available_counts)
    if avail:
        final = max((c for c in avail if c <= final), default=avail[0])
    return raw, final


def _band_book(
    order: list[str],
    scores: dict[str, float],
    tenure: set[str],
    composite_min: float = ADAPTIVE_COMPOSITE_MIN,
    min_picks: int = ADAPTIVE_MIN_PICKS,
) -> tuple[list[str], set[str], int]:
    """Pure hysteresis-hold-band book builder (C2 unit-testability gate).

    Post-uncap (2026-06-11): the ``MAX_PICKS`` ceiling on ``core`` is REMOVED.
    ``order`` may contain > MAX_PICKS names (the caller passes ``full_order`` from
    the uncapped ``select_picks(count=None)`` call), and the band book may grow
    beyond MAX_PICKS when many incumbents score >= 65 or there are many fresh
    entrants. Cap removed per the 2026-06-11 uncap ratification; floor logic
    unchanged: pads to ``min(min_picks, len(order))``.

    ``order``        — HC-eligible tickers sorted composite-desc (output of
                       ``select_picks(count=None)``; the caller's HC gate is the sole
                       eligibility filter — ``_band_book`` does not re-check veto flags).
    ``scores``       — composite score for each ticker (at minimum covers every ticker
                       in ``order``; extra keys are silently ignored).
    ``tenure``       — set of tickers that entered the book via >= ``composite_min``
                       in a prior rebalance; empty on the first rebalance (band inert).
    ``composite_min`` — entry threshold (default ADAPTIVE_COMPOSITE_MIN = 65.0). The
                       12-config grid passes explicit overrides; existing callers that
                       omit this argument are BYTE-IDENTICAL to the pre-refactor behaviour.
    ``min_picks``    — floor on book size (default ADAPTIVE_MIN_PICKS = 5). Same
                       byte-identity guarantee for existing callers.

    Returns ``(book, next_tenure, carry_count)`` where:
      ``book``        — ordered list of selected tickers (composite-desc, alpha-asc tiebreak);
      ``next_tenure`` — tenure set to carry forward (= set(core), pads excluded — C0);
      ``carry_count`` — # tenured names retained via the band (score in [55, composite_min));
                        first rebalance always returns 0.

    Semantics (C0 strict tenure):
      carries  = tenured ∩ eligible with composite >= ``ADAPTIVE_HOLD_BAND_MIN``
                 (55 <= score; the >= composite_min entry requirement was met in a prior rebalance).
      fresh    = eligible with composite >= ``composite_min``
                 that are NOT already counted as carries.
      core     = sorted(carries ∪ fresh) by (-composite, ticker).
                 (NO MAX_PICKS cap — uncapped per 2026-06-11 ratification.)
      pads     = top non-core eligible names to reach
                 ``min(min_picks, len(order))``; pads get NO tenure.
      book     = sorted(core + pads) by (-composite, ticker).
      next_tenure = set(core) (not pads — C0).
      carry_count = #{t in core : t in tenure AND score < composite_min}
                    i.e. names held via the band (not fresh entrants).
    """
    eligible_set = set(order)  # HC-eligible this rebalance (already filtered by caller)

    # Carries: prior tenured names that are still HC-eligible AND score >= band floor.
    carries: list[str] = [
        t for t in tenure
        if t in eligible_set and scores.get(t, 0.0) >= ADAPTIVE_HOLD_BAND_MIN
    ]

    # Fresh: HC-eligible names scoring >= entry threshold, not already a carry.
    carry_set = set(carries)
    fresh: list[str] = [
        t for t in order
        if t not in carry_set and scores.get(t, 0.0) >= composite_min
    ]

    # Core: union of carries + fresh, sorted by (-score, ticker).
    # NO MAX_PICKS cap — uncapped per the 2026-06-11 uncap ratification.
    core_unsorted = carries + [t for t in fresh if t not in carry_set]
    core: list[str] = sorted(
        core_unsorted,
        key=lambda t: (-scores.get(t, 0.0), t),
    )
    core_set = set(core)

    # Pads: top non-core eligible names to reach min_picks (or available count).
    target = min(min_picks, len(order))
    pads: list[str] = []
    if len(core) < target:
        for t in order:
            if t not in core_set:
                pads.append(t)
                if len(core) + len(pads) >= target:
                    break

    # Book: core + pads sorted by (-score, ticker).
    book: list[str] = sorted(
        core + pads,
        key=lambda t: (-scores.get(t, 0.0), t),
    )

    # Next tenure = set(core) only — pads get no tenure (C0).
    next_tenure: set[str] = core_set

    # Carry count: core names that are tenured AND score < entry threshold (the band is
    # the reason they are in the book — fresh entrants >= composite_min are NOT carry-band names).
    carry_count: int = sum(
        1 for t in core
        if t in tenure and scores.get(t, 0.0) < composite_min
    )

    return book, next_tenure, carry_count


def run_backfill(
    start: date, end: date, *, data_dir: Path | None = None, gate: str = "high_conviction"
) -> Path:
    """``gate`` selects the eligibility filter (see ``select_picks``): the production
    default ``"high_conviction"`` (Strong Buy/Buy + MoS>0 + composite>=50 +
    loss-chance<=45) or ``"veto_only"`` (the legacy composite-rank basket). The
    end-to-end WIRING (snapshot -> pillars -> composite -> NAV -> canary) is gate-
    independent, so wiring tests pass ``gate="veto_only"`` to exercise it with
    synthetic data that need not clear the conviction gate."""
    data_dir = data_dir or config.DATA_DIR
    members = get_sp500_constituents()
    current = {str(r.ticker) for r in members.itertuples(index=False)}
    cik_by_ticker = {str(r.ticker): str(r.cik) for r in members.itertuples(index=False)}
    sector_by_ticker = {str(r.ticker): str(r.sector) for r in members.itertuples(index=False)}

    # --- GAP 2: item402 PIT history observability (Rule 18) ---
    # Check parquet presence ONCE before the loop; emit meta counters regardless.
    _item402_pit_rows: int = item402_parquet_row_count()
    _item402_parquet_present: bool = _item402_pit_rows > 0
    _item402_veto_fired_count: int = 0  # incremented per-rebalance below

    # --- GAP 1: historical sector PIT observability (Rule 18) ---
    _sector_stats = historical_sector_parquet_stats()
    _sector_parquet_present: bool = _sector_stats["parquet_present"]
    _historical_sector_lookup_count: int = 0
    _historical_sector_fallback_count: int = 0

    def _pit_sector(ticker: str, as_of: date) -> str:
        """Return PIT GICS sector; track fallbacks for Rule 18 meta counters."""
        nonlocal _historical_sector_lookup_count, _historical_sector_fallback_count
        _historical_sector_lookup_count += 1
        if not _sector_parquet_present:
            # Parquet absent: all lookups are fallbacks; call sector_at anyway
            # so it returns via today's-sector fallback gracefully.
            _historical_sector_fallback_count += 1
            return sector_at(ticker, as_of)
        result = sector_at(ticker, as_of)
        # Detect fallback: if the parquet is present but returned today's sector,
        # the sector_at call fell back (ticker not in parquet for this date).
        # We infer fallback by checking whether the parquet has a row for this
        # ticker + date; since sector_at is opaque, we use today's sector dict
        # as a signal (if result == sector_by_ticker.get(ticker, "Unknown"),
        # it MAY be a fallback OR a genuine PIT match). We accept this
        # over-counting trade-off (conservative: may over-count fallbacks for
        # tickers whose sector didn't change) — the counter is diagnostic only.
        today_sector = sector_by_ticker.get(ticker, "Unknown")
        if result == today_sector or result == "Unknown":
            # Potential fallback — could also be a PIT match that happens to
            # equal today's sector (which is correct for ~91% of rebalances).
            # We count it as a potential fallback only for tickers NOT in the
            # current universe (removed tickers never appear in the parquet).
            if ticker not in sector_by_ticker:
                _historical_sector_fallback_count += 1
        return result

    # Load each name's caches ONCE (warm in CI). annual rows (PIT) + price frame.
    #
    # Price depth contract: the backfill needs price history back to
    # ``start - _SIGMA_LOOKBACK_BUFFER_DAYS`` so the FIRST rebalance's
    # trailing-90-day sigma window is fully populated.  Under Design A the
    # download path always fetches from config.PRICES_FETCH_START, so the
    # ``period="max"`` argument here is VESTIGIAL — ``min_start`` is the
    # load-bearing backstop that turns a too-shallow cached frame into a deep
    # refetch (do NOT delete it on the strength of the period arg).
    # Newly-listed tickers whose entire history is shallower than the floor are
    # returned as-is (single refetch, no loop — see fetch_prices docstring).
    _price_floor: date = start - timedelta(days=_SIGMA_LOOKBACK_BUFFER_DAYS)
    rows_by_ticker: dict[str, list[dict]] = {}
    prices_by_ticker: dict[str, pd.DataFrame] = {}
    for ticker in sorted(current):
        try:
            rows_by_ticker[ticker] = _annual_rows(fetch_fundamentals_history(cik_by_ticker[ticker]))
            pf = fetch_prices(ticker, period="max", min_start=_price_floor)
            if pf is not None and len(pf) > 0:
                prices_by_ticker[ticker] = pf
        except Exception as e:  # noqa: BLE001 — one bad name never kills the backfill
            logger.warning("backfill: load failed for %s: %s", ticker, e)

    # --- Survivorship-bias fix: expand the pre-fetch set to include REMOVED tickers.
    #
    # The pre-fetch loop above only covers today's S&P 500 (~502 tickers).  At each
    # rebalance T, ``members_at(T)`` correctly reverse-walks the ledger and adds back
    # tickers that WERE members at T but have since been removed (the ``cohort``).
    # Without this block those removed tickers are absent from ``rows_by_ticker`` /
    # ``prices_by_ticker``, so the scoring loop's ``if prices is None: continue``
    # silently drops them — preserving residual survivorship bias even though the
    # membership is PIT-correct.
    #
    # GUARDRAIL: NEVER pass an empty / unresolved CIK to ``fetch_fundamentals_history``
    # (``Company('')`` resolves to an ARBITRARY company, CLAUDE.md §Gotchas).  For each
    # removed ticker we resolve a real CIK via ``_resolve_cik_for_removed_ticker``; any
    # ticker whose CIK cannot be resolved is skipped entirely with a structured log line.
    #
    # Rule 18 observability (SKILL.md): three counters land in ``meta`` so the next run
    # makes the closure VISIBLE without requiring manual log parsing.
    _removed_events = list_known_events(since=start)
    _removed_tickers: set[str] = {
        ev.ticker for ev in _removed_events if ev.action == _ACTION_REMOVE
    } - current  # exclude any ticker re-added to current universe
    _scoring_universe_removed_candidates_count: int = len(_removed_tickers)
    _scoring_universe_removed_fetched_count: int = 0
    _scoring_universe_removed_unavailable_count: int = 0

    for ticker in sorted(_removed_tickers):
        cik = _resolve_cik_for_removed_ticker(ticker)
        if cik is None:
            # CIK unresolvable — log already emitted by the resolver.
            logger.warning(
                "backfill: removed ticker %s skipped — no-CIK (survivorship fix)",
                ticker,
            )
            _scoring_universe_removed_unavailable_count += 1
            continue
        try:
            rows = _annual_rows(fetch_fundamentals_history(cik))
            pf = fetch_prices(ticker, period="max", min_start=_price_floor)
            if pf is not None and len(pf) > 0:
                rows_by_ticker[ticker] = rows
                prices_by_ticker[ticker] = pf
                _scoring_universe_removed_fetched_count += 1
                logger.info(
                    "backfill: removed ticker %s (CIK=%s) pre-fetched successfully"
                    " — rows=%d price_rows=%d",
                    ticker, cik, len(rows), len(pf),
                )
            else:
                logger.warning(
                    "backfill: removed ticker %s (CIK=%s) skipped — no usable prices"
                    " (survivorship fix)",
                    ticker, cik,
                )
                _scoring_universe_removed_unavailable_count += 1
        except Exception as exc:  # noqa: BLE001 — one bad removed ticker never kills the backfill
            logger.warning(
                "backfill: removed ticker %s (CIK=%s) fetch-error — %s"
                " (survivorship fix, graceful-degradation)",
                ticker, cik, exc,
            )
            _scoring_universe_removed_unavailable_count += 1

    # Removed tickers only need sector assignment for the rebalances where they
    # appear.  We use "Unknown" as a safe fallback — GICS sector is "stable from
    # today" (the existing backtest approximation; see meta.sector_from_today).
    # Tickers already in sector_by_ticker (current universe) are unaffected.
    for ticker in _removed_tickers:
        if ticker not in sector_by_ticker:
            sector_by_ticker[ticker] = "Unknown"

    logger.info(
        "backfill: survivorship-fix pre-fetch complete — candidates=%d fetched=%d"
        " unavailable=%d",
        _scoring_universe_removed_candidates_count,
        _scoring_universe_removed_fetched_count,
        _scoring_universe_removed_unavailable_count,
    )

    spy = fetch_prices("SPY", period="max", min_start=_price_floor)

    rebal_dates = quarterly_rebalance_dates(start, end)
    rebalances_out: list[dict] = []
    # Per rebalance: (snapped_date, {count N -> {ticker -> weight}}, n_adaptive) for
    # N=1..MAX_PICKS.  The NAV builder turns each N into its own daily NAV series; the
    # frontend slider reads the matching count. n_adaptive is the adaptive-book count
    # for this rebalance (composite >= ADAPTIVE_COMPOSITE_MIN, floored at ADAPTIVE_MIN_PICKS,
    # capped at MAX_PICKS; see the adaptive-rule constants above).
    rebalance_picks: list[tuple[str, dict[int, dict[str, float]], int]] = []
    # Band-leg list for _assemble_nav: each entry is (snapped_date, {ticker: weight}).
    # The band NAV replaces the prefix-based adaptive NAV as the product adaptive series.
    band_legs_for_nav: list[tuple[str, dict[str, float]]] = []
    # C0 tenure set: names that entered the book via composite >= ADAPTIVE_COMPOSITE_MIN;
    # carries forward across rebalances; empty = band inert on first rebalance.
    band_tenure: set[str] = set()

    # 12-config grid: per-config band legs (for monthly NAV assembly) and tenure state.
    # FOOTGUN GUARD: each config needs its OWN tenure set — sharing would couple
    # hysteresis across configs with different composite_min thresholds (e.g. a name
    # tenured at cmin=55 silently leaking into cmin=70's carry set).  NEVER alias.
    # Initialised as dict-of-list (band legs) + dict-of-set (tenure per config).
    grid_legs: dict[str, list[tuple[str, dict[str, float]]]] = {k: [] for k in _GRID_CONFIG_KEYS}
    grid_tenure: dict[str, set[str]] = {k: set() for k in _GRID_CONFIG_KEYS}

    incomplete_membership = 0
    restate_names: set[str] = set()
    picked_names: set[str] = set()
    restate_unresolved: set[str] = set()
    hc_counts: list[int] = []  # PR-1: per-rebalance high-conviction-eligible counts (C1)

    # Restatement canary — re-sourced from the EDGAR filings index (the live
    # restatement_history flag's feed) rather than companyfacts-XBRL. Amendment history
    # is per-name (filtered by filing_date > T per rebalance), so fetch it LAZILY per
    # picked name and memoize: only the ~50-80 names ever selected hit EDGAR, not the
    # full ~500 universe. Lookback spans the whole window back from today.
    amend_window_days = (date.today() - start).days + 60
    amend_memo: dict[str, list[dict] | None] = {}

    def _amendments(ticker: str) -> list[dict] | None:
        if ticker not in amend_memo:
            try:
                amend_memo[ticker] = fetch_amendments(ticker, lookback_days=amend_window_days)
            except Exception as e:  # noqa: BLE001 — a canary fetch never kills the backfill
                logger.warning("backfill: amendment fetch failed for %s: %s", ticker, e)
                amend_memo[ticker] = None
        return amend_memo[ticker]

    for T in rebal_dates:
        T_iso = T.isoformat()
        T_ts = pd.Timestamp(T)
        res = members_at(T, current_universe=current)
        if not res.is_complete:
            incomplete_membership += 1
            continue  # don't trust a leg whose survivorship is degraded
        cohort = res.tickers

        inputs: dict[str, TickerInputs] = {}
        for ticker in cohort:
            rows = rows_by_ticker.get(ticker, [])
            prices = prices_by_ticker.get(ticker)
            if prices is None:
                continue
            cur_px = _price_at(prices, T_ts)
            if cur_px is None:
                continue
            snap = _pit_snapshot(ticker, cik_by_ticker.get(ticker, ""), rows, T_iso)
            # GUARDRAIL 1 — history fed to growth/quality pillars is filed<=T.
            pit_hist = pd.DataFrame(pit_history_rows(rows, T_iso)) if rows else None
            inputs[ticker] = TickerInputs(
                snapshot=snap,
                prices=prices.loc[:T_ts],
                benchmark_prices=spy.loc[:T_ts] if spy is not None else None,
                current_price=cur_px,
                # GAP 1: Use PIT sector from historical_sector parquet when present;
                # falls back to today's Wikipedia sector gracefully when absent.
                sector=_pit_sector(ticker, T),
                history=pit_hist,
            )

        if not inputs:
            continue

        pillar_df = compute_all_pillars(inputs)
        pillar_df, _ = neutralize_pillar_scores(pillar_df)
        composite = compute_composite(pillar_df)

        # --- Point-in-time valuation + recommendation replay. Reuse the LIVE
        # cross-sectional builders on THIS rebalance's PIT cohort so MoS / recommendation
        # / loss-chance match the forward rule. PR-1 added this to COUNT eligibles; PR-2
        # now FEEDS it into selection — `select_picks(gate=gate)` (production default
        # "high_conviction") holds only names clearing Strong Buy/Buy + MoS>0 +
        # composite>=50 + loss-chance<=45. eligible_high_conviction_count stays as the
        # per-rebalance diagnostic (C1 cleared: median 52 >> DEFAULT_COUNT).
        snaps_by_ticker = {t: inp.snapshot for t, inp in inputs.items()}
        hist_by_ticker = {
            t: inp.history for t, inp in inputs.items() if inp.history is not None
        }
        val_df = pd.DataFrame(
            [
                {"ticker": t, "current_price": inp.current_price, "sector": inp.sector}
                for t, inp in inputs.items()
            ]
        )
        universe_metrics = _build_universe_metrics(snaps_by_ticker, val_df)
        _by_sub, by_sector_panel, broad_ex_fin_util = _build_peer_groupings(val_df)
        historical_metrics = _build_historical_metrics(hist_by_ticker, snaps_by_ticker)

        mos_by_ticker: dict[str, float | None] = {}
        rec_by_ticker: dict[str, str | None] = {}
        lc_by_ticker: dict[str, float | None] = {}
        for raw_t in composite.index:
            t = str(raw_t)
            inp = inputs.get(t)
            snap_t = snaps_by_ticker.get(t)
            if inp is None or snap_t is None:
                continue
            sector_panel = [x for x in by_sector_panel.get(inp.sector, []) if x != t]
            broad_panel = [x for x in broad_ex_fin_util if x != t]
            tier_panel = {
                "sub_industry": [],  # GICS sub-industry not carried PIT -> sector fallback
                "industry": [],
                "sector": sector_panel,
                "broad": broad_panel,
            }
            peer_panels = {"pe": tier_panel, "pb": tier_panel, "ev_ebitda": tier_panel}
            mos: float | None = None
            try:
                result, _flags = compute_fair_price_ensemble(
                    ticker=t,
                    snap=snap_t,
                    sector=inp.sector,
                    sub_industry=None,
                    industry=None,
                    current_price=inp.current_price,
                    filing_lag_days_value=_pit_filing_lag(rows_by_ticker.get(t, []), T_iso, T),
                    peer_panels=peer_panels,
                    universe_metrics=universe_metrics,
                    historical_metrics=historical_metrics,
                    hard_stale_days=BACKTEST_HARD_STALE_DAYS,
                )
                mos = result.mos_pct
            except Exception as e:  # noqa: BLE001 — one bad name never kills the backfill
                logger.warning("backfill: ensemble failed for %s @ %s: %s", t, T_iso, e)
            cs = float(composite[t])
            mos_by_ticker[t] = mos
            rec_by_ticker[t] = derive_recommendation(
                composite_score=cs, risk_flags=(), valuation_warnings=(), mos_pct=mos
            )
            lc_by_ticker[t] = derive_loss_chance(
                composite_score=cs, risk_flags=(), valuation_warnings=(), mos_pct=mos
            )

        # --- Phase 7.0c: PIT veto-layer replay ---
        # Compute Beneish and Dechow scores per-ticker before calling compute_risk_flags
        # (the inject paths in compute_risk_flags take pre-computed scores as dicts).
        # Using PIT pit_hist ensures the prior-year lookbacks are also filed<=T.
        beneish_scores: dict[str, float | None] = {}
        dechow_scores: dict[str, float | None] = {}
        for t, inp in inputs.items():
            snap_t = snaps_by_ticker.get(t)
            pit_hist_t = inp.history  # already filed<=T (GUARDRAIL 1 above)
            try:
                br = compute_beneish(snap_t, pit_hist_t)
                beneish_scores[t] = br.m_score
            except Exception as e:  # noqa: BLE001
                logger.warning("backfill: beneish failed for %s @ %s: %s", t, T_iso, e)
                beneish_scores[t] = None
            try:
                dr = compute_dechow_f(snap_t, pit_hist_t)
                dechow_scores[t] = dr.f_score
            except Exception as e:  # noqa: BLE001
                logger.warning("backfill: dechow failed for %s @ %s: %s", t, T_iso, e)
                dechow_scores[t] = None

        # --- GAP 2: item402 PIT replay (non_reliance_filing veto) ---
        # When the parquet is present, build a PIT-correct non_reliance_by_ticker dict
        # by calling check_non_reliance with filings pre-filtered to <= T.
        # When absent, non_reliance_by_ticker=None → _compute_pit_risk_flags falls back
        # to all-False (byte-identical to the pre-parquet backtest — graceful degradation).
        pit_non_reliance: dict[str, bool] | None = None
        if _item402_parquet_present:
            pit_non_reliance = {}
            for t in snaps_by_ticker:
                try:
                    filings_pit = item402_filings_for(t, before_date=T)
                    flag = check_non_reliance(t, asof=T, filings=filings_pit)
                    pit_non_reliance[t] = flag.fired
                    if flag.fired:
                        _item402_veto_fired_count += 1
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "backfill: item402 lookup failed for %s @ %s: %s — defaulting to False",
                        t, T_iso, e,
                    )
                    pit_non_reliance[t] = False

        # Only pass non_reliance_by_ticker when the parquet is present; omitting
        # it entirely when None preserves backward compat with existing test mocks
        # that don't expect the new keyword argument.
        _nr_kwargs = (
            {"non_reliance_by_ticker": pit_non_reliance}
            if pit_non_reliance is not None
            else {}
        )
        pit_risk_flags = _compute_pit_risk_flags(
            snapshots=snaps_by_ticker,
            pit_histories={t: inp.history for t, inp in inputs.items()},
            sectors={t: inp.sector for t, inp in inputs.items()},
            rebalance_date=T,
            beneish_scores=beneish_scores,
            dechow_scores=dechow_scores,
            **_nr_kwargs,
        )

        # Build full_ranked: top-_FULL_RANKED_LIMIT names by composite at this rebalance,
        # including vetoed names (the rank excludes no one — vetoed names just can't be
        # picked). Provides the raw composite leaderboard the veto selection effect
        # analysis reads from.
        composite_sorted = sorted(
            [(str(t), float(composite[t])) for t in composite.index],
            key=lambda x: -x[1],
        )
        # NOTE — full_ranked[*].recommendation is derived pre-veto (risk_flags=() in
        # derive_recommendation above). This is DELIBERATE: full_ranked is a raw-signal
        # leaderboard for rank-banding / sector-cap experiments; it carries the composite
        # rank and valuation label before the veto layer has a chance to exclude names.
        # Selection is NOT affected — vetoes operate in select_picks via PickCandidate
        # .risk_flags (populated from pit_risk_flags below). Do NOT "fix" this to pass
        # the live veto flags into derive_recommendation for full_ranked: that would hide
        # a vetoed name's true recommendation label and make the leaderboard look cleaner
        # than the raw signal warrants (a Rule-16 annotate-vs-veto violation).
        full_ranked = [
            {
                "ticker": t,
                "composite_score": round(cs, 2),
                "sector": sector_by_ticker.get(t, "Unknown"),
                "mos_pct": (
                    round(mos_by_ticker[t], 2) if mos_by_ticker.get(t) is not None else None
                ),
                "recommendation": rec_by_ticker.get(t),
            }
            for t, cs in composite_sorted[:_FULL_RANKED_LIMIT]
        ]

        candidates = [
            PickCandidate(
                ticker=str(t),
                composite_score=float(composite[t]),
                sector=sector_by_ticker.get(str(t), "Unknown"),
                risk_flags=tuple(pit_risk_flags.get(str(t), [])),  # PIT veto flags
                recommendation=rec_by_ticker.get(str(t)),
                mos_pct=mos_by_ticker.get(str(t)),
                loss_chance_pct=lc_by_ticker.get(str(t)),
            )
            for t in composite.index
        ]
        # Fast O(1) lookup for the high_conviction_count per-pick computation below.
        candidates_by_ticker: dict[str, PickCandidate] = {c.ticker: c for c in candidates}
        # PR-2: the high-conviction gate now DRIVES selection (C1 cleared on PR-1's
        # backfill — median eligible 52 >> DEFAULT_COUNT). eligible_high_conviction_count
        # stays as the per-rebalance diagnostic; picks = top-N BY COMPOSITE among the
        # gate-eligible names (Strong Buy/Buy + MoS>0 + composite>=50 + loss-chance<=45).
        high_conviction_count = sum(1 for c in candidates if is_high_conviction(c))
        mos_positive_count = sum(
            1 for c in candidates if c.mos_pct is not None and c.mos_pct > 0.0
        )
        hc_counts.append(high_conviction_count)

        # Phase 7.0c: Record names that would have been top-MAX_PICKS picks by composite
        # but were excluded by veto flags. These are the "selection effect" names — the
        # headline measurement of whether the veto layer rescues or suppresses picks.
        # We collect candidates that: (a) have at least one active veto flag, and
        # (b) rank in the top MAX_PICKS by composite among all candidates, so they
        # WOULD have appeared if the veto layer were absent.
        vetoed_pick_candidates: list[dict] = []
        top_n_by_composite = sorted(candidates, key=lambda c: -c.composite_score)[:MAX_PICKS]
        for c in top_n_by_composite:
            flags = list(c.risk_flags)
            if flags:  # has at least one active veto -> would have been in top-N but vetoed
                vetoed_pick_candidates.append(
                    {
                        "ticker": c.ticker,
                        "composite_score": round(c.composite_score, 2),
                        "flags": flags,
                    }
                )

        # Sell-eviction is implicit: a name that decayed out of the gate this quarter
        # is absent from the eligible set and won't be re-picked (the basket is rebuilt
        # from scratch each rebalance).
        # U2 uncap (2026-06-11): get the FULL uncapped eligible order (all HC-eligible
        # names in composite-desc order, no [MIN_PICKS, MAX_PICKS] clamp); then take
        # ``picks`` as the top-MAX_PICKS prefix for the legacy holdings/weights_by_count
        # path. The single select_picks(count=None) call preserves all ordering/dedup
        # semantics (dual-class, tiebreak) on the full domain.
        full_order = select_picks(candidates, count=None, gate=gate)
        if not full_order:
            continue
        picks = full_order[:MAX_PICKS]

        # U3 sigma coverage: compute sigmas over the UNION of picks (by_count domain)
        # AND band_book (which may include members beyond rank-20 when the band retains
        # them). Since band_book is computed BELOW (needs only order+scores+tenure),
        # we first compute sigmas over `picks` here for weights_by_count, then extend
        # to the full band_book domain after _band_book is called. prices_by_ticker
        # already holds the full cohort, so extending is cheap.
        sigmas: dict[str, float] = {}
        for t in picks:
            if t not in prices_by_ticker:
                continue
            closes = prices_by_ticker[t].loc[:T_ts]
            col = "Adj Close" if "Adj Close" in closes.columns else "Close"
            sig = trailing_return_sigma(closes[col].tolist())
            if sig is not None:
                sigmas[t] = sig
        # Per-count inverse-vol weights: for each selectable basket size N=1..MAX_PICKS,
        # weight the top-N picks by inverse vol (the SAME ratified rule, applied to the
        # top-N subset of THIS rebalance's cohort). The legacy 1-20 slider fallback reads
        # weights_by_count[N]; _assemble_nav builds a NAV per N from these.
        weights_by_count: dict[int, dict[str, float]] = {}
        for n in range(1, MAX_PICKS + 1):
            sub = {t: sigmas[t] for t in picks[:n] if t in sigmas}
            w = inverse_vol_weights(sub) if sub else {}
            if w:
                weights_by_count[n] = w
        if not weights_by_count:
            continue  # no name in this leg had a computable 90d sigma

        # U4 adaptive_count_raw: count from the FULL deduped pool (full_order), not
        # just the MAX_PICKS prefix. This is the uncensored pool size the A1/A2/A2-S
        # gates read. The legacy `_adaptive_count` `final` value keys into
        # weights_by_count for the per-rebalance analytics export.
        n_adaptive_raw, n_adaptive = _adaptive_count(
            [float(composite[t]) for t in full_order], list(weights_by_count.keys())
        )

        rebalance_picks.append((T_iso, weights_by_count, n_adaptive))

        # V55 hysteresis hold-band: build the banded book from the HC-eligible
        # full_order (uncapped domain), threading tenure state across rebalances
        # (C0 strict tenure semantics). The band book may exceed MAX_PICKS now that
        # the core cap is removed — all fresh >= 65 + carried >= 55 names are included.
        scores_this = {t: float(composite[t]) for t in full_order}
        # Snapshot prior tenure BEFORE updating — carry_names_in_book references the OLD
        # tenure (names that were tenured going INTO this rebalance, i.e. the true carries).
        prior_band_tenure = band_tenure
        band_book, next_band_tenure, band_carry_count = _band_book(
            full_order, scores_this, prior_band_tenure
        )

        # U3 sigma coverage extension: ensure sigmas cover every band_book member
        # (rank-21+ names that the band retains need their sigma for band_weights).
        for t in band_book:
            if t in sigmas or t not in prices_by_ticker:
                continue
            closes = prices_by_ticker[t].loc[:T_ts]
            col = "Adj Close" if "Adj Close" in closes.columns else "Close"
            sig = trailing_return_sigma(closes[col].tolist())
            if sig is not None:
                sigmas[t] = sig
        band_tenure = next_band_tenure  # thread tenure state to the next rebalance

        # Compute inverse-vol weights FRESH over the banded book (not from weights_by_count
        # which is prefix-based; the band book is not necessarily a prefix).
        band_sigmas = {t: sigmas[t] for t in band_book if t in sigmas}
        band_weights_map = inverse_vol_weights(band_sigmas) if band_sigmas else {}

        # Carry-weight share: fraction of the band book's total weight held by carry names
        # (those in prior tenure AND score < ADAPTIVE_COMPOSITE_MIN — the band's value).
        # Rounded to 4 dp per spec; None when the book has no weight (degenerate leg).
        # Carry names: tenured incumbents held via the band (55 <= score < 65).
        # Lower bound matters: a force-sold (< 55) tenured name re-entering as a
        # floor PAD must not pollute the H2 gate's carry-share input.
        carry_names_in_book = {
            t for t in band_book
            if t in prior_band_tenure
            and ADAPTIVE_HOLD_BAND_MIN <= scores_this.get(t, 0.0) < ADAPTIVE_COMPOSITE_MIN
        }
        band_carry_weight_share: float | None = None
        if band_weights_map:
            band_carry_weight_share = round(
                # float() guards the empty-carry case: sum() over an empty
                # generator returns int(0); the artifact contract is float.
                float(sum(band_weights_map.get(t, 0.0) for t in carry_names_in_book)),
                4,
            )

        # Collect this leg's band weights for the adaptive NAV (replaces the old
        # prefix-based adaptive series as THE product adaptive line).
        if band_weights_map:
            band_legs_for_nav.append((T_iso, band_weights_map))

        # 12-config grid fork: each config calls _band_book with its own (cmin, floor)
        # and its OWN tenure set — NEVER share tenure across configs.
        # scores_this and full_order are already computed; sigmas coverage from the
        # product band_book pass above is REUSED (no price re-walk per config).
        for g_key, (g_cmin, g_floor) in zip(_GRID_CONFIG_KEYS, _GRID_CONFIGS, strict=True):
            g_prior_tenure = grid_tenure[g_key]
            g_book, g_next_tenure, _ = _band_book(
                full_order, scores_this, g_prior_tenure,
                composite_min=float(g_cmin), min_picks=g_floor,
            )
            grid_tenure[g_key] = g_next_tenure  # thread tenure forward (per-config isolation)
            # Sigma coverage for grid members: reuse sigmas dict (already covers full_order
            # + product band_book); extend for any grid-only members the product missed.
            for t in g_book:
                if t in sigmas or t not in prices_by_ticker:
                    continue
                closes_t = prices_by_ticker[t].loc[:T_ts]
                col_t = "Adj Close" if "Adj Close" in closes_t.columns else "Close"
                sig_t = trailing_return_sigma(closes_t[col_t].tolist())
                if sig_t is not None:
                    sigmas[t] = sig_t
            g_sigmas = {t: sigmas[t] for t in g_book if t in sigmas}
            g_weights = inverse_vol_weights(g_sigmas) if g_sigmas else {}
            if g_weights:
                grid_legs[g_key].append((T_iso, g_weights))
                logger.debug(
                    "backfill: grid config %s emitted %d/%d legs (T=%s, book_size=%d)",
                    g_key,
                    len(grid_legs[g_key]),
                    # expected_leg_count is only known at assembly; log partial count here
                    len(rebalance_picks),
                    T_iso,
                    len(g_book),
                )
            else:
                logger.info(
                    "backfill: grid config %s leg %s — no usable sigmas, leg dropped"
                    " (book_size=%d, all uncomputable)",
                    g_key, T_iso, len(g_book),
                )

        # Contamination canary tracks the FULL selectable set (top-MAX_PICKS) — any of
        # these names can surface once the user slides the count up. A name whose
        # amendment fetch failed is "unresolved" (counted separately), not at-risk.
        # Post-uncap the product band book can hold rank-21+ names outside `picks`;
        # the contamination canary must see every holdable name, not just the top-20.
        #
        # FIX 1 (restatement period-map refinement, 2026-06-13): pass the PIT fiscal
        # year so _restatement_at_risk only counts amendments whose filing_date falls
        # within 2 years of the PIT 10-K's fiscal year-end, reducing the over-count
        # of amendments targeting entirely different fiscal years.
        picked_names.update(set(picks) | set(band_book))
        for t in sorted(set(picks) | set(band_book)):
            amends = _amendments(t)
            if amends is None:
                restate_unresolved.add(t)
            else:
                pit_fy = _pit_fiscal_year_at(rows_by_ticker.get(t, []), T_iso)
                if _restatement_at_risk(amends, T_iso, pit_fiscal_year=pit_fy):
                    restate_names.add(t)

        # Phase 7.0c: sector_weights_by_count — derived per-N sector-weight map.
        sw_by_count = _sector_weights_by_count(weights_by_count, sector_by_ticker)

        rebalances_out.append(
            {
                "date": T_iso,
                "members_complete": True,
                "holdings": [
                    {
                        "ticker": t,
                        "composite_score": round(float(composite[t]), 2),
                        "sector": sector_by_ticker.get(t, "Unknown"),
                        "sigma_90d": round(sigmas[t], 6) if t in sigmas else None,
                        # Phase 7.0c: signed MoS% per holding (None-safe).
                        "mos_pct": (
                            round(mos_by_ticker[t], 2)
                            if mos_by_ticker.get(t) is not None
                            else None
                        ),
                    }
                    for t in picks
                ],
                "weights_by_count": {
                    str(n): {t: round(w, 6) for t, w in wmap.items()}
                    for n, wmap in weights_by_count.items()
                },
                # PR-1 observability (not yet driving selection): how many cohort names
                # would clear the high-conviction gate / have positive MoS this rebalance.
                "eligible_high_conviction_count": high_conviction_count,
                "mos_positive_count": mos_positive_count,
                # Phase 7.0c: new fields.
                # full_ranked: top-_FULL_RANKED_LIMIT names by composite (including vetoed);
                # enables rank-banding + sector-cap experiments.
                "full_ranked": full_ranked,
                # high_conviction_count: how many of the MAX_PICKS picks cleared
                # the high-conviction gate at this rebalance (distinct from the
                # cohort-wide eligible_high_conviction_count above).
                "high_conviction_count": sum(
                    1 for t in picks
                    if is_high_conviction(candidates_by_ticker.get(t, PickCandidate(
                        ticker=t, composite_score=0.0, sector="Unknown"
                    )))
                ),
                # sector_weights_by_count: {str(N): {sector: total_weight}}.
                "sector_weights_by_count": sw_by_count,
                # vetoed_pick_candidates: names that would have appeared in the top-N
                # composite basket but were excluded by at least one active veto.
                "vetoed_pick_candidates": vetoed_pick_candidates,
                # adaptive_count: LEGACY/analytics prefix count (floored at
                # ADAPTIVE_MIN_PICKS, clamped to an available weights_by_count key
                # <= MAX_PICKS). band_held_count is the authoritative book size.
                "adaptive_count": n_adaptive,
                # adaptive_count_raw: PRE-floor count over the FULL deduped
                # HC-eligible pool (uncensored, post-uncap) — the A1 drought /
                # A2 inflation / A2-S spike gates read this, not the floored count.
                "adaptive_count_raw": n_adaptive_raw,
                # V55 hysteresis hold-band exports (ratified 2026-06-11).
                # band_book: the banded book tickers ordered by (-composite, ticker).
                "band_book": band_book,
                # band_weights: inverse-vol weights over the band book (fresh per leg);
                # {ticker: round(w, 6)} — NOT a prefix of weights_by_count.
                "band_weights": {t: round(w, 6) for t, w in band_weights_map.items()},
                # band_held_count: number of names in the banded book this rebalance.
                "band_held_count": len(band_book),
                # band_carry_count: tenured names retained via the band (55 <= score < 65).
                "band_carry_count": band_carry_count,
                # band_carry_weight_share: fraction of band book weight from carry names;
                # None when band_weights is empty (degenerate leg with no usable sigmas).
                "band_carry_weight_share": band_carry_weight_share,
                # band_carry_names: the exact carry cohort (sorted) — lets the UI mark
                # carried names without inferring from scores, and the H2 audit read
                # the cohort directly.
                "band_carry_names": sorted(carry_names_in_book),
            }
        )

    nav, _grid_monthly_by_config, _grid_month_labels, _grid_aligned_net, _grid_diagnostics = (
        _assemble_nav(rebalance_picks, prices_by_ticker, data_dir, band_legs_for_nav, grid_legs)
    )

    restate_pct = (
        round(100.0 * len(restate_names) / len(picked_names), 1) if picked_names else None
    )
    # Append conditional non_reliance_filing disclosure based on parquet availability.
    _nr_clause = (
        "non_reliance_filing (8-K Item 4.02) is replayed point-in-time via the "
        "pit_item402_history.parquet — names that filed an Item 4.02 in the trailing "
        "year at a historical rebalance are correctly excluded from the AI-pick basket. "
        if _item402_parquet_present
        else "non_reliance_filing (8-K Item 4.02) is NOT replayed — no 8-K history "
        "parquet was present at backfill time — so a name that filed an Item 4.02 in "
        "the trailing year at a historical rebalance will appear in this backtest un-vetoed. "
    )
    disclaimer = DISCLAIMER_BASE + _nr_clause + _insample_lag_clause(nav, start, end)

    # Phase 7.0c: veto_layer_replayed is True when all six accounting vetoes were
    # included in the replay (non_reliance_filing is deliberately excluded and
    # disclosed in vetoes_not_replayed — this does NOT suppress the True flag).
    # The flag answers: "did the backtest include the accounting veto layer?" = yes.
    payload = {
        "meta": {
            "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "rule_version": RULE_VERSION,
            "as_of_start": start.isoformat(),
            "as_of_end": end.isoformat(),
            "rebalance_count": len(rebalances_out),
            "max_holdings": MAX_PICKS,
            "default_count": DEFAULT_COUNT,
            "default_benchmark": "spy",
            "cost_bps_per_side": DEFAULT_COST_BPS_PER_SIDE,
            "cost_bps_conservative": CONSERVATIVE_COST_BPS,
            "incomplete_membership_count": incomplete_membership,
            # FIX 1 (restatement period-map refinement, 2026-06-13):
            # restatement_contamination_pct is now a TIGHTER upper bound than before.
            # Prior behaviour: ANY post-as-of amendment counted (over-counted amendments
            # for fiscal years never seen by the PIT score at T).
            # Refined behaviour: only amendments whose filing_date falls within
            # 2 calendar years of the PIT 10-K's fiscal year-end are counted.
            # Residual over-count: (a) non-Dec-31 FYE names (ceiling approximate);
            # (b) multi-year restatements filed > 2y after FY-end (missed).
            # Semantics: still an upper bound on contamination; "period-map-gated" = True.
            "restatement_contamination_pct": restate_pct,
            "restatement_canary_source": "edgar-filings-index",
            "restatement_canary_unresolved_count": len(restate_unresolved),
            # period_map_gated=True: amendments are gated to the PIT 10-K's fiscal-year
            # ±2 calendar years (FIX 1). False would indicate the legacy over-counting
            # behaviour (all post-as-of amendments counted regardless of fiscal year).
            "restatement_canary_period_map_gated": True,
            # FIX 2 (ticker-rename micro-leakage disclosure, 2026-06-13):
            # ~15-20 tickers in the backtest window correspond to renamed/merged
            # entities where the ledger's REMOVE-old + ADD-new pair causes members_at
            # to correctly return the historical ticker (e.g. KDP at pre-2018 dates,
            # FB at pre-2022-06 dates). However, the price and fundamentals fetch
            # uses the CURRENT entity's data (yfinance/EDGAR for the new ticker's CIK),
            # which for a pure rename is correct, but for a merger (DPSG→KDP 2018) the
            # pre-merger entity's EDGAR CIK differs from the post-merger one. In
            # practice the impact is limited: the post-merger entity (KDP) has no EDGAR
            # annual-10-K filings before 2018, so the PIT snapshot at a pre-2018
            # rebalance is all-null and KDP scores at a neutral/median composite —
            # it is unlikely to clear the high-conviction gate. The contamination is
            # effectively zero for the scoring output but non-zero for the
            # universe representation. A full fix requires a verified rename-map with
            # per-entity CIK resolution and confirmed pre-rename price history in
            # yfinance — infrastructure not currently available. Tracked for future
            # implementation (see issue text in PHASE_STATUS_INFLIGHT.md).
            # Known affected tickers (estimated; ledger-derived):
            #   KDP (pre-2018-07: was DPSG / Dr Pepper Snapple Group)
            #   META (pre-2022-06: was FB / Facebook Inc.)
            #   DAY (pre-2024-02: was CDAY / Ceridian Dayforce)
            # For FB/META and CDAY/DAY, the post-rename entity IS the same legal CIK
            # (pure symbol change, not a merger), so price + fundamentals are correct.
            # Only merger renames (KDP) carry true micro-leakage — and those score
            # null-fundamentals PIT, limiting the actual selection contamination.
            "ticker_rename_microleakage_note": (
                "Merger-renamed tickers (e.g. KDP pre-2018-07-02) may appear in the "
                "historical cohort via the ledger but score null-fundamentals PIT "
                "(post-merger entity has no pre-merger 10-K filings), limiting "
                "practical selection contamination. Pure symbol-change renames "
                "(FB→META, CDAY→DAY) share the same CIK — no data mismatch. "
                "Full fix requires per-entity CIK resolution + confirmed yfinance "
                "pre-rename price history; tracked as a future issue."
            ),
            # GAP 1: sector_from_today is False when the historical sector parquet is
            # present (PIT sectors used); True when absent (today's Wikipedia sector).
            "sector_from_today": not _sector_parquet_present,
            # Phase 7.0c: veto_layer_replayed=True — six (or seven when item402
            # parquet is present) accounting vetoes are replayed PIT.
            "veto_layer_replayed": True,
            # GAP 2: non_reliance_filing moves from vetoes_not_replayed to vetoes_replayed
            # when the item402 parquet is present.  Computed dynamically so the disclosure
            # is always consistent with what was actually replayed.
            "vetoes_replayed": (
                list(_VETOES_REPLAYED) + ["non_reliance_filing"]
                if _item402_parquet_present
                else list(_VETOES_REPLAYED)
            ),
            "vetoes_not_replayed": (
                []
                if _item402_parquet_present
                else [{"name": v["name"], "reason": v["reason"]} for v in _VETOES_NOT_REPLAYED]
            ),
            # PR-2 (Phase 7): the recommendation/valuation layer is replayed point-in-time
            # AND now DRIVES selection (gate_active=True) — the basket holds only
            # high-conviction names. C1 cleared on PR-1's backfill (median eligible 52 >>
            # default_count). Phase 7.0c replays the accounting vetoes too (see
            # _VETOES_REPLAYED / _VETOES_NOT_REPLAYED above). high_conviction_eligible_median
            # remains the per-rebalance diagnostic (picks = top-N by composite among the
            # eligible set).
            "recommendation_layer_replayed": True,
            "high_conviction_gate_active": gate == "high_conviction",
            "high_conviction_eligible_median": (
                statistics.median(hc_counts) if hc_counts else None
            ),
            "high_conviction_gate": {
                "recommendations": sorted(HIGH_CONVICTION_RECOMMENDATIONS),
                "mos_pct_min_exclusive": 0.0,
                "composite_min": HIGH_CONVICTION_COMPOSITE_MIN,
                "loss_chance_max": HIGH_CONVICTION_LOSS_CHANCE_MAX,
                "hard_stale_days": BACKTEST_HARD_STALE_DAYS,
            },
            # Adaptive-book rule: AI sizes its own basket each rebalance.
            # Hold every HC pick with composite >= composite_min; incumbents are
            # retained while composite >= hold_band_min (V55 hysteresis, ratified
            # 2026-06-11); min_picks floor; max_picks = None (uncapped per the
            # 2026-06-11 uncap ratification — key kept, explicit null, so callers
            # can detect the artifact generation; max_holdings=20 unchanged).
            # methodology-scientist RATIFY 2026-06-11 + RATIFY-WITH-CONDITIONS
            # 2026-06-11 (hold_band_min; C0 strict tenure) +
            # RATIFY-WITH-CONDITIONS (uncap) 2026-06-11 (cap inert 0/40).
            "adaptive_rule": {
                "composite_min": ADAPTIVE_COMPOSITE_MIN,
                "hold_band_min": ADAPTIVE_HOLD_BAND_MIN,
                "min_picks": ADAPTIVE_MIN_PICKS,
                "max_picks": None,  # uncapped per 2026-06-11 ratification
            },
            # Survivorship-bias fix: Rule 18 observability counters.
            # scoring_universe_removed_candidates_count: tickers in the ledger as REMOVE
            #   events on/after ``start`` that are NOT in today's current universe — the
            #   full set of historically-removed names we ATTEMPT to pre-fetch.
            # scoring_universe_removed_fetched_count: subset with usable EDGAR + price data
            #   that actually entered the scoring universe (the win of this fix).
            # scoring_universe_removed_unavailable_count: subset that could not be loaded
            #   (no-CIK / no-prices / fetch-error) and remain absent from scoring
            #   (graceful degradation — same behavior as the pre-fix code, but explicit).
            "scoring_universe_removed_candidates_count": _scoring_universe_removed_candidates_count,
            "scoring_universe_removed_fetched_count": _scoring_universe_removed_fetched_count,
            "scoring_universe_removed_unavailable_count": _scoring_universe_removed_unavailable_count,
            # GAP 2: item402 PIT veto replay observability (Rule 18).
            # item402_pit_rows: number of rows in the item402 parquet (0 = absent).
            # item402_veto_fired_count: number of (ticker, rebalance) pairs where
            #   non_reliance_filing fired PIT (0 when parquet absent).
            "item402_pit_rows": _item402_pit_rows,
            "item402_veto_fired_count": _item402_veto_fired_count,
            # GAP 1: historical sector PIT observability (Rule 18).
            # historical_sector_coverage_pct: fraction of (ticker, rebalance) sector
            #   lookups served by the PIT parquet (0.0 when parquet absent).
            # historical_sector_fallback_count: number of lookups that fell back to
            #   today's Wikipedia sector (equal to total lookups when parquet absent).
            "historical_sector_coverage_pct": (
                round(
                    100.0 * max(0, _historical_sector_lookup_count - _historical_sector_fallback_count)
                    / _historical_sector_lookup_count,
                    1,
                )
                if _historical_sector_lookup_count > 0
                else None
            ),
            "historical_sector_fallback_count": _historical_sector_fallback_count,
            "disclaimer": disclaimer,
        },
        "rebalances": rebalances_out,
        "nav": nav,
    }

    # Phase-A OOS-validation: compute DSR + walk-forward stability on the PRODUCED
    # artifact (no network calls, no artifact regeneration). Emit as meta.validation
    # so future artifact consumers see the inferential gate result inline.
    # Graceful-degradation: a failure here (e.g. degenerate NAV) logs a warning and
    # leaves meta.validation = None rather than killing the backfill (Rule 18).
    validation_block: dict | None = None
    try:
        validation_block = compute_basket_rule_validation(
            payload, n_trials=BASKET_RULE_N_TRIALS
        )
    except Exception as _val_exc:  # noqa: BLE001 — validation failure never kills the backfill
        logger.warning(
            "backfill: compute_basket_rule_validation failed: %s — meta.validation will be null",
            _val_exc,
        )

    # 12-config grid diagnostics, PBO, and purged-embargo holdout.
    # These are DIAGNOSTIC / ANNOTATE-ONLY blocks — they do NOT change selection, ranking,
    # or nav.adaptive. Graceful-degradation: each sub-block fails independently and leaves
    # its key = None rather than killing the backfill (Rule 18 / SKILL.md Rule 16).
    grid_block: dict | None = None
    grid_pbo_block: dict | None = None
    grid_holdout_block: dict | None = None

    if _grid_month_labels and _grid_aligned_net:
        try:
            # Compact grid artifact: one shared month-label list + per-config net arrays.
            # ~10 KB for ~118 months × 12 configs; daily series discarded.
            grid_block = {
                "configs": _GRID_CONFIG_KEYS,
                "freq": "monthly",
                "dates": _grid_month_labels,
                "net": {k: _grid_aligned_net[k] for k in _GRID_CONFIG_KEYS if k in _grid_aligned_net},
            }
        except Exception as _ge:  # noqa: BLE001
            logger.warning("backfill: grid block assembly failed: %s", _ge)

        try:
            grid_pbo_block = compute_grid_pbo(_grid_aligned_net)
        except Exception as _pbo_exc:  # noqa: BLE001
            logger.warning("backfill: compute_grid_pbo failed: %s — pbo block will be null", _pbo_exc)

        try:
            # Extract the benchmark monthly series for the holdout (use SPY if available).
            _bench_series = nav.get("benchmark", {}).get("spy", [])
            _bench_dates = nav.get("dates", [])
            _bench_monthly: list[float | None] = []
            if _bench_series and _bench_dates:
                _, _bench_monthly_vals = _snap_monthly_nav(_bench_series, _bench_dates)
                _bench_monthly = _bench_monthly_vals
            grid_holdout_block = compute_holdout(
                _grid_aligned_net,
                _bench_monthly,
            )
        except Exception as _ho_exc:  # noqa: BLE001
            logger.warning(
                "backfill: compute_holdout failed: %s — holdout block will be null", _ho_exc
            )

    if validation_block is not None:
        validation_block["grid"] = grid_block
        validation_block["pbo"] = grid_pbo_block
        validation_block["holdout"] = grid_holdout_block
        validation_block["grid_diagnostics"] = _grid_diagnostics if _grid_diagnostics else None
    payload["meta"]["validation"] = validation_block

    out = write_backtest_pit_json(payload, data_dir)
    logger.info(
        "backfill wrote %s — %d rebalances, %d incomplete-membership legs, restatement %.1f%%, "
        "validation dsr=%.4f phi=%.6f",
        out,
        len(rebalances_out),
        incomplete_membership,
        restate_pct or 0.0,
        validation_block.get("dsr", float("nan")) if validation_block else float("nan"),
        validation_block.get("dsr_confidence_phi", float("nan")) if validation_block else float("nan"),
    )
    return out


def _snap_to_trading_day(date_iso: str, dates: list[str]) -> str | None:
    """First trading day in ``dates`` on or after ``date_iso`` (decide at T, trade the
    next open); falls back to the last trading day before it if none follows. ``dates``
    is sorted-ascending ISO strings (lexical == chronological). None only if empty."""
    if not dates:
        return None
    i = bisect.bisect_left(dates, date_iso)
    return dates[i] if i < len(dates) else dates[-1]


def _build_price_panel(
    rebalance_picks: list[tuple[str, dict[int, dict[str, float]], int]],
    prices_by_ticker: dict[str, pd.DataFrame],
    extra_leg_sets: list[list[tuple[str, dict[str, float]]]] | None = None,
) -> tuple[dict[str, dict[str, float]], list[str], list[str]]:
    """Build the shared price panel used by both the product NAV path and the grid path.

    Extracts adjusted-close time series from ``prices_by_ticker`` for every ticker
    that appears in ``rebalance_picks`` OR any of ``extra_leg_sets`` (e.g. the 12
    grid leg lists), starting from the first rebalance date. Returns:

    ``(closes, dates, axis)``
      closes — ``{ticker: {date_iso: close}}`` sparse dict
      dates  — sorted list of all trading-day ISO strings in the panel
      axis   — dates from the first snapped rebalance onward (the NAV time axis)

    Computing the panel ONCE and passing it to both ``_assemble_nav`` and
    ``_assemble_grid_navs`` avoids re-walking the (potentially large) price
    DataFrames 12 additional times per call.
    """
    all_held: set[str] = {
        t for _, wbc, _ in rebalance_picks for wmap in wbc.values() for t in wmap
    }
    for leg_list in (extra_leg_sets or []):
        for _, wmap in leg_list:
            all_held.update(wmap)

    held = sorted(all_held)
    if not held or not rebalance_picks:
        return {}, [], []

    start_ts = pd.Timestamp(rebalance_picks[0][0])
    closes: dict[str, dict[str, float]] = {}
    all_dates: set[str] = set()
    for t in held:
        pf = prices_by_ticker.get(t)
        if pf is None:
            continue
        col = "Adj Close" if "Adj Close" in pf.columns else "Close"
        for ts, v in pf.loc[start_ts:, col].items():
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if f == f and f > 0:
                d = ts.strftime("%Y-%m-%d")
                closes.setdefault(t, {})[d] = f
                all_dates.add(d)

    dates = sorted(all_dates)
    if not dates:
        return {}, [], []

    global_start = _snap_to_trading_day(rebalance_picks[0][0], dates)
    axis = [d for d in dates if d >= global_start]
    return closes, dates, axis


def _snap_monthly_nav(
    daily_net: list[float | None],
    daily_dates: list[str],
) -> tuple[list[str], list[float | None]]:
    """Resample a daily NAV series to month-end (last trading day <= calendar month-end).

    Uses an on-or-before discipline (mirrors ``basket_rule_validation._snap_to_trading_day``
    and ``_extract_quarterly_returns`` boundary semantics) — NO look-ahead.

    Parameters
    ----------
    daily_net:
        Daily net NAV values aligned to ``daily_dates``.  May contain leading ``None``
        (padding from the left-pad contract in ``by_count`` / ``adaptive``).
    daily_dates:
        ISO ``YYYY-MM-DD`` strings, sorted ascending.

    Returns
    -------
    (month_labels, month_values)
        ``month_labels`` — one ISO label per month-end (e.g. ``"2016-08"``)
        ``month_values`` — last non-None NAV on or before that calendar month-end
    """
    if not daily_dates or not daily_net:
        return [], []

    # Build (year, month) -> last valid (date, value) mapping.
    month_map: dict[tuple[int, int], tuple[str, float]] = {}
    for d_iso, v in zip(daily_dates, daily_net, strict=False):
        if v is None:
            continue
        year, month = int(d_iso[:4]), int(d_iso[5:7])
        # Keep the latest date within the month (dates are sorted so this is always
        # an overwrite in forward order — the final overwrite wins).
        month_map[(year, month)] = (d_iso, float(v))

    if not month_map:
        return [], []

    month_labels: list[str] = []
    month_values: list[float | None] = []
    for (yr, mo), (_d, val) in sorted(month_map.items()):
        month_labels.append(f"{yr:04d}-{mo:02d}")
        month_values.append(val)

    return month_labels, month_values


def _assemble_grid_navs(
    grid_legs: dict[str, list[tuple[str, dict[str, float]]]],
    closes: dict[str, dict[str, float]],
    dates: list[str],
    axis: list[str],
    expected_leg_count: int,
) -> tuple[dict[str, dict], dict[str, list[str]], dict[str, list[float | None]], dict]:
    """Build monthly net NAV for each of the 12 grid configs from the shared price panel.

    The daily series is computed via ``build_portfolio_nav`` over the shared panel
    (no price re-walk), then resampled to MONTHLY via ``_snap_monthly_nav`` (last
    trading day <= calendar month-end, no look-ahead). The daily series is DISCARDED;
    only monthly data is persisted in the output.

    Returns
    -------
    (monthly_by_config, all_month_labels, monthly_net_by_config, grid_diagnostics)
      monthly_by_config     — ``{key: {net: [...], gross: [...]}}`` (monthly, compact)
      all_month_labels      — union of all month labels (typically ~118 months)
      monthly_net_by_config — ``{key: [float|None]}`` aligned to all_month_labels
      grid_diagnostics      — observability block (per-config leg counts, etc.)
    """
    per_config_leg_counts: dict[str, int] = {}
    configs_with_dropped_legs: list[str] = []
    monthly_by_config: dict[str, dict] = {}
    monthly_net_only: dict[str, list[float | None]] = {}
    all_month_label_set: set[str] = set()

    for g_key, legs in grid_legs.items():
        n_legs = len(legs)
        per_config_leg_counts[g_key] = n_legs
        if n_legs < expected_leg_count:
            configs_with_dropped_legs.append(g_key)

        if not legs or not dates:
            monthly_by_config[g_key] = {"net": [], "gross": []}
            monthly_net_only[g_key] = []
            continue

        # Build daily NAV over the shared panel (no re-walk of prices_by_ticker).
        snapped_legs = [
            (snapped, wmap)
            for d, wmap in legs
            if (snapped := _snap_to_trading_day(d, dates)) is not None
        ]
        if not snapped_legs:
            monthly_by_config[g_key] = {"net": [], "gross": []}
            monthly_net_only[g_key] = []
            continue

        gn = build_portfolio_nav(dates, closes, snapped_legs)

        # Resample to monthly — discard daily, persist only month-end values.
        # The NAV from build_portfolio_nav starts at the first snapped leg date,
        # but the axis may have a prefix of None-padded dates if other configs start
        # later. Align to axis before resampling.
        pad_n = len(axis) - len(gn["dates"])
        padded_net: list[float | None] = [None] * pad_n + gn["net"]
        padded_gross: list[float | None] = [None] * pad_n + gn["gross"]

        m_labels_net, m_vals_net = _snap_monthly_nav(padded_net, axis)
        m_labels_gross, m_vals_gross = _snap_monthly_nav(padded_gross, axis)

        all_month_label_set.update(m_labels_net)
        monthly_by_config[g_key] = {
            "net": m_vals_net,
            "gross": m_vals_gross,
            "month_labels": m_labels_net,
        }
        monthly_net_only[g_key] = m_vals_net

    # Align all configs to the UNION of month labels (some configs may start later
    # if their first leg was dropped; None-pad the prefix for those).
    all_month_labels: list[str] = sorted(all_month_label_set)

    aligned_net: dict[str, list[float | None]] = {}
    for g_key, m_net in monthly_net_only.items():
        cfg_labels = monthly_by_config[g_key].get("month_labels", [])
        if not cfg_labels or not all_month_labels:
            aligned_net[g_key] = [None] * len(all_month_labels)
            continue
        label_to_val: dict[str, float | None] = dict(zip(cfg_labels, m_net, strict=False))
        aligned_net[g_key] = [label_to_val.get(lbl) for lbl in all_month_labels]

    grid_diagnostics: dict = {
        "per_config_leg_counts": per_config_leg_counts,
        "configs_with_dropped_legs": configs_with_dropped_legs,
        "min_leg_count": min(per_config_leg_counts.values()) if per_config_leg_counts else 0,
        "expected_leg_count": expected_leg_count,
    }

    return monthly_by_config, all_month_labels, aligned_net, grid_diagnostics


def _assemble_nav(
    rebalance_picks: list[tuple[str, dict[int, dict[str, float]], int]],
    prices_by_ticker: dict[str, pd.DataFrame],
    data_dir: Path,
    band_legs: list[tuple[str, dict[str, float]]] | None = None,
    grid_legs: dict[str, list[tuple[str, dict[str, float]]]] | None = None,
) -> tuple[dict, dict[str, dict], list[str], dict[str, list[float | None]], dict]:
    """Daily gross/net/conservative NAV for EACH holding count N=1..MAX_PICKS + benchmarks.
    Also computes monthly grid NAVs for the 12-config grid if ``grid_legs`` is provided.

    ``rebalance_picks`` is ``[(as_of_date, {N: {ticker: weight}}, n_adaptive)]``.
    For each count N the matching per-rebalance weight maps become one daily NAV series
    (the legacy 1-20 slider fallback selects the count); ``dates`` + ``benchmark`` are
    shared across all counts (same trading calendar, same rebased index lines).

    ``band_legs`` is ``[(as_of_date, {ticker: weight})]`` — the V55 hysteresis band book
    weights for each rebalance. When provided, the ``"adaptive"`` NAV entry is built from
    these band legs (the ratified product adaptive series); otherwise falls back to the
    old prefix-based ``weights_by_count[n_adaptive]`` path (backward-compatible for tests
    that omit the argument). Same inner shape as a by_count entry; left-padded with None
    when a leg is missing — same contract as by_count.

    ``grid_legs`` is the 12-config band legs dict from the backfill loop. When provided,
    ``_assemble_grid_navs`` is called on the SHARED price panel (no re-walk).

    Returns
    -------
    (nav, monthly_by_config, all_month_labels, aligned_net, grid_diagnostics)
        nav               — the product NAV dict (``dates``, ``by_count``, ``adaptive``,
                           ``benchmark``, ``default_count``)
        monthly_by_config — ``{key: {net, gross, month_labels}}`` for each grid config
        all_month_labels  — union of month label strings (~118 entries)
        aligned_net       — ``{key: [float|None]}`` aligned to ``all_month_labels``
        grid_diagnostics  — observability block from ``_assemble_grid_navs``

    Backward-compat note: callers that do not use the grid return value (``_assemble_nav``
    called without ``grid_legs``) receive empty dicts/lists for the grid outputs.
    """
    empty_nav = {
        "dates": [],
        "benchmark": {},
        "by_count": {},
        "adaptive": {},
        "default_count": DEFAULT_COUNT,
    }
    empty_grid: tuple = ({}, [], {}, {})
    if not rebalance_picks:
        return empty_nav, *empty_grid

    # Build the shared price panel ONCE — used for both product NAV and grid NAVs.
    closes, dates, axis = _build_price_panel(
        rebalance_picks,
        prices_by_ticker,
        extra_leg_sets=list(grid_legs.values()) if grid_legs else None,
    )
    if not dates:
        return empty_nav, *empty_grid

    by_count: dict[str, dict] = {}
    for n in range(1, MAX_PICKS + 1):
        legs = [
            (snapped, wbc[n])
            for d, wbc, _ in rebalance_picks
            if n in wbc and (snapped := _snap_to_trading_day(d, dates)) is not None
        ]
        if not legs:
            continue
        gn = build_portfolio_nav(dates, closes, legs)
        cons = build_portfolio_nav(
            dates, closes, legs, cost_bps_per_side=CONSERVATIVE_COST_BPS
        )
        pad: list[float | None] = [None] * (len(axis) - len(gn["dates"]))
        by_count[str(n)] = {
            "gross": pad + gn["gross"],
            "net": pad + gn["net"],
            "net_conservative": pad + cons["net"],
            "turnover_by_rebalance": gn["turnover_by_rebalance"],
        }

    # Adaptive NAV: V55 hysteresis band legs when provided (the ratified product adaptive
    # series); falls back to the old prefix-based weights_by_count[n_adaptive] path for
    # backward compatibility with tests that pre-date the band (no band_legs argument).
    # Skip a leg when the snapped date cannot be resolved (the skip keeps the series honest).
    if band_legs:
        adaptive_legs = [
            (snapped, wmap)
            for d, wmap in band_legs
            if (snapped := _snap_to_trading_day(d, dates)) is not None
        ]
    else:
        # Legacy fallback: prefix-based adaptive (no tenure state, n_adaptive count).
        adaptive_legs = [
            (snapped, wbc[n_adp])
            for d, wbc, n_adp in rebalance_picks
            if n_adp in wbc and (snapped := _snap_to_trading_day(d, dates)) is not None
        ]
    adaptive: dict = {}
    if adaptive_legs:
        gn_adp = build_portfolio_nav(dates, closes, adaptive_legs)
        cons_adp = build_portfolio_nav(
            dates, closes, adaptive_legs, cost_bps_per_side=CONSERVATIVE_COST_BPS
        )
        pad_adp: list[float | None] = [None] * (len(axis) - len(gn_adp["dates"]))
        adaptive = {
            "gross": pad_adp + gn_adp["gross"],
            "net": pad_adp + gn_adp["net"],
            "net_conservative": pad_adp + cons_adp["net"],
            "turnover_by_rebalance": gn_adp["turnover_by_rebalance"],
        }

    nav = {
        "dates": axis,
        "benchmark": _benchmark_navs(axis, data_dir),
        "by_count": by_count,
        "adaptive": adaptive,
        "default_count": DEFAULT_COUNT,
    }

    # 12-config grid NAVs — computed over the SHARED panel (no re-walk).
    monthly_by_config: dict[str, dict] = {}
    all_month_labels: list[str] = []
    aligned_net: dict[str, list[float | None]] = {}
    grid_diagnostics: dict = {}
    if grid_legs:
        expected_legs = len(rebalance_picks)
        monthly_by_config, all_month_labels, aligned_net, grid_diagnostics = _assemble_grid_navs(
            grid_legs, closes, dates, axis, expected_leg_count=expected_legs
        )

    return nav, monthly_by_config, all_month_labels, aligned_net, grid_diagnostics


def _benchmark_navs(portfolio_dates: list[str], data_dir: Path) -> dict[str, list]:
    """Rebased benchmark NAVs aligned to the portfolio dates, from benchmarks.json."""
    import json

    out: dict[str, list] = {}
    path = data_dir / BENCHMARKS_JSON
    if not portfolio_dates or not path.exists():
        return out
    try:
        bench = json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        logger.warning("backfill: could not read %s: %s", path, e)
        return out
    bench_dates = bench.get("dates", [])
    for sym in ("spy", "qqq", "dia", "iwm"):
        closes = bench.get(sym)
        if closes:
            out[sym] = align_benchmark_nav(portfolio_dates, bench_dates, closes)
    return out


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Phase 7.0 point-in-time portfolio backtest backfill")
    today = datetime.now(UTC).date()
    # The default start is BACKTEST_CANONICAL_START (2016-06-01), not a rolling
    # ``today - 10y``.  A rolling default caused the artifact's window to advance
    # one day per run: around Aug 2026 the canonical first rebalance (2016-08-14)
    # would have silently dropped off the left edge.  The fixed constant keeps the
    # rebalance count, NAV, and band-tenure history stable across every cron run.
    # Survivorship ledger covers 2016+ (historical_universe.EARLIEST_EVENT_DATE =
    # 2016-01); ~15-20 tickers renamed before ~2021 (e.g. CDAY→DAY) are missing
    # pre-rename legs.  The FIRST (cold) backfill must still run via the manual
    # backfill-portfolio.yml dispatch: cold runtime (~60-85m) exceeds the cron's
    # 55m folded-step cap (bumped 2026-06-08); warm steady-state ~35-45m fits.
    parser.add_argument("--start", default=BACKTEST_CANONICAL_START.isoformat())
    parser.add_argument("--end", default=today.isoformat())
    args = parser.parse_args(argv)
    run_backfill(date.fromisoformat(args.start), date.fromisoformat(args.end))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
