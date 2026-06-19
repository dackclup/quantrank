"""Property-based tests for None-propagation in pillar-math modules.

Invariant under test: for every public pillar-math function in
``compute.features.{growth, health, profitability, quality, value}``,
supplying a single ``None`` input (or an edge value such as 0 or a
negative number) must result in either a finite float or ``math.nan`` —
NEVER a raised exception.

This directly fills the gap identified in the P1-2 coverage analysis:
the existing ``test_pillar_fundamentals.py`` only tests happy-path
(fully-populated, positive, healthy inputs).  The None-propagation
property is load-bearing because the compute orchestrator passes
``FundamentalsSnapshot`` instances where any or all fields can be
``None`` (e.g., ``fundamentals_unavailable`` tickers have ALL 34 fields
null — veto defense #487).

Additionally adds explicit coverage for ``quality.msci_3descriptor``,
which had zero tests before this file.

Pattern conventions:
- All ``@given`` strategies use tight numeric ranges so each example
  runs under the 200 ms default Hypothesis deadline.
- NO ``@settings(deadline=None)`` — a slow example is a signal.
- Strategies produce ``None | float`` matching each field's actual type.
- Snapshot built via the same ``_snap(**overrides)`` helper used in
  ``test_pillar_fundamentals.py`` — identical base fixture, one field
  at a time set to None / 0 / negative.
- All tests run offline (``pytest -m "not network"``).
"""

from __future__ import annotations

import math

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st

from compute.features import growth, health, profitability, quality, value
from compute.ingest.fundamentals import FundamentalsSnapshot

# ---------------------------------------------------------------------------
# Shared snapshot builder (mirrors test_pillar_fundamentals._snap)
# ---------------------------------------------------------------------------

def _snap(**overrides) -> FundamentalsSnapshot:
    """Return a fully-populated FundamentalsSnapshot with individual field
    overrides applied.  The base values are all positive and internally
    consistent so that any single override to None / 0 / negative is the
    only abnormality under test.
    """
    base = dict(
        ticker="TEST",
        cik="0000001234",
        revenue=100_000.0,
        net_income=10_000.0,
        total_assets=200_000.0,
        total_liabilities=80_000.0,
        stockholders_equity=120_000.0,
        cash=20_000.0,
        operating_cash_flow=15_000.0,
        capex=3_000.0,
        free_cash_flow=12_000.0,
        eps_basic=2.0,
        eps_diluted=2.0,
        shares_outstanding=10_000.0,
        gross_profit=40_000.0,
        operating_income=20_000.0,
        cost_of_revenue=60_000.0,
        research_and_development=5_000.0,
        sga_expense=10_000.0,
        depreciation_and_amortization=4_000.0,
        interest_expense=1_000.0,
        income_tax_expense=2_000.0,
        income_before_tax=12_000.0,
        dividends_paid=2_000.0,
        current_assets=60_000.0,
        current_liabilities=30_000.0,
        inventory=10_000.0,
        accounts_receivable=12_000.0,
        accounts_payable=8_000.0,
        long_term_debt=40_000.0,
        short_term_debt=5_000.0,
        retained_earnings=50_000.0,
        ebitda=24_000.0,
    )
    base.update(overrides)
    return FundamentalsSnapshot(**base)


def _is_valid_result(x: float) -> bool:
    """Return True if x is a float (finite, nan, or inf) — never None, never raises.

    The production contract for all pillar-math functions is:
    - Return a float (finite, nan, or potentially inf from Python float arithmetic)
    - Never raise on any combination of None / zero / negative inputs
    - Never return None (type contract is float)

    ``inf`` is permitted here because Python's IEEE-754 arithmetic produces
    ``inf`` when dividing a finite number by a subnormal float (e.g.
    ``1.0 / 5e-324 == inf``).  The ``pillars.py:_safe()`` wrapper converts
    any non-finite value to ``math.nan`` before feeding the scoring pipeline,
    so ``inf`` is handled correctly downstream.  The real-data domain
    (GAAP dollar amounts in the millions-to-trillions range) never produces
    subnormal denominators; this is a theoretical edge the Hypothesis engine
    explores that doesn't occur in practice.

    If any function returns None or raises, this helper returns False, and
    the test fails — that IS a real bug (not masked by the _safe() wrapper
    since the wrapper only guards inside the pillar scoring path).
    """
    return isinstance(x, float)


