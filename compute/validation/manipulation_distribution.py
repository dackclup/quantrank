"""Manipulation-index distribution shift report — Phase 4.6 task #2e.

Consumer of ``compute.validation.ranking_history.load_ranking_history()``.
Walks git-archived rankings.json snapshots, extracts the per-ticker
``manipulation_index`` time series, and reports the distribution shift
across the cron window: mean / std / quantiles + fire-rate by band
(LOW [0, 20), MODERATE [20, 50), HIGH [50, ∞)) per date.

Produces the JSON + text artifact that closes ``docs/research/historical-
revalidation-harness.md`` future-work item #2e — the manipulation_index
distribution shift answers the honest question: **has the cohort of
flagged stocks materially changed across the cron's lifetime?** A
distribution drift > ~5 pts on the universe-mean would signal Phase 4.5e
weight recalibration is needed (per Q3 2026-08-19 cohort-audit gate).

This module does NOT replay or recompute manipulation_index — it reads
the values the cron already wrote to rankings.json. Phase 4.6 task #2c
will add the orthogonal "honest historical IC" step that DOES recompute
pillars against historical universes via PR #275's universe_provider.

API:
    >>> from datetime import date
    >>> from compute.validation.manipulation_distribution import (
    ...     compute_manipulation_distribution_shift,
    ... )
    >>> report = compute_manipulation_distribution_shift(
    ...     start_date=date(2026, 5, 1),
    ...     end_date=date(2026, 5, 27),
    ... )
    >>> report.per_date_summary
    {date(2026, 5, 14): DistributionSummary(mean=12.4, std=18.1, ...), ...}
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from datetime import date as _date

import pandas as pd

from compute.validation.ranking_history import load_ranking_history

logger = logging.getLogger(__name__)

# Band boundaries match ``compute/scoring/manipulation_index.py`` + the
# ``ManipulationRiskCard`` UI 3-band chip.
LOW_UPPER: float = 20.0
MODERATE_UPPER: float = 50.0


@dataclass(frozen=True)
class DistributionSummary:
    """Per-date manipulation_index distribution snapshot."""

    n_tickers: int
    n_non_null: int
    mean: float
    std: float
    median: float
    q25: float
    q75: float
    q95: float
    max_value: float
    # Fire-rate band counts (LOW + MODERATE + HIGH cover non-null universe)
    low_count: int     # mi ∈ [0, 20)
    moderate_count: int  # mi ∈ [20, 50)
    high_count: int    # mi ∈ [50, ∞)
    # Top-3 ticker:value pairs by manipulation_index this date
    top_3_tickers: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class ShiftReport:
    """Aggregate report across the windowed date range."""

    start_date: _date
    end_date: _date
    n_dates: int
    n_unique_tickers: int
    per_date_summary: dict[_date, DistributionSummary]
    # Time-window deltas: start-of-window vs end-of-window
    mean_delta: float | None       # last_date.mean − first_date.mean
    std_delta: float | None
    high_count_delta: int | None
    high_count_first: int | None
    high_count_last: int | None
    note: str = ""


def _summarize_one_date(
    date_index: _date, values: pd.Series
) -> DistributionSummary:
    """Build a DistributionSummary from one date's manipulation_index slice."""
    non_null = values.dropna()
    n_total = len(values)
    n_non_null = len(non_null)

    if n_non_null == 0:
        return DistributionSummary(
            n_tickers=n_total,
            n_non_null=0,
            mean=0.0,
            std=0.0,
            median=0.0,
            q25=0.0,
            q75=0.0,
            q95=0.0,
            max_value=0.0,
            low_count=0,
            moderate_count=0,
            high_count=0,
            top_3_tickers=(),
        )

    arr = non_null.to_numpy(dtype=float)
    mean = float(arr.mean())
    std = float(arr.std(ddof=0))
    median = float(statistics.median(arr.tolist()))
    q25, q75, q95 = (
        float(pd.Series(arr).quantile(q)) for q in (0.25, 0.75, 0.95)
    )

    low = int((arr < LOW_UPPER).sum())
    moderate = int(((arr >= LOW_UPPER) & (arr < MODERATE_UPPER)).sum())
    high = int((arr >= MODERATE_UPPER).sum())

    # top-3 by value, descending
    top = non_null.sort_values(ascending=False).head(3)
    top_3 = tuple((str(idx), float(val)) for idx, val in top.items())

    return DistributionSummary(
        n_tickers=n_total,
        n_non_null=n_non_null,
        mean=mean,
        std=std,
        median=median,
        q25=q25,
        q75=q75,
        q95=q95,
        max_value=float(arr.max()),
        low_count=low,
        moderate_count=moderate,
        high_count=high,
        top_3_tickers=top_3,
    )


