"""Fair-price ensemble + Tier-1 defense modules (Phase 3c).

Public surface re-exported here so the rest of ``compute/`` can import via
``from compute.valuation import tangible_book_value_per_share``. Individual
sub-modules document their own preconditions and source citations:

- ``tangible_book`` — TBVPS = (equity − goodwill − intangibles) / shares.
  Used by Graham + RIM in fair-price computation; NOT used in the Value
  pillar (compute/features/value.py keeps the fast-TTM Graham
  intentionally — dual implementation per the kickoff §B4 spec).

Subsequent steps add ``applicability``, ``dcf``, ``graham``, ``rim``,
``multiples``, ``ensemble``.
"""

from __future__ import annotations

from compute.valuation.tangible_book import (
    goodwill_heavy_flag,
    tangible_book_value_per_share,
)

__all__ = [
    "goodwill_heavy_flag",
    "tangible_book_value_per_share",
]
