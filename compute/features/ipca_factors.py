"""Phase 4k scout — Kelly-Pruitt-Su IPCA latent factor model integration.

Scout PR scope. Surfaces the IPCA package's API + license + sklearn-shape
facts so the follow-on full-integration PR (characteristics-matrix
construction + universe-wide IPCA fit + composite blend decision)
starts from solid ground.

Background — Kelly, Pruitt, Su (2019) *Journal of Financial Economics*
"Characteristics are covariances: A unified model of risk and return".
The `ipca` PyPI package implements ``InstrumentedPCA`` as a sklearn-
style estimator: a panel ``X`` of shape ``(N stocks × T dates, L
characteristics)`` plus realized returns ``y`` decompose into
``Gamma`` (L × K factor loadings) and ``Factors`` (K × T latent factor
returns) where K is the user-chosen number of factors.

Pre-plan investigation results (verified 2026-05-19 — pre-PR probes):

1. **PyPI package**: ``ipca==0.6.7`` (canonical, matches SKILL.md L155).
   Available versions back to 0.1; last release 2021-04-22 (~5 years
   stale). Pin tightly via ``>=0.6.7,<0.7`` in ``[factors]`` extra.

2. **License**: MIT (verified verbatim from ``LICENSE.md`` —
   "Copyright (c) [2019] [Matthias Buechner, Leland Bybee]"). No CC
   BY-NC complication unlike JKP (Phase 4i). Safe for Phase 6+
   commercial roadmap.

3. **sklearn-compatible API surface** (8 public methods extracted
   from wheel source pre-install):
   ``fit / get_factors / fit_path / predict / predict_panel /
   predict_portfolio / score / predictOOS``.
   Post-fit attributes: ``self.Gamma`` (L × K loadings), ``self.Factors``
   (K × T returns), ``self.n_factors_eff``, ``self.has_PSF``,
   ``self.metad`` (dict with N / L / T / dates / chars keys),
   ``self.PSFcase``. **Divergence from "standard" sklearn**: NO
   ``transform`` / ``fit_transform`` — user brief assumed these; they
   don't exist. Use ``fit`` + Gamma/Factors attrs + ``predict_panel``
   for the panel-prediction path.

4. **Data requirements**: panel data as either ``MultiIndex (entity,
   date)`` DataFrame OR explicit ``indices`` array. Min stable size
   from maintainer's ``test_ipca.py``: 10 firms × 20 years × 2
   characteristics fits cleanly. NaN handling: internal drop/impute
   per ``data_type``. Unbalanced panels supported.

5. **CI install footprint**: ~50-80 MB net-new
   (numba ~50 MB + llvmlite ~30 MB + small progressbar). Substantially
   lighter than Qlib's 150-180 MB.

**Scout strategy**: install the package via the ``[factors]`` extra,
lock the 8-method public-API surface via a hardcoded manifest tuple
(drift detector — fires module-load if upstream renames any method),
expose lightweight ``init_ipca()`` and ``fit_ipca_panel()`` wrappers
for the integration PR to consume. **No production wiring this PR.**

Module placement: ``compute/features/`` per the pre-existing
``.claude/skills/phase-4/ipca-factor-fit/PLAN.md:24`` lock + the
``compute/features/osap_replicate.py`` precedent for library-action
modules. IPCA has no namespace-collision risk (module is
``ipca_factors``, PyPI package is ``ipca``) so the Phase 4j
``qlib_features.py`` workaround doesn't apply here.

**Tenacity NOT applied** — IPCA is pure local sklearn-style
computation; no network retry semantics needed. Mirrors Phase 4j Qlib
divergence from the canonical ``compute/ingest/osap.py:52-56`` retry
decorator pattern.

No vendored data — fitted-estimator pickle cache lives at
``compute/cache/ipca/`` (gitignored via parent glob).
"""

from __future__ import annotations

import logging

from compute import config

logger = logging.getLogger(__name__)

# Re-export the cache path for callers that need the artifacts dir.
IPCA_FITTED_ARTIFACTS_CACHE = config.IPCA_FITTED_ARTIFACTS_CACHE

# Kelly-Pruitt-Su 2019 baseline defaults. K=5 factors + intercept=True
# matches the KPS 2019 RFS replication code. Validated by smoke test
# `test_init_ipca_returns_unfitted_estimator_with_kps_defaults` (NOT
# by module-load assert — defaults are our choice, not an external
# surface contract).
IPCA_DEFAULT_N_FACTORS: int = 5
IPCA_DEFAULT_INTERCEPT: bool = True

