"""Unit tests for compute.scoring.manipulation_index (PR 4.5f).

Three pure functions:

- `compute_manipulation_index` — flag rollup, [0, 100] clipped
- `compute_adjusted_composite` — soft penalty, [0, 100] clamped
- `manipulation_components` — UI drill-down dict

Tests reference the module-level weight constants symbolically per
SKILL.md Rule 17 #2 — they assert behaviour against `WEIGHT ± epsilon`
rather than hard-coded numbers so a weight tweak won't shower the
suite red.
"""

from __future__ import annotations

import pytest

from compute.scoring.manipulation_index import (
    ACCRUALS_MOMENTUM_WEIGHT,
    BENEISH_HIGH_WEIGHT,
    BENEISH_VETO_WEIGHT,
    DECHOW_HIGH_WEIGHT,
    DECHOW_VETO_WEIGHT,
    FLAG_WEIGHTS,
    LATE_FILING_WEIGHT,
    LOSS_AVOIDANCE_WEIGHT,
    MAX_INDEX,
    NON_RELIANCE_WEIGHT,
    PENALTY_BUDGET,
    PENALTY_MULTIPLIER,
    REM_SUSPECT_WEIGHT,
    RESTATEMENT_HISTORY_WEIGHT,
    SLOAN_WEIGHT,
    TRIPLE_FLAG_WEIGHT,
    compute_adjusted_composite,
    compute_manipulation_index,
    manipulation_components,
)

# ---------------------------------------------------------------------------
# compute_manipulation_index
# ---------------------------------------------------------------------------


def test_empty_inputs_return_zero():
    assert compute_manipulation_index(None, None) == 0.0
    assert compute_manipulation_index([], []) == 0.0
    assert compute_manipulation_index(set(), set()) == 0.0


def test_unknown_flag_contributes_zero():
    # Forward compatibility — a new defense flag can land in
    # risk_flags before manipulation_index.py is updated, and the
    # rollup should silently ignore it (vs crashing).
    result = compute_manipulation_index(["totally_new_flag_2030"], [])
    assert result == 0.0


def test_single_active_veto_uses_correct_weight():
    result = compute_manipulation_index(["sloan_accruals_top_decile"], [])
    assert result == pytest.approx(SLOAN_WEIGHT)


def test_single_annotate_uses_correct_weight():
    result = compute_manipulation_index([], ["rem_suspect"])
    assert result == pytest.approx(REM_SUSPECT_WEIGHT)


def test_flag_in_both_arrays_counted_once():
    # Defensive: shouldn't happen in production, but the union
    # semantic guards against double-counting if a flag accidentally
    # lands in both lists.
    a = compute_manipulation_index(["sloan_accruals_top_decile"], [])
    b = compute_manipulation_index(
        ["sloan_accruals_top_decile"], ["sloan_accruals_top_decile"]
    )
    assert a == b


def test_multiple_flags_sum_additively():
    # Sloan + Beneish-veto + Dechow-veto = 20+20+20 = 60.
    expected = SLOAN_WEIGHT + BENEISH_VETO_WEIGHT + DECHOW_VETO_WEIGHT
    result = compute_manipulation_index(
        [
            "sloan_accruals_top_decile",
            "beneish_manipulation_veto",
            "dechow_manipulation_veto",
        ],
        [],
    )
    assert result == pytest.approx(expected)


def test_mixed_risk_flags_and_warnings_sum():
    # Sloan (veto) + REM (annotate) + Restatement (annotate) = 33.
    expected = SLOAN_WEIGHT + REM_SUSPECT_WEIGHT + RESTATEMENT_HISTORY_WEIGHT
    result = compute_manipulation_index(
        ["sloan_accruals_top_decile"],
        ["rem_suspect", "restatement_history"],
    )
    assert result == pytest.approx(expected)


def test_saturation_at_max_index():
    # Worst-case stock firing every currently-active 4.5a-d flag.
    # Sum of all weights in FLAG_WEIGHTS > MAX_INDEX → clipped to 100.
    all_flags = list(FLAG_WEIGHTS.keys())
    result = compute_manipulation_index(all_flags, [])
    assert result == MAX_INDEX


def test_sum_of_all_active_weights_exceeds_clip_floor():
    # Sanity-check: the FLAG_WEIGHTS table must be calibrated such that
    # a max-stack stock can hit (or exceed) the clip ceiling. If a
    # future weight reduction breaks this, the index loses its top end.
    assert sum(FLAG_WEIGHTS.values()) >= MAX_INDEX


def test_smci_real_world_case_saturates():
    # SMCI in run #50: sloan + beneish_veto + dechow_veto +
    # manipulation_triple_flag + rem_suspect. Sum =
    # 20+20+20+10+8 = 78. Below the clip — meaningful headroom for
    # an even worse stock to differentiate.
    result = compute_manipulation_index(
        [
            "sloan_accruals_top_decile",
            "beneish_manipulation_veto",
            "dechow_manipulation_veto",
        ],
        ["manipulation_triple_flag", "rem_suspect"],
    )
    expected = (
        SLOAN_WEIGHT
        + BENEISH_VETO_WEIGHT
        + DECHOW_VETO_WEIGHT
        + TRIPLE_FLAG_WEIGHT
        + REM_SUSPECT_WEIGHT
    )
    assert result == pytest.approx(expected)
    assert 70.0 <= result <= 90.0


