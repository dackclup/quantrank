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
    # S&P 1500 cutover Slice 5 (2026-06-20): universe parquets for sp600 + sp1500
    # must live in the fast-bundle path: blocks so the constituent lists persist
    # across CI runs and avoid re-scraping Wikipedia on every cron.
    config.SP600_UNIVERSE_CACHE,
    config.SP1500_UNIVERSE_CACHE,
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
    """FAST cache key has the full shape ``cache-v11-fast-${{ steps.quarter.outputs.q }}-${{ runner.os }}``
    in BOTH compute-rankings.yml and precache-edgar.yml.

    WHY (WARN 1): the predecessor test only asserted the prefix
    ``key: cache-vN-fast-`` — it would pass if the suffix were reordered
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
        r"key: cache-v11-fast-\$\{\{ steps\.quarter\.outputs\.q \}\}"
        r"-\$\{\{ runner\.os \}\}"
    )
    for workflow in ("compute-rankings.yml", "precache-edgar.yml"):
        text = _workflow_text(workflow)
        assert full_shape_re.search(text), (
            f"{workflow} fast-cache key is missing or has the wrong full shape. "
            f"Expected: ``key: cache-v11-fast-"
            f"${{{{ steps.quarter.outputs.q }}}}-${{{{ runner.os }}}}`` — "
            f"a suffix reorder (e.g., -<os>-<quarter>) would silently break "
            f"exact-key parity between the cron and the Saturday precache."
        )


def test_workflow_fast_cache_key_is_v11() -> None:
    """FAST cache key is `cache-v11-fast-` (S&P 1500 cutover Slice 5 bump).

    Bump history on the fundamentals/prices ("fast", quarter-keyed) bundle:

    - v8 → v9-fast (Issue #385, 2026-06-15): `us-gaap:OilAndGasRevenue`
      added to `_TTM_REVENUE_TAGS` + `_ANNUAL_TAGS["revenue"]` so E&P filers
      (APA, COP, OXY) resolve revenue instead of shipping `revenue=None` — a
      new `_TTM_`/`_ANNUAL_TAGS` metric that per-cache `_is_fresh()` filing-
      date checks can't detect, so the quarter's frozen fast parquets must be
      flushed to repopulate. Bumped in ALL FOUR files (cron / precache /
      backfill / sim).
    - v9 → v10-fast (precache-900 Phase B flip, 2026-06-16): cron-default
      flip sp500 → sp900. The fast bundle's exact-key save-skip means sp400
      fundamentals/prices won't persist via a warm-key precache (save skipped
      on an exact-key hit). The v10 bump forces a cold-seed of the full sp900
      fast bundle on the first post-flip cron so all ~903 tickers warm
      correctly. Also adds universe_sp400-v1.parquet + universe_sp900-v1.parquet
      to the path: blocks so the constituent lists persist across runs.
    - v10 → v11-fast (S&P 1500 cutover Slice 5, 2026-06-20): adds
      universe_sp600-v1.parquet + universe_sp1500-v1.parquet to the path:
      blocks so the sp600/sp1500 constituent lists persist across runs. The
      fast bundle's exact-key save-skip means sp600 fundamentals/prices
      written under a warm v10 sp900 key would be silently dropped; v11
      forces a cold-seed so all ~1500 tickers warm correctly once the sp1500
      dispatch or Slice 7 cron-default flip fires. The cron default STAYS
      sp900 — same mechanism as v9→v10 (#492). Bumped in ALL FOUR files.
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
    - **Bump on universe-expansion that a warm exact-key save-skip would
      prevent from persisting** (sp400/sp500 → sp900 Phase B flip v10;
      sp900 → sp1500 Slice 5 v11).

    Bump again to v12-fast next time any of the four triggers fires —
    in ALL FOUR files at once (compute-rankings / precache-edgar /
    backfill-portfolio / pre-merge-prod-sim; the tri-file pattern became
    quad-file when Issue #249 Option B added the Saturday precache).
    The slow-text bundle (`cache-v5-text-` + run-id key) is governed
    separately — bump it only on a text-cache schema change per the
    workflow comment, and see the lockstep test below.
    """
    text = _workflow_text()
    assert "key: cache-v11-fast-" in text, (
        "compute-rankings.yml FAST cache key must be `cache-v11-fast-${{ ... }}` "
        "(S&P 1500 cutover Slice 5, 2026-06-20). Bump to v12-fast only when a "
        "cache directory's *schema* changes, a new metric is added to `_ANNUAL_TAGS` "
        "/ `_TTM_*` / `_BALANCE_TAGS`, a value-correctness fix lands in a "
        "live-fetch-only path that cache replay would short-circuit past, OR a "
        "universe-expansion makes warm-key save-skip prevent full warming."
    )
    bf_text = _workflow_text("backfill-portfolio.yml")
    assert "cache-v11-fast-" in bf_text, (
        "backfill-portfolio.yml must share the v11-fast key family (aligned in "
        "the S&P 1500 Slice 5 bump so both consumers see the same sp1500 depth)"
    )
    assert "cache-v11-bf-" in bf_text, (
        "backfill-portfolio.yml must SAVE under its own -bf- key (its bundle is "
        "a subset of the cron's — an exact-key save would poison the quarter)"
    )
    sim_text = _workflow_text("pre-merge-prod-sim.yml")
    assert "cache-v11-fast-" in sim_text and "cache-v10-fast-" not in sim_text, (
        "pre-merge-prod-sim.yml mirrors the cron's key family (its own header "
        "comment commands bumping together) — a stale family goes silently cold "
        "after archive eviction"
    )
    pre_text = _workflow_text("precache-edgar.yml")
    assert "key: cache-v11-fast-" in pre_text and "cache-v10-fast-" not in pre_text, (
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


def _job_timeout_minutes(text: str) -> int:
    """Return the first ``timeout-minutes: <N>`` value in a workflow file.

    Plain regex (no PyYAML, per this module's convention). Both the cron and
    the sim declare exactly one timeout-bearing job, so the first match is the
    job budget.
    """
    m = re.search(r"^\s*timeout-minutes:\s*(\d+)\s*$", text, re.MULTILINE)
    assert m, "no `timeout-minutes:` found in workflow text"
    return int(m.group(1))


def test_sim_timeout_at_least_cron_timeout() -> None:
    """The pre-merge sim's job timeout must be >= the weekly cron's.

    WHY (2026-06-13): the sim restores the cron's cache but CANNOT save (it is
    restore-only on a PR branch), so on any cache MISS — which a PR-context run
    can hit even when `main` has a fresh save, because GitHub scopes caches per
    branch — every QR_SKIP_* escape hatch falls through to a cold live EDGAR
    fetch and the sim runs as long as a cold cron. The cron was bumped to 240
    min (the #249 era + the Phase 7.0 folded backtest) but the sim was left at
    90, so sim run #98 was CANCELLED at the 90-min cap mid per-stock write
    (`Cache not found for input keys: cache-v9-fast-2026Q2-Linux, ...`). The
    sim runs FEWER loops than the cron (5 skip vars, no committed output, no
    PIT backtest), so it never NEEDS more than the cron — but it must not be
    LESS, or a legitimately-cold sim (and the S&P 900 pilot's first cold run)
    re-introduces the silent cancellation. This guard fails loudly if a future
    cron timeout bump leaves the sim stranded again.
    """
    sim_timeout = _job_timeout_minutes(_workflow_text("pre-merge-prod-sim.yml"))
    cron_timeout = _job_timeout_minutes(_workflow_text("compute-rankings.yml"))
    assert sim_timeout >= cron_timeout, (
        f"pre-merge-prod-sim.yml timeout-minutes ({sim_timeout}) is below the "
        f"weekly cron's ({cron_timeout}). The sim is restore-only, so a "
        f"cache-MISS run goes fully cold and needs the cron's headroom; a "
        f"shorter budget re-introduces the run #98 90-min cancellation. Raise "
        f"the sim's timeout to >= the cron's (they may be equal)."
    )


def test_sim_restores_both_cron_cache_families() -> None:
    """The pre-merge sim must restore BOTH cron cache bundles by their families.

    WHY (2026-06-13): the cron writes its cache as TWO bundles under DIFFERENT
    keys — the fast bundle (`cache-v9-fast-`) and the slow-text bundle
    (`cache-v5-text-<os>-<run_id>`). The sim originally listed every path under
    the single fast key, so the 5 slow-text paths (edgar_10k_text / edgar_8k /
    osap / amendments / late_filings) were NEVER restored — they live in a
    cache the sim never requested. OSAP therefore cold-downloaded on EVERY sim
    even with QR_SKIP_OSAP=1 (the skip falls through to a live fetch when the
    parquet is absent). The sim must request the slow-text family by prefix
    (it can't exact-hit the cron's run-id key, and it never saves) so both
    bundles restore warm. This guard fails if the slow-text restore is dropped.
    """
    sim_text = _workflow_text("pre-merge-prod-sim.yml")
    # Fast family (already pinned by the v11 test; re-checked here for symmetry).
    assert "cache-v11-fast-" in sim_text, (
        "pre-merge-prod-sim.yml must restore the cron's fast cache family "
        "(`cache-v11-fast-`)."
    )
    # Slow-text family — the bundle the old single-key restore silently dropped.
    assert re.search(r"cache-v\d+-text-\$\{\{ runner\.os \}\}-", sim_text), (
        "pre-merge-prod-sim.yml must ALSO restore the cron's slow-text cache "
        "family (`cache-vN-text-<os>-` prefix) — without it edgar_10k_text / "
        "edgar_8k / osap restore cold every sim and OSAP live-downloads even "
        "under QR_SKIP_OSAP=1 (the run #98 cold-cascade contributor). The sim "
        "restores this family by restore-keys prefix (the cron's save key is "
        "run-id-unique, so there is no stable key to exact-hit)."
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


def test_canary_emits_edgar_8k_ttl_warning() -> None:
    """The canary step emits the Issue #469 edgar_8k TTL-proximity warning in
    BOTH workflows.

    WHY: the byte-equality test above only guarantees the two canary steps
    AGREE — it would stay green if a future refactor dropped the TTL warning
    from BOTH files simultaneously.  This positive teeth-check asserts the
    warning is actually PRESENT, so the #469 observability can't silently
    regress on both sides at once.

    Pinned surface: the ``::warning::edgar_8k cache within 72h of its 144h
    TTL`` literal (the predicted-long-tier2 signal) lives inside the canary
    step of each cache-warming workflow.  The 72h threshold equals
    config.EDGAR_8K_CACHE_TTL_JITTER_SECONDS (widened from 24h on
    2026-06-13 to defeat the weekday-cliff and Sat→Mon re-bunching failure
    modes — see the config comment for the sufficiency analysis).
    """
    warning_literal = "::warning::edgar_8k cache within 72h of its 144h TTL"
    for workflow in _CACHE_WARMING_WORKFLOWS:
        canary = _extract_canary_block(_workflow_text(workflow))
        assert warning_literal in canary, (
            f"{workflow} canary step is missing the Issue #469 edgar_8k "
            f"TTL-proximity warning. Expected the literal "
            f"{warning_literal!r} inside the canary block (it warns when the "
            f"edgar_8k layer's newest file is within 72h of its 144h TTL so the "
            f"~80-min tier2 refetch is predicted, not surprising)."
        )


def test_sp900_universe_parquets_in_fast_path_blocks() -> None:
    """The sp400 + sp900 + sp600 + sp1500 universe parquets are listed in the
    fast-bundle ``path:`` blocks in BOTH cache-warming workflows and in
    pre-merge-prod-sim.yml.

    WHY (precache-900 Phase B flip, 2026-06-16): the sp500-only `universe-v2.parquet`
    was already in the fast bundle. After the flip, the weekday cron also needs
    `universe_sp400-v1.parquet` + `universe_sp900-v1.parquet` to persist across
    runs — without them, the Saturday precache or next cron re-scrapes Wikipedia
    for all ~903 constituent names on every run (the 7-day file-freshness check
    in `compute/ingest/universe.py::get_sp500_constituents`).

    S&P 1500 cutover Slice 5 (2026-06-20) extended this to include
    `universe_sp600-v1.parquet` + `universe_sp1500-v1.parquet` so the small-cap
    constituent list persists across runs once the sp1500 dispatch or Slice 7
    cron-default flip fires. Without them the sp600 Wikipedia scrape would run
    on EVERY cron. The fast-cache key was bumped from v10 → v11 in lockstep.

    Config paths: `config.SP400_UNIVERSE_CACHE`, `config.SP900_UNIVERSE_CACHE`,
    `config.SP600_UNIVERSE_CACHE`, `config.SP1500_UNIVERSE_CACHE`.
    """
    sp400_path = config.SP400_UNIVERSE_CACHE.relative_to(config.PROJECT_ROOT).as_posix()
    sp900_path = config.SP900_UNIVERSE_CACHE.relative_to(config.PROJECT_ROOT).as_posix()
    sp600_path = config.SP600_UNIVERSE_CACHE.relative_to(config.PROJECT_ROOT).as_posix()
    sp1500_path = config.SP1500_UNIVERSE_CACHE.relative_to(config.PROJECT_ROOT).as_posix()

    for workflow in ("compute-rankings.yml", "precache-edgar.yml", "pre-merge-prod-sim.yml"):
        text = _workflow_text(workflow)
        path_blocks = _extract_path_blocks(text)
        for parquet_path in (sp400_path, sp900_path, sp600_path, sp1500_path):
            found = any(
                parquet_path in {line.strip() for line in block.splitlines()}
                for block in path_blocks
            )
            assert found, (
                f"{workflow} is missing `{parquet_path}` inside a ``path: |`` block. "
                f"Add it to the fast-bundle cache step so the sp400/sp900/sp600/sp1500 "
                f"universe parquets persist across runs."
            )


def test_sim_mirrors_cron_universe_default() -> None:
    """pre-merge-prod-sim.yml sets ``QR_UNIVERSE: sp1500`` explicitly to mirror the
    weekday cron's sp1500 default after the S&P 1500 cutover Slice 7 cron-default
    flip (2026-06-20).

    WHY: the cron's QR_UNIVERSE resolves to sp1500 via the ``|| 'sp1500'`` fallback
    (Slice 7, 2026-06-20); compute/config.py keeps its code default as 'sp500' for
    local-dev safety. The sim pins ``QR_UNIVERSE`` explicitly in its ``env:`` block
    (no dispatch input — it's a bare literal) so the composite-score diff it produces
    is against the same sp1500 universe the cron uses — a silent universe mismatch
    would compare apples to oranges (GOTCHAS.md §pre-merge-prod-sim must mirror the
    cron).

    Prior history: Phase B flip (2026-06-16) → sp900; Slice 7 (2026-06-20) → sp1500.
    """
    text = _workflow_text("pre-merge-prod-sim.yml")
    assert "QR_UNIVERSE: sp1500" in text, (
        "pre-merge-prod-sim.yml must set ``QR_UNIVERSE: sp1500`` explicitly in its "
        "``env:`` block to mirror the weekday cron's sp1500 default after the "
        "S&P 1500 cutover Slice 7 cron-default flip (2026-06-20). The compute/"
        "config.py code default is 'sp500' for local-dev safety, so the sim cannot "
        "rely on it. Prior history: Phase B flip (2026-06-16) → sp900; Slice 7 "
        "(2026-06-20) → sp1500."
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


def test_compute_rankings_has_universe_dispatch_input() -> None:
    """compute-rankings.yml exposes the `universe` dispatch input wired to
    QR_UNIVERSE. After the S&P 1500 cutover Slice 7 cron-default flip (2026-06-20)
    the scheduled cron defaults to sp1500; the `|| 'sp1500'` fallback makes the
    cron rank the full S&P 1500 universe (~1500 names) when the schedule trigger
    fires (null inputs).  sp900 and sp500 remain available as manual-dispatch
    options for diagnostics / rollback.

    Prior history: Phase B flip (2026-06-16) moved the default to sp900; Slice 5
    (2026-06-20) added sp1500 as a manual-dispatch option; Slice 7 (2026-06-20)
    moved the default to sp1500.

    WHY: PR 1 added `config.QR_UNIVERSE` (code default sp500) + a midcap coverage
    probe that only fires on sp900+. The Phase B flip moved the WORKFLOW default to
    sp900 so the weekday cron ranked midcaps; the Slice 7 flip moves it to sp1500
    so the cron ranks all ~1500 names. The env-block assignment (not a run-line
    ${{ }}) keeps it injection-safe.
    """
    text = _workflow_text("compute-rankings.yml")
    assert "universe:" in text, "compute-rankings.yml missing the `universe` dispatch input"
    # choices present — all three options must remain available
    for choice in ("- sp500", "- sp900", "- sp1500"):
        assert choice in text, f"`universe` input missing choice {choice!r}"
    # default sp1500 (Slice 7 flip — cron now ranks the full S&P 1500 universe)
    assert "default: sp1500" in text, (
        "`universe` input must default to sp1500 after the S&P 1500 cutover Slice 7 "
        "cron-default flip (2026-06-20). The scheduled cron now permanently ranks the "
        "full S&P 1500 universe (~1500 names: sp500 + sp400 + sp600)."
    )
    # QR_UNIVERSE wired with the sp1500 fallback (schedule trigger has null inputs)
    assert "QR_UNIVERSE: ${{ github.event.inputs.universe || 'sp1500' }}" in text, (
        "compute-rankings.yml must wire QR_UNIVERSE from the universe input with a "
        "`|| 'sp1500'` fallback so the scheduled cron (null inputs) defaults to sp1500 "
        "(S&P 1500 cutover Slice 7, 2026-06-20)"
    )
    # injection-safety: the universe input must NOT be interpolated into a run: line
    assert "${{ github.event.inputs.universe }}" not in text or "run:" not in text.split(
        "${{ github.event.inputs.universe }}"
    )[0][-200:], "universe input must not feed a run: shell line (script-injection)"


def test_precache_has_universe_dispatch_input() -> None:
    """precache-edgar.yml exposes the `universe` dispatch input wired to
    QR_UNIVERSE with a sp1500 fallback after the S&P 1500 cutover Slice 7
    cron-default flip (2026-06-20). The scheduled Saturday precache now warms
    sp1500 by default so it matches the weekday cron's universe and the Monday
    run restores warm. The `|| 'sp1500'` fallback keeps the Saturday run (null
    inputs) on sp1500.  sp900 and sp500 remain available as manual-dispatch
    options for diagnostics / rollback.

    Prior history: Phase B flip (2026-06-16) moved the precache default to sp900;
    Slice 5 (2026-06-20) added sp1500 as a manual-dispatch option; Slice 7
    (2026-06-20) moved the default to sp1500 to match the weekday cron."""
    text = _workflow_text("precache-edgar.yml")
    assert "universe:" in text
    for choice in ("- sp500", "- sp900", "- sp1500"):
        assert choice in text
    # default sp1500 (Slice 7 flip — precache now warms the same universe as the cron)
    assert "default: sp1500" in text, (
        "precache-edgar.yml `universe` input must default to sp1500 after the "
        "S&P 1500 cutover Slice 7 flip (2026-06-20) so the Saturday precache warms "
        "the same universe as the weekday cron"
    )
    assert "QR_UNIVERSE: ${{ github.event.inputs.universe || 'sp1500' }}" in text, (
        "precache-edgar.yml must wire QR_UNIVERSE with a `|| 'sp1500'` fallback "
        "so the scheduled Saturday run (null inputs) defaults to sp1500"
    )
    # injection-safety: the universe input must NOT be interpolated into a run: line
    assert "${{ github.event.inputs.universe }}" not in text or "run:" not in text.split(
        "${{ github.event.inputs.universe }}"
    )[0][-200:], "universe input must not feed a run: shell line (script-injection)"
