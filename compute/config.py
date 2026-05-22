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
SCHEMA_VERSION: str = "0.10.0-phase4.5e"

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

# Issue #67 — sector-adjusted cost of equity (Damodaran 2019 Table 8.4).
#
# When ``True``, ``compute.valuation.ensemble.compute_fair_price_ensemble``
# uses the per-GICS-Sector Ke from
# ``compute.scoring.cost_of_equity.get_cost_of_equity`` instead of the
# flat ``COST_OF_EQUITY = 0.10``.
#
# DEFAULT = False — this PR is DATA-COLLECTION ONLY per Rule 18
# (observability-before-wiring).  The flip to ``True`` follows after ≥ 1
# cron confirms the delta-flag-count via
# ``Metadata.value_trap_risk_count_with_sector_coe`` vs
# ``Metadata.value_trap_risk_count_without_sector_coe``.
# Expected: ``value_trap_risk`` drops from ~176 toward ~80-110 for
# cyclical sectors; Utilities/REITs (sector Ke < 10%) may pick up new
# flags — net change needs empirical confirmation before the flip.
#
# Methodology-scientist Mode B sign-off REQUIRED before the flip PR lands.
USE_SECTOR_COE: bool = False

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

# PR 4.5b — disclosure-driven defenses. 10-K/A + 10-Q/A list (5y) +
# Form 12b-25 (NT 10-K / NT 10-Q, 1y) per-ticker JSON caches.
# 7-day TTL matches the existing 8-K cache rhythm — restatements
# don't unfile, so a 7-day stale cache won't miss a flag.
EDGAR_AMENDMENTS_CACHE_DIR: Path = CACHE_DIR / "edgar_amendments"
EDGAR_LATE_FILINGS_CACHE_DIR: Path = CACHE_DIR / "edgar_late_filings"

# --- Phase 4.5e scout: SEC Form 4 insider-transaction ingest ---
# Form 4 is filed within 2 business days of a reportable insider transaction.
# 365-day lookback captures ~4 earnings cycles worth of insider activity per
# ticker (Cohen-Malloy-Pomorski 2012 *JF* §3.1 use the same trailing-year
# window for the insider-sell signal). Adjust to 180d if the cron fetch loop
# adds > 10 min to the weekly run (i.e., warm-cache run > 30 min total).
FORM4_LOOKBACK_DAYS: int = 365
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
