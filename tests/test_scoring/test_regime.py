"""Unit tests for compute.scoring.regime — Proposal D (market-regime diagnostic).

Proposal D (2026-06-25) — 2nd slice of the legendary-fund deep-research
6-proposal program.  This module is WRITE-ONLY / OBSERVABILITY-ONLY per Rule 18
and the Welch-Goyal 2008 rejection-as-tilt rationale (see regime.py module
docstring for the full academic justification).

Coverage
--------
Section A — threshold constants (Tier-3 gut-feel calibration pinned to catch drift)
Section B — normal regime paths (all above, all below, neutral band)
Section C — boundary conditions (exactly 60% → risk_on, exactly 40% → risk_off)
Section D — short-history exclusion (< 200 bars excluded from denominator)
Section E — graceful edge cases (empty input, None frames, no eligible tickers)
Section F — column fallback (Adj Close used when Close is absent)
Section G — NaN handling (dropna does not crash and excludes NaN rows)
Section H — Metadata schema round-trip (both new fields, default-None compat)
"""

from __future__ import annotations

import pandas as pd

from compute import config
from compute.output.schemas import Metadata
from compute.scoring.regime import compute_market_regime

# ---------------------------------------------------------------------------
# Helpers — synthetic price-frame builders
# ---------------------------------------------------------------------------

def _price_frame(n_bars: int, latest_above_sma: bool, *, col: str = "Close") -> pd.DataFrame:
    """Build a minimal synthetic price DataFrame with `n_bars` rows.

    When `latest_above_sma=True` the latest close sits above the 200-day SMA;
    when False it sits below.  For the SMA-200 to be meaningful the frame must
    have at least 200 rows — frames with fewer rows are only used to test
    the short-history exclusion path.

    The SMA-200 of a flat series is just the flat value itself; adding/
    subtracting 1.0 puts the latest bar definitively above/below.
    """
    closes = [100.0] * n_bars
    if n_bars >= 200:
        # Make the last bar clearly above or below the trailing 200-bar mean
        closes[-1] = 101.0 if latest_above_sma else 99.0
    return pd.DataFrame({col: closes})


def _above(n_bars: int = 250, *, col: str = "Close") -> pd.DataFrame:
    return _price_frame(n_bars, latest_above_sma=True, col=col)


def _below(n_bars: int = 250, *, col: str = "Close") -> pd.DataFrame:
    return _price_frame(n_bars, latest_above_sma=False, col=col)


# ---------------------------------------------------------------------------
# Section A — threshold constants
# ---------------------------------------------------------------------------


def test_A1_regime_risk_on_threshold_is_60():
    """REGIME_RISK_ON_THRESHOLD = 60.0 (Tier-3 gut-feel calibration; config.py).

    Pinned so a silent recalibration surfaces as a CI failure rather than a
    silent production change.  Changing this requires a config diff + a new
    test-engineer sign-off.
    """
    assert config.REGIME_RISK_ON_THRESHOLD == 60.0


def test_A2_regime_risk_off_threshold_is_40():
    """REGIME_RISK_OFF_THRESHOLD = 40.0 (Tier-3 gut-feel calibration; config.py).

    Same discipline as A1.
    """
    assert config.REGIME_RISK_OFF_THRESHOLD == 40.0


def test_A3_risk_on_threshold_strictly_greater_than_risk_off():
    """Structural sanity: risk_on floor must be > risk_off ceiling.

    If they were equal or inverted the neutral band would be empty or
    the "risk_on" and "risk_off" labels would be co-assigned.
    """
    assert config.REGIME_RISK_ON_THRESHOLD > config.REGIME_RISK_OFF_THRESHOLD


# ---------------------------------------------------------------------------
# Section B — normal regime paths
# ---------------------------------------------------------------------------


def test_B1_all_above_200dma_gives_risk_on():
    """All eligible tickers above 200d SMA → breadth 100% → 'risk_on'."""
    frames = {
        "AAPL": _above(),
        "MSFT": _above(),
        "GOOG": _above(),
    }
    breadth_pct, regime_state = compute_market_regime(frames)
    assert breadth_pct == 100.0
    assert regime_state == "risk_on"


def test_B2_all_below_200dma_gives_risk_off():
    """All eligible tickers below 200d SMA → breadth 0% → 'risk_off'."""
    frames = {
        "AAPL": _below(),
        "MSFT": _below(),
        "GOOG": _below(),
    }
    breadth_pct, regime_state = compute_market_regime(frames)
    assert breadth_pct == 0.0
    assert regime_state == "risk_off"


