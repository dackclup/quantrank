"""Forward-return computation from the gitignored price cache — Phase 4.6 task #2b.

Consumer of ``compute/cache/prices/<TICKER>.parquet`` (written by
``compute.ingest.prices.fetch_prices``). Walks the cached daily OHLCV
frame and computes the close-to-close N-month forward total return at
any as-of date.

Used by Phase 4.6 task #2c (per-pillar IC re-baseline at historical
dates) — for each ticker in the universe at as-of T, look up the
realized return over [T, T + horizon_months] and correlate against the
pillar score the ranking system produced at T.

Honest-baseline anchor: ``compute_manipulation_distribution`` and
``load_ranking_history`` answer "what did we rank?"; this module
answers "what actually paid off?". The pairing is what closes the
honest re-validation loop (Hou-Xue-Zhang 2020 RFS replicability +
McLean-Pontiff 2016 JF 32% decay).

API:
    >>> from datetime import date
    >>> from compute.validation.forward_returns import (
    ...     compute_forward_return,
    ...     compute_forward_returns_batch,
    ... )
    >>> compute_forward_return("AAPL", date(2024, 1, 2), 6)
    0.1842
    >>> compute_forward_returns_batch(["AAPL", "MSFT"], date(2024, 1, 2), 6)
    {'AAPL': 0.1842, 'MSFT': 0.0913}

Edge cases:
    - Ticker has no cached parquet → returns ``None`` (treated as
      "delisted before horizon" by the caller; cf. PR #277
      ``removed_since`` cohort).
    - Cache exists but as-of date is outside the cached range → ``None``.
    - As-of date trades but T + horizon is past the last row (still
      live) → ``None`` (caller treats as censored).
    - As-of date doesn't trade (weekend / holiday) → snap forward to
      the next trading day (≤ 5 calendar days; longer = ``None``).
    - T + horizon doesn't trade → snap back to the prior trading day
      within the same window.

Honest-baseline disclaimer per Research Report v1.0:
    Returns are NAIVE close-to-close — no dividends, no splits, no
    transaction costs, no slippage, no survivorship-bias correction
    (this module only loads price; the survivorship correction lives
    in PR #274 ``compute.ingest.historical_universe.members_at``).
    Callers MUST pair the universe drift report (PR #277) with the
    forward returns here when computing realized-return statistics.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date as _date
from datetime import timedelta
from pathlib import Path

import pandas as pd

from compute import config

logger = logging.getLogger(__name__)

# Approximate trading days per calendar month — used to derive a default
# horizon-in-rows when caller doesn't specify. Refined to NAV horizon by
# bisecting on the parquet's actual DatetimeIndex (no assumption that
# 21 × horizon_months exists in the frame).
_TRADING_DAYS_PER_MONTH: int = 21

# Maximum forward-snap window when as-of date doesn't trade (weekend /
# holiday). Days BEYOND this band yield None (caller treats as missing).
_MAX_FORWARD_SNAP_DAYS: int = 5

# Default close-column candidates, in priority order. yfinance writes
# both `Close` and `Adj Close`; we prefer `Adj Close` for total return
# (dividend-adjusted) and fall back to `Close` for pre-adjusted frames.
_CLOSE_COLUMN_CANDIDATES: tuple[str, ...] = ("Adj Close", "Close")


@dataclass(frozen=True)
class ForwardReturnResult:
    """Per-ticker forward return + the actual dates used.

    Useful for downstream IC computation where the realized return needs
    to be paired with the exact (T, T + horizon) the close prices came
    from — not the caller's nominal as-of date which may have snapped.
    """

    ticker: str
    as_of_date: _date
    horizon_months: int
    start_date: _date | None
    end_date: _date | None
    start_close: float | None
    end_close: float | None
    forward_return: float | None
    note: str = ""


def _resolve_close_column(df: pd.DataFrame) -> str | None:
    """Return the first close-column candidate present in ``df``."""
    for col in _CLOSE_COLUMN_CANDIDATES:
        if col in df.columns:
            return col
    return None


def _load_price_frame(
    ticker: str, *, cache_dir: Path | None = None
) -> pd.DataFrame | None:
    """Read the cached parquet for ``ticker``, or return ``None``.

    Pure file IO — no live fetch. Mirrors
    :func:`compute.ingest.prices.fetch_prices`'s on-disk format but does
    NOT trigger yfinance, so this is safe to call inside validation /
    backtest loops where ingest-cache-misses must NOT cascade into
    SEC-rate-limit hits.
    """
    dir_ = cache_dir if cache_dir is not None else config.PRICES_CACHE_DIR
    path = dir_ / f"{ticker}.parquet"
    if not path.exists():
        logger.debug("Price cache miss for %s (no parquet at %s)", ticker, path)
        return None
    try:
        df = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to read %s: %s", path, exc)
        return None
    if df.empty:
        return None
    # Coerce a DatetimeIndex if not already (yfinance writes one but
    # parquet round-trips can demote to range-index in some pandas /
    # pyarrow combos).
    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not coerce %s index to DatetimeIndex: %s", ticker, exc)
            return None
    return df.sort_index()


def _snap_to_trading_day(
    target: _date, index: pd.DatetimeIndex, *, direction: str
) -> _date | None:
    """Snap ``target`` forward / backward to the nearest trading day.

    ``direction="forward"`` returns the first index date >= target, up to
    ``_MAX_FORWARD_SNAP_DAYS`` calendar days later. ``direction="backward"``
    returns the last index date <= target within the same band. Returns
    ``None`` when no trading day exists within the window.
    """
    ts = pd.Timestamp(target)
    if direction == "forward":
        upper = ts + pd.Timedelta(days=_MAX_FORWARD_SNAP_DAYS)
        candidates = index[(index >= ts) & (index <= upper)]
        if len(candidates) == 0:
            return None
        return candidates[0].date()
    if direction == "backward":
        lower = ts - pd.Timedelta(days=_MAX_FORWARD_SNAP_DAYS)
        candidates = index[(index <= ts) & (index >= lower)]
        if len(candidates) == 0:
            return None
        return candidates[-1].date()
    raise ValueError(f"direction must be 'forward' or 'backward', got {direction!r}")


def compute_forward_return(
    ticker: str,
    as_of_date: _date,
    horizon_months: int,
    *,
    cache_dir: Path | None = None,
) -> float | None:
    """Compute the close-to-close forward N-month return for ``ticker``.

    Args:
        ticker: stock symbol matching the parquet basename in the cache.
        as_of_date: ranking-system "T" — return is measured from this day's close.
        horizon_months: forward horizon in months. Common values: 1, 3, 6, 12.
        cache_dir: optional override (defaults to ``config.PRICES_CACHE_DIR``).

    Returns:
        Forward total return as a float (e.g. ``0.10`` = +10% over the
        horizon), or ``None`` when any input gate fails:
            - No cached parquet
            - Empty frame or missing close column
            - As-of date snaps fail (more than 5 calendar days from a
              trading day)
            - As-of + horizon is past the last cached row (censored)

    Honest disclosure:
        - Returns are NAIVE (no transaction costs, no slippage)
        - ``Adj Close`` is preferred (dividend-adjusted) but the caller
          gets ``Close`` if ``Adj Close`` is missing — be aware that
          mixed-source comparisons can leak ~1-3% per year
    """
    if horizon_months <= 0:
        raise ValueError(f"horizon_months must be positive, got {horizon_months}")

    result = compute_forward_return_detailed(
        ticker, as_of_date, horizon_months, cache_dir=cache_dir
    )
    return result.forward_return


def compute_forward_return_detailed(
    ticker: str,
    as_of_date: _date,
    horizon_months: int,
    *,
    cache_dir: Path | None = None,
) -> ForwardReturnResult:
    """Like :func:`compute_forward_return` but returns the full result.

    Use this when downstream tooling needs to know the actual trading
    dates the return was measured between — e.g. IC computation that
    wants to align the ranking date with the realized-return start.
    """
    if horizon_months <= 0:
        raise ValueError(f"horizon_months must be positive, got {horizon_months}")

    df = _load_price_frame(ticker, cache_dir=cache_dir)
    if df is None:
        return ForwardReturnResult(
            ticker=ticker,
            as_of_date=as_of_date,
            horizon_months=horizon_months,
            start_date=None,
            end_date=None,
            start_close=None,
            end_close=None,
            forward_return=None,
            note="no cached parquet",
        )

    close_col = _resolve_close_column(df)
    if close_col is None:
        return ForwardReturnResult(
            ticker=ticker,
            as_of_date=as_of_date,
            horizon_months=horizon_months,
            start_date=None,
            end_date=None,
            start_close=None,
            end_close=None,
            forward_return=None,
            note=f"no close column (candidates={_CLOSE_COLUMN_CANDIDATES})",
        )

    index = df.index
    start = _snap_to_trading_day(as_of_date, index, direction="forward")
    if start is None:
        return ForwardReturnResult(
            ticker=ticker,
            as_of_date=as_of_date,
            horizon_months=horizon_months,
            start_date=None,
            end_date=None,
            start_close=None,
            end_close=None,
            forward_return=None,
            note=f"as_of {as_of_date} does not snap to trading day within {_MAX_FORWARD_SNAP_DAYS}d",
        )

    target_end = start + timedelta(days=int(round(horizon_months * 30.44)))
    end = _snap_to_trading_day(target_end, index, direction="backward")
    if end is None:
        return ForwardReturnResult(
            ticker=ticker,
            as_of_date=as_of_date,
            horizon_months=horizon_months,
            start_date=start,
            end_date=None,
            start_close=None,
            end_close=None,
            forward_return=None,
            note=f"horizon-end {target_end} past last cached row {index[-1].date()} (censored)",
        )

    if end <= start:
        return ForwardReturnResult(
            ticker=ticker,
            as_of_date=as_of_date,
            horizon_months=horizon_months,
            start_date=start,
            end_date=end,
            start_close=None,
            end_close=None,
            forward_return=None,
            note=f"end {end} not strictly after start {start} (horizon too short for cache resolution)",
        )

    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    try:
        start_close = float(df.loc[start_ts, close_col])
        end_close = float(df.loc[end_ts, close_col])
    except KeyError as exc:
        return ForwardReturnResult(
            ticker=ticker,
            as_of_date=as_of_date,
            horizon_months=horizon_months,
            start_date=start,
            end_date=end,
            start_close=None,
            end_close=None,
            forward_return=None,
            note=f"loc-lookup failed: {exc}",
        )

    if start_close <= 0 or not (start_close == start_close):  # NaN-safe
        return ForwardReturnResult(
            ticker=ticker,
            as_of_date=as_of_date,
            horizon_months=horizon_months,
            start_date=start,
            end_date=end,
            start_close=start_close,
            end_close=end_close,
            forward_return=None,
            note="start_close non-positive / NaN",
        )

    if not (end_close == end_close):  # NaN-safe
        return ForwardReturnResult(
            ticker=ticker,
            as_of_date=as_of_date,
            horizon_months=horizon_months,
            start_date=start,
            end_date=end,
            start_close=start_close,
            end_close=end_close,
            forward_return=None,
            note="end_close NaN",
        )

    fwd_return = (end_close - start_close) / start_close
    return ForwardReturnResult(
        ticker=ticker,
        as_of_date=as_of_date,
        horizon_months=horizon_months,
        start_date=start,
        end_date=end,
        start_close=start_close,
        end_close=end_close,
        forward_return=fwd_return,
        note="",
    )


def compute_forward_returns_batch(
    tickers: Iterable[str],
    as_of_date: _date,
    horizon_months: int,
    *,
    cache_dir: Path | None = None,
) -> dict[str, float | None]:
    """Batch wrapper for :func:`compute_forward_return`.

    Returns:
        Dict mapping ``ticker → float | None`` — the None values are
        kept (not filtered out) so the caller can distinguish "missing
        data" from "computed and zero" downstream. Tickers in the input
        order are preserved as dict-insertion order (Python 3.7+).
    """
    out: dict[str, float | None] = {}
    for ticker in tickers:
        out[ticker] = compute_forward_return(
            ticker, as_of_date, horizon_months, cache_dir=cache_dir
        )
    return out


def coverage_report(
    tickers: Iterable[str],
    as_of_date: _date,
    horizon_months: int,
    *,
    cache_dir: Path | None = None,
) -> dict[str, int]:
    """Aggregate counts of why returns failed across a ticker universe.

    Useful for the Phase 4.6 #2c IC re-baseline — surfaces whether the
    survivorship-bias-corrected cohort is missing > N% of returns
    (typical Hou-Xue-Zhang 2020 RFS report rate: 5-15% missing on a
    cross-section depending on cache freshness + delisting density).

    Returns:
        Dict with keys::

            "total"     : universe size
            "ok"        : tickers with a non-None forward return
            "no_cache"  : tickers missing the parquet on disk
            "no_close"  : parquet exists but missing the close column
            "no_snap"   : as-of doesn't snap within the 5-day window
            "censored"  : horizon-end past the last cached row
            "bad_price" : start_close non-positive / NaN
            "nan_end"   : end_close NaN
            "other"     : everything else
    """
    counts = {
        "total": 0,
        "ok": 0,
        "no_cache": 0,
        "no_close": 0,
        "no_snap": 0,
        "censored": 0,
        "bad_price": 0,
        "nan_end": 0,
        "other": 0,
    }
    for ticker in tickers:
        counts["total"] += 1
        result = compute_forward_return_detailed(
            ticker, as_of_date, horizon_months, cache_dir=cache_dir
        )
        if result.forward_return is not None:
            counts["ok"] += 1
            continue
        note = result.note
        if "no cached parquet" in note:
            counts["no_cache"] += 1
        elif "no close column" in note:
            counts["no_close"] += 1
        elif "does not snap" in note:
            counts["no_snap"] += 1
        elif "censored" in note or "past last cached" in note:
            counts["censored"] += 1
        elif "non-positive" in note:
            counts["bad_price"] += 1
        elif "end_close NaN" in note:
            counts["nan_end"] += 1
        else:
            counts["other"] += 1
    return counts


__all__ = [
    "ForwardReturnResult",
    "compute_forward_return",
    "compute_forward_return_detailed",
    "compute_forward_returns_batch",
    "coverage_report",
]
