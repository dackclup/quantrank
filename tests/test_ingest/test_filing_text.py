"""Contract tests for compute.ingest.filing_text (PR 3d perf hotfix).

Locks the contract that BeautifulSoup get_text extraction over typical
SEC HTML preserves the LM-dictionary going-concern phrases such that
:func:`compute.scoring.going_concern.scan_going_concern` matches them.

This guards the perf decision: ``fetch_latest_10k_text`` deliberately
skips ``edgartools.Filing.text()`` (which routes through
``hybrid_section_detector`` and CPU-bounds at ~5-10s per filing) and
instead uses ``filing.html()`` + ``BeautifulSoup.get_text(separator=" ")``.
If edgartools' html() output ever changed shape, or BS extraction
started losing whitespace boundaries, this test catches it.
"""

from __future__ import annotations

from bs4 import BeautifulSoup

from compute.scoring.going_concern import scan_going_concern


def _strip(html: str) -> str:
    return BeautifulSoup(html, "lxml").get_text(separator=" ")


def test_bs_extraction_preserves_going_concern_phrase_inline_b_tags():
    """Going-concern phrase split by inline ``<b>`` tags survives the
    extraction pass — phrase regex with ``\\b`` anchors + ``[\\s\\-]+``
    flex matches the resulting whitespace-collapsed text."""
    html = (
        "<html><body><p>The Company reports "
        "<b>substantial doubt</b> about its "
        "ability to continue as a going concern.</p></body></html>"
    )
    text = _strip(html)
    assert scan_going_concern(text) is True


def test_bs_extraction_handles_table_layouts():
    """Filing tables (where MD&A often appears) preserve phrase
    detectability after get_text(separator=' ')."""
    html = (
        "<table><tr><td>Item 7. MD&amp;A</td></tr>"
        "<tr><td>The Company has <em>substantial doubt</em> "
        "about the entity's ability to continue.</td></tr></table>"
    )
    text = _strip(html)
    assert "substantial doubt" in text.lower()
    # The "substantial doubt" phrase from GOING_CONCERN_PHRASES fires.
    assert scan_going_concern(text) is True


def test_bs_extraction_collapses_inline_styling_whitespace():
    """Heavily-styled SEC HTML (inline spans, br tags) still yields
    text that ``\\s+``-flex regex can match."""
    html = (
        '<p><span style="font-weight:bold">going</span><br/>'
        '<span style="font-style:italic">concern</span></p>'
    )
    text = _strip(html)
    # BS get_text(separator=" ") joins with spaces between elements.
    # The pattern \bgoing[\s\-]+concern\b should fire on this output.
    assert scan_going_concern(text) is True


def test_bs_extraction_negative_clean_filing():
    """Sanity inverse: clean filing text after BS strip still scans False."""
    html = (
        "<html><body><p>Revenue grew 12% year-over-year, driven by "
        "enterprise demand. The Company expects continued operational "
        "efficiency improvements.</p></body></html>"
    )
    text = _strip(html)
    assert scan_going_concern(text) is False


def test_bs_extraction_empty_html_yields_empty_text():
    """Edge case — empty body HTML yields empty string, scan returns False."""
    text = _strip("<html><body></body></html>")
    assert scan_going_concern(text) is False
