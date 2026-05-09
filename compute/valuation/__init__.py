"""Fair-price ensemble + Tier-1 defense modules (Phase 3c).

Public surface re-exported here so the rest of ``compute/`` can import via
``from compute.valuation import tangible_book_value_per_share``. Individual
sub-modules document their own preconditions and source citations:

- ``tangible_book`` — TBVPS = (equity − goodwill − intangibles) / shares.
  Used by Graham + RIM in fair-price computation; NOT used in the Value
  pillar (compute/features/value.py keeps the fast-TTM Graham
  intentionally — dual implementation per the kickoff §B4 spec).
- ``applicability`` — per-method applicability gates + stale-filing
  primitives (Defense #3). Pure functions with stable snake_case ``reason``
  strings; Step 5 ensemble pattern-matches to populate
  ``StockDetail.fair_price.methods.<method>.reason``.
- ``graham`` — defense-aware Graham number using TBVPS + 3y-avg EPS.
- ``multiples`` — sector P/E + P/B + EV/EBITDA with 4-tier peer-median walk
  and 5/95 winsorization.

Subsequent steps add ``rim``, ``dcf``, ``ensemble``.
"""

from __future__ import annotations

from compute.valuation.applicability import (
    LagStatus,
    MethodApplicability,
    check_dcf_applicability,
    check_graham_applicability,
    check_multiples_ev_ebitda_applicability,
    check_multiples_pb_applicability,
    check_multiples_pe_applicability,
    check_rim_applicability,
    filing_lag_days,
    stale_filing_status,
)
from compute.valuation.graham import graham_fair_price
from compute.valuation.multiples import (
    PeerMedian,
    PeerTierUsed,
    compute_peer_medians,
    multiples_ev_ebitda_fair_price,
    multiples_pb_fair_price,
    multiples_pe_fair_price,
)
from compute.valuation.tangible_book import (
    goodwill_heavy_flag,
    tangible_book_value_per_share,
)

__all__ = [
    # tangible_book
    "goodwill_heavy_flag",
    "tangible_book_value_per_share",
    # applicability
    "LagStatus",
    "MethodApplicability",
    "check_dcf_applicability",
    "check_graham_applicability",
    "check_multiples_ev_ebitda_applicability",
    "check_multiples_pb_applicability",
    "check_multiples_pe_applicability",
    "check_rim_applicability",
    "filing_lag_days",
    "stale_filing_status",
    # graham
    "graham_fair_price",
    # multiples
    "PeerMedian",
    "PeerTierUsed",
    "compute_peer_medians",
    "multiples_ev_ebitda_fair_price",
    "multiples_pb_fair_price",
    "multiples_pe_fair_price",
]
