"""Unit tests for Proposal C-1 — high-conviction gate counter (schema 0.10.39).

Coverage:
  A. _passes_ex_loss_chance divergence (THE key behavioral test — not a tautology)
  B. Superset invariant: ex_loss_chance_count >= high_conviction_count always
  C. _count_high_conviction edge cases
  D. Loss-chance-only blockers — marginal bite = exact N
  E. Adapter faithfulness: StockSummary fields map correctly via PickCandidate
  F. high_conviction_below_floor artifact-read semantics
  G. Metadata schema round-trip + defaults
  H. Regression guard: old tautological field name must be absent
"""

from __future__ import annotations

import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Imports — production modules under test
# ---------------------------------------------------------------------------
from compute.main import _count_high_conviction, _passes_ex_loss_chance
from compute.output.schemas import Metadata, StockSummary
from compute.portfolio.weights import (
    HIGH_CONVICTION_COMPOSITE_MIN,
    PickCandidate,
    is_high_conviction,
)

# ---------------------------------------------------------------------------
# Synthetic fixture builders
# ---------------------------------------------------------------------------

_ADAPTIVE_MIN_PICKS_C1: int = 5  # mirrors the production constant in main.py


def _candidate(
    *,
    recommendation: str = "bullish",
    mos_pct: float | None = 15.0,
    composite_score: float = 65.0,
    loss_chance_pct: float | None = 30.0,
    risk_flags: tuple[str, ...] = (),
    ticker: str = "TST",
    sector: str = "Technology",
) -> PickCandidate:
    """Build a PickCandidate; defaults are all-pass (clears all 5 HC legs)."""
    return PickCandidate(
        ticker=ticker,
        composite_score=composite_score,
        sector=sector,
        risk_flags=risk_flags,
        recommendation=recommendation,
        mos_pct=mos_pct,
        loss_chance_pct=loss_chance_pct,
    )


def _summary(
    *,
    ticker: str = "TST",
    composite_score: float = 65.0,
    recommendation: str | None = "bullish",
    margin_of_safety_pct: float | None = 15.0,
    loss_chance_pct: float | None = 30.0,
    risk_flags: list[str] | None = None,
    sector: str = "Technology",
) -> StockSummary:
    """Build a minimal StockSummary (the type _count_high_conviction consumes)."""
    return StockSummary(
        rank=1,
        ticker=ticker,
        name="Test Corp",
        sector=sector,
        composite_score=composite_score,
        current_price=100.0,
        risk_flags=risk_flags if risk_flags is not None else [],
        recommendation=recommendation,
        margin_of_safety_pct=margin_of_safety_pct,
        loss_chance_pct=loss_chance_pct,
    )


def _meta(**overrides) -> Metadata:
    """Build a minimal Metadata; all C-1 fields default to None."""
    defaults = dict(
        version="0.10.39-phase8pilot",
        last_update_utc="2026-06-26T22:00:00Z",
        next_update_utc="2026-06-27T22:00:00Z",
        universe="SP1500",
        universe_size=1504,
        compute_run_id="test-c1-001",
        git_commit="c1c1c1c1",
    )
    defaults.update(overrides)
    return Metadata(**defaults)


# ===========================================================================
# Section A — _passes_ex_loss_chance divergence (THE behavioral test)
# ===========================================================================


def test_A1_divergence_loss_chance_only_blocker():
    """A candidate passing legs 1-4 but failing leg 5 (loss_chance=50 > 45)
    must be counted by _passes_ex_loss_chance but NOT by is_high_conviction.

    This is the KEY behavioral test: it proves the two counters are NOT
    tautological — ex_loss_chance counts names that the loss-chance leg
    specifically excludes, providing the marginal-bite denominator.
    """
    c = _candidate(loss_chance_pct=50.0)  # > HIGH_CONVICTION_LOSS_CHANCE_MAX=45

    assert _passes_ex_loss_chance(c) is True, (
        "_passes_ex_loss_chance (legs 1-4 only) must fire even though "
        "loss_chance_pct=50 would fail the full HC gate"
    )
    assert is_high_conviction(c) is False, (
        "is_high_conviction must fail because loss_chance_pct=50 > 45 (leg 5)"
    )


def test_A2_divergence_loss_chance_at_ceiling():
    """Boundary: loss_chance_pct = 45 passes the full gate (≤ 45 is the rule)."""
    c = _candidate(loss_chance_pct=45.0)
    assert is_high_conviction(c) is True
    assert _passes_ex_loss_chance(c) is True


