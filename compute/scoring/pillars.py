"""Pillar score construction.

Each ``compute_*_pillar`` function takes the per-ticker raw inputs, computes
each metric, normalizes via ``compute.scoring.normalize``, and averages the
metric scores into a 0-100 pillar score per ticker.

Direction (higher_is_better) and sector-relativity (per SKILL.md Rule 6) are
encoded in METRIC_SPECS at the top of each pillar.

Phase 3 pillars: quality, value, growth, momentum, health, profitability,
technical, risk. The ``sentiment`` and ``ml`` pillars stay null and their
weight is redistributed in ``compute.scoring.composite``.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from compute.features import (
    growth,
    health,
    momentum,
    profitability,
    quality,
    risk,
    technical,
    value,
)
from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.scoring.normalize import average_pillar_score, normalize_metric
from compute.scoring.sector_rules import is_metric_excluded_for_sector


@dataclass(frozen=True)
class TickerInputs:
    """Per-ticker raw inputs available to pillar scoring."""

    snapshot: FundamentalsSnapshot | None
    prices: pd.DataFrame | None
    benchmark_prices: pd.DataFrame | None
    current_price: float
    sector: str
    history: pd.DataFrame | None = None


def _safe(fn, *args, **kwargs) -> float:
    """Call a feature function and return float('nan') on any failure."""
    try:
        v = fn(*args, **kwargs)
    except Exception:  # noqa: BLE001
        return math.nan
    if v is None:
        return math.nan
    if isinstance(v, int | float) and not math.isfinite(float(v)):
        return math.nan
    return float(v)


def _quality_metrics(inp: TickerInputs) -> dict[str, float]:
    s = inp.snapshot
    if s is None:
        return {k: math.nan for k in ("roe", "roic", "gross_profitability", "msci_q", "piotroski")}
    metrics = {
        "roe": _safe(quality.return_on_equity, s),
        "roic": _safe(quality.return_on_invested_capital, s),
        "gross_profitability": _safe(quality.gross_profitability, s),
        "msci_q": _safe(quality.msci_3descriptor, s),
        "piotroski": _safe(quality.piotroski_f_score, s),
    }
    # Defense #6: sector exclusions for EBIT-based ROIC and gross
    # profitability (Greenblatt 2005 + Novy-Marx 2013 sector caveats).
    if is_metric_excluded_for_sector(metric="ebit_based_roic", sector=inp.sector):
        metrics["roic"] = math.nan
    if is_metric_excluded_for_sector(metric="gross_profitability", sector=inp.sector):
        metrics["gross_profitability"] = math.nan
    return metrics


def _value_metrics(inp: TickerInputs) -> dict[str, float]:
    s = inp.snapshot
    if s is None:
        return {k: math.nan for k in ("pe", "pb", "ps", "ev_ebitda", "ev_fcf", "earnings_yield")}
    metrics = {
        # P/E, P/B, P/S, EV/EBITDA, EV/FCF: lower is better → caller passes higher_is_better=False
        "pe": _safe(value.pe_ratio, s, inp.current_price),
        "pb": _safe(value.pb_ratio, s, inp.current_price),
        "ps": _safe(value.ps_ratio, s, inp.current_price),
        "ev_ebitda": _safe(value.ev_to_ebitda, s, inp.current_price),
        "ev_fcf": _safe(value.ev_to_fcf, s, inp.current_price),
        "earnings_yield": _safe(value.earnings_yield_greenblatt, s, inp.current_price),
    }
    # Defense #6: EV/EBITDA pillar metric mirrors the fair-price-side
    # sector exclusion for Financials (no meaningful EBITDA for banks).
    if is_metric_excluded_for_sector(metric="ev_ebitda_multiple", sector=inp.sector):
        metrics["ev_ebitda"] = math.nan
    return metrics


def _growth_metrics(inp: TickerInputs) -> dict[str, float]:
    s = inp.snapshot
    return {
        "revenue_cagr_3y": _safe(growth.revenue_cagr_3y, inp.history),
        "eps_cagr_3y": _safe(growth.eps_cagr_3y, inp.history),
        "fcf_cagr_3y": _safe(growth.fcf_cagr_3y, inp.history),
        "sgr": _safe(growth.sustainable_growth_rate, s) if s is not None else math.nan,
    }


def _momentum_metrics(inp: TickerInputs) -> dict[str, float]:
    p = inp.prices
    return {
        "mom_12_1": _safe(momentum.momentum_12_1, p),
        "mom_6_1": _safe(momentum.momentum_6_1, p),
        "mom_3_1": _safe(momentum.momentum_3_1, p),
        "dist_52w_high": _safe(momentum.distance_from_52w_high, p),
    }


def _health_metrics(inp: TickerInputs) -> dict[str, float]:
    s = inp.snapshot
    if s is None:
        return {k: math.nan for k in ("current", "quick", "d_e", "ic", "altman_z")}
    return {
        "current": _safe(health.current_ratio, s),
        "quick": _safe(health.quick_ratio, s),
        # debt_to_equity: lower is better → invert direction at normalization
        "d_e": _safe(health.debt_to_equity, s),
        "ic": _safe(health.interest_coverage, s),
        "altman_z": _safe(health.altman_z_double_prime, s),
    }


def _profitability_metrics(inp: TickerInputs) -> dict[str, float]:
    s = inp.snapshot
    if s is None:
        return {k: math.nan for k in ("gm", "om", "nm", "roa", "asset_turnover", "gross_p")}
    metrics = {
        "gm": _safe(profitability.gross_margin, s),
        "om": _safe(profitability.operating_margin, s),
        "nm": _safe(profitability.net_margin, s),
        "roa": _safe(profitability.return_on_assets, s),
        "asset_turnover": _safe(profitability.asset_turnover, s),
        "gross_p": _safe(profitability.gross_profitability, s),
    }
    # Defense #6: asset_turnover (revenue/total_assets) and gross
    # profitability are meaningless for Financials (their "assets" are
    # loans + securities, not productive capital). The asset_turnover
    # docstring already claimed this exclusion; this wires the actual gate.
    if is_metric_excluded_for_sector(metric="asset_turnover", sector=inp.sector):
        metrics["asset_turnover"] = math.nan
    if is_metric_excluded_for_sector(metric="gross_profitability", sector=inp.sector):
        metrics["gross_p"] = math.nan
    return metrics


def _technical_metrics(inp: TickerInputs) -> dict[str, float]:
    p = inp.prices
    if p is None or p.empty:
        return {k: math.nan for k in ("rsi_dist50", "macd_hist", "adx", "bb_pctb", "mfi")}
    rsi_val = _safe(technical.rsi, p)
    # RSI: closeness to 50 is "balanced"; we score |RSI - 50| inverted as a
    # proxy for absence of extreme conditions. Higher score = more balanced.
    rsi_score = math.nan if math.isnan(rsi_val) else 50.0 - abs(rsi_val - 50.0)
    return {
        "rsi_dist50": rsi_score,
        "macd_hist": _safe(technical.macd_signal, p),
        "adx": _safe(technical.adx, p),
        "bb_pctb": _safe(technical.bollinger_pct_b, p),
        "mfi": _safe(technical.mfi, p),
    }


def _risk_metrics(inp: TickerInputs) -> dict[str, float]:
    p = inp.prices
    bench = inp.benchmark_prices
    if p is None or p.empty:
        return {k: math.nan for k in ("vol", "sharpe", "sortino", "calmar", "max_dd", "beta")}
    return {
        "vol": _safe(risk.vol_252, p),
        "sharpe": _safe(risk.sharpe, p),
        "sortino": _safe(risk.sortino, p),
        "calmar": _safe(risk.calmar, p),
        # max_drawdown returns a negative number; less negative is better.
        "max_dd": _safe(risk.max_drawdown, p),
        "beta": _safe(risk.beta, p, bench) if bench is not None else math.nan,
    }


# (sector_relative, higher_is_better) per metric, per pillar.
PILLAR_METRIC_DIRECTIONS: dict[str, dict[str, tuple[bool, bool]]] = {
    "quality": {
        "roe": (True, True),
        "roic": (True, True),
        "gross_profitability": (True, True),
        "msci_q": (True, True),
        "piotroski": (True, True),
    },
    "value": {
        "pe": (True, False),
        "pb": (True, False),
        "ps": (True, False),
        "ev_ebitda": (True, False),
        "ev_fcf": (True, False),
        "earnings_yield": (True, True),
    },
    "growth": {
        "revenue_cagr_3y": (True, True),
        "eps_cagr_3y": (True, True),
        "fcf_cagr_3y": (True, True),
        "sgr": (True, True),
    },
    "momentum": {
        "mom_12_1": (False, True),
        "mom_6_1": (False, True),
        "mom_3_1": (False, True),
        # distance_from_52w_high is negative or zero; closer to zero is better
        # → higher (less negative) is better.
        "dist_52w_high": (False, True),
    },
    "health": {
        "current": (False, True),
        "quick": (False, True),
        "d_e": (False, False),
        "ic": (False, True),
        "altman_z": (False, True),
    },
    "profitability": {
        "gm": (True, True),
        "om": (True, True),
        "nm": (True, True),
        "roa": (True, True),
        "asset_turnover": (True, True),
        "gross_p": (True, True),
    },
    "technical": {
        "rsi_dist50": (False, True),
        "macd_hist": (False, True),
        "adx": (False, True),
        "bb_pctb": (False, True),
        "mfi": (False, True),
    },
    "risk": {
        "vol": (False, False),
        "sharpe": (False, True),
        "sortino": (False, True),
        "calmar": (False, True),
        "max_dd": (False, True),
        "beta": (False, False),
    },
}

# Map pillar → metric extractor.
_PILLAR_EXTRACTORS = {
    "quality": _quality_metrics,
    "value": _value_metrics,
    "growth": _growth_metrics,
    "momentum": _momentum_metrics,
    "health": _health_metrics,
    "profitability": _profitability_metrics,
    "technical": _technical_metrics,
    "risk": _risk_metrics,
}


def compute_all_pillars(inputs: Mapping[str, TickerInputs]) -> pd.DataFrame:
    """Compute all 8 active pillar scores cross-sectionally.

    Returns a DataFrame indexed by ticker with one column per pillar. Pillars
    with insufficient coverage per ticker show NaN; the caller (composite)
    neutralizes them to 50 and records the imputation.
    """
    if not inputs:
        return pd.DataFrame()

    tickers = list(inputs.keys())
    sectors = pd.Series({t: inputs[t].sector for t in tickers})

    out_cols: dict[str, pd.Series] = {}
    for pillar, extractor in _PILLAR_EXTRACTORS.items():
        # Build per-metric panel for this pillar.
        per_metric: dict[str, pd.Series] = {}
        directions = PILLAR_METRIC_DIRECTIONS[pillar]
        # Compute raw metric values per ticker.
        raw: dict[str, dict[str, float]] = {t: extractor(inputs[t]) for t in tickers}
        metric_names = list(directions.keys())
        for metric in metric_names:
            values = pd.Series({t: raw[t].get(metric, math.nan) for t in tickers}, dtype=float)
            sec_rel, higher_is_better = directions[metric]
            normalized = normalize_metric(
                values,
                sectors,
                sector_relative=sec_rel,
                higher_is_better=higher_is_better,
                impute_missing=True,
            )
            per_metric[metric] = normalized
        pillar_score = average_pillar_score(per_metric)
        out_cols[pillar] = pillar_score

    return pd.DataFrame(out_cols)
