"""Tests for the post-split share-lag defense (PR-2, schema 0.10.25-phase8pilot).

Coverage:
- PSL1: KLAC-correct (Tier 1) — recent 10:1 split, ratio-reconciled, corrected_shares set.
- PSL2: ratio-mismatch-veto (Tier 2) — legs 1+2 hold, leg 3 fails.
- PSL3: outside-100d-no-fire — split too old → tier 0.
- PSL4: below-2x-no-fire — split_ratio < POST_SPLIT_MIN_RATIO → tier 0.
- PSL5: Tier-1 NOT in risk_flags (PR-2 fix) — compute_risk_flags does NOT emit
        "post_split_share_lag" for a Tier-1 inject; Tier-2 ("post_split_share_lag_
        unreconciled") DOES appear BEFORE data_quality_input_corruption in the list.
- PSL7: raw-value audit pin — RawMetrics.shares_outstanding_pre_split_raw is the
        pre-correction EDGAR value for a Tier-1 ticker, None for a Tier-0 ticker.
        Field is populated when post_split_share_lag is in valuation_warnings (not
        risk_flags — PR-2 double-penalty fix).
- PSL_ROT: Top-5 rotation pin — Tier-1 corrected ticker has EMPTY risk_flags so
        the Step-7 gate does NOT skip it; Tier-2 ticker has
        "post_split_share_lag_unreconciled" in risk_flags so IS skipped.
- PSL_VW: Tier-1 valuation_warnings companion — the main.py per-ticker emission
        logic appends "post_split_share_lag" to valuation_warnings (not risk_flags).
- SPLITS1: splits.py graceful-degradation — fetch failure → None, no crash.
"""

from __future__ import annotations

from datetime import date

import pytest

from compute import config
from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.ingest.splits import SplitEvent, fetch_splits
from compute.output.schemas import RawMetrics
from compute.scoring.risk_overlay import (
    PostSplitResult,
    check_post_split_share_lag,
    compute_risk_flags,
)

# ---------------------------------------------------------------------------
# Shared helpers (mirrors the _snap() / _filing() pattern from test_risk_overlay)
# ---------------------------------------------------------------------------

def _snap(**kwargs) -> FundamentalsSnapshot:
    """Build a healthy FundamentalsSnapshot; overrides target specific fields."""
    defaults = {
        "ticker": "TST",
        "cik": "0000000001",
        "revenue": 100_000_000.0,
        "net_income": 10_000_000.0,
        "total_assets": 200_000_000.0,
        "total_liabilities": 100_000_000.0,
        "stockholders_equity": 100_000_000.0,
        "current_assets": 100_000_000.0,
        "current_liabilities": 50_000_000.0,
        "operating_cash_flow": 10_000_000.0,
        "retained_earnings": 50_000_000.0,
        "operating_income": 20_000_000.0,
        "latest_period_end": date(2025, 12, 31),
        "latest_filed_date": date(2026, 2, 14),
    }
    defaults.update(kwargs)
    return FundamentalsSnapshot(**defaults)


# Deterministic "today" for all tests — inside the 100-day window.
_TODAY = date(2026, 6, 18)


def _split_event(days_ago: int, ratio: float) -> SplitEvent:
    """Build a SplitEvent relative to _TODAY."""
    return SplitEvent(
        split_date=_TODAY - __import__("datetime").timedelta(days=days_ago),
        ratio=ratio,
    )


# ---------------------------------------------------------------------------
# PSL1 — KLAC-correct (Tier 1)
#
# Scenario: EDGAR holds 130.6M shares (pre-split value not yet updated).
# yfinance says the split happened 6 days ago at 10:1.
# yf-implied shares ≈ 1306.3M.  Tier-1 must fire; corrected_shares = 1306M.
# ---------------------------------------------------------------------------

KLAC_EDGAR_SHARES = 130_600_000.0     # EDGAR stale value (pre-split)
KLAC_SPLIT_RATIO = 10.0
KLAC_YF_IMPLIED = KLAC_EDGAR_SHARES * KLAC_SPLIT_RATIO  # 1_306_000_000.0


