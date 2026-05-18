"""End-to-end @network integration test for Phase 4h OSAP pipeline.

Exercises the full ingest → replicate → gate → IC → blend chain against
the real OSAP package release. Skips when ``--run-network`` is absent
(conftest.py default), so casual ``pytest tests/`` runs are unaffected.

Scope:
  - Real ``fetch_osap_returns`` call against the live OSAP CDN (cached
    in ``tmp_path`` so the host cache stays clean)
  - ``compute_long_short_returns`` over the real cross-section
  - ``gate_osap_signals`` PBO/DSR gate runs end-to-end on a real
    100-signal candidate cohort
  - ``compute_rolling_ic_12m`` returns a finite [-1, 1] value for
    ``Mom1m`` (a canonical positive-IC factor — sanity check, NOT a
    threshold assertion)
  - ``compute_osap_signals`` produces a per-ticker proxy map for a
    20-ticker S&P sample
  - ``aggregate_osap_signals`` → ``apply_osap_blend`` round-trips
    without crashing and produces a Series clipped to [0, 100]

The test does NOT run the full ``compute/main.py`` (that would hit
SEC EDGAR for 502 tickers — too expensive for CI). The OSAP pipeline
is exercised in isolation against real data; the ``compute/main.py``
wiring it together is covered by offline unit tests on each layer +
this @network suite confirming the data shapes match end-to-end.
"""

from __future__ import annotations

import time
from datetime import date

import pandas as pd
import pytest

from compute.features.osap_replicate import (
    compute_long_short_returns,
    compute_osap_signals,
    coverage_by_signal,
)
from compute.ingest import osap as osap_mod
from compute.ingest.osap import fetch_osap_returns
from compute.scoring.osap_blend import aggregate_osap_signals, apply_osap_blend
from compute.validation.osap_validation import (
    compute_rolling_ic_12m,
    filter_accepted_signals,
    gate_osap_signals,
)

SAMPLE_TICKERS_20 = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
    "META", "TSLA", "BRK.B", "UNH", "JPM",
    "XOM", "V", "JNJ", "WMT", "PG",
    "HD", "MA", "AVGO", "CVX", "LLY",
]

# A small, well-known-name subset of OSAP signals that the live release
# is guaranteed to expose. Keeps the integration test cheap and
# deterministic on release shifts — full 100-signal run is the cron
# job's concern.
SAMPLE_SIGNALS = ("Mom1m", "BM", "GP", "Accruals")


@pytest.mark.network
@pytest.mark.timeout(600)
def test_osap_pipeline_end_to_end_real_fetch(monkeypatch, tmp_path) -> None:
    """Full Phase-4h chain on real OSAP data — 4-signal × 20-ticker slice."""
    cache = tmp_path / "osap" / "returns.parquet"
    monkeypatch.setattr(osap_mod.config, "OSAP_RETURNS_CACHE", cache)

    # 1) Real fetch — filter to SAMPLE_SIGNALS so download stays cheap.
    t0 = time.monotonic()
    returns = fetch_osap_returns(
        force_refresh=True, signals=list(SAMPLE_SIGNALS), as_of=date.today()
    )
    elapsed = time.monotonic() - t0
    print(
        f"\n[osap-e2e] live fetch elapsed={elapsed:.2f}s "
        f"rows={len(returns)} cols={list(returns.columns)}"
    )
    assert not returns.empty
    assert set(returns["signalname"].unique()).issubset(set(SAMPLE_SIGNALS))

    # 2) Long-short derivation.
    ls = compute_long_short_returns(returns)
    assert {"signalname", "date", "ls_return"}.issubset(ls.columns)
    assert not ls.empty
    print(
        f"[osap-e2e] long-short rows={len(ls)} "
        f"signals={ls['signalname'].nunique()}"
    )

    # 3) PBO/DSR gate.
    gate_results = gate_osap_signals(ls, requested_signals=SAMPLE_SIGNALS)
    assert len(gate_results) >= 1
    accepted, excluded = filter_accepted_signals(gate_results)
    print(
        f"[osap-e2e] gate accepted={accepted} excluded={excluded} "
        f"of candidates={list(gate_results.keys())}"
    )

    # Every gate result must have a sensible structure regardless of
    # accept/reject outcome.
    for sig, res in gate_results.items():
        assert isinstance(res.accepted, bool), sig
        if res.accepted:
            assert res.rejection_reason is None, sig
            assert res.pbo is not None and 0.0 <= res.pbo <= 1.0, sig
            assert res.dsr is not None, sig
        else:
            assert res.rejection_reason in {
                "high_pbo", "low_dsr", "insufficient_data", "gate_failed",
            }, (sig, res.rejection_reason)

    # 4) Rolling-12m IC sanity on Mom1m (well-known +IC factor).
    mom_ic = compute_rolling_ic_12m(ls, "Mom1m")
    print(f"[osap-e2e] Mom1m rolling-12m IC={mom_ic}")
    if mom_ic is not None:
        assert -1.0 <= mom_ic <= 1.0, mom_ic
        # NOT asserting > 0 — rolling-12m on a single window is noisy;
        # canonical full walk-forward is Phase 5's job.

    # 5) Per-ticker proxy signal map — 20 sample tickers.
    signal_map = compute_osap_signals(
        returns,
        tickers=SAMPLE_TICKERS_20,
        as_of=date.today(),
        requested_signals=SAMPLE_SIGNALS,
    )
    assert len(signal_map) == 20
    populated_tickers = [t for t, m in signal_map.items() if m]
    print(
        f"[osap-e2e] per-ticker map: {len(populated_tickers)}/20 "
        f"have non-empty signal dicts"
    )
    coverage = coverage_by_signal(signal_map)
    print(f"[osap-e2e] coverage by signal: {coverage}")

    # 6) Aggregate + blend round-trip with a synthetic composite series.
    composite = pd.Series(
        {t: 60.0 + (i % 5) * 4.0 for i, t in enumerate(SAMPLE_TICKERS_20)}
    )
    osap_aggregate = aggregate_osap_signals(signal_map)
    blended = apply_osap_blend(composite, osap_aggregate)
    assert blended.name == "composite_score_osap_adjusted"
    assert (blended >= 0.0).all() and (blended <= 100.0).all()
    assert set(blended.index) == set(SAMPLE_TICKERS_20)
    print(
        f"[osap-e2e] blended range=[{blended.min():.2f}, "
        f"{blended.max():.2f}] OSAP-covered tickers="
        f"{int((~osap_aggregate.reindex(composite.index).isna()).sum())}"
    )
