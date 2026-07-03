"""Atomic JSON writers (Rule 12 — never leave a partial file on disk)."""

from __future__ import annotations

import json
import logging
import math
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

from compute.output.schemas import Metadata, StockDetail, StockSummary

logger = logging.getLogger(__name__)


HISTORY_TAIL_DAYS = 1260  # ~5 trading years (PR 4f Phase 4.2 — was 252)


def atomic_write_json(path: Path, data: Any) -> None:
    """Write ``data`` to ``path`` atomically via tmp file + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    logger.info("Wrote %s (%d bytes)", path, path.stat().st_size)


def write_rankings_json(rows: list[StockSummary], data_dir: Path) -> Path:
    payload = [r.model_dump(mode="json") for r in rows]
    out = data_dir / "rankings.json"
    atomic_write_json(out, payload)
    return out


def write_metadata_json(meta: Metadata, data_dir: Path) -> Path:
    out = data_dir / "metadata.json"
    atomic_write_json(out, meta.model_dump(mode="json"))
    return out


def write_stock_detail(detail: StockDetail, data_dir: Path) -> Path:
    """Write per-stock detail JSON to ``data_dir / 'stocks' / '{ticker}.json'``."""
    out = data_dir / "stocks" / f"{detail.ticker}.json"
    atomic_write_json(out, detail.model_dump(mode="json"))
    return out


def write_stock_history(
    *,
    ticker: str,
    prices_df: pd.DataFrame,
    output_dir: Path,
) -> bool:
    """Write per-stock 1-year OHLCV history JSON, atomically.

    Slices the last ``min(HISTORY_TAIL_DAYS, len(prices_df))`` rows of
    ``prices_df`` (which carries OHLCV columns from the yfinance
    ingest) and writes a column-major JSON to
    ``output_dir/stocks/history/{TICKER}.json``. NaN values are
    serialized as ``null`` (JSON-compatible, frontend-renderer-friendly).

    Returns
    -------
    bool
        True if the file was written; False on empty input, missing
        columns, or any I/O error. Step 7 sets ``has_history = True``
        in StockDetail iff this returns True for that ticker.
    """
    if prices_df is None or len(prices_df) == 0:
        return False

    close_col = "Adj Close" if "Adj Close" in prices_df.columns else "Close"
    required = {"Open", "High", "Low", close_col, "Volume"}
    if not required.issubset(prices_df.columns):
        logger.warning(
            "write_stock_history: %s missing OHLCV columns (have %s)",
            ticker,
            list(prices_df.columns),
        )
        return False

    tail = prices_df.tail(min(HISTORY_TAIL_DAYS, len(prices_df)))

    def _column_to_list(col: pd.Series, *, as_int: bool = False) -> list:
        """Serialize a pandas column to JSON-safe list (NaN → None)."""
        out: list = []
        for v in col.tolist():
            if v is None:
                out.append(None)
                continue
            try:
                f = float(v)
            except (TypeError, ValueError):
                out.append(None)
                continue
            if not math.isfinite(f):
                out.append(None)
                continue
            out.append(int(f) if as_int else f)
        return out

    payload: dict[str, Any] = {
        "ticker": ticker,
        "dates": [d.strftime("%Y-%m-%d") for d in tail.index],
        "opens": _column_to_list(tail["Open"]),
        "highs": _column_to_list(tail["High"]),
        "lows": _column_to_list(tail["Low"]),
        "closes": _column_to_list(tail[close_col]),
        "volumes": _column_to_list(tail["Volume"], as_int=True),
    }

    try:
        out_path = output_dir / "stocks" / "history" / f"{ticker}.json"
        atomic_write_json(out_path, payload)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("write_stock_history: %s atomic write failed: %s", ticker, e)
        return False


# Defensive floor: never prune when the "keep" set is implausibly small. A
# degraded run (empty / truncated rankings) must NOT be allowed to wipe the
# whole stocks/ directory. The live universe is ~502, and run_weekly_compute
# already aborts before the write step if too few tickers priced — so a healthy
# run is never anywhere near this floor.
_PRUNE_SAFETY_FLOOR = 50


def prune_orphan_stock_files(keep_tickers: Iterable[str], data_dir: Path) -> list[str]:
    """Delete per-stock JSON for tickers no longer in the universe.

    The weekly cron rewrites ``stocks/{TICKER}.json`` (+ ``stocks/history/
    {TICKER}.json``) for every CURRENT constituent but never removes the files
    of a DROPPED ticker — so an index de-listing (e.g. EPAM leaving the S&P 500)
    leaves orphan detail + history files shipping forever in the static export.
    The orphan never renders a page (``generateStaticParams`` reads
    ``rankings.json`` with ``dynamicParams = false``, so ``/stock/<dropped>``
    404s), but the file count drifts above the ranked-universe count — which
    trips production-output verification and bloats the deploy.

    Removes both ``stocks/{T}.json`` and ``stocks/history/{T}.json`` for every
    ``T`` not in ``keep_tickers``. The weekly cron's existing
    ``git add frontend/public/data/`` stages the deletions (git >= 2.0 pathspec
    semantics record removals), so no workflow change is needed.

    Safety: pruning is SKIPPED entirely when ``keep_tickers`` is smaller than
    ``_PRUNE_SAFETY_FLOOR`` so a degraded run can never wipe ``stocks/``.

    Returns
    -------
    list[str]
        The sorted tickers whose files were pruned (for logging / audit).
    """
    keep = {str(t) for t in keep_tickers}
    if len(keep) < _PRUNE_SAFETY_FLOOR:
        logger.warning(
            "prune_orphan_stock_files: keep set too small (%d < %d) — skipping "
            "prune so a degraded run cannot wipe stocks/",
            len(keep),
            _PRUNE_SAFETY_FLOOR,
        )
        return []

    pruned: set[str] = set()
    for sub in (data_dir / "stocks", data_dir / "stocks" / "history"):
        if not sub.is_dir():
            continue
        for f in sub.glob("*.json"):
            if f.stem in keep:
                continue
            try:
                f.unlink()
                pruned.add(f.stem)
            except OSError as e:
                logger.warning(
                    "prune_orphan_stock_files: could not remove %s: %s", f, e
                )

    if pruned:
        logger.warning(
            "Pruned %d orphan stock ticker(s) (de-listed / dropped): %s",
            len(pruned),
            ", ".join(sorted(pruned)),
        )
    return sorted(pruned)


def write_benchmarks_json(
    benchmarks: dict[str, pd.DataFrame | None],
    output_dir: Path,
) -> tuple[Path | None, float]:
    """Write the multi-index benchmark close series for the portfolio backtest.

    Writes a column-major JSON to ``output_dir/portfolio/benchmarks.json``::

        {"dates": ["YYYY-MM-DD", ...],
         "spy": [float | null, ...], "qqq": [...], "dia": [...], "iwm": [...]}

    keyed by LOWERCASE ticker. Each series is the Adj-Close-preferred close over the
    FULL fetched window (fixed floor ``config.PRICES_FETCH_START`` = 2015-11-29,
    ~10.5y and growing ~1y/year) — NOT capped at the
    per-stock ``HISTORY_TAIL_DAYS`` (~5y) — so the AI-pick backtest's "Max" chart can
    show the benchmark line across the full fixed-floor span (a 5y cap would blank the SPY/QQQ
    line for the pre-2021 half). This file is read ONLY by the backfill (the frontend
    uses the pre-aligned ``nav.benchmark`` in ``backtest_pit.json``), so its size is
    not a frontend-payload concern. Aligned to the UNION of all benchmarks' trading
    dates (a symbol missing a date → ``null``). NaN → null.

    F2 (AI-pick backtest methodology fix, price-basis guard): tracks, per symbol,
    whether the series was built from the dividend-adjusted ``"Adj Close"`` column or
    fell back to the raw ``"Close"`` column (no ``"Adj Close"`` in the fetched frame).
    A raw-``Close`` benchmark understates total return for a dividend-paying index ETF
    (SPY/DIA/IWM) — this is logged loudly (``logger.warning``, named per-symbol) and
    disclosed in ``payload["price_basis"]`` so a downstream consumer (the backfill's
    ``meta.benchmark_price_basis`` + disclaimer clause) can flag any raw-basis
    comparison rather than silently mixing adjusted and unadjusted series. Fallback
    behavior (use raw ``Close``) is UNCHANGED from before this fix — this is
    observability only, never a functional change to which column is used.

    Returns
    -------
    tuple[Path | None, float]
        ``(path, coverage_pct)`` where ``coverage_pct`` is the % of requested
        benchmarks that produced a non-empty series — surfaced as
        ``Metadata.benchmark_coverage_pct`` (observability-before-wiring: the
        field ships ≥ 1 cron before the home page reads this file). ``path`` is
        ``None`` when NO benchmark had usable data (the cron continues — the
        benchmark layer is display-only).
    """
    requested = list(benchmarks.keys())
    series_by_sym: dict[str, pd.Series] = {}
    basis_by_sym: dict[str, str] = {}
    for sym, df in benchmarks.items():
        if df is None or len(df) == 0:
            continue
        has_adj_close = "Adj Close" in df.columns
        close_col = "Adj Close" if has_adj_close else "Close"
        if close_col not in df.columns:
            continue
        if not has_adj_close:
            logger.warning(
                "write_benchmarks_json: %s has no 'Adj Close' column — falling back "
                "to raw 'Close'. This UNDERSTATES total return for a dividend-paying "
                "benchmark (dividend drag is not reflected in the series).",
                sym,
            )
        # Full window (not HISTORY_TAIL_DAYS-capped) — the backtest needs the whole
        # fixed-floor span for its Max benchmark line; benchmarks.json is backfill-only.
        series_by_sym[sym] = df[close_col]
        basis_by_sym[sym] = "adjusted" if has_adj_close else "close"

    coverage_pct = (
        round(100.0 * len(series_by_sym) / len(requested), 1) if requested else 0.0
    )
    if not series_by_sym:
        return None, coverage_pct

    all_dates = sorted(set().union(*(set(s.index) for s in series_by_sym.values())))
    payload: dict[str, Any] = {"dates": [d.strftime("%Y-%m-%d") for d in all_dates]}
    payload["price_basis"] = {
        sym.lower(): basis_by_sym[sym] for sym in requested if sym in basis_by_sym
    }
    for sym in requested:
        s = series_by_sym.get(sym)
        if s is None:
            payload[sym.lower()] = [None] * len(all_dates)
            continue
        col: list = []
        for v in s.reindex(all_dates).tolist():
            try:
                f = float(v)
            except (TypeError, ValueError):
                col.append(None)
                continue
            col.append(f if math.isfinite(f) else None)
        payload[sym.lower()] = col

    try:
        out_path = output_dir / "portfolio" / "benchmarks.json"
        atomic_write_json(out_path, payload)
        return out_path, coverage_pct
    except Exception as e:  # noqa: BLE001
        logger.warning("write_benchmarks_json atomic write failed: %s", e)
        return None, coverage_pct


def write_backtest_pit_json(payload: dict[str, Any], output_dir: Path) -> Path:
    """Write the point-in-time portfolio backtest artifact atomically.

    Target: ``output_dir/portfolio/backtest_pit.json``. The artifact is
    self-describing — it carries its OWN ``meta`` block (window, rebalance count,
    survivorship + restatement canaries, the honesty disclaimer) rather than
    leaning on ``metadata.json``, because the backfill is a standalone
    ``workflow_dispatch`` job, NOT the weekly cron (which would have to
    read-modify-write metadata.json and race the bot commit). Produced by
    ``scripts/backfill_portfolio_pit.py``; consumed by the home page (PR-4).
    """
    out = output_dir / "portfolio" / "backtest_pit.json"
    atomic_write_json(out, payload)
    return out


def read_previous_top5(data_dir: Path) -> set[str]:
    """Return the ticker set that ranked in the previous run's Top-5.

    Returns an empty set if ``rankings.json`` doesn't exist (first run) or
    can't be parsed. Used for entered_top5 / exited_top5 annotations.
    """
    path = data_dir / "rankings.json"
    if not path.exists():
        return set()
    try:
        with path.open("r", encoding="utf-8") as f:
            rows = json.load(f)
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not read previous rankings.json (%s): %s", path, e)
        return set()
    return {
        str(r["ticker"])
        for r in rows[:5]
        if isinstance(r, dict) and "ticker" in r
    }
