"""Unit tests for compute.orchestrator.osap (PR #259-R6).

All tests are offline/synthetic. ``run_osap_pipeline`` performs its
OSAP-library imports (``compute.features.osap_replicate``,
``compute.ingest.osap``, ``compute.scoring.osap_blend``,
``compute.validation.osap_validation``) INSIDE the try block (the
Phase-4a deferred-import pattern — ``openassetpricing`` only ships via
the ``.[factors]`` optional extra). A deferred ``from X import Y``
re-reads the current ``X.Y`` attribute at call time, so monkeypatching
the SOURCE module's function (e.g. ``compute.ingest.osap.fetch_osap_returns``)
is picked up correctly — no network, no real OSAP/qlib.

Coverage
--------
A — ``run_osap_pipeline`` happy path
    A1  Returns an ``OsapPipelineResult`` NamedTuple with 10 fields.
    A2  osap_signals_used / osap_excluded_signals populated from
        filter_accepted_signals's stubbed return.
    A3  osap_signals_ic_12m populated per accepted signal from
        compute_rolling_ic_12m's stubbed return.
    A4  osap_signal_map + osap_signals_coverage_pct populated when
        osap_signals_used is non-empty.
    A5  composite_osap_adjusted is the Series returned by the stubbed
        apply_osap_blend, called with (composite, osap_aggregate).
    A6  osap_signals_missing_from_dataset is the manifest-vs-dataset
        set diff (config.OSAP_SIGNALS_100 - signals_in_dataframe(...)).
    A7  osap_gate_diagnostics is keyed by signal name with an
        OsapGateDiagnostic per GateResult.
    A8  osap_signals_dropped_no_long_short_list restricted to the
        OSAP_SIGNALS_100 manifest.
    A9  osap_wall_clock_seconds is a non-negative float (not None) on
        the happy path.

B — ``run_osap_pipeline`` zero-accepted-signals path
    B1  When filter_accepted_signals returns ([], [...]), osap_signal_map
        / osap_signals_coverage_pct stay empty and
        composite_osap_adjusted stays the pd.Series(dtype=float) init
        (apply_osap_blend never called).
    B2  A warning is logged mentioning "0 signals".

C — ``run_osap_pipeline`` outer-except path
    C1  When fetch_osap_returns raises, ALL 10 outputs reset to their
        empty/None/pd.Series(dtype=float) values.
    C2  outer-except logs a WARNING containing "OSAP pipeline failed".
    C3  An ImportError from a deferred import (library not installed)
        is caught the same way as any other exception — same reset.

D — return-shape / identity guards
    D1  osap_wall_clock_seconds is None on the outer-except path.
    D2  composite_osap_adjusted is a pd.Series in every path (never a
        bare dict/list).
"""

from __future__ import annotations

import logging
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from compute import config
from compute.orchestrator.osap import OsapPipelineResult, run_osap_pipeline
from compute.validation.osap_validation import GateResult

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

_ASOF = date(2026, 6, 30)


def _make_pillar_df(*tickers: str) -> pd.DataFrame:
    """Minimal pillar-score DataFrame indexed by ticker (only .index is
    read by run_osap_pipeline)."""
    return pd.DataFrame(index=list(tickers))


def _make_composite(values: dict[str, float]) -> pd.Series:
    return pd.Series(values, dtype=float, name="composite_score")


def _make_gate_result(
    *,
    accepted: bool,
    pbo: float | None = 0.3,
    dsr: float | None = 0.8,
    sharpe: float | None = 1.2,
    n_observations: int = 24,
    rejection_reason: str | None = None,
) -> GateResult:
    return GateResult(
        accepted=accepted,
        pbo=pbo,
        dsr=dsr,
        sharpe=sharpe,
        n_observations=n_observations,
        rejection_reason=rejection_reason,
    )


