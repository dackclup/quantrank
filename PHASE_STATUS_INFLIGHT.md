# PHASE_STATUS_INFLIGHT.md — append-only side-file for in-flight PRs

This file exists to solve the **parallel-PR §Phase status collision
pattern** documented in [`CLAUDE.md`](CLAUDE.md) §Gotchas. Every PR
that needs to satisfy the §Conventions "ship with every PR" lockstep
rule was previously inserting a `**X in flight (this PR)**` bullet
at the same anchor line in CLAUDE.md §Phase status + AGENTS.md
§Phase + version state. Two PRs opened in parallel both target that
single line → `mergeable_state: dirty` → recurring `git merge`
conflicts → user frustration.

Surfaced 2026-05-24 by PR #230 (`docs(form4)+ci(simulate)`) which
hit the collision pattern **3 times in one session** while iterating
on the simulate-cap fix:
- vs PR #229 (security WARN cleanup) mid-iteration
- vs PR #232 + PR #233 (LedgerCraft A1 + A2) before Mark-Ready
- vs PR #234 + PR #235 + PR #236 (LedgerCraft A3 + B1 + B2+B3+B4)
  during the simulate-fix re-push loop

Each conflict was BENIGN (both PRs added distinct entries at the
same insertion line; resolution was always "keep both in
chronological order"). But `git merge` cannot auto-detect that.

## The new convention

**Open PRs MUST add their in-flight entry HERE**, not directly to
CLAUDE.md §Phase status or AGENTS.md §Phase + version state. New
entries go at the END of this file (append-only). Parallel PRs both
append to disjoint last-lines and `git merge` resolves trivially —
no conflict.

**Format** — one fenced block per in-flight PR, dated header,
trailing horizontal rule for visual separation:

```
## PR #NNN — <one-line summary> (in flight, 2026-MM-DD)

<2-15 line paragraph describing the change, the rationale, and any
follow-up items. Mirrors the format used by historical entries in
CLAUDE.md §Phase status — keep it readable for the next reviewer.>

---
```

**On merge** — the entry STAYS HERE (do NOT move on merge). This
file is append-only by design; the cost of in-place moves at merge
time would re-introduce the collision pattern. The historical
record gets aggregated periodically (weekly / per-release) by a
**housekeeping commit** that:

1. Moves entries from this file's "Merged" section (auto-marked by
   the housekeeping script — see `tools/housekeep_phase_status.py`
   when implemented) into CLAUDE.md §Phase status with their
   `merged via PR #N (commit-SHA)` headers
2. Leaves the still-in-flight section untouched

The housekeeping commit is one-touch (single file modified, all PR
authors disjoint by then) so it doesn't re-trigger the parallel-PR
collision.

## File structure

```
# PHASE_STATUS_INFLIGHT.md
## In flight (current)
  ## PR #NNN — ... (in flight, YYYY-MM-DD)
  ## PR #MMM — ... (in flight, YYYY-MM-DD)
## Merged (awaiting housekeeping move to CLAUDE.md)
  ## PR #LLL — ... (merged YYYY-MM-DD, SHA)
```

After housekeeping runs, the "Merged" sub-section drains to empty
(entries land in CLAUDE.md §Phase status proper); "In flight"
keeps growing/draining as PRs cycle.

## Cross-references

- [`CLAUDE.md`](CLAUDE.md) §Conventions — the lockstep rule that
  this file satisfies
- [`CLAUDE.md`](CLAUDE.md) §Gotchas "Parallel-PR §Phase status
  collision pattern" — the recurring symptom this file fixes
- [`AGENTS.md`](AGENTS.md) §Phase + version state — cross-tool
  mirror of CLAUDE.md §Phase status; same housekeeping pattern
  applies

## SKIP this file when

- The PR is a doc-only edit to this file itself (the lockstep is
  trivially satisfied)
- The PR is updating CLAUDE.md / AGENTS.md ONLY (no code change) —
  in that case, edit CLAUDE.md / AGENTS.md directly; the parallel
  collision risk is low for doc-only PRs since they're less common
- Housekeeping commits that move entries from here to CLAUDE.md —
  those touch CLAUDE.md + this file but the rationale is in the
  commit message, not a duplicated in-flight entry

---

## In flight (current)

## PR (this PR) — New skill: `good-code-bad-code-review` reference catalog (Miler / milerdev paired good/bad examples) (in flight, 2026-05-26)

New invocation-triggerable skill at
`.claude/skills/good-code-bad-code-review/SKILL.md`. Wraps the
publicly-hosted catalog at <https://good-code-bad-code.pages.dev/>
(author: Miler / `milerdev`) — 18 language/framework tracks × 10
paired side-by-side good/bad code-review examples.

**Posture**: REFERENCE LINK ONLY — no content vendored. The skill
body contains zero verbatim copy of any example; it's a QuantRank-
original index that catalogs the resource's structure (track list,
per-track topic list, URL pattern) and tells the agent how to deep-
link via `WebFetch` to the relevant example at review-time.

**Skill scope** (QuantRank-relevant tracks only):

| Track | URL | Domain |
|---|---|---|
| Python | `/tracks/python` | `compute/**/*.py` |
| TypeScript | `/tracks/typescript` | `frontend/lib/types.ts` |
| React | `/tracks/react` | `frontend/components/**/*.tsx` |
| Next.js | `/tracks/nextjs` | `frontend/app/**/*.tsx` |
| Tailwind CSS | `/tracks/tailwindcss` | utility-token review |
| Git | `/tracks/git` | workflow review |

12 other tracks (PHP / Java / Go / Express / Django / FastAPI / SQL
/ Docker / HTML / raw CSS / JavaScript / Node.js) explicitly listed
as SKIP — QuantRank doesn't use those stacks (static-export only,
no DB, no server-side runtime, TS exclusively).

**Trigger conditions** in description follow the PR #157 sharp-
keyword convention: "is this idiomatic" / "is this Pythonic" /
"is this good code" / "review this function" / "any code-smells" /
"ดู code นี้ดีมั้ย". Complements (does not replace)
`quantrank-reviewer` (opus agent owns project invariants —
Rules 1-18, schema triple, annotate-before-veto, tenacity policy);
this skill covers generic-language idioms orthogonally.

**Files** (4):

- `.claude/skills/good-code-bad-code-review/SKILL.md` (new)
- `THIRD_PARTY_NOTICES.md` — new section documenting reference-link
  posture + attribution + action-table for upstream license outcomes
- `CLAUDE.md` §Layout — skill count `44` → `45`
- `AGENTS.md` §Project structure — skill count `44` → `45`
- `SKILL.md` §Repository Structure — skill count `44` → `45`
- `PHASE_STATUS.md` §Current state — skill inventory `44` → `45`

**Hard constraints** built into the skill body:

- DO NOT vendor the content (no declared license)
- DO NOT block on `WebFetch` failure — fall back to
  `portable-karpathy-guidelines` + project SKILL.md rules
- DO NOT override `quantrank-reviewer` project-invariant findings
  with generic-language idioms (Rule 16 / schema / tenacity win)
- DO NOT fire on trivial diffs (single-line / typo / pure rename)

**Maintenance gate**: quarterly health-check at the next cohort
audit (2026-08-19) — re-confirm the home page resolves; refresh
the track-list table if Miler renamed/added tracks; update license
posture if Miler declares one.

**ZERO behavior change** to compute / scoring / valuation /
frontend code. Skill-config + docs only. No CI surface beyond the
existing schema-check (which is N/A — no schema touched).

PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship
with every PR" lockstep per PR #237 convention. CLAUDE.md +
AGENTS.md substance touched (skill count is substance-bearing).

---

## PR (this PR) — Post-release housekeeping: backfill v1.3.0-phase4.5e pointer + drain 11 stale (in flight) markers (in flight, 2026-05-26)

Phase B (post-tag housekeeping) PR per the v1.3.0 release plan.
Cuts no code; pure doc-pointer maintenance.

**Scope (3 files)**:

- **`CLAUDE.md`** §Phase status `Latest release tag` line — bumped
  `v1.2.0-phase4.5` (2026-05-17, `6d414a9b`) → `v1.3.0-phase4.5e`
  (2026-05-26, `5db3b978`); prior tag preserved as historical
  reference per release-tag SKILL.md §7 convention.
- **`PHASE_STATUS.md`** §Current state `Latest release tag` row —
  same pointer bump, plus a one-line description of what the
  release closes.
- **`PHASE_STATUS_INFLIGHT.md`** — 11 stale `(in flight, YYYY-MM-DD)`
  header markers updated to `(merged YYYY-MM-DD, <SHA>)` with the
  PR number prefix. The bodies stay in place (full historical
  record preserved); a future weekly housekeeping commit will
  move them from the "In flight (current)" section into the
  "Merged (awaiting housekeeping move to CLAUDE.md)" sub-section
  per the PR #237 convention. PRs drained in this pass: #244,
  #245, #246, #250, #251, #252, #256, #257, #258, #263, #266.

**Note on the tag**: `v1.3.0-phase4.5e` was created locally during
the release session but **the `git push origin` of the tag failed
with HTTP 403** from the sandbox (the sandboxed git proxy permits
branch pushes but not tag-ref pushes). The user must run
`git tag -a v1.3.0-phase4.5e -F docs/release-notes/v1.3.0-phase4.5e.md`
then `git push origin v1.3.0-phase4.5e` from their own machine on
the squash-merge SHA `5db3b978`. This PR's pointer bumps reference
the tag AS IF live (release-tag SKILL.md §7 anchors pointers to
the commit SHA, not the tag-availability state).

**Verification**:
- `ruff check .` — N/A (no Python touched)
- `python -m compute.output.schema_check` — N/A (no schemas touched)
- `pytest tests/ -m "not network"` — N/A (no test surface)
- Markdown-only diff; tracked by `docs-reviewer` if substance review needed

**Deferred follow-ups**:
- Future weekly housekeeping commit to move the drained PR bodies
  from "In flight (current)" → "Merged (awaiting housekeeping)" →
  CLAUDE.md §Phase status proper per the 3-step `tools/housekeep_phase_status.py`
  pattern (script not yet implemented; manual for now)
- The release tag itself needs `git push origin v1.3.0-phase4.5e`
  from the user's machine — separate operation, not part of this PR
- The GitHub Release page creation — separate operation via web UI
  or `gh release create`

No CLAUDE.md / AGENTS.md substance change beyond the pointer bump.
PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship
with every PR" lockstep per PR #237 convention.

---

## PR #266 — `chore(release): v1.3.0-phase4.5e` — Form-4 insider clustering + LedgerCraft frontend (merged 2026-05-26, `5db3b978`)

