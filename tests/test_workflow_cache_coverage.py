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
    config.EDGAR_AMENDMENTS_CACHE_DIR,
    config.EDGAR_LATE_FILINGS_CACHE_DIR,
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


def test_workflow_cache_key_is_v4() -> None:
    """Cache key bumped v3 → v4 in PR 4c.1.

    Rationale: PR 4c extended `_ANNUAL_TAGS` with `stockholders_equity`
    (issue #11 per-year ROE fix). The v3-era `fundamentals_history`
    parquets pre-date that column and silently let `_avg_3y_roe` fall
    back to the legacy single-period path — first post-PR-4c warm run
    showed value_trap_risk count unchanged (197 → 196). Forcing a fresh
    cold fetch via key bump is the established pattern (precedent:
    PR #49 bumped v1 → v2 after audit-#6 `_TTM_*` expansion).

    Bump again to v5 when:
      - any cache directory's parquet/JSON schema changes (column rename,
        column add, shape change), OR
      - `_TTM_*` / `_ANNUAL_TAGS` / `_BALANCE_TAGS` gains a new metric that
        per-cache `_is_fresh()` checks can't detect through filing-date
        staleness alone.
    """
    text = _workflow_text()
    assert "key: cache-v4-" in text, (
        "Workflow cache key must be `cache-v4-${{ ... }}` per PR 4c.1. "
        "Bump to v5 only when a cache directory's *schema* changes or a "
        "new metric is added to `_ANNUAL_TAGS` / `_TTM_*` / `_BALANCE_TAGS`."
    )
