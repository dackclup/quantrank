"""Tests for Proposal E — Turnover / hysteresis diagnostic + liquidity capacity tilt.

Coverage policy (AGENTS.md §Testing): new functions + new ``Metadata`` fields
→ tests required.

Covers:
  E_TU — ``book_turnover``: pure name-count metric, 5 edge cases.
  E_I  — ``liquidity_capacity_tilt`` identity guards (empty sets, empty book).
  E_DIR — Haircut direction (low-liq weight decreases, non-liq weight increases).
  E_ALL — All-flagged: haircut ×all → renorm cancels → relative weights preserved.
  E_CAP — MAX_WEIGHT holds post-tilt (Hypothesis property, n ≥ 4).
  E_CONST — ``LIQ_CAPACITY_TILT`` pinned at 0.5.
  E_META — ``Metadata`` round-trip for the two new Proposal E fields.
  E_STACK — Stacking identity: inv_vol → liq_tilt(∅) → mos_tilt(all-None) = inv_vol.

All tests are fully offline (pure-function dicts, no network, no I/O).
Hypothesis is available in CI (pyproject.toml dev extras).  The property test
routes the base through ``inverse_vol_weights`` (same pattern as
``test_mos_tilt.py::test_C2_PROP_max_weight_and_sum_invariants``) so the
MAX_WEIGHT invariant is unconditionally testable.

Methodology pins:
  LIQ_CAPACITY_TILT = 0.5   (Tier-2 gut-feel, disclosed)
  MAX_WEIGHT        = 0.35  (inherited from inverse_vol_weights)

Cap-feasibility note: with n tickers and MAX_WEIGHT=0.35 the cap is infeasible
when n·0.35 < 1.0 (n ≤ 2 → equal-weight collapse).  All non-trivial haircut-
direction / cap-property tests use n ≥ 4.

Defense-precedence assertion coverage: the inline assertion in
``scripts/backfill_portfolio_pit.py`` over ``band_book`` and the stateless
counterfactual cannot be unit-tested here (it reads the committed
``backtest_pit.json`` artifact, which is absent in the offline suite).  The
assertion is deferred to the backfill integration test in
``tests/test_portfolio/test_backfill_integration.py`` (issue #579 follow-up)
once the artifact is committed.  See the E_STACK stacking-identity test below
for the functional analogue: the capacity tilt degenerates to identity on clean
books (no low-liquidity names), confirming the live NAV path is byte-identical.

Anchors:
  Garleanu-Pedersen 2013 *JF* 68(6) — no-trade region / turnover cost.
  Novy-Marx-Velikov 2016 *RFS* 29(7) — turnover erodes return premia.
  Amihud 2002 *JFM* 5(1) — illiquidity capacity constraint ($5M ADV floor).
"""

from __future__ import annotations

import math

from hypothesis import given
from hypothesis import strategies as st

from compute.portfolio.weights import (
    LIQ_CAPACITY_TILT,
    MAX_WEIGHT,
    book_turnover,
    inverse_vol_weights,
    liquidity_capacity_tilt,
    mos_conviction_tilt,
)

# ---------------------------------------------------------------------------
# Helpers (mirror the pattern from test_mos_tilt.py)
# ---------------------------------------------------------------------------


def _equal_book(tickers: list[str]) -> dict[str, float]:
    """Equal-weight book for a list of tickers (sum = 1.0)."""
    w = 1.0 / len(tickers)
    return {t: w for t in tickers}


def _renorm(d: dict[str, float]) -> dict[str, float]:
    """Renormalize a dict of positive floats to sum 1.0."""
    total = sum(d.values())
    return {k: v / total for k, v in d.items()}


# ---------------------------------------------------------------------------
# E_TU — book_turnover edge cases
# ---------------------------------------------------------------------------


def test_E_TU1_empty_prev_returns_zero() -> None:
    """book_turnover: prev is empty → 0.0 (first rebalance sentinel).

    The hysteresis band has no predecessor on the first rebalance; by
    convention turnover is 0.0 (band inert, nothing to measure against).
    """
    result = book_turnover(curr={"AAPL", "MSFT", "GOOG"}, prev=set())

    assert result == 0.0, f"Expected 0.0 for empty prev, got {result!r}"


def test_E_TU2_identical_sets_returns_zero() -> None:
    """book_turnover: curr == prev → 0.0 (perfect persistence, zero churn).

    The symmetric difference of a set with itself is the empty set, so
    |curr △ prev| / |prev| = 0 / N = 0.0.
    """
    book = {"AAPL", "MSFT", "GOOG", "AMZN"}

    result = book_turnover(curr=book, prev=book)

    assert result == 0.0, f"Expected 0.0 for identical sets, got {result!r}"