class _OsapStubs:
    """Bundles the patch.multiple() targets for every deferred-import
    OSAP function, across all 4 source modules. Each field is a
    callable/return-value the caller can override per-test."""

    def __init__(
        self,
        *,
        osap_returns_raw: pd.DataFrame | None = None,
        present_signals: frozenset[str] | None = None,
        dropped_no_ls: list[str] | None = None,
        long_short: pd.DataFrame | None = None,
        gate_results: dict[str, GateResult] | None = None,
        accepted_excluded: tuple[list[str], list[str]] | None = None,
        rolling_ic: float | None = 0.05,
        signal_map: dict[str, dict[str, float] | None] | None = None,
        coverage: dict[str, float] | None = None,
        aggregate: pd.Series | None = None,
        blended: pd.Series | None = None,
        raise_at: str | None = None,
        raise_exc: type[Exception] = RuntimeError,
    ):
        self.osap_returns_raw = (
            osap_returns_raw
            if osap_returns_raw is not None
            # Default carries a `signalname` column so the
            # `osap_returns_raw["signalname"].isin(osap_signals_used)`
            # filter at the real block's line "Per-ticker signal map"
            # step never KeyErrors when a test accepts a signal without
            # supplying its own osap_returns_raw.
            else pd.DataFrame(columns=["signalname", "date", "ls_return"])
        )
        self.present_signals = (
            present_signals if present_signals is not None else frozenset()
        )
        self.dropped_no_ls = dropped_no_ls if dropped_no_ls is not None else []
        self.long_short = long_short if long_short is not None else pd.DataFrame(
            columns=["signalname", "date", "ls_return"]
        )
        self.gate_results = gate_results if gate_results is not None else {}
        self.accepted_excluded = accepted_excluded if accepted_excluded is not None else (
            [],
            [],
        )
        self.rolling_ic = rolling_ic
        self.signal_map = signal_map if signal_map is not None else {}
        self.coverage = coverage if coverage is not None else {}
        self.aggregate = aggregate if aggregate is not None else pd.Series(dtype=float)
        self.blended = blended if blended is not None else pd.Series(dtype=float)
        self.raise_at = raise_at
        self.raise_exc = raise_exc

    def _maybe_raise(self, name: str):
        if self.raise_at == name:
            raise self.raise_exc(f"simulated failure at {name}")

    def fetch_osap_returns(self, *, signals, as_of):
        self._maybe_raise("fetch_osap_returns")
        return self.osap_returns_raw

    def signals_in_dataframe(self, df):
        self._maybe_raise("signals_in_dataframe")
        return self.present_signals

    def signals_dropped_no_long_short(self, df):
        self._maybe_raise("signals_dropped_no_long_short")
        return self.dropped_no_ls

    def compute_long_short_returns(self, returns):
        self._maybe_raise("compute_long_short_returns")
        return self.long_short

    def gate_osap_signals(self, long_short_returns, requested_signals=None):
        self._maybe_raise("gate_osap_signals")
        return self.gate_results

    def filter_accepted_signals(self, gate_results):
        self._maybe_raise("filter_accepted_signals")
        return self.accepted_excluded

    def compute_rolling_ic_12m(self, long_short_returns, signalname):
        self._maybe_raise("compute_rolling_ic_12m")
        return self.rolling_ic

    def compute_osap_signals(self, returns, tickers, as_of, requested_signals=None):
        self._maybe_raise("compute_osap_signals")
        return self.signal_map

    def coverage_by_signal(self, signal_map):
        self._maybe_raise("coverage_by_signal")
        return self.coverage

    def aggregate_osap_signals(self, signal_map):
        self._maybe_raise("aggregate_osap_signals")
        return self.aggregate

    def apply_osap_blend(self, composite_scores, osap_signal_aggregate):
        self._maybe_raise("apply_osap_blend")
        return self.blended


