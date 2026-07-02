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

Phase 9.3 — RANKED universe path (dispatch-only, QR_UNIVERSE=broad_investable_us):
    This slice adds two functions that turn the candidate pool into an actual
    SCORED/RANKED universe when ``QR_UNIVERSE=broad_investable_us`` is set via
    manual ``workflow_dispatch`` (see ``compute/main.py``'s universe-selector
    seam).  This is DISPATCH-ONLY — the scheduled weekday cron default stays
    ``sp1500``, UNCHANGED.

    ``candidates_to_universe_frame`` shapes the raw candidate DataFrame (which
    has only ``ticker``/``name``/``exchange``[/``cik_str``]) into the column
    shape ``fetch_all_prices`` / ``fetch_all_fundamentals`` expect
    (``ticker``/``name``/``sector``/``sub_industry``/``cik``/``cohort``).  GICS
    sector is NOT available from the SEC company-tickers source, so every row
    gets ``sector="Unknown"`` — this mirrors the EXACT precedent already in
    ``compute/ingest/universe.py`` (the S&P 400/600 Wikipedia-table loader
    degrades to ``sector="Unknown"`` when the source table lacks a sector
    column).  Downstream consumers already tolerate this: sector-exclusion
    checks are exact-string comparisons against ``"Financials"``/``"Utilities"``
    (never trip on ``"Unknown"``), ``get_cost_of_equity`` falls back to the flat
    10% default for any unmapped sector string, and the peer-grouping walk
    (``_build_peer_groupings``) simply buckets every ``"Unknown"``-sector name
    into one large peer group (comfortably clears ``MULTIPLES_MIN_PEERS=8``).

    ``select_broad_universe_survivors`` is the RANKED-PATH counterpart to
    ``screen_broad_universe_investability`` (which stays a pure diagnostic
    returning COUNTS for the probe's ``Metadata`` fields).  This new function
    applies the identical price >= $5 / ADV >= $5M screen but returns the
    SURVIVING TICKER SET so the caller can reduce the scored frame to
    survivors BEFORE fundamentals fetch (Step 2) — this is the P1-G3
    methodology gate (methodology-scientist ratified): non-survivors are
    REMOVED from the peer set entirely, never emitted as a ``low_liquidity``
    annotate.  Kept as a separate function (not a mutation of the probe) so
    the Rule-18 diagnostic boundary of ``screen_broad_universe_investability``
    stays untouched — the probe path and the ranked path use different
    entry points into the same underlying floors.

    P1-G4 re-normalization disclosure (methodology-REQUIRED): broadening the
    scored universe from S&P 1500 (~1504 names) to the Broad Investable US
    pool (~3,545 names) RE-BASES every cross-sectional percentile and sector
    median used by the 8-pillar composite.  A score computed on the broad
    universe is NOT comparable to a score computed on the same ticker under
    an sp1500 cron — the percentile rank, sector-relative pillars, and
    peer-median valuation inputs are all universe-relative by construction.
    This PR does not change the frontend disclaimer (deferred to Phase 9.4);
    the caveat lives here + in ``compute/main.py``'s universe-selector seam
    + CLAUDE.md §Gotchas for anyone touching this path before 9.4 ships a
    user-facing label.

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

PR-1 — ADV-floor-scoping shadow-observability slice (SHADOW-ONLY, Rule 18):
    Two additions, both write-only / observability-only — NO behavioral
    change, rankings/scores/flags are BYTE-IDENTICAL on every path.

    1. ``select_broad_universe_survivors`` now defaults its ``adv_floor``
       parameter to the NEW ``config.BROAD_UNIVERSE_ADV_FLOOR_USD`` constant
       instead of ``config.ADV_FLOOR_USD``.  This fixes a latent coupling
       defect (the RANKED-path investability screen and the sp1500
       ``low_liquidity`` annotate threshold were the SAME constant, so
       re-tuning one would silently re-tune the other).  The new constant's
       initial value is IDENTICAL to ``ADV_FLOOR_USD`` ($5M), so survivors
       are unchanged.  ``screen_broad_universe_investability`` (the Phase 9.1
       probe diagnostic) intentionally keeps ``config.ADV_FLOOR_USD`` as its
       default — that function measures against the SAME floor the
       sp1500-cron ``low_liquidity`` annotate uses, for continuity of the
       probe's historical coverage numbers.

    2. ``sweep_broad_universe_floors`` (new) is a PURE diagnostic that
       returns survivor counts at 3 ADV floors ($5M / $10M / $15M,
       MONOTONE-NESTED by construction — a real-number threshold-comparison
       property, not extra bookkeeping) plus 3 single-value diagnostics
       (ADR-suspect count, chosen-floor survivor fundamentals coverage,
       chosen-floor survivor sector-unknown rate) for 6 new ``Metadata``
       fields.  Feeds PR-2's empirical re-pin of
       ``BROAD_UNIVERSE_ADV_FLOOR_USD`` — see that constant's docstring in
       ``compute/config.py`` for the full academic anchor (Amihud 2002 +
       Novy-Marx-Velikov 2016 on the dollar level; Fama-French 2008 +
       Hou-Xue-Zhang 2020 on why a stricter-than-sp600 floor should exist
       for this un-pre-screened pool).  Called from ``compute/main.py`` in
       the SAME place as the Phase 9.1 probe above (immediately after
       Step 1 prices) — at that point in the pipeline, security-type and
       fundamentals data are NOT yet available, so ``adr_suspect_count`` and
       ``survivor_fundamentals_coverage_pct`` are structurally ``None`` on
       every run until a future slice threads those signals through (ship
       the field first, populate the signal later — Rule 18).
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


# ---------------------------------------------------------------------------
# Phase 9.3 — RANKED universe path (dispatch-only)
# ---------------------------------------------------------------------------


def candidates_to_universe_frame(candidates: pd.DataFrame) -> pd.DataFrame:
    """Shape the Broad Investable US candidate pool into a ``universe``-frame.

    Adds the columns the rest of the compute pipeline expects on a universe
    DataFrame (``sector``, ``sub_industry``, ``cik``, ``cohort``) that the
    raw candidate pool from ``fetch_broad_universe_candidates`` does not
    carry.  Mirrors the exact graceful-degradation pattern already used by
    the S&P 400/600 Wikipedia loader in ``compute/ingest/universe.py`` when
    the source table lacks a sector column.

    Parameters
    ----------
    candidates:
        DataFrame from ``fetch_broad_universe_candidates`` — at least
        ``["ticker", "name"]``; optionally ``"exchange"`` and ``"cik_str"``.

    Returns
    -------
    DataFrame with columns
    ``["ticker", "name", "sector", "sub_industry", "cik", "cohort"]``:

    - ``sector``: always ``"Unknown"`` (GICS sector is not available from
      the SEC company-tickers source).  Downstream sector-exclusion checks
      are exact-string comparisons against ``"Financials"``/``"Utilities"``
      so ``"Unknown"`` never trips them; ``get_cost_of_equity`` falls back
      to the flat 10% default for any unmapped sector.
    - ``sub_industry``: always ``None`` (not available; the peer-grouping
      walk already tolerates ``None`` sub_industry and falls through to the
      sector-level peer group — see ``_build_peer_groupings`` docstring in
      ``compute/main.py``).
    - ``cik``: zero-padded ``cik_str`` when present, else ``None``.  A
      missing CIK is NOT fatal — ``fetch_fundamentals``'s
      ``Company(cik or ticker)`` call falls back to ticker-symbol
      resolution (same fallback the S&P 400/600 loader relies on), at the
      cost of bypassing the snapshot parquet cache for that ticker.
    - ``cohort``: always ``"broad"``.  This is intentionally NOT overlaid
      with sp500/sp400/sp600 membership — the S&P-cohort tag is a
      DIFFERENT dimension (index constituency) than "was sourced via the
      broad-universe candidate pool", and downstream code
      (``derive_index_memberships``) already treats ``"broad"`` as its own
      suppression bucket for the russell1000 proxy tag (see
      ``compute/ingest/universe.py``).

    Returns an empty-but-correctly-columned DataFrame when ``candidates`` is
    empty — never raises.
    """
    if candidates.empty:
        return pd.DataFrame(
            columns=["ticker", "name", "sector", "sub_industry", "cik", "cohort"]
        )

    out = pd.DataFrame(
        {
            "ticker": candidates["ticker"].astype(str),
            "name": candidates["name"].astype(str)
            if "name" in candidates.columns
            else candidates["ticker"].astype(str),
        }
    )
    out["sector"] = "Unknown"
    out["sub_industry"] = None

    if "cik_str" in candidates.columns:
        # PANDAS 3.0 GOTCHA: assigning a plain Python list (or
        # ``Series.map(...).to_numpy()`` / ``pd.array(..., dtype=object)``)
        # containing a MIX of strings and ``None`` into a DataFrame column
        # triggers pandas 3.0's automatic string-dtype inference, which
        # silently coerces every ``None`` back into a float ``NaN`` — even
        # though ``dtype=object`` was explicitly requested on the source
        # array.  A NaN in the ``cik`` column is a live corruption risk:
        # ``bool(float("nan"))`` is True, so ``r.get("cik") or ""``
        # downstream would keep the NaN (never fall through to the
        # empty-string default) and ``str(nan_value)`` would hand
        # ``fetch_fundamentals`` the literal string "nan" as a CIK.
        #
        # FIX: wrap the values in ``pd.Series(..., dtype=object,
        # index=out.index)`` (NOT a bare list / pd.array) BEFORE assigning
        # to the column — constructing the Series with an explicit dtype
        # up front bypasses the content-based string-dtype inference that
        # a subsequent bare-list assignment triggers.  Verified against
        # pandas 3.0.3 (the version pinned in this repo's uv.lock).
        _cik_values: list[str | None] = []
        for v in candidates["cik_str"]:
            if v is None or (not isinstance(v, str) and pd.isna(v)):
                _cik_values.append(None)
                continue
            s = str(v).strip()
            if not s or s.lower() in ("none", "nan"):
                _cik_values.append(None)
                continue
            try:
                _cik_values.append(str(int(float(s))).zfill(10))
            except (ValueError, TypeError):
                _cik_values.append(None)
        out["cik"] = pd.Series(_cik_values, dtype=object, index=out.index)
    else:
        out["cik"] = None

    out["cohort"] = "broad"
    return out.reset_index(drop=True)


def select_broad_universe_survivors(
    candidates: pd.DataFrame,
    prices_by_ticker: dict[str, pd.DataFrame],
    *,
    price_floor: float = config.BROAD_UNIVERSE_PRICE_FLOOR_USD,
    adv_floor: float = config.BROAD_UNIVERSE_ADV_FLOOR_USD,
    adv_lookback_days: int = config.ADV_LOOKBACK_DAYS,
) -> set[str]:
    """Return the set of ticker survivors of the investability screen.

    This is the RANKED-PATH counterpart to
    ``screen_broad_universe_investability`` (which stays a pure diagnostic
    returning COUNTS for the Metadata probe fields).  This function applies
    the IDENTICAL price >= ``price_floor`` AND trailing-``adv_lookback_days``
    ADV >= ``adv_floor`` screen but returns the surviving TICKER SET so the
    caller can reduce the scored universe frame to survivors before
    fundamentals fetch (Step 2 of ``run_weekly_compute``).

    P1-G3 (methodology-scientist ratified): non-survivors are REMOVED from
    the peer set entirely — this function does NOT emit a ``low_liquidity``
    annotate for excluded names; it simply omits them from the returned set.
    That is a deliberate methodology choice: the ``low_liquidity`` annotate
    exists for names that ARE ranked but trade thinly (S&P 1500 Slice 4);
    on the broad-universe path, sub-floor names are excluded from the peer
    set before scoring begins, so there is no ticker to annotate.

    PR-1 of the ADV-floor-scoping shadow-observability slice DECOUPLED
    ``adv_floor``'s default from ``config.ADV_FLOOR_USD`` to the new
    ``config.BROAD_UNIVERSE_ADV_FLOOR_USD`` (fixes a latent coupling defect —
    the RANKED-path screen and the sp1500 ``low_liquidity`` annotate
    threshold were previously the SAME constant, so re-tuning one would have
    silently re-tuned the other).  The new constant's initial value is
    IDENTICAL to ``ADV_FLOOR_USD`` ($5M) — this change is byte-identical;
    the survivor set is unaffected.  See ``BROAD_UNIVERSE_ADV_FLOOR_USD``'s
    docstring in ``compute/config.py`` for the full academic anchor + the
    PR-2 empirical re-pin plan.

    Parameters
    ----------
    candidates:
        DataFrame with at least a ``ticker`` column (the shaped universe
        frame from ``candidates_to_universe_frame``, or the raw
        ``fetch_broad_universe_candidates`` output — either works, only
        ``ticker`` is read).
    prices_by_ticker:
        Ticker → OHLCV DataFrame, already fetched (Step 1 of the compute
        pipeline).  On the ranked path this MUST be the broad-universe
        price fetch (not a restricted sp1500 dict) or the survivor set will
        be artificially small.
    price_floor, adv_floor, adv_lookback_days:
        Same floors as ``screen_broad_universe_investability`` — kept as
        separate keyword defaults (not a shared call) so the two functions
        remain independently testable and cannot silently diverge without a
        visible diff on both call sites.  NOTE: ``adv_floor`` here defaults
        to ``BROAD_UNIVERSE_ADV_FLOOR_USD``, NOT the sibling function's
        ``ADV_FLOOR_USD`` — see the PR-1 paragraph above.

    Returns
    -------
    set[str]
        Ticker symbols passing BOTH floors.  Empty set (never raises) when
        ``candidates`` is empty or no ticker has usable price data.
    """
    from compute.ingest.prices import compute_average_dollar_volume  # noqa: PLC0415

    survivors: set[str] = set()
    if candidates.empty:
        return survivors

    for ticker in candidates["ticker"].astype(str):
        df_prices = prices_by_ticker.get(ticker)
        if df_prices is None or df_prices.empty:
            continue

        close_col = "Adj Close" if "Adj Close" in df_prices.columns else "Close"
        try:
            last_close = float(df_prices[close_col].dropna().iloc[-1])
        except (IndexError, KeyError, TypeError, ValueError):
            continue

        if last_close < price_floor:
            continue

        adv = compute_average_dollar_volume(df_prices, adv_lookback_days)
        if adv is None or adv < adv_floor:
            continue

        survivors.add(ticker)

    logger.info(
        "[broad-universe-ranked] Investability screen: %d / %d candidates survived "
        "(price >= $%.2f AND trailing-%dd ADV >= $%.0f)",
        len(survivors), len(candidates), price_floor, adv_lookback_days, adv_floor,
    )
    return survivors


# ---------------------------------------------------------------------------
# PR-1 — ADV-floor-scoping shadow-observability slice (SHADOW-ONLY, Rule 18)
# ---------------------------------------------------------------------------
#
# HARD RULE 18 CONSTRAINT: every field this section computes is WRITE-ONLY /
# OBSERVABILITY-ONLY.  ``sweep_broad_universe_floors``'s return values MUST
# NEVER be read by scoring, composite, pillar computation, veto/flag logic,
# fair-price, or ``select_picks`` — they feed ONLY the ``Metadata``
# constructor in ``compute/main.py``.  No floor is flipped by this PR;
# ``select_broad_universe_survivors`` (the only function that actually
# gates universe membership) is untouched by anything below this line.


def _adv_survivors_at_floors(
    candidates: pd.DataFrame,
    prices_by_ticker: dict[str, pd.DataFrame],
    floors: tuple[float, ...],
    *,
    price_floor: float,
    adv_lookback_days: int,
) -> tuple[dict[float, set[str]], int]:
    """Return ``(survivors_by_floor, n_with_prices)`` for the given floors.

    ``survivors_by_floor`` maps each floor in ``floors`` (as given — NOT
    de-duplicated, but see the sort note below) to the SET of candidate
    tickers whose last close >= ``price_floor`` AND whose trailing-
    ``adv_lookback_days`` mean dollar volume (reusing
    ``compute.ingest.prices.compute_average_dollar_volume`` — the identical
    "same price >= $5 leg" as ``select_broad_universe_survivors`` /
    ``screen_broad_universe_investability``) is >= that floor.

    MONOTONE-NESTED BY CONSTRUCTION: for any two floors ``f1 <= f2``, a
    ticker's ADV is a single real number, so ``adv >= f2`` implies
    ``adv >= f1``.  This means ``survivors_by_floor[f2]`` is always a subset
    of ``survivors_by_floor[f1]`` whenever ``f1 <= f2`` — a mathematical
    property of the threshold comparison, not extra bookkeeping this
    function performs.  The floors are visited in ascending order purely for
    readability; the subset property holds regardless of iteration order.

    ``n_with_prices`` is the count of candidates for which price data was
    found in ``prices_by_ticker`` at all (regardless of whether they passed
    any floor) — the "had data" denominator callers use to distinguish a
    genuine zero-survivor measurement (``n_with_prices > 0``, all floor
    counts are real integers, possibly 0) from "no data available"
    (``n_with_prices == 0`` → callers degrade every field to ``None``).
    Mirrors the identical None-vs-zero convention already used by
    ``screen_broad_universe_investability``.

    Pure / no I/O / never raises (matches every other Rule-18 diagnostic
    function in this module) — any per-ticker parsing failure is treated as
    "no usable data" for that ticker and silently skipped.
    """
    from compute.ingest.prices import compute_average_dollar_volume  # noqa: PLC0415

    sorted_floors = tuple(sorted(floors))
    survivors_by_floor: dict[float, set[str]] = {f: set() for f in sorted_floors}
    n_with_prices = 0

    if candidates is None or candidates.empty:
        return survivors_by_floor, n_with_prices

    for ticker in candidates["ticker"].astype(str):
        df_prices = prices_by_ticker.get(ticker)
        if df_prices is None or df_prices.empty:
            continue

        close_col = "Adj Close" if "Adj Close" in df_prices.columns else "Close"
        try:
            last_close = float(df_prices[close_col].dropna().iloc[-1])
        except (IndexError, KeyError, TypeError, ValueError):
            continue

        n_with_prices += 1

        if last_close < price_floor:
            continue

        adv = compute_average_dollar_volume(df_prices, adv_lookback_days)
        if adv is None:
            continue

        for f in sorted_floors:
            if adv >= f:
                survivors_by_floor[f].add(ticker)
            # No early `break`: floors is ascending, so once adv < f for the
            # smallest failing floor, adv < every larger floor too — the
            # remaining comparisons correctly also miss.  Not short-
            # circuiting costs at most 2 extra float comparisons per ticker
            # (len(floors) is always small — 3 by default) and keeps the
            # loop trivially easy to reason about / test.

    return survivors_by_floor, n_with_prices


def sweep_broad_universe_floors(
    candidates: pd.DataFrame,
    prices_by_ticker: dict[str, pd.DataFrame],
    *,
    floors: tuple[float, ...] = (
        config.BROAD_UNIVERSE_ADV_FLOOR_USD,  # $5M — today's production floor
        10_000_000.0,                          # $10M
        15_000_000.0,                          # $15M
    ),
    price_floor: float = config.BROAD_UNIVERSE_PRICE_FLOOR_USD,
    adv_lookback_days: int = config.ADV_LOOKBACK_DAYS,
    security_types_by_ticker: dict[str, str | None] | None = None,
    foreign_filer_by_ticker: dict[str, bool] | None = None,
    fundamentals_ok_by_ticker: dict[str, bool] | None = None,
) -> dict[str, int | float | None]:
    """PR-1 shadow floor-sweep — survivor counts at 3 ADV floors + 3 diagnostics.

    PURE function (no I/O, no network, no disk-cache read) feeding 6 NEW
    ``Metadata`` fields.  SHADOW-ONLY / OBSERVABILITY-ONLY (Rule 18): no
    floor is flipped by this function — ``select_broad_universe_survivors``
    is the only function that actually gates universe membership, and it is
    untouched by this one.  Rankings/scores/flags are BYTE-IDENTICAL whether
    or not this function runs.  Defense layer is UNCHANGED.

    Reuses ``compute.ingest.prices.compute_average_dollar_volume`` and the
    identical "price >= ``price_floor``" leg as
    ``select_broad_universe_survivors`` / ``screen_broad_universe_investability``
    (via the private ``_adv_survivors_at_floors`` helper) — the floor-sweep
    counts are computed with the SAME screen logic as the production RANKED
    path, just evaluated at 3 candidate cutoffs instead of 1.

    Parameters
    ----------
    candidates:
        DataFrame with at least a ``ticker`` column.  Works with either the
        raw ``fetch_broad_universe_candidates`` output (no ``sector``
        column — the Phase 9.1 probe callsite) or the shaped
        ``candidates_to_universe_frame`` output (has a ``sector`` column,
        always ``"Unknown"`` — the Phase 9.3 ranked-path callsite).
    prices_by_ticker:
        Ticker → OHLCV DataFrame already fetched (Step 1).  Same contract
        as the sibling screen functions.
    floors:
        Ascending-sortable tuple of ADV dollar floors to sweep.  Defaults to
        ``(BROAD_UNIVERSE_ADV_FLOOR_USD, 10_000_000.0, 15_000_000.0)`` — the
        FIRST entry is tied to the live production constant (not a literal)
        so the sweep always includes "today's floor" as a data point even
        after a future PR-2 re-pin.  The 3 named
        ``broad_universe_survivors_at_{5,10,15}m_count`` output keys map
        positionally to ``sorted(floors)[0:3]`` — a caller passing custom
        floors (e.g. a test exercising the general monotone-nesting
        property with arbitrary cutoffs) still gets internally-consistent,
        correctly-nested counts under those same 3 keys; only the "5m /
        10m / 15m" NAMING assumes the literal default values. Fewer than 3
        floors pads the remaining keys with ``None``; more than 3 floors
        only the first 3 (ascending) are surfaced under these 3 fixed keys.
    price_floor, adv_lookback_days:
        Same floors/window as the sibling screen functions.
    security_types_by_ticker:
        Optional ticker → security-type LABEL mapping (the value shape
        ``fetch_yfinance_security_type`` returns via
        ``compute.ingest.cross_source.security_type_label`` — e.g.
        ``"Common stock"`` for yfinance's ``EQUITY`` quote-type).  Required
        (together with ``foreign_filer_by_ticker``) to compute
        ``broad_universe_adr_suspect_count``.  ``None`` = signal unavailable
        this run (graceful degradation — see that field's description
        below).  NOT populated by the current ``compute/main.py`` callsite
        (security-type resolution happens later, in the Step 8 per-ticker
        loop) — always ``None`` in this PR; wired for a future slice.
    foreign_filer_by_ticker:
        Optional ticker → bool mapping, ``True`` when SEC signals a foreign
        private issuer (e.g. a 20-F filer, or EDGAR submissions-JSON
        ``entityType`` == "foreign private issuer").  THIS SIGNAL DOES NOT
        EXIST ANYWHERE IN THIS CODEBASE YET — per issue #541 PR-1b (see the
        ``cross_source.py`` module comment), wiring it requires a new SEC
        submissions-JSON fetch with no existing cache surface, which this
        PR deliberately does NOT add (no new EDGAR round-trip).  Always
        ``None`` at every current callsite; the parameter exists so a
        future slice can populate it without another schema bump.
    fundamentals_ok_by_ticker:
        Optional ticker → bool mapping ("this ticker's fundamentals
        snapshot is usable" — e.g. not ``_snapshot_has_no_usable_fundamentals``).
        Required to compute ``broad_universe_survivor_fundamentals_coverage_pct``.
        ``None`` = signal unavailable this run.  The current
        ``compute/main.py`` callsite calls this function immediately after
        Step 1 (prices) — BEFORE Step 2 (fundamentals) has run — so this is
        structurally ``None`` on every run until a future slice moves (or
        duplicates) the call after fundamentals are available.

    Returns
    -------
    dict with keys:
        broad_universe_survivors_at_5m_count    int | None
        broad_universe_survivors_at_10m_count   int | None
        broad_universe_survivors_at_15m_count   int | None
            Survivor counts at each ascending floor (MONOTONE-NESTED: count
            at a larger floor is always <= count at a smaller floor). All
            three ``None`` together when no candidate has any price data
            (``n_with_prices == 0``) or ``candidates`` is empty.
        broad_universe_adr_suspect_count        int | None
            Count of candidates whose security type resolves to "equity"
            (heuristic: case-insensitive match against ``"EQUITY"`` — the
            raw yfinance quote-type code — or ``"Common stock"`` — the
            mapped display label ``security_type_label`` returns) AND whose
            ``foreign_filer_by_ticker`` entry is ``True``.  ``None`` when
            EITHER input mapping is ``None`` (today: always, since neither
            signal is wired into any callsite yet — see the parameter docs
            above).  This is a DELIBERATELY CONSERVATIVE heuristic per
            issue #541 PR-1b: it never guesses at a ticker missing from
            ``foreign_filer_by_ticker`` (treated as "not known foreign",
              i.e. NOT counted, avoiding false positives from an
              incomplete mapping).
        broad_universe_survivor_fundamentals_coverage_pct   float | None
            % of the CHOSEN-FLOOR (the smallest floor in ``floors``, i.e.
            "today's production floor") survivors with usable fundamentals,
            per ``fundamentals_ok_by_ticker``.  ``None`` when that mapping
            is ``None`` (today: always — see the parameter docs above) or
            when the chosen-floor survivor set is empty.
        broad_universe_sector_unknown_pct   float | None
            % of the chosen-floor survivors whose ``sector`` is
            ``"Unknown"``.  When ``candidates`` HAS a ``sector`` column
            (the Phase 9.3 ranked-path callsite, always ``"Unknown"`` per
            ``candidates_to_universe_frame``), computed directly from it.
            When ``candidates`` has NO ``sector`` column at all (the Phase
            9.1 probe callsite — the raw SEC company-tickers source never
            carries GICS classification for any row), every chosen-floor
            survivor is counted as unknown-sector — this is a STRUCTURAL
            fact of the data source, not a per-run coincidence, so the
            value is a real measured percentage (documented to land
            ~100% "until a future SIC crosswalk" — see the module
            docstring's P1-G4 cross-reference), not a placeholder ``None``.
            ``None`` only when the chosen-floor survivor set is empty.

    Never raises — any internal failure degrades individual fields to
    ``None``, matching the graceful-degradation contract of every other
    function in this module. The caller (``compute/main.py``) additionally
    wraps the call site in its own try/except so a failure here can never
    block the cron.
    """
    _empty: dict[str, int | float | None] = {
        "broad_universe_survivors_at_5m_count": None,
        "broad_universe_survivors_at_10m_count": None,
        "broad_universe_survivors_at_15m_count": None,
        "broad_universe_adr_suspect_count": None,
        "broad_universe_survivor_fundamentals_coverage_pct": None,
        "broad_universe_sector_unknown_pct": None,
    }
    if candidates is None or candidates.empty:
        return dict(_empty)

    survivors_by_floor, n_with_prices = _adv_survivors_at_floors(
        candidates,
        prices_by_ticker,
        floors,
        price_floor=price_floor,
        adv_lookback_days=adv_lookback_days,
    )
    if n_with_prices == 0:
        return dict(_empty)

    sorted_floors = tuple(sorted(floors))
    raw_counts = [len(survivors_by_floor[f]) for f in sorted_floors]
    # Pad/truncate to exactly the 3 named slots this schema exposes — see
    # the ``floors`` parameter doc above for the positional-mapping contract.
    counts: list[int | None] = (raw_counts + [None, None, None])[:3]

    chosen_floor_survivors = survivors_by_floor[sorted_floors[0]]

    # --- ADR-suspect count (candidates, NOT restricted to survivors) -------
    adr_suspect_count: int | None
    if security_types_by_ticker is None or foreign_filer_by_ticker is None:
        adr_suspect_count = None
        logger.info(
            "[broad-universe-sweep] broad_universe_adr_suspect_count = None: "
            "%s unavailable this run (obs-first — field ships now, populates "
            "once a future slice wires the signal; see #541 PR-1b)",
            "security_types_by_ticker"
            if security_types_by_ticker is None
            else "foreign_filer_by_ticker",
        )
    else:
        adr_suspect_count = 0
        for ticker in candidates["ticker"].astype(str):
            st = security_types_by_ticker.get(ticker)
            is_equity = bool(st) and st.strip().upper() in ("EQUITY", "COMMON STOCK")
            if is_equity and bool(foreign_filer_by_ticker.get(ticker)):
                adr_suspect_count += 1

    # --- Chosen-floor survivor fundamentals coverage ------------------------
    survivor_fundamentals_coverage_pct: float | None
    if fundamentals_ok_by_ticker is None:
        survivor_fundamentals_coverage_pct = None
        logger.info(
            "[broad-universe-sweep] broad_universe_survivor_fundamentals_coverage_pct "
            "= None: fundamentals_ok_by_ticker unavailable — this function runs "
            "immediately after Step 1 (prices), before Step 2 (fundamentals) "
            "has fetched anything (obs-first — field ships now, populates "
            "once a future slice moves/duplicates the call after Step 2)"
        )
    elif not chosen_floor_survivors:
        survivor_fundamentals_coverage_pct = None
    else:
        n_ok = sum(
            1 for t in chosen_floor_survivors if fundamentals_ok_by_ticker.get(t)
        )
        survivor_fundamentals_coverage_pct = round(
            100.0 * n_ok / len(chosen_floor_survivors), 2
        )

    # --- Chosen-floor survivor sector-unknown rate ---------------------------
    sector_unknown_pct: float | None
    if not chosen_floor_survivors:
        sector_unknown_pct = None
    elif "sector" in candidates.columns:
        sector_by_ticker = candidates.assign(
            ticker=candidates["ticker"].astype(str)
        ).set_index("ticker")["sector"]
        n_unknown = sum(
            1
            for t in chosen_floor_survivors
            if str(sector_by_ticker.get(t, "Unknown")) == "Unknown"
        )
        sector_unknown_pct = round(100.0 * n_unknown / len(chosen_floor_survivors), 2)
    else:
        # No `sector` column at all — structurally every candidate from this
        # data source is sector-unknown (see module docstring /
        # candidates_to_universe_frame): the SEC company-tickers endpoint
        # carries no GICS classification for any row, so the ENTIRE
        # chosen-floor survivor cohort is "Unknown" regardless of whether a
        # caller happened to materialize an explicit column for it.
        sector_unknown_pct = 100.0

    logger.info(
        "[broad-universe-sweep] Survivors at $%s: %s | adr_suspect=%s | "
        "survivor_fundamentals_coverage=%s%% | sector_unknown=%s%%",
        [f"{f / 1e6:.0f}M" for f in sorted_floors],
        counts,
        adr_suspect_count,
        survivor_fundamentals_coverage_pct,
        sector_unknown_pct,
    )

    return {
        "broad_universe_survivors_at_5m_count": counts[0],
        "broad_universe_survivors_at_10m_count": counts[1],
        "broad_universe_survivors_at_15m_count": counts[2],
        "broad_universe_adr_suspect_count": adr_suspect_count,
        "broad_universe_survivor_fundamentals_coverage_pct": survivor_fundamentals_coverage_pct,
        "broad_universe_sector_unknown_pct": sector_unknown_pct,
    }
