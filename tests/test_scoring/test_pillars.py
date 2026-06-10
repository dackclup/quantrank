"""Unit tests for compute.scoring.pillars.

These tests exercise the full pillar-scoring pipeline on a tiny synthetic
universe so we can assert ordering invariants without relying on real data.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.scoring.pillars import (
    PILLAR_METRIC_DIRECTIONS,
    TickerInputs,
    compute_all_pillars,
)


def _synthetic_prices(seed: int, drift: float = 0.0005, vol: float = 0.01) -> pd.DataFrame:
    """Generate ~520 days of OHLCV with a deterministic random walk."""
    rng = np.random.default_rng(seed)
    n = 520
    rets = rng.normal(drift, vol, size=n)
    close = 100.0 * np.exp(np.cumsum(rets))
    high = close * (1.0 + np.abs(rng.normal(0, 0.003, size=n)))
    low = close * (1.0 - np.abs(rng.normal(0, 0.003, size=n)))
    open_ = close * (1.0 + rng.normal(0, 0.002, size=n))
    volume = rng.integers(1_000_000, 5_000_000, size=n)
    idx = pd.date_range(end=pd.Timestamp("2026-05-01"), periods=n, freq="B")
    return pd.DataFrame(
        {
            "Open": open_,
            "High": high,
            "Low": low,
            "Close": close,
            "Adj Close": close,
            "Volume": volume,
        },
        index=idx,
    )


def _snap(ticker: str, **kwargs) -> FundamentalsSnapshot:
    defaults = {
        "ticker": ticker,
        "cik": f"{hash(ticker) % 10**10:010d}",
        "revenue": 1000.0,
        "net_income": 100.0,
        "gross_profit": 500.0,
        "operating_income": 200.0,
        "total_assets": 2000.0,
        "total_liabilities": 1000.0,
        "stockholders_equity": 1000.0,
        "current_assets": 800.0,
        "current_liabilities": 400.0,
        "long_term_debt": 300.0,
        "operating_cash_flow": 150.0,
        "free_cash_flow": 100.0,
        "capex": 50.0,
        "retained_earnings": 400.0,
        "shares_outstanding": 100.0,
        "eps_basic": 1.0,
        "eps_diluted": 1.0,
        "interest_expense": 10.0,
        "income_before_tax": 110.0,
        "income_tax_expense": 10.0,
        "depreciation_and_amortization": 20.0,
        "ebitda": 220.0,
        "latest_period_end": date(2025, 12, 31),
        "latest_filed_date": date(2026, 2, 14),
    }
    defaults.update(kwargs)
    return FundamentalsSnapshot(**defaults)


def _build_universe(n: int = 12, sectors: tuple[str, ...] = ("tech", "health")) -> dict[str, TickerInputs]:
    """Build a synthetic universe — n tickers across two sectors with a
    monotone quality gradient (later-indexed tickers have higher margins/ROE)."""
    inputs: dict[str, TickerInputs] = {}
    for i in range(n):
        ticker = f"T{i:02d}"
        sector = sectors[i % len(sectors)]
        # Monotone gradient: NI scales with i.
        snap = _snap(
            ticker,
            net_income=10.0 + i * 20.0,
            operating_income=20.0 + i * 30.0,
            gross_profit=200.0 + i * 50.0,
        )
        inputs[ticker] = TickerInputs(
            snapshot=snap,
            prices=_synthetic_prices(seed=i, drift=0.0001 * i),
            benchmark_prices=_synthetic_prices(seed=999),
            current_price=100.0,
            sector=sector,
        )
    return inputs


def test_compute_all_pillars_returns_expected_columns():
    inputs = _build_universe()
    df = compute_all_pillars(inputs)
    expected_pillars = set(PILLAR_METRIC_DIRECTIONS.keys())
    assert set(df.columns) == expected_pillars
    assert len(df) == len(inputs)


def test_pillar_scores_in_0_100_range():
    inputs = _build_universe()
    df = compute_all_pillars(inputs)
    # Growth is NaN here because the synthetic universe doesn't supply
    # multi-year fundamentals history (CAGR inputs). Check bounds only on
    # finite values — NaN means "couldn't compute", not "out of range".
    finite_values = df.values[~pd.isna(df.values)]
    assert ((finite_values >= 0.0) & (finite_values <= 100.0)).all()


def test_quality_pillar_increases_with_margins():
    # The synthetic universe has a monotone quality gradient — higher-indexed
    # tickers should rank higher on the quality pillar within each sector.
    inputs = _build_universe(n=12)
    df = compute_all_pillars(inputs)
    # Per Rule 6, quality is sector-relative. Compare within one sector.
    tech = [t for t in df.index if int(t[1:]) % 2 == 0]  # T00, T02, T04, ...
    quality_tech = df.loc[tech, "quality"].dropna()
    # The last (highest-NI) tech ticker should outrank the first.
    assert quality_tech.iloc[-1] > quality_tech.iloc[0]


def test_compute_all_pillars_empty_input():
    assert compute_all_pillars({}).empty


def test_pillar_score_unaffected_by_individual_ticker_isolation():
    # If we drop a ticker, the remaining pillar scores should still all be
    # in [0, 100] and not produce NaN avalanches.
    inputs = _build_universe(n=12)
    smaller = {k: v for k, v in inputs.items() if k != "T00"}
    df = compute_all_pillars(smaller)
    assert "T00" not in df.index
    finite_values = df.values[~pd.isna(df.values)]
    assert ((finite_values >= 0.0) & (finite_values <= 100.0)).all()


# -- Defense #6 sector exclusions (PR 3c Step 6) ----------------------------

import math  # noqa: E402

from compute.scoring.pillars import (  # noqa: E402
    _profitability_metrics,
    _quality_metrics,
    _value_metrics,
)


def _ticker_input(sector: str, **snap_kwargs) -> TickerInputs:
    """Build a TickerInputs with sector + populated snapshot for sector-gate tests."""
    snap = _snap("TST", **snap_kwargs)
    return TickerInputs(
        snapshot=snap,
        prices=None,
        benchmark_prices=None,
        current_price=100.0,
        sector=sector,
    )


# B. ebit_based_roic exclusion --------------------------------------------------

def test_B1_jpm_financials_roic_returns_nan():
    inp = _ticker_input("Financials")
    metrics = _quality_metrics(inp)
    assert math.isnan(metrics["roic"])


def test_B2_nee_utilities_roic_returns_nan():
    inp = _ticker_input("Utilities")
    metrics = _quality_metrics(inp)
    assert math.isnan(metrics["roic"])


def test_B3_aapl_it_roic_returns_finite_value():
    inp = _ticker_input("Information Technology")
    metrics = _quality_metrics(inp)
    # The synthetic snap has positive operating_income + equity → ROIC computes.
    assert math.isfinite(metrics["roic"])


# C. gross_profitability exclusion (Quality pillar) ---------------------------

def test_C1_jpm_financials_gross_profitability_returns_nan():
    inp = _ticker_input("Financials")
    metrics = _quality_metrics(inp)
    assert math.isnan(metrics["gross_profitability"])


def test_C2_aapl_it_gross_profitability_returns_finite_value():
    inp = _ticker_input("Information Technology")
    metrics = _quality_metrics(inp)
    assert math.isfinite(metrics["gross_profitability"])


# C bis. gross_profitability also gated in the Profitability pillar -----------

def test_C3_jpm_profitability_gross_p_returns_nan():
    """Same metric (Novy-Marx GP/A) appears in BOTH Quality (gross_profitability)
    AND Profitability (gross_p) pillars; both must gate."""
    inp = _ticker_input("Financials")
    metrics = _profitability_metrics(inp)
    assert math.isnan(metrics["gross_p"])


def test_C4_aapl_profitability_gross_p_returns_finite_value():
    inp = _ticker_input("Information Technology")
    metrics = _profitability_metrics(inp)
    assert math.isfinite(metrics["gross_p"])


# D. ev_ebitda_multiple exclusion (Value pillar) ------------------------------

def test_D1_jpm_financials_ev_ebitda_returns_nan():
    inp = _ticker_input("Financials")
    metrics = _value_metrics(inp)
    assert math.isnan(metrics["ev_ebitda"])


def test_D2_aapl_it_ev_ebitda_returns_finite_value():
    inp = _ticker_input("Information Technology")
    metrics = _value_metrics(inp)
    assert math.isfinite(metrics["ev_ebitda"])


def test_D3_utilities_ev_ebitda_NOT_excluded():
    """Per Step 4.1 spec — Utilities have meaningful EBITDA above D&A line.
    The pillar-side ev_ebitda gate should match (Financials only)."""
    inp = _ticker_input("Utilities")
    metrics = _value_metrics(inp)
    assert math.isfinite(metrics["ev_ebitda"])


# E. asset_turnover exclusion (already documented as Financials-only) ---------

def test_E1_jpm_asset_turnover_returns_nan():
    inp = _ticker_input("Financials")
    metrics = _profitability_metrics(inp)
    assert math.isnan(metrics["asset_turnover"])


def test_E2_aapl_asset_turnover_returns_finite_value():
    inp = _ticker_input("Information Technology")
    metrics = _profitability_metrics(inp)
    assert math.isfinite(metrics["asset_turnover"])


# F. Pillar-score robustness when sector-gate fires ---------------------------

def test_F1_jpm_quality_pillar_still_finite_with_some_nans():
    """JPM (Financials) has roic + gross_profitability gated to NaN, but
    roe + msci_q + piotroski (history-dependent) are still in play. The
    pillar averaging should produce a finite score from the non-NaN
    metrics (per SKILL.md Rule 7 / compute.scoring.normalize."""
    inp = _ticker_input("Financials")
    q_metrics = _quality_metrics(inp)
    # Confirm exactly 2 Quality metrics gated to NaN.
    assert math.isnan(q_metrics["roic"])
    assert math.isnan(q_metrics["gross_profitability"])
    # Confirm at least 1 Quality metric is finite (roe — NI/equity).
    assert math.isfinite(q_metrics["roe"])
    # Pillar score will be averaged in compute_all_pillars; tested
    # separately in test_pillar_scores_in_0_100_range above.


def test_F2_full_universe_with_financials_does_not_crash():
    """Smoke test: synthetic universe including a Financials ticker
    completes compute_all_pillars without crashing on NaN propagation."""
    inputs = _build_universe(n=12, sectors=("Financials", "Information Technology"))
    df = compute_all_pillars(inputs)
    # Verify: at least Financials tickers have finite Quality scores
    # (roic + gross_profitability NaN'd, but roe/msci_q + piotroski
    # remain — though piotroski may be NaN without history; Quality
    # pillar should still aggregate from the survivors).
    assert df.shape[0] == len(inputs)
    # No assertion on specific values — too dependent on synthetic gen.
    # The smoke aspect is that the call completes without crashing.


# -- Issue #441: macd_hist regression suite (live 5th technical input) ---------
# The dead isinstance(macd, dict) block always returned NaN (pre-fix). These
# tests pin the four contracts that would have caught the bug.

from compute.scoring.pillars import _technical_metrics  # noqa: E402


def _linear_prices(n: int, slope: float = 0.5, start: float = 10.0) -> pd.DataFrame:
    """Build a deterministic linear OHLCV price series of length *n*.

    A strictly linear close produces a well-defined, sign-stable MACD
    histogram regardless of random seed — essential for the directional test.
    """
    idx = pd.date_range(end=pd.Timestamp("2026-06-10"), periods=n, freq="B")
    close = pd.Series([start + i * slope for i in range(n)], index=idx)
    high = close * 1.005
    low = close * 0.995
    return pd.DataFrame(
        {
            "Open": close,
            "High": high,
            "Low": low,
            "Close": close,
            "Adj Close": close,
            "Volume": pd.Series(1_000_000, index=idx),
        }
    )


def _tech_inp(prices: pd.DataFrame) -> TickerInputs:
    """Minimal TickerInputs wrapping a prices DataFrame."""
    return TickerInputs(
        snapshot=None,
        prices=prices,
        benchmark_prices=None,
        current_price=100.0,
        sector="Information Technology",
    )


# G1 — regression: >=35 bars → macd_hist is FINITE (the test that would
# have caught #441: the old isinstance(macd, dict) block always returned NaN).
def test_G1_macd_hist_finite_with_sufficient_history():
    """>=35 bars of price history yields a finite macd_hist in _technical_metrics.

    Regression guard for issue #441: the dead isinstance-dict block silently
    discarded the float returned by macd_signal; _safe() now wires it directly.
    macd_signal warm-up = slow + signal = 26 + 9 = 35 bars.
    """
    prices = _linear_prices(n=35)
    metrics = _technical_metrics(_tech_inp(prices))
    assert math.isfinite(metrics["macd_hist"]), (
        "macd_hist should be finite when len(prices) >= slow + signal (35). "
        "Got NaN — the isinstance(dict) dead-code regression may have returned."
    )


# G2 — short history → macd_hist is NaN (the imputation path is preserved).
def test_G2_macd_hist_nan_with_insufficient_history():
    """<35 bars → macd_hist is NaN; imputation-to-50 path is preserved.

    macd_signal returns NaN when len(close) < slow + signal (35). _safe()
    converts that to NaN, which the cross-sectional normalizer imputes to 50.
    """
    prices = _linear_prices(n=34)  # one bar below the 26+9 warm-up
    metrics = _technical_metrics(_tech_inp(prices))
    assert math.isnan(metrics["macd_hist"]), (
        "macd_hist should be NaN when len(prices) < slow + signal (35). "
        f"Got {metrics['macd_hist']!r}."
    )


# G3 — macd_hist demonstrably participates in the technical pillar score
# when the input is live (not all-NaN).
def test_G3_technical_pillar_differs_when_macd_hist_is_live():
    """Technical pillar scores differ between live-macd and all-NaN-macd universes.

    Constructs a 10-ticker synthetic universe with >=35 bars per ticker, runs
    compute_all_pillars twice — once normally, once with macd_signal patched to
    always return NaN (simulating the pre-#441-fix state) — and asserts the
    technical pillar column differs.  Proves the 5th input actually participates.
    """
    import compute.features.technical as _tech_module  # noqa: PLC0415

    _MACD_WARM_UP = 100  # well above 35, so every ticker has a finite macd_hist

    inputs: dict[str, TickerInputs] = {
        f"T{i}": _tech_inp(_synthetic_prices(seed=i, drift=0.001 * (i - 5)))
        for i in range(10)
    }

    df_live = compute_all_pillars(inputs)

    # Simulate the pre-fix bug: macd_signal always returns NaN.
    original_macd = _tech_module.macd_signal
    _tech_module.macd_signal = lambda *_a, **_kw: float("nan")
    try:
        df_nanmacd = compute_all_pillars(inputs)
    finally:
        _tech_module.macd_signal = original_macd

    tech_live = df_live["technical"].round(4)
    tech_nan = df_nanmacd["technical"].round(4)

    assert not (tech_live == tech_nan).all(), (
        "Technical pillar scores are identical with and without live macd_hist. "
        "The 5th input is not influencing the pillar — check _safe(technical.macd_signal, p) wiring."
    )


# G4 — directional: uptrending series → positive macd_hist;
# downtrending series → negative macd_hist.
def test_G4_macd_hist_positive_for_uptrend_negative_for_downtrend():
    """Strictly uptrending prices → macd_hist > 0; downtrending → macd_hist < 0.

    Validates that the signal is live and correctly signed: a persistent upward
    trend makes EMA_fast > EMA_slow and grows the MACD line above the signal
    line; a persistent downward trend inverts the relationship.

    Uses a deterministic linear series (no random seed dependency) with 80 bars
    so the warm-up (35) is well exceeded and the trend has time to dominate.
    """
    prices_up = _linear_prices(n=80, slope=+0.5)   # strictly increasing
    prices_down = _linear_prices(n=80, slope=-0.5)  # strictly decreasing

    hist_up = _technical_metrics(_tech_inp(prices_up))["macd_hist"]
    hist_down = _technical_metrics(_tech_inp(prices_down))["macd_hist"]

    assert math.isfinite(hist_up), f"Expected finite macd_hist for uptrend, got {hist_up!r}"
    assert math.isfinite(hist_down), f"Expected finite macd_hist for downtrend, got {hist_down!r}"
    assert hist_up > 0, f"Uptrending series should yield positive macd_hist; got {hist_up}"
    assert hist_down < 0, f"Downtrending series should yield negative macd_hist; got {hist_down}"
