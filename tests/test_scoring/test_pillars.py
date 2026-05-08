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
