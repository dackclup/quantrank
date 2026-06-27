"""Daily OHLCV prices via yfinance, with disk caching and tenacity retry.

Returns ``None`` on persistent failure or empty response so the orchestrator
can skip the ticker without crashing the whole run.
"""

from __future__ import annotations

import datetime
import logging
import math as _math
import os
import time

import pandas as pd
import yfinance as yf
from tenacity import retry, stop_after_attempt, wait_exponential

from compute import config

logger = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10), reraise=True)
def _yf_download(
    ticker: str,
    period: str,
    *,
    start: datetime.date | None = None,
) -> pd.DataFrame:
    """Download OHLCV (+ Dividends when ``QR_SKIP_DIVIDENDS`` is unset) from yfinance.

    Parameters
    ----------
    ticker:
        Exchange symbol.
    period:
        yfinance period string (e.g. ``"10y"``, ``"max"``).  Used only when
        ``start`` is ``None`` — when ``start`` is provided the ``start=`` date
        path is used instead and ``period`` is ignored by this function.
        Callers that bypass ``fetch_prices`` and call ``_yf_download`` directly
        (e.g. tests) may still use ``period`` alone (``start=None``).
    start:
        Optional fixed calendar floor for the download.  When provided,
        ``yf.download`` is called with ``start=start.isoformat()`` and no
        ``period`` argument, fetching all available data from that date forward.

    Notes
    -----
    ``actions=True`` is passed to ``yf.download`` so the ``Dividends`` (and
    ``Stock Splits``) column is fetched on the SAME HTTP round-trip at zero
    extra cost.  The ``Dividends`` column is used by
    ``fetch_dividends_panel`` (Option-B shadow NAV series, issue #620).
    Set ``QR_SKIP_DIVIDENDS=1`` to suppress this addition (the column will be
    absent from the returned frame and ``fetch_dividends_panel`` degrades
    gracefully to an empty dict).

    MultiIndex flatten: when yfinance returns a MultiIndex (multi-ticker
    download — rare here since we download per-ticker), the existing
    ``get_level_values(0)`` call flattens the first level.  For single-ticker
    downloads with ``actions=True``, yfinance returns a flat column set that
    already includes ``Dividends`` — no special handling required.
    """
    _skip_dividends = bool(os.environ.get("QR_SKIP_DIVIDENDS"))
    _actions = not _skip_dividends
    if start is not None:
        df = yf.download(
            ticker,
            start=start.isoformat(),
            auto_adjust=False,
            actions=_actions,
            progress=False,
            threads=False,
            group_by="column",
        )
    else:
        df = yf.download(
            ticker,
            period=period,
            auto_adjust=False,
            actions=_actions,
            progress=False,
            threads=False,
            group_by="column",
        )
    if isinstance(df.columns, pd.MultiIndex):
        # Flatten MultiIndex: prefer level 0 (the field name — Open/High/Low/Close/
        # Volume/Dividends/Stock Splits) rather than level 1 (the ticker), which is
        # what the existing code uses for single-ticker downloads.
        df.columns = df.columns.get_level_values(0)
    return df


SPY_TICKER: str = "SPY"


def fetch_spy_benchmark(period: str = config.PRICES_PERIOD) -> pd.DataFrame | None:
    """Fetch SPY OHLCV for use as the β benchmark + market-return baseline."""
    return fetch_prices(SPY_TICKER, period=period)


# Phase 7.0 PR-1 — index-proxy ETFs exported for the portfolio-backtest
# benchmark selector. SPY = S&P 500 (also the β baseline above); QQQ =
# Nasdaq-100; DIA = Dow Jones Industrial Average; IWM = Russell 2000.
# Display-only — no scoring / ranking / veto impact; the home page lets the
# user compare the AI-pick basket against the chosen index. SPY shares
# fetch_prices' on-disk cache with fetch_spy_benchmark (no double download).
BENCHMARK_TICKERS: tuple[str, ...] = ("SPY", "QQQ", "DIA", "IWM")