def compute_manipulation_distribution_shift(
    start_date: _date | None = None,
    end_date: _date | None = None,
    *,
    repo: str | None = None,
) -> ShiftReport:
    """Walk git-archived rankings.json and return a per-date + delta report.

    Args:
        start_date: ISO-date inclusive lower bound (None = unlimited).
        end_date: ISO-date inclusive upper bound (None = unlimited).
        repo: optional repo root override (passed through to ranking_history).

    Returns:
        ShiftReport with one DistributionSummary per unique date in the
        window + first-to-last deltas. Empty per_date_summary if no
        commits in the window OR no non-null manipulation_index found.
    """
    df = load_ranking_history(
        start_date=start_date,
        end_date=end_date,
        columns=("manipulation_index",),
        repo=__import__("pathlib").Path(repo) if repo else None,
    )

    if df.empty:
        logger.warning(
            "No rankings.json commits in window [%s, %s]", start_date, end_date,
        )
        return ShiftReport(
            start_date=start_date or _date.min,
            end_date=end_date or _date.max,
            n_dates=0,
            n_unique_tickers=0,
            per_date_summary={},
            mean_delta=None,
            std_delta=None,
            high_count_delta=None,
            high_count_first=None,
            high_count_last=None,
            note="empty window",
        )

    # Drop any rows where manipulation_index is None — schema-compat for
    # pre-0.8.0 snapshots where the field didn't exist yet.
    df = df.dropna(subset=["manipulation_index"])
    if df.empty:
        logger.warning(
            "No non-null manipulation_index values in window [%s, %s] — "
            "likely pre-0.8.0-phase4.5f snapshots only.",
            start_date, end_date,
        )
        return ShiftReport(
            start_date=start_date or _date.min,
            end_date=end_date or _date.max,
            n_dates=0,
            n_unique_tickers=0,
            per_date_summary={},
            mean_delta=None,
            std_delta=None,
            high_count_delta=None,
            high_count_first=None,
            high_count_last=None,
            note="all manipulation_index values null (pre-phase4.5f)",
        )

    per_date: dict[_date, DistributionSummary] = {}
    for date_idx in df.index.get_level_values("date").unique():
        # Slice: this date's series of (ticker → manipulation_index)
        slice_df = df.xs(date_idx, level="date")
        values = slice_df["manipulation_index"]
        per_date[date_idx] = _summarize_one_date(date_idx, values)

    # Sorted-by-date dict
    per_date_sorted = dict(sorted(per_date.items(), key=lambda kv: kv[0]))

    if len(per_date_sorted) < 2:
        return ShiftReport(
            start_date=start_date or _date.min,
            end_date=end_date or _date.max,
            n_dates=len(per_date_sorted),
            n_unique_tickers=len(df.index.get_level_values("ticker").unique()),
            per_date_summary=per_date_sorted,
            mean_delta=None,
            std_delta=None,
            high_count_delta=None,
            high_count_first=None,
            high_count_last=None,
            note="single date in window — no delta computable",
        )

    first_date = next(iter(per_date_sorted))
    last_date = next(reversed(per_date_sorted))
    first = per_date_sorted[first_date]
    last = per_date_sorted[last_date]

    return ShiftReport(
        start_date=start_date or first_date,
        end_date=end_date or last_date,
        n_dates=len(per_date_sorted),
        n_unique_tickers=len(df.index.get_level_values("ticker").unique()),
        per_date_summary=per_date_sorted,
        mean_delta=last.mean - first.mean,
        std_delta=last.std - first.std,
        high_count_delta=last.high_count - first.high_count,
        high_count_first=first.high_count,
        high_count_last=last.high_count,
        note=f"first={first_date.isoformat()}, last={last_date.isoformat()}",
    )


def format_shift_report(report: ShiftReport, *, max_dates: int = 20) -> str:
    """Render a ShiftReport as a human-readable text block."""
    lines = [
        "Manipulation-index distribution shift report",
        f"  window           : [{report.start_date}, {report.end_date}]",
        f"  n_dates          : {report.n_dates}",
        f"  n_unique_tickers : {report.n_unique_tickers}",
    ]
    if report.note:
        lines.append(f"  note             : {report.note}")
    lines.append("")

    if report.mean_delta is not None:
        lines.append("  Window-end deltas (last_date − first_date):")
        lines.append(f"    Δmean       : {report.mean_delta:+.2f}")
        lines.append(f"    Δstd        : {report.std_delta:+.2f}")
        lines.append(
            f"    ΔHIGH count : {report.high_count_delta:+d} "
            f"({report.high_count_first} → {report.high_count_last})"
        )
        lines.append("")

    lines.append("  Per-date summary (chronological, capped):")
    items = list(report.per_date_summary.items())
    if len(items) > max_dates:
        head = items[: max_dates // 2]
        tail = items[-max_dates // 2 :]
        items = head + [None] + tail
    lines.append(
        "    {:<10} {:>4} {:>6} {:>6} {:>6} {:>6} {:>6}   top".format(
            "date", "n", "mean", "std", "p75", "p95", "HIGH",
        )
    )
    for entry in items:
        if entry is None:
            lines.append("    ... (truncated; pass --max-dates N to widen) ...")
            continue
        d, s = entry
        top_str = ", ".join(f"{t}={v:.1f}" for t, v in s.top_3_tickers[:3])
        lines.append(
            f"    {d.isoformat():<10} {s.n_non_null:>4} {s.mean:>6.2f} {s.std:>6.2f} {s.q75:>6.2f} {s.q95:>6.2f} {s.high_count:>6}   {top_str}"
        )
    return "\n".join(lines)


__all__ = [
    "LOW_UPPER",
    "MODERATE_UPPER",
    "DistributionSummary",
    "ShiftReport",
    "compute_manipulation_distribution_shift",
    "format_shift_report",
]