Cuts the **v1.3.0-phase4.5e** release tag, closing the Phase 4.5e
Form-4 insider-clustering ladder (PRs #167 + #205 + #222 + #224 + #238)
and shipping the LedgerCraft frontend reskin (A1-A3 + B1-B4 +
animation PRs 1-3 + #244 polish + dark-mode tooltip fixes through
PR #263) since the prior `v1.2.0-phase4.5` (`6d414a9b`, 2026-05-17).

**Scope of this PR** (3 files):

- `pyproject.toml` — `version = "0.3.0"` → `"1.3.0"` (matches the
  `v1.3.0-phase4.5e` git-tag SemVer; tag carries the phase suffix
  per release-tag SKILL.md convention)
- `docs/release-notes/v1.3.0-phase4.5e.md` (NEW) — paste-ready
  release body grouped by Phase 4.5e Form-4 / data-quality fixes /
  defense layer / frontend / methodology + agent infra / CI hygiene.
  ~800 words; cites every PR # back to v1.2.0.
- `PHASE_STATUS.md` — Current state schema `0.10.4` → `0.10.5-phase4.5e`,
  defense layer headline `32 → 33 declared`, production-run pointer
  refreshed to `26423296287` (cron #4 2026-05-26T01:12).

**Pre-flight ladder** (release-captain 2026-05-26):

| Check | Status |
|---|---|
| `ruff check .` | PASS |
| `pytest -m "not network"` | **1216 passed**, 7 skipped (factors extras), 24 deselected |
| `python -m compute.output.schema_check` | PASS (triple in sync at `0.10.5-phase4.5e`) |
| `verify-production-output/helper.py` Section A-G + I-L | PASS |
| Section H | 1 known FAIL — orphan `BK.json` (legacy BNY Mellon snapshot from 2026-05-23 ticker rename in `compute/ingest/universe.py::TICKER_OVERRIDES`); pre-existing housekeeping debris, NOT a regression |
| `tsc --noEmit` + `next build` | Verified via Vercel preview (UI-touching PRs since v1.2.0 all deployed clean) |

**Defense scorecard verification**: 7 active vetoes confirmed in
`compute/scoring/risk_overlay.py:411-495`. Headline 27 emitting / 33
declared — the gap is explained by (a) `FORM4_FETCH_SKIP=1`
suppressing `insider_sell_cluster` + `c_suite_unusual_sell` (-2);
(b) PR #264 `multi_class_aggregate_shares_suspected` + PR #265
`valuation_output_anomalous` ship with this release and don't emit
until next cron (-2); (c) rare-fire annotates that didn't trip on
the cron-#4 cohort.

**Production output 1-PATCH lag** — `frontend/public/data/metadata.json`
reports `0.10.4-phase4.5e` from cron `26423296287` (post-PR #257,
pre-PR #264 + #265). Next weekday cron (Wed 2026-05-27 22:00 UTC,
~21h post-tag) re-renders at full `0.10.5-phase4.5e` semantics
including the 2 new annotates. Acceptable per release-tag SKILL.md
§Gotchas — tag is anchored to code, not to the last committed
snapshot.

**Post-merge workflow** (USER AUTHORIZATION required for the tag
push):

```bash
# After this PR merges, on the squash-merge SHA:
git fetch origin main
git checkout main
git pull origin main
git tag -a v1.3.0-phase4.5e -F docs/release-notes/v1.3.0-phase4.5e.md
# DESTRUCTIVE — requires explicit user authorization:
git push origin v1.3.0-phase4.5e
```

Then create GitHub Release via web UI or `gh release create`
(target: post-merge SHA; title: "v1.3.0-phase4.5e — Form-4 insider
clustering + LedgerCraft frontend"; body: paste from the new
release-notes file; set-as-latest: YES).

**Deferred follow-ups** (separate PRs):

- INFLIGHT.md housekeeping drain — 6 stale "In flight (current)"
  entries (PR #245, #244, #246, #250-252, #265, etc.) should move to
  "Merged (awaiting housekeeping move to CLAUDE.md)" sub-section in a
  follow-up commit.
- CLAUDE.md "Latest release tag" pointer backfill to the post-tag SHA
  (release-tag SKILL.md §7 post-release hygiene).
- Issue #261 PR-B — reverse-allowlist per-class XBRL extraction
  (structural fix for GOOG/GOOGL); edgar-debugger probe locked the
  `goog:CapitalClassCMember` filer-namespace gotcha. Tracks as v1.3.1.
- Revert `FORM4_FETCH_SKIP=1` from `.github/workflows/compute-rankings.yml`
  once the durable timeout-rebaseline + cache-restore canary lands
  (performance-engineer scope).

PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with
every PR" lockstep per PR #237 convention. No CLAUDE.md / AGENTS.md
substance change required for this PR — release-tag is itself the
documented "Phase + version state" update mechanism.

---

## PR #265 — Issue #262: rename DQIC site-2 emission to `valuation_output_anomalous` + writer-parity for veto cohort (merged 2026-05-26, `e6013bae`)

Closes [issue #262](https://github.com/dackclup/quantrank/issues/262) (DQIC dual-surface emission inconsistency). Per the methodology-scientist Mode B verdict 2026-05-26 (APPROVED-AS-ANNOTATE, Path 3 = rename):

**The dual-surface bug**: `data_quality_input_corruption` was emitted from TWO independent check sites with DIFFERENT trigger conditions — `compute/scoring/risk_overlay.py:411` (INPUT-level corruption: TBVPS > $10K/share OR TTM revenue < $50M OR |NI| > |revenue|; appends to `risk_flags` VETO surface) AND `compute/valuation/ensemble.py:545` (OUTPUT-level anomaly: ANY of 6 method outputs > $10K/share; emits to `valuation_warnings` ANNOTATE surface). Site 2's check is strictly broader than Site 1's.

**Universe scan on 2026-05-23 cron #3** (methodology-scientist universe-walk):

| Surface pattern | Count | Tickers |
|---|---|---|
| BOTH `risk_flags` + `valuation_warnings` | 2 | ERIE (rank 69), BRK-B (rank 223) |
| Site 1 only — veto with NO UI explanation chip | **4** | MTB (320), CPT (347), MRNA (447), HBAN (460) |
| Site 2 only — annotate, Top-5-safety gap if rose | 1 | NVR (267) |

The **bigger smell than the NVR Top-5 risk** is the UI explainability gap for the 4 veto-only tickers — `FairPriceCard.tsx:82` reads only `valuation_warnings`, so MTB/CPT/MRNA/HBAN render the all-null fair-price ensemble with NO explanation chip.

**Path 3 fix (this PR)**:

- **Rename Site 2** — `compute/valuation/ensemble.py::_data_quality_corrupt_result` now emits `valuation_output_anomalous` (per-method `reason` field + the `valuation_warnings` list). Semantically distinct from the input-level `data_quality_input_corruption`: "a method produced an absurd output despite plausible inputs" is NOT categorical evidence of input untrust (could be residual input bug Site-1 missed, legitimately extreme RIM, OR formula edge case) — annotate-only is the correct Rule 16 surface.
- **Writer-parity emit** — `compute/main.py` per-ticker loop now ALSO appends `valuation_output_anomalous` to `valuation_warnings` when `data_quality_input_corruption` is in `risk_flags` for that ticker. Closes the veto-only-cohort UI explainability gap (MTB/CPT/MRNA/HBAN now gain the UI chip).
- **Consumer updates**:
  - `compute/valuation/applicability.py` — `SKIP_REASONS` taxonomy gains `valuation_output_anomalous`; legacy `data_quality_input_corruption` retained for backward-compat on pre-rename JSON snapshots. Count 25 → 26.
  - `compute/scoring/sanity.py:83` — `compute_mos_trailing_ic` IC-smoke exclusion checks BOTH identifiers.
  - `frontend/components/FairPriceCard.tsx:82` — `dataQualityIssue` flag check ORs both identifiers (backward-compat for pre-rename snapshots still on the static site between cron-#4 and cron-#5).

**Test updates** (4 sites):

- `tests/test_valuation/test_ensemble.py` (4 assertions) — assert new identifier on Site 2 emissions
- `tests/test_output/test_tier2_schema.py::test_B4_skip_reasons_count_is_25` → `_is_26` (taxonomy gains the new identifier)
- `tests/test_scoring/test_sanity_smoke.py` (2 sites) — unchanged; legacy-snapshot identifier path still verified via the OR check
- `tests/test_scoring/test_recommendation.py` (2 sites) — unchanged; veto identifier never renamed

**No schema bump** — string-identifier rename only, no new `Metadata` / `StockDetail` field. `SCHEMA_VERSION` stays at `0.10.5-phase4.5e`. The triple lockstep (`schemas.py` / `types.ts` / `schema-snapshot.json`) is unchanged.

**ZERO composite-rank impact** — composite scores / risk_flags VETO identifiers / Top-5 rotation unchanged. The only behavioral effect is which identifier appears in `valuation_warnings` (a display field) and gains the writer-parity for the veto cohort UI.

**Verification**:
- `ruff check .` — clean
- `python -m compute.output.schema_check` — clean (no schema change)
- `pytest tests/ -m "not network"` — **1216 passed**, 7 skipped, 24 deselected

**Deferred follow-ups** (not in this PR):
- Cohort-PPV cohort-acceptance check at Q3 2026-08-19 quarterly audit per methodology-scientist Q6 — walk the `valuation_output_anomalous` firing list, decide whether to retire the legacy `data_quality_input_corruption` identifier from the taxonomy after ≥ 2 crons of clean rename adoption.
- φ-correlation re-baseline of `valuation_output_anomalous` vs existing `extreme_*_estimate` annotates (methodology-scientist Q3 — confirms the new identifier is independent enough to justify the slot).

No CLAUDE.md / AGENTS.md substance change required — the rename doesn't introduce a new invariant; methodology-scientist verdict already documented in this entry. PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with every PR" lockstep per PR #237 convention.

---

## PR #264 — Issue #261 PR-A: `multi_class_aggregate_shares_suspected` annotate (CIK-collision detector) (merged 2026-05-26, `d9c62292`)

Closes the observability half of [issue #261](https://github.com/dackclup/quantrank/issues/261) (GOOG/GOOGL multi-class shares overcount). Per the methodology-scientist Mode B verdict 2026-05-26 (NEEDS-MORE-CALIBRATION) the issue splits into:

- **PR-A (this PR)** — annotate-only `multi_class_aggregate_shares_suspected` flag fires on the CIK-collision signature (two or more tickers in the universe share the same CIK AND each ticker's market_cap > 10% of universe-median). Annotate-only per `portable-annotate-before-veto`; composite rank UNCHANGED.
- **PR-B (next PR)** — reverse-allowlist per-class XBRL extraction (the structural fix). Gated on `edgar-debugger` probe 2026-05-26 which CONFIRMED per-class dimensional contexts are available — see "Edgar-debugger findings" below.

**Production code (1 new module + 4 edits)**:

- `compute/scoring/multi_class_shares.py` (NEW) — `detect_multi_class_aggregate_shares_suspected(cik_by_ticker, market_cap_by_ticker) -> set[str]` universe-level detector. `MARKET_CAP_FLOOR_RATIO: Final[float] = 0.10` constant. Pure function, no I/O, graceful on None inputs.
- `compute/config.py` — `SCHEMA_VERSION` bumped `0.10.4-phase4.5e` → `0.10.5-phase4.5e` (PATCH; additive Metadata field only).
- `compute/output/schemas.py` — new `Metadata.multi_class_aggregate_shares_suspected_count: int | None` with full docstring (expected steady-state firing rate 6 — GOOG / GOOGL / NWS / NWSA / FOX / FOXA per 2026-05-23 cron #3 cohort).
- `compute/main.py` — import + pre-compute `cik_by_ticker` + `market_cap_by_ticker` dicts BEFORE the per-ticker scoring loop + call detector + emit annotate inside the loop + increment counter + wire to `Metadata(...)`.
- `frontend/lib/types.ts` + `frontend/lib/schema-snapshot.json` — triple lockstep per §Conventions.

**Tests (`tests/test_scoring/test_multi_class_shares.py`, NEW; 13 cases)**:

1. `MARKET_CAP_FLOOR_RATIO` constant pin (10%)
2. Empty universe → empty set
3. No-collision universe → empty set
4. GOOG/GOOGL canonical case → both fire
5. Collision below floor (micro-class) → empty set
6. Partial above floor → only above-floor sibling fires
7. None CIK → excluded from collision detection
8. None market_cap → excluded from firing set
9. All-None market_caps → empty set (no median computable)
10. Three-way collision all above floor → all three fire
11. Threshold strict-inequality boundary → at-floor excluded
12. Hypothesis property: firing set ⊆ collision set (regression guard)
13. Plus `tests/test_config.py::test_schema_version_is_phase4_5e` pin updated `0.10.4` → `0.10.5-phase4.5e`

Tests: 1216 passing offline (+13 new — `test_multi_class_shares.py` adds 12 cases; +1 from config pin).

**Edgar-debugger findings (2026-05-26 live probe, AAPL filing accession `0001652044-26-000018`)**:

- **VERDICT**: PER-CLASS-AVAILABLE-IN-XBRL ✅
- Per-class share counts ARE present as dimensional facts in Alphabet's 10-K:
  - `us-gaap:CommonClassAMember` → 5.822B shares (GOOGL)
  - `us-gaap:CommonClassBMember` → 0.837B (not traded — founders)
  - `goog:CapitalClassCMember` → 5.429B (GOOG)
- **Critical gotcha for PR-B**: GOOG Class C uses **filer-specific namespace `goog:CapitalClassCMember`**, NOT the standard `us-gaap:CommonClassCMember`. An allowlist keyed to the standard namespace would silently return zero rows for GOOG.
- Per-class sum (5.822 + 0.837 + 5.429 = 12.088B) reconciles to companyfacts aggregate exactly — confirms the overcount is the aggregate-vs-per-class disambiguation pattern, not a different data-quality issue.
- PR-B's `MULTI_CLASS_SHARE_PER_CLASS_ALLOWLIST` will need: `{"GOOGL": "us-gaap:CommonClassAMember", "GOOG": "goog:CapitalClassCMember"}` keyed to the dimensional member, queried against `us-gaap:CommonStockSharesOutstanding` at `period_instant`.

**ZERO behavior change for the 496 non-colliding S&P 500 tickers** — composite / risk_flags / fair_price / top5 rotation unchanged. The 6 multi-class tickers (GOOG / GOOGL / NWS / NWSA / FOX / FOXA) gain the new annotate in `valuation_warnings`; composite rank unaffected.

**Expected Metadata fingerprint** (post first cron after merge):
- `multi_class_aggregate_shares_suspected_count` ≈ 6

**Deferred follow-ups** (not in this PR):
- PR-B — reverse-allowlist per-class XBRL extraction, structural fix for GOOG/GOOGL market_cap overcount. Code shape proposed by edgar-debugger 2026-05-26.
- Combined-per-class-MC reconcile invariant as Rule-18 diagnostic (`|Σ MC_per_class − MC_aggregate| / MC_aggregate < 0.05`) — methodology-scientist Mode B Q3 suggestion.
- Q3 2026-08-19 quarterly audit: walk the `multi_class_aggregate_shares_suspected_count` history, decide whether to retire after ≥ 2 crons of clean reconcile + recalibrate the 10% floor against the empirical universe.

No CLAUDE.md / AGENTS.md substance change required — the annotate doesn't introduce a new invariant, convention, or gotcha that future code authors need to remember. The pattern itself is already documented in CLAUDE.md §Gotchas under "shares_outstanding partial-extraction" and PR #257's allowlist precedent. PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with every PR" lockstep per PR #237 convention.

---

## PR #245 — EMERGENCY: cron-rankings.yml add `FORM4_FETCH_SKIP=1` to unblock 2h30m timeout (merged 2026-05-25, `fbbaeeec`)

`compute-rankings.yml` manual `workflow_dispatch` cancelled at the
150m `timeout-minutes` ceiling (2026-05-25 00:13 UTC). Production
data ~44h stale (last successful chore commit `9015748` Sat
2026-05-23 03:38 UTC).

**`incident-commander` session-8 verdict**: classification **(δ)
budget exhausted, NOT code regression**. PR #238's `filing.xml()`
cache-hit invariant verified intact against vendored edgartools
5.31.5 source (load-bearing-correct, ~lxml-find cost only). Root
cause: 150m timeout set in Phase 4g for 4-loop reality; PR #205
added Form-4 (5th SEC EDGAR loop, +20-30m cold) 12 days ago
without bumping the budget. Cache eviction over 44h Fri→Sun gap
made all 5 cold simultaneously → > 150m.

**Path B mitigation** (user-authorized): add `FORM4_FETCH_SKIP: "1"`
to workflow-level `env:` block in `.github/workflows/compute-rankings.yml`.
Form-4 fetch is observability-only (`form4_enabled=False`,
`_FORM4_FLAGS_ENABLED=False`) so skipping has ZERO scoring impact —
composite + risk_flags + rankings + per-stock JSON all identical.
`Metadata.form4_*` fields coerce to None for this run (acceptable;
Q3 cohort-audit gate 2026-08-19 has plenty of subsequent crons to
repopulate).

Expected: cron completes in 12-25m on warm partial cache; up to
~90m worst-case if fundamentals/Tier-2 caches are ALSO cold (still
under 150m).

**Durable follow-ups** (NOT in this PR — separate sessions):
- `performance-engineer` issue: rebaseline `timeout-minutes` against
  5-loop cold-cache reality OR refactor to off-cycle pre-cache
- Cache-restore canary step (size + age per cache dir, emit before
  fetch — surfaces cache eviction in 30s instead of after 150m)
- Per-loop wall-clock budget in Metadata (parity with existing
  `fundamentals_latency_p95_seconds` — add for tier2 / form4 / OSAP)
- `workflow_dispatch.inputs.*_skip` UI controls so operator can
  mitigate without YAML edit
- After fresh data lands: REVERT this env-var (Form-4 is the source
  for Phase 4.5e PR 5 weight-promotion firing-rate observation)

CI workflow YAML change ONLY (single env-var line + inline rationale
comment). PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions
lockstep.

---

## PR #243 — Doc-staleness sweep: cron schedule Sun→Mon-Fri (4 files) + subagent count 15→18 + housekeep PR #241+#242 → Merged (merged 2026-05-25, `af1079c`)

The user called out that I repeatedly stated "cron Sun 22:00 UTC" in
session 7 summaries; the actual `.github/workflows/compute-rankings.yml`
schedule is `"0 22 * * 1-5"` (Mon-Fri only — "Weekends skipped (no
new trading data)" per the inline comment, which was never Sunday in
the file's git history). The handoff prompt at session start said
"Sun 2026-05-24 22:00 UTC (cron-#4)" and I echoed without verifying
against the YAML. Audit + correction sweep:

- **`CLAUDE.md:31`** — §Stack bullet "weekly `compute-rankings.yml`
  (cron Sun 22:00 UTC)" → "weekday `compute-rankings.yml`
  (cron Mon-Fri 22:00 UTC; weekends skipped — no new trading data)"
- **`docs/RESEARCH_FINDINGS.md:854`** — "WEEKLY (GitHub Actions,
  Sunday 22:00 UTC)" → "WEEKDAY (GitHub Actions, Mon-Fri 22:00 UTC;
  weekends skipped)"
- **`docs/ARCHITECTURE.md:7`** — mermaid label "GitHub Actions cron
  / Sun 22:00 UTC" → "Mon-Fri 22:00 UTC" + edge label "run weekly"
  → "run weekdays"
- **`docs/stock_ranking_knowledge.md:993`** — "Weekly Sunday 22:00
  UTC: Main compute cron" → "Weekday Mon-Fri 22:00 UTC: Main compute
  cron (weekends skipped — no new trading data)"

Companion stale-info fix:
- **`AGENTS.md:1294`** — "The 15 subagents under `.claude/agents/`"
  → "The 18 subagents under `.claude/agents/`" (post-PR #225 the
  roster expanded ci-triage-engineer + vercel-preview-auditor +
  literature-searcher; AGENTS.md:91 already says 18; line 1294 was
  drift)

Companion INFLIGHT.md housekeeping (move merged entries from
"In flight (current)" → "Merged (awaiting housekeeping move to
CLAUDE.md)" sub-section):
- PR #241 (simulate Parts 5+6+7, `e9d7836`) — moved with full
  4-iteration-fix summary preserved
- PR #242 (light-mode soften + Strong Buy nowrap + StockLogo square,
  `a30c017`) — moved with the original entry text preserved
- Duplicate "## Merged" sub-section header removed so the file has
  ONE Merged section (was two due to the prior rebase resolution
  leaving the old header in place)

No compute / schema / scoring / valuation / Python / TS code change.
Doc-only PR. PHASE_STATUS_INFLIGHT.md side-file pattern (PR #237)
satisfies §Conventions lockstep.

---

## PR #250 — Animation polish PR 1: micro-interactions (Tier 1 P1, 10 className edits) (merged 2026-05-25, `25c2f2b1`)

First PR of the post-LedgerCraft animation polish series surfaced by
the `frontend-design-reviewer` open-scope animation audit (no PR
number yet — fresh branch from `main` HEAD `fbbaeeec`). Ten P1
micro-interaction polishes across 6 frontend components — pure
className-level diff, zero new keyframes, zero new deps, zero schema
/ Python / scoring / valuation / output JSON change.

**LedgerCraft compliance**: every transition ≤ 200ms; easing defaults
to Tailwind's `cubic-bezier(0.4,0,0.2,1)` (Material standard); no
bouncy / spring / overshoot; all transitions functional
(state-change feedback) not decorative.

**The 10 edits**:
- **A1** `FilterDrawer.tsx:238` — fix typo `transition-colors-colors`
  → `transition-colors` (Valuation chip group had ZERO color
  transition before — silent Tailwind class-validity drop)
- **A2** `FilterDrawer.tsx:296` — add `transition-colors duration-150`
  to "View N stocks" CTA (emerald-700 → emerald-800 smooth)
- **A3** `RankingTable.tsx:244` — replace text sort-glyph (`▲` /
  `▼` / `↕`) with rotating SVG chevron that smoothly transitions
  `rotate-0` ↔ `rotate-180` on asc/desc toggle (150ms ease-out);
  inactive columns keep the dual-arrow `↕` SVG. Most-frequent
  interaction on the page — sort.
- **A4** `RankingTable.tsx:256` — add `transition-colors duration-150`
  to Filters toolbar button hover
- **A5** `RankingTable.tsx:414` — add `transition-colors duration-100`
  to desktop `<tr>` hover (50 rows × snap-color → smooth fade every
  hover; most-frequent visual feedback on the page)
- **A6** `RankingTable.tsx:451` — add `transition-colors duration-100`
  to mobile `<li>` card hover (mobile parity with desktop A5)
- **A7** `FairPriceCard.tsx:37` — add `transition-colors duration-100`
  to `MethodRow` `<tr>` hover (6-row per-method table fade)
- **A8** `RawMetricsTable.tsx:65` — add `transition-colors duration-100`
  to `<tr>` hover (14-row raw-fundamentals table fade)
- **A9** `Sidebar.tsx:95` — replace `transition-transform duration-200`
  with `[transition:transform_200ms_ease-out,width_200ms_ease-out]`
  so desktop collapse 240px → 64px (and 64 → 240) animates smoothly
  instead of hard-jumping. Mobile slide-in keeps the same 200ms
  timing — both transitions share the easing.
- **A10** `Sidebar.tsx:127` — add explicit `duration-200` to
  collapse chevron `transition-transform` (was bare default 150ms;
  bumped to match sibling 200ms transitions for visual consistency)
- **A11** `PriceTimePeriodSelector.tsx:72-75` — dark-mode contrast
  bump on the 7-button period selector (1D / 5D / 1M / 6M / YTD /
  1Y / 5Y). Pre-fix: unselected enabled used `dark:text-slate-400`
  on `dark:bg-slate-900` (~4.5:1, just barely WCAG AA) and disabled
  1D/5D used `dark:text-slate-600` (~3:1, sub-AA) — user spot-check
  on Vercel preview reported the buttons "มองไม่ค่อยเห็น". Bumped
  unselected → `dark:text-slate-300` (~7:1, AAA), disabled →
  `dark:text-slate-500` (~5:1, AA — visibly muted but readable),
  and lifted both unselected + selected ring to `dark:ring-slate-600`
  (was 700) for better button outline visibility in the same band.
  Ride-along contrast polish — fits the PR's "polish" theme even
  though it's a contrast fix not an animation; bundling avoids a
  separate 1-line PR.

**Out of scope this PR (queued for PR 2 + 3)**:
- P2 polish items — 7 more button hover transitions + active chip
  opacity + AppShell mobile backdrop fade
- Skeleton loaders — PriceHistoryChart shimmer + StockLogo fade-in
  (requires `@keyframes shimmer` + `@keyframes fade-in` in globals.css
  + Tailwind config keyframes/animation registration)

**Out of scope permanently (LedgerCraft restraint)**:
- ScoreBadge / MoSBadge radial gauge arc-draw animation (decorative)
- ThemeToggle icon crossfade (asymmetric without Framer Motion
  `AnimatePresence` — looks like a bug)
- Body color crossfade on theme toggle (next-themes
  `disableTransitionOnChange: true` blocks; flipping to false would
  cause 50+ row simultaneous color sweep — noisy)
- Recharts `Area` draw animation (already `isAnimationActive={false}`
  per LedgerCraft "data instantly readable" register — keep)

Frontend-only PR. Branch from latest `main` (`fbbaeeec`, includes PR
#245 EMERGENCY cron fix). PHASE_STATUS_INFLIGHT.md side-file pattern
(PR #237) satisfies §Conventions lockstep — CLAUDE.md / AGENTS.md
substance UNCHANGED.

---

## PR #251 — Animation polish PR 2: secondary polish (Tier 1 P2 + Tier 2 layout, 13 edits across 6 files) (merged 2026-05-25, `e23861af`)

Second PR of the post-LedgerCraft animation polish series. Continues
the `frontend-design-reviewer` open-scope animation audit Section C
(PR 2 scope) — P2 micro-interaction polish + Tier 2 layout refactor.
Pure className diff + 1 small JSX refactor; zero new keyframes, zero
new deps, zero schema / Python / scoring / valuation / output JSON
change.

**LedgerCraft compliance**: every transition ≤ 200ms; functional
state-change feedback only; same Material easing standard as PR 1.

**The 13 edits**:

P2 button hover transitions (smooth color fade on hover, was
instant-snap):
- **B1** `FilterDrawer.tsx:127` — Close button (X) — add
  `transition-colors duration-150`
- **B2** `FilterDrawer.tsx:289` — "Clear all" button — add
  `transition-colors duration-150`
- **B3** `AppShell.tsx:58` — mobile hamburger menu button — add
  `transition-colors duration-150`

Active filter chip dismissal (RankingTable toolbar — 5 chip variants
gain opacity transition so the hover feedback is smooth):
- **B4** `RankingTable.tsx:334` — active sector filter chip
  `transition-opacity duration-100`
- **B5** `RankingTable.tsx:349` — active tier filter chip same
- **B6** `RankingTable.tsx:364` — active MoS filter chip same
- **B7** `RankingTable.tsx:377` — active recommendation filter chip same
- **B8** `RankingTable.tsx:388` — active score-range filter chip same

Pagination buttons (RankingTable footer):
- **B9** `RankingTable.tsx:620` — "← Prev" button — add
  `transition-colors duration-150`
- **B10** `RankingTable.tsx:631` — "Next →" button same

Per-method row hover (Fair price card list):
- **B11** `FairPriceBarChart.tsx:316` — `<li>` row gains
  `hover:bg-slate-50 dark:hover:bg-slate-800/30
  transition-colors duration-100`. Previously had ZERO hover state
  (sibling `FairPriceCard.tsx` MethodRow already has hover post-PR 1)

Filing link hover (Tier-2 event card):
- **B12** `Tier2EventCard.tsx:202` — "View filing" external link
  `transition-colors duration-150` (smoothens the hover →
  text-slate-900 + underline)

Tier 2 layout refactor (small JSX change, not a className diff):
- **B13** `Sidebar.tsx:84-91` — mobile overlay backdrop refactored
  from conditional render (`{mobileOpen && <button>}`) to
  always-mounted opacity toggle. Mirrors the `FilterDrawer` backdrop
  pattern: `transition-opacity duration-200` with `pointer-events-none
  opacity-0` when closed. Added `aria-hidden={!mobileOpen}` +
  `tabIndex={mobileOpen ? 0 : -1}` so the invisible backdrop can't
  trap keyboard focus when closed. Visual result: mobile nav drawer
  backdrop now FADES in/out instead of snap-appearing/disappearing
  alongside the sidebar slide.

**Out of scope this PR (queued for PR 3)**:
- Skeleton loaders — PriceHistoryChart shimmer + StockLogo fade-in
  (requires `@keyframes shimmer` + `@keyframes fade-in` in globals.css
  + Tailwind config keyframes/animation registration)

**Out of scope permanently** (carry-over from PR 1):
- Decorative animations (ScoreBadge / MoSBadge radial arc-draw)
- ThemeToggle icon crossfade
- Body color crossfade on theme toggle
- Recharts `Area` draw animation

Frontend-only PR. Branch from latest `main` (`25c2f2b1`, includes
PR #250 = animation polish PR 1). PHASE_STATUS_INFLIGHT.md side-file
pattern (PR #237) satisfies §Conventions lockstep — CLAUDE.md /
AGENTS.md substance UNCHANGED.

---

## PR #252 — Animation polish PR 3: skeleton loaders + @keyframes (merged 2026-05-25, `6e37c25e`)

Third (and final base-tier) PR of the post-LedgerCraft animation
polish series. Adds the project's first `@keyframes` declarations
(none existed prior to this PR) for skeleton-loading shimmer + image
fade-in. Frontend-only; zero new deps, zero schema / Python /
scoring / valuation / output JSON change.

**LedgerCraft compliance**: shimmer runs at 1.5s linear (loading-
state convention, not the 200ms transition budget — different
animation class); fade-in matches the 200ms `ease-out` budget;
`prefers-reduced-motion: reduce` guard suppresses both and falls
back to static slate-200 / slate-800 placeholder blocks (still
visible as loading cues, just non-animated).

**The 5 edits across 4 files**:

- **C1** `tailwind.config.ts` `theme.extend` — register the
  `shimmer` + `fade-in` keyframes + `.animate-shimmer` +
  `.animate-fade-in` animation utility classes so they're available
  as Tailwind classes. Pure config addition — no existing tokens
  modified.
- **C2** `app/globals.css` (end of file, after the soft-color
  overrides) — `@keyframes shimmer` (background-position sweep
  -200% → +200%) + `@keyframes fade-in` (opacity 0 → 1) +
  `.animate-shimmer` light + `.dark .animate-shimmer` dark base
  gradient + `prefers-reduced-motion` guard. Light gradient uses
  slate-200 base + slate-100 highlight; dark uses slate-800 +
  slate-700 (preserves visual distinguishability against the
  slate-950 dark canvas).
- **C3** `PriceHistoryChart.tsx:118-124` — loading state replaced
  from a centered text "Loading price history…" to a 4-block
  shimmer skeleton (headline + change row + period selector + chart
  canvas). Wrapped in `aria-busy + aria-live="polite"` with a
  `sr-only` span so screen readers still hear the loading announcement.
  Reduces perceived load time + layout shift (the skeleton roughly
  matches the post-load layout shape).
- **C4** `StockLogo.tsx:80-88` — `imgStyle` gains
  `animation: 'fade-in 200ms ease-out'`. The Parqet SVG logo now
  fades in on mount instead of flashing in from nothing. Typical
  Parqet SVG load is < 50ms (cached) so the user sees the image
  appear mid-animation; for slower loads, the element opacity
  animates against white-bg-border while the SVG arrives.
- **C5** `StockLogo.tsx:57-72` — `fallbackStyle` (the deterministic
  letter-avatar) also gains the fade-in animation. When the Parqet
  img errors and `setFailed(true)` swaps to the letter-avatar, the
  swap reads as a smooth fade-in instead of a hard pop. Visual
  symmetry with the img path.

**Reduced-motion guard semantics**:
- `.animate-shimmer` → `animation: none` + static slate-200 (light)
  / slate-800 (dark) background. Skeleton STILL communicates
  "loading" — just no motion.
- `.animate-fade-in` → `animation: none`. Element appears at full
  opacity immediately. The StockLogo + skeleton blocks render
  instantly with no animation cycle. Hard-tested locally by
  toggling Chrome DevTools "Emulate CSS prefers-reduced-motion".

**Out of scope (deferred to follow-ups if user requests)**:
- Skeleton states on RankingTable / detail page chrome — those are
  STATICALLY GENERATED (no async client-side load) so no skeleton
  is needed; data is on the wire at first paint
- Number tickup animation on score changes — different scope
  (deterministic recomputation, not an async load)
- ScoreBadge / MoSBadge / PillarRadarChart entrance animations —
  decorative per LedgerCraft restraint (covered already in PR 1
  out-of-scope list)
- ThemeToggle icon crossfade / body color cross-fade — same
  permanent out-of-scope as PR 1 + PR 2

Frontend-only PR. Branch from latest `main` (`e23861af`, includes
PR #251 = animation polish PR 2). PHASE_STATUS_INFLIGHT.md side-file
pattern (PR #237) satisfies §Conventions lockstep — CLAUDE.md /
AGENTS.md substance UNCHANGED.

**Series progress**: PR 1 (#250) + PR 2 (#251) + PR 3 (this) closes
the 3-tier animation polish roadmap. Total: 11 + 13 + 5 = 29 edits
across 9 files. Zero deps added; zero bundle-size impact (CSS
+ ~600 bytes uncompressed). Optional Tier 3 (Framer Motion page
transitions ~50KB) deliberately NOT pursued — LedgerCraft accountant
aesthetic doesn't reward page-level motion.

---

## Merged (awaiting housekeeping move to CLAUDE.md)

## PR #241 — Simulate Parts 5+6+7: wire `QR_SKIP_OSAP` + `QR_SKIP_CROSS_SOURCE` + timeout-minutes 45→90 backstop (merged 2026-05-24, `e9d7836`)

Closes the 4-iteration simulate-cap fix saga: PRs #230 / #238 / #241
all hit the 45-min cap despite each round wiring another skip env
var. Part 5 added `QR_SKIP_OSAP` + `compute/cache/osap` to both
workflows' cache `path:` blocks. Part 6 added `QR_SKIP_CROSS_SOURCE`
to skip the 502-ticker yfinance.info loop (the 5th external-data
loop identified by ci-triage-engineer session-6) which has a 24h
TTL inside `_cache_read` — Sunday simulate restores Friday's cron
cache as 39h-old → fails freshness → live yfinance fetch. Part 7
bumped `timeout-minutes: 45 → 90` as a pragmatic backstop when
PR #241's live-fire with all 5 skip vars still hit 45m. Simulate
IS informational-only per workflow comment line 24; cron uses
150m so simulate at 90m stays well below. If 90m still cancels,
hard evidence of cache-empty / env-propagation / 6th loop and
escalates to incident-commander. CLAUDE.md §Gotchas "CI escape-
hatch env-var combo" rewritten to a 5-var combo listing read sites
for all five: FORM4_FETCH_SKIP + QR_SKIP_TIER2 + QR_SKIP_FUNDAMENTALS
+ QR_SKIP_OSAP + QR_SKIP_CROSS_SOURCE.

---

## PR #242 — Light-mode soften + Strong Buy nowrap + StockLogo square (merged 2026-05-24, `a30c017`)

Three user-direction visual polish tweaks landed post-LedgerCraft series:

- **`frontend/app/globals.css`** — body bg `rgb(250 250 250)` (#FAFAFA
  canonical LedgerCraft) → `rgb(248 246 243)` (warm-cream shift ~3pts
  toward yellow, away from cold off-white). Reduces the stark contrast
  vs pure-`#FFFFFF` card surfaces post-A3 shadow-drop while staying
  within the LedgerCraft canvas register (perceptual lightness ~96%);
  user feedback "ทำให้สีขาว soft ลงหน่อย".
- **`frontend/components/RecommendationBadge.tsx`** — chip body gains
  `whitespace-nowrap` so "Strong Buy" / "Lean Bullish" labels stay on
  a single line in narrow contexts (mobile cards · sidebar · ranking
  table ticker col). Previously could wrap to 2 rows when the parent
  container squeezed; user feedback "strong buy แบบแนวนอนทำให้เป็น
  แถวเดียวไม่ต้องตัดเป็นสองแถว".
- **`frontend/components/StockLogo.tsx`** — both inline-style call
  sites flipped `borderRadius: '50%'` (circle) → `borderRadius: '4px'`
  (square with LedgerCraft Cards Medium radius). Applies to BOTH the
  Parqet `<img>` logo path and the deterministic letter-avatar
  fallback; user feedback "รูปโลโก้หุ้นเปลี่ยนจากวงกลมเป็นสี่เหลี่ยม".
  Note: this overrides the post-A3 design-reviewer audit OK-TO-KEEP
  carve-out ("logo container, not a chip — 50% acceptable") because
  user explicitly directed the change.

No schema / Python / scoring / valuation / output JSON change.
className+style-only diff. PHASE_STATUS_INFLIGHT.md side-file
satisfies §Conventions lockstep per PR #237 convention.

---

## PR #244 — Post-LedgerCraft polish bundle A1-A10 (dark variants + sort affordance + a11y + stale copy) (merged 2026-05-25, `a2f9ea8e`)

10 quick-win design polish items surfaced by the post-#242
`frontend-design-reviewer` open-scope audit. All single-line or
two-line fixes across 6 files. No schema / Python / scoring /
valuation / output JSON change. Closes the residual gaps that
slipped through the LedgerCraft A1-B4 + #242 polish series.

- **A1** `app/stock/[ticker]/page.tsx` 2 `h2` section headers
  ("Price (1y)" + "Raw fundamentals") gain `dark:text-slate-400`
- **A2** `app/stock/[ticker]/page.tsx` "← Back to ranking" link
  gains `dark:text-slate-400 dark:hover:text-slate-100`
- **A3** `FilterDrawer.tsx` MoS/Valuation chips gain dark hover
  state matching the 3 sibling filter groups
- **A4** `FairPriceCard.tsx` 4 KPI `dd` values gain `font-mono
  font-semibold leading-none` to match hero-metric weight register
- **A5** `RankingTable.tsx` inactive sortable columns now render
  a subtle `↕` glyph in `text-slate-300` (sortability affordance
  cue per Bloomberg/Google Finance pattern)
- **A6** `RankingTable.tsx` `aria-sort={ascending | descending |
  none}` attribute added for screen-reader column-sort announcement
- **A7** `FilterDrawer.tsx` search input gains
  `dark:focus:border-slate-500 dark:focus:ring-slate-500`
- **A8** `FilterDrawer.tsx` 4 chip surfaces — `transition` (ALL
  CSS props) → `transition-colors` (scoped) matching
  `PriceTimePeriodSelector` pattern
- **A9** `app/page.tsx` + `app/stock/[ticker]/page.tsx` — stale
  "Phase 3b" / "Phase 3c" references stripped from user-facing
  footer copy; explanatory content preserved
- **A10** `PriceHistoryChart.tsx` Recharts tooltip `borderRadius:
  '0.375rem'` (6px) → `'0.25rem'` (4px) matching post-A3 4px
  card-radius normalization

Out of scope (deferred from audit):
- B1 dead-sort-key `SortKey` cleanup (no UI impact)
- B2/C1 Instrument Serif use-or-remove (design taste call)
- B3/C2 MoS column on desktop ranking table (data-density tradeoff)
- C3 focus-visible ring system across all 23 buttons (a11y, wider scope)

PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions lockstep
per PR #237 convention. CLAUDE.md / AGENTS.md substance UNCHANGED.

---

## PR #238 — Form-4 `<aff10b5One>` direct-XML parse closes the architectural gap (merged 2026-05-24, `cdf70bd`)

Closes the architectural-gap surfaced by PR #230's edgar-debugger
audit + Part 1 §"Footnote resolution" docstring. Pre-fix: filers
who checked `<aff10b5One>true` at the document level but omitted
the per-transaction footnote text slipped past the footnote-text
regex path and INCORRECTLY entered the opportunistic-trades cohort
that drives `insider_sell_cluster` + `c_suite_unusual_sell`.

`edgar-debugger` session 5 design report confirmed the cleanest
access path is `filing.xml()` — already `@lru_cache(maxsize=4)` so
calling it AFTER `filing.obj()` is a free cache hit (zero extra
HTTP per filing; universe-wide added cost ~1.5s for lxml find).
The XML element lives at `ownershipDocument/aff10b5One` per SEC
schema X0609 (Release 33-11138, effective 2023-04-01). Edgartools
5.31.5's `Ownership.parse_xml` walks a fixed set of child tags and
never reads it — the element is PRESENT in the BS4 tree but
discarded after parse.

Implementation in `compute/scoring/form4_insider.py`:
- New `_AFF10B5_REQUIRED_ATTRS = ("aff10b5One",)` manifest tuple
  (drift-detector documenting the canonical SEC element name)
- New `_extract_aff10b5_one(xml_str)` helper — lxml-based, handles
  `1`/`true`/`0`/`false` variants, returns None on absent / parse
  fail (graceful-degradation per existing pattern + methodology-
  scientist Mode B option (a) from PR #224)
- New `_combine_10b5_one_signals(doc_level, footnote_result)` helper
  — OR-of-True truth table: `True if either signal is True; None
  only when both are None; False otherwise`
- `_form4_to_transactions` modified to call `filing.xml()` +
  `_extract_aff10b5_one()` ONCE per filing, then propagate via
  `_combine_10b5_one_signals()` to every transaction in that
  filing's rows
- `Form4Transaction` dataclass gains `aff10b5_one_doc_level: bool
  | None = None` field with backward-compat default; `from_dict`
  reads it via `.get(...)` with None fallback

Tests in `tests/test_scoring/test_form4_insider.py` — `test-engineer`
spawn added 10 H-prefixed cases (9 offline + 1 @network-gated):
- H1-H4: `_extract_aff10b5_one` truth + variants + malformed + absent
- H5: doc-level propagation to all transactions in a filing
- H6-H8: `_combine_10b5_one_signals` truth-table coverage
- H9: `_AFF10B5_REQUIRED_ATTRS` manifest drift-detector
- H10 (@network): live AAPL Form 4 extraction verifies access path

Verification: `pytest tests/test_scoring/test_form4_insider.py -v -m
"not network"` → **32 passed, 2 deselected** (1 @network H10 + 1
@network D4). Smoke-test of helpers via direct `python3 -c` ✓ 14
assertions. `ruff check` clean.

Scope estimate from edgar-debugger held: ~30 LOC prod + ~80 LOC tests
+ 0 new deps + 0 schema changes (the new field lives in Form-4
cache rows only; doesn't surface in `StockDetail` / `Metadata` in
this PR). Defense layer flag count unchanged at 32. Downstream
consumer `_is_opportunistic_sell` in `form4_signals.py` reads the
existing combined `is_rule_10b5_one` field (now produced by
`_combine_10b5_one_signals` instead of just the footnote-text scan)
— no consumer changes needed.

This PR ALSO dogfoods the new `PHASE_STATUS_INFLIGHT.md` convention
adopted in PR #237 (`1ff6c11`) — this entry is the FIRST PR to
test-drive the side-file pattern. CLAUDE.md + AGENTS.md §Phase
status sections UNCHANGED in this PR (the in-flight entry is right
here in the side file). Lockstep rule satisfied per the new
§Conventions wording.

**Known follow-up surfaced at merge time**: simulate workflow on
this PR cancelled at 45m16s despite PR #230's QR_SKIP_TIER2 +
QR_SKIP_FUNDAMENTALS fix being in place. Session 6 `ci-triage-engineer`
investigation in flight to identify the remaining unkilled SEC EDGAR
loop. Simulate is informational-only per workflow comment line 24
so merge was allowed; user authorized.

## PR #239 — Phase doc-triple lockstep refresh (PHASE_STATUS + SKILL + WORKFLOW) (merged 2026-05-24, `3e102e1`)

Addresses release-captain BLOCKED-ON-PRE-FLIGHT blocker #3 from
the v1.3.0 tag attempt: `PHASE_STATUS.md` / `SKILL.md` /
`WORKFLOW.md` were 3 days + ~32 PRs stale (last touched PR #171,
2026-05-21). Brings all three docs current to main HEAD so the
release-captain ladder can re-attempt cleanly.

- **`PHASE_STATUS.md`** — "Current state" header date 2026-05-21
  → 2026-05-24; schema `0.9.4-phase4h.4` → `0.10.2-phase4.5e`;
  defense layer 27 → 32 emitted flags; subagent inventory 14 → 18
  (named tier roster — 4 opus / 14 sonnet); skill inventory 42 → 43;
  recently-merged block refreshed to cover PR #170 → PR #237 (~36
  entries with commit shas); next-deliverables list updated (Phase
  4.5e PR 5 cluster weight promotion / Issue #67 sector-CoE flip /
  v1.3.0 release tag gate / Phase 4i.1-4j.1-4k.1 factor
  integrations / Phase 5 ML meta-learner).
- **`SKILL.md`** — schema-version table: 7 new rows added in
  reverse-chronological order (matching existing 0.9.x convention)
  for `0.9.5` → `0.9.6` → `0.9.7` → `0.9.8` → `0.10.0` → `0.10.1`
  → `0.10.2` covering PRs #180/#181/#183/#204/#205/#222/#224. Each
  row carries PR # + 1-line scope + backward-compat note +
  literature anchor where applicable.
- **`WORKFLOW.md`** — five edits: Phase Overview table 4.5 row
  marked ✅ DONE 2026-05-23 + 10b5-1 filter scope note; Form 4 SEC
  Filing Roadmap row flipped "planned" → "active" with 4-PR ladder
  reference (#167/#205/#222/#224); Phase 4.5e task list 5 items
  flipped `[ ]` → `[x]` with per-PR commits + methodology-scientist
  Mode B verdicts inline; Phase 4.5 Acceptance Criteria 9 items
  flipped; Phase 4.5f tag item marked ✅ at `6d414a9b`.

Unblocks the v1.3.0 release tag — blockers 1 (wrong branch — need
main checkout), 2 (`pyproject.toml` stale `0.3.0` → `1.3.0`),
4 (production output 1 cycle behind code — next cron fixes), and
5 (release notes draft scope — release-captain has the full draft
staged) all still need resolution before tag cut; this PR closes
blocker 3 only.

No compute / schema / scoring / valuation / frontend / Python /
TypeScript code change. Doc-only PR. PHASE_STATUS_INFLIGHT.md side-
file pattern (PR #237) satisfies the §Conventions "ship with every
PR" lockstep rule.

---

## PR #237 — adopt PHASE_STATUS_INFLIGHT.md side-file (merged 2026-05-24, 1ff6c11)

Closes the structural follow-up tracked in PR #230's §Gotcha
"Parallel-PR §Phase status collision pattern". PR #230 itself hit
the collision **3 times in one session** while iterating on the
simulate-cap fix — empirical proof that the doc-discipline §Convention
landed in PR #230 (rebase-before-Mark-Ready) is necessary but NOT
sufficient when 5+ PRs land on main in a single hour.

This PR creates `PHASE_STATUS_INFLIGHT.md` at the repo root with the
append-only convention documented above. Future PRs MUST add their
in-flight entry HERE instead of CLAUDE.md §Phase status / AGENTS.md
§Phase + version state. Parallel PRs both append at disjoint
last-lines → `git merge` auto-resolves → no more `mergeable_state:
dirty` from this pattern. CLAUDE.md §Conventions + §Gotchas updated
to point at this file as the canonical destination for in-flight
notes; AGENTS.md mirrored for cross-tool agents (Copilot / Cursor /
Devin).

Housekeeping workflow (`tools/housekeep_phase_status.py`) deferred —
manual housekeeping is fine for the first few weeks while the pattern
proves itself; a script can land later once we know the volume +
shape of entries this file accumulates.

No compute / schema / scoring / valuation / frontend / Python /
TS code change. Doc-only PR. CLAUDE.md + AGENTS.md lockstep
satisfied via §Conventions + §Gotchas substantive updates (the
"ship with every PR" rule now points at this file as the canonical
destination).

---

## PR #255 — PriceHistoryChart tooltip dark-mode readability fix (merged 2026-05-25, `bceb5fc`)

User screenshot 2026-05-25 of `/stock/[ticker]` price chart in dark
mode: the Recharts tooltip date label ("Feb 24, 2026") rendered in
a barely-visible light-blue-gray on a white tooltip background.
"Close : $192.84" stayed readable because Recharts colors item
entries with the data-series stroke (`trendStroke` =
`emerald-500` / `rose-600`) which is set explicitly on the entry
element. The LABEL has no explicit color, so it inherited the
cascade from `.dark body { color: rgb(226 232 240) }` (slate-200)
in `globals.css:127` — light-text-on-white = invisible.

Root cause: the Tooltip's `contentStyle` set only
`fontSize / borderRadius / border` and didn't pin
`backgroundColor` (Recharts default = white in both themes) or
`labelStyle.color` (Recharts default = inherit). The white tooltip
on a dark chart was also jarring as a depth cue — a real dark-mode
tooltip should sit dark on the dark canvas.

Fix in `frontend/components/PriceHistoryChart.tsx` (single file,
~30 lines added):
- Import `useTheme` from `next-themes` + add `mounted` guard
  (same hydration-safety pattern as `ThemeToggle.tsx:62-65`).
- Compute `isDark = mounted && resolvedTheme === 'dark'` and two
  style objects — `tooltipContentStyle` (BG + border switches
  white/slate-200 ↔ slate-900/slate-700) and `tooltipLabelStyle`
  (color switches slate-900 ↔ slate-100, weight 600).
- Pass both to `<Tooltip>` as `contentStyle` + `labelStyle`.
- Add `boxShadow` per LedgerCraft Elevation spec ("shadows used
  sparingly — only for overlays and dropdowns"); the Recharts
  tooltip is exactly that.
- Pre-mount default is light to match `color-scheme: light` initial
  value in `globals.css:135` (avoids hydration flicker on the
  first paint before the theme resolves).

`itemStyle` deliberately left unset so Recharts continues to color
the item entry with the trend stroke (emerald = up / rose = down)
— that's the Google-Finance-style cue the chart already uses. Both
emerald-500 (`#10b981`) and rose-600 (`#e11d48`) clear AA contrast
against the new slate-900 (`#0f172a`) dark tooltip BG.

No schema / Python / scoring / valuation / output JSON change —
JSX + style-object diff inside one file. Tests unchanged (no
existing tests on `PriceHistoryChart`; the dark-mode toggle path
is exercised by `ThemeToggle.tsx`'s upstream production use).

---

## PR #246 — Issue #246 ERIE fix: extend `_fetch_shares_from_per_filing_xbrl` trigger to catch implausibly-low primary extraction (merged 2026-05-25, `4059b38e`)

Closes [issue #246](https://github.com/dackclup/quantrank/issues/246).

`stock-detail-auditor` 2026-05-25 audit on production `9015748` flagged
ERIE with `raw_metrics.shares_outstanding = 2542` (real ~57M). Root
cause traced by `edgar-debugger` session 2026-05-25: SEC `companyfacts`
aggregate API filters out *dimensional* facts. ERIE Indemnity files
Class A (~54.9M) only with a `dei:` share-class dimension and Class B
(~2,541) without; the aggregate returns Class B only → 2,542 shares
extracted → market_cap $570K → all 6 valuation methods skip via the
existing `FAIR_PRICE_DATA_QUALITY_CEILING = $10K/share` TBVPS gate
→ `data_quality_input_corruption` veto fires correctly. The veto is
working — but ranking still shows ERIE at #69 / composite 60.42
because non-valuation pillars don't observe shares_outstanding.

The PR #182 STZ fallback `_fetch_shares_from_per_filing_xbrl`
(`compute/ingest/fundamentals.py:552-685`) recovers correct shares by
summing dimensional contexts at `period_instant` from per-filing XBRL.
BUT the trigger condition was strict `shares is None` (Issue #176 STZ
signature), so ERIE's non-None 2,542 slipped past → fallback never
fired. PR1 closes the gap.

**Production code changes** (2 files, ~12 net LOC):

- `compute/config.py` — new `MIN_PLAUSIBLE_SHARE_COUNT: int = 100_000`.
  Threshold rationale: S&P 500 index floor (~$15B mcap) at the most
  extreme single-share-price seen on the index (BRK-B ~$500
  post-50:1-split) implies ≥ 30M shares minimum. 100K is 30× safer
  than any plausible legitimate value and catches the ERIE
  dimensional-filter pattern without false-positives on any index
  member.
- `compute/ingest/fundamentals.py:774-803` — trigger extended from
  strict `shares is None` to `shares is None OR shares < MIN_PLAUSIBLE_SHARE_COUNT`.
  Existing `revenue > 0` + `total_assets > 0` gates preserved.
  Logger message updated to surface `primary=<None|count>` so the
  operator can distinguish None-case (STZ signature, PR #182) from
  too-low-case (ERIE signature, this PR) without re-running a probe.

**Side-effect coverage**:

- **BRK-B**: extracted 1.64M shares — ABOVE the 100K threshold, so
  fallback does NOT fire. Existing `data_quality_input_corruption`
  veto stays in place (TBVPS gate fires). Class A → Class B 1500:1
  conversion is a separate methodology call deferred to a follow-up
  PR — bundling it here would couple unrelated entity-specific
  conversion-ratio logic into the generic fix.
- **V (Visa)**: extracted 469M shares — ABOVE threshold, fallback does
  NOT fire. V's failure mode is covered by issue #248 PR2a/PR2b
  (methodology-scientist 2026-05-25 verdict: SPLIT into observability-
  first + escalation policy per Rule 18 Phase 4h.2 precedent).
- **FOXA / NWS / NWSA**: ALL above 100K → not covered by this PR;
  routed to PR2b per `methodology-scientist` Q4 verdict (include in
  regression fixture for that PR, NOT here).

**Backward-compat note**: ERIE's `risk_flags = ['data_quality_input_corruption']`
will STOP firing after this PR lands (since shares_outstanding becomes
plausible). No existing test pins ERIE's veto state (verified via
`grep -r ERIE tests/` — zero hits). ERIE's rank will shift based on
the now-valid valuation pillar values; expected behavior.

**Test coverage** — `test-engineer` spawn writes 12 cases to
`tests/test_ingest/test_fundamentals.py`:

1. Fallback fires when primary returns 2542 (ERIE shape)
2. Fallback does NOT fire when primary returns 100M (normal universe)
3. Fallback fires when primary returns None (STZ backward-compat)
4. Boundary at 99_999 fires
5. Boundary at 100_000 does NOT fire (strict `<`)
6. Boundary at 100_001 does NOT fire
7. Fallback NOT invoked when too-low but revenue=0 (gate preserved)
8. Fallback NOT invoked when too-low but total_assets=0 (gate preserved)
9. Log distinguishes None-case vs too-low-case (caplog)
10. Hypothesis property: fallback fires iff `primary is None or primary < 100_000`
11. Config constant `MIN_PLAUSIBLE_SHARE_COUNT == 100_000` pin
12. `@network` ERIE drift-detector — live SEC, recovered shares ≈ 57M

Tests land in a follow-up commit on the same branch (test-engineer
spawn finishing after the production-code commit).

**Schema impact**: None — fix is in the ingest layer; no new
`StockDetail` / `Metadata` field. Schema stays at `0.10.2-phase4.5e`.

**No CLAUDE.md / AGENTS.md substance change** — this PR is a focused
bug fix that doesn't introduce a new invariant, convention, or gotcha
that future code authors need to remember. The §Gotchas entry for the
shares-extraction pattern (issue #176 + #182) already covers the
class of failure; this PR extends an existing fallback's trigger, not
adds a new mechanism. PHASE_STATUS_INFLIGHT.md side-file satisfies
the §Conventions "ship with every PR" lockstep rule per PR #237
convention.

**Sibling issues filed in same audit batch (2026-05-25)**:
- [#247](https://github.com/dackclup/quantrank/issues/247) NVR
  scoring-layer DQ gap → `methodology-scientist` Mode B owns
- [#248](https://github.com/dackclup/quantrank/issues/248) V/Visa
  cross-source escalation → PR2a + PR2b split per methodology verdict
- [#249](https://github.com/dackclup/quantrank/issues/249) Rebaseline
  `compute-rankings.yml` timeout (durable fix for 2026-05-25 P1)

---

## PR #256 — Issue #248 PR2a + #246 Rule 18 retrofit: cross-source observability surface + shares-fallback counter (merged 2026-05-25, `bc57398a`)

Closes the Rule 18 observability gap surfaced by the post-PR-#253
[methodology-scientist Mode B verdict](https://github.com/dackclup/quantrank/issues/248)
on issue #248 (V/Visa cross-source escalation). Per the verdict's Q5
`SPLIT into PR2a (observability) + PR2b (escalation)` decision and
the Phase 4h.2 forcing precedent (PRs #112 → #118 → #124), this PR
ships the observability surface FIRST so PR2b's severe-threshold
decision (75 / 100 / 150 %) can be calibrated against empirical
1-cron data instead of gut-feel.

**Scope** — locked across 7 grill-me questions (2026-05-25 session 8):

- **Q1 / Option C** — schema includes (a) universe counter
  `Metadata.cross_source_disagreement_count`, (b) universe histogram
  `Metadata.cross_source_delta_histogram`, AND (c) per-ticker
  `StockDetail.cross_source_delta` so post-hoc threshold-sweep analysis
  is possible on any of the 9 buckets.
- **Q2 / Option A** — push hard, land before tonight's cron-#4
  (Mon 22:00 UTC) so the new fields populate on the first cron rather
  than waiting +24 / +48h for cron-#5 / cron-#6.
- **Q3 / Option B** — symmetric histogram buckets around the 100%
  decision boundary: `[<5, 5-25, 25-50, 50-75, 75-100, 100-150,
  150-200, >200, unavailable]` (9 buckets) — gives 4 buckets of
  resolution across 50-150% where the PR2b threshold candidates live.
- **Q4 / Option A** — fold the PR1 (issue #246) Rule 18 retrofit
  into the same schema bump:
  `Metadata.shares_fallback_triggered_count` (union of None +
  too_low) and `Metadata.shares_fallback_too_low_count` (ERIE-class
  subset). One schema bump, one CR.
- **Q5 / Option X** — refactor `validate_market_cap` signature
  `bool` → `tuple[bool, float | None]` for single-source-of-truth
  delta exposure; 1 production callsite update + test sweep. Internal
  function, no external consumers.
- **Q6 / Option A** — schema-only PR; UI rendering deferred to a
  follow-up PR2c so frontend-design-reviewer can iterate against
  real cron data (precedent: PRs #180 / #181 / #224 all schema-only).
- **Q7 / Option C** — histogram covers ALL deltas (not just firing
  > 5%): the `<5` and `unavailable` buckets are explicit so future
  tolerance recalibration + yfinance coverage health are observable
  without re-running the validator. Field renamed
  `cross_source_disagreement_histogram` → `cross_source_delta_histogram`
  to match the broader semantics.

**Production code changes**:

- `compute/config.py` — `SCHEMA_VERSION` bumped `0.10.2-phase4.5e`
  → `0.10.3-phase4.5e` (PATCH; all 4 new fields nullable / additive).
- `compute/ingest/cross_source.py` — `validate_market_cap` refactored
  to tuple return; new `bucket_delta()` helper + `BUCKET_KEYS` public
  tuple (drift-detector pin).
- `compute/ingest/fundamentals.py` — `_FALLBACK_STATS_LOCK` +
  module-level counter dict + `reset_fallback_stats()` /
  `get_fallback_stats()` public functions. Lock acquired inside
  `_build_snapshot` because the function runs under a ThreadPool
  in main.py (sequential-counter pattern from share_count_extraction
  doesn't apply — fallback fires before snapshot returns, and adding
  per-snapshot metadata would pollute the serialized schema).
- `compute/main.py` — import the new helpers; `reset_fallback_stats()`
  before the fundamentals fetch loop; init `cross_source_*` counters
  before the per-ticker scoring loop; update callsite to tuple-unpack
  + increment counter / histogram bucket / per-ticker delta dict;
  `get_fallback_stats()` after the loop; wire all 4 new fields into
  `Metadata(...)` + `StockDetail.cross_source_delta` constructor.
- `compute/output/schemas.py` — 3 `Metadata` fields + 1 `StockDetail`
  field with full docstrings (bucket boundary table + lifecycle notes).

**Frontend lockstep** (schema-triple per §Conventions):

- `frontend/lib/types.ts` — mirrors the 4 new Pydantic fields.
- `frontend/lib/schema-snapshot.json` — regenerated via
  `python -m compute.output.schema_check --update-snapshot`; schema
  check passes.

**Empirical baseline** (Sat 9015748 production cron, pre-fix):
22/502 = 4.4% tickers fire `cross_source_disagreement` (within
expected 3-8% band per quarterly-cohort-audit/SKILL.md). The 22
include V ($154B SEC vs ~$580B yf, 276% delta = `>200` bucket post-
fix), FOXA (~26% = `25-50` bucket), and 20 others spanning the
candidate decision range.

**ZERO behavior change** — composite / risk_flags / fair_price /
top5 rotation unchanged. Per-method valuation outputs unchanged.
The validator fires the same annotate at the same 5% threshold;
the only difference is the second tuple-element is now consumed
by the observability layer instead of discarded.

**PR2b gate** — after this PR lands + cron-#4 22:00 UTC populates
the new Metadata fields, the histogram tail mass directly answers
"if severe threshold = 75% → fire X; = 100% → fire Y; = 150% →
fire Z". Methodology-scientist Mode B will pick the threshold from
that empirical distribution.

**Deferred follow-ups** (not in this PR):
- PR2b — `cross_source_disagreement_severe` sibling flag + weight
  10.0 (methodology Q1) + V XBRL conversion-equivalent fix (Q2-Q3)
  + NWS/NWSA regression fixture (Q4). Gated on this PR's cron data.
- PR2c — frontend UI surface for `cross_source_delta` chip /
  histogram debug panel. Spawn frontend-design-reviewer with real
  numbers from PR2a cron.
- Q3 2026-08-19 quarterly cohort audit reads
  `Metadata.cross_source_disagreement_count` + histogram as a
  defense-layer health signal alongside the existing 27 annotates.

---

## PR #257 — V/FOX/BRK-B multi-class XBRL fix + Issue #248 mechanical recovery (PR2b) (merged 2026-05-25, `4226b19c`)

**Background** — PR2a (PR #256, merged 2026-05-25) shipped the
cross-source observability surface. PR2b is the **mechanical recovery
half** of the Issue #248 split — the half that doesn't need cron-#4
data because it's about the V/Visa undercount root cause (companyfacts
aggregate API filters dimensional facts), not the severe-flag threshold
calibration (that's PR2c, blocks on cron-#4 histogram data).

**Scope** — locked across 6 grill-me questions (2026-05-25 session 9,
grill-with-docs skill):

- **Q1 / Option SPLIT** — PR2a (PR #256) shipped observability; PR2b
  ships mechanical V/NWS/NWSA/FOX/FOXA/BRK-B XBRL recovery; PR2c later
  ships the `cross_source_disagreement_severe` flag. Decoupling means
  V holders see correct `market_cap` THIS WEEK without waiting on
  cron-#4 + methodology Mode B verdict on severe threshold.

- **Q2 / Option D (allowlist)** — performance-engineer Mode B (2026-05-25)
  rejected universal peek-XBRL: adds ~5 min wall-clock at warm cache,
  breaches the <5 min budget. Current p95 fundamentals latency 16.25s
  (1.25s over the 15s warn threshold). Allowlist limits peek to 7
  tickers → ~5s wall-clock total.

- **Q3 / Option 0% threshold** — methodology-scientist Mode B
  (2026-05-25) rejected the originally-proposed 10% gap threshold as
  WRONG SHAPE not just wrong number. Damodaran 2019 *Investment
  Valuation* 3rd ed. Ch. 16: total common shares outstanding = sum
  across all classes; voting-premium discount applies to PRICE only.
  The summed dimensional value is **definitionally** the truth when
  the XBRL exposes dimensional contexts. A 10% gate would suppress
  the truth for any filer with minor classes < 10% of total. New
  rule: `summed_dimensional > primary` (any positive delta) wins.

- **Q4 / Option SPAWN PARALLEL** — methodology-scientist (opus) +
  performance-engineer (sonnet) ran in parallel pre-code. Both
  agents independently rejected the original 10% / universal-peek
  design, converging on the allowlist + 0% threshold combo. The
  parallel-validate pattern caught a major design mismatch that
  would have failed reviewer + cron post-merge — confirming the
  Rule 18 observability-before-wiring discipline extends to
  observability-before-design.

- **Q5 / Option A (D allowlist + 0% threshold)** — rejected C
  ("D now + scout PR later for universal discovery") as overengineering
  per CLAUDE.md §"Doing tasks": "Don't design for hypothetical future
  requirements." `cross_source_disagreement` annotate already serves
  as the discovery mechanism for new multi-class tickers; Q3 cohort
  audit is the canonical expansion venue (no separate scout PR
  needed).

- **Q6 / Option 6-A (defer BRK-B Class A weighting)** — edgar-debugger
  verdict (2026-05-25) confirmed allowlist completeness: `{V, NWS,
  NWSA, STZ, FOX, FOXA, BRK-B}` (7 tickers, not the originally-proposed
  4). GOOG / GOOGL deliberately excluded — they file non-dimensionally,
  companyfacts returns the correct total. BRK-B has a residual ~14%
  undercount because Class A shares carry 1500x economic weight per
  share vs Class B — the naive dimensional sum (Class A 1.46M +
  Class B 2.14B) ignores the conversion ratio. Naive fix still a
  1300x improvement on the current $799M → ~$1.04T market_cap;
  perfect fix (`Class_A * 1500 + Class_B`) deferred to Q3 2026-08-19
  cohort audit follow-up since it requires ticker-specific economic-
  equivalence math (code smell that needs methodology Mode B before
  landing in the ingest hot path).

**Production code changes**:

- `compute/config.py` — `SCHEMA_VERSION` bumped
  `0.10.3-phase4.5e` → `0.10.4-phase4.5e` (PATCH; additive Metadata
  field only). New `MULTI_CLASS_SHARE_ALLOWLIST: frozenset[str]` of
  7 tickers with full Damodaran-anchored provenance docstring +
  BRK-B caveat note + expansion-gate procedure.
- `compute/ingest/fundamentals.py` — `_FALLBACK_STATS` dict gains
  `dimensional_override` key; `reset_fallback_stats()` +
  `get_fallback_stats()` cover the new counter. New `elif` branch
  in `_build_snapshot` fires when ticker is in the allowlist AND
  primary returned a PLAUSIBLE value (not None, not too low) AND
  the rest of the snapshot looks healthy. Inside the branch: call
  `_fetch_shares_from_per_filing_xbrl` (same function PR #182
  introduced for the STZ None-trigger path — reused, not
  duplicated), compare summed vs primary, override + increment
  counter + log INFO if `summed > primary`.
- `compute/main.py` — read the new counter from
  `get_shares_fallback_stats()`, log it alongside the existing
  pair, wire to `Metadata.shares_fallback_dimensional_override_count`.
- `compute/output/schemas.py` — new
  `Metadata.shares_fallback_dimensional_override_count: int | None`
  with full docstring (disjoint from `triggered_count`, expected
  steady-state firing rate 6-7).

**Frontend lockstep** (schema-triple per §Conventions):

- `frontend/lib/types.ts` — mirrors the new optional field.
- `frontend/lib/schema-snapshot.json` — regenerated via
  `python -m compute.output.schema_check --update-snapshot`;
  schema check passes.

**Test pin** (`tests/test_ingest/test_fundamentals.py`):

7 new offline tests covering: (a) V Class A → A+B+C override fires;
(b) BRK-B Class A → A+B naive sum override (with docstring note on
14% residual); (c) STZ-like edge where summed ≈ primary (override
fires per Damodaran 0% rule — any positive delta wins); (d) AAPL
NOT in allowlist → peek is never called; (e) defensive: summed <
primary → no override (guards against bad XBRL); (f) ERIE-style
too-low primary → hits existing None / too_low branch, NOT the new
dimensional branch; (g) `get_fallback_stats()` returns all 3 keys
correctly after reset. Plus `tests/test_config.py` schema-version
pin update `0.10.3 → 0.10.4` AND a new
`test_multi_class_share_allowlist_membership` pin (catches
accidental removal / addition of a ticker without the EPS cross-
check verification step).

**Allowlist verification** (edgar-debugger Mode B 2026-05-25):

EPS cross-check on production `frontend/public/data/stocks/<TICKER>.json`
(no live network needed):
- V: 469M extracted → 5.4B true (4.5x undercount); calc EPS $47.38 vs
  reported $10.50 ✓
- NWS / NWSA: 561M → 877M (1.56x); same CIK confirmed ✓
- STZ: None-trigger path already handles (existing PR #182) ✓
- FOX / FOXA: 443M → 985M (2.2x); same CIK confirmed ✓
- BRK-B: 1.46M → 2.14B naive sum (1300x improvement; ~14% residual
  deferred) ✓
- GOOG / GOOGL: extracted 12.12B = 99.3% of known 12.2B total →
  companyfacts works correctly, NOT in allowlist
- WBD: single-class Series A → NOT in allowlist
- BF.A / BF.B / DISH / PARA: NOT in S&P 500 universe → irrelevant

**ZERO behavior change for non-allowlist tickers** — composite /
risk_flags / fair_price / top5 rotation unchanged for the 495 other
S&P 500 tickers. The 7 allowlist tickers will see their
`shares_outstanding` corrected (V/NWS/NWSA/FOX/FOXA/BRK-B), which
flows downstream to `market_cap` + `pe_ratio_ttm` + fair-price
ensemble — meaning some Top-N rank moves are likely. STZ unchanged
(already on the None-trigger path).

**Expected Metadata fingerprint** (post first cron after merge):
- `shares_fallback_triggered_count` ≈ 1-3 (STZ + ERIE existing)
- `shares_fallback_too_low_count` ≈ 1 (ERIE)
- `shares_fallback_dimensional_override_count` ≈ 6 (V + NWS + NWSA
  + FOX + FOXA + BRK-B; STZ may not appear here because the None-
  trigger path captures it first)

**Deferred follow-ups** (not in this PR):
- BRK-B Class A 1500x weighting — Q3 2026-08-19 cohort audit gate.
- PR2c — `cross_source_disagreement_severe` flag (the OTHER half of
  Issue #248, blocked on cron-#4 histogram + methodology Mode B
  verdict on severe threshold 75 / 100 / 150%).
- IBKR NI-attribution issue (edgar-debugger surfaced, low priority,
  separate from PR2b scope).

---

## PR #258 — mattpocock-setup-harness scaffold (merged 2026-05-25, `5a533ed5`)

**Background** — the vendored `mattpocock-setup-harness` skill
configures per-repo glue files (`docs/agents/issue-tracker.md`,
`docs/agents/domain.md`, optional `docs/agents/triage-labels.md`) that
the other vendored engineering skills (`to-issues`, `to-prd`,
`improve-codebase-architecture`, `diagnose`, `tdd`) read on invocation.
Until this PR they didn't exist; the skills fell back to upstream-
default assumptions which don't match QuantRank's actual layout (no
`CONTEXT.md`; ADRs live in `PHASE_STATUS_INFLIGHT.md`, not
`docs/adr/0001-*.md`).

**Scope** — locked in one chat round (no grill-me — the harness setup
is itself a deterministic 3-decision script):

- **Section A (issue tracker)** — GitHub via the GitHub MCP server
  (NOT the `gh` CLI; the remote execution environment doesn't ship
  `gh`). The MCP tools cover every operation `gh` would; surface is
  restricted to the `dackclup/quantrank` repo per CLAUDE.md
  §Connectors.
- **Section B (triage labels)** — DELIBERATELY SKIPPED. The upstream
  `triage` skill is not vendored in QuantRank (skipped at the
  2026-05-20 base sync per `THIRD_PARTY_NOTICES.md`), so a triage
  label vocabulary would be dead config. The CLAUDE.md §Agent skills
  block documents the skip + the re-run gate if `triage` is later
  vendored.
- **Section C (domain docs)** — declared "single-context" for the
  upstream binary axis, but the `docs/agents/domain.md` body
  documents QuantRank's actual layout: the `CONTEXT.md` analog is
  **multi-file** (CLAUDE.md + docs/METHODOLOGY.md + SKILL.md +
  WORKFLOW.md) and the ADR analog is `PHASE_STATUS_INFLIGHT.md`.
  This adaptation note pre-dates the harness scaffold — it was
  written into `.claude/skills/mattpocock-grill-with-docs/SKILL.md`
  trailer when grill-with-docs was vendored in PR #256.

**Files** (4):

- `docs/agents/issue-tracker.md` (new) — GitHub MCP conventions +
  frugality note + skip rationale for `gh` / GitLab / `.scratch/`.
- `docs/agents/domain.md` (new) — upstream-instruction →
  QuantRank-file mapping + project vocabulary list + ADR-conflict
  flag protocol.
- `CLAUDE.md` — new `## Agent skills` section (3 subsections); new
  `docs/agents/` row in §Layout table; 2 new entries in §Companion
  files.
- `PHASE_STATUS_INFLIGHT.md` (this entry).

**ZERO behavior change** — doc-only chore. No compute / schema /
scoring / valuation / frontend / Python / TS production-code change.
`schema_check` trivially passes (no schema touched). `ruff` /
`pytest` unaffected.

**Cross-tool lockstep** — AGENTS.md is NOT touched in this PR; the
`docs/agents/*` files are Claude-Code-skill-specific (consumed by
the vendored mattpocock skills, which only run in Claude Code
sessions). Cross-tool agents (Copilot / Cursor / Devin) don't
invoke mattpocock skills, so a mirror to AGENTS.md would be
no-op for them. The PR is doc-only and the §Conventions lockstep
rule is satisfied via this `PHASE_STATUS_INFLIGHT.md` entry per
the side-file convention adopted in PR #237.

**Deferred follow-ups**:

- If a future `vendor-sync` run pulls upstream `triage` skill,
  re-run `/mattpocock-setup-harness` to add the §B triage label
  block. Today the gate is a no-op.
- If a future PR introduces a `CONTEXT.md` at the repo root
  (unlikely — QuantRank's multi-file pattern is durable), update
  `docs/agents/domain.md` accordingly.

---

## PR #263 — 15-agent self-audit follow-up: bug-fix bundle + doc-drift sweep + BLY 2002 citation correction (merged 2026-05-26, `25080c33`)

Output of the 15-parallel-agent self-audit run on `claude/eager-bohr-12bQi`
(branch HEAD `ba13f80`). All 15 agents reported; consolidated synthesis
identified 5 BLOCKERS + 13 MAJORs + 12 NITs across code + docs + literature.
This PR bundles the actionable items into one focused change.

**Code fixes (3 files)**:

- **`compute/ingest/fundamentals.py`** — `_build_snapshot` Issue #248
  PR2b dimensional override `elif` branch now gates on
  `not os.environ.get("QR_SKIP_FUNDAMENTALS")`. Closes the ci-triage-engineer
  session-7 finding that PR #257's multi-class peek-XBRL path fired
  unconditionally even when the CI escape-hatch env var was set,
  contributing to the simulate 90m01s cancel pattern. Primary plausible
  value is still written; only the multi-class refinement (V/NWS/NWSA/
  FOX/FOXA/BRK-B/STZ allowlist) is skipped. Weekly cron unchanged
  (env var unset → full precision path).
- **`frontend/components/PriceHistoryChart.tsx`** — `<ReferenceLine y=
  {fairPriceMax}>` `stroke` + `label.fill` were hard-coded `#0f172a`
  (slate-950) which IS the dark-mode body bg → Target reference line
  + its label rendered INVISIBLE in dark mode. Fixed via the existing
  `isDark = mounted && resolvedTheme === 'dark'` guard already
  imported for the tooltip path (PR #255). Light mode unchanged; dark
  mode now shows the Target line as `#e2e8f0` (slate-200) for AAA
  contrast against `slate-950` canvas.
- **`compute/scoring/manipulation_index.py` + `compute/scoring/restatement_filings.py`**
  — `late_filing_notification` flag academic citation corrected.
  `literature-searcher` 2026-05-26 verified that the "Bartov-Lai-Yeung
  2002 *JAR*" attribution in module docstring + LATE_FILING_WEIGHT
  provenance block + module References list was **a hallucinated
  citation**. No paper with the Bartov-Lai-Yeung author tuple exists
  in JAR or any related accounting journal. The real anchor is
  **Bartov & Konchitchki 2017 *Accounting Horizons* 31(4) "SEC
  Filings, Regulatory Deadlines, and Capital Market Consequences"**
  — NT-10Q late filings drive a -2.93% 5-day abnormal return, NT-10K
  -1.96%, both drifting downward in post-filing months. 5 sites
  corrected (module References list, LATE_FILING_WEIGHT provenance
  docstring, restatement_filings module docstring + References block,
  + 2 doc cross-references in CLAUDE.md / AGENTS.md). Weight 5.0
  unchanged — the underlying finding (late filings carry negative
  predictive power) holds; only the paper attribution was wrong.

**Doc-drift sweep (7 files)**:

- **`docs/METHODOLOGY.md`** — BLOCKER fixes: line 16 intro
  rewritten "10 active defenses — 4 vetoes + 5 numerical guards +
  7 annotate-only flags" → "33 active defenses — 7 vetoes + 5
  numerical guards + 21 annotate-only flags, plus the
  `manipulation_index` rollup" (intro arithmetic now reconciles
  with the body sections). §"Annotate-only flags" section header
  `(18)` → `(21)`. THREE missing bullets added per methodology-
  scientist (opus) authoritative content: `rem_suspect` (Roychowdhury
  2006 *JAE*), `insider_sell_cluster` (Cohen-Malloy-Pomorski 2012
  *JFE*), `c_suite_unusual_sell` (Jeng-Metrick-Zeckhauser 2003 *JAR*
  §V). `late_filing_notification` bullet citation also corrected to
  Bartov & Konchitchki 2017 with effect-size figures inline.
- **`PHASE_STATUS.md`** — §Current state table: schema `0.10.2` →
  `0.10.4-phase4.5e` (catches up to PR #256 + #257); skill inventory
  43 → 44 (mattpocock-grill-with-docs added on the harness chore);
  date 2026-05-24 → 2026-05-26.
- **`SKILL.md`** — §Repository Structure `38 skills` → `44`. Schema-
  version table gains 2 missing rows: `0.10.4-phase4.5e` (PR #257
  multi-class dimensional override) + `0.10.3-phase4.5e` (PR #256
  cross-source observability 4-field surface).
- **`CLAUDE.md`** — §Auto-routing §Main agent role: "15-agent team"
  → "18-agent team" (post-PR #225 expansion: `ci-triage-engineer` +
  `vercel-preview-auditor` + `literature-searcher`). §Phase status
  PR #184 entry's `late_filing_notification` provenance corrected
  to Bartov & Konchitchki 2017 with a note that the original
  Cohen-Malloy-Pomorski 2012 mis-attribution was caught + replaced
  with what turned out to also be hallucinated (BLY 2002 *JAR*),
  then literature-searcher verified the correct anchor on 2026-05-26.
- **`AGENTS.md`** — 6 lockstep fixes: §Project structure skill count
  42 → 44; §Project structure hooks list adds `delegate-first.sh`;
  §Security considerations expands `FORM4_FETCH_SKIP=1` single-bullet
  to the full 5-var CI escape-hatch combo (`FORM4_FETCH_SKIP` +
  `QR_SKIP_TIER2` + `QR_SKIP_FUNDAMENTALS` + `QR_SKIP_OSAP` +
  `QR_SKIP_CROSS_SOURCE`); `dependency-auditor` CVE baseline
  `25-active-CVE` → `15-active-CVE` (PR #194 + #226 wave closed 10);
  Two PostToolUse hooks paragraph rewritten to "Three hooks
  (2 PostToolUse + 1 UserPromptSubmit)" with `delegate-first.sh`
  description; `stock-detail-auditor` "≤ 20 tickers per run" stale
  claim removed (cap lifted in PR #219); "15 agent prompts" + "11 of
  15 agents" → "18" / "14 of 18".
- **`WORKFLOW.md`** — Phase 4.5 Defense Roadmap row for
  `c_suite_unusual_sell` updated: spec `> 5× comp / 90d` → actual
  implementation `≥ 2 distinct CEO/CFO/President insiders, 30-day
  window` per Jeng-Metrick-Zeckhauser 2003 §V (matches PR #222
  emit semantic); `late_filing_notification` citation corrected to
  Bartov & Konchitchki 2017; `insider_sell_cluster` thresholds
  expanded to match Phase 4.5e PR3 implementation.
- **`README.md`** — §Honest Limitations gains explicit Phase 4.5e
  Form-4 insider clustering paragraph (`insider_sell_cluster` +
  `c_suite_unusual_sell` + 10b5-1 filter); `late_filing_notification`
  citation corrected.

**GitHub issues filed (2)**:

- **[#261](https://github.com/dackclup/quantrank/issues/261) GOOG/GOOGL multi-class shares overcount** —
  stock-detail-auditor surfaced that BOTH `GOOG` (Class C) and
  `GOOGL` (Class A) tickers store Alphabet's 12.12B total shares
  (companyfacts returns the aggregate without dimensional
  disaggregation for this filer), giving each ticker a $4.6T market
  cap vs real ~$1.05T per class (4.4× overcount, opposite direction
  to the PR #257 allowlist pattern which fixes UNDERCOUNTS). The
  allowlist's `summed > primary wins` invariant rules out a naive
  extension — for GOOG/GOOGL the primary is ALREADY the summed
  value and the per-class value would be smaller. No defense flag
  catches it (`data_quality_input_corruption` doesn't fire because
  shares are plausible-magnitude; `cross_source_disagreement`
  doesn't fire because yfinance also uses the aggregate).
- **[#262](https://github.com/dackclup/quantrank/issues/262) DQIC dual-surface emission inconsistency** —
  defense-layer-auditor + stock-detail-auditor confirmed that
  `data_quality_input_corruption` emits to TWO surfaces from TWO
  distinct check sites: `risk_overlay.py:411` (veto surface, fires
  when TBVPS > ceiling OR revenue tag mis-pick OR |NI| > |revenue|)
  AND `valuation/ensemble.py:545` (annotate surface, fires when
  ANY of the 6 valuation method outputs > ceiling). The valuation-
  layer check is BROADER than the risk-overlay check, so a ticker
  (e.g., NVR) can land in `valuation_warnings` but NOT
  `risk_flags` — meaning the veto wouldn't fire if NVR ever rose
  into Top-5 contention. Currently NVR is rank ~267 so no live
  safety impact. Fix requires methodology-scientist Mode B sign-off
  on which surface is authoritative; deferred to a focused PR.

**Verification**:

- `ruff check .` clean
- `pytest tests/ -m "not network"` — full suite unchanged from
  pre-PR baseline (no new tests added; no production logic changed
  except the QR_SKIP guard which has zero behavior change on the
  weekly cron's unset path)
- `python -m compute.output.schema_check` clean (no schema fields
  touched; only docstring + comment edits in `compute/`)
- `cd frontend && npx --no -- tsc --noEmit` clean for edited files
- `cd frontend && npx --no -- next build` clean

**Sub-agent runtime**: 15 read-only audit agents ran fully thorough
(no caps); the 2 follow-up agents (methodology-scientist Mode B for
3 missing METHODOLOGY.md bullets + literature-searcher for BLY 2002
verification) ran in parallel for the substance/citation deliverables.
Total agent-hours: ~12h aggregate sonnet pool. Demonstrates the
PR #219 + PR #223 "spawn-thorough-don't-cap-the-pool" discipline
working as designed.

CLAUDE.md + AGENTS.md substance touched in lockstep (multiple §sections
each); §Conventions "ship with every PR" rule satisfied. This
PHASE_STATUS_INFLIGHT.md entry mirrors the changes for parallel-PR
safety per PR #237 convention.

---
