"""Risk overlay flags — annotate-only.

Per the user's PR-3b scope decision (2026-05-08): flagged stocks keep their
honest composite score; the veto is enforced one layer up at Top-5 rotation
(``compute.main``) — a flagged stock cannot earn the ``entered_top5`` badge
even if its composite would qualify.

Phase 3 ships **four** vetoes (annotate-only flags surfaced in JSON; the
Top-5 rotation layer in ``compute.main`` is the only place a flag changes
behavior):

- ``altman_distress`` — Altman Z″ < 1.1 (Altman 2003, *Corporate Financial
  Distress and Bankruptcy*, 3rd ed., Wiley)
- ``sloan_accruals_top_decile`` — Sloan accruals = (NI − CFO) / TotalAssets,
  flagged if this stock sits in the cross-sectional top decile (Sloan 1996).
  Issue #7 tracks the over-firing on growers + financials; Phase 4 will
  switch to within-sector / growth-adjusted variants.
- ``net_issuance_top_decile`` — Net Stock Issuance = ln(shares_t /
  shares_{t-12m}), flagged if **within sector** in the top decile
  (Pontiff-Woodgate 2008, *Journal of Finance*). Within-sector framing is
  required because the post-SBC era inflates NSI uniformly across tech but
  much less in mature sectors (mature staples vs. RSU-heavy software).
- ``non_reliance_filing`` — SEC Form 8-K Item 4.02 within trailing 365
  days. Schroeder 2024 SSRN finds ~50% of 4.02 filings precede formal
  restatement. Implemented in :mod:`compute.scoring.eight_k_events`;
  this module just appends the flag when ``check_non_reliance`` fires.

Two additional Tier-2 defenses ship in PR 3d as **annotate-only** flags
that do NOT enter ``risk_flags`` (they live only in
``StockDetail.tier2_events``):

- ``going_concern_disclosure`` — 10-K phrase scan; Mayew-Sethuraman-
  Venkatachalam 2015 *TAR*. See :mod:`compute.scoring.going_concern`.
- ``auditor_change`` — 8-K Item 4.01 within trailing 730 days; Reg S-K
  Item 304. False-positive rate is too high for veto (audit firm
  restructuring fires the same item).

The Beneish M-score flag (``beneish_manipulation``) is documented in
``SKILL.md`` but deferred to Phase 3e — its 8-ratio composite needs prior-
period balance items (sales-receivables variation), which Phase 2 only
persists for the latest fiscal period. PR 3a's ``fetch_fundamentals_history``
provides 5y annual history, so Phase 3e can reach for prior-year values.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from compute import config
from compute.features import health
from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.scoring.eight_k_events import check_non_reliance

ALTMAN_DISTRESS_THRESHOLD = 1.1
SLOAN_TOP_DECILE = 0.90
# Minimum sample size before Sloan accruals deciles are statistically
# meaningful. Below this, we skip the Sloan flag entirely (a 1-ticker
# universe trivially makes that ticker its own 90th percentile).
SLOAN_MIN_POPULATION = 10
# Minimum per-sector population before NSI within-sector decile is
# meaningful. Same rationale as Sloan but applied per-sector. With S&P 500's
# 11 GICS sectors and smallest = Energy n=21, this floor is comfortably
# satisfied in production. Phase 8 (S&P 1500) may break some sub-buckets
# below the floor — those sectors will simply skip the NSI flag.
NSI_MIN_POPULATION = 10


def _altman_distress(snap: FundamentalsSnapshot | None) -> bool:
    if snap is None:
        return False
    z = health.altman_z_double_prime(snap)
    if z is None or (isinstance(z, float) and math.isnan(z)):
        return False
    return float(z) < ALTMAN_DISTRESS_THRESHOLD


def _sloan_accruals(snap: FundamentalsSnapshot | None) -> float:
    """Compute Sloan accruals = (Net Income − Operating Cash Flow) / Total Assets.

    Returns NaN when any input is missing/zero.
    """
    if snap is None:
        return math.nan
    ni = snap.net_income
    cfo = snap.operating_cash_flow
    ta = snap.total_assets
    if ni is None or cfo is None or ta is None:
        return math.nan
    if ta == 0:
        return math.nan
    return (ni - cfo) / ta


def _shares_at_lookback(
    history: pd.DataFrame | None,
    asof_days: int,
    *,
    today: date | None = None,
) -> float | None:
    """Return shares_outstanding from `history` closest to `today − asof_days`.

    `history` is the long-form DataFrame produced by
    ``compute.ingest.fundamentals.fetch_fundamentals_history`` — columns
    include ``metric``, ``value``, ``period_end``. We pick the row with
    ``period_end`` closest to the target date but at least ``asof_days/2``
    days behind today (so we never compare current quarterly to a same-
    quarter-this-year row, which would understate dilution).

    Returns ``None`` when the history can't supply a reliable prior value.
    """
    if history is None or len(history) == 0:
        return None
    if "metric" not in history.columns or "period_end" not in history.columns:
        return None
    sh = history[history["metric"] == "shares_outstanding"]
    if sh.empty:
        return None
    today = today if today is not None else datetime.now(UTC).date()
    target = today - timedelta(days=asof_days)
    cutoff = today - timedelta(days=max(asof_days // 2, 90))
    sh = sh.copy()
    sh["_period_end"] = pd.to_datetime(sh["period_end"]).dt.date
    sh_old = sh[sh["_period_end"] <= cutoff]
    if sh_old.empty:
        return None
    sh_old = sh_old.assign(
        _dist=sh_old["_period_end"].apply(lambda d: abs((d - target).days))
    )
    best = sh_old.sort_values("_dist", kind="mergesort").iloc[0]
    val = best["value"]
    if val is None:
        return None
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v) or v <= 0:
        return None
    return v


def _net_stock_issuance(
    snap: FundamentalsSnapshot | None,
    history: pd.DataFrame | None,
    *,
    today: date | None = None,
) -> float:
    """Compute NSI = ln(shares_t / shares_{t-12m}). NaN when inputs missing.

    Positive NSI = dilution (more shares outstanding now). Top decile of NSI
    (within-sector) is the flag trigger per Pontiff-Woodgate 2008.
    """
    if snap is None or snap.shares_outstanding is None or snap.shares_outstanding <= 0:
        return math.nan
    prior = _shares_at_lookback(history, config.NSI_LOOKBACK_DAYS, today=today)
    if prior is None or prior <= 0:
        return math.nan
    return math.log(float(snap.shares_outstanding) / prior)


def compute_risk_flags(
    snapshots: dict[str, FundamentalsSnapshot | None],
    *,
    histories: dict[str, pd.DataFrame] | None = None,
    sectors: dict[str, str] | None = None,
    today: date | None = None,
    non_reliance_by_ticker: dict[str, bool] | None = None,
) -> dict[str, list[str]]:
    """Compute the risk-flag list per ticker.

    Four flag pathways:

    1. **Altman Z″ < 1.1** — per-ticker, no cross-section.
    2. **Sloan accruals top decile** — cross-sectional 90th percentile across
       the universe (legacy from PR-3b; over-firing tracked in #7).
    3. **NSI top decile within sector** — requires both ``histories`` and
       ``sectors`` to be passed; if either is absent the NSI flag is
       suppressed entirely (rather than degrading to cross-sectional, which
       was the lesson learned from #7's Sloan over-firing on REITs/banks).
    4. **Non-reliance filing (8-K Item 4.02)** — per-ticker. By default
       calls :func:`compute.scoring.eight_k_events.check_non_reliance`
       which hits the on-disk EDGAR cache (or fetches if cache miss).
       ``non_reliance_by_ticker`` overrides this with a pre-computed
       ``{ticker: bool}`` map — Step 5's ``compute/main.py`` wire-up
       passes that map so the EDGAR fetch happens once per ticker
       (shared with ``StockDetail.tier2_events`` display) instead of
       being re-issued here.

    Per-sector NSI thresholds use ``NSI_MIN_POPULATION`` as a floor; sectors
    smaller than that fall through without firing the flag.
    """
    if not snapshots:
        return {}

    # --- Sloan accruals panel (cross-sectional, legacy from PR-3b) ---
    accruals = pd.Series(
        {t: _sloan_accruals(s) for t, s in snapshots.items()}, dtype=float
    )
    finite = accruals.dropna()
    sloan_enabled = len(finite) >= SLOAN_MIN_POPULATION
    sloan_threshold = (
        float(finite.quantile(SLOAN_TOP_DECILE)) if sloan_enabled else math.nan
    )

    # --- NSI panel (per-ticker float; per-sector threshold) ---
    nsi_values: dict[str, float] = {}
    nsi_thresholds_by_sector: dict[str, float] = {}
    if histories is not None:
        nsi_values = {
            t: _net_stock_issuance(snap, histories.get(t), today=today)
            for t, snap in snapshots.items()
        }
        if sectors is not None:
            nsi_series = pd.Series(nsi_values, dtype=float).dropna()
            if not nsi_series.empty:
                sec_for = pd.Series(
                    {t: sectors.get(t) for t in nsi_series.index},
                    dtype=object,
                )
                for sector_name, idx in nsi_series.groupby(sec_for).groups.items():
                    group = nsi_series.loc[idx]
                    if len(group) >= NSI_MIN_POPULATION:
                        nsi_thresholds_by_sector[str(sector_name)] = float(
                            group.quantile(config.NSI_TOP_DECILE)
                        )

    out: dict[str, list[str]] = {}
    for ticker, snap in snapshots.items():
        flags: list[str] = []

        if _altman_distress(snap):
            flags.append("altman_distress")

        accrual_val = accruals.get(ticker)
        if (
            sloan_enabled
            and accrual_val is not None
            and isinstance(accrual_val, float)
            and math.isfinite(accrual_val)
            and accrual_val >= sloan_threshold
        ):
            flags.append("sloan_accruals_top_decile")

        if sectors is not None:
            ticker_sector = sectors.get(ticker)
            threshold = (
                nsi_thresholds_by_sector.get(str(ticker_sector))
                if ticker_sector is not None
                else None
            )
            v = nsi_values.get(ticker, math.nan)
            # Strict-positive guard: NSI ≤ 0 = buybacks/stable shares, never a
            # dilution flag. Necessary even when threshold > 0, because in
            # populations with mostly-zero NSI the linear-interpolation
            # 90th-percentile collapses to 0 (synthetic-stable-shares case in
            # tests) and the >= comparison would fire on all stable tickers.
            if (
                threshold is not None
                and isinstance(v, float)
                and math.isfinite(v)
                and v > 0.0
                and v >= threshold
            ):
                flags.append("net_issuance_top_decile")

        # Defense #9 — 8-K Item 4.02 non-reliance (HARD VETO).
        # Inject path used by Step 5 / tests; default falls through to a
        # per-ticker check_non_reliance call which hits the EDGAR cache.
        if non_reliance_by_ticker is not None:
            non_reliance_fired = bool(non_reliance_by_ticker.get(ticker, False))
        else:
            non_reliance_fired = check_non_reliance(ticker).fired
        if non_reliance_fired:
            flags.append("non_reliance_filing")

        out[ticker] = flags
    return out
