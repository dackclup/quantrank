"""Risk overlay flags — annotate-only.

Per the user's PR-3b scope decision (2026-05-08): flagged stocks keep their
honest composite score; the veto is enforced one layer up at Top-5 rotation
(``compute.main``) — a flagged stock cannot earn the ``entered_top5`` badge
even if its composite would qualify.

Phase 3 + Phase 4 issue-#18 fix ships **five** active vetoes (annotate-only
flags surfaced in JSON; the Top-5 rotation layer in ``compute.main`` is the
only place a flag changes behavior):

- ``altman_distress`` — Altman Z″ < 1.1 (Altman 2003, *Corporate Financial
  Distress and Bankruptcy*, 3rd ed., Wiley)
- ``sloan_accruals_top_decile`` — Sloan accruals = (NI − CFO) / TotalAssets,
  flagged if this stock sits in the **within-sector** top decile when
  ``sectors`` is supplied (PR 4.5a.1, closes issue #7 — Sloan economics
  differ by sector, so Financials + REITs over-fire on cross-sectional
  decile). Falls back to cross-sectional top decile when ``sectors`` is
  not supplied. Original threshold rubric: Sloan 1996 *TAR*.
- ``net_issuance_top_decile`` — Net Stock Issuance = ln(shares_t /
  shares_{t-12m}), flagged if **within sector** in the top decile
  (Pontiff-Woodgate 2008, *Journal of Finance*). Within-sector framing is
  required because the post-SBC era inflates NSI uniformly across tech but
  much less in mature sectors (mature staples vs. RSU-heavy software).
- ``non_reliance_filing`` — SEC Form 8-K Item 4.02 within trailing 365
  days. Schroeder 2024 SSRN finds ~50% of 4.02 filings precede formal
  restatement. Implemented in :mod:`compute.scoring.eight_k_events`;
  this module just appends the flag when ``check_non_reliance`` fires.
  Currently deferred behind the ``_EIGHT_K_DEFENSES_ENABLED`` feature
  flag in :mod:`compute.scoring.tier2`; re-enabled in Phase 4 per issue #14.
- ``data_quality_input_corruption`` — fundamentals ingest corruption (e.g.,
  ``shares_outstanding`` ingested in the wrong unit, surfaced as TBVPS >
  ``FAIR_PRICE_DATA_QUALITY_CEILING`` of $10K/share). The fair-price
  ensemble already nulls all 6 methods + emits this name in
  ``valuation_warnings`` when its post-hoc ceiling guard fires; this module
  detects the same corruption upstream from snapshot inputs alone so the
  Top-5 rotation skip catches the ticker without depending on the
  ensemble pass. Promoted to veto per issue #18 (FP rate 8/502 ≈ 1.6%,
  acceptable for veto). Top issue: SPG ranked #1 in Run #15 despite
  market_cap $1.62M (real ~$76B) — only suppressed from effective Top-5
  by coincidental Sloan co-firing. Now suppressed explicitly.

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
from compute.scoring.beneish import BENEISH_VETO_THRESHOLD
from compute.scoring.eight_k_events import check_non_reliance
from compute.valuation.tangible_book import tangible_book_value_per_share

ALTMAN_DISTRESS_THRESHOLD = 1.1
SLOAN_TOP_DECILE = 0.90
# Minimum cross-sectional sample size before Sloan accruals deciles are
# statistically meaningful. Below this, we skip the Sloan flag entirely
# (a 1-ticker universe trivially makes that ticker its own 90th
# percentile). Used as the fallback floor when ``sectors`` is not
# supplied — production always supplies sectors so the per-sector path
# (``SLOAN_MIN_POPULATION_SECTOR``) is the active threshold for the
# S&P 500 universe.
SLOAN_MIN_POPULATION = 10
# Minimum per-sector population before within-sector Sloan decile is
# meaningful (PR 4.5a.1, closes issue #7). Sloan accrual economics
# differ structurally by sector — Financials and REITs report higher
# accruals from non-cash items (D&A, loan-loss provisions, fair-value
# adjustments) that aren't earnings manipulation. Cross-sectional
# top-decile over-fires on those sectors; within-sector top-decile
# compares each ticker to its own sector peers and removes that bias.
# With S&P 500's 11 GICS sectors and smallest = Energy n=21, this
# floor is comfortably satisfied. Sectors below the floor fall back
# to cross-sectional Sloan (or skip if total population also < 10).
SLOAN_MIN_POPULATION_SECTOR = 15
# Minimum per-sector population before NSI within-sector decile is
# meaningful. Same rationale as Sloan but applied per-sector. With S&P 500's
# 11 GICS sectors and smallest = Energy n=21, this floor is comfortably
# satisfied in production. Phase 8 (S&P 1500) may break some sub-buckets
# below the floor — those sectors will simply skip the NSI flag.
NSI_MIN_POPULATION = 10


# Audit #5 (2026-05-14, pre-v1.0 stop-the-line) found three additional
# patterns of silent input corruption that escape the TBVPS ceiling:
#
#   A. REIT-style revenue subset — `RevenueFromContractWithCustomerExcludingAssessedTax`
#      tagged with just non-rental contract revenue ($7M for AVB) while the
#      actual total (`Revenues`) is in the billions. Fixed at the ingest
#      layer via `_try_ttm_max_fresh`, but defense-in-depth here catches
#      any residual.
#   B. Bank-only `RevenueFromContract...` — banks like HBAN file only the
#      contract-revenue subset (no `Revenues` total tag). Net income then
#      legitimately exceeds the partial-revenue figure. Veto rather than
#      ship a Top-5 ranking against a 50% partial-revenue input.
#   C. NVDA-style stale-concept TTM — fixed upstream; this is the
#      catch-all in case a new filer hits the same pattern.
#
# Threshold rationale: any S&P 500 company has revenue ≥ $200M (smallest
# constituent in 2026); below $50M is several orders of magnitude wrong
# and almost certainly a tag-pick bug rather than a real micro-cap.
_MIN_PLAUSIBLE_TTM_REVENUE: float = 50_000_000.0


def _data_quality_input_corruption(snap: FundamentalsSnapshot | None) -> bool:
    """True iff snapshot inputs look corrupted by any of the patterns the
    audit identified.

    Patterns:
    1. TBVPS > FAIR_PRICE_DATA_QUALITY_CEILING — shares_outstanding bug
       (e.g., PSKY=1000 shares, BKR=100 shares — issue #10).
    2. TTM revenue < $50M — for an S&P 500 company this is impossible;
       indicates the wrong XBRL concept was picked (e.g., a contract-
       revenue subset or a stale historical FY).
    3. |TTM net_income| > |TTM revenue| — accounting identity says NI
       cannot exceed revenue except in rare one-time gain scenarios; the
       common cause is a partial-revenue tag with full NI (banks that
       only file `RevenueFromContractWithCustomerExcludingAssessedTax`).

    All three patterns null the entire fair-price ensemble AND suppress
    Top-5 entry — these tickers' composite scores remain visible (for
    transparency) but they can't appear in the curated top tier with
    inputs the screener can't trust.
    """
    if snap is None:
        return False
    # Pattern 1 — shares_outstanding bug surfaces as TBVPS ceiling break.
    tbvps = tangible_book_value_per_share(snap)
    if tbvps is not None and tbvps > config.FAIR_PRICE_DATA_QUALITY_CEILING:
        return True
    # Pattern 2 — implausibly small revenue (XBRL tag mis-pick).
    if (
        snap.revenue is not None
        and 0 < snap.revenue < _MIN_PLAUSIBLE_TTM_REVENUE
    ):
        return True
    # Pattern 3 — net income exceeds revenue (partial-revenue tag bug).
    if (
        snap.revenue is not None
        and snap.net_income is not None
        and snap.revenue > 0
        and abs(snap.net_income) > abs(snap.revenue)
    ):
        return True
    return False


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
    beneish_m_scores: dict[str, float | None] | None = None,
) -> dict[str, list[str]]:
    """Compute the risk-flag list per ticker.

    Five flag pathways:

    1. **Data-quality input corruption** — TBVPS > $10K/share. Snapshot-
       only signal, mirrors the ensemble's post-hoc ceiling guard. Veto
       per issue #18 (was annotate-only before).
    2. **Altman Z″ < 1.1** — per-ticker, no cross-section.
    3. **Sloan accruals top decile** — cross-sectional 90th percentile across
       the universe (legacy from PR-3b; over-firing tracked in #7).
    4. **NSI top decile within sector** — requires both ``histories`` and
       ``sectors`` to be passed; if either is absent the NSI flag is
       suppressed entirely (rather than degrading to cross-sectional, which
       was the lesson learned from #7's Sloan over-firing on REITs/banks).
    5. **Non-reliance filing (8-K Item 4.02)** — per-ticker. By default
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

    # --- Sloan accruals panel ---
    #
    # PR 4.5a.1 (issue #7) — switched from cross-sectional to within-sector
    # top decile when ``sectors`` is supplied. Cross-sectional path stays
    # as a fallback for callers that don't pass sectors (tests + future
    # external integrations). Per-sector thresholds activate when
    # len(sector_group) >= SLOAN_MIN_POPULATION_SECTOR; sectors below the
    # floor fall back to the cross-sectional threshold for those tickers
    # (or skip entirely when the total cross-sectional population also
    # fails the SLOAN_MIN_POPULATION gate).
    accruals = pd.Series(
        {t: _sloan_accruals(s) for t, s in snapshots.items()}, dtype=float
    )
    finite = accruals.dropna()
    sloan_cross_sectional_enabled = len(finite) >= SLOAN_MIN_POPULATION
    sloan_cross_sectional_threshold = (
        float(finite.quantile(SLOAN_TOP_DECILE))
        if sloan_cross_sectional_enabled
        else math.nan
    )
    sloan_thresholds_by_sector: dict[str, float] = {}
    if sectors is not None and not finite.empty:
        sec_for_sloan = pd.Series(
            {t: sectors.get(t) for t in finite.index},
            dtype=object,
        )
        for sector_name, idx in finite.groupby(sec_for_sloan).groups.items():
            group = finite.loc[idx]
            if len(group) >= SLOAN_MIN_POPULATION_SECTOR:
                sloan_thresholds_by_sector[str(sector_name)] = float(
                    group.quantile(SLOAN_TOP_DECILE)
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

        # Issue #18: data-quality corruption is a veto, not a soft warning.
        # Emit first so a corrupted snapshot never relies on a coincidental
        # co-firing of altman/sloan/NSI to be suppressed from Top-5.
        if _data_quality_input_corruption(snap):
            flags.append("data_quality_input_corruption")

        if _altman_distress(snap):
            flags.append("altman_distress")

        accrual_val = accruals.get(ticker)
        if (
            accrual_val is not None
            and isinstance(accrual_val, float)
            and math.isfinite(accrual_val)
        ):
            # Prefer the per-sector threshold (PR 4.5a.1). Fall back to
            # the cross-sectional threshold when the ticker's sector
            # didn't reach SLOAN_MIN_POPULATION_SECTOR or when sectors
            # weren't supplied at all.
            ticker_sector = (
                sectors.get(ticker) if sectors is not None else None
            )
            sector_threshold = (
                sloan_thresholds_by_sector.get(str(ticker_sector))
                if ticker_sector is not None
                else None
            )
            sloan_threshold_for_ticker: float | None = None
            if sector_threshold is not None:
                sloan_threshold_for_ticker = sector_threshold
            elif sloan_cross_sectional_enabled:
                sloan_threshold_for_ticker = sloan_cross_sectional_threshold
            if (
                sloan_threshold_for_ticker is not None
                and accrual_val >= sloan_threshold_for_ticker
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

        # PR 4.5a.2 — Beneish manipulation soft-veto (HARD VETO at the
        # stricter ``BENEISH_VETO_THRESHOLD = -1.78``). Original
        # ``beneish_high`` annotate at M > -2.22 still emits separately
        # in ``compute/main.py`` per-ticker loop; this is the active-
        # veto path that suppresses ``entered_top5``. Inject pattern
        # mirrors ``non_reliance_by_ticker``.
        if beneish_m_scores is not None:
            m = beneish_m_scores.get(ticker)
            if m is not None and math.isfinite(float(m)) and float(m) > BENEISH_VETO_THRESHOLD:
                flags.append("beneish_manipulation_veto")

        out[ticker] = flags
    return out
