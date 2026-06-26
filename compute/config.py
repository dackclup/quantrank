"""Project paths and defaults. No env vars in code — secrets come from CI."""

from __future__ import annotations

import datetime
from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
FRONTEND_DIR: Path = PROJECT_ROOT / "frontend"
DATA_DIR: Path = FRONTEND_DIR / "public" / "data"
STOCKS_DIR: Path = DATA_DIR / "stocks"
CACHE_DIR: Path = PROJECT_ROOT / "compute" / "cache"
# Research warehouse: point-in-time Parquet snapshots (NOT under frontend/public —
# research data must NOT ship in the static site deploy). Written each cron run;
# never blocks the cron (wrapped in try/except at the main.py call site).
# Layout: data/warehouse/snapshots/year=<YYYY>/run_date=<ISO>/part-0.parquet
#         data/warehouse/_manifest.parquet
WAREHOUSE_DIR: Path = PROJECT_ROOT / "data" / "warehouse"
# Universe constituents file. The `-v2` suffix bumped 2026-05-14 in
# PR 4c.3 after PR #63 (Wikipedia name normalize) — pre-v2 cached
# parquets store un-normalized names like "Hartford (The)" /
# "Lilly (Eli)" because they were written before the `_normalize_
# company_name` helper landed. The 7-day filename freshness check in
# `compute/ingest/universe.py::get_sp500_constituents` would keep
# returning the stale parquet for up to a week. Bumping the filename
# (not the workflow cache key) is a surgical refresh — the other 6
# caches stay warm, only universe re-fetches Wikipedia (~2 sec).
# Bump to `-v3` if another universe ingest change lands (column
# rename, TICKER_OVERRIDES additions that touch existing rows, etc.).
UNIVERSE_CACHE: Path = CACHE_DIR / "universe-v2.parquet"
PRICES_CACHE_DIR: Path = CACHE_DIR / "prices"
FUNDAMENTALS_CACHE_DIR: Path = CACHE_DIR / "fundamentals"
FUNDAMENTALS_HISTORY_CACHE_DIR: Path = CACHE_DIR / "fundamentals_history"
MODELS_DIR: Path = PROJECT_ROOT / "models"

UNIVERSE: str = "SP500"
# Phase 8 pilot — universe selector (default "sp500" for local runs + tests;
# the cron sets QR_UNIVERSE=sp900 via workflow env-var since Phase B flip).
# When set to "sp1500" (Slice 2, manual dispatch only), main.py loads SP1500
# (sp500 + sp400 + sp600) and runs the smallcap coverage probe (Rule 18
# observability-first). NO cron/workflow change in Slice 2.
# Accepted values: "sp500" | "sp900" | "sp1500".
QR_UNIVERSE: str = __import__("os").environ.get("QR_UNIVERSE", "sp500").lower()

# 0.10.20-phase4.6 (issue #75 §3) layers the additive
# ``Metadata.decay_report_url`` on top of 0.10.19-phase8pilot (#479's S&P 900
# cohort diagnostics) — the next monotonic patch after #479 took 0.10.19.
# 0.10.23-phase8pilot — additive ``index_memberships: list[str]`` on
# ``StockSummary`` + ``StockDetail`` for Dow 30 / NDX 100 overlap tabs.
# ``index_membership`` (singular) is kept unchanged — MidcapChip + the
# membership-ledger script depend on it as the sp500/sp400 partition.
SCHEMA_VERSION: str = "0.10.40-phase8pilot"

# 10y so the AI-pick backtest's "Max" chart spans a full decade (2016+, the
# survivorship-ledger floor). The weekly compute only consumes ~1y (momentum + NSI
# lookback), so the extra history is cache overhead, not extra compute. NOTE: the
# price + fundamentals_history caches are PERIOD-BLIND, so changing this REQUIRES a
# workflow cache-key bump (cache-vN-fast) to invalidate the stale 5y parquets —
# otherwise a warm run silently returns the old 5y data.
PRICES_PERIOD: str = "10y"

# Provenance: STRUCTURAL — equals BACKTEST_CANONICAL_START (2016-06-01) minus
# _SIGMA_LOOKBACK_BUFFER_DAYS (185) so the first PIT rebalance's (2016-08-14)
# sigma window is fully populated in the shared price cache. Replaces the rolling
# period='10y' anchor so the live compute's daily re-download serves the same depth
# the backfill's min_start floor needs — eliminating the per-run sequential
# max-refetch (+5-15 min vs the 55m folded-step cap) AND fixing the
# benchmarks.json late-rebase cliff (align_benchmark_nav never rebases
# QQQ/DIA/IWM after the portfolio start). Growth: ~+252 rows/year (~+5.4%
# today); revisit if the window exceeds ~15y (≈2031) or prices/ cache > 200 MB.
# Changing this constant requires a cache-vN-fast bump + methodology confirmation
# the backtest window is unchanged.
#
# Consistency note: scripts/backfill_portfolio_pit.py independently derives its
# own price floor as BACKTEST_CANONICAL_START - _SIGMA_LOOKBACK_BUFFER_DAYS =
# date(2016, 6, 1) - timedelta(days=185) = date(2015, 11, 29) — the same date
# as this constant. The scripts layer may NOT import compute.config (layering:
# scripts may import compute, never the reverse), so the equality is maintained
# by derivation rather than shared reference. Do not introduce a circular import.
PRICES_FETCH_START: datetime.date = datetime.date(2015, 11, 29)
MAX_PARALLEL_FETCHES: int = 10
# Bumped from 5 to 8 (PR-3d quick wins). SEC EDGAR fair-access policy
# documents a 10 req/s ceiling per IP. With ~5-10s per snapshot HTTP
# call after the PR-3d tenacity tightening, 8 workers sustain ~1
# req/s — comfortably under the 10/s ceiling, while ~60% more
# throughput than the prior 5. Monitor
# Metadata.fundamentals_latency_p95_seconds — a sustained p95 > 15s
# on a healthy SEC run means we're triggering rate-limit responses
# and should drop back to 5 or 6.
EDGAR_MAX_WORKERS: int = 8
UNIVERSE_CACHE_MAX_AGE_DAYS: int = 7
# SP400 universe re-fetch cadence. 7 days matches the SP500 cache so both
# constituent lists refresh on the same weekly schedule.
SP400_CACHE_MAX_AGE_DAYS: int = 7
PRICES_CACHE_MAX_AGE_HOURS: int = 24
# Prices data-recency floor — the authoritative freshness gate on GitHub Actions.
# On GHA runners, ``actions/cache`` restore resets every restored file's mtime to
# "now", so the mtime-based ``PRICES_CACHE_MAX_AGE_HOURS`` check never fires for
# stale DATA (the mtime is always fresh after a cache restore).  This constant
# closes that gap: if the cached frame's LAST BAR DATE is older than this many
# calendar days, the cache is treated as stale and a live refetch is triggered
# regardless of the file's mtime.  7 days covers the Fri→Mon weekend gap plus a
# single-day holiday extension.  For a cache entry whose last bar IS recent
# (calendar_days_stale <= 7), behaviour is byte-identical to the pre-fix path.
# See compute/ingest/prices.fetch_prices for the guard implementation.
# Rationale mirrors fundamentals Design B (config.py lines 91-104): the mtime-based
# gate is dead on GHA frozen caches; data-content checking is the real gate.
PRICES_CACHE_MAX_STALE_DAYS: int = 7
FUNDAMENTALS_REFETCH_DAYS: int = 45
# Issue #471 / #15 — Design B filing-date precheck (replaces Design C mtime gate).
# Design C used the parquet's st_mtime to decide whether to skip _build_snapshot —
# but the cron's fast cache uses an EXACT quarter key
# (cache-v8-fast-<quarter>-<os>), so on a cache hit actions/cache SKIPS the
# post-job save (immutability).  The fast cache is FROZEN within a quarter, so a
# restored parquet's mtime is the last reseed time (often weeks old) and the
# mtime gate never fired for the stale tickers it was meant to help.  Under the
# frozen cache the "wasteful" refetch is also load-bearing for output freshness —
# a plain serve-cache design causes real staleness.
# Design B avoids all of this: for a stale-but-cached ticker, a CHEAP
# get_filings("10-K"/"10-Q") call re-verifies the latest SEC filing date each run
# and skips _build_snapshot only when no new filing exists.  This reuses the
# Company construction the refetch path already pays and skips only the heavy
# get_facts() pull.  No day constant needed: the precheck queries SEC directly.
# See compute/ingest/fundamentals._latest_filing_date + fetch_fundamentals.
MIN_VALID_TICKERS: int = 100
MIN_FUNDAMENTALS_COVERAGE: float = 0.5

