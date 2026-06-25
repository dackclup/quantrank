"""Market-regime diagnostic — WRITE-ONLY / OBSERVABILITY-ONLY (Rule 18).

Proposal D (2026-06-25) — 2nd slice of the legendary-fund deep-research
6-proposal program.  Methodology-scientist verdict: **RATIFY-SHADOW,
concur with rejection-as-tilt**.

REJECTION RATIONALE — no read path, ever
-----------------------------------------
The financial-engineer REJECTED market-regime state as a basket / scoring
tilt because it would smuggle market-timing into a cross-sectional engine.

Academic anchor: **Welch and Goyal 2008** "A Comprehensive Look at the
Empirical Performance of Equity Premium Prediction", *Review of Financial
Studies* 21(4), 1455-1508 — their Table 3 shows that essentially every
equity-premium predictor (valuation ratios, yield spreads, technical
indicators, breadth metrics) fails OOS: Campbell-Thompson OOS R² < 0 on
aggregate-equity-premium forecasting for nearly all predictors tested.
Breadth is a *CORRELATED* cross-sectional signal, not a validated predictor
of the equity premium; using it to tilt the basket would reduce to disguised
market timing with no OOS support.

The CORRECT forward use is as a **write-only contextual label** that seeds a
future Phase-7 Student-t Hidden Markov Model (HMM) regime-classifier, where
the breadth signal can be ONE input feature alongside realized vol,
credit-spread, and yield-curve data — evaluated rigorously OOS before any
tilt is authorized.  Reference: Kacperczyk, Van Nieuwerburgh, and Veldkamp
2014, "Time-Varying Fund Manager Skill", *Journal of Finance* 69(4),
1455-1484 — regime-conditional skill IS documented in the academic literature,
but only within an HMM framework trained on multi-year panels, not from a
single-day breadth reading.

DO NOT WIRE INTO SCORING
-------------------------
This module is OBSERVABILITY-ONLY.  It MUST NEVER be imported by:
  - ``compute/scoring/pillars.py``
  - ``compute/scoring/composite.py``
  - ``compute/scoring/risk_overlay.py`` / ``manipulation_index.py``
  - ``compute/valuation/ensemble.py``
  - any flag, veto, weight, or ``select_picks`` path

The only permitted consumer is the ``Metadata(...)`` constructor in
``compute/main.py``, which writes the fields to ``metadata.json``
(write-only, no downstream reads within the same cron run).

Defense layer is UNCHANGED at 36.

Thresholds (Tier-3 gut-feel calibration)
-----------------------------------------
No academic paper pins exact breadth cutoffs for regime classification.
The thresholds below are **TIER-3 GUT-FEEL CALIBRATION**:

  breadth_pct >= REGIME_RISK_ON_THRESHOLD  → "risk_on"   (60% — broad participation)
  breadth_pct <= REGIME_RISK_OFF_THRESHOLD → "risk_off"  (40% — broad deterioration)
  else                                     → "neutral"

These round numbers are documented as Tier-3 here and in config.py.
They are NOT derived from any paper; they are conventional technical-
analysis "breadth thrust" levels.  A future HMM (Phase 7) will derive
data-driven thresholds once a panel of regime labels is available.
The constants are named in config.py (``REGIME_RISK_ON_THRESHOLD`` /
``REGIME_RISK_OFF_THRESHOLD``) so any future recalibration is a visible
config diff, not a code change here.
"""

from __future__ import annotations

import logging

import pandas as pd

from compute import config

logger = logging.getLogger(__name__)