def test_B3_half_above_half_below_gives_neutral():
    """50% of eligible tickers above 200d SMA → breadth 50% → 'neutral'."""
    frames = {
        "A": _above(),
        "B": _below(),
    }
    breadth_pct, regime_state = compute_market_regime(frames)
    assert breadth_pct == 50.0
    assert regime_state == "neutral"


def test_B4_three_of_four_above_gives_risk_on():
    """3/4 = 75% above → 'risk_on'."""
    frames = {
        "A": _above(),
        "B": _above(),
        "C": _above(),
        "D": _below(),
    }
    breadth_pct, regime_state = compute_market_regime(frames)
    assert breadth_pct == 75.0
    assert regime_state == "risk_on"


def test_B5_one_of_four_above_gives_risk_off():
    """1/4 = 25% above → 'risk_off'."""
    frames = {
        "A": _above(),
        "B": _below(),
        "C": _below(),
        "D": _below(),
    }
    breadth_pct, regime_state = compute_market_regime(frames)
    assert breadth_pct == 25.0
    assert regime_state == "risk_off"


# ---------------------------------------------------------------------------
# Section C — boundary conditions (inclusive edges)
# ---------------------------------------------------------------------------


def test_C1_exactly_60_pct_above_gives_risk_on():
    """Exactly 60% above → breadth == REGIME_RISK_ON_THRESHOLD → 'risk_on' (≥ inclusive).

    3 of 5 tickers above: 3/5 = 60.0%.
    """
    frames = {
        "A": _above(),
        "B": _above(),
        "C": _above(),
        "D": _below(),
        "E": _below(),
    }
    breadth_pct, regime_state = compute_market_regime(frames)
    assert breadth_pct == 60.0
    assert regime_state == "risk_on"


def test_C2_just_below_risk_on_gives_neutral():
    """Just below 60% → 'neutral' (not risk_on).

    2 of 4 = 50% is neutral; we need a value strictly inside the (40, 60) band.
    """
    # 2 of 4 = 50% → neutral
    frames = {
        "A": _above(),
        "B": _above(),
        "C": _below(),
        "D": _below(),
    }
    breadth_pct, regime_state = compute_market_regime(frames)
    assert 40.0 < breadth_pct < 60.0
    assert regime_state == "neutral"


def test_C3_exactly_40_pct_above_gives_risk_off():
    """Exactly 40% above → breadth == REGIME_RISK_OFF_THRESHOLD → 'risk_off' (≤ inclusive).

    2 of 5 tickers above: 2/5 = 40.0%.
    """
    frames = {
        "A": _above(),
        "B": _above(),
        "C": _below(),
        "D": _below(),
        "E": _below(),
    }
    breadth_pct, regime_state = compute_market_regime(frames)
    assert breadth_pct == 40.0
    assert regime_state == "risk_off"


def test_C4_just_above_risk_off_gives_neutral():
    """Just above 40% → 'neutral' (not risk_off).

    Need breadth strictly between 40 and 60.  3 of 6 = 50% works.
    """
    frames = {f"T{i}": (_above() if i < 3 else _below()) for i in range(6)}
    breadth_pct, regime_state = compute_market_regime(frames)
    assert breadth_pct == 50.0
    assert regime_state == "neutral"


# ---------------------------------------------------------------------------
# Section D — short-history exclusion (< 200 bars excluded from denominator)
# ---------------------------------------------------------------------------


def test_D1_short_history_tickers_excluded_from_denominator():
    """Tickers with < 200 bars are excluded from the denominator entirely.

    1 eligible (250 bars, above) + 2 ineligible (100 bars each).
    Denominator = 1, breadth = 100%, regime = 'risk_on'.
    """
    frames = {
        "LONG": _above(250),           # 250 bars — eligible, above
        "SHORT_A": _price_frame(100, latest_above_sma=False),  # only 100 bars
        "SHORT_B": _price_frame(199, latest_above_sma=False),  # 199 bars — still ineligible
    }
    breadth_pct, regime_state = compute_market_regime(frames)
    assert breadth_pct == 100.0
    assert regime_state == "risk_on"


def test_D2_exactly_200_bars_is_eligible():
    """A ticker with EXACTLY 200 bars IS eligible (len(closes) >= 200).

    200 bars, above SMA → contributes to the denominator and the above count.
    """
    # Build a 200-bar frame where the last bar is above the trailing mean
    closes = [100.0] * 200
    closes[-1] = 101.0  # above the 200-bar SMA of 100.0
    df = pd.DataFrame({"Close": closes})
    breadth_pct, regime_state = compute_market_regime({"TST": df})
    assert breadth_pct == 100.0
    assert regime_state == "risk_on"


