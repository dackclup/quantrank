"""Cross-sectional normalization for pillar scoring.

Per `SKILL.md` Rule 6: Quality, Value, Growth, Profitability rank within
GICS sector; Risk, Momentum, Technical, Health rank absolutely. Per Rule 7
(missing data): single-metric NaN imputes to sector median; if a pillar
loses ≥50% of its metrics, the caller flags the pillar neutral (50).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

WINSOR_LOW = 0.01
WINSOR_HIGH = 0.99


def _winsorize(series: pd.Series, low: float = WINSOR_LOW, high: float = WINSOR_HIGH) -> pd.Series:
    finite = series[series.apply(lambda x: isinstance(x, int | float) and math.isfinite(x))]
    if finite.empty:
        return series
    lo = finite.quantile(low)
    hi = finite.quantile(high)
    return series.clip(lower=lo, upper=hi)


def _percentile_rank(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """Map a numeric series to 0-100 via percentile rank.

    NaNs propagate (caller decides how to impute). The lowest finite value
    maps near 0, the highest near 100.
    """
    finite_mask = series.apply(lambda x: isinstance(x, int | float) and math.isfinite(x))
    out = pd.Series(np.nan, index=series.index, dtype=float)
    if not finite_mask.any():
        return out
    finite = series[finite_mask]
    ranks = finite.rank(pct=True, method="average") * 100.0
    if not higher_is_better:
        ranks = 100.0 - ranks
    out.loc[finite_mask] = ranks
    return out


def _sector_median_impute(series: pd.Series, sectors: pd.Series) -> pd.Series:
    """Replace NaN entries with their per-sector median. Falls back to the
    cross-sectional median if a sector has no finite values."""
    out = series.copy().astype(float)
    finite_mask = out.apply(lambda x: isinstance(x, int | float) and math.isfinite(x))
    if finite_mask.all():
        return out
    sector_medians = (
        out[finite_mask].groupby(sectors[finite_mask]).median()
    )
    global_median = float(out[finite_mask].median()) if finite_mask.any() else math.nan
    for idx in out.index[~finite_mask]:
        sec = sectors.loc[idx]
        med = sector_medians.get(sec, global_median)
        if isinstance(med, float) and math.isnan(med):
            med = global_median
        out.loc[idx] = med
    return out


def normalize_metric(
    series: pd.Series,
    sectors: pd.Series,
    *,
    sector_relative: bool,
    higher_is_better: bool = True,
    impute_missing: bool = True,
) -> pd.Series:
    """Winsorize + percentile-rank a metric across the universe.

    Parameters
    ----------
    series : per-ticker metric values, indexed by ticker.
    sectors : per-ticker GICS sector, same index.
    sector_relative : if True, rank within each sector; else rank absolutely.
    higher_is_better : invert the rank if the metric is "lower = better".
    impute_missing : if True, fill NaNs with sector median before ranking.
    """
    if series.empty:
        return series

    if impute_missing:
        series = _sector_median_impute(series, sectors)

    series = _winsorize(series)

    if sector_relative:
        out = pd.Series(np.nan, index=series.index, dtype=float)
        for _sector, group_idx in series.groupby(sectors).groups.items():
            group = series.loc[group_idx]
            ranked = _percentile_rank(group, higher_is_better=higher_is_better)
            out.loc[group_idx] = ranked
        return out

    return _percentile_rank(series, higher_is_better=higher_is_better)


def average_pillar_score(
    metric_scores: dict[str, pd.Series],
    *,
    min_coverage: float = 0.5,
) -> pd.Series:
    """Average per-metric 0-100 scores into a pillar 0-100 score.

    For each ticker, count the number of finite metric scores. If coverage
    < `min_coverage`, return NaN (caller decides to neutralize to 50 with a
    flag, per SKILL.md Rule 7).
    """
    if not metric_scores:
        return pd.Series(dtype=float)

    df = pd.DataFrame(metric_scores)
    n_metrics = df.shape[1]
    threshold = max(1, math.ceil(min_coverage * n_metrics))

    coverage = df.notna().sum(axis=1)
    pillar = df.mean(axis=1, skipna=True)
    pillar[coverage < threshold] = np.nan
    return pillar
