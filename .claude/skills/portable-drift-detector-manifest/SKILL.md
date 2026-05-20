---
name: portable-drift-detector-manifest
description: Lock the public-API surface of an external dependency via a
  hardcoded manifest tuple asserted at module load. Catches silent API
  drift on a future minor version bump — a renamed method, a dropped
  attribute, a changed feature-set ordering. Generic — drop-in for any
  project that imports an external library whose API stability isn't
  guaranteed by SemVer. TRIGGER when adopting a new dep whose public API
  the project consumes by name, when the dep's last release is > 1 year
  old (stale-API risk), or when upstream's CHANGELOG history shows
  past breaking changes within a minor version band. SKIP for deps with
  rigorous SemVer + decade-stable APIs (`requests`, `numpy.array`) —
  the manifest is noise.
---

# portable-drift-detector-manifest

A 5-line pattern that converts "we hope upstream doesn't rename
things" into a fail-fast module-load assertion. Portable — no
project-specific business logic.

## Pattern

```python
# In the module that imports the external API:

# Public-API surface lock — drift detector against upstream upgrades.
# Extracted from the dependency's source at adoption time. If a future
# minor releases drops or renames any of these, module load fails fast.
EXTERNAL_API_MANIFEST: tuple[str, ...] = (
    "method_one",
    "method_two",
    "method_three",
    # ... one entry per public method / class / attribute the project
    # consumes by name
)

# Module-load invariant: cardinality + uniqueness.
assert len(EXTERNAL_API_MANIFEST) == EXPECTED_COUNT, (
    f"EXTERNAL_API_MANIFEST drifted: expected {EXPECTED_COUNT}, "
    f"got {len(EXTERNAL_API_MANIFEST)}"
)
assert len(set(EXTERNAL_API_MANIFEST)) == len(EXTERNAL_API_MANIFEST), (
    "EXTERNAL_API_MANIFEST contains duplicate method names"
)
```

Paired with a runtime introspection test that confirms each name
resolves to a callable on the actual class:

```python
def test_external_api_matches_runtime_introspection():
    from external_lib import TheClass
    for name in EXTERNAL_API_MANIFEST:
        assert hasattr(TheClass, name), f"missing: {name}"
        assert callable(getattr(TheClass, name))
```

## Trigger conditions

- Adopting a new dep whose public API the project consumes by name
- The dep's last release is > 1 year old (stale-API risk — older
  packages without recent maintenance can silently drift on the
  next minor)
- Upstream's CHANGELOG shows past breaking changes within a minor
  version band
- The dep doesn't follow SemVer rigorously (most ML / quant
  packages don't)

## Skip conditions

- Deps with rigorous SemVer + decade-stable APIs (`requests`,
  `numpy.array`, stdlib modules)
- Internal libraries within the same monorepo (use direct type
  imports + mypy/pyright)
- The project consumes the dep via a single function call
  (one-method wrappers don't need a manifest)

## What the manifest catches

- **Renamed methods** — `dep.fit()` → `dep.train()` in next minor
- **Dropped methods** — feature removed in a refactor
- **Reordered enum / tuple constants** — when the project uses
  positional indexing
- **Changed default constructor params** — separate test for kwarg
  defaults

## What the manifest does NOT catch

- Method *behavior* changes (same name, different output) — needs
  golden-value test
- Changed exception classes
- Performance regressions
- Deprecation warnings (use `python -W error` in CI for those)

## QuantRank precedents

- `INSTRUMENTED_PCA_PUBLIC_API` (8-method tuple) at
  `compute/features/ipca_factors.py` — locks the
  `ipca` package's `InstrumentedPCA` class against a future minor.
  `ipca` last released 2021-04-22, so the manifest is the only
  affirmative evidence the project won't break on a rogue upstream
  patch
- `ALPHA158_FEATURE_NAMES` (158-name tuple) at
  `compute/ingest/qlib_features.py` — locks the
  Qlib `Alpha158DL` feature ordering, which any blend layer would
  consume by positional index
- Both manifests have an accompanying runtime introspection test
  that catches drift on `pip install --upgrade`
