"""Unit tests for compute.scoring.sector_rules (Defense #6)."""

from __future__ import annotations

from compute.scoring.sector_rules import (
    SECTOR_BLACKLIST,
    is_metric_excluded_for_sector,
)

# -- A. SECTOR_BLACKLIST module tests ----------------------------------------

def test_A1_existing_entry_lookup_returns_true():
    assert is_metric_excluded_for_sector(
        metric="magic_formula", sector="Financials"
    ) is True


def test_A2_sector_not_in_blacklist_returns_false():
    assert is_metric_excluded_for_sector(
        metric="magic_formula", sector="Information Technology"
    ) is False


def test_A3_metric_not_in_blacklist_returns_false():
    assert is_metric_excluded_for_sector(
        metric="some_random_metric", sector="Financials"
    ) is False


def test_A4_sector_none_returns_false():
    assert is_metric_excluded_for_sector(
        metric="magic_formula", sector=None
    ) is False


# -- Coverage of the spec-required entries -----------------------------------

def test_blacklist_covers_step6_spec_entries():
    """All 5 SECTOR_BLACKLIST keys per kickoff §Step 6 spec."""
    expected_keys = {
        "magic_formula",
        "asset_turnover",
        "ebit_based_roic",
        "gross_profitability",
        "ev_ebitda_multiple",
    }
    assert expected_keys.issubset(SECTOR_BLACKLIST.keys())


def test_magic_formula_excludes_3_sectors():
    assert SECTOR_BLACKLIST["magic_formula"] == frozenset({
        "Financials", "Utilities", "Real Estate",
    })


def test_ebit_based_roic_excludes_financials_and_utilities():
    assert SECTOR_BLACKLIST["ebit_based_roic"] == frozenset({
        "Financials", "Utilities",
    })


def test_gross_profitability_excludes_financials_only():
    """Per kickoff §Step 6 spec — only Financials, NOT Utilities/Real Estate."""
    assert SECTOR_BLACKLIST["gross_profitability"] == frozenset({"Financials"})


def test_ev_ebitda_multiple_excludes_financials_only():
    """Mirrors fair-price applicability gate (Step 4.1 — Financials only,
    NOT Utilities; Utilities have meaningful EBITDA above the D&A line)."""
    assert SECTOR_BLACKLIST["ev_ebitda_multiple"] == frozenset({"Financials"})


def test_asset_turnover_excludes_financials_only():
    assert SECTOR_BLACKLIST["asset_turnover"] == frozenset({"Financials"})


def test_ebit_based_roic_does_not_exclude_real_estate():
    """REITs DO have meaningful ROIC; Phase 4 will add FFO/AFFO substitutes
    but PR-3c keeps REITs in the ROIC ranking."""
    assert is_metric_excluded_for_sector(
        metric="ebit_based_roic", sector="Real Estate"
    ) is False


def test_blacklist_values_are_frozensets():
    """Frozen for hashability + immutability — prevents accidental mutation."""
    for key, value in SECTOR_BLACKLIST.items():
        assert isinstance(value, frozenset), (
            f"{key}: expected frozenset, got {type(value).__name__}"
        )