def compute_market_regime(
    prices_by_ticker: dict[str, pd.DataFrame],
) -> tuple[float | None, str | None]:
    """Compute market breadth above 200-day SMA + derive a regime label.

    This function is **WRITE-ONLY / OBSERVABILITY-ONLY** per Rule 18 and
    the Welch-Goyal 2008 rejection rationale above.  It MUST NOT be called
    from scoring, flag, or valuation paths.

    The function reuses the already-loaded price frames from Step 1
    (``prices_by_ticker`` passed from ``compute/main.py``) — NO new network
    call, NO new data source, NO new cache.

    Algorithm
    ---------
    1.  For each ticker in ``prices_by_ticker``, try to extract the latest
        close and the 200-day simple moving average.
    2.  Tickers with fewer than 200 trading-day bars are EXCLUDED from the
        denominator (not counted as above OR below) — insufficient history
        to compute a valid SMA-200.
    3.  ``breadth_pct`` = (count above SMA-200) / (count with ≥ 200 bars)
        expressed as a percentage in [0, 100].
    4.  ``regime_state`` is derived by comparing ``breadth_pct`` against the
        Tier-3 thresholds in config.py.

    Parameters
    ----------
    prices_by_ticker:
        ``{ticker: DataFrame}`` from Step 1 of the weekly compute.  Each
        DataFrame has a ``Close`` column (or ``Adj Close``; the 200-SMA is
        computed from the last available close column in the DataFrame).
        Missing or empty frames are silently skipped.

    Returns
    -------
    tuple[float | None, str | None]
        ``(breadth_pct, regime_state)``

        breadth_pct
            % of the eligible universe (≥ 200 bars) whose latest close is
            above its 200-day SMA.  ``None`` if no eligible tickers were found
            (e.g., all price frames were empty or too short).

        regime_state
            One of ``"risk_on"`` / ``"neutral"`` / ``"risk_off"``, or
            ``None`` when ``breadth_pct`` is ``None``.

    Notes
    -----
    Welch-Goyal 2008 (RFS 21(4)): equity-premium predictors fail OOS →
    breadth is a PLACEHOLDER FEATURE for Phase-7 HMM, NOT a regime classifier.
    This diagnostic is write-only.  No scoring consumer reads it.
    """
    above_200: int = 0
    eligible: int = 0

    for ticker, price_frame in prices_by_ticker.items():
        if price_frame is None or price_frame.empty:
            continue
        # Prefer 'Close'; fall back to 'Adj Close' if needed.
        close_col: str | None = None
        for col in ("Close", "Adj Close", "close", "adj close"):
            if col in price_frame.columns:
                close_col = col
                break
        if close_col is None:
            logger.debug(
                "[regime] %s: no Close/Adj Close column — skipping", ticker
            )
            continue

        closes = price_frame[close_col].dropna()
        if len(closes) < 200:
            # Insufficient history — exclude from denominator (honest).
            logger.debug(
                "[regime] %s: only %d bars < 200 — excluded from breadth denominator",
                ticker,
                len(closes),
            )
            continue

        eligible += 1
        sma_200 = closes.iloc[-200:].mean()
        latest_close = closes.iloc[-1]
        if latest_close > sma_200:
            above_200 += 1

    if eligible == 0:
        logger.warning(
            "[regime Proposal D] No eligible tickers (≥ 200 bars) found "
            "— breadth_pct → None.  (OBSERVABILITY-ONLY; Welch-Goyal 2008.)"
        )
        return (None, None)

    breadth_pct = round(100.0 * above_200 / eligible, 2)

    # Tier-3 gut-feel threshold derivation (see module docstring).
    if breadth_pct >= config.REGIME_RISK_ON_THRESHOLD:
        regime_state = "risk_on"
    elif breadth_pct <= config.REGIME_RISK_OFF_THRESHOLD:
        regime_state = "risk_off"
    else:
        regime_state = "neutral"

    logger.info(
        "[regime Proposal D] breadth_above_200dma_pct=%.2f%% "
        "eligible=%d above=%d regime_state=%s "
        "(WRITE-ONLY diagnostic; Welch-Goyal 2008 rejection-as-tilt; "
        "Phase-7 HMM seed — NOT wired into scoring, flags, or rankings.)",
        breadth_pct,
        eligible,
        above_200,
        regime_state,
    )
    return (breadth_pct, regime_state)
