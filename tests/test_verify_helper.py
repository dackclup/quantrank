"""Regression tests for `.claude/skills/verify-production-output/helper.py`.

Epic #150 Phase 1.4 + 1.5 (issue #155 trail). Covers:

- Section A schema reporter — happy + tier2_coverage_pct missing + low
  fundamentals coverage branches
- Section B Tier-2 fired-flag inventory — the 4-branch matrix from
  PR #149 (tier2_enabled × {within-band, over-band, has-fire-but-
  disabled, no-fire-and-disabled})
- Section J annotate-flag audit — empty + populated paths
- Section L OSAP factor-exposure proxy invariant (issue #218) —
  empty/skip + phase4h_proxy pass + blending_regression fail +
  graduated warn + schema_drift fail branches

The helper module lives outside any Python package, so it's loaded via
`importlib.util.spec_from_file_location` rather than a regular import.
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

_HELPER_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / ".claude" / "skills" / "verify-production-output" / "helper.py"
)


@pytest.fixture(scope="module")
def helper():
    spec = importlib.util.spec_from_file_location("verify_helper", _HELPER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _stock(ticker: str, **overrides) -> dict:
    base = {
        "ticker": ticker,
        "rank": 1,
        "composite_score": 75.0,
        "risk_flags": [],
        "valuation_warnings": [],
        "tier2_events": {
            "going_concern_disclosure": False,
            "non_reliance_filing": False,
            "auditor_change": False,
            "latest_8k_filing_date": None,
            "latest_8k_filing_url": None,
        },
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Section A — schema + metadata
# ---------------------------------------------------------------------------


def test_section_a_happy_path(helper, capsys):
    metadata = {
        "version": "0.9.2-phase4h.2",
        "git_commit": "aea27e1f00",
        "universe_size": 502,
        "tier2_coverage_pct": 99,
        "fundamentals_coverage_pct": 100,
        "fundamentals_latency_p50_seconds": 1.2,
        "fundamentals_latency_p95_seconds": 4.5,
    }
    w, f = helper.section_a_schema(metadata, baseline=None)
    assert (w, f) == (0, 0)


def test_section_a_missing_tier2_coverage_warns(helper, capsys):
    metadata = {
        "version": "0.9.2-phase4h.2",
        "git_commit": "aea27e1f00",
        "universe_size": 502,
        "fundamentals_coverage_pct": 100,
    }
    w, f = helper.section_a_schema(metadata, baseline=None)
    assert w == 1
    assert f == 0
    assert "tier2_coverage_pct" in capsys.readouterr().out


def test_section_a_low_fundamentals_coverage_fails(helper, capsys):
    metadata = {
        "version": "0.9.2-phase4h.2",
        "git_commit": "aea27e1f00",
        "universe_size": 502,
        "tier2_coverage_pct": 99,
        "fundamentals_coverage_pct": 60,
    }
    w, f = helper.section_a_schema(metadata, baseline=None)
    assert f == 1
    assert "heavily throttled" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Section B — Tier-2 fired-flag inventory (4-branch matrix from PR #149)
# ---------------------------------------------------------------------------


def _tier2_metadata(coverage_pct: float) -> dict:
    return {"tier2_coverage_pct": coverage_pct}


def test_section_b_enabled_within_band_passes(helper, capsys):
    stocks = [_stock(f"S{i}") for i in range(100)]
    stocks[0]["tier2_events"]["non_reliance_filing"] = True
    stocks[1]["tier2_events"]["auditor_change"] = True
    w, f = helper.section_b_tier2(stocks, _tier2_metadata(99))
    assert (w, f) == (0, 0)


def test_section_b_enabled_over_band_warns(helper, capsys):
    stocks = [_stock(f"S{i}") for i in range(100)]
    for s in stocks[:6]:
        s["tier2_events"]["non_reliance_filing"] = True
    w, f = helper.section_b_tier2(stocks, _tier2_metadata(99))
    assert w >= 1
    assert f == 0
    assert "over 2% expected band" in capsys.readouterr().out


def test_section_b_disabled_no_fires_passes(helper, capsys):
    stocks = [_stock(f"S{i}") for i in range(100)]
    w, f = helper.section_b_tier2(stocks, _tier2_metadata(0))
    assert (w, f) == (0, 0)
    assert "Tier-2 disabled — contract holds" in capsys.readouterr().out


def test_section_b_disabled_with_fires_fails(helper, capsys):
    stocks = [_stock(f"S{i}") for i in range(100)]
    stocks[0]["tier2_events"]["non_reliance_filing"] = True
    w, f = helper.section_b_tier2(stocks, _tier2_metadata(0))
    assert f >= 1
    assert "flag broken?" in capsys.readouterr().out


# Phase 1.6 (issue #155) — explicit `tier2_enabled` field in metadata
# overrides the coverage-based inference. Covers the two cases the
# legacy heuristic could not distinguish:
#   1. tier2_enabled=False but coverage non-zero (impossible normally,
#      but tests the precedence is on the flag, not coverage)
#   2. tier2_enabled=True but coverage near 0 (real failure mode where
#      8-K fetch returned nothing — should NOT be treated as disabled)


def test_section_b_explicit_flag_overrides_coverage_when_disabled(helper, capsys):
    stocks = [_stock(f"S{i}") for i in range(100)]
    stocks[0]["tier2_events"]["non_reliance_filing"] = True
    metadata = {"tier2_coverage_pct": 99, "tier2_enabled": False}
    w, f = helper.section_b_tier2(stocks, metadata)
    assert f >= 1
    out = capsys.readouterr().out
    assert "flag broken?" in out
    assert "tier2_enabled=False" in out


def test_section_b_explicit_flag_enabled_with_zero_coverage(helper, capsys):
    stocks = [_stock(f"S{i}") for i in range(100)]
    stocks[0]["tier2_events"]["non_reliance_filing"] = True
    metadata = {"tier2_coverage_pct": 0, "tier2_enabled": True}
    w, f = helper.section_b_tier2(stocks, metadata)
    assert (w, f) == (0, 0)
    out = capsys.readouterr().out
    assert "flag broken?" not in out
    assert "Tier-2 disabled" not in out


# ---------------------------------------------------------------------------
# Section J — annotate-flag inventory (new in Phase 1.5)
# ---------------------------------------------------------------------------


def test_section_j_empty_universe(helper, capsys):
    w, f = helper.section_j_annotate_audit([])
    assert (w, f) == (0, 0)
    out = capsys.readouterr().out
    assert "(none)" in out  # both valuation_warnings + tier2_events report empty
    assert out.count("(none)") == 2


def test_section_j_counts_and_sorts_descending(helper, capsys):
    stocks = [
        _stock("AAA", valuation_warnings=["value_trap_risk", "goodwill_heavy"]),
        _stock("BBB", valuation_warnings=["value_trap_risk"]),
        _stock("CCC", valuation_warnings=["value_trap_risk"]),
    ]
    stocks[0]["tier2_events"]["auditor_change"] = True
    stocks[1]["tier2_events"]["auditor_change"] = True
    stocks[2]["tier2_events"]["going_concern_disclosure"] = True

    w, f = helper.section_j_annotate_audit(stocks)
    assert (w, f) == (0, 0)
    out = capsys.readouterr().out

    # valuation_warnings: value_trap_risk (3) printed before goodwill_heavy (1)
    assert out.index("value_trap_risk") < out.index("goodwill_heavy")
    assert "value_trap_risk: 3 (100.0%)" in out
    assert "goodwill_heavy: 1 (33.3%)" in out

    # tier2_events: auditor_change (2) printed before going_concern_disclosure (1)
    assert out.index("auditor_change") < out.index("going_concern_disclosure")
    assert "auditor_change: 2 (66.7%)" in out
    assert "going_concern_disclosure: 1 (33.3%)" in out

    # Non-boolean tier2 fields are excluded (latest_8k_filing_date is None)
    assert "latest_8k_filing_date" not in out


# ---------------------------------------------------------------------------
# Section L — OSAP factor-exposure proxy invariant (issue #218)
# ---------------------------------------------------------------------------


def _osap_signals(seed: int = 0) -> dict[str, float]:
    """Return the universe-wide Phase 4h proxy signal dict."""
    return {
        "AbnormalAccruals": 0.42 + seed,
        "Activism1": 0.31 + seed,
        "BPEBM": 0.55 + seed,
    }


def test_section_l_empty_universe_skips(helper, capsys):
    w, f = helper.section_l_osap_proxy_invariant({}, [])
    assert (w, f) == (0, 0)
    assert "skipped" in capsys.readouterr().out


def test_section_l_no_osap_populated_skips(helper, capsys):
    stocks = [_stock(f"S{i}") for i in range(10)]
    w, f = helper.section_l_osap_proxy_invariant({}, stocks)
    assert (w, f) == (0, 0)
    assert "skipped" in capsys.readouterr().out


def test_section_l_phase4h_proxy_passes(helper, capsys):
    # Phase 4h contract: uniform osap_signals + per-ticker varying
    # osap_blended_score (mirrors the live 2026-05-23 cron #3 surface,
    # 1 unique signal set × 428 distinct blended scores on 502 tickers).
    uniform = _osap_signals()
    stocks = [
        _stock(f"S{i}",
               osap_signals=dict(uniform),
               osap_blended_score=50.0 + i * 0.13)
        for i in range(20)
    ]
    w, f = helper.section_l_osap_proxy_invariant({}, stocks)
    assert (w, f) == (0, 0)
    out = capsys.readouterr().out
    assert "phase4h_proxy" in out
    assert "1 signal set × 20 blended scores" in out


def test_section_l_blending_regression_fails(helper, capsys):
    # Failure mode 1 — uniform signals AND uniform blended_score
    # (per-ticker scalar multiplication in osap_blend.py is broken).
    uniform = _osap_signals()
    stocks = [
        _stock(f"S{i}",
               osap_signals=dict(uniform),
               osap_blended_score=50.0)  # ALL the same
        for i in range(20)
    ]
    w, f = helper.section_l_osap_proxy_invariant({}, stocks)
    assert (w, f) == (0, 1)
    out = capsys.readouterr().out
    assert "blending_regression" in out
    assert "osap_blend.py" in out


def test_section_l_graduated_warns(helper, capsys):
    # Failure mode 2 — varying osap_signals (Phase 4i+ graduation
    # signature). WARN until the docstring scope-note is updated.
    stocks = [
        _stock(f"S{i}",
               osap_signals=_osap_signals(seed=i * 0.01),
               osap_blended_score=50.0 + i * 0.13)
        for i in range(20)
    ]
    w, f = helper.section_l_osap_proxy_invariant({}, stocks)
    assert (w, f) == (1, 0)
    out = capsys.readouterr().out
    assert "graduated" in out
    assert "osap_replicate.py:14-35" in out


def test_section_l_schema_drift_fails(helper, capsys):
    # Failure mode 3 — osap_signals key set differs across tickers.
    base = _osap_signals()
    stocks = [
        _stock(f"S{i}",
               osap_signals=dict(base),
               osap_blended_score=50.0 + i * 0.13)
        for i in range(20)
    ]
    # Corrupt one ticker's signal dict shape (rename a key)
    stocks[5]["osap_signals"] = {"DifferentKey": 0.42, **{k: v for k, v in base.items() if k != "AbnormalAccruals"}}
    w, f = helper.section_l_osap_proxy_invariant({}, stocks)
    assert (w, f) == (0, 1)
    out = capsys.readouterr().out
    assert "schema_drift" in out


def test_section_l_ignores_none_osap_signals(helper, capsys):
    # Tickers with osap_signals=None (universe-gap policy from
    # osap_replicate.py:37-43) are excluded from the invariant — the
    # proxy contract only applies to populated rows.
    uniform = _osap_signals()
    stocks = [
        _stock(f"S{i}",
               osap_signals=dict(uniform),
               osap_blended_score=50.0 + i * 0.13)
        for i in range(20)
    ]
    # Half the universe is in a coverage gap
    for s in stocks[:10]:
        s["osap_signals"] = None
        s["osap_blended_score"] = None
    w, f = helper.section_l_osap_proxy_invariant({}, stocks)
    assert (w, f) == (0, 0)
    out = capsys.readouterr().out
    assert "phase4h_proxy" in out
    assert "tickers with osap_signals: 10" in out


# ---------------------------------------------------------------------------
# Section K — Form-4 universe accounting equation (Issue #208)
# ---------------------------------------------------------------------------
#
# section_k_form4_universe verifies:
#   universe_size == ok_active + ok_zero_activity + failed + missing_diag
# and cross-checks metadata.form4_tickers_with_recent_activity against
# the per-stock ok_active ground truth.


def _f4_stock(ticker: str, fetch_status: str | None, insider_count: int = 0) -> dict:
    """Build a stock dict with a form4_diagnostics payload.

    ``fetch_status=None`` simulates a ticker whose diagnostics are absent
    (fetch was skipped entirely — the ``missing_diag`` bucket).
    """
    base = _stock(ticker)
    if fetch_status is None:
        base["form4_diagnostics"] = None
    else:
        base["form4_diagnostics"] = {
            "fetch_status": fetch_status,
            "insider_count": insider_count,
            "latest_filing_date": "2026-04-12" if insider_count > 0 else None,
        }
    return base


def _f4_metadata(
    universe_size: int,
    *,
    form4_enabled: bool = True,
    form4_coverage_pct: float = 99.0,
    form4_tickers_with_recent_activity: int | None = None,
) -> dict:
    m = {
        "universe_size": universe_size,
        "form4_enabled": form4_enabled,
        "form4_coverage_pct": form4_coverage_pct,
    }
    if form4_tickers_with_recent_activity is not None:
        m["form4_tickers_with_recent_activity"] = form4_tickers_with_recent_activity
    return m


def test_section_k_pre_pr2_snapshot_skips(helper, capsys):
    """A legacy snapshot (form4_enabled absent + form4_coverage_pct absent)
    must skip cleanly: return (0, 0).
    """
    metadata = {"universe_size": 502}  # no form4_* fields
    stocks = [_f4_stock(f"S{i}", "ok", 0) for i in range(5)]
    w, f = helper.section_k_form4_universe(metadata, stocks)
    assert (w, f) == (0, 0)
    assert "skipped" in capsys.readouterr().out


def test_section_k_accounting_equation_passes_on_balanced_universe(helper, capsys):
    """Happy path: ok_active + ok_zero + failed + missing sums to universe_size.

    Composition: 2 active, 2 zero-activity, 1 failed, 1 missing → universe=6.
    """
    stocks = [
        _f4_stock("A", "ok", insider_count=3),   # ok_active
        _f4_stock("B", "ok", insider_count=1),   # ok_active
        _f4_stock("C", "ok", insider_count=0),   # ok_zero
        _f4_stock("D", "ok", insider_count=0),   # ok_zero
        _f4_stock("E", "failed", insider_count=0),  # failed
        _f4_stock("F", None),                    # missing_diag
    ]
    metadata = _f4_metadata(
        universe_size=6,
        form4_tickers_with_recent_activity=2,  # matches ok_active
    )
    w, f = helper.section_k_form4_universe(metadata, stocks)
    assert (w, f) == (0, 0)
    out = capsys.readouterr().out
    assert "2 active" in out
    assert "accounting equation" in out


def test_section_k_accounting_equation_fails_when_universe_size_mismatch(helper, capsys):
    """When the per-stock counts don't sum to universe_size, the check must
    emit a FAIL and return (0, 1).
    """
    stocks = [
        _f4_stock("A", "ok", insider_count=3),
        _f4_stock("B", "ok", insider_count=0),
        # 2 stocks but universe_size=5 — 3 unaccounted
    ]
    metadata = _f4_metadata(universe_size=5)
    w, f = helper.section_k_form4_universe(metadata, stocks)
    assert f >= 1, "Accounting mismatch must produce at least 1 failure"
    out = capsys.readouterr().out
    assert "accounting equation" in out
    assert "!=" in out


def test_section_k_metadata_active_mismatch_warns(helper, capsys):
    """When ``form4_tickers_with_recent_activity`` in metadata disagrees
    with the per-stock ground truth ok_active count, the check must emit
    a WARN (not a FAIL).
    """
    stocks = [
        _f4_stock("A", "ok", insider_count=3),   # ok_active
        _f4_stock("B", "ok", insider_count=0),   # ok_zero
    ]
    metadata = _f4_metadata(
        universe_size=2,
        form4_tickers_with_recent_activity=5,  # disagrees: per-stock truth = 1
    )
    w, f = helper.section_k_form4_universe(metadata, stocks)
    assert w >= 1, "Metadata active-count mismatch must produce at least 1 warning"
    assert f == 0, "Mismatch is a warning, not a failure"
    out = capsys.readouterr().out
    assert "form4_tickers_with_recent_activity" in out


def test_section_k_all_failed_is_accounted(helper, capsys):
    """A universe where every ticker failed is still accounted — the equation
    holds (all in the failed bucket) and no accounting failure is emitted.
    """
    stocks = [_f4_stock(f"S{i}", "failed") for i in range(5)]
    metadata = _f4_metadata(universe_size=5)
    w, f = helper.section_k_form4_universe(metadata, stocks)
    assert f == 0, "All-failed universe must satisfy the accounting equation"


def test_section_k_all_missing_is_accounted(helper, capsys):
    """A universe where every ticker has form4_diagnostics=None (fetch
    entirely skipped) is still accounted — all in the missing_diag bucket.
    """
    stocks = [_f4_stock(f"S{i}", None) for i in range(10)]
    metadata = _f4_metadata(universe_size=10)
    w, f = helper.section_k_form4_universe(metadata, stocks)
    assert f == 0, "All-missing-diag universe must satisfy the accounting equation"


def test_section_k_zero_universe_size_with_no_stocks_passes(helper, capsys):
    """Edge case: empty universe (universe_size=0) with no stocks → equation
    0 == 0 holds; must pass cleanly.
    """
    metadata = _f4_metadata(universe_size=0)
    w, f = helper.section_k_form4_universe(metadata, [])
    assert f == 0
