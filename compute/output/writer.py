"""Atomic JSON writers (Rule 12 — never leave a partial file on disk)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from compute.output.schemas import Metadata, StockDetail, StockSummary

logger = logging.getLogger(__name__)


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
