"""Per-pillar Information Coefficient at historical dates — Phase 4.6 task #2c.

Pairs PR #278's :func:`load_ranking_history` (ranking at T) with PR
#280's :func:`compute_forward_return` (realized return at T + horizon)
to compute the per-pillar IC time series — the headline number for the
honest re-validation harness.

The Information Coefficient (IC) is the cross-sectional Spearman
rank-correlation between a predictor's score at T and the realized
forward return measured at T → T+horizon. An IC of 0 means "no
predictive power"; |IC| > ~0.05 is the rough alpha threshold per
Grinold-Kahn (2000) "Active Portfolio Management" Ch.4.

The honest re-validation question this answers: **does QuantRank's
pillar set still predict next-period returns, AFTER reversing
survivorship bias AND looking at the same as-of-dates the rankings
were produced for?**

Per the autonomous mission ceiling: IC computed here is a *naive*
IC — it does NOT subtract transaction costs, slippage, sector
neutralization, or capacity discount. Real net-of-cost IC is
typically 30-50% smaller per McLean-Pontiff (2016) JF post-publication
decay. Downstream PRs (#2f honest-baseline) net this through frictions.

API:
    >>> from datetime import date
    >>> from compute.validation.historical_ic import (
    ...     compute_historical_ic_report,
    ... )
    >>> report = compute_historical_ic_report(
    ...     start_date=date(2024, 1, 1),
    ...     end_date=date(2024, 6, 30),
    ...     horizon_months=6,
    ...     pillars=("value", "quality", "growth"),
    ... )
    >>> report.summary_by_pillar
    {'value': PillarICSummary(mean=0.024, std=0.018, n_dates=22, ...),
     'quality': PillarICSummary(mean=0.041, std=0.022, n_dates=22, ...),
     ...}

Honest-baseline disclaimer per Research Report v1.0:
    - Returns are NAIVE (no costs / slippage / sector neutralization)
    - The historical universe MUST come from PR #274's `members_at()`
      to avoid survivorship bias — passing the current universe
      inflates IC by 0.5-2 pts per Hou-Xue-Zhang 2020 RFS
    - IC is reported as a TIME SERIES + summary; not as a single
      headline number, because a 1-quarter shock can mask a real
      decay trend
    - Decay > 32% vs the published-period baseline is the
      McLean-Pontiff 2016 expected post-publication mean — wider
      = signal-quality concern, narrower = signal still live
"""

from __future__ import annotations

import json
import logging
import math
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path

import pandas as pd

from compute.validation.forward_returns import compute_forward_returns_batch
from compute.validation.ranking_history import (
    DEFAULT_RANKINGS_PATH,
    dedupe_by_date,
    list_ranking_commits,
)

logger = logging.getLogger(__name__)

# Per-pillar IC: minimum cross-section size required for a stable
# Spearman correlation. Below this, the date's IC is dropped from the
# report (too few tickers → noise dominates). Standard rule of thumb
# from Grinold-Kahn (2000) §4.2 — at least 30 names for a meaningful
# rank-correlation.
MIN_TICKERS_PER_DATE: int = 30

# Canonical pillar list (mirrors :class:`compute.output.schemas.PillarScores`).
# This is the default set walked by :func:`compute_historical_ic_report`
# when the caller doesn't specify ``pillars=...``.
DEFAULT_PILLARS: tuple[str, ...] = (
    "quality",
    "value",
    "growth",
    "momentum",
    "health",
    "profitability",
    "technical",
    "risk",
    "sentiment",
    "ml",
)


@dataclass(frozen=True)
class PillarICEntry:
    """Per-date IC for one pillar."""

    date: _date
    pillar: str
    ic: float
    n_tickers: int  # cross-section size used for the correlation
    note: str = ""


@dataclass(frozen=True)
class PillarICSummary:
    """Aggregate IC stats for one pillar across the windowed dates."""

    pillar: str
    n_dates: int
    mean: float | None
    std: float | None
    median: float | None
    min_value: float | None
    max_value: float | None
    # IC Information Ratio = mean / std × sqrt(n_dates). Risk-adjusted
    # signal strength per Grinold-Kahn (2000) §4.4. > 0.5 considered
    # decent.
    ic_ir: float | None
    # Hit-rate: fraction of dates with strictly positive IC. > 50% +
    # significant ICIR is the honest joint criterion.
    hit_rate: float | None