def test_D3_199_bars_is_ineligible():
    """A ticker with exactly 199 bars is NOT eligible — excluded from denominator."""
    closes = [100.0] * 199
    closes[-1] = 101.0
    df = pd.DataFrame({"Close": closes})
    # No eligible tickers → (None, None)
    breadth_pct, regime_state = compute_market_regime({"TST": df})
    assert breadth_pct is None
    assert regime_state is None


def test_D4_mixed_eligible_and_ineligible_denominator_is_eligible_only():
    """Denominator counts only eligible tickers; short-history tickers are transparent.

    2 eligible (above), 3 short-history (would-be below if counted).
    Expected: breadth = 2/2 = 100%, regime = 'risk_on'.
    """
    frames = {
        "E1": _above(250),
        "E2": _above(300),
        "S1": _price_frame(50, latest_above_sma=False),
        "S2": _price_frame(100, latest_above_sma=False),
        "S3": _price_frame(199, latest_above_sma=False),
    }
    breadth_pct, regime_state = compute_market_regime(frames)
    assert breadth_pct == 100.0
    assert regime_state == "risk_on"


# ---------------------------------------------------------------------------
# Section E — graceful edge cases (no raise)
# ---------------------------------------------------------------------------


def test_E1_empty_dict_returns_none_none():
    """Empty price dict → (None, None), no error."""
    result = compute_market_regime({})
    assert result == (None, None)


def test_E2_all_none_frames_returns_none_none():
    """All None frames → (None, None), no raise."""
    frames = {"AAPL": None, "MSFT": None}
    result = compute_market_regime(frames)
    assert result == (None, None)


def test_E3_all_empty_dataframes_returns_none_none():
    """All empty DataFrames → (None, None), no raise."""
    frames = {
        "AAPL": pd.DataFrame({"Close": []}),
        "MSFT": pd.DataFrame({"Close": []}),
    }
    result = compute_market_regime(frames)
    assert result == (None, None)


def test_E4_all_short_history_returns_none_none():
    """All tickers have < 200 bars → no eligible tickers → (None, None)."""
    frames = {f"T{i}": _price_frame(100, latest_above_sma=True) for i in range(5)}
    result = compute_market_regime(frames)
    assert result == (None, None)


def test_E5_mix_of_none_and_empty_and_no_close_column():
    """Mixed bad frames (None, empty, no recognized close column) → (None, None)."""
    frames = {
        "A": None,
        "B": pd.DataFrame({"Close": []}),
        "C": pd.DataFrame({"Open": [100.0] * 250}),  # no Close column at all
    }
    result = compute_market_regime(frames)
    assert result == (None, None)


def test_E6_return_type_is_tuple():
    """Return type is always a 2-tuple."""
    result = compute_market_regime({})
    assert isinstance(result, tuple)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Section F — Close vs Adj Close column fallback
# ---------------------------------------------------------------------------


def test_F1_uses_close_column_when_present():
    """Primary column 'Close' is used when available."""
    frames = {"TST": _above(250, col="Close")}
    breadth_pct, _ = compute_market_regime(frames)
    assert breadth_pct == 100.0


def test_F2_falls_back_to_adj_close_when_close_absent():
    """'Adj Close' is used when 'Close' column is not present."""
    # Build a frame with only 'Adj Close'
    closes = [100.0] * 250
    closes[-1] = 101.0
    df = pd.DataFrame({"Adj Close": closes})
    breadth_pct, regime_state = compute_market_regime({"TST": df})
    assert breadth_pct == 100.0
    assert regime_state == "risk_on"


def test_F3_close_takes_priority_over_adj_close():
    """When both 'Close' and 'Adj Close' are present, 'Close' is used (priority order).

    We make Close signal above-SMA and Adj Close signal below-SMA to
    confirm the correct column is read.
    """
    # Close: all 100s with last = 101 → above SMA (above)
    # Adj Close: all 100s with last = 99 → below SMA
    df = pd.DataFrame({
        "Close": [100.0] * 249 + [101.0],
        "Adj Close": [100.0] * 249 + [99.0],
    })
    breadth_pct, _ = compute_market_regime({"TST": df})
    # If Close is used: above → 100.0%
    # If Adj Close were used: below → 0.0%
    assert breadth_pct == 100.0


def test_F4_no_recognized_column_ticker_skipped():
    """A frame with neither 'Close' nor 'Adj Close' is silently skipped.

    If the only ticker has no recognized column the result is (None, None).
    """
    df = pd.DataFrame({"Open": [100.0] * 250, "Volume": [1_000_000] * 250})
    result = compute_market_regime({"TST": df})
    assert result == (None, None)


# ---------------------------------------------------------------------------
# Section G — NaN handling
# ---------------------------------------------------------------------------


