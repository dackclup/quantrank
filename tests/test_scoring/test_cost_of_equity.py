"""Tests for compute.scoring.cost_of_equity.

Covers:
- 11-sector dict pin (exact value check for each GICS Sector)
- Fallback-to-0.10 for None and unknown sectors
- Hypothesis property: return value always in [COE_BAND_MIN, COE_BAND_MAX]
- Constant pin for COE_BAND_MIN and COE_BAND_MAX
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from compute.scoring.cost_of_equity import (
    _DEFAULT_COE,
    COE_BAND_MAX,
    COE_BAND_MIN,
    SECTOR_COST_OF_EQUITY,
    get_cost_of_equity,
)

# ---------------------------------------------------------------------------
# 11-sector dict pin — exact values from Damodaran 2019 Table 8.4 +
# Damodaran NYU online betas dataset (January 2025 update).
# These pins lock the academic-prior transcription so any accidental edit
# triggers a test failure and requires a methodology-scientist Mode B review.
# ---------------------------------------------------------------------------
_EXPECTED_SECTOR_COE: dict[str, float] = {
    "Utilities":                 0.06,
    "Real Estate":               0.07,
    "Consumer Staples":          0.088,
    "Financials":                0.085,
    "Communication Services":    0.095,
    "Industrials":               0.095,
    "Consumer Discretionary":    0.10,
    "Health Care":               0.105,
    "Information Technology":    0.11,
    "Materials":                 0.11,
    "Energy":                    0.12,
}


def test_sector_coe_dict_has_all_11_gics_sectors() -> None:
    """SECTOR_COST_OF_EQUITY must cover exactly the 11 GICS Sectors."""
    assert set(SECTOR_COST_OF_EQUITY.keys()) == set(_EXPECTED_SECTOR_COE.keys())


@pytest.mark.parametrize("sector,expected", list(_EXPECTED_SECTOR_COE.items()))
def test_sector_coe_dict_values_match_damodaran(sector: str, expected: float) -> None:
    """Each sector CoE must match the pinned Damodaran 2019 / NYU 2025 value."""
    assert SECTOR_COST_OF_EQUITY[sector] == pytest.approx(expected, abs=1e-9)


# ---------------------------------------------------------------------------
# get_cost_of_equity function — known-sector paths
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sector,expected", list(_EXPECTED_SECTOR_COE.items()))
def test_get_cost_of_equity_known_sectors(sector: str, expected: float) -> None:
    """get_cost_of_equity returns the pinned value for every known sector."""
    assert get_cost_of_equity(sector) == pytest.approx(expected, abs=1e-9)


def test_get_cost_of_equity_none_returns_default() -> None:
    """get_cost_of_equity(None) falls back to the flat 10% default."""
    assert get_cost_of_equity(None) == pytest.approx(_DEFAULT_COE, abs=1e-9)


def test_get_cost_of_equity_unknown_sector_returns_default() -> None:
    """Unmapped sector string falls back to the flat 10% default."""
    assert get_cost_of_equity("Unknown Sector XYZ") == pytest.approx(_DEFAULT_COE, abs=1e-9)


def test_get_cost_of_equity_empty_string_returns_default() -> None:
    """Empty string is treated as unmapped — fallback to 10%."""
    assert get_cost_of_equity("") == pytest.approx(_DEFAULT_COE, abs=1e-9)


def test_default_coe_equals_flat_constant() -> None:
    """_DEFAULT_COE must equal 0.10 (the flat COST_OF_EQUITY baseline)."""
    assert _DEFAULT_COE == pytest.approx(0.10, abs=1e-9)


# ---------------------------------------------------------------------------
# Constants pin — COE_BAND_MIN / COE_BAND_MAX
# ---------------------------------------------------------------------------

def test_coe_band_min_constant() -> None:
    assert COE_BAND_MIN == pytest.approx(0.04, abs=1e-9)


def test_coe_band_max_constant() -> None:
    assert COE_BAND_MAX == pytest.approx(0.22, abs=1e-9)


# ---------------------------------------------------------------------------
# Hypothesis property — return value always within the documented band
# ---------------------------------------------------------------------------

@given(
    sector=st.one_of(
        st.none(),
        st.sampled_from(list(SECTOR_COST_OF_EQUITY.keys())),
        st.text(min_size=0, max_size=50),
    )
)
@settings(max_examples=200)
def test_get_cost_of_equity_always_in_band(sector: str | None) -> None:
    """get_cost_of_equity must always return a value in [COE_BAND_MIN, COE_BAND_MAX]."""
    result = get_cost_of_equity(sector)
    assert COE_BAND_MIN <= result <= COE_BAND_MAX, (
        f"CoE {result!r} for sector {sector!r} is outside [{COE_BAND_MIN}, {COE_BAND_MAX}]"
    )


# ---------------------------------------------------------------------------
# Ordering sanity — Utilities should be lower than Energy
# (directional regression test for the academic prior)
# ---------------------------------------------------------------------------

def test_utilities_lower_than_energy() -> None:
    """Utilities CoE < Energy CoE (stable regulated vs volatile E&P beta)."""
    assert get_cost_of_equity("Utilities") < get_cost_of_equity("Energy")


def test_real_estate_lower_than_info_tech() -> None:
    """REIT CoE < Info Tech CoE (low beta vs high beta sector)."""
    assert get_cost_of_equity("Real Estate") < get_cost_of_equity("Information Technology")