# Issue #34: per-sector pillar-median overlay floor. Sectors with fewer
# than this many peers in the universe skip the overlay entirely — a
# 5-stock median notch on the pillar bars is noisier than no notch at
# all. S&P 500's smallest sector (Energy, n=21) sits comfortably above.
# Phase 8 universe expansion may surface sub-buckets that fail the
# floor; those simply emit pillar_baseline=null.
PILLAR_BASELINE_MIN_PEERS: int = 10

WIKIPEDIA_SP500_URL: str = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
# Phase 8 pilot — S&P 400 Wikipedia URL + on-disk parquet cache. The
# cache sits next to the SP500 universe cache under compute/cache/;
# filename suffix `-v1` follows the universe-v2 bump convention (bump if
# column set or normalization changes). ADRs are NOT in the S&P 400
# (domestic mid-cap index) so no 20-F/6-K handling needed.
WIKIPEDIA_SP400_URL: str = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
SP400_UNIVERSE_CACHE: Path = CACHE_DIR / "universe_sp400-v1.parquet"
# SP900 = SP500 ∪ SP400 combined universe cache (de-duped, cohort column).
SP900_UNIVERSE_CACHE: Path = CACHE_DIR / "universe_sp900-v1.parquet"
# S&P 1500 cutover — Slice 1 scout (no main.py wiring yet).
# SP600 = small-cap index; SP1500 = SP500 ∪ SP400 ∪ SP600 (de-duped, cohort column).
# Cache filename suffix `-v1` follows the universe-v2 bump convention
# (bump if column set or normalisation changes). 7-day TTL matches SP500/SP400 cadence.
WIKIPEDIA_SP600_URL: str = "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies"
SP600_UNIVERSE_CACHE: Path = CACHE_DIR / "universe_sp600-v1.parquet"
SP1500_UNIVERSE_CACHE: Path = CACHE_DIR / "universe_sp1500-v1.parquet"
# SP600 universe re-fetch cadence. 7 days matches the SP500/SP400 cache so all
# constituent lists refresh on the same weekly schedule.
SP600_CACHE_MAX_AGE_DAYS: int = 7
# Multi-index membership — Dow 30 + NASDAQ 100 overlap tabs (0.10.23-phase8pilot).
# Wikipedia pages for Dow Jones Industrial Average + Nasdaq-100 components.
# 7-day TTL matches the SP500/SP400 cache cadence.
WIKIPEDIA_DOW_URL: str = "https://en.wikipedia.org/wiki/Dow_Jones_Industrial_Average"
WIKIPEDIA_NDX_URL: str = "https://en.wikipedia.org/wiki/Nasdaq-100"
DOW30_UNIVERSE_CACHE: Path = CACHE_DIR / "universe_dow30-v1.json"
NDX_UNIVERSE_CACHE: Path = CACHE_DIR / "universe_ndx-v1.json"
DOW30_CACHE_MAX_AGE_DAYS: int = 7
NDX_CACHE_MAX_AGE_DAYS: int = 7
# Sanity bands: reject obviously-broken scrapes.
DOW30_EXPECTED_COUNT: int = 30  # Dow is always exactly 30 components
NDX_MIN_COUNT: int = 95
NDX_MAX_COUNT: int = 105
HTTP_USER_AGENT: str = "QuantRank/0.3 (+https://github.com/dackclup/quantrank)"

# --- Phase 3c: fair price ensemble + Tier-1 defense constants ---
# Anchored in WORKFLOW.md "PR 3c — Tier-1 Defense Layer" and
# docs/RESEARCH_FINDINGS.md "Defense Playbook §PR 3c".

# DCF (Damodaran practitioner defaults; revisited per-sector in Phase 7).
DISCOUNT_RATE: float = 0.10  # WACC proxy for non-Financial/non-Utility S&P 500
TERMINAL_GROWTH: float = 0.03  # long-run nominal GDP cap (Damodaran)
COST_OF_EQUITY: float = 0.10  # used by RIM (Cost of Equity ≈ WACC for S&P 500 cash-flat names)

# Issue #67 — sector-adjusted cost of equity (Damodaran 2019 Ch. 8.4 +
# NYU January 2025 betas dataset; 11 GICS sectors with Ke range 6%-12%).
#
# When ``True``, ``compute.valuation.ensemble.compute_fair_price_ensemble``
# uses the per-GICS-Sector Ke from
# ``compute.scoring.cost_of_equity.get_cost_of_equity`` instead of the
# flat ``COST_OF_EQUITY = 0.10``.
#
# FLIPPED True 2026-05-28 per methodology-scientist Mode B verdict +
# cron #69 empirical confirmation (`value_trap_risk_count_without_sector_coe`
# 132 → `_with_sector_coe` 109 = 17.4% reduction, absolute landing
# inside the original PR #204 target band [80, 110]). The 38%-vs-17%
# spread vs the original PR #204 projection is explained by PR #166's
# RIM equity-denominator fix (Issue #11 closure) already removing ~44
# false positives from the pre-PR-#204 ~176 baseline — the
# proportional difference is baseline drift, not signal failure.
#
# The flat-CoE counter ``Metadata.value_trap_risk_count_without_sector_coe``
# remains in production Metadata as the comparison baseline; do NOT
# remove it without a separate methodology-scientist verdict. Flipping
# BACK to False also requires a methodology-scientist Mode B verdict —
# this is now a load-bearing default, not a feature toggle.
USE_SECTOR_COE: bool = True

