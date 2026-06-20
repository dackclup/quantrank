"""Tests for multi-index membership feature — Dow 30 + NDX 100 overlap tabs.

Covers (0.10.23-phase8pilot):
  1. derive_index_memberships — pure derivation logic (unit tests + Hypothesis
     property test).
  2. Schema round-trips: index_memberships on StockSummary + StockDetail;
     legacy default ([]); extra="forbid" still enforced.
  3. HTML parser tests for _parse_dow30_html + _parse_ndx_html (NO network —
     fixture HTML strings supplied inline).
  4. Graceful-degradation: malformed table → empty set, no raise.
  5. Sanity-band: Dow ≠ 30 → assertion rejected (empty set); NDX outside
     [95, 105] → rejected.
  6. Ledger-unchanged regression: verify_membership_ledger.current_universe()
     reads index_membership (singular); introducing index_memberships
     (plural) must NOT change its output.

All tests are offline (no network calls, no filesystem writes beyond tmp_path).
"""
from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest

# ---------------------------------------------------------------------------
# 1. derive_index_memberships — pure unit tests
# ---------------------------------------------------------------------------


class TestDeriveIndexMemberships:
    """Unit tests for the pure derive_index_memberships helper."""

    def test_sp500_only_no_overlaps(self):
        """An sp500 ticker not in Dow30 or NDX returns ['sp500'] only."""
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships(
            "XYZ", cohort="sp500", dow30={"AAPL", "MSFT"}, ndx={"AAPL", "GOOGL"}
        )
        assert result == ["sp500"]

    def test_sp500_in_dow30_only(self):
        """sp500 ticker in Dow30 but not NDX → ['sp500', 'dow30']."""
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships(
            "WMT", cohort="sp500", dow30={"WMT", "TRV"}, ndx={"AAPL"}
        )
        assert result == ["sp500", "dow30"]

    def test_sp500_in_ndx_only(self):
        """sp500 ticker in NDX but not Dow30 → ['sp500', 'ndx']."""
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships(
            "GOOGL", cohort="sp500", dow30={"AAPL"}, ndx={"GOOGL", "META"}
        )
        assert result == ["sp500", "ndx"]

    def test_sp500_in_both_dow30_and_ndx(self):
        """sp500 ticker in both Dow30 + NDX → ['sp500', 'dow30', 'ndx']."""
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships(
            "AAPL",
            cohort="sp500",
            dow30={"AAPL", "MSFT"},
            ndx={"AAPL", "MSFT", "GOOGL"},
        )
        assert result == ["sp500", "dow30", "ndx"]

    def test_sp400_only(self):
        """sp400 midcap ticker not in Dow30/NDX → ['sp400'] only."""
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships(
            "BRKR", cohort="sp400", dow30={"AAPL"}, ndx={"AAPL"}
        )
        assert result == ["sp400"]

    def test_primary_cohort_always_first(self):
        """Primary cohort is always the first element."""
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships(
            "AAPL", cohort="sp500", dow30={"AAPL"}, ndx={"AAPL"}
        )
        assert result[0] == "sp500"

    def test_empty_dow30_and_ndx_sets(self):
        """When both sets are empty (degraded fetch), returns [cohort] only."""
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships("AAPL", cohort="sp500", dow30=set(), ndx=set())
        assert result == ["sp500"]

    def test_empty_dow30_set(self):
        """Empty dow30 → ndx membership still works."""
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships(
            "AAPL", cohort="sp500", dow30=set(), ndx={"AAPL"}
        )
        assert result == ["sp500", "ndx"]

    def test_empty_ndx_set(self):
        """Empty ndx → dow30 membership still works."""
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships(
            "MSFT", cohort="sp500", dow30={"MSFT"}, ndx=set()
        )
        assert result == ["sp500", "dow30"]

    def test_result_is_list_not_set(self):
        """Return type must be list, not set (ordering contract)."""
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships(
            "AAPL", cohort="sp500", dow30={"AAPL"}, ndx={"AAPL"}
        )
        assert isinstance(result, list)

    def test_no_duplicates(self):
        """No duplicate codes in the result."""
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships(
            "AAPL", cohort="sp500", dow30={"AAPL"}, ndx={"AAPL"}
        )
        assert len(result) == len(set(result))


# ---------------------------------------------------------------------------
# 1b. russell1000 proxy — new market_cap branch (0.10.23+ / russell1000 tag)
# ---------------------------------------------------------------------------


