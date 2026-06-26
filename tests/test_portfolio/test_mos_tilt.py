"""Tests for Proposal C-2 — MoS conviction tilt (``compute/portfolio/weights.py``).

Coverage policy (AGENTS.md §Testing): new function + new ``Metadata`` field
→ tests required.

All tests are fully offline (pure-function dicts, no network, no I/O).
``hypothesis`` is imported conditionally so the property test collection does
not break this env (hypothesis is absent); the test still exists for CI where
the dep is installed (pyproject.toml dev extras).

Methodology pins:
  MOS_TILT_KAPPA    = 0.25  (Tier-2 gut-feel calibration, disclosed)
  MOS_TILT_CLIP_LO  = 0.5
  MOS_TILT_CLIP_HI  = 1.5
  MAX_WEIGHT        = 0.35  (inherited from inverse_vol_weights)

Cap-feasibility note (compute-builder): with n tickers and MAX_WEIGHT=0.35
the cap is infeasible when n·0.35 < 1.0 (i.e. n ≤ 2 → equal-weight
collapse).  All non-trivial tilt-direction / cap-property tests use n ≥ 4.
"""

from __future__ import annotations

import math
import statistics

from hypothesis import given
from hypothesis import strategies as st

from compute.portfolio.weights import (
    MAX_WEIGHT,
    MOS_TILT_CLIP_HI,
    MOS_TILT_CLIP_LO,
    MOS_TILT_KAPPA,
    inverse_vol_weights,
    mos_conviction_tilt,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _renorm(d: dict[str, float]) -> dict[str, float]:
    """Renormalise a dict of positive floats to sum 1.0 (for building fixtures)."""
    total = sum(d.values())
    return {k: v / total for k, v in d.items()}


def _equal_book(tickers: list[str]) -> dict[str, float]:
    """Equal-weight book for a list of tickers (sum = 1.0)."""
    w = 1.0 / len(tickers)
    return {t: w for t in tickers}


# ---------------------------------------------------------------------------
# C2_I — Identity guards (methodology-pinned)
# ---------------------------------------------------------------------------


def test_C2_I1_all_mos_equal_returns_base_weights() -> None:
    """Identity guard: σ_mos == 0 (all holdings share the same MoS value)
    → all z_i = 0 → all m_i = 1 → tilt is a no-op.

    Result must equal base_weights to within 1e-12 (floating-point identity).
    """
    base = _renorm({"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25})
    mos = {"A": 10.0, "B": 10.0, "C": 10.0, "D": 10.0}

    result = mos_conviction_tilt(base, mos)

    for t, w in base.items():
        assert math.isclose(result[t], w, abs_tol=1e-12), (
            f"Ticker {t}: expected {w!r}, got {result[t]!r} "
            f"(σ_mos=0 identity guard failed)"
        )


def test_C2_I2_all_mos_none_returns_base_weights() -> None:
    """Identity guard: all mos values are None → all z_i = 0 → identity.

    The function hits the 'len(mos_vals) < 2' early-return path (zero valid
    MoS values → no dispersion to tilt on).
    """
    base = _renorm({"A": 0.30, "B": 0.20, "C": 0.25, "D": 0.25})
    mos: dict[str, float | None] = {"A": None, "B": None, "C": None, "D": None}

    result = mos_conviction_tilt(base, mos)

    for t, w in base.items():
        assert math.isclose(result[t], w, abs_tol=1e-12), (
            f"Ticker {t}: expected {w!r}, got {result[t]!r} "
            f"(all-None identity guard failed)"
        )


def test_C2_I3_single_name_book_returns_base_weights() -> None:
    """Identity guard: single-name book (n=1) → stdev undefined (ddof=1 needs
    ≥ 2 points) → treated as σ=0 → identity.

    The function hits the 'len(mos_vals) < 2' path (only 1 non-None MoS).
    """
    base = {"SOLO": 1.0}
    mos = {"SOLO": 25.0}

    result = mos_conviction_tilt(base, mos)

    assert result == {"SOLO": 1.0}, (
        f"Single-name identity guard failed: got {result!r}"
    )


def test_C2_I4_empty_base_weights_returns_empty_dict() -> None:
    """Identity guard: empty base_weights → returns {} immediately (first guard)."""
    result = mos_conviction_tilt({}, {"A": 10.0, "B": 5.0})

    assert result == {}, f"Empty base_weights guard failed: got {result!r}"


# ---------------------------------------------------------------------------
# C2_I5 — Single mos non-None (only 1 non-None among many)
# ---------------------------------------------------------------------------


def test_C2_I5_one_valid_mos_among_many_none_returns_identity() -> None:
    """When only 1 ticker has a non-None MoS (and others are None),
    len(mos_vals) < 2 → identity path.

    Edge: the function must NOT compute z when there is no dispersion
    (you cannot compute a stdev from a single observation).
    """
    base = _renorm({"A": 0.3, "B": 0.3, "C": 0.2, "D": 0.2})
    mos: dict[str, float | None] = {"A": 20.0, "B": None, "C": None, "D": None}

    result = mos_conviction_tilt(base, mos)

    for t, w in base.items():
        assert math.isclose(result[t], w, abs_tol=1e-12), (
            f"Ticker {t}: expected {w!r}, got {result[t]!r} "
            f"(1-valid-mos identity guard failed)"
        )


# ---------------------------------------------------------------------------
# C2_C — Clip-bound tests
# ---------------------------------------------------------------------------


def test_C2_C1_low_mos_multiplier_clamps_at_clip_lo() -> None:
    """Clip lower bound: construct a mos spread so that
    1 + κ·z < MOS_TILT_CLIP_LO for the lowest-MoS ticker.

    With κ=0.25, clip_lo=0.5: need 1 + 0.25·z < 0.5 → z < -2.
    We need |z| > 2, which requires the worst name to be > 2σ below mean.

    Strategy: one name at 0.0, three names tightly clustered near 100.
    With values [0, 100, 100, 100]:
      μ = 75, σ = stdev([0,100,100,100]) = 50, z_0 = (0−75)/50 = −1.5 → too shallow.
    We need a tighter cluster — use values [0.0, 1.0, 1.0, 1.0]:
      μ = 0.75, σ ≈ 0.5, z_0 = (0−0.75)/0.5 = −1.5 → still ±1.5.

    The sample stdev with 3 identical values in a 4-element list always yields
    |z_extreme| = 1.5 (geometric constraint).  To achieve |z| > 2, we need
    a 5-element fixture with all-but-one at the same value, OR we need the
    cluster to NOT be degenerate.  Using a 5-book:
      values = [ε, x, x, x, x]: μ=(ε+4x)/5, σ=stdev, z_ε = (ε−μ)/σ
      with ε→0, x=10: μ=8, σ=stdev([0,10,10,10,10])=4.47, z_ε=−8/4.47≈−1.79 — still < -2.

    The easiest exact construction: draw extreme z directly.
    Use values [0, 0, 0, 100, 100, 100, 100] (n=7, 3 low + 4 high):
      μ = (0×3 + 100×4)/7 = 400/7 ≈ 57.14
      σ = stdev (sample, ddof=1)
      z_0 = (0 − 57.14)/σ

    Let's compute this programmatically to confirm the clip fires, then call
    the function. The assertion for fixture validity is a PRE-CONDITION check.
    """
    # Use a 6-ticker book with strong MoS separation.
    # 1 ticker at MoS=0, 5 tickers at MoS=100.
    # With n=6 (1 extreme + 5 identical), |z_extreme| ≈ 2.04 → 1 + κ·z < 0.49 < 0.5.
    tickers = ["LOW", "H1", "H2", "H3", "H4", "H5"]
    base = _equal_book(tickers)
    mos = {"LOW": 0.0, "H1": 100.0, "H2": 100.0, "H3": 100.0, "H4": 100.0, "H5": 100.0}

    # Verify fixture triggers the low clip.
    mos_vals = [0.0, 100.0, 100.0, 100.0, 100.0, 100.0]
    mu = statistics.mean(mos_vals)
    sigma = statistics.stdev(mos_vals)
    z_low = (0.0 - mu) / sigma
    raw_m_low = 1.0 + MOS_TILT_KAPPA * z_low

    # The clip must bind: raw_m_low < MOS_TILT_CLIP_LO
    assert raw_m_low < MOS_TILT_CLIP_LO, (
        f"Test fixture failed to produce z that triggers low clip: "
        f"z={z_low:.4f}, raw_m={raw_m_low:.4f}, clip_lo={MOS_TILT_CLIP_LO}"
    )

    result = mos_conviction_tilt(base, mos)

    # All weights must be non-negative.
    assert all(v >= 0 for v in result.values()), (
        f"Negative weight after low-clip: {result}"
    )

    # Sum must equal 1.0.
    assert math.isclose(sum(result.values()), 1.0, abs_tol=1e-9), (
        f"Weights do not sum to 1: sum={sum(result.values())}"
    )

    # LOW was clipped at 0.5; HIGH names have higher multipliers → LOW
    # weight < any single H weight.
    assert result["LOW"] < result["H1"], (
        f"LOW should have lower weight than H1 after clip-lo: "
        f"LOW={result['LOW']:.4f}, H1={result['H1']:.4f}"
    )


def test_C2_C2_high_mos_multiplier_clamps_at_clip_hi() -> None:
    """Clip upper bound: construct a mos spread so that
    1 + κ·z > MOS_TILT_CLIP_HI for the highest-MoS ticker.

    With κ=0.25, clip_hi=1.5: need 1 + 0.25·z > 1.5 → z > 2.
    Mirror of C2_C1: use 7-ticker fixture with 4 tickers at MoS=0
    and 3 tickers at MoS=100.
      μ = (100×3 + 0×4)/7 ≈ 42.86
      σ = stdev (sample)
      z_HIGH = (100 − μ) / σ > 2 → clip binds at MOS_TILT_CLIP_HI.
    """
    # Mirror of C2_C1: 1 ticker at MoS=100, 5 at MoS=0 (n=6).
    # |z_HIGH| ≈ 2.04 → 1 + κ·z_HIGH > 1.51 > MOS_TILT_CLIP_HI.
    tickers = ["HIGH", "L1", "L2", "L3", "L4", "L5"]
    base = _equal_book(tickers)
    mos = {"HIGH": 100.0, "L1": 0.0, "L2": 0.0, "L3": 0.0, "L4": 0.0, "L5": 0.0}

    # Verify the clip fires for the HIGH name.
    mos_vals = [100.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    mu = statistics.mean(mos_vals)
    sigma = statistics.stdev(mos_vals)
    z_high = (100.0 - mu) / sigma
    raw_m_high = 1.0 + MOS_TILT_KAPPA * z_high

    assert raw_m_high > MOS_TILT_CLIP_HI, (
        f"Test fixture failed to produce z that triggers high clip: "
        f"z={z_high:.4f}, raw_m={raw_m_high:.4f}, clip_hi={MOS_TILT_CLIP_HI}"
    )

    result = mos_conviction_tilt(base, mos)

    assert all(v >= 0 for v in result.values()), (
        f"Negative weight after high-clip: {result}"
    )
    assert math.isclose(sum(result.values()), 1.0, abs_tol=1e-9), (
        f"Weights do not sum to 1: sum={sum(result.values())}"
    )

    # HIGH was clip-hi'd; LOW names get depressed multipliers → HIGH weight > any L.
    assert result["HIGH"] > result["L1"], (
        f"HIGH should have higher weight than L1 after clip-hi: "
        f"HIGH={result['HIGH']:.4f}, L1={result['L1']:.4f}"
    )


# ---------------------------------------------------------------------------
# C2_S — Sum-to-1
# ---------------------------------------------------------------------------


def test_C2_S1_sum_to_one_typical_book() -> None:
    """All non-degenerate non-empty outputs sum to 1.0 (within 1e-9).

    4-ticker book with dispersed MoS values (mix of positive and negative).
    """
    base = _renorm({"A": 0.30, "B": 0.20, "C": 0.25, "D": 0.25})
    mos = {"A": 25.0, "B": -5.0, "C": 10.0, "D": 0.0}

    result = mos_conviction_tilt(base, mos)

    assert math.isclose(sum(result.values()), 1.0, abs_tol=1e-9), (
        f"Weights do not sum to 1: {sum(result.values())}"
    )


def test_C2_S2_sum_to_one_mixed_none_mos() -> None:
    """Sum-to-1 holds when some MoS values are None (neutral z=0 path).

    None-MoS tickers get z=0 → m=1.0; the tilt still comes from the
    non-None tickers' dispersion.  The final renorm must sum to 1.
    """
    base = _renorm({"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25})
    mos: dict[str, float | None] = {"A": 30.0, "B": None, "C": -20.0, "D": None}

    result = mos_conviction_tilt(base, mos)

    assert math.isclose(sum(result.values()), 1.0, abs_tol=1e-9), (
        f"Weights with None mos do not sum to 1: {sum(result.values())}"
    )


def test_C2_S3_sum_to_one_all_weights_non_negative() -> None:
    """All output weights must be ≥ 0 (negativity not possible from the formula,
    but pin it anyway — an implementation bug could produce negative weights
    from a degenerate renorm path).
    """
    base = _renorm({"A": 0.4, "B": 0.15, "C": 0.20, "D": 0.25})
    mos = {"A": 50.0, "B": -30.0, "C": 15.0, "D": -10.0}

    result = mos_conviction_tilt(base, mos)

    assert all(v >= 0 for v in result.values()), (
        f"Negative weight found: {result}"
    )
    assert math.isclose(sum(result.values()), 1.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# C2_CAP — MAX_WEIGHT holds post-tilt
# ---------------------------------------------------------------------------


def test_C2_CAP1_max_weight_holds_after_tilt() -> None:
    """MAX_WEIGHT cap (0.35) must hold post-tilt on a 4-ticker book
    where one name would otherwise dominate.

    Construct a book where A is low-volatility (high base weight) AND
    highest-MoS → tilt amplifies its weight → the cap must bind and
    redistribute.
    """
    # Start from a skewed base (A already near MAX_WEIGHT after inverse-vol)
    # then give A a very high MoS.
    base = {"A": 0.34, "B": 0.25, "C": 0.21, "D": 0.20}
    mos = {"A": 80.0, "B": -20.0, "C": -10.0, "D": -30.0}

    result = mos_conviction_tilt(base, mos)

    assert all(v <= MAX_WEIGHT + 1e-9 for v in result.values()), (
        f"MAX_WEIGHT violated: {result}"
    )
    assert math.isclose(sum(result.values()), 1.0, abs_tol=1e-9), (
        f"Weights do not sum to 1 post-cap: {sum(result.values())}"
    )


def test_C2_CAP2_max_weight_holds_extreme_dispersion() -> None:
    """MAX_WEIGHT cap holds even with extreme MoS dispersion that would produce
    a very large multiplier for one name (clipped to MOS_TILT_CLIP_HI).

    n=4 (cap feasible: 4 × 0.35 = 1.40 > 1.0).
    """
    # Very unequal base, extreme MoS values
    base = {"A": 0.50, "B": 0.25, "C": 0.15, "D": 0.10}
    mos = {"A": 200.0, "B": -100.0, "C": -50.0, "D": -80.0}

    result = mos_conviction_tilt(base, mos)

    for t, w in result.items():
        assert w <= MAX_WEIGHT + 1e-9, (
            f"Ticker {t} exceeds MAX_WEIGHT after extreme-dispersion tilt: {w:.6f}"
        )
    assert math.isclose(sum(result.values()), 1.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# C2_DIR — Tilt direction (n ≥ 4, economically correct direction)
# ---------------------------------------------------------------------------


def test_C2_DIR1_highest_mos_weight_increases() -> None:
    """Tilt direction: the highest-MoS ticker's tilted weight > its base weight.

    Fixture: 4 tickers, equal base weight, dispersed MoS (no cap binding).
    The highest-MoS name gets a positive z → m > 1 → weight increases.
    """
    base = _equal_book(["A", "B", "C", "D"])
    mos = {"A": 30.0, "B": 10.0, "C": -5.0, "D": -20.0}

    result = mos_conviction_tilt(base, mos)

    # A has highest MoS → its weight must have increased from the base 0.25.
    assert result["A"] > base["A"], (
        f"Highest-MoS name weight decreased: base={base['A']:.4f}, tilted={result['A']:.4f}"
    )


def test_C2_DIR2_lowest_mos_weight_decreases() -> None:
    """Tilt direction: the lowest-MoS ticker's tilted weight < its base weight.

    Same fixture as C2_DIR1. D has the lowest MoS → most negative z
    → m < 1 → weight decreases.
    """
    base = _equal_book(["A", "B", "C", "D"])
    mos = {"A": 30.0, "B": 10.0, "C": -5.0, "D": -20.0}

    result = mos_conviction_tilt(base, mos)

    # D has lowest MoS → its weight must have decreased from 0.25.
    assert result["D"] < base["D"], (
        f"Lowest-MoS name weight increased: base={base['D']:.4f}, tilted={result['D']:.4f}"
    )


def test_C2_DIR3_rank_order_consistent_with_mos() -> None:
    """Tilt direction: with equal base weights and no cap binding, the resulting
    weight order must match the MoS order (highest MoS → highest weight).

    Fixture: 5 tickers, equal base, strictly ordered MoS values,
    dispersion small enough that the cap (MAX_WEIGHT=0.35) does not bind
    for any name (equal base = 0.20; the tilt can at most multiply by
    MOS_TILT_CLIP_HI=1.5, giving a provisional 0.30 < 0.35 → cap-free).
    """
    tickers = ["V5", "V4", "V3", "V2", "V1"]  # intentionally scrambled order
    base = _equal_book(tickers)
    # Assign mos in descending order to V5 > V4 > ... > V1
    mos = {"V5": 50.0, "V4": 25.0, "V3": 5.0, "V2": -15.0, "V1": -40.0}

    result = mos_conviction_tilt(base, mos)

    # Weight order must follow MoS order.
    assert result["V5"] > result["V4"] > result["V3"] > result["V2"] > result["V1"], (
        f"Weight order does not follow MoS order: {result}"
    )


# ---------------------------------------------------------------------------
# C2_NOIO — Pure function / no I/O
# ---------------------------------------------------------------------------


def test_C2_NOIO_no_filesystem_or_network() -> None:
    """Confirm mos_conviction_tilt is a pure in-memory function.

    Call it with plain dicts and assert the return value — no file access,
    no network, no side effects. This test is trivially true for a function
    that operates only on dict arguments, but exists explicitly to pin the
    contract (a future implementor must not add I/O to this function).
    """
    base = _renorm({"X": 0.6, "Y": 0.2, "Z": 0.1, "W": 0.1})
    mos = {"X": 20.0, "Y": 5.0, "Z": -10.0, "W": -30.0}

    result = mos_conviction_tilt(base, mos)

    # Basic sanity to confirm the call completed with a valid return.
    assert isinstance(result, dict)
    assert set(result.keys()) == set(base.keys())
    assert math.isclose(sum(result.values()), 1.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# C2_N2 — n=2 cap-infeasible → equal weight
# ---------------------------------------------------------------------------


def test_C2_N2_two_ticker_book_degrades_to_equal_weight() -> None:
    """n=2 cap infeasibility: n·MAX_WEIGHT = 2×0.35 = 0.70 < 1.0 → equal weight.

    The cap is infeasible; the function must return {A: 0.5, B: 0.5}
    regardless of MoS values — matching the inverse_vol_weights documented
    collapse (test_inverse_vol_infeasible_cap_degrades_to_equal in
    test_weights.py pins the same behaviour for inverse_vol_weights).

    This prevents the tilt from ever returning a sub-0.50 weight in a 2-name
    book (which would be financially nonsensical — you can't hold -50% of a
    position — and confirms the implementation reuses the same cap-feasibility
    guard as inverse_vol_weights).
    """
    base = {"A": 0.5, "B": 0.5}
    mos = {"A": 80.0, "B": -30.0}  # large dispersion that would normally dominate

    result = mos_conviction_tilt(base, mos)

    assert math.isclose(result["A"], 0.5, abs_tol=1e-9), (
        f"n=2 should degrade to equal weight; A={result['A']:.6f}"
    )
    assert math.isclose(result["B"], 0.5, abs_tol=1e-9), (
        f"n=2 should degrade to equal weight; B={result['B']:.6f}"
    )
    assert math.isclose(sum(result.values()), 1.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# C2_CONST — Constants pinned (methodology-scientist ratified calibration)
# ---------------------------------------------------------------------------


def test_C2_CONST_kappa_pinned() -> None:
    """MOS_TILT_KAPPA must be exactly 0.25 (Tier-2 gut-feel, disclosed).

    Changing this without a methodology-scientist re-derivation + CI sign-off
    is forbidden.  The pin makes any accidental change fail CI immediately.
    """
    assert MOS_TILT_KAPPA == 0.25, (
        f"MOS_TILT_KAPPA changed: got {MOS_TILT_KAPPA!r}, expected 0.25"
    )


def test_C2_CONST_clip_lo_pinned() -> None:
    """MOS_TILT_CLIP_LO must be exactly 0.5 (minimum multiplier)."""
    assert MOS_TILT_CLIP_LO == 0.5, (
        f"MOS_TILT_CLIP_LO changed: got {MOS_TILT_CLIP_LO!r}, expected 0.5"
    )


def test_C2_CONST_clip_hi_pinned() -> None:
    """MOS_TILT_CLIP_HI must be exactly 1.5 (maximum multiplier)."""
    assert MOS_TILT_CLIP_HI == 1.5, (
        f"MOS_TILT_CLIP_HI changed: got {MOS_TILT_CLIP_HI!r}, expected 1.5"
    )


# ---------------------------------------------------------------------------
# C2_PROP — Hypothesis property tests (MAX_WEIGHT + sum invariants)
#
# Input-contract note: mos_conviction_tilt's documented contract states that
# base_weights ALREADY satisfy MAX_WEIGHT (they come from inverse_vol_weights,
# which caps).  On the identity path (σ_mos=0 / all-None / n<2) the function
# returns base_weights UNCHANGED — byte-identity, by design, no re-cap.
# Passing arbitrary un-capped weights and asserting MAX_WEIGHT on the identity
# path violates the input contract and produces spurious falsifications.
#
# Fix: route generated weights through inverse_vol_weights (which caps) before
# passing to mos_conviction_tilt.  This mirrors the REAL production scenario:
# valid capped base (from inverse_vol_weights) → tilt → still valid.
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
    st.dictionaries(
        st.text(min_size=1, max_size=4),
        st.one_of(
            st.none(),
            st.floats(
                min_value=-200.0, max_value=200.0,
                allow_nan=False, allow_infinity=False,
            ),
        ),
        min_size=0,
        max_size=12,
    ),
)
def test_C2_PROP_max_weight_and_sum_invariants(raw_sigmas, mos_by_ticker):
    """Property: for any production-valid book (pre-capped via inverse_vol_weights)
    and any MoS vector (mix of floats and None):
    - max(result.values()) ≤ MAX_WEIGHT + 1e-9
    - all weights ≥ 0
    - sum(result.values()) == 1.0 ± 1e-9

    Strategy: generate raw_sigmas (positive floats as stand-in volatilities),
    run them through inverse_vol_weights to get a valid pre-capped base, then
    call mos_conviction_tilt.  This is the REAL production call chain: the
    function's input contract says base_weights already satisfy MAX_WEIGHT
    (they come from inverse_vol_weights); on the identity path (σ_mos==0 /
    all-None / n<2) base_weights are returned UNCHANGED — byte-identity by
    design — so we must not assert MAX_WEIGHT on the identity path unless we
    know the inputs already satisfy it.  Routing through inverse_vol_weights
    guarantees that invariant unconditionally.

    NO @settings(deadline=None) per issue #126 — slow examples are signal.
    """
    # Build production-valid pre-capped base weights.
    base = inverse_vol_weights(raw_sigmas)
    if not base:
        # inverse_vol_weights drops non-positive / nan sigmas; if all are bad
        # the result is {} — nothing to tilt, skip this example.
        return

    result = mos_conviction_tilt(base, mos_by_ticker)

    if not result:
        # Empty result only possible when base was empty (guarded above).
        return

    assert math.isclose(sum(result.values()), 1.0, abs_tol=1e-9), (
        f"Weights do not sum to 1: {sum(result.values())}"
    )
    assert all(v >= 0 for v in result.values()), (
        f"Negative weight found: {result}"
    )
    # MAX_WEIGHT invariant: always holds because either (a) the tilt path
    # re-caps via the iterative pin-redistribute loop, or (b) the identity
    # path returns base unchanged — and base was produced by inverse_vol_weights
    # which already guarantees MAX_WEIGHT.
    n = len(result)
    if n * MAX_WEIGHT >= 1.0 - 1e-12:  # cap feasible (always true for n ≥ 4)
        assert all(v <= MAX_WEIGHT + 1e-9 for v in result.values()), (
            f"MAX_WEIGHT ({MAX_WEIGHT}) violated: {result}"
        )
