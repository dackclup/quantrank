"""Unit tests for compute.scoring.going_concern (PR 3d Defense #8).

Coverage map:
- A. Phrase detection (8 cases) — primary phrases match
- B. Whitespace + punctuation flex (4 cases) — multi-space / newline / hyphen
- C. Negative cases (4 cases) — non-matching text returns False
- D. Edge cases (3 cases) — None / single char / multi-occurrence
- E. Boundary (2 cases) — phrase at start / end of text
- F. Module surface (2 cases) — phrase set is tuple + has ≥12 entries
"""

from __future__ import annotations

import pytest

from compute.scoring.going_concern import (
    GOING_CONCERN_PHRASES,
    scan_going_concern,
)

# ---------------------------------------------------------------------------
# A. Phrase detection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "There is substantial doubt about the company's ability",
        "going concern",
        "Going Concern",
        "Our auditors have noted ability to continue as a going concern",
        "material uncertainty related to going concern was disclosed",
        "negative cash flow from operations is expected",
        "An independent going concern qualification was issued",
        "The going concern uncertainty is disclosed",
    ],
    ids=[
        "A1_substantial_doubt",
        "A2_going_concern_verbatim",
        "A3_mixed_case",
        "A4_ability_to_continue_long",
        "A5_material_uncertainty",
        "A6_negative_cash_flow",
        "A7_qualification",
        "A8_uncertainty",
    ],
)
def test_A_primary_phrases_detected(text: str):
    assert scan_going_concern(text) is True


# ---------------------------------------------------------------------------
# B. Whitespace + punctuation flex
# ---------------------------------------------------------------------------

def test_B1_multiple_spaces():
    assert scan_going_concern("there is substantial   doubt here") is True


def test_B2_line_break_between_words():
    assert scan_going_concern("there is substantial\ndoubt here") is True


def test_B3_multiple_double_spaces_in_3_word_phrase():
    assert (
        scan_going_concern("a going  concern  qualification was attached")
        is True
    )


def test_B4_hyphen_between_words():
    """``going-concern`` (hyphen separator) must match the
    ``going concern`` phrase per spec."""
    assert (
        scan_going_concern("the going-concern footnote describes risks")
        is True
    )


# ---------------------------------------------------------------------------
# C. Negative cases
# ---------------------------------------------------------------------------

def test_C1_clean_filing_text():
    text = (
        "Revenue grew 12% year-over-year, driven by enterprise demand. "
        "The Company expects continued operational efficiency improvements "
        "throughout fiscal 2026."
    )
    assert scan_going_concern(text) is False


def test_C2_partial_concern_no_going():
    """``concern about quality`` is not a going-concern signal."""
    assert scan_going_concern("we have some concern about quality") is False


def test_C3_doubt_without_substantial():
    """``we doubt this strategy`` lacks the ``substantial`` qualifier."""
    assert scan_going_concern("we doubt this strategy will scale") is False


def test_C4_empty_string():
    assert scan_going_concern("") is False


# ---------------------------------------------------------------------------
# D. Edge cases
# ---------------------------------------------------------------------------

def test_D1_none_input():
    assert scan_going_concern(None) is False


def test_D2_single_character():
    assert scan_going_concern("x") is False


def test_D3_multiple_occurrences():
    """A phrase appearing 5 times still returns True (any-match)."""
    text = "going concern. " * 5
    assert scan_going_concern(text) is True


# ---------------------------------------------------------------------------
# E. Boundary
# ---------------------------------------------------------------------------

def test_E1_phrase_at_start():
    assert (
        scan_going_concern("substantial doubt remains as of the filing date")
        is True
    )


def test_E2_phrase_at_end():
    assert (
        scan_going_concern("the auditor noted a going concern qualification")
        is True
    )


# ---------------------------------------------------------------------------
# F. Module surface
# ---------------------------------------------------------------------------

def test_F1_phrase_set_is_tuple():
    """Tuple = immutable. Prevents accidental phrase mutation at runtime."""
    assert isinstance(GOING_CONCERN_PHRASES, tuple)


def test_F2_phrase_set_has_at_least_12_entries():
    """Sanity check on the curated subset — drift would dilute the
    signal or miss known going-concern boilerplate."""
    assert len(GOING_CONCERN_PHRASES) >= 12


# ---------------------------------------------------------------------------
# G. Word-boundary safety (not in the original spec — guards against the
# obvious failure mode "ongoing concerns" tripping the flag)
# ---------------------------------------------------------------------------

def test_G1_ongoing_concerns_does_not_match():
    """``ongoing concerns`` contains the substring ``going concern``
    but should NOT trigger because both word boundaries fail."""
    assert (
        scan_going_concern("the company addressed ongoing concerns")
        is False
    )


def test_G2_discontinued_operations_does_not_match():
    """``discontinued`` contains ``continued`` — no match expected."""
    assert (
        scan_going_concern("revenue from discontinued operations declined")
        is False
    )
