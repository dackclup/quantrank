"""Phase 9.1 — Broad Investable US universe fetcher and investability screen.

Sources the candidate pool from SEC EDGAR's public ``company_tickers.json``
endpoint, applies a name/format exclusion pass (ETF/FUND/SPAC/preferred/warrant),
then screens by price >= BROAD_UNIVERSE_PRICE_FLOOR_USD ($5) and trailing-30-day
ADV >= ADV_FLOOR_USD ($5M).

HARD NAMING CONSTRAINT (legal/trademark):
    Call this universe "Broad Investable US" everywhere.  NEVER use the strings
    "Russell 3000", "Russell-3000-class", or "equivalent to Russell 3000" in any
    field name, comment, log line, or user-visible label.

Rule 18 observability-before-wiring (CLAUDE.md §Conventions):
    This module ships the data-sourcing and screen logic.  The probe function in
    ``compute/main.py`` (*_run_broad_universe_probe*) emits diagnostic ``Metadata``
    fields (``broad_universe_*``) that are WRITE-ONLY / OBSERVABILITY-ONLY.

    HARD CONSTRAINT: none of the fields emitted by this module or the probe
    function MUST EVER be read by scoring, composite, pillar computation, veto/flag
    logic, fair-price, or ``select_picks``.  They are computed once near the
    Metadata assembly and feed ONLY the Metadata constructor.

    Rankings/scores/flags are BYTE-IDENTICAL whether or not the probe ran.
    Defense layer is UNCHANGED at 36.

ADR detection note:
    yfinance returns ``EQUITY`` for most ADRs (issue #541 PR-1b TODO).  We
    exclude by exchange filter (Nasdaq/NYSE/CBOE only) and the
    ``security_type`` field where available, but ADRs on those exchanges that
    lack a 20-F/6-K keyword in their name may survive into the candidate pool.
    This is a known limitation documented in the probe's Metadata field
    comments; ADR detection is deferred to a future slice.

Escape hatch:
    Set ``QR_SKIP_BROAD_UNIVERSE=1`` to skip the probe entirely (useful in
    CI pre-merge simulations that cannot reach the SEC endpoint).
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from compute import config

if TYPE_CHECKING:
    pass  # keep mypy happy — no runtime conditional imports

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Name / format exclusion patterns
# Mirror the exclusion logic used by the 9.0 Scout so the probe's candidate
# count is comparable to the scout's validated estimate.
# ---------------------------------------------------------------------------

# ETF / Fund name-keyword filter (only when the title EXPLICITLY says so —
# ETFs whose name lacks the keyword are caught by security_type where available).
_ETF_FUND_PAT: re.Pattern[str] = re.compile(r"\bETF\b|\bFUND\b", re.IGNORECASE)

# SPAC / blank-check name filter — SPACs generate noise in the candidate pool
# and have no investable fundamentals.
_SPAC_PAT: re.Pattern[str] = re.compile(
    r"\bACQUISITION\b|\bBLANK\s+CHECK\b|\bSPAC\b", re.IGNORECASE
)

# Ticker-suffix filter for non-equity securities:
#   -P / -PA / -PB … preferred share lines
#   -W / -WA / -WS / -WT   warrants
#   -UN / -U               unit trust (bundled share + warrant)
#   -R / -RT / -RI         rights
_NONEQUITY_TICKER_PAT: re.Pattern[str] = re.compile(
    r"-P[A-Z]?$|-W[A-Z]?$|-UN$|-U$|-WS$|-WT$|-R$|-RT$|-RI$"
)

# ---------------------------------------------------------------------------
# Edgartools bundled parquet discovery
# The bundled parquet (shipped with the edgartools package) carries an
# ``exchange`` column that the live SEC JSON lacks.  We prefer the bundled
# file for the exchange-based filter because a live SEC round-trip is expensive
# and the exchange data is stable between parquet versions.
# ---------------------------------------------------------------------------

def _find_bundled_company_tickers_parquet() -> Path | None:
    """Locate the edgartools bundled company_tickers.parquet.

    Returns the path on success, ``None`` if not found.  Never raises.
    Checked in priority order: known installation paths, then edgar.__file__
    introspection.
    """
    _PARQUET_CANDIDATES: list[Path] = [
        Path("/usr/local/lib/python3.11/dist-packages/edgar/reference/data/company_tickers.parquet"),
        Path("/usr/lib/python3/dist-packages/edgar/reference/data/company_tickers.parquet"),
    ]
    for p in _PARQUET_CANDIDATES:
        if p.exists():
            return p
    try:
        import edgar  # type: ignore[import-untyped]  # noqa: PLC0415
        candidate = Path(edgar.__file__).parent / "reference" / "data" / "company_tickers.parquet"
        if candidate.exists():
            return candidate
    except ImportError:
        pass
    return None


def _load_bundled_company_tickers() -> pd.DataFrame | None:
    """Load the edgartools bundled company_tickers parquet.

    Returns a DataFrame with at least columns ``ticker``, ``name``
    (or ``title``), ``exchange``.  Returns ``None`` on any failure.
    """
    p = _find_bundled_company_tickers_parquet()
    if p is None:
        logger.warning(
            "[broad-universe] Bundled company_tickers.parquet not found — "
            "will fall back to live SEC JSON (no exchange column)"
        )
        return None
    try:
        df = pd.read_parquet(p)
        logger.info(
            "[broad-universe] Loaded bundled company_tickers parquet: %d rows from %s",
            len(df), p,
        )
        return df
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[broad-universe] Failed to load bundled parquet %s: %s (graceful degradation)",
            p, exc,
        )
        return None


# ---------------------------------------------------------------------------
# Live SEC endpoint fetcher (fallback path; required User-Agent)
# ---------------------------------------------------------------------------

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20), reraise=True)
def _fetch_sec_company_tickers_json() -> dict:
    """Fetch https://www.sec.gov/files/company_tickers.json with EDGAR identity.

    Raises ``EnvironmentError`` when ``EDGAR_USER_AGENT`` is not set — the SEC
    fair-access policy requires a meaningful User-Agent string for all
    programmatic access; using a blank or generic agent risks rate-limiting for
    the whole project.

    Uses tenacity (stop_after_attempt=3, exponential backoff 2-20s) matching
    the project's existing EDGAR retry policy (``compute/ingest/fundamentals.py``).

    Returns the raw parsed JSON dict (keyed by numeric string index).
    """
    ua = os.environ.get("EDGAR_USER_AGENT")
    if not ua:
        raise OSError(
            "EDGAR_USER_AGENT env-var is not set.  The SEC company_tickers.json "
            "endpoint requires a meaningful User-Agent string (e.g. "
            "'YourName YourEmail@example.com') per SEC fair-access policy.  "
            "Set EDGAR_USER_AGENT before running the broad-universe probe."
        )
    resp = requests.get(
        config.SEC_COMPANY_TICKERS_URL,
        headers={"User-Agent": ua},
        timeout=30,
        verify=os.environ.get("REQUESTS_CA_BUNDLE", True),  # respects CA bundle
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Disk-cache layer for the broad-universe candidate DataFrame
# ---------------------------------------------------------------------------

def _candidates_from_bundled(df: pd.DataFrame) -> pd.DataFrame:
    """Extract the investable candidate pool from the bundled parquet.

    Applies:
      1. Exchange filter (Nasdaq / NYSE / CBOE main-market only).
      2. Name-pattern exclusions (ETF/FUND/SPAC name keywords).
      3. Ticker-format exclusions (preferred / warrant / rights suffixes).

    Returns a DataFrame with columns ``["ticker", "name", "exchange"]``.
    The ``cik_str`` column is included when present (forward-safe).
    """
    # Normalise column names (bundled parquets may differ between edgartools versions).
    col_map: dict[str, str] = {}
    for col in df.columns:
        cl = col.lower().strip()
        if cl in ("ticker", "ticker_symbol"):
            col_map[col] = "ticker"
        elif cl in ("name", "title", "company_name"):
            col_map[col] = "name"
        elif cl == "exchange":
            col_map[col] = "exchange"
        elif cl in ("cik", "cik_str"):
            col_map[col] = "cik_str"
    df = df.rename(columns=col_map)

    if "ticker" not in df.columns or "exchange" not in df.columns:
        raise ValueError(
            f"Bundled parquet missing required columns. Available: {list(df.columns)}"
        )

    if "name" not in df.columns:
        df["name"] = df["ticker"]

    # 1. Exchange filter
    mask_exchange = df["exchange"].isin(config.BROAD_UNIVERSE_ELIGIBLE_EXCHANGES)
    df = df[mask_exchange].copy()

    # 2. Name-pattern exclusions
    name_col = df["name"].fillna("").str.upper()
    mask_etf = name_col.str.contains(_ETF_FUND_PAT, na=False, regex=True)
    mask_spac = name_col.str.contains(_SPAC_PAT, na=False, regex=True)

    # 3. Ticker-format exclusions
    mask_nonequity = df["ticker"].str.contains(
        _NONEQUITY_TICKER_PAT, na=False, regex=True
    )

    mask_exclude = mask_etf | mask_spac | mask_nonequity
    df = df[~mask_exclude].copy()

    keep_cols = ["ticker", "name", "exchange"]
    if "cik_str" in df.columns:
        keep_cols.append("cik_str")
    return df[keep_cols].drop_duplicates(subset=["ticker"]).reset_index(drop=True)


def _candidates_from_live_json(raw: dict) -> pd.DataFrame:
    """Extract the candidate pool from the live SEC company_tickers.json.

    The live JSON has no exchange column — we can only apply name/format
    exclusions.  A subsequent caller should cross-reference against the bundled
    parquet to add the exchange dimension when available.

    Returns a DataFrame with columns ``["ticker", "name", "cik_str"]``.
    """
    rows: list[dict] = []
    for entry in raw.values():
        ticker = str(entry.get("ticker") or "").strip()
        name = str(entry.get("title") or "").strip()
        cik_str = str(entry.get("cik_str") or entry.get("cik") or "").strip()
        if not ticker:
            continue
        rows.append({"ticker": ticker, "name": name, "cik_str": cik_str})

    df = pd.DataFrame(rows)

    # Name exclusions
    name_col = df["name"].fillna("").str.upper()
    mask_etf = name_col.str.contains(_ETF_FUND_PAT, na=False, regex=True)
    mask_spac = name_col.str.contains(_SPAC_PAT, na=False, regex=True)

    # Ticker-format exclusions
    mask_nonequity = df["ticker"].str.contains(
        _NONEQUITY_TICKER_PAT, na=False, regex=True
    )

    mask_exclude = mask_etf | mask_spac | mask_nonequity
    df = df[~mask_exclude].copy()

    return df[["ticker", "name", "cik_str"]].drop_duplicates(subset=["ticker"]).reset_index(drop=True)


def fetch_broad_universe_candidates(force_refresh: bool = False) -> pd.DataFrame:
    """Return the Broad Investable US candidate pool, hitting the disk cache when fresh.

    Strategy (graceful degradation in order):
      1. Return the cached parquet if it is within ``BROAD_UNIVERSE_CACHE_MAX_AGE_DAYS``.
      2. Try to build from the edgartools bundled company_tickers.parquet
         (has exchange column → enables the exchange filter).
      3. Fall back to a live SEC JSON fetch (no exchange column; applies name/
         format exclusions only and tags all rows exchange=``"unknown"``).
      4. If all sources fail, return an empty DataFrame and log a WARNING.

    Disk cache lives at ``compute/cache/broad_universe-v1.parquet`` (gitignored).

    Returns a DataFrame with at minimum columns ``["ticker", "name", "exchange"]``.
    The ``cik_str`` column is included when the source provides it.

    Rule 18 invariant:
        This function is called exclusively from ``_run_broad_universe_probe``
        in ``compute/main.py``.  Its output MUST NEVER be used for scoring,
        composite calculation, veto/flag emission, fair-price, or ``select_picks``.
    """
    cache: Path = config.BROAD_UNIVERSE_CACHE

    # --- Cache hit path ---
    if not force_refresh and cache.exists():
        age_days = (time.time() - cache.stat().st_mtime) / 86400
        if age_days < config.BROAD_UNIVERSE_CACHE_MAX_AGE_DAYS:
            logger.info(
                "[broad-universe] Cache hit (age=%.1f days): %s", age_days, cache
            )
            return pd.read_parquet(cache)

    # --- Try bundled parquet first (has exchange column) ---
    bundled_df = _load_bundled_company_tickers()
    candidates: pd.DataFrame | None = None

    if bundled_df is not None:
        try:
            candidates = _candidates_from_bundled(bundled_df)
            logger.info(
                "[broad-universe] Built candidate pool from bundled parquet: %d tickers",
                len(candidates),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[broad-universe] Bundled parquet extraction failed: %s — trying live SEC JSON",
                exc,
            )
            candidates = None

    # --- Fall back to live SEC JSON ---
    if candidates is None:
        try:
            raw = _fetch_sec_company_tickers_json()
            candidates = _candidates_from_live_json(raw)
            # No exchange column from the live JSON — tag as unknown so callers
            # can detect they are working without the exchange filter.
            candidates["exchange"] = "unknown"
            logger.info(
                "[broad-universe] Built candidate pool from live SEC JSON: %d tickers "
                "(exchange filter NOT applied — bundled parquet unavailable)",
                len(candidates),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[broad-universe] Live SEC JSON fetch failed: %s — returning empty DataFrame",
                exc,
            )
            return pd.DataFrame(columns=["ticker", "name", "exchange"])

    # --- Persist to cache ---
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        candidates.to_parquet(cache, index=False)
        logger.info(
            "[broad-universe] Cached %d candidates to %s",
            len(candidates), cache,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[broad-universe] Cache write failed (non-fatal): %s", exc)

    return candidates


# ---------------------------------------------------------------------------
# Investability screen — applies to a prices_by_ticker dict from Step 1
# ---------------------------------------------------------------------------

def screen_broad_universe_investability(
    candidates: pd.DataFrame,
    prices_by_ticker: dict[str, pd.DataFrame],
    *,
    price_floor: float = config.BROAD_UNIVERSE_PRICE_FLOOR_USD,
    adv_floor: float = config.ADV_FLOOR_USD,
    adv_lookback_days: int = config.ADV_LOOKBACK_DAYS,
    security_types_by_ticker: dict[str, str | None] | None = None,
) -> dict[str, int | float | None]:
    """Apply the investability screen to the Broad Investable US candidate pool.

    This function is a PURE diagnostic — it returns counts and percentages
    for the ``Metadata`` fields only.  It does NOT modify any existing scored
    ticker data and NEVER feeds scoring, vetoes, composite, pillar computation,
    fair-price, or ``select_picks``.

    Parameters
    ----------
    candidates:
        DataFrame returned by ``fetch_broad_universe_candidates``.  Must have
        at least a ``ticker`` column.
    prices_by_ticker:
        The ``prices_by_ticker`` dict already built in Step 1 of the weekly
        compute (ticker → OHLCV DataFrame).  Reused here to avoid a second
        round of network calls.  Tickers not in this dict are counted as
        "no price data available".
    price_floor:
        Minimum last-close price; defaults to ``BROAD_UNIVERSE_PRICE_FLOOR_USD``.
    adv_floor:
        Minimum trailing-N-day ADV; defaults to ``ADV_FLOOR_USD`` ($5M).
    adv_lookback_days:
        Trailing trading-day window; defaults to ``ADV_LOOKBACK_DAYS`` (30).
    security_types_by_ticker:
        Optional mapping of ticker → security_type string from yfinance
        (``_QUOTE_TYPE_LABEL`` map in ``compute/ingest/cross_source.py``).
        Used to exclude ETF/fund tickers whose name didn't flag them.
        ``None`` means security-type filtering is skipped (graceful
        degradation when the type cache is cold).

    Returns
    -------
    dict with keys:
        broad_universe_raw_count        int — total rows in ``candidates``
        broad_universe_candidate_count  int — after exchange + name/format exclusions
                                              (already applied in ``fetch_broad_universe_candidates``)
        broad_universe_screened_count   int | None — passing price AND ADV floors
        broad_universe_price_fail_pct   float | None — % of candidates failing price >= $5
        broad_universe_adv_fail_pct     float | None — % of candidates failing ADV >= $5M
        broad_universe_coverage_pct     float | None — % of candidates with any price data
    """
    from compute.ingest.prices import compute_average_dollar_volume  # noqa: PLC0415

    raw_count = len(candidates)
    # After exchange+name/format exclusions are already applied in the fetcher.
    candidate_count = raw_count

    if candidate_count == 0:
        return {
            "broad_universe_raw_count": 0,
            "broad_universe_candidate_count": 0,
            "broad_universe_screened_count": None,
            "broad_universe_price_fail_pct": None,
            "broad_universe_adv_fail_pct": None,
            "broad_universe_coverage_pct": None,
        }

    # Identify tickers NOT already in the prices_by_ticker dict.  The dict
    # holds only the SP1500 (or current universe) tickers — the broad-universe
    # candidates that are NOT in SP1500 will not have pre-fetched prices.
    # We do NOT fetch prices for the extra candidates here (that would require
    # ~2k additional yfinance calls); instead we report coverage_pct and
    # apply the screen only to the subset that happens to already have prices.
    #
    # On the 9.1 Probe slice, the screen is CHEAP because it reuses Step-1
    # prices already in memory.  The 9.3 RANKED slice (a future PR) will
    # add the full price-fetch loop for the extra candidates.
    n_with_prices = 0
    n_price_fail = 0
    n_adv_fail = 0
    n_both_pass = 0
    n_no_data = 0

    _ETF_SECURITY_TYPES = {"ETF", "Fund", "MUTUALFUND"}

    for _, row in candidates.iterrows():
        ticker = str(row.get("ticker", "")).strip()
        if not ticker:
            n_no_data += 1
            continue

        # Optional security-type exclusion (obs-first; skipped on cold cache)
        if security_types_by_ticker is not None:
            st = security_types_by_ticker.get(ticker)
            if st and st.upper() in _ETF_SECURITY_TYPES or (
                st and any(k in st.lower() for k in ("etf", "fund"))
            ):
                n_no_data += 1  # counted as filtered-out, not a screened name
                continue

        df_prices = prices_by_ticker.get(ticker)
        if df_prices is None or df_prices.empty:
            n_no_data += 1
            continue

        n_with_prices += 1

        # Last close
        close_col = "Adj Close" if "Adj Close" in df_prices.columns else "Close"
        try:
            last_close = float(df_prices[close_col].dropna().iloc[-1])
        except (IndexError, KeyError, TypeError, ValueError):
            n_price_fail += 1
            continue

        if last_close < price_floor:
            n_price_fail += 1
            continue

        # ADV — reuse the production helper
        adv = compute_average_dollar_volume(df_prices, adv_lookback_days)
        if adv is None or adv < adv_floor:
            n_adv_fail += 1
            continue

        n_both_pass += 1

    n_screened = n_with_prices  # denominator for pass/fail rates

    # coverage_pct = % of candidates with any price data
    coverage_pct: float | None = (
        round(100.0 * n_with_prices / candidate_count, 2)
        if candidate_count > 0
        else None
    )

    # Pass rates (among those with price data)
    price_fail_pct: float | None = (
        round(100.0 * n_price_fail / n_screened, 2)
        if n_screened > 0
        else None
    )
    adv_fail_pct: float | None = (
        round(100.0 * n_adv_fail / n_screened, 2)
        if n_screened > 0
        else None
    )
    screened_count: int | None = n_both_pass if n_screened > 0 else None

    logger.info(
        "[broad-universe] Screen results: raw=%d candidates=%d "
        "with_prices=%d price_fail=%d adv_fail=%d both_pass=%d no_data=%d",
        raw_count, candidate_count,
        n_with_prices, n_price_fail, n_adv_fail, n_both_pass, n_no_data,
    )
    logger.info(
        "[broad-universe] Coverage %.1f%% | price_fail %.1f%% | adv_fail %.1f%% | screened=%s",
        coverage_pct or 0.0,
        price_fail_pct or 0.0,
        adv_fail_pct or 0.0,
        screened_count,
    )

    return {
        "broad_universe_raw_count": raw_count,
        "broad_universe_candidate_count": candidate_count,
        "broad_universe_screened_count": screened_count,
        "broad_universe_price_fail_pct": price_fail_pct,
        "broad_universe_adv_fail_pct": adv_fail_pct,
        "broad_universe_coverage_pct": coverage_pct,
    }