@dataclass(frozen=True)
class HistoricalICReport:
    """Top-level report for one (start, end, horizon) window."""

    start_date: _date
    end_date: _date
    horizon_months: int
    n_dates_walked: int
    n_dates_with_ic: int
    entries: list[PillarICEntry]
    summary_by_pillar: dict[str, PillarICSummary]
    note: str = ""


def _run_git(args: list[str], *, repo: Path | None = None) -> str:
    """Subprocess git; mirrors :mod:`compute.validation.ranking_history`."""
    cwd = str(repo) if repo else None
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _load_pillar_snapshot_at(
    commit_sha: str,
    pillar: str,
    *,
    path: str = DEFAULT_RANKINGS_PATH,
    repo: Path | None = None,
) -> dict[str, float]:
    """Return ``{ticker → pillar_score}`` for ``pillar`` at ``commit_sha``.

    Skips tickers where ``pillar_scores`` is missing or the requested
    pillar isn't present (legacy snapshots before phase 3 didn't have
    ``technical`` / ``profitability``).
    """
    try:
        raw = _run_git(["show", f"{commit_sha}:{path}"], repo=repo)
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "git show %s:%s failed (rc=%d) — treating as missing.",
            commit_sha[:8],
            path,
            exc.returncode,
        )
        return {}
    if not raw.strip():
        return {}
    try:
        snapshot = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Malformed JSON at %s: %s", commit_sha[:8], exc)
        return {}

    out: dict[str, float] = {}
    for entry in snapshot:
        ticker = entry.get("ticker")
        if not ticker:
            continue
        pillars = entry.get("pillar_scores")
        if not pillars:
            continue
        value = pillars.get(pillar)
        if value is None:
            continue
        try:
            out[ticker] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def compute_pillar_ic(
    pillar_scores: dict[str, float],
    forward_returns: dict[str, float | None],
    *,
    method: str = "spearman",
    min_tickers: int = MIN_TICKERS_PER_DATE,
) -> tuple[float | None, int, str]:
    """Compute cross-sectional IC for one (pillar_scores, forward_returns) pair.

    Args:
        pillar_scores: ``{ticker → pillar_score}`` at as-of T.
        forward_returns: ``{ticker → forward_return | None}`` at T → T+horizon.
            None values are silently dropped (treated as missing data).
        method: ``"spearman"`` (rank correlation, robust to outliers; default)
            or ``"pearson"`` (linear correlation; sensitive to outliers).
        min_tickers: minimum cross-section size; below this, returns
            ``(None, n_used, "too few tickers")``.

    Returns:
        ``(ic_value, n_tickers_used, note)`` — ``ic_value`` is None if
        below ``min_tickers`` OR if std is zero (constant inputs;
        correlation undefined). ``note`` describes the failure.

    Implementation note: uses pandas' ``Series.corr(method=...)`` so we
    don't add a scipy dependency. Pure-function — no side effects.
    """
    if method not in {"spearman", "pearson"}:
        raise ValueError(f"method must be 'spearman' or 'pearson', got {method!r}")

    common: list[tuple[str, float, float]] = []
    for ticker, score in pillar_scores.items():
        ret = forward_returns.get(ticker)
        if ret is None:
            continue
        if score is None:
            continue
        if not math.isfinite(score) or not math.isfinite(ret):
            continue
        common.append((ticker, float(score), float(ret)))

    n_used = len(common)
    if n_used < min_tickers:
        return None, n_used, f"too few tickers ({n_used} < {min_tickers})"

    score_series = pd.Series([row[1] for row in common])
    return_series = pd.Series([row[2] for row in common])

    # Constant-input guard: both Spearman and Pearson are undefined when
    # either series has zero variance. pandas returns NaN in that case;
    # we surface a clearer note instead.
    if score_series.std(ddof=0) == 0 or return_series.std(ddof=0) == 0:
        return None, n_used, "constant inputs (zero variance)"

    if method == "spearman":
        # Compute Spearman as Pearson on ranks — avoids the scipy dep
        # that ``pandas.Series.corr(method='spearman')`` pulls in
        # transitively. Equivalent by definition (Spearman ρ = Pearson r
        # of the rank-transformed series; cf. Spearman 1904 + Conover
        # 1999 "Practical Nonparametric Statistics" §5.4).
        score_ranks = score_series.rank()
        return_ranks = return_series.rank()
        if score_ranks.std(ddof=0) == 0 or return_ranks.std(ddof=0) == 0:
            return None, n_used, "constant inputs (zero variance after rank)"
        ic = score_ranks.corr(return_ranks, method="pearson")
    else:
        ic = score_series.corr(return_series, method="pearson")

    if pd.isna(ic):
        return None, n_used, "correlation undefined (NaN)"
    return float(ic), n_used, ""