DCF_FORECAST_YEARS: int = 5
DCF_FCF_WINDOW_YEARS: int = 5  # trailing window for FCF base estimation
RIM_FORECAST_YEARS: int = 5  # explicit RIM residual-income forecast horizon

# Stale-filing guards (10-Q deadline 45d; 75d past = unusual, missed = restatement risk).
FILING_STALE_SOFT_DAYS: int = 120
FILING_STALE_HARD_DAYS: int = 180

# Tangible-book "goodwill heavy" threshold: TBVPS / BVPS_reported < 0.5 → annotate.
GOODWILL_HEAVY_RATIO: float = 0.5

# Multi-method outlier guard: exclude estimates outside [0.2×, 5×] current price from MAX
# (still in MEDIAN — robust to one outlier per RESEARCH §V-4).
EXTREME_ESTIMATE_HIGH: float = 5.0
EXTREME_ESTIMATE_LOW: float = 0.2

# Issue #177 (0.9.7-phase4h.7) — Defense #4 majority annotate threshold.
# The ensemble's median is a 50% trimmed estimator over 6 methods, so it
# tolerates ⌊5/2⌋ = 2 outliers before degrading (Huber 1981 *Robust
# Statistics* §1.4 breakdown-point). When 3 or more of the 6 methods
# fire ``extreme_*_estimate``, the median is past its breakdown point
# and collapses toward the low-cluster (Damodaran 2019 *Investment
# Valuation* 3rd ed. Ch. 18 — discard methods whose inputs fall outside
# their domain of applicability). The new annotate
# ``extreme_estimate_majority`` fires at that threshold. Annotate-only
# in this PR per Rule 16 + ``portable-annotate-before-veto`` — a
# follow-up PR after ≥ 1 cron's firing-rate observation will add the
# actual median-exclusion + a ``fair_price.methods_excluded_from_median``
# field for transparency. Provenance: GUT-FEEL with Huber 1981
# breakdown-point rationale (per methodology-scientist Mode B,
# 2026-05-21).
EXTREME_MAJORITY_THRESHOLD: int = 3

# Issue #587 — low-applicability floor for ``extreme_estimate_majority``
# (RE-BASE-WITH-FLOOR, methodology-scientist ratified, 0.10.32-phase8pilot).
#
# The S&P 1500 small-cap cutover exposed a false-negative dead-zone: a
# ticker with only 2-3 applicable ensemble methods can have a strict
# majority (≥ 2 of 3) be extreme without reaching the 3-of-6 absolute
# threshold (e.g., GFF MoS −1143.9%: 2 extreme of 3 applicable → silent).
#
# ``EXTREME_MAJORITY_LOWAPP_MAX``: the n_applicable ceiling that enables
# the floor regime. Set to 3 (same as EXTREME_MAJORITY_THRESHOLD) so the
# new behaviour is strictly confined to tickers with ≤ 3 applicable
# methods — i.e., only the low-applicability tail that is invisible to
# the existing 3-of-6 rule. S&P 500 stocks (typically 5-6 applicable
# methods) are byte-identical.
#
# ``EXTREME_MAJORITY_LOWAPP_MIN``: the minimum n_extreme to fire in the
# low-applicability regime. Set to 2 (GUT-FEEL, inherits the Huber 1981
# §1.4 breakdown-point provenance tier of the parent threshold — this is
# a low-applicability RECALIBRATION, not a new literature cutoff). The
# floor kills the 1-of-2 false-positive: a single extreme of 2 applicable
# is not an n=2-median breakdown event; 2 of 2 or 2 of 3 IS majority.
#
# The strict-majority guard (``n_extreme > n_applicable - n_extreme``) is
# the firing gate in the low-applicability regime, ensuring ≥ 50%+1 of
# applicable methods are extreme. Combined with LOWAPP_MIN, this aligns
# the live annotate with the already-shipped ``median_trimmed`` shadow's
# applicable-based majority logic.
#
# Ship annotate-first behind the Q3 2026-08-19 cohort-audit
# pre-registration. Defense layer unchanged at 36 (annotate-only).
EXTREME_MAJORITY_LOWAPP_MAX: int = 3
EXTREME_MAJORITY_LOWAPP_MIN: int = 2

# Data-quality sanity ceiling. Used by Site-1 (input-level) check at
# `compute/scoring/risk_overlay.py::_data_quality_input_corruption` —
# fires `data_quality_input_corruption` VETO when TBVPS > $10K/share
# (typically caused by `shares_outstanding` ingested in millions
# instead of full units). Site-1 is the canonical input-corruption
# guard; the active veto stays.
#
# Issue #289 (2026-05-28, methodology-scientist Mode B verdict Option C)
# — RETIRED FROM SITE-2 only. The Site-2 OUTPUT-level check that lived
# in `compute/valuation/ensemble.py` (Step 4.5) used this same ceiling
# to null the ensemble when ANY method's OUTPUT exceeded $10K. That
# conflated input-corruption (Type A) with high-per-share-magnitude
# (Type C: out-of-distribution but valid). NVR ($458 EPS, $6,098 price,
# ~2.7M shares) was the empirical false-positive — `multiples_pe ≈ 22×
# × $458.86 ≈ $10,094` tripped Site-2 → all 6 methods blocked → `/stock/
# NVR` empty fair-price section despite legitimate inputs and a 65% MoS
# signal. Per Penman 2013 §7.4 + Damodaran 2019 Ch. 18: defend at the
# source (Site-1 input layer), not at downstream output magnitude.
# Site-2 trigger DELETED at `compute/valuation/ensemble.py` (PR #293);
# dead-code helpers `_has_corrupt_input` + `_data_quality_corrupt_result`
# REMOVED in the PR #293 follow-up after cron Run #71 confirmed clean.
# Defense #4 `extreme_*_estimate` + Issue #177 `extreme_estimate_majority`
# (Huber 1981 §1.4 breakdown) provide the correct ensemble-robustness
# layer. This ceiling remains active for Site-1 / input layer.
FAIR_PRICE_DATA_QUALITY_CEILING: float = 10000.0