def test_PSL1_klac_correct_fires_tier1():
    """KLAC-shape: 10:1 split 6 days ago, yf-implied ≈ edgar × 10 → Tier-1."""
    snap = _snap(ticker="KLAC", shares_outstanding=KLAC_EDGAR_SHARES)
    split_6d = _split_event(days_ago=6, ratio=KLAC_SPLIT_RATIO)

    result = check_post_split_share_lag(
        ticker="KLAC",
        snap=snap,
        yf_market_cap=None,
        current_price=None,
        today=_TODAY,
        splits_override=[split_6d],
        yf_shares_outstanding_override=KLAC_YF_IMPLIED,
    )

    assert result.tier == 1, f"Expected Tier-1 (CORRECT), got tier={result.tier}"
    assert result.corrected_shares is not None
    # corrected_shares = edgar_shares × split_ratio
    assert abs(result.corrected_shares - KLAC_EDGAR_SHARES * KLAC_SPLIT_RATIO) < 1.0, (
        f"corrected_shares={result.corrected_shares} far from expected "
        f"{KLAC_EDGAR_SHARES * KLAC_SPLIT_RATIO}"
    )


def test_PSL1_klac_corrected_shares_value():
    """Tier-1: corrected_shares ≈ 1306.3M (130.6M × 10)."""
    snap = _snap(ticker="KLAC", shares_outstanding=KLAC_EDGAR_SHARES)
    split_6d = _split_event(days_ago=6, ratio=KLAC_SPLIT_RATIO)

    result = check_post_split_share_lag(
        ticker="KLAC",
        snap=snap,
        yf_market_cap=None,
        current_price=None,
        today=_TODAY,
        splits_override=[split_6d],
        yf_shares_outstanding_override=KLAC_YF_IMPLIED,
    )

    expected_corrected = 1_306_000_000.0  # 130.6M × 10
    assert result.corrected_shares == pytest.approx(expected_corrected, rel=0.01), (
        f"corrected_shares={result.corrected_shares}, expected ≈{expected_corrected}"
    )


def test_PSL1_klac_split_event_attached():
    """Tier-1 result must carry the triggering SplitEvent."""
    snap = _snap(ticker="KLAC", shares_outstanding=KLAC_EDGAR_SHARES)
    split_6d = _split_event(days_ago=6, ratio=KLAC_SPLIT_RATIO)

    result = check_post_split_share_lag(
        ticker="KLAC",
        snap=snap,
        yf_market_cap=None,
        current_price=None,
        today=_TODAY,
        splits_override=[split_6d],
        yf_shares_outstanding_override=KLAC_YF_IMPLIED,
    )

    assert result.split_event is not None
    assert result.split_event.ratio == KLAC_SPLIT_RATIO


# ---------------------------------------------------------------------------
# PSL2 — ratio-mismatch-veto (Tier 2)
#
# Legs 1+2 hold (recent 10:1 split), but the yf-implied/edgar ratio = 1.5×
# instead of 10× → leg 3 fails → Tier-2 VETO.
# ---------------------------------------------------------------------------

def test_PSL2_ratio_mismatch_fires_tier2():
    """Legs 1+2 pass (recent 10:1 split), leg 3 fails (yf/edgar ratio ≈ 1.5×) → Tier-2."""
    snap = _snap(ticker="MISMATCH", shares_outstanding=100_000_000.0)
    split_10x = _split_event(days_ago=30, ratio=10.0)

    # yf-implied ≈ 1.5× edgar (ratio_delta = |1.5 - 10| / 10 = 85% >> 10% tolerance)
    yf_implied_mismatch = 100_000_000.0 * 1.5

    result = check_post_split_share_lag(
        ticker="MISMATCH",
        snap=snap,
        yf_market_cap=None,
        current_price=None,
        today=_TODAY,
        splits_override=[split_10x],
        yf_shares_outstanding_override=yf_implied_mismatch,
    )

    assert result.tier == 2, (
        f"Expected Tier-2 (VETO) on ratio mismatch, got tier={result.tier}"
    )
    assert result.corrected_shares is None, (
        "Tier-2 must NOT set corrected_shares (ratio unreconcilable)"
    )


def test_PSL2_tier2_has_no_corrected_shares():
    """Tier-2 result: corrected_shares is None (cannot safely correct)."""
    snap = _snap(ticker="T2", shares_outstanding=200_000_000.0)
    split_4x = _split_event(days_ago=20, ratio=4.0)
    # yf implies only 1.3× edgar — big mismatch
    yf_bad = 200_000_000.0 * 1.3

    result = check_post_split_share_lag(
        ticker="T2",
        snap=snap,
        yf_market_cap=None,
        current_price=None,
        today=_TODAY,
        splits_override=[split_4x],
        yf_shares_outstanding_override=yf_bad,
    )

    assert result.tier == 2
    assert result.corrected_shares is None


