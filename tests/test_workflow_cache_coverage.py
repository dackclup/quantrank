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


def test_workflow_cache_key_is_v5() -> None:
    """Cache key bumped v4 → v5 in Issue #288 follow-up PR (2026-05-28).

    Rationale: PR #292 (`e9aaab31`, 2026-05-28) + PR #269 introduced the
    GOOG/GOOGL per-class XBRL share-override at
    `compute/ingest/fundamentals.py:1043-1067` (Branch 3 of `_build_snapshot`).
    Branch 3 only executes on live EDGAR fetch — `fetch_fundamentals`
    short-circuits at `_is_fresh()` (line 1292) when cached parquet age
    by `latest_filed_date` < `FUNDAMENTALS_REFETCH_DAYS = 45`. The warm
    cache replayed pre-PR-#292 aggregate `shares_outstanding = 12.116B`
    for GOOG / GOOGL on cron Run #71 (`368dccd9`, 2026-05-28 08:44 UTC),
    surfaced by the PR #292 Rule 18 disambiguator showing
    `multi_class_per_class_attempt_count = 0`. Cache-key bump flushes
    stale parquets so Branch 3 exercises on the next live fetch.
    Established v3→v4 precedent (PR 4c.1) + v1→v2 precedent (PR #49).

    Bump rationale taxonomy (introduced this PR, expanded from PR 4c.1):

    - Bump on parquet/JSON *schema* change (column rename / add / shape
      change), OR
    - Bump on `_TTM_*` / `_ANNUAL_TAGS` / `_BALANCE_TAGS` new metric that
      per-cache `_is_fresh()` checks can't detect via filing-date alone,
      OR
    - **Bump on *value-correctness* fix inside a live-fetch-only code path
      that cache replay short-circuits past** (e.g., the per-class XBRL
      share-override Branch 3 — the fix code is correct but never reaches
      execution on warm-cache crons).

    Bump again to v6 next time any of the three triggers fires.
    """
    text = _workflow_text()
    assert "key: cache-v5-" in text, (
        "Workflow cache key must be `cache-v5-${{ ... }}` per Issue #288 "
        "follow-up (2026-05-28). Bump to v6 only when a cache directory's "
        "*schema* changes, a new metric is added to `_ANNUAL_TAGS` / "
        "`_TTM_*` / `_BALANCE_TAGS`, OR a value-correctness fix lands in a "
        "live-fetch-only path that cache replay would short-circuit past."
    )