def _summarize_pillar(entries: list[PillarICEntry]) -> PillarICSummary:
    """Build a PillarICSummary from a list of per-date entries.

    Caller must guarantee all entries share the same ``pillar`` field.
    """
    pillar = entries[0].pillar if entries else ""
    if not entries:
        return PillarICSummary(
            pillar=pillar,
            n_dates=0,
            mean=None,
            std=None,
            median=None,
            min_value=None,
            max_value=None,
            ic_ir=None,
            hit_rate=None,
        )

    values = [float(e.ic) for e in entries]
    series = pd.Series(values)
    mean = float(series.mean())
    std = float(series.std(ddof=0))
    median = float(series.median())
    min_v = float(series.min())
    max_v = float(series.max())
    hit_rate = float((series > 0).mean())
    if std > 0:
        ic_ir = mean / std * math.sqrt(len(values))
    else:
        ic_ir = None
    return PillarICSummary(
        pillar=pillar,
        n_dates=len(entries),
        mean=mean,
        std=std,
        median=median,
        min_value=min_v,
        max_value=max_v,
        ic_ir=ic_ir,
        hit_rate=hit_rate,
    )


def compute_historical_ic_report(
    start_date: _date,
    end_date: _date,
    *,
    horizon_months: int = 6,
    pillars: Iterable[str] = DEFAULT_PILLARS,
    method: str = "spearman",
    min_tickers: int = MIN_TICKERS_PER_DATE,
    path: str = DEFAULT_RANKINGS_PATH,
    repo: Path | None = None,
    cache_dir: Path | None = None,
) -> HistoricalICReport:
    """Walk git-archived rankings + forward-return cache → per-pillar IC report.

    For each unique date in [start_date, end_date]:
        1. Load that date's rankings.json snapshot → per-ticker pillar scores
        2. Compute the universe of tickers at that date
        3. For each pillar, look up forward returns at T → T+horizon
        4. Compute Spearman IC across the cross-section
        5. Aggregate into per-pillar summary stats

    Args:
        start_date / end_date: ISO-date inclusive window.
        horizon_months: forward-return horizon (default 6m, matches the
            Damodaran 2019 + standard alpha-discovery horizon).
        pillars: which pillar columns to compute IC for. Defaults to all
            10 in :class:`PillarScores`.
        method: ``"spearman"`` (default; robust) or ``"pearson"``.
        min_tickers: minimum cross-section per date (default 30).
        path: rankings.json path in the repo (default canonical).
        repo: optional git repo root override.
        cache_dir: optional override for the price cache (defaults to
            ``compute.config.PRICES_CACHE_DIR``).

    Returns:
        HistoricalICReport with per-date entries and per-pillar summary.
    """
    pillar_list = tuple(pillars)
    if not pillar_list:
        raise ValueError("pillars must be a non-empty iterable")
    if horizon_months <= 0:
        raise ValueError(f"horizon_months must be positive, got {horizon_months}")

    commits = list_ranking_commits(start_date, end_date, path, repo=repo)
    commits = dedupe_by_date(commits, prefer="latest")

    entries: list[PillarICEntry] = []
    dates_with_any_ic: set[_date] = set()
    for sha, commit_date in commits:
        # Load this date's universe once, then re-use the (ticker →
        # score) dict across each pillar by re-querying snapshot per
        # pillar (cheap — git show only fires once per date because
        # we cache via the loop variable).
        try:
            raw = _run_git(["show", f"{sha}:{path}"], repo=repo)
        except subprocess.CalledProcessError:
            logger.warning("git show %s failed; skipping date %s", sha[:8], commit_date)
            continue
        if not raw.strip():
            continue
        try:
            snapshot = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(
                "Malformed rankings.json at commit %s; skipping date %s",
                sha[:8],
                commit_date,
            )
            continue

        # Build the universe and forward returns ONCE per date (returns
        # don't depend on which pillar we're correlating against).
        tickers = [e.get("ticker") for e in snapshot if e.get("ticker")]
        if len(tickers) < min_tickers:
            logger.debug(
                "Snapshot %s has only %d tickers (< %d); skipping",
                commit_date, len(tickers), min_tickers,
            )
            continue
        fwd_returns = compute_forward_returns_batch(
            tickers, commit_date, horizon_months, cache_dir=cache_dir,
        )

        for pillar in pillar_list:
            scores: dict[str, float] = {}
            for entry in snapshot:
                t = entry.get("ticker")
                ps = entry.get("pillar_scores")
                if not t or not ps:
                    continue
                v = ps.get(pillar)
                if v is None:
                    continue
                try:
                    scores[t] = float(v)
                except (TypeError, ValueError):
                    continue

            ic, n_used, note = compute_pillar_ic(
                scores, fwd_returns, method=method, min_tickers=min_tickers,
            )
            if ic is None:
                logger.debug(
                    "IC undefined for pillar=%s date=%s: %s",
                    pillar, commit_date, note,
                )
                continue
            entries.append(
                PillarICEntry(
                    date=commit_date,
                    pillar=pillar,
                    ic=ic,
                    n_tickers=n_used,
                    note=note,
                )
            )
            dates_with_any_ic.add(commit_date)

    # Aggregate per-pillar
    by_pillar: dict[str, list[PillarICEntry]] = {p: [] for p in pillar_list}
    for entry in entries:
        by_pillar[entry.pillar].append(entry)
    summary = {
        p: _summarize_pillar(sorted(rows, key=lambda r: r.date))
        for p, rows in by_pillar.items()
    }

    return HistoricalICReport(
        start_date=start_date,
        end_date=end_date,
        horizon_months=horizon_months,
        n_dates_walked=len(commits),
        n_dates_with_ic=len(dates_with_any_ic),
        entries=entries,
        summary_by_pillar=summary,
        note=(
            f"walked {len(commits)} commits; "
            f"{len(dates_with_any_ic)} dates produced IC"
        ),
    )


