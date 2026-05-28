"""Tests for the PR 6 10b5-1 negation guard in compute.scoring.form4_insider.

Phase 4.5e PR 6 adds a post-detector negation guard wrapping
``edgar.ownership.core.detect_10b5_1_plan``. When the upstream detector
returns True, a new ``_has_negation(text)`` helper re-scans the resolved
footnote text for negation phrases within ±5 word tokens of a 10b5-1
mention. On match, the detection is downgraded True → False and the
module-level ``_negation_downgrade_count`` is incremented.

This file covers:

- Section P — pattern coverage (11 negation patterns)
- Section N — negative paths (should NOT fire)
- Section W — ±5 token window boundary
- Section S — alt spelling (10b5-1 / 10b-5-1)
- Section I — ``_detect_10b5_1_on_transaction`` integration
- Section C — counter thread-safety and reset/bump/get cycle
- Section H — Hypothesis properties (idempotence + monotonicity)
- Section M — manifest pin (``_NEGATION_PATTERNS`` frozenset)

Footgun #1 link: see module docstring §"PR 6 — 10b5-1 negation guard" in
``compute/scoring/form4_insider.py``.

All tests are offline. No edgartools live EDGAR fetch. ``detect_10b5_1_plan``
is monkeypatched via ``pytest.monkeypatch`` for integration-layer tests;
``_has_negation`` unit tests exercise the compiled regex directly.
"""

from __future__ import annotations

import concurrent.futures
import types

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from compute.scoring.form4_insider import (
    _NEGATION_PATTERNS,
    _NEGATION_REGEX,
    _bump_negation_downgrade_count,
    _detect_10b5_1_on_transaction,
    _has_negation,
    get_negation_downgrade_count,
    reset_negation_downgrade_count,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tx(footnote_ids: str = "F1") -> types.SimpleNamespace:
    """Minimal duck-typed transaction with ``.footnotes`` as a newline-joined
    ID string. Mirrors edgartools ``NonDerivativeTransaction.footnotes``
    semantics used by ``_detect_10b5_1_on_transaction``."""
    return types.SimpleNamespace(footnotes=footnote_ids)


def _footnotes(f1_text: str = "") -> dict[str, str]:
    """Minimal Footnotes-dict stub — satisfies the ``.get(key, default)``
    duck-typing contract used by ``_detect_10b5_1_on_transaction``."""
    return {"F1": f1_text}


# ---------------------------------------------------------------------------
# P. Pattern coverage — one sub-test per negation phrase
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        # AFTER branch — negation follows the 10b5-1 mention
        "Rule 10b5-1 plan terminated in January 2022",
        "Rule 10b5-1 plan was cancelled by the issuer",
        "Rule 10b5-1 plan was canceled on March 3",
        "Rule 10b5-1 plan expired December 31 2021",
        "Rule 10b5-1 plan rescinded",
        "Rule 10b5-1 was discontinued",
        # BEFORE branch — negation precedes the 10b5-1 mention
        "rescinded the Rule 10b5-1 plan",
        "discontinued prior 10b5-1 plan",
        "no Rule 10b5-1 plan on file",
        "not in effect any Rule 10b5-1 plan",
        "previously had a 10b5-1 plan",
        "former 10b5-1 plan",
        "without any 10b5-1 plan",
    ],
    ids=[
        "terminated-after",
        "cancelled-double-l-after",
        "canceled-single-l-after",
        "expired-after",
        "rescinded-after",
        "discontinued-after",
        "rescinded-before",
        "discontinued-before",
        "no-before",
        "not-in-effect-before",
        "previously-before",
        "former-before",
        "without-before",
    ],
)
def test_P_negation_pattern_fires(text: str) -> None:
    """Every negation phrase in ``_NEGATION_PATTERNS`` must trigger
    ``_has_negation`` when placed within ±5 tokens of a 10b5-1 mention."""
    assert _has_negation(text) is True


