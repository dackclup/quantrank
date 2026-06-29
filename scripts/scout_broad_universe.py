"""Phase 9.0 Broad Investable US Universe Scout — measurement-only, dev tool.

Investigates feasibility of expanding the live AI-pick universe from SP1500
(~1504 names) to a "Broad Investable US" cohort (~3,000 names target) sourced
from SEC company_tickers.json + our own liquidity/price/market-cap screen.

SCOUT ONLY — no production wiring, no schema changes, no cron integration.
Intended for one-shot manual runs; outputs go to scout_out/.

Usage:

    # Requires live SEC access (EDGAR_USER_AGENT optional for company_tickers.json).
    # Fetches prices via Yahoo Finance chart API (requests-based, proxy-compatible).

    python -m scripts.scout_broad_universe --mode population
    python -m scripts.scout_broad_universe --mode screen --sample 200
    python -m scripts.scout_broad_universe --mode runtime
    python -m scripts.scout_broad_universe --mode report   # synthesize all

DEV TOOL — never imported by production or CI.
Analogous to: scripts/scout_universe_expansion.py (Phase 8).
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import re
import statistics
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from compute import config  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCOUT_OUT_DIR = _REPO_ROOT / "scout_out" / "broad_universe"
POPULATION_JSON = SCOUT_OUT_DIR / "population.json"
SCREEN_JSON = SCOUT_OUT_DIR / "screen_results.json"
RUNTIME_JSON = SCOUT_OUT_DIR / "runtime.json"
REPORT_MD = SCOUT_OUT_DIR / "report.md"

# Bundled edgartools parquet — includes exchange column (live JSON does not)
_EDGARTOOLS_BUNDLED_PARQUET = (
    Path(__file__).resolve().parent.parent
    / ".."
    / "usr"
    / "local"
    / "lib"
    / "python3.11"
    / "dist-packages"
    / "edgar"
    / "reference"
    / "data"
    / "company_tickers.parquet"
)
# Canonical path (discovered at runtime)
EDGARTOOLS_PARQUET_CANDIDATES: list[Path] = [
    Path("/usr/local/lib/python3.11/dist-packages/edgar/reference/data/company_tickers.parquet"),
    Path("/usr/lib/python3/dist-packages/edgar/reference/data/company_tickers.parquet"),
]

SEC_COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Name-pattern exclusions (what we CAN infer from title alone)
_ETF_FUND_PAT = re.compile(r"\bETF\b|\bFUND\b", re.I)
_SPAC_PAT = re.compile(r"\bACQUISITION\b|\bBLANK CHECK\b|\bSPAC\b", re.I)
# Ticker-format exclusions (preferred, warrants, rights)
_NONEQUITY_TICKER_PAT = re.compile(
    r"-P[A-Z]?$|-W[A-Z]?$|-UN$|-U$|-WS$|-WT$|-R$|-RT$|-RI$"
)

# Investability floor (matches config.py)
PRICE_FLOOR_USD: float = 5.0
ADV_FLOOR_USD: float = config.ADV_FLOOR_USD  # $5M
ADV_LOOKBACK_DAYS: int = config.ADV_LOOKBACK_DAYS  # 30

# Yahoo Finance chart API (requests-based; avoids curl_cffi TLS issues in CI env)
YF_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
YF_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; QuantRank research scout)"}
YF_REQUEST_DELAY_S: float = 0.05  # gentle rate limit between tickers


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------


def _find_bundled_parquet() -> Path | None:
    """Locate the edgartools bundled company_tickers parquet."""
    for p in EDGARTOOLS_PARQUET_CANDIDATES:
        if p.exists():
            return p
    # Try importing edgar to find its path
    try:
        import edgar  # type: ignore

        edgar_dir = Path(edgar.__file__).parent
        candidate = edgar_dir / "reference" / "data" / "company_tickers.parquet"
        if candidate.exists():
            return candidate
    except ImportError:
        pass
    return None


def _fetch_live_company_tickers(session: requests.Session) -> dict | None:
    """Fetch SEC company_tickers.json. Returns raw dict or None on failure."""
    ua = os.environ.get("EDGAR_USER_AGENT", config.HTTP_USER_AGENT)
    try:
        r = session.get(
            SEC_COMPANY_TICKERS_URL,
            headers={"User-Agent": ua},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("Live company_tickers.json fetch failed: %s", e)
        return None


def _load_bundled_parquet() -> pd.DataFrame | None:
    """Load edgartools bundled company_tickers parquet."""
    p = _find_bundled_parquet()
    if p is None:
        logger.warning("Bundled company_tickers parquet not found")
        return None
    try:
        df = pd.read_parquet(p)
        logger.info("Loaded bundled parquet: %d rows from %s", len(df), p)
        return df
    except Exception as e:
        logger.warning("Failed to load bundled parquet: %s", e)
        return None


# ---------------------------------------------------------------------------
# Population analysis
# ---------------------------------------------------------------------------


def _classify_population(
    live_data: dict | None,
    bundled_df: pd.DataFrame | None,
) -> dict:
    """Classify the raw SEC population. Returns structured population report."""

    # --- Live JSON analysis (ticker + CIK + title only) ---
    live_stats: dict = {}
    if live_data is not None:
        entries = list(live_data.values())
        n_total = len(entries)

        # Name-pattern categorisation
        n_etf_by_name = sum(
            1 for e in entries if _ETF_FUND_PAT.search(str(e.get("title", "")))
        )
        n_spac_by_name = sum(
            1 for e in entries if _SPAC_PAT.search(str(e.get("title", "")))
        )
        n_trust_by_name = sum(
            1
            for e in entries
            if re.search(r"\bTRUST\b", str(e.get("title", "")), re.I)
        )
        # Ticker-format exclusions
        n_preferred = sum(
            1
            for e in entries
            if re.search(r"-P[A-Z]?$", str(e.get("ticker", "")))
        )
        n_warrants = sum(
            1
            for e in entries
            if re.search(r"-(W[A-Z]?|WS|WT|UN|U|R|RT|RI)$", str(e.get("ticker", "")))
        )

        # Combined exclusion set
        all_excl: set[str] = set()
        for e in entries:
            t = str(e.get("ticker", ""))
            title = str(e.get("title", ""))
            if (
                _ETF_FUND_PAT.search(title)
                or _SPAC_PAT.search(title)
                or _NONEQUITY_TICKER_PAT.search(t)
            ):
                all_excl.add(t)

        remaining_live = n_total - len(all_excl)

        live_stats = {
            "total_entries": n_total,
            "etf_fund_by_name": n_etf_by_name,
            "trust_by_name": n_trust_by_name,
            "spac_acquisition_by_name": n_spac_by_name,
            "preferred_by_ticker": n_preferred,
            "warrant_unit_by_ticker": n_warrants,
            "total_clearly_excludable": len(all_excl),
            "remaining_after_name_format_filter": remaining_live,
            "classification_limits": [
                "No exchange column — cannot distinguish OTC from listed",
                "No security_type — cannot filter ETFs whose name lacks ETF/FUND keyword",
                "No market_cap / price — cannot apply investability floor",
                "ADR detection unreliable — title has no consistent ADR keyword",
                "TRUST includes REITs and BDCs that may be valid equities",
            ],
            "extra_signal_needed": [
                "exchange (bundled parquet adds this — 4 tiers: Nasdaq/NYSE/CBOE/OTC)",
                "security_type from yfinance fast_info.quote_type (#565) or SEC submissions entityType",
                "price + ADV (yfinance download / Yahoo Chart API) for investability floor",
                "SEC submissions-JSON entityType for ADR detection (#541 PR-1b TODO)",
            ],
        }

    # --- Bundled parquet analysis (adds exchange column) ---
    bundled_stats: dict = {}
    if bundled_df is not None:
        n_total_bundled = len(bundled_df)
        exch_counts = bundled_df["exchange"].value_counts().to_dict()

        main_exch = bundled_df[bundled_df["exchange"].isin(["Nasdaq", "NYSE", "CBOE"])]
        n_otc = int((bundled_df["exchange"] == "OTC").sum())

        # Apply name + format exclusions on main-exchange set
        excl_mask = (
            main_exch["name"].str.contains(_ETF_FUND_PAT, na=False)
            | main_exch["name"].str.contains(_SPAC_PAT, na=False)
            | main_exch["ticker"].str.contains(
                r"-P[A-Z]?$|-W[A-Z]?$|-UN$|-U$|-WS$|-WT$|-R$|-RT$|-RI$", na=False
            )
        )
        candidates = main_exch[~excl_mask]
        n_candidates = len(candidates)

        bundled_stats = {
            "note": "Bundled parquet adds exchange column; may be 1-2 weeks stale vs live JSON",
            "total_rows": n_total_bundled,
            "exchange_distribution": exch_counts,
            "on_main_us_exchanges_nasdaq_nyse_cboe": len(main_exch),
            "on_otc": n_otc,
            "after_name_format_filter_main_exchanges": n_candidates,
            "candidate_pool_estimate": n_candidates,
            "sp1500_current": 1504,
            "ratio_vs_sp1500": round(n_candidates / 1504, 1),
        }

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "live_json": live_stats,
        "bundled_parquet": bundled_stats,
    }


# ---------------------------------------------------------------------------
# Screen sizing (sample-based)
# ---------------------------------------------------------------------------


def _fetch_price_adv(
    ticker: str,
    session: requests.Session,
) -> dict:
    """Fetch last price + 30-day ADV via Yahoo Finance chart API.

    Returns dict with status + price + adv fields.  Never raises.
    """
    try:
        r = session.get(
            YF_CHART_URL.format(ticker=ticker),
            params={"interval": "1d", "range": "3mo"},
            headers=YF_HEADERS,
            timeout=8,
        )
        if r.status_code != 200:
            return {"ticker": ticker, "status": f"http_{r.status_code}"}

        data = r.json()
        result_list = (data.get("chart") or {}).get("result")
        if not result_list:
            return {"ticker": ticker, "status": "no_result"}

        indicators = result_list[0].get("indicators", {})
        quote = (indicators.get("quote") or [{}])[0]

        closes = [c for c in (quote.get("close") or []) if c is not None]
        volumes = [v for v in (quote.get("volume") or []) if v is not None]

        if not closes or not volumes:
            return {"ticker": ticker, "status": "no_bars"}

        n = min(len(closes), len(volumes))
        closes = closes[-n:]
        volumes = volumes[-n:]
        last_price = float(closes[-1])

        tail_n = min(ADV_LOOKBACK_DAYS, n)
        tail_c = closes[-tail_n:]
        tail_v = volumes[-tail_n:]
        adv = sum(tail_c[j] * tail_v[j] for j in range(tail_n)) / tail_n

        return {
            "ticker": ticker,
            "status": "ok",
            "price": round(last_price, 2),
            "adv": round(adv, 0),
            "n_bars": n,
            "pass_price": last_price >= PRICE_FLOOR_USD,
            "pass_adv": adv >= ADV_FLOOR_USD,
            "pass_both": last_price >= PRICE_FLOOR_USD and adv >= ADV_FLOOR_USD,
        }
    except requests.exceptions.Timeout:
        return {"ticker": ticker, "status": "timeout"}
    except Exception as e:
        return {"ticker": ticker, "status": f"error:{type(e).__name__}"}


def _wilson_ci(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% confidence interval for a proportion."""
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def run_screen(n_sample: int = 200, seed: int = 42) -> dict:
    """Sample n_sample tickers from the candidate pool, fetch price + ADV."""
    bundled_df = _load_bundled_parquet()
    if bundled_df is None:
        logger.error("Cannot run screen without bundled parquet")
        return {}

    main_exch = bundled_df[bundled_df["exchange"].isin(["Nasdaq", "NYSE", "CBOE"])]
    excl_mask = (
        main_exch["name"].str.contains(_ETF_FUND_PAT, na=False)
        | main_exch["name"].str.contains(_SPAC_PAT, na=False)
        | main_exch["ticker"].str.contains(
            r"-P[A-Z]?$|-W[A-Z]?$|-UN$|-U$|-WS$|-WT$|-R$|-RT$|-RI$", na=False
        )
    )
    candidates = main_exch[~excl_mask].reset_index(drop=True)
    n_pool = len(candidates)
    logger.info("Candidate pool: %d tickers", n_pool)

    # Stratified sample by exchange
    nasdaq = candidates[candidates["exchange"] == "Nasdaq"]
    nyse = candidates[candidates["exchange"] == "NYSE"]
    n_nasdaq = min(len(nasdaq), n_sample // 2)
    n_nyse = min(len(nyse), n_sample - n_nasdaq)

    rng = random.Random(seed)
    sample_tickers: list[str] = (
        nasdaq.sample(n_nasdaq, random_state=seed)["ticker"].tolist()
        + nyse.sample(n_nyse, random_state=seed)["ticker"].tolist()
    )
    rng.shuffle(sample_tickers)
    logger.info(
        "Sample: %d tickers (%d Nasdaq + %d NYSE)",
        len(sample_tickers),
        n_nasdaq,
        n_nyse,
    )

    session = requests.Session()
    session.verify = "/root/.ccr/ca-bundle.crt"

    results: list[dict] = []
    per_ticker_times: list[float] = []
    t_start = time.time()

    for i, ticker in enumerate(sample_tickers):
        t0 = time.time()
        result = _fetch_price_adv(ticker, session)
        elapsed = time.time() - t0
        per_ticker_times.append(elapsed)
        results.append(result)
        time.sleep(YF_REQUEST_DELAY_S)

        if (i + 1) % 50 == 0:
            logger.info(
                "  %d/%d done (%.1fs elapsed)",
                i + 1,
                len(sample_tickers),
                time.time() - t_start,
            )

    total_elapsed = time.time() - t_start
    median_ms = statistics.median(per_ticker_times) * 1000

    ok = [r for r in results if r.get("status") == "ok"]
    failed = [r for r in results if r.get("status") != "ok"]

    if not ok:
        logger.warning("No successful price fetches in sample")
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "error": "no_successful_fetches",
            "results": results,
        }

    n_ok = len(ok)
    pass_price = sum(1 for r in ok if r.get("pass_price"))
    pass_adv = sum(1 for r in ok if r.get("pass_adv"))
    pass_both = sum(1 for r in ok if r.get("pass_both"))

    rate_price = pass_price / n_ok
    rate_adv = pass_adv / n_ok
    rate_both = pass_both / n_ok

    ci_lo, ci_hi = _wilson_ci(rate_both, n_ok)

    prices = sorted(r["price"] for r in ok)
    advs = sorted(r["adv"] for r in ok)

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "candidate_pool_n": n_pool,
        "sample_n": len(sample_tickers),
        "sample_n_nasdaq": n_nasdaq,
        "sample_n_nyse": n_nyse,
        "successful_fetches": n_ok,
        "failed_fetches": len(failed),
        "failure_status_counts": dict(Counter(r["status"] for r in failed)),
        "timing": {
            "total_elapsed_s": round(total_elapsed, 1),
            "per_ticker_median_ms": round(median_ms, 0),
            "per_ticker_p90_ms": round(
                sorted(per_ticker_times)[int(len(per_ticker_times) * 0.9)] * 1000, 0
            ),
        },
        "screen_rates": {
            "pass_price_pct": round(rate_price * 100, 1),
            "pass_adv_pct": round(rate_adv * 100, 1),
            "pass_both_pct": round(rate_both * 100, 1),
        },
        "extrapolation": {
            "N_pool": n_pool,
            "est_survivors": round(n_pool * rate_both),
            "ci_95_lo": round(ci_lo * n_pool),
            "ci_95_hi": round(ci_hi * n_pool),
            "ci_method": "Wilson (95%)",
            "target_was": 3000,
            "note": (
                "Extrapolation assumes the 200-ticker sample is representative of "
                "the full 6,883-name candidate pool. The pool itself is filtered by "
                "name/format only (ETF/FUND/ACQUISITION/preferred/warrant/rights) — "
                "ADRs, BDCs, and micro-cap shells remain and are expected to fail "
                "the investability screen."
            ),
        },
        "price_distribution": {
            "median": statistics.median(prices),
            "below_1": sum(1 for p in prices if p < 1),
            "1_to_5": sum(1 for p in prices if 1 <= p < 5),
            "above_5": sum(1 for p in prices if p >= 5),
        },
        "adv_distribution": {
            "median": statistics.median(advs),
            "below_1m": sum(1 for a in advs if a < 1_000_000),
            "1m_to_5m": sum(1 for a in advs if 1_000_000 <= a < 5_000_000),
            "5m_to_50m": sum(1 for a in advs if 5_000_000 <= a < 50_000_000),
            "above_50m": sum(1 for a in advs if a >= 50_000_000),
        },
        "results": results,
    }
    return summary


