"""Unit + property tests for compute.scoring.form4_signals
(Phase 4.5e PR 3 — annotate emission layer).

All offline. The two predicates operate on the cache-dict shape
documented in compute.scoring.form4_insider — a list of plain dicts,
one per insider transaction. No edgartools / SEC fetch involved.

Methodology anchors (see module docstring for citations):

- Cohen-Malloy-Pomorski 2012 §III.A — opportunistic-transaction set
  {S, D}; ≥ 3 distinct insiders / same-direction cluster definition
- Jeng-Metrick-Zeckhauser 2003 §V — CFO + CEO co-sell signature
- Jagolinzer 2009 §3.2 — 30-day signal-decay regime
"""

from __future__ import annotations

from datetime import date, timedelta

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from compute.scoring.form4_signals import (
    C_SUITE_UNUSUAL_SELL_LOOKBACK_DAYS,
    C_SUITE_UNUSUAL_SELL_MIN_DISTINCT_INSIDERS,
    INSIDER_SELL_CLUSTER_LOOKBACK_DAYS,
    INSIDER_SELL_CLUSTER_MIN_DISTINCT_INSIDERS,
    INSIDER_SELL_CLUSTER_MIN_DOLLAR_VALUE,
    _is_opportunistic_sell,  # private helper, direct import
    count_10b5_1_filtered_transactions,
    detect_c_suite_unusual_sell,
    detect_insider_sell_cluster,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

AS_OF = date(2026, 5, 23)


def _tx(
    *,
    cik: str,
    days_ago: int,
    code: str = "S",
    dollar_value: float = 500_000.0,
    is_officer: bool = False,
    officer_title: str | None = None,
) -> dict:
    """Minimal Form-4 transaction dict matching the cache shape."""
    tx_date = AS_OF - timedelta(days=days_ago)
    return {
        "accession": f"0001-{cik}-{days_ago:03d}",
        "filing_date": tx_date.isoformat(),
        "transaction_date": tx_date.isoformat(),
        "insider_name": f"INSIDER {cik}",
        "insider_cik": cik,
        "is_director": False,
        "is_officer": is_officer,
        "is_ten_percent_owner": False,
        "officer_title": officer_title,
        "transaction_code": code,
        "shares": 1000.0,
        "price_per_share": 100.0,
        "dollar_value": dollar_value,
        "shares_owned_following": 5000.0,
        "filing_url": "https://example.com/",
    }


# ---------------------------------------------------------------------------
# insider_sell_cluster
# ---------------------------------------------------------------------------


def test_cluster_none_input_returns_false():
    assert detect_insider_sell_cluster(None, AS_OF) is False


def test_cluster_empty_input_returns_false():
    assert detect_insider_sell_cluster([], AS_OF) is False


def test_cluster_below_distinct_threshold_returns_false():
    # 2 distinct insiders — needs ≥ 3.
    txns = [
        _tx(cik="A", days_ago=5, dollar_value=600_000),
        _tx(cik="B", days_ago=10, dollar_value=600_000),
    ]
    assert detect_insider_sell_cluster(txns, AS_OF) is False


def test_cluster_below_dollar_floor_returns_false():
    # 3 distinct insiders BUT total $ < $1M.
    txns = [
        _tx(cik="A", days_ago=5, dollar_value=300_000),
        _tx(cik="B", days_ago=10, dollar_value=300_000),
        _tx(cik="C", days_ago=15, dollar_value=300_000),
    ]
    assert detect_insider_sell_cluster(txns, AS_OF) is False


def test_cluster_at_thresholds_fires():
    # Exactly 3 distinct insiders, exactly $1M total.
    txns = [
        _tx(cik="A", days_ago=5, dollar_value=400_000),
        _tx(cik="B", days_ago=10, dollar_value=400_000),
        _tx(cik="C", days_ago=15, dollar_value=200_000),
    ]
    assert detect_insider_sell_cluster(txns, AS_OF) is True


def test_cluster_outside_window_does_not_fire():
    # All transactions older than the 30-day window.
    txns = [
        _tx(cik="A", days_ago=45, dollar_value=600_000),
        _tx(cik="B", days_ago=60, dollar_value=600_000),
        _tx(cik="C", days_ago=75, dollar_value=600_000),
    ]
    assert detect_insider_sell_cluster(txns, AS_OF) is False


def test_cluster_at_window_boundary_inclusive():
    # Exactly 30 days ago — boundary is inclusive.
    txns = [
        _tx(cik="A", days_ago=30, dollar_value=400_000),
        _tx(cik="B", days_ago=30, dollar_value=400_000),
        _tx(cik="C", days_ago=30, dollar_value=400_000),
    ]
    assert detect_insider_sell_cluster(txns, AS_OF) is True


def test_cluster_excludes_compensation_code_f():
    # Code F is tax-via-shares (compensation-mechanical) per CMP 2012.
    # 3 distinct insiders BUT all on code F → does not count as
    # opportunistic, no fire even at $3M total.
    txns = [
        _tx(cik="A", days_ago=5, code="F", dollar_value=1_000_000),
        _tx(cik="B", days_ago=10, code="F", dollar_value=1_000_000),
        _tx(cik="C", days_ago=15, code="F", dollar_value=1_000_000),
    ]
    assert detect_insider_sell_cluster(txns, AS_OF) is False


def test_cluster_includes_code_d_sale_back_to_issuer():
    # Code D is sale-back-to-issuer — per CMP 2012 §III.A this IS
    # opportunistic and counts toward the cluster.
    txns = [
        _tx(cik="A", days_ago=5, code="D", dollar_value=400_000),
        _tx(cik="B", days_ago=10, code="S", dollar_value=400_000),
        _tx(cik="C", days_ago=15, code="D", dollar_value=400_000),
    ]
    assert detect_insider_sell_cluster(txns, AS_OF) is True


def test_cluster_excludes_grant_and_exercise_codes():
    # Codes A (grant), M (exercise), G (gift) are compensation-mechanical.
    txns = [
        _tx(cik="A", days_ago=5, code="A", dollar_value=1_000_000),
        _tx(cik="B", days_ago=10, code="M", dollar_value=1_000_000),
        _tx(cik="C", days_ago=15, code="G", dollar_value=1_000_000),
    ]
    assert detect_insider_sell_cluster(txns, AS_OF) is False


def test_cluster_same_insider_multiple_txns_counts_once():
    # Same CIK with multiple transactions counts as 1 distinct insider,
    # not 3 — guards against single-insider spam triggering the cluster.
    txns = [
        _tx(cik="A", days_ago=5, dollar_value=2_000_000),
        _tx(cik="A", days_ago=10, dollar_value=2_000_000),
        _tx(cik="A", days_ago=15, dollar_value=2_000_000),
    ]
    assert detect_insider_sell_cluster(txns, AS_OF) is False


def test_cluster_missing_cik_skipped():
    # A row with no insider_cik should be ignored — defensive against
    # cache corruption / partial parses.
    txns = [
        _tx(cik="", days_ago=5, dollar_value=2_000_000),
        _tx(cik="B", days_ago=10, dollar_value=400_000),
        _tx(cik="C", days_ago=15, dollar_value=400_000),
    ]
    assert detect_insider_sell_cluster(txns, AS_OF) is False  # only 2 valid


def test_cluster_dollar_value_none_excluded_from_sum():
    # Insiders count toward distinct-CIK threshold but None dollar_value
    # contributes 0 to the sum — guards against missing price data.
    txns = [
        _tx(cik="A", days_ago=5, dollar_value=400_000),
        _tx(cik="B", days_ago=10, dollar_value=400_000),
        _tx(cik="C", days_ago=15, dollar_value=None),  # type: ignore[arg-type]
    ]
    assert detect_insider_sell_cluster(txns, AS_OF) is False  # only $800K


# ---------------------------------------------------------------------------
# c_suite_unusual_sell
# ---------------------------------------------------------------------------


def test_c_suite_none_input_returns_false():
    assert detect_c_suite_unusual_sell(None, AS_OF) is False


def test_c_suite_below_distinct_threshold_returns_false():
    # Only 1 C-suite insider — needs ≥ 2.
    txns = [
        _tx(cik="A", days_ago=5, is_officer=True, officer_title="CEO"),
    ]
    assert detect_c_suite_unusual_sell(txns, AS_OF) is False


def test_c_suite_ceo_plus_cfo_fires():
    # Canonical JMZ 2003 signature.
    txns = [
        _tx(cik="A", days_ago=5, is_officer=True, officer_title="CEO"),
        _tx(cik="B", days_ago=10, is_officer=True, officer_title="CFO"),
    ]
    assert detect_c_suite_unusual_sell(txns, AS_OF) is True


def test_c_suite_chief_executive_officer_full_title():
    # The regex should match the verbose form too.
    txns = [
        _tx(cik="A", days_ago=5, is_officer=True,
            officer_title="Chief Executive Officer"),
        _tx(cik="B", days_ago=10, is_officer=True,
            officer_title="Chief Financial Officer"),
    ]
    assert detect_c_suite_unusual_sell(txns, AS_OF) is True


def test_c_suite_president_counts_per_wachtell_lipton_2018():
    # 31% of S&P 500 use President as the operating-CEO title.
    txns = [
        _tx(cik="A", days_ago=5, is_officer=True, officer_title="President"),
        _tx(cik="B", days_ago=10, is_officer=True, officer_title="CFO"),
    ]
    assert detect_c_suite_unusual_sell(txns, AS_OF) is True


def test_c_suite_excludes_coo():
    # Per JMZ 2003 — COO is operational not financial-information.
    txns = [
        _tx(cik="A", days_ago=5, is_officer=True, officer_title="CEO"),
        _tx(cik="B", days_ago=10, is_officer=True, officer_title="COO"),
    ]
    assert detect_c_suite_unusual_sell(txns, AS_OF) is False  # only CEO valid


def test_c_suite_excludes_cto_cmo_chro():
    # Methodology-scientist Mode B: regex deliberately narrow.
    txns = [
        _tx(cik="A", days_ago=5, is_officer=True, officer_title="CTO"),
        _tx(cik="B", days_ago=10, is_officer=True,
            officer_title="Chief Marketing Officer"),
        _tx(cik="C", days_ago=15, is_officer=True,
            officer_title="Chief Human Resources Officer"),
    ]
    assert detect_c_suite_unusual_sell(txns, AS_OF) is False


def test_c_suite_director_only_excluded():
    # is_officer=False — board director, not C-suite.
    txns = [
        _tx(cik="A", days_ago=5, is_officer=False, officer_title="CEO"),
        _tx(cik="B", days_ago=10, is_officer=False, officer_title="CFO"),
    ]
    assert detect_c_suite_unusual_sell(txns, AS_OF) is False


def test_c_suite_excludes_compensation_code_f():
    # Same opportunistic-code partition as the cluster flag.
    txns = [
        _tx(cik="A", days_ago=5, is_officer=True, officer_title="CEO", code="F"),
        _tx(cik="B", days_ago=10, is_officer=True, officer_title="CFO", code="F"),
    ]
    assert detect_c_suite_unusual_sell(txns, AS_OF) is False


def test_c_suite_outside_30d_window_does_not_fire():
    txns = [
        _tx(cik="A", days_ago=40, is_officer=True, officer_title="CEO"),
        _tx(cik="B", days_ago=50, is_officer=True, officer_title="CFO"),
    ]
    assert detect_c_suite_unusual_sell(txns, AS_OF) is False


def test_c_suite_no_dollar_floor():
    # C-suite flag has no dollar threshold — JMZ 2003 signal is in
    # the co-occurrence pattern, not the $ size.
    txns = [
        _tx(cik="A", days_ago=5, is_officer=True,
            officer_title="CEO", dollar_value=1.0),
        _tx(cik="B", days_ago=10, is_officer=True,
            officer_title="CFO", dollar_value=1.0),
    ]
    assert detect_c_suite_unusual_sell(txns, AS_OF) is True


# ---------------------------------------------------------------------------
# Threshold-constant pins — guard against accidental retuning
# ---------------------------------------------------------------------------


def test_threshold_constants_pinned_to_methodology_verdict():
    # Methodology-scientist Mode B verdict (Phase 4.5e PR 3):
    # CMP 2012 cluster def (≥ 3); JMZ 2003 C-suite def (≥ 2);
    # Jagolinzer 2009 30d window; $1M cohort floor (gut-feel, S&P 500 scale).
    # Any change to these constants requires a methodology-scientist
    # Mode B re-validation — bumping the test means re-anchoring against
    # literature.
    assert INSIDER_SELL_CLUSTER_MIN_DISTINCT_INSIDERS == 3
    assert INSIDER_SELL_CLUSTER_LOOKBACK_DAYS == 30
    assert INSIDER_SELL_CLUSTER_MIN_DOLLAR_VALUE == 1_000_000.0
    assert C_SUITE_UNUSUAL_SELL_MIN_DISTINCT_INSIDERS == 2
    assert C_SUITE_UNUSUAL_SELL_LOOKBACK_DAYS == 30


# ---------------------------------------------------------------------------
# Hypothesis property — monotonicity invariant (Process Hygiene Item #1)
# ---------------------------------------------------------------------------


@settings(
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    max_examples=50,
)
@given(
    n_extra_zero_value_grants=st.integers(min_value=0, max_value=50),
)
def test_cluster_monotonic_under_added_compensation_txns(
    n_extra_zero_value_grants: int,
) -> None:
    """Adding compensation-tied transactions (codes A/M/F/G) to a known-
    firing cluster cohort must NEVER flip the result from True to False.

    The whole point of the {S, D} opportunistic-set partition is that
    grants and exercises don't pollute the signal. Hypothesis stress-
    tests this invariant across random batch sizes of code-A grants.
    """
    fired_base_txns = [
        _tx(cik="A", days_ago=5, dollar_value=400_000),
        _tx(cik="B", days_ago=10, dollar_value=400_000),
        _tx(cik="C", days_ago=15, dollar_value=400_000),
    ]
    assert detect_insider_sell_cluster(fired_base_txns, AS_OF) is True

    extra_grants = [
        _tx(
            cik=f"GRANT{i}",
            days_ago=(i % 25) + 1,
            code="A",
            dollar_value=5_000_000.0,
        )
        for i in range(n_extra_zero_value_grants)
    ]
    polluted = fired_base_txns + extra_grants
    assert detect_insider_sell_cluster(polluted, AS_OF) is True


@settings(
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    max_examples=50,
)
@given(
    days_ago=st.integers(min_value=1, max_value=200),
)
def test_cluster_fires_only_within_lookback(days_ago: int) -> None:
    """A 3-insider cohort with $1M+ total should fire iff all
    transactions fall within the 30-day window."""
    txns = [
        _tx(cik="A", days_ago=days_ago, dollar_value=400_000),
        _tx(cik="B", days_ago=days_ago, dollar_value=400_000),
        _tx(cik="C", days_ago=days_ago, dollar_value=400_000),
    ]
    fired = detect_insider_sell_cluster(txns, AS_OF)
    assert fired == (days_ago <= INSIDER_SELL_CLUSTER_LOOKBACK_DAYS)


# ---------------------------------------------------------------------------
# Strict-superset invariant — c_suite firing implies cluster firing
# ---------------------------------------------------------------------------


def test_strict_superset_invariant_with_sufficient_dollar_value():
    """Per the manipulation_index.py DELTA semantic: when c_suite fires
    AND the cohort meets the $1M cluster floor, BOTH flags fire — so
    the combined weight 5 + 3 = 8 lands. This test pins the strict-
    superset relationship that the DELTA semantic depends on."""
    txns = [
        _tx(cik="A", days_ago=5, is_officer=True,
            officer_title="CEO", dollar_value=600_000),
        _tx(cik="B", days_ago=10, is_officer=True,
            officer_title="CFO", dollar_value=600_000),
        # Third insider needed for the cluster's ≥ 3 distinct hurdle
        _tx(cik="C", days_ago=15, dollar_value=400_000),
    ]
    cluster_fires = detect_insider_sell_cluster(txns, AS_OF)
    c_suite_fires = detect_c_suite_unusual_sell(txns, AS_OF)
    assert c_suite_fires is True
    assert cluster_fires is True


def test_c_suite_can_fire_alone_when_cluster_dollar_floor_missed():
    """Edge: c_suite has no dollar floor, so 2 C-suite insiders selling
    small amounts trigger c_suite but NOT cluster (which requires $1M).
    This is the only case where DELTA semantic breaks down — the
    c_suite flag contributes its 3 pts in isolation rather than as a
    delta on top of cluster's 5. Documented behavior."""
    txns = [
        _tx(cik="A", days_ago=5, is_officer=True,
            officer_title="CEO", dollar_value=100_000),
        _tx(cik="B", days_ago=10, is_officer=True,
            officer_title="CFO", dollar_value=100_000),
    ]
    assert detect_c_suite_unusual_sell(txns, AS_OF) is True
    assert detect_insider_sell_cluster(txns, AS_OF) is False  # < $1M


def _tx_10b5(
    *,
    cik: str,
    days_ago: int,
    code: str = "S",
    dollar_value: float = 500_000.0,
    is_officer: bool = False,
    officer_title: str | None = None,
    is_rule_10b5_one: bool | None = False,
) -> dict:
    """Variant of _tx that includes the PR 4-eq is_rule_10b5_one field."""
    base = _tx(
        cik=cik,
        days_ago=days_ago,
        code=code,
        dollar_value=dollar_value,
        is_officer=is_officer,
        officer_title=officer_title,
    )
    base["is_rule_10b5_one"] = is_rule_10b5_one
    return base


# ---------------------------------------------------------------------------
# PR 4-eq: _is_opportunistic_sell — 10b5-1 filter unit tests (#1-#4)
# ---------------------------------------------------------------------------


def test_opportunistic_sell_excludes_explicit_10b5_1_true():
    """A transaction with is_rule_10b5_one=True must be excluded from
    the opportunistic cohort — it is a pre-scheduled trade with near-zero
    information-asymmetry signal (Jagolinzer 2009 §3.1)."""
    tx = {"transaction_code": "S", "is_rule_10b5_one": True}
    assert _is_opportunistic_sell(tx) is False


def test_opportunistic_sell_includes_explicit_10b5_1_false():
    """A transaction explicitly marked as NOT a 10b5-1 plan is
    opportunistic per the CMP 2012 §III.A partition."""
    tx = {"transaction_code": "S", "is_rule_10b5_one": False}
    assert _is_opportunistic_sell(tx) is True


def test_opportunistic_sell_includes_10b5_1_none_pre_mandate_compat():
    """is_rule_10b5_one=None means 'no 10b5-1 footnote resolved' — the
    option (a) None-handling pin per methodology-scientist Mode B 2026-05-23.
    Such trades remain in the opportunistic cohort (matches the CMP 2012 /
    Jagolinzer 2009 calibration regime)."""
    tx = {"transaction_code": "S", "is_rule_10b5_one": None}
    assert _is_opportunistic_sell(tx) is True


def test_opportunistic_sell_legacy_row_without_10b5_field_passes():
    """Pre-PR-4-eq cache rows have no is_rule_10b5_one key at all. The
    dict.get() fallback returns None, which passes through as opportunistic.
    Back-compat invariant: existing caches must not have their cluster
    signals wiped until the TTL repopulates them."""
    tx = {"transaction_code": "S"}  # no is_rule_10b5_one key
    assert _is_opportunistic_sell(tx) is True


# ---------------------------------------------------------------------------
# PR 4-eq: cluster + c_suite with 10b5-1 filter (#5-#8)
# ---------------------------------------------------------------------------


def test_cluster_with_majority_10b5_1_drops_below_threshold():
    """4 distinct insiders all selling $1M+ opportunistic codes, but 3 of 4
    are 10b5-1 scheduled trades. Only 1 distinct CIK survives the filter —
    below the MIN_DISTINCT_INSIDERS=3 threshold. Flag must NOT fire."""
    txns = [
        _tx_10b5(cik="A", days_ago=5, dollar_value=400_000, is_rule_10b5_one=True),
        _tx_10b5(cik="B", days_ago=8, dollar_value=400_000, is_rule_10b5_one=True),
        _tx_10b5(cik="C", days_ago=12, dollar_value=400_000, is_rule_10b5_one=True),
        _tx_10b5(cik="D", days_ago=15, dollar_value=400_000, is_rule_10b5_one=False),
    ]
    assert detect_insider_sell_cluster(txns, AS_OF) is False


def test_cluster_with_minority_10b5_1_still_fires():
    """5 distinct insiders, only 1 is 10b5-1 scheduled. 4 distinct CIKs
    survive the filter — above MIN_DISTINCT_INSIDERS=3 and with total
    dollar_value ≥ $1M. Flag must fire."""
    txns = [
        _tx_10b5(cik="A", days_ago=3, dollar_value=300_000, is_rule_10b5_one=False),
        _tx_10b5(cik="B", days_ago=5, dollar_value=300_000, is_rule_10b5_one=False),
        _tx_10b5(cik="C", days_ago=8, dollar_value=300_000, is_rule_10b5_one=False),
        _tx_10b5(cik="D", days_ago=10, dollar_value=300_000, is_rule_10b5_one=False),
        _tx_10b5(cik="E", days_ago=12, dollar_value=400_000, is_rule_10b5_one=True),
    ]
    assert detect_insider_sell_cluster(txns, AS_OF) is True


def test_c_suite_inherits_10b5_1_filter():
    """CEO with is_rule_10b5_one=True + CFO with is_rule_10b5_one=False.
    Only 1 distinct C-suite CIK survives — below MIN_DISTINCT_INSIDERS=2.
    The c_suite flag must NOT fire: the 10b5-1 filter applies equally
    to both predicates via _is_opportunistic_sell."""
    txns = [
        _tx_10b5(
            cik="A", days_ago=5, is_officer=True, officer_title="CEO",
            dollar_value=200_000, is_rule_10b5_one=True,
        ),
        _tx_10b5(
            cik="B", days_ago=8, is_officer=True, officer_title="CFO",
            dollar_value=200_000, is_rule_10b5_one=False,
        ),
    ]
    assert detect_c_suite_unusual_sell(txns, AS_OF) is False


def test_strict_superset_invariant_holds_under_10b5_1_filter():
    """When the 10b5-1 filter drops the cluster below threshold, the
    c_suite flag MUST also be False (c_suite ⊆ cluster strict-superset
    invariant from PR #222 must survive the filter).

    Scenario: 3 distinct insiders with sufficient dollar_value, but all 3
    have is_rule_10b5_one=True — neither cluster nor c_suite should fire.
    """
    txns = [
        _tx_10b5(
            cik="A", days_ago=5, is_officer=True, officer_title="CEO",
            dollar_value=500_000, is_rule_10b5_one=True,
        ),
        _tx_10b5(
            cik="B", days_ago=8, is_officer=True, officer_title="CFO",
            dollar_value=500_000, is_rule_10b5_one=True,
        ),
        _tx_10b5(
            cik="C", days_ago=12, dollar_value=500_000, is_rule_10b5_one=True,
        ),
    ]
    cluster_fires = detect_insider_sell_cluster(txns, AS_OF)
    c_suite_fires = detect_c_suite_unusual_sell(txns, AS_OF)
    # strict-superset invariant: if cluster is False, c_suite must also be False
    assert cluster_fires is False
    assert c_suite_fires is False
    # Verify the invariant direction: c_suite cannot be True when cluster is False
    # (c_suite requires a subset of the conditions cluster requires)
    assert not (c_suite_fires and not cluster_fires), (
        "Strict-superset invariant violated: c_suite fired but cluster did not. "
        "This breaks the DELTA-weight semantic in manipulation_index.py."
    )


# ---------------------------------------------------------------------------
# PR 4-eq: count_10b5_1_filtered_transactions (#9-#10)
# ---------------------------------------------------------------------------


def test_count_10b5_1_filtered_counts_only_opportunistic_codes():
    """The counter must only count transactions that:
    (a) have code ∈ {S, D}  AND  (b) have is_rule_10b5_one=True.
    A grant (code=A) with is_rule_10b5_one=True must NOT be counted —
    it was never in the opportunistic cohort in the first place."""
    txns = [
        # Grant with 10b5-1 True — should NOT count (wrong code)
        _tx_10b5(cik="A", days_ago=5, code="A", dollar_value=200_000,
                 is_rule_10b5_one=True),
        # Sale with 10b5-1 True — SHOULD count
        _tx_10b5(cik="B", days_ago=8, code="S", dollar_value=200_000,
                 is_rule_10b5_one=True),
        # Sale-back-to-issuer with 10b5-1 True — SHOULD count
        _tx_10b5(cik="C", days_ago=10, code="D", dollar_value=200_000,
                 is_rule_10b5_one=True),
        # Sale with 10b5-1 False — should NOT count (not filtered)
        _tx_10b5(cik="D", days_ago=12, code="S", dollar_value=200_000,
                 is_rule_10b5_one=False),
        # Sale with 10b5-1 None — should NOT count (None = no plan detected)
        _tx_10b5(cik="E", days_ago=14, code="S", dollar_value=200_000,
                 is_rule_10b5_one=None),
    ]
    result = count_10b5_1_filtered_transactions(txns, AS_OF)
    assert result == 2  # only the code=S and code=D with True


def test_count_10b5_1_filtered_respects_window():
    """Transactions outside the 30-day cluster window must NOT be counted
    even if is_rule_10b5_one=True. The counter tracks contamination
    eliminated from the cluster-detection INPUT (which is window-filtered)."""
    txns = [
        # Inside window — should count
        _tx_10b5(cik="A", days_ago=5, code="S", dollar_value=200_000,
                 is_rule_10b5_one=True),
        # Exactly at boundary — should count (inclusive)
        _tx_10b5(cik="B", days_ago=30, code="S", dollar_value=200_000,
                 is_rule_10b5_one=True),
        # Outside window — should NOT count
        _tx_10b5(cik="C", days_ago=31, code="S", dollar_value=200_000,
                 is_rule_10b5_one=True),
        # Well outside window — should NOT count
        _tx_10b5(cik="D", days_ago=90, code="S", dollar_value=200_000,
                 is_rule_10b5_one=True),
    ]
    result = count_10b5_1_filtered_transactions(txns, AS_OF)
    assert result == 2  # only the 2 within-window ones


# ---------------------------------------------------------------------------
# PR 4-eq: Hypothesis property — filter monotonicity invariant (#11)
# ---------------------------------------------------------------------------


@settings(
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    max_examples=100,
)
@given(
    n_opportunistic=st.integers(min_value=0, max_value=20),
    n_10b5_opportunistic=st.integers(min_value=0, max_value=20),
    n_non_opportunistic=st.integers(min_value=0, max_value=10),
)
def test_filter_monotonicity_property(
    n_opportunistic: int,
    n_10b5_opportunistic: int,
    n_non_opportunistic: int,
) -> None:
    """The 10b5-1 filter never ADDS transactions — it only removes.

    For any list of transactions:
    - count_10b5_1_filtered_transactions(...) >= 0 (trivially)
    - count_10b5_1_filtered_transactions(...) <= len(opportunistic_in_window)
      where opportunistic_in_window = transactions with code ∈ {S, D} in the window.

    The filter strictly removes a subset of opportunistic transactions;
    it cannot inflate the count above the opportunistic ceiling.
    """
    # Build a cohort: n_opportunistic non-10b5-1 sells + n_10b5_opportunistic
    # 10b5-1 sells + n_non_opportunistic grants (code=A)
    txns = []
    for i in range(n_opportunistic):
        txns.append(_tx_10b5(
            cik=f"OPP{i}", days_ago=(i % 25) + 1, code="S",
            dollar_value=100_000.0, is_rule_10b5_one=False,
        ))
    for i in range(n_10b5_opportunistic):
        txns.append(_tx_10b5(
            cik=f"10B5{i}", days_ago=(i % 25) + 1, code="S",
            dollar_value=100_000.0, is_rule_10b5_one=True,
        ))
    for i in range(n_non_opportunistic):
        txns.append(_tx_10b5(
            cik=f"GRANT{i}", days_ago=(i % 25) + 1, code="A",
            dollar_value=100_000.0, is_rule_10b5_one=True,
        ))

    filtered_count = count_10b5_1_filtered_transactions(txns, AS_OF)

    # Invariant 1: non-negative
    assert filtered_count >= 0

    # Invariant 2: cannot exceed the count of opportunistic-coded txns
    # in the window (code ∈ {S, D}, regardless of 10b5-1 status)
    opportunistic_in_window = sum(
        1 for tx in txns
        if str(tx.get("transaction_code", "")).upper() in {"S", "D"}
    )
    assert filtered_count <= opportunistic_in_window, (
        f"filter monotonicity violated: "
        f"filtered_count={filtered_count} > opportunistic_in_window={opportunistic_in_window}"
    )

    # Invariant 3: exactly equals n_10b5_opportunistic (all within-window)
    # because all our synthetic txns are within 25 days
    assert filtered_count == n_10b5_opportunistic, (
        f"Expected exactly {n_10b5_opportunistic} 10b5-1 filtered transactions "
        f"(all code=S within window), got {filtered_count}"
    )
