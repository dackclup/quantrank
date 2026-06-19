"""P2-1: Tests for the manipulation_triple_flag joint-gate semantics.

The ``manipulation_triple_flag`` is injected by ``compute/main.py`` Step 5
into ``valuation_warnings`` when three quant defenses co-fire on the SAME
ticker:

  - ``sloan_accruals_top_decile``  in risk_flags
  - ``beneish_high``               in valuation_warnings
  - ``dechow_high``                in valuation_warnings

``compute_manipulation_index`` treats it as a regular table-driven flag
worth ``TRIPLE_FLAG_WEIGHT = 10.0``.  The joint-gate semantics live in
``main.py``, NOT in the index rollup.

Coverage:
- TF1: when all three prerequisites are present AND the gate label is
  injected, the manipulation index reaches the documented ≥70 point
  threshold (three 20-pt vetoes = 60; + 10-pt bonus = 70).
- TF2: when only two of the three prerequisites are present (and therefore
  ``main.py`` would NOT inject the gate label), the index stays at 40
  (two vetoes only — no bonus).
- TF3: the ``manipulation_triple_flag`` label alone (without the three
  prerequisites) contributes EXACTLY ``TRIPLE_FLAG_WEIGHT`` — the weight
  table entry is real and the rollup doesn't special-case it.
- TF4: adding ``beneish_high`` + ``dechow_high`` without Sloan does NOT
  fire the joint gate (the main.py check requires Sloan explicitly).
"""

from __future__ import annotations

import pytest

from compute.scoring.manipulation_index import (
    BENEISH_HIGH_WEIGHT,
    BENEISH_VETO_WEIGHT,
    DECHOW_HIGH_WEIGHT,
    DECHOW_VETO_WEIGHT,
    SLOAN_WEIGHT,
    TRIPLE_FLAG_WEIGHT,
    compute_manipulation_index,
)

# The three prerequisite flag strings (matching the main.py check).
_SLOAN_FLAG = "sloan_accruals_top_decile"
_BENEISH_HIGH_FLAG = "beneish_high"
_DECHOW_HIGH_FLAG = "dechow_high"
_GATE_LABEL = "manipulation_triple_flag"


# ---------------------------------------------------------------------------
# TF1 — All three prerequisites + gate label → index ≥ 70
# ---------------------------------------------------------------------------


def test_TF1_triple_flag_fires_index_reaches_70_threshold() -> None:
    """TF1: Sloan (20) + Beneish-high (3) + Dechow-high (3) + triple-gate (10)
    = 36 base + potential other flags.

    But the MOST COMMON production path (SMCI-class) fires the ACTIVE vetoes
    (beneish_manipulation_veto + dechow_manipulation_veto) alongside Sloan —
    that's 20 + 20 + 20 = 60.  Add the triple-gate label at 10 → 70.

    This test uses the active-veto path (the typical triple-flag co-fire
    scenario confirmed by test_smci_real_world_case_saturates in the
    main test file) and asserts the total EXACTLY reaches 70 (no extra
    flags, no saturation clipping).
    """
    risk_flags = [
        _SLOAN_FLAG,
        "beneish_manipulation_veto",
        "dechow_manipulation_veto",
    ]
    # main.py injects the gate label into valuation_warnings
    valuation_warnings = [_GATE_LABEL]

    result = compute_manipulation_index(risk_flags, valuation_warnings)

    expected = SLOAN_WEIGHT + BENEISH_VETO_WEIGHT + DECHOW_VETO_WEIGHT + TRIPLE_FLAG_WEIGHT
    assert result == pytest.approx(expected)
    assert result >= 70.0, (
        f"Triple-flag co-fire must reach ≥70 (documented intent); got {result}"
    )