# ---------------------------------------------------------------------------
# Runtime extrapolation
# ---------------------------------------------------------------------------


def compute_runtime_extrapolation(screen_summary: dict) -> dict:
    """Extrapolate cold run times from SP1500 baseline."""

    # SP1500 production baseline (from CLAUDE.md + metadata.json)
    sp1500_n = 1504
    sp1500_cold_min = 174.0  # CLAUDE.md: "sp1500 cold ~174 min"
    timeout_min = 270.0  # .github/workflows/compute-rankings.yml timeout-minutes

    # From screen results
    est_survivors = (screen_summary.get("extrapolation") or {}).get("est_survivors", 3544)
    ci_lo_n = (screen_summary.get("extrapolation") or {}).get("ci_95_lo", 3071)
    ci_hi_n = (screen_summary.get("extrapolation") or {}).get("ci_95_hi", 4015)

    per_ticker_median_ms = (screen_summary.get("timing") or {}).get("per_ticker_median_ms", 91)

    # Linear extrapolation (lower bound — ignores parallelism ceiling effects)
    def _cold_min(n: int) -> float:
        return sp1500_cold_min * n / sp1500_n

    cold_screened = _cold_min(est_survivors)
    cold_ci_lo = _cold_min(ci_lo_n)
    cold_ci_hi = _cold_min(ci_hi_n)
    cold_raw_3000 = _cold_min(3000)
    cold_budget_ceil = int(timeout_min / sp1500_cold_min * sp1500_n)

    # Price-screen-only timing (the cheap pre-filter step)
    # Per-ticker: ~91ms measured; with 8 workers: ~91ms / 8 ≈ 11ms effective
    n_pool = 6883
    screen_only_sequential_min = n_pool * per_ticker_median_ms / 1000 / 60
    screen_only_parallel_min = screen_only_sequential_min / 8  # EDGAR_MAX_WORKERS

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "sp1500_baseline": {
            "tickers": sp1500_n,
            "cold_run_min": sp1500_cold_min,
            "per_ticker_s": round(sp1500_cold_min * 60 / sp1500_n, 1),
            "source": "CLAUDE.md + metadata.json",
        },
        "screened_universe": {
            "est_tickers": est_survivors,
            "cold_run_min_linear": round(cold_screened, 0),
            "ci_95_lo_min": round(cold_ci_lo, 0),
            "ci_95_hi_min": round(cold_ci_hi, 0),
            "exceeds_270_min_budget": cold_screened > timeout_min,
            "overage_min": round(max(0, cold_screened - timeout_min), 0),
        },
        "raw_3000": {
            "tickers": 3000,
            "cold_run_min_linear": round(cold_raw_3000, 0),
            "exceeds_270_min_budget": cold_raw_3000 > timeout_min,
        },
        "budget_ceiling": {
            "timeout_min": timeout_min,
            "max_tickers_linear": cold_budget_ceil,
            "note": "Linear ceiling; real ceiling lower due to EDGAR rate-limit non-linearity",
        },
        "security_reviewer_estimate": {
            "estimated_min": 348,
            "assumed_tickers": 3000,
            "our_estimate_at_same_n": round(cold_raw_3000, 0),
            "comparison": "CONFIRMS — our linear estimate at 3k names is ~347 min, closely matching SR's 348 min",
        },
        "price_screen_cost": {
            "n_candidates": n_pool,
            "per_ticker_median_ms": per_ticker_median_ms,
            "sequential_min": round(screen_only_sequential_min, 1),
            "parallel_8workers_min": round(screen_only_parallel_min, 1),
            "note": "One-time setup cost; cached thereafter; negligible vs full compute",
        },
        "key_super_linear_factors": [
            "EDGAR rate-limit (10 req/s ceiling, 8 workers): ~1 req/s sustained → proportional not sub-linear",
            "Form-4 loop: 4345.7s for SP1500; scales ~linearly with ticker count",
            "Tier-2 8-K fetches: 3300.7s for SP1500; per-ticker independent, scales linearly",
            "Cross-source validator: 471.3s; .info calls also rate-limited",
            "EDGAR cold cache: 2x more tickers = 2x more round-trips, no batching",
        ],
        "cron_feasibility": (
            "NOT FEASIBLE in the current single-cron architecture. "
            f"Linear estimate for ~{est_survivors} screened survivors: ~{round(cold_screened, 0):.0f} min cold, "
            f"which exceeds the 270-min GHA budget by ~{round(max(0, cold_screened - timeout_min), 0):.0f} min. "
            "Options for 9.1 Probe: (a) pre-screen step runs Saturday precache, "
            "(b) multi-job GHA matrix parallelism, or (c) tighten screen to ~1500-2000 survivors."
        ),
    }


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------


