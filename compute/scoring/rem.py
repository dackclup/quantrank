"""Real Earnings Management (REM) detection — Phase 4.5c.

Roychowdhury 2006 *JAE* "Earnings management through real activities
manipulation" — three abnormal proxies per ticker, each modelled
against sector-relative cross-sectional baselines:

1. **Abnormal CFO**: residual from regressing
   ``CFO_t / Assets_{t-1}`` on
   ``[1, 1/Assets_{t-1}, Sales_t/Assets_{t-1}, ΔSales_t/Assets_{t-1}]``.
   **Low (negative) abnormal CFO** = suspicious — firm front-loaded
   sales via channel stuffing / loose credit terms / price discounts
   to inflate current-period CFO, leaving abnormally low residual
   relative to its sales level.
2. **Abnormal Production**: residual from regressing
   ``(COGS_t + ΔInventory_t) / Assets_{t-1}`` on
   ``[1, 1/Assets_{t-1}, Sales_t/Assets_{t-1}, ΔSales_t/Assets_{t-1},
   ΔSales_{t-1}/Assets_{t-1}]``.
   **High abnormal production** = suspicious — overproduction
   spreads fixed costs over more units, reducing per-unit COGS and
   inflating reported gross margin.
3. **Abnormal Discretionary Expenses**: residual from regressing
   ``(R&D_t + SGA_t) / Assets_{t-1}`` on
   ``[1, 1/Assets_{t-1}, Sales_{t-1}/Assets_{t-1}]``.
   **Low (negative) abnormal DISEXP** = suspicious — firm cut
   discretionary spending (R&D, advertising, maintenance) to boost
   current-period earnings.

The flag ``rem_suspect`` fires when **2 of 3** abnormal proxies sit
in the "worst" decile within the ticker's GICS sector:
- bottom decile for abnormal CFO
- top decile for abnormal production
- bottom decile for abnormal DISEXP

ANNOTATE-only (mirrors PR 4.5b's restatement_history posture).
Catches REAL manipulation (cutting R&D, channel stuffing, deferring
maintenance) — invisible to Sloan / Beneish / Dechow which target
accrual manipulation.

Implementation notes
--------------------

- **Annual data** (not quarterly per Roychowdhury 2006's preferred
  spec) — QuantRank's free-tier XBRL pull is annual only via
  ``compute/ingest/fundamentals.py``. Per PR #86 plan §4.5c, this is
  an acceptable simplification; the model still identifies extreme
  residuals correctly.
- **DISEXP simplification**: Roychowdhury 2006's DISEXP =
  R&D + SGA + Advertising. SEC XBRL exposes R&D and SGA separately
  but Advertising is rarely tagged — it's usually subsumed in SGA.
  We use ``R&D + SGA`` (which captures advertising as a SGA subset);
  this is the standard practitioner adaptation.
- **Per-sector regression** with ``REM_MIN_POPULATION_SECTOR = 15``
  floor (same threshold as 4.5a.1 Sloan sector-relative). Sectors
  below the floor skip REM (callers see ``fired=False``).
- **No new dependencies** — OLS via ``numpy.linalg.lstsq``.

References
----------

- Roychowdhury, S. (2006). "Earnings management through real
  activities manipulation." *Journal of Accounting and Economics*
  42(3), 335-370.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final

import numpy as np
import pandas as pd

from compute.ingest.fundamentals import FundamentalsSnapshot

logger = logging.getLogger(__name__)


# Top/bottom decile cutoff per Roychowdhury 2006 Table 6 "high REM"
# classification.
REM_DECILE: Final[float] = 0.10
# Minimum per-sector population before within-sector decile is
# meaningful. Same floor as 4.5a.1 (Sloan sector-relative). Smallest
# S&P 500 sector = Energy n=21 → comfortably above 15.
REM_MIN_POPULATION_SECTOR: Final[int] = 15


@dataclass(frozen=True)
class REMProxies:
    """Per-ticker REM input vector.

    Each ratio is normalised by ``Assets_{t-1}``. All fields finite
    when the proxy was constructible. Missing any required input
    (e.g., no inventory tag for a service firm) returns
    ``REMProxies(None, ...)`` for the affected ratio; the per-sector
    regression then drops that ticker from the fit AND skips its
    residual computation.
    """

    # Dependent variables (left-hand side of each regression)
    cfo_over_assets: float | None
    """``CFO_t / Assets_{t-1}``"""
    prod_over_assets: float | None
    """``(COGS_t + ΔInventory_t) / Assets_{t-1}``"""
    disexp_over_assets: float | None
    """``(R&D_t + SGA_t) / Assets_{t-1}``"""

    # Independent variables (right-hand side, shared across all 3 models)
    inv_assets: float | None
    """``1 / Assets_{t-1}`` — intercept scale factor"""
    sales_over_assets: float | None
    """``Sales_t / Assets_{t-1}``"""
    dsales_over_assets: float | None
    """``ΔSales_t / Assets_{t-1}`` = (Sales_t − Sales_{t-1}) / A_{t-1}"""
    dsales_lag_over_assets: float | None
    """``ΔSales_{t-1} / Assets_{t-1}`` (for PROD model only)"""
    sales_lag_over_assets: float | None
    """``Sales_{t-1} / Assets_{t-1}`` (for DISEXP model only)"""


@dataclass(frozen=True)
class REMResult:
    """Per-ticker REM output.

    All three residuals are None when the ticker was excluded from
    the sector fit (e.g., missing inputs OR sector below
    ``REM_MIN_POPULATION_SECTOR``). ``fired`` is True when ≥2 of the
    3 residuals sit in their respective "worst" decile within sector.
    """

    abnormal_cfo: float | None
    abnormal_prod: float | None
    abnormal_disexp: float | None
    fired: bool
    triggers: tuple[str, ...]
    """Names of the abnormal proxies that sit in worst decile (subset
    of {"cfo", "prod", "disexp"})."""


# ---------------------------------------------------------------------------
# Per-ticker proxy construction
# ---------------------------------------------------------------------------


def _prior_year_value(
    history: pd.DataFrame | None,
    metric: str,
    snap_period_end: date | None,
    *,
    years_back: int = 1,
) -> float | None:
    """Return annual value for ``metric`` ~``years_back`` years before
    ``snap_period_end``. Mirrors the lookback shape used in Beneish
    and Dechow.

    Picks the row whose ``period_end`` is closest to
    ``snap_period_end - years_back * 365d`` AND at least 180 days
    behind ``snap_period_end`` (so we never compare a same-period
    annual against the snapshot's TTM).
    """
    if history is None or len(history) == 0:
        return None
    if snap_period_end is None:
        return None
    if "metric" not in history.columns or "period_end" not in history.columns:
        return None
    rows = history[history["metric"] == metric]
    if rows.empty:
        return None
    rows = rows.copy()
    rows["_period_end"] = pd.to_datetime(rows["period_end"]).dt.date
    target = snap_period_end - timedelta(days=365 * years_back)
    cutoff = snap_period_end - timedelta(days=180)
    candidates = rows[rows["_period_end"] <= cutoff]
    if candidates.empty:
        return None
    candidates = candidates.assign(
        _dist=candidates["_period_end"].apply(lambda d: abs((d - target).days))
    )
    best = candidates.sort_values("_dist", kind="mergesort").iloc[0]
    val = best["value"]
    if val is None:
        return None
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return v


def compute_proxies(
    snap: FundamentalsSnapshot | None,
    history: pd.DataFrame | None,
) -> REMProxies:
    """Build the per-ticker REM input vector from snapshot + history.

    Missing inputs → corresponding field is None; the regression
    layer drops such tickers from the fit AND skips residual
    computation.
    """
    none = REMProxies(
        cfo_over_assets=None,
        prod_over_assets=None,
        disexp_over_assets=None,
        inv_assets=None,
        sales_over_assets=None,
        dsales_over_assets=None,
        dsales_lag_over_assets=None,
        sales_lag_over_assets=None,
    )
    if snap is None:
        return none
    period = snap.latest_period_end
    if period is None:
        return none

    prior_assets = _prior_year_value(history, "total_assets", period)
    prior_sales = _prior_year_value(history, "revenue", period)
    prior_lag_sales = _prior_year_value(
        history, "revenue", period, years_back=2
    )
    prior_inv = _prior_year_value(history, "inventory", period)

    # Assets_{t-1} is the denominator everywhere — without it no proxy.
    if prior_assets is None or prior_assets <= 0:
        return none

    inv_a = 1.0 / prior_assets

    sales_a: float | None = None
    if snap.revenue is not None and math.isfinite(snap.revenue):
        sales_a = float(snap.revenue) / prior_assets

    dsales_a: float | None = None
    if sales_a is not None and prior_sales is not None and prior_sales > 0:
        dsales_a = (float(snap.revenue) - prior_sales) / prior_assets

    dsales_lag_a: float | None = None
    if (
        prior_sales is not None
        and prior_lag_sales is not None
        and prior_lag_sales > 0
    ):
        dsales_lag_a = (prior_sales - prior_lag_sales) / prior_assets

    sales_lag_a: float | None = None
    if prior_sales is not None and prior_sales > 0:
        sales_lag_a = prior_sales / prior_assets

    # CFO model
    cfo_a: float | None = None
    if (
        snap.operating_cash_flow is not None
        and math.isfinite(snap.operating_cash_flow)
    ):
        cfo_a = float(snap.operating_cash_flow) / prior_assets

    # Production model — needs COGS + ΔInventory.
    prod_a: float | None = None
    if (
        snap.cost_of_revenue is not None
        and math.isfinite(snap.cost_of_revenue)
        and snap.inventory is not None
        and math.isfinite(snap.inventory)
        and prior_inv is not None
    ):
        d_inv = float(snap.inventory) - prior_inv
        prod_a = (float(snap.cost_of_revenue) + d_inv) / prior_assets

    # DISEXP model — R&D + SGA. Roychowdhury 2006 adds Advertising but
    # SEC XBRL rarely tags it separately (usually subsumed in SGA).
    disexp_a: float | None = None
    rnd = snap.research_and_development
    sga = snap.sga_expense
    if rnd is not None and math.isfinite(rnd) and sga is not None and math.isfinite(sga):
        disexp_a = (float(rnd) + float(sga)) / prior_assets
    elif sga is not None and math.isfinite(sga):
        # R&D missing (financials, REITs, utilities) — use SGA alone.
        # Per Roychowdhury 2006 footnote 7: when one component is
        # missing, use the available one rather than dropping the
        # observation; the regression's intercept absorbs the level
        # difference within sector.
        disexp_a = float(sga) / prior_assets

    return REMProxies(
        cfo_over_assets=cfo_a,
        prod_over_assets=prod_a,
        disexp_over_assets=disexp_a,
        inv_assets=inv_a,
        sales_over_assets=sales_a,
        dsales_over_assets=dsales_a,
        dsales_lag_over_assets=dsales_lag_a,
        sales_lag_over_assets=sales_lag_a,
    )


# ---------------------------------------------------------------------------
# Per-sector regression
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _SectorModel:
    """Sector-fit coefficients for the 3 REM regressions.

    Each coefficient vector is the OLS solution. Layout (column order):
      - cfo:    [α, β_inv_assets, β_sales, β_dsales]
      - prod:   [α, β_inv_assets, β_sales, β_dsales, β_dsales_lag]
      - disexp: [α, β_inv_assets, β_sales_lag]

    The intercept α is included as the first coefficient (regression
    matrix has a column of 1s prepended).
    """

    cfo_coefs: np.ndarray | None
    prod_coefs: np.ndarray | None
    disexp_coefs: np.ndarray | None
    n_cfo: int
    n_prod: int
    n_disexp: int


def _fit_one_model(
    y_list: list[float],
    x_cols_list: list[list[float]],
) -> np.ndarray | None:
    """OLS fit. Returns coefficient vector or None when underdetermined."""
    n = len(y_list)
    if n < REM_MIN_POPULATION_SECTOR:
        return None
    y = np.asarray(y_list, dtype=float)
    x = np.asarray(x_cols_list, dtype=float)
    # Prepend intercept column
    x_with_intercept = np.column_stack([np.ones(n), x])
    if x_with_intercept.shape[0] <= x_with_intercept.shape[1]:
        # Underdetermined (more params than observations)
        return None
    try:
        coefs, *_ = np.linalg.lstsq(x_with_intercept, y, rcond=None)
    except np.linalg.LinAlgError as e:
        logger.warning("REM OLS fit failed: %s", e)
        return None
    return coefs


def _fit_sector_models(
    proxies_by_ticker: dict[str, REMProxies],
    sectors: dict[str, str],
) -> dict[str, _SectorModel]:
    """Build per-sector regression coefficients for the 3 REM models."""
    by_sector: dict[str, list[tuple[str, REMProxies]]] = {}
    for ticker, p in proxies_by_ticker.items():
        sec = sectors.get(ticker)
        if sec is None:
            continue
        by_sector.setdefault(sec, []).append((ticker, p))

    out: dict[str, _SectorModel] = {}
    for sec, items in by_sector.items():
        # CFO model: y=cfo_over_assets, X=[inv_assets, sales, dsales]
        cfo_y: list[float] = []
        cfo_x: list[list[float]] = []
        for _, p in items:
            if (
                p.cfo_over_assets is not None
                and p.inv_assets is not None
                and p.sales_over_assets is not None
                and p.dsales_over_assets is not None
            ):
                cfo_y.append(p.cfo_over_assets)
                cfo_x.append(
                    [
                        p.inv_assets,
                        p.sales_over_assets,
                        p.dsales_over_assets,
                    ]
                )
        cfo_coefs = _fit_one_model(cfo_y, cfo_x)

        # PROD model: y=prod_over_assets, X=[inv_assets, sales, dsales, dsales_lag]
        prod_y: list[float] = []
        prod_x: list[list[float]] = []
        for _, p in items:
            if (
                p.prod_over_assets is not None
                and p.inv_assets is not None
                and p.sales_over_assets is not None
                and p.dsales_over_assets is not None
                and p.dsales_lag_over_assets is not None
            ):
                prod_y.append(p.prod_over_assets)
                prod_x.append(
                    [
                        p.inv_assets,
                        p.sales_over_assets,
                        p.dsales_over_assets,
                        p.dsales_lag_over_assets,
                    ]
                )
        prod_coefs = _fit_one_model(prod_y, prod_x)

        # DISEXP model: y=disexp_over_assets, X=[inv_assets, sales_lag]
        disexp_y: list[float] = []
        disexp_x: list[list[float]] = []
        for _, p in items:
            if (
                p.disexp_over_assets is not None
                and p.inv_assets is not None
                and p.sales_lag_over_assets is not None
            ):
                disexp_y.append(p.disexp_over_assets)
                disexp_x.append([p.inv_assets, p.sales_lag_over_assets])
        disexp_coefs = _fit_one_model(disexp_y, disexp_x)

        out[sec] = _SectorModel(
            cfo_coefs=cfo_coefs,
            prod_coefs=prod_coefs,
            disexp_coefs=disexp_coefs,
            n_cfo=len(cfo_y),
            n_prod=len(prod_y),
            n_disexp=len(disexp_y),
        )
    return out


def _residual(
    actual: float | None,
    inputs: list[float | None],
    coefs: np.ndarray | None,
) -> float | None:
    """Compute residual = actual − predicted from the fitted model."""
    if actual is None or coefs is None:
        return None
    if any(v is None for v in inputs):
        return None
    x = np.array([1.0] + [float(v) for v in inputs], dtype=float)
    if x.shape[0] != coefs.shape[0]:
        return None
    predicted = float(np.dot(coefs, x))
    return actual - predicted


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def compute_rem_flags(
    snapshots: dict[str, FundamentalsSnapshot | None],
    *,
    histories: dict[str, pd.DataFrame] | None = None,
    sectors: dict[str, str] | None = None,
) -> dict[str, REMResult]:
    """Compute the REM result per ticker.

    Two-pass:
      1. Build all per-ticker proxies + fit per-sector regression models
      2. Compute residuals + within-sector decile rank + fire flag

    Returns a dict keyed by ticker; tickers excluded from the fit
    (missing inputs or sector below floor) get
    ``REMResult(None, None, None, fired=False, triggers=())``.
    """
    if not snapshots:
        return {}
    if histories is None:
        histories = {}
    if sectors is None:
        sectors = {}

    # Pass 1 — proxies
    proxies: dict[str, REMProxies] = {}
    for ticker, snap in snapshots.items():
        proxies[ticker] = compute_proxies(snap, histories.get(ticker))

    # Pass 1.5 — per-sector models
    sector_models = _fit_sector_models(proxies, sectors)

    # Pass 2 — residuals + within-sector decile rank
    cfo_residuals: dict[str, float] = {}
    prod_residuals: dict[str, float] = {}
    disexp_residuals: dict[str, float] = {}
    for ticker, p in proxies.items():
        sec = sectors.get(ticker)
        if sec is None or sec not in sector_models:
            continue
        model = sector_models[sec]
        cfo_r = _residual(
            p.cfo_over_assets,
            [p.inv_assets, p.sales_over_assets, p.dsales_over_assets],
            model.cfo_coefs,
        )
        if cfo_r is not None:
            cfo_residuals[ticker] = cfo_r
        prod_r = _residual(
            p.prod_over_assets,
            [
                p.inv_assets,
                p.sales_over_assets,
                p.dsales_over_assets,
                p.dsales_lag_over_assets,
            ],
            model.prod_coefs,
        )
        if prod_r is not None:
            prod_residuals[ticker] = prod_r
        disexp_r = _residual(
            p.disexp_over_assets,
            [p.inv_assets, p.sales_lag_over_assets],
            model.disexp_coefs,
        )
        if disexp_r is not None:
            disexp_residuals[ticker] = disexp_r

    # Per-sector decile thresholds
    cfo_low_by_sector = _within_sector_decile(
        cfo_residuals, sectors, REM_DECILE
    )
    prod_high_by_sector = _within_sector_decile(
        prod_residuals, sectors, 1.0 - REM_DECILE
    )
    disexp_low_by_sector = _within_sector_decile(
        disexp_residuals, sectors, REM_DECILE
    )

    # Assemble per-ticker results
    out: dict[str, REMResult] = {}
    for ticker in snapshots:
        sec = sectors.get(ticker)
        cfo_r = cfo_residuals.get(ticker)
        prod_r = prod_residuals.get(ticker)
        disexp_r = disexp_residuals.get(ticker)
        triggers: list[str] = []
        if (
            cfo_r is not None
            and sec is not None
            and sec in cfo_low_by_sector
            and cfo_r <= cfo_low_by_sector[sec]
        ):
            triggers.append("cfo")
        if (
            prod_r is not None
            and sec is not None
            and sec in prod_high_by_sector
            and prod_r >= prod_high_by_sector[sec]
        ):
            triggers.append("prod")
        if (
            disexp_r is not None
            and sec is not None
            and sec in disexp_low_by_sector
            and disexp_r <= disexp_low_by_sector[sec]
        ):
            triggers.append("disexp")
        out[ticker] = REMResult(
            abnormal_cfo=cfo_r,
            abnormal_prod=prod_r,
            abnormal_disexp=disexp_r,
            fired=len(triggers) >= 2,
            triggers=tuple(triggers),
        )
    return out


def _within_sector_decile(
    residuals: dict[str, float],
    sectors: dict[str, str],
    quantile: float,
) -> dict[str, float]:
    """Per-sector quantile threshold dict. Sectors with population
    below ``REM_MIN_POPULATION_SECTOR`` are excluded — those tickers
    won't fire even if their residual would otherwise qualify.
    """
    if not residuals:
        return {}
    series = pd.Series(residuals, dtype=float).dropna()
    if series.empty:
        return {}
    sec_for = pd.Series(
        {t: sectors.get(t) for t in series.index},
        dtype=object,
    )
    out: dict[str, float] = {}
    for sector_name, idx in series.groupby(sec_for).groups.items():
        group = series.loc[idx]
        if len(group) >= REM_MIN_POPULATION_SECTOR:
            out[str(sector_name)] = float(group.quantile(quantile))
    return out


__all__ = [
    "REM_DECILE",
    "REM_MIN_POPULATION_SECTOR",
    "REMProxies",
    "REMResult",
    "compute_proxies",
    "compute_rem_flags",
]
