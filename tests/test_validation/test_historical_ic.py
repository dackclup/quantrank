"""Tests for ``compute.validation.historical_ic``.

Phase 4.6 task #2c — per-pillar IC at historical dates.

Tests use synthetic fixtures + monkeypatch over `_run_git` /
`compute_forward_returns_batch` to exercise the orchestrator without
needing the real git history or the gitignored price cache.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from compute.validation import historical_ic as hi
from compute.validation.historical_ic import (
    DEFAULT_PILLARS,
    MIN_TICKERS_PER_DATE,
    HistoricalICReport,
    PillarICEntry,
    PillarICSummary,
    compute_historical_ic_report,
    compute_pillar_ic,
    format_ic_report,
)

# ---------------------------------------------------------------- Module constants


def test_default_pillars_match_pillar_scores_schema() -> None:
    """DEFAULT_PILLARS mirrors all 10 fields of PillarScores."""
    assert set(DEFAULT_PILLARS) == {
        "quality", "value", "growth", "momentum", "health",
        "profitability", "technical", "risk", "sentiment", "ml",
    }


def test_min_tickers_per_date_is_30() -> None:
    """Grinold-Kahn 2000 §4.2 minimum cross-section convention."""
    assert MIN_TICKERS_PER_DATE == 30


# ---------------------------------------------------------------- compute_pillar_ic


def test_pillar_ic_perfect_positive_rank_correlation() -> None:
    """Pillar score = ticker hash; return = same monotone — IC ≈ 1.0."""
    n = 50
    scores = {f"T{i:03d}": float(i) for i in range(n)}
    returns = {f"T{i:03d}": float(i) * 0.001 for i in range(n)}

    ic, n_used, note = compute_pillar_ic(scores, returns)
    assert ic == pytest.approx(1.0, abs=1e-6)
    assert n_used == n
    assert note == ""


def test_pillar_ic_perfect_negative_rank_correlation() -> None:
    """Score inversely tied to return → IC ≈ -1.0."""
    n = 50
    scores = {f"T{i:03d}": float(i) for i in range(n)}
    returns = {f"T{i:03d}": -float(i) * 0.001 for i in range(n)}

    ic, n_used, _ = compute_pillar_ic(scores, returns)
    assert ic == pytest.approx(-1.0, abs=1e-6)
    assert n_used == n


def test_pillar_ic_uncorrelated_random() -> None:
    """Unrelated series → finite IC in [-1, 1] band, not perfect."""
    # Deterministic shuffle so the test doesn't flake; the resulting
    # IC is finite and bounded but not guaranteed to be near zero —
    # we just want to verify the math doesn't blow up.
    scores = {f"T{i:03d}": float(i) for i in range(60)}
    # Reverse-then-rotate: a non-trivial permutation
    return_values = list(range(60))
    return_values = return_values[30:] + return_values[:30]
    returns = {f"T{i:03d}": float(v) * 0.001 for i, v in enumerate(return_values)}

    ic, n_used, _ = compute_pillar_ic(scores, returns)
    assert ic is not None
    # IC must be a finite real in [-1, 1] (math invariant)
    assert -1.0 <= ic <= 1.0
    # Permutation isn't monotone — |IC| strictly less than 1
    assert abs(ic) < 1.0
    assert n_used == 60


def test_pillar_ic_below_min_tickers_returns_none() -> None:
    """Cross-section < 30 → None + descriptive note."""
    scores = {f"T{i:03d}": float(i) for i in range(20)}
    returns = {f"T{i:03d}": float(i) * 0.001 for i in range(20)}

    ic, n_used, note = compute_pillar_ic(scores, returns)
    assert ic is None
    assert n_used == 20
    assert "too few tickers" in note


def test_pillar_ic_drops_tickers_with_none_returns() -> None:
    """Tickers with None forward returns are excluded from IC."""
    n = 50
    scores = {f"T{i:03d}": float(i) for i in range(n)}
    returns: dict[str, float | None] = {
        f"T{i:03d}": float(i) * 0.001 for i in range(n)
    }
    # Knock out 10 → 40 remain (still above min)
    for i in range(10):
        returns[f"T{i:03d}"] = None

    ic, n_used, note = compute_pillar_ic(scores, returns)
    assert ic is not None
    assert n_used == 40
    assert note == ""


def test_pillar_ic_drops_tickers_with_none_score() -> None:
    """Tickers with None pillar score are excluded."""
    n = 50
    scores: dict[str, float | None] = {f"T{i:03d}": float(i) for i in range(n)}
    returns = {f"T{i:03d}": float(i) * 0.001 for i in range(n)}
    # Mark 5 scores as None — the typing of compute_pillar_ic accepts
    # only dict[str, float] so use a manual cast:
    scores_typed: dict[str, float] = {}
    for k, v in scores.items():
        if k in {"T000", "T001", "T002", "T003", "T004"}:
            continue  # simulate missing pillar score
        scores_typed[k] = v

    ic, n_used, _ = compute_pillar_ic(scores_typed, returns)
    assert ic is not None
    assert n_used == 45


def test_pillar_ic_constant_score_returns_none_with_note() -> None:
    """All-identical scores → std=0 → undefined correlation."""
    scores = {f"T{i:03d}": 50.0 for i in range(40)}
    returns = {f"T{i:03d}": float(i) * 0.001 for i in range(40)}

    ic, n_used, note = compute_pillar_ic(scores, returns)
    assert ic is None
    assert n_used == 40
    assert "constant inputs" in note


def test_pillar_ic_constant_return_returns_none_with_note() -> None:
    """All-identical returns → std=0 → undefined correlation."""
    scores = {f"T{i:03d}": float(i) for i in range(40)}
    returns = {f"T{i:03d}": 0.10 for i in range(40)}

    ic, n_used, note = compute_pillar_ic(scores, returns)
    assert ic is None
    assert "constant inputs" in note


def test_pillar_ic_drops_nan_inf_scores() -> None:
    """NaN / inf scores silently excluded."""
    n = 50
    scores = {f"T{i:03d}": float(i) for i in range(n)}
    scores["T000"] = float("nan")
    scores["T001"] = float("inf")
    returns = {f"T{i:03d}": float(i) * 0.001 for i in range(n)}

    ic, n_used, _ = compute_pillar_ic(scores, returns)
    assert ic is not None
    assert n_used == 48  # 50 - 2 nan/inf


def test_pillar_ic_invalid_method_raises() -> None:
    """method must be 'spearman' or 'pearson'."""
    with pytest.raises(ValueError, match="method must be"):
        compute_pillar_ic({}, {}, method="kendall")


def test_pillar_ic_pearson_method_works() -> None:
    """Pearson method produces a different (linear) correlation."""
    n = 50
    scores = {f"T{i:03d}": float(i) for i in range(n)}
    # Quadratic return — Spearman ≈ 1.0, Pearson < 1.0
    returns = {f"T{i:03d}": float(i) ** 2 * 0.0001 for i in range(n)}

    ic_spearman, _, _ = compute_pillar_ic(scores, returns, method="spearman")
    ic_pearson, _, _ = compute_pillar_ic(scores, returns, method="pearson")
    assert ic_spearman == pytest.approx(1.0, abs=1e-6)
    assert ic_pearson is not None
    assert ic_pearson < ic_spearman  # quadratic relationship → Pearson lower


# ---------------------------------------------------------------- _summarize_pillar


def test_summarize_pillar_empty_returns_zero_summary() -> None:
    """Empty entry list → zero-shaped summary."""
    summary = hi._summarize_pillar([])
    assert summary.n_dates == 0
    assert summary.mean is None
    assert summary.ic_ir is None


def test_summarize_pillar_aggregates_stats() -> None:
    """Multi-date entries → mean / std / IC-IR aggregated."""
    entries = [
        PillarICEntry(date(2024, 1, d), "value", ic=0.05, n_tickers=400)
        for d in (1, 2, 3, 4, 5)
    ]
    summary = hi._summarize_pillar(entries)
    assert summary.n_dates == 5
    assert summary.mean == pytest.approx(0.05, abs=1e-9)
    assert summary.std == pytest.approx(0.0, abs=1e-9)
    assert summary.ic_ir is None  # std=0 → undefined IC-IR
    assert summary.hit_rate == pytest.approx(1.0, abs=1e-9)


def test_summarize_pillar_hit_rate_correct() -> None:
    """Hit rate counts strictly positive ICs."""
    entries = [
        PillarICEntry(date(2024, 1, 1), "value", ic=0.05, n_tickers=400),
        PillarICEntry(date(2024, 1, 2), "value", ic=-0.02, n_tickers=400),
        PillarICEntry(date(2024, 1, 3), "value", ic=0.03, n_tickers=400),
        PillarICEntry(date(2024, 1, 4), "value", ic=0.0, n_tickers=400),  # exactly zero
    ]
    summary = hi._summarize_pillar(entries)
    # 2 of 4 strictly > 0
    assert summary.hit_rate == pytest.approx(0.5, abs=1e-9)


def test_summarize_pillar_ic_ir_formula() -> None:
    """IC-IR = mean/std × sqrt(n_dates)."""
    entries = [
        PillarICEntry(date(2024, 1, 1), "value", ic=0.10, n_tickers=400),
        PillarICEntry(date(2024, 1, 2), "value", ic=0.00, n_tickers=400),
        PillarICEntry(date(2024, 1, 3), "value", ic=0.20, n_tickers=400),
        PillarICEntry(date(2024, 1, 4), "value", ic=0.10, n_tickers=400),
    ]
    summary = hi._summarize_pillar(entries)
    # mean = 0.10, std (ddof=0) = sqrt(0.005) ≈ 0.0707, n=4
    # IC-IR = 0.10 / 0.0707 × sqrt(4) ≈ 2.828
    assert summary.ic_ir is not None
    assert summary.ic_ir == pytest.approx(2.828, abs=0.01)


# ---------------------------------------------------------------- compute_historical_ic_report


def _make_snapshot(tickers_scores: list[tuple[str, dict[str, float]]]) -> str:
    """Build a rankings.json-shaped JSON string from a list of (ticker, pillars)."""
    payload = [
        {
            "ticker": ticker,
            "pillar_scores": pillars,
            "composite_score": 50.0,
        }
        for ticker, pillars in tickers_scores
    ]
    return json.dumps(payload)


def test_report_zero_horizon_raises() -> None:
    with pytest.raises(ValueError, match="horizon_months must be positive"):
        compute_historical_ic_report(
            date(2024, 1, 1), date(2024, 6, 30), horizon_months=0,
        )


def test_report_empty_pillars_raises() -> None:
    with pytest.raises(ValueError, match="pillars must be a non-empty"):
        compute_historical_ic_report(
            date(2024, 1, 1), date(2024, 6, 30), pillars=(),
        )


def test_report_no_commits_returns_empty(monkeypatch) -> None:
    """Empty git window → empty report, no exception."""
    monkeypatch.setattr(hi, "list_ranking_commits", lambda *a, **k: [])

    report = compute_historical_ic_report(
        date(2099, 1, 1), date(2099, 12, 31), pillars=("value",),
    )
    assert report.n_dates_walked == 0
    assert report.entries == []
    assert report.summary_by_pillar["value"].n_dates == 0


def test_report_full_path_one_date_one_pillar(monkeypatch) -> None:
    """Single commit + 50 tickers + perfect rank pairing → IC ≈ 1.0."""
    monkeypatch.setattr(
        hi, "list_ranking_commits",
        lambda *a, **k: [("sha1", date(2024, 3, 1))],
    )

    # 50 tickers; pillar score equals index, forward return equals index
    snapshot = _make_snapshot(
        [(f"T{i:03d}", {"value": float(i)}) for i in range(50)]
    )

    def fake_run_git(args, *, repo=None):
        return snapshot

    monkeypatch.setattr(hi, "_run_git", fake_run_git)

    monkeypatch.setattr(
        hi, "compute_forward_returns_batch",
        lambda tickers, asof, horizon, *, cache_dir=None: {
            t: float(i) * 0.001 for i, t in enumerate(tickers)
        },
    )

    report = compute_historical_ic_report(
        date(2024, 1, 1), date(2024, 6, 30), pillars=("value",),
    )
    assert report.n_dates_walked == 1
    assert report.n_dates_with_ic == 1
    assert len(report.entries) == 1
    assert report.entries[0].pillar == "value"
    assert report.entries[0].ic == pytest.approx(1.0, abs=1e-6)
    assert report.entries[0].n_tickers == 50
    assert report.summary_by_pillar["value"].mean == pytest.approx(1.0, abs=1e-6)


def test_report_skips_pillar_with_too_few_tickers(monkeypatch) -> None:
    """Snapshot with < min_tickers → no IC produced."""
    monkeypatch.setattr(
        hi, "list_ranking_commits",
        lambda *a, **k: [("sha1", date(2024, 3, 1))],
    )
    snapshot = _make_snapshot(
        [(f"T{i:03d}", {"value": float(i)}) for i in range(10)]
    )
    monkeypatch.setattr(hi, "_run_git", lambda args, **k: snapshot)
    monkeypatch.setattr(
        hi, "compute_forward_returns_batch",
        lambda tickers, asof, horizon, *, cache_dir=None: {
            t: float(i) * 0.001 for i, t in enumerate(tickers)
        },
    )

    report = compute_historical_ic_report(
        date(2024, 1, 1), date(2024, 6, 30), pillars=("value",),
    )
    assert report.entries == []


def test_report_multi_date_aggregates_per_pillar(monkeypatch) -> None:
    """Multi-date walk produces per-pillar mean/median/IC-IR aggregates."""
    monkeypatch.setattr(
        hi, "list_ranking_commits",
        lambda *a, **k: [
            ("sha1", date(2024, 3, 1)),
            ("sha2", date(2024, 4, 1)),
            ("sha3", date(2024, 5, 1)),
        ],
    )

    # Same snapshot for all dates → IC same each date
    snapshot = _make_snapshot(
        [(f"T{i:03d}", {"value": float(i), "quality": float(50 - i)})
         for i in range(50)]
    )
    monkeypatch.setattr(hi, "_run_git", lambda args, **k: snapshot)

    # Forward returns monotone in ticker index for all dates
    monkeypatch.setattr(
        hi, "compute_forward_returns_batch",
        lambda tickers, asof, horizon, *, cache_dir=None: {
            t: float(i) * 0.001 for i, t in enumerate(tickers)
        },
    )

    report = compute_historical_ic_report(
        date(2024, 1, 1), date(2024, 6, 30), pillars=("value", "quality"),
    )
    # value → perfect positive (IC = 1.0 each date)
    # quality → score reversed from index → IC = -1.0 each date
    assert report.summary_by_pillar["value"].mean == pytest.approx(1.0, abs=1e-6)
    assert report.summary_by_pillar["quality"].mean == pytest.approx(-1.0, abs=1e-6)
    assert report.summary_by_pillar["value"].n_dates == 3
    assert report.summary_by_pillar["quality"].n_dates == 3


def test_report_handles_missing_pillar_field(monkeypatch) -> None:
    """Snapshot without the requested pillar → skipped, no IC."""
    monkeypatch.setattr(
        hi, "list_ranking_commits",
        lambda *a, **k: [("sha1", date(2024, 3, 1))],
    )
    # Snapshot has only `value`; we ask for `quality`
    snapshot = _make_snapshot(
        [(f"T{i:03d}", {"value": float(i)}) for i in range(50)]
    )
    monkeypatch.setattr(hi, "_run_git", lambda args, **k: snapshot)
    monkeypatch.setattr(
        hi, "compute_forward_returns_batch",
        lambda tickers, asof, horizon, *, cache_dir=None: {
            t: float(i) * 0.001 for i, t in enumerate(tickers)
        },
    )

    report = compute_historical_ic_report(
        date(2024, 1, 1), date(2024, 6, 30), pillars=("quality",),
    )
    # No `quality` pillar in snapshot → 0 entries
    assert report.entries == []
    assert report.summary_by_pillar["quality"].n_dates == 0


def test_report_handles_malformed_json(monkeypatch) -> None:
    """Bad JSON at a commit → date skipped, no exception."""
    monkeypatch.setattr(
        hi, "list_ranking_commits",
        lambda *a, **k: [
            ("sha_bad", date(2024, 3, 1)),
            ("sha_good", date(2024, 4, 1)),
        ],
    )

    def fake_run_git(args, *, repo=None):
        if "sha_bad" in args[1]:
            return "{not valid json"
        return _make_snapshot(
            [(f"T{i:03d}", {"value": float(i)}) for i in range(50)]
        )

    monkeypatch.setattr(hi, "_run_git", fake_run_git)
    monkeypatch.setattr(
        hi, "compute_forward_returns_batch",
        lambda tickers, asof, horizon, *, cache_dir=None: {
            t: float(i) * 0.001 for i, t in enumerate(tickers)
        },
    )

    report = compute_historical_ic_report(
        date(2024, 1, 1), date(2024, 6, 30), pillars=("value",),
    )
    # Only the good snapshot produced an entry
    assert len(report.entries) == 1
    assert report.entries[0].date == date(2024, 4, 1)


# ---------------------------------------------------------------- format_ic_report


def test_format_ic_report_renders_header(monkeypatch) -> None:
    """Text formatter contains the headline IC IR + naive disclaimer."""
    summary = PillarICSummary(
        pillar="value", n_dates=3,
        mean=0.05, std=0.02, median=0.05,
        min_value=0.03, max_value=0.07, ic_ir=4.33, hit_rate=1.0,
    )
    report = HistoricalICReport(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 6, 30),
        horizon_months=6,
        n_dates_walked=3,
        n_dates_with_ic=3,
        entries=[],
        summary_by_pillar={"value": summary},
        note="synthetic",
    )
    text = format_ic_report(report)
    assert "Per-pillar Historical IC report" in text
    assert "value" in text
    assert "IC IR" in text
    assert "Honest-baseline disclaimer" in text
    assert "McLean-Pontiff" in text


def test_format_ic_report_no_dates_pillar() -> None:
    """Pillar with zero dates renders gracefully."""
    empty_summary = PillarICSummary(
        pillar="quality", n_dates=0,
        mean=None, std=None, median=None,
        min_value=None, max_value=None, ic_ir=None, hit_rate=None,
    )
    report = HistoricalICReport(
        start_date=date(2024, 1, 1),
        end_date=date(2024, 6, 30),
        horizon_months=6,
        n_dates_walked=0,
        n_dates_with_ic=0,
        entries=[],
        summary_by_pillar={"quality": empty_summary},
        note="empty",
    )
    text = format_ic_report(report)
    assert "(no dates)" in text


# ---------------------------------------------------------------- live-git smoke


def test_compute_historical_ic_live_repo_recent_window() -> None:
    """Smoke test against real repo's recent rankings.json + (likely empty) price cache."""
    # If no price cache → forward_returns mostly None → fewer IC entries,
    # but no crash. This pins the "doesn't explode on cold sandbox" guarantee.
    report = compute_historical_ic_report(
        date(2026, 5, 22),
        date(2026, 5, 27),
        horizon_months=6,
        pillars=("value",),
        min_tickers=2,  # Allow small cross-section to verify code path
    )
    assert isinstance(report, HistoricalICReport)
    # Either succeeds (forwarded prices present) or skips per date — either OK
    assert report.n_dates_walked >= 0