def test_clean_stock_returns_zero():
    # CF / HST / NVDA on a clean week: empty risk_flags and only
    # neutral valuation_warnings (goodwill_heavy, value_trap_risk,
    # extreme_*_estimate) which are NOT in FLAG_WEIGHTS.
    result = compute_manipulation_index(
        [],
        ["goodwill_heavy", "value_trap_risk", "extreme_dcf_estimate"],
    )
    assert result == 0.0


def test_accepts_set_and_tuple_inputs():
    a = compute_manipulation_index({"sloan_accruals_top_decile"}, ())
    b = compute_manipulation_index(("sloan_accruals_top_decile",), set())
    c = compute_manipulation_index(frozenset({"sloan_accruals_top_decile"}), None)
    assert a == b == c == pytest.approx(SLOAN_WEIGHT)


# ---------------------------------------------------------------------------
# compute_adjusted_composite
# ---------------------------------------------------------------------------


def test_zero_index_does_not_penalize():
    assert compute_adjusted_composite(75.0, 0.0) == 75.0


def test_max_index_caps_penalty_at_budget_times_multiplier():
    # PENALTY_MULTIPLIER × PENALTY_BUDGET = 0.5 × 20 = 10 point max.
    expected_max_penalty = PENALTY_MULTIPLIER * PENALTY_BUDGET
    result = compute_adjusted_composite(75.0, MAX_INDEX)
    assert result == pytest.approx(75.0 - expected_max_penalty)


def test_half_index_half_max_penalty():
    expected_penalty = PENALTY_MULTIPLIER * 0.5 * PENALTY_BUDGET
    result = compute_adjusted_composite(75.0, 50.0)
    assert result == pytest.approx(75.0 - expected_penalty)


def test_adjusted_clamped_to_zero_floor():
    # Composite 2 + index 100 → adjusted = 2 - 10 = -8 → clamped to 0.
    result = compute_adjusted_composite(2.0, MAX_INDEX)
    assert result == 0.0


def test_adjusted_clamped_to_100_ceiling():
    # Pathological — composite > 100 + index 0 shouldn't happen but
    # the clamp keeps the contract honored.
    result = compute_adjusted_composite(105.0, 0.0)
    assert result == 100.0


def test_penalty_is_monotone_in_index():
    base = compute_adjusted_composite(80.0, 0.0)
    mid = compute_adjusted_composite(80.0, 50.0)
    high = compute_adjusted_composite(80.0, 100.0)
    assert base >= mid >= high


# ---------------------------------------------------------------------------
# manipulation_components
# ---------------------------------------------------------------------------


def test_components_returns_stable_key_set():
    # Every flag in FLAG_WEIGHTS must appear in the output, even
    # when no flags fire (UI invariant — sorted-by-weight grid).
    result = manipulation_components(None, None)
    assert set(result.keys()) == set(FLAG_WEIGHTS.keys())
    assert all(v is False for v in result.values())


def test_components_marks_fired_flags_true():
    result = manipulation_components(
        ["sloan_accruals_top_decile"],
        ["rem_suspect"],
    )
    assert result["sloan_accruals_top_decile"] is True
    assert result["rem_suspect"] is True
    assert result["beneish_manipulation_veto"] is False
    assert result["restatement_history"] is False


def test_components_unknown_flag_does_not_pollute_keys():
    # Forward compatibility: an unknown flag shouldn't leak into
    # the component output (it'd break the UI grid layout).
    result = manipulation_components(["totally_new_flag_2030"], [])
    assert "totally_new_flag_2030" not in result
    assert set(result.keys()) == set(FLAG_WEIGHTS.keys())


# ---------------------------------------------------------------------------
# Constants pinning
# ---------------------------------------------------------------------------


def test_max_index_is_100():
    # Pin the index range so a future tweak surfaces explicitly.
    assert MAX_INDEX == 100.0


def test_penalty_max_is_10_composite_points():
    # PENALTY_MULTIPLIER × PENALTY_BUDGET = 0.5 × 20 = 10. Pinning
    # this so the design contract ("max 10-point deduction") stays
    # honored when knobs move.
    assert PENALTY_MULTIPLIER * PENALTY_BUDGET == pytest.approx(10.0)


def test_active_veto_weights_dominate_annotates():
    # Calibration check: any active-veto flag should outweigh any
    # individual annotate, reflecting the higher PPV.
    veto_weights = (
        SLOAN_WEIGHT,
        BENEISH_VETO_WEIGHT,
        DECHOW_VETO_WEIGHT,
        NON_RELIANCE_WEIGHT,
    )
    annotate_weights = (
        REM_SUSPECT_WEIGHT,
        RESTATEMENT_HISTORY_WEIGHT,
        LATE_FILING_WEIGHT,
        ACCRUALS_MOMENTUM_WEIGHT,
        LOSS_AVOIDANCE_WEIGHT,
        BENEISH_HIGH_WEIGHT,
        DECHOW_HIGH_WEIGHT,
    )
    assert min(veto_weights) > max(annotate_weights)


def test_triple_flag_weight_below_individual_vetoes():
    # The joint gate (manipulation_triple_flag) is a label, not a
    # new signal — should weight less than any individual veto
    # whose firing it depends on.
    individual_vetos = (SLOAN_WEIGHT, BENEISH_VETO_WEIGHT, DECHOW_VETO_WEIGHT)
    assert TRIPLE_FLAG_WEIGHT < min(individual_vetos)
