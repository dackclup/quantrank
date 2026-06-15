"""Tests for Issue #377 — manipulation_index rollup coverage for the 6
annotate flags that have FLAG_WEIGHTS entries but zero isolated rollup-path
test coverage in the existing ``test_manipulation_index.py``.

Missing flags identified by diffing FLAG_WEIGHTS keys against what
``test_manipulation_index.py`` exercises with an isolated single-flag test:

FLAG_WEIGHTS keys (16 total in production code):
    sloan_accruals_top_decile         — covered (test_single_active_veto_uses_correct_weight)
    beneish_manipulation_veto         — covered (test_multiple_flags_sum_additively)
    dechow_manipulation_veto          — covered (test_multiple_flags_sum_additively)
    non_reliance_filing               — NOT covered with an isolated single-flag test
    manipulation_triple_flag          — covered (test_smci_real_world_case_saturates)
    rem_suspect                       — covered (test_single_annotate_uses_correct_weight)
    restatement_history               — covered (test_mixed_risk_flags_and_warnings_sum)
    restatement_high_confidence       — NOT covered (no isolation test)
    late_filing_notification          — NOT covered (no isolation test)
    accruals_momentum_high            — NOT covered (no isolation test)
    loss_avoidance_pattern            — NOT covered (no isolation test)
    loss_avoidance_pattern_size_invariant — NOT covered (no isolation test)
    beneish_high                      — NOT covered (no isolation test)
    dechow_high                       — NOT covered (no isolation test)
    insider_sell_cluster              — NOT covered (no isolation test)
    c_suite_unusual_sell              — NOT covered (no isolation test)

The 6 chosen for this file (most newly landed / least covered):
    restatement_high_confidence, loss_avoidance_pattern_size_invariant,
    insider_sell_cluster, c_suite_unusual_sell, late_filing_notification,
    accruals_momentum_high

Each parametrized case asserts:
  - Only that ONE flag set → ``compute_manipulation_index`` returns
    exactly FLAG_WEIGHTS[flag] (within floating-point tolerance).
  - The rollup does not accidentally add noise from missing siblings.

Style mirrors ``test_manipulation_index.py``'s symbolic-weight convention
(Rule 17 #2): weights are imported from the module, not hard-coded.
"""

from __future__ import annotations

import pytest

from compute.scoring.manipulation_index import (
    ACCRUALS_MOMENTUM_WEIGHT,
    BENEISH_HIGH_WEIGHT,
    C_SUITE_UNUSUAL_SELL_WEIGHT,
    DECHOW_HIGH_WEIGHT,
    FLAG_WEIGHTS,
    INSIDER_SELL_CLUSTER_WEIGHT,
    LATE_FILING_WEIGHT,
    LOSS_AVOIDANCE_SIZE_INVARIANT_WEIGHT,
    LOSS_AVOIDANCE_WEIGHT,
    NON_RELIANCE_WEIGHT,
    RESTATEMENT_HIGH_CONFIDENCE_WEIGHT,
    compute_manipulation_index,
)

# ---------------------------------------------------------------------------
# Parametrized isolation tests — one flag at a time
# ---------------------------------------------------------------------------

_ISOLATED_FLAG_CASES = [
    ("non_reliance_filing",                  NON_RELIANCE_WEIGHT),
    ("restatement_high_confidence",          RESTATEMENT_HIGH_CONFIDENCE_WEIGHT),
    ("late_filing_notification",             LATE_FILING_WEIGHT),
    ("accruals_momentum_high",               ACCRUALS_MOMENTUM_WEIGHT),
    ("loss_avoidance_pattern",               LOSS_AVOIDANCE_WEIGHT),
    ("loss_avoidance_pattern_size_invariant", LOSS_AVOIDANCE_SIZE_INVARIANT_WEIGHT),
    ("beneish_high",                         BENEISH_HIGH_WEIGHT),
    ("dechow_high",                          DECHOW_HIGH_WEIGHT),
    ("insider_sell_cluster",                 INSIDER_SELL_CLUSTER_WEIGHT),
    ("c_suite_unusual_sell",                 C_SUITE_UNUSUAL_SELL_WEIGHT),
]


