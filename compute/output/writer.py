"""Atomic JSON writers (Rule 12 — never leave a partial file on disk)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from compute.output.schemas import Metadata, StockSummary

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