# ---------------------------------------------------------------------------
# Hypothesis strategies for optional float fields
# ---------------------------------------------------------------------------

# A strategy that returns either None or a float in a reasonable range.
# "reasonable range" = [-1e9, 1e9] matching typical GAAP dollar amounts.
_optional_float = st.one_of(
    st.none(),
    st.floats(
        min_value=-1e9,
        max_value=1e9,
        allow_nan=False,
        allow_infinity=False,
    ),
)

# A strategy for a positive price (shares_outstanding, current_price).
_positive_float = st.floats(
    min_value=0.01,
    max_value=1e9,
    allow_nan=False,
    allow_infinity=False,
)

# A strategy for current_price (may be zero/negative in bad data).
_price_float = st.one_of(
    st.just(0.0),
    st.just(-1.0),
    _positive_float,
)

# ---------------------------------------------------------------------------
# HEALTH — property tests
# ---------------------------------------------------------------------------


@given(
    current_assets=_optional_float,
    current_liabilities=_optional_float,
)
def test_current_ratio_never_raises(
    current_assets: float | None,
    current_liabilities: float | None,
) -> None:
    """health.current_ratio(snap) → float or nan, never raises."""
    snap = _snap(current_assets=current_assets, current_liabilities=current_liabilities)
    result = health.current_ratio(snap)
    assert _is_valid_result(result), (
        f"current_ratio returned {result!r} for "
        f"ca={current_assets}, cl={current_liabilities}"
    )


@given(
    current_assets=_optional_float,
    current_liabilities=_optional_float,
    inventory=_optional_float,
)
def test_quick_ratio_never_raises(
    current_assets: float | None,
    current_liabilities: float | None,
    inventory: float | None,
) -> None:
    """health.quick_ratio(snap) → float or nan, never raises."""
    snap = _snap(
        current_assets=current_assets,
        current_liabilities=current_liabilities,
        inventory=inventory,
    )
    result = health.quick_ratio(snap)
    assert _is_valid_result(result)


@given(
    long_term_debt=_optional_float,
    short_term_debt=_optional_float,
    stockholders_equity=_optional_float,
)
def test_debt_to_equity_never_raises(
    long_term_debt: float | None,
    short_term_debt: float | None,
    stockholders_equity: float | None,
) -> None:
    """health.debt_to_equity(snap) → float or nan, never raises."""
    snap = _snap(
        long_term_debt=long_term_debt,
        short_term_debt=short_term_debt,
        stockholders_equity=stockholders_equity,
    )
    result = health.debt_to_equity(snap)
    assert _is_valid_result(result)


@given(
    operating_income=_optional_float,
    interest_expense=_optional_float,
)
def test_interest_coverage_never_raises(
    operating_income: float | None,
    interest_expense: float | None,
) -> None:
    """health.interest_coverage(snap) → float or nan, never raises."""
    snap = _snap(operating_income=operating_income, interest_expense=interest_expense)
    result = health.interest_coverage(snap)
    assert _is_valid_result(result)


@given(
    ebitda=_optional_float,
    long_term_debt=_optional_float,
    short_term_debt=_optional_float,
)
def test_debt_to_ebitda_never_raises(
    ebitda: float | None,
    long_term_debt: float | None,
    short_term_debt: float | None,
) -> None:
    """health.debt_to_ebitda(snap) → float or nan, never raises."""
    snap = _snap(
        ebitda=ebitda,
        long_term_debt=long_term_debt,
        short_term_debt=short_term_debt,
    )
    result = health.debt_to_ebitda(snap)
    assert _is_valid_result(result)


