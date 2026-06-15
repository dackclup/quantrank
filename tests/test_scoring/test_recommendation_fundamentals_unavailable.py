"""Pin the OZK/PBF cautious-path for the ``fundamentals_unavailable`` veto.

Commit 31e95b6f added ``"fundamentals_unavailable"`` to
``_CAUTIOUS_FORCING_RISK`` in ``recommendation.py``.  Before that fix a
ticker with composite ~51-55 (above ``LEAN_BULLISH_COMPOSITE_MIN = 50``)
and ``risk_flags=["fundamentals_unavailable"]`` was routed to
``"lean_bullish"`` because DQIC did not fire on a ``None`` snapshot
(issue #18 / test_D3 partition).

This file pins two invariants:

1. **positive case** — ``fundamentals_unavailable`` forces ``"cautious"``
   regardless of composite and MoS.
2. **negative case** — a clean sp500 ticker at the *same* composite
   (no forcing flag) still reaches ``"lean_bullish"`` — confirming the
   new flag doesn't widen the cautious bucket spuriously.
"""

from __future__ import annotations

from compute.scoring.recommendation import (
    LEAN_BULLISH_COMPOSITE_MIN,
    _CAUTIOUS_FORCING_RISK,
    derive_recommendation,
)

# ---------------------------------------------------------------------------
# 1. Positive case — flag fires, overrides what would otherwise be lean_bullish
# ---------------------------------------------------------------------------

def test_fundamentals_unavailable_forces_cautious_in_lean_bullish_band():
    """OZK/PBF scenario: composite in lean_bullish band + no other notable
    flags + mos_pct=None → without the fix this returned ``lean_bullish``.
    With the fix it must return ``cautious``.

    Uses ``LEAN_BULLISH_COMPOSITE_MIN + 5.0`` so the test is not sensitive
    to future composite-min re-calibration as long as the lean-bullish band
    still exists.
    """
    composite = LEAN_BULLISH_COMPOSITE_MIN + 5.0  # e.g. 55.0 — inside lean-bullish band

    result = derive_recommendation(
        composite_score=composite,
        risk_flags=["fundamentals_unavailable"],
        valuation_warnings=[],
        mos_pct=None,
    )
    assert result == "cautious", (
        f"Expected 'cautious' for composite={composite} + "
        f"risk_flags=['fundamentals_unavailable'], got '{result}'. "
        "Regression: 'fundamentals_unavailable' must be in _CAUTIOUS_FORCING_RISK."
    )


def test_fundamentals_unavailable_in_cautious_forcing_risk_set():
    """Structure pin: ``_CAUTIOUS_FORCING_RISK`` must contain the flag.

    If a refactor renames the flag or removes it from the set, this test
    fails before the recommendation routing test can even exercise the path.
    """
    assert "fundamentals_unavailable" in _CAUTIOUS_FORCING_RISK


# ---------------------------------------------------------------------------
# 2. Negative case — same composite + no forcing flag → lean_bullish (no widening)
# ---------------------------------------------------------------------------

def test_clean_ticker_at_same_composite_is_lean_bullish_not_cautious():
    """Confirm the cautious gate does NOT widen for a clean ticker.

    A stock at the same composite as OZK/PBF but with ``risk_flags=[]``
    and ``mos_pct=None`` (unknown valuation) must still reach
    ``lean_bullish`` — the new flag must not add false-positives.
    """
    composite = LEAN_BULLISH_COMPOSITE_MIN + 5.0  # same as positive case

    result = derive_recommendation(
        composite_score=composite,
        risk_flags=[],
        valuation_warnings=[],
        mos_pct=None,
    )
    assert result == "lean_bullish", (
        f"Expected 'lean_bullish' for composite={composite} + empty flags, "
        f"got '{result}'. Adding 'fundamentals_unavailable' to _CAUTIOUS_FORCING_RISK "
        "must not expand the cautious bucket for clean tickers."
    )
