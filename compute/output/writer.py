"""Atomic JSON writers (Rule 12 — never leave a partial file on disk)."""

from __future__ import annotations

import json
import logging
import math
import os
from pathlib import Path
from typing import Any

import pandas as pd

from compute.output.schemas import Metadata, StockDetail, StockSummary

logger = logging.getLogger(__name__)


HISTORY_TAIL_DAYS = 252  # ~1 trading year


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