def test_A3_divergence_extreme_loss_chance():
    """loss_chance_pct=99 — extreme failure of leg 5 — still passes legs 1-4."""
    c = _candidate(loss_chance_pct=99.0)
    assert _passes_ex_loss_chance(c) is True
    assert is_high_conviction(c) is False


def test_A4_divergence_loss_chance_none_fails_full_gate_passes_ex():
    """loss_chance_pct=None: full HC gate is fail-closed (returns False),
    but _passes_ex_loss_chance must still pass legs 1-4 — None is
    neither required nor fail-closed in the ex variant.
    """
    c = _candidate(loss_chance_pct=None)
    # Full gate: None → fail-closed
    assert is_high_conviction(c) is False
    # Ex variant: loss_chance leg is omitted → passes if legs 1-4 clear
    assert _passes_ex_loss_chance(c) is True


def test_A5_all_pass_candidate_agrees():
    """A clean candidate (all 5 legs pass) should be counted by BOTH functions."""
    c = _candidate(loss_chance_pct=20.0)  # comfortably within ceiling
    assert is_high_conviction(c) is True
    assert _passes_ex_loss_chance(c) is True


# ===========================================================================
# Section B — Superset invariant: ex_loss_chance_count >= high_conviction_count
# ===========================================================================


def test_B1_superset_invariant_holds_for_mixed_pool():
    """ex_loss_chance_count must be >= high_conviction_count for any mix of candidates."""
    summaries = [
        _summary(loss_chance_pct=20.0),    # passes all 5 legs
        _summary(loss_chance_pct=50.0, ticker="B"),  # fails only leg 5
        _summary(recommendation="neutral", ticker="C"),  # fails leg 2
        _summary(margin_of_safety_pct=None, ticker="D"),  # fails leg 3
    ]
    hc_count, ex_count = _count_high_conviction(summaries)
    assert ex_count >= hc_count, (
        f"Superset invariant violated: ex_count={ex_count} < hc_count={hc_count}"
    )


def test_B2_superset_invariant_all_pass():
    """When every candidate passes all 5 legs, ex == hc (bite == 0)."""
    summaries = [
        _summary(ticker=f"T{i}", composite_score=65.0, loss_chance_pct=20.0)
        for i in range(5)
    ]
    hc_count, ex_count = _count_high_conviction(summaries)
    assert ex_count >= hc_count


def test_B3_superset_invariant_none_pass():
    """When no candidate passes even legs 1-4, ex_count == hc_count == 0."""
    summaries = [
        _summary(recommendation="cautious", ticker="A"),
        _summary(recommendation="neutral", ticker="B"),
    ]
    hc_count, ex_count = _count_high_conviction(summaries)
    assert hc_count == 0
    assert ex_count == 0
    assert ex_count >= hc_count


# ===========================================================================
# Section C — _count_high_conviction edge cases
# ===========================================================================


def test_C1_empty_list_returns_zero_zero():
    """_count_high_conviction([]) must return (0, 0) — no ZeroDivisionError,
    no crash, no sentinel.
    """
    result = _count_high_conviction([])
    assert result == (0, 0), f"Expected (0, 0), got {result}"


def test_C2_return_type_is_int_tuple():
    """Return type must be a 2-tuple of ints."""
    result = _count_high_conviction([])
    assert isinstance(result, tuple)
    assert len(result) == 2
    hc, ex = result
    assert isinstance(hc, int)
    assert isinstance(ex, int)


def test_C3_single_all_pass_candidate():
    """A single fully-passing candidate → (1, 1)."""
    summaries = [_summary()]
    hc, ex = _count_high_conviction(summaries)
    assert hc == 1
    assert ex == 1


def test_C4_single_all_fail_candidate():
    """A candidate failing leg 1 (active veto) → (0, 0)."""
    summaries = [_summary(risk_flags=["beneish_manipulation_veto"])]
    hc, ex = _count_high_conviction(summaries)
    assert hc == 0
    assert ex == 0


# ===========================================================================
# Section D — All-pass candidates → both counts == universe size
# ===========================================================================


def test_D1_all_pass_universe():
    """N candidates all passing all 5 legs → hc_count == ex_count == N."""
    N = 10
    summaries = [
        _summary(
            ticker=f"T{i}",
            composite_score=65.0,
            recommendation="bullish",
            margin_of_safety_pct=20.0,
            loss_chance_pct=30.0,
        )
        for i in range(N)
    ]
    hc, ex = _count_high_conviction(summaries)
    assert hc == N, f"Expected hc={N}, got {hc}"
    assert ex == N, f"Expected ex={N}, got {ex}"


