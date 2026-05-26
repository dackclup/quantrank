"""Sanity smoke tests for the fair-price ensemble (Phase 3c Step 8).

This module provides a single sanity check that runs once per weekly
compute and surfaces a number on ``Metadata.mos_trailing_ic_smoke`` so
operators can spot-check whether the fair-price ensemble is producing
*any* signal across the cross-section.

**This is NOT a backtest.** We are not claiming the ensemble predicts
future returns. We are asking: does today's
``StockSummary.margin_of_safety_pct`` have any cross-sectional
relationship to today's trailing 12-month total return? A non-trivial
correlation (positive OR negative) means the ensemble is producing
values with some signal-to-noise vs. historical price moves; a near-zero
correlation says "the fair-price field is essentially uncorrelated with
recent return drift" — informative either way.

We use Spearman rank correlation rather than Pearson because both inputs
have heavy tails:

- ``mos_pct`` has 143 stocks with values outside ``[-99%, +500%]`` (per
  Step 7 verification on commit ``c13e4f7``); a few outliers would
  dominate Pearson.
- 12-month equity returns are similarly heavy-tailed (PLTR / NVDA / TSLA
  spikes vs. mean reversion).

Spearman is rank-based and robust to monotonic transforms, so the result
isn't driven by a handful of extreme tickers.

Implementation note: scipy isn't in the project ``pyproject.toml`` deps,
so we compute Spearman directly as the Pearson correlation of the rank
vectors via ``pd.Series.rank()``. This is mathematically identical to
``scipy.stats.spearmanr`` (without the p-value, which we don't surface).
"""

from __future__ import annotations

import logging
import math

import pandas as pd

from compute.output.schemas import StockSummary

logger = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS: int = 252  # ~1 trading year
MIN_SAMPLE: int = 30  # below this, rank corr is too noisy to trust


def compute_mos_trailing_ic(
    *,
    rankings: list[StockSummary],
    prices_by_ticker: dict[str, pd.DataFrame],
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> float | None:
    """Spearman rank correlation between ``mos_pct`` and trailing return.

    Cross-sectional sanity smoke test. **NOT a backtest.** Returns a
    float in ``[-1, 1]`` when at least :data:`MIN_SAMPLE` valid pairs
    are available; returns ``None`` otherwise.

    Skips per-ticker:
    - ``mos_pct is None`` (fair-price ensemble couldn't aggregate)
    - ``data_quality_input_corruption`` in ``valuation_warnings``
      (Defense #7 fired; ``mos_pct`` is null anyway, but this is an
      explicit guard against future regressions where the warning is
      surfaced even when ``mos_pct`` happens to be set)
    - ``ticker`` missing from ``prices_by_ticker`` or has fewer than
      ``lookback_days`` price rows
    - lookback close ``<= 0`` (defensive — shouldn't happen with real
      yfinance data but cheap to guard)

    Returns ``None`` (rather than a misleading number) when:
    - Fewer than :data:`MIN_SAMPLE` valid pairs after filtering
    - All ``mos_pct`` values identical (rank corr undefined)
    - All trailing returns identical (rank corr undefined)
    - Computed coefficient is non-finite (defensive)
    """
    pairs: list[tuple[float, float]] = []
    for stock in rankings:
        if stock.margin_of_safety_pct is None:
            continue
        # Issue #262 rename (2026-05-26) — check BOTH the legacy
        # ``data_quality_input_corruption`` (still emitted by the
        # writer-parity path in ``compute/main.py`` for the veto cohort
        # AND present on pre-rename legacy snapshots) and the new
        # ``valuation_output_anomalous`` identifier (emitted by
        # ``compute/valuation/ensemble.py`` post-rename). Either flag
        # marks an untrustworthy ``mos_pct`` for the IC smoke test.
        warnings = stock.valuation_warnings or []
        if (
            "data_quality_input_corruption" in warnings
            or "valuation_output_anomalous" in warnings
        ):
            continue
        prices = prices_by_ticker.get(stock.ticker)
        if prices is None or len(prices) < lookback_days:
            continue
        close_col = "Adj Close" if "Adj Close" in prices.columns else "Close"
        if close_col not in prices.columns:
            continue
        trailing_close = float(prices[close_col].iloc[-1])
        lookback_close = float(prices[close_col].iloc[-lookback_days])
        if (
            not math.isfinite(trailing_close)
            or not math.isfinite(lookback_close)
            or lookback_close <= 0
            or trailing_close <= 0
        ):
            continue
        return_1y = trailing_close / lookback_close - 1.0
        pairs.append((float(stock.margin_of_safety_pct), return_1y))

    if len(pairs) < MIN_SAMPLE:
        logger.info(
            "compute_mos_trailing_ic: insufficient sample (%d < %d) — returning None",
            len(pairs),
            MIN_SAMPLE,
        )
        return None

    mos_series = pd.Series([p[0] for p in pairs])
    ret_series = pd.Series([p[1] for p in pairs])

    if mos_series.nunique(dropna=False) < 2:
        return None
    if ret_series.nunique(dropna=False) < 2:
        return None

    # Spearman = Pearson on the ranks. Equivalent to scipy.stats.spearmanr
    # without the p-value.
    coef = mos_series.rank().corr(ret_series.rank())
    if coef is None or not math.isfinite(coef):
        return None
    return float(coef)


__all__ = [
    "DEFAULT_LOOKBACK_DAYS",
    "MIN_SAMPLE",
    "compute_mos_trailing_ic",
]
