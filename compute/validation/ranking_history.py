"""Git-archived ``rankings.json`` time-series loader.

Phase 4.6 task #2 follow-up #2a (per
``docs/research/historical-revalidation-harness.md`` Future-work TODO).

Walks ``git log`` to enumerate every historical commit that touched
``frontend/public/data/rankings.json``, then ``git show``s each one to
reconstruct the daily composite_score time series per ticker. This is
the data source for downstream per-pillar IC re-baselining (#2c) and
manipulation-index distribution shift analysis (#2e).

Pure-functional + cached. Spawns a small number of ``git`` subprocess
calls — fast for the ~6-month window of cron commits the project has
on main.

API:
    >>> from datetime import date
    >>> from compute.validation.ranking_history import load_ranking_history
    >>> df = load_ranking_history(date(2026, 5, 1), date(2026, 5, 27))
    >>> df.head()
                    composite_score
    date       ticker
    2026-05-26 NVDA              73.39
               AAPL              68.21
               ...

Schema-compat: handles both the current ``0.10.x`` rankings.json shape
and earlier ``0.5.x`` / ``0.7.x`` / ``0.8.x`` shapes — they all carry
``ticker`` + ``composite_score`` as top-level keys. Rows missing those
two keys are skipped with a warning.

Subprocess safety: every ``git show`` runs through subprocess argv
(no shell=True) to prevent shell-injection on the SHA + path inputs.
"""

from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date as _date
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_RANKINGS_PATH: str = "frontend/public/data/rankings.json"
DEFAULT_COLUMNS: tuple[str, ...] = ("composite_score",)


@dataclass(frozen=True)
class RankingSnapshot:
    """A single historical rankings.json snapshot."""

    commit_sha: str
    commit_date: _date
    n_rows: int
    has_composite_score: bool
    note: str = ""


def _run_git(args: list[str], *, repo: Path | None = None) -> str:
    """Run a git command and return stdout.

    Raises subprocess.CalledProcessError on non-zero exit. Caller is
    responsible for argument hygiene — pass list args, never shell=True.
    """
    cwd = str(repo) if repo else None
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def list_ranking_commits(
    start_date: _date | None = None,
    end_date: _date | None = None,
    path: str = DEFAULT_RANKINGS_PATH,
    *,
    repo: Path | None = None,
) -> list[tuple[str, _date]]:
    """Enumerate (commit_sha, commit_date) tuples that touched ``path``.

    Sorted oldest → newest. When multiple commits share a date, all are
    returned — caller can dedupe via ``dedupe_by_date()`` if only the
    latest per-day is wanted.

    Args:
        start_date: filter commits with date >= this (inclusive). None = no lower bound.
        end_date: filter commits with date <= this (inclusive). None = no upper bound.
        path: repo-relative path to the file (default rankings.json).
        repo: optional repo root override (defaults to cwd).

    Returns:
        list of (commit_sha, commit_date) tuples sorted ascending by date.
    """
    args = [
        "log",
        "--format=%H %ad",
        "--date=short",
        "--",
        path,
    ]
    raw = _run_git(args, repo=repo)
    out: list[tuple[str, _date]] = []
    for line in raw.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split(" ", 1)
        if len(parts) != 2:
            continue
        sha, date_str = parts
        try:
            commit_date = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
        except ValueError:
            logger.warning("Skipping commit with malformed date: %r", line)
            continue
        if start_date is not None and commit_date < start_date:
            continue
        if end_date is not None and commit_date > end_date:
            continue
        out.append((sha, commit_date))
    # git log returns newest-first; flip to ascending
    out.reverse()
    return out


