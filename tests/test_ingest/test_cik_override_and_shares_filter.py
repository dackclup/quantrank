"""Tests for two compute/ingest data-quality fixes (issues #567 + #569).

Fix 1 (#567) — NE stale-CIK override:
  ``config.TICKER_CIK_OVERRIDES["NE"]`` must be wired into both
  ``_resolve_cik_for_midcap`` (universe.py) and ``fetch_fundamentals``
  (fundamentals.py) so the post-bankruptcy Noble Corp plc CIK 0001895262
  is preferred over the stale PRE-bankruptcy CIK 1458891 bundled in
  edgartools' company_tickers.parquet.

Fix 2 (#569) — shares-path form-type filter:
  ``_try_balance_tags_most_recent`` now uses ``get_all_facts()`` with a
  Tier-1 filter (``_BALANCE_SHEET_FORM_TYPES`` + unit ``"shares"``), so
  that an 8-K / S-type / DEI cover-page shares fact that was filed more
  recently than the consolidated 10-Q/10-K fact does NOT win by recency.
  Tier-3 fallback to ``get_fact()`` preserves backward compatibility.

  NOTE: BKNG's ~774M shares from a cover-page DEI tag in a valid 10-Q
  filing STILL pass the form filter (10-Q is in ``_BALANCE_SHEET_FORM_TYPES``)
  and therefore BKNG is not affected by this fix — its post-split share count
  is defended by the existing ``post_split_share_lag`` veto (issue #499).

All tests are offline (no network required).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from compute import config
from compute.ingest import universe as universe_mod
from compute.ingest.fundamentals import (
    _BALANCE_SHEET_FORM_TYPES,  # noqa: PLC2701
    _try_balance_tags_most_recent,  # noqa: PLC2701
)

# ===========================================================================
# Fix 1 — NE stale-CIK override
# ===========================================================================


class TestTickerCikOverridesConfig:
    """The TICKER_CIK_OVERRIDES dict in config.py is structurally correct
    and contains the NE override as the verified anchor entry."""

    def test_ne_override_present(self):
        """NE must map to the post-merger Noble Corp plc CIK."""
        assert "NE" in config.TICKER_CIK_OVERRIDES, (
            "TICKER_CIK_OVERRIDES must contain 'NE' (issue #567)"
        )

    def test_ne_cik_is_correct_format(self):
        """NE CIK must be a 10-digit zero-padded string matching the SEC record."""
        cik = config.TICKER_CIK_OVERRIDES["NE"]
        assert cik == "0001895262", (
            f"NE CIK should be '0001895262' (Noble Corp plc post-merger), got {cik!r}"
        )

    def test_overrides_dict_is_typed_correctly(self):
        """All keys must be uppercase strings; all values must be 10-digit strings."""
        for ticker, cik in config.TICKER_CIK_OVERRIDES.items():
            assert ticker == ticker.upper(), f"Key {ticker!r} must be uppercase"
            assert isinstance(cik, str), f"CIK for {ticker!r} must be a str"
            assert len(cik) == 10 and cik.isdigit(), (
                f"CIK for {ticker!r} must be 10 digits, got {cik!r}"
            )


class TestResolveCikForMidcapOverride:
    """_resolve_cik_for_midcap must check TICKER_CIK_OVERRIDES FIRST and skip
    the edgartools Company() lookup when an override is present."""

    def test_ne_returns_override_cik_without_edgar_lookup(self):
        """For NE, the override CIK must be returned and edgartools Company()
        must NOT be called at all (the bundled CIK 1458891 is stale)."""
        with patch("compute.ingest.universe.config") as mock_cfg:
            mock_cfg.TICKER_CIK_OVERRIDES = {"NE": "0001895262"}
            # Company should never be called — patch it to raise if it is
            with patch("edgar.Company", side_effect=AssertionError("edgartools Company() was called unexpectedly for NE")):
                result = universe_mod._resolve_cik_for_midcap("NE")
        assert result == "0001895262", (
            f"Expected override CIK '0001895262' for NE, got {result!r}"
        )

    def test_non_override_ticker_still_uses_edgar_lookup(self):
        """A ticker without an override must still go through the edgartools
        Company() path (override dict miss → normal resolution)."""
        mock_company = MagicMock()
        mock_company.cik = 123456

        with patch("compute.ingest.universe.config") as mock_cfg:
            mock_cfg.TICKER_CIK_OVERRIDES = {}  # empty — no override for AAPL
            with patch("edgar.Company", return_value=mock_company):
                result = universe_mod._resolve_cik_for_midcap("AAPL")
        # 123456 → "0000123456"
        assert result == "0000123456", (
            f"Expected zero-padded CIK '0000123456', got {result!r}"
        )

    def test_lookup_is_case_insensitive_on_input(self):
        """The lookup must normalise the input ticker to uppercase before
        checking the override dict."""
        with patch("compute.ingest.universe.config") as mock_cfg:
            mock_cfg.TICKER_CIK_OVERRIDES = {"NE": "0001895262"}
            with patch("edgar.Company", side_effect=AssertionError("edgartools should not be called")):
                result = universe_mod._resolve_cik_for_midcap("ne")  # lowercase
        assert result == "0001895262"


class TestFetchFundamentalsOverride:
    """fetch_fundamentals must apply TICKER_CIK_OVERRIDES after _require_identity()
    so a wrong cik passed in from the universe layer is corrected before the
    cache-load and _build_snapshot call."""

    def test_fetch_fundamentals_corrects_stale_cik_for_ne(self):
        """When fetch_fundamentals is called with a stale CIK for 'NE', the
        override CIK '0001895262' must be used for all downstream calls."""
        stale_cik = "0001458891"  # pre-bankruptcy Noble Corp entity
        correct_cik = "0001895262"

        # We only need to verify that _load_cached and _build_snapshot
        # are called with the CORRECTED cik, not the stale one.
        calls = []

        def fake_load_cached(cik):
            calls.append(("load_cached", cik))
            return None  # simulate cache miss

        def fake_build_snapshot(ticker, cik):
            calls.append(("build_snapshot", cik))
            # Return a minimal snapshot-like object to satisfy the function
            snap = MagicMock()
            snap.latest_filed_date = date(2026, 2, 12)
            return snap

        from compute.ingest import fundamentals as fund_mod

        with (
            patch.object(fund_mod, "_require_identity"),
            patch.object(fund_mod, "_load_cached", side_effect=fake_load_cached),
            patch.object(fund_mod, "_is_fresh", return_value=False),
            patch.object(fund_mod, "_latest_filing_date", return_value=None),
            patch.object(fund_mod, "_build_snapshot", side_effect=fake_build_snapshot),
            patch.object(fund_mod, "_save_cached"),
        ):
            fund_mod.fetch_fundamentals("NE", stale_cik)

        # _load_cached must have been called with the CORRECTED CIK
        load_calls = [c for c in calls if c[0] == "load_cached"]
        assert load_calls, "Expected at least one _load_cached call"
        assert all(c[1] == correct_cik for c in load_calls), (
            f"_load_cached was called with stale CIK; calls: {load_calls}"
        )
        # _build_snapshot must also receive the corrected CIK
        build_calls = [c for c in calls if c[0] == "build_snapshot"]
        assert build_calls, "Expected a _build_snapshot call (cache miss)"
        assert all(c[1] == correct_cik for c in build_calls), (
            f"_build_snapshot was called with stale CIK; calls: {build_calls}"
        )

    def test_fetch_fundamentals_no_change_for_non_override_ticker(self):
        """A ticker without an override must use the original cik unchanged."""
        original_cik = "0000320193"
        calls = []

        def fake_load_cached(cik):
            calls.append(("load_cached", cik))
            return None

        def fake_build_snapshot(ticker, cik):
            calls.append(("build_snapshot", cik))
            snap = MagicMock()
            snap.latest_filed_date = date(2026, 1, 1)
            return snap

        from compute.ingest import fundamentals as fund_mod

        with (
            patch.object(fund_mod, "_require_identity"),
            patch.object(fund_mod, "_load_cached", side_effect=fake_load_cached),
            patch.object(fund_mod, "_is_fresh", return_value=False),
            patch.object(fund_mod, "_latest_filing_date", return_value=None),
            patch.object(fund_mod, "_build_snapshot", side_effect=fake_build_snapshot),
            patch.object(fund_mod, "_save_cached"),
        ):
            fund_mod.fetch_fundamentals("AAPL", original_cik)

        build_calls = [c for c in calls if c[0] == "build_snapshot"]
        assert build_calls, "Expected a _build_snapshot call"
        assert all(c[1] == original_cik for c in build_calls), (
            f"_build_snapshot received a different CIK for AAPL: {build_calls}"
        )


# ===========================================================================
# Fix 2 — _try_balance_tags_most_recent form-type filter
# ===========================================================================


def _make_share_fact(
    *,
    concept: str,
    value: float,
    form_type: str = "10-Q",
    unit: str = "shares",
    period_end: date = date(2024, 12, 31),
    filing_date: date = date(2025, 2, 15),
) -> SimpleNamespace:
    """Return a minimal FinancialFact-shaped namespace for a shares concept."""
    return SimpleNamespace(
        concept=concept,
        value=value,
        form_type=form_type,
        unit=unit,
        period_end=period_end,
        filing_date=filing_date,
    )


def _make_facts_with_get_all_and_get_fact(
    all_facts: list[SimpleNamespace],
    *,
    get_fact_returns: dict[str, SimpleNamespace | None] | None = None,
) -> MagicMock:
    """Return a mock EntityFacts-like object."""
    facts = MagicMock()
    facts.get_all_facts.return_value = all_facts
    if get_fact_returns is not None:
        facts.get_fact.side_effect = lambda tag: get_fact_returns.get(tag)
    else:
        facts.get_fact.return_value = None
    return facts


class TestSharesFormFilter:
    """_try_balance_tags_most_recent must prefer consolidated form (10-K/10-Q)
    shares facts over 8-K / S-type cover-page contaminants."""

    tag = "dei:EntityCommonStockSharesOutstanding"

    def test_tier1_picks_10q_over_8k_cover_page_by_form(self):
        """An 8-K cover-page shares fact filed more recently than a 10-Q fact
        must be excluded by Tier 1; the 10-Q fact must win."""
        real_10q = _make_share_fact(
            concept=self.tag,
            value=500_000_000.0,
            form_type="10-Q",
            period_end=date(2024, 9, 30),
            filing_date=date(2024, 11, 1),
        )
        cover_8k = _make_share_fact(
            concept=self.tag,
            value=250_000_000.0,   # post-event artificially low count
            form_type="8-K",
            period_end=date(2024, 9, 30),
            filing_date=date(2024, 12, 5),  # filed LATER than 10-Q
        )
        facts = _make_facts_with_get_all_and_get_fact(
            [real_10q, cover_8k],
            get_fact_returns={self.tag: None},
        )

        val, pe, _ = _try_balance_tags_most_recent(facts, [self.tag])

        assert val == 500_000_000.0, (
            f"Expected 10-Q value 500M; got {val}. 8-K cover-page fact mis-picked."
        )
        assert pe == date(2024, 9, 30)

    def test_tier1_picks_10k_over_s1_filing(self):
        """An S-1 registration shares fact must be excluded from Tier 1."""
        real_10k = _make_share_fact(
            concept=self.tag,
            value=800_000_000.0,
            form_type="10-K",
            period_end=date(2024, 12, 31),
            filing_date=date(2025, 2, 15),
        )
        s1_fact = _make_share_fact(
            concept=self.tag,
            value=100_000_000.0,
            form_type="S-1",
            period_end=date(2024, 12, 31),
            filing_date=date(2025, 3, 1),   # filed later
        )
        facts = _make_facts_with_get_all_and_get_fact(
            [real_10k, s1_fact],
            get_fact_returns={self.tag: None},
        )

        val, _, _ = _try_balance_tags_most_recent(facts, [self.tag])

        assert val == 800_000_000.0, (
            f"S-1 registration fact should be excluded; got {val}"
        )

    def test_tier1_picks_most_recent_period_end_among_10k_facts(self):
        """When two 10-K facts exist, Tier 1 must pick the one with the
        more recent period_end, NOT the one with the later filing_date."""
        older = _make_share_fact(
            concept=self.tag,
            value=400_000_000.0,
            form_type="10-K",
            period_end=date(2023, 12, 31),
            filing_date=date(2025, 2, 20),  # filed more recently
        )
        newer_correct = _make_share_fact(
            concept=self.tag,
            value=450_000_000.0,
            form_type="10-K",
            period_end=date(2024, 12, 31),  # more recent period_end
            filing_date=date(2025, 2, 15),
        )
        facts = _make_facts_with_get_all_and_get_fact([older, newer_correct])

        val, pe, _ = _try_balance_tags_most_recent(facts, [self.tag])

        assert pe == date(2024, 12, 31), "Should pick fact with the latest period_end"
        assert val == 450_000_000.0

    def test_tier2_fires_when_no_consolidated_form_facts_exist(self):
        """An odd filer reporting shares only in a non-standard form
        must resolve via Tier 2 (shares unit, any form)."""
        odd_form_fact = _make_share_fact(
            concept=self.tag,
            value=300_000_000.0,
            form_type="40-F",   # Canadian FPI — not in _BALANCE_SHEET_FORM_TYPES
            period_end=date(2024, 12, 31),
            filing_date=date(2025, 3, 1),
        )
        facts = _make_facts_with_get_all_and_get_fact(
            [odd_form_fact],
            get_fact_returns={self.tag: None},
        )

        val, pe, _ = _try_balance_tags_most_recent(facts, [self.tag])

        assert val == 300_000_000.0, "Tier 2 should pick up the odd-form fact"
        assert pe == date(2024, 12, 31)

    def test_tier3_fallback_when_get_all_facts_absent(self):
        """If get_all_facts is not on the facts object, the Tier-3 get_fact()
        path must still work (backward compatibility guard)."""
        fact_ns = SimpleNamespace(
            value=600_000_000.0,
            period_end=date(2024, 12, 31),
            filing_date=date(2025, 2, 15),
        )
        # MagicMock with spec=['get_fact'] does NOT have get_all_facts
        facts = MagicMock(spec=["get_fact"])
        facts.get_fact.return_value = fact_ns

        val, pe, _ = _try_balance_tags_most_recent(facts, [self.tag])

        assert val == 600_000_000.0
        assert pe == date(2024, 12, 31)

    def test_returns_none_when_no_valid_shares_fact(self):
        """All tags missing or invalid → (None, None, None)."""
        facts = _make_facts_with_get_all_and_get_fact(
            [],
            get_fact_returns={self.tag: None},
        )

        val, pe, fd = _try_balance_tags_most_recent(facts, [self.tag])

        assert val is None
        assert pe is None
        assert fd is None

    def test_balance_sheet_form_types_excludes_8k(self):
        """Sanity-check: 8-K must not be in _BALANCE_SHEET_FORM_TYPES
        (the same invariant as test_fundamentals_balance_tag_fix.py)."""
        assert "8-K" not in _BALANCE_SHEET_FORM_TYPES
        assert "S-1" not in _BALANCE_SHEET_FORM_TYPES
        assert "10-K" in _BALANCE_SHEET_FORM_TYPES
        assert "10-Q" in _BALANCE_SHEET_FORM_TYPES

    def test_multi_tag_chain_picks_most_recent_across_tags(self):
        """When multiple tags are provided, the winner is the fact with
        the most recent period_end across ALL tags (original semantics)."""
        tag1 = "dei:EntityCommonStockSharesOutstanding"
        tag2 = "us-gaap:CommonStockSharesOutstanding"

        # tag1: 10-K from 2023
        t1_fact = _make_share_fact(
            concept=tag1,
            value=200_000_000.0,
            form_type="10-K",
            period_end=date(2023, 12, 31),
            filing_date=date(2024, 2, 15),
        )
        # tag2: 10-Q from 2024 (more recent)
        t2_fact = _make_share_fact(
            concept=tag2,
            value=210_000_000.0,
            form_type="10-Q",
            period_end=date(2024, 9, 30),
            filing_date=date(2024, 11, 1),
        )
        facts = _make_facts_with_get_all_and_get_fact(
            [t1_fact, t2_fact],
            get_fact_returns={tag1: None, tag2: None},
        )

        val, pe, _ = _try_balance_tags_most_recent(facts, [tag1, tag2])

        # tag2's 2024-09-30 period_end is more recent → tag2 wins
        assert pe == date(2024, 9, 30), (
            f"Expected period_end 2024-09-30 (tag2), got {pe}"
        )
        assert val == 210_000_000.0

    def test_usd_unit_fact_excluded_from_shares_tiers(self):
        """A USD-unit fact (e.g., an equity-dollar amount mistakenly on the same
        concept) must be excluded from Tier 1 and Tier 2 (both require unit='shares').
        Falls back to Tier 3 if get_fact() has a valid fact."""
        usd_fact = _make_share_fact(
            concept=self.tag,
            value=999_999_999.0,
            form_type="10-K",
            unit="USD",           # wrong unit — should be excluded
            period_end=date(2024, 12, 31),
            filing_date=date(2025, 2, 15),
        )
        shares_fallback = SimpleNamespace(
            value=500_000_000.0,
            period_end=date(2024, 6, 30),
            filing_date=date(2024, 8, 10),
        )
        facts = _make_facts_with_get_all_and_get_fact(
            [usd_fact],
            get_fact_returns={self.tag: shares_fallback},
        )

        val, pe, _ = _try_balance_tags_most_recent(facts, [self.tag])

        # USD-unit fact excluded from Tier 1+2; Tier 3 get_fact() returns
        # the shares_fallback
        assert val == 500_000_000.0, (
            f"USD-unit fact should be excluded from Tier 1+2; got {val}"
        )
