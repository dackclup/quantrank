"""Project paths and defaults. No env vars in code — secrets come from CI."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
FRONTEND_DIR: Path = PROJECT_ROOT / "frontend"
DATA_DIR: Path = FRONTEND_DIR / "public" / "data"
STOCKS_DIR: Path = DATA_DIR / "stocks"
CACHE_DIR: Path = PROJECT_ROOT / "compute" / "cache"
UNIVERSE_CACHE: Path = CACHE_DIR / "universe.parquet"
PRICES_CACHE_DIR: Path = CACHE_DIR / "prices"
FUNDAMENTALS_CACHE_DIR: Path = CACHE_DIR / "fundamentals"
FUNDAMENTALS_HISTORY_CACHE_DIR: Path = CACHE_DIR / "fundamentals_history"
MODELS_DIR: Path = PROJECT_ROOT / "models"

UNIVERSE: str = "SP500"
SCHEMA_VERSION: str = "0.5.0-phase3c"

PRICES_PERIOD: str = "5y"
MAX_PARALLEL_FETCHES: int = 10
EDGAR_MAX_WORKERS: int = 5
UNIVERSE_CACHE_MAX_AGE_DAYS: int = 7
PRICES_CACHE_MAX_AGE_HOURS: int = 24
FUNDAMENTALS_REFETCH_DAYS: int = 45
MIN_VALID_TICKERS: int = 100
MIN_FUNDAMENTALS_COVERAGE: float = 0.5

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

# Stale-filing guards (10-Q deadline 45d; 75d past = unusual, missed = restatement risk).
FILING_STALE_SOFT_DAYS: int = 120
FILING_STALE_HARD_DAYS: int = 180

# Tangible-book "goodwill heavy" threshold: TBVPS / BVPS_reported < 0.5 → annotate.
GOODWILL_HEAVY_RATIO: float = 0.5

# Multi-method outlier guard: exclude estimates outside [0.2×, 5×] current price from MAX
# (still in MEDIAN — robust to one outlier per RESEARCH §V-4).
EXTREME_ESTIMATE_HIGH: float = 5.0
EXTREME_ESTIMATE_LOW: float = 0.2

# Sector-multiples peer-group floor; below this fall back to global median + flag.
MULTIPLES_MIN_PEERS: int = 8

# Net Stock Issuance veto (Pontiff-Woodgate 2008 JF). Top decile within sector.
NSI_TOP_DECILE: float = 0.90
NSI_LOOKBACK_DAYS: int = 365