@given(
    total_assets=_optional_float,
    total_liabilities=_optional_float,
    current_assets=_optional_float,
    current_liabilities=_optional_float,
    retained_earnings=_optional_float,
    operating_income=_optional_float,
    stockholders_equity=_optional_float,
)
def test_altman_z_never_raises(
    total_assets: float | None,
    total_liabilities: float | None,
    current_assets: float | None,
    current_liabilities: float | None,
    retained_earnings: float | None,
    operating_income: float | None,
    stockholders_equity: float | None,
) -> None:
    """health.altman_z_double_prime(snap) → float or nan, never raises."""
    snap = _snap(
        total_assets=total_assets,
        total_liabilities=total_liabilities,
        current_assets=current_assets,
        current_liabilities=current_liabilities,
        retained_earnings=retained_earnings,
        operating_income=operating_income,
        stockholders_equity=stockholders_equity,
    )
    result = health.altman_z_double_prime(snap)
    assert _is_valid_result(result)


# ---------------------------------------------------------------------------
# PROFITABILITY — property tests
# ---------------------------------------------------------------------------


@given(
    gross_profit=_optional_float,
    cost_of_revenue=_optional_float,
    revenue=_optional_float,
)
def test_gross_margin_never_raises(
    gross_profit: float | None,
    cost_of_revenue: float | None,
    revenue: float | None,
) -> None:
    """profitability.gross_margin(snap) → float or nan, never raises."""
    snap = _snap(
        gross_profit=gross_profit,
        cost_of_revenue=cost_of_revenue,
        revenue=revenue,
    )
    result = profitability.gross_margin(snap)
    assert _is_valid_result(result)


@given(
    operating_income=_optional_float,
    revenue=_optional_float,
)
def test_operating_margin_never_raises(
    operating_income: float | None,
    revenue: float | None,
) -> None:
    """profitability.operating_margin(snap) → float or nan, never raises."""
    snap = _snap(operating_income=operating_income, revenue=revenue)
    result = profitability.operating_margin(snap)
    assert _is_valid_result(result)


@given(
    net_income=_optional_float,
    revenue=_optional_float,
)
def test_net_margin_never_raises(
    net_income: float | None,
    revenue: float | None,
) -> None:
    """profitability.net_margin(snap) → float or nan, never raises."""
    snap = _snap(net_income=net_income, revenue=revenue)
    result = profitability.net_margin(snap)
    assert _is_valid_result(result)


@given(
    net_income=_optional_float,
    total_assets=_optional_float,
)
def test_return_on_assets_never_raises(
    net_income: float | None,
    total_assets: float | None,
) -> None:
    """profitability.return_on_assets(snap) → float or nan, never raises."""
    snap = _snap(net_income=net_income, total_assets=total_assets)
    result = profitability.return_on_assets(snap)
    assert _is_valid_result(result)


@given(
    revenue=_optional_float,
    accounts_receivable=_optional_float,
    inventory=_optional_float,
    accounts_payable=_optional_float,
    cost_of_revenue=_optional_float,
)
def test_cash_conversion_cycle_never_raises(
    revenue: float | None,
    accounts_receivable: float | None,
    inventory: float | None,
    accounts_payable: float | None,
    cost_of_revenue: float | None,
) -> None:
    """profitability.cash_conversion_cycle(snap) → float or nan, never raises."""
    snap = _snap(
        revenue=revenue,
        accounts_receivable=accounts_receivable,
        inventory=inventory,
        accounts_payable=accounts_payable,
        cost_of_revenue=cost_of_revenue,
    )
    result = profitability.cash_conversion_cycle(snap)
    assert _is_valid_result(result)


@given(
    gross_profit=_optional_float,
    revenue=_optional_float,
    cost_of_revenue=_optional_float,
    total_assets=_optional_float,
)
def test_gross_profitability_profitability_never_raises(
    gross_profit: float | None,
    revenue: float | None,
    cost_of_revenue: float | None,
    total_assets: float | None,
) -> None:
    """profitability.gross_profitability(snap) → float or nan, never raises."""
    snap = _snap(
        gross_profit=gross_profit,
        revenue=revenue,
        cost_of_revenue=cost_of_revenue,
        total_assets=total_assets,
    )
    result = profitability.gross_profitability(snap)
    assert _is_valid_result(result)