@pytest.mark.parametrize("flag,expected_weight", _ISOLATED_FLAG_CASES)
def test_single_flag_rollup_returns_its_weight(flag: str, expected_weight: float):
    """When ONLY ``flag`` is set (in risk_flags), ``compute_manipulation_index``
    returns exactly ``FLAG_WEIGHTS[flag]``.

    This pins the rollup path for every annotate flag individually —
    a weight mis-wiring or a missing FLAG_WEIGHTS entry shows up immediately.
    """
    result = compute_manipulation_index([flag], [])
    assert result == pytest.approx(expected_weight), (
        f"compute_manipulation_index(['{flag}'], []) must equal "
        f"FLAG_WEIGHTS['{flag}'] = {expected_weight}; got {result}"
    )


@pytest.mark.parametrize("flag,expected_weight", _ISOLATED_FLAG_CASES)
def test_single_flag_in_valuation_warnings_rollup(flag: str, expected_weight: float):
    """Same rollup assertion but via ``valuation_warnings`` (the second
    input channel).  Both channels contribute to the fired-flag union.
    """
    result = compute_manipulation_index([], [flag])
    assert result == pytest.approx(expected_weight), (
        f"compute_manipulation_index([], ['{flag}']) must equal "
        f"FLAG_WEIGHTS['{flag}'] = {expected_weight}; got {result}"
    )


# ---------------------------------------------------------------------------
# Additive combinations — insider cluster + c_suite delta semantics
# ---------------------------------------------------------------------------


def test_insider_sell_cluster_plus_c_suite_additive():
    """Per the module docstring, ``c_suite_unusual_sell`` is a strict subset of
    ``insider_sell_cluster`` — a C-suite firing also fires the cluster flag.
    When both are set, they sum additively:
    INSIDER_SELL_CLUSTER_WEIGHT + C_SUITE_UNUSUAL_SELL_WEIGHT = 8.0 target.
    """
    result = compute_manipulation_index(
        ["insider_sell_cluster", "c_suite_unusual_sell"], []
    )
    expected = INSIDER_SELL_CLUSTER_WEIGHT + C_SUITE_UNUSUAL_SELL_WEIGHT
    assert result == pytest.approx(expected), (
        f"Combined C-suite cluster: expected {expected}; got {result}"
    )


def test_c_suite_unusual_sell_isolated_is_delta_weight():
    """``c_suite_unusual_sell`` in isolation contributes only the delta weight
    (3.0), NOT the combined total.  When the cluster flag is absent, only the
    delta accrues.
    """
    result_c_suite_only = compute_manipulation_index(["c_suite_unusual_sell"], [])
    result_cluster_only = compute_manipulation_index(["insider_sell_cluster"], [])

    assert result_c_suite_only == pytest.approx(C_SUITE_UNUSUAL_SELL_WEIGHT)
    assert result_cluster_only == pytest.approx(INSIDER_SELL_CLUSTER_WEIGHT)
    # Delta relationship: combined > either alone
    combined = compute_manipulation_index(
        ["insider_sell_cluster", "c_suite_unusual_sell"], []
    )
    assert combined > result_cluster_only
    assert combined > result_c_suite_only


# ---------------------------------------------------------------------------
# All new flags must be present in FLAG_WEIGHTS (schema guard)
# ---------------------------------------------------------------------------


def test_all_parametrized_flags_in_flag_weights():
    """All flags in ``_ISOLATED_FLAG_CASES`` must be present in FLAG_WEIGHTS.

    This guards against the test set going stale if a flag is ever renamed
    or removed — the FLAG_WEIGHTS lookup is the authoritative registry.
    """
    for flag, _ in _ISOLATED_FLAG_CASES:
        assert flag in FLAG_WEIGHTS, (
            f"Flag '{flag}' used in isolation tests but missing from FLAG_WEIGHTS"
        )
