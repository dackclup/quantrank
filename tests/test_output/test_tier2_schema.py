"""PR 3d Step 4 — schema additions + SKIP_REASONS taxonomy + snapshot tests.

Locks the new Pydantic fields (StockDetail.tier2_events,
Metadata.tier2_coverage_pct) + the 3 new SKIP_REASONS entries
(going_concern_disclosure, non_reliance_filing, auditor_change) +
the schema-snapshot CI guard's view of those fields.
"""

from __future__ import annotations

import json

from compute.output.schema_check import SNAPSHOT_PATH, generate_snapshot
from compute.output.schemas import Metadata, StockDetail
from compute.valuation.applicability import SKIP_REASONS

# ---------------------------------------------------------------------------
# A. Pydantic field tests
# ---------------------------------------------------------------------------

_DETAIL_REQUIRED = {
    "ticker": "TST",
    "name": "Test Co.",
    "sector": "Information Technology",
    "current_price": 100.0,
    "rank": 1,
    "composite_score": 50.0,
}


def test_A1_stock_detail_accepts_tier2_events_dict():
    detail = StockDetail(
        **_DETAIL_REQUIRED,
        tier2_events={
            "going_concern_disclosure": False,
            "non_reliance_filing": False,
            "auditor_change": False,
            "latest_8k_filing_date": None,
            "latest_8k_filing_url": None,
        },
    )
    assert detail.tier2_events is not None
    assert detail.tier2_events["non_reliance_filing"] is False


def test_A2_stock_detail_accepts_tier2_events_none():
    detail = StockDetail(**_DETAIL_REQUIRED, tier2_events=None)
    assert detail.tier2_events is None


def test_A3_metadata_accepts_tier2_coverage_pct_float():
    meta = Metadata(
        version="0.6.0-phase3d",
        last_update_utc="2026-05-10T03:49:51Z",
        next_update_utc="2026-05-17T03:49:51Z",
        universe="SP500",
        universe_size=502,
        compute_run_id="local",
        git_commit="0" * 40,
        tier2_coverage_pct=0.95,
    )
    assert meta.tier2_coverage_pct == 0.95


def test_A4_metadata_accepts_tier2_coverage_pct_none():
    meta = Metadata(
        version="0.6.0-phase3d",
        last_update_utc="2026-05-10T03:49:51Z",
        next_update_utc="2026-05-17T03:49:51Z",
        universe="SP500",
        universe_size=502,
        compute_run_id="local",
        git_commit="0" * 40,
        tier2_coverage_pct=None,
    )
    assert meta.tier2_coverage_pct is None


def test_A5_json_round_trip_preserves_tier2_events_shape():
    detail = StockDetail(
        **_DETAIL_REQUIRED,
        tier2_events={
            "going_concern_disclosure": True,
            "non_reliance_filing": False,
            "auditor_change": True,
            "latest_8k_filing_date": "2025-12-15",
            "latest_8k_filing_url": "https://www.sec.gov/Archives/test.htm",
        },
    )
    payload = detail.model_dump(mode="json")
    restored = StockDetail.model_validate(payload)
    assert restored.tier2_events == detail.tier2_events


# ---------------------------------------------------------------------------
# B. SKIP_REASONS taxonomy
# ---------------------------------------------------------------------------

def test_B1_going_concern_disclosure_in_skip_reasons():
    assert "going_concern_disclosure" in SKIP_REASONS


def test_B2_non_reliance_filing_in_skip_reasons():
    assert "non_reliance_filing" in SKIP_REASONS


def test_B3_auditor_change_in_skip_reasons():
    assert "auditor_change" in SKIP_REASONS


def test_B4_skip_reasons_count_is_24():
    """Was 21 in PR 3c (Step 7.5 + earlier). PR 3d Step 4 adds 3 Tier-2
    entries — total 24 stable identifiers."""
    assert len(SKIP_REASONS) == 24


def test_B5_skip_reasons_all_unique():
    """Stable-identifier rule: no duplicates allowed — JSON contract."""
    assert len(SKIP_REASONS) == len(set(SKIP_REASONS))


# ---------------------------------------------------------------------------
# D. Schema snapshot
# ---------------------------------------------------------------------------

def test_D1_committed_snapshot_includes_tier2_events_and_coverage():
    """The on-disk snapshot file (committed alongside this commit) must
    list tier2_events under StockDetail and tier2_coverage_pct under
    Metadata. Mirrors the fresh-generation test below — the difference
    is this one reads the file from disk."""
    assert SNAPSHOT_PATH.exists()
    stored = json.loads(SNAPSHOT_PATH.read_text())
    assert "tier2_events" in stored["StockDetail"]
    assert "tier2_coverage_pct" in stored["Metadata"]


def test_D2_fresh_snapshot_tier2_events_shape():
    snap = generate_snapshot()
    assert snap["StockDetail"]["tier2_events"] == {
        "type": "dict | None",
        "required": False,
        "default": None,
    }


def test_D3_fresh_snapshot_tier2_coverage_pct_shape():
    snap = generate_snapshot()
    assert snap["Metadata"]["tier2_coverage_pct"] == {
        "type": "float | None",
        "required": False,
        "default": None,
    }