def _patch_osap(stubs: _OsapStubs):
    """Context manager patching every deferred-import OSAP function at
    its SOURCE module location (picked up by the deferred `from X import
    Y` inside run_osap_pipeline's try block)."""
    return (
        patch.multiple(
            "compute.features.osap_replicate",
            compute_long_short_returns=stubs.compute_long_short_returns,
            compute_osap_signals=stubs.compute_osap_signals,
            coverage_by_signal=stubs.coverage_by_signal,
            signals_dropped_no_long_short=stubs.signals_dropped_no_long_short,
            signals_in_dataframe=stubs.signals_in_dataframe,
        ),
        patch("compute.ingest.osap.fetch_osap_returns", stubs.fetch_osap_returns),
        patch.multiple(
            "compute.scoring.osap_blend",
            aggregate_osap_signals=stubs.aggregate_osap_signals,
            apply_osap_blend=stubs.apply_osap_blend,
        ),
        patch.multiple(
            "compute.validation.osap_validation",
            compute_rolling_ic_12m=stubs.compute_rolling_ic_12m,
            filter_accepted_signals=stubs.filter_accepted_signals,
            gate_osap_signals=stubs.gate_osap_signals,
        ),
    )


class _MultiPatch:
    """Combine several patch/patch.multiple context managers into one
    `with` target (simple ExitStack-lite for readability at call sites)."""

    def __init__(self, patchers):
        self._patchers = patchers

    def __enter__(self):
        for p in self._patchers:
            p.__enter__()
        return self

    def __exit__(self, *exc_info):
        for p in reversed(self._patchers):
            p.__exit__(*exc_info)


def _apply(stubs: _OsapStubs) -> _MultiPatch:
    return _MultiPatch(_patch_osap(stubs))


# ---------------------------------------------------------------------------
# Section A: run_osap_pipeline happy path
# ---------------------------------------------------------------------------


def test_A1_returns_namedtuple_with_ten_fields():
    """run_osap_pipeline returns an OsapPipelineResult with 10 fields."""
    stubs = _OsapStubs()
    with _apply(stubs):
        result = run_osap_pipeline(
            _make_pillar_df("AAPL"), _make_composite({"AAPL": 50.0}), _ASOF
        )

    assert isinstance(result, OsapPipelineResult)
    assert isinstance(result, tuple)
    assert len(result) == 10


def test_A2_accepted_excluded_signals_populated(caplog):
    """osap_signals_used / osap_excluded_signals reflect
    filter_accepted_signals's stubbed return."""
    gate_results = {
        "sig_a": _make_gate_result(accepted=True),
        "sig_b": _make_gate_result(
            accepted=False, pbo=0.9, dsr=None, rejection_reason="high_pbo"
        ),
    }
    stubs = _OsapStubs(
        gate_results=gate_results,
        accepted_excluded=(["sig_a"], ["sig_b"]),
        signal_map={"AAPL": {"sig_a": 0.5}},
        coverage={"sig_a": 100.0},
        aggregate=pd.Series({"AAPL": 60.0}),
        blended=pd.Series({"AAPL": 55.0}),
    )
    with _apply(stubs):
        result = run_osap_pipeline(
            _make_pillar_df("AAPL"), _make_composite({"AAPL": 50.0}), _ASOF
        )

    assert result.osap_signals_used == ["sig_a"]
    assert result.osap_excluded_signals == ["sig_b"]


def test_A3_ic_12m_populated_per_accepted_signal():
    """osap_signals_ic_12m gets an entry per accepted signal from
    compute_rolling_ic_12m's stubbed return, rounded to 4 dp."""
    gate_results = {"sig_a": _make_gate_result(accepted=True)}
    stubs = _OsapStubs(
        gate_results=gate_results,
        accepted_excluded=(["sig_a"], []),
        rolling_ic=0.123456,
        signal_map={"AAPL": {"sig_a": 0.5}},
        coverage={"sig_a": 100.0},
        aggregate=pd.Series({"AAPL": 60.0}),
        blended=pd.Series({"AAPL": 55.0}),
    )
    with _apply(stubs):
        result = run_osap_pipeline(
            _make_pillar_df("AAPL"), _make_composite({"AAPL": 50.0}), _ASOF
        )

    assert result.osap_signals_ic_12m == {"sig_a": 0.1235}