def mode_population(args: argparse.Namespace) -> None:
    """Analyse the raw SEC population from company_tickers.json."""
    _setup_logging()
    SCOUT_OUT_DIR.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.verify = "/root/.ccr/ca-bundle.crt"

    logger.info("Fetching live company_tickers.json from SEC...")
    live_data = _fetch_live_company_tickers(session)
    if live_data is None:
        logger.warning("Live fetch failed — will rely on bundled parquet for exchange info")

    bundled_df = _load_bundled_parquet()

    report = _classify_population(live_data, bundled_df)

    with POPULATION_JSON.open("w") as f:
        json.dump(report, f, indent=2)
    logger.info("Population report written to %s", POPULATION_JSON)

    # Print summary
    if live := report.get("live_json"):
        print("\n=== LIVE company_tickers.json ===")
        print(f"Total entries: {live['total_entries']:,}")
        print(f"ETF/FUND by name: {live['etf_fund_by_name']}")
        print(f"SPAC/ACQUISITION by name: {live['spac_acquisition_by_name']}")
        print(f"TRUST by name: {live['trust_by_name']}")
        print(f"Preferred (ticker -P*): {live['preferred_by_ticker']}")
        print(f"Warrant/unit: {live['warrant_unit_by_ticker']}")
        print(f"Total clearly-excludable: {live['total_clearly_excludable']:,}")
        print(f"Remaining after filter: {live['remaining_after_name_format_filter']:,}")

    if bundled := report.get("bundled_parquet"):
        print("\n=== Bundled parquet (has exchange column) ===")
        print(f"Total rows: {bundled['total_rows']:,}")
        for exch, cnt in sorted(
            bundled["exchange_distribution"].items(), key=lambda x: -x[1]
        ):
            print(f"  {exch}: {cnt:,}")
        print(f"On Nasdaq+NYSE+CBOE: {bundled['on_main_us_exchanges_nasdaq_nyse_cboe']:,}")
        print(f"OTC: {bundled['on_otc']:,}")
        print(
            f"After name/format filter: {bundled['after_name_format_filter_main_exchanges']:,} "
            f"({bundled['ratio_vs_sp1500']}x SP1500)"
        )


