"""Kelly-Pruitt-Su Instrumented Principal Component Analysis (IPCA) scout.

Phase 4k scout — installs the `ipca` PyPI package (MIT, Buechner+Bybee 2019,
github.com/bkelly-lab/ipca) + locks the InstrumentedPCA 8-method public API
surface at module load + ships 6 offline tests. NO @network test (pure local
sklearn-style computation, no remote endpoint — mirrors Phase 4j Qlib
rationale at compute/ingest/qlib_features.py:23-30).

This is the 4th of 4 factor-library scouts (4h OSAP, 4i JKP, 4j Qlib, 4k IPCA);
structurally distinct from prior three: IPCA takes a panel of characteristics
(N entities x T dates x L characteristics) and produces Gamma (L x K loadings)
+ Factors (K x T latent factor returns) via an ALS-style decomposition.
Characteristics-matrix construction, universe-wide fit, and composite-blend
decision are integration-PR scope (~Phase 4k.1).

Pre-plan investigations carried verbatim (2026-05-19, against ipca==0.6.7):

1. PyPI canonical name:
   `pip index versions ipca` -> ipca 0.6.7 latest. `ipca-py` / `pyipca` 404.
   Last upstream release 2021-04-22 -- package is ~5 years stale; pin to
   0.6.x band in pyproject.toml [factors].

2. License: MIT (verbatim from ipca-0.6.7.dist-info/LICENSE.md):
   `MIT License - Copyright (c) [2019] [Matthias Buechner, Leland Bybee]`.
   Same as Qlib 4j, unlike JKP 4i's CC BY-NC 4.0 -- no Phase 6+ commercial
   complication.

3. sklearn-style public API surface (extracted from wheel `ipca/ipca.py`,
   8 public methods on `InstrumentedPCA(BaseEstimator)`):
       fit / get_factors / fit_path / predict / predict_panel /
       predict_portfolio / score / predictOOS
   Notable divergence: NO `transform` / `fit_transform` (sklearn pattern
   absent). Use `fit` + `Gamma`/`Factors` attrs + `predict_panel` for the
   panel-prediction path. RegressorMixin imported in source but unused.

4. Data requirements (from maintainer's `ipca/test_ipca.py`):
   - Panel: pandas DataFrame with MultiIndex (entity, time), or numpy
     ndarray plus an explicit `indices` argument.
   - Min stable size: maintainer uses 10 firms x 20 years x 2 chars.
   - Unbalanced panels + interior NaNs supported.
   - For 502-ticker universe (integration-PR scope), `data_type="portfolio"`
     is the recommended scaling path -- ALS on Q matrix not raw panel.

5. CI install footprint (net-new transitives over `[factors]` baseline):
   numba (~50 MB w/ llvmlite ~30 MB) + progressbar (~50 KB).
   ~50-80 MB total. Substantially lighter than Qlib's 150-180 MB (4j).
   `scipy`, `joblib`, `scikit-learn` already in tree via Phase 4h/4i.

Reference: Kelly, B., Pruitt, S., Su, Y. (2019). "Characteristics are
covariances: A unified model of risk and return." Journal of Financial
Economics 134(3), 501-524.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from compute import config

if TYPE_CHECKING:
    from ipca import InstrumentedPCA

logger = logging.getLogger(__name__)

# Cache for fitted-estimator pickle artifacts. Scout writes nothing -- the
# integration PR will persist the universe-wide IPCA fit (Gamma loadings +
# Factors returns + metadata) here for downstream consumption.
IPCA_FITTED_ARTIFACTS_CACHE: Path = config.IPCA_FITTED_ARTIFACTS_CACHE

# KPS 2019 baseline defaults. Validated against the `InstrumentedPCA`
# constructor signature by the init_ipca smoke test (NOT module-load assert
# -- separates "our defaults" from "external API surface lock"). Integration
# PR will tune via walk-forward IC per phase-4/ipca-factor-fit/PLAN.md
# acceptance criteria.
IPCA_DEFAULT_N_FACTORS: int = 5
IPCA_DEFAULT_INTERCEPT: bool = True

# Public-API drift detector. If a future `ipca` release drops or renames
# any of these methods, module load fails fast at the assertion below.
# This is the scout's analogue to Phase 4j's ALPHA158_FEATURE_NAMES
# (158-entry feature manifest at compute/ingest/qlib_features.py) -- the
# external surface shape is different (method dispatch table vs feature
# names) because IPCA has no fixed feature set (X matrix is user-supplied),
# but the drift-detector intent is identical.
INSTRUMENTED_PCA_PUBLIC_API: tuple[str, ...] = (
    "fit",
    "get_factors",
    "fit_path",
    "predict",
    "predict_panel",
    "predict_portfolio",
    "score",
    "predictOOS",
)
assert len(INSTRUMENTED_PCA_PUBLIC_API) == config.IPCA_PUBLIC_API_METHOD_COUNT, (
    f"INSTRUMENTED_PCA_PUBLIC_API drifted: expected "
    f"{config.IPCA_PUBLIC_API_METHOD_COUNT} methods, got "
    f"{len(INSTRUMENTED_PCA_PUBLIC_API)} -- check ipca package upgrade."
)
assert len(set(INSTRUMENTED_PCA_PUBLIC_API)) == len(INSTRUMENTED_PCA_PUBLIC_API), (
    "INSTRUMENTED_PCA_PUBLIC_API contains duplicate method names"
)


def init_ipca(
    n_factors: int = IPCA_DEFAULT_N_FACTORS,
    intercept: bool = IPCA_DEFAULT_INTERCEPT,
    **kwargs: Any,
) -> InstrumentedPCA:
    """Idempotent factory for an unfitted `InstrumentedPCA` estimator.

    Scout-mode defaults match KPS 2019 baseline (5 latent factors, intercept
    on). Integration PR will call this from compute/main.py with the
    universe-wide characteristics matrix. NO tenacity policy -- IPCA is a
    pure local sklearn-style computation, no network endpoint to retry
    against (mirrors Phase 4j Qlib).
    """
    from ipca import InstrumentedPCA

    return InstrumentedPCA(n_factors=n_factors, intercept=intercept, **kwargs)


def fit_ipca_panel(
    estimator: InstrumentedPCA,
    *,
    X: Any,
    y: Any,
    indices: Any = None,
    **fit_kwargs: Any,
) -> InstrumentedPCA:
    """Forward-compat wrapper around `InstrumentedPCA.fit(X, y, indices=...)`.

    Scout returns the fitted estimator; post-fit attributes `.Gamma`
    (L x n_factors loadings) and `.Factors` (n_factors x T returns) are
    accessible on the returned object. Integration PR will persist these
    artifacts to `IPCA_FITTED_ARTIFACTS_CACHE` after the universe-wide fit.

    Args:
        estimator: Unfitted `InstrumentedPCA` from `init_ipca()`.
        X: Characteristics panel. Either a pandas DataFrame with MultiIndex
            (entity, time), or a numpy ndarray (in which case `indices` must
            be supplied -- two-column array of [entity_id, time_id] pairs).
        y: Realized returns. Either a pandas Series with the same MultiIndex
            as X, or a numpy 1-D array aligned with `indices`.
        indices: Required only when X/y are ndarrays.
        **fit_kwargs: Forwarded to `InstrumentedPCA.fit()` (e.g. `PSF`,
            `data_type`, `label_ind`, `Gamma`, `Factors`).

    Returns:
        The same `estimator` instance, now fitted (sklearn-style).
    """
    return estimator.fit(X=X, y=y, indices=indices, **fit_kwargs)