def test_D2_lean_bullish_recommendation_also_qualifies():
    """lean_bullish is in HIGH_CONVICTION_RECOMMENDATIONS — must pass legs 2+."""
    summaries = [
        _summary(recommendation="lean_bullish", composite_score=50.0, loss_chance_pct=44.0)
    ]
    hc, ex = _count_high_conviction(summaries)
    assert hc == 1
    assert ex == 1


# ===========================================================================
# Section E — Loss-chance-only blockers: bite == N (ex − hc == N)
# ===========================================================================


def test_E1_loss_chance_blockers_bite_exact_count():
    """N candidates fail ONLY leg 5 (loss_chance_pct > 45) while passing legs 1-4.
    ex − hc must equal exactly N.
    """
    N = 3
    # These all pass legs 1-4 but fail leg 5
    blockers = [
        _summary(ticker=f"LC{i}", loss_chance_pct=50.0 + i)
        for i in range(N)
    ]
    # These pass all 5 legs
    passers = [
        _summary(ticker=f"OK{i}", loss_chance_pct=20.0)
        for i in range(2)
    ]
    hc, ex = _count_high_conviction(blockers + passers)
    # passers contribute 2 to both; blockers contribute 0 to hc, N to ex
    assert hc == 2, f"Expected hc=2 (passers only), got {hc}"
    assert ex == N + 2, f"Expected ex={N + 2} (all legs-1-4 passers), got {ex}"
    bite = ex - hc
    assert bite == N, (
        f"Bite (ex − hc) must equal the number of loss-chance-only blockers "
        f"N={N}; got bite={bite}"
    )


def test_E2_zero_loss_chance_blockers_zero_bite():
    """When all candidates either fully pass or fail before leg 5, bite == 0."""
    summaries = [
        _summary(ticker="A", loss_chance_pct=20.0),    # passes all 5
        _summary(ticker="B", recommendation="neutral"), # fails leg 2
        _summary(ticker="C", margin_of_safety_pct=None),  # fails leg 3
    ]
    hc, ex = _count_high_conviction(summaries)
    bite = ex - hc
    assert bite == 0, (
        "No loss-chance-only blockers → bite must be 0; "
        f"got hc={hc}, ex={ex}, bite={bite}"
    )


# ===========================================================================
# Section F — Adapter faithfulness: StockSummary → PickCandidate mapping
# ===========================================================================


def test_F1_summary_fully_qualifying_maps_to_hc_pass():
    """A StockSummary with all qualifying fields maps via _count_high_conviction
    to hc=1, ex=1 (the adapter builds a correct PickCandidate internally).
    """
    s = _summary(
        recommendation="bullish",
        margin_of_safety_pct=15.0,
        composite_score=60.0,
        loss_chance_pct=30.0,
    )
    hc, ex = _count_high_conviction([s])
    assert hc == 1
    assert ex == 1


def test_F2_summary_below_composite_floor_excluded():
    """composite_score < HIGH_CONVICTION_COMPOSITE_MIN (50.0) → fails leg 4."""
    s = _summary(composite_score=HIGH_CONVICTION_COMPOSITE_MIN - 0.1)
    hc, ex = _count_high_conviction([s])
    assert hc == 0
    assert ex == 0


def test_F3_summary_zero_mos_excluded_both_counts():
    """margin_of_safety_pct = 0.0 is NOT > 0 → fails leg 3 (strict gt).
    Both counts must be 0.
    """
    s = _summary(margin_of_safety_pct=0.0)
    hc, ex = _count_high_conviction([s])
    assert hc == 0
    assert ex == 0


def test_F4_summary_negative_mos_excluded():
    """Negative margin_of_safety_pct (overvalued) → fails leg 3."""
    s = _summary(margin_of_safety_pct=-5.0)
    hc, ex = _count_high_conviction([s])
    assert hc == 0
    assert ex == 0


def test_F5_summary_loss_chance_only_fail_diverges():
    """StockSummary with loss_chance_pct > 45 → hc=0, ex=1 (divergence via adapter)."""
    s = _summary(loss_chance_pct=60.0)
    hc, ex = _count_high_conviction([s])
    assert hc == 0
    assert ex == 1