# Issue #246 — minimum plausible ``shares_outstanding`` for any S&P 500
# constituent. The index floor (~$15B mcap) at the most extreme single-
# share price seen on the index (BRK-B ~$500, post-50:1-split) implies
# ~30M shares minimum; the smallest legitimate count is well above 1M.
# A 100K floor is 30× safer than any plausible legitimate value and
# catches the ERIE pattern: SEC ``companyfacts`` aggregate filters out
# dimensional facts, so multi-class filers (ERIE Class A 54.9M / Class B
# 2,541; the aggregate returns only Class B → 2,542 shares extracted).
# Below this threshold, the per-filing XBRL fallback in
# ``compute/ingest/fundamentals.py:_fetch_shares_from_per_filing_xbrl``
# is invoked to recover the correct sum across dimensional contexts.
MIN_PLAUSIBLE_SHARE_COUNT: int = 100_000

# Issue #248 PR2b — multi-class share-structure allowlist for the
# per-filing XBRL dimensional override path. Tickers in this set have
# their primary ``companyfacts`` ``shares_outstanding`` value compared
# against the per-filing XBRL dimensional sum (Class A + Class B + ...).
# If the dimensional sum exceeds the primary value, the dimensional
# value wins.
#
# Provenance: **LITERATURE-ANCHORED on shape, EMPIRICAL on membership**.
#   - Shape (always-sum-when-dimensional, 0% delta threshold): Damodaran
#     2019 *Investment Valuation* 3rd ed. Ch. 16 — for multi-class
#     issuers, total common shares outstanding = sum across all classes.
#     The voting-premium discount applies to PRICE, not share-count
#     aggregation. The summed value is definitionally the truth; no
#     materiality bar applies. The methodology-scientist verdict
#     2026-05-25 (Mode B) rejected a 10% gap threshold as suppressing
#     the truth for any filer with minor classes < 10% of total.
#   - Membership (the 7 tickers below): verified 2026-05-25 by the
#     edgar-debugger via EPS cross-check on production output
#     (``NI / shares_outstanding`` vs known-correct reported EPS). The
#     listed tickers each show > 2x undercount via the companyfacts
#     aggregate path. GOOG / GOOGL filed non-dimensionally and don't
#     belong here despite their 3-class structure.
#
# Universal-scan rejected by the performance-engineer 2026-05-25 — a
# per-ticker peek-XBRL adds ~5 min wall-clock and breaches the < 5 min
# warm-cache budget; current p95 fundamentals latency is already 16.25s
# (1.25s over the 15s warn threshold). Allowlist limits the peek to 7
# tickers (~5s wall-clock) which is negligible.
#
# BRK-B caveat (deferred to Q3 2026-08-19 cohort audit follow-up):
# Berkshire Class A shares carry 1500x economic weight per share vs
# Class B. The naive dimensional sum (Class A 1.46M + Class B 2.14B)
# yields a ~14% residual undercount on EPS attribution. The "perfect
# fix" requires ticker-specific conversion math
# (``Class_A_count * 1500 + Class_B_count``); pending methodology Mode B
# verdict on whether economic-equivalence weighting belongs in the
# ingest layer or a higher abstraction.
#
# Expansion gate: quarterly cohort audit (next 2026-08-19) walks the
# universe-wide ``cross_source_disagreement`` annotate firing list and
# adds any newly-detected multi-class structure that survives EPS
# cross-check (see PR2b methodology + edgar-debugger verdicts).
MULTI_CLASS_SHARE_ALLOWLIST: frozenset[str] = frozenset(
    {
        "V",      # Visa Class A + B + C (B held by member banks; C by Visa International)
        "NWS",    # News Corp Class B (same CIK as NWSA)
        "NWSA",   # News Corp Class A (same CIK as NWS)
        "STZ",    # Constellation Brands Class A + Class B (already covered by None-trigger path; included for completeness)
        "FOX",    # Fox Corporation Class B (same CIK as FOXA)
        "FOXA",   # Fox Corporation Class A (same CIK as FOX)
        "BRK-B",  # Berkshire Hathaway Class B (Class A weighting deferred; see caveat above)
    }
)

# Issue #261 PR-B (0.10.6-phase4.5e) + Issue #374 (RATIFY-B, 2026-06-11) —
# Tickers where the SEC ``companyfacts`` API returns the AGGREGATE share count
# across all classes. ``shares_outstanding`` on these tickers holds the
# COMPANY-TOTAL aggregate (ASC 260 / RATIFY-B convention); the per-class XBRL
# value is captured in the NEW ``shares_outstanding_listed_class`` field for
# checksum / display only — NO scoring consumer reads it.
#
# Prior to Issue #374, Branch 3 in ``compute/ingest/fundamentals._build_snapshot``
# OVERRODE ``shares_outstanding`` with the per-class count (RATIFY-B reversed
# that: company-total must be class-invariant so the CIK-keyed parquet cache
# cannot corrupt it across the GOOG/GOOGL CIK-collision path).
# ``shares_outstanding`` is now the companyfacts AGGREGATE on BOTH cold and
# warm crons — the CIK-keyed cache collision is harmless because both entries
# return the same company-total value.
#
# This dict still drives the per-class FIELD extraction (not a shares_outstanding
# override). Class-member string format: ``<namespace>:<MemberName>`` matching
# the ``StatementClassOfStockAxis`` axis member on ``us-gaap:CommonStockSharesOutstanding``.
#
# CRITICAL GOTCHA — filer-specific namespace: edgar-debugger live probe
# 2026-05-26 on Alphabet 10-K accession ``0001652044-26-000018``
# confirmed that GOOG (Class C) uses ``goog:CapitalClassCMember`` (the
# filer's own namespace), NOT the standard ``us-gaap:CommonClassCMember``.
# GOOGL (Class A) uses the standard ``us-gaap:CommonClassAMember``.
# An allowlist keyed to the standard namespace alone would silently
# return zero rows for GOOG. Verify namespace per-ticker via live XBRL
# probe before adding new entries.
#
# Live FY2025 values from the 2026-05-26 probe (sum reconciles to the
# 12.088B aggregate exactly):
#   - GOOGL (Class A) = 5.822B shares  ← us-gaap:CommonClassAMember
#   - (Class B, founders, not traded) = 0.837B shares
#   - GOOG  (Class C) = 5.429B shares  ← goog:CapitalClassCMember
# BRK-B deferral caveat (ratio-1 classes only): BRK-B is NOT in this allowlist
# because Class A carries 1500× economic weight — the naive per-class share
# count would mis-state BRK-B's weight. Pending methodology Mode B verdict.
#
# Expansion gate: quarterly cohort audit (next 2026-08-19) walks any
# universe-wide ``multi_class_aggregate_shares_suspected`` annotate
# firings that AREN'T on this allowlist — the discovery signal for new
# candidate aggregate-only filers. Each new entry needs a live XBRL probe
# to confirm namespace + EPS cross-check.
MULTI_CLASS_OVERCOUNT_ALLOWLIST: dict[str, str] = {
    "GOOGL": "us-gaap:CommonClassAMember",   # Alphabet Class A — standard namespace
    "GOOG":  "goog:CapitalClassCMember",     # Alphabet Class C — filer-specific namespace (gotcha)
}