def mode_screen(args: argparse.Namespace) -> None:
    """Run sample screen: price >= $5 AND ADV >= $5M."""
    _setup_logging()
    SCOUT_OUT_DIR.mkdir(parents=True, exist_ok=True)

    n_sample = getattr(args, "sample", 200)
    logger.info("Running price+ADV screen on %d-ticker sample...", n_sample)

    summary = run_screen(n_sample=n_sample)
    if not summary:
        print("Screen failed — no data", file=sys.stderr)
        sys.exit(1)

    with SCREEN_JSON.open("w") as f:
        json.dump(summary, f, indent=2)
    logger.info("Screen results written to %s", SCREEN_JSON)

    print("\n=== SCREEN RESULTS ===")
    print(f"Candidate pool: {summary['candidate_pool_n']:,}")
    print(f"Sample size: {summary['sample_n']} ({summary['sample_n_nasdaq']} Nasdaq + {summary['sample_n_nyse']} NYSE)")
    print(f"Successful fetches: {summary['successful_fetches']}/{summary['sample_n']}")
    print(f"Per-ticker median: {summary['timing']['per_ticker_median_ms']:.0f}ms")
    rates = summary["screen_rates"]
    print(f"Pass price >= ${PRICE_FLOOR_USD:.0f}: {rates['pass_price_pct']}%")
    print(f"Pass ADV >= ${ADV_FLOOR_USD/1e6:.0f}M: {rates['pass_adv_pct']}%")
    print(f"Pass BOTH: {rates['pass_both_pct']}%")
    ext = summary["extrapolation"]
    print(f"\nExtrapolated survivors: ~{ext['est_survivors']:,}")
    print(f"95% CI: [{ext['ci_95_lo']:,}, {ext['ci_95_hi']:,}]")
    print(f"Target was: ~{ext['target_was']:,}")

    # Also compute runtime
    runtime = compute_runtime_extrapolation(summary)
    with RUNTIME_JSON.open("w") as f:
        json.dump(runtime, f, indent=2)
    logger.info("Runtime extrapolation written to %s", RUNTIME_JSON)
    print("\n=== RUNTIME (cold) ===")
    print(
        f"Screened universe (~{ext['est_survivors']:,}): "
        f"{runtime['screened_universe']['cold_run_min_linear']:.0f} min linear estimate"
    )
    print(
        f"270-min budget: {'EXCEEDED by ' + str(runtime['screened_universe']['overage_min']) + ' min' if runtime['screened_universe']['exceeds_270_min_budget'] else 'within budget'}"
    )
    print(f"\n{runtime['cron_feasibility']}")


