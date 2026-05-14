"""Workflow cache coverage guard (PR 4a — workflow-cache-improvements/PLAN.md).

Asserts that every on-disk cache directory declared in ``compute.config``
is restored by the ``compute-rankings.yml`` workflow's cache step. This
prevents future contributors from adding a new cache (e.g., Phase 4
``compute/cache/osap/``, ``compute/cache/jkp/``) and silently forgetting
to extend the workflow's ``path:`` block — which would force cold
re-fetches every weekly run and erase the perf win.

The check is a plain string scan, not YAML parsing, because:
  * PyYAML isn't a project dependency
  * The cache step is a single block — substring containment is
    unambiguous
  * False positives (path matched but not under the cache step) would
    require contortions to construct; future maintainers can refactor
    this test if the workflow layout changes
"""

from __future__ import annotations

from pathlib import Path

import pytest

from compute import config

_WORKFLOW_PATH = (
    Path(__file__).resolve().parent.parent
    / ".github"
    / "workflows"
    / "compute-rankings.yml"
)

# Cache locations declared in compute/config.py that the workflow MUST
# preserve across CI runs. Adding a new entry to compute.config (e.g.,
# Phase 4 OSAP / JKP parquet caches) requires extending both this list
# AND the workflow YAML — this test fails loudly if they fall out of
# sync.
_REQUIRED_CACHE_PATHS = (
    config.FUNDAMENTALS_CACHE_DIR,
    config.FUNDAMENTALS_HISTORY_CACHE_DIR,
    config.PRICES_CACHE_DIR,
    config.UNIVERSE_CACHE,
    config.EDGAR_8K_CACHE_DIR,
    config.EDGAR_10K_TEXT_CACHE_DIR,
    config.YFINANCE_INFO_CACHE_DIR,
)


def _workflow_text() -> str:
    assert _WORKFLOW_PATH.exists(), f"workflow file missing: {_WORKFLOW_PATH}"
    return _WORKFLOW_PATH.read_text(encoding="utf-8")


@pytest.mark.parametrize("cache_path", _REQUIRED_CACHE_PATHS)
def test_workflow_restores_each_cache_dir(cache_path: Path) -> None:
    """Every config CACHE_* path is restored by compute-rankings.yml."""
    text = _workflow_text()
    # Workflow paths are repo-relative POSIX strings.
    repo_relative = cache_path.relative_to(config.PROJECT_ROOT).as_posix()
    assert repo_relative in text, (
        f"Workflow {_WORKFLOW_PATH.name} is missing cache path "
        f"'{repo_relative}'. Add it to the `Restore compute caches` "
        f"step's `path:` block."
    )


def test_workflow_cache_key_is_v3() -> None:
    """PR 4a bumped the atomic-rotation key from v2 → v3.

    If this assertion fails, either the key got rolled back (perf
    regression — partial restore-key matches resurrect stale state) or
    a schema-changing PR forgot to bump to v4. Both warrant explicit
    review.
    """
    text = _workflow_text()
    assert "key: cache-v3-" in text, (
        "Workflow cache key must be `cache-v3-${{ ... }}` per PR 4a. "
        "Bump to v4 only when a cache directory's *schema* changes "
        "(parquet column rename, JSON shape change); value drift is "
        "handled by per-cache `_is_fresh()` checks."
    )