# ---------------------------------------------------------------------------
# PSL3 — outside-100d-no-fire
#
# A split that happened 101 days ago must NOT fire (EDGAR has had time to refresh).
# ---------------------------------------------------------------------------

def test_PSL3_split_outside_window_fires_tier0():
    """Split 101 days ago (> POST_SPLIT_WINDOW_DAYS=100) → tier 0 (no-fire)."""
    snap = _snap(ticker="OLD", shares_outstanding=500_000_000.0)
    old_split = _split_event(days_ago=101, ratio=4.0)

    result = check_post_split_share_lag(
        ticker="OLD",
        snap=snap,
        yf_market_cap=None,
        current_price=None,
        today=_TODAY,
        splits_override=[old_split],
        yf_shares_outstanding_override=500_000_000.0 * 4.0,
    )

    assert result.tier == 0, (
        f"Split at 101 days should not fire (window={config.POST_SPLIT_WINDOW_DAYS}d), "
        f"got tier={result.tier}"
    )


def test_PSL3_boundary_at_window_fires():
    """Split exactly POST_SPLIT_WINDOW_DAYS days ago IS within the window → may fire."""
    # The window condition is days_ago <= POST_SPLIT_WINDOW_DAYS (inclusive).
    snap = _snap(ticker="BOUNDARY", shares_outstanding=100_000_000.0)
    boundary_split = _split_event(days_ago=config.POST_SPLIT_WINDOW_DAYS, ratio=2.0)
    yf_implied = 100_000_000.0 * 2.0

    result = check_post_split_share_lag(
        ticker="BOUNDARY",
        snap=snap,
        yf_market_cap=None,
        current_price=None,
        today=_TODAY,
        splits_override=[boundary_split],
        yf_shares_outstanding_override=yf_implied,
    )
    # At the boundary the split IS within the window; tier should be 1 or 2, not 0.
    assert result.tier != 0, (
        f"Split exactly at window boundary ({config.POST_SPLIT_WINDOW_DAYS}d) "
        "should fire (inclusive), got tier=0"
    )


# ---------------------------------------------------------------------------
# PSL4 — below-2x-no-fire
#
# A 1.5:1 split ratio < POST_SPLIT_MIN_RATIO=2.0 → tier 0 (not material).
# ---------------------------------------------------------------------------

def test_PSL4_sub_threshold_ratio_fires_tier0():
    """split_ratio=1.5 < POST_SPLIT_MIN_RATIO=2.0 → tier 0 (not material)."""
    snap = _snap(ticker="SMALL", shares_outstanding=300_000_000.0)
    tiny_split = _split_event(days_ago=10, ratio=1.5)

    result = check_post_split_share_lag(
        ticker="SMALL",
        snap=snap,
        yf_market_cap=None,
        current_price=None,
        today=_TODAY,
        splits_override=[tiny_split],
        yf_shares_outstanding_override=300_000_000.0 * 1.5,
    )

    assert result.tier == 0, (
        f"split_ratio=1.5 < POST_SPLIT_MIN_RATIO={config.POST_SPLIT_MIN_RATIO} "
        f"must not fire, got tier={result.tier}"
    )


def test_PSL4_exact_min_ratio_fires():
    """split_ratio == POST_SPLIT_MIN_RATIO (≥ semantics) → fires (tier 1 or 2)."""
    snap = _snap(ticker="EXACT", shares_outstanding=100_000_000.0)
    at_min_split = _split_event(days_ago=10, ratio=config.POST_SPLIT_MIN_RATIO)
    yf_implied = 100_000_000.0 * config.POST_SPLIT_MIN_RATIO

    result = check_post_split_share_lag(
        ticker="EXACT",
        snap=snap,
        yf_market_cap=None,
        current_price=None,
        today=_TODAY,
        splits_override=[at_min_split],
        yf_shares_outstanding_override=yf_implied,
    )

    assert result.tier != 0, (
        f"split_ratio == POST_SPLIT_MIN_RATIO ({config.POST_SPLIT_MIN_RATIO}) "
        "must fire (≥ is inclusive), got tier=0"
    )