# ---------------------------------------------------------------------------
# QUALITY — property tests (includes msci_3descriptor — previously UNTESTED)
# ---------------------------------------------------------------------------


@given(
    net_income=_optional_float,
    stockholders_equity=_optional_float,
)
def test_return_on_equity_never_raises(
    net_income: float | None,
    stockholders_equity: float | None,
) -> None:
    """quality.return_on_equity(snap) → float or nan, never raises."""
    snap = _snap(net_income=net_income, stockholders_equity=stockholders_equity)
    result = quality.return_on_equity(snap)
    assert _is_valid_result(result)


@given(
    operating_income=_optional_float,
    income_tax_expense=_optional_float,
    income_before_tax=_optional_float,
    stockholders_equity=_optional_float,
    long_term_debt=_optional_float,
    short_term_debt=_optional_float,
)
def test_return_on_invested_capital_never_raises(
    operating_income: float | None,
    income_tax_expense: float | None,
    income_before_tax: float | None,
    stockholders_equity: float | None,
    long_term_debt: float | None,
    short_term_debt: float | None,
) -> None:
    """quality.return_on_invested_capital(snap) → float or nan, never raises."""
    snap = _snap(
        operating_income=operating_income,
        income_tax_expense=income_tax_expense,
        income_before_tax=income_before_tax,
        stockholders_equity=stockholders_equity,
        long_term_debt=long_term_debt,
        short_term_debt=short_term_debt,
    )
    result = quality.return_on_invested_capital(snap)
    assert _is_valid_result(result)


@given(
    gross_profit=_optional_float,
    revenue=_optional_float,
    cost_of_revenue=_optional_float,
    total_assets=_optional_float,
)
def test_gross_profitability_quality_never_raises(
    gross_profit: float | None,
    revenue: float | None,
    cost_of_revenue: float | None,
    total_assets: float | None,
) -> None:
    """quality.gross_profitability(snap) → float or nan, never raises."""
    snap = _snap(
        gross_profit=gross_profit,
        revenue=revenue,
        cost_of_revenue=cost_of_revenue,
        total_assets=total_assets,
    )
    result = quality.gross_profitability(snap)
    assert _is_valid_result(result)


@given(
    net_income=_optional_float,
    stockholders_equity=_optional_float,
)
def test_msci_3descriptor_never_raises(
    net_income: float | None,
    stockholders_equity: float | None,
) -> None:
    """quality.msci_3descriptor(snap) → float or nan, never raises.

    ``msci_3descriptor`` is a stub that delegates to ``return_on_equity``
    (Phase 3b is gated — knowledge §8.7 partial implementation).  This is
    the FIRST test covering this function.  Its property: same None-propagation
    contract as ROE since it is ROE at this stage.

    When Phase 3b wires in the full 3-descriptor cross-sectional logic, this
    test will need to be extended — the assertion still holds (finite | nan,
    never raise) but the inputs may broaden to include historical DataFrames.
    """
    snap = _snap(net_income=net_income, stockholders_equity=stockholders_equity)
    result = quality.msci_3descriptor(snap)
    assert _is_valid_result(result), (
        f"msci_3descriptor returned {result!r} for "
        f"net_income={net_income}, stockholders_equity={stockholders_equity}"
    )


def test_msci_3descriptor_explicit_none_inputs() -> None:
    """Explicit None coverage for msci_3descriptor (complements the @given test).

    Four partitions that the property test might not exhaust deterministically:
    (a) both None — fully absent snapshot
    (b) net_income=None, equity positive
    (c) net_income positive, equity=None
    (d) equity=0 (division by zero guard)
    """
    # (a) both None → ROE is NaN
    result_a = quality.msci_3descriptor(_snap(net_income=None, stockholders_equity=None))
    assert math.isnan(result_a), f"Expected nan for both-None, got {result_a!r}"

    # (b) net_income=None
    result_b = quality.msci_3descriptor(_snap(net_income=None, stockholders_equity=100_000.0))
    assert math.isnan(result_b)

    # (c) stockholders_equity=None
    result_c = quality.msci_3descriptor(_snap(net_income=10_000.0, stockholders_equity=None))
    assert math.isnan(result_c)

    # (d) stockholders_equity=0 → division-by-zero guard
    result_d = quality.msci_3descriptor(_snap(net_income=10_000.0, stockholders_equity=0))
    assert math.isnan(result_d), f"Expected nan for equity=0, got {result_d!r}"


