"""Tests for ``compute/ingest/qlib_features.py`` — Phase 4j scout.

Mirrors the Phase 4i scout test layout
(``tests/test_ingest/test_jkp.py``, 6 tests). Notable differences:

- **ALL 6 tests are OFFLINE.** There is no ``@network`` test for this
  scout — see ``compute/ingest/qlib_features.py`` module docstring
  §"NO public US data bundle" for the architectural reason (Qlib has
  no remote CDN to hit; its data pipeline is local-bin-only).
- The "real Alpha158 compute on synthetic fixture" test originally
  planned was DROPPED post-investigation 2026-05-19: ``pyqlib``'s
  PyPI wheel does not bundle the ``scripts/dump_bin.py`` utility
  needed for OHLCV-CSV → ``.bin`` conversion. That scaffolding is
  integration-PR scope. The replacement test #3 below asserts the
  hardcoded ``ALPHA158_FEATURE_NAMES`` tuple matches the runtime
  introspection from ``Alpha158DL.get_feature_config()[1]`` — a
  stronger drift detector that triggers on every ``pip install``
  upgrade.
- Tests that touch ``import qlib`` are wrapped in
  ``pytest.importorskip("qlib")`` so the suite passes on dev
  environments without the ``[factors]`` extra installed
  (graceful-skip pattern matches ``tests/test_features/
  test_osap_e2e_integration.py``). CI always installs ``[factors]``,
  so real failures still surface there.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from compute import config
from compute.ingest import qlib_features


def test_alpha158_feature_manifest_has_158_entries():
    """Primary CI signal: 158-feature count locked. No ``qlib`` import,
    no runtime introspection — pure tuple cardinality + uniqueness
    check that survives even when the ``[factors]`` extra isn't
    installed."""
    assert len(qlib_features.ALPHA158_FEATURE_NAMES) == 158
    assert len(set(qlib_features.ALPHA158_FEATURE_NAMES)) == 158


def test_alpha158_feature_manifest_first_5_anchor():
    """Anchor the first 5 entries against the canonical Qlib v0.9.7
    surface. Cheap drift detector — if
    ``Alpha158DL.get_feature_config()`` upstream changes its leading
    K-bar features in a future release, this test fails and we
    deliberately re-hardcode the manifest."""
    assert qlib_features.ALPHA158_FEATURE_NAMES[:5] == (
        "KMID", "KLEN", "KMID2", "KUP", "KUP2",
    )


def test_alpha158_feature_manifest_matches_runtime_introspection():
    """When ``pyqlib`` is installed, the hardcoded
    :data:`qlib_features.ALPHA158_FEATURE_NAMES` tuple must match
    ``Alpha158DL.get_feature_config()[1]`` exactly. Skips gracefully
    when the ``[factors]`` extra isn't installed."""
    pytest.importorskip("qlib")
    from qlib.contrib.data.loader import Alpha158DL

    _, runtime_names = Alpha158DL.get_feature_config()
    assert tuple(runtime_names) == qlib_features.ALPHA158_FEATURE_NAMES


def test_qlib_data_cache_constant_under_repo_cache_dir():
    """Config constants sanity. ``compute/cache/`` is already
    gitignored (.gitignore:221) so the ``compute/cache/qlib/`` subtree
    inherits the ignore automatically — no explicit .gitignore edit
    needed for this scout."""
    assert isinstance(config.QLIB_DATA_CACHE, Path)
    parts = config.QLIB_DATA_CACHE.parts
    assert parts[-3:] == ("cache", "qlib", "us_data"), (
        f"QLIB_DATA_CACHE last 3 parts = {parts[-3:]}, expected "
        f"('cache', 'qlib', 'us_data')"
    )
    assert config.QLIB_DATA_MAX_AGE_DAYS == 31
    assert config.ALPHA158_FEATURE_COUNT == 158


def test_init_qlib_passes_us_region_and_provider_uri(monkeypatch, tmp_path):
    """Monkeypatch ``qlib.init`` to capture kwargs; assert the
    wrapper passes ``region="us"`` (Qlib's ``REG_US`` constant) and
    the provided ``provider_uri`` as a string. Locks the US-only
    scope vs Qlib's CN-market default."""
    pytest.importorskip("qlib")
    import qlib

    captured: dict = {}

    def fake_init(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(qlib, "init", fake_init)
    qlib_features.init_qlib(provider_uri=tmp_path)

    assert captured["region"] == "us"
    assert captured["provider_uri"] == str(tmp_path)


def test_init_qlib_defaults_to_config_cache_when_no_uri(monkeypatch):
    """Wrapper defaults to :data:`config.QLIB_DATA_CACHE` when no
    ``provider_uri`` argument is supplied. Locks the
    "scout-cache-by-default, override-for-tests" contract."""
    pytest.importorskip("qlib")
    import qlib

    captured: dict = {}

    def fake_init(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(qlib, "init", fake_init)
    qlib_features.init_qlib()

    assert captured["provider_uri"] == str(config.QLIB_DATA_CACHE)
    assert captured["region"] == "us"