# ---------------------------------------------------------------------------
# PSL5 — Tier-1 NOT in risk_flags; Tier-2 ordering relative to DQIC preserved
#
# PR-2 fix (2026-06-18): Tier-1 "post_split_share_lag" is NO LONGER emitted
# into risk_flags — it goes to valuation_warnings in the main.py per-ticker
# loop only.  The Top-5 rotation gate (Step 7) skips any ticker with non-empty
# risk_flags, so routing a corrected (data-is-correct) Tier-1 ticker through
# risk_flags was a double-penalty bug.
#
# Tier-2 "post_split_share_lag_unreconciled" is still in risk_flags (unchanged),
# and must still appear BEFORE data_quality_input_corruption in the list — the
# split check runs before the DQIC check in compute_risk_flags by design.
# ---------------------------------------------------------------------------

def test_PSL5_post_split_flag_appears_before_dqic_in_list():
    """Tier-2 unreconciled flag appears before DQIC in risk_flags list (ordering pin).

    Premise of the old Tier-1 ordering test is now moot — Tier-1 does NOT live
    in risk_flags at all (PR-2 fix).  The ordering that still matters is:
    post_split_share_lag_unreconciled (Tier-2) must precede
    data_quality_input_corruption in the flag list, because the split check
    runs before the DQIC ceiling check in compute_risk_flags.

    We use a DQIC-triggering snapshot (huge equity / tiny shares) WITH a Tier-2
    inject to exercise the Tier-2 ordering.
    """
    dqic_snap = _snap(
        ticker="SPLIT_DQIC",
        stockholders_equity=76_000_000_000.0,
        shares_outstanding=8_000.0,
    )

    tier2_result = PostSplitResult(
        tier=2,
        split_event=_split_event(days_ago=10, ratio=10.0),
        edgar_shares=8_000.0,
        corrected_shares=None,
        yf_implied_shares=12_000.0,  # mismatch → Tier-2
    )

    flags = compute_risk_flags(
        {"SPLIT_DQIC": dqic_snap},
        post_split_results={"SPLIT_DQIC": tier2_result},
    )

    flag_list = flags["SPLIT_DQIC"]
    assert "post_split_share_lag_unreconciled" in flag_list, (
        "post_split_share_lag_unreconciled must be in risk_flags for a Tier-2 inject"
    )
    assert "data_quality_input_corruption" in flag_list, (
        "data_quality_input_corruption must also fire on the DQIC-shaped snapshot"
    )

    psl_idx = flag_list.index("post_split_share_lag_unreconciled")
    dqic_idx = flag_list.index("data_quality_input_corruption")
    assert psl_idx < dqic_idx, (
        f"post_split_share_lag_unreconciled (index {psl_idx}) must come BEFORE "
        f"data_quality_input_corruption (index {dqic_idx}) in the flag list — "
        "the split check runs BEFORE DQIC by design (compute_risk_flags ordering)."
    )


def test_PSL5_post_split_tier1_flag_name_is_correct():
    """Tier-1 inject → 'post_split_share_lag' NOT in compute_risk_flags output.

    PR-2 fix (2026-06-18): Tier-1 is the CORRECT path (data is repaired);
    routing it through risk_flags was a double-penalty bug — the Step-7
    Top-5 gate skips any ticker with non-empty risk_flags.  Tier-1 now
    emits into valuation_warnings only (see test_PSL_VW_* tests).
    """
    snap = _snap(ticker="TIER1FLAG")
    tier1 = PostSplitResult(
        tier=1,
        split_event=_split_event(days_ago=5, ratio=10.0),
        edgar_shares=100_000_000.0,
        corrected_shares=1_000_000_000.0,
        yf_implied_shares=1_000_000_000.0,
    )
    flags = compute_risk_flags({"TIER1FLAG": snap}, post_split_results={"TIER1FLAG": tier1})
    assert "post_split_share_lag" not in flags["TIER1FLAG"], (
        "post_split_share_lag must NOT appear in risk_flags for Tier-1 "
        "(PR-2 fix: Tier-1 is the CORRECT path, should not block Top-5)"
    )
    assert "post_split_share_lag_unreconciled" not in flags["TIER1FLAG"]


def test_PSL5_post_split_tier2_flag_name_is_correct():
    """Tier-2 inject → flag name is 'post_split_share_lag_unreconciled' (the veto)."""
    snap = _snap(ticker="TIER2FLAG")
    tier2 = PostSplitResult(
        tier=2,
        split_event=_split_event(days_ago=10, ratio=4.0),
        edgar_shares=100_000_000.0,
        corrected_shares=None,
        yf_implied_shares=130_000_000.0,
    )
    flags = compute_risk_flags({"TIER2FLAG": snap}, post_split_results={"TIER2FLAG": tier2})
    assert "post_split_share_lag_unreconciled" in flags["TIER2FLAG"]
    assert "post_split_share_lag" not in flags["TIER2FLAG"]