def test_E_TU3_full_swap_returns_two() -> None:
    """book_turnover: no overlap between curr and prev → |curr △ prev| / |prev|.

    With |curr| = |prev| = N and no shared names:
      symmetric_diff = |curr| + |prev| = 2N
      turnover = 2N / N = 2.0

    This is the maximum possible value when both books have the same size.
    A full replacement generates a turnover of 2 because both the N
    departures AND the N arrivals count in the symmetric difference.
    """
    prev = {"A", "B", "C"}
    curr = {"X", "Y", "Z"}

    result = book_turnover(curr=curr, prev=prev)

    assert result == 2.0, f"Expected 2.0 for full swap (n=3), got {result!r}"


def test_E_TU4_partial_overlap() -> None:
    """book_turnover: 1 shared name out of prev=2 → turnover = 1 / 2 = 0.5.

    prev = {A, B}, curr = {A, C}.
    symmetric_diff = {B, C} → |{B, C}| = 2.
    Wait — the correct formula is |curr △ prev| / |prev|.
    symmetric_diff({A,C}, {A,B}) = {B, C} → size 2.
    turnover = 2 / 2 = 1.0.

    Re-examine: prev={A,B}, curr={A,B,C}:
    symmetric_diff = {C} → 1 / 2 = 0.5.
    Use that fixture instead: prev 2 names, curr adds 1, keeps both → 0.5.
    """
    prev = {"A", "B"}
    curr = {"A", "B", "C"}  # added C, kept both originals

    result = book_turnover(curr=curr, prev=prev)

    assert result == 0.5, f"Expected 0.5 (1 new / |prev|=2), got {result!r}"


def test_E_TU5_curr_empty_prev_nonempty_returns_one() -> None:
    """book_turnover: curr is empty, prev is non-empty → symmetric diff = prev → 1.0.

    prev = {A, B, C}, curr = {}.
    symmetric_diff({}, {A,B,C}) = {A,B,C} → 3 / 3 = 1.0.

    Degenerate: complete liquidation of the band book.  The metric correctly
    captures 100% departure-side churn (all prev names left, no new names arrived).
    """
    prev = {"A", "B", "C"}

    result = book_turnover(curr=set(), prev=prev)

    assert result == 1.0, f"Expected 1.0 for curr-empty, got {result!r}"


# ---------------------------------------------------------------------------
# E_I — liquidity_capacity_tilt identity guards
# ---------------------------------------------------------------------------


def test_E_I1_empty_low_liquidity_returns_base_weights() -> None:
    """Identity guard: empty ``low_liquidity_tickers`` → all haircut multipliers
    are 1.0 → provisional == base → returns base weights (up to MAX_WEIGHT re-cap).

    Use a 4-ticker equal-weight book (each 0.25 < MAX_WEIGHT=0.35) so the
    cap does not bind and the result is byte-identical to the input.
    """
    base = _equal_book(["A", "B", "C", "D"])

    result = liquidity_capacity_tilt(base, low_liquidity_tickers=set())

    for t, w in base.items():
        assert math.isclose(result[t], w, abs_tol=1e-12), (
            f"Ticker {t}: expected {w!r}, got {result[t]!r} "
            f"(empty low-liq identity guard failed)"
        )


def test_E_I2_empty_base_weights_returns_empty_dict() -> None:
    """Identity guard: empty base_weights → returns {} immediately (first guard)."""
    result = liquidity_capacity_tilt({}, low_liquidity_tickers={"ILLIQ"})

    assert result == {}, f"Empty base_weights guard failed: got {result!r}"


# ---------------------------------------------------------------------------
# E_DIR — Haircut direction (n ≥ 4, economically correct)
# ---------------------------------------------------------------------------


def test_E_DIR1_low_liq_weight_decreases() -> None:
    """Haircut direction: the flagged low-liquidity ticker's post-tilt weight
    must be STRICTLY less than its base weight.

    Fixture: 4-ticker equal-weight book, one name flagged as low-liquidity.
    The haircut halves that name's pre-renorm weight; after renorm the
    remaining 3 names absorb the freed weight → the flagged name's share drops.
    """
    base = _equal_book(["LL", "A", "B", "C"])  # LL = low liquidity
    low_liq = {"LL"}

    result = liquidity_capacity_tilt(base, low_liquidity_tickers=low_liq)

    assert result["LL"] < base["LL"], (
        f"Low-liq name weight should DECREASE: base={base['LL']:.4f}, "
        f"tilted={result['LL']:.4f}"
    )