def test_G1_nan_rows_dropped_and_ticker_still_counted():
    """NaN close values are dropped via dropna; remaining valid rows are used.

    250 rows total, 10 NaN at the start → 240 valid bars (>= 200).
    Latest non-NaN close is above its own SMA → breadth = 100%.
    """
    closes = [float("nan")] * 10 + [100.0] * 239 + [101.0]
    df = pd.DataFrame({"Close": closes})
    breadth_pct, regime_state = compute_market_regime({"TST": df})
    assert breadth_pct == 100.0
    assert regime_state == "risk_on"


def test_G2_all_nan_close_column_treated_as_empty():
    """A frame whose entire Close column is NaN has 0 valid bars after dropna.

    Since len(closes) < 200 → excluded from denominator.
    If it is the only ticker → (None, None).
    """
    df = pd.DataFrame({"Close": [float("nan")] * 250})
    result = compute_market_regime({"TST": df})
    assert result == (None, None)


def test_G3_nan_reduces_effective_bar_count_below_200_excludes_ticker():
    """If NaN removal leaves fewer than 200 valid bars the ticker is excluded.

    Frame has 300 rows but 150 are NaN → 150 valid bars < 200 → ineligible.
    """
    closes = [float("nan")] * 150 + [100.0] * 149 + [101.0]
    df = pd.DataFrame({"Close": closes})
    result = compute_market_regime({"TST": df})
    assert result == (None, None)


# ---------------------------------------------------------------------------
# Section H — Metadata schema round-trip
# ---------------------------------------------------------------------------

_GIT_COMMIT_PLACEHOLDER = "abc12345" + "a" * 32  # 40 hex chars


def _base_metadata_payload() -> dict:
    """Minimal Metadata payload with only the 7 required fields set.

    Pattern follows tests/test_output/test_median_trim_delta_count_schema.py.
    The model accepts any string for ``version`` — no validation against the
    current SCHEMA_VERSION constant — so this fixture does not need updating on
    future schema bumps as long as the 7 required fields stay in the model.
    """
    return {
        "version": "0.10.36-phase8pilot",
        "last_update_utc": "2026-06-25T22:00:00Z",
        "next_update_utc": "2026-07-02T22:00:00Z",
        "universe": "SP1500",
        "universe_size": 1504,
        "compute_run_id": "local",
        "git_commit": _GIT_COMMIT_PLACEHOLDER,
    }


def test_H1_metadata_accepts_both_regime_fields_populated():
    """Metadata.model_validate() with both new Proposal D fields populated parses cleanly."""
    payload = _base_metadata_payload()
    payload["market_breadth_above_200dma_pct"] = 65.5
    payload["market_regime_state"] = "risk_on"
    meta = Metadata.model_validate(payload)
    assert meta.market_breadth_above_200dma_pct == 65.5
    assert meta.market_regime_state == "risk_on"


def test_H2_metadata_both_fields_default_to_none():
    """Both new fields default to None — backward-compat with pre-Proposal-D snapshots."""
    meta = Metadata.model_validate(_base_metadata_payload())
    assert meta.market_breadth_above_200dma_pct is None
    assert meta.market_regime_state is None


def test_H3_metadata_round_trip_model_dump_then_validate():
    """model_dump() → model_validate() round-trip preserves both new fields."""
    payload = _base_metadata_payload()
    payload["market_breadth_above_200dma_pct"] = 38.2
    payload["market_regime_state"] = "risk_off"
    meta_orig = Metadata.model_validate(payload)
    dumped = meta_orig.model_dump()
    meta_rt = Metadata.model_validate(dumped)
    assert meta_rt.market_breadth_above_200dma_pct == 38.2
    assert meta_rt.market_regime_state == "risk_off"


def test_H4_metadata_neutral_regime_state_round_trip():
    """Neutral regime_state survives a dump/validate round-trip."""
    payload = _base_metadata_payload()
    payload["market_breadth_above_200dma_pct"] = 50.0
    payload["market_regime_state"] = "neutral"
    meta = Metadata.model_validate(payload)
    dumped = meta.model_dump()
    meta2 = Metadata.model_validate(dumped)
    assert meta2.market_regime_state == "neutral"
    assert meta2.market_breadth_above_200dma_pct == 50.0


def test_H5_both_fields_appear_in_model_dump_when_none():
    """Both fields appear in model_dump() with None value even when absent from input.

    JSON contract stability: readers must not KeyError on pre-Proposal-D snapshots.
    """
    meta = Metadata.model_validate(_base_metadata_payload())
    dumped = meta.model_dump()
    assert "market_breadth_above_200dma_pct" in dumped
    assert "market_regime_state" in dumped
    assert dumped["market_breadth_above_200dma_pct"] is None
    assert dumped["market_regime_state"] is None