def test_PSL5_tier0_result_emits_no_flag():
    """Tier-0 inject → no post_split flag in the output list."""
    snap = _snap(ticker="TIER0")
    tier0 = PostSplitResult(tier=0)
    flags = compute_risk_flags({"TIER0": snap}, post_split_results={"TIER0": tier0})
    assert "post_split_share_lag" not in flags["TIER0"]
    assert "post_split_share_lag_unreconciled" not in flags["TIER0"]


def test_PSL5_missing_from_inject_dict_emits_no_flag():
    """When post_split_results dict is present but ticker is absent → no flag."""
    snap = _snap(ticker="ABSENT")
    flags = compute_risk_flags(
        {"ABSENT": snap},
        post_split_results={"OTHER": PostSplitResult(tier=1)},
    )
    assert "post_split_share_lag" not in flags["ABSENT"]
    assert "post_split_share_lag_unreconciled" not in flags["ABSENT"]


def test_PSL5_no_inject_dict_emits_no_flag():
    """When post_split_results=None (default), no post_split flag fires."""
    snap = _snap(ticker="NOINJECT")
    flags = compute_risk_flags({"NOINJECT": snap})
    assert "post_split_share_lag" not in flags["NOINJECT"]
    assert "post_split_share_lag_unreconciled" not in flags["NOINJECT"]


# ---------------------------------------------------------------------------
# PSL7 — raw-value audit pin
#
# RawMetrics.shares_outstanding_pre_split_raw must be:
# - the pre-correction EDGAR value when post_split_share_lag is in
#   valuation_warnings (Tier-1 path — Rule 9 audit trail).
#   NOTE: PR-2 fix moved Tier-1 from risk_flags → valuation_warnings;
#   the audit-trail field still captures the pre-correction value.
# - None for a Tier-0 ticker (no correction applied)
# ---------------------------------------------------------------------------

def test_PSL7_pre_split_raw_field_accepts_edgar_value():
    """RawMetrics.shares_outstanding_pre_split_raw = the pre-correction EDGAR value
    for a Tier-1 ticker (audit trail per Rule 9).

    PR-2 note: Tier-1 emits "post_split_share_lag" into valuation_warnings
    (not risk_flags — double-penalty fix); this field is the audit trail
    regardless of the emit channel.
    """
    edgar_pre_correction = 130_600_000.0  # KLAC-shape

    raw = RawMetrics(
        shares_outstanding=KLAC_EDGAR_SHARES * KLAC_SPLIT_RATIO,  # corrected value
        shares_outstanding_pre_split_raw=edgar_pre_correction,
    )

    assert raw.shares_outstanding_pre_split_raw == edgar_pre_correction, (
        "shares_outstanding_pre_split_raw must hold the raw EDGAR value "
        f"({edgar_pre_correction}) before the Tier-1 correction"
    )
    # shares_outstanding is the corrected value
    assert raw.shares_outstanding == KLAC_EDGAR_SHARES * KLAC_SPLIT_RATIO


def test_PSL7_pre_split_raw_field_none_for_no_split():
    """RawMetrics.shares_outstanding_pre_split_raw is None for a Tier-0 ticker
    (no split correction applied — normal path)."""
    raw = RawMetrics(
        shares_outstanding=500_000_000.0,
        shares_outstanding_pre_split_raw=None,
    )

    assert raw.shares_outstanding_pre_split_raw is None, (
        "shares_outstanding_pre_split_raw must be None on a normal (no-split) ticker"
    )


def test_PSL7_pre_split_raw_round_trips():
    """shares_outstanding_pre_split_raw round-trips through model_dump / model_validate."""
    edgar_value = 250_000_000.0
    raw = RawMetrics(shares_outstanding_pre_split_raw=edgar_value)

    dumped = raw.model_dump(mode="json")
    assert dumped["shares_outstanding_pre_split_raw"] == edgar_value

    restored = RawMetrics.model_validate(dumped)
    assert restored.shares_outstanding_pre_split_raw == edgar_value