def test_E_DIR2_non_low_liq_weights_increase() -> None:
    """Haircut direction: each non-low-liq ticker's post-tilt weight must be
    STRICTLY greater than its base weight (they absorb the freed weight).

    Same fixture as E_DIR1: 4-ticker equal-weight, only 'LL' flagged.
    The haircut frees weight from LL; A, B, C proportionally receive it.
    """
    base = _equal_book(["LL", "A", "B", "C"])
    low_liq = {"LL"}

    result = liquidity_capacity_tilt(base, low_liquidity_tickers=low_liq)

    for t in ["A", "B", "C"]:
        assert result[t] > base[t], (
            f"Non-low-liq ticker {t} weight should INCREASE: "
            f"base={base[t]:.4f}, tilted={result[t]:.4f}"
        )


def test_E_DIR3_sum_equals_one_after_haircut() -> None:
    """Post-haircut weights must sum to 1.0 ± 1e-9.

    4-ticker book, 1 low-liq ticker, diverse base weights.
    """
    base = _renorm({"LL": 0.30, "A": 0.25, "B": 0.25, "C": 0.20})
    low_liq = {"LL"}

    result = liquidity_capacity_tilt(base, low_liquidity_tickers=low_liq)

    assert math.isclose(sum(result.values()), 1.0, abs_tol=1e-9), (
        f"Weights do not sum to 1 after haircut: {sum(result.values())}"
    )


# ---------------------------------------------------------------------------
# E_ALL — All tickers flagged: renorm cancels, relative weights preserved
# ---------------------------------------------------------------------------


def test_E_ALL_all_flagged_preserves_relative_weights() -> None:
    """All tickers flagged as low-liq → haircut × ALL names →
    renorm cancels the haircut → relative weights preserved ≈ base.

    Specifically: provisional[t] = base[t] × 0.5 for all t.
    After renorm: weight[t] = (base[t] × 0.5) / (Σ base × 0.5)
                             = base[t] / Σ base = base[t]  (since Σbase = 1).
    Result must be base weights (within float tolerance) unless MAX_WEIGHT binds.

    Use a 4-ticker equal-weight book so MAX_WEIGHT (0.35) does not bind
    (each base weight = 0.25 < 0.35).
    """
    base = _equal_book(["A", "B", "C", "D"])
    low_liq = {"A", "B", "C", "D"}

    result = liquidity_capacity_tilt(base, low_liquidity_tickers=low_liq)

    for t, w in base.items():
        assert math.isclose(result[t], w, abs_tol=1e-9), (
            f"Ticker {t}: all-flagged should preserve relative weight: "
            f"base={w:.6f}, result={result[t]:.6f}"
        )

    assert math.isclose(sum(result.values()), 1.0, abs_tol=1e-9), (
        f"Sum-to-1 failed: {sum(result.values())}"
    )


# ---------------------------------------------------------------------------
# E_CAP — MAX_WEIGHT property (Hypothesis, n ≥ 4)
# ---------------------------------------------------------------------------