class TestRussell1000Membership:
    """Tests for the russell1000 proxy tag added to derive_index_memberships.

    Production rule: append "russell1000" iff market_cap is not None and > 0.
    Ordering: cohort → dow30 → ndx → russell1000.
    """

    def test_sp900_ticker_with_positive_cap_gets_russell1000(self):
        """Positive market_cap → 'russell1000' appended; exact order preserved."""
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships(
            "AAPL", cohort="sp500", dow30=set(), ndx=set(), market_cap=1_000_000_000
        )
        assert result == ["sp500", "russell1000"]
        assert "russell1000" in result

    def test_sp900_ticker_with_none_cap_no_russell1000(self):
        """market_cap=None (missing snapshot) → 'russell1000' NOT in result."""
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships(
            "AAPL", cohort="sp500", dow30=set(), ndx=set(), market_cap=None
        )
        assert "russell1000" not in result

    def test_sp900_ticker_with_zero_cap_no_russell1000(self):
        """market_cap=0.0 (zero) → 'russell1000' NOT in result."""
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships(
            "AAPL", cohort="sp500", dow30=set(), ndx=set(), market_cap=0.0
        )
        assert "russell1000" not in result

    def test_sp900_ticker_with_negative_cap_no_russell1000(self):
        """market_cap=-1.0 (defensive boundary) → 'russell1000' NOT in result."""
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships(
            "AAPL", cohort="sp500", dow30=set(), ndx=set(), market_cap=-1.0
        )
        assert "russell1000" not in result

    def test_all_memberships_ordering_contract(self):
        """Ticker in dow30 AND ndx AND positive cap → exact ordering contract."""
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships(
            "AAPL",
            cohort="sp500",
            dow30={"AAPL"},
            ndx={"AAPL"},
            market_cap=3_000_000_000_000,
        )
        assert result == ["sp500", "dow30", "ndx", "russell1000"]

    def test_sp400_ticker_with_positive_cap_gets_russell1000(self):
        """sp400 midcap with positive market_cap → exact ['sp400', 'russell1000']."""
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships(
            "BRKR", cohort="sp400", dow30=set(), ndx=set(), market_cap=5_000_000_000
        )
        assert result == ["sp400", "russell1000"]

    def test_dow30_and_ndx_unaffected_by_market_cap(self):
        """dow30/ndx membership is unchanged whether market_cap is supplied or not."""
        from compute.ingest.universe import derive_index_memberships

        # Without market_cap — dow30 + ndx still both present
        result_no_cap = derive_index_memberships(
            "AAPL", cohort="sp500", dow30={"AAPL"}, ndx={"AAPL"}
        )
        # With market_cap — dow30 + ndx still both present (russell1000 also added)
        result_with_cap = derive_index_memberships(
            "AAPL", cohort="sp500", dow30={"AAPL"}, ndx={"AAPL"}, market_cap=1e12
        )
        # Both should carry dow30 and ndx regardless
        assert "dow30" in result_no_cap
        assert "ndx" in result_no_cap
        assert "dow30" in result_with_cap
        assert "ndx" in result_with_cap
        # Only result_with_cap carries russell1000
        assert "russell1000" not in result_no_cap
        assert "russell1000" in result_with_cap

    def test_singular_index_membership_semantics_unchanged(self):
        """russell1000 is an ADDITIVE code; cohort is always memberships[0].

        Documents that derive_index_memberships never conflates cohort codes
        with russell1000: the first element is always the primary cohort, and
        russell1000 can only appear as a trailing additive element — never in
        position [0] where it could be confused with the singular
        index_membership field (set from cohort_by_ticker, not this helper).
        """
        from compute.ingest.universe import derive_index_memberships

        for cohort in ("sp500", "sp400"):
            result = derive_index_memberships(
                "XYZ", cohort=cohort, dow30=set(), ndx=set(), market_cap=1e9
            )
            # Primary cohort is always first
            assert result[0] == cohort, (
                f"Expected cohort {cohort!r} first, got {result!r}"
            )
            # russell1000 is additive — never in position 0
            assert result.index("russell1000") > 0, (
                f"russell1000 must not be at position 0 in {result!r}"
            )

    def test_russell1000_not_tagged_for_sp600_cohort(self):
        """sp600 ticker with well-above-cutoff market_cap must NOT receive 'russell1000'.

        Slice 2 Rule-18 guard: the 'S&P 900 ⊂ Russell 1000' structural argument
        does NOT hold for S&P 600 small-caps.  derive_index_memberships must
        suppress the russell1000 proxy tag for cohort=='sp600' regardless of
        market_cap value — even a clearly above-cutoff cap (5e9) must not trigger it.
        """
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships(
            "SML1",
            cohort="sp600",
            dow30=set(),
            ndx=set(),
            market_cap=5_000_000_000,  # well above any Russell 1000 cutoff
        )
        assert "russell1000" not in result, (
            f"russell1000 must NOT be tagged for sp600 cohort, got {result!r}"
        )
        # The primary cohort should still be present and first
        assert result[0] == "sp600"

    def test_russell1000_tagged_for_sp500_sp400_cohorts(self):
        """sp500 and sp400 tickers with positive market_cap both receive 'russell1000'.

        Regression guard: the sp600 suppression guard must not over-broaden and
        accidentally remove the russell1000 tag from sp500 or sp400 tickers.
        The structural argument 'S&P 900 ⊂ Russell 1000' holds for both cohorts.
        """
        from compute.ingest.universe import derive_index_memberships

        for cohort in ("sp500", "sp400"):
            result = derive_index_memberships(
                "AAPL",
                cohort=cohort,
                dow30=set(),
                ndx=set(),
                market_cap=1_000_000_000,  # positive cap → should get russell1000
            )
            assert "russell1000" in result, (
                f"russell1000 must be tagged for cohort={cohort!r} with positive market_cap, "
                f"got {result!r}"
            )
            assert result[0] == cohort, (
                f"Primary cohort {cohort!r} must be first in {result!r}"
            )

    def test_main_memberships_by_ticker_russell1000_wiring(self):
        """Integration smoke for the main.py memberships_by_ticker comprehension.

        The comprehension is:
            memberships_by_ticker = {
                ticker: derive_index_memberships(
                    ticker, cohort=cohort, dow30=..., ndx=...,
                    market_cap=market_cap_by_ticker.get(ticker),
                )
                for ticker, cohort in cohort_by_ticker.items()
            }

        We replicate that comprehension exactly here — no full compute.main
        invocation — to confirm:
          - .get() miss (key absent) → None → no russell1000 tag
          - .get() hit with None value → None → no russell1000 tag
          - .get() hit with 0.0 → no russell1000 tag
          - .get() hit with positive float → russell1000 tag present
        """
        from compute.ingest.universe import derive_index_memberships

        # Mirrors market_cap_by_ticker as built in main.py lines ~1916-1929
        market_cap_by_ticker: dict[str, float | None] = {
            "AAPL": 3_000_000_000_000.0,  # positive → russell1000 expected
            "BRKR": 5_000_000_000.0,       # positive sp400 → russell1000 expected
            "OZK": None,                   # None (missing snapshot) → no tag
            "GHOST": 0.0,                  # zero → no tag
        }
        # cohort_by_ticker as built in main.py lines ~1941-1944
        cohort_by_ticker: dict[str, str] = {
            "AAPL": "sp500",
            "BRKR": "sp400",
            "OZK": "sp500",
            "GHOST": "sp500",
        }

        # Replicate the main.py comprehension (including the .get() miss path
        # for a ticker that is in cohort_by_ticker but absent from
        # market_cap_by_ticker — e.g. the "MISS" case)
        cohort_by_ticker["MISS"] = "sp500"  # in cohort map, but not in cap map

        memberships_by_ticker: dict[str, list[str]] = {
            ticker: derive_index_memberships(
                ticker,
                cohort=cohort,
                dow30=set(),
                ndx=set(),
                market_cap=market_cap_by_ticker.get(ticker),  # .get() → None on miss
            )
            for ticker, cohort in cohort_by_ticker.items()
        }

        # Positive cap → russell1000
        assert "russell1000" in memberships_by_ticker["AAPL"]
        assert "russell1000" in memberships_by_ticker["BRKR"]
        # None cap (explicit None value) → no tag
        assert "russell1000" not in memberships_by_ticker["OZK"]
        # Zero cap → no tag
        assert "russell1000" not in memberships_by_ticker["GHOST"]
        # .get() miss (key absent from market_cap_by_ticker) → None → no tag
        assert "russell1000" not in memberships_by_ticker["MISS"]

        # Cohort always first regardless of cap
        assert memberships_by_ticker["AAPL"][0] == "sp500"
        assert memberships_by_ticker["BRKR"][0] == "sp400"