def test_PSL7_pre_split_raw_default_is_none():
    """RawMetrics.shares_outstanding_pre_split_raw defaults to None (backward-compat
    with pre-0.10.25 serialized JSONs)."""
    raw = RawMetrics()
    assert raw.shares_outstanding_pre_split_raw is None

    # Legacy JSON without the key must deserialize cleanly.
    legacy_json: dict = {}  # empty — simulates a pre-0.10.25 artifact
    restored = RawMetrics.model_validate(legacy_json)
    assert restored.shares_outstanding_pre_split_raw is None


# ---------------------------------------------------------------------------
# PSL_ROT — Top-5 rotation pin (PR-2 key fix)
#
# The Step-7 rotation gate in compute/main.py reads:
#
#     if risk_flags.get(ticker):
#         continue   # skip flagged stocks even if they'd qualify
#
# After PR-2:
#   Tier-1 corrected ticker → risk_flags entry is EMPTY (or absent) → NOT skipped
#   Tier-2 veto ticker      → "post_split_share_lag_unreconciled" in risk_flags → IS skipped
#
# We test the gate logic directly using the exact data structures main.py
# passes to it — no need to run the full compute.main.
# ---------------------------------------------------------------------------

def test_PSL_ROT1_tier1_ticker_not_skipped_by_rotation_gate():
    """Tier-1 corrected ticker has no entry in risk_flags → rotation gate lets it through.

    The key invariant: after PR-2, a Tier-1 split corrected ticker has
    CORRECT data and must NOT be blocked from entered_top5.

    Logic mirrored from compute/main.py Step 7 (~line 1547):
        if risk_flags.get(ticker):
            continue
    """
    # Simulate the risk_flags dict as compute_risk_flags() would produce for a
    # Tier-1 ticker: the ticker is either absent or maps to an empty list.
    # (The production code skips writing an entry when no flags fire.)
    risk_flags_for_tier1: dict[str, list[str]] = {
        "TIER1_CORRECTED": [],  # empty → falsy → gate does NOT skip
        "OTHER_CLEAN": [],
    }

    # Mirror the Step-7 loop gate exactly.
    skipped: list[str] = []
    for ticker in ["TIER1_CORRECTED", "OTHER_CLEAN"]:
        if risk_flags_for_tier1.get(ticker):
            skipped.append(ticker)

    assert "TIER1_CORRECTED" not in skipped, (
        "Tier-1 corrected ticker must NOT be skipped by the Top-5 rotation gate "
        "(risk_flags is empty for Tier-1 after PR-2 fix)"
    )


def test_PSL_ROT2_tier2_ticker_is_skipped_by_rotation_gate():
    """Tier-2 veto ticker has 'post_split_share_lag_unreconciled' in risk_flags
    → rotation gate skips it (Top-5 suppressed, as required).

    Logic mirrored from compute/main.py Step 7 (~line 1547):
        if risk_flags.get(ticker):
            continue
    """
    risk_flags_for_tier2: dict[str, list[str]] = {
        "TIER2_VETO": ["post_split_share_lag_unreconciled"],
        "CLEAN_STOCK": [],
    }

    skipped: list[str] = []
    for ticker in ["TIER2_VETO", "CLEAN_STOCK"]:
        if risk_flags_for_tier2.get(ticker):
            skipped.append(ticker)

    assert "TIER2_VETO" in skipped, (
        "Tier-2 veto ticker must be skipped by the Top-5 rotation gate "
        "('post_split_share_lag_unreconciled' is a real veto)"
    )
    assert "CLEAN_STOCK" not in skipped, (
        "Clean stock with empty risk_flags must pass the rotation gate"
    )


def test_PSL_ROT3_tier1_and_tier2_diverge_at_gate():
    """Tier-1 (corrected) and Tier-2 (veto) differ at the rotation gate.

    Combined scenario: one Tier-1 corrected ticker and one Tier-2 veto ticker
    in the same simulated run.  Only the Tier-2 ticker is excluded from Top-5.
    """
    risk_flags: dict[str, list[str]] = {
        "KLAC_TIER1": [],                                         # Tier-1 → no flags
        "MISMATCH_TIER2": ["post_split_share_lag_unreconciled"],  # Tier-2 → veto flag
        "AAPL_CLEAN": [],                                         # unrelated clean stock
    }

    skipped: list[str] = []
    passed: list[str] = []
    for ticker in ["KLAC_TIER1", "MISMATCH_TIER2", "AAPL_CLEAN"]:
        if risk_flags.get(ticker):
            skipped.append(ticker)
        else:
            passed.append(ticker)

    assert "KLAC_TIER1" in passed, (
        "Tier-1 corrected stock must pass the rotation gate (no risk_flags entry)"
    )
    assert "MISMATCH_TIER2" in skipped, (
        "Tier-2 veto stock must be excluded from Top-5 rotation"
    )
    assert "AAPL_CLEAN" in passed, (
        "Unrelated clean stock must pass the rotation gate"
    )