# ---------------------------------------------------------------------------
# N. Negative paths — guard must NOT fire
# ---------------------------------------------------------------------------


def test_N1_affirmative_adoption_phrase_does_not_fire() -> None:
    """'Rule 10b5-1 trading plan adopted 2024' is a live-plan disclosure —
    no negation phrase present; guard must return False."""
    assert _has_negation("Rule 10b5-1 trading plan adopted October 2024") is False


def test_N2_10b5_1_mention_with_no_nearby_negation_does_not_fire() -> None:
    """10b5-1 mentioned but no negation token within 5 words; guard stays silent."""
    # "entered into" and "remains in force" are clearly affirmative and none of
    # the 11 negation tokens appear near the mention.
    assert _has_negation("The seller entered into a Rule 10b5-1 plan remains in force") is False


def test_N3_empty_string_does_not_fire() -> None:
    """Empty string is an explicit early-return path (``if not text: return False``)."""
    assert _has_negation("") is False


def test_N4_none_via_empty_string_sentinel() -> None:
    """Callers may pass an empty string when footnote resolution returns
    nothing; guard handles this without error."""
    assert _has_negation("") is False


def test_N5_negation_word_without_10b5_1_mention_does_not_fire() -> None:
    """'terminated' appearing in text with no 10b5-1 mention must not fire —
    the regex requires BOTH the negation token AND a 10b5-1 pattern."""
    assert _has_negation("the arrangement was terminated last year") is False


# ---------------------------------------------------------------------------
# W. ±5 token window boundary
# ---------------------------------------------------------------------------


def test_W1_negation_within_5_tokens_after_fires() -> None:
    """Negation token at exactly 5 intervening words AFTER the mention fires."""
    # 'Rule 10b5-1' → 'one' 'two' 'three' 'four' 'five' → 'terminated'
    # The regex uses ``(?:\W+\w+){0,5}\W+`` which allows 0-to-5 words.
    # 5 intervening words is within the window.
    text = "Rule 10b5-1 one two three four five terminated"
    assert _has_negation(text) is True


def test_W2_negation_at_6_tokens_after_does_not_fire() -> None:
    """Negation token at 6 intervening words after the mention is outside the
    ±5 token window and must NOT trigger the guard."""
    # 'Rule 10b5-1' → 6 words → 'terminated'
    text = "Rule 10b5-1 one two three four five six terminated"
    assert _has_negation(text) is False


# ---------------------------------------------------------------------------
# S. Both 10b5-1 / 10b-5-1 spellings are accepted
# ---------------------------------------------------------------------------


def test_S1_canonical_spelling_10b5_1_with_negation() -> None:
    """Canonical SEC spelling '10b5-1' with negation fires the guard."""
    assert _has_negation("no 10b5-1 plan in effect") is True


def test_S2_alt_spelling_10b_5_1_with_negation() -> None:
    """Alternate spelling '10b-5-1' (hyphen between b and 5) with negation
    fires the guard — mirrors the upstream ``detect_10b5_1_plan`` pattern list."""
    assert _has_negation("no 10b-5-1 plan in effect") is True


# ---------------------------------------------------------------------------
# I. _detect_10b5_1_on_transaction integration
# ---------------------------------------------------------------------------


def test_I1_detector_true_plus_negation_returns_false_and_increments_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the upstream detector returns True AND negation guard fires,
    ``_detect_10b5_1_on_transaction`` must return False and increment the
    module-level counter by 1."""
    monkeypatch.setattr(
        "edgar.ownership.core.detect_10b5_1_plan",
        lambda text: True,
    )
    reset_negation_downgrade_count()

    tx = _tx("F1")
    fn = _footnotes("10b5-1 plan terminated 2022")  # negation fires

    result = _detect_10b5_1_on_transaction(tx, fn)

    assert result is False
    assert get_negation_downgrade_count() == 1


def test_I2_detector_true_no_negation_returns_true_counter_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the upstream detector returns True and no negation phrase is near
    the 10b5-1 mention, result stays True and counter is NOT incremented."""
    monkeypatch.setattr(
        "edgar.ownership.core.detect_10b5_1_plan",
        lambda text: True,
    )
    reset_negation_downgrade_count()

    tx = _tx("F1")
    fn = _footnotes("Rule 10b5-1 trading plan adopted October 2024")  # affirmative

    result = _detect_10b5_1_on_transaction(tx, fn)

    assert result is True
    assert get_negation_downgrade_count() == 0


