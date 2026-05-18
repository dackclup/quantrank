"""Tests for ``compute/ingest/jkp.py`` — Phase 4i scout.

Mirrors the OSAP scout test layout (``tests/test_ingest/test_osap.py``,
6 tests = 5 offline + 1 ``@network``). Differences from OSAP:

- **Primary CI signal is the theme-manifest assertion** (cheap; runs
  without any package import or network call) instead of a
  ``hasattr(<package>, "<class>")`` smoke test, because JKP has NO
  PyPI package — see ``compute/ingest/jkp.py`` module docstring
  §"Access-path discovery" for the verification record.
- ``@network`` test hits the publicly-readable ``jkpfactors.s3.
  amazonaws.com`` bucket directly. Logs elapsed time for the PR-
  comment latency report; does NOT assert wall-clock latency (flaky
  on shared CI runners).
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import pytest

from compute import config
from compute.ingest import jkp as jkp_mod

FIXTURE_CSV = Path(__file__).parent.parent / "fixtures" / "jkp_returns_sample.csv"


def test_jkp_themes_manifest_has_13_entries():
    """Primary CI signal: the 13-theme manifest is the load-bearing
    contract for the integration PR. Asserts cardinality + canonical
    names + uniqueness with zero network / package dependence."""
    assert len(jkp_mod.JKP_THEMES) == 13
    assert len(set(jkp_mod.JKP_THEMES)) == 13  # no duplicates
    expected = {
        "quality", "value", "investment", "profitability", "profit_growth",
        "momentum", "leverage", "trading_frictions", "skewness", "low_risk",
        "size", "accruals", "seasonality",
    }
    assert set(jkp_mod.JKP_THEMES) == expected


def test_cache_hit_returns_parquet(monkeypatch, tmp_path):
    """Fresh cache short-circuits the fetcher entirely."""
    cache = tmp_path / "jkp" / "returns.parquet"
    cache.parent.mkdir(parents=True)
    # Seed a parquet that already has the required columns so the
    # post-load schema check passes.
    seed = pd.read_csv(FIXTURE_CSV)
    seed.to_parquet(cache, index=False)
    monkeypatch.setattr(config, "JKP_RETURNS_CACHE", cache)
    monkeypatch.setattr(config, "JKP_RETURNS_MAX_AGE_DAYS", 31)

    calls = {"count": 0}

    def fake_fetcher(url):
        calls["count"] += 1
        raise AssertionError("fetcher should not be called on a fresh cache")

    monkeypatch.setattr(jkp_mod, "_fetch_jkp_csv_uncached", fake_fetcher)
    df = jkp_mod.fetch_jkp_returns()

    assert calls["count"] == 0
    assert len(df) == len(seed)
    assert jkp_mod.JKP_SCOUT_REQUIRED_COLUMNS.issubset(df.columns)


def test_cache_miss_calls_fetcher(monkeypatch, tmp_path):
    """Empty cache directory → fetcher invoked once, result cached
    to parquet, returned DataFrame matches what the fetcher produced."""
    cache = tmp_path / "jkp" / "returns.parquet"
    monkeypatch.setattr(config, "JKP_RETURNS_CACHE", cache)

    fresh = pd.read_csv(FIXTURE_CSV)
    calls = {"count": 0, "url": None}

    def fake_fetcher(url):
        calls["count"] += 1
        calls["url"] = url
        return fresh

    monkeypatch.setattr(jkp_mod, "_fetch_jkp_csv_uncached", fake_fetcher)
    df = jkp_mod.fetch_jkp_returns()

    assert calls["count"] == 1
    assert calls["url"] == f"{jkp_mod.JKP_BUCKET_ROOT}/{jkp_mod.JKP_SCOUT_ASSET_PATH}"
    assert cache.exists()
    assert len(df) == len(fresh)


def test_force_refresh_bypasses_cache(monkeypatch, tmp_path):
    """``force_refresh=True`` re-runs the fetcher even when cache is
    fresh — for ops who need to nuke a stale parquet without manual
    rm."""
    cache = tmp_path / "jkp" / "returns.parquet"
    cache.parent.mkdir(parents=True)
    seed = pd.read_csv(FIXTURE_CSV)
    seed.to_parquet(cache, index=False)
    monkeypatch.setattr(config, "JKP_RETURNS_CACHE", cache)
    monkeypatch.setattr(config, "JKP_RETURNS_MAX_AGE_DAYS", 31)

    fresh = pd.read_csv(FIXTURE_CSV)
    calls = {"count": 0}

    def fake_fetcher(url):
        calls["count"] += 1
        return fresh

    monkeypatch.setattr(jkp_mod, "_fetch_jkp_csv_uncached", fake_fetcher)
    df = jkp_mod.fetch_jkp_returns(force_refresh=True)

    assert calls["count"] == 1
    assert len(df) == len(fresh)


def test_fixture_csv_matches_required_schema():
    """The bundled synthetic fixture must satisfy
    ``JKP_SCOUT_REQUIRED_COLUMNS`` so the cache-mechanic tests'
    baseline isn't accidentally invalidated by a schema-contract
    tweak in the module."""
    df = pd.read_csv(FIXTURE_CSV)
    assert jkp_mod.JKP_SCOUT_REQUIRED_COLUMNS.issubset(df.columns)
    assert len(df) >= 3, "fixture must have at least 3 rows for cache-miss parity"


@pytest.mark.network
@pytest.mark.timeout(300)
def test_fetch_jkp_returns_live(monkeypatch, tmp_path):
    """Real S3 fetch — asserts non-empty + required schema. The scout
    PR's main access-path verification. Logs elapsed time for the PR-
    comment latency report; does NOT assert wall-clock latency.

    NOTE: If this test fails with a 4xx, the public S3 bucket may have
    been gated (mirroring the jkpfactors.com UI gating discovered in
    pre-plan probes). See ``compute/ingest/jkp.py`` module docstring
    §"Access-path discovery" for the verification record.
    """
    cache = tmp_path / "jkp" / "returns.parquet"
    monkeypatch.setattr(config, "JKP_RETURNS_CACHE", cache)

    t0 = time.monotonic()
    df = jkp_mod.fetch_jkp_returns(force_refresh=True)
    elapsed = time.monotonic() - t0

    print(
        f"\n[jkp-scout] cold fetch elapsed={elapsed:.2f}s "
        f"rows={len(df)} cols={list(df.columns)}"
    )
    assert len(df) > 0
    assert jkp_mod.JKP_SCOUT_REQUIRED_COLUMNS.issubset(df.columns)
    assert cache.exists()
    cache_size_kb = cache.stat().st_size / 1024
    print(f"[jkp-scout] parquet size={cache_size_kb:.1f}KB")