def format_ic_report(report: HistoricalICReport) -> str:
    """Render a HistoricalICReport as a human-readable text block."""
    lines = [
        "Per-pillar Historical IC report",
        f"  window           : [{report.start_date}, {report.end_date}]",
        f"  horizon          : {report.horizon_months} months",
        f"  n_dates_walked   : {report.n_dates_walked}",
        f"  n_dates_with_ic  : {report.n_dates_with_ic}",
    ]
    if report.note:
        lines.append(f"  note             : {report.note}")
    lines.append("")
    lines.append("  Per-pillar summary (Spearman IC):")
    lines.append(
        "    {:<14} {:>4} {:>7} {:>7} {:>7} {:>7} {:>7} {:>7}".format(
            "pillar", "n", "mean", "median", "std", "min", "max", "IC IR",
        )
    )
    for pillar, summary in report.summary_by_pillar.items():
        if summary.n_dates == 0:
            lines.append(f"    {pillar:<14} {0:>4}   (no dates)")
            continue
        lines.append(
            f"    {pillar:<14} {summary.n_dates:>4} {summary.mean or 0.0:>7.4f} {summary.median or 0.0:>7.4f} {summary.std or 0.0:>7.4f} {summary.min_value or 0.0:>7.4f} {summary.max_value or 0.0:>7.4f} {summary.ic_ir or 0.0:>7.3f}"
        )
    lines.append("")
    lines.append(
        "  Honest-baseline disclaimer: IC reported here is NAIVE — "
        "no costs / slippage."
    )
    lines.append(
        "  Real net-of-cost IC is typically 30-50% smaller per "
        "McLean-Pontiff 2016 JF."
    )
    return "\n".join(lines)


__all__ = [
    "DEFAULT_PILLARS",
    "MIN_TICKERS_PER_DATE",
    "HistoricalICReport",
    "PillarICEntry",
    "PillarICSummary",
    "compute_historical_ic_report",
    "compute_pillar_ic",
    "format_ic_report",
]