def test_A3b_ic_12m_skips_none_values():
    """A signal whose rolling IC is None is NOT added to
    osap_signals_ic_12m (matches the `if ic is not None` guard)."""
    gate_results = {"sig_a": _make_gate_result(accepted=True)}
    stubs = _OsapStubs(
        gate_results=gate_results,
        accepted_excluded=(["sig_a"], []),
        rolling_ic=None,
        signal_map={"AAPL": {"sig_a": 0.5}},
        coverage={"sig_a": 100.0},
        aggregate=pd.Series({"AAPL": 60.0}),
        blended=pd.Series({"AAPL": 55.0}),
    )
    with _apply(stubs):
        result = run_osap_pipeline(
            _make_pillar_df("AAPL"), _make_composite({"AAPL": 50.0}), _ASOF
        )

    assert result.osap_signals_ic_12m == {}


def test_A4_signal_map_and_coverage_populated_when_signals_used():
    """osap_signal_map + osap_signals_coverage_pct populated when
    osap_signals_used is non-empty."""
    gate_results = {"sig_a": _make_gate_result(accepted=True)}
    signal_map = {"AAPL": {"sig_a": 0.7}, "MSFT": None}
    stubs = _OsapStubs(
        gate_results=gate_results,
        accepted_excluded=(["sig_a"], []),
        signal_map=signal_map,
        coverage={"sig_a": 50.001},
        aggregate=pd.Series({"AAPL": 60.0, "MSFT": 40.0}),
        blended=pd.Series({"AAPL": 55.0, "MSFT": 45.0}),
    )
    with _apply(stubs):
        result = run_osap_pipeline(
            _make_pillar_df("AAPL", "MSFT"),
            _make_composite({"AAPL": 50.0, "MSFT": 50.0}),
            _ASOF,
        )

    assert result.osap_signal_map == signal_map
    assert result.osap_signals_coverage_pct == {"sig_a": 50.0}


def test_A5_composite_osap_adjusted_is_blended_result():
    """composite_osap_adjusted is exactly the Series returned by the
    stubbed apply_osap_blend."""
    gate_results = {"sig_a": _make_gate_result(accepted=True)}
    expected_blend = pd.Series({"AAPL": 42.5})
    stubs = _OsapStubs(
        gate_results=gate_results,
        accepted_excluded=(["sig_a"], []),
        signal_map={"AAPL": {"sig_a": 0.7}},
        coverage={"sig_a": 100.0},
        aggregate=pd.Series({"AAPL": 60.0}),
        blended=expected_blend,
    )
    with _apply(stubs):
        result = run_osap_pipeline(
            _make_pillar_df("AAPL"), _make_composite({"AAPL": 50.0}), _ASOF
        )

    pd.testing.assert_series_equal(result.composite_osap_adjusted, expected_blend)


def test_A6_signals_missing_from_dataset_is_manifest_minus_present():
    """osap_signals_missing_from_dataset = OSAP_SIGNALS_100 - present_signals,
    sorted."""
    manifest = set(config.OSAP_SIGNALS_100)
    # Pretend everything except the first two manifest signals is present.
    sample = sorted(manifest)[:2]
    present = frozenset(manifest - set(sample))
    stubs = _OsapStubs(present_signals=present)
    with _apply(stubs):
        result = run_osap_pipeline(
            _make_pillar_df("AAPL"), _make_composite({"AAPL": 50.0}), _ASOF
        )

    assert result.osap_signals_missing_from_dataset == sorted(sample)