@given(
    st.dictionaries(
        st.text(min_size=1, max_size=4),
        st.floats(
            min_value=0.01, max_value=2.0, allow_nan=False, allow_infinity=False
        ),
        min_size=4,   # n ≥ 4 so MAX_WEIGHT cap is feasible (4 × 0.35 = 1.4 > 1)
        max_size=12,
    ),
    st.frozensets(
        st.text(min_size=1, max_size=4),
        min_size=0,
        max_size=12,
    ),
)
def test_E_CAP_max_weight_and_sum_invariants(raw_sigmas, low_liq_keys) -> None:
    """Property: for any production-valid book (pre-capped via inverse_vol_weights)
    and any low-liquidity ticker set:
    - max(result.values()) ≤ MAX_WEIGHT + 1e-9
    - all weights ≥ 0
    - sum(result.values()) == 1.0 ± 1e-9

    Strategy: generate raw_sigmas (positive floats as stand-in volatilities),
    run through inverse_vol_weights (which caps at MAX_WEIGHT) to get a valid
    base, then call liquidity_capacity_tilt with a random low-liq subset.

    This mirrors the real production call chain:
        inverse_vol_weights(sigmas) → liq_capacity_tilt(base, liq_set)

    The input contract for liquidity_capacity_tilt states that base_weights
    already satisfy MAX_WEIGHT (they come from inverse_vol_weights).  On the
    identity path (empty low_liq_tickers OR all flagged) the function returns
    base weights unchanged — byte-identity by design — so routing through
    inverse_vol_weights guarantees the invariant unconditionally.

    NO @settings(deadline=None) per issue #126 — slow examples are signal.
    """
    base = inverse_vol_weights(raw_sigmas)
    if not base:
        # inverse_vol_weights returns {} when no usable sigmas — skip.
        return

    # Intersect with the actual book keys (random keys from hypothesis may
    # not overlap with the generated tickers at all — that's fine and tests
    # the empty-intersection path too).
    low_liq = set(low_liq_keys)

    result = liquidity_capacity_tilt(base, low_liquidity_tickers=low_liq)

    if not result:
        # Empty result only possible when base was empty (guarded above).
        return

    assert math.isclose(sum(result.values()), 1.0, abs_tol=1e-9), (
        f"Weights do not sum to 1: {sum(result.values())}"
    )
    assert all(v >= 0 for v in result.values()), (
        f"Negative weight found: {result}"
    )
    # MAX_WEIGHT invariant: guaranteed because either (a) the tilt path
    # re-caps via the iterative pin-redistribute loop, or (b) the identity
    # path returns base unchanged — and base was produced by inverse_vol_weights
    # which already guarantees MAX_WEIGHT.
    n = len(result)
    if n * MAX_WEIGHT >= 1.0 - 1e-12:  # cap feasible (always true for n ≥ 4)
        assert all(v <= MAX_WEIGHT + 1e-9 for v in result.values()), (
            f"MAX_WEIGHT ({MAX_WEIGHT}) violated: {result}"
        )


# ---------------------------------------------------------------------------
# E_CONST — LIQ_CAPACITY_TILT constant pinned
# ---------------------------------------------------------------------------


def test_E_CONST_liq_capacity_tilt_pinned() -> None:
    """LIQ_CAPACITY_TILT must be exactly 0.5 (Tier-2 gut-feel, disclosed).

    The haircut halves the weight of any low-liquidity holding before renorm.
    Changing this without a methodology-scientist re-derivation + CI sign-off
    is forbidden.  The pin makes any accidental change fail CI immediately.

    Anchor: Amihud 2002 *JFM* 5(1) capacity constraint — the $5M ADV floor
    is a capacity guard, not an alpha claim; 0.5 is the implementation haircut.
    """
    assert LIQ_CAPACITY_TILT == 0.5, (
        f"LIQ_CAPACITY_TILT changed: got {LIQ_CAPACITY_TILT!r}, expected 0.5"
    )


# ---------------------------------------------------------------------------
# E_META — Metadata round-trip for the two new Proposal E fields
# ---------------------------------------------------------------------------


def test_E_META1_new_fields_default_to_none() -> None:
    """Proposal E (0.10.40-phase8pilot): the 2 new Metadata fields exist and
    default to None — backward-compatible with all pre-0.10.40 JSON artifacts
    (which have no such keys).

    Fields:
    - hysteresis_turnover_reduction_mean_pp: float | None
    - low_liquidity_held_count: int | None

    extra="forbid" must NOT raise on construction with these fields absent.
    """
    from compute.output.schemas import Metadata

    m = Metadata(
        version="0.10.40-phase8pilot",
        last_update_utc="2026-06-26T22:00:00Z",
        next_update_utc="2026-06-27T22:00:00Z",
        universe="SP1500",
        universe_size=1504,
        compute_run_id="test-e-defaults",
        git_commit="e0e0e0e0",
    )

    assert m.hysteresis_turnover_reduction_mean_pp is None, (
        "hysteresis_turnover_reduction_mean_pp must default to None (backward-compat)"
    )
    assert m.low_liquidity_held_count is None, (
        "low_liquidity_held_count must default to None (backward-compat)"
    )


