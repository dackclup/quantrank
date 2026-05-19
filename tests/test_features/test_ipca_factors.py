"""Phase 4k scout — Kelly-Pruitt-Su IPCA scout tests.

6 offline tests, NO @network. Mirrors the Phase 4j Qlib scout rationale
(tests/test_ingest/test_qlib_features.py): IPCA is a pure local sklearn-
style computation with no remote endpoint, so there is no live-network
slot to fill.

Test 6 uses an inline synthetic 5 entities x 30 dates x 10 characteristics
panel built with `np.random.RandomState(42)`. The panel shape matches the
maintainer's canonical `ipca/test_ipca.py` example (MultiIndex DataFrame
with entity + time levels) and is comfortably above the maintainer's stable
floor (10 firms x 20 years x 2 chars).

Tests 1, 3, 5, 6 use `pytest.importorskip("ipca")` so they skip gracefully
when the `[factors]` extra is not installed. Tests 2 + 4 are pure assertions
against our own module / config constants and run without `ipca` present.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from compute import config
from compute.features import ipca_factors

# --- Inline synthetic panel fixture (test 6) ---------------------------------

@pytest.fixture
def synthetic_ipca_panel() -> tuple[pd.DataFrame, pd.Series]:
    """5 entities x 30 dates x 10 characteristics, deterministic via RNG=42.

    Returns (X, y) where:
      - X is a (150, 10) DataFrame with MultiIndex [(entity, time)]
      - y is a (150,) Series with the same MultiIndex

    Shape matches the maintainer's `ipca/test_ipca.py` canonical usage
    (`data.set_index(['firm', 'year'])` -> X = data.drop(y_col); y = data[y_col]).
    """
    rng = np.random.RandomState(42)
    n_entities = 5
    n_dates = 30
    n_chars = 10
    entities = [f"E{i:02d}" for i in range(n_entities)]
    dates = list(range(2000, 2000 + n_dates))
    index = pd.MultiIndex.from_product([entities, dates], names=["entity", "time"])
    char_names = [f"char_{i:02d}" for i in range(n_chars)]
    X = pd.DataFrame(
        rng.standard_normal((n_entities * n_dates, n_chars)),
        index=index,
        columns=char_names,
    )
    y = pd.Series(
        rng.standard_normal(n_entities * n_dates),
        index=index,
        name="ret",
    )
    return X, y


# --- Tests -------------------------------------------------------------------

def test_ipca_imports_and_exposes_instrumented_pca() -> None:
    """Primary CI signal — `ipca` PyPI package installs and exposes the
    `InstrumentedPCA` estimator. Skips when the `[factors]` extra is absent.
    """
    ipca_pkg = pytest.importorskip("ipca")
    assert hasattr(ipca_pkg, "InstrumentedPCA"), (
        "ipca package missing InstrumentedPCA -- upstream API drift?"
    )
    assert callable(ipca_pkg.InstrumentedPCA), (
        "ipca.InstrumentedPCA is not callable -- not a class?"
    )


def test_instrumented_pca_public_api_manifest_locks_8_methods() -> None:
    """Pure-assertion drift detector — the 8-name manifest tuple in
    `compute.features.ipca_factors` matches the asserted count constant in
    `compute.config`. Catches accidental edits to either side. Runs without
    `ipca` installed (no importorskip needed).
    """
    assert len(ipca_factors.INSTRUMENTED_PCA_PUBLIC_API) == 8
    assert (
        len(ipca_factors.INSTRUMENTED_PCA_PUBLIC_API)
        == config.IPCA_PUBLIC_API_METHOD_COUNT
    )
    # Cardinality + uniqueness invariants the module's own load-time assert
    # already enforces, restated here as an explicit test surface.
    assert len(set(ipca_factors.INSTRUMENTED_PCA_PUBLIC_API)) == 8
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


def test_instrumented_pca_public_api_matches_runtime_introspection() -> None:
    """Runtime drift detector — for each name in the manifest, assert that
    `InstrumentedPCA` actually exposes it as a callable attribute. This is
    the test that catches an `ipca>0.6.7` upgrade silently dropping or
    renaming a method.
    """
    ipca_pkg = pytest.importorskip("ipca")
    cls = ipca_pkg.InstrumentedPCA
    missing = [
        name
        for name in ipca_factors.INSTRUMENTED_PCA_PUBLIC_API
        if not hasattr(cls, name) or not callable(getattr(cls, name))
    ]
    assert not missing, (
        f"InstrumentedPCA missing or non-callable methods: {missing} -- "
        f"upstream ipca package may have dropped or renamed methods. "
        f"Update INSTRUMENTED_PCA_PUBLIC_API in compute/features/ipca_factors.py "
        f"and IPCA_PUBLIC_API_METHOD_COUNT in compute/config.py together."
    )


def test_ipca_fitted_artifacts_cache_under_repo_cache_dir() -> None:
    """Sanity check — the cache path is under `compute/cache/`, which is
    gitignored via the parent glob at .gitignore:221. No `ipca` runtime
    needed; pure path arithmetic.
    """
    cache_path = ipca_factors.IPCA_FITTED_ARTIFACTS_CACHE
    assert cache_path == config.CACHE_DIR / "ipca", (
        f"IPCA_FITTED_ARTIFACTS_CACHE drifted from CACHE_DIR / 'ipca': "
        f"got {cache_path}"
    )
    assert cache_path.parent.name == "cache", (
        f"IPCA cache must live directly under compute/cache/ to inherit the "
        f".gitignore parent glob; got parent={cache_path.parent}"
    )


def test_init_ipca_returns_unfitted_estimator_with_kps_defaults() -> None:
    """Smoke — `init_ipca()` returns an unfitted `InstrumentedPCA` with
    KPS 2019 baseline defaults (5 latent factors, intercept on). Validates
    our default constants against the actual estimator constructor.
    """
    pytest.importorskip("ipca")
    est = ipca_factors.init_ipca()
    assert est.n_factors == 5, (
        f"IPCA_DEFAULT_N_FACTORS drifted from KPS 2019 baseline: got "
        f"{est.n_factors}, expected 5"
    )
    assert est.intercept is True, (
        f"IPCA_DEFAULT_INTERCEPT drifted: got {est.intercept}, expected True"
    )
    # Unfitted estimator has no Gamma / Factors attributes yet.
    assert not hasattr(est, "Gamma"), (
        "init_ipca() returned a pre-fitted estimator -- factory should be "
        "idempotent / unfitted"
    )


def test_fit_ipca_panel_on_synthetic_5x30x10_fixture(
    synthetic_ipca_panel: tuple[pd.DataFrame, pd.Series],
) -> None:
    """End-to-end smoke — `init_ipca` + `fit_ipca_panel` on the synthetic
    5 x 30 x 10 panel. Validates the sklearn-style return-self contract +
    post-fit attribute shapes (Gamma loadings, Factors latent returns,
    metad dict with N/T/L counts).
    """
    pytest.importorskip("ipca")
    X, y = synthetic_ipca_panel
    est = ipca_factors.init_ipca(n_factors=2, intercept=False)
    fitted = ipca_factors.fit_ipca_panel(est, X=X, y=y)

    # sklearn-style: fit() returns self.
    assert fitted is est, "fit_ipca_panel must return the same estimator (sklearn contract)"

    # Post-fit shape contract.
    assert fitted.Gamma.shape == (10, 2), (
        f"Gamma shape drift: expected (L=10, n_factors=2), got {fitted.Gamma.shape}"
    )
    assert fitted.Factors.shape == (2, 30), (
        f"Factors shape drift: expected (n_factors=2, T=30), got {fitted.Factors.shape}"
    )

    # Metadata dict reflects the panel dimensions.
    assert fitted.metad["N"] == 5, f"N (entities) drift: got {fitted.metad['N']}"
    assert fitted.metad["T"] == 30, f"T (dates) drift: got {fitted.metad['T']}"
    assert fitted.metad["L"] == 10, f"L (characteristics) drift: got {fitted.metad['L']}"