def test_A7_gate_diagnostics_keyed_by_signal():
    """osap_gate_diagnostics carries one OsapGateDiagnostic per
    GateResult, preserving pbo/dsr/sharpe/rejection_reason."""
    gate_results = {
        "sig_a": _make_gate_result(accepted=True, pbo=0.2, dsr=1.1, sharpe=0.9),
        "sig_b": _make_gate_result(
            accepted=False, pbo=0.95, dsr=None, sharpe=None, rejection_reason="high_pbo"
        ),
    }
    stubs = _OsapStubs(
        gate_results=gate_results,
        accepted_excluded=(["sig_a"], ["sig_b"]),
        signal_map={"AAPL": {"sig_a": 0.5}},
        coverage={"sig_a": 100.0},
        aggregate=pd.Series({"AAPL": 60.0}),
        blended=pd.Series({"AAPL": 55.0}),
    )
    with _apply(stubs):
        result = run_osap_pipeline(
            _make_pillar_df("AAPL"), _make_composite({"AAPL": 50.0}), _ASOF
        )

    assert set(result.osap_gate_diagnostics.keys()) == {"sig_a", "sig_b"}
    assert result.osap_gate_diagnostics["sig_a"].pbo == 0.2
    assert result.osap_gate_diagnostics["sig_a"].rejection_reason is None
    assert result.osap_gate_diagnostics["sig_b"].rejection_reason == "high_pbo"


def test_A8_dropped_no_long_short_restricted_to_manifest():
    """osap_signals_dropped_no_long_short_list only includes entries
    that are also in config.OSAP_SIGNALS_100."""
    manifest_sample = sorted(config.OSAP_SIGNALS_100)[:1]
    stubs = _OsapStubs(
        dropped_no_ls=[*manifest_sample, "not_in_manifest_signal"]
    )
    with _apply(stubs):
        result = run_osap_pipeline(
            _make_pillar_df("AAPL"), _make_composite({"AAPL": 50.0}), _ASOF
        )

    assert result.osap_signals_dropped_no_long_short_list == manifest_sample
    assert "not_in_manifest_signal" not in result.osap_signals_dropped_no_long_short_list


def test_A9_wall_clock_is_nonnegative_float_on_happy_path():
    """osap_wall_clock_seconds is a float (not None) on the happy path."""
    stubs = _OsapStubs()
    with _apply(stubs):
        result = run_osap_pipeline(
            _make_pillar_df("AAPL"), _make_composite({"AAPL": 50.0}), _ASOF
        )

    assert isinstance(result.osap_wall_clock_seconds, float)
    assert result.osap_wall_clock_seconds >= 0.0


# ---------------------------------------------------------------------------
# Section B: run_osap_pipeline zero-accepted-signals path
# ---------------------------------------------------------------------------


def test_B1_zero_accepted_signals_skips_map_and_blend():
    """When filter_accepted_signals returns no accepted signals,
    osap_signal_map / osap_signals_coverage_pct stay empty and
    composite_osap_adjusted stays the init pd.Series(dtype=float)
    (apply_osap_blend is never invoked)."""
    gate_results = {
        "sig_a": _make_gate_result(
            accepted=False, pbo=0.9, dsr=None, rejection_reason="high_pbo"
        )
    }
    apply_blend_called = []
    stubs = _OsapStubs(
        gate_results=gate_results,
        accepted_excluded=([], ["sig_a"]),
    )
    # Wrap apply_osap_blend to detect a call (should never happen).
    original_apply = stubs.apply_osap_blend

    def _tracking_apply(*args, **kwargs):
        apply_blend_called.append(True)
        return original_apply(*args, **kwargs)

    stubs.apply_osap_blend = _tracking_apply

    with _apply(stubs):
        result = run_osap_pipeline(
            _make_pillar_df("AAPL"), _make_composite({"AAPL": 50.0}), _ASOF
        )

    assert result.osap_signal_map == {}
    assert result.osap_signals_coverage_pct == {}
    assert result.composite_osap_adjusted.empty
    assert apply_blend_called == []


