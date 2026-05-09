"""Tangible Book Value per Share (TBVPS) — Defense Playbook §PR 3c #2.

TBVPS subtracts both goodwill **and** other identifiable intangibles from
reported book equity before per-share normalization (Penman 2013, *Financial
Statement Analysis and Security Valuation*; Damodaran's tangible-book
treatment of acquirers). The full netting is the conservative practitioner
default — half-netting (goodwill only) is acceptable when intangibles
tagging is unreliable, but Phase 3 Step 1's 3-tag fallback chain
(`us-gaap:IntangibleAssetsNetExcludingGoodwill` →
`us-gaap:OtherIntangibleAssetsNet` →
`us-gaap:FiniteLivedIntangibleAssetsNet`) targets ≥85% intangibles coverage
on S&P 500, so we ship full netting by default and accept ``None`` for the
tail of stocks where intangibles tag isn't found at all.

**Intentional dual implementation**: ``compute/features/value.py``'s
``graham_number()`` uses the *reported* book value per share (no netting),
which keeps the Value pillar fast and aligned with Graham 1949's original
formulation. The fair-price ensemble — which feeds the user-facing
``fair_price`` field rather than a normalized pillar — uses TBVPS instead
because over-paying for goodwill is a Phase-3c-era concern that didn't
exist when Graham wrote. Graph the two side-by-side on the stock detail
page (Phase 3d) to surface the divergence.

Usage anchors (subsequent steps):
- Step 4.2 (graham.py): ``graham_value(snap, current_price, tbvps=…)``
- Step 4.4 (rim.py): RIM terminal book uses TBVPS for tangible-equity ROE
- Step 5 (ensemble.py): ``goodwill_heavy`` flag joins ``valuation_warnings``
"""

from __future__ import annotations

from compute import config
from compute.ingest.fundamentals import FundamentalsSnapshot


def tangible_book_value_per_share(snap: FundamentalsSnapshot) -> float | None:
    """Return TBVPS = (equity − goodwill − intangibles_net) / shares.

    Returns ``None`` when:

    - ``stockholders_equity`` is missing
    - ``shares_outstanding`` is missing or zero
    - tangible book is non-positive (the firm's identifiable + indefinite-
      life intangible assets exceed reported book equity — the firm is on
      a going-concern footing only because of intangibles' carrying value)

    Missing ``goodwill`` or ``intangibles_net`` are coerced to ``0.0``
    (consistent with the Phase-3c fallback chain achieving ~85% intangibles
    coverage; the remaining ~15% with no intangibles tag are treated as
    having zero intangibles, which is the most-conservative-but-imperfect
    default).

    Parameters
    ----------
    snap : FundamentalsSnapshot
        Latest fundamentals snapshot. Reads ``stockholders_equity``,
        ``goodwill``, ``intangibles_net``, ``shares_outstanding``.

    Returns
    -------
    float | None
        TBVPS in same currency as equity (USD for S&P 500), or ``None`` if
        unusable.

    Examples
    --------
    >>> # equity=100, goodwill=30, intangibles=20, shares=10 → TBVPS=5.0
    """
    if snap.stockholders_equity is None:
        return None
    if snap.shares_outstanding in (None, 0):
        return None

    equity = float(snap.stockholders_equity)
    goodwill = float(snap.goodwill or 0.0)
    intangibles = float(snap.intangibles_net or 0.0)
    shares = float(snap.shares_outstanding)

    tangible_book = equity - goodwill - intangibles
    if tangible_book <= 0:
        return None

    tbvps = tangible_book / shares
    if tbvps <= 0:
        return None
    return tbvps


def goodwill_heavy_flag(
    snap: FundamentalsSnapshot, tbvps: float | None
) -> bool:
    """Return True if TBVPS / BVPS_reported < ``GOODWILL_HEAVY_RATIO`` (0.5).

    Annotate-only flag for stock detail UI. Surfaces stocks where a large
    fraction of book equity is goodwill+intangibles — typically post-
    acquisition firms (e.g., GE 2018-style writedown risk; conglomerate
    serial acquirers). NOT a veto: composite stays unchanged. The ensemble
    step (5) will append ``goodwill_heavy`` to ``valuation_warnings`` when
    this returns True.

    Returns ``False`` when:

    - ``tbvps`` is ``None`` (cannot compute the ratio)
    - reported BVPS is non-positive (e.g., MCD-style buyback-into-deficit
      firms; the ratio is mathematically undefined / not meaningful)
    - ``shares_outstanding`` is missing or zero

    Parameters
    ----------
    snap : FundamentalsSnapshot
        Used to compute reported BVPS = stockholders_equity / shares.
    tbvps : float | None
        Result of ``tangible_book_value_per_share(snap)``. Pass through
        directly — re-computing wastes work.

    Returns
    -------
    bool
        True iff the firm's reported equity is ≥50% goodwill+intangibles.
    """
    if tbvps is None:
        return False
    if snap.shares_outstanding in (None, 0):
        return False
    if snap.stockholders_equity is None or snap.stockholders_equity <= 0:
        return False

    bvps_reported = float(snap.stockholders_equity) / float(snap.shares_outstanding)
    if bvps_reported <= 0:
        return False
    return (tbvps / bvps_reported) < config.GOODWILL_HEAVY_RATIO