def fetch_benchmarks(
    period: str = config.PRICES_PERIOD,
) -> dict[str, pd.DataFrame | None]:
    """Fetch OHLCV for each ``BENCHMARK_TICKERS`` symbol, degrading per symbol.

    Returns a dict keyed by ticker; the value is ``None`` when that symbol's
    fetch failed (network / empty response). Never raises — a single benchmark
    failure must not block the weekly cron (graceful-degradation pattern); the
    caller surfaces the success rate as ``Metadata.benchmark_coverage_pct``.
    """
    out: dict[str, pd.DataFrame | None] = {}
    for sym in BENCHMARK_TICKERS:
        try:
            out[sym] = fetch_prices(sym, period=period)
        except Exception as e:  # noqa: BLE001
            logger.warning("benchmark fetch failed for %s: %s", sym, e)
            out[sym] = None
    return out


def fetch_prices(
    ticker: str,
    period: str = config.PRICES_PERIOD,
    min_start: datetime.date | None = None,
) -> pd.DataFrame | None:
    """Return a daily OHLCV DataFrame for ``ticker``, or ``None`` on failure.

    Parameters
    ----------
    ticker:
        Exchange symbol to fetch.
    period:
        yfinance period string (e.g. ``"10y"``, ``"max"``).  On the default
        code path ALL downloads use ``start=config.PRICES_FETCH_START`` (a
        fixed calendar floor) regardless of this argument, so ``period`` is
        vestigial on that path and is kept only for interface stability and for
        callers that call ``_yf_download`` directly (e.g. tests).  Passing an
        explicit ``period`` here does NOT override the fixed start floor.
    min_start:
        Optional earliest-date floor for depth-sensitive callers.  The cache is
        period-blind (keyed by ticker, not by period), so a cached frame may be
        shallower than required for a long backtest window.  When ``min_start``
        is provided and a fresh cache hit's earliest index date is AFTER
        ``min_start``, the cached frame is treated as a depth miss: the function
        refetches once (using ``start=config.PRICES_FETCH_START`` — the fixed
        floor satisfies any ``min_start`` that is <= it), writes the deeper
        frame to the cache, and returns it.  The refetch happens AT MOST ONCE
        per call — if the newly fetched frame still starts after ``min_start``
        that IS the full history available (e.g. a recently-listed ticker), and
        the result is cached and returned without looping.
        Default ``None`` = byte-identical current behaviour (the live weekly
        compute path never passes this argument).
        Fail-closed: if the deeper refetch itself fails, ``None`` is returned
        even though a (shallow) fresh cache exists — a silently short sigma
        window is the bug this parameter prevents, so the ticker drops from
        that run instead.
    """
    cache_dir = config.PRICES_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{ticker}.parquet"

    if cache_path.exists():
        age_hours = (time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < config.PRICES_CACHE_MAX_AGE_HOURS:
            try:
                cached = pd.read_parquet(cache_path)
                # Depth check: if min_start is set and the cached frame is
                # shallower than required, fall through to a fresh download.
                if min_start is None or _frame_covers(cached, min_start):
                    # Data-recency guard — the authoritative freshness check on GHA.
                    # ``actions/cache`` restore resets mtime to "now" each run, so the
                    # mtime-based age_hours check above is DEAD on GHA (always looks
                    # fresh).  We verify the actual DATA is recent by checking the last
                    # bar date.  If it is None (empty frame) we fall through unchanged;
                    # if it is stale (> PRICES_CACHE_MAX_STALE_DAYS calendar days old)
                    # we log and fall through to a live refetch regardless of mtime.
                    last_bar = _latest_date(cached)
                    if last_bar is not None:
                        calendar_days_stale = (
                            datetime.date.today() - last_bar
                        ).days
                        if calendar_days_stale > config.PRICES_CACHE_MAX_STALE_DAYS:
                            logger.info(
                                "fetch_prices(%s): cache last-bar %s is %d days old"
                                " > floor %d — refetching",
                                ticker,
                                last_bar,
                                calendar_days_stale,
                                config.PRICES_CACHE_MAX_STALE_DAYS,
                            )
                            # Fall through to live download below.
                        else:
                            return cached
                    else:
                        return cached
                logger.info(
                    "fetch_prices(%s): cache shallow (earliest %s > floor %s) — refetching",
                    ticker,
                    _earliest_date(cached),
                    min_start,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("Cache read failed for %s: %s", ticker, e)

    try:
        # All downloads use the fixed PRICES_FETCH_START floor — this ensures
        # the shared cache always carries the depth the backfill's min_start
        # contract requires, eliminating the per-run sequential max-refetch.
        # The ``period`` argument is vestigial on this path (see docstring).
        df = _yf_download(ticker, period=period, start=config.PRICES_FETCH_START)
    except Exception as e:  # noqa: BLE001
        logger.warning("yfinance download failed for %s: %s", ticker, e)
        return None

    if df is None or df.empty:
        logger.warning("Empty price response for %s", ticker)
        return None

    # If the freshly downloaded frame is still shallower than min_start, that
    # IS the full history for this ticker (new listing).  Cache and return it —
    # no retry loop.
    if min_start is not None and not _frame_covers(df, min_start):
        logger.info(
            "fetch_prices(%s): max-depth frame still starts at %s (after floor %s) "
            "— new listing or data unavailable; caching as-is",
            ticker,
            _earliest_date(df),
            min_start,
        )

    try:
        df.to_parquet(cache_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("Cache write failed for %s: %s", ticker, e)

    return df


def compute_average_dollar_volume(
    df: pd.DataFrame | None,
    lookback_days: int,
) -> float | None:
    """Return trailing-N-day mean dollar volume (close * volume) in USD.

    Parameters
    ----------
    df:
        Daily OHLCV DataFrame as returned by ``fetch_prices``.  Must contain
        a close column (``"Close"`` or ``"Adj Close"``) and a ``"Volume"``
        column.  ``None`` or empty → ``None``.
    lookback_days:
        Number of trailing trading-day rows to average over.  Recommended
        value: ``config.ADV_LOOKBACK_DAYS`` (30).

    Returns
    -------
    float | None
        Mean daily dollar volume over the last ``lookback_days`` trading
        days, or ``None`` when volume data is missing, zero-filled, or
        the frame has fewer than 1 usable row.

    Graceful degradation contract (Rule 18)
    ----------------------------------------
    Never raises.  Any failure — missing column, NaN-only series,
    insufficient depth — silently returns ``None`` so the caller can
    propagate ``None`` without breaking the weekly cron.
    """
    if df is None or df.empty:
        return None
    try:
        # Pick the close column (prefer Adj Close for return accuracy).
        if "Adj Close" in df.columns:
            close_col = "Adj Close"
        elif "Close" in df.columns:
            close_col = "Close"
        else:
            return None

        if "Volume" not in df.columns:
            return None

        # Slice the last N rows (most-recent trading days).
        tail = df[[close_col, "Volume"]].tail(lookback_days)
        if tail.empty:
            return None

        close = tail[close_col].astype(float)
        volume = tail["Volume"].astype(float)

        # Dollar volume = price × shares traded per day.
        dollar_vol = close * volume

        # Drop NaN / infinite values before averaging.
        dollar_vol = dollar_vol.replace(
            [float("inf"), float("-inf")], float("nan")
        )
        dollar_vol = dollar_vol.dropna()

        if dollar_vol.empty:
            return None

        mean_adv = float(dollar_vol.mean())
        if not _math.isfinite(mean_adv) or mean_adv <= 0:
            return None

        return mean_adv
    except Exception:  # noqa: BLE001
        # Broad catch: never let a volume computation failure crash the cron.
        return None


def fetch_dividends_panel(
    price_frames: dict[str, pd.DataFrame | None],
) -> dict[str, dict[str, float]]:
    """Extract the ``Dividends`` column from pre-fetched price frames.

    Parameters
    ----------
    price_frames:
        ``{ticker: DataFrame | None}`` as produced by the Step-1 prices loop.
        DataFrames MUST already contain a ``Dividends`` column (present when
        ``_yf_download`` was called with ``actions=True`` and
        ``QR_SKIP_DIVIDENDS`` was not set).  Frames that lack the column (old
        cached parquets, or a ``QR_SKIP_DIVIDENDS=1`` run) are silently skipped
        — graceful degradation, NOT a crash.

    Returns
    -------
    dict[str, dict[str, float]]
        ``{ticker: {iso_date: div_per_share}}`` containing only ex-dates with a
        non-zero, finite dividend.  Returns an empty dict when
        ``QR_SKIP_DIVIDENDS=1`` is set or when no frame has a ``Dividends``
        column — the Option-B shadow NAV caller treats an empty panel as
        "no dividends available" and degrades gracefully.

    Notes
    -----
    * Zero-value rows (``Dividends == 0``) are dropped — yfinance emits a 0
      for every trading day; only actual ex-dates have positive values.
    * This function is a PURE READ of data already downloaded and cached by
      ``fetch_prices``; it performs zero network calls.
    * Set ``QR_SKIP_DIVIDENDS=1`` to suppress the entire dividend panel (useful
      for debugging or environments where yfinance ``actions=True`` is not
      available).  The escape hatch mirrors ``QR_SKIP_SPLITS``.
    * Rule 18 (observability-before-wiring): this panel feeds the Option-B
      SHADOW NAV series only (``nav.adaptive_div_pooled``).  The live
      ``nav.adaptive`` path is BYTE-IDENTICAL regardless of this panel.
    """
    if bool(os.environ.get("QR_SKIP_DIVIDENDS")):
        logger.info("fetch_dividends_panel: QR_SKIP_DIVIDENDS=1 — returning empty panel")
        return {}

    panel: dict[str, dict[str, float]] = {}
    for ticker, df in price_frames.items():
        if df is None or df.empty:
            continue
        if "Dividends" not in df.columns:
            # Old cached parquet or QR_SKIP_DIVIDENDS run — skip silently.
            continue
        try:
            div_series = df["Dividends"].dropna()
            # Keep only positive (actual ex-date) rows.
            div_series = div_series[div_series > 0.0]
            if div_series.empty:
                continue
            ticker_map: dict[str, float] = {}
            for ts, val in div_series.items():
                val_f = float(val)
                if _math.isfinite(val_f) and val_f > 0.0:
                    # Convert pandas Timestamp index to ISO date string.
                    if hasattr(ts, "date"):
                        iso_date = ts.date().isoformat()
                    elif isinstance(ts, datetime.date):
                        iso_date = ts.isoformat()
                    else:
                        iso_date = str(ts)[:10]
                    ticker_map[iso_date] = val_f
            if ticker_map:
                panel[ticker] = ticker_map
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "fetch_dividends_panel: skipping %s due to error: %s", ticker, e
            )
    logger.info(
        "fetch_dividends_panel: %d tickers with dividend data out of %d frames",
        len(panel),
        len(price_frames),
    )
    return panel


def _earliest_date(df: pd.DataFrame) -> datetime.date | None:
    """Return the earliest index date of a price DataFrame, or ``None`` if empty."""
    if df is None or df.empty:
        return None
    idx = df.index
    first = idx[0]
    if hasattr(first, "date"):
        return first.date()
    if isinstance(first, datetime.date):
        return first
    return None


def _latest_date(df: pd.DataFrame) -> datetime.date | None:
    """Return the latest index date of a price DataFrame, or ``None`` if empty.

    Mirrors ``_earliest_date``'s exact style: handles both pandas Timestamp
    (via ``.date()``) and bare ``datetime.date`` index types.  Returns ``None``
    for ``None`` or empty frames so callers can treat the result uniformly.
    """
    if df is None or df.empty:
        return None
    idx = df.index
    last = idx[-1]
    if hasattr(last, "date"):
        return last.date()
    if isinstance(last, datetime.date):
        return last
    return None


# Depth-check grace window: the floor may land on a non-trading day (e.g. the
# canonical PRICES_FETCH_START 2015-11-29 is a SUNDAY — the first available row
# is Monday 2015-11-30), so an exact `earliest <= floor` comparison would fail
# against the floor itself and re-trigger the deep refetch on EVERY warm run —
# silently reinstating the per-run cost Design A removes. 7 days absorbs any
# weekend/holiday cluster. Design choice: a grace window beats moving the floor
# to a trading day — it stays correct if the floor constant is ever edited.
_DEPTH_GRACE_DAYS = 7


def _frame_covers(df: pd.DataFrame, floor: datetime.date) -> bool:
    """True when ``df``'s earliest row is within ``_DEPTH_GRACE_DAYS`` of ``floor``
    (on/before it, or just after when the floor is a non-trading day)."""
    earliest = _earliest_date(df)
    if earliest is None:
        return False
    return earliest <= floor + datetime.timedelta(days=_DEPTH_GRACE_DAYS)
