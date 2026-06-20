"""Coverage-gap tests for compute.scoring.risk_overlay.

These tests target specific uncovered branches identified in the
2026-06-20 coverage baseline (risk_overlay.py at 95%; lines
151, 258, 278, 305, 320, 323-324, 353, 469, 477, 502-509 were
uncovered).

Coverage policy (AGENTS.md §Testing): "add a test when a bug is found,
when a new defense ships, or when a contract is added to the output
schema."  The post_split branch paths added with defense #35 (#499)
ship with only the tier-0/tier-1/tier-2 happy-path tested; the
graceful-degradation branches below are the gap.

Companion: tests/test_scoring/test_post_split_share_lag.py covers the
main tier-1 / tier-2 happy paths.  This file adds the remaining
branches.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.scoring.risk_overlay import (
    SplitEvent,
    _data_quality_input_corruption,
    _shares_at_lookback,
    _sloan_accruals,
    check_post_split_share_lag,
)

# ---------------------------------------------------------------------------
# Minimal fixture builder — mirrors test_risk_overlay._snap style.
# ---------------------------------------------------------------------------

def _snap(**kwargs) -> FundamentalsSnapshot:
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
        "shares_outstanding": 100_000_000.0,
        "latest_period_end": date(2025, 12, 31),
        "latest_filed_date": date(2026, 2, 14),
    }
    defaults.update(kwargs)
    return FundamentalsSnapshot(**defaults)


_ASOF = date(2026, 5, 1)


def _split(days_ago: int, ratio: float = 2.0) -> SplitEvent:
    """Build a SplitEvent occurring `days_ago` days before _ASOF."""
    return SplitEvent(split_date=_ASOF - timedelta(days=days_ago), ratio=ratio)


# ---------------------------------------------------------------------------
# G1 — check_post_split_share_lag: splits_override=None fetch failure path
#      (line 469: ``if split_events is None: return _no_fire``)
# ---------------------------------------------------------------------------

def test_G1_fetch_failure_returns_tier0(monkeypatch) -> None:
    """When fetch_splits returns None (network failure / cache miss), the
    function gracefully returns tier=0 (no-fire) — not an exception.

    This locks the graceful-degradation contract: a yfinance fetch failure
    must never propagate as a flag.  Line 469 in risk_overlay.py.
    """
    monkeypatch.setattr(
        "compute.scoring.risk_overlay.fetch_splits",
        lambda ticker: None,
    )
    snap = _snap()
    result = check_post_split_share_lag(
        "TST",
        snap,
        yf_market_cap=None,
        current_price=100.0,
        today=_ASOF,
    )
    assert result.tier == 0, (
        "fetch_splits returning None must yield tier=0 (graceful degradation)"
    )


# ---------------------------------------------------------------------------
# G2 — check_post_split_share_lag: future-dated event skipped (line 477)
#      ``if days_ago <= 0: continue``
# ---------------------------------------------------------------------------

def test_G2_future_dated_split_event_is_skipped() -> None:
    """A split event whose split_date is in the future (days_ago <= 0)
    must be skipped, not counted as a triggering event.

    This covers the ``continue`` branch at line 477 in risk_overlay.py.
    Scenario: one future event + one past qualifying event.  Only the
    past event should trigger (confirming the future one was skipped).
    """
    future_split = _split(days_ago=-5, ratio=3.0)  # tomorrow-ish; days_ago = -5
    past_split = _split(days_ago=30, ratio=2.0)    # 30 days ago — qualifies

    # edgar_shares = 50M; with 2:1 split yf_implied = 100M.
    snap = _snap(shares_outstanding=50_000_000.0)
    yf_implied_shares = 100_000_000.0  # 2× edgar → exact ratio-match

    result = check_post_split_share_lag(
        "TST",
        snap,
        yf_market_cap=None,
        current_price=100.0,
        today=_ASOF,
        splits_override=[future_split, past_split],
        yf_shares_outstanding_override=yf_implied_shares,
    )
    # The past split (2:1) should trigger Tier-1 CORRECT.
    assert result.tier == 1, (
        f"Future event must be skipped; qualifying past event should trigger tier=1, "
        f"got tier={result.tier}"
    )
    assert result.split_event is past_split, (
        "Triggering event must be the past split, not the future-dated one"
    )


# ---------------------------------------------------------------------------
# G3 — check_post_split_share_lag: legs 1+2 hold but yf_implied unavailable
#      (lines 502-509: ``if yf_implied is None or yf_implied <= 0 …: return Tier-2``)
# ---------------------------------------------------------------------------

def test_G3_legs_1_2_hold_yf_implied_unavailable_yields_tier2() -> None:
    """When legs 1+2 hold (recent material split detected) but yf_implied_shares
    cannot be derived (no yf_market_cap, no yf_shares_override), the function
    emits Tier-2 (VETO) rather than failing silently.

    This locks the critical safety net at lines 502-509: the veto fires even
    when we can't numerically reconcile the correction — better to flag and
    review than to silently pass through a corrupted share count.
    """
    snap = _snap(shares_outstanding=50_000_000.0)
    result = check_post_split_share_lag(
        "TST",
        snap,
        yf_market_cap=None,   # no market cap → yf_implied can't be derived
        current_price=None,   # no price either
        today=_ASOF,
        splits_override=[_split(days_ago=30, ratio=2.0)],
        yf_shares_outstanding_override=None,  # no direct override
    )
    assert result.tier == 2, (
        "Legs 1+2 hold but yf_implied unavailable → must emit Tier-2 VETO "
        "(lines 502-509 in risk_overlay.py)"
    )
    assert result.corrected_shares is None, "Tier-2 result must have no corrected_shares"
    assert result.yf_implied_shares is None, "Tier-2 result must have no yf_implied_shares"
    # The split event that triggered legs 1+2 must be recorded.
    assert result.split_event is not None, (
        "split_event must be set on Tier-2 result (used for logging)"
    )


def test_G3b_legs_1_2_hold_yf_implied_zero_yields_tier2() -> None:
    """Variant: yf_shares_outstanding_override=0 is treated as unavailable
    (``yf_implied <= 0`` guard) and also produces Tier-2, not Tier-1.

    Zero shares is physically impossible and would corrupt the ratio
    calculation (division by zero risk), so it must be treated the same as None.
    """
    snap = _snap(shares_outstanding=50_000_000.0)
    result = check_post_split_share_lag(
        "TST",
        snap,
        yf_market_cap=None,
        current_price=100.0,
        today=_ASOF,
        splits_override=[_split(days_ago=30, ratio=2.0)],
        yf_shares_outstanding_override=0.0,  # zero — treated as unavailable
    )
    assert result.tier == 2, (
        "yf_shares_outstanding_override=0 must be treated as unavailable → Tier-2"
    )


# ---------------------------------------------------------------------------
# G4 — _sloan_accruals: total_assets == 0 path (line 278)
#      ``if ta == 0: return math.nan``
# ---------------------------------------------------------------------------

def test_G4_sloan_accruals_zero_total_assets_returns_nan() -> None:
    """When total_assets == 0, _sloan_accruals must return NaN (not divide by zero).

    This is the line-278 guard: ``if ta == 0: return math.nan``.
    The branch is distinct from ``ta is None`` (line 275).
    """
    snap = _snap(net_income=10.0, operating_cash_flow=5.0, total_assets=0.0)
    result = _sloan_accruals(snap)
    assert math.isnan(result), (
        "_sloan_accruals must return NaN when total_assets == 0 (division guard)"
    )


# ---------------------------------------------------------------------------
# G5 — _data_quality_input_corruption: None snap → False (line 151)
#      Partition lock already in test_risk_overlay.py (test_D3); this test
#      directly exercises the helper function itself, not via compute_risk_flags.
# ---------------------------------------------------------------------------

def test_G5_data_quality_corruption_false_for_none_snap() -> None:
    """_data_quality_input_corruption(None) must return False (not raise).

    The None-snap case belongs to fundamentals_unavailable, not DQIC —
    the partition invariant documented in issue #18 and CLAUDE.md §Gotchas.
    Line 151 in risk_overlay.py.
    """
    assert _data_quality_input_corruption(None) is False


# ---------------------------------------------------------------------------
# G6 — _shares_at_lookback: val is None path (line 320)
#      A history row whose ``value`` is None must return None (not crash).
# ---------------------------------------------------------------------------

def test_G6_shares_at_lookback_none_value_returns_none() -> None:
    """When the matching shares row has value=None (e.g., XBRL extraction
    found the concept but could not parse the value), _shares_at_lookback
    must return None without raising.

    Line 320: ``if val is None: return None``.
    """
    import pandas as pd

    today = date(2026, 5, 1)
    old_period = today - timedelta(days=400)

    history = pd.DataFrame([{
        "metric": "shares_outstanding",
        "value": None,           # value present but None
        "period_end": old_period,
        "fiscal_year": 2025,
        "filing_date": old_period + timedelta(days=60),
        "form_type": "10-K",
    }])
    result = _shares_at_lookback(history, asof_days=365, today=today)
    assert result is None, (
        "_shares_at_lookback must return None when the shares row value is None"
    )


# ---------------------------------------------------------------------------
# G7 — _shares_at_lookback: non-finite or non-positive float (line 325)
#      ``if not math.isfinite(v) or v <= 0: return None``
# ---------------------------------------------------------------------------

def test_G7_shares_at_lookback_nan_value_returns_none() -> None:
    """A row with value=NaN (or inf) must return None — not propagate a
    non-finite float into the NSI computation, which would produce a NaN
    NSI and silently skip the dilution flag for that ticker.

    Line 325-326 in risk_overlay.py.
    """
    import pandas as pd

    today = date(2026, 5, 1)
    old_period = today - timedelta(days=400)

    history = pd.DataFrame([{
        "metric": "shares_outstanding",
        "value": float("nan"),
        "period_end": old_period,
        "fiscal_year": 2025,
        "filing_date": old_period + timedelta(days=60),
        "form_type": "10-K",
    }])
    result = _shares_at_lookback(history, asof_days=365, today=today)
    assert result is None


def test_G7b_shares_at_lookback_negative_value_returns_none() -> None:
    """A row with value=-1 (corrupt XBRL extraction) must return None.

    Part of the same ``v <= 0`` guard — negative shares counts are
    physically impossible.
    """
    import pandas as pd

    today = date(2026, 5, 1)
    old_period = today - timedelta(days=400)

    history = pd.DataFrame([{
        "metric": "shares_outstanding",
        "value": -1_000_000.0,
        "period_end": old_period,
        "fiscal_year": 2025,
        "filing_date": old_period + timedelta(days=60),
        "form_type": "10-K",
    }])
    result = _shares_at_lookback(history, asof_days=365, today=today)
    assert result is None


# ---------------------------------------------------------------------------
# G8 — _shares_at_lookback: non-castable value (lines 323-324)
#      ``except (TypeError, ValueError): return None``
# ---------------------------------------------------------------------------

def test_G8_shares_at_lookback_non_castable_string_returns_none() -> None:
    """A row with a string value that cannot be cast to float must return None.

    Lines 323-324: ``try: v = float(val) / except (TypeError, ValueError): return None``.
    """
    import pandas as pd

    today = date(2026, 5, 1)
    old_period = today - timedelta(days=400)

    history = pd.DataFrame([{
        "metric": "shares_outstanding",
        "value": "not-a-number",
        "period_end": old_period,
        "fiscal_year": 2025,
        "filing_date": old_period + timedelta(days=60),
        "form_type": "10-K",
    }])
    result = _shares_at_lookback(history, asof_days=365, today=today)
    assert result is None, (
        "Non-castable value in shares row must return None (TypeError guard)"
    )


# ---------------------------------------------------------------------------
# G9 — check_post_split_share_lag: snap with None shares_outstanding
#      (line 353: ``if snap is None or snap.shares_outstanding is None … return _no_fire``)
# ---------------------------------------------------------------------------

def test_G9_snap_with_none_shares_returns_tier0() -> None:
    """A valid snap with shares_outstanding=None must return tier=0 (no-fire).

    Line 456 in risk_overlay.py: the second guard after ``snap is None``.
    This fires for tickers where XBRL extraction found a Company object
    but shares_outstanding was None (e.g., partially-populated snapshot).
    """
    snap = _snap(shares_outstanding=None)
    result = check_post_split_share_lag(
        "TST",
        snap,
        yf_market_cap=1_000_000_000.0,
        current_price=100.0,
        today=_ASOF,
        splits_override=[_split(days_ago=30, ratio=2.0)],
    )
    assert result.tier == 0, (
        "snap.shares_outstanding=None must yield tier=0 (no flag)"
    )