def dedupe_by_date(
    commits: Iterable[tuple[str, _date]],
    *,
    prefer: str = "latest",
) -> list[tuple[str, _date]]:
    """Return one (sha, date) per unique date.

    ``prefer="latest"`` keeps the LAST commit per day (assumes input is
    sorted ascending, so the last is the most recent). ``prefer="earliest"``
    keeps the first.
    """
    if prefer not in {"latest", "earliest"}:
        raise ValueError(f"prefer must be 'latest' or 'earliest', got {prefer!r}")
    by_date: dict[_date, str] = {}
    for sha, d in commits:
        if d not in by_date or prefer == "latest":
            by_date[d] = sha
    return sorted(((sha, d) for d, sha in by_date.items()), key=lambda kv: kv[1])


def load_snapshot_at(
    commit_sha: str,
    path: str = DEFAULT_RANKINGS_PATH,
    *,
    repo: Path | None = None,
) -> list[dict]:
    """Return the parsed rankings.json content at ``commit_sha``.

    Returns an empty list when the file doesn't exist at that commit
    (handles the very-early history before rankings.json was committed).

    Raises:
        json.JSONDecodeError: on malformed JSON (rare; would indicate
            a corrupt commit).
    """
    try:
        raw = _run_git(["show", f"{commit_sha}:{path}"], repo=repo)
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "git show %s:%s failed (rc=%d) — treating as missing file. "
            "stderr: %s",
            commit_sha[:8],
            path,
            exc.returncode,
            (exc.stderr or "").strip()[:200],
        )
        return []
    if not raw.strip():
        return []
    return json.loads(raw)


def load_ranking_history(
    start_date: _date | None = None,
    end_date: _date | None = None,
    columns: tuple[str, ...] = DEFAULT_COLUMNS,
    *,
    path: str = DEFAULT_RANKINGS_PATH,
    repo: Path | None = None,
    dedupe_dates: bool = True,
) -> pd.DataFrame:
    """Load a (date × ticker) DataFrame of historical rankings columns.

    Args:
        start_date / end_date: ISO-date filter window (inclusive).
        columns: rankings.json top-level keys to extract per row. Default
            ``("composite_score",)``. Common alternatives:
            ``("composite_score", "composite_score_adjusted")`` for
            penalty-aware analysis.
        path: repo-relative path; defaults to ``frontend/public/data/rankings.json``.
        repo: optional repo root.
        dedupe_dates: when True (default), one snapshot per unique date
            (the latest commit of that day).

    Returns:
        DataFrame indexed by ``(date, ticker)`` MultiIndex with one
        column per ``columns`` entry. Rows missing ``ticker`` or any
        requested column emit a debug log and are skipped.
    """
    commits = list_ranking_commits(start_date, end_date, path, repo=repo)
    if dedupe_dates:
        commits = dedupe_by_date(commits, prefer="latest")

    rows: list[dict] = []
    for sha, commit_date in commits:
        try:
            snapshot = load_snapshot_at(sha, path, repo=repo)
        except json.JSONDecodeError as exc:
            logger.warning(
                "Skipping commit %s — malformed JSON (%s)", sha[:8], exc
            )
            continue
        for entry in snapshot:
            ticker = entry.get("ticker")
            if not ticker:
                continue
            row: dict = {"date": commit_date, "ticker": ticker}
            missing_any = False
            for col in columns:
                if col in entry:
                    row[col] = entry[col]
                else:
                    missing_any = True
                    break
            if missing_any:
                logger.debug(
                    "Skipping ticker %s @ %s (commit %s): missing column",
                    ticker, commit_date, sha[:8],
                )
                continue
            rows.append(row)

    if not rows:
        return pd.DataFrame(columns=["date", "ticker", *columns]).set_index(
            ["date", "ticker"]
        )
    df = pd.DataFrame(rows).set_index(["date", "ticker"]).sort_index()
    return df


__all__ = [
    "DEFAULT_COLUMNS",
    "DEFAULT_RANKINGS_PATH",
    "RankingSnapshot",
    "dedupe_by_date",
    "list_ranking_commits",
    "load_ranking_history",
    "load_snapshot_at",
]