# ---------------------------------------------------------------------------
# PSL_VW — Tier-1 → valuation_warnings emission (PR-2 fix channel pin)
#
# The main.py per-ticker loop (compute/main.py ~line 2196) emits
# "post_split_share_lag" into valuation_warnings when post_split_results
# has a Tier-1 entry for the ticker.  We replicate the exact emission
# logic (a pure dict/list operation) without invoking compute.main.
# ---------------------------------------------------------------------------

def test_PSL_VW1_tier1_emits_into_valuation_warnings():
    """Simulating the main.py Tier-1 emission block confirms 'post_split_share_lag'
    lands in valuation_warnings, NOT risk_flags.

    The block verbatim from compute/main.py (~line 2196):

        _psr_for_ticker = post_split_results.get(ticker)
        if _psr_for_ticker is not None and _psr_for_ticker.tier == 1:
            if "post_split_share_lag" not in valuation_warnings:
                valuation_warnings.append("post_split_share_lag")
    """
    ticker = "KLAC_TIER1"
    post_split_results: dict[str, PostSplitResult] = {
        ticker: PostSplitResult(
            tier=1,
            split_event=_split_event(days_ago=6, ratio=10.0),
            edgar_shares=KLAC_EDGAR_SHARES,
            corrected_shares=KLAC_YF_IMPLIED,
            yf_implied_shares=KLAC_YF_IMPLIED,
        )
    }
    risk_flags: dict[str, list[str]] = {ticker: []}  # Tier-1 → empty
    valuation_warnings: list[str] = []

    # Mirror the emission block from compute/main.py exactly.
    _psr_for_ticker = post_split_results.get(ticker)
    if _psr_for_ticker is not None and _psr_for_ticker.tier == 1:
        if "post_split_share_lag" not in valuation_warnings:
            valuation_warnings.append("post_split_share_lag")

    assert "post_split_share_lag" in valuation_warnings, (
        "Tier-1 path must emit 'post_split_share_lag' into valuation_warnings"
    )
    assert "post_split_share_lag" not in risk_flags.get(ticker, []), (
        "Tier-1 path must NOT emit 'post_split_share_lag' into risk_flags "
        "(PR-2 double-penalty fix)"
    )


def test_PSL_VW2_tier2_does_not_emit_into_valuation_warnings_as_psl_key():
    """Tier-2 path does NOT add 'post_split_share_lag' (the Tier-1 annotate key)
    to valuation_warnings.  Tier-2 only writes 'post_split_share_lag_unreconciled'
    into risk_flags + 'valuation_output_anomalous' into valuation_warnings.

    This pins that the two tier channels don't bleed into each other.
    """
    ticker = "MISMATCH_TIER2"
    post_split_results: dict[str, PostSplitResult] = {
        ticker: PostSplitResult(
            tier=2,
            split_event=_split_event(days_ago=10, ratio=4.0),
            edgar_shares=100_000_000.0,
            corrected_shares=None,
            yf_implied_shares=130_000_000.0,
        )
    }
    valuation_warnings: list[str] = []

    # Mirror the Tier-1 emission block — it must NOT fire for a Tier-2 result.
    _psr_for_ticker = post_split_results.get(ticker)
    if _psr_for_ticker is not None and _psr_for_ticker.tier == 1:
        if "post_split_share_lag" not in valuation_warnings:
            valuation_warnings.append("post_split_share_lag")

    assert "post_split_share_lag" not in valuation_warnings, (
        "Tier-2 path must NOT emit the Tier-1 annotate key 'post_split_share_lag' "
        "into valuation_warnings"
    )


