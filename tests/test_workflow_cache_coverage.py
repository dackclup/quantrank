"""Workflow cache coverage guard (PR 4a — workflow-cache-improvements/PLAN.md).

Asserts that every on-disk cache directory declared in ``compute.config``
is restored by BOTH cache-warming workflows:

  * ``compute-rankings.yml`` — the weekday production cron
  * ``precache-edgar.yml`` — the Saturday off-cycle warmer (Issue #249
    Option B), which must mirror the cron's cache paths + key families
    EXACTLY so that (a) its post-eviction save is restorable by the cron
    and (b) its warm-Saturday pass exact-hits the cron's quarter key and
    no-ops the save

This prevents future contributors from adding a new cache (e.g., Phase 4
``compute/cache/osap/``, ``compute/cache/jkp/``) and silently forgetting
to extend the workflows' ``path:`` blocks — which would force cold
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

import re
from pathlib import Path

import pytest

from compute import config

_WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / ".github" / "workflows"
_WORKFLOW_PATH = _WORKFLOWS_DIR / "compute-rankings.yml"

# Both workflows that restore AND save the compute cache bundles. They must
# stay in lockstep (paths + key families) — see precache-edgar.yml's header
# comment for the exact-key save semantics that depend on it.
_CACHE_WARMING_WORKFLOWS = ("compute-rankings.yml", "precache-edgar.yml")

# Cache locations declared in compute/config.py that the workflows MUST
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
    config.EDGAR_FORM4_CACHE_DIR,
    # OSAP_RETURNS_CACHE is a FILE (osap/returns.parquet); the workflows
    # cache its parent DIR, so assert on that.
    config.OSAP_RETURNS_CACHE.parent,
)

# ---------------------------------------------------------------------------
# Helpers — path-block + canary-block extraction (string/regex only; no PyYAML)
# ---------------------------------------------------------------------------


def _workflow_text(filename: str = "compute-rankings.yml") -> str:
    path = _WORKFLOWS_DIR / filename
    assert path.exists(), f"workflow file missing: {path}"
    return path.read_text(encoding="utf-8")


def _extract_path_blocks(text: str) -> list[str]:
    """Return the raw contents of every ``path: |`` block in *text*.

    WHY: the parametrized path-presence scan (WARN 2) must check that each
    required path lives INSIDE a ``path: |`` block of a cache step, not
    merely anywhere in the file.  The canary step lists every cache layer
    in a shell script — those lines would shadow a removal from the actual
    ``path:`` block, making the scan pass even though the cache step had
    lost the entry.  Whole-line matching within the extracted blocks also
    eliminates the substring-subsumption nit where
    ``compute/cache/fundamentals`` matches inside
    ``compute/cache/fundamentals_history``.

    Strategy: split on ``path: |`` and take everything after each
    occurrence up to the first line that, when stripped, starts with a
    YAML key (``<word>:``) — that signals the end of the scalar block.
    """
    blocks: list[str] = []
    # Each element after splitting on "path: |" is the text that follows
    # that marker; the first element (index 0) is text before the first marker.
    parts = text.split("path: |")
    for part in parts[1:]:
        lines = part.splitlines()
        block_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            # A non-empty line that looks like a YAML key at any indent
            # level signals the end of the block-scalar content.
            if stripped and re.match(r"^[a-zA-Z_-]+:", stripped):
                break
            block_lines.append(line)
        blocks.append("\n".join(block_lines))
    return blocks


def _extract_canary_block(text: str) -> str:
    """Return the canary step block from its ``- name:`` line to the next
    sibling ``- name:`` at the same 6-space indent, trailing whitespace
    stripped.

    WHY: both workflows carry a comment "Keep this step textually IDENTICAL"
    but that was purely a social contract (WARN 3).  Extracting the block
    deterministically lets ``test_canary_step_identical_in_both_workflows``
    enforce byte-equality so any divergence is caught by the test suite
    rather than at the next human review.

    Delimiting strategy (no PyYAML):
      1. Locate the quoted step name literal that appears verbatim in both
         files.
      2. Capture from that line up to (but not including) the next line
         that starts with ``      - name:`` at the same 6-space indent —
         that is the exclusive end boundary of the canary step block.
      3. Strip trailing whitespace so trailing-newline differences between
         files don't produce spurious inequality.
      4. Drop TRAILING blank/comment-only lines from the captured block —
         an inter-step comment that documents the FOLLOWING step (e.g.
         precache's "# The real pipeline, all loops enabled..." banner)
         sits between the canary body and the next ``- name:`` and is NOT
         part of the canary step's lockstep surface; without this, adding
         legitimate documentation for a neighbouring step would force a
         false divergence.
    """
    step_name_literal = (
        '      - name: "Cache restore canary (Issue #287 PR A + #249 Option C)"'
    )
    # Sibling step at the same 6-space indent — exclusive end boundary.
    next_step_re = re.compile(r"^      - name:", re.MULTILINE)

    start_idx = text.find(step_name_literal)
    if start_idx == -1:
        raise AssertionError(
            f"Canary step name not found in workflow text. "
            f"Expected literal: {step_name_literal!r}"
        )

    # Search for the next sibling step AFTER our opening line.
    search_from = start_idx + len(step_name_literal)
    match = next_step_re.search(text, search_from)
    if match:
        block = text[start_idx : match.start()]
    else:
        # Canary is the last step — take to end of file.
        block = text[start_idx:]

    # Step 4: trailing blank / comment-only lines belong to the NEXT step's
    # documentation, not the canary's lockstep surface — drop them.
    lines = block.rstrip().splitlines()
    while lines and (not lines[-1].strip() or lines[-1].lstrip().startswith("#")):
        lines.pop()
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("workflow", _CACHE_WARMING_WORKFLOWS)
@pytest.mark.parametrize("cache_path", _REQUIRED_CACHE_PATHS)
def test_workflow_restores_each_cache_dir(workflow: str, cache_path: Path) -> None:
    """Every config CACHE_* path appears as a whole line inside a ``path: |``
    block in every cache-warming workflow.

    WHY the scope change (WARN 2): the original check used ``repo_relative in
    text`` — a plain substring match across the entire file.  The canary step
    enumerates every cache layer in a shell ``printf`` block, so removing a
    path from the actual ``path: |`` block while the canary still lists it
    would have made the old test pass silently.  Whole-line matching within
    the extracted ``path: |`` blocks eliminates that shadow AND the substring-
    subsumption nit (``fundamentals`` matching inside ``fundamentals_history``).
    """
    text = _workflow_text(workflow)
    # Workflow paths are repo-relative POSIX strings.
    repo_relative = cache_path.relative_to(config.PROJECT_ROOT).as_posix()

    path_blocks = _extract_path_blocks(text)
    assert path_blocks, (
        f"No ``path: |`` blocks found in {workflow} — the cache steps may have "
        f"been restructured; update ``_extract_path_blocks`` accordingly."
    )

    # Whole-line match: the path must appear as a complete trimmed line within
    # at least one ``path: |`` block, not merely as a substring anywhere.
    found = any(
        repo_relative in {line.strip() for line in block.splitlines()}
        for block in path_blocks
    )
    assert found, (
        f"Workflow {workflow} is missing cache path '{repo_relative}' inside a "
        f"``path: |`` block. Add it to the cache steps' `path:` blocks — "
        f"in BOTH cache-warming workflows ({', '.join(_CACHE_WARMING_WORKFLOWS)})."
    )


def test_workflow_fast_cache_key_full_shape_pinned() -> None:
    """FAST cache key has the full shape ``cache-v8-fast-${{ steps.quarter.outputs.q }}-${{ runner.os }}``
    in BOTH compute-rankings.yml and precache-edgar.yml.

    WHY (WARN 1): the predecessor test only asserted the prefix
    ``key: cache-v8-fast-`` — it would pass if the suffix were reordered
    (e.g., ``-<os>-<quarter>``), breaking the exact-key parity that the
    Saturday precache depends on to no-op its save on warm Saturdays.
    The slow-text test already pins the full shape of that key; this test
    mirrors that discipline for the fast-bundle key.

    The ``${{ }}`` delimiters are regex-escaped because they are literal
    characters in the workflow YAML, not regex metacharacters.
    """
    # Full shape: version token + quarter expression + OS expression.
    # Regex-escape ${{ and }} so they match literally in the workflow text.
    full_shape_re = re.compile(
        r"key: cache-v8-fast-\$\{\{ steps\.quarter\.outputs\.q \}\}"
        r"-\$\{\{ runner\.os \}\}"
    )
    for workflow in ("compute-rankings.yml", "precache-edgar.yml"):
        text = _workflow_text(workflow)
        assert full_shape_re.search(text), (
            f"{workflow} fast-cache key is missing or has the wrong full shape. "
            f"Expected: ``key: cache-v8-fast-"
            f"${{{{ steps.quarter.outputs.q }}}}-${{{{ runner.os }}}}`` — "
            f"a suffix reorder (e.g., -<os>-<quarter>) would silently break "
            f"exact-key parity between the cron and the Saturday precache."
        )


def test_workflow_fast_cache_key_is_v8() -> None:
    """FAST cache key is `cache-v8-fast-` (fixed-floor PR).

    Bump history on the fundamentals/prices ("fast", quarter-keyed) bundle:

    - v4 → v5 (Issue #288 follow-up, 2026-05-28): PR #292 + PR #269
      introduced the GOOG/GOOGL per-class XBRL share-override in Branch 3
      of `_build_snapshot`. Branch 3 only executes on live EDGAR fetch —
      `fetch_fundamentals` short-circuits at `_is_fresh()` when the cached
      parquet is < `FUNDAMENTALS_REFETCH_DAYS = 45` days old — so the warm
      cache replayed stale values (cron Run #71, surfaced by
      `multi_class_per_class_attempt_count = 0`).
    - v5 → v6-fast (Phase 7.0 10y rebuild): `PRICES_PERIOD` /
      `ANNUAL_HISTORY_YEARS` → 10y; the period-blind parquets required a
      flush. (The old form of this test kept matching `key: cache-v5-`
      via the SLOW-TEXT key substring after that bump — the guard had
      rotted; it now pins the fast key explicitly.)
    - v7-fast → v8-fast (fixed-floor PR, 2026-06-11): PRICES_FETCH_START
      = 2015-11-29 replaces the rolling period='10y' — v7's period-blind
      parquets are shallow vs the new floor and must be discarded.
    - v6-fast → v7-fast (Issue #374 / PR #456 RATIFY-B, 2026-06-11):
      second firing of taxonomy trigger 3. The RATIFY-B revert makes
      `shares_outstanding` the companyfacts company-total aggregate, but
      warm parquets for the 6 `MULTI_CLASS_OVERCOUNT_ALLOWLIST` tickers
      still carry per-class / cross-contaminated values written by the
      pre-fix code (the #374 CIK-collision). The bump flushes them so the
      next cron cold-fetches and repopulates on the ratified basis.
      `backfill-portfolio.yml` + `pre-merge-prod-sim.yml` move to the same
      `cache-v7-` family so their prefix restore-keys keep matching the
      cron's saves (the sim had drifted to the dead v5 family, which after
      this fix would have produced phantom GOOG/GOOGL movers on every PR).

    Bump rationale taxonomy (PR 4c.1 lineage):

    - Bump on parquet/JSON *schema* change (column rename / add / shape
      change), OR
    - Bump on `_TTM_*` / `_ANNUAL_TAGS` / `_BALANCE_TAGS` new metric that
      per-cache `_is_fresh()` checks can't detect via filing-date alone,
      OR
    - **Bump on *value-correctness* fix inside a live-fetch-only code path
      that cache replay short-circuits past** (Branch 3, both firings).

    Bump again to v9-fast next time any of the three triggers fires —
    in ALL FOUR files at once (compute-rankings / precache-edgar /
    backfill-portfolio / pre-merge-prod-sim; the tri-file pattern became
    quad-file when Issue #249 Option B added the Saturday precache).
    The slow-text bundle (`cache-v5-text-` + run-id key) is governed
    separately — bump it only on a text-cache schema change per the
    workflow comment, and see the lockstep test below.
    """
    text = _workflow_text()
    assert "key: cache-v8-fast-" in text, (
        "compute-rankings.yml FAST cache key must be `cache-v8-fast-${{ ... }}` "
        "(fixed-floor PR, 2026-06-11). Bump to v9-fast only when a cache "
        "directory's *schema* changes, a new metric is added to `_ANNUAL_TAGS` "
        "/ `_TTM_*` / `_BALANCE_TAGS`, OR a value-correctness fix lands in a "
        "live-fetch-only path that cache replay would short-circuit past."
    )
    bf_text = _workflow_text("backfill-portfolio.yml")
    assert "cache-v8-fast-" in bf_text, (
        "backfill-portfolio.yml must share the v8-fast key family (aligned in "
        "the fixed-floor PR so both consumers see the same depth)"
    )
    assert "cache-v8-bf-" in bf_text, (
        "backfill-portfolio.yml must SAVE under its own -bf- key (its bundle is "
        "a subset of the cron's — an exact-key save would poison the quarter)"
    )
    sim_text = _workflow_text("pre-merge-prod-sim.yml")
    assert "cache-v8-fast-" in sim_text and "cache-v7-" not in sim_text, (
        "pre-merge-prod-sim.yml mirrors the cron's key family (its own header "
        "comment commands bumping together) — a stale family goes silently cold "
        "after archive eviction"
    )
    pre_text = _workflow_text("precache-edgar.yml")
    assert "key: cache-v8-fast-" in pre_text and "cache-v7-" not in pre_text, (
        "precache-edgar.yml (Issue #249 Option B) must SAVE under the cron's "
        "EXACT fast key family — exact-key parity is what makes the Saturday "
        "post-eviction save restorable by the weekday cron, and what no-ops "
        "the save on warm Saturdays"
    )


def test_precache_slow_text_family_matches_cron() -> None:
    """SLOW-TEXT cache family is in lockstep between cron and precache.

    Deliberately version-AGNOSTIC (the fast-bundle test above owns
    version-pinning duty): this guards that bumping the text family
    (`cache-vN-text-`) in one file but not the other can't silently split
    the two workflows onto disjoint text caches — the Saturday warmer
    (Issue #249 Option B) would then save snapshots the weekday cron can
    never restore, resurrecting the cold-Tier-2 trap the warmer exists to
    prevent.

    Also pins the run-id-keyed save idiom in BOTH files: a static text key
    would skip the post-job save on hit and freeze the cache into the
    90-day TTL cliff (see the cron's slow-text step comment).
    """
    family = re.compile(r"cache-v(\d+)-text-")
    cron_text = _workflow_text()
    pre_text = _workflow_text("precache-edgar.yml")
    cron_families = set(family.findall(cron_text))
    pre_families = set(family.findall(pre_text))
    assert cron_families, "compute-rankings.yml lost its slow-text cache family"
    assert cron_families == pre_families, (
        f"slow-text cache family drifted: compute-rankings.yml has "
        f"{sorted(cron_families)} but precache-edgar.yml has "
        f"{sorted(pre_families)} — bump `cache-vN-text-` in BOTH files in "
        f"lockstep (precache-edgar.yml header comment)"
    )
    run_id_key = re.compile(
        r"key: cache-v\d+-text-\$\{\{ runner\.os \}\}-\$\{\{ github\.run_id \}\}"
    )
    for name, text in (("compute-rankings.yml", cron_text),
                       ("precache-edgar.yml", pre_text)):
        assert run_id_key.search(text), (
            f"{name} must SAVE the slow-text bundle under a run-id key "
            f"(`cache-vN-text-<os>-<run_id>`) — a static key skips the "
            f"post-job save on hit and freezes the text cache into the "
            f"90-day TTL cliff"
        )


def test_canary_step_identical_in_both_workflows() -> None:
    """The cache-restore canary step body is byte-identical in both workflows.

    WHY (WARN 3): both files carry a comment "Keep this step textually
    IDENTICAL" but a comment-only invariant is unenforceable.  This test
    extracts the canary block from each workflow by its quoted step name and
    asserts equality so any divergence (added line, changed path, different
    warning threshold) is caught immediately rather than at the next review.

    The block delimiter is the next ``      - name:`` line at the same
    6-space indent — deterministic and immune to internal whitespace changes
    inside the block body.  See ``_extract_canary_block`` for full rationale.
    """
    cron_text = _workflow_text("compute-rankings.yml")
    pre_text = _workflow_text("precache-edgar.yml")

    cron_canary = _extract_canary_block(cron_text)
    pre_canary = _extract_canary_block(pre_text)

    assert cron_canary == pre_canary, (
        "The cache-restore canary step has diverged between compute-rankings.yml "
        "and precache-edgar.yml. Edit BOTH files to restore byte-equality. "
        "Diff (first differing line index):\n"
        + _first_diff(cron_canary, pre_canary)
    )


def _first_diff(a: str, b: str) -> str:
    """Return a short diagnostic string showing the first differing line."""
    a_lines = a.splitlines()
    b_lines = b.splitlines()
    for i, (la, lb) in enumerate(zip(a_lines, b_lines, strict=False)):
        if la != lb:
            return f"  line {i}: cron={la!r}\n  line {i}: pre ={lb!r}"
    if len(a_lines) != len(b_lines):
        return (
            f"  compute-rankings.yml has {len(a_lines)} lines, "
            f"precache-edgar.yml has {len(b_lines)} lines"
        )
    return "  (no difference found — strings are equal)"
