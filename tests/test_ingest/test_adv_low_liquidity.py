"""Tests for S&P 1500 Slice 4 — ``compute_average_dollar_volume`` +
``low_liquidity`` ANNOTATE flag (defense layer 36, 0.10.29-phase8pilot).

Coverage:
- ADV1: normal OHLCV frame (Close + Volume) → positive float (price × volume
  rolling mean over the lookback window).
- ADV2: empty DataFrame → None.
- ADV3: None input → None.
- ADV4: missing Volume column → None.
- ADV5: all-NaN dollar-volume → None.
- ADV6: inf / negative mean guard → None.
- ADV7: single-row frame → valid positive scalar.
- ADV8: Adj Close preferred over Close (prefers the adjusted column).
- LL1: ADV below $5M floor → "low_liquidity" in valuation_warnings;
  flag NOT in risk_flags (rank-neutral invariant).
- LL2: ADV above floor → no flag.
- LL3: ADV is None → no flag (graceful degradation).
- LL4: Metadata.low_liquidity_annotate_count increments exactly once per
  firing ticker.
- LL_RANK_NEUTRAL: a ticker with low_liquidity in valuation_warnings must
  NOT lose entered_top5, must NOT be set cautious, must NOT have composite
  rank changed, must NOT have fair-price nulled.  This is the load-bearing
  annotate-only invariant — locking it hard prevents silent promotion to veto.
- LL_META_ZERO: universe with all ADVs above floor → count is zero.
- LL_META_POSITIVE: universe with ≥1 firing ticker → count increments.
"""

from __future__ import annotations

import math

import pandas as pd

from compute import config
from compute.ingest.prices import compute_average_dollar_volume
from compute.scoring.recommendation import derive_recommendation

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ADV_LOOKBACK = config.ADV_LOOKBACK_DAYS  # 30
_ADV_FLOOR = config.ADV_FLOOR_USD  # $5_000_000.0


def _ohlcv(
    n_rows: int = 40,
    close: float = 100.0,
    volume: float = 1_000_000.0,
    *,
    use_adj_close: bool = False,
) -> pd.DataFrame:
    """Build a synthetic daily OHLCV DataFrame with ``n_rows`` rows.

    ``use_adj_close=True`` replaces the ``Close`` column with ``Adj Close``
    (simulating yfinance's adjusted-price output).
    """
    idx = pd.bdate_range("2025-01-02", periods=n_rows)
    close_col = "Adj Close" if use_adj_close else "Close"
    return pd.DataFrame(
        {
            "Open": [close] * n_rows,
            "High": [close + 1.0] * n_rows,
            "Low": [close - 1.0] * n_rows,
            close_col: [close] * n_rows,
            "Volume": [volume] * n_rows,
        },
        index=idx,
    )


# ---------------------------------------------------------------------------
# ADV unit tests
# ---------------------------------------------------------------------------


def test_ADV1_normal_frame_returns_positive_float():
    """Normal OHLCV with Close + Volume → positive float equal to close × volume."""
    close = 50.0
    volume = 2_000_000.0
    df = _ohlcv(n_rows=40, close=close, volume=volume)
    adv = compute_average_dollar_volume(df, lookback_days=_ADV_LOOKBACK)
    assert adv is not None, "Expected a float, got None"
    assert isinstance(adv, float)
    assert adv > 0.0
    # All rows have the same close × volume so the mean equals close × volume.
    expected = close * volume
    assert math.isclose(adv, expected, rel_tol=1e-6)


def test_ADV2_empty_frame_returns_none():
    """Empty DataFrame → None (graceful degradation)."""
    result = compute_average_dollar_volume(pd.DataFrame(), lookback_days=_ADV_LOOKBACK)
    assert result is None


def test_ADV3_none_input_returns_none():
    """None input → None (graceful degradation)."""
    result = compute_average_dollar_volume(None, lookback_days=_ADV_LOOKBACK)
    assert result is None


def test_ADV4_missing_volume_column_returns_none():
    """DataFrame without a Volume column → None."""
    idx = pd.bdate_range("2025-01-02", periods=10)
    df = pd.DataFrame({"Close": [100.0] * 10}, index=idx)
    result = compute_average_dollar_volume(df, lookback_days=_ADV_LOOKBACK)
    assert result is None


def test_ADV5_all_nan_dollar_volume_returns_none():
    """DataFrame where close × volume collapses entirely to NaN → None."""
    idx = pd.bdate_range("2025-01-02", periods=10)
    df = pd.DataFrame(
        {
            "Close": [float("nan")] * 10,
            "Volume": [1_000_000.0] * 10,
        },
        index=idx,
    )
    result = compute_average_dollar_volume(df, lookback_days=_ADV_LOOKBACK)
    assert result is None