# Ticker→CIK overrides for post-restructuring entities where edgartools'
# bundled company_tickers.parquet still maps the ticker to the PRE-bankruptcy
# CIK. Each entry MUST be verified against the live SEC
# https://www.sec.gov/files/company_tickers.json before adding.
# Format: ticker (uppercase) → 10-digit zero-padded CIK string.
#
# Expansion gate: add a new entry ONLY after live confirmation against both
# company_tickers.json and data.sec.gov/submissions/CIK<ID>.json that the
# new CIK carries current 10-K/10-Q filings under the expected ticker.
# FUN and SMC were NOT added (need separate live verification — issue #567).
TICKER_CIK_OVERRIDES: dict[str, str] = {
    "NE": "0001895262",  # Noble Corp plc (post-2021 Ch.11 + Maersk Drilling merger).
                         # Old entity CIK 1458891 (last 10-Q 2020-06-30) must NOT be used.
                         # Source: SEC company_tickers.json, verified 2026-06-23 (issue #567).
}

# Sector-multiples peer-group floor; below this fall back to global median + flag.
MULTIPLES_MIN_PEERS: int = 8

# Net Stock Issuance veto (Pontiff-Woodgate 2008 JF). Top decile within sector.
NSI_TOP_DECILE: float = 0.90
NSI_LOOKBACK_DAYS: int = 365

# --- Phase 3d: Tier-2 event defenses (going-concern + 8-K Items 4.02/4.01) ---
# Anchored in WORKFLOW.md "PR 3d — Tier-2 Defense Layer" + Mayew-Sethuraman-
# Venkatachalam 2015 (TAR) for going-concern, Schroeder 2024 SSRN for 8-K 4.02.

# 8-K Item 4.02 hard veto: "Non-Reliance on Previously Issued Financial
# Statements". Trailing-12-month window — restatement-style events have
# ~50% subsequent restatement rate per Schroeder 2024.
EIGHT_K_LOOKBACK_DAYS_VETO: int = 365

# 8-K Item 4.01 annotate: "Changes in Registrant's Certifying Accountant".
# 2-year window per Reg S-K Item 304 disclosure horizon.
EIGHT_K_LOOKBACK_DAYS_ANNOTATE: int = 730

# Going-concern phrase scan: 1-year + buffer to capture the most recent
# 10-K. 10-K filings cluster ~75d after fiscal year-end so 400d covers
# all calendar-year filers + most off-cycle filers.
GOING_CONCERN_FILING_LOOKBACK_DAYS: int = 400

# PR 4.5b — Disclosure-driven manipulation defenses.
#
# Restatement history scan: 5-year window matches the Hennes-Leone-
# Miller 2008 *TAR* original cohort. 1825 = 5 × 365; the leap-day
# buffer is absorbed by the ``_filing_date_within`` inclusive bounds.
# A ticker with even ONE 10-K/A in this window earns
# `restatement_history` annotate; recurrent restaters (count >= 2)
# get the same flag plus a higher displayed count.
RESTATEMENT_HISTORY_LOOKBACK_DAYS: int = 1825

# Late-filing notification scan: 365-day window per Bartov-Lai-Yeung
# 2002 *JAR* baseline. Form 12b-25 (NT 10-K / NT 10-Q) within the
# trailing year flags ``late_filing_notification``.
LATE_FILING_LOOKBACK_DAYS: int = 365

# 8-K event-fetch JSON cache. Per-ticker filing list refreshes weekly;
# Item 4.02 / 4.01 disclosures are sticky once filed so even a 7-day
# stale cache won't cause a flagged ticker to silently un-flag.
EDGAR_8K_CACHE_DIR: Path = CACHE_DIR / "edgar_8k"
# 6 days (was 7): a 7-day TTL equals the weekly cron cadence, so a cache entry
# exactly 7 days old lands on the `age > ttl` boundary and re-fetches on any run
# drift / DST shift. 6 days adds a 24h buffer so a warm 8-K cache reliably hits
# run-to-run (edgar-debugger 2026-06-06, secondary to the tier2 cache-split fix).
EDGAR_8K_CACHE_TTL_SECONDS: int = 6 * 86400  # 6 days

# Issue #469 — de-synchronize the cold-burst cohort expiry.
# All 502 tickers are written in one cold-rebuild burst, so without jitter
# they ALL cross the 6-day TTL cliff simultaneously ~6 days later, producing
# an ~80-minute tier2 refetch spike on that run.  Adding a per-ticker
# deterministic jitter in [0, W) spreads expiry across the window so
# refreshes trickle in across daily cron runs instead of all-at-once.
#
# 2026-06-13 sufficiency analysis (performance-engineer): the original 24h
# window (W=24h) is structurally insufficient.  Two failure modes:
#   1. Weekday-cliff: the June 18-19 cohort expires on Thu 2026-06-19
#      22:00 UTC — a WEEKDAY where the binding cron gap is 24h, not 144h.
#      With W=24h the jitter spread equals one cron interval, leaving
#      ~471/502 tickers expiring in the SAME Thursday run (~75-min tier2
#      spike, reproducing the original problem).
#   2. Sat→Mon re-bunching: the Sat precache writes a fresh cold cohort at
#      08:00 UTC.  The Sat→Mon gap is 62h.  Re-bunching from cycle 1 is
#      only prevented when W > 62h.  At W=24h the cohort re-syncs on the
#      first Monday run.
# Fix: W=72h (3 days).  72h > 62h escapes both failure modes:
#   - The June-19 weekday cliff now spreads ~157 tickers/+25 min (vs ~471).
#   - The Sat→Mon 62h gap is fully covered: jitter 0..72h spreads the
#     first post-precache expiry across three daily cron runs instead of
#     one.
# Max staleness = 72h — negligible vs the 730-day 8-K lookback and the
# daily cron cadence; the 4.01/4.02 item rarity is unchanged.
EDGAR_8K_CACHE_TTL_JITTER_SECONDS: int = 72 * 3600  # 72 hours

# Cap how much of an Item body we keep in the cache + surface in the
# UI excerpt. 500 chars is enough for the human reviewer to gauge
# context without pulling the whole 8-K.
EDGAR_8K_ITEM_TEXT_EXCERPT_CHARS: int = 500

# Latest-10-K text cache (Defense #8 going-concern phrase scan). 90-day TTL
# is safe — 10-K filings are annual, and a ticker's most-recent 10-K only
# changes once per year. Even a stale 89-day cache hit is the same filing
# we'd fetch fresh.
EDGAR_10K_TEXT_CACHE_DIR: Path = CACHE_DIR / "edgar_10k_text"
EDGAR_10K_TEXT_CACHE_TTL_SECONDS: int = 90 * 86400  # 90 days

