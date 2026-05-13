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


# ---------------------------------------------------------------------------
# Section H — Negation lookbehind (issue #16). The 10.8% FP rate in Run #15
# was driven by risk-factor language using negation: "no substantial doubt
# about our ability...", "Management believes there is no material
# uncertainty...", etc. These tests lock the negation-aware contract that
# drops the FP class while preserving positive-control matches.
# ---------------------------------------------------------------------------


def test_H1_no_substantial_doubt_does_not_fire():
    """The single biggest FP class in Run #15 — `no substantial doubt`."""
    text = (
        "Based on this evaluation, management has concluded that there is "
        "no substantial doubt about our ability to continue as a going concern."
    )
    assert scan_going_concern(text) is False


def test_H2_management_believes_no_material_uncertainty():
    """Verbose-negation case from the issue body."""
    text = (
        "Management believes there is no material uncertainty related to "
        "going concern based on the cash flow projections described above."
    )
    assert scan_going_concern(text) is False


def test_H3_company_has_no_doubt():
    """Common variant: `The Company has no doubt about its ability...`."""
    text = (
        "The Company has no doubt about its ability to continue operations "
        "and meet financial obligations as they come due."
    )
    assert scan_going_concern(text) is False


def test_H4_positive_control_substantial_doubt_still_fires():
    """Bare positive — no negation in window — must still fire.

    Without this guarantee the fix degrades into "always returns False".
    """
    text = (
        "The auditor has raised substantial doubt about the Company's "
        "ability to continue as a going concern beyond the next 12 months."
    )
    assert scan_going_concern(text) is True


def test_H5_positive_control_isolated_phrase():
    """Whole text is the phrase + period — sanity check."""
    assert scan_going_concern("substantial doubt about its ability.") is True


def test_H6_without_substantial_doubt():
    """`without` is a negation token (not `no`)."""
    text = "The Company operates without substantial doubt about future cash flows."
    assert scan_going_concern(text) is False


def test_H7_absent_substantial_doubt():
    """`absent` is also a negation token."""
    text = "Absent any substantial doubt, the audit opinion was unqualified."
    assert scan_going_concern(text) is False


def test_H8_not_identified_multi_word_negation():
    """`have not identified` — multi-word negation form."""
    text = (
        "Management has not identified conditions raising substantial doubt "
        "about the Company's ability to continue as a going concern."
    )
    assert scan_going_concern(text) is False


def test_H9_sentence_boundary_isolates_negation():
    """Negation in prior sentence MUST NOT carry over to a new sentence."""
    text = (
        "We have no operations in conflict zones. There is substantial doubt "
        "about the parent guarantor's ability to continue as a going concern."
    )
    assert scan_going_concern(text) is True


def test_H10_case_insensitive_negation():
    """Negation tokens are case-insensitive (same as the phrase patterns)."""
    text = "NO SUBSTANTIAL DOUBT about ability."
    assert scan_going_concern(text) is False


def test_H11_hyphenated_phrase_after_negation():
    """`no substantial-doubt` (hyphen flex) — negation still applies."""
    text = "there is no substantial-doubt regarding the company's solvency"
    assert scan_going_concern(text) is False


def test_H12_does_not_believe_negation():
    """`does not believe` — multi-word negation captured by the regex."""
    text = (
        "The auditor does not believe substantial doubt exists about the "
        "Company's ability to operate."
    )
    assert scan_going_concern(text) is False


def test_H13_multiple_matches_one_negated_one_positive():
    """If a filing contains both a negated mention AND a positive mention,
    the positive one wins. This guards against over-aggressive negation
    silencing a real signal that happens to share the text with risk-
    factor boilerplate."""
    text = (
        "Note 1: There is no substantial doubt about the parent. "
        "Note 7: However, with respect to Segment B, substantial doubt "
        "remains about the ability to continue operations."
    )
    assert scan_going_concern(text) is True


def test_H14_distant_no_does_not_negate():
    """A `no` further than 60 chars away in the SAME sentence does NOT
    suppress the match. Window is intentionally narrow to bias toward
    catching real signals."""
    # 90+ chars of filler between the "no" and the phrase. We want this
    # to FIRE — the "no" applied to "operations", not "doubt".
    text = (
        "The Company has no operations whatsoever in the Korean peninsula, "
        "the southeast Asian region, or the Middle East zones, and the "
        "auditor has raised substantial doubt about ability to operate."
    )
    assert scan_going_concern(text) is True


def test_H15_negation_window_60_char_boundary():
    """Boundary case: a `no` exactly at the edge of the 60-char window
    is INCLUDED in the negation (window is `match_start - 60` to
    `match_start`, inclusive on the lower bound).
    """
    # Craft a string where "no" sits exactly 60 chars before "substantial".
    prefix = "no "
    filler = "x" * 57  # 57 + 3 ("no ") = 60 chars before "substantial"
    text = prefix + filler + "substantial doubt about ability"
    # "no" is at index 0, "substantial" starts at index 60.
    # Window is text[0:60] = "no" + 58 chars → "no" is in window.
    assert scan_going_concern(text) is False