def test_TF1_triple_flag_fires_with_beneish_dechow_high_path() -> None:
    """TF1 (annotation-only path): Sloan (20) + beneish_high (3) + dechow_high (3)
    + triple-gate (10) = 36. Below the veto path but validates the warning-band
    triple-gate computation precisely.

    This is the beneish_high + dechow_high path that main.py checks for the gate
    injection condition (not the active-veto path).
    """
    risk_flags = [_SLOAN_FLAG]
    valuation_warnings = [_BENEISH_HIGH_FLAG, _DECHOW_HIGH_FLAG, _GATE_LABEL]

    result = compute_manipulation_index(risk_flags, valuation_warnings)

    expected = SLOAN_WEIGHT + BENEISH_HIGH_WEIGHT + DECHOW_HIGH_WEIGHT + TRIPLE_FLAG_WEIGHT
    assert result == pytest.approx(expected)


# ---------------------------------------------------------------------------
# TF2 — Only two of the three prerequisites (no gate label injected)
# ---------------------------------------------------------------------------


def test_TF2_two_flags_no_gate_label_no_bonus() -> None:
    """TF2: Only Sloan + beneish_high (no dechow_high) → main.py does NOT
    inject the gate label, so the index is 20 + 3 = 23.

    This confirms the joint-gate semantics: the bonus is NOT auto-computed by
    ``compute_manipulation_index`` — the caller is responsible for injecting
    ``manipulation_triple_flag`` into the flag sets.
    """
    risk_flags = [_SLOAN_FLAG]
    valuation_warnings = [_BENEISH_HIGH_FLAG]  # no dechow_high, no gate label

    result = compute_manipulation_index(risk_flags, valuation_warnings)

    expected = SLOAN_WEIGHT + BENEISH_HIGH_WEIGHT
    assert result == pytest.approx(expected)
    # Must NOT silently reach the triple-flag level.
    assert result < SLOAN_WEIGHT + BENEISH_HIGH_WEIGHT + DECHOW_HIGH_WEIGHT + TRIPLE_FLAG_WEIGHT


def test_TF2_sloan_plus_dechow_high_only_no_gate_label() -> None:
    """TF2 (alt): Sloan + dechow_high only (no beneish_high) → no gate label
    injected; index is 20 + 3 = 23.
    """
    risk_flags = [_SLOAN_FLAG]
    valuation_warnings = [_DECHOW_HIGH_FLAG]

    result = compute_manipulation_index(risk_flags, valuation_warnings)

    expected = SLOAN_WEIGHT + DECHOW_HIGH_WEIGHT
    assert result == pytest.approx(expected)


# ---------------------------------------------------------------------------
# TF3 — Gate label alone contributes exactly TRIPLE_FLAG_WEIGHT
# ---------------------------------------------------------------------------


def test_TF3_gate_label_alone_contributes_triple_flag_weight() -> None:
    """TF3: ``manipulation_triple_flag`` in valuation_warnings with no other
    flags contributes exactly ``TRIPLE_FLAG_WEIGHT`` (10.0) and nothing more.

    This validates the FLAG_WEIGHTS table entry is correctly wired — the
    rollup doesn't special-case the gate label (just a regular table lookup).
    """
    result = compute_manipulation_index([], [_GATE_LABEL])
    assert result == pytest.approx(TRIPLE_FLAG_WEIGHT)


# ---------------------------------------------------------------------------
# TF4 — beneish_high + dechow_high without Sloan → no gate injection possible
# ---------------------------------------------------------------------------


def test_TF4_beneish_high_plus_dechow_high_without_sloan_no_gate() -> None:
    """TF4: The main.py gate requires ``sloan_accruals_top_decile`` in
    risk_flags.  Without Sloan, even if beneish_high + dechow_high fire, the
    gate label is NOT injected.

    Index should be BENEISH_HIGH_WEIGHT + DECHOW_HIGH_WEIGHT = 6.0 only.
    """
    risk_flags: list[str] = []  # no Sloan
    valuation_warnings = [_BENEISH_HIGH_FLAG, _DECHOW_HIGH_FLAG]

    result = compute_manipulation_index(risk_flags, valuation_warnings)

    expected = BENEISH_HIGH_WEIGHT + DECHOW_HIGH_WEIGHT
    assert result == pytest.approx(expected)
    # No gate bonus.
    assert result < TRIPLE_FLAG_WEIGHT, (
        f"Without Sloan the gate cannot fire; "
        f"expected < {TRIPLE_FLAG_WEIGHT}, got {result}"
    )