# --- Phase 4b: Defense Infrastructure ---
# Per `.claude/skills/phase-4/defense-infrastructure/PLAN.md` §1.

# Cross-source validator (compute.ingest.cross_source). Compare
# SEC-derived market cap (shares × current_price) against yfinance's
# reported marketCap. Delta > 5% surfaces as `cross_source_disagreement`
# in valuation_warnings (annotate-only, no Top-N veto). Catches ~80% of
# yfinance scraper drift — the canonical Phase 1 fragility documented in
# README "Honest Limitations".
CROSS_SOURCE_MARKET_CAP_TOLERANCE: float = 0.05  # 5%

# yfinance Ticker.info cache. The `marketCap` field comes from a
# separate API surface than the OHLCV history (yf.download). The .info
# call is rate-limited more aggressively than history, so we cache
# 24h per ticker — same cadence as `PRICES_CACHE_MAX_AGE_HOURS`.
YFINANCE_INFO_CACHE_DIR: Path = CACHE_DIR / "yfinance_info"
YFINANCE_INFO_CACHE_MAX_AGE_HOURS: int = 24

# --- Post-split share-lag defense (defense layer 34 → 35) ---
# Frozen pre-registration constants — methodology-scientist ruling 2026-06-18.
# Citation: CRSP CFACSHR / Damodaran 2019 *Investment Valuation* 3rd ed. Ch. 16.
#
# ``POST_SPLIT_WINDOW_DAYS``: a split within this many calendar days of today
# is "recent" (leg 1 of the 3-leg detection). At 100 days, one missed 10-Q/A
# cycle (45-day EDGAR refetch cadence × 2 quarters + buffer) is covered.
#
# ``POST_SPLIT_MIN_RATIO``: only material splits (≥ 2:1) trigger the defense.
# Prevents noise from tiny rounding-lot adjustments.
#
# ``POST_SPLIT_RATIO_TOLERANCE``: the yfinance-implied share count must match
# the EDGAR-reported count × split_ratio to within 10% for Tier-1 (CORRECT).
# If the ratio-match fails, the split is real but unreconcilable → Tier-2 (VETO).
POST_SPLIT_WINDOW_DAYS: int = 100
POST_SPLIT_MIN_RATIO: float = 2.0
POST_SPLIT_RATIO_TOLERANCE: float = 0.10

# --- Cross-source share-count-corruption defense (PR-1 shadow observability) ---
# Methodology-scientist RATIFIED-WITH-CONDITIONS 2026-06-19.
#
# ``DELTA_CORRUPTION_THRESHOLD``: the minimum cross_source_delta
# (|sec_mc − yf_mc| / sec_mc) at which a ticker is graded as a
# corruption candidate rather than normal noise.
#
# Provenance: LITERATURE-ANCHORED on shape, empirical on value.
#   - Shape: Ince-Porter 2006 *J. Financial Research* 29(4), 463-479 §II
#     (cross-source price/share discrepancy consistent with an unadjusted
#     split → corruption signal; literature-searcher 2026-06-19) + the #114
#     `cross_source_delta_histogram` audit (first cron with the Rule-18
#     histogram surface, 2026-06-19).
#     The histogram shows 95.45% of the universe at delta < 5%; the
#     corruption tail (COKE 6.07, CVNA 3.89, KLAC-pre-#499 ~10) is
#     separated from the clean mass at delta ≥ 50%.  A 0.50 (50%) threshold
#     captures the documented corruption cases with structurally zero FP rate
#     on clean stocks (BKNG ≈ 0, KLAC-post-#499 ≈ 0).
#   - Empirical: #114 daylight analysis — the clean cluster is < 5% and the
#     corruption cluster is ≥ 50% (no observed cases 5-50%).  The choice of
#     0.50 as the boundary is CONSERVATIVE: a lower threshold (e.g. 0.25)
#     would still yield zero FPs on the current universe but lacks the
#     histogram daylight evidence that the 0.50 threshold carries.
#   - Q3 2026-08-19 follow-up: recalibrate if new crons show cases in the
#     5%-50% band (would indicate a new class of partial corruption not seen
#     in the current universe).
DELTA_CORRUPTION_THRESHOLD: float = 0.50

# ``INTEGER_RATIO_TOLERANCE`` (reuses ``POST_SPLIT_RATIO_TOLERANCE``):
# tolerance for the near-integer test in the shadow grading function.
# ``|R − round(R)| / round(R) ≤ 0.10`` with ``round(R) ≥ 2``.
# Named alias so callers import the semantic rather than a magic float.
#
# GUT-FEEL provenance (the round(R) integer-recovery inference): NO
# peer-reviewed anchor as of 2026-06-19 (literature-searcher). Closest
# documented analog is the Linnsoft Stock Split Finder (round 2.007 → 2:1)
# — within-series only, NOT cross-source. COUNTER-EVIDENCE: Chen 2012
# (kaichen.work) documents a near-integer cross-source market-cap ratio
# (Ascent Media 11.7×) arising from MISSING SHARE CLASSES, not a split —
# so a near-integer cross-source ratio does NOT uniquely identify a stale
# split. This is why PR-1 only COUNTS candidates (shadow) and the future
# PR-2 CORRECT mutation must require a corroborating yfinance `.splits`
# event before mutating (esp. dual-class names like CVNA). Q3 2026-08-19
# academic-validation follow-up.
INTEGER_RATIO_TOLERANCE: float = POST_SPLIT_RATIO_TOLERANCE  # 0.10