def test_I3_detector_false_counter_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the upstream detector returns False (no 10b5-1 mention at all),
    the guard does not touch the counter — it only downgrades True."""
    monkeypatch.setattr(
        "edgar.ownership.core.detect_10b5_1_plan",
        lambda text: False,
    )
    reset_negation_downgrade_count()

    tx = _tx("F1")
    fn = _footnotes("sold shares at market price")  # no plan language

    result = _detect_10b5_1_on_transaction(tx, fn)

    assert result is False
    assert get_negation_downgrade_count() == 0


def test_I4_detector_none_no_footnotes_returns_none_counter_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty footnotes → ``_detect_10b5_1_on_transaction`` returns None
    before reaching the detector; counter stays at zero."""
    # Because ``tx.footnotes`` is empty, the function returns early with None.
    monkeypatch.setattr(
        "edgar.ownership.core.detect_10b5_1_plan",
        lambda text: True,  # would return True if reached — but it isn't
    )
    reset_negation_downgrade_count()

    tx_no_fn = types.SimpleNamespace(footnotes="")
    result = _detect_10b5_1_on_transaction(tx_no_fn, None)

    assert result is None
    assert get_negation_downgrade_count() == 0


def test_I5_footnote_id_not_in_dict_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Footnote ID present in tx but not resolvable in the dict → None
    (no text to scan; guard never fires)."""
    monkeypatch.setattr(
        "edgar.ownership.core.detect_10b5_1_plan",
        lambda text: True,
    )
    reset_negation_downgrade_count()

    tx = _tx("F99")
    fn: dict[str, str] = {}  # F99 not in dict

    result = _detect_10b5_1_on_transaction(tx, fn)

    assert result is None
    assert get_negation_downgrade_count() == 0


# ---------------------------------------------------------------------------
# C. Counter thread-safety and reset/bump/get cycle
# ---------------------------------------------------------------------------


def test_C1_reset_get_bump_get_cycle_returns_expected_values() -> None:
    """reset → get (0) → bump → bump → get (2) → reset → get (0)."""
    reset_negation_downgrade_count()
    assert get_negation_downgrade_count() == 0

    _bump_negation_downgrade_count()
    _bump_negation_downgrade_count()
    assert get_negation_downgrade_count() == 2

    reset_negation_downgrade_count()
    assert get_negation_downgrade_count() == 0


def test_C2_concurrent_100_bumps_reach_exact_count() -> None:
    """Prove the threading.Lock protects ``_negation_downgrade_count``:
    100 concurrent increments from 8 workers must yield exactly 100."""
    reset_negation_downgrade_count()

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [
            pool.submit(_bump_negation_downgrade_count) for _ in range(100)
        ]
        concurrent.futures.wait(futures)

    assert get_negation_downgrade_count() == 100


# ---------------------------------------------------------------------------
# H. Hypothesis properties
# ---------------------------------------------------------------------------


@given(text=st.text(min_size=0, max_size=500))
def test_H1_has_negation_is_deterministic(text: str) -> None:
    """``_has_negation`` is a pure function — calling it twice on the same
    string must return the same bool regardless of module state."""
    assert _has_negation(text) == _has_negation(text)


@settings(suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much])
@given(prefix=st.text(min_size=0, max_size=200))
def test_H2_adding_negation_suffix_cannot_turn_true_into_false(prefix: str) -> None:
    """Monotonicity: if ``_has_negation(prefix + '10b5-1 terminated')`` is
    True, it cannot become False when we append more negation-bearing text.

    This test appends a canonical negation phrase to an arbitrary prefix
    and asserts the result is True. It doesn't check the prefix alone
    (it may or may not fire); it checks that the combined string fires.
    The invariant: once a negation trigger is present, the guard stays True.
    """
    combined = prefix + " 10b5-1 plan terminated"
    # The combined string always contains a negation pattern, so it must fire.
    assert _has_negation(combined) is True


# ---------------------------------------------------------------------------
# M. Manifest pin — _NEGATION_PATTERNS must be exactly 11 items
# ---------------------------------------------------------------------------


def test_M1_negation_patterns_is_exact_11_item_frozenset() -> None:
    """Hard-pin ``_NEGATION_PATTERNS`` to the methodology-approved 11-item set.

    Adding or removing a pattern requires a deliberate test update AND a
    methodology-scientist Mode B re-validation per AGENTS.md §Testing coverage
    policy ("add a test when a new defense ships").
    """
    expected: frozenset[str] = frozenset({
        "terminated",
        "cancelled",
        "canceled",
        "expired",
        "rescinded",
        "discontinued",
        "no",
        "not in effect",
        "previously",
        "former",
        "without",
    })
    assert _NEGATION_PATTERNS == expected
    assert len(_NEGATION_PATTERNS) == 11


def test_M2_negation_regex_is_compiled_pattern() -> None:
    """``_NEGATION_REGEX`` must be a compiled ``re.Pattern`` (not a raw string)
    so that repeated calls don't re-compile on every invocation."""
    import re

    assert isinstance(_NEGATION_REGEX, re.Pattern)
    # Sanity: the pattern is case-insensitive and verbose (flags set in the
    # inline ``(?ix)`` group — re.IGNORECASE | re.VERBOSE).
    assert _NEGATION_REGEX.flags & re.IGNORECASE
    assert _NEGATION_REGEX.flags & re.VERBOSE


