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
from compute.ingest.historical_universe import _ACTION_REMOVE, list_known_events, members_at
from compute.ingest.prices import fetch_prices
from compute.ingest.universe import get_sp500_constituents

# Reuse the LIVE cross-sectional valuation-input builders (private, but pure) so the
# PIT proxy's MoS/recommendation match the forward rule exactly. Importing them keeps
# compute/main.py untouched for PR-1 (methodology-scientist: no live main.py change
# until PR-3); a future refactor could extract them to a shared module.
from compute.main import (
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
from compute.scoring.loss_chance import derive_loss_chance
from compute.scoring.pillars import TickerInputs, compute_all_pillars
from compute.scoring.recommendation import derive_recommendation
from compute.scoring.restatement_filings import fetch_amendments
from compute.scoring.risk_overlay import compute_risk_flags
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
    "non_reliance_filing (8-K Item 4.02) is NOT replayed — no 8-K history is "
    "available in the loaded PIT data — so a name that filed an Item 4.02 in the "
    "trailing year at a historical rebalance will appear in this backtest un-vetoed. "
    "Net figures charge a modeled per-side spread cost (10-25 bps on turnover) but "
    "are gross of additional market-impact slippage; per McLean-Pontiff (2016) "
    "published-factor edges decay ~32% post-publication. "
    "The adaptive AI-pick book sizes itself each rebalance: it holds ALL "
    "high-conviction picks with composite score >= 65 (no ceiling), with a floor of "
    "5 names, so holding count varies by quarter (uncap ratified 2026-06-11 — "
    "in-sample max book 16 over 40 rebalances; the former cap never bound fresh "
    "entries (max raw 13) and its carry-leg rank-slice exit was removed as the "
    "V55.0 -> V55.1 protocol amendment; A2-S spike tripwire: raw >= 25 in a single "
    "rebalance triggers reopening, registered #130; forward acceptance gates "
    "pre-registered). Incumbents are retained while scoring "
    ">= 55 to reduce turnover (V55 hysteresis band ratified 2026-06-11; the band is "
    "a turnover/implementation-cost device — no performance claims)."
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


def _restatement_at_risk(amendments: list[dict] | None, as_of: str) -> bool:
    """True if the name filed ANY 10-K/A or 10-Q/A AFTER ``as_of``.

    Re-sourced (methodology-scientist 2026-06-05) from the SAME EDGAR filings-index
    feed the live ``restatement_history`` flag uses (``fetch_amendments`` →
    ``company.get_filings``), NOT the companyfacts-XBRL annual-fact scan it used
    before — that scan only saw amendments that re-filed a pulled annual XBRL concept,
    so it systematically under-counted partial / non-financial amendments and reported
    a misleading 0.0%. This is a CONSERVATIVE look-ahead-contamination canary: a
    post-as-of amendment means the cached companyfacts data the backtest read at T may
    silently reflect that later restatement. It does NOT restrict to the specific
    fiscal years that fed the as-of score (the filings index carries no period map), so
    it over- rather than under-counts — the safe direction for a disclosed canary.
    ``None`` (fetch failed / no EDGAR identity) is treated as "unresolved", NOT at-risk
    (the caller counts those separately).
    """
    if not amendments:
        return False
    for f in amendments:
        fd = f.get("filing_date")
        if isinstance(fd, str) and fd > as_of:
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

    States how the DEFAULT-count NET line actually did vs SPY in-sample, computed from
    the produced NAV so the disclaimer can never claim a win the chart contradicts
    (methodology-scientist 2026-06-05). Falls back to a generic caveat if either series
    is unavailable.
    """
    series = nav.get("by_count", {}).get(str(DEFAULT_COUNT), {})
    net = series.get("net") or []
    spy = nav.get("benchmark", {}).get("spy") or []
    p = next((v for v in reversed(net) if v is not None), None)
    s = next((v for v in reversed(spy) if v is not None), None)
    if p is None or s is None:
        return (
            " Past performance, even favorable, does not predict future results; read the"
            " full holding-count ladder, not any single line."
        )
    verb = "underperformed" if p < s - 0.5 else "outperformed" if p > s + 0.5 else "tracked"
    return (
        f" In this {start.year}-{end.year} sample the default {DEFAULT_COUNT}-holding net"
        f" line {verb} the S&P 500 ({p:.0f} vs {s:.0f}, both rebased to 100 at the start):"
        f" a factor-tilted, sector-CONCENTRATED book (no per-sector cap — it can hold many"
        f" names in one sector) carries higher single-sector risk and can diverge from a"
        f" cap-weighted index, in either direction, for long stretches. Any in-sample edge"
        f" is concentration- and regime-driven, not a free lunch (McLean-Pontiff 2016) —"
        f" past performance, even favorable, does not predict future results; read the full"
        f" 1-{MAX_PICKS} holding-count ladder, not any single line."
    )


def _compute_pit_risk_flags(
    snapshots: dict[str, FundamentalsSnapshot | None],
    pit_histories: dict[str, pd.DataFrame | None],
    sectors: dict[str, str],
    rebalance_date: date,
    beneish_scores: dict[str, float | None],
    dechow_scores: dict[str, float | None],
) -> dict[str, list[str]]:
    """Compute the six accounting-based active vetoes against the PIT cross-section.

    This is a SUBSET of ``compute_risk_flags`` — non_reliance_filing is excluded
    (no 8-K history in the PIT data). Sloan + NSI cross-sections are computed against
    the live cohort AT THIS REBALANCE, not today's universe, so the within-sector
    decile thresholds are PIT-correct.

    ``beneish_scores`` and ``dechow_scores`` are pre-computed per-ticker before calling
    this function (to avoid recomputing inside compute_risk_flags which doesn't call
    those scorers directly — it only applies thresholds via the inject paths).
    """
    return compute_risk_flags(
        snapshots=snapshots,
        histories={t: h for t, h in pit_histories.items() if h is not None},
        sectors=sectors,
        today=rebalance_date,  # PIT: NSI lookback anchors to T, not today
        non_reliance_by_ticker={t: False for t in snapshots},  # excluded; all False
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


def _adaptive_count(scores: list[float], available_counts: list[int]) -> tuple[int, int]:
    """``(raw, final)`` adaptive-book counts for one rebalance.

    ``raw`` = #{score >= ADAPTIVE_COMPOSITE_MIN} in the FULL deduped eligible pool
    (all scores passed in, INCLUSIVE boundary — a pick scoring exactly 65.0 is in
    the book). Post-uncap (2026-06-11), ``scores`` covers the full ``full_order``
    list (not just ``picks[:MAX_PICKS]``), so ``raw`` is the uncensored pool size.
    The A1/A2/A2-S acceptance gates read this raw count.

    ``final`` (LEGACY / analytics only) = raw floored at
    ``min(ADAPTIVE_MIN_PICKS, len(scores))``, then clamped to the largest available
    weights count <= it — falling back to the smallest available when none is (the
    sigma-coverage degradation path; gate A1 monitors the final count for exactly
    this reason). ``final`` keys into ``weights_by_count`` for the per-count ladder
    and is retained for the per-rebalance ``adaptive_count`` export (analytics), but
    it is NOT the authoritative book size. ``band_held_count`` is the authoritative
    band-book size (uncapped). C2 test pin:
    tests/test_portfolio/test_backfill_integration.py.
    """
    raw = sum(1 for s in scores if s >= ADAPTIVE_COMPOSITE_MIN)
    final = max(raw, min(ADAPTIVE_MIN_PICKS, len(scores)))
    avail = sorted(available_counts)
    if avail:
        final = max((c for c in avail if c <= final), default=avail[0])
    return raw, final


def _band_book(
    order: list[str],
    scores: dict[str, float],
    tenure: set[str],
) -> tuple[list[str], set[str], int]:
    """Pure hysteresis-hold-band book builder (C2 unit-testability gate).

    Post-uncap (2026-06-11): the ``MAX_PICKS`` ceiling on ``core`` is REMOVED.
    ``order`` may contain > MAX_PICKS names (the caller passes ``full_order`` from
    the uncapped ``select_picks(count=None)`` call), and the band book may grow
    beyond MAX_PICKS when many incumbents score >= 65 or there are many fresh
    entrants. Cap removed per the 2026-06-11 uncap ratification; floor logic
    unchanged: pads to ``min(ADAPTIVE_MIN_PICKS, len(order))``.

    ``order``   — HC-eligible tickers sorted composite-desc (output of
                  ``select_picks(count=None)``; the caller's HC gate is the sole
                  eligibility filter — ``_band_book`` does not re-check veto flags).
    ``scores``  — composite score for each ticker (at minimum covers every ticker
                  in ``order``; extra keys are silently ignored).
    ``tenure``  — set of tickers that entered the book via >= ``ADAPTIVE_COMPOSITE_MIN``
                  in a prior rebalance; empty on the first rebalance (band inert).

    Returns ``(book, next_tenure, carry_count)`` where:
      ``book``        — ordered list of selected tickers (composite-desc, alpha-asc tiebreak);
      ``next_tenure`` — tenure set to carry forward (= set(core), pads excluded — C0);
      ``carry_count`` — # tenured names retained via the band (score in [55, 65));
                        first rebalance always returns 0.

    Semantics (C0 strict tenure):
      carries  = tenured ∩ eligible with composite >= ``ADAPTIVE_HOLD_BAND_MIN``
                 (55 <= score; the >= 65 entry requirement was met in a prior rebalance).
      fresh    = eligible with composite >= ``ADAPTIVE_COMPOSITE_MIN`` (>= 65)
                 that are NOT already counted as carries.
      core     = sorted(carries ∪ fresh) by (-composite, ticker).
                 (NO MAX_PICKS cap — uncapped per 2026-06-11 ratification.)
      pads     = top non-core eligible names to reach
                 ``min(ADAPTIVE_MIN_PICKS, len(order))``; pads get NO tenure.
      book     = sorted(core + pads) by (-composite, ticker).
      next_tenure = set(core) (not pads — C0).
      carry_count = #{t in core : t in tenure AND score < ADAPTIVE_COMPOSITE_MIN}
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
        if t not in carry_set and scores.get(t, 0.0) >= ADAPTIVE_COMPOSITE_MIN
    ]

    # Core: union of carries + fresh, sorted by (-score, ticker).
    # NO MAX_PICKS cap — uncapped per the 2026-06-11 uncap ratification.
    core_unsorted = carries + [t for t in fresh if t not in carry_set]
    core: list[str] = sorted(
        core_unsorted,
        key=lambda t: (-scores.get(t, 0.0), t),
    )
    core_set = set(core)

    # Pads: top non-core eligible names to reach ADAPTIVE_MIN_PICKS (or available count).
    target = min(ADAPTIVE_MIN_PICKS, len(order))
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
    # the reason they are in the book — fresh entrants >= 65 are NOT carry-band names).
    carry_count: int = sum(
        1 for t in core
        if t in tenure and scores.get(t, 0.0) < ADAPTIVE_COMPOSITE_MIN
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
                sector=sector_by_ticker.get(ticker, "Unknown"),
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

        pit_risk_flags = _compute_pit_risk_flags(
            snapshots=snaps_by_ticker,
            pit_histories={t: inp.history for t, inp in inputs.items()},
            sectors={t: inp.sector for t, inp in inputs.items()},
            rebalance_date=T,
            beneish_scores=beneish_scores,
            dechow_scores=dechow_scores,
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

        # Contamination canary tracks the FULL selectable set (top-MAX_PICKS) — any of
        # these names can surface once the user slides the count up. A name whose
        # amendment fetch failed is "unresolved" (counted separately), not at-risk.
        # Post-uncap the product band book can hold rank-21+ names outside `picks`;
        # the contamination canary must see every holdable name, not just the top-20.
        picked_names.update(set(picks) | set(band_book))
        for t in sorted(set(picks) | set(band_book)):
            amends = _amendments(t)
            if amends is None:
                restate_unresolved.add(t)
            elif _restatement_at_risk(amends, T_iso):
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

    nav = _assemble_nav(rebalance_picks, prices_by_ticker, data_dir, band_legs_for_nav)

    restate_pct = (
        round(100.0 * len(restate_names) / len(picked_names), 1) if picked_names else None
    )
    disclaimer = DISCLAIMER_BASE + _insample_lag_clause(nav, start, end)

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
            "restatement_contamination_pct": restate_pct,
            "restatement_canary_source": "edgar-filings-index",
            "restatement_canary_unresolved_count": len(restate_unresolved),
            "sector_from_today": True,
            # Phase 7.0c: veto_layer_replayed=True — six of seven accounting vetoes
            # are replayed point-in-time from PIT snapshot + history. The one
            # excluded veto (non_reliance_filing) is disclosed in vetoes_not_replayed.
            "veto_layer_replayed": True,
            "vetoes_replayed": list(_VETOES_REPLAYED),
            "vetoes_not_replayed": [
                {"name": v["name"], "reason": v["reason"]}
                for v in _VETOES_NOT_REPLAYED
            ],
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
            "disclaimer": disclaimer,
        },
        "rebalances": rebalances_out,
        "nav": nav,
    }
    out = write_backtest_pit_json(payload, data_dir)
    logger.info(
        "backfill wrote %s — %d rebalances, %d incomplete-membership legs, restatement %.1f%%",
        out, len(rebalances_out), incomplete_membership, restate_pct or 0.0,
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


def _assemble_nav(
    rebalance_picks: list[tuple[str, dict[int, dict[str, float]], int]],
    prices_by_ticker: dict[str, pd.DataFrame],
    data_dir: Path,
    band_legs: list[tuple[str, dict[str, float]]] | None = None,
) -> dict:
    """Daily gross/net/conservative NAV for EACH holding count N=1..MAX_PICKS + benchmarks.

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
    """
    empty = {
        "dates": [],
        "benchmark": {},
        "by_count": {},
        "adaptive": {},
        "default_count": DEFAULT_COUNT,
    }
    if not rebalance_picks:
        return empty

    # Collect all tickers from both prefix-count legs AND band legs so their price
    # series are loaded once; band tickers may not be in the prefix-count universe
    # when the band book diverges from the simple prefix.
    held = sorted(
        {t for _, wbc, _ in rebalance_picks for wmap in wbc.values() for t in wmap}
        | {t for _, wmap in (band_legs or []) for t in wmap}
    )
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
        return empty

    # Snap each calendar rebalance (quarter-end + 45d — may land on a weekend) to the
    # first trading day on/after it, so every leg fires on a real price date. The axis
    # = every trading day from the earliest snapped rebalance; each count's NAV is a
    # suffix of it, so a count first selectable at a LATER rebalance is left-padded with
    # None (the same gap contract the benchmark line uses). In a full-universe run every
    # count is present from the first rebalance and no padding occurs.
    global_start = _snap_to_trading_day(rebalance_picks[0][0], dates)
    axis = [d for d in dates if d >= global_start]

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

    return {
        "dates": axis,
        "benchmark": _benchmark_navs(axis, data_dir),
        "by_count": by_count,
        "adaptive": adaptive,
        "default_count": DEFAULT_COUNT,
    }


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
