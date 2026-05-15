"""Project paths and defaults. No env vars in code — secrets come from CI."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
FRONTEND_DIR: Path = PROJECT_ROOT / "frontend"
DATA_DIR: Path = FRONTEND_DIR / "public" / "data"
STOCKS_DIR: Path = DATA_DIR / "stocks"
CACHE_DIR: Path = PROJECT_ROOT / "compute" / "cache"
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
SCHEMA_VERSION: str = "0.7.2-phase4g"

PRICES_PERIOD: str = "5y"
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
PRICES_CACHE_MAX_AGE_HOURS: int = 24
FUNDAMENTALS_REFETCH_DAYS: int = 45
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
HTTP_USER_AGENT: str = "QuantRank/0.3 (+https://github.com/dackclup/quantrank)"

# --- Phase 3c: fair price ensemble + Tier-1 defense constants ---
# Anchored in WORKFLOW.md "PR 3c — Tier-1 Defense Layer" and
# docs/RESEARCH_FINDINGS.md "Defense Playbook §PR 3c".

# DCF (Damodaran practitioner defaults; revisited per-sector in Phase 7).
DISCOUNT_RATE: float = 0.10  # WACC proxy for non-Financial/non-Utility S&P 500
TERMINAL_GROWTH: float = 0.03  # long-run nominal GDP cap (Damodaran)
COST_OF_EQUITY: float = 0.10  # used by RIM (Cost of Equity ≈ WACC for S&P 500 cash-flat names)
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

# Data-quality sanity ceiling. No S&P 500 stock has a sensible fair price
# > $10,000/share (BRK-A trades ~$700K but is not in the index; BRK-B is).
# If any applicable method computes a value above this ceiling, the
# upstream snapshot inputs are corrupted (typically shares_outstanding
# ingested with the wrong unit). The ensemble nulls all 6 methods and
# surfaces ``data_quality_input_corruption`` as a single warning rather
# than ship nonsense to the UI. See compute/valuation/ensemble.py.
FAIR_PRICE_DATA_QUALITY_CEILING: float = 10000.0

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

# 8-K event-fetch JSON cache. Per-ticker filing list refreshes weekly;
# Item 4.02 / 4.01 disclosures are sticky once filed so even a 7-day
# stale cache won't cause a flagged ticker to silently un-flag.
EDGAR_8K_CACHE_DIR: Path = CACHE_DIR / "edgar_8k"
EDGAR_8K_CACHE_TTL_SECONDS: int = 7 * 86400  # 7 days

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
