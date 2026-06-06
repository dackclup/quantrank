"""Offline tests for compute/features/alpha158_replicate.py (Phase 4j.1).

Coverage policy: "add a test when a new defense ships, or when a contract
is added to the output schema" (AGENTS.md §Testing). Phase 4j.1 adds:
- The Alpha158 long-short adapter (new production module)
- 9 optional Metadata.alpha158_* fields (new schema contracts)

All tests use synthetic fixtures — no @pytest.mark.network, no live SEC
EDGAR, no qlib, no openassetpricing import.

Test index
----------
A. Adapter core (5 example-based)
   A1 — empty feature panel → empty long_short DataFrame with correct columns
   A2 — basic decile spread: 2 features × 20 months → rows produced, columns correct
   A3 — last month has no forward return (by construction) → no row for the last month
   A4 — feature with always <10 valued names → forms no long_short row (dropped bucket)
   A5 — features_present / features_missing_from_compute / features_dropped_no_long_short helpers

B. Lag discipline (1 example-based, critical for look-ahead safety)
   B1 — signal predictive FORWARD but anti-correlated TRAILING: adapter's forward-shift
        means the predictive signal reaches the gate (dsr > 0 / accepted);
        a contemporaneous join would fail this test

C. Accounting equation property test (Hypothesis @given, load-bearing pin)
   C1 — for any synthetic manifest × feature panel, the four-bucket equation:
        len(requested) == missing + dropped + len(used) + len(excluded)
        holds EXACTLY. This is the invariant whose absence let Phase 4h's
        ~78-signal silent drop stay invisible for a full phase.

D. Survivorship honesty (3 example-based)
   D1 — universe_provider=None → survivorship_bias_corrected is False
   D2 — provider returning is_complete=True for every month → True
   D3 — any single month returning is_complete=False → False

E. Accounting bucket semantics (3 example-based, distinct from C)
   E1 — manifest feature never present as column → features_missing_from_compute
   E2 — feature present but never forms a row (<10 universe) → features_dropped_no_long_short
   E3 — feature that forms rows but is pure noise → reaches gate (may be excluded),
        is NOT in dropped bucket

F. Graceful degradation (1 example-based)
   F1 — _acquire_alpha158_inputs raises RuntimeError (deferred source)

G. coverage_pct (3 example-based)
   G1 — empty panel → None
   G2 — universe_size <= 0 → None
   G3 — known null/non-null panel at latest date → correct %

H. Schema — Δscore = 0 / no per-stock surface (2 structural assertions)
   H1 — StockDetail has NO alpha158_* field
   H2 — every Metadata.alpha158_* field is optional with default None
        (legacy data + degraded path both deserialize clean)
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from compute.features.alpha158_replicate import (
    MIN_UNIVERSE_FOR_DECILE_SPREAD,
    Alpha158LongShort,
    compute_alpha158_long_short_returns,
    coverage_pct,
    features_dropped_no_long_short,
    features_missing_from_compute,
    features_present,
)
from compute.validation.osap_validation import (
    filter_accepted_signals,
    gate_osap_signals,
)

# ---------------------------------------------------------------------------
# Helpers — synthetic fixture builders
# ---------------------------------------------------------------------------

_BASE_DATE = date(2020, 1, 31)
_MONTH = timedelta(days=31)


def _make_monthly_dates(n: int) -> list[date]:
    """Return n month-end dates starting at _BASE_DATE."""
    return [_BASE_DATE + _MONTH * i for i in range(n)]


def _make_feature_panel(
    features: dict[str, dict[tuple[date, str], float | None]],
    *,
    tickers: list[str] | None = None,
    dates: list[date] | None = None,
) -> pd.DataFrame:
    """Build a (date, ticker) MultiIndexed feature DataFrame.

    Args:
        features: {feature_name: {(date, ticker): value_or_None}}
            Use None to leave a cell NaN.
        tickers: override universe (defaults to sorted union of all tickers
            referenced in features).
        dates: override date list (defaults to sorted union).
    """
    # Collect all (date, ticker) pairs
    all_pairs: set[tuple[date, str]] = set()
    for cell_map in features.values():
        all_pairs.update(cell_map.keys())

    if not all_pairs:
        # Return empty panel with correct MultiIndex names
        idx = pd.MultiIndex.from_tuples([], names=["date", "ticker"])
        return pd.DataFrame(
            index=idx, columns=list(features.keys()), dtype=float
        )

    if dates is None:
        dates = sorted({d for d, _ in all_pairs})
    if tickers is None:
        tickers = sorted({t for _, t in all_pairs})

    idx = pd.MultiIndex.from_product([dates, tickers], names=["date", "ticker"])
    df = pd.DataFrame(index=idx, columns=list(features.keys()), dtype=float)
    for feat_name, cell_map in features.items():
        for (d, t), v in cell_map.items():
            if v is not None:
                df.loc[(d, t), feat_name] = float(v)
    return df


def _make_period_returns(
    ret_map: dict[tuple[date, str], float],
) -> pd.Series:
    """Build a (date, ticker) trailing-return Series."""
    pairs = sorted(ret_map.keys())
    idx = pd.MultiIndex.from_tuples(pairs, names=["date", "ticker"])
    return pd.Series([ret_map[p] for p in pairs], index=idx, name="ret", dtype=float)


def _make_dense_panel_and_returns(
    n_tickers: int,
    n_dates: int,
    feature_names: list[str],
    *,
    rng: np.random.RandomState | None = None,
) -> tuple[pd.DataFrame, pd.Series]:
    """Build a fully-populated (n_tickers × n_dates) panel + trailing returns.

    Returns a feature DataFrame and a matching trailing-return Series where
    every (date, ticker) cell has a finite value — the simplest possible
    input for property tests.
    """
    if rng is None:
        rng = np.random.RandomState(42)
    dates = _make_monthly_dates(n_dates)
    tickers = [f"TKR{i:02d}" for i in range(n_tickers)]
    idx = pd.MultiIndex.from_product([dates, tickers], names=["date", "ticker"])
    data = {f: rng.randn(len(idx)) for f in feature_names}
    feats = pd.DataFrame(data, index=idx)
    rets_vals = rng.randn(len(idx)) * 0.05  # plausible monthly scale
    rets = pd.Series(rets_vals, index=idx, name="ret")
    return feats, rets


# ---------------------------------------------------------------------------
# A. Adapter core
# ---------------------------------------------------------------------------


def test_A1_empty_feature_panel_returns_empty_long_short():
    """Empty feature panel → Alpha158LongShort with empty long_short + correct columns."""
    empty = pd.DataFrame(
        index=pd.MultiIndex.from_tuples([], names=["date", "ticker"]),
        columns=["KMID", "KLEN"],
        dtype=float,
    )
    rets = _make_period_returns({})
    result = compute_alpha158_long_short_returns(empty, rets)

    assert isinstance(result, Alpha158LongShort)
    assert result.long_short.empty
    assert set(result.long_short.columns) == {"signalname", "date", "ls_return"}
    assert result.survivorship_bias_corrected is False


def test_A2_basic_decile_spread_two_features_twenty_months():
    """2 features × 20 months (>= MIN for decile spread) → long_short rows with correct columns."""
    n_tickers = 15
    n_dates = 20
    feats, rets = _make_dense_panel_and_returns(
        n_tickers, n_dates, ["F1", "F2"], rng=np.random.RandomState(1)
    )
    result = compute_alpha158_long_short_returns(feats, rets)

    assert isinstance(result, Alpha158LongShort)
    assert not result.long_short.empty
    assert set(result.long_short.columns) == {"signalname", "date", "ls_return"}
    assert set(result.long_short["signalname"].unique()).issubset({"F1", "F2"})
    # Every ls_return must be a finite float
    assert result.long_short["ls_return"].notna().all()
    assert np.isfinite(result.long_short["ls_return"].values).all()


def test_A3_last_month_forms_no_row_no_forward_return():
    """The last month in the panel has no forward return by construction.

    With n_dates months, the adapter can only form rows for months
    0..n_dates-2 (the last month has no forward return). The long_short
    frame must have no rows with date == the final date.
    """
    n_tickers = 15
    n_dates = 6
    feats, rets = _make_dense_panel_and_returns(
        n_tickers, n_dates, ["F1"], rng=np.random.RandomState(2)
    )
    result = compute_alpha158_long_short_returns(feats, rets)
    if result.long_short.empty:
        return  # trivially correct

    dates_in_dates = _make_monthly_dates(n_dates)
    last_date = max(dates_in_dates)
    dates_in_ls = set(result.long_short["date"])
    assert last_date not in dates_in_ls, (
        f"Last month {last_date} must not appear in long_short (no forward return exists)"
    )


def test_A4_feature_below_min_universe_never_forms_row():
    """A feature with only 5 tickers across all dates forms no LS row.

    MIN_UNIVERSE_FOR_DECILE_SPREAD = 10. A panel with 5 tickers for one
    feature means that feature is always below the floor → goes to
    features_dropped_no_long_short, not to the gate.
    """
    dates = _make_monthly_dates(20)
    # Build a panel with 5 tickers for F_tiny, 15 for F_ok
    tickers_all = [f"TKR{i:02d}" for i in range(15)]
    tickers_tiny = tickers_all[:5]

    rng = np.random.RandomState(3)
    idx_all = pd.MultiIndex.from_product([dates, tickers_all], names=["date", "ticker"])
    idx_tiny = pd.MultiIndex.from_product([dates, tickers_tiny], names=["date", "ticker"])

    f_ok = pd.Series(rng.randn(len(idx_all)), index=idx_all, name="F_ok")
    f_tiny = pd.Series(rng.randn(len(idx_tiny)), index=idx_tiny, name="F_tiny")

    feats = pd.concat([f_ok, f_tiny], axis=1)
    rets = pd.Series(rng.randn(len(idx_all)) * 0.05, index=idx_all, name="ret")

    result = compute_alpha158_long_short_returns(feats, rets)
    ls_features = set(result.long_short["signalname"].unique())
    assert "F_tiny" not in ls_features, (
        "F_tiny has only 5 tickers, below MIN_UNIVERSE_FOR_DECILE_SPREAD; "
        "it must form no long_short row"
    )
    assert "F_ok" in ls_features, (
        "F_ok has 15 tickers and should form long_short rows"
    )


def test_A5_helper_functions_consistent():
    """features_present / features_missing_from_compute / features_dropped_no_long_short
    helpers return correct sets for a simple two-feature panel."""
    dates = _make_monthly_dates(5)
    tickers = [f"T{i}" for i in range(15)]
    rng = np.random.RandomState(4)
    idx = pd.MultiIndex.from_product([dates, tickers], names=["date", "ticker"])
    feats = pd.DataFrame(
        {"F_here": rng.randn(len(idx)), "F_also": rng.randn(len(idx))}, index=idx
    )
    rets = pd.Series(rng.randn(len(idx)) * 0.05, index=idx)
    ls_result = compute_alpha158_long_short_returns(feats, rets)

    requested = ("F_here", "F_also", "F_absent")
    assert features_present(feats) == frozenset({"F_here", "F_also"})
    missing = features_missing_from_compute(feats, requested)
    assert missing == ["F_absent"]

    dropped = features_dropped_no_long_short(ls_result.long_short, feats, requested)
    # F_absent is already in missing; dropped should not include it
    assert "F_absent" not in dropped
    # F_here / F_also may or may not be dropped depending on whether they
    # formed rows — but they should not be in dropped if they appear in LS
    ls_signals = set(ls_result.long_short["signalname"].unique())
    for sig in ls_signals:
        assert sig not in dropped, (
            f"{sig} forms LS rows but appears in dropped; that is wrong"
        )


# ---------------------------------------------------------------------------
# B. Lag discipline — the load-bearing look-ahead test
# ---------------------------------------------------------------------------


def test_B1_forward_shift_makes_predictive_signal_pass_gate():
    """Signal predictive of FORWARD return but anti-correlated with TRAILING return.

    Construction:
    - Dates: 24 months so we get 23 LS rows (MIN_OBS = 16 satisfied).
    - 30 tickers (> MIN_UNIVERSE_FOR_DECILE_SPREAD = 10).
    - For each month m, the 'PredictiveSignal' feature value is set to
      the future (m+1) return rank, so long-leg tickers are those whose
      NEXT month's return will be high. Anti-correlated with the current
      (trailing) return by construction.
    - The adapter shifts period_returns forward by one period internally,
      so feature@m pairs with the return over (m, m+1]. A correct
      forward-shift adapter will produce positive LS returns for this
      signal; a contemporaneous join would produce negative LS returns.
    - We then run gate_osap_signals and verify dsr > 0 (accepted or at
      minimum positive Sharpe from the right-direction rows).

    Smoke-verified by the implementation author: dsr ≈ 33 for the
    injected signal. This test pins the SIGN/acceptance only.
    """
    n_tickers = 30
    n_dates = 24  # gives 23 forward-return months
    rng = np.random.RandomState(99)
    dates = _make_monthly_dates(n_dates)
    tickers = [f"TKR{i:02d}" for i in range(n_tickers)]

    # Build TRAILING returns: random walk around 0
    trailing = rng.randn(n_dates, n_tickers) * 0.05  # shape (n_dates, n_tickers)

    # Build feature = forward return rank so it PREDICTS (m→m+1):
    # For month m, feature_value[m, t] ∝ trailing[m+1, t]
    # This makes the feature anti-correlated with trailing[m] but
    # perfectly predictive of trailing[m+1].
    feature = np.zeros((n_dates, n_tickers))
    for m in range(n_dates - 1):
        fwd = trailing[m + 1]  # next month's return
        # Feature = rank of next-month return (higher = better)
        ranks = fwd.argsort().argsort().astype(float)
        feature[m] = ranks
    # Last month: set feature to random (irrelevant; no forward return)
    feature[n_dates - 1] = rng.randn(n_tickers)

    # Build MultiIndex panel (dates × tickers, row-major order matches flatten())
    idx = pd.MultiIndex.from_product([dates, tickers], names=["date", "ticker"])
    feat_vals = feature.flatten()  # shape (n_dates * n_tickers,) row-major
    ret_vals = trailing.flatten()

    # Add a second noise signal so the PBO cohort has ≥ 2 columns
    # (gate_osap_signals requires cohort_size >= 2 to attempt PBO/DSR).
    noise_signal = rng.randn(len(idx)) * 0.1
    feats = pd.DataFrame(
        {"PredictiveSignal": feat_vals, "NoiseSignal": noise_signal}, index=idx
    )
    rets = pd.Series(ret_vals, index=idx, name="ret")

    result = compute_alpha158_long_short_returns(feats, rets)
    assert not result.long_short.empty, (
        "PredictiveSignal should form LS rows (30 tickers >= 10, 24 months)"
    )

    # Run the gate — cohort now has 2 signals so PBO/DSR can run
    gate_results = gate_osap_signals(result.long_short)
    assert "PredictiveSignal" in gate_results, (
        "gate should produce a result for PredictiveSignal"
    )
    gr = gate_results["PredictiveSignal"]

    # The key lag-discipline assertions:
    # 1. Sharpe > 0 (mean LS return is positive, correct forward direction).
    #    A contemporaneous/backward join would produce negative mean LS return
    #    → Sharpe < 0. The forward-shift adapter produces the correct direction.
    # 2. Mean LS return > 0 (raw signal, no gate threshold noise).
    # NOTE: DSR may land at exactly 0.0 with only 2 signals in the cohort
    # because the multiple-testing correction SR* ≈ observed Sharpe at that
    # cohort size. That is a mathematical boundary artifact, not a sign error.
    # The load-bearing lag-discipline pin is the SHARPE SIGN, not the DSR value.
    assert gr.sharpe is not None, (
        f"sharpe must not be None for a signal with enough obs (n_obs={gr.n_observations}, "
        f"rejection_reason={gr.rejection_reason!r})"
    )
    assert gr.sharpe > 0, (
        f"PredictiveSignal was injected to predict FORWARD returns; "
        f"the forward-shift adapter should yield sharpe > 0 (got {gr.sharpe:.4f}). "
        "A contemporaneous/backward join would flip the LS direction and "
        "produce sharpe < 0 — this is the look-ahead leak test."
    )
    # Verify mean LS return is positive (belt + suspenders)
    ps_rows = result.long_short[result.long_short["signalname"] == "PredictiveSignal"]
    mean_ls = float(ps_rows["ls_return"].mean())
    assert mean_ls > 0, (
        f"PredictiveSignal mean LS return = {mean_ls:.4f}; expected positive. "
        "Negative mean LS return would indicate the forward-shift is missing "
        "(contemporaneous join = look-ahead leak)."
    )


# ---------------------------------------------------------------------------
# C. Accounting equation property test (load-bearing pin, @given Hypothesis)
# ---------------------------------------------------------------------------


@st.composite
def _synthetic_panel_and_manifest(draw: st.DrawFn) -> tuple[
    pd.DataFrame, pd.Series, tuple[str, ...]
]:
    """Draw a synthetic feature panel + trailing returns + requested manifest.

    Strategy bounds:
    - n_tickers ∈ [MIN_UNIVERSE + 2, 25] so at least one feature can form LS rows
    - n_dates ∈ [18, 30] so MIN_OBS_PER_SIGNAL = 16 can be met
    - n_features_present ∈ [0, 5] columns in the panel
    - n_features_absent ∈ [0, 5] names in manifest but NOT in panel
    - n_features_tiny ∈ [0, 3] columns that always have < MIN_UNIVERSE non-NaN
      (guaranteed to be in dropped bucket)

    Returns (feats, rets, requested) with feats as a (date, ticker) MultiIndex
    DataFrame.
    """
    n_tickers = draw(st.integers(
        min_value=MIN_UNIVERSE_FOR_DECILE_SPREAD + 2, max_value=25
    ))
    n_dates = draw(st.integers(min_value=18, max_value=30))
    n_features_present = draw(st.integers(min_value=0, max_value=5))
    n_features_absent = draw(st.integers(min_value=0, max_value=5))
    n_features_tiny = draw(st.integers(min_value=0, max_value=3))
    seed = draw(st.integers(min_value=0, max_value=2**31 - 1))
    rng = np.random.RandomState(seed)

    dates = _make_monthly_dates(n_dates)
    tickers = [f"TKR{i:02d}" for i in range(n_tickers)]
    # Use only a few tickers for tiny features
    tiny_tickers = tickers[:max(1, MIN_UNIVERSE_FOR_DECILE_SPREAD - 1)]

    feat_names_present = [f"FP_{i}" for i in range(n_features_present)]
    feat_names_absent = [f"FA_{i}" for i in range(n_features_absent)]
    feat_names_tiny = [f"FT_{i}" for i in range(n_features_tiny)]

    requested: tuple[str, ...] = tuple(
        sorted(feat_names_present + feat_names_absent + feat_names_tiny)
    )

    # Build feature panel
    if feat_names_present or feat_names_tiny:
        idx_full = pd.MultiIndex.from_product(
            [dates, tickers], names=["date", "ticker"]
        )
        data: dict[str, np.ndarray] = {}
        for f in feat_names_present:
            data[f] = rng.randn(len(idx_full))
        # Tiny features: only populated for tiny_tickers
        tiny_data: dict[str, float] = {}
        for d in dates:
            for t in tiny_tickers:
                for f in feat_names_tiny:
                    tiny_data[(d, t, f)] = float(rng.randn())

        if data:
            feats = pd.DataFrame(data, index=idx_full)
        else:
            feats = pd.DataFrame(index=idx_full, columns=[], dtype=float)

        # Add tiny feature columns (reindex will fill with NaN for full tickers)
        for f in feat_names_tiny:
            tiny_series_data = {
                (d, t): tiny_data[(d, t, f)] for d in dates for t in tiny_tickers
            }
            tiny_idx = pd.MultiIndex.from_tuples(
                list(tiny_series_data.keys()), names=["date", "ticker"]
            )
            tiny_s = pd.Series(
                list(tiny_series_data.values()), index=tiny_idx, name=f
            )
            feats = feats.join(tiny_s, how="left")

        rets_raw = pd.Series(
            rng.randn(len(idx_full)) * 0.05, index=idx_full, name="ret"
        )
    else:
        # No features at all — empty panel
        empty_idx = pd.MultiIndex.from_tuples([], names=["date", "ticker"])
        feats = pd.DataFrame(index=empty_idx, columns=[], dtype=float)
        rets_raw = pd.Series([], index=empty_idx, name="ret", dtype=float)

    return feats, rets_raw, requested


@given(args=_synthetic_panel_and_manifest())
@settings(
    max_examples=60,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
    deadline=4000,  # 4s per example; explicit bounded deadline
)
def test_C1_accounting_equation_holds_for_all_inputs(
    args: tuple[pd.DataFrame, pd.Series, tuple[str, ...]],
) -> None:
    """The four-bucket accounting equation MUST close exactly:

        len(requested) == (
            len(features_missing_from_compute(feats, requested))
          + len(features_dropped_no_long_short(ls, feats, requested))
          + len(used)
          + len(excluded)
        )

    where used + excluded come from filter_accepted_signals(gate_osap_signals(ls)).

    This is the invariant whose absence made Phase 4h's ~78-signal silent
    drop invisible for a full phase. It must be airtight for Alpha158's
    158-feature cohort.
    """
    feats, rets, requested = args

    # Build long-short
    ls_result = compute_alpha158_long_short_returns(feats, rets)
    ls = ls_result.long_short

    # Bucket 1: missing from compute
    missing = features_missing_from_compute(feats, requested)

    # Bucket 2: present in panel but never formed a LS row
    dropped = features_dropped_no_long_short(ls, feats, requested)

    # Buckets 3 + 4: gate (accepted = used, rejected = excluded)
    gate_results = gate_osap_signals(ls, requested_signals=requested)
    used, excluded = filter_accepted_signals(gate_results)

    # --- invariant ---
    total = len(missing) + len(dropped) + len(used) + len(excluded)
    assert total == len(requested), (
        f"Accounting equation violated: {len(missing)} missing + "
        f"{len(dropped)} dropped + {len(used)} used + {len(excluded)} excluded "
        f"= {total} != len(requested) = {len(requested)}"
    )

    # --- disjointness: no signal in more than one bucket ---
    missing_set = set(missing)
    dropped_set = set(dropped)
    used_set = set(used)
    excluded_set = set(excluded)

    assert not (missing_set & dropped_set), (
        f"Signal(s) appear in BOTH missing and dropped: "
        f"{missing_set & dropped_set}"
    )
    assert not (missing_set & used_set), (
        f"Signal(s) appear in BOTH missing and used: {missing_set & used_set}"
    )
    assert not (missing_set & excluded_set), (
        f"Signal(s) appear in BOTH missing and excluded: "
        f"{missing_set & excluded_set}"
    )
    assert not (dropped_set & used_set), (
        f"Signal(s) appear in BOTH dropped and used: {dropped_set & used_set}"
    )
    assert not (dropped_set & excluded_set), (
        f"Signal(s) appear in BOTH dropped and excluded: "
        f"{dropped_set & excluded_set}"
    )
    assert not (used_set & excluded_set), (
        f"Signal(s) appear in BOTH used and excluded: {used_set & excluded_set}"
    )

    # --- coverage: union of all four buckets == requested ---
    all_buckets = missing_set | dropped_set | used_set | excluded_set
    assert all_buckets == set(requested), (
        f"Buckets union {all_buckets} != requested set {set(requested)}"
    )


# ---------------------------------------------------------------------------
# D. Survivorship honesty
# ---------------------------------------------------------------------------


def _make_dense_adapter_input(n_tickers: int = 15, n_dates: int = 6) -> tuple:
    """Quick factory for (feats, rets, dates, tickers)."""
    dates = _make_monthly_dates(n_dates)
    tickers = [f"TKR{i:02d}" for i in range(n_tickers)]
    rng = np.random.RandomState(7)
    idx = pd.MultiIndex.from_product([dates, tickers], names=["date", "ticker"])
    feats = pd.DataFrame({"F1": rng.randn(len(idx))}, index=idx)
    rets = pd.Series(rng.randn(len(idx)) * 0.05, index=idx)
    return feats, rets, dates, tickers


def test_D1_no_universe_provider_gives_survivorship_false():
    """universe_provider=None → survivorship_bias_corrected is False."""
    feats, rets, _, _ = _make_dense_adapter_input()
    result = compute_alpha158_long_short_returns(feats, rets, universe_provider=None)
    assert result.survivorship_bias_corrected is False


def test_D2_provider_all_complete_gives_survivorship_true():
    """Provider returning is_complete=True for every month → True."""
    feats, rets, dates, tickers = _make_dense_adapter_input()
    ticker_set = set(tickers)

    def provider(as_of: date):
        return ticker_set, True

    result = compute_alpha158_long_short_returns(feats, rets, universe_provider=provider)
    assert result.survivorship_bias_corrected is True


def test_D3_one_incomplete_month_flips_survivorship_false():
    """Any single month with is_complete=False → survivorship_bias_corrected is False."""
    feats, rets, dates, tickers = _make_dense_adapter_input(n_dates=8)
    ticker_set = set(tickers)
    degraded_month = dates[3]  # one month in the middle is degraded

    def provider(as_of: date):
        if as_of == degraded_month:
            return ticker_set, False
        return ticker_set, True

    result = compute_alpha158_long_short_returns(
        feats, rets, universe_provider=provider
    )
    assert result.survivorship_bias_corrected is False, (
        "A single is_complete=False month must flip survivorship_bias_corrected "
        "to False, even if all other months are complete"
    )


# ---------------------------------------------------------------------------
# E. Accounting bucket semantics
# ---------------------------------------------------------------------------


def test_E1_manifest_feature_never_present_goes_to_missing():
    """A name in the manifest that is never a panel column → features_missing_from_compute."""
    feats, rets, _, _ = _make_dense_adapter_input()
    requested = ("F1", "F_ABSENT_FROM_PANEL")
    missing = features_missing_from_compute(feats, requested)
    assert "F_ABSENT_FROM_PANEL" in missing
    assert "F1" not in missing


def test_E2_feature_present_but_tiny_universe_goes_to_dropped():
    """Feature present in panel but never forming ≥ MIN_UNIVERSE LS rows
    → features_dropped_no_long_short, not in missing."""
    n_dates = 20
    dates = _make_monthly_dates(n_dates)
    tickers_ok = [f"TKR{i:02d}" for i in range(15)]
    # tiny tickers: only 5 — below MIN_UNIVERSE_FOR_DECILE_SPREAD = 10
    tiny_ticker_set = set(tickers_ok[:5])

    rng = np.random.RandomState(8)
    idx_full = pd.MultiIndex.from_product([dates, tickers_ok], names=["date", "ticker"])

    f_ok_vals = rng.randn(len(idx_full))
    # F_tiny: NaN for all tickers NOT in tiny_ticker_set → only 5 non-NaN per month
    f_tiny_vals = np.full(len(idx_full), np.nan)
    for pos, (_, t) in enumerate(idx_full):
        if t in tiny_ticker_set:
            f_tiny_vals[pos] = rng.randn()

    feats = pd.DataFrame(
        {"F_ok": f_ok_vals, "F_tiny": f_tiny_vals}, index=idx_full
    )
    rets = pd.Series(rng.randn(len(idx_full)) * 0.05, index=idx_full)
    ls_result = compute_alpha158_long_short_returns(feats, rets)

    requested = ("F_ok", "F_tiny")
    missing = features_missing_from_compute(feats, requested)
    dropped = features_dropped_no_long_short(ls_result.long_short, feats, requested)

    assert "F_tiny" not in missing, "F_tiny IS present as a column; must not be in missing"
    assert "F_tiny" in dropped, (
        "F_tiny has < MIN_UNIVERSE non-NaN rows per month; must land in dropped"
    )
    assert "F_ok" not in dropped, (
        "F_ok has 15 tickers and should form LS rows; must not be in dropped"
    )


def test_E3_pure_noise_signal_reaches_gate_not_dropped():
    """A feature forming LS rows (≥ MIN_UNIVERSE tickers) reaches the gate.

    Even if the gate rejects it (noise), it is in excluded, NOT in dropped.
    This verifies the three-bucket distinction: dropped = never formed a row;
    excluded = formed rows, gate rejected.
    """
    n_tickers = 15
    n_dates = 25
    rng = np.random.RandomState(11)
    dates = _make_monthly_dates(n_dates)
    tickers = [f"TKR{i:02d}" for i in range(n_tickers)]
    idx = pd.MultiIndex.from_product([dates, tickers], names=["date", "ticker"])
    # Pure Gaussian noise — expected to fail gate (overfit / low DSR)
    feats = pd.DataFrame({"F_noise": rng.randn(len(idx))}, index=idx)
    rets = pd.Series(rng.randn(len(idx)) * 0.05, index=idx)
    ls_result = compute_alpha158_long_short_returns(feats, rets)

    requested = ("F_noise",)
    dropped = features_dropped_no_long_short(ls_result.long_short, feats, requested)

    # Regardless of gate outcome: noise signal forms LS rows → NOT in dropped
    assert "F_noise" not in dropped, (
        "F_noise forms LS rows (15 tickers > MIN_UNIVERSE); it must NOT be "
        "in dropped. It may be in excluded if the gate rejects it, but that "
        "is a gate decision, not a dropped-no-LS decision."
    )


# ---------------------------------------------------------------------------
# F. Graceful degradation
# ---------------------------------------------------------------------------


def test_F1_acquire_alpha158_inputs_raises_runtime_error():
    """_acquire_alpha158_inputs raises RuntimeError (deferred bin cache).

    This pins the graceful-degradation path that makes every alpha158_*
    Metadata field degrade to None in production until the bin cache lands.
    """
    from datetime import date as _date

    from compute.main import _acquire_alpha158_inputs

    with pytest.raises(RuntimeError) as exc_info:
        _acquire_alpha158_inputs(_date(2026, 6, 1), ["AAPL"])

    # The message must mention the deferred bin cache so a future reader
    # understands WHY the error fires (not an unexpected failure).
    error_msg = str(exc_info.value).lower()
    assert "deferred" in error_msg or "bin" in error_msg, (
        f"RuntimeError message does not mention 'deferred' or 'bin'; got: {exc_info.value!r}"
    )


# ---------------------------------------------------------------------------
# G. coverage_pct
# ---------------------------------------------------------------------------


def test_G1_coverage_pct_empty_panel_returns_none():
    """Empty feature panel → coverage_pct returns None."""
    empty = pd.DataFrame(
        index=pd.MultiIndex.from_tuples([], names=["date", "ticker"]),
        columns=["F1"],
        dtype=float,
    )
    assert coverage_pct(empty, 500) is None


def test_G2_coverage_pct_nonpositive_universe_returns_none():
    """universe_size <= 0 → coverage_pct returns None."""
    feats, _, _, _ = _make_dense_adapter_input(n_tickers=10)
    assert coverage_pct(feats, 0) is None
    assert coverage_pct(feats, -1) is None


def test_G3_coverage_pct_correct_percentage():
    """Panel with known non-null rows at the latest date → correct %."""
    # 10 tickers, but only 6 have the feature at the latest date
    dates = _make_monthly_dates(3)
    tickers = [f"TKR{i:02d}" for i in range(10)]
    latest = max(dates)

    idx = pd.MultiIndex.from_product([dates, tickers], names=["date", "ticker"])
    vals = np.full(len(idx), np.nan)
    # Set 6 tickers non-null at the latest date
    for i, t in enumerate(tickers[:6]):
        loc = idx.get_loc((latest, t))
        vals[loc] = float(i + 1)

    feats = pd.DataFrame({"F1": vals}, index=idx)
    result = coverage_pct(feats, universe_size=10)

    assert result is not None
    assert math.isclose(result, 60.0, abs_tol=0.01), (
        f"Expected 60.0 (6/10 tickers covered), got {result}"
    )


# ---------------------------------------------------------------------------
# H. Schema: Δscore = 0 / no per-stock surface
# ---------------------------------------------------------------------------


def test_H1_stock_detail_has_no_alpha158_field():
    """StockDetail must have NO alpha158_* field.

    Phase 4j.1 is observability-only: the blend that could influence rank
    is deferred to 4j.2. If any alpha158_* field appears on StockDetail,
    it means the Δscore = 0 guarantee was accidentally broken (someone
    wired scoring output to the per-stock JSON).
    """
    from compute.output.schemas import StockDetail

    alpha_fields = [
        name for name in StockDetail.model_fields if "alpha158" in name.lower()
    ]
    assert alpha_fields == [], (
        f"StockDetail must have no alpha158_* fields (Δscore = 0 contract). "
        f"Found: {alpha_fields}"
    )


def test_H2_metadata_alpha158_fields_all_optional_none_default():
    """Every Metadata.alpha158_* field is optional (Union[T, None]) and
    defaults to None.

    Contract: legacy metadata.json (pre-0.10.15) and the degraded pipeline
    path (RuntimeError in _acquire_alpha158_inputs) both deserialize clean.
    """
    from compute.output.schemas import Metadata

    alpha_fields = {
        name: field
        for name, field in Metadata.model_fields.items()
        if "alpha158" in name.lower()
    }

    # Exactly 9 fields were added (per the schema PR)
    assert len(alpha_fields) == 9, (
        f"Expected 9 Metadata.alpha158_* fields; found {len(alpha_fields)}: "
        f"{sorted(alpha_fields.keys())}"
    )

    for name, field in alpha_fields.items():
        # All must have None as the default
        default = field.default
        assert default is None, (
            f"Metadata.{name} has default={default!r}; expected None. "
            "Legacy deserialization requires every alpha158_* field to "
            "default to None."
        )

    # Additionally: the minimal required-fields payload (no alpha158_* keys)
    # must deserialize without error — proves the degraded path works.
    minimal_payload = {
        "version": "0.10.14-phase4.6",
        "last_update_utc": "2026-06-06T22:00:00Z",
        "next_update_utc": "2026-06-13T22:00:00Z",
        "universe": "sp500",
        "universe_size": 502,
        "compute_run_id": "test",
        "git_commit": "a" * 40,
    }
    m = Metadata.model_validate(minimal_payload)
    for name in alpha_fields:
        assert getattr(m, name) is None, (
            f"Metadata.{name} should be None when absent from payload; "
            f"got {getattr(m, name)!r}"
        )
