"""Unit tests for the cross-source share-count-corruption shadow grader
(PR-1, ``compute.scoring.risk_overlay.grade_cross_source_corruption`` +
``compute_cross_source_corruption_shadow``).

Coverage policy (AGENTS.md §Testing): "add a test when a new defense ships"
— this file satisfies that policy for the PR-1 shadow observability layer.

Tests 1-9 live here (grading-function + aggregator);
Test 10 lives in ``tests/test_output/test_cross_source_corruption_schema.py``
(schema nullability — Metadata field contract).

Naming scheme mirrors the existing sibling:
``tests/test_scoring/test_post_split_share_lag.py`` (CSC prefix).

All inputs are SYNTHETIC DETERMINISTIC — no @network, no live SEC calls.
"""

from __future__ import annotations

from compute.ingest.fundamentals import FundamentalsSnapshot
from compute.scoring.risk_overlay import (
    _CORRUPTION_GRADE_CORRECT_CANDIDATE,
    _CORRUPTION_GRADE_NO_FIRE,
    _CORRUPTION_GRADE_VETO_CANDIDATE,
    compute_cross_source_corruption_shadow,
    grade_cross_source_corruption,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _snap(**kwargs) -> FundamentalsSnapshot:
    """Minimal healthy FundamentalsSnapshot; overrides target specific fields."""
    from datetime import date

    defaults = {
        "ticker": "TST",
        "cik": "0000000001",
        "revenue": 100_000_000.0,
        "net_income": 10_000_000.0,
        "total_assets": 200_000_000.0,
        "total_liabilities": 100_000_000.0,
        "stockholders_equity": 100_000_000.0,
        "current_assets": 100_000_000.0,
        "current_liabilities": 50_000_000.0,
        "operating_cash_flow": 10_000_000.0,
        "retained_earnings": 50_000_000.0,
        "operating_income": 20_000_000.0,
        "latest_period_end": date(2025, 12, 31),
        "latest_filed_date": date(2026, 2, 14),
    }
    defaults.update(kwargs)
    return FundamentalsSnapshot(**defaults)


# ---------------------------------------------------------------------------
# CSC1 — NO_FIRE below threshold (delta < 0.50)
# ---------------------------------------------------------------------------

def test_CSC1_no_fire_below_threshold():
    """Clean stock: delta ≈ 0.02 (2%) — well below 0.50 threshold.

    BKNG-style: EDGAR shares ≈ yfinance shares; tiny cross-source noise.
    """
    edgar_shares = 50_000_000.0
    current_price = 4_000.0
    # sec_mc = 50M × $4000 = $200B
    # yf_mc slightly different (2% delta) → NO_FIRE
    yf_market_cap = 200_000_000_000.0 * (1 + 0.02)  # 2% above

    result = grade_cross_source_corruption(
        edgar_shares=edgar_shares,
        current_price=current_price,
        yf_market_cap=yf_market_cap,
        yf_shares_outstanding=None,
    )

    assert result.grade == _CORRUPTION_GRADE_NO_FIRE
    assert result.inferred_ratio is None
    assert result.ratio_disagreement is False


# ---------------------------------------------------------------------------
# CSC2 — Threshold boundary: delta=0.499 → NO_FIRE; delta=0.500 → NOT NO_FIRE
# ---------------------------------------------------------------------------

def test_CSC2a_threshold_boundary_just_below():
    """delta = 0.499 → NO_FIRE (strictly below threshold 0.50)."""
    edgar_shares = 100_000_000.0
    current_price = 100.0
    # sec_mc = 100M × $100 = $10B
    # yf_mc such that delta = 0.499:
    # |sec_mc - yf_mc| / sec_mc = 0.499
    # yf_mc can be sec_mc * (1 - 0.499) = sec_mc * 0.501 (yf < sec)
    sec_mc = edgar_shares * current_price  # $10B
    yf_market_cap = sec_mc * (1 - 0.499)  # just below threshold

    result = grade_cross_source_corruption(
        edgar_shares=edgar_shares,
        current_price=current_price,
        yf_market_cap=yf_market_cap,
        yf_shares_outstanding=None,
    )

    assert result.grade == _CORRUPTION_GRADE_NO_FIRE


def test_CSC2b_threshold_boundary_exactly_at():
    """delta = 0.500 → NOT NO_FIRE (at-or-above threshold fires the grader).

    Note: 0.50 is the boundary; the code checks ``delta < threshold``,
    so 0.50 lands in the corruption territory (NOT NO_FIRE).
    """
    edgar_shares = 100_000_000.0
    current_price = 100.0
    sec_mc = edgar_shares * current_price  # $10B
    # delta = |sec_mc - yf_mc| / sec_mc = 0.50
    # choose yf_mc = sec_mc * (1 - 0.50) = sec_mc * 0.50
    yf_market_cap = sec_mc * 0.50  # exactly 50% below

    result = grade_cross_source_corruption(
        edgar_shares=edgar_shares,
        current_price=current_price,
        yf_market_cap=yf_market_cap,
        yf_shares_outstanding=None,
    )

    assert result.grade != _CORRUPTION_GRADE_NO_FIRE


# ---------------------------------------------------------------------------
# CSC3 — CORRECT_CANDIDATE CVNA-class
# ---------------------------------------------------------------------------

def test_CSC3_correct_candidate_cvna_class():
    """CVNA-class: mc_ratio ≈ 4.89, share_ratio ≈ 4.89, both round to 5.

    Simulates CVNA where EDGAR has 1/5th the true share count
    (unit-conversion: millions filed as units, causing a 5× undercount).

    CORRECT_CANDIDATE requires:
    - delta >= 0.50
    - mc_ratio is near-integer (rounds to ≥ 2, within 10% of that integer)
    - share_ratio is near-integer, rounds to the SAME integer as mc_ratio
    """
    edgar_shares = 100_000_000.0     # EDGAR sees 100M (corrupted: should be 500M)
    current_price = 50.0             # price $50
    # yf has the correct total: 500M shares × $50 = $25B
    yf_market_cap = 500_000_000.0 * current_price  # $25B
    # sec_mc = 100M × $50 = $5B
    # mc_ratio = $25B / $5B = 5.0 exactly → near-integer → rounds to 5
    # share_ratio = 489M / 100M = 4.89 (close to 5 but not exact — matches CVNA)
    yf_shares_outstanding = 489_000_000.0  # 4.89 × edgar_shares

    result = grade_cross_source_corruption(
        edgar_shares=edgar_shares,
        current_price=current_price,
        yf_market_cap=yf_market_cap,
        yf_shares_outstanding=yf_shares_outstanding,
    )

    assert result.grade == _CORRUPTION_GRADE_CORRECT_CANDIDATE
    assert result.inferred_ratio == 5.0
    assert result.ratio_disagreement is False
    assert result.share_ratio is not None
    # mc_ratio = 5.0 (exact)
    assert abs(result.mc_ratio - 5.0) < 0.01  # type: ignore[operator]
    # share_ratio = 489M / 100M = 4.89
    assert abs(result.share_ratio - 4.89) < 0.01  # type: ignore[operator]


# ---------------------------------------------------------------------------
# CSC4 — VETO_CANDIDATE COKE-class (LOAD-BEARING)
# ---------------------------------------------------------------------------

def test_CSC4_veto_candidate_coke_class_ratio_disagreement():
    """COKE-class: mc_ratio ≈ 7.07 → 7, share_ratio = 10.0 → 10, DISAGREE.

    This is the load-bearing test for the dual-ratio corroboration guard.
    COKE's yfinance marketCap is stale (reflects ~7× the EDGAR mc), while
    yfinance sharesOutstanding reflects the true 10× factor (or vice versa).

    A bare round(mc_ratio) = 7 would install the WRONG share-count correction.
    The corroboration guard catches this: both ratios are near-integer but
    round to DIFFERENT integers (7 ≠ 10) → VETO_CANDIDATE + ratio_disagreement=True.

    This is the methodology condition that COKE must NOT be auto-corrected.
    """
    edgar_shares = 100_000_000.0  # EDGAR sees 100M (corrupted — real is 1B)
    current_price = 50.0

    # sec_mc = 100M × $50 = $5B
    # yf_mc reflects stale data: 7.07 × sec_mc ≈ $35.35B
    sec_mc = edgar_shares * current_price
    yf_market_cap = sec_mc * 7.07  # mc_ratio = 7.07 → rounds to 7

    # yf sharesOutstanding is fresher: 10× edgar_shares
    yf_shares_outstanding = edgar_shares * 10.0  # share_ratio = 10.0 → rounds to 10

    result = grade_cross_source_corruption(
        edgar_shares=edgar_shares,
        current_price=current_price,
        yf_market_cap=yf_market_cap,
        yf_shares_outstanding=yf_shares_outstanding,
    )

    assert result.grade == _CORRUPTION_GRADE_VETO_CANDIDATE
    assert result.ratio_disagreement is True
    assert result.inferred_ratio is None  # no correction inferred when disagree


# ---------------------------------------------------------------------------
# CSC5 — VETO_CANDIDATE when yf_shares is None (no corroboration)
# ---------------------------------------------------------------------------

def test_CSC5_veto_candidate_no_yf_shares():
    """delta >= 0.50, mc_ratio near-integer BUT yf_shares_outstanding=None.

    Without corroboration from the share-ratio channel, CORRECT_CANDIDATE
    cannot be reached.  Safe fallback: VETO_CANDIDATE.
    """
    edgar_shares = 100_000_000.0
    current_price = 50.0
    sec_mc = edgar_shares * current_price  # $5B
    # mc_ratio = 5.0 → near-integer → rounds to 5
    yf_market_cap = sec_mc * 5.0

    result = grade_cross_source_corruption(
        edgar_shares=edgar_shares,
        current_price=current_price,
        yf_market_cap=yf_market_cap,
        yf_shares_outstanding=None,  # no corroboration
    )

    assert result.grade == _CORRUPTION_GRADE_VETO_CANDIDATE
    assert result.share_ratio is None
    assert result.inferred_ratio is None


# ---------------------------------------------------------------------------
# CSC6 — VETO_CANDIDATE when mc_ratio is NOT near-integer
# ---------------------------------------------------------------------------

def test_CSC6_veto_candidate_mc_ratio_not_near_integer():
    """mc_ratio = 5.15 — outside the 10% near-integer tolerance of any integer ≥ 2.

    |5.15 - 5| / 5 = 0.03 ≤ 0.10 → actually near-integer.
    Need ratio that is more than 10% away from the nearest integer.
    Use mc_ratio = 5.55 → |5.55 - 6| / 6 = 0.075 ≤ 0.10... also near 6.
    Per methodology: |R − round(R)| / round(R) ≤ 0.10.

    round(5.55) = 6; |5.55 - 6| / 6 = 0.075 — within 10% of 6.
    round(5.50) = ... python rounds half-even: round(5.5) = 6. |5.5-6|/6=0.083 ≤ 0.10.

    Use mc_ratio = 5.15; round(5.15)=5; |5.15-5|/5 = 0.03 ≤ 0.10 → near 5.

    The comment in the test prompt says mc_ratio=5.15 → VETO. Let's re-read
    the _is_near_integer logic: |r - rounded| / rounded <= tolerance (0.10).
    5.15: rounded=5, |5.15-5|/5 = 0.03 ≤ 0.10 → IS near-integer.

    To get NOT near-integer, need: |r - round(r)| / round(r) > 0.10.
    E.g., mc_ratio = 5.6: round=6, |5.6-6|/6 = 0.067 ≤ 0.10 → near 6.
    mc_ratio = 1.5: round=2, |1.5-2|/2 = 0.25 > 0.10 → NOT near integer (and round=2 ≥ 2).

    Better: mc_ratio = 1.5 (round=2, frac_error=0.25 > 0.10 → NOT near integer).
    Or mc_ratio = 2.3: round=2, |2.3-2|/2 = 0.15 > 0.10 → NOT near integer.

    The test prompt says mc_ratio=5.15 → VETO. Looking at threshold for factor 5:
    tolerance boundary = 5 ± 10% × 5 = [4.5, 5.5). mc_ratio=5.15 is inside [4.5,5.5)
    → IS near-integer. The prompt seems to specify 5.15 as > 10% of 5, which is wrong.

    Let's use mc_ratio = 2.3: round=2, |2.3-2|/2=0.15>0.10 → NOT near-integer → VETO.
    This captures the spirit: mc_ratio not near any integer ≥ 2.
    """
    edgar_shares = 100_000_000.0
    current_price = 50.0
    sec_mc = edgar_shares * current_price  # $5B
    # mc_ratio = 2.3: |2.3-2|/2 = 0.15 > 0.10 → NOT near integer (round=2 ≥ 2 but fails)
    yf_market_cap = sec_mc * 2.3

    result = grade_cross_source_corruption(
        edgar_shares=edgar_shares,
        current_price=current_price,
        yf_market_cap=yf_market_cap,
        yf_shares_outstanding=edgar_shares * 2.3,
    )

    assert result.grade == _CORRUPTION_GRADE_VETO_CANDIDATE
    assert result.inferred_ratio is None
    # mc_ratio ≈ 2.3 → not near-integer → ratio_disagreement should be False
    # (single non-near-integer mc_ratio path does NOT set ratio_disagreement)
    assert result.ratio_disagreement is False


# ---------------------------------------------------------------------------
# CSC7 — VETO_CANDIDATE when share_ratio is NOT near-integer (mc IS near-integer)
# ---------------------------------------------------------------------------

def test_CSC7_veto_candidate_share_ratio_not_near_integer():
    """mc_ratio = 5.0 (near-integer, rounds to 5) BUT share_ratio = 5.15 would be
    near-integer. Need share_ratio that's NOT near-integer.

    Per the prompt: mc_ratio=5.0→5 but share_ratio=5.15.
    |5.15-5|/5 = 0.03 ≤ 0.10 → actually near-integer! But the prompt
    says VETO + ratio_disagreement=True.

    The condition for ratio_disagreement=True (from the production code):
    - mc IS near-integer (mc_rounded = 5)
    - share IS available
    - if share NOT near-integer → ratio_disagreement=True → VETO
    - if share IS near-integer BUT mc_rounded ≠ share_rounded → ratio_disagreement=True

    The code at line 780-789: if not share_near → ratio_disagreement=True.
    So if share_ratio=5.15 IS near 5 (error=0.03 ≤ 0.10), share_near=True,
    then mc_rounded=5 == share_rounded=5 → CORRECT_CANDIDATE. That contradicts
    the prompt which says VETO.

    Re-reading the test spec: "share_ratio=5.15 → VETO_CANDIDATE + ratio_disagreement=True"
    The only way this is VETO + disagreement is if share_ratio is near-integer but
    rounds to DIFFERENT integer than mc_ratio. E.g.:
      mc_ratio = 5.0 → rounds to 5
      share_ratio = 5.15 → rounds to 5 (near-integer, same integer → CORRECT)
    That contradicts the spec.

    Alternatively: mc_ratio=5.0→5, share_ratio=6.0→6 → disagree=True → VETO.
    This makes CSC7 a "share near-integer but disagrees" test, distinct from
    CSC4 (COKE). Let's use that interpretation to make the test meaningful.

    Use: mc_ratio=5.0 (near 5), share_ratio=6.0 (near 6), disagree → VETO.
    """
    edgar_shares = 100_000_000.0
    current_price = 50.0
    sec_mc = edgar_shares * current_price  # $5B
    # mc_ratio = 5.0 exactly
    yf_market_cap = sec_mc * 5.0
    # share_ratio = 6.0 (near-integer → 6, disagrees with mc_rounded=5)
    yf_shares_outstanding = edgar_shares * 6.0

    result = grade_cross_source_corruption(
        edgar_shares=edgar_shares,
        current_price=current_price,
        yf_market_cap=yf_market_cap,
        yf_shares_outstanding=yf_shares_outstanding,
    )

    assert result.grade == _CORRUPTION_GRADE_VETO_CANDIDATE
    assert result.ratio_disagreement is True
    assert result.inferred_ratio is None


# ---------------------------------------------------------------------------
# CSC8 — NO_FIRE graceful on missing / None inputs
# ---------------------------------------------------------------------------

def test_CSC8a_no_fire_when_edgar_shares_none():
    """None edgar_shares → NO_FIRE, no crash."""
    result = grade_cross_source_corruption(
        edgar_shares=None,
        current_price=50.0,
        yf_market_cap=10_000_000_000.0,
        yf_shares_outstanding=100_000_000.0,
    )
    assert result.grade == _CORRUPTION_GRADE_NO_FIRE


def test_CSC8b_no_fire_when_price_none():
    """None current_price → NO_FIRE, no crash."""
    result = grade_cross_source_corruption(
        edgar_shares=100_000_000.0,
        current_price=None,
        yf_market_cap=10_000_000_000.0,
        yf_shares_outstanding=100_000_000.0,
    )
    assert result.grade == _CORRUPTION_GRADE_NO_FIRE


def test_CSC8c_no_fire_when_yf_market_cap_none():
    """None yf_market_cap → NO_FIRE, no crash."""
    result = grade_cross_source_corruption(
        edgar_shares=100_000_000.0,
        current_price=50.0,
        yf_market_cap=None,
        yf_shares_outstanding=100_000_000.0,
    )
    assert result.grade == _CORRUPTION_GRADE_NO_FIRE


# ---------------------------------------------------------------------------
# CSC9 — compute_cross_source_corruption_shadow aggregation
# ---------------------------------------------------------------------------

def test_CSC9_aggregation_4_ticker_universe():
    """4-ticker universe (COKE/CVNA/BKNG/KLAC-style synthetic inputs).

    Expected outcome:
    - CVNA_STYLE: CORRECT_CANDIDATE → correct_candidate=1, inferred_ratio=5.0
    - COKE_STYLE: VETO_CANDIDATE (ratio_disagreement=True) → veto=1, ratio_disagree=1
    - BKNG_STYLE: NO_FIRE (delta < 0.50) → no counts
    - KLAC_STYLE: NO_FIRE (delta ≈ 0 post-correction) → no counts

    Counts: correct_candidate=1, veto_candidate=1, ratio_disagreement=1
    inferred_ratio_by_ticker = {"CVNA_STYLE": 5.0}
    """
    # CVNA_STYLE: 5× undercount, both ratios → 5 (CORRECT_CANDIDATE)
    cvna_shares = 100_000_000.0
    cvna_price = 50.0
    cvna_sec_mc = cvna_shares * cvna_price  # $5B
    cvna_yf_mc = cvna_sec_mc * 5.0        # $25B
    cvna_yf_so = cvna_shares * 4.89       # share_ratio≈4.89→5, agrees

    # COKE_STYLE: mc_ratio≈7.07→7, share_ratio=10→10, disagree (VETO)
    coke_shares = 100_000_000.0
    coke_price = 50.0
    coke_sec_mc = coke_shares * coke_price
    coke_yf_mc = coke_sec_mc * 7.07      # mc_ratio≈7.07→7
    coke_yf_so = coke_shares * 10.0      # share_ratio=10.0→10, disagrees

    # BKNG_STYLE: clean stock, delta≈0.02 < 0.50 (NO_FIRE)
    bkng_shares = 50_000_000.0
    bkng_price = 4_000.0
    bkng_sec_mc = bkng_shares * bkng_price  # $200B
    bkng_yf_mc = bkng_sec_mc * 1.02        # 2% delta

    # KLAC_STYLE: already corrected, delta≈0 (NO_FIRE)
    klac_shares = 134_000_000.0
    klac_price = 700.0
    klac_sec_mc = klac_shares * klac_price
    klac_yf_mc = klac_sec_mc * 1.01  # 1% delta

    # Build FundamentalsSnapshot objects (for snap.shares_outstanding)
    cvna_snap = _snap(ticker="CVNA", shares_outstanding=cvna_shares)
    coke_snap = _snap(ticker="COKE", shares_outstanding=coke_shares)
    bkng_snap = _snap(ticker="BKNG", shares_outstanding=bkng_shares)
    klac_snap = _snap(ticker="KLAC", shares_outstanding=klac_shares)

    # universe_deltas: non-None so the aggregator processes each ticker
    universe_deltas = {
        "CVNA_STYLE": abs(cvna_sec_mc - cvna_yf_mc) / cvna_sec_mc,
        "COKE_STYLE": abs(coke_sec_mc - coke_yf_mc) / coke_sec_mc,
        "BKNG_STYLE": abs(bkng_sec_mc - bkng_yf_mc) / bkng_sec_mc,
        "KLAC_STYLE": abs(klac_sec_mc - klac_yf_mc) / klac_sec_mc,
    }
    snapshots = {
        "CVNA_STYLE": cvna_snap,
        "COKE_STYLE": coke_snap,
        "BKNG_STYLE": bkng_snap,
        "KLAC_STYLE": klac_snap,
    }
    current_prices = {
        "CVNA_STYLE": cvna_price,
        "COKE_STYLE": coke_price,
        "BKNG_STYLE": bkng_price,
        "KLAC_STYLE": klac_price,
    }
    yf_market_caps = {
        "CVNA_STYLE": cvna_yf_mc,
        "COKE_STYLE": coke_yf_mc,
        "BKNG_STYLE": bkng_yf_mc,
        "KLAC_STYLE": klac_yf_mc,
    }
    yf_shares = {
        "CVNA_STYLE": cvna_yf_so,
        "COKE_STYLE": coke_yf_so,
        "BKNG_STYLE": None,
        "KLAC_STYLE": None,
    }

    correct, veto, ratio_disagree, inferred = compute_cross_source_corruption_shadow(
        universe_deltas=universe_deltas,
        snapshots=snapshots,
        current_prices=current_prices,
        yf_market_caps=yf_market_caps,
        yf_shares_outstanding=yf_shares,
    )

    assert correct == 1, f"Expected 1 CORRECT_CANDIDATE (CVNA_STYLE), got {correct}"
    assert veto == 1, f"Expected 1 VETO_CANDIDATE (COKE_STYLE), got {veto}"
    assert ratio_disagree == 1, f"Expected 1 ratio_disagreement (COKE_STYLE), got {ratio_disagree}"
    assert "CVNA_STYLE" in inferred, f"Expected CVNA_STYLE in inferred_ratio_by_ticker: {inferred}"
    assert inferred["CVNA_STYLE"] == 5.0, f"Expected inferred_ratio=5.0 for CVNA_STYLE, got {inferred.get('CVNA_STYLE')}"
    assert "COKE_STYLE" not in inferred, "COKE_STYLE must NOT be in inferred_ratio_by_ticker (VETO)"
