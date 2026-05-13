"""Going-concern phrase scan (Phase 3d Defense #8, annotate-only).

Scans 10-K / 10-Q filing text for going-concern indicator phrases drawn
from the Loughran-McDonald financial dictionary subset documented in
Mayew-Sethuraman-Venkatachalam 2015 *The Accounting Review*,
"MD&A Disclosure and the Firm's Ability to Continue as a Going Concern".

The original Mayew et al. study found that mere mention of going-concern
phrases in MD&A predicts subsequent bankruptcy or restatement at a
statistically significant rate. **However**, Run #15 production
verification surfaced a 10.8% FP rate on the S&P 500 universe (54/502)
— well above Mayew's expected 1-3% range. Two-stage Phase 4 fix:

**Stage 1 (PR #35, Option A — negation lookbehind)**: after a phrase
match fires, look at the ~60 characters preceding the match within the
same sentence; if a negation token (``no`` / ``not`` / ``without`` /
``absent`` / multi-word forms like ``has not identified``) appears in
that window, drop the match. Sentence-level propagation: if ANY phrase
match in the sentence is locally negated, drop the whole sentence.

**Stage 2 (this PR, Option B — MD&A-section restriction)**: post-
verification on Run @ commit ``bdb49ee`` showed Stage 1 dropped only 1
of 54 firing tickers (54 → 53 = 10.6%, still well above the 5% target).
The dominant FP class was NOT negation prose but **off-section
mentions** — phrases appearing in Risk Factors (Item 1A), Forward-
Looking Statements, or peer-comparison narrative that are textually
about going concern but not in the section that Mayew 2015 studied.
Restrict the scan to the **Item 7 / MD&A section** before applying the
Stage-1 negation logic. If the MD&A boundary can't be identified, fall
back to full-text scan with a logged warning (gracefully degrade — same
FP rate as Stage 1 alone, never worse).

Per SKILL.md Rule 16, this defense **never** modifies the composite
score. It surfaces in ``StockDetail.tier2_events.going_concern_disclosure``
and the user-visible flag list on the detail page.

Source / license note
---------------------

Master Dictionary © 2011-present Tim Loughran and Bill McDonald,
University of Notre Dame. The dictionary is published under
Creative Commons Attribution 4.0 International (CC BY 4.0). The phrase
subset below is a *curated* extract of going-concern + restatement
indicators relevant to S&P 500 issuers; it is not the complete
dictionary, and we do not redistribute the full file.

References
----------
- Mayew, W., Sethuraman, M., Venkatachalam, M. (2015). *The Accounting
  Review* 90(4):1621-51, "MD&A Disclosure and the Firm's Ability to
  Continue as a Going Concern".
- Loughran, McDonald (2011) — *Journal of Finance* 66:35-65,
  "When is a Liability not a Liability? Textual Analysis,
  Dictionaries, and 10-Ks".
- SEC AS 2415 / ASU 2014-15 — going-concern disclosure standards
  governing the boilerplate language matched here.
- Regulation S-K Item 303 — defines the MD&A scope used by Stage 2.
"""

from __future__ import annotations

import logging
import re
from typing import Final

logger = logging.getLogger(__name__)

# Locked phrase set. New phrases require a separate review (signal
# semantics matter — we don't want to dilute the flag with low-precision
# matches like "we are concerned about market conditions").
GOING_CONCERN_PHRASES: Final[tuple[str, ...]] = (
    "substantial doubt",
    "going concern",
    "ability to continue as a going concern",
    "material uncertainty related to going concern",
    "raise substantial doubt about",
    "substantial doubt about its ability",
    "substantial doubt about our ability",
    "doubt about the Company's ability to continue",
    "doubt about the entity's ability to continue",
    "questions about the Company's ability to continue",
    "negative cash flow from operations",
    "may be unable to continue",
    "going concern qualification",
    "going concern uncertainty",
)


def _build_pattern(phrase: str) -> re.Pattern[str]:
    """Build a case-insensitive, whitespace/hyphen-flexible regex.

    The pattern:
    - escapes the phrase to neutralize any regex metacharacters
    - replaces every escaped space with ``[\\s\\-]+`` so the match
      tolerates multiple spaces, line breaks, and hyphens between words
      (e.g., ``"going-concern"`` matches ``"going concern"``)
    - anchors with ``\\b`` at the start of the first word and the end
      of the last word so partial-word matches (``"ongoing concerns"``,
      ``"discontinued"``) don't trip the flag
    """
    escaped = re.escape(phrase)
    flexed = escaped.replace(r"\ ", r"[\s\-]+")
    return re.compile(rf"\b{flexed}\b", re.IGNORECASE)