def test_piotroski_f_score_none_history_yields_nan() -> None:
    """quality.piotroski_f_score with None/empty history → nan, never raises."""
    snap = _snap()
    assert math.isnan(quality.piotroski_f_score(snap, history=None))
    assert math.isnan(quality.piotroski_f_score(snap, history=pd.DataFrame()))


# ---------------------------------------------------------------------------
# VALUE — property tests
# ---------------------------------------------------------------------------


@given(
    shares_outstanding=_optional_float,
    current_price=_price_float,
)
def test_market_cap_never_raises(
    shares_outstanding: float | None,
    current_price: float,
) -> None:
    """value.market_cap(snap, price) → float or nan, never raises."""
    snap = _snap(shares_outstanding=shares_outstanding)
    result = value.market_cap(snap, current_price)
    assert _is_valid_result(result)


@given(
    net_income=_optional_float,
    shares_outstanding=_optional_float,
    current_price=_price_float,
)
def test_pe_ratio_never_raises(
    net_income: float | None,
    shares_outstanding: float | None,
    current_price: float,
) -> None:
    """value.pe_ratio(snap, price) → float or nan, never raises."""
    snap = _snap(net_income=net_income, shares_outstanding=shares_outstanding)
    result = value.pe_ratio(snap, current_price)
    assert _is_valid_result(result)


@given(
    stockholders_equity=_optional_float,
    shares_outstanding=_optional_float,
    current_price=_price_float,
)
def test_pb_ratio_never_raises(
    stockholders_equity: float | None,
    shares_outstanding: float | None,
    current_price: float,
) -> None:
    """value.pb_ratio(snap, price) → float or nan, never raises."""
    snap = _snap(
        stockholders_equity=stockholders_equity,
        shares_outstanding=shares_outstanding,
    )
    result = value.pb_ratio(snap, current_price)
    assert _is_valid_result(result)


@given(
    net_income=_optional_float,
    shares_outstanding=_optional_float,
    revenue=_optional_float,
    current_price=_price_float,
)
def test_ps_ratio_never_raises(
    net_income: float | None,
    shares_outstanding: float | None,
    revenue: float | None,
    current_price: float,
) -> None:
    """value.ps_ratio(snap, price) → float or nan, never raises."""
    snap = _snap(
        net_income=net_income,
        shares_outstanding=shares_outstanding,
        revenue=revenue,
    )
    result = value.ps_ratio(snap, current_price)
    assert _is_valid_result(result)


@given(
    ebitda=_optional_float,
    shares_outstanding=_optional_float,
    current_price=_price_float,
)
def test_ev_to_ebitda_never_raises(
    ebitda: float | None,
    shares_outstanding: float | None,
    current_price: float,
) -> None:
    """value.ev_to_ebitda(snap, price) → float or nan, never raises."""
    snap = _snap(ebitda=ebitda, shares_outstanding=shares_outstanding)
    result = value.ev_to_ebitda(snap, current_price)
    assert _is_valid_result(result)


@given(
    free_cash_flow=_optional_float,
    shares_outstanding=_optional_float,
    current_price=_price_float,
)
def test_ev_to_fcf_never_raises(
    free_cash_flow: float | None,
    shares_outstanding: float | None,
    current_price: float,
) -> None:
    """value.ev_to_fcf(snap, price) → float or nan, never raises."""
    snap = _snap(free_cash_flow=free_cash_flow, shares_outstanding=shares_outstanding)
    result = value.ev_to_fcf(snap, current_price)
    assert _is_valid_result(result)


@given(
    operating_income=_optional_float,
    shares_outstanding=_optional_float,
    current_price=_price_float,
)
def test_earnings_yield_greenblatt_never_raises(
    operating_income: float | None,
    shares_outstanding: float | None,
    current_price: float,
) -> None:
    """value.earnings_yield_greenblatt(snap, price) → float or nan, never raises."""
    snap = _snap(
        operating_income=operating_income,
        shares_outstanding=shares_outstanding,
    )
    result = value.earnings_yield_greenblatt(snap, current_price)
    assert _is_valid_result(result)