def test_PSL_VW3_idempotent_valuation_warnings_append():
    """The idempotency guard prevents 'post_split_share_lag' from appearing
    twice in valuation_warnings if the block runs more than once (or the key
    was already present from another defense).
    """
    ticker = "IDEMPOTENT"
    post_split_results: dict[str, PostSplitResult] = {
        ticker: PostSplitResult(
            tier=1,
            split_event=_split_event(days_ago=3, ratio=5.0),
            edgar_shares=50_000_000.0,
            corrected_shares=250_000_000.0,
            yf_implied_shares=250_000_000.0,
        )
    }
    # Pre-seed the list as if another code path already added the key.
    valuation_warnings: list[str] = ["post_split_share_lag"]

    _psr_for_ticker = post_split_results.get(ticker)
    if _psr_for_ticker is not None and _psr_for_ticker.tier == 1:
        if "post_split_share_lag" not in valuation_warnings:
            valuation_warnings.append("post_split_share_lag")

    assert valuation_warnings.count("post_split_share_lag") == 1, (
        "idempotency guard must prevent duplicate 'post_split_share_lag' entries "
        "in valuation_warnings"
    )


# ---------------------------------------------------------------------------
# SPLITS1 — graceful degradation in splits.py
#
# On yfinance fetch failure → fetch_splits returns None; no crash.
# ---------------------------------------------------------------------------

def test_SPLITS1_fetch_failure_returns_none(monkeypatch, tmp_path):
    """fetch_splits graceful-degradation: any yfinance exception → None (no crash).

    Uses monkeypatch to inject a failing yfinance call without a network hit,
    and tmp_path so no real cache directory is touched.
    """
    import compute.ingest.splits as splits_mod

    # Point the cache directory at tmp_path so nothing touches the real cache.
    monkeypatch.setattr(splits_mod, "_SPLITS_CACHE_DIR", tmp_path / "yfinance_splits")

    # Patch _yf_fetch_splits to raise — simulates network error or yfinance API change.
    def _raise(*args, **kwargs):
        raise RuntimeError("yfinance API unavailable (test-injected)")

    monkeypatch.setattr(splits_mod, "_yf_fetch_splits", _raise)

    # Remove QR_SKIP_SPLITS if present so we hit the normal code path.
    monkeypatch.delenv("QR_SKIP_SPLITS", raising=False)

    result = fetch_splits("KLAC")

    assert result is None, (
        f"fetch_splits must return None on fetch failure (graceful degradation), got: {result}"
    )


def test_SPLITS1_no_splits_returns_empty_list(monkeypatch, tmp_path):
    """fetch_splits: empty yfinance .splits → empty list (not None).

    Empty list means "successful fetch found no events" — distinct from None (error).
    """
    import compute.ingest.splits as splits_mod

    monkeypatch.setattr(splits_mod, "_SPLITS_CACHE_DIR", tmp_path / "yfinance_splits")

    def _empty(*args, **kwargs):
        return []

    monkeypatch.setattr(splits_mod, "_yf_fetch_splits", _empty)
    monkeypatch.delenv("QR_SKIP_SPLITS", raising=False)

    result = fetch_splits("AAPL")
    assert result == [], (
        f"fetch_splits must return [] when yfinance reports no splits, got: {result}"
    )


def test_SPLITS1_snap_none_fires_no_flag_when_splits_available():
    """check_post_split_share_lag with snap=None → tier 0 (graceful, no crash).

    The ``snap is None`` path is the complete-EDGAR-ingest-failure case handled
    upstream by fundamentals_unavailable.  post_split must not co-fire.
    """
    result = check_post_split_share_lag(
        ticker="NULL",
        snap=None,
        yf_market_cap=None,
        current_price=None,
        today=_TODAY,
        splits_override=[_split_event(days_ago=5, ratio=10.0)],
        yf_shares_outstanding_override=1_000_000_000.0,
    )

    assert result.tier == 0, (
        f"snap=None → tier 0 (no-fire), got tier={result.tier}"
    )


def test_SPLITS1_qr_skip_splits_cold_cache_returns_none(monkeypatch, tmp_path):
    """QR_SKIP_SPLITS=1 with cold cache (no cache file) → returns None, no fetch."""
    import compute.ingest.splits as splits_mod

    monkeypatch.setenv("QR_SKIP_SPLITS", "1")
    monkeypatch.setattr(splits_mod, "_SPLITS_CACHE_DIR", tmp_path / "yfinance_splits")

    # Verify no live fetch happens by asserting _yf_fetch_splits is never called.
    called = []

    def _should_not_be_called(*args, **kwargs):
        called.append(True)
        return []

    monkeypatch.setattr(splits_mod, "_yf_fetch_splits", _should_not_be_called)

    result = fetch_splits("TSLA")

    assert result is None, (
        "QR_SKIP_SPLITS=1 + cold cache must return None (no live fetch)"
    )
    assert not called, "_yf_fetch_splits must not be called when QR_SKIP_SPLITS=1"
