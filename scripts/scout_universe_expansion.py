"""Phase-8 universe expansion scout — dev tool (NOT production wiring).

Investigates whether S&P 400 midcaps or large US-listed ADRs would crack the
AI-pick book under the current scoring rules. Analogous precedent:
``scripts/analysis_veto_counterfactual.py``.

Usage (export EDGAR_USER_AGENT first):

    export EDGAR_USER_AGENT="QuantRank research scout (dack30@gmail.com)"

    # Stage 1: fetch + score up to N midcaps
    python -m scripts.scout_universe_expansion --mode sp400-stage1 --limit 8

    # ADR filing-type probe
    python -m scripts.scout_universe_expansion --mode adr-probe --tickers TSM,MELI,ASML

    # Stage 2: full defense layer for >= 60 composite names
    python -m scripts.scout_universe_expansion --mode sp400-stage2 --tickers-file scout_out/sp400_stage1_summary.json

    # Synthesize report
    python -m scripts.scout_universe_expansion --mode report

DEV TOOL — never imported by production or CI.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import time
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Project root on sys.path so ``compute.*`` imports resolve when invoked as
# ``python -m scripts.scout_universe_expansion`` from the repo root.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from compute import config  # noqa: E402
from compute.ingest.fundamentals import (  # noqa: E402
    fetch_fundamentals,
    fetch_fundamentals_history,
)
from compute.ingest.prices import fetch_prices, fetch_spy_benchmark  # noqa: E402
from compute.ingest.universe import (  # noqa: E402
    _fetch_wikipedia_html,
    _normalize_ticker,
)
from compute.scoring.composite import compute_composite, neutralize_pillar_scores  # noqa: E402
from compute.scoring.pillars import TickerInputs, compute_all_pillars  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCOUT_OUT_DIR = _REPO_ROOT / "scout_out"
SP400_STAGE1_JSONL = SCOUT_OUT_DIR / "sp400_stage1.jsonl"
SP400_STAGE1_SUMMARY = SCOUT_OUT_DIR / "sp400_stage1_summary.json"
SP400_STAGE2_JSONL = SCOUT_OUT_DIR / "sp400_stage2.jsonl"
ADR_PROBE_JSON = SCOUT_OUT_DIR / "adr_probe.json"
REPORT_MD = SCOUT_OUT_DIR / "report.md"
SP400_UNIVERSE_CACHE = SCOUT_OUT_DIR / "sp400_universe.json"

WIKIPEDIA_SP400_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"

# 30-day freshness for the S&P 400 list — scout re-runs don't need daily refreshes
SP400_CACHE_MAX_AGE_DAYS = 30

# AI-pick book threshold: composite >= 65 enters (floor 5, uncapped adaptive rule)
BOOK_COMPOSITE_THRESHOLD = 65.0
NEAR_MISS_BAND_LOW = 60.0

# Default ADR probe list: a mix of 20-F names and known domestic-style 10-K filers
DEFAULT_ADR_TICKERS = [
    "TSM", "ASML", "SAP", "NVO", "AZN", "SHEL", "UL", "TM", "SONY",
    "BABA", "BHP", "RIO", "TTE", "BP", "HSBC", "NVS", "SNY", "GSK",
    "DEO", "BTI", "MUFG", "INFY", "ARM", "SPOT", "SE", "MELI",
]

# Forms that indicate full US-GAAP quarterly filing capability
FULL_GAAP_FORMS = {"10-K", "10-Q"}
ANNUAL_ONLY_FORMS = {"20-F", "40-F", "6-K"}


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


# ---------------------------------------------------------------------------
# S&P 400 universe fetch
# ---------------------------------------------------------------------------

def _parse_sp400_html(html: str) -> pd.DataFrame:
    """Parse the S&P 400 Wikipedia page into a DataFrame.

    The S&P 400 Wikipedia table uses the same column structure as the S&P 500
    page; we reuse the same parsing logic from compute/ingest/universe.py.
    CIK column may be absent on the S&P 400 page — we tolerate that.
    """
    soup = BeautifulSoup(html, "lxml")
    # The S&P 400 page may have multiple wikitables; find the constituents one
    tables = soup.find_all("table", {"class": "wikitable"})
    if not tables:
        raise ValueError("Could not find any wikitable on S&P 400 Wikipedia page.")

    df: pd.DataFrame | None = None
    for table in tables:
        try:
            candidate = pd.read_html(StringIO(str(table)))[0]
        except Exception:
            continue
        # Must have Symbol/Security columns
        cols_lower = {str(c).lower(): c for c in candidate.columns}
        if "symbol" in cols_lower or "ticker" in cols_lower:
            df = candidate
            break

    if df is None:
        raise ValueError("Could not find S&P 400 constituents table on Wikipedia page.")

    # Normalize column names — S&P 400 page uses "Ticker" or "Symbol"
    col_map: dict[str, str] = {}
    for col in df.columns:
        cl = str(col).lower()
        if cl in ("symbol", "ticker"):
            col_map[col] = "wiki_ticker"
        elif cl in ("security", "company"):
            col_map[col] = "name"
        elif "sector" in cl and "sub" not in cl:
            col_map[col] = "sector"
        elif "sub" in cl and "industry" in cl:
            col_map[col] = "sub_industry"
        elif cl == "cik":
            col_map[col] = "cik"

    df = df.rename(columns=col_map)

    if "wiki_ticker" not in df.columns:
        raise ValueError(f"Wikipedia S&P 400 table missing ticker column. Columns: {list(df.columns)}")

    df["wiki_ticker"] = df["wiki_ticker"].astype(str)
    df["ticker"] = df["wiki_ticker"].map(_normalize_ticker)

    # Sector / name fallbacks
    if "name" not in df.columns:
        df["name"] = df["ticker"]
    else:
        df["name"] = df["name"].astype(str)

    if "sector" not in df.columns:
        df["sector"] = "Unknown"
    else:
        df["sector"] = df["sector"].astype(str).fillna("Unknown")

    if "sub_industry" not in df.columns:
        df["sub_industry"] = None

    if "cik" not in df.columns:
        df["cik"] = None
    else:
        # CIK may be numeric — zero-pad to 10 digits like the S&P 500 path does
        def _safe_cik(v: Any) -> str | None:
            if pd.isna(v) or str(v).strip() in ("", "nan"):
                return None
            try:
                return str(int(float(str(v)))).zfill(10)
            except (ValueError, TypeError):
                return None
        df["cik"] = df["cik"].map(_safe_cik)

    df = df[["ticker", "name", "sector", "sub_industry", "cik", "wiki_ticker"]]
    df = df.drop_duplicates(subset=["ticker"]).reset_index(drop=True)
    return df


def fetch_sp400_constituents(force_refresh: bool = False) -> pd.DataFrame:
    """Fetch S&P 400 constituents from Wikipedia, caching to scout_out/."""
    SCOUT_OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not force_refresh and SP400_UNIVERSE_CACHE.exists():
        age_days = (time.time() - SP400_UNIVERSE_CACHE.stat().st_mtime) / 86400
        if age_days < SP400_CACHE_MAX_AGE_DAYS:
            logger.info("S&P 400 cache hit (age=%.1f days)", age_days)
            with SP400_UNIVERSE_CACHE.open() as f:
                data = json.load(f)
            return pd.DataFrame(data)

    logger.info("Fetching S&P 400 constituents from Wikipedia")
    html = _fetch_wikipedia_html(WIKIPEDIA_SP400_URL)
    df = _parse_sp400_html(html)

    with SP400_UNIVERSE_CACHE.open("w") as f:
        json.dump(df.to_dict(orient="records"), f)
    logger.info("Cached %d S&P 400 constituents to %s", len(df), SP400_UNIVERSE_CACHE)
    return df


# ---------------------------------------------------------------------------
# Current S&P 500 cache loader — for building the combined cross-section
# ---------------------------------------------------------------------------

def _load_sp500_current_composites() -> dict[str, float] | None:
    """Load current S&P 500 composite scores from rankings.json if available.

    Returns dict[ticker → composite_score] or None if unavailable. Used to
    determine whether we have a warm 500 cross-section for combined ranking.
    """
    rankings_path = config.DATA_DIR / "rankings.json"
    if not rankings_path.exists():
        return None
    try:
        with rankings_path.open() as f:
            data = json.load(f)
        # rankings.json is a plain list of stock summary dicts
        rankings_list = data if isinstance(data, list) else data.get("stocks", [])
        return {s["ticker"]: s["composite_score"] for s in rankings_list}
    except Exception as e:
        logger.warning("Could not load rankings.json: %s", e)
        return None


def _load_sp500_pillar_inputs_from_cache() -> dict[str, TickerInputs] | None:
    """Attempt to reconstruct a lightweight S&P 500 TickerInputs dict from
    per-ticker caches so we can form a combined cross-section for pillar scoring.

    LIMITATION: This is APPROXIMATE — we can only reconstruct TickerInputs from
    the disk caches, and the production cross-section was built on a specific
    run date with a specific price. We include only tickers for which BOTH
    fundamentals cache and prices cache exist. Missing tickers are silently
    excluded — this means the cross-section may be smaller than production's 502.

    Returns None if we cannot load enough data (fewer than 50 tickers).
    """
    from compute.ingest.fundamentals import fetch_fundamentals  # pylint: disable=reimported

    universe_cache = config.UNIVERSE_CACHE
    if not universe_cache.exists():
        return None
    try:
        sp500_df = pd.read_parquet(universe_cache)
    except Exception as e:
        logger.warning("Could not read S&P 500 universe cache: %s", e)
        return None

    inputs: dict[str, TickerInputs] = {}
    logger.info("Checking S&P 500 price/fundamentals caches for cross-section (%d tickers)...", len(sp500_df))

    for _, row in sp500_df.iterrows():
        ticker = str(row["ticker"])
        cik = str(row.get("cik") or "")
        sector = str(row.get("sector") or "Unknown")

        prices_path = config.PRICES_CACHE_DIR / f"{ticker}.parquet"
        fund_path = config.FUNDAMENTALS_CACHE_DIR / f"{cik}.parquet" if cik else None

        if not prices_path.exists():
            continue
        if fund_path is None or not fund_path.exists():
            continue

        try:
            prices = pd.read_parquet(prices_path)
            if prices.empty:
                continue
            col = "Adj Close" if "Adj Close" in prices.columns else "Close"
            if col not in prices.columns:
                continue
            last = prices[col].dropna()
            if last.empty:
                continue
            current_price = float(last.iloc[-1])
            if math.isnan(current_price) or current_price <= 0:
                continue
        except Exception:
            continue

        # Snapshot: attempt cached read without network — pass empty CIK to trigger
        # cache-only path. Actually, fetch_fundamentals reads from cache if fresh.
        try:
            snap = fetch_fundamentals(ticker, cik)
        except Exception:
            snap = None

        inputs[ticker] = TickerInputs(
            snapshot=snap,
            prices=prices,
            benchmark_prices=None,
            current_price=current_price,
            sector=sector,
            history=None,
        )

    logger.info("Loaded %d S&P 500 tickers from warm cache for cross-section", len(inputs))
    if len(inputs) < 50:
        return None
    return inputs


# ---------------------------------------------------------------------------
# Stage-1 helpers
# ---------------------------------------------------------------------------

def _already_processed_tickers(jsonl_path: Path) -> set[str]:
    """Return the set of tickers already written to a JSONL file."""
    if not jsonl_path.exists():
        return set()
    seen: set[str] = set()
    with jsonl_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                t = obj.get("ticker")
                if t:
                    seen.add(t)
            except json.JSONDecodeError:
                pass
    return seen


def _score_ticker_batch(
    ticker_rows: list[dict],
    *,
    sp500_inputs: dict[str, TickerInputs] | None,
    benchmark: pd.DataFrame | None,
) -> list[dict]:
    """Fetch data + compute pillar scores for a batch of midcap tickers.

    Each element of ticker_rows is a dict with keys: ticker, name, sector,
    sub_industry, cik.

    Returns a list of result dicts (one per ticker, including degradation notes).
    Cross-sectional scoring: if sp500_inputs is provided, scores midcaps within
    the COMBINED (S&P 500 + midcap batch) cross-section. Otherwise scores within
    the midcap-batch-only cross-section (noted as a caveat).
    """
    results: list[dict] = []

    # Step 1: fetch prices for each midcap ticker
    prices_by_ticker: dict[str, pd.DataFrame] = {}
    current_prices: dict[str, float] = {}

    for row in ticker_rows:
        ticker = row["ticker"]
        try:
            prices = fetch_prices(ticker)
            if prices is not None and not prices.empty:
                col = "Adj Close" if "Adj Close" in prices.columns else "Close"
                if col in prices.columns:
                    last = prices[col].dropna()
                    if not last.empty:
                        cp = float(last.iloc[-1])
                        if not math.isnan(cp) and cp > 0:
                            prices_by_ticker[ticker] = prices
                            current_prices[ticker] = cp
        except Exception as e:
            logger.warning("[scout] Price fetch failed for %s: %s", ticker, e)

    # Step 2: fetch fundamentals + history for each midcap ticker.
    # CIK resolution: the S&P 400 Wikipedia page carries no CIK column (all
    # None at parse time), so we must resolve ticker → CIK via edgartools'
    # Company(ticker) lookup.  Precedence:
    #   1. CIK from the row (wiki-provided, if ever populated)
    #   2. CIK captured from FundamentalsSnapshot.cik after fetch_fundamentals
    #      succeeds — _build_snapshot stores it when Company(cik or ticker)
    #      resolves via the numeric CIK path.
    #   3. Explicit Company(ticker).cik lookup as a last resort.
    # fetch_fundamentals_history(cik) calls Company(cik) directly and will
    # query a random company when given an empty string, so a real CIK is
    # required before calling it.
    snapshots: dict[str, Any] = {}
    histories: dict[str, pd.DataFrame] = {}
    resolved_ciks: dict[str, str] = {}
    for row in ticker_rows:
        ticker = row["ticker"]
        cik = str(row.get("cik") or "")
        try:
            snap = fetch_fundamentals(ticker, cik)
            snapshots[ticker] = snap
            # Attempt to harvest the resolved CIK from the snapshot itself.
            # _build_snapshot writes the cik it was called with into the
            # snapshot; when cik was '' the snapshot also has '' — so we
            # fall through to the explicit lookup below in that case.
            if snap is not None and snap.cik and snap.cik.strip():
                cik = snap.cik.strip()
        except Exception as e:
            logger.warning("[scout] Fundamentals failed for %s: %s", ticker, e)
            snapshots[ticker] = None

        # Resolve CIK from Company(ticker) if still missing.
        if not cik:
            try:
                from edgar import Company as _Company  # already imported at module top
                co = _Company(ticker)
                raw_cik = getattr(co, "cik", None)
                if raw_cik is not None:
                    cik = str(int(str(raw_cik))).zfill(10)
                    logger.debug("[scout] Resolved CIK for %s via ticker lookup: %s", ticker, cik)
            except Exception as e:
                logger.warning("[scout] CIK lookup failed for %s: %s", ticker, e)

        resolved_ciks[ticker] = cik

        try:
            if cik:
                hist = fetch_fundamentals_history(cik)
            else:
                logger.warning("[scout] No CIK resolved for %s — history skipped", ticker)
                hist = pd.DataFrame()
            histories[ticker] = hist
        except Exception as e:
            logger.warning("[scout] History failed for %s (cik=%s): %s", ticker, cik, e)
            histories[ticker] = pd.DataFrame()

    # Step 3: build TickerInputs for midcaps (only those with prices)
    midcap_inputs: dict[str, TickerInputs] = {}
    for row in ticker_rows:
        ticker = row["ticker"]
        if ticker not in current_prices:
            continue
        midcap_inputs[ticker] = TickerInputs(
            snapshot=snapshots.get(ticker),
            prices=prices_by_ticker.get(ticker),
            benchmark_prices=benchmark,
            current_price=current_prices[ticker],
            sector=str(row.get("sector") or "Unknown"),
            history=histories.get(ticker),
        )

    if not midcap_inputs:
        logger.warning("[scout] No midcap tickers with valid prices in batch")
        return results

    # Step 4: form combined cross-section
    combined_inputs: dict[str, TickerInputs]
    cross_section_note: str
    if sp500_inputs:
        combined_inputs = {**sp500_inputs, **midcap_inputs}
        cross_section_note = "combined_sp500_plus_midcap"
    else:
        combined_inputs = midcap_inputs
        cross_section_note = (
            "midcap_only_CAVEAT_percentile_pillars_biased "
            "(S&P 500 cache cold or unavailable — sector-relative pillars "
            "ranked within midcap cohort only, not vs the full 500)"
        )

    # Step 5: compute pillars cross-sectionally
    try:
        pillar_df = compute_all_pillars(combined_inputs)
        pillar_df, imputed_by_ticker = neutralize_pillar_scores(pillar_df)
        composite_scores = compute_composite(pillar_df)
    except Exception as e:
        logger.error("[scout] Pillar/composite computation failed: %s", e)
        return results

    # Step 6: assemble per-ticker results (midcaps only)
    pillar_cols = ["quality", "value", "growth", "momentum", "health", "profitability", "technical", "risk"]

    for row in ticker_rows:
        ticker = row["ticker"]
        if ticker not in current_prices:
            results.append({
                "ticker": ticker,
                "name": row.get("name"),
                "sector": row.get("sector"),
                "status": "no_price",
                "composite": None,
                "pillars": {},
                "imputed_pillars": [],
                "degradation_notes": ["price_fetch_failed"],
                "cross_section_note": cross_section_note,
                "fundamentals_ok": False,
                "history_ok": False,
            })
            continue

        snap = snapshots.get(ticker)
        hist = histories.get(ticker, pd.DataFrame())

        fundamentals_ok = snap is not None
        history_ok = hist is not None and not hist.empty

        composite = None
        pillars = {}
        imputed = []

        if ticker in composite_scores.index:
            composite = round(float(composite_scores[ticker]), 2)
        if ticker in pillar_df.index:
            row_pillars = pillar_df.loc[ticker]
            for col in pillar_cols:
                v = row_pillars.get(col)
                pillars[col] = round(float(v), 2) if v is not None and not math.isnan(float(v)) else None
        imputed = imputed_by_ticker.get(ticker, [])

        degradation_notes: list[str] = []
        if not fundamentals_ok:
            degradation_notes.append("fundamentals_failed_all_financial_pillars_neutral")
        if not history_ok:
            degradation_notes.append("history_unavailable_growth_pillar_degraded")
        if imputed:
            degradation_notes.append(f"imputed_pillars:{','.join(imputed)}")

        # Note which specific pillar metrics couldn't fire
        null_pillars = [col for col in pillar_cols if pillars.get(col) is None]
        if null_pillars:
            degradation_notes.append(f"null_pillar_scores:{','.join(null_pillars)}")

        results.append({
            "ticker": ticker,
            "name": row.get("name"),
            "sector": row.get("sector"),
            "status": "scored",
            "composite": composite,
            "pillars": pillars,
            "imputed_pillars": imputed,
            "degradation_notes": degradation_notes,
            "cross_section_note": cross_section_note,
            "fundamentals_ok": fundamentals_ok,
            "history_ok": history_ok,
            "current_price": current_prices.get(ticker),
        })

    return results


# ---------------------------------------------------------------------------
# Mode: sp400-stage1
# ---------------------------------------------------------------------------

def mode_sp400_stage1(args: argparse.Namespace) -> None:
    """Fetch + score S&P 400 midcaps at stage 1 (no event-layer)."""
    _setup_logging()
    SCOUT_OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Require EDGAR_USER_AGENT before any EDGAR calls
    if not os.environ.get("EDGAR_USER_AGENT"):
        print(
            "ERROR: EDGAR_USER_AGENT not set. Export it first:\n"
            '  export EDGAR_USER_AGENT="QuantRank research scout (dack30@gmail.com)"',
            file=sys.stderr,
        )
        sys.exit(1)

    # Fetch S&P 400 universe
    sp400_df = fetch_sp400_constituents()
    logger.info("S&P 400 universe: %d tickers", len(sp400_df))

    # Filter to specific tickers if requested
    if args.tickers:
        requested = {t.strip().upper() for t in args.tickers.split(",")}
        sp400_df = sp400_df[sp400_df["ticker"].isin(requested)].reset_index(drop=True)
        logger.info("Filtered to %d requested tickers", len(sp400_df))

    # Apply limit
    if args.limit and args.limit > 0:
        sp400_df = sp400_df.head(args.limit)
        logger.info("Limiting to first %d tickers", len(sp400_df))

    # --force-rescore: truncate the JSONL so all tickers re-score from scratch,
    # reusing on-disk ingest caches (prices + fundamentals snapshots); only the
    # annual-history fetch adds network time.
    force_rescore = getattr(args, "force_rescore", False)
    if force_rescore and SP400_STAGE1_JSONL.exists():
        logger.info("--force-rescore: truncating %s for fresh re-score", SP400_STAGE1_JSONL)
        SP400_STAGE1_JSONL.write_text("")

    # Check which tickers are already done (resumable)
    already_done = set() if force_rescore else _already_processed_tickers(SP400_STAGE1_JSONL)
    pending = sp400_df[~sp400_df["ticker"].isin(already_done)].reset_index(drop=True)
    logger.info(
        "%d tickers to process (%d already in JSONL, %d remaining)",
        len(sp400_df), len(already_done), len(pending)
    )

    if pending.empty:
        logger.info("All tickers already processed — skipping to summary")
    else:
        # Try to load warm S&P 500 cross-section
        sp500_inputs = _load_sp500_pillar_inputs_from_cache()
        if sp500_inputs:
            logger.info(
                "Warm S&P 500 cross-section loaded: %d tickers — midcaps will be "
                "scored within combined universe (most honest).",
                len(sp500_inputs),
            )
        else:
            logger.warning(
                "S&P 500 cache COLD or unavailable — midcaps will be scored within "
                "midcap-only cross-section. CAVEAT: sector-relative percentile pillars "
                "(quality, value, growth, profitability) will be biased. "
                "Re-run after a warm 'python -m compute.main' to get the combined cross-section."
            )

        # Fetch SPY benchmark for beta
        try:
            benchmark = fetch_spy_benchmark()
        except Exception as e:
            logger.warning("SPY benchmark unavailable: %s — beta will be NaN", e)
            benchmark = None

        # Process in batches of 1 (sequential outer loop; inner fetchers parallelize)
        rows_to_process = pending.to_dict(orient="records")
        logger.info("Processing %d tickers one at a time...", len(rows_to_process))

        with SP400_STAGE1_JSONL.open("a") as out_f:
            for i, row in enumerate(rows_to_process):
                ticker = row["ticker"]
                logger.info("[%d/%d] Processing %s", i + 1, len(rows_to_process), ticker)
                batch_results = _score_ticker_batch(
                    [row],
                    sp500_inputs=sp500_inputs,
                    benchmark=benchmark,
                )
                for result in batch_results:
                    out_f.write(json.dumps(result) + "\n")
                    out_f.flush()

    # Build summary
    _build_stage1_summary()


def _dominant_cross_section_note(records: list[dict]) -> str:
    """Return the cross_section_note that applies to the MAJORITY of records.

    The summary previously used records[0] which could be a cold-cache record
    from a prior partial run, causing the note to say CAVEAT even when 390+/400
    records were scored on the combined warm path.  We pick the note held by
    the most records; ties break in favour of ``combined_sp500_plus_midcap``
    (honest mode beats caveat mode in tie-breaking).
    """
    if not records:
        return "no_data"
    from collections import Counter
    note_counts: Counter[str] = Counter(
        r.get("cross_section_note", "unknown") for r in records
    )
    if not note_counts:
        return "unknown"
    # If combined mode is present at all, pick it when it ties with CAVEAT
    # (it is the honest representation of what most tickers were scored on).
    most_common = note_counts.most_common()
    top_note, top_count = most_common[0]
    if len(most_common) > 1:
        combined_key = "combined_sp500_plus_midcap"
        combined_count = note_counts.get(combined_key, 0)
        if combined_count >= top_count:
            return combined_key
    return top_note


def _build_stage1_summary() -> None:
    """Read the JSONL and write a summary JSON."""
    if not SP400_STAGE1_JSONL.exists():
        logger.warning("No stage-1 JSONL found; nothing to summarize")
        return

    records: list[dict] = []
    with SP400_STAGE1_JSONL.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    scored = [r for r in records if r.get("status") == "scored" and r.get("composite") is not None]
    composites = [r["composite"] for r in scored]

    ge65 = [r for r in scored if r["composite"] >= BOOK_COMPOSITE_THRESHOLD]
    band60_65 = [r for r in scored if NEAR_MISS_BAND_LOW <= r["composite"] < BOOK_COMPOSITE_THRESHOLD]

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_tickers": len(records),
        "scored_count": len(scored),
        "no_price_count": len([r for r in records if r.get("status") == "no_price"]),
        "composite_ge65_count": len(ge65),
        "composite_60_65_band_count": len(band60_65),
        "composite_ge65_tickers": sorted(
            [(r["ticker"], r["composite"]) for r in ge65], key=lambda x: -x[1]
        ),
        "composite_60_65_band_tickers": sorted(
            [(r["ticker"], r["composite"]) for r in band60_65], key=lambda x: -x[1]
        ),
        "composite_stats": {
            "mean": round(sum(composites) / len(composites), 2) if composites else None,
            "median": round(float(pd.Series(composites).median()), 2) if composites else None,
            "p25": round(float(pd.Series(composites).quantile(0.25)), 2) if composites else None,
            "p75": round(float(pd.Series(composites).quantile(0.75)), 2) if composites else None,
            "min": round(min(composites), 2) if composites else None,
            "max": round(max(composites), 2) if composites else None,
        },
        "degradation_summary": _degradation_summary(records),
        "cross_section_note": _dominant_cross_section_note(records),
        "top30_by_composite": sorted(
            [
                {
                    "ticker": r["ticker"],
                    "name": r.get("name"),
                    "sector": r.get("sector"),
                    "composite": r["composite"],
                    "pillars": r.get("pillars", {}),
                    "degradation_notes": r.get("degradation_notes", []),
                }
                for r in scored
            ],
            key=lambda x: -(x["composite"] or 0),
        )[:30],
    }

    with SP400_STAGE1_SUMMARY.open("w") as f:
        json.dump(summary, f, indent=2)
    logger.info("Stage-1 summary written to %s", SP400_STAGE1_SUMMARY)

    # Print quick summary
    print("\n=== Stage-1 Summary ===")
    print(f"Total: {summary['total_tickers']}  Scored: {summary['scored_count']}")
    print(f"Composite >= {BOOK_COMPOSITE_THRESHOLD}: {summary['composite_ge65_count']} tickers")
    print(f"Near-miss {NEAR_MISS_BAND_LOW}-{BOOK_COMPOSITE_THRESHOLD}: {summary['composite_60_65_band_count']} tickers")
    if summary["composite_ge65_tickers"]:
        print(f"Book-eligible midcaps: {summary['composite_ge65_tickers']}")
    if summary["composite_60_65_band_tickers"]:
        print(f"Near-miss midcaps: {summary['composite_60_65_band_tickers']}")


def _degradation_summary(records: list[dict]) -> dict:
    """Count how many tickers had each type of degradation."""
    counter: dict[str, int] = {}
    for r in records:
        for note in r.get("degradation_notes", []):
            # Normalize: strip dynamic parts after ':'
            key = note.split(":")[0]
            counter[key] = counter.get(key, 0) + 1
    return counter


# ---------------------------------------------------------------------------
# Mode: adr-probe
# ---------------------------------------------------------------------------

def _probe_edgar_submissions(ticker: str) -> dict:
    """Query EDGAR submissions endpoint for one ticker.

    Returns dict with:
      - forms_filed: set of unique form types from recent filings
      - has_quarterly: bool — does it have 10-Q-style quarterly forms
      - has_ifrs_namespace: bool — ifrs-full namespace in companyfacts
      - form_sample: first 10 recent forms
      - error: str or None
    """
    try:
        from edgar import Company, set_identity  # type: ignore
        ua = os.environ.get("EDGAR_USER_AGENT")
        if ua:
            set_identity(ua)
        company = Company(ticker)
        if company is None:
            return {"error": f"Company({ticker!r}) returned None", "forms_filed": set(), "has_quarterly": False, "has_ifrs_namespace": None, "non_null_gaap_fields": 0}

        # Get recent filings
        filings = company.get_filings()
        forms: set[str] = set()
        form_sample: list[str] = []
        if filings is not None:
            try:
                # edgartools returns a Filings object — iterate
                for filing in list(filings)[:50]:
                    try:
                        form = str(getattr(filing, "form", "") or "").strip()
                        if form:
                            forms.add(form)
                            if len(form_sample) < 10:
                                form_sample.append(form)
                    except Exception:
                        pass
            except Exception:
                pass

        has_quarterly = bool(forms & {"10-Q", "6-K"})
        has_10k = bool(forms & {"10-K", "20-F", "40-F"})

        # Check companyfacts for ifrs-full namespace
        has_ifrs_namespace: bool | None = None
        non_null_gaap_fields: int = 0
        try:
            facts = company.facts
            if facts is not None:
                # Attempt to access ifrs-full namespace
                try:
                    ifrs_data = facts.ifrs
                    has_ifrs_namespace = ifrs_data is not None
                except Exception:
                    has_ifrs_namespace = False

                # Try to run the production fundamentals extractor to count non-null fields
                try:
                    snap = fetch_fundamentals(ticker, "")
                    if snap is not None:
                        from compute.ingest.fundamentals import ALL_METRIC_KEYS  # type: ignore
                        non_null_gaap_fields = sum(
                            1 for k in ALL_METRIC_KEYS
                            if getattr(snap, k, None) is not None
                        )
                except Exception:
                    non_null_gaap_fields = 0
        except Exception:
            has_ifrs_namespace = None

        return {
            "forms_filed": sorted(forms),
            "has_quarterly": has_quarterly,
            "has_10k_or_annual": has_10k,
            "has_ifrs_namespace": has_ifrs_namespace,
            "non_null_gaap_fields": non_null_gaap_fields,
            "form_sample": form_sample,
            "error": None,
        }
    except Exception as e:
        return {
            "forms_filed": [],
            "has_quarterly": False,
            "has_10k_or_annual": False,
            "has_ifrs_namespace": None,
            "non_null_gaap_fields": 0,
            "form_sample": [],
            "error": str(e),
        }


def _adr_verdict(probe: dict) -> str:
    """Classify an ADR probe result into one of three verdicts."""
    if probe.get("error") and not probe.get("forms_filed"):
        return "NO_DATA"
    forms = set(probe.get("forms_filed", []))
    # Full US-GAAP quarterly filer
    if "10-K" in forms or "10-Q" in forms:
        if probe.get("non_null_gaap_fields", 0) >= 5:
            return "SCOREABLE_FULL"
        # Has forms but extraction failed
        return "SCOREABLE_PARTIAL"
    # Annual-only foreign filer
    if forms & {"20-F", "40-F", "6-K"}:
        return "ANNUAL_ONLY"
    if not forms:
        return "NO_DATA"
    # Has some filings but not the expected ones
    return "ANNUAL_ONLY"


def mode_adr_probe(args: argparse.Namespace) -> None:
    """Probe EDGAR filing types + tag resolution for ADR tickers."""
    _setup_logging()
    SCOUT_OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not os.environ.get("EDGAR_USER_AGENT"):
        print(
            "ERROR: EDGAR_USER_AGENT not set. Export it first:\n"
            '  export EDGAR_USER_AGENT="QuantRank research scout (dack30@gmail.com)"',
            file=sys.stderr,
        )
        sys.exit(1)

    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
    else:
        tickers = DEFAULT_ADR_TICKERS

    logger.info("Probing %d ADR tickers: %s", len(tickers), tickers)
    results: dict[str, dict] = {}

    for ticker in tickers:
        logger.info("Probing %s...", ticker)
        probe = _probe_edgar_submissions(ticker)
        verdict = _adr_verdict(probe)
        results[ticker] = {**probe, "verdict": verdict}
        logger.info(
            "  %s: verdict=%s forms=%s non_null_gaap=%d",
            ticker,
            verdict,
            probe.get("forms_filed", [])[:5],
            probe.get("non_null_gaap_fields", 0),
        )

    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "tickers_probed": tickers,
        "results": results,
        "verdict_counts": {
            v: sum(1 for r in results.values() if r.get("verdict") == v)
            for v in ["SCOREABLE_FULL", "SCOREABLE_PARTIAL", "ANNUAL_ONLY", "NO_DATA"]
        },
    }

    with ADR_PROBE_JSON.open("w") as f:
        json.dump(output, f, indent=2)
    logger.info("ADR probe written to %s", ADR_PROBE_JSON)

    # Print compact table
    print("\n=== ADR Probe Results ===")
    print(f"{'Ticker':<8} {'Verdict':<20} {'Forms (sample)':<35} {'GAAP fields'}")
    print("-" * 85)
    for ticker, r in results.items():
        forms_str = ",".join(r.get("form_sample", [])[:4]) or "(none)"
        print(f"{ticker:<8} {r['verdict']:<20} {forms_str:<35} {r.get('non_null_gaap_fields', 0)}")
    print()
    print("Verdict counts:", output["verdict_counts"])


# ---------------------------------------------------------------------------
# Mode: sp400-stage2
# ---------------------------------------------------------------------------

def mode_sp400_stage2(args: argparse.Namespace) -> None:
    """Run defense-layer flags for tickers with composite >= 60.

    Only runs vetoes/flags that can be computed per-ticker without the full
    universe cross-section. Flags that require cross-sectional percentiles
    (sloan_accruals_top_decile, net_issuance_top_decile) are marked as SKIPPED
    because they require the full combined universe to compute honestly.
    """
    _setup_logging()
    SCOUT_OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not os.environ.get("EDGAR_USER_AGENT"):
        print(
            "ERROR: EDGAR_USER_AGENT not set.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load tickers from file or stage-1 summary
    tickers_file = args.tickers_file if hasattr(args, "tickers_file") and args.tickers_file else str(SP400_STAGE1_SUMMARY)
    tickers_to_run: list[str] = []

    if Path(tickers_file).exists():
        with open(tickers_file) as f:
            data = json.load(f)
        # Extract tickers from stage-1 summary that are >= 60 composite
        for entry in data.get("composite_ge65_tickers", []):
            tickers_to_run.append(entry[0])
        for entry in data.get("composite_60_65_band_tickers", []):
            tickers_to_run.append(entry[0])
        logger.info("Loaded %d tickers from %s for stage-2 defense pass", len(tickers_to_run), tickers_file)
    else:
        logger.warning("No tickers-file found at %s; nothing to run", tickers_file)
        return

    if not tickers_to_run:
        logger.info("No tickers in >= 60 composite band; stage-2 has nothing to evaluate")
        return

    # Flags that CAN be run per-ticker without cross-sectional percentile ranking:
    # - altman_distress: absolute threshold on Z-score (no cross-section needed)
    # - data_quality_input_corruption: absolute threshold on TBVPS/revenue
    # - stale_filing_hard: absolute filing-lag check
    # - non_reliance_filing: per-ticker EDGAR 8-K fetch (independent)
    # - going_concern_disclosure: per-ticker 10-K text scan (independent)
    # - beneish_manipulation: per-ticker ratio composite (no cross-section)
    # - dechow_f: per-ticker ratio composite (no cross-section)
    #
    # Flags that CANNOT be run honestly without the full universe cross-section:
    SKIPPED_FLAGS = [
        "sloan_accruals_top_decile",
        "net_issuance_top_decile",
    ]
    logger.info(
        "SKIPPED flags (require full universe cross-section for honest percentile ranking): %s",
        SKIPPED_FLAGS,
    )

    from compute.scoring.beneish import compute_beneish
    from compute.scoring.dechow_f import compute_dechow_f
    from compute.scoring.risk_overlay import (
        _data_quality_input_corruption,
        check_share_count_extraction_missing,
    )
    from compute.valuation.applicability import stale_filing_status

    already_done = _already_processed_tickers(SP400_STAGE2_JSONL)

    with SP400_STAGE2_JSONL.open("a") as out_f:
        for ticker in tickers_to_run:
            if ticker in already_done:
                logger.info("[stage2] %s already done, skipping", ticker)
                continue
            logger.info("[stage2] Processing %s...", ticker)

            # Fetch snapshot + history (may hit cache from stage-1).
            # CIK resolution: same pattern as _score_ticker_batch — resolve via
            # Company(ticker).cik because the S&P 400 rows carry no wiki CIK.
            # Beneish + Dechow need the annual history, which fetch_fundamentals_
            # history() keys by CIK; passing "" calls Company("") and fetches a
            # random company's history.
            s2_cik = ""
            try:
                snap = fetch_fundamentals(ticker, "")
                if snap is not None and snap.cik and snap.cik.strip():
                    s2_cik = snap.cik.strip()
            except Exception as e:
                snap = None
                logger.warning("[stage2] fundamentals failed for %s: %s", ticker, e)

            if not s2_cik:
                try:
                    from edgar import Company as _Company
                    _co = _Company(ticker)
                    _raw = getattr(_co, "cik", None)
                    if _raw is not None:
                        s2_cik = str(int(str(_raw))).zfill(10)
                        logger.debug("[stage2] Resolved CIK for %s: %s", ticker, s2_cik)
                except Exception as e:
                    logger.warning("[stage2] CIK lookup failed for %s: %s", ticker, e)

            try:
                if s2_cik:
                    hist = fetch_fundamentals_history(s2_cik)
                else:
                    logger.warning("[stage2] No CIK resolved for %s — history skipped", ticker)
                    hist = pd.DataFrame()
            except Exception as e:
                logger.warning("[stage2] History failed for %s (cik=%s): %s", ticker, s2_cik, e)
                hist = pd.DataFrame()

            flags: dict[str, bool | None] = {}
            flag_notes: list[str] = []

            # altman_distress
            from compute.features import health as health_features
            if snap is not None:
                try:
                    z = health_features.altman_z_double_prime(snap)
                    from compute.scoring.risk_overlay import ALTMAN_DISTRESS_THRESHOLD
                    flags["altman_distress"] = z is not None and z < ALTMAN_DISTRESS_THRESHOLD
                except Exception:
                    flags["altman_distress"] = None
                    flag_notes.append("altman_z_compute_failed")
            else:
                flags["altman_distress"] = None
                flag_notes.append("no_snapshot_altman_skipped")

            # data_quality_input_corruption
            try:
                flags["data_quality_input_corruption"] = _data_quality_input_corruption(snap)
            except Exception:
                flags["data_quality_input_corruption"] = None
                flag_notes.append("data_quality_check_failed")

            # share_count_extraction_missing
            try:
                flags["share_count_extraction_missing"] = check_share_count_extraction_missing(snap)
            except Exception:
                flags["share_count_extraction_missing"] = None

            # stale_filing_hard
            if snap is not None and snap.latest_filed_date is not None:
                from datetime import date
                lag = (date.today() - snap.latest_filed_date).days
                flags["stale_filing_hard"] = stale_filing_status(lag) == "hard"
                flags["filing_lag_days"] = lag
            else:
                flags["stale_filing_hard"] = None
                flag_notes.append("no_filing_date_stale_check_skipped")

            # beneish_manipulation
            try:
                b_result = compute_beneish(snap, hist if not hist.empty else None)
                flags["beneish_manipulation"] = b_result.beneish_manipulation
                flags["beneish_m_score"] = b_result.m_score
            except Exception:
                flags["beneish_manipulation"] = None
                flags["beneish_m_score"] = None
                flag_notes.append("beneish_compute_failed")

            # dechow_f
            try:
                d_result = compute_dechow_f(snap, hist if not hist.empty else None)
                flags["dechow_high"] = d_result.dechow_high
                flags["dechow_f_score"] = d_result.f_score
            except Exception:
                flags["dechow_high"] = None
                flags["dechow_f_score"] = None
                flag_notes.append("dechow_compute_failed")

            # Tier-2 defenses (8-K + 10-K text) — independent per-ticker fetches
            try:
                from compute.scoring.tier2 import fetch_tier2_for_ticker
                t2 = fetch_tier2_for_ticker(ticker)
                flags["non_reliance_filing"] = t2.non_reliance_flag.fired
                flags["going_concern_disclosure"] = t2.going_concern_disclosure
                flags["auditor_change"] = t2.auditor_change_flag.fired
            except Exception as e:
                flags["non_reliance_filing"] = None
                flags["going_concern_disclosure"] = None
                flags["auditor_change"] = None
                flag_notes.append(f"tier2_fetch_failed:{e!s:.50}")

            # HC gate approximation: any active veto fires?
            # Production active vetoes: altman_distress, sloan_accruals_top_decile,
            # net_issuance_top_decile, non_reliance_filing, data_quality_input_corruption
            evaluable_vetoes = [
                "altman_distress",
                "non_reliance_filing",
                "data_quality_input_corruption",
            ]
            veto_fired_evaluable = any(flags.get(v) for v in evaluable_vetoes)

            result = {
                "ticker": ticker,
                "flags": flags,
                "flag_notes": flag_notes,
                "skipped_flags": SKIPPED_FLAGS,
                "veto_fired_evaluable": veto_fired_evaluable,
                "caveat": (
                    "sloan_accruals_top_decile and net_issuance_top_decile were NOT evaluated "
                    "(require full universe cross-section). HC gate approximation may be OVER-OPTIMISTIC."
                ),
            }
            out_f.write(json.dumps(result) + "\n")
            out_f.flush()

    logger.info("Stage-2 written to %s", SP400_STAGE2_JSONL)
    print(f"\nStage-2 complete. Results in: {SP400_STAGE2_JSONL}")
    print(f"IMPORTANT: Skipped flags: {SKIPPED_FLAGS}")
    print("HC gate approximation may be OVER-OPTIMISTIC (missing Sloan + NSI vetoes).")


# ---------------------------------------------------------------------------
# Mode: report
# ---------------------------------------------------------------------------

def _load_jsonl(path: Path) -> list[dict]:
    records = []
    if not path.exists():
        return records
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def mode_report(args: argparse.Namespace) -> None:
    """Synthesize all scout outputs into a markdown report."""
    _setup_logging()
    SCOUT_OUT_DIR.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []

    def _h(text: str, level: int = 2) -> None:
        lines.append(f"{'#' * level} {text}\n")

    def _p(text: str) -> None:
        lines.append(text + "\n")

    _h("Phase-8 Universe Expansion Scout Report", 1)
    _p(f"Generated: {datetime.now(UTC).isoformat()}")
    _p("")

    # --- Stage-1 summary ---
    _h("S&P 400 Stage-1: Composite Distribution")

    stage1_records = _load_jsonl(SP400_STAGE1_JSONL)
    scored = [r for r in stage1_records if r.get("status") == "scored" and r.get("composite") is not None]
    composites = [r["composite"] for r in scored]

    if not scored:
        _p("No stage-1 data available. Run `--mode sp400-stage1` first.")
    else:
        _p(f"Scored tickers: {len(scored)} / {len(stage1_records)}")
        _p(f"No-price tickers: {len([r for r in stage1_records if r.get('status') == 'no_price'])}")

        if composites:
            s = pd.Series(composites)
            _p("\n**Composite statistics:**")
            _p(f"- Mean: {s.mean():.2f}")
            _p(f"- Median: {s.median():.2f}")
            _p(f"- P25/P75: {s.quantile(0.25):.2f} / {s.quantile(0.75):.2f}")
            _p(f"- Min/Max: {s.min():.2f} / {s.max():.2f}")

            _p("\n**Decile histogram:**")
            deciles = pd.cut(s, bins=[0, 10, 20, 30, 40, 50, 60, 65, 70, 80, 90, 100], include_lowest=True)
            for bucket, count in deciles.value_counts().sort_index().items():
                _p(f"  {bucket}: {count} tickers")

        ge65 = [r for r in scored if r["composite"] >= BOOK_COMPOSITE_THRESHOLD]
        band60_65 = [r for r in scored if NEAR_MISS_BAND_LOW <= r["composite"] < BOOK_COMPOSITE_THRESHOLD]

        _p(f"\n**Book-eligible (composite >= {BOOK_COMPOSITE_THRESHOLD}):** {len(ge65)} tickers")
        _p(f"**Near-miss ({NEAR_MISS_BAND_LOW}–{BOOK_COMPOSITE_THRESHOLD}):** {len(band60_65)} tickers")

        _h("Top-30 Midcaps by Composite", 3)
        _p("| Ticker | Name | Sector | Composite | Degradation |")
        _p("|--------|------|--------|-----------|-------------|")
        for r in sorted(scored, key=lambda x: -(x["composite"] or 0))[:30]:
            deg = "; ".join(r.get("degradation_notes", []))[:60]
            _p(f"| {r['ticker']} | {r.get('name', '')} | {r.get('sector', '')} | {r['composite']:.1f} | {deg} |")

        _h("Per-pillar null/degradation rates", 3)
        pillar_cols = ["quality", "value", "growth", "momentum", "health", "profitability", "technical", "risk"]
        for col in pillar_cols:
            null_count = sum(1 for r in scored if r.get("pillars", {}).get(col) is None)
            _p(f"- {col}: {null_count}/{len(scored)} null ({100*null_count/max(len(scored),1):.0f}%)")

        # Cross-section caveat
        if stage1_records:
            cs_note = stage1_records[0].get("cross_section_note", "unknown")
            _p(f"\n**Cross-section mode:** `{cs_note}`")
            if "CAVEAT" in cs_note:
                _p("> WARNING: S&P 500 caches were cold — sector-relative pillars (quality, value, "
                   "growth, profitability) were ranked within the midcap cohort only, NOT vs the S&P 500. "
                   "This biases composites UPWARD for midcaps (easier peer group). "
                   "Re-run stage-1 with a warm S&P 500 cache for honest numbers.")

    # --- Stage-2 defense summary ---
    _h("Stage-2: Defense-Layer Flags")

    stage2_records = _load_jsonl(SP400_STAGE2_JSONL)
    if not stage2_records:
        _p("No stage-2 data. Run `--mode sp400-stage2` for tickers in the >= 60 band.")
    else:
        _p(f"Tickers evaluated: {len(stage2_records)}")
        _p("**Skipped flags** (require full universe, can only be evaluated honestly on combined cross-section):")
        for f in (stage2_records[0].get("skipped_flags") or []):
            _p(f"  - `{f}`")

        veto_count = sum(1 for r in stage2_records if r.get("veto_fired_evaluable"))
        _p(f"\nEvaluable-veto fired: {veto_count} / {len(stage2_records)} tickers")

        _p("\n| Ticker | altman | non_reliance | data_quality | beneish | dechow | going_concern | stale_filing |")
        _p("|--------|--------|--------------|--------------|---------|--------|---------------|--------------|")
        for r in stage2_records:
            f = r.get("flags", {})
            def _fmt(v: bool | None) -> str:
                if v is None:
                    return "?"
                return "YES" if v else "no"
            _p(f"| {r['ticker']} | {_fmt(f.get('altman_distress'))} | {_fmt(f.get('non_reliance_filing'))} | "
               f"{_fmt(f.get('data_quality_input_corruption'))} | {_fmt(f.get('beneish_manipulation'))} | "
               f"{_fmt(f.get('dechow_high'))} | {_fmt(f.get('going_concern_disclosure'))} | "
               f"{_fmt(f.get('stale_filing_hard'))} |")

        _p("\n> CAVEAT: `sloan_accruals_top_decile` and `net_issuance_top_decile` were NOT evaluated. "
           "The HC gate assessment above is therefore OPTIMISTIC — additional vetoes may fire on these "
           "tickers once the full combined universe cross-section is available.")

    # --- ADR probe ---
    _h("ADR Probe Results")

    if ADR_PROBE_JSON.exists():
        with ADR_PROBE_JSON.open() as f:
            adr_data = json.load(f)
        results = adr_data.get("results", {})

        _p(f"Tickers probed: {len(results)}")
        _p(f"Verdict counts: {adr_data.get('verdict_counts', {})}")

        _p("\n| Ticker | Verdict | Key Forms | GAAP fields non-null | IFRS namespace |")
        _p("|--------|---------|-----------|----------------------|----------------|")
        for ticker, r in results.items():
            forms = ",".join(r.get("form_sample", [])[:4]) or "(none)"
            _p(f"| {ticker} | {r.get('verdict')} | {forms} | {r.get('non_null_gaap_fields', 0)} | {r.get('has_ifrs_namespace')} |")

        _p("\n**Key finding:** Most foreign private issuers (20-F/6-K filers) are `ANNUAL_ONLY` — "
           "our US-GAAP TTM extraction returns no quarterly data and typically zero to few non-null fields. "
           "Only companies filing 10-K/10-Q (MELI-style domestically reporting FPIs) are `SCOREABLE_FULL`.")
    else:
        _p("No ADR probe data. Run `--mode adr-probe` first.")

    # --- Book impact ---
    _h("Book Impact")

    rankings_path = config.DATA_DIR / "rankings.json"
    pit_path = config.DATA_DIR / "portfolio" / "backtest_pit.json"

    if not rankings_path.exists():
        _p("rankings.json not found — cannot compute book impact.")
    elif not scored:
        _p("No stage-1 scored data — cannot compute book impact.")
    else:
        with rankings_path.open() as f:
            rankings_data = json.load(f)
        # rankings.json is a plain list of stock summary dicts
        rankings_list = rankings_data if isinstance(rankings_data, list) else rankings_data.get("stocks", [])
        sp500_scores = {s["ticker"]: s["composite_score"] for s in rankings_list}

        _p(f"Current S&P 500 tickers in rankings.json: {len(sp500_scores)}")

        book_eligible = [r for r in scored if r["composite"] >= BOOK_COMPOSITE_THRESHOLD]
        _p(f"Midcaps passing composite >= {BOOK_COMPOSITE_THRESHOLD}: {len(book_eligible)}")

        # Stage-2 veto filter
        stage2_by_ticker = {r["ticker"]: r for r in stage2_records}
        clean_eligible = []
        for r in book_eligible:
            t = r["ticker"]
            if t in stage2_by_ticker:
                s2 = stage2_by_ticker[t]
                if not s2.get("veto_fired_evaluable"):
                    clean_eligible.append(r)
            else:
                # Not in stage-2 — unknown defense status, flag as such
                clean_eligible.append({**r, "defense_status": "not_evaluated"})

        _p(f"After evaluable vetoes: {len(clean_eligible)} midcaps potentially book-eligible")
        _p("> (Reminder: sloan_accruals_top_decile + net_issuance_top_decile still un-evaluated)")

        if clean_eligible:
            _p("\n**Potentially book-eligible midcaps (stage-2 evaluable vetoes clean):**")
            _p("| Ticker | Composite | Defense status |")
            _p("|--------|-----------|----------------|")
            for r in sorted(clean_eligible, key=lambda x: -(x.get("composite") or 0)):
                ds = stage2_by_ticker.get(r["ticker"], {}).get("veto_fired_evaluable", "not_evaluated")
                _p(f"| {r['ticker']} | {r['composite']:.1f} | {ds} |")

        # Inverse-vol dilution note
        if pit_path.exists():
            with pit_path.open() as f:
                pit_data = json.load(f)
            # Latest rebalance
            rebalances = pit_data.get("rebalances", [])
            if rebalances:
                latest = rebalances[-1]
                current_book = [h["ticker"] for h in latest.get("holdings", [])]
                n_current = len(current_book)
                n_new = len(clean_eligible)
                _p(
                    f"\n**Inverse-vol weight dilution:** Current book has {n_current} positions. "
                    f"Adding {n_new} midcaps would expand the pool to ~{n_current + n_new} names. "
                    f"Inverse-vol weighting re-normalizes automatically — existing positions' weights "
                    f"would be diluted proportionally (not 1/N uniform; exact dilution depends on "
                    f"trailing 90d sigma of each new name, which was not computed in stage-1)."
                )
        else:
            _p("\nbacktest_pit.json not found — weight dilution estimate skipped.")

    # --- Deviations from production ---
    _h("Deviations from Production Scoring")

    _p("The following deviations from the full production pipeline were applied in this scout:")
    deviations = [
        "**Stage-1 cross-section**: If S&P 500 cache was cold, midcaps were scored within midcap-only cross-section. "
        "This biases sector-relative percentile pillars (quality, value, growth, profitability) UPWARD for midcaps. "
        "Remedy: warm S&P 500 cache first via `python -m compute.main` then re-run stage-1.",
        "**Event-layer inputs skipped in stage-1**: Form 4 / 8-K / 10-K text event fetches were NOT run. "
        "The production graceful-degradation paths handled the missing inputs (None → neutral / annotated). "
        "Pillars that depend on these (risk, manipulation_index) run in degraded mode.",
        "**sloan_accruals_top_decile and net_issuance_top_decile not evaluated in stage-2**: "
        "These two active vetoes require the full universe for within-sector percentile ranking. "
        "They could not be computed honestly for isolated midcap tickers. "
        "HC gate assessment in stage-2 is OVER-OPTIMISTIC by this count.",
        "**No OSAP/Alpha158/Qlib blend**: The production pipeline applies Phase-4h OSAP blend "
        "(composite_osap_adjusted) if OSAP pipeline succeeds. Scout stage-1 uses raw composite_score only "
        "(same as production's unblended composite, which is what the Top-5 rotation actually uses).",
        "**Form 4 insider signals**: fetch_recent_form4 and the associated detect_insider_sell_cluster / "
        "detect_c_suite_unusual_sell / count_10b5_1_filtered_transactions calls were skipped in stage-1 "
        "(event-layer skip). These feed the risk pillar and manipulation_index annotates.",
        "**Beneish/Dechow in stage-1**: Computed via graceful-degradation in stage-1 (no history → None → annotated). "
        "Stage-2 runs them explicitly where history is available.",
        "**ADR probe**: The non_null_gaap_fields count calls fetch_fundamentals with an empty CIK string, "
        "which may not find the correct CIK for all tickers. Verdict may be less accurate for "
        "tickers where edgartools Company() lookup works but CIK was not provided.",
    ]
    for d in deviations:
        _p(f"- {d}")

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
        description="Phase-8 universe expansion scout — dev tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["sp400-stage1", "adr-probe", "sp400-stage2", "report"],
        help="Scout mode to run",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="(sp400-stage1) Limit to first N tickers from S&P 400 list",
    )
    parser.add_argument(
        "--tickers",
        type=str,
        default="",
        help="Comma-separated ticker list (sp400-stage1 or adr-probe)",
    )
    parser.add_argument(
        "--tickers-file",
        type=str,
        default="",
        help="(sp400-stage2) Path to JSON file with tickers; defaults to scout_out/sp400_stage1_summary.json",
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        default=False,
        help="Force re-fetch of cached universe list",
    )
    parser.add_argument(
        "--force-rescore",
        action="store_true",
        default=False,
        help=(
            "(sp400-stage1) Re-score ALL tickers even if already present in the "
            "JSONL; truncates the existing JSONL before starting.  Reuses on-disk "
            "ingest caches (prices + fundamentals snapshots) so only the annual-"
            "history fetch adds network time (~1 s/ticker)."
        ),
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.mode == "sp400-stage1":
        mode_sp400_stage1(args)
    elif args.mode == "adr-probe":
        mode_adr_probe(args)
    elif args.mode == "sp400-stage2":
        mode_sp400_stage2(args)
    elif args.mode == "report":
        mode_report(args)
    else:
        parser.error(f"Unknown mode: {args.mode}")


if __name__ == "__main__":
    main()