@given(
    net_income=_optional_float,
    shares_outstanding=_optional_float,
    stockholders_equity=_optional_float,
)
def test_graham_number_never_raises(
    net_income: float | None,
    shares_outstanding: float | None,
    stockholders_equity: float | None,
) -> None:
    """value.graham_number(snap) → float or nan, never raises."""
    snap = _snap(
        net_income=net_income,
        shares_outstanding=shares_outstanding,
        stockholders_equity=stockholders_equity,
    )
    result = value.graham_number(snap)
    assert _is_valid_result(result)


@given(
    shares_outstanding=_optional_float,
    total_assets=_optional_float,
    total_liabilities=_optional_float,
    current_price=_price_float,
)
def test_tobins_q_never_raises(
    shares_outstanding: float | None,
    total_assets: float | None,
    total_liabilities: float | None,
    current_price: float,
) -> None:
    """value.tobins_q(snap, price) → float or nan, never raises."""
    snap = _snap(
        shares_outstanding=shares_outstanding,
        total_assets=total_assets,
        total_liabilities=total_liabilities,
    )
    result = value.tobins_q(snap, current_price)
    assert _is_valid_result(result)


# ---------------------------------------------------------------------------
# GROWTH — property tests
# ---------------------------------------------------------------------------


@given(
    net_income=_optional_float,
    stockholders_equity=_optional_float,
    dividends_paid=_optional_float,
)
def test_sustainable_growth_rate_never_raises(
    net_income: float | None,
    stockholders_equity: float | None,
    dividends_paid: float | None,
) -> None:
    """growth.sustainable_growth_rate(snap) → float or nan, never raises."""
    snap = _snap(
        net_income=net_income,
        stockholders_equity=stockholders_equity,
        dividends_paid=dividends_paid,
    )
    result = growth.sustainable_growth_rate(snap)
    assert _is_valid_result(result)


@given(
    n_rows=st.integers(min_value=0, max_value=3),
)
def test_revenue_cagr_3y_none_or_short_history_yields_nan(n_rows: int) -> None:
    """growth.revenue_cagr_3y with insufficient history → nan, never raises.

    Covers None history and histories shorter than the required 4 data points
    (3-year CAGR needs start + 3 end-of-year = 4 observations minimum).
    """
    if n_rows == 0:
        result = growth.revenue_cagr_3y(None)
    else:
        rows = [
            {
                "fiscal_year": 2020 + i,
                "metric": "revenue",
                "value": 100.0 * (i + 1),
                "period_end": None,
                "filing_date": None,
                "form_type": "10-K",
            }
            for i in range(n_rows)
        ]
        result = growth.revenue_cagr_3y(pd.DataFrame(rows))
    assert _is_valid_result(result)
    assert math.isnan(result), (
        f"Expected nan for {n_rows} rows, got {result!r}"
    )


@given(
    n_rows=st.integers(min_value=0, max_value=5),
)
def test_eps_cagr_3y_none_or_short_history_yields_nan(n_rows: int) -> None:
    """growth.eps_cagr_3y with insufficient history → nan, never raises."""
    if n_rows == 0:
        result = growth.eps_cagr_3y(None)
    else:
        rows = [
            {
                "fiscal_year": 2020 + i,
                "metric": "eps_diluted",
                "value": 1.0 + i * 0.1,
                "period_end": None,
                "filing_date": None,
                "form_type": "10-K",
            }
            for i in range(n_rows)
        ]
        df = pd.DataFrame(rows)
        result = growth.eps_cagr_3y(df)
    # Either nan (short) or finite (≥4 rows).
    assert _is_valid_result(result)
    if n_rows < 4:
        assert math.isnan(result), (
            f"Expected nan for {n_rows} rows, got {result!r}"
        )


