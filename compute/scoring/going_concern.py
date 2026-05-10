"""Going-concern phrase scan (Phase 3d Defense #8, annotate-only).

Scans 10-K / 10-Q filing text for going-concern indicator phrases drawn
from the Loughran-McDonald financial dictionary subset documented in
Mayew-Sethuraman-Venkatachalam 2015 *The Accounting Review*,
"MD&A Disclosure and the Firm's Ability to Continue as a Going Concern".

The original Mayew et al. study found that mere mention of going-concern
phrases in MD&A predicts subsequent bankruptcy or restatement at a
statistically significant rate, even when the disclosure is accompanied
by management's denial. We therefore use **mere mention** as the signal
— context analysis (positive vs. negative framing, hedging language) is
out of scope for this annotate-only flag. The expected false-positive
rate is non-trivial because some filings cite going-concern phrases
when describing peers or historical events; that's acceptable here
because the flag does **not** veto, only annotate.

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
- Mayew, Sethuraman, Venkatachalam (2015) — *The Accounting Review*
  90(4):1621-51, "MD&A Disclosure and the Firm's Ability to Continue
  as a Going Concern".
- Loughran, McDonald (2011) — *Journal of Finance* 66:35-65,
  "When is a Liability not a Liability? Textual Analysis,
  Dictionaries, and 10-Ks".
- SEC AS 2415 / ASU 2014-15 — going-concern disclosure standards
  governing the boilerplate language matched here.
"""

from __future__ import annotations

import re
from typing import Final

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


def scan_going_concern(text: str | None) -> bool:
    """Return True if any going-concern phrase appears in ``text``.

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
        True iff at least one phrase from :data:`GOING_CONCERN_PHRASES`
        appears in ``text`` (case-insensitive, hyphen / whitespace
        flexible). Returns False for ``None``, empty string, or any
        text where no phrase fires.

        Note: a False return means *no signal*, not *signal is absent*.
        Callers distinguish "we couldn't fetch the filing" from "we
        fetched it and it's clean" via the surrounding pipeline (see
        ``Metadata.tier2_coverage_pct``).
    """
    if text is None or not text:
        return False
    for pattern in _COMPILED_PATTERNS:
        if pattern.search(text):
            return True
    return False


__all__ = [
    "GOING_CONCERN_PHRASES",
    "scan_going_concern",
]