# --- S&P 1500 Slice 4: ADV liquidity backstop (annotate-first, defense 36) ---
# Ships as ANNOTATE ONLY per Rule 16 / ``portable-annotate-before-veto``.
# PRE-REGISTERED PROMOTION PLAN (issue #544, methodology-scientist RATIFY-WITH-
# CONDITIONS 2026-06-23): keep this $5M ``ADV_FLOOR_USD`` as the ANNOTATE cutoff
# and add a SEPARATE, stricter ``ADV_VETO_FLOOR_USD = 3_000_000`` veto floor at
# the Q3 2026-08-19 cohort audit. NOT WIRED YET — this is a docs-only pre-
# registration; the live veto constant + cautious/Top-5 suppression land in the
# Q3 promotion PR. A $3M veto flips only the genuinely un-tradeable tail
# (BFS/CENT/SBSI) to ``cautious`` while $4.6-5.0M names keep the softer $5M
# annotate. Promotion is gated on acceptance bands B1-B5 (docs/METHODOLOGY.md
# §low_liquidity): firing rate ∈ [3,15], ≤30% population churn, ZERO fired names
# in rank ≤ 10 / the AI-pick basket (HARD gate), ADV coverage ≥ 99%, ≥ 8 sp1500
# crons (5 observed 2026-06-23, set {BFS,CENT,CPF,SBSI,SMP}, 0% churn). The veto
# is an INVESTABILITY filter, NOT an alpha claim — illiquidity carries a return
# PREMIUM (Amihud 2002), so the hard-suppress means "un-tradeable for this
# audience", an owner-policy call ratified for Q3 (WORKFLOW.md §8.6).
#
# Academic anchor: Amihud 2002 *J. Financial Markets* "Illiquidity and stock
# returns" — dollar volume (price × shares) IS the denominator of the Amihud
# ILLIQ ratio, so this guard sits squarely in the illiquidity-premium family
# (see also Amihud-Mendelson 1986; Kyle 1985 price-impact). The $5M/day figure
# is a CALIBRATION CONVENTION at the conservative end of the institutional
# ADDV-floor band ($1M-$5M), NOT a cutoff lifted from any paper table. It was
# RE-DERIVED 2026-06-23 from the realized sp600 ADV distribution (n=602:
# p0.5≈$4.64M, p1≈$5.05M, p2.5≈$6.30M, median≈$31.5M) — the $5M annotate sits at
# ≈ sp600 p0.8, and the pre-registered $3M veto floor matches the natural break
# below the BFS/CENT/SBSI cluster (methodology-scientist RATIFY-WITH-CONDITIONS,
# issue #544, S&P 1500 Slice 4). Below this scale, market-impact noise dominates
# any fundamental signal.
#
# ``ADV_FLOOR_USD``: minimum acceptable 30-day mean dollar volume.
# ``ADV_LOOKBACK_DAYS``: trailing trading-day window for the mean.
#   30 trading days ≈ 6 calendar weeks — long enough to smooth single-day
#   volume spikes, short enough to reflect current liquidity regime.
ADV_FLOOR_USD: float = 5_000_000.0  # $5M average daily dollar volume
ADV_LOOKBACK_DAYS: int = 30  # trailing trading days

# PR 4.5b — disclosure-driven defenses. 10-K/A + 10-Q/A list (5y) +
# Form 12b-25 (NT 10-K / NT 10-Q, 1y) per-ticker JSON caches.
# 7-day TTL matches the existing 8-K cache rhythm — restatements
# don't unfile, so a 7-day stale cache won't miss a flag.
EDGAR_AMENDMENTS_CACHE_DIR: Path = CACHE_DIR / "edgar_amendments"
EDGAR_LATE_FILINGS_CACHE_DIR: Path = CACHE_DIR / "edgar_late_filings"

# --- Phase 4.5e scout: SEC Form 4 insider-transaction ingest ---
# Form 4 is filed within 2 business days of a reportable insider transaction.
# 180-day lookback (was 365). The 2026-05-22 hotfix for the edgartools
# property→method silent-drop made the per-filing ``obj()`` call actually
# do its HTTP round-trip (vs the pre-fix silent-fast-failure). 365d at
# 502 tickers exceeded the 45-min CI cap on cold cache (pre-merge-prod-sim
# on PR #210 timed out at 43m44s). Cohen-Malloy-Pomorski 2012 *JF* §3.1
# used parallel 6m / 12m windows in their backtest, so 180d (≈ 6m)
# remains literature-anchored. The 365d window will be restored once a
# per-filing cache lands (avoid re-fetching ``filing.obj()`` for already-
# seen accession numbers) — tracked as a follow-up to PR #210.
FORM4_LOOKBACK_DAYS: int = 180
# Per-ticker Form-4 JSON cache. 7-day TTL matches the existing 8-K rhythm —
# Form 4 filings are weekly at most for any given insider, and the cache keys
# by (ticker, asof_date) so a 7-day stale entry won't miss a NEW filing
# (the fetch covers the entire lookback window, not a delta).
EDGAR_FORM4_CACHE_DIR: Path = CACHE_DIR / "edgar_form4"
EDGAR_FORM4_CACHE_TTL_SECONDS: int = 7 * 86400  # 7 days

# --- Phase 4h scout: OpenAssetPricing portfolio returns ingest ---
# Chen-Zimmermann openassetpricing.com long-short portfolio returns
# (MIT-licensed package). The scout PR adds an ingest skeleton only;
# Phase 4h consumes this in compute/features/osap_replicate.py.
# 31-day freshness matches OSAP's monthly release cadence — pulling
# more often is wasted bandwidth.
OSAP_RETURNS_CACHE: Path = CACHE_DIR / "osap" / "returns.parquet"
OSAP_RETURNS_MAX_AGE_DAYS: int = 31

# --- Phase 4i scout: Jensen-Kelly-Pedersen factor library ingest ---
# Jensen-Kelly-Pedersen 2023 *Journal of Finance* "Is There a
# Replication Crisis in Finance?" — 153 individual signals collapsed
# into 13 quasi-orthogonal theme clusters. Data lives on the
# `jkpfactors.s3.amazonaws.com` public S3 bucket (CC BY-NC 4.0 data
# license; MIT code license on `bkelly-lab/jkp-data`). The scout PR
# adds an ingest skeleton + 6 smoke tests; Phase 4i full integration
# (theme aggregation + pillar blending + PBO/DSR gate + main.py
# wiring) ships in a follow-on ~5-commit PR after the scout merges.
#
# 31-day freshness matches JKP's monthly release cadence (S3
# `LastModified` headers show ~monthly file updates).
JKP_RETURNS_CACHE: Path = CACHE_DIR / "jkp" / "returns.parquet"
JKP_RETURNS_MAX_AGE_DAYS: int = 31

# --- Phase 4j scout: Microsoft Qlib (Alpha158) integration ---
# Microsoft Qlib factor library — per-stock per-date features
# computed locally from OHLCV bars via the `pyqlib` package (MIT
# licensed, verified via PyPI wheel METADATA 2026-05-19). Phase 4j
# is structurally different from 4h (OSAP) + 4i (JKP): Qlib has NO
# public US data bundle (`REG_US` exists but the cache is BYO), so
# the integration PR will need to convert our existing yfinance
# OHLCV cache (`compute/cache/prices/*.parquet`) into Qlib's `.bin`
# format. The scout PR ships an install skeleton + 158-feature
# manifest + offline tests; the BYO adapter is integration-PR scope.
#
# `compute/cache/` is already gitignored at .gitignore:221 — the
# parent glob covers `compute/cache/qlib/` so no explicit
# `.gitignore` edit needed for this scout.
QLIB_DATA_CACHE: Path = CACHE_DIR / "qlib" / "us_data"
QLIB_DATA_MAX_AGE_DAYS: int = 31

# Alpha158 feature count. Asserted at module load in
# `compute/ingest/qlib_features.py::ALPHA158_FEATURE_NAMES` against
# the hardcoded 158-name tuple (which is itself test-asserted against
# the runtime introspection from `Alpha158DL.get_feature_config()`).
ALPHA158_FEATURE_COUNT: int = 158