def test_B2_zero_accepted_signals_logs_warning(caplog):
    """The zero-accepted-signals branch logs a WARNING mentioning
    '0 signals'."""
    gate_results = {
        "sig_a": _make_gate_result(
            accepted=False, pbo=0.9, dsr=None, rejection_reason="high_pbo"
        )
    }
    stubs = _OsapStubs(
        gate_results=gate_results,
        accepted_excluded=([], ["sig_a"]),
    )
    with caplog.at_level(logging.WARNING, logger="compute.orchestrator.osap"):
        with _apply(stubs):
            run_osap_pipeline(
                _make_pillar_df("AAPL"), _make_composite({"AAPL": 50.0}), _ASOF
            )

    assert any("0 signals" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Section C: run_osap_pipeline outer-except path
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raise_at",
    [
        "fetch_osap_returns",
        "signals_in_dataframe",
        "compute_long_short_returns",
        "gate_osap_signals",
        "filter_accepted_signals",
    ],
)
def test_C1_exception_anywhere_in_try_resets_all_ten_outputs(raise_at):
    """Whatever step raises inside the try block, ALL 10 outputs reset
    to their empty/None/pd.Series(dtype=float) values."""
    stubs = _OsapStubs(raise_at=raise_at)
    with _apply(stubs):
        result = run_osap_pipeline(
            _make_pillar_df("AAPL"), _make_composite({"AAPL": 50.0}), _ASOF
        )

    assert result.osap_signals_used == []
    assert result.osap_excluded_signals == []
    assert result.osap_signals_ic_12m == {}
    assert result.osap_signal_map == {}
    assert result.osap_signals_coverage_pct == {}
    assert isinstance(result.composite_osap_adjusted, pd.Series)
    assert result.composite_osap_adjusted.empty
    assert result.osap_signals_missing_from_dataset == []
    assert result.osap_gate_diagnostics == {}
    assert result.osap_signals_dropped_no_long_short_list == []
    assert result.osap_wall_clock_seconds is None


def test_C2_outer_except_logs_warning(caplog):
    """outer-except path logs a WARNING containing 'OSAP pipeline failed'."""
    stubs = _OsapStubs(raise_at="fetch_osap_returns")
    with caplog.at_level(logging.WARNING, logger="compute.orchestrator.osap"):
        with _apply(stubs):
            run_osap_pipeline(
                _make_pillar_df("AAPL"), _make_composite({"AAPL": 50.0}), _ASOF
            )

    assert any("OSAP pipeline failed" in r.message for r in caplog.records)


def test_C3_import_error_from_deferred_import_is_caught_same_way():
    """An ImportError raised by a deferred-import target (simulating the
    library not being installed) is caught by the same broad
    `except Exception` — same reset semantics as any other failure."""
    stubs = _OsapStubs(raise_at="fetch_osap_returns", raise_exc=ImportError)
    with _apply(stubs):
        result = run_osap_pipeline(
            _make_pillar_df("AAPL"), _make_composite({"AAPL": 50.0}), _ASOF
        )

    assert result.osap_wall_clock_seconds is None
    assert result.osap_signals_used == []
    assert result.composite_osap_adjusted.empty


# ---------------------------------------------------------------------------
# Section D: return-shape / identity guards
# ---------------------------------------------------------------------------


def test_D1_wall_clock_is_none_on_outer_except():
    """osap_wall_clock_seconds is None (not 0.0, not missing) on the
    outer-except path."""
    stubs = _OsapStubs(raise_at="fetch_osap_returns")
    with _apply(stubs):
        result = run_osap_pipeline(
            _make_pillar_df("AAPL"), _make_composite({"AAPL": 50.0}), _ASOF
        )

    assert result.osap_wall_clock_seconds is None


def test_D2_composite_osap_adjusted_is_always_a_series():
    """composite_osap_adjusted is a pd.Series on both the happy path and
    the outer-except path — never a bare dict/list."""
    happy_stubs = _OsapStubs()
    with _apply(happy_stubs):
        happy_result = run_osap_pipeline(
            _make_pillar_df("AAPL"), _make_composite({"AAPL": 50.0}), _ASOF
        )
    assert isinstance(happy_result.composite_osap_adjusted, pd.Series)

    failure_stubs = _OsapStubs(raise_at="fetch_osap_returns")
    with _apply(failure_stubs):
        failure_result = run_osap_pipeline(
            _make_pillar_df("AAPL"), _make_composite({"AAPL": 50.0}), _ASOF
        )
    assert isinstance(failure_result.composite_osap_adjusted, pd.Series)