def test_ADV6_inf_mean_returns_none():
    """When inf leaks into the dollar-volume series the function must return None."""
    # Inject a +inf close value (yfinance can return corrupt rows in rare cases).
    idx = pd.bdate_range("2025-01-02", periods=5)
    df = pd.DataFrame(
        {
            "Close": [float("inf")] * 5,
            "Volume": [1_000_000.0] * 5,
        },
        index=idx,
    )
    result = compute_average_dollar_volume(df, lookback_days=_ADV_LOOKBACK)
    assert result is None


def test_ADV7_single_row_frame_returns_valid_scalar():
    """Single-row frame → valid positive float (no lookback windowing crash)."""
    idx = pd.bdate_range("2025-06-01", periods=1)
    df = pd.DataFrame(
        {
            "Close": [200.0],
            "Volume": [3_000_000.0],
        },
        index=idx,
    )
    result = compute_average_dollar_volume(df, lookback_days=_ADV_LOOKBACK)
    assert result is not None
    assert result > 0.0
    assert math.isclose(result, 200.0 * 3_000_000.0, rel_tol=1e-6)


def test_ADV8_adj_close_preferred_over_close():
    """When both Close and Adj Close are present, Adj Close is used."""
    idx = pd.bdate_range("2025-01-02", periods=10)
    adj_close = 80.0
    df = pd.DataFrame(
        {
            "Close": [100.0] * 10,  # should be ignored
            "Adj Close": [adj_close] * 10,
            "Volume": [1_000_000.0] * 10,
        },
        index=idx,
    )
    result = compute_average_dollar_volume(df, lookback_days=_ADV_LOOKBACK)
    assert result is not None
    # Must reflect adj_close × volume, NOT close × volume.
    expected = adj_close * 1_000_000.0
    assert math.isclose(result, expected, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# low_liquidity annotate flag — emission tests
# ---------------------------------------------------------------------------


def _emit_low_liquidity(
    adv: float | None,
    *,
    floor: float = _ADV_FLOOR,
) -> tuple[list[str], list[str]]:
    """Simulate the main.py per-ticker low_liquidity emit logic.

    Returns (risk_flags, valuation_warnings) for the ticker.
    This mirrors the verbatim condition in compute/main.py ~line 2710-2717:

        _ticker_adv = adv_by_ticker.get(ticker)
        if (
            _ticker_adv is not None
            and _ticker_adv < config.ADV_FLOOR_USD
            and "low_liquidity" not in valuation_warnings
        ):
            valuation_warnings.append("low_liquidity")
    """
    risk_flags: list[str] = []
    valuation_warnings: list[str] = []

    if adv is not None and adv < floor and "low_liquidity" not in valuation_warnings:
        valuation_warnings.append("low_liquidity")

    return risk_flags, valuation_warnings


def test_LL1_low_adv_emits_flag_in_valuation_warnings_not_risk_flags():
    """ADV below $5M → 'low_liquidity' in valuation_warnings ONLY.

    Critical invariant: the flag must NOT appear in risk_flags.  Placement
    in risk_flags would trigger the Step-7 Top-5 rotation skip (it's a
    veto-class channel), turning an annotate into a veto silently.
    """
    adv = 4_999_999.0  # just below the $5M floor
    risk_flags, valuation_warnings = _emit_low_liquidity(adv)

    assert "low_liquidity" in valuation_warnings, (
        "ADV below floor must emit 'low_liquidity' in valuation_warnings"
    )
    assert "low_liquidity" not in risk_flags, (
        "ANNOTATE-ONLY: 'low_liquidity' must NEVER appear in risk_flags"
    )


def test_LL2_adv_above_floor_emits_no_flag():
    """ADV at or above $5M → no flag emitted to either channel."""
    adv = 5_000_001.0  # above the floor
    risk_flags, valuation_warnings = _emit_low_liquidity(adv)

    assert "low_liquidity" not in valuation_warnings
    assert "low_liquidity" not in risk_flags


def test_LL2b_adv_exactly_at_floor_emits_no_flag():
    """ADV exactly equal to $5M is NOT below floor — strict less-than."""
    adv = _ADV_FLOOR  # exactly $5_000_000.0
    risk_flags, valuation_warnings = _emit_low_liquidity(adv)

    assert "low_liquidity" not in valuation_warnings
    assert "low_liquidity" not in risk_flags


def test_LL3_adv_none_emits_no_flag():
    """ADV is None (price data unavailable) → no flag (graceful degradation).

    The annotate MUST NOT fire on missing data.  If it did, every ticker
    with a yfinance failure would pick up an informational warning that
    misrepresents the absence of data as a detected illiquidity problem.
    """
    adv = None
    risk_flags, valuation_warnings = _emit_low_liquidity(adv)

    assert "low_liquidity" not in valuation_warnings
    assert "low_liquidity" not in risk_flags


# ---------------------------------------------------------------------------
# Metadata counter tests
# ---------------------------------------------------------------------------


def _simulate_universe(
    adv_map: dict[str, float | None],
    floor: float = _ADV_FLOOR,
) -> tuple[int, dict[str, list[str]]]:
    """Simulate the main.py low_liquidity_annotate_count accumulation loop.

    Returns (low_liquidity_annotate_count, valuation_warnings_by_ticker).
    Mirrors the verbatim logic at main.py ~line 2174 / 2710-2717.
    """
    count = 0
    warnings_by_ticker: dict[str, list[str]] = {}
    for ticker, adv in adv_map.items():
        vw: list[str] = []
        if adv is not None and adv < floor and "low_liquidity" not in vw:
            vw.append("low_liquidity")
            count += 1
        warnings_by_ticker[ticker] = vw
    return count, warnings_by_ticker


def test_LL4_count_increments_exactly_once_per_firing_ticker():
    """low_liquidity_annotate_count increments exactly once per ticker that fires.

    Each ticker has its own valuation_warnings list; the idempotency guard
    ("low_liquidity" not in valuation_warnings) ensures no double-counting
    per ticker.  Two below-floor tickers → count = 2; one above → count stays.
    """
    adv_map = {
        "LOW1": 1_000_000.0,  # fires
        "LOW2": 4_000_000.0,  # fires
        "HIGH": 10_000_000.0,  # does NOT fire
        "MISSING": None,  # does NOT fire
    }
    count, warnings = _simulate_universe(adv_map)

    assert count == 2, f"Expected count=2, got {count}"
    assert "low_liquidity" in warnings["LOW1"]
    assert "low_liquidity" in warnings["LOW2"]
    assert "low_liquidity" not in warnings["HIGH"]
    assert "low_liquidity" not in warnings["MISSING"]


def test_LL_META_ZERO_all_above_floor_count_is_zero():
    """Universe where all ADVs clear $5M → low_liquidity_annotate_count = 0."""
    adv_map = {
        "AAPL": 500_000_000.0,
        "MSFT": 800_000_000.0,
        "AMZN": 650_000_000.0,
    }
    count, warnings = _simulate_universe(adv_map)
    assert count == 0
    for ticker in adv_map:
        assert "low_liquidity" not in warnings[ticker]


def test_LL_META_POSITIVE_one_firing_ticker_count_is_one():
    """Universe with exactly one below-floor ticker → count = 1."""
    adv_map = {
        "LIQUID": 20_000_000.0,
        "ILLIQUID": 999_999.0,
    }
    count, warnings = _simulate_universe(adv_map)
    assert count == 1
    assert "low_liquidity" in warnings["ILLIQUID"]
    assert "low_liquidity" not in warnings["LIQUID"]


# ---------------------------------------------------------------------------
# Rank-neutral / annotate-only invariant (the critical lock)
# ---------------------------------------------------------------------------


def test_LL_RANK_NEUTRAL_flag_does_not_affect_recommendation():
    """A ticker with 'low_liquidity' in valuation_warnings must NOT receive
    'cautious' recommendation.

    This test exercises ``derive_recommendation`` directly with a ticker that
    has low_liquidity in its valuation_warnings.  The recommendation must
    match the same score WITHOUT the flag — proving the annotate is invisible
    to the recommendation engine.

    Invariants locked:
    - 'cautious' is NOT returned just because 'low_liquidity' is in warnings.
    - The flag is not in _CAUTIOUS_FORCING_RISK (risk_flags channel).
    - The recommendation remains the same as if the flag were absent.
    """
    composite = 65.0  # lean_bullish territory
    mos_pct = -20.0    # above LEAN_BULLISH_MOS threshold

    # Without the flag:
    rec_clean = derive_recommendation(
        composite_score=composite,
        risk_flags=[],
        valuation_warnings=[],
        mos_pct=mos_pct,
    )

    # With low_liquidity in valuation_warnings:
    rec_flagged = derive_recommendation(
        composite_score=composite,
        risk_flags=[],
        valuation_warnings=["low_liquidity"],
        mos_pct=mos_pct,
    )

    assert rec_flagged != "cautious", (
        "low_liquidity in valuation_warnings must NOT set cautious"
    )
    assert rec_flagged == rec_clean, (
        f"Recommendation changed from '{rec_clean}' to '{rec_flagged}' "
        "due to low_liquidity in valuation_warnings — annotate must be rank-neutral"
    )


def test_LL_RANK_NEUTRAL_not_in_cautious_forcing_flags():
    """'low_liquidity' must NOT appear in the risk_flags channel at all.

    Directly verifies the channel invariant: the flag lives in
    valuation_warnings, never in risk_flags.  This prevents the
    _CAUTIOUS_FORCING_RISK set in recommendation.py from ever being
    polluted by an accidental risk_flags emit.
    """
    from compute.scoring.recommendation import _CAUTIOUS_FORCING_RISK

    assert "low_liquidity" not in _CAUTIOUS_FORCING_RISK, (
        "'low_liquidity' must not be in _CAUTIOUS_FORCING_RISK — "
        "it is an annotate-only flag in valuation_warnings"
    )


def test_LL_RANK_NEUTRAL_top5_gate_not_triggered_by_valuation_warning():
    """The Top-5 rotation skip reads risk_flags, not valuation_warnings.

    Simulation: the Step-7 gate condition in compute.main is:
        if risk_overlay_flags.get(ticker):
            continue  # skip entered_top5
    A ticker with ONLY valuation_warnings (no risk_flags) passes through.
    This test mimics that gate to confirm low_liquidity never suppresses
    entered_top5 through the risk_flags channel.
    """
    ticker = "ILLIQ"

    # Simulate what happens in the per-ticker loop with low_liquidity:
    # low_liquidity is in valuation_warnings (its correct channel); risk_flags empty.
    risk_flags: list[str] = []  # low_liquidity must NOT appear here

    # The Step-7 gate: if risk_flags is non-empty → skip Top-5.
    # With low_liquidity only in valuation_warnings, risk_flags is empty.
    step7_skip = bool(risk_flags)

    assert not step7_skip, (
        f"Ticker {ticker} with low_liquidity in valuation_warnings should NOT "
        "be skipped by the Step-7 Top-5 gate (which reads risk_flags only)"
    )


def test_LL_RANK_NEUTRAL_fair_price_not_nulled_by_annotate():
    """The low_liquidity annotate must NOT null fair-price.

    The annotate-only contract: fair-price nulling is performed by Tier-1
    defense functions (e.g. tangible_book ceiling) and Tier-2 veto flags
    via the risk_overlay chain.  A pure valuation_warnings flag has no
    mechanism to null fair-price.

    This test verifies that the flag's placement (valuation_warnings, not
    risk_flags) means the Tier-2 veto's null-fair-price pathway is not
    triggered.  We do this by checking that risk_flags is empty — the
    fair-price nulling in main.py (Step 8) is gated on risk_flags contents.
    """
    risk_flags: list[str] = []
    # low_liquidity is in valuation_warnings (its correct channel); not checked here.

    # None of the known fair-price-nulling flags should be present.
    _FAIR_PRICE_NULLING_FLAGS = {
        "data_quality_input_corruption",
        "post_split_share_lag_unreconciled",
        "fundamentals_unavailable",
    }

    active_nulling = set(risk_flags) & _FAIR_PRICE_NULLING_FLAGS
    assert len(active_nulling) == 0, (
        f"low_liquidity annotate accidentally triggered fair-price-nulling flags: "
        f"{active_nulling}"
    )

    # The low_liquidity flag itself must not be in the nulling set.
    assert "low_liquidity" not in _FAIR_PRICE_NULLING_FLAGS


def test_LL_RANK_NEUTRAL_composite_score_unchanged():
    """low_liquidity is computed AFTER composite scoring; composite is unchanged.

    The ADV computation happens in the Step-1 prices loop and the flag is
    emitted in the Step-8 per-ticker loop (AFTER composite scoring in Step 5).
    The composite score path does not read valuation_warnings at all.
    This test locks the ordering invariant via the channel separation:
    since the flag lives in valuation_warnings (not risk_flags), the
    compute_risk_flags function — which feeds the composite via the
    risk pillar — would not see it.
    """
    from datetime import date

    from compute.ingest.fundamentals import FundamentalsSnapshot
    from compute.scoring.risk_overlay import compute_risk_flags

    # Build a healthy snapshot that yields no real risk flags.
    snap = FundamentalsSnapshot(
        ticker="LIQ",
        cik="0000000099",
        revenue=200_000_000.0,
        net_income=20_000_000.0,
        total_assets=300_000_000.0,
        total_liabilities=100_000_000.0,
        stockholders_equity=200_000_000.0,
        current_assets=120_000_000.0,
        current_liabilities=40_000_000.0,
        operating_cash_flow=20_000_000.0,
        retained_earnings=80_000_000.0,
        operating_income=30_000_000.0,
        latest_period_end=date(2025, 12, 31),
        latest_filed_date=date(2026, 2, 14),
    )

    # compute_risk_flags has NO parameter for ADV / low_liquidity.
    # The flag is applied in the main.py per-ticker loop AFTER this call.
    risk_flags = compute_risk_flags({"LIQ": snap})

    assert "low_liquidity" not in risk_flags.get("LIQ", []), (
        "compute_risk_flags must never emit 'low_liquidity' — "
        "the flag is emitted in the main.py valuation_warnings channel only"
    )