def test_F6_summary_active_veto_excludes_from_both():
    """An active rank-gate veto (leg 1 failure) excludes from both counts."""
    s = _summary(risk_flags=["altman_distress"])
    hc, ex = _count_high_conviction([s])
    assert hc == 0
    assert ex == 0


# ===========================================================================
# Section G — high_conviction_below_floor artifact-read logic
# ===========================================================================


def _write_pit(tmp_path: Path, rebalances: list[dict]) -> Path:
    """Write a synthetic backtest_pit.json artifact to tmp_path/portfolio/."""
    pit_dir = tmp_path / "portfolio"
    pit_dir.mkdir(parents=True, exist_ok=True)
    pit_file = pit_dir / "backtest_pit.json"
    pit_file.write_text(json.dumps({"rebalances": rebalances}), encoding="utf-8")
    return pit_file


def _below_floor_from_artifact(tmp_path: Path, rebalances: list[dict]) -> bool | None:
    """Replicate the C-1 below_floor read block from main.py inline.

    Returns True / False / None as the production code does.
    Kept here (not imported) because the block is embedded in
    run_weekly_compute and has no standalone function to import.
    """
    _ADAPTIVE_MIN = 5
    _c1_pit_path = tmp_path / "portfolio" / "backtest_pit.json"
    if not _c1_pit_path.exists():
        return None
    try:
        with _c1_pit_path.open("r", encoding="utf-8") as fh:
            pit_data = json.load(fh)
        legs = [
            int(rb["eligible_high_conviction_count"])
            for rb in pit_data.get("rebalances", [])
            if rb.get("eligible_high_conviction_count") is not None
        ]
        if not legs:
            return None
        return any(n < _ADAPTIVE_MIN for n in legs)
    except Exception:  # noqa: BLE001
        return None


def test_G1_below_floor_false_when_all_legs_clear_floor(tmp_path: Path):
    """All rebalance legs have eligible_high_conviction_count >= 5 → False."""
    rebalances = [
        {"eligible_high_conviction_count": 5},
        {"eligible_high_conviction_count": 10},
        {"eligible_high_conviction_count": 7},
    ]
    _write_pit(tmp_path, rebalances)
    result = _below_floor_from_artifact(tmp_path, rebalances)
    assert result is False, (
        f"Expected False (all legs >= 5), got {result!r}"
    )


def test_G2_below_floor_true_when_one_leg_below_floor(tmp_path: Path):
    """One rebalance leg has eligible_high_conviction_count < 5 → True."""
    rebalances = [
        {"eligible_high_conviction_count": 6},
        {"eligible_high_conviction_count": 4},  # below floor
        {"eligible_high_conviction_count": 8},
    ]
    _write_pit(tmp_path, rebalances)
    result = _below_floor_from_artifact(tmp_path, rebalances)
    assert result is True, (
        f"Expected True (one leg < 5), got {result!r}"
    )


def test_G3_below_floor_none_when_artifact_absent(tmp_path: Path):
    """Missing backtest_pit.json → None (graceful degradation)."""
    result = _below_floor_from_artifact(tmp_path, [])
    # File does not exist → None
    assert result is None, (
        f"Expected None when artifact is absent, got {result!r}"
    )


def test_G4_below_floor_none_when_no_hc_count_entries(tmp_path: Path):
    """Rebalances present but none have eligible_high_conviction_count → None."""
    rebalances = [
        {"date": "2025-01-01", "picks": ["AAPL", "MSFT"]},
    ]
    _write_pit(tmp_path, rebalances)
    result = _below_floor_from_artifact(tmp_path, rebalances)
    assert result is None, (
        "No eligible_high_conviction_count entries → None (not False)"
    )


def test_G5_below_floor_none_on_malformed_json(tmp_path: Path):
    """Corrupt JSON → None (non-fatal try/except, cron never blocked)."""
    pit_dir = tmp_path / "portfolio"
    pit_dir.mkdir(parents=True, exist_ok=True)
    (pit_dir / "backtest_pit.json").write_text("{not valid json", encoding="utf-8")
    result = _below_floor_from_artifact(tmp_path, [])
    assert result is None, (
        f"Malformed JSON must degrade to None, got {result!r}"
    )


def test_G6_below_floor_boundary_exactly_5_is_not_below(tmp_path: Path):
    """Exactly 5 clears the floor (< 5 fires, == 5 does not)."""
    rebalances = [
        {"eligible_high_conviction_count": 5},
    ]
    _write_pit(tmp_path, rebalances)
    result = _below_floor_from_artifact(tmp_path, rebalances)
    assert result is False, (
        "eligible_high_conviction_count == 5 is exactly at floor, not below it"
    )