# ---------------------------------------------------------------------------
# 1b. Hypothesis property test — primary cohort always in memberships
# ---------------------------------------------------------------------------

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st

    _HYPOTHESIS_AVAILABLE = True
except ImportError:
    _HYPOTHESIS_AVAILABLE = False


@pytest.mark.skipif(not _HYPOTHESIS_AVAILABLE, reason="hypothesis not installed")
class TestDeriveIndexMembershipsProperties:
    @given(
        ticker=st.text(min_size=1, max_size=6, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ-"),
        cohort=st.sampled_from(["sp500", "sp400"]),
        dow30_tickers=st.frozensets(
            st.text(min_size=1, max_size=6, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ-"),
            max_size=40,
        ),
        ndx_tickers=st.frozensets(
            st.text(min_size=1, max_size=6, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ-"),
            max_size=110,
        ),
    )
    @settings(max_examples=200)
    def test_primary_cohort_always_in_result(self, ticker, cohort, dow30_tickers, ndx_tickers):
        """Property: the primary cohort is ALWAYS the first element."""
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships(
            ticker,
            cohort=cohort,
            dow30=set(dow30_tickers),
            ndx=set(ndx_tickers),
        )
        assert result[0] == cohort, f"Primary cohort {cohort!r} not first in {result!r}"

    @given(
        ticker=st.text(min_size=1, max_size=6, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ-"),
        cohort=st.sampled_from(["sp500", "sp400"]),
        dow30_tickers=st.frozensets(
            st.text(min_size=1, max_size=6, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ-"),
            max_size=40,
        ),
        ndx_tickers=st.frozensets(
            st.text(min_size=1, max_size=6, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ-"),
            max_size=110,
        ),
        # market_cap: None | float≤0 | float>0 — exercises all three branches
        # of the russell1000 proxy gate.  st.none() | st.floats() covers the
        # full domain including zero, negatives, and large positives.
        market_cap=st.one_of(
            st.none(),
            st.floats(min_value=-1e15, max_value=1e15, allow_nan=False, allow_infinity=False),
        ),
    )
    @settings(max_examples=200)
    def test_only_valid_codes_in_result(
        self, ticker, cohort, dow30_tickers, ndx_tickers, market_cap
    ):
        """Property: result contains only known index codes (incl. russell1000)."""
        from compute.ingest.universe import derive_index_memberships

        # "russell1000" is now a valid output code (added by the market_cap branch)
        valid_codes = {"sp500", "sp400", "dow30", "ndx", "russell1000"}
        result = derive_index_memberships(
            ticker,
            cohort=cohort,
            dow30=set(dow30_tickers),
            ndx=set(ndx_tickers),
            market_cap=market_cap,
        )
        for code in result:
            assert code in valid_codes, f"Unknown code {code!r} in {result!r}"

    @given(
        ticker=st.text(min_size=1, max_size=6, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ-"),
        cohort=st.sampled_from(["sp500", "sp400"]),
        dow30_tickers=st.frozensets(
            st.text(min_size=1, max_size=6, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ-"),
            max_size=40,
        ),
        ndx_tickers=st.frozensets(
            st.text(min_size=1, max_size=6, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ-"),
            max_size=110,
        ),
    )
    @settings(max_examples=200)
    def test_no_duplicates_property(self, ticker, cohort, dow30_tickers, ndx_tickers):
        """Property: no duplicate codes in any result."""
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships(
            ticker,
            cohort=cohort,
            dow30=set(dow30_tickers),
            ndx=set(ndx_tickers),
        )
        assert len(result) == len(set(result)), f"Duplicates in {result!r}"

    @given(
        ticker=st.text(min_size=1, max_size=6, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ-"),
        cohort=st.sampled_from(["sp500", "sp400"]),
    )
    @settings(max_examples=100)
    def test_empty_sets_returns_cohort_only(self, ticker, cohort):
        """Property: empty dow30 + ndx → exactly [cohort]."""
        from compute.ingest.universe import derive_index_memberships

        result = derive_index_memberships(
            ticker, cohort=cohort, dow30=set(), ndx=set()
        )
        assert result == [cohort]


# ---------------------------------------------------------------------------
# 2. Schema round-trips
# ---------------------------------------------------------------------------


class TestIndexMembershipsSchema:
    """index_memberships field round-trips on StockSummary + StockDetail."""

    def test_stock_summary_default_is_empty_list(self):
        """StockSummary.index_memberships defaults to [] when omitted."""
        from compute.output.schemas import StockSummary

        s = StockSummary(
            rank=1, ticker="AAPL", name="Apple Inc.",
            sector="IT", composite_score=75.0, current_price=195.0,
        )
        assert s.index_memberships == []

    def test_stock_summary_round_trip_sp500_only(self):
        """index_memberships=['sp500'] round-trips correctly."""
        from compute.output.schemas import StockSummary

        s = StockSummary(
            rank=1, ticker="AAPL", name="Apple Inc.",
            sector="IT", composite_score=75.0, current_price=195.0,
            index_memberships=["sp500"],
        )
        assert s.index_memberships == ["sp500"]

    def test_stock_summary_round_trip_all_memberships(self):
        """index_memberships=['sp500','dow30','ndx'] round-trips correctly."""
        from compute.output.schemas import StockSummary

        s = StockSummary(
            rank=1, ticker="AAPL", name="Apple Inc.",
            sector="IT", composite_score=75.0, current_price=195.0,
            index_memberships=["sp500", "dow30", "ndx"],
        )
        assert s.index_memberships == ["sp500", "dow30", "ndx"]

    def test_stock_summary_serialises_index_memberships(self):
        """index_memberships appears in model_dump() output."""
        from compute.output.schemas import StockSummary

        s = StockSummary(
            rank=1, ticker="AAPL", name="Apple Inc.",
            sector="IT", composite_score=75.0, current_price=195.0,
            index_memberships=["sp500", "ndx"],
        )
        d = s.model_dump()
        assert "index_memberships" in d
        assert d["index_memberships"] == ["sp500", "ndx"]

    def test_stock_summary_legacy_json_default_empty(self):
        """Legacy JSON without index_memberships key → default []."""
        from compute.output.schemas import StockSummary

        payload = {
            "rank": 1, "ticker": "AAPL", "name": "Apple Inc.",
            "sector": "IT", "composite_score": 75.0, "current_price": 195.0,
            # index_memberships deliberately absent
        }
        s = StockSummary.model_validate(payload)
        assert s.index_memberships == []

    def test_stock_summary_index_membership_singular_unchanged(self):
        """index_membership (singular) is unchanged when index_memberships is set."""
        from compute.output.schemas import StockSummary

        s = StockSummary(
            rank=1, ticker="AAPL", name="Apple Inc.",
            sector="IT", composite_score=75.0, current_price=195.0,
            index_membership="sp500",
            index_memberships=["sp500", "dow30"],
        )
        assert s.index_membership == "sp500"
        assert s.index_memberships == ["sp500", "dow30"]

    def test_stock_detail_default_is_empty_list(self):
        """StockDetail.index_memberships defaults to [] when omitted."""
        from compute.output.schemas import StockDetail

        d = StockDetail(
            ticker="AAPL", name="Apple Inc.", sector="IT",
            current_price=195.0, rank=1, composite_score=75.0,
        )
        assert d.index_memberships == []

    def test_stock_detail_round_trip_with_memberships(self):
        """StockDetail.index_memberships round-trips correctly."""
        from compute.output.schemas import StockDetail

        detail = StockDetail(
            ticker="AAPL", name="Apple Inc.", sector="IT",
            current_price=195.0, rank=1, composite_score=75.0,
            index_memberships=["sp500", "dow30", "ndx"],
        )
        assert detail.index_memberships == ["sp500", "dow30", "ndx"]

    def test_stock_detail_legacy_json_default_empty(self):
        """Legacy StockDetail JSON without index_memberships → default []."""
        from compute.output.schemas import StockDetail

        payload = {
            "ticker": "AAPL", "name": "Apple Inc.", "sector": "IT",
            "current_price": 195.0, "rank": 1, "composite_score": 75.0,
            # index_memberships deliberately absent
        }
        d = StockDetail.model_validate(payload)
        assert d.index_memberships == []

    def test_extra_fields_forbidden_still_applies_summary(self):
        """extra='forbid' still blocks unknown fields on StockSummary."""
        from compute.output.schemas import StockSummary

        with pytest.raises(Exception):  # noqa: B017
            StockSummary(
                rank=1, ticker="AAPL", name="Apple Inc.",
                sector="IT", composite_score=75.0, current_price=195.0,
                index_memberships=["sp500"],
                unknown_field="should_fail",
            )

    def test_extra_fields_forbidden_still_applies_detail(self):
        """extra='forbid' still blocks unknown fields on StockDetail."""
        from compute.output.schemas import StockDetail

        with pytest.raises(Exception):  # noqa: B017
            StockDetail(
                ticker="AAPL", name="Apple Inc.", sector="IT",
                current_price=195.0, rank=1, composite_score=75.0,
                index_memberships=["sp500"],
                unknown_field="should_fail",
            )


# ---------------------------------------------------------------------------
# 3. HTML parser tests — fixture HTML, no network
# ---------------------------------------------------------------------------

# Minimal valid DOW 30 table HTML (30 rows, Symbol column)
_DOW30_FIXTURE_HTML = dedent("""\
    <html><body>
    <table class="wikitable sortable">
    <thead><tr><th>Symbol</th><th>Company</th></tr></thead>
    <tbody>
    """ + "\n".join(
    f"<tr><td>{t}</td><td>Company {i}</td></tr>"
    for i, t in enumerate([
        "AAPL", "AMGN", "AXP", "BA", "CAT", "CRM", "CSCO", "CVX", "DIS",
        "DOW", "GS", "HD", "HON", "IBM", "INTC", "JNJ", "JPM", "KO",
        "MCD", "MMM", "MRK", "MSFT", "NKE", "PG", "TRV", "UNH", "V",
        "VZ", "WBA", "WMT",
    ])
) + """
    </tbody></table>
    </body></html>
""")

# Minimal valid NDX table HTML (~100 rows, Ticker column)
_NDX_BASE_TICKERS = [
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA",
    "AVGO", "COST", "ASML", "CSCO", "TMUS", "ADBE", "AMD", "PEP",
    "NFLX", "INTU", "AZN", "QCOM", "TXN", "AMAT", "AMGN", "MU",
    "ISRG", "BKNG", "LRCX", "REGN", "PANW", "ADI", "KLAC", "VRTX",
    "ABNB", "MDLZ", "CDNS", "SNPS", "MRVL", "FTNT", "ORLY", "PYPL",
    "NXPI", "ADP", "ROP", "MELI", "CRWD", "DASH", "CEG", "EXC",
    "ON", "CSGP", "BIIB", "CPRT", "IDXX", "VRSK", "FANG", "DDOG",
    "ANSS", "GFS", "ZS", "CTAS", "ODFL", "TEAM", "FAST", "GEHC",
    "TTWO", "MRNA", "SMCI", "APP", "CDW", "NTAP", "ILMN", "KHC",
    "GILD", "ARM", "HBAN", "SBUX", "MNST", "WDAY", "NDAQ", "CHTR",
    "PCAR", "DLTR", "LCID", "RIVN", "SIRI", "MDB", "DOCU", "ZI",
    "ALGN", "LOGI", "BMRN", "BGNE", "ROST", "WBD", "TTD", "ACGL",
    "HOOD", "EXAS", "CCCS", "FLEX",
]

_NDX_FIXTURE_HTML = dedent("""\
    <html><body>
    <table class="wikitable sortable">
    <thead><tr><th>Ticker</th><th>Company</th></tr></thead>
    <tbody>
    """ + "\n".join(
    f"<tr><td>{t}</td><td>Company {i}</td></tr>"
    for i, t in enumerate(_NDX_BASE_TICKERS[:100])
) + """
    </tbody></table>
    </body></html>
""")


class TestDow30HtmlParser:
    def test_parses_30_tickers_from_fixture(self):
        """_parse_dow30_html returns exactly 30 tickers from fixture HTML."""
        from compute.ingest.universe import _parse_dow30_html  # noqa: PLC0415

        result = _parse_dow30_html(_DOW30_FIXTURE_HTML)
        assert len(result) == 30

    def test_all_tickers_uppercase_normalised(self):
        """All returned tickers are uppercase (dot→dash normalised)."""
        from compute.ingest.universe import _parse_dow30_html  # noqa: PLC0415

        result = _parse_dow30_html(_DOW30_FIXTURE_HTML)
        assert all(t == t.upper() for t in result)

    def test_known_ticker_present(self):
        """AAPL must appear in the parsed set."""
        from compute.ingest.universe import _parse_dow30_html  # noqa: PLC0415

        result = _parse_dow30_html(_DOW30_FIXTURE_HTML)
        assert "AAPL" in result

    def test_malformed_html_no_table_returns_empty(self):
        """HTML with no wikitable → empty set, no raise."""
        from compute.ingest.universe import _parse_dow30_html  # noqa: PLC0415

        result = _parse_dow30_html("<html><body><p>nothing here</p></body></html>")
        assert result == set()

    def test_table_without_symbol_column_returns_empty(self):
        """wikitable with no Symbol/Ticker column → empty set, no raise."""
        from compute.ingest.universe import _parse_dow30_html  # noqa: PLC0415

        html = dedent("""\
            <html><body>
            <table class="wikitable">
            <thead><tr><th>Name</th><th>Exchange</th></tr></thead>
            <tbody><tr><td>Apple</td><td>NASDAQ</td></tr></tbody>
            </table></body></html>
        """)
        result = _parse_dow30_html(html)
        assert result == set()

    def test_returns_set_type(self):
        """Return type must be set."""
        from compute.ingest.universe import _parse_dow30_html  # noqa: PLC0415

        result = _parse_dow30_html(_DOW30_FIXTURE_HTML)
        assert isinstance(result, set)


class TestNdxHtmlParser:
    def test_parses_100_tickers_from_fixture(self):
        """_parse_ndx_html returns exactly 100 tickers from fixture HTML."""
        from compute.ingest.universe import _parse_ndx_html  # noqa: PLC0415

        result = _parse_ndx_html(_NDX_FIXTURE_HTML)
        assert len(result) == 100

    def test_all_tickers_uppercase_normalised(self):
        """All returned tickers are uppercase."""
        from compute.ingest.universe import _parse_ndx_html  # noqa: PLC0415

        result = _parse_ndx_html(_NDX_FIXTURE_HTML)
        assert all(t == t.upper() for t in result)

    def test_known_ticker_present(self):
        """AAPL must appear in the parsed set."""
        from compute.ingest.universe import _parse_ndx_html  # noqa: PLC0415

        result = _parse_ndx_html(_NDX_FIXTURE_HTML)
        assert "AAPL" in result

    def test_malformed_html_no_table_returns_empty(self):
        """HTML with no wikitable → empty set, no raise."""
        from compute.ingest.universe import _parse_ndx_html  # noqa: PLC0415

        result = _parse_ndx_html("<html><body><p>nothing</p></body></html>")
        assert result == set()

    def test_table_without_ticker_or_symbol_column_returns_empty(self):
        """wikitable with no Ticker/Symbol column → empty set, no raise."""
        from compute.ingest.universe import _parse_ndx_html  # noqa: PLC0415

        html = dedent("""\
            <html><body>
            <table class="wikitable">
            <thead><tr><th>Name</th><th>Sector</th></tr></thead>
            <tbody><tr><td>Apple Inc.</td><td>Technology</td></tr></tbody>
            </table></body></html>
        """)
        result = _parse_ndx_html(html)
        assert result == set()

    def test_returns_set_type(self):
        """Return type must be set."""
        from compute.ingest.universe import _parse_ndx_html  # noqa: PLC0415

        result = _parse_ndx_html(_NDX_FIXTURE_HTML)
        assert isinstance(result, set)

    def test_ticker_column_name_variant(self):
        """Parser accepts 'Symbol' as an alternative to 'Ticker'."""
        from compute.ingest.universe import _parse_ndx_html  # noqa: PLC0415

        # Build a 100-row table with 'Symbol' header instead of 'Ticker'
        html = dedent("""\
            <html><body>
            <table class="wikitable">
            <thead><tr><th>Symbol</th><th>Company</th></tr></thead>
            <tbody>
        """ + "\n".join(
            f"<tr><td>T{i:03d}</td><td>Co {i}</td></tr>"
            for i in range(100)
        ) + """
            </tbody></table></body></html>
        """)
        result = _parse_ndx_html(html)
        assert len(result) == 100


# ---------------------------------------------------------------------------
# 4. Graceful-degradation — fetch_dow30_constituents / fetch_ndx_constituents
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """Malformed or no-network scenarios return empty set, never raise."""

    def test_dow30_fetch_failure_returns_empty_set(self, monkeypatch):
        """When _fetch_wikipedia_html raises, fetch_dow30_constituents returns set()."""
        import compute.ingest.universe as uni_mod  # noqa: PLC0415

        monkeypatch.setattr(
            uni_mod, "_fetch_wikipedia_html",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("network error")),
        )
        result = uni_mod.fetch_dow30_constituents(force_refresh=True)
        assert result == set()

    def test_ndx_fetch_failure_returns_empty_set(self, monkeypatch):
        """When _fetch_wikipedia_html raises, fetch_ndx_constituents returns set()."""
        import compute.ingest.universe as uni_mod  # noqa: PLC0415

        monkeypatch.setattr(
            uni_mod, "_fetch_wikipedia_html",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("network error")),
        )
        result = uni_mod.fetch_ndx_constituents(force_refresh=True)
        assert result == set()

    def test_dow30_malformed_table_returns_empty_set(self, monkeypatch):
        """Malformed HTML (no table) → empty set, no raise."""
        import compute.ingest.universe as uni_mod  # noqa: PLC0415

        monkeypatch.setattr(
            uni_mod, "_fetch_wikipedia_html",
            lambda *a, **kw: "<html><body><p>no table</p></body></html>",
        )
        result = uni_mod.fetch_dow30_constituents(force_refresh=True)
        assert result == set()

    def test_ndx_malformed_table_returns_empty_set(self, monkeypatch):
        """Malformed HTML (no table) → empty set, no raise."""
        import compute.ingest.universe as uni_mod  # noqa: PLC0415

        monkeypatch.setattr(
            uni_mod, "_fetch_wikipedia_html",
            lambda *a, **kw: "<html><body><p>no table</p></body></html>",
        )
        result = uni_mod.fetch_ndx_constituents(force_refresh=True)
        assert result == set()


# ---------------------------------------------------------------------------
# 5. Sanity-band tests
# ---------------------------------------------------------------------------


class TestSanityBand:
    """Wrong component counts are rejected (empty set + WARNING, no raise)."""

    def _make_dow_html(self, n: int) -> str:
        """Build a DOW-style wikitable with n rows."""
        rows = "\n".join(
            f"<tr><td>T{i:03d}</td><td>Company {i}</td></tr>"
            for i in range(n)
        )
        return dedent(f"""\
            <html><body>
            <table class="wikitable">
            <thead><tr><th>Symbol</th><th>Company</th></tr></thead>
            <tbody>{rows}</tbody>
            </table></body></html>
        """)

    def _make_ndx_html(self, n: int) -> str:
        """Build an NDX-style wikitable with n rows."""
        rows = "\n".join(
            f"<tr><td>T{i:03d}</td><td>Company {i}</td></tr>"
            for i in range(n)
        )
        return dedent(f"""\
            <html><body>
            <table class="wikitable">
            <thead><tr><th>Ticker</th><th>Company</th></tr></thead>
            <tbody>{rows}</tbody>
            </table></body></html>
        """)

    def test_dow30_wrong_count_returns_empty(self, monkeypatch):
        """DOW with 29 tickers → sanity band rejected → empty set."""
        import compute.ingest.universe as uni_mod  # noqa: PLC0415

        monkeypatch.setattr(
            uni_mod, "_fetch_wikipedia_html",
            lambda *a, **kw: self._make_dow_html(29),
        )
        result = uni_mod.fetch_dow30_constituents(force_refresh=True)
        assert result == set()

    def test_dow30_correct_count_accepted(self, monkeypatch):
        """DOW with exactly 30 tickers → accepted."""
        import compute.ingest.universe as uni_mod  # noqa: PLC0415

        monkeypatch.setattr(
            uni_mod, "_fetch_wikipedia_html",
            lambda *a, **kw: self._make_dow_html(30),
        )
        result = uni_mod.fetch_dow30_constituents(force_refresh=True)
        assert len(result) == 30

    def test_dow30_31_tickers_returns_empty(self, monkeypatch):
        """DOW with 31 tickers → sanity band rejected → empty set."""
        import compute.ingest.universe as uni_mod  # noqa: PLC0415

        monkeypatch.setattr(
            uni_mod, "_fetch_wikipedia_html",
            lambda *a, **kw: self._make_dow_html(31),
        )
        result = uni_mod.fetch_dow30_constituents(force_refresh=True)
        assert result == set()

    def test_ndx_too_few_tickers_returns_empty(self, monkeypatch):
        """NDX with 90 tickers → below NDX_MIN_COUNT (95) → empty set."""
        import compute.ingest.universe as uni_mod  # noqa: PLC0415

        monkeypatch.setattr(
            uni_mod, "_fetch_wikipedia_html",
            lambda *a, **kw: self._make_ndx_html(90),
        )
        result = uni_mod.fetch_ndx_constituents(force_refresh=True)
        assert result == set()

    def test_ndx_too_many_tickers_returns_empty(self, monkeypatch):
        """NDX with 110 tickers → above NDX_MAX_COUNT (105) → empty set."""
        import compute.ingest.universe as uni_mod  # noqa: PLC0415

        monkeypatch.setattr(
            uni_mod, "_fetch_wikipedia_html",
            lambda *a, **kw: self._make_ndx_html(110),
        )
        result = uni_mod.fetch_ndx_constituents(force_refresh=True)
        assert result == set()

    def test_ndx_100_tickers_accepted(self, monkeypatch):
        """NDX with exactly 100 tickers → within band [95, 105] → accepted."""
        import compute.ingest.universe as uni_mod  # noqa: PLC0415

        monkeypatch.setattr(
            uni_mod, "_fetch_wikipedia_html",
            lambda *a, **kw: self._make_ndx_html(100),
        )
        result = uni_mod.fetch_ndx_constituents(force_refresh=True)
        assert len(result) == 100

    def test_ndx_95_tickers_accepted(self, monkeypatch):
        """NDX with exactly 95 tickers → lower bound accepted."""
        import compute.ingest.universe as uni_mod  # noqa: PLC0415

        monkeypatch.setattr(
            uni_mod, "_fetch_wikipedia_html",
            lambda *a, **kw: self._make_ndx_html(95),
        )
        result = uni_mod.fetch_ndx_constituents(force_refresh=True)
        assert len(result) == 95

    def test_ndx_105_tickers_accepted(self, monkeypatch):
        """NDX with exactly 105 tickers → upper bound accepted."""
        import compute.ingest.universe as uni_mod  # noqa: PLC0415

        monkeypatch.setattr(
            uni_mod, "_fetch_wikipedia_html",
            lambda *a, **kw: self._make_ndx_html(105),
        )
        result = uni_mod.fetch_ndx_constituents(force_refresh=True)
        assert len(result) == 105


# ---------------------------------------------------------------------------
# 6. Ledger-unchanged regression
# ---------------------------------------------------------------------------


def _make_rankings_with_memberships(n_sp500: int = 502, n_sp400: int = 398) -> str:
    """Build a rankings.json that includes BOTH index_membership AND
    index_memberships fields (the new 0.10.23 shape)."""
    rows = []
    for i in range(n_sp500):
        rows.append({
            "rank": i + 1,
            "ticker": f"S5_{i:04d}",
            "name": f"SP500 Co {i}",
            "sector": "Technology",
            "composite_score": 80.0 - i * 0.1,
            "current_price": 100.0,
            "index_membership": "sp500",
            "index_memberships": ["sp500"],  # new field
        })
    for i in range(n_sp400):
        rows.append({
            "rank": n_sp500 + i + 1,
            "ticker": f"S4_{i:04d}",
            "name": f"SP400 Co {i}",
            "sector": "Industrials",
            "composite_score": 50.0 - i * 0.1,
            "current_price": 30.0,
            "index_membership": "sp400",
            "index_memberships": ["sp400"],  # new field
        })
    return json.dumps(rows)


class TestLedgerUnchangedRegression:
    """verify_membership_ledger.current_universe() reads index_membership
    (singular) — introducing index_memberships (plural) must NOT change
    its output."""

    def _import_ledger(self, tmp_path: Path, rankings_json_text: str):
        rankings_file = tmp_path / "rankings.json"
        rankings_file.write_text(rankings_json_text)

        import importlib
        import importlib.util

        ROOT = Path(__file__).resolve().parents[2]
        spec = importlib.util.spec_from_file_location(
            "verify_membership_ledger_regression_test",
            ROOT / "scripts" / "verify_membership_ledger.py",
        )
        mod = importlib.util.module_from_spec(spec)
        mod.__dict__["__builtins__"] = __builtins__
        spec.loader.exec_module(mod)
        mod.RANKINGS = rankings_file
        return mod

    def test_current_universe_returns_only_sp500_with_new_field(self, tmp_path):
        """900-row payload with index_memberships field → still returns sp500 only."""
        text = _make_rankings_with_memberships(n_sp500=502, n_sp400=398)
        mod = self._import_ledger(tmp_path, text)
        uni = mod.current_universe()
        assert len(uni) == 502
        assert all(t.startswith("S5_") for t in uni)

    def test_current_universe_count_unchanged(self, tmp_path):
        """Adding index_memberships field does NOT change the count returned."""
        text = _make_rankings_with_memberships(n_sp500=502, n_sp400=398)
        mod = self._import_ledger(tmp_path, text)
        uni = mod.current_universe()
        assert len(uni) == 502

    def test_sp400_tickers_excluded_even_with_new_field(self, tmp_path):
        """S4_* tickers must NEVER appear in current_universe() output."""
        text = _make_rankings_with_memberships(n_sp500=10, n_sp400=5)
        mod = self._import_ledger(tmp_path, text)
        uni = mod.current_universe()
        assert all(not t.startswith("S4_") for t in uni)
