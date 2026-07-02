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
#
# ``precache-broad-universe.yml`` (Phase 9.3 gate-C1 fix, 2026-07-02) is
# DELIBERATELY EXCLUDED from this tuple — same precedent as
# ``backfill-portfolio.yml`` / ``pre-merge-prod-sim.yml`` / ``backfill-
# warehouse.yml``, none of which are in ``_CACHE_WARMING_WORKFLOWS`` either.
# Its save-key strategy is fundamentally different from the two canonical
# workflows' EXACT-KEY parity contract this tuple's tests enforce: every
# job in that workflow SAVES under a unique per-job/per-run "-broad-"
# namespaced key (never the bare canonical key), by design — see that
# workflow's own dedicated tests below
# (``test_precache_broad_universe_*``), which check the properties that
# actually matter for ITS strategy instead of the exact-key-parity
# properties above, which do not apply to it.
_CACHE_WARMING_WORKFLOWS = ("compute-rankings.yml", "precache-edgar.yml")

# The three workflows this PR (Phase 9.3 gate-C1 fix) is responsible for
# keeping at-or-under GitHub Actions' hard 6-hour (360-minute) per-job
# ceiling: the two files whose `timeout-minutes:` were LOWERED to 360 in
# this PR (they were previously set ABOVE the unmovable hard cap — dead
# configuration that masked the real ceiling) plus the new 4-job split
# workflow, whose whole reason to exist is respecting that same cap.  Used
# by the gate-C1 regression ratchet
# (``test_gate_c1_workflows_at_or_under_six_hour_hard_cap``) below.
#
# Deliberately NOT scope-widened to EVERY timeout-bearing workflow in the
# repo: ``pre-merge-prod-sim.yml`` still declares `timeout-minutes: 420`
# (also technically unreachable past the same 360-min hard cap, but fixing
# that value is OUT OF SCOPE for this PR — only its stale numeric comment
# was corrected here; see that workflow's own timeout comment). Widening
# this tuple to include it would make this new ratchet fail immediately on
# a PRE-EXISTING, not-this-PR's-doing value. ``backfill-portfolio.yml``
# (120) and ``backfill-warehouse.yml`` (300) already comply but are also
# left out of this specific PR's ratchet scope — narrower is more honest
# here than implying this PR audited every workflow in the repo.
_GATE_C1_FIXED_WORKFLOWS = (
    "compute-rankings.yml",
    "precache-edgar.yml",
    "precache-broad-universe.yml",
)

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
    """FAST cache key has the full shape ``cache-v12-fast-${{ steps.quarter.outputs.q }}-${{ runner.os }}``
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
        r"key: cache-v12-fast-\$\{\{ steps\.quarter\.outputs\.q \}\}"
        r"-\$\{\{ runner\.os \}\}"
    )
    for workflow in ("compute-rankings.yml", "precache-edgar.yml"):
        text = _workflow_text(workflow)
        assert full_shape_re.search(text), (
            f"{workflow} fast-cache key is missing or has the wrong full shape. "
            f"Expected: ``key: cache-v12-fast-"
            f"${{{{ steps.quarter.outputs.q }}}}-${{{{ runner.os }}}}`` — "
            f"a suffix reorder (e.g., -<os>-<quarter>) would silently break "
            f"exact-key parity between the cron and the Saturday precache."
        )


def test_workflow_fast_cache_key_is_v12() -> None:
    """FAST cache key is `cache-v12-fast-` (Phase 9.3 runtime pre-req bump).

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
    - v11 → v12-fast (Phase 9.3 runtime pre-req, 2026-06-29): adds
      `compute/cache/broad_universe-v1.parquet` to the path: blocks in the
      three warming workflows (compute-rankings / precache-edgar /
      pre-merge-prod-sim) so the Broad Investable US candidate parquet
      (Phase 9.1, 7-day TTL, ~3,545 names) persists across runs. The
      fast bundle's exact-key save-skip means a warm v11 bundle would
      silently omit this new path; v12 forces a cold-seed so all four
      workflows see the new path correctly. Bumped in ALL FOUR files.
      Also adds `broad_investable_us` to dispatch options in compute-rankings
      and precache-edgar. The `backfill-portfolio.yml` uses save key
      `cache-v12-bf-` (distinct from `-fast-` to avoid poisoning the
      quarter's bundle with an impoverished subset).
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
    - **Bump on new cache path added to the fast-bundle** that a warm
      exact-key save would silently omit (broad_universe-v1.parquet v12).

    Bump again to v13-fast next time any of the four triggers fires —
    in ALL FOUR files at once (compute-rankings / precache-edgar /
    backfill-portfolio / pre-merge-prod-sim; the tri-file pattern became
    quad-file when Issue #249 Option B added the Saturday precache).
    The slow-text bundle (`cache-v5-text-` + run-id key) is governed
    separately — bump it only on a text-cache schema change per the
    workflow comment, and see the lockstep test below.
    """
    text = _workflow_text()
    assert "key: cache-v12-fast-" in text, (
        "compute-rankings.yml FAST cache key must be `cache-v12-fast-${{ ... }}` "
        "(Phase 9.3 runtime pre-req, 2026-06-29). Bump to v13-fast only when a "
        "cache directory's *schema* changes, a new metric is added to `_ANNUAL_TAGS` "
        "/ `_TTM_*` / `_BALANCE_TAGS`, a value-correctness fix lands in a "
        "live-fetch-only path that cache replay would short-circuit past, OR a "
        "universe-expansion makes warm-key save-skip prevent full warming."
    )
    bf_text = _workflow_text("backfill-portfolio.yml")
    assert "cache-v12-fast-" in bf_text, (
        "backfill-portfolio.yml must share the v12-fast key family (aligned in "
        "the Phase 9.3 bump so both consumers see the broad_universe parquet path)"
    )
    assert "cache-v12-bf-" in bf_text, (
        "backfill-portfolio.yml must SAVE under its own -bf- key (its bundle is "
        "a subset of the cron's — an exact-key save would poison the quarter)"
    )
    sim_text = _workflow_text("pre-merge-prod-sim.yml")
    assert "cache-v12-fast-" in sim_text and "cache-v11-fast-" not in sim_text, (
        "pre-merge-prod-sim.yml mirrors the cron's key family (its own header "
        "comment commands bumping together) — a stale family goes silently cold "
        "after archive eviction"
    )
    pre_text = _workflow_text("precache-edgar.yml")
    assert "key: cache-v12-fast-" in pre_text and "cache-v11-fast-" not in pre_text, (
        "precache-edgar.yml (Issue #249 Option B) must SAVE under the cron's "
        "EXACT fast key family — exact-key parity is what makes the Saturday "
        "post-eviction save restorable by the weekday cron, and what no-ops "
        "the save on warm Saturdays"
    )
    wh_text = _workflow_text("backfill-warehouse.yml")
    assert "cache-v12-fast-" in wh_text and "cache-v11-fast-" not in wh_text, (
        "backfill-warehouse.yml restore-keys must reference the v12-fast family "
        "(Phase 9.3 bump, 2026-06-29) so the warehouse backfill can borrow a warm "
        "v12 fast-bundle that includes broad_universe-v1.parquet. A stale v11 "
        "reference silently misses the new path and falls back to a cold refetch. "
        "The save key stays -whbf- (subset isolation) but restore-keys must track "
        "the current fast family in lockstep."
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
    keys — the fast bundle (`cache-v12-fast-`) and the slow-text bundle
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
    # Fast family (already pinned by the v12 test; re-checked here for symmetry).
    assert "cache-v12-fast-" in sim_text, (
        "pre-merge-prod-sim.yml must restore the cron's fast cache family "
        "(`cache-v12-fast-`)."
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

    Pinned surface: the ``::warning::edgar_8k cache within 96h of its 144h
    TTL`` literal (the predicted-long-tier2 signal) lives inside the canary
    step of each cache-warming workflow.  The 96h threshold equals
    config.EDGAR_8K_CACHE_TTL_JITTER_SECONDS (widened from 72h to 96h in
    Phase 9.3, 2026-06-29, to cover the full Sat 08:00 → Wed 08:00 UTC spread
    window at ~3,545 broad-investable-US names — see the config comment for
    the sufficiency analysis).
    """
    warning_literal = "::warning::edgar_8k cache within 96h of its 144h TTL"
    for workflow in _CACHE_WARMING_WORKFLOWS:
        canary = _extract_canary_block(_workflow_text(workflow))
        assert warning_literal in canary, (
            f"{workflow} canary step is missing the Issue #469 edgar_8k "
            f"TTL-proximity warning. Expected the literal "
            f"{warning_literal!r} inside the canary block (it warns when the "
            f"edgar_8k layer's newest file is within 96h of its 144h TTL so the "
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


def test_sim_pins_sp500_universe_per_616_exception() -> None:
    """pre-merge-prod-sim.yml pins ``QR_UNIVERSE: sp500`` — the #616 exception to the
    "sim mirrors the cron" invariant (2026-06-30).

    WHY: the weekday cron ranks the full sp1500, but a cold sp1500 sim cold-fetches
    ~1500 names over ~3.6h and intermittently trips the ~4h hosted-runner stability
    ceiling ("runner lost communication", #616). The sim therefore pins sp500
    (~43min cold) — it still fetches live (a REAL composite-score diff on the
    sp500 ∩ committed-main intersection), but the smaller universe stays under the
    ceiling. The skip-live-fetch fix (#616 Option 4a, `QR_SIM_NO_LIVE_FETCH`) was
    REVERTED: on a full cold cache miss it suppressed all prices → 0 tickers <
    MIN_VALID_TICKERS=100 → compute abort (no output), strictly worse than a slow
    completion. TRADEOFF: sp400/sp600 ingest-specific regressions aren't exercised
    by the sim (the cron + post-cron audits cover them; the sim is non-required).

    This is the re-inflation ratchet for the #616 decision — flipping the sim back
    to sp1500 must be a deliberate, documented choice (re-trips the runner ceiling).

    Prior history: Phase B flip (2026-06-16) → sp900; Slice 7 (2026-06-20) → sp1500;
    #616 (2026-06-30) → sp500 (runner-ceiling exception).
    """
    text = _workflow_text("pre-merge-prod-sim.yml")
    assert "QR_UNIVERSE: sp500" in text, (
        "pre-merge-prod-sim.yml must pin ``QR_UNIVERSE: sp500`` (the #616 exception) "
        "so a cold sim stays under the ~4h hosted-runner ceiling. A cold sp1500 sim "
        "(~3.6h) intermittently trips the runner-communication-loss limit; sp500 cold "
        "is ~43min. Flipping back to sp1500 re-introduces #616."
    )
    assert "QR_UNIVERSE: sp1500" not in text, (
        "pre-merge-prod-sim.yml must NOT pin sp1500 — that re-trips the #616 "
        "hosted-runner ceiling. Use sp500 (the documented exception)."
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


def test_precache_edgar_no_longer_offers_broad_investable_us_dispatch_option() -> None:
    """precache-edgar.yml's `universe` dispatch no longer offers
    `broad_investable_us` as a choice (Phase 9.3 gate-C1 fix, 2026-07-02).

    WHY: a single-job cold `universe: broad_investable_us` dispatch on this
    workflow was CANCELLED at GitHub Actions' 6-hour per-job hard cap with
    no cache saved. Broad-universe precaching moved to the dedicated
    ``precache-broad-universe.yml`` 4-job split; offering the option here
    would let an operator re-trigger the exact failure mode this PR fixes.
    sp500/sp900/sp1500 remain (all fit comfortably in one job).

    Matches on the literal YAML list-item bullet (``- broad_investable_us``
    at the same indent as the other choices), NOT a bare substring check —
    the string ``broad_investable_us`` legitimately still appears elsewhere
    in this file's descriptive comments (explaining WHERE the option went),
    so a naive ``"broad_investable_us" not in text`` assertion would be a
    false positive.
    """
    text = _workflow_text("precache-edgar.yml")
    assert "          - broad_investable_us" not in text, (
        "precache-edgar.yml must NOT offer `broad_investable_us` as a `universe` "
        "dispatch choice — it belongs to the dedicated "
        "precache-broad-universe.yml 4-job split (Phase 9.3 gate-C1 fix)."
    )
    # The three that DO fit in one job remain.
    for choice in ("- sp500", "- sp900", "- sp1500"):
        assert choice in text, f"precache-edgar.yml `universe` input missing choice {choice!r}"


def test_compute_rankings_still_offers_broad_investable_us_dispatch_option() -> None:
    """compute-rankings.yml's `universe` dispatch KEEPS `broad_investable_us`
    (Phase 9.3 gate-C1 fix, 2026-07-02) — this is the dedicated, deliberate
    asymmetry vs. precache-edgar.yml: the WARM ranked run still dispatches
    through this workflow; only the COLD precaching moved to
    precache-broad-universe.yml. Losing this option here would silently
    remove the only way to actually RANK the broad-investable-US universe.
    """
    text = _workflow_text("compute-rankings.yml")
    assert "          - broad_investable_us" in text, (
        "compute-rankings.yml must KEEP `broad_investable_us` as a `universe` "
        "dispatch choice — only the COLD precaching moved to "
        "precache-broad-universe.yml; the warm RANKED dispatch still lives here."
    )


def _all_job_timeout_minutes(text: str) -> list[int]:
    """Return every ``timeout-minutes: <N>`` value in a workflow file (job-level
    and step-level alike — unlike ``_job_timeout_minutes``, which returns only
    the first). Used by the gate-C1 ratchet, which must check ALL FOUR jobs in
    ``precache-broad-universe.yml``, not just the first.
    """
    return [int(m) for m in re.findall(r"^\s*timeout-minutes:\s*(\d+)\s*$", text, re.MULTILINE)]


def test_gate_c1_workflows_at_or_under_six_hour_hard_cap() -> None:
    """Every `timeout-minutes:` value in the 3 gate-C1-fixed workflows is
    <= 360 — GitHub Actions' HARD, unmovable 6-hour per-job ceiling.

    WHY (Phase 9.3 gate-C1, 2026-07-02): `compute-rankings.yml` and
    `precache-edgar.yml` previously declared `timeout-minutes: 420` / `540`
    — both ABOVE the hard cap, which is dead configuration: GitHub silently
    clamps the actual enforcement to 360 regardless of what YAML says, so
    the visible number lied about the real ceiling. This was discovered
    when a single-job cold `universe: broad_investable_us` dispatch was
    CANCELLED at 360 min with no cache saved (the gate-C1 finding). Per
    CLAUDE.md's error->regression-ratchet convention, this mechanical,
    structural invariant ("every job timeout must be a REACHABLE number")
    is converted into a deterministic guard here, in the same PR that fixed
    the two stale values and introduced the new 4-job workflow whose own
    ENTIRE PURPOSE is fitting under this exact cap.

    Deliberately scoped to `_GATE_C1_FIXED_WORKFLOWS` only — see that
    tuple's comment for why `pre-merge-prod-sim.yml` (still 420, a
    pre-existing and out-of-this-PR's-scope value) is excluded.
    """
    for workflow in _GATE_C1_FIXED_WORKFLOWS:
        text = _workflow_text(workflow)
        timeouts = _all_job_timeout_minutes(text)
        assert timeouts, f"{workflow}: no `timeout-minutes:` found at all"
        for t in timeouts:
            assert t <= 360, (
                f"{workflow} declares timeout-minutes: {t}, which is ABOVE "
                f"GitHub Actions' hard 6-hour (360-minute) per-job ceiling. "
                f"A value above 360 is dead configuration — GitHub silently "
                f"clamps enforcement to 360 regardless, exactly the gate-C1 "
                f"finding (a single-job cold broad-universe dispatch was "
                f"CANCELLED at the real 360-min cap with NO cache saved, "
                f"despite `timeout-minutes: 540` implying much more headroom)."
            )


def test_precache_broad_universe_is_dispatch_only_no_schedule() -> None:
    """precache-broad-universe.yml has NO `schedule:` trigger — it is an
    occasional, manually-triggered cold-warming pass, not a recurring cron
    (unlike precache-edgar.yml's Saturday schedule).
    """
    text = _workflow_text("precache-broad-universe.yml")
    assert "workflow_dispatch:" in text, (
        "precache-broad-universe.yml must expose a workflow_dispatch trigger"
    )
    # Match the STRUCTURED `on:`-block trigger key (2-space indent, per this
    # repo's YAML style — see `schedule:` under `on:` in precache-edgar.yml),
    # NOT a bare substring: this file's own header comment legitimately says
    # "deliberately NO `schedule:` trigger" (discussing the absence), and a
    # naive `"schedule:" not in text` check would trip on that comment text.
    assert "\n  schedule:\n" not in text, (
        "precache-broad-universe.yml must NOT declare a `schedule:` trigger — "
        "it is a manually-triggered, occasional cold-warming pass, not a "
        "recurring cron. A schedule here would repeatedly re-run an ~hours-long "
        "4-job EDGAR crawl with no corresponding consumer."
    )


def test_precache_broad_universe_concurrency_group_matches_canonical() -> None:
    """precache-broad-universe.yml joins the SAME `edgar-cache-writers`
    concurrency group as compute-rankings.yml / precache-edgar.yml, so it
    never races either for the cache-write surface.
    """
    text = _workflow_text("precache-broad-universe.yml")
    assert "group: edgar-cache-writers" in text
    assert "cancel-in-progress: false" in text, (
        "must queue (not cancel) a concurrent run — a cancelled run must "
        "still eventually run, never silently disappear"
    )


def test_precache_broad_universe_needs_chain_is_sequential() -> None:
    """The 4 jobs form a strict LINEAR `needs:` chain (job2->job1,
    job3->job2, job4->job3) — never parallel.

    WHY: running the jobs in parallel would risk amplifying the sustained
    EDGAR request rate beyond what each stage's timeout budget assumes (a
    budget derived from running ALONE), and the whole point of the split is
    to stay a well-behaved, serialized, single cache-writing sequence — the
    same invariant `concurrency: group: edgar-cache-writers` enforces
    against the OTHER cache-writing workflows.
    """
    text = _workflow_text("precache-broad-universe.yml")
    # Plain-regex parse (module convention — no PyYAML dependency). Job
    # blocks are 2-space-indented `<job-id>:` lines directly under `jobs:`;
    # split on that boundary FIRST so each block's `needs:` search cannot
    # bleed into a LATER sibling job (a lazy single-pass regex without this
    # boundary would incorrectly attribute a later job's `needs:` line back
    # to an earlier job that has none — caught while writing this test).
    job_start_re = re.compile(r"^  (\S+):\s*$", re.MULTILINE)
    starts = list(job_start_re.finditer(text))
    assert len(starts) == 4, f"expected exactly 4 top-level jobs, found {[m.group(1) for m in starts]!r}"

    blocks: dict[str, str] = {}
    for i, m in enumerate(starts):
        job_id = m.group(1)
        block_start = m.end()
        block_end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        blocks[job_id] = text[block_start:block_end]

    needs_re = re.compile(r"^\s*needs:\s*(\S+)\s*$", re.MULTILINE)

    def _needs_of(job_id: str) -> str | None:
        m = needs_re.search(blocks[job_id])
        return m.group(1) if m else None

    assert _needs_of("price-screen") is None, "price-screen (job 1) must have no `needs:` at all"
    assert _needs_of("fundamentals-history") == "price-screen", (
        f"fundamentals-history must declare `needs: price-screen`, "
        f"found {_needs_of('fundamentals-history')!r}"
    )
    assert _needs_of("form4") == "fundamentals-history", (
        f"form4 must declare `needs: fundamentals-history`, found {_needs_of('form4')!r}"
    )
    assert _needs_of("tier2") == "form4", f"tier2 must declare `needs: form4`, found {_needs_of('tier2')!r}"


def test_precache_broad_universe_save_keys_are_broad_namespaced_and_unique() -> None:
    """Every cache `key:` (the SAVE key) in precache-broad-universe.yml is
    `-broad-`-namespaced, includes `${{ github.run_id }}` + a per-job label,
    and NEVER equals the bare canonical key literal used by
    compute-rankings.yml / precache-edgar.yml.

    WHY (the exact-key-skip-save trap): `actions/cache` SKIPS the post-job
    save when the computed `key:` exact-hits an existing cache entry. If any
    job here saved under the bare canonical key (or a key some EARLIER job
    in the SAME run just saved), its own contribution would silently vanish
    — the same class of bug as the #471 frozen-fast-cache gotcha. Using a
    `-broad-<run_id>-<job label>` key guarantees the exact key has NEVER
    existed before, so the save is NEVER skipped.
    """
    text = _workflow_text("precache-broad-universe.yml")
    # `.+` (not `\S+`) because the key value contains `${{ github.run_id }}`
    # — an internal-space interpolation — so a whitespace-stopped token
    # would truncate mid-key and never reach the trailing newline anchor.
    save_key_re = re.compile(r"^\s*key: (cache-v.+)$", re.MULTILINE)
    save_keys = save_key_re.findall(text)
    assert len(save_keys) == 4, f"expected exactly 4 cache SAVE keys (one per job), found {save_keys!r}"

    canonical_fast = "cache-v12-fast-${{ steps.quarter.outputs.q }}-${{ runner.os }}"
    canonical_slow = "cache-v5-text-${{ runner.os }}-${{ github.run_id }}"
    for key in save_keys:
        assert key != canonical_fast, (
            f"SAVE key {key!r} must never equal the bare canonical fast key "
            f"{canonical_fast!r} — that would poison the sp1500 bundle and/or "
            f"trip the exact-key-skip-save trap."
        )
        assert key != canonical_slow, (
            f"SAVE key {key!r} must never equal the bare canonical slow-text key "
            f"{canonical_slow!r}."
        )
        assert "-broad-" in key, f"SAVE key {key!r} must be namespaced with '-broad-'"
        assert "${{ github.run_id }}" in key, (
            f"SAVE key {key!r} must include ${{{{ github.run_id }}}} so it is "
            f"unique per workflow run (never re-used, so the save is never skipped)"
        )
    # Each job's key carries its own distinguishing label, so jobs never
    # collide with EACH OTHER's save key within the same run either.
    assert save_keys == sorted(set(save_keys)) or len(set(save_keys)) == 4, (
        f"all 4 SAVE keys must be pairwise distinct, found {save_keys!r}"
    )
    for job_label in ("job1", "job2", "job3", "job4"):
        assert any(key.endswith(job_label) for key in save_keys), (
            f"no SAVE key ends with the expected per-job label {job_label!r}: {save_keys!r}"
        )


def test_precache_broad_universe_restore_keys_fall_back_to_canonical() -> None:
    """Every cache step's `restore-keys:` include the broad-namespaced
    quarter/os prefix FIRST, then fall back to the CANONICAL prefix the
    weekday cron / Saturday precache maintain — so a first-ever run (no
    prior broad-namespaced save yet) still inherits sp1500 warmth for the
    survivor-set overlap, and a later run inherits ITS OWN prior warm state.
    """
    text = _workflow_text("precache-broad-universe.yml")
    # Fast-bundle jobs (price-screen, fundamentals-history).
    assert "cache-v12-fast-${{ steps.quarter.outputs.q }}-broad-\n" in text, (
        "fast-bundle cache steps must restore the broad-namespaced quarter "
        "prefix (no run-id/job suffix) so THIS run's earlier jobs' saves are "
        "picked up by prefix match"
    )
    assert "cache-v12-fast-${{ steps.quarter.outputs.q }}-\n" in text, (
        "fast-bundle cache steps must ALSO restore the CANONICAL quarter "
        "prefix as a fallback, inheriting sp1500 warmth for the survivor-set "
        "overlap on a first-ever run"
    )
    # Slow-text-bundle jobs (form4, tier2).
    assert "cache-v5-text-${{ runner.os }}-broad-\n" in text, (
        "slow-text-bundle cache steps must restore the broad-namespaced "
        "os prefix (no run-id/job suffix)"
    )
    assert "cache-v5-text-${{ runner.os }}-\n" in text, (
        "slow-text-bundle cache steps must ALSO restore the CANONICAL "
        "os prefix as a fallback, inheriting the cron's warm Form-4/tier2 cache"
    )
    # Ordering: within each restore-keys block, the broad-namespaced prefix
    # must come BEFORE the canonical one (actions/cache tries restore-keys
    # in order; the more-specific/fresher entry should win first).
    fast_block_re = re.compile(
        r"restore-keys: \|\n\s*(cache-v12-fast-\$\{\{ steps\.quarter\.outputs\.q \}\}-broad-)\n"
        r"\s*(cache-v12-fast-\$\{\{ steps\.quarter\.outputs\.q \}\}-)\n"
    )
    assert fast_block_re.search(text), (
        "fast-bundle restore-keys must list the broad-namespaced prefix BEFORE "
        "the canonical prefix (actions/cache tries them in declared order)"
    )
    slow_block_re = re.compile(
        r"restore-keys: \|\n\s*(cache-v5-text-\$\{\{ runner\.os \}\}-broad-)\n"
        r"\s*(cache-v5-text-\$\{\{ runner\.os \}\}-)\n"
    )
    assert slow_block_re.search(text), (
        "slow-text-bundle restore-keys must list the broad-namespaced prefix "
        "BEFORE the canonical prefix"
    )


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
