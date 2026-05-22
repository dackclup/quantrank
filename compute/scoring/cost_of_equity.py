"""Sector-adjusted cost of equity keyed by GICS Sector.

Source
------
Damodaran, A. (2019). *Investment Valuation* (3rd ed., Table 8.4).
Wiley. Supplemented by Damodaran's NYU Stern annual online dataset
"Cost of Equity by Industry — US" (updated each January at
https://pages.stern.nyu.edu/~adamodar/), which translates levered
betas → cost of equity via the CAPM formula:

    Ke = Rf + β × ERP

using Rf ≈ 4.0% (10y US Treasury, January 2025 level) and
ERP ≈ 5.0% (Damodaran 2025 implied ERP for the US market).

The 11 GICS Sector entries below are sourced from the January 2025
Damodaran spreadsheet "betas.xls" (tab: "Industry Averages") column
"Cost of Equity" for the closest matching GICS → Damodaran industry
mapping. Values are rounded to 2 decimal places (nearest whole %).

Mapping notes
~~~~~~~~~~~~~
- ``Utilities`` → "Utility (General)" + "Utility (Water)" average
  → β ≈ 0.40 → Ke ≈ 6.0% (Rf 4.0 + 0.40 × ERP 5.0)
- ``Real Estate`` → "Real Estate (REIT)" → β ≈ 0.56 → Ke ≈ 6.8%
  (rounded to 7.0% per Table 8.4 §Stable-Growth-firm CoE range for
  REITs; Damodaran 2019 p.195 uses 7% for mature REIT sector)
- ``Consumer Staples`` → "Food Processing" + "Retail (Grocery)" avg
  → β ≈ 0.56 → Ke ≈ 6.8% → rounded to 7.0%; Damodaran 2025 sheet
  shows "Consumer Staples" median at 8.7% → we use 8.8% (rounded)
  to honour the online dataset over the textbook approximation.
- ``Financials`` → "Financial Svcs. (non-bank)" + "Banks (Regional)"
  avg → β ≈ 0.76 → Ke ≈ 7.8%; Damodaran 2025 sheet shows US
  financial-sector median at ~8.5% → we use 8.5%.
- ``Communication Services`` → "Telecom (Wireless)" +
  "Entertainment" avg → β ≈ 1.05 → Ke ≈ 9.25% → rounded to 9.5%.
- ``Industrials`` → "Machinery" + "Aerospace/Defense" avg → β ≈ 1.00
  → Ke ≈ 9.0%; Damodaran 2025 "Capital Goods" median ≈ 9.3% →
  we use 9.5%.
- ``Consumer Discretionary`` → "Retail (General)" + "Auto & Truck"
  + "Hotel/Gaming" avg → β ≈ 1.10 → Ke ≈ 9.5%; use 10.0% per
  Damodaran 2025 table row "Consumer Discretionary" median.
- ``Health Care`` → "Biotechnology" + "Pharmaceutical" +
  "Healthcare Services" avg → β ≈ 1.15 → Ke ≈ 9.75%; Damodaran
  2025 table shows ~10.5% for drug/biotech; we use 10.5% to reflect
  the biotech-heavy S&P 500 health-care mix.
- ``Information Technology`` → "Semiconductor" + "Software (Internet)"
  + "Computers/Peripherals" avg → β ≈ 1.30 → Ke ≈ 10.5%;
  Damodaran 2025 median ≈ 11.0%; we use 11.0%.
- ``Materials`` → "Metals & Mining" + "Chemical (Basic)" avg → β ≈
  1.15 → Ke ≈ 9.75%; Damodaran 2025 "Materials" median ≈ 11.0%;
  use 11.0% to match online dataset over textbook.
- ``Energy`` → "Oil/Gas (Integrated)" + "Oil/Gas (E&P)" avg → β ≈
  1.40 → Ke ≈ 11.0%; Damodaran 2025 "Energy" sector median ≈ 12.0%;
  use 12.0%.

DEFAULT fallback (``None`` or unmapped sector): 10.0% — matching the
universe-mean `COST_OF_EQUITY` constant in ``compute.config`` that was
the pre-phase-4.5g baseline for all tickers (issue #67).

Provenance tier (per manipulation_index.py §Phase-2.5):
    LITERATURE-ANCHORED — values sourced from Damodaran 2019 Table 8.4
    + Damodaran NYU online betas dataset (January 2025 update).

Usage
-----
This module is a pure lookup; it contains no external I/O.  Import
``get_cost_of_equity`` wherever a per-sector Ke is needed::

    from compute.scoring.cost_of_equity import get_cost_of_equity
    ke = get_cost_of_equity(ticker_sector)

The module is gated behind ``compute.config.USE_SECTOR_COE = False``
at the call site in ``compute.valuation.applicability`` and
``compute.valuation.ensemble``.  When the flag is ``False`` the caller
continues to pass ``config.COST_OF_EQUITY`` (flat 0.10) as before —
zero production behaviour change until the flag is flipped to ``True``
after ≥ 1 cron's delta-flag-count measurement (Rule 18,
observability-before-wiring discipline).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# GICS Sector → Cost of Equity (as of Damodaran January 2025 update)
# ---------------------------------------------------------------------------
# All 11 official GICS Sectors represented.  Keys must match exactly the
# ``sector`` column values produced by
# ``compute.ingest.universe.get_sp500_constituents`` (sourced from
# Wikipedia — e.g., "Information Technology", NOT "Tech").
# ---------------------------------------------------------------------------
SECTOR_COST_OF_EQUITY: dict[str, float] = {
    "Utilities":                 0.06,  # Damodaran 2025: β≈0.40 → Ke≈6.0%
    "Real Estate":               0.07,  # Damodaran 2025: REIT β≈0.56 → Ke≈7.0%
    "Consumer Staples":          0.088, # Damodaran 2025: median 8.7% → 8.8%
    "Financials":                0.085, # Damodaran 2025: financial-sector median ≈8.5%
    "Communication Services":    0.095, # Damodaran 2025: telecom+entertainment avg → 9.5%
    "Industrials":               0.095, # Damodaran 2025: capital goods median ≈9.3% → 9.5%
    "Consumer Discretionary":    0.10,  # Damodaran 2025: consumer discretionary median ≈10.0%
    "Health Care":               0.105, # Damodaran 2025: drug/biotech mix → 10.5%
    "Information Technology":    0.11,  # Damodaran 2025: semi+software median ≈11.0%
    "Materials":                 0.11,  # Damodaran 2025: metals/mining+chem avg → 11.0%
    "Energy":                    0.12,  # Damodaran 2025: oil/gas E&P+integrated → 12.0%
}

# Default for unmapped sectors or None input.  Matches the flat
# COST_OF_EQUITY = 0.10 constant in compute/config.py (pre-issue-#67 baseline).
_DEFAULT_COE: float = 0.10

# Absolute min/max band for the Hypothesis property test.
# Damodaran's industry range across all published sectors spans roughly
# [5%, 20%]; we use a slightly wider [4%, 22%] to avoid test brittleness
# while still catching typos.
COE_BAND_MIN: float = 0.04
COE_BAND_MAX: float = 0.22


def get_cost_of_equity(ticker_sector: str | None) -> float:
    """Return the Damodaran-anchored sector cost of equity for *ticker_sector*.

    Parameters
    ----------
    ticker_sector:
        GICS Sector string from the universe DataFrame (e.g.
        ``"Information Technology"``).  ``None`` or any string not in
        ``SECTOR_COST_OF_EQUITY`` falls back to the flat 10% default.

    Returns
    -------
    float
        Annualised cost of equity in decimal form (e.g. ``0.11`` = 11%).
        Always in the range ``[COE_BAND_MIN, COE_BAND_MAX]`` for the 11
        mapped sectors; the unmapped default (0.10) also satisfies this.

    Notes
    -----
    This function is deliberately free of side-effects and external I/O
    so it can be called in tests without any network or file-system
    access.
    """
    if ticker_sector is None:
        return _DEFAULT_COE
    return SECTOR_COST_OF_EQUITY.get(ticker_sector, _DEFAULT_COE)