def mode_runtime(args: argparse.Namespace) -> None:
    """Compute runtime extrapolation from existing screen results."""
    _setup_logging()
    SCOUT_OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not SCREEN_JSON.exists():
        print("ERROR: Run --mode screen first", file=sys.stderr)
        sys.exit(1)

    with SCREEN_JSON.open() as f:
        screen_summary = json.load(f)

    runtime = compute_runtime_extrapolation(screen_summary)
    with RUNTIME_JSON.open("w") as f:
        json.dump(runtime, f, indent=2)
    logger.info("Runtime report written to %s", RUNTIME_JSON)

    # Print
    print("\n=== RUNTIME EXTRAPOLATION ===")
    base = runtime["sp1500_baseline"]
    print(f"SP1500 baseline: {base['tickers']} tickers, {base['cold_run_min']} min cold")
    su = runtime["screened_universe"]
    print(f"Screened (~{su['est_tickers']:,}): {su['cold_run_min_linear']:.0f} min linear")
    print(f"270-min budget: {'EXCEEDED' if su['exceeds_270_min_budget'] else 'ok'}")
    print(f"\n{runtime['cron_feasibility']}")


def mode_report(args: argparse.Namespace) -> None:
    """Synthesize all scout outputs into a text report."""
    _setup_logging()
    SCOUT_OUT_DIR.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []

    def _h(text: str, level: int = 2) -> None:
        lines.append(f"{'#' * level} {text}\n")

    def _p(text: str) -> None:
        lines.append(text + "\n")

    _h("Phase 9.0 Broad Investable US — Scout Report", 1)
    _p(f"Generated: {datetime.now(UTC).isoformat()}")
    _p("")

    if POPULATION_JSON.exists():
        with POPULATION_JSON.open() as f:
            pop = json.load(f)

        _h("1. Raw Population (SEC company_tickers.json)", 2)
        if live := pop.get("live_json"):
            _p(f"**Total entries (live JSON):** {live['total_entries']:,}")
            _p(f"- ETF/FUND by name: {live['etf_fund_by_name']}")
            _p(f"- SPAC/ACQUISITION by name: {live['spac_acquisition_by_name']}")
            _p(f"- TRUST by name (incl. REITs/BDCs): {live['trust_by_name']}")
            _p(f"- Preferred stock (ticker -P*): {live['preferred_by_ticker']}")
            _p(f"- Warrants/units (ticker -W*/UN etc): {live['warrant_unit_by_ticker']}")
            _p(f"- Remaining after format/name filter: {live['remaining_after_name_format_filter']:,}")
            _p("")
            _p("**Classification limits (company_tickers.json is ticker+CIK+title only):**")
            for lim in live.get("classification_limits", []):
                _p(f"  - {lim}")
            _p("")
            _p("**Extra signal needed for reliable classification:**")
            for sig in live.get("extra_signal_needed", []):
                _p(f"  - {sig}")
        if bundled := pop.get("bundled_parquet"):
            _p("")
            _p("**Bundled edgartools parquet** (adds exchange; may be ~1-2 weeks stale):")
            _p(f"  - Total: {bundled['total_rows']:,}")
            for exch, cnt in sorted(
                bundled["exchange_distribution"].items(), key=lambda x: -x[1]
            ):
                _p(f"  - {exch}: {cnt:,}")
            _p(
                f"  - After name/format filter on Nasdaq+NYSE+CBOE: "
                f"{bundled['after_name_format_filter_main_exchanges']:,} "
                f"(~{bundled['ratio_vs_sp1500']}x SP1500)"
            )
    else:
        _h("1. Raw Population", 2)
        _p("No population data. Run `--mode population` first.")

    _p("")
    if SCREEN_JSON.exists():
        with SCREEN_JSON.open() as f:
            screen = json.load(f)

        _h("2. Screen Sizing", 2)
        _p(f"**Sample:** {screen['sample_n']} tickers ({screen['sample_n_nasdaq']} Nasdaq + {screen['sample_n_nyse']} NYSE)")
        _p(f"**Successful fetches:** {screen['successful_fetches']}/{screen['sample_n']}")
        rates = screen.get("screen_rates", {})
        _p(f"**Pass price >= $5:** {rates.get('pass_price_pct')}%")
        _p(f"**Pass ADV >= $5M:** {rates.get('pass_adv_pct')}%")
        _p(f"**Pass BOTH:** {rates.get('pass_both_pct')}%")
        ext = screen.get("extrapolation", {})
        _p("")
        _p(f"**Extrapolated survivors (from N={ext.get('N_pool'):,} pool):** ~{ext.get('est_survivors'):,}")
        _p(f"**95% CI (Wilson):** [{ext.get('ci_95_lo'):,}, {ext.get('ci_95_hi'):,}]")
        _p(f"**Target was:** ~{ext.get('target_was'):,}")
        _p(f"> {ext.get('note', '')}")
        _p("")
        price_d = screen.get("price_distribution", {})
        adv_d = screen.get("adv_distribution", {})
        _p("**Price distribution:**")
        _p(f"  - < $1: {price_d.get('below_1')}, $1-5: {price_d.get('1_to_5')}, >= $5: {price_d.get('above_5')}")
        _p("**ADV distribution:**")
        _p(f"  - < $1M: {adv_d.get('below_1m')}, $1M-5M: {adv_d.get('1m_to_5m')}, $5M-50M: {adv_d.get('5m_to_50m')}, >= $50M: {adv_d.get('above_50m')}")
    else:
        _h("2. Screen Sizing", 2)
        _p("No screen data. Run `--mode screen` first.")

    _p("")
    if RUNTIME_JSON.exists():
        with RUNTIME_JSON.open() as f:
            rt = json.load(f)

        _h("3. Runtime Extrapolation", 2)
        base = rt.get("sp1500_baseline", {})
        _p(f"**SP1500 baseline:** {base.get('tickers')} tickers, {base.get('cold_run_min')} min cold")
        su = rt.get("screened_universe", {})
        _p(f"**Screened (~{su.get('est_tickers'):,}):** {su.get('cold_run_min_linear'):.0f} min cold (linear)")
        _p(f"  CI: [{su.get('ci_95_lo_min'):.0f}, {su.get('ci_95_hi_min'):.0f}] min")
        _p(f"  270-min budget: {'EXCEEDED by ' + str(su.get('overage_min')) + ' min' if su.get('exceeds_270_min_budget') else 'within budget'}")
        raw3k = rt.get("raw_3000", {})
        _p(f"**Raw 3,000:** {raw3k.get('cold_run_min_linear'):.0f} min — {'EXCEEDS' if raw3k.get('exceeds_270_min_budget') else 'within'} 270-min budget")
        sr = rt.get("security_reviewer_estimate", {})
        _p(f"**Security-reviewer estimate:** {sr.get('estimated_min')} min — {sr.get('comparison')}")
        _p("")
        _p("**Price-screen-only cost** (pre-filter step, separate from main cron):")
        ps = rt.get("price_screen_cost", {})
        _p(f"  - {ps.get('n_candidates'):,} candidates, {ps.get('per_ticker_median_ms'):.0f}ms/ticker")
        _p(f"  - Sequential: {ps.get('sequential_min'):.0f} min, with 8 workers: {ps.get('parallel_8workers_min'):.0f} min")
        _p("")
        _p(f"**Cron feasibility verdict:** {rt.get('cron_feasibility', '')}")
        _p("")
        _p("**Key super-linear risk factors:**")
        for factor in rt.get("key_super_linear_factors", []):
            _p(f"  - {factor}")
    else:
        _h("3. Runtime Extrapolation", 2)
        _p("No runtime data. Run `--mode screen` or `--mode runtime` first.")

    report_text = "\n".join(lines)
    with REPORT_MD.open("w") as f:
        f.write(report_text)
    logger.info("Report written to %s", REPORT_MD)
    print(report_text)
    print(f"\n--- Report also written to: {REPORT_MD} ---")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Phase 9.0 Broad Investable US universe scout — dev tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["population", "screen", "runtime", "report"],
        help="Scout mode",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=200,
        help="(screen) Sample size for screen sizing",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.mode == "population":
        mode_population(args)
    elif args.mode == "screen":
        mode_screen(args)
    elif args.mode == "runtime":
        mode_runtime(args)
    elif args.mode == "report":
        mode_report(args)


if __name__ == "__main__":
    main()