# Public-API surface lock — drift detector against upstream `ipca`
# package upgrades. Extracted from wheel source 2026-05-19 (ipca
# 0.6.7); module-load assertion below catches any rename / removal.
# Distinct from `transform` / `fit_transform` (which sklearn estimators
# typically expose) — InstrumentedPCA deliberately omits these per
# investigation #3 in the module docstring.
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

# Module-load invariant: the manifest must match the cardinality
# locked in `compute/config.py::IPCA_PUBLIC_API_METHOD_COUNT`. If the
# scout adds or removes a method here, the config constant must move
# in lockstep — fail fast at import.
assert len(INSTRUMENTED_PCA_PUBLIC_API) == config.IPCA_PUBLIC_API_METHOD_COUNT, (
    f"INSTRUMENTED_PCA_PUBLIC_API has "
    f"{len(INSTRUMENTED_PCA_PUBLIC_API)} entries, expected "
    f"{config.IPCA_PUBLIC_API_METHOD_COUNT} per config"
)
assert len(set(INSTRUMENTED_PCA_PUBLIC_API)) == len(INSTRUMENTED_PCA_PUBLIC_API), (
    "INSTRUMENTED_PCA_PUBLIC_API contains duplicate method names"
)


def init_ipca(
    n_factors: int = IPCA_DEFAULT_N_FACTORS,
    intercept: bool = IPCA_DEFAULT_INTERCEPT,
    **kwargs,
):
    """Return an unfitted ``InstrumentedPCA`` estimator with KPS defaults.

    Idempotent factory wrapper around ``ipca.InstrumentedPCA(...)``. NOT
    tenacity-wrapped — pure local sklearn-style construction, no
    network. Calling this with default args twice returns two distinct
    estimator instances (sklearn pattern, not a singleton).

    Args:
        n_factors: number of latent factors K. Default
            :data:`IPCA_DEFAULT_N_FACTORS` (5, KPS 2019 baseline).
        intercept: whether to include an intercept term in the
            characteristic-loading regression. Default
            :data:`IPCA_DEFAULT_INTERCEPT` (True per KPS 2019).
        **kwargs: forwarded to ``InstrumentedPCA(...)``. Integration
            PR may pass ``alpha`` / ``l1_ratio`` for regularization.

    Returns:
        Unfitted ``ipca.InstrumentedPCA`` instance. Call
        :func:`fit_ipca_panel` to fit against a characteristics
        panel + return series.

    Raises:
        ImportError: if the ``ipca`` package isn't installed (must
            install via the ``[factors]`` extra in ``pyproject.toml``).
    """
    from ipca import InstrumentedPCA

    return InstrumentedPCA(n_factors=n_factors, intercept=intercept, **kwargs)


def fit_ipca_panel(estimator, *, X, y, indices=None, **fit_kwargs):
    """Fit an ``InstrumentedPCA`` estimator against a characteristics panel.

    Forward-compat wrapper around ``estimator.fit(X, y, indices=...)``.
    Returns the fitted estimator (sklearn returns-self convention).
    Integration PR will call this with the 502-ticker × N_dates × L-
    characteristics panel from `compute/scoring/` + selected OSAP/JKP/
    Qlib signals.

    Args:
        estimator: an unfitted ``InstrumentedPCA`` instance (typically
            from :func:`init_ipca`).
        X: characteristics matrix. Either a ``MultiIndex`` DataFrame
            with ``(entity, date)`` index OR a 2-D array; in the array
            case ``indices`` must be provided. Shape
            ``(N entities × T dates, L characteristics)``.
        y: realized returns aligned to ``X``'s row index. Shape
            ``(N × T,)``.
        indices: optional ``(entity, date)`` pairs for array-style
            ``X``. Ignored when ``X`` is a MultiIndex DataFrame.
        **fit_kwargs: forwarded to ``estimator.fit(...)``. Common
            choices: ``PSF`` (pre-specified factors) for the
            "P + L" KPS model variant.

    Returns:
        The same ``estimator`` instance, now fitted. Post-fit
        attributes ``self.Gamma`` (L × K), ``self.Factors`` (K × T),
        and ``self.metad`` dict are populated.

    Raises:
        Whatever ``InstrumentedPCA.fit`` raises (typically ``ValueError``
            on misshapen inputs).
    """
    estimator.fit(X, y, indices=indices, **fit_kwargs)
    return estimator