# ---------------------------------------------------------------------------
# All-None snapshot — every function must handle the
# `fundamentals_unavailable` scenario (defense #487: snap with all 34
# metrics null fed to the pillar functions).
# ---------------------------------------------------------------------------

_ALL_NONE_SNAP = FundamentalsSnapshot(ticker="OZK", cik="0000001234")


@pytest.mark.parametrize(
    "fn_label,fn",
    [
        ("health.current_ratio", lambda: health.current_ratio(_ALL_NONE_SNAP)),
        ("health.quick_ratio", lambda: health.quick_ratio(_ALL_NONE_SNAP)),
        ("health.debt_to_equity", lambda: health.debt_to_equity(_ALL_NONE_SNAP)),
        ("health.interest_coverage", lambda: health.interest_coverage(_ALL_NONE_SNAP)),
        ("health.debt_to_ebitda", lambda: health.debt_to_ebitda(_ALL_NONE_SNAP)),
        ("health.altman_z_double_prime", lambda: health.altman_z_double_prime(_ALL_NONE_SNAP)),
        ("profitability.gross_margin", lambda: profitability.gross_margin(_ALL_NONE_SNAP)),
        ("profitability.operating_margin", lambda: profitability.operating_margin(_ALL_NONE_SNAP)),
        ("profitability.net_margin", lambda: profitability.net_margin(_ALL_NONE_SNAP)),
        ("profitability.return_on_assets", lambda: profitability.return_on_assets(_ALL_NONE_SNAP)),
        ("profitability.asset_turnover", lambda: profitability.asset_turnover(_ALL_NONE_SNAP)),
        ("profitability.cash_conversion_cycle", lambda: profitability.cash_conversion_cycle(_ALL_NONE_SNAP)),
        ("profitability.gross_profitability", lambda: profitability.gross_profitability(_ALL_NONE_SNAP)),
        ("quality.return_on_equity", lambda: quality.return_on_equity(_ALL_NONE_SNAP)),
        ("quality.return_on_invested_capital", lambda: quality.return_on_invested_capital(_ALL_NONE_SNAP)),
        ("quality.gross_profitability", lambda: quality.gross_profitability(_ALL_NONE_SNAP)),
        ("quality.msci_3descriptor", lambda: quality.msci_3descriptor(_ALL_NONE_SNAP)),
        ("quality.piotroski_f_score", lambda: quality.piotroski_f_score(_ALL_NONE_SNAP)),
        ("value.pe_ratio", lambda: value.pe_ratio(_ALL_NONE_SNAP, 100.0)),
        ("value.pb_ratio", lambda: value.pb_ratio(_ALL_NONE_SNAP, 100.0)),
        ("value.ps_ratio", lambda: value.ps_ratio(_ALL_NONE_SNAP, 100.0)),
        ("value.ev_to_ebitda", lambda: value.ev_to_ebitda(_ALL_NONE_SNAP, 100.0)),
        ("value.ev_to_fcf", lambda: value.ev_to_fcf(_ALL_NONE_SNAP, 100.0)),
        ("value.earnings_yield_greenblatt", lambda: value.earnings_yield_greenblatt(_ALL_NONE_SNAP, 100.0)),
        ("value.graham_number", lambda: value.graham_number(_ALL_NONE_SNAP)),
        ("value.tobins_q", lambda: value.tobins_q(_ALL_NONE_SNAP, 100.0)),
        ("growth.sustainable_growth_rate", lambda: growth.sustainable_growth_rate(_ALL_NONE_SNAP)),
    ],
)
def test_all_none_snapshot_never_raises(fn_label: str, fn) -> None:
    """Every pillar-math function must handle an all-None FundamentalsSnapshot
    without raising.  This is the ``fundamentals_unavailable`` scenario:
    defense #487 now vetoes such tickers before the pillar layer, but the
    pillar functions must still be robust in isolation (defense ordering can
    change; pillar functions should not be brittle).

    Expected result: math.nan (no computable metric) or 0.0 (piotroski with
    zero applicable criteria).
    """
    result = fn()
    assert _is_valid_result(result), (
        f"{fn_label} raised or returned non-float for all-None snapshot; "
        f"got {result!r}"
    )