_COMPILED_PATTERNS: Final[tuple[re.Pattern[str], ...]] = tuple(
    _build_pattern(p) for p in GOING_CONCERN_PHRASES
)


# Negation tokens that, when appearing in the 60-char window before a
# phrase match, mark the match as negated. Captures the patterns
# explicitly listed in issue #16:
#
# - "no substantial doubt" / "no material uncertainty" / "no doubt about"
# - "Management believes there is no ..."
# - "we have not identified ..." / "has not identified ..."
# - "without" / "absent" risk-factor phrasing
#
# Multi-word forms like "has not identified" let us catch the longer
# negation patterns when they sit within the local 60-char window.
_NEGATION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"""
    \b(?:
        no                                              # "no [phrase]"
      | not                                             # "not [phrase]"
      | without                                         # "without [phrase]"
      | absent                                          # "absent [phrase]"
      | denies | denied | dismisses | dismissed
      | (?:has|have|had)\s+not\s+(?:identified|noted|raised|believed)
      | believes?\s+(?:there\s+is\s+)?no
      | does\s+not\s+(?:believe|indicate|raise|create)
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# 60-char window before each phrase match. Empirically wide enough to
# catch "Management believes there is no material uncertainty..." (the
# longest negation pattern from issue #16) while staying tight enough to
# avoid claiming distant negation applies (e.g., "no operations" 100
# chars before "substantial doubt" attaches to "operations", not the
# phrase).
_NEGATION_WINDOW: Final[int] = 60

# Sentence splitter. Used to (a) clip the negation window so prior-
# sentence negation doesn't leak across boundaries, and (b) propagate a
# local-negation hit on one phrase match to all other phrase matches in
# the same sentence (issue #16's H8 case: one negation verb "has not
# identified" sits within local range of "substantial doubt" but >60
# chars from the later "going concern" — without sentence-level
# propagation, "going concern" would fire non-negated even though the
# entire sentence is semantically negative).
_SENTENCE_SPLIT: Final[re.Pattern[str]] = re.compile(r"(?<=[.!?])\s+")

# Stage 2 (Option B): MD&A section boundary detection. 10-K filings
# follow Reg S-K Item 303 — the MD&A lives at Item 7, bounded above by
# Item 6 (Selected Financial Data) and below by Item 7A (Quantitative
# and Qualitative Disclosures About Market Risk) / Item 8 (Financial
# Statements). The going-concern phrase scan should run ONLY on the
# MD&A text — off-section mentions (Risk Factors / Forward-Looking
# Statements / Item 1A) routinely cite going-concern phrases when
# describing peers or hypothetical scenarios.
#
# We look for "Item 7" as a section header (NOT followed by "A") and
# take the LAST occurrence — earlier occurrences typically live in the
# Table of Contents. The end boundary is the FIRST "Item 7A" or
# "Item 8" after the chosen "Item 7".
#
# Whitespace flexibility: edgartools' BeautifulSoup.get_text(" ")
# output flattens line breaks into single spaces, so the regex doesn't
# need multi-line anchoring. Case-insensitive to handle the mix of
# "Item 7." / "ITEM 7." / "PART II, ITEM 7" forms seen in practice.

_MDA_START_RE: Final[re.Pattern[str]] = re.compile(
    r"\bitem\s+7\b(?!\s*[Aa])",
    re.IGNORECASE,
)
_MDA_END_RE: Final[re.Pattern[str]] = re.compile(
    r"\bitem\s+(?:7\s*[Aa]|8)\b",
    re.IGNORECASE,
)


def _extract_mda_section(text: str) -> str | None:
    """Return the MD&A (Item 7) substring of a 10-K narrative.

    Heuristic: the LAST ``Item 7`` (not followed by ``A``) is the body
    section header (earlier occurrences are typically in the Table of
    Contents). The closing boundary is the first ``Item 7A`` or
    ``Item 8`` that appears AFTER the chosen start.

    Returns ``None`` when the boundary can't be located — callers fall
    back to scanning the full text (worst case: same FP rate as
    Stage-1 alone, never worse than today).
    """
    starts = list(_MDA_START_RE.finditer(text))
    if not starts:
        return None
    # Take the LAST "Item 7" — earlier occurrences are TOC entries.
    start = starts[-1].start()
    end_match = _MDA_END_RE.search(text, pos=start + 1)
    if end_match is None:
        # No closing boundary found — take from start to EOF rather
        # than abandoning the restriction entirely. Section-end
        # markers are sometimes truncated in the cached extraction.
        return text[start:]
    return text[start:end_match.start()]


def _is_locally_negated(sentence: str, match_start: int) -> bool:
    """True iff a negation token appears within 60 chars before ``match_start``.

    ``sentence`` is already clipped at sentence boundaries by the caller,
    so we don't risk crossing into a prior sentence's text.
    """
    window_start = max(0, match_start - _NEGATION_WINDOW)
    return bool(_NEGATION_PATTERN.search(sentence[window_start:match_start]))


def scan_going_concern(text: str | None) -> bool:
    """Return True iff a non-negated going-concern phrase appears.

    Splits ``text`` into sentences. For each sentence that contains at
    least one phrase match, the sentence is considered **negative-
    framed** (skipped) if ANY of its phrase matches is locally negated
    (negation token within 60 chars before the match). Otherwise the
    sentence is a positive signal → return True.

    This handles three FP classes from issue #16:

    1. Direct: ``"there is no substantial doubt"`` — local "no" attaches
       to the immediate phrase.
    2. Multi-phrase: ``"Management has not identified ... substantial
       doubt ... going concern"`` — local "has not" attaches to the
       first phrase, sentence-level propagation drops the later phrases
       that would have escaped a per-match-only check.
    3. Cross-sentence false alarm: ``"We have no operations. There is
       substantial doubt..."`` — sentence split prevents the first
       sentence's "no" from negating the second sentence's phrase.

    And preserves H14-class TRUE positives:

    4. Distant unrelated negation: ``"has no operations whatsoever in
       region X, and the auditor has raised substantial doubt..."`` —
       "no" is >60 chars from the phrase → not locally negated → not
       propagated → sentence fires positive.

    Parameters
    ----------
    text:
        Raw filing body (10-K Item 7 / 10-Q discussion). May contain
        line breaks, multiple spaces, and HTML entities — the regex
        layer is tolerant of whitespace variation but will not strip
        HTML tags. Callers that ingest HTML directly should pre-strip
        with BeautifulSoup before passing here.

    Returns
    -------
    bool
        True iff at least one sentence contains a phrase from
        :data:`GOING_CONCERN_PHRASES` AND no phrase in that sentence is
        locally negated. Returns False for ``None`` / empty / all-
        sentences-negated text.

        Note: a False return means *no signal we trust*, not *signal
        is absent in the filing*. Callers distinguish "we couldn't
        fetch the filing" from "we fetched it and it's clean (or all
        negated)" via the surrounding pipeline (see
        ``Metadata.tier2_coverage_pct``).
    """
    if text is None or not text:
        return False
    # Stage 2 (Option B): restrict to MD&A (Item 7) when the section
    # boundary is identifiable. Falls back to full text when not — that
    # keeps the worst case at parity with Stage 1 alone.
    mda = _extract_mda_section(text)
    if mda is None:
        logger.debug(
            "scan_going_concern: MD&A boundary not found in %d-char text; "
            "falling back to full-text scan",
            len(text),
        )
        scan_target = text
    else:
        scan_target = mda
    sentences = _SENTENCE_SPLIT.split(scan_target)
    for sentence in sentences:
        matches: list[re.Match[str]] = []
        for pattern in _COMPILED_PATTERNS:
            matches.extend(pattern.finditer(sentence))
        if not matches:
            continue
        # Sentence-level propagation: if ANY phrase match in this
        # sentence is locally negated, drop the whole sentence as
        # negative-framed (H8 case from the issue).
        if any(_is_locally_negated(sentence, m.start()) for m in matches):
            continue
        return True
    return False


__all__ = [
    "GOING_CONCERN_PHRASES",
    "scan_going_concern",
]
