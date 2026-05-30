"""Tests for the OpenAssetPricing (OSAP) ingest scout module.

Scout PR scope: 5 offline smoke tests + 1 opt-in @network live test.
Test #1 (import + API surface) is the primary CI scout signal —
it runs by default and proves both that ``openassetpricing==0.0.2``
resolved AND that the package's ``OpenAP`` class is exposed at the
top level. The other offline tests cover the cache discipline.
"""

from __future__ import annotations

import time
from pathlib import Path

import openassetpricing
import pandas as pd
import pytest

from compute.ingest import osap as osap_mod

FIXTURE_CSV = Path(__file__).parent.parent / "fixtures" / "osap_returns_sample.csv"


def test_package_imports_and_exposes_openap_class():
    """Primary CI scout signal: the ``openassetpricing`` package
    resolves AND exposes the ``OpenAP`` class we depend on.

    If this fails, the scout PR has discovered that the dep is
    either un-installable on PyPI or its public API surface
    differs from what Phase 4h plans to consume — exactly the
    kind of finding the scout PR exists to surface before the
    larger Phase 4h integration commits to it.
    """
    assert hasattr(openassetpricing, "OpenAP")
    # Check the API surface on the CLASS, not an instance. Instantiating
    # OpenAP() in openassetpricing 0.0.2 triggers a live Google-Drive metadata
    # download inside the constructor — which made this default-lane scout test
    # flaky whenever Drive rate-limits (the fetch returns a "Quota exceeded"
    # HTML page and polars then raises ColumnNotFoundError on the missing
    # "Acronym" column). The four methods are class-level defs, so hasattr
    # resolves them without constructing an instance / hitting the network. The
    # live instantiation + fetch path stays covered by the @network
    # test_fetch_osap_returns_live below.
    for method in ("dl_port", "dl_signal", "dl_all_signals", "list_port"):
        assert hasattr(openassetpricing.OpenAP, method), f"OpenAP missing method: {method}"


def test_cache_hit_returns_parquet(monkeypatch, tmp_path):
    """Fresh cache short-circuits the fetcher."""
    cache = tmp_path / "returns.parquet"
    monkeypatch.setattr(osap_mod.config, "OSAP_RETURNS_CACHE", cache)

    expected = pd.read_csv(FIXTURE_CSV)
    cache.parent.mkdir(parents=True, exist_ok=True)
    expected.to_parquet(cache, index=False)

    def boom(*args, **kwargs):
        raise AssertionError("network fetch should not be called when cache is fresh")

    monkeypatch.setattr(osap_mod, "_fetch_osap_returns_uncached", boom)
    df = osap_mod.fetch_osap_returns()
    assert len(df) == len(expected)
    assert set(osap_mod.REQUIRED_COLUMNS).issubset(df.columns)


def test_cache_miss_calls_fetcher(monkeypatch, tmp_path):
    """Empty cache directory triggers the fetcher; result lands in parquet."""
    cache = tmp_path / "osap" / "returns.parquet"
    monkeypatch.setattr(osap_mod.config, "OSAP_RETURNS_CACHE", cache)

    synthetic = pd.read_csv(FIXTURE_CSV)
    monkeypatch.setattr(
        osap_mod, "_fetch_osap_returns_uncached", lambda *a, **kw: synthetic
    )

    assert not cache.exists()
    df = osap_mod.fetch_osap_returns()
    assert cache.exists()
    assert len(df) == len(synthetic)


def test_force_refresh_bypasses_cache(monkeypatch, tmp_path):
    """``force_refresh=True`` re-runs the fetcher even when the cache is fresh."""
    cache = tmp_path / "returns.parquet"
    monkeypatch.setattr(osap_mod.config, "OSAP_RETURNS_CACHE", cache)

    stale = pd.read_csv(FIXTURE_CSV).head(2)
    cache.parent.mkdir(parents=True, exist_ok=True)
    stale.to_parquet(cache, index=False)

    fresh = pd.read_csv(FIXTURE_CSV)
    calls = {"count": 0}

    def fetcher(*args, **kwargs):
        calls["count"] += 1
        return fresh

    monkeypatch.setattr(osap_mod, "_fetch_osap_returns_uncached", fetcher)
    df = osap_mod.fetch_osap_returns(force_refresh=True)
    assert calls["count"] == 1
    assert len(df) == len(fresh)


def test_fixture_csv_matches_required_schema():
    """The bundled synthetic fixture itself must satisfy ``REQUIRED_COLUMNS``
    so the cache tests' baseline isn't accidentally invalidated.
    """
    df = pd.read_csv(FIXTURE_CSV)
    assert set(osap_mod.REQUIRED_COLUMNS).issubset(df.columns)
    assert len(df) >= 3, "fixture must have at least 3 rows for cache-miss test parity"


@pytest.mark.network
@pytest.mark.timeout(300)
def test_fetch_osap_returns_live(monkeypatch, tmp_path):
    """Real OSAP package call. Asserts non-empty + required schema.
    Logs elapsed time for the PR-comment latency report; does NOT
    assert wall-clock latency (flaky on shared CI runners).
    """
    cache = tmp_path / "osap" / "returns.parquet"
    monkeypatch.setattr(osap_mod.config, "OSAP_RETURNS_CACHE", cache)

    t0 = time.monotonic()
    df = osap_mod.fetch_osap_returns(force_refresh=True)
    elapsed = time.monotonic() - t0

    print(f"\n[osap-scout] cold fetch elapsed={elapsed:.2f}s rows={len(df)} cols={list(df.columns)}")
    assert len(df) > 0
    assert set(osap_mod.REQUIRED_COLUMNS).issubset(df.columns)
    assert cache.exists()
    cache_size_mb = cache.stat().st_size / (1024 * 1024)
    print(f"[osap-scout] parquet size={cache_size_mb:.1f}MB")