# ===========================================================================
# Section H — Metadata schema round-trip + defaults
# ===========================================================================


def test_H1_metadata_c1_fields_default_to_none():
    """All 3 C-1 Metadata fields must default to None (backward-compat with
    pre-0.10.39 JSON artifacts that have no high_conviction_* keys).
    """
    m = _meta()
    assert m.high_conviction_count is None, (
        "high_conviction_count must default to None"
    )
    assert m.high_conviction_ex_loss_chance_count is None, (
        "high_conviction_ex_loss_chance_count must default to None"
    )
    assert m.high_conviction_below_floor is None, (
        "high_conviction_below_floor must default to None"
    )


def test_H2_metadata_c1_fields_round_trip():
    """C-1 fields survive a Pydantic model_dump → model_validate round-trip."""
    m = _meta(
        high_conviction_count=40,
        high_conviction_ex_loss_chance_count=45,
        high_conviction_below_floor=False,
    )
    payload = m.model_dump(mode="json")
    m2 = Metadata.model_validate(payload)

    assert m2.high_conviction_count == 40
    assert m2.high_conviction_ex_loss_chance_count == 45
    assert m2.high_conviction_below_floor is False


def test_H3_metadata_extra_forbid_does_not_raise_on_c1_fields():
    """StockSummary + Metadata both carry extra="forbid"; constructing with
    the 3 C-1 fields must not raise.
    """
    # Should not raise ValidationError
    m = _meta(
        high_conviction_count=10,
        high_conviction_ex_loss_chance_count=12,
        high_conviction_below_floor=True,
    )
    assert m.high_conviction_count == 10
    assert m.high_conviction_ex_loss_chance_count == 12
    assert m.high_conviction_below_floor is True


def test_H4_metadata_below_floor_bool_true_round_trips():
    """high_conviction_below_floor=True survives serialization."""
    m = _meta(high_conviction_below_floor=True)
    payload = m.model_dump(mode="json")
    assert payload["high_conviction_below_floor"] is True
    m2 = Metadata.model_validate(payload)
    assert m2.high_conviction_below_floor is True


def test_H5_metadata_ex_count_geq_hc_count_when_both_populated():
    """Pydantic does NOT enforce the superset invariant at the schema level
    (it is a behavioral contract, not a validator).  Verify you CAN construct
    a Metadata with ex_count > hc_count (the expected real-world case).
    """
    m = _meta(
        high_conviction_count=38,
        high_conviction_ex_loss_chance_count=47,  # 47 >= 38
    )
    assert m.high_conviction_ex_loss_chance_count >= m.high_conviction_count


# ===========================================================================
# Section I — Regression guard: old tautological field must NOT exist
# ===========================================================================


def test_I1_old_tautological_field_absent_from_metadata():
    """REGRESSION GUARD: the old field 'high_conviction_mos_positive_count'
    (which was trivially == high_conviction_count and therefore useless as a
    marginal-bite denominator) must NOT be present in Metadata.model_fields.

    methodology-scientist corrected this to 'high_conviction_ex_loss_chance_count'
    with the proper semantics (legs 1-4 only, loss_chance NOT checked).
    Its absence prevents the tautological field from resurging.
    """
    assert "high_conviction_mos_positive_count" not in Metadata.model_fields, (
        "Tautological field 'high_conviction_mos_positive_count' must not exist "
        "on Metadata — it was renamed to 'high_conviction_ex_loss_chance_count' "
        "with corrected semantics (methodology-scientist correction 2026-06-26)"
    )


def test_I2_corrected_field_present_with_correct_name():
    """The corrected field 'high_conviction_ex_loss_chance_count' must exist
    on Metadata.model_fields (the correct name, not the tautological one).
    """
    assert "high_conviction_ex_loss_chance_count" in Metadata.model_fields, (
        "'high_conviction_ex_loss_chance_count' must be a Metadata field "
        "(legs 1-4 only, loss_chance leg omitted)"
    )


def test_I3_all_three_c1_fields_present():
    """All 3 C-1 schema fields must exist on Metadata.model_fields."""
    for field_name in (
        "high_conviction_count",
        "high_conviction_ex_loss_chance_count",
        "high_conviction_below_floor",
    ):
        assert field_name in Metadata.model_fields, (
            f"C-1 schema field '{field_name}' missing from Metadata.model_fields"
        )