# --- Phase 4k scout: Kelly-Pruitt-Su IPCA latent factor model ---
# IPCA = Instrumented Principal Component Analysis. Reference:
# Kelly, Pruitt, Su (2019) *Journal of Financial Economics*
# "Characteristics are covariances: A unified model of risk and
# return". The `ipca` PyPI package (MIT licensed, verified via
# LICENSE.md 2026-05-19) implements `InstrumentedPCA` as a sklearn-
# style estimator: a panel of (N stocks × T dates × L characteristics)
# decomposes into Gamma (L × K factor loadings) + Factors (K × T
# latent factor returns). Phase 4k is the final factor-library
# scout; integration PR (4k.1) will wire characteristics-matrix
# construction + universe-wide fit + composite blend decision.
#
# `compute/cache/` is already gitignored at .gitignore parent glob —
# the `compute/cache/ipca/` subdir is covered, no explicit
# `.gitignore` edit needed.
IPCA_FITTED_ARTIFACTS_CACHE: Path = CACHE_DIR / "ipca"
IPCA_FITTED_ARTIFACTS_MAX_AGE_DAYS: int = 31

# InstrumentedPCA public-API method count. Asserted at module load in
# `compute/features/ipca_factors.py::INSTRUMENTED_PCA_PUBLIC_API`
# against the hardcoded 8-name tuple (drift detector against any
# future `ipca` package upgrade — pin range `>=0.6.7,<0.7` plus this
# manifest catches silent API renames).
IPCA_PUBLIC_API_METHOD_COUNT: int = 8

# --- Phase 4h: 100-signal manifest ---
#
# Theme buckets mirror the table at
# `.claude/skills/phase-4/osap-integration/PLAN.md` L60-73
# (Value/Quality/Momentum/Investment/Risk/EarningsNews/Trading +
# Misc). CamelCase names follow the Chen-Zimmermann OSAP convention
# (see github.com/OpenSourceAP/CrossSection signal docs).
#
# Aspirational manifest — commit 4's PBO/DSR gate
# (`compute/validation/osap_validation.py`) will catch any signal that
# does not resolve in the fetched OSAP returns DataFrame and log it
# under `metadata.json::osap_excluded_signals` with reason
# `not_found_in_osap_dataset` so the manifest can be tuned over
# subsequent compute runs without a redeploy.
OSAP_SIGNALS_BY_THEME: dict[str, tuple[str, ...]] = {
    "Value": (
        "BM", "EP", "SP", "CF", "DivYieldST", "NetEquityFinance",
        "NetDebtFinance", "BookLeverage", "IntanBM", "IntanCFP",
        "IntanEP", "IntanSP", "DebtIssuance", "OperatingLeverage",
        "CompositeDebtIssuance",
    ),  # 15
    "Quality": (
        "GP", "RoE", "RoA", "AssetTurnover", "AOP", "OperatingProfit",
        "RDS", "RD", "ProfitMargin", "CashProf", "GrcapxThreeYears",
        "AccrualsBM", "OperatingAccruals", "PctTotAcc", "Cash",
    ),  # 15
    "Momentum": (
        "Mom12m", "Mom6m", "Mom36m", "Mom1m", "STreversal", "IndMom",
        "IntMom", "EarnSupBig", "MomVol", "MomOffSeason", "MomSeason",
        "Recomm_ShortInterest",
    ),  # 12
    "Investment": (
        "AssetGrowth", "ChNNCOA", "ChNWC", "GrLTNOA", "ChInv",
        "ShareIss1Y", "ShareIss5Y", "GrSaleToGrInv",
    ),  # 8
    "Risk": (
        "MaxRet", "IdioVol3F", "IdioVolAHT", "BetaTailRisk", "Beta",
        "BetaFP", "ReturnSkew", "ReturnSkew3F", "IndIPO",
        "AbnormalAccruals",
    ),  # 10
    "EarningsNews": (
        "SUE", "EarningsSurprise", "REV6", "RDIPO", "NumEarnIncrease",
        "ConsRecomm", "Recomm", "EarningsForecastDisparity",
    ),  # 8
    "Trading": (
        "Illiquidity", "Turnover", "Bid_Ask", "VolMkt", "VolSD",
        "dVolCall", "Coskewness",
    ),  # 7
    "Misc": (
        "Leverage", "OrgCapital", "Tax", "ChAssetTurnover", "BAR",
        "GS", "AnnouncementReturn", "OScore", "ZScore", "CredRatDG",
        "FailureProbability", "IRA", "FR", "BPEBM", "Activism1",
        "Activism2", "AnalystValue", "ChForecastAccrual", "ChInvIA",
        "AnalystRevision", "ForecastDispersion", "GrowthCapEx",
        "MeanRankRevGrowth", "AbnormalAccrualsPercent", "ChEQ",
    ),  # 25
}

OSAP_SIGNALS_100: tuple[str, ...] = tuple(
    sig for theme_signals in OSAP_SIGNALS_BY_THEME.values() for sig in theme_signals
)
assert len(OSAP_SIGNALS_100) == 100, (
    f"OSAP_SIGNALS_100 must have exactly 100 entries, got {len(OSAP_SIGNALS_100)}"
)
assert len(set(OSAP_SIGNALS_100)) == 100, (
    "OSAP_SIGNALS_100 contains duplicate signal names"
)

# --- Proposal D: Market-regime diagnostic (WRITE-ONLY / OBSERVABILITY-ONLY) ---
# Computed from prices_by_ticker already loaded in Step 1 — NO new data source.
# SHADOW / Rule 18 — NEVER feeds scoring, vetoes, composite, or select_picks.
# Rejection rationale: Welch-Goyal 2008 *RFS* 21(4), 1455-1508 — equity-premium
# predictors fail OOS; breadth is a PLACEHOLDER FEATURE for Phase-7 HMM, not a
# validated regime classifier.  These thresholds are TIER-3 GUT-FEEL CALIBRATION
# (no paper pins exact breadth cutoffs); they are named constants so any future
# recalibration is a visible diff rather than a magic-number hunt.
#
# Breadth >= REGIME_RISK_ON_THRESHOLD  → "risk_on"  (broad market participation)
# Breadth <= REGIME_RISK_OFF_THRESHOLD → "risk_off" (broad deterioration)
# else                                 → "neutral"
#
# Round numbers (60% / 40%) are conventional technical-analysis "breadth thrust"
# levels — NOT anchored to any peer-reviewed table.  Recalibrate at Phase-7 HMM
# design time when an empirical panel of regime labels is available.
REGIME_RISK_ON_THRESHOLD: float = 60.0   # breadth_pct >= 60% → risk_on  (Tier-3)
REGIME_RISK_OFF_THRESHOLD: float = 40.0  # breadth_pct <= 40% → risk_off (Tier-3)