def test_E_META2_round_trip_preserves_types_and_values() -> None:
    """Proposal E: both new fields survive a Pydantic model_dump → model_validate
    round-trip with realistic values, preserving Python types.

    hysteresis_turnover_reduction_mean_pp = 3.14 (float, pp reduction)
    low_liquidity_held_count = 2 (int, two holdings flagged in the final leg)

    The round-trip check guards against Pydantic coercion surprises (e.g.
    an int field silently converting to float on model_validate).
    """
    from compute.output.schemas import Metadata

    m = Metadata(
        version="0.10.40-phase8pilot",
        last_update_utc="2026-06-26T22:00:00Z",
        next_update_utc="2026-06-27T22:00:00Z",
        universe="SP1500",
        universe_size=1504,
        compute_run_id="test-e-round-trip",
        git_commit="e1e1e1e1",
        hysteresis_turnover_reduction_mean_pp=3.14,
        low_liquidity_held_count=2,
    )

    assert m.hysteresis_turnover_reduction_mean_pp == 3.14
    assert m.low_liquidity_held_count == 2
    assert isinstance(m.low_liquidity_held_count, int), (
        f"low_liquidity_held_count must be int, got {type(m.low_liquidity_held_count)}"
    )

    payload = m.model_dump(mode="json")
    assert payload["hysteresis_turnover_reduction_mean_pp"] == 3.14
    assert payload["low_liquidity_held_count"] == 2

    m2 = Metadata.model_validate(payload)
    assert m2.hysteresis_turnover_reduction_mean_pp == 3.14
    assert m2.low_liquidity_held_count == 2
    assert isinstance(m2.low_liquidity_held_count, int), (
        f"After round-trip: low_liquidity_held_count must be int, "
        f"got {type(m2.low_liquidity_held_count)}"
    )


def test_E_META3_zero_held_count_distinct_from_none() -> None:
    """low_liquidity_held_count = 0 is DISTINCT from None.

    0 means 'no low-liq holdings in the final rebalance leg' (a positive
    confirmation of clean book); None means 'backtest artifact absent or
    not yet populated'.  This test pins that semantic boundary.
    """
    from compute.output.schemas import Metadata

    m = Metadata(
        version="0.10.40-phase8pilot",
        last_update_utc="2026-06-26T22:00:00Z",
        next_update_utc="2026-06-27T22:00:00Z",
        universe="SP1500",
        universe_size=1504,
        compute_run_id="test-e-zero-held",
        git_commit="e2e2e2e2",
        low_liquidity_held_count=0,
    )

    assert m.low_liquidity_held_count == 0
    assert m.low_liquidity_held_count is not None, (
        "0 must not be treated as None (absent-data sentinel)"
    )

    payload = m.model_dump(mode="json")
    m2 = Metadata.model_validate(payload)
    assert m2.low_liquidity_held_count == 0
    assert m2.low_liquidity_held_count is not None


# ---------------------------------------------------------------------------
# E_STACK — Stacking identity (byte-identity safety test)
# ---------------------------------------------------------------------------


def test_E_STACK_degenerate_inputs_compose_to_identity() -> None:
    """Stacking identity: the three shadow tilt functions compose to identity
    on degenerate (no-op) inputs — guaranteeing the live NAV path is
    byte-identical when Proposals C-2 and E are both SHADOW-only.

    Chain under test:
        base = inverse_vol_weights(sigmas)              # production baseline
        step1 = liquidity_capacity_tilt(base, liq=∅)   # no-op (empty low-liq)
        step2 = mos_conviction_tilt(step1, mos_all_None) # no-op (all-None mos)

    Expected: step2 == base (within float tolerance) because:
    - liq_tilt with empty low_liq returns base unchanged (E_I1 identity guard).
    - mos_tilt with all-None mos values returns base unchanged (C2_I2 guard).

    Use a 5-ticker book built via inverse_vol_weights so MAX_WEIGHT already
    holds on the input (contract of both tilt functions).
    """
    sigmas = {"AAPL": 0.012, "MSFT": 0.014, "GOOG": 0.010, "AMZN": 0.018, "NVDA": 0.020}
    base = inverse_vol_weights(sigmas)
    assert base, "inverse_vol_weights returned empty — fixture error"

    # Step 1: liq tilt with no flagged names — must be identity.
    step1 = liquidity_capacity_tilt(base, low_liquidity_tickers=set())
    for t in base:
        assert math.isclose(step1[t], base[t], abs_tol=1e-12), (
            f"liq_tilt(∅) identity failed for {t}: "
            f"base={base[t]:.8f}, step1={step1[t]:.8f}"
        )

    # Step 2: mos tilt with all-None mos values — must be identity relative to step1.
    mos_all_none: dict[str, float | None] = {t: None for t in step1}
    step2 = mos_conviction_tilt(step1, mos_all_none)
    for t in step1:
        assert math.isclose(step2[t], step1[t], abs_tol=1e-12), (
            f"mos_tilt(all-None) identity failed for {t}: "
            f"step1={step1[t]:.8f}, step2={step2[t]:.8f}"
        )

    # Final: step2 == base (transitive).
    for t in base:
        assert math.isclose(step2[t], base[t], abs_tol=1e-12), (
            f"Stacked identity failed for {t}: "
            f"base={base[t]:.8f}, step2={step2[t]:.8f}"
        )