def test_M3_negation_patterns_each_appear_in_compiled_regex() -> None:
    """Drift-detector: every token in ``_NEGATION_PATTERNS`` must appear
    somewhere in the compiled ``_NEGATION_REGEX.pattern`` source string.

    Without this pin, someone could:
    1. Add a 12th token to ``_NEGATION_PATTERNS`` without wiring it into
       the regex alternation → frozenset claims coverage that the actual
       guard doesn't deliver.
    2. Remove a token from the regex alternation without bumping
       ``_NEGATION_PATTERNS`` → frozenset overstates coverage.

    The carve-outs handle:
    - ``cancelled`` (double-L) and ``canceled`` (single-L) both appear in
      ``_NEGATION_PATTERNS``; the regex collapses them to one
      ``cancell?ed`` token, so we substring-match the shared prefix
      ``cancel``.
    - ``not in effect`` is multi-word; the regex uses ``\\s+`` for the
      inner space, so we substring-match the visible-word fragments
      ``not`` and ``effect`` separately.
    - ``no`` is BEFORE-only by design (see ``_NEGATION_REGEX`` BEFORE
      NOTE); the pattern still appears in the source string of the
      BEFORE branch, so plain substring search succeeds.
    """
    pattern_source = _NEGATION_REGEX.pattern.lower()

    for token in _NEGATION_PATTERNS:
        if token in ("cancelled", "canceled"):
            assert "cancel" in pattern_source, (
                f"_NEGATION_PATTERNS contains {token!r} but the "
                "regex source string is missing the 'cancel' "
                "stem — drift detected."
            )
        elif token == "not in effect":
            assert "not" in pattern_source and "effect" in pattern_source, (
                "_NEGATION_PATTERNS contains 'not in effect' but the "
                "regex source string is missing 'not' or 'effect' — "
                "drift detected."
            )
        else:
            assert token in pattern_source, (
                f"_NEGATION_PATTERNS contains {token!r} but the regex "
                "source string is missing it — drift detected."
            )
