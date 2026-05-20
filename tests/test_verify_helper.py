"""Regression tests for `.claude/skills/verify-production-output/helper.py`.

Epic #150 Phase 1.4 + 1.5 (issue #155 trail). Covers:

- Section A schema reporter — happy + tier2_coverage_pct missing + low
  fundamentals coverage branches
- Section B Tier-2 fired-flag inventory — the 4-branch matrix from
  PR #149 (tier2_enabled × {within-band, over-band, has-fire-but-
  disabled, no-fire-and-disabled})
- Section J annotate-flag audit — empty + populated paths

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
