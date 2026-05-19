"""Tests for ``compute/features/ipca_factors.py`` — Phase 4k IPCA scout.

Mirrors the Phase 4j Qlib scout test layout (6 offline / 0 @network).
IPCA is pure local sklearn-style computation — no remote endpoint to
network-test, so the `@pytest.mark.network` slot is deliberately empty
(see module docstring §"Critical scope decision" in PR body).

Test pattern:
- Tests #1, #3, #5, #6 require the ``ipca`` package — wrapped in
  ``pytest.importorskip("ipca")`` for graceful skip when ``[factors]``
  extra isn't installed (e.g., a contributor running tests with bare
  ``pip install -e ".[dev]"``).
- Tests #2 and #4 are pure-Python assertions that run regardless of
  ``[factors]`` extra state.

Synthetic fixture is inline (NOT a committed CSV / parquet) per user
authorization 2026-05-19 — IPCA inputs are numpy arrays, no roundtrip
needed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from compute import config
from compute.features import ipca_factors

# ---------------------------------------------------------------------------
# Synthetic fixture — 5 entities × 30 dates × 10 characteristics
# ---------------------------------------------------------------------------


@pytest.fixture
def synthetic_panel_5x30x10():
    """Build a 150-row MultiIndex panel matching ``InstrumentedPCA.fit``
    input shape (entity × date, 10 characteristics).

    Uses ``np.random.RandomState(42)`` for determinism. Matches the
    shape the maintainer's ``test_ipca.py`` exercises, comfortably
    above IPCA's minimum-stable-size threshold (10 firms × 20 years ×
    2 chars).

    Returns:
        ``(X, y)`` tuple. ``X`` is a MultiIndex DataFrame indexed by
        ``(entity, date)`` with 10 characteristic columns. ``y`` is a
        Series aligned to ``X.index``, representing realized returns.
    """
    rng = np.random.RandomState(42)
    entities = [f"E{i:02d}" for i in range(5)]
    dates = list(range(30))
    char_cols = [f"char_{c:02d}" for c in range(10)]

    index = pd.MultiIndex.from_product(
        [entities, dates], names=["entity", "date"]
    )
    X_arr = rng.standard_normal((len(index), len(char_cols)))
    X = pd.DataFrame(X_arr, index=index, columns=char_cols)

    # Linear-ish return generating process so IPCA can fit meaningfully.
    # y = X @ beta + noise; beta vector chosen to be non-degenerate.
    beta = rng.standard_normal(len(char_cols))
    noise = rng.standard_normal(len(index)) * 0.1
    y = pd.Series(X_arr @ beta + noise, index=index, name="ret")

    return X, y


# ---------------------------------------------------------------------------
# Test 1 — Primary CI signal: package install + class exposure
# ---------------------------------------------------------------------------


def test_ipca_imports_and_exposes_instrumented_pca():
    """Primary CI signal — the ``ipca`` package resolves AND exposes
    the ``InstrumentedPCA`` class we depend on.

    If this fails, the scout PR has discovered that the dep is either
    un-installable on PyPI or its public API surface differs from what
    Phase 4k.1 integration plans to consume.
    """
    pytest.importorskip("ipca")
    from ipca import InstrumentedPCA  # noqa: WPS433

    assert callable(InstrumentedPCA)


# ---------------------------------------------------------------------------
# Test 2 — Manifest cardinality lock (no IPCA runtime; runs without extra)
# ---------------------------------------------------------------------------


def test_instrumented_pca_public_api_manifest_locks_8_methods():
    """The hardcoded 8-method manifest must match the cardinality
    locked in ``compute/config.py::IPCA_PUBLIC_API_METHOD_COUNT``.
    Drift detector: if the manifest changes, the config constant must
    move in lockstep.
    """
    assert len(ipca_factors.INSTRUMENTED_PCA_PUBLIC_API) == 8
    assert (
        len(ipca_factors.INSTRUMENTED_PCA_PUBLIC_API)
        == config.IPCA_PUBLIC_API_METHOD_COUNT
    )
    # No duplicates — same lock the module-load assert enforces.
    assert len(set(ipca_factors.INSTRUMENTED_PCA_PUBLIC_API)) == 8
    # Canonical names (alphabetical-ish per upstream source order).
    expected = {
        "fit",
        "get_factors",
        "fit_path",
        "predict",
        "predict_panel",
        "predict_portfolio",
        "score",
        "predictOOS",
    }
    assert set(ipca_factors.INSTRUMENTED_PCA_PUBLIC_API) == expected


# ---------------------------------------------------------------------------
# Test 3 — Runtime introspection drift detector (needs [factors])
# ---------------------------------------------------------------------------


def test_instrumented_pca_public_api_matches_runtime_introspection():
    """Every name in ``INSTRUMENTED_PCA_PUBLIC_API`` must be a callable
    attribute of ``InstrumentedPCA`` at runtime. Catches upstream
    ``ipca>0.6.7`` API drift on next deliberate version bump.
    """
    pytest.importorskip("ipca")
    from ipca import InstrumentedPCA  # noqa: WPS433

    for method_name in ipca_factors.INSTRUMENTED_PCA_PUBLIC_API:
        assert hasattr(InstrumentedPCA, method_name), (
            f"InstrumentedPCA missing locked method: {method_name}"
        )
        assert callable(getattr(InstrumentedPCA, method_name)), (
            f"InstrumentedPCA.{method_name} exists but isn't callable"
        )


# ---------------------------------------------------------------------------
# Test 4 — Cache path sanity (no IPCA runtime; runs without extra)
# ---------------------------------------------------------------------------


def test_ipca_fitted_artifacts_cache_under_repo_cache_dir():
    """The fitted-estimator artifacts cache must live under the repo's
    gitignored ``compute/cache/`` parent. Sanity check that prevents
    accidental commit of binary pickles.
    """
    cache = ipca_factors.IPCA_FITTED_ARTIFACTS_CACHE
    assert isinstance(cache, Path)
    assert cache == config.IPCA_FITTED_ARTIFACTS_CACHE
    # Walk up — the immediate parent must be `compute/cache/`.
    assert cache.parent.name == "cache"
    # And the cache dir-name itself is `ipca`.
    assert cache.name == "ipca"


# ---------------------------------------------------------------------------
# Test 5 — init_ipca returns unfitted estimator with KPS defaults
# ---------------------------------------------------------------------------


def test_init_ipca_returns_unfitted_estimator_with_kps_defaults():
    """``init_ipca()`` with no args must produce an unfitted estimator
    carrying the KPS 2019 baseline defaults (n_factors=5, intercept=True).
    Validates the constants live alongside the InstrumentedPCA shape
    they describe — drift between our defaults and upstream's expected
    keyword names surfaces here.
    """
    pytest.importorskip("ipca")

    est = ipca_factors.init_ipca()

    # KPS 2019 defaults.
    assert est.n_factors == ipca_factors.IPCA_DEFAULT_N_FACTORS == 5
    assert est.intercept is ipca_factors.IPCA_DEFAULT_INTERCEPT is True

    # Unfitted — Gamma / Factors attributes should NOT exist yet.
    assert not hasattr(est, "Gamma") or est.Gamma is None
    assert not hasattr(est, "Factors") or est.Factors is None


# ---------------------------------------------------------------------------
# Test 6 — Smoke fit on synthetic 5×30×10 fixture
# ---------------------------------------------------------------------------


def test_fit_ipca_panel_on_synthetic_5x30x10_fixture(synthetic_panel_5x30x10):
    """The end-to-end smoke. Inline-fixture panel → init_ipca →
    fit_ipca_panel → assert Gamma / Factors / metad shapes.

    Uses n_factors=2 + intercept=False to keep the fitted geometry
    deterministic and trivially shape-checkable. Production
    integration PR will use n_factors=5 (KPS baseline) on the
    502-ticker universe.
    """
    pytest.importorskip("ipca")

    X, y = synthetic_panel_5x30x10
    est = ipca_factors.init_ipca(n_factors=2, intercept=False)
    fitted = ipca_factors.fit_ipca_panel(est, X=X, y=y)

    # sklearn returns-self convention.
    assert fitted is est

    # Post-fit attributes — see module docstring investigation #3.
    assert hasattr(fitted, "Gamma")
    assert hasattr(fitted, "Factors")
    assert hasattr(fitted, "metad")

    # Gamma: (L × K) — 10 characteristics × 2 factors.
    assert fitted.Gamma.shape == (10, 2)
    # Factors: (K × T) — 2 factors × 30 dates.
    assert fitted.Factors.shape == (2, 30)
    # metad dict — N / T / L surface keys per investigation #3.
    assert fitted.metad["N"] == 5
    assert fitted.metad["T"] == 30
    assert fitted.metad["L"] == 10
