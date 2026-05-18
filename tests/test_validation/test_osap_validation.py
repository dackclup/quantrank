"""Tests for ``compute/validation/osap_validation.py`` (Phase 4h commit 4).

Anchors the PBO/DSR hard-gate behavior + the rolling-12m Spearman IC
observability metric. Coverage focus:

- Bailey 2014 cohort framing (``n_trials = cohort_size``) holds
  end-to-end through :func:`factor_passes_gates`.
- Asymmetric NaN policy (per-signal ``dropna`` + cohort
  ``fillna(0.0)``) is locked in regression — test #13 fails if a
  future maintainer accidentally reverts to ``dropna(how='any')``.
- Rejection-reason classification is exact (``insufficient_data`` /
  ``high_pbo`` / ``low_dsr`` / ``gate_failed``) so commit 5's
  metadata writer can group correctly.
- Rolling-IC pure-pandas Spearman matches a hand-computed reference
  and gracefully degrades on insufficient history.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from compute.validation.osap_validation import (
    MIN_OBS_PER_SIGNAL,
    ROLLING_IC_WINDOW_MONTHS,
    GateResult,
    compute_rolling_ic_12m,
    filter_accepted_signals,
    gate_osap_signals,
)


def _long_format(
    wide: pd.DataFrame,
) -> pd.DataFrame:
    """Helper: wide (date × signal) → long (signalname, date, ls_return).

    Mirrors commit 2's ``compute_long_short_returns`` output. Drops
    NaN cells (commit 2 does the same — long format never carries
    explicit NaN rows).
    """
    long = (
        wide.rename_axis(index="date", columns="signalname")
        .stack()
        .rename("ls_return")
        .reset_index()
    )
    return long.dropna(subset=["ls_return"]).astype({"signalname": str})


def _make_noise_cohort(
    n_dates: int = 64,
    n_signals: int = 10,
    *,
    seed: int = 42,
    start: str = "2020-01-31",
) -> pd.DataFrame:
    """Synthetic monthly long-short returns — independent noise per signal.

    Matches the synthetic-fixture pattern at
    ``tests/test_validation/test_pbo_dsr.py:63`` (deterministic seed +
    Normal(0, 0.05) monthly returns).
    """
    rng = np.random.default_rng(seed=seed)
    dates = pd.date_range(start=start, periods=n_dates, freq="ME")
    data = rng.normal(0.0, 0.05, size=(n_dates, n_signals))
    cols = [f"NoiseSig{i:02d}" for i in range(n_signals)]
    wide = pd.DataFrame(data, index=dates, columns=cols)
    return _long_format(wide)


# ---------------------------------------------------------------------------
# gate_osap_signals
# ---------------------------------------------------------------------------


def test_gate_osap_signals_random_noise_yields_high_pbo() -> None:
    """Pure-noise cohort → no signals accepted (Bailey 2014 invariant).

    Independent random strategies have no persistent signal, so PBO
    clusters near 0.5+ AND deflated Sharpe (corrected for n_trials
    multiple-testing) lands at or below zero for typical samples. The
    gate's hard PBO ≤ 0.5 conjunction-with DSR > 0 should reject every
    signal — categorized as ``'high_pbo'`` (PBO-only fail),
    ``'low_dsr'`` (DSR-only fail), or ``'gate_failed'`` (both fail)
    depending on which side wins for that draw.
    """
    df = _make_noise_cohort(n_dates=64, n_signals=10, seed=42)

    results = gate_osap_signals(df)

    assert len(results) == 10
    assert all(isinstance(r, GateResult) for r in results.values())

    # Bailey 2014 invariant: pure noise → zero acceptances.
    accepted = [s for s, r in results.items() if r.accepted]
    assert accepted == []

    # All rejections cite one of the three real-gate reasons (no
    # short-circuits — every signal got a real PBO/DSR computation).
    reasons = {r.rejection_reason for r in results.values()}
    assert reasons.issubset({"high_pbo", "low_dsr", "gate_failed"})
    assert "insufficient_data" not in reasons

    # Sanity: every result has populated pbo + dsr + sharpe floats.
    for r in results.values():
        assert r.pbo is not None and 0.0 <= r.pbo <= 1.0
        assert r.dsr is not None
        assert r.sharpe is not None
        assert r.n_observations == 64


def test_gate_osap_signals_low_sharpe_signal_rejected_for_dsr() -> None:
    """Near-zero-mean signal in a strong cohort → fails DSR."""
    rng = np.random.default_rng(seed=7)
    dates = pd.date_range(start="2020-01-31", periods=64, freq="ME")
    # 9 random signals at modest scale + 1 near-zero signal.
    data = rng.normal(0.0, 0.05, size=(64, 9))
    near_zero = rng.normal(0.0, 1e-4, size=(64, 1))
    wide = pd.DataFrame(
        np.hstack([data, near_zero]),
        index=dates,
        columns=[f"Sig{i:02d}" for i in range(9)] + ["DeadSig"],
    )
    df = _long_format(wide)

    results = gate_osap_signals(df)

    dead = results["DeadSig"]
    # Near-zero σ → DSR ≈ 0 → fails DSR_VETO_THRESHOLD (= 0.0, strict >).
    assert dead.accepted is False
    assert dead.rejection_reason in ("low_dsr", "gate_failed")
    assert dead.dsr is not None and dead.dsr <= 0.0


def test_gate_osap_signals_strong_signal_accepted() -> None:
    """Monotone-drift signal beats noisy cohort → accepted with float metrics."""
    rng = np.random.default_rng(seed=11)
    dates = pd.date_range(start="2015-01-31", periods=120, freq="ME")
    # 9 noise + 1 strong drift signal with very high Sharpe and stable OOS rank.
    noise = rng.normal(0.0, 0.05, size=(120, 9))
    strong = np.full((120, 1), 0.03) + rng.normal(0.0, 0.005, size=(120, 1))
    wide = pd.DataFrame(
        np.hstack([noise, strong]),
        index=dates,
        columns=[f"Noise{i:02d}" for i in range(9)] + ["StrongSig"],
    )
    df = _long_format(wide)

    results = gate_osap_signals(df)

    strong_result = results["StrongSig"]
    assert strong_result.accepted is True
    assert strong_result.rejection_reason is None
    assert strong_result.pbo is not None and strong_result.pbo <= 0.5
    assert strong_result.dsr is not None and strong_result.dsr > 0.0
    assert strong_result.sharpe is not None and strong_result.sharpe > 0.0


def test_gate_osap_signals_insufficient_data() -> None:
    """Cohort with < ``MIN_OBS_PER_SIGNAL`` rows → all signals rejected
    with reason ``insufficient_data`` (cohort precondition fails)."""
    rng = np.random.default_rng(seed=3)
    dates = pd.date_range(start="2024-01-31", periods=10, freq="ME")
    wide = pd.DataFrame(
        rng.normal(0.0, 0.05, size=(10, 4)),
        index=dates,
        columns=["A", "B", "C", "D"],
    )
    df = _long_format(wide)

    results = gate_osap_signals(df)

    assert len(results) == 4
    for r in results.values():
        assert r.accepted is False
        assert r.rejection_reason == "insufficient_data"
        assert r.pbo is None
        assert r.dsr is None
        assert r.sharpe is None
        assert r.n_observations == 10


def test_gate_osap_signals_requested_signals_filter() -> None:
    """``requested_signals`` subsets the cohort before gating — result
    has only those keys."""
    df = _make_noise_cohort(n_dates=48, n_signals=5, seed=42)
    # Input contains NoiseSig00..NoiseSig04. Request a 3-signal subset.
    requested = ("NoiseSig00", "NoiseSig02", "NoiseSig04")

    results = gate_osap_signals(df, requested_signals=requested)

    assert set(results.keys()) == set(requested)
    # All three got a real PBO/DSR run (cohort size 3 ≥ 2, dates ≥ 16).
    for r in results.values():
        assert r.rejection_reason != "insufficient_data"


def test_gate_osap_signals_requested_none_uses_all_signals_in_df() -> None:
    """``requested_signals=None`` (default) → result covers every
    unique signalname in the input."""
    df = _make_noise_cohort(n_dates=32, n_signals=6, seed=1)

    results = gate_osap_signals(df, requested_signals=None)

    assert set(results.keys()) == set(df["signalname"].unique())


def test_gate_osap_signals_empty_input_returns_empty_dict() -> None:
    """Empty long-format DF → ``{}``, no crash."""
    df = pd.DataFrame(columns=["signalname", "date", "ls_return"])
    results = gate_osap_signals(df)
    assert results == {}


def test_gate_osap_signals_single_signal_cohort_rejects_with_insufficient_data() -> None:
    """Cohort with 1 column → PBO precondition (``cohort_size < 2``)
    short-circuits all signals to insufficient_data."""
    rng = np.random.default_rng(seed=5)
    dates = pd.date_range(start="2020-01-31", periods=64, freq="ME")
    wide = pd.DataFrame(
        rng.normal(0.0, 0.05, size=(64, 1)),
        index=dates,
        columns=["LonelySig"],
    )
    df = _long_format(wide)

    results = gate_osap_signals(df)

    assert results["LonelySig"].accepted is False
    assert results["LonelySig"].rejection_reason == "insufficient_data"
    assert results["LonelySig"].pbo is None


def test_compute_rolling_ic_12m_known_signal() -> None:
    """Hand-constructed lag-1-correlated series → Spearman ≈ expected."""
    # Strictly monotone increasing series — every (t, t+1) pair has rank
    # correlation = 1.0 (perfectly preserved order under shift).
    dates = pd.date_range(start="2023-01-31", periods=15, freq="ME")
    series = pd.DataFrame(
        {
            "signalname": ["S"] * 15,
            "date": dates,
            "ls_return": np.arange(15, dtype=float) * 0.01,
        }
    )

    ic = compute_rolling_ic_12m(series, "S")

    assert ic is not None
    assert ic == pytest.approx(1.0, abs=1e-9)


def test_compute_rolling_ic_12m_insufficient_history() -> None:
    """Signal with < 13 monthly observations → ``None``."""
    dates = pd.date_range(start="2024-01-31", periods=8, freq="ME")
    df = pd.DataFrame(
        {
            "signalname": ["S"] * 8,
            "date": dates,
            "ls_return": np.linspace(0.01, 0.08, 8),
        }
    )

    assert compute_rolling_ic_12m(df, "S") is None


def test_compute_rolling_ic_12m_nan_safe_with_gaps() -> None:
    """NaN ``ls_return`` rows OUTSIDE the rolling-12m tail window are
    pruned by ``tail(13)`` and do not poison the IC.

    Production long-format DataFrames never carry explicit NaN rows
    (commit 2's ``compute_long_short_returns`` drops them at long
    conversion), but pre-window NaN sourced from upstream test fixtures
    or future refactors must not propagate into the Spearman result.
    """
    # 20 rows total. The last 13 (tail window) are strictly monotone
    # with no NaN. NaN are punched into older history.
    dates = pd.date_range(start="2022-06-30", periods=20, freq="ME")
    rets = np.arange(20, dtype=float) * 0.01
    rets[0] = np.nan
    rets[3] = np.nan
    rets[5] = np.nan  # All three NaN sit in indices 0..6 (pruned by tail(13)).
    df = pd.DataFrame(
        {
            "signalname": ["S"] * 20,
            "date": dates,
            "ls_return": rets,
        }
    )

    ic = compute_rolling_ic_12m(df, "S")

    # Strictly monotone tail-13 → Spearman should be exactly 1.0.
    assert ic is not None
    assert math.isfinite(ic)
    assert ic == pytest.approx(1.0, abs=1e-9)


def test_filter_accepted_signals_splits_into_sorted_lists() -> None:
    """Mixed gate_results → alphabetically sorted accepted vs excluded;
    union equals the full key set."""
    gate_results = {
        "C_pass": GateResult(True, 0.3, 1.5, 1.2, 60, None),
        "A_fail_pbo": GateResult(False, 0.7, 1.2, 1.0, 60, "high_pbo"),
        "B_pass": GateResult(True, 0.4, 2.0, 1.6, 60, None),
        "Z_insufficient": GateResult(
            False, None, None, None, 10, "insufficient_data"
        ),
        "Y_fail_dsr": GateResult(False, 0.3, -0.5, 0.2, 60, "low_dsr"),
    }

    accepted, excluded = filter_accepted_signals(gate_results)

    assert accepted == ["B_pass", "C_pass"]
    assert excluded == ["A_fail_pbo", "Y_fail_dsr", "Z_insufficient"]
    # Round-trip: union of the two lists equals all gate-result keys.
    assert set(accepted + excluded) == set(gate_results.keys())


def test_gate_osap_signals_sparse_cohort_zero_filled_not_decimated() -> None:
    """Lock the §NaN policy: sparse coverage signals stay in the cohort
    via ``fillna(0.0)`` rather than being dropped by ``dropna(how='any')``.

    Regression guard — if a future maintainer reverts the cohort
    fillna(0.0) to ``dropna(how='any')``, the cohort matrix would
    collapse to the intersection (8 rows after sparse signals drop 16
    of 64 months each), tripping the cohort-precondition row count and
    cascading every signal to ``insufficient_data``.
    """
    rng = np.random.default_rng(seed=23)
    dates = pd.date_range(start="2020-01-31", periods=64, freq="ME")
    n_signals = 10
    data = rng.normal(0.0, 0.05, size=(64, n_signals))
    cols = [f"Sig{i:02d}" for i in range(n_signals)]
    wide = pd.DataFrame(data, index=dates, columns=cols)

    # Punch sparse-coverage NaN holes into 3 signals (~25% of rows
    # missing each, but DIFFERENT rows per signal — so a
    # dropna(how='any') intersection would decimate hard).
    sparse_signals = ["Sig00", "Sig03", "Sig07"]
    for offset, sig in enumerate(sparse_signals):
        nan_rows = np.arange(offset, 64, 4)  # 16 NaN rows, offset per signal
        wide.loc[wide.index[nan_rows], sig] = np.nan

    df_long = _long_format(wide)

    results = gate_osap_signals(df_long)

    # All 10 signals received a GateResult (not collapsed by dropna).
    assert set(results.keys()) == set(cols)

    # The 3 sparse signals each have ≥ 48 obs (well above MIN_OBS_PER_SIGNAL
    # = 16) so none short-circuited on per-signal insufficient_data.
    # Critically: NO signal should have rejection_reason='insufficient_data'
    # — that would mean the cohort precondition failed, which is exactly
    # what dropna(how='any') would trigger.
    insufficient = [
        s for s, r in results.items() if r.rejection_reason == "insufficient_data"
    ]
    assert insufficient == [], (
        f"Cohort decimation detected — signals {insufficient} short-"
        f"circuited on insufficient_data despite having enough per-signal "
        f"obs. Did the cohort fillna(0.0) get reverted to dropna(how='any')?"
    )

    # Every signal has a populated n_observations from the actual
    # factor_passes_gates call (not the precheck-only count).
    for sig, r in results.items():
        assert r.pbo is not None, f"{sig} missing pbo — short-circuited?"
        assert r.dsr is not None, f"{sig} missing dsr — short-circuited?"


def test_module_load_constants_sourced_from_pbo_dsr() -> None:
    """Smoke test — module-level constants match pbo_dsr defaults so
    a downstream caller using the wrapper's defaults gets the canonical
    Phase 4 PBO ≤ 0.5 / DSR > 0 gate."""
    from compute.validation.pbo_dsr import DEFAULT_N_PARTITIONS as PD_NP

    assert MIN_OBS_PER_SIGNAL == PD_NP  # 16
    assert ROLLING_IC_WINDOW_MONTHS == 12
