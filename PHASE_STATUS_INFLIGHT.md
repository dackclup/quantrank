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

## PR #269 — Issue #261 PR-B: per-class XBRL extraction (structural fix for GOOG/GOOGL `$4.6T` overcount) (merged 2026-05-26, `5bf38c12`)

Closes the structural half of [issue #261](https://github.com/dackclup/quantrank/issues/261) — the OVERCOUNT pattern where SEC `companyfacts` returns Alphabet's 12.12B total shares to both per-class tickers, producing `$4.6T` market_cap per ticker vs the real ~$1.05T per class. PR-A (PR #264, merged) shipped the `multi_class_aggregate_shares_suspected` annotate observability; **this PR-B ships the actual fix**.

Per methodology-scientist Mode B verdict 2026-05-26 (Path 1 — reverse-allowlist per-class XBRL extraction) + edgar-debugger live probe 2026-05-26 (Alphabet 10-K accession `0001652044-26-000018` confirms per-class dimensional contexts are available with one critical filer-namespace gotcha).

**The fix**:

- **`compute/config.py`** — new `MULTI_CLASS_OVERCOUNT_ALLOWLIST: dict[str, str]` mapping ticker → exact XBRL class-member string:
  - `GOOGL → "us-gaap:CommonClassAMember"` (standard namespace)
  - `GOOG  → "goog:CapitalClassCMember"` ← **filer-specific namespace gotcha** caught by the edgar-debugger probe. An allowlist keyed to the standard `us-gaap:CommonClassCMember` would silently return zero rows and let the overcount through. Each new allowlist entry needs live XBRL probe confirmation.
- **`compute/ingest/fundamentals.py`** — extended `_fetch_shares_from_per_filing_xbrl` with `target_class_member: str | None = None` parameter. When set, filters dimensional contexts to ONLY rows whose `us-gaap:StatementClassOfStockAxis` equals the target member (vs the default sum-all mode that PR #257 uses for the OPPOSITE-direction undercount path).
- **`compute/ingest/fundamentals.py`** — new elif branch in `_build_snapshot` fires when ticker is on the new allowlist + primary is plausible (aggregate-shape) + `QR_SKIP_FUNDAMENTALS` not set. Calls the filter mode; overrides primary IFF per_class < primary (sanity invariant — the per-class subset MUST be smaller than the aggregate). Skips the override on per_class >= primary AND increments `mc_reconcile_failure` defensive counter.
- **`compute/output/schemas.py`** — two new `Metadata` fields (additive): `multi_class_per_class_override_count: int | None` (expected steady-state ≈ 2 = GOOG + GOOGL) + `multi_class_mc_reconcile_failure_count: int | None` (Rule-18 defensive guard per methodology Q3 — fires when per-class fraction is outside the expected 5-95% band of primary OR when override is skipped on per_class >= primary).
- **`compute/main.py`** — wire both counters from `_FALLBACK_STATS` to the Metadata construction.
- **`frontend/lib/types.ts` + `frontend/lib/schema-snapshot.json`** — triple lockstep.

**Schema bump**: `0.10.5-phase4.5e` → `0.10.6-phase4.5e` (PATCH; two additive optional `Metadata` fields).

**Tests** (1216 → 1225, +9 new):

- `tests/test_config.py` — schema-version pin update, new `MULTI_CLASS_OVERCOUNT_ALLOWLIST` membership pin (verifies exact `goog:CapitalClassCMember` namespace string), disjoint-allowlist invariant test
- `tests/test_ingest/test_fundamentals.py` — 7 new cases: GOOG override with filer-namespace, GOOGL override with standard namespace, non-allowlist ticker doesn't fire, `QR_SKIP_FUNDAMENTALS` escape-hatch, per_class >= primary sanity skip, mc_reconcile warning on <5% fraction, None return silently skipped. Plus 3 existing `_FALLBACK_STATS` tests updated to the new 5-key dict shape (was 3 keys).

**Edgar-debugger live probe findings** (from PR-A INFLIGHT entry, repeated here for tag-cut completeness):

- Filing inspected: Alphabet 10-K accession `0001652044-26-000018`, FY2025
- Per-class breakdown via `us-gaap:CommonStockSharesOutstanding`:
  - `us-gaap:CommonClassAMember` = 5.822B → **GOOGL**
  - `us-gaap:CommonClassBMember` = 0.837B (founders, not traded)
  - `goog:CapitalClassCMember` = 5.429B → **GOOG**
- Per-class sum (5.822 + 0.837 + 5.429 = 12.088B) reconciles to the aggregate `companyfacts` value exactly (Damodaran 2019 Ch. 16 identity)

**ZERO behavior change for 500 non-allowlist tickers**. The 2 allowlist tickers (GOOG + GOOGL) gain a corrected `shares_outstanding` (~5.4B / ~5.8B from the prior 12.12B overcount) which flows through to:
- `market_cap` (corrected from ~$4.6T → ~$1.05T per class)
- `pe_ratio_ttm` (re-derives from NI / corrected shares)
- Fair-price ensemble (Graham / multiples / RIM / DCF re-anchor to corrected per-share inputs)
- `multi_class_aggregate_shares_suspected` annotate continues to fire (CIK collision invariant holds for GOOG + GOOGL pair) — PR-A's observability surface stays informative

Expected rank impact: GOOG + GOOGL likely move significantly in composite ranking (currently mid-rank with `value_trap_risk` from the overcount-inflated price ratios; with corrected MC the value pillar should normalize). Composite delta capped by the universe-level normalization but the per-stock display becomes correct.

**Verification**:
- `ruff check .` — clean
- `python -m compute.output.schema_check` — triple in sync at `0.10.6-phase4.5e`
- `pytest tests/ -m "not network"` — **1225 passed**, 7 skipped (factors extras), 24 deselected
- `@network` GOOG / GOOGL drift-detector — deferred to a separate follow-up PR (live SEC fetch isn't a blocker; the unit tests with mocked XBRL fully exercise the code path, and edgar-debugger already did the live probe)

**Deferred follow-ups** (not in this PR):

- `@network` GOOG / GOOGL drift-detector tests (live SEC probe with `EDGAR_USER_AGENT`) — adds the `test_goog_googl_per_class_recovers_correct_shares` shape for cron-time regression catching
- Q3 2026-08-19 quarterly cohort audit: walk `multi_class_per_class_override_count` + `multi_class_mc_reconcile_failure_count` history; consider promoting `multi_class_aggregate_shares_suspected` annotate retirement once override coverage is comprehensive (≥ 2 crons of clean reconcile with `mc_reconcile_failure_count = 0`)
- Future multi-class S&P 500 additions discovery: walk universe-wide `multi_class_aggregate_shares_suspected` annotate firings that AREN'T already on the new allowlist — discovery signal for new aggregate-only filers requiring expansion

PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with every PR" lockstep per PR #237 convention. No CLAUDE.md / AGENTS.md substance change required — the structural fix continues the documented Issue #261 split (PR-A annotate + PR-B structural) and doesn't introduce new invariants.

---

## PR #268 — New skill: `good-code-bad-code-review` reference catalog (Miler / milerdev paired good/bad examples) (merged 2026-05-26, `f79548f0`)

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

## PR #267 — Post-release housekeeping: backfill v1.3.0-phase4.5e pointer + drain 11 stale (in flight) markers (merged 2026-05-26, `a70978af`)

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

## PR #271 — Distill Agentic 6-Phase Cadence into WORKFLOW.md + CLAUDE.md (merged 2026-05-27, `75b6c682`)

Refactors the user-shared research report
(`02d29fc4-Research_Report.md`, an artifact analysis + Master Prompt + 6
phase sub-prompts + CLAUDE.md template) into the existing doc surface
without creating a new `.claude/skills/agentic-6-phase/` skill. The
report's underlying logic is already implemented in QuantRank's 18
subagents + `CLAUDE.md` §Auto-routing policy; what was genuinely
missing was a 6-phase mapping table a new session can scan in < 30 sec
on top of the 9 phases below.

**Scope (2 files, ≤ 1 page each)**:

- **`WORKFLOW.md`** — new section "Agentic 6-Phase Cadence" inserted
  between §"Tools You'll Use Daily" and §"Phase Overview". Single
  mapping table (Step × Fire trigger × Subagent(s) × Done when) plus
  5 invariant bullets. Reuses existing 18 subagents only — no new
  agent files. Session-start protocol cites the actual numbers from
  PHASE_STATUS.md: schema `0.10.5-phase4.5e` (PRs #264 + #265; cron
  #4 still at `0.10.4`, next cron Wed 2026-05-27 re-renders at
  `0.10.5`), defense layer **33 declared** = 7 vetoes + 26 annotates,
  release tag `v1.3.0-phase4.5e`, CVE baseline **15 open** (down
  from 25 after PR #194 patch + PR #226 triage).
- **`CLAUDE.md`** — new §Conventions bullet "Session-start phase
  identification" (~5 lines) pointing readers at PHASE_STATUS.md
  §"Current state" + WORKFLOW.md §"Agentic 6-Phase Cadence" as the
  routing source. No duplication of the cadence table.

**Out of scope (deliberately NOT done per user direction 2026-05-27)**:

- ❌ NOT creating `.claude/skills/agentic-6-phase/` — overhead
  exceeds benefit (the 18 subagents ARE the per-phase prompts;
  cadence is referenceable inline)
- ❌ NOT copying Master Prompt + 6 phase sub-prompts from the
  artifact into the repo — they stay outside the repo as a reference
  card for new sessions
- ❌ NOT touching any of the 18 subagent files under
  `.claude/agents/`
- ❌ NOT touching AGENTS.md substance — the cadence section is
  Claude-Code-subagent-specific; cross-tool agents (Copilot / Cursor
  / Devin) don't have access to `.claude/agents/` and would route
  differently. This INFLIGHT.md entry satisfies the §Conventions
  "ship with every PR" lockstep per PR #237 convention.

**Verification**:
- `ruff check .` — N/A (no Python touched)
- `python -m compute.output.schema_check` — N/A (no schemas touched)
- `pytest tests/ -m "not network"` — N/A (no test surface)
- `docs-reviewer` subagent run BEFORE commit per user acceptance
  criteria (drift check vs PHASE_STATUS.md + SKILL.md)
- Markdown-only diff; ~45 added lines across `WORKFLOW.md` + ~6
  added lines in `CLAUDE.md`

**Deferred follow-ups** (not in this PR):
- Re-evaluate the "Agentic 6-Phase Cadence" section at the Q3
  2026-08-19 quarterly cohort audit — confirm the table's subagent
  mapping still matches the live `.claude/agents/` roster (currently
  18; could grow). If a new subagent doesn't fit a step cleanly,
  consider adding a 7th cadence step OR a "Cross-cutting" row.
- Optional companion in `AGENTS.md` §"Multi-session audit pattern"
  pointing cross-tool agents at the same WORKFLOW.md section as a
  read-only reference (substance is QuantRank-internal and uses
  Claude Code's `Agent` tool which Copilot / Cursor / Devin don't
  have; mirror is optional, not required).
- **SKILL.md schema-version table backfill** — pre-existing drift
  surfaced by `docs-reviewer` 2026-05-27 (not introduced by this
  PR): SKILL.md's schema-version table stops at `0.10.4-phase4.5e`;
  rows for `0.10.5-phase4.5e` (PR #264 `multi_class_aggregate_shares_suspected_count`)
  and the `valuation_output_anomalous` identifier rename (PR #265,
  no schema bump) are missing. Escalate to `schema-sentinel` /
  `docs-reviewer` as a separate doc-only PR; this PR does NOT block
  on it because the gap is pre-existing and orthogonal to the
  cadence-distillation scope.

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

## PR #280 — Phase 4.6 task #2b: forward-return loader from gitignored price cache (merged 2026-05-27, `1ef962cd`)

Sixth unit of the Phase 4.6 honest re-validation harness (task chain
#2a → #2b → #2c → #2d → #2e → #2f per
`docs/research/historical-revalidation-harness.md`). After PR #277
(universe-drift, #2 first unit) + PR #278 (`ranking_history`, #2a) +
PR #279 (`manipulation_distribution`, #2e), this PR adds the forward-
return loader (#2b) — the OTHER half of the honest IC re-baseline
that #2c will compute (ranking @ T from #2a, paired with realized
return at T + horizon from this PR).

**The new module**: `compute/validation/forward_returns.py`

- `compute_forward_return(ticker, as_of_date, horizon_months, *, cache_dir=None) -> float | None`
  — close-to-close N-month total return at `as_of_date` for `ticker`.
  Returns `None` when (a) no cached parquet, (b) no close column, (c)
  as-of doesn't snap to a trading day within 5 calendar days, (d)
  horizon-end is past the last cached row (censored), or (e)
  start_close non-positive / NaN / end_close NaN.
- `compute_forward_return_detailed(...) -> ForwardReturnResult` — the
  same computation but returns a `@dataclass(frozen=True)` carrying
  the actual `start_date` / `end_date` / `start_close` / `end_close`
  the return was measured between, plus a `note: str` describing why
  the return is `None` (when applicable). Use this when the IC
  consumer needs to align ranking dates with realized-return start
  dates exactly.
- `compute_forward_returns_batch(tickers, as_of_date, horizon_months, *, cache_dir=None) -> dict[str, float | None]`
  — universe batch wrapper. Preserves insertion order; maps missing
  tickers to `None` (not filtered out) so the caller can distinguish
  "missing data" from "computed zero".
- `coverage_report(tickers, as_of_date, horizon_months, *, cache_dir=None) -> dict[str, int]`
  — aggregate counts (total / ok / no_cache / no_close / no_snap /
  censored / bad_price / nan_end / other) for surfacing how much of
  the survivorship-bias-corrected cohort actually has measurable
  realized returns at the horizon. The Hou-Xue-Zhang 2020 RFS
  cross-section typically reports 5-15% missing depending on cache
  freshness + delisting density.

**Source semantics + honest disclosure (per Research Report v1.0)**:

- Total return prefers `Adj Close` (dividend-adjusted) over bare
  `Close`. Falls back to `Close` when `Adj Close` is missing; mixed-
  source comparisons can leak ~1-3%/yr.
- NAIVE returns — no transaction costs, no slippage, no bid-ask, no
  borrow cost. The honest-baseline disclaimer per the autonomous
  mission constraint "ห้าม overclaim α" requires every downstream
  consumer to subtract a realistic frictions band before claiming
  α-after-costs.
- Survivorship-bias correction is NOT done here — it lives in PR #274
  `compute.ingest.historical_universe.members_at`. Callers MUST pair
  the two: load the historical universe at as-of, THEN look up forward
  returns per ticker in that universe. Loading current-universe
  tickers + forward returns silently excludes the `removed_since`
  cohort and inflates Sharpe estimates per Hou-Xue-Zhang 2020 RFS.
- Forward-snap window: 5 calendar days. As-of on a Saturday snaps to
  Monday's close; as-of on a holiday in the middle of a 4-day weekend
  fails (returns `None`) by design. Horizon-end snaps BACKWARD
  symmetrically.
- Horizon translation: `int(round(horizon_months × 30.44))` calendar
  days, then bisected against the actual `DatetimeIndex` (no
  assumption that the cache contains exactly `21 × horizon_months`
  trading rows).

**Tests (19 new + 1 live-cache smoke skipped without warm cache)**:

`tests/test_validation/test_forward_returns.py` ships 20 tests against
synthetic OHLCV parquets written to `tmp_path` and read back via
`cache_dir=tmp_path` (the gitignored production cache isn't checked
into git, so the test strategy mirrors PR #278's synthetic-fixture
pattern).

| Group | Cases |
|---|---|
| Happy path | flat-price → 0.0 · 1%/day geometric growth → 2.0 < r < 3.5 band · -1%/day drift → -0.80 < r < -0.65 band |
| Result dataclass | detailed result carries start_date / end_date / start_close / end_close |
| Missing-data paths | no cached parquet · missing Close column · `Adj Close` absent → falls back to `Close` · horizon past last row → censored · as-of pre-cache → no snap |
| Weekend snap | Sat as-of → snaps forward to Mon |
| Bad-price guards | start_close = 0 → None · NaN at horizon-end → None |
| Input validation | horizon=0 → ValueError · horizon<0 → ValueError |
| Batch API | dict-keyed batch + insertion-order preserved · empty input → empty dict |
| Coverage report | classifies each failure mode into the right bucket · empty universe → all zeros |
| Index recovery | string-index parquet round-trip → coerced back to DatetimeIndex |
| Live-cache smoke | runs against real `compute/cache/prices/AAPL.parquet` IF present; otherwise skipped silently |

**Schema impact**: zero. No new Pydantic / TypeScript / snapshot
field — this is pure read-only consumer of the gitignored
`compute/cache/prices/*.parquet` shape that
`compute/ingest/prices.py` already writes. Triple-lockstep N/A.

**Production-wiring impact**: zero. No `compute/main.py` import
hook; no `Metadata` field; no consumer of the new module lands in
this PR. The forward-return loader is exclusively a validation /
backtest tool. Production wiring happens in #2c (per-pillar IC
re-baseline) where this module becomes the realized-return source
paired with `ranking_history` (PR #278) as the ranking source.

**Honest-baseline disclaimer per the autonomous mission constraint**:
the returns this module produces are inputs to IC / DSR / PBO
re-baselining — they are NOT a backtest of QuantRank's composite
score. Any downstream report claiming an α figure must (a) net out a
realistic frictions band (≥ 30bp per leg per
`docs/research/honest-baseline-2026-05-27.md` once filed), (b) cite
the McLean-Pontiff 2016 32% post-publication decay, and (c) cap the
honest-α claim at 2-5% net before fees per the Research Report v1.0
ceiling.

**Verification**:
- `ruff check compute/validation/forward_returns.py tests/test_validation/test_forward_returns.py` — clean
- `python -m pytest tests/test_validation/test_forward_returns.py` — 19 passed, 1 skipped (live-cache smoke, no cache present)
- `python -m pytest tests/test_validation/` — 113 passed, 1 skipped (full validation suite; no regressions)
- `python -m compute.output.schema_check` — N/A (no schema touched)

**Deferred follow-ups (NOT in this PR)**:
- #2c per-pillar IC re-baseline — pairs this module with PR #278's
  `load_ranking_history`. Output: per-pillar IC at historical dates,
  honest band vs current published.
- #2d PBO/DSR re-baseline — uses #2c's output via PR #275's
  `factor_passes_gates(universe_provider=members_at, ...)` kwarg.
- #2f `docs/research/honest-baseline-2026-05-27.md` — the closing
  report carrying the revised numbers + disclaimer.
- Live-CI execution: this PR ships synthetic-fixture tests + a
  live-cache smoke that auto-skips when `compute/cache/prices/` is
  absent (CI / sandbox case). A future PR with warm-CI cache access
  will run the live-cache execution end-to-end.

No CLAUDE.md / AGENTS.md substance change required — the forward-
return loader doesn't introduce a new invariant, gotcha, or routing
cue. The harness doc (`docs/research/historical-revalidation-
harness.md`) is updated with #2b status `✅ this PR`.
PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with
every PR" lockstep per PR #237 convention.

---

## PR #281 — Phase 4.6 task #2c: per-pillar IC at historical dates (merged 2026-05-27, `858e8666`)

Seventh unit of the Phase 4.6 honest re-validation harness, closes
the IC re-baseline half of the chain. After PR #278 (ranking history,
#2a) + PR #279 (manipulation distribution, #2e) + PR #280 (forward
returns, #2b), this PR adds the orchestrator that PAIRS them — per-
pillar Information Coefficient at historical dates.

**The new module**: `compute/validation/historical_ic.py`

- `compute_pillar_ic(pillar_scores, forward_returns, *, method="spearman", min_tickers=30) -> tuple[float | None, int, str]`
  — pure cross-sectional IC for one (pillar, date) pair. Drops tickers
  with None / NaN / inf in either input. Returns `(None, n_used, note)`
  when cross-section < 30 (Grinold-Kahn 2000 §4.2) OR when std=0
  (constant inputs → correlation undefined).
- `compute_historical_ic_report(start_date, end_date, *, horizon_months=6, pillars=DEFAULT_PILLARS, method, min_tickers, path, repo, cache_dir) -> HistoricalICReport`
  — orchestrator that walks git-archived rankings.json snapshots in
  the window, loads each date's pillar scores, pulls forward returns
  via PR #280's `compute_forward_returns_batch`, computes Spearman IC
  per pillar per date, and aggregates into a per-pillar summary
  (mean / std / median / min / max / IC IR / hit rate).
- `format_ic_report(report)` — human-readable text rendering with
  table per pillar + honest-baseline disclaimer printed inline.
- `PillarICEntry` / `PillarICSummary` / `HistoricalICReport` —
  three `@dataclass(frozen=True)` carriers for one-date, per-pillar,
  full-window respectively.

**Spearman without scipy**: pandas' `Series.corr(method="spearman")`
pulls in scipy transitively — which QuantRank doesn't ship. Worked
around by computing Spearman as Pearson on rank-transformed series
(Spearman 1904 + Conover 1999 §5.4 — same definition). Zero new
dependencies.

**Honest-baseline disclaimer per Research Report v1.0**:

- IC reported here is **NAIVE** — no transaction costs, no slippage,
  no sector neutralization, no capacity discount. Real net-of-cost IC
  is typically 30-50% smaller per McLean-Pontiff (2016) JF post-
  publication decay.
- The historical universe MUST come from PR #274's `members_at()` to
  avoid survivorship bias — passing the current universe inflates IC
  by 0.5-2 pts per Hou-Xue-Zhang 2020 RFS. The orchestrator does NOT
  default to any universe; the caller supplies the universe via the
  rankings.json snapshot at as-of T, which is itself the historical
  universe at that date (correct by construction).
- IC is reported as a TIME SERIES + summary, not as a single headline
  number — a 1-quarter shock can mask a real decay trend. Decay > 32%
  vs the published-period baseline is the McLean-Pontiff (2016)
  expected post-publication mean.

**Tests (28 new)**:

`tests/test_validation/test_historical_ic.py` ships 28 tests covering
the orchestrator + the pure IC computation:

| Group | Cases |
|---|---|
| Module constants | DEFAULT_PILLARS = 10 keys mirroring PillarScores · MIN_TICKERS_PER_DATE = 30 |
| `compute_pillar_ic` | perfect positive rank → IC ≈ 1.0 · perfect negative → IC ≈ -1.0 · uncorrelated → finite in [-1, 1] · below min_tickers → None · None returns dropped · None scores dropped · constant scores → None · constant returns → None · NaN/inf scores dropped · invalid method raises · Pearson method works (different from Spearman on quadratic) |
| `_summarize_pillar` | empty entries → zero-shaped summary · multi-date aggregates mean/std/IC-IR · hit-rate counts strictly positive ICs · IC-IR = mean/std × sqrt(n) formula |
| `compute_historical_ic_report` | zero horizon raises · empty pillars raises · no commits → empty report · full path one-date one-pillar → IC = 1.0 · too few tickers → no IC entries · multi-date aggregates per pillar correctly · missing pillar field → skipped · malformed JSON snapshot → date skipped |
| `format_ic_report` | renders header + Honest-baseline disclaimer + McLean-Pontiff line · graceful "(no dates)" for empty pillar |
| Live-git smoke | runs against the real repo's recent rankings.json + (likely empty) price cache without crashing |

**Schema impact**: zero. Pure validation tool reading existing
rankings.json shape; no new Pydantic / TypeScript / snapshot field.
Triple-lockstep N/A.

**Production-wiring impact**: zero. No `compute/main.py` import; no
`Metadata` field. The orchestrator is purely a validation /
re-baseline tool. Downstream PRs (#2d PBO/DSR re-baseline + #2f
honest-baseline report) consume the output.

**Verification**:
- `ruff check compute/validation/historical_ic.py tests/test_validation/test_historical_ic.py` — clean
- `python -m pytest tests/test_validation/test_historical_ic.py` — **28 passed**
- `python -m pytest tests/test_validation/` — **141 passed, 1 skipped** (full validation suite; no regressions)
- `python -m compute.output.schema_check` — N/A (no schema touched)

**Deferred follow-ups (NOT in this PR)**:
- #2d PBO/DSR re-baseline — pairs this report's output with PR #275's
  `factor_passes_gates(universe_provider=members_at, ...)` kwarg.
- #2f `docs/research/honest-baseline-2026-05-27.md` — closes the
  chain with revised PBO / DSR / IC numbers + honest-α ceiling
  reaffirmation (2-5% net per Research Report v1.0).
- Live-CI execution: this PR ships synthetic-fixture tests + a
  live-git smoke that auto-degrades when the gitignored price cache
  is absent (the orchestrator returns `n_dates_with_ic = 0` instead
  of crashing). A future PR with warm-CI cache access will run the
  orchestrator end-to-end and publish the actual IC table.

No CLAUDE.md / AGENTS.md substance change required — the historical
IC orchestrator doesn't introduce a new invariant, gotcha, or
routing cue. The harness doc (`docs/research/historical-revalidation-
harness.md`) is updated with #2c status `✅ this PR`. PHASE_STATUS_INFLIGHT.md
side-file satisfies §Conventions "ship with every PR" lockstep per
PR #237 convention.

---

## PR #282 — Phase 4.6 task #2f: honest-baseline skeleton + CLI (closing the chain) (merged 2026-05-27, `c7cdd881`)

Eighth and **final structural unit** of the Phase 4.6 honest re-
validation harness. After PR #277 (universe drift) + #278 (ranking
history) + #279 (manipulation distribution) + #280 (forward returns)
+ #281 (historical IC orchestrator), this PR lands the closing
artifact: a methodology-final-form skeleton report + a CLI that
wires the Phase 4.6 modules end-to-end. **6 of 6 chain items now
structurally landed**; the only remaining work is a warm-CI
execution session that fills the TBD numeric cells.

**The new files**:

- **`docs/research/honest-baseline-2026-05-27.md`** (≈260 lines) —
  10-section skeleton report with TBD cells in §2 (per-pillar IC
  table), §3 (PBO/DSR re-baseline), §4 (manipulation distribution
  shift), §5 (survivorship-bias delta). All methodology + framing +
  honest-α ceiling + disclaimer ladder is final-form. Citation
  block carries 7 mandatory anchors: Hou-Xue-Zhang (2020) RFS,
  McLean-Pontiff (2016) JF, Bailey-Lopez de Prado (2014) JPM,
  Bailey-Borwein-Lopez de Prado-Zhu (2014) AMS Notices, Grinold-Kahn
  (2000), Spearman (1904) + Conover (1999), Kissell-Glantz (2003).
  Frictions ladder per Research Report v1.0: 30 bp/leg → 60 bp
  round-trip → 120 bp/yr annualized. **Honest α ceiling**: 2-5% net.
- **`scripts/generate_honest_baseline.py`** (≈230 lines) — argparse
  CLI that runs `compute_historical_ic_report` (PR #281) +
  `compute_manipulation_distribution_shift` (PR #279) and emits
  text (with disclaimer banner on stderr) or JSON (with `__banner__`
  embedded). Exit codes: `0` (report produced), `1` (input validation
  failed), `2` (empty report; useful CI signal that warm cache is
  needed). PBO / DSR section explicitly out of scope of this CLI —
  that call requires factor-return inputs separately and is
  delegated to `compute.validation.pbo_dsr.factor_passes_gates(
  universe_provider=members_at, ...)` (PR #275's gate kwarg).
- **`tests/test_validation/test_generate_honest_baseline_cli.py`**
  (17 tests) — covers argparse shape, `_parse_date` validation,
  exit codes, text-mode banner emission to stderr, JSON-mode payload
  shape + alpha ceiling cells + disclaimer string + banner
  embedding, `_report_to_payload` with synthetic + populated
  manipulation reports, and a constant pin on the banner's 5
  mandatory phrases.

**5 mandatory phrases pin-tested into the disclaimer banner**:
`"NAIVE"`, `"McLean-Pontiff"`, `"2-5%"`, `"Rule 16"`, `"S&P 500"`.

**Schema impact**: ZERO. Pure doc + CLI consumer of existing
validation modules. Triple-lockstep N/A.

**Production-wiring impact**: ZERO. No `compute/main.py` import;
no `Metadata` field.

**Smoke run on real repo's recent rankings.json (no live price cache)**:

```
$ python -m scripts.generate_honest_baseline \
    --start-date 2026-05-22 --end-date 2026-05-27 \
    --horizon-months 6 --min-tickers 2 --json --no-banner
{ "report_version": "0.1.0-skeleton", ...
  "pillar_ic": { "n_dates_walked": 3, "n_dates_with_ic": 0, ... } }
$ echo $?
2  # → empty-report exit code (warm cache needed)
```

CLI degrades gracefully: orchestrator walks 3 commits, finds no
warm price cache, returns `n_dates_with_ic = 0`, exit code 2
surfaces the missing-cache signal cleanly to CI without crashing.

**Verification**:

- `ruff check scripts/generate_honest_baseline.py tests/test_validation/test_generate_honest_baseline_cli.py` — clean
- `python -m pytest tests/test_validation/test_generate_honest_baseline_cli.py` — **17 passed**
- `python -m pytest tests/test_validation/ tests/test_smoke.py` — **160 passed, 1 skipped** (no regressions)
- `python -m compute.output.schema_check` — N/A (no schema touched)

**Phase 4.6 chain — now closed structurally**:

| # | Item | Status |
|---|---|---|
| 1/#2 | universe-drift first unit | ✅ PR #277 |
| #2a | ranking history loader | ✅ PR #278 |
| #2b | forward returns loader | ✅ PR #280 |
| #2c | per-pillar IC at historical dates | ✅ PR #281 |
| #2d | PBO/DSR re-baseline via gate kwarg | gate kwarg PR #275; warm-CI execution pending |
| #2e | manipulation distribution shift | ✅ PR #279 |
| #2f | honest-baseline skeleton + CLI | ✅ this PR |

**Deferred follow-ups (NOT in this PR)**:

- **Warm-CI execution session** — runs the CLI against a populated
  `compute/cache/prices/` to fill the TBD cells in
  `honest-baseline-2026-05-27.md` with actual figures.
- **Markdown writer mode** — future `--markdown` flag that re-writes
  the doc in-place with TBD cells replaced.
- **PBO/DSR factor-return wiring** — future `--include-pbo-dsr` flag
  that wires the factor-return path.

No CLAUDE.md / AGENTS.md substance change required — the honest-
baseline closing artifact is methodology + CLI only, no new
invariant / gotcha / routing cue. The harness doc (`docs/research/
historical-revalidation-harness.md`) is updated with #6 status
`✅ this PR` + closing note. PHASE_STATUS_INFLIGHT.md side-file
satisfies §Conventions "ship with every PR" lockstep per PR #237
convention.

---

## PR #285 — Codify mobile-only release-tag convention (merged 2026-05-27, `8f373758`)

Locks the **mobile-operator release workflow** that was discovered + battle-tested during the v1.3.0 + v1.4.0 cut on 2026-05-27. The user operates GitHub from a phone only (no desktop / no `gh` CLI / no terminal); the sandbox itself can't push tag-refs (HTTP 403 from the git proxy). The only path that actually works = pre-filled `/releases/new` URL the user taps once.

**3 files updated in lockstep**:

- **`.claude/skills/release-tag/SKILL.md`** — adds top-of-file "OPERATOR CONSTRAINT — mobile-only (locked 2026-05-27)" section; rewrites historical Step 5+6 ("Tag + push" + "Create GitHub release") into a single new "Mobile-operator release workflow" section covering the URL pattern, query-parameter table, 8 KB URL-size budget, short-body template (links to full release-notes file already on `main`), Python generator helper, what-the-user-does click-flow, multi-release ladder ordering rule (newest FIRST + retroactive LAST to avoid the auto-flag-latest footgun), and the post-publish verify-via-`get_latest_release` + edit-URL fallback. Old shell pattern preserved in §"Reference: shell pattern (NOT for this user)" for posterity.
- **`.claude/agents/release-captain.md`** — Step 5 rewritten to emit pre-filled URL via Python generator instead of shell commands; "What you do NOT do" gains 3 new bullets (no shell tag commands, no MCP-create-release attempt, no multi-release publish without Latest-flag verify); pre-existing rules preserved.
- **`CLAUDE.md`** §Gotchas — new "Release tags are mobile-only (locked 2026-05-27)" entry above the existing Parallel-PR collision pattern entry; captures the constraint + URL pattern + ladder ordering + cross-refs to the SKILL.md + agent file.
- **`AGENTS.md`** §"What you must NOT do" — mirror bullet added; cross-tool agents (Copilot / Cursor / Devin) see the same constraint.

**Lessons codified from the 2026-05-27 session**:

1. Sandbox `git push origin <tag>` → HTTP 403 (proxy blocks tag-refs but allows branch pushes)
2. `gh` CLI not available in the remote execution environment
3. GitHub MCP server (as of 2026-05-27) does NOT expose `create_release` — only `get_release_by_tag` / `get_latest_release` / `list_releases`
4. Full release-notes body (12 KB raw, ~18 KB URL-encoded) exceeds GitHub's 8 KB URL limit → short-body pattern needed
5. Publishing v1.3.0 retroactive AFTER v1.4.0 with default "Set as latest" checked → v1.3.0 became Latest (wrong!) → required edit-URL re-promotion
6. Mobile UI's "Choose target" dropdown only shows recent branch commits — older SHA (`5db3b978`) doesn't appear → MUST pass `target=<40-char-SHA>` in query string, not via mobile UI selection

**Scope: doc-only**. No compute / schema / scoring / valuation / frontend / Python / TypeScript code change. No test surface (the skill / agent doc updates aren't covered by pytest; they're prose). `ruff` / `schema_check` / `pytest` trivially pass.

**Deferred follow-ups** (NOT in this PR):
- A `tools/build_release_url.py` helper script that takes `(tag, target_sha, headline, prior_tag)` and emits the ready-to-tap URL — would let `release-captain` shell out instead of regenerating the URL-encoding logic inline each time. Low priority; the Python one-liner in SKILL.md is short enough.
- Update `THIRD_PARTY_NOTICES.md` if `gh` CLI is ever vendored — currently N/A since gh isn't installed.

PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with every PR" lockstep per PR #237 convention.

---

## PR #286 — Housekeeping PR-B: drain merged INFLIGHT entries + bump pointers post-v1.4.0 release (merged 2026-05-28, `27361047`)

Phase B (post-v1.4.0-tag housekeeping) PR. Cuts no code; pure doc-pointer + INFLIGHT.md maintenance — addresses the doc drift that accumulated across PRs #264-#285 (13 PRs landed since the last housekeeping in PR #267).

**Scope (5 files, doc-only)**:

- **`CLAUDE.md`** §Phase status — schema pointer `0.10.2-phase4.5e` → **`0.10.7-phase4.6`**; defense-layer narrative refresh; `Latest release tag` bumped `v1.3.0-phase4.5e` → **`v1.4.0-phase4.6`** (2026-05-27, `bbca9cac`); `Prior tag` updated; "Recently merged" list refreshed from 6 stale entries (PRs #147-#154) → 22 current entries (PRs #264-#285).
- **`PHASE_STATUS.md`** §Current state — schema + release tag pointers mirrored from CLAUDE.md; "Production run" pointer bumped to `559c5269` (cron-#5 2026-05-27 chore commit); "Recently merged" list prepended with 22 entries since v1.3.0 (PRs #264-#285), legacy list relabeled as "Earlier" sub-section.
- **`SKILL.md`** schema-version history table — 3 new rows prepended for the schema bumps that landed since the last housekeeping: `0.10.7-phase4.6` (PR #283 release / Phase 4.6 Metadata fields), `0.10.6-phase4.5e` (PR #269 GOOG/GOOGL per-class XBRL — includes the filer-namespace `goog:CapitalClassCMember` gotcha), `0.10.5-phase4.5e` (PR #264 multi-class CIK-collision annotate).
- **`WORKFLOW.md`** §Agentic 6-Phase Cadence Session-start protocol — stale schema/tag pointer block bumped `0.10.5-phase4.5e` / `v1.3.0-phase4.5e` → `0.10.7-phase4.6` / `v1.4.0-phase4.6`; defense layer narrative refreshed to reference Phase 4.6 honest re-validation harness closure.
- **`PHASE_STATUS_INFLIGHT.md`** — 7 stale `(in flight, YYYY-MM-DD)` header markers updated to `(merged YYYY-MM-DD, <SHA>)` with PR-number prefix (PRs #269, #267, #271, #280, #281, #282, #285). Bodies stay in place (full historical record preserved); future `tools/housekeep_phase_status.py` will eventually move them from "In flight (current)" → "Merged (awaiting housekeeping move to CLAUDE.md)" sub-section per the PR #237 convention.

**Verification**:
- `ruff check .` — N/A (no Python touched)
- `python -m compute.output.schema_check` — N/A (no schema touched)
- `pytest tests/ -m "not network"` — N/A (no test surface)
- Markdown-only diff; `docs-reviewer` (sonnet) spawned for substance review

**Deferred follow-ups**:
- `AGENTS.md` §Phase + version state already uses the `pointer-to-CLAUDE.md` delegation pattern — no bump needed; cross-tool agents reading state pull from CLAUDE.md per the existing convention.
- Future `tools/housekeep_phase_status.py` script (PR #237 deferred) — would automate the INFLIGHT-drain + CLAUDE.md pointer bump as one command. Manual for now until volume + shape are stable enough to lock the script API.
- `AGENTS.md` line 380-382 "Open Phase 4+ issues" — `#67 (Damodaran sector-adjusted CoE, Phase 5+)` is now mis-attributed since PR #204 (2026-05-22) landed the data-collection module; flip-PR `USE_SECTOR_COE = True` is a Phase 4 follow-up not Phase 5. Refresh in a separate substance PR after the cron data confirms the `value_trap_risk` delta-count.

CLAUDE.md substance touched (pointer block + Recently merged list refresh — both materially substantive). AGENTS.md substance untouched per the delegation-pattern explanation above; the lockstep is satisfied by PHASE_STATUS_INFLIGHT.md side-file per PR #237 convention.

---

## PR #290 — Cleanup post cron #69: BK orphan removal + 3 doc drifts (merged 2026-05-28, `dea8e3ad`)

Post-cron-#69 cleanup bundle. Cron run #69 (workflow_dispatch by user 2026-05-28 ~01:00 UTC, landed `233117ac chore: update rankings 2026-05-28` at `27361047` PR #286 merge SHA) surfaced 3 findings via `defense-layer-auditor` Section A-J + `stock-detail-auditor` deterministic prefilter + LLM verdict pass. 2 findings filed as issues (deferred to scoped follow-up sessions); 1 + 3 doc drifts batched into this PR.

**Scope (5 files, doc-only + 1 stale-file removal)**:

- **`frontend/public/data/stocks/BK.json`** (DELETED) — Bank of NY Mellon renamed to BNY on 2026-05-26 commit `b7514cf8`; `BK.json` was never purged from `frontend/public/data/stocks/` when `BNY.json` was created. Old file claims `rank: 230` which now belongs to GEHC; users navigating `/stock/BK` would see stale data conflicting with another stock's current position. `git rm` is the surgical fix; systematic writer-purge pattern (so this can't recur for future ticker renames) is tracked separately under issue #290 (filed next session).

- **`CLAUDE.md`** §Stack — `TypeScript 5.4 · Recharts 2.12` → `TypeScript 5.9 · Recharts 2.15` to match actual `frontend/package.json` pins (typescript 5.9.3, recharts 2.15.4, both bumped within their major bands during PR #215 LedgerCraft Phase 3c, 2026-05-22). Closes security-reviewer 2026-05-28 W2 finding.

- **`CLAUDE.md`** §Gotchas — new bullet documenting `GITHUB_RUN_ID` + `GITHUB_SHA` env-vars (auto-provided by GitHub Actions runner, read at `compute/main.py:1965-1966`, surface into `Metadata.compute_run_id` + `Metadata.git_commit` for audit trail). Closes security-reviewer 2026-05-28 W1 finding (the env-var inventory was incomplete).

- **`.claude/agents/dependency-auditor.md`** Frozen-by-design pins — `edgartools 2.30` → `edgartools 5.31 (5.x band, <6 upper bound per pyproject.toml)`. The 2.30 reference predates the project's migration to the 5.x band that happened during the Form-4 integration work (Filing.obj method-vs-property reclassification in PR #210). Closes dependency-auditor 2026-05-28 informational finding (the agent's own frozen-pin baseline was self-stale, would have caused future confusion).

**Findings deferred to scoped issues** (not in this PR):

- Issue **#288** (`bug(ingest): PR #269 GOOG/GOOGL per-class XBRL fix never fires`) — `_fetch_shares_from_per_filing_xbrl` filter mode returns `None` for both tickers because `xbrl.contexts` dimension axis lookup doesn't match Alphabet's actual XBRL structure. Display-only impact (market_cap 2.2× inflated to $4.66T/$4.71T vs correct ~$2.09T/~$2.59T); composite/rankings/Rule 16 unaffected; `multi_class_aggregate_shares_suspected` annotate fires correctly as safety net. Needs `edgar-debugger` live XBRL probe of Alphabet 10-K before proposing the 1-line fix.

- Issue **#289** (`bug(valuation): NVR DQIC ceiling false positive`) — `FAIR_PRICE_DATA_QUALITY_CEILING = $10,000` at `compute/config.py:128` too low for NVR ($458 EPS × ~22× sector PE = ~$10,094, trips ceiling); ALL 6 valuation methods blocked → `/stock/NVR` renders empty fair-price section. Needs `methodology-scientist` Mode B verdict on Option A (raise ceiling) / Option B (ratio-based) / Option C (input vs output split).

**Verification**:
- `ruff check .` — N/A (no Python touched)
- `python -m compute.output.schema_check` — N/A (no schema touched)
- `pytest tests/ -m "not network"` — N/A (no test surface)
- BK orphan removal verified clean via `verify-production-output/helper.py` Section H (502 ranking entries == 502 stock files post-removal)
- `defense-layer-auditor` Section H FAIL (orphan) clears after this PR merges
- Markdown-only diff on the 3 doc-drift items

**Hard constraints honored**:
- No scoring / composite / Rule 16 / Top-5 rotation invariant touched
- No schema change (snapshot triple unchanged)
- AGENTS.md substance untouched per the delegation-pattern (line 372-375) — lockstep satisfied by PHASE_STATUS_INFLIGHT.md side-file per PR #237 convention.

PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with every PR" lockstep per PR #237 convention. CLAUDE.md substance touched (Stack version refresh + Gotchas inventory completion — both materially substantive).

---

## PR #291 — AGENTS.md substance refresh: production-verified run pointer + open-issues list (merged 2026-05-28, `cb9114bb`)

Second cleanup PR same day. PR #286 (housekeeping) opted to defer the AGENTS.md substance update under the `pointer-to-CLAUDE.md` delegation pattern; PR #290 (post-cron cleanup) noted the deferred AGENTS.md items but kept scope tight. This PR closes both deferred items.

**Scope (1 file, doc-only)**:

- **`AGENTS.md`** line 377 — Production-verified run pointer bumped from cron #51 (`b1588b2a`, 5m14s, ~2026-05-14) → cron #69 (`233117ac`, 13m 16s, 2026-05-28). Adds verification details (defense-layer-auditor + stock-detail-auditor on schema `0.10.7-phase4.6`, 7 active vetoes confirmed, Rule 16 Top-5 invariant holds with PPG carrying badge). Cross-tool agents (Copilot / Cursor / Devin) validating local output against a known-good baseline now have the current reference point. Closes `security-reviewer` 2026-05-28 informational finding.

- **`AGENTS.md`** lines 380-382 — "Open Phase 4+ issues" list refreshed from 4 entries → 11 entries:
  - REMOVED stale qualifier: `#67 (Damodaran sector-adjusted CoE, Phase 5+)` was mis-attributed; PR #204 (2026-05-22) landed the data-collection module so `#67` is Phase 4 follow-up, NOT Phase 5+. Now reads `#67 (sector-CoE flip-PR; data-collection landed PR #204, flip gated on cron data after #287 lands)`.
  - ADDED context to #41: "15 advisories open, all zero-exploitability on static-export deployment" so cross-tool agents understand the migration is release-tag cleanliness not security-critical.
  - ADDED 7 missing open issues: #115 (JKP license) · #130 (Q3 cohort 2026-08-19) · #137 (9arm-skills license deadline 2026-06-17) · #150 (Phase 2-3 epic) · #287 (FORM4 revert + durable timeout, NEW today) · #288 (GOOG/GOOGL XBRL broken, NEW today) · #289 (NVR DQIC false positive, NEW today).

**Why this PR exists**:

Cross-tool agents (Copilot / Cursor / Devin) reading AGENTS.md before doing work on the repo would have:
- Validated against a 14-day-stale baseline (`b1588b2a` from ~2026-05-14)
- Skipped `#67` thinking it was Phase 5+ work (when it's actually Phase 4 follow-up gated only on cron data)
- Missed the 7 newly-filed issues entirely

This is operationally a small-scope PR but high-leverage: AGENTS.md is the cross-tool agent SoT for "Open Phase 4+ issues", and stale pointers there cause repeated re-derivation across sessions.

**Out of scope (deferred to scoped follow-ups)**:

- CLAUDE.md §Phase status touched per the standing delegation pattern (CLAUDE.md is SoT for "Current state" + "Recently merged" + "Next deliverables"). The CLAUDE.md side already bumped in PR #286 and #290; this PR adds the AGENTS.md mirror only.
- `tools/build_release_url.py` helper (PR #285 deferred follow-up) — different scope; queued for separate PR.
- `tools/housekeep_phase_status.py` (PR #237 deferred) — different scope; queued for separate PR.
- Issue #288 / #289 substantive fixes — agent verdicts (edgar-debugger + methodology-scientist) in flight as of this PR; fix-PRs follow once verdicts land.

**Verification**:
- `ruff check .` — N/A (no Python touched)
- `python -m compute.output.schema_check` — N/A (no schema touched)
- `pytest tests/ -m "not network"` — N/A (no test surface)
- Markdown-only diff on a single file

**Hard constraints honored**:
- No scoring / composite / Rule 16 / Top-5 rotation invariant touched
- No schema change
- CLAUDE.md substance untouched THIS PR (PR #286 + PR #290 already bumped it); the lockstep flips this time — AGENTS.md substance touched while CLAUDE.md stays. PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions per PR #237 convention.

PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with every PR" lockstep per PR #237 convention. AGENTS.md substance touched (production-verified run bump + open-issues list refresh — both materially substantive). CLAUDE.md substance untouched per the delegation-pattern (PR #286 + PR #290 already updated the CLAUDE.md side; this PR closes the AGENTS.md side of the lockstep).

---

## PR #292 — Issue #288 fix: GOOG/GOOGL XBRL concept-name omission (merged 2026-05-28, `e9aaab31`)

Closes Issue #288 — `multi_class_per_class_override_count = 0` on every production cron since PR #269 landed (2026-05-26). Both GOOG and GOOGL render inflated `market_cap` (~$4.66T / $4.71T) instead of correct per-class values (~$2.09T / $2.59T).

**Root cause** (from `edgar-debugger` verdict 2026-05-28): `compute/ingest/fundamentals.py:735` `_fetch_shares_from_per_filing_xbrl` queried only 2 XBRL concepts (`dei:EntityCommonStockSharesOutstanding` + `us-gaap:CommonStockSharesIssued`). Alphabet's 10-K files per-class share counts under **`us-gaap:CommonStockSharesOutstanding`** — missing 3rd concept. Primary path at lines 115-124 already queries all 3 in this order; XBRL fallback drifted out of parity. Existing tests at `test_fundamentals.py:822-857` mock `_fetch_shares_from_per_filing_xbrl` entirely with `return_value=per_class` — never exercised the actual concept-lookup path; bug survived the suite.

**Fix scope (9 files)**:

- **`compute/ingest/fundamentals.py:735-749`** — Add `us-gaap:CommonStockSharesOutstanding` to the concept tuple (between the 2 existing entries, matching primary path order); fix misleading docstring at lines 686-687.
- **`compute/ingest/fundamentals.py:48-71`** — Add `"per_class_attempt": 0` to `_FALLBACK_STATS` dict + reset in `reset_fallback_stats()`.
- **`compute/ingest/fundamentals.py:~1030`** — Increment `per_class_attempt` AT TOP of Branch 3 elif (before the XBRL call), so the counter captures "branch entered" regardless of whether XBRL lookup succeeded.
- **`compute/config.py:30`** — Schema PATCH bump `0.10.7-phase4.6 → 0.10.8-phase4.6`.
- **`compute/output/schemas.py:~340`** — New `Metadata.multi_class_per_class_attempt_count: int | None = None` field (Rule 18 disambiguator).
- **`compute/main.py:~2023`** — Wire `multi_class_per_class_attempt_count=shares_fallback_stats.get("per_class_attempt")` to Metadata construction.
- **`frontend/lib/types.ts:~233`** — Mirror TS field `multi_class_per_class_attempt_count?: number | null;`.
- **`frontend/lib/schema-snapshot.json`** — Regenerated via `--update-snapshot` (in sync at `0.10.8-phase4.6`).
- **`tests/test_config.py`** — Schema version pin `0.10.7 → 0.10.8`; docstring updated to reference Issue #288.
- **`tests/test_ingest/test_fundamentals.py`** — New regression tests authored by `test-engineer` (sonnet) with synthetic XBRL fixture; exercise concept-lookup path directly (do NOT mock `_fetch_shares_from_per_filing_xbrl`); includes concept-tuple pin against re-omission.

**Rule 18 diagnostic disambiguation** (the new counter):

- `attempt == override == 0` → Branch 3 never triggered (allowlist empty OR `QR_SKIP_FUNDAMENTALS` set)
- `attempt > 0`, `override = 0` → XBRL lookup returned None (regression class of #288)
- `attempt == override > 0` → normal operation; post-fix steady-state = both equal 2 (GOOG + GOOGL)

**Impact (display-only)**:
- ✅ Composite scores / rankings / Rule 16 / Top-5 rotation **UNAFFECTED** (`market_cap` not an 8-pillar input)
- ✅ Annotate safety net **continues to work** — `multi_class_aggregate_shares_suspected` fires (PR #264)
- ✅ `/stock/GOOG` + `/stock/GOOGL` UI renders correct per-class market_cap on next cron
- ✅ `pe_ratio_ttm` re-derives from corrected shares

**Verification**:
- `ruff check .` — PASS
- `python -m compute.output.schema_check` — PASS (triple in sync at `0.10.8-phase4.6`)
- `schema-sentinel` Mode A verdict — TRIPLE-IN-SYNC
- `python -m pytest tests/test_config.py tests/test_output/ -q -m "not network"` — **70 passed**
- `test-engineer` regression test PASS (synthetic XBRL fixture; would have FAILED pre-fix)

**Deferred follow-ups**:
- `@network` GOOG/GOOGL drift-detector test (live SEC, requires `EDGAR_USER_AGENT`) — separate follow-up PR
- Issue #289 NVR DQIC fix (Option C delete Site-2 ceiling per methodology-scientist) — separate fix-PR; different code site + different test surface

PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with every PR" lockstep per PR #237 convention. CLAUDE.md + AGENTS.md substance untouched this PR — the schema bump is itself substantive (the schema triple lockstep moved + the SKILL.md schema-version table will get the new row in a follow-up housekeeping PR, not THIS bug-fix PR which scopes tight).

---

## PR #293 — Issue #289 fix: retire Site-2 DQIC ceiling per Option C (merged 2026-05-28, `95e638bf`)

Closes Issue #289 — NVR `/stock/NVR` rendered empty fair-price section despite legitimate inputs ($458 EPS / $6,098 price / ~2.7M shares / `risk_flags: []`). Site-2 output-level ceiling (`FAIR_PRICE_DATA_QUALITY_CEILING = $10,000` in `compute/config.py`) tripped on `multiples_pe ≈ 22× × $458.86 ≈ $10,094` and nulled all 6 valuation methods.

**Per methodology-scientist Mode B verdict 2026-05-28** = **Option C** (delete redundant Site-2 ceiling; LITERATURE-ANCHORED on Penman 2013 §7.4 + Damodaran 2019 Ch. 18 + Huber 1981 §1.4):

- Site-2 was a defense-in-depth layer that turned out structurally redundant with Defense #4 (`extreme_*_estimate` per-method outlier guard) + Issue #177 `extreme_estimate_majority` (Huber breakdown-point check)
- Site-1 input-level check (`compute/scoring/risk_overlay.py::_data_quality_input_corruption` — TBVPS > $10K / TTM revenue < $50M / |NI| > |revenue|) already catches the upstream units-bug class AT THE SOURCE
- Cohort impact: Option A ($50K) = 0 newly flagged · Option B (5× ratio) = **12 newly nulled tickers** (CHTR/ROP/EPAM/LEN/SWKS/GM/BBY/CTSH/CMCSA/HPE/T/AES — clear regression) · Option C = 0 newly missed (Site-1 already covers the units-bug class)
- PPV on 2026-05-28 cron #69 for Site-2: 0/1 = 0% (the only firing was NVR's false positive)

**Fix scope (5 files)**:

- **`compute/valuation/ensemble.py:450`** — Site-2 trigger DELETED. The `if _has_corrupt_input(methods): return (_data_quality_corrupt_result(methods), [])` 2-line check that lived just before `_aggregate_methods` is replaced with a long-form comment block citing Issue #289 + methodology verdict + NVR empirical case. **`_has_corrupt_input` + `_data_quality_corrupt_result` functions retained as DEAD CODE for one cycle** (easier review per methodology verdict; follow-up PR removes them after ≥ 1 cron of clean operation confirms no regression).

- **`compute/config.py:121-138`** — `FAIR_PRICE_DATA_QUALITY_CEILING = 10000.0` **CONSTANT KEPT ACTIVE** (initially commented out by the main agent and immediately restored — see below). Site-1 input-level check at `compute/scoring/risk_overlay.py:149` USES the same constant for the TBVPS > $10K ceiling; commenting it out would break the input-corruption veto. Docstring rewritten to: (a) confirm Site-1 active use; (b) document Site-2 retirement per Issue #289 + methodology verdict; (c) note the post-fix expected behavior on the empirical NVR case.

- **`compute/main.py:1495-1499`** — Writer-parity emit UNCHANGED. When `data_quality_input_corruption` veto fires in `risk_flags` (Site-1 path), `valuation_output_anomalous` is still appended to `valuation_warnings` so the UI explanation chip in `FairPriceCard.tsx` continues to render for the Site-1 veto cohort (MTB / CPT / MRNA / HBAN per PR #265). The annotate's UI surface persists; only the Site-2 ensemble-path trigger is retired.

- **`docs/METHODOLOGY.md:412-428`** — `valuation_output_anomalous` annotate description re-anchored: now reflects "Site-2 retired per Issue #289; emit remains via writer-parity from compute/main.py on Site-1 cohort." Cites Penman 2013 §7.4 + Damodaran 2019 Ch. 18 + Huber 1981 §1.4 anchors + the empirical 0/1 PPV justification.

- **`tests/test_valuation/test_ensemble.py:1005-1078`** — `test_data_quality_guard_end_to_end_via_full_ensemble` REWRITTEN as `test_site2_data_quality_guard_retired_post_issue_289` retirement-guard. Same corrupted-snapshot fixture (`shares_outstanding=10` → equity $5B / 10 shares = $500M/share TBVPS); post-fix assertions confirm: (1) `valuation_output_anomalous` ABSENT from ensemble's `valuation_warnings`; (2) Defense #4 `extreme_*_estimate` annotates fire correctly; (3) no method carries reason `valuation_output_anomalous` from the ensemble path. 3 other Site-2 tests (`test_data_quality_sanity_guard_triggers_on_extreme_method_value` / `_boundary_exactly_at_ceiling` / `_skipped_methods_dont_trigger`) call the standalone helpers and continue to pass (they exercise the dead-code functions which are retained for 1 cycle).

- **`tests/test_valuation/test_ensemble.py`** — New NVR regression tests authored by `test-engineer` (sonnet) — synthetic NVR-shaped `raw_metrics` ($458 EPS / $6,098 price / ~2.7M shares); assert `result.median is not None`, `valuation_output_anomalous` not in ensemble warnings, ≥ 1 method applicable.

**Construction error caught + corrected mid-PR**:

Initial main-agent edit commented out `FAIR_PRICE_DATA_QUALITY_CEILING` per the verdict's "Retire from config.py" line. This BROKE Site-1 at `risk_overlay.py:149` which uses the same constant for the input-level TBVPS ceiling. Fix immediately reverted: constant kept active with rewritten docstring distinguishing Site-1 (preserved, active) from Site-2 (retired, dead code). 4 test_ensemble.py failures during the constant-commented-out window resolved automatically after restore (3 were dead-code function tests that lost their config reference; 1 was the end-to-end test that's now rewritten as a retirement guard).

**Impact (display-only — NVR specifically)**:

- ✅ `/stock/NVR` now renders fair-price section with the median of surviving methods (post-fix sanity check via offline test)
- ✅ NVR ranking + composite UNCHANGED (composite = 50.99 didn't depend on Site-2; rank stays #252 per cron #69 data)
- ✅ Rule 16 + Top-5 rotation UNAFFECTED (no scoring code touched)
- ✅ Site-1 input-corruption veto unchanged — 4 cohort tickers (MTB / CPT / MRNA / HBAN) keep their VETO + UI explanation chip
- ⏳ Defense layer count unchanged at 33 declared (Site-2 was an emission path, not a flag; the `valuation_output_anomalous` annotate identifier persists via writer-parity)

**Verification**:

- `ruff check .` — PASS
- `python -m compute.output.schema_check` — PASS (no schema change in this PR)
- `python -m pytest tests/test_valuation/test_ensemble.py -q -m "not network"` — **51 passed**
- `python -m pytest tests/ -q -m "not network" --ignore=tests/test_validation` — **1203 passed**, 7 skipped (optional deps), 0 failed
- methodology-scientist Mode B verdict — Option C LITERATURE-ANCHORED
- NVR regression test (synthetic `raw_metrics`) authored by `test-engineer` — pending agent completion

**Deferred follow-ups** (NOT in this PR):

- Dead-code removal PR — delete `_has_corrupt_input` + `_data_quality_corrupt_result` + the 3 standalone helper tests (`test_data_quality_sanity_guard_triggers_on_extreme_method_value` / `_boundary_exactly_at_ceiling` / `_skipped_methods_dont_trigger`) after ≥ 1 cron of clean operation confirms no regression
- `THIRD_PARTY_NOTICES.md` JKP entry (Issue #115 closure prep) — separate scope
- Site-1 input-level threshold recalibration — Q3 2026-08-19 cohort audit will revisit the $10K TBVPS ceiling + $50M revenue / |NI|>|revenue| patterns. NVR's $1,294 TBVPS is comfortably below ceiling (no Site-1 regression from this PR)

PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with every PR" lockstep per PR #237 convention. CLAUDE.md + AGENTS.md substance untouched this PR — the methodology + code change IS substantive (Site-2 emission path retired) but the CLAUDE.md §Phase status entry will fold into a Q3 2026-08-19 cohort-audit comment per issue #130 (already noted in the 2026-05-28 dependency-auditor comment on that issue).

---

## PR #294 — Issue #67 sector-CoE flip: `USE_SECTOR_COE = True` (merged 2026-05-28, `0ddb6b81`)

Closes Issue #67 — flips `USE_SECTOR_COE` from `False` → `True` per methodology-scientist Mode B verdict 2026-05-28 + cron #69 empirical confirmation. Consumes the data-collection module landed in PR #204 (2026-05-22, Damodaran 2019 Ch. 8.4 + NYU January 2025 betas — LITERATURE-ANCHORED across all 11 GICS sectors).

**Empirical gate satisfied** (cron #69 metadata, 2026-05-28):
- `value_trap_risk_count_without_sector_coe: 132` (current baseline; flat `COST_OF_EQUITY = 0.10`)
- `value_trap_risk_count_with_sector_coe: 109` (post-flip projection; per-GICS Ke 6%-12%)
- **Delta: −23 tickers, −17.4% reduction**
- Absolute landing point (109) inside the original PR #204 target band `[80, 110]` ✅
- 38%-vs-17% spread vs original projection explained by baseline drift (PR #166 Issue #11 RIM equity-denominator fix already removed ~44 false positives from the pre-PR-#204 ~176 baseline; the proportional difference is baseline drift, not signal failure)

**Methodology-scientist verdict**:

> VERDICT = APPROVED. Cron #69's 132 → 109 reduction clears the gate per Damodaran 2019 Ch. 8.4 §"Industry Beta" framework. Lower-Ke sectors (Utilities/REIT/Staples) gain leniency; higher-Ke sectors (Tech/Energy) gain stringency; net is negative because S&P 500 has more market-cap exposure to defensives than the flat 10% baseline assumed. Per-sector delta verification recommended but NOT a blocker — Q3 2026-08-19 cohort audit (~12 weekly crons of post-flip data) is the natural shape-verification gate. The flat-CoE counter remains as monitoring baseline; flipping back requires a separate methodology-scientist verdict (load-bearing default).

**Fix scope (5 files)**:

- **`compute/config.py:86`** — `USE_SECTOR_COE: bool = False → True`. Docstring rewritten to: (a) cite the methodology verdict + cron #69 numbers; (b) explain the baseline-drift rationale for the smaller-than-projected delta; (c) mark the flag as a load-bearing default (flipping back requires separate verdict).

- **`compute/scoring/cost_of_equity.py:73-79`** — Module docstring updated to reflect post-flip state ("flipped True 2026-05-28; flat-CoE remains as monitoring baseline").

- **`tests/test_scoring/test_value_trap_risk_sector_coe.py:134-156`** — Test renamed `test_flat_coe_path_unchanged_by_sector_module_import` → `test_use_sector_coe_default_post_issue_67_flip`; assertion inverted from `not config.USE_SECTOR_COE` → `config.USE_SECTOR_COE` (would BREAK on flip otherwise). Docstring updated to document the regression-guard semantics post-flip.

- **`tests/test_config.py`** — New `test_use_sector_coe_flipped_true` pin added (per methodology-scientist Q5b: every config-value flip should pin the new value in `tests/test_config.py` per Phase 2.4/2.5 convention).

**Verification**:

- `ruff check .` — PASS
- `python -m compute.output.schema_check` — PASS (no schema change in this PR; the dual-counter Metadata fields already shipped in PR #204)
- `python -m pytest tests/test_config.py tests/test_scoring/test_value_trap_risk_sector_coe.py tests/test_scoring/test_cost_of_equity.py tests/test_valuation/ -q -m "not network"` — **256 passed**
- `python -m pytest tests/ -q -m "not network" --ignore=tests/test_validation` — **1207 passed**, 7 skipped (optional deps), 0 failed
- methodology-scientist Mode B verdict — APPROVED (LITERATURE-ANCHORED across all 11 GICS sectors)

**Impact (production behavior change — first methodology-affecting flip post-v1.4.0)**:

- ✅ `value_trap_risk` annotate count: 132 → 109 universe-wide (per cron #69 dual-counter)
- ✅ Affected pillar: `value` (via RIM applicability gate); the 23 newly-not-flagged tickers regain RIM as a contributing valuation method
- ✅ Composite ranks DO shift for the cyclical-vs-defensive cohort — but the magnitude is bounded by the per-pillar weight and the median-of-6 aggregation; expected ranking-table impact: small (verified by pre-merge-prod-sim on this PR)
- ✅ Rule 16 + Top-5 rotation MECHANICS unchanged (no scoring-formula change; only Ke parameter shift on RIM)
- ✅ No schema change (Metadata dual-counter fields already shipped PR #204)
- ✅ No new defense flag (defense layer count unchanged at 33 declared)

**Deferred follow-ups** (NOT in this PR):

- **Per-sector delta instrumentation** (methodology-scientist Q2 recommendation) — adds `Metadata.value_trap_risk_delta_by_sector: dict[str, int] | None` to confirm the shape matches Damodaran 2019 Ch. 8.4 §"Industry Beta" expectations (lower-Ke sectors gain flags, higher-Ke sectors lose flags). Separate PR; the universe-wide count is sufficient for THIS flip per the gate contract.
- **Q3 2026-08-19 cohort audit** — natural review point for per-sector shape verification (~12 weekly crons of post-flip data by then). Already in the issue #130 pre-prep checklist (posted 2026-05-28 by dependency-auditor sweep).

PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with every PR" lockstep per PR #237 convention. CLAUDE.md + AGENTS.md substance untouched this PR — the methodology flip IS substantive but Q3 cohort audit (issue #130) is the canonical narrative venue, where the pre-prep checklist comment already documents the gating decision.

---

## PR #295 (merged 2026-05-28, `2d2ec83e`) — Post-session housekeeping 2026-05-28: drain 6 INFLIGHT markers + bump pointers

End-of-day Track-A2 housekeeping. After 6 PRs landed on main today (#286 / #290 / #291 / #292 / #293 / #294), the CLAUDE.md / PHASE_STATUS.md / SKILL.md pointers drifted again — schema bumped via PR #292 (`0.10.7 → 0.10.8-phase4.6`); `USE_SECTOR_COE` flipped via PR #294. This PR closes the doc-drift loop so session N+1 reads correct state.

**Scope (4 files, doc-only)**:

- **`CLAUDE.md`** §Phase status pointer block — schema `0.10.7-phase4.6 → 0.10.8-phase4.6`; defense layer narrative refreshed to note `USE_SECTOR_COE = True` post-#294; "Post-tag production patches" subsection added between Latest tag + Prior tag, citing PRs #292 / #293 / #294 + their SHAs + the substantive change each closes. "Recently merged" list prepended with 6 same-day entries; legacy "Earlier (PR #264 → PR #285)" subsection relabeled.

- **`PHASE_STATUS.md`** §Current state — schema pointer mirrored (`0.10.7 → 0.10.8-phase4.6`); new "Post-tag production patches" row added (parallel structure to CLAUDE.md); Production-run pointer updated `559c5269 → 0ad1d574` (cron #69 chore-commit on 2026-05-28). "Recently merged" list prepended; legacy list relabeled "Earlier".

- **`SKILL.md`** schema-version history table — new top row added for `0.10.8-phase4.6` (PR #292, GOOG/GOOGL XBRL fix + Rule 18 `multi_class_per_class_attempt_count` disambiguator); existing `0.10.7-phase4.6` row preserved as second entry.

- **`PHASE_STATUS_INFLIGHT.md`** — 6 stale `(in flight, 2026-05-28)` markers updated to `(merged 2026-05-28, <SHA>)` (PRs #286 / #290 / #291 / #292 / #293 / #294). Bodies preserved (historical record).

**Why this PR exists**:

Without this housekeeping, the next session reading CLAUDE.md §Phase status would see schema `0.10.7` despite code shipping `0.10.8`, and "Recently merged" would list PRs #264-#285 as the latest (missing 6 PRs from today). The pattern surfaced 2026-05-28 morning (Track A PR #286 closed analogous drift across PRs #264-#285); applying the same housekeeping at end-of-day for PRs #286-#294 prevents the same friction tomorrow.

**Verification**:
- `ruff check .` — PASS (no Python touched)
- `python -m compute.output.schema_check` — PASS (no schema touched)
- `pytest tests/ -m "not network"` — N/A (no test surface)
- Markdown-only diff

**Hard constraints honored**:
- No code / scoring / schema / Rule 16 / Top-5 invariant touched
- No new defense flag · No new dep
- AGENTS.md substance untouched per the existing delegation pattern (CLAUDE.md = SoT for §Phase status / Stack); PR #291 already bumped AGENTS.md production-verified run pointer this morning

PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with every PR" lockstep per PR #237 convention. CLAUDE.md substance touched (pointer block + Recently merged list refresh — both materially substantive).

---

## PR #296 (merged 2026-05-28, `e85dfbcf`) — Add root `CONTEXT.md` pointer + reconcile `docs/agents/domain.md`

End-of-day Track-A3 follow-up to the post-session housekeeping commit (`0949a3c1`). Adds a single-file `CONTEXT.md` entry point at the repo root so external tools / fresh agents / vendored skills that expect the upstream mattpocock convention have one bridge file to read first. Reconciles `docs/agents/domain.md` which previously declared "QuantRank has NO `CONTEXT.md`" (now stale).

**Scope (3 files, doc-only — additive)**:

- **`CONTEXT.md`** (NEW, ~245 lines) — bridge / live-snapshot pointer. 11 sections: Design note (explicit "not source of truth" framing) · What is QuantRank · Live snapshot (schema `0.10.8-phase4.6` · `v1.4.0-phase4.6` tag · 33 declared flags · `USE_SECTOR_COE=True` post-#294 · cron #69 green) · Multi-file mapping (12-row file→topic + 6-row topic→file tables mirroring `docs/agents/domain.md`) · 8 Key invariants (Rule 16 / schema triple / Rule 18 / lockstep / rebase / mobile-only / formula sacred / orchestrator role) · Stack · Layout · Quick-start commands (verification ladder + local compute + network tests) · 9 Standing constraints (license + scope) · 7 Vocabulary discipline terms · Roadmap pointer (Stage 0 → Stage 6 / v2.0) · Companion files index.

- **`docs/agents/domain.md`** §"QuantRank has NO `CONTEXT.md`" — section header + opening paragraph rewritten to "`CONTEXT.md` is a pointer, not the source of truth" with the new framing (the four-file analog remains canonical; CONTEXT.md is a bridge). The topic-driven lookup table + "update `CONTEXT.md` inline when a term resolves" + "Use the project vocabulary" sections remain unchanged (their semantics still apply — updates land in the appropriate deep file, not in CONTEXT.md which is pointer-only).

- **`PHASE_STATUS_INFLIGHT.md`** — this entry.

**Why this PR exists**:

`docs/agents/domain.md` referenced the upstream-vs-QuantRank divergence by stating QuantRank has NO `CONTEXT.md`. That statement was reasonable before this PR but creates friction for any tool / agent / vendored skill that genuinely expects to read `CONTEXT.md` first — they'd 404 and either error out or fall back to a generic search. Adding a pointer-only `CONTEXT.md` satisfies the upstream contract without compromising the multi-file design: the four canonical files (CLAUDE.md + SKILL.md + WORKFLOW.md + docs/METHODOLOGY.md) remain source of truth, and `CONTEXT.md` is explicit about its role as "bridge + snapshot" in its first paragraph.

**Design discipline**:

- `CONTEXT.md` MUST NOT duplicate content from the four canonical files — when content drifts, the four files win and `CONTEXT.md` updates to point at the new location.
- "Live snapshot" block in `CONTEXT.md` IS expected to drift; the next end-of-session housekeeping commit refreshes the snapshot (schema version / latest tag / cron status) the same way it refreshes CLAUDE.md §Phase status.
- "Roadmap pointer" block in `CONTEXT.md` is a 6-line summary; for full detail readers route to PHASE_STATUS.md §"Next deliverables" + WORKFLOW.md per-phase task lists (linked from the block).

**Verification**:

- `ruff check .` — N/A (no Python touched)
- `python -m compute.output.schema_check` — N/A (no schema touched)
- `pytest tests/ -m "not network"` — N/A (no test surface)
- Markdown-only diff; broken-link check on the 12+ internal links in `CONTEXT.md` — all targets exist on `main` (CLAUDE.md, AGENTS.md, SKILL.md, WORKFLOW.md, PHASE_STATUS.md, PHASE_STATUS_INFLIGHT.md, docs/METHODOLOGY.md, docs/design.md, docs/agents/domain.md, docs/agents/issue-tracker.md, THIRD_PARTY_NOTICES.md, README.md, .claude/agents/README.md, .claude/skills/README.md, .claude/skills/release-tag/SKILL.md).

**Hard constraints honored**:

- No code / scoring / schema / Rule 16 / Top-5 invariant touched
- No new defense flag · No new dep · No new env-var
- Doc-only, pointer-only (no duplicated content from canonical files)
- Four-file analog remains canonical per `docs/agents/domain.md` reconciliation
- AGENTS.md substance untouched (CLAUDE.md = SoT for §Phase status / Stack; this PR adds a pointer file, not a rule change)

PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with every PR" lockstep per PR #237 convention. CLAUDE.md substance untouched this PR — `CONTEXT.md` is a NEW top-level file that pointers TO CLAUDE.md, not a substance change WITHIN CLAUDE.md.

---

## PR #297 (merged 2026-05-28, `ecb60e64`) — Issue #287 PR A: durable timeout + cache canary + per-loop wall-clock Metadata

Three-part durable fix for the 2026-05-25 cron cancellation at 150m
(incident-commander session 8 verdict — PR #205 added Form-4 as the
5th SEC EDGAR loop without bumping the `timeout-minutes` ceiling).
**Does NOT revert `FORM4_FETCH_SKIP=1`** — that is PR B (Issue #287
Part 4), gated on ≥ 1 cron completing under the new 195m ceiling
with all 4 wall-clock fields populated.

**Part 1 — `timeout-minutes: 150 → 195`** in
`.github/workflows/compute-rankings.yml`. Per-loop cold-cache budget
math documented inline (5 EDGAR loops: prices ~5m + fundamentals ~25m
+ history ~15m + Form-4 ~10m + Tier-2 ~35m + OSAP ~5m + write ~3m =
~98m warm-realistic, +20% SEC-throttle = ~118m, +headroom + Commit
= 195m target). Old Phase 4g 90→150m rationale comment replaced
with the 5-loop budget table.

**Part 2 — Cache-restore canary step** inserted between `Restore
compute caches` and `Run weekly compute`. Bash one-liner (`du -sm`
+ `find -printf '%T@'`) emits size (MB) + age (hours since newest
file) for each of 10 cache directories (fundamentals /
fundamentals_history / prices / edgar_8k / edgar_10k_text /
yfinance_info / edgar_amendments / edgar_late_filings / edgar_form4 /
osap) to the workflow log in ~15-30 seconds. Surfaces cache eviction
BEFORE any SEC fetch begins instead of after 150-195m of polling.
`bc` + GNU `find -printf` are standard on ubuntu-latest; fail-open
on missing tools (size still prints, age falls back to "?").

**Part 3 — 4 new `Metadata.*_wall_clock_seconds` fields**:

- `tier2_wall_clock_seconds: float | None = None`
- `form4_wall_clock_seconds: float | None = None`
- `osap_wall_clock_seconds: float | None = None`
- `cross_source_wall_clock_seconds: float | None = None`

Parity with existing `fundamentals_latency_p95_seconds` BUT
semantically different: those measure per-ticker fetch p95
(tenacity-cascade detector); these measure total elapsed WALL-CLOCK
seconds for the entire loop start-to-end (budget-overrun + cache-
eviction detector). `None` semantic when loop was skipped via
escape-hatch env-var (`FORM4_FETCH_SKIP` / `QR_SKIP_OSAP`) OR when
the loop failed before the end marker. `cross_source_wall_clock_seconds`
measures the entire Step 8 per-ticker loop (fair-price ensemble +
manipulation + StockDetail write — documented limitation in the
schema field docstring; on cold-cache cross-source dominates at
17-67 min, on warm it doesn't).

Schema bump `0.10.8-phase4.6` → `0.10.9-phase4.6` (PATCH — additive
Metadata-only, no consumer migration). Schema triple lockstep
satisfied: `compute/output/schemas.py` + `frontend/lib/types.ts` +
`frontend/lib/schema-snapshot.json` all regenerated; in-sync per
`python -m compute.output.schema_check`.

**Files changed (6 + tests)**:

- `.github/workflows/compute-rankings.yml` — timeout bump (150→195m)
  + 5-loop budget docstring + cache-restore canary step (~50 lines added)
- `compute/config.py` — `SCHEMA_VERSION = "0.10.9-phase4.6"`
- `compute/output/schemas.py` — 4 new `Metadata` fields (+ docstring
  explaining wall-clock vs per-ticker-p95 semantics)
- `frontend/lib/types.ts` — 4 new optional TS properties (mirror)
- `frontend/lib/schema-snapshot.json` — regenerated via
  `python -m compute.output.schema_check --update-snapshot`
- `compute/main.py` — `time.monotonic()` start/end markers wrapping
  4 loops (Tier-2 / Form-4 / OSAP / cross_source/Step 8). Tier-2
  loop wrapped in defensive outer try/except so an interpreter-level
  failure keeps `tier2_wall_clock_seconds = None`. Form-4 path:
  start marker INSIDE the `else:` branch (FORM4_FETCH_SKIP path
  leaves wall-clock = None). OSAP path: start before try, end at
  end of try success path, None in except. Step 8: start before
  loop, end after the "Wrote N stock detail" logger.info.
  4 new keyword arguments wired into the `Metadata(...)` constructor
  at the end.
- `tests/test_config.py` — schema version pin `0.10.8 → 0.10.9` +
  docstring rewritten to document Issue #287 PR A as the bump reason
- `tests/test_output/test_wall_clock_schema.py` (new) — schema
  contract tests (instantiate Metadata with + without the 4 new
  fields; assert serialization round-trip + None defaults). Behavior
  tests (skipped-via-env-var, failed-before-end-marker) deferred
  to a follow-up since the existing `tests/test_main.py` harness is
  pandas-dep heavy and not amenable to a unit-test mock.

**Part 4 (PR B — separate, gated)** — revert `FORM4_FETCH_SKIP=1`
from `compute-rankings.yml` env block. Lands only after PR A merges
+ ≥ 1 weekly cron green at < 195m wall-clock with all 4 fields
populated AND `form4_wall_clock_seconds` is not None (confirms the
revert path will work). Unblocks Phase 4.5e PR 5 (cluster weight
promotion 5.0 → 7.0) gate-data accumulation for Q3 2026-08-19
quarterly cohort audit.

**Verification ladder (pre-push)**:
- `ruff check .` — PASS (run; clean)
- `python -m compute.output.schema_check` — PASS (snapshot regenerated)
- `pytest tests/test_config.py -v` — PASS 11/11 (schema-version pin held)
- `pytest tests/ -m "not network"` — DEFERRED to CI (sandbox missing
  pandas; CI installs full extras)
- `cd frontend && npx --no -- tsc --noEmit` + `next build` — DEFERRED
  to Vercel preview (sandbox missing node_modules)

**Hard constraints honored**:
- No new defense flag · No scoring formula change · No Rule 16 / Top-5 violation
- Additive-only schema change (PATCH bump)
- All 4 new fields nullable per Rule 18 graceful-degradation
- `FORM4_FETCH_SKIP=1` UNCHANGED in this PR — strict Part-1-through-3 scope
- AGENTS.md substance unchanged (no new agent / no roster change);
  CLAUDE.md §Gotchas gains the `*_wall_clock_seconds` semantic note;
  AGENTS.md §Production-verified run state pointer untouched (cron #69
  still the latest)

PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with
every PR" lockstep per PR #237 convention. CLAUDE.md substance
touched (Gotcha for wall-clock semantic + Phase status pointer for
schema bump). Both Phase 4.5e PR 5 (cluster weight promotion) and
Issue #67 follow-up per-sector delta are still gated on cron data
accumulation — this PR is the pre-req that lets the cron actually
populate the gate-data.

---

## PR #298 (merged 2026-05-28, `030675e9`) — Issue #288 follow-up: cache-key bump `cache-v4 → cache-v5`

One-line YAML fix closing the silent-failure gap surfaced by Issue #287 PR A's Rule 18 instrumentation on cron Run #71 (`368dccd9`, 2026-05-28 08:44 UTC). Post-cron audit (`defense-layer-auditor` + `stock-detail-auditor` + `edgar-debugger` chain) confirmed:

**Root cause** (per `edgar-debugger` 2026-05-28 session):
- PR #292 (`e9aaab31`, merged 04:22 UTC) landed the GOOG/GOOGL per-class XBRL share-override at `compute/ingest/fundamentals.py:1043-1067` (Branch 3 of `_build_snapshot`)
- Branch 3 only executes on live EDGAR fetch — `fetch_fundamentals` short-circuits at `_is_fresh()` (line 1292-1294) when cached parquet age by `latest_filed_date` < `FUNDAMENTALS_REFETCH_DAYS = 45`
- Earlier cron `0ad1d574` (03:22 UTC, pre-PR-#292) wrote the stale parquet (GOOG `shares_outstanding = 12.116B` aggregate)
- Cron Run #71 (08:44 UTC, post-PR-#292) restored that parquet from the GitHub Actions cache, `_is_fresh()` returned True on `latest_filed_date = 2026-04-30` (28d < 45d), and Branch 3 never ran
- `metadata.multi_class_per_class_attempt_count = 0` (PR #292's Rule 18 disambiguator working perfectly — the signal that confirmed the bypass)

**Smoking gun**: `metadata.fundamentals_latency_p50_seconds = 0.0` (warm cache replayed for nearly every ticker) + GOOG/GOOGL still at $4.66T/$4.71T (should be $2.09T/$2.59T per-class).

**Fix scope (1 file, YAML-only)**:

- **`.github/workflows/compute-rankings.yml`** line 129/131/132 — `cache-v4-` → `cache-v5-` (key + 2 restore-keys). Comment block at lines 105-126 expanded to:
  - Cite Issue #288 follow-up + PR #292 + PR #269 anchor PRs
  - Document the `_is_fresh()` short-circuit + Branch 3 placement gap
  - Introduce a 2-trigger bump taxonomy (schema change OR value-correctness fix in live-fetch-only path)
  - Pin the next bump (v5 → v6) trigger conditions

**Why Option A (cache-key bump) over B (targeted invalidation) or C (refactor override out of fetch path)** per `edgar-debugger` verdict:
- Option B: introduces cache-layer-knows-multi-class semantics + chicken-and-egg "detect stale aggregate from cached parquet" condition
- Option C: cache hit triggering live SEC call violates cache semantics + `FundamentalsSnapshot` is frozen
- Option A: matches PR 4c.1 v3→v4 precedent exactly + zero compute/ change + guaranteed correctness on next cron

**One-time cost**: ~25-50 min cold-cache cron on the immediately-following weekly run (full S&P 500 universe live re-fetch). Subsequent crons return to warm-cache ~5-10 min budget. No `timeout-minutes` impact — PR #297 just bumped to 195m which absorbs cold-cache reality with headroom.

**Verification (post-merge, on next cron Run #72)**:

- `metadata.multi_class_per_class_attempt_count = 2` (was 0 — Branch 3 entered for GOOG + GOOGL)
- `metadata.multi_class_per_class_override_count = 2` (Branch 3 succeeded for both)
- `stocks/GOOG.json::raw_metrics.shares_outstanding ≈ 5.429B` (Class C, was 12.116B aggregate)
- `stocks/GOOGL.json::raw_metrics.shares_outstanding ≈ 5.822B` (Class A, was 12.116B aggregate)
- `stocks/GOOG.json::raw_metrics.market_cap ≈ $2.09T` (was $4.66T)
- `stocks/GOOGL.json::raw_metrics.market_cap ≈ $2.59T` (was $4.71T)
- `metadata.fundamentals_latency_p50_seconds > 0.0` (live fetch path active on cold restore)

**Adjacent findings deferred** (not in this PR):

- **FOX / FOXA / NWS / NWSA**: same `multi_class_aggregate_shares_suspected` annotate firing, but they are on `MULTI_CLASS_SHARE_ALLOWLIST` (UNDERCOUNT path, PR #257) NOT `MULTI_CLASS_OVERCOUNT_ALLOWLIST`. The annotate firing IS protective behavior. Decision on whether to add to overcount allowlist deferred to Q3 2026-08-19 quarterly cohort audit per methodology-scientist precedent (needs live XBRL probe).
- **OSAP wall-clock 347.1s on Run #71**: cold OSAP download (cache > 31d mtime or evicted). Single observation; not a regression. Watch on next 2-3 crons for performance-engineer attention if pattern recurs.

**Hard constraints honored**:
- No compute / scoring / schema / valuation / Rule 16 / Top-5 invariant touched
- No new defense flag · No new dep · No new env-var
- YAML-only diff (workflow file + docs)
- Schema version UNCHANGED at `0.10.9-phase4.6` (no Pydantic / TS / snapshot change)
- AGENTS.md substance untouched (CLAUDE.md = SoT for §Phase status; this PR's substance lands in CLAUDE.md §Gotchas as a follow-up note to the "Cron-#3 silent-failure gap" entry + Phase status pointer mention)

PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with every PR" lockstep per PR #237 convention. Closes the GOOG/GOOGL display-only bug that was opened by PR #292's incomplete coverage (the fix code was correct; just never reached due to cache-replay path).

---

## PR (this PR) — End-of-day housekeeping 2026-05-28: drain 3 INFLIGHT markers + bump pointers (in flight, 2026-05-28)

End-of-day Track-A3 housekeeping closing today's 10-PR cycle (#286 / #290 / #291 / #292 / #293 / #294 / #295 / #296 / **#297** / **#298**). Mirror of PR #286 (which drained the post-v1.4.0 cycle) for the post-cron-#71 cycle. Three stale `(in flight, 2026-05-28)` markers in `PHASE_STATUS_INFLIGHT.md` drained to `(merged 2026-05-28, <SHA>)`:

- PR #295 (`2d2ec83e`) — Post-session housekeeping drain 6 INFLIGHT + bump pointers
- PR #297 (`ecb60e64`) — Issue #287 PR A: durable timeout + cache canary + per-loop wall-clock Metadata (schema `0.10.8 → 0.10.9-phase4.6`)
- PR #298 (`030675e9`) — Issue #288 follow-up: cache-key bump `v4 → v5`

Bodies preserved (historical record). CLAUDE.md §Phase status pointer updated to note PR #298 cache-v5 active + production-verified cron Run #71 pointer (`368dccd9`); AGENTS.md open-issues list updated to mark #288 closed by PR #298 + clarify follow-up state.

**Why this PR exists**: without end-of-day drain, session N+1 reads CLAUDE.md / PHASE_STATUS_INFLIGHT.md and sees 3 PRs still "in flight" despite them merging hours earlier — exact same friction pattern PR #286 closed for the post-v1.4.0 cycle. Three same-day drains in one PR keeps the side-file clean for next session.

**Scope (3 files, doc-only)**:

- `PHASE_STATUS_INFLIGHT.md` — 3 header substitutions (in flight → merged + SHA) + this entry appended at end
- `CLAUDE.md` §Phase status — pointer block refresh: PR #298 cache-v5 active + Run #71 production-verified pointer + drain "(in flight this PR)" qualifier from the cache-v5 mention
- `AGENTS.md` open-issues list — #288 status `(fix in flight this PR)` → `(closed by PR #298 cache-v5 bump)`; clarify #287 status post-Run-#71 empirical validation

**Hard constraints honored**:

- No code / scoring / schema / valuation / Rule 16 / Top-5 invariant touched
- No new defense flag · No new dep · No new env-var
- Doc-only diff (Markdown only)
- Schema version UNCHANGED at `0.10.9-phase4.6` (no Pydantic / TS / snapshot change)
- AGENTS.md substance touched per the existing delegation pattern (CLAUDE.md = SoT for §Phase status; this PR refreshes the open-issues lifecycle cross-reference)

PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with every PR" lockstep per PR #237 convention. The drain pattern itself is the same template used in PR #286 (post-v1.4.0 cycle) — keeping the side-file disciplined as the project pattern.

---

## PR #301 (merged 2026-05-28, `978cab65`) — End-of-day 2026-05-28 comprehensive .md sweep: fix 8 MUST-FIX + 6 SHOULD-FIX drifts across 6 canonical docs

Comprehensive `.md` housekeeping closing the 11-PR session day. Output of `docs-reviewer` (sonnet) full Tier 1 + Tier 2 audit on `main` (post-PR-#299) — verdict **NEEDS-CROSS-REF-FIX** with 14 prioritized findings.

**Scope (6 canonical docs)**:

- **`SKILL.md`** — schema-version history table at line 240 prepended with 2 new rows: `0.10.9-phase4.6` (PR #297 — 4 `*_wall_clock_seconds` fields + 195m timeout + cache canary, empirically validated cron Run #71) + `0.10.10-phase4.6` (PR #300 in flight — Issue #67 follow-up per-sector delta). Closes the gap where PR #297 + PR #300 schema bumps were absent from the canonical history.

- **`PHASE_STATUS.md`** §Current state — schema row `0.10.8 → 0.10.9` + PR #300 in-flight note; Post-tag production patches row expanded with PR #295/#296/#297/#298/#299; Production run pointer `0ad1d574` cron #69 → `368dccd9` cron Run #71 with the PR #297 wall-clock empirical numbers + Issue #288 cache-replay smoking-gun. Recently merged block extended 6 PRs → 11 PRs. Issue closure status: #287 (PR A merged, PR B gated) · #288 (closed via #292 + #298) · #289 (closed via #293). Next deliverables refreshed: Issue #67 flip removed (PR #294 already executed); item 2 now = Issue #287 PR B FORM4 revert; PR #300 per-sector delta added as item 3.

- **`CLAUDE.md`** §Phase status — Recently merged block extended 6 → 11 PRs with full SHA + one-liner per PR. New "In flight" sub-section added for PR #300.

- **`AGENTS.md`** §Phase + version state — Production-verified run cron #69 (`233117ac`, 13m 16s) → cron Run #71 (`368dccd9`, 14m 32s, 2026-05-28 08:44 UTC, schema `0.10.7 → 0.10.9-phase4.6`); 4 new wall-clock field values cited (`tier2=10.6s`, `form4=null`, `osap=347.1s`, `cross_source=133.2s`); Issue #288 cache-replay smoking gun captured; closed-issue note for #288 + #289 + #287 PR A.

- **`CONTEXT.md`** §Live snapshot — schema `0.10.8 → 0.10.9` + PR #300 in-flight note; new "Post-tag patches" row listing PRs #292-#299 + PR #300 in flight; cron status cron #69 2026-05-27 → Run #71 2026-05-28; Sector-CoE row updated with empirical 132 → 109 figure; §Roadmap Stage 0 description refreshed: "Cron #70 confirmation + Issue #287 closure" → "Issue #287 PR B FORM4 revert (single-line, gated on cron < 195m + form4 wall-clock populated) · PR #300 merge confirmation".

- **`WORKFLOW.md`** §Agentic 6-Phase Cadence session-start protocol — inline schema `0.10.7-phase4.6` replaced with current `0.10.9-phase4.6` + pointer guidance to PHASE_STATUS.md §Current state as the canonical bump-per-schema-PR target (closes the recurring inline-schema drift pattern).

**3 NICE-TO-FIX items deferred** (per docs-reviewer recommendation):

1. README.md Honest Limitations section does not yet reference the Phase 4.6 honest re-validation harness (PR #283 Hou-Xue-Zhang 2020 survivorship-bias fix + McLean-Pontiff 2016 32% decay banner). Coverage gap, not a cross-reference break. Defer to a follow-up README polish PR.
2. WORKFLOW.md Phase 4.5 row at line 83 cites `v1.2.0` tag; Phase 4.5e ladder technically closed at `v1.3.0-phase4.5e`. Historical-context only — no session confusion risk.
3. METHODOLOGY.md `USE_SECTOR_COE` framing may still say "future flip" pending; needs Read confirmation before edit. Defer to follow-up methodology pass.

**docs-reviewer Lockstep summary cross-check after this PR**:

- `SCHEMA_VERSION`: ALIGNED across CLAUDE.md / PHASE_STATUS.md / SKILL.md / CONTEXT.md / WORKFLOW.md / AGENTS.md at `0.10.9-phase4.6` (main) with PR #300 in-flight note where applicable
- Defense layer `33 declared`: ALIGNED (was already)
- `USE_SECTOR_COE = True` post-PR #294: ALIGNED (was stale in AGENTS.md issue #67 framing + PHASE_STATUS.md Next deliverables — both fixed)
- Subagent count 18: ALIGNED (was already)
- Skill count 45: ALIGNED (was already)
- Latest cron Run #71 `368dccd9`: ALIGNED (was stale in AGENTS.md + PHASE_STATUS.md + CONTEXT.md — all fixed)
- Issue #288 + #289 closure status: ALIGNED (was stale as open in AGENTS.md + PHASE_STATUS.md — both fixed)

**Scope (7 files, doc-only)**:

- `SKILL.md` · `PHASE_STATUS.md` · `CLAUDE.md` · `AGENTS.md` · `CONTEXT.md` · `WORKFLOW.md` — substance updates per punch list
- `PHASE_STATUS_INFLIGHT.md` — this entry appended per PR #237 side-file convention

**Hard constraints honored**:

- No code / scoring / schema / valuation / Rule 16 / Top-5 invariant touched
- No new defense flag · No new dep · No new env-var
- Markdown-only diff (no JSON / YAML / Python / TS change)
- Schema version UNCHANGED on `main` at `0.10.9-phase4.6` (PR #300 will bump 0.10.10 on its merge)
- AGENTS.md substance lockstep with CLAUDE.md per the established delegation pattern

**Verification ladder**:

- `ruff check .` — N/A (no Python touched)
- `python -m compute.output.schema_check` — N/A (no schema touched; passes trivially)
- `pytest tests/ -m "not network"` — N/A (no test surface)
- `grep` cross-reference check — all 7 anchor strings (schema version / cron pointer / `USE_SECTOR_COE` / 18 / 45 / 33 / `v1.4.0-phase4.6`) consistent across all 6 docs after fix

PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with every PR" lockstep per PR #237 convention. Doc-only PR; closes the comprehensive cross-doc drift surface tracked by `docs-reviewer` 2026-05-28 audit.

---

## PR (this PR) — Issue #67 follow-up: per-sector `value_trap_risk` delta instrumentation (in flight, 2026-05-28)

Methodology-scientist Mode B Q2 follow-up deferred from PR #294 (sector-CoE flip, 2026-05-28 05:39 UTC). Adds `Metadata.value_trap_risk_delta_by_sector: dict[str, int] | None` so Q3 2026-08-19 quarterly cohort audit (~12 weekly crons of post-flip data away) has visible per-sector shape evidence — not just the aggregate `value_trap_risk_count_{without,with}_sector_coe` scalars that landed in PR #204.

**Methodology context** (Damodaran 2019 *Investment Valuation* Ch. 8.4 §"Industry Beta"):

After flipping `USE_SECTOR_COE = True` per-sector Ke replaces the flat 10% baseline at `compute/scoring/cost_of_equity.SECTOR_COST_OF_EQUITY` (11 GICS sectors, Ke 6%-12%). Directional predictions:

- **Lower-Ke sectors** (Utilities ~6-7% / Real Estate ~7-8% / Consumer Staples ~7-8%) — ROE ≥ Ke threshold relaxed → fewer RIM-skipped → POSITIVE delta (sector DROPPED flags)
- **Higher-Ke sectors** (Information Technology ~11-12% / Energy ~10-12%) — ROE ≥ Ke threshold tightened → more RIM-skipped → NEGATIVE delta
- **Neutral sectors** (the other 6 GICS sectors at ~9-11%) — small absolute delta near zero

Cron #69 + Run #71 universe-wide already confirmed the aggregate: `132 → 109` (−23 tickers, −17.4%). This PR breaks that −23 down by sector so the next cron's `metadata.json` shows whether the cohort shift matches Damodaran prediction shape OR has unexpected outliers (methodology-scientist re-review trigger).

**Scope (7 files, additive only)**:

- `compute/output/schemas.py` — new `Metadata.value_trap_risk_delta_by_sector: dict[str, int] | None = None` field with full docstring citing methodology-scientist verdict + Damodaran 2019 anchor + direction semantics
- `frontend/lib/types.ts` — mirror TS field as `Record<string, number> | null` (optional, nullable)
- `frontend/lib/schema-snapshot.json` — regenerated via `python -m compute.output.schema_check --update-snapshot`
- `compute/config.py` — `SCHEMA_VERSION = "0.10.10-phase4.6"` (PATCH bump; additive Metadata-only)
- `compute/main.py` — 3 surgical edits mirroring existing scalar dual-counter pattern (lines 1410-1411 init two `dict[str, int]` counters / per-sector increment alongside existing scalar bumps at the two `value_trap_risk_roe_below_cost_of_equity` branches / Metadata constructor computes `delta = sorted(without ∪ with) → {sector: without − with}` or falls back to `None` when both dicts empty)
- `tests/test_config.py` — schema version pin `0.10.9 → 0.10.10` + docstring rewrite citing Issue #67 follow-up
- `tests/test_output/test_value_trap_delta_by_sector_schema.py` (NEW, via `test-engineer`) — 2 active GREEN schema-contract tests mirroring `test_wall_clock_schema.py` pattern from PR #297

**Verification ladder (pre-push)**:

- `ruff check .` — PASS
- `python -m compute.output.schema_check` — PASS (triple in sync at `0.10.10-phase4.6`)
- `pytest tests/test_config.py -v` — 11/11 PASS (schema-version pin held)
- `pytest tests/test_output/test_value_trap_delta_by_sector_schema.py -v` — expect 2 NEW GREEN

**Empirical validation** (post-merge, next cron Run #72):

- `metadata.value_trap_risk_delta_by_sector` populated as non-null dict
- Damodaran shape directionally correct (Util/RE/Staples POSITIVE; IT/Energy NEGATIVE)
- `sum(delta.values()) == value_trap_risk_count_without_sector_coe - value_trap_risk_count_with_sector_coe`

Note: per-sector accumulation runs in the Step 8 per-ticker loop, INDEPENDENT of cache-v5 cache busting. Field populates on next cron regardless of warm/cold fetch path.

**Hard constraints honored**:

- No new defense flag · No scoring formula change · No Rule 16 / Top-5 violation
- Additive-only schema change (PATCH bump)
- Field nullable per Rule 18 graceful-degradation (both dicts empty → `None`)
- Phase 4.5e PR 5 (cluster weight promotion) gate-data UNCHANGED — independent track

**Methodology decision**: methodology-scientist verdict NOT re-requested — the per-sector instrumentation is the EXACT field shape Mode B Q2 verdict from PR #294 explicitly authorized. Future re-trigger only if (a) post-merge cron shows sector breakdown contradicting Damodaran prediction OR (b) Q3 2026-08-19 cohort audit reads ≥ 6 crons of data + per-sector decay pattern needs interpretation.

---

## PR (this PR) — PR #293 follow-up: Site-2 dead-code removal (`_has_corrupt_input` + `_data_quality_corrupt_result`) (in flight, 2026-05-28)

PR #293 (`95e638bf`, merged 2026-05-28 05:20 UTC) retired the Site-2 output-level data-quality ceiling per methodology-scientist Mode B Option C verdict (Penman 2013 §7.4 + Damodaran 2019 Ch. 18 + Huber 1981 §1.4 — defend at corruption source via Site-1, not at downstream output magnitude). PR #293 deleted the call site at `compute/valuation/ensemble.py` Step 4.5 but RETAINED the 2 helper functions as dead code for "one cycle hold" before removal — explicit `test_L2_dead_code_functions_still_callable_after_site2_deletion` retention guard pinned the deferred state. **This PR is that follow-up** — cron Run #71 (`368dccd9`, 2026-05-28 08:44 UTC) confirmed clean operation (NVR fair-price section renders correctly; `valuation_output_anomalous` cohort dropped 5 → 4 = NVR removed correctly; no regression on the Site-1 veto cohort MTB / CPT / MRNA / HBAN).

**Scope (5 files, net −108 lines)**:

- **`compute/valuation/ensemble.py`** — REMOVED 2 dead functions:
  - `_has_corrupt_input(methods) -> bool` (13 lines)
  - `_data_quality_corrupt_result(methods) -> EnsembleResult` (43 lines)
  - Step 4.5 comment block at lines 449-479 updated: "functions kept below as DEAD CODE for one cycle" → "Dead-code helpers `_has_corrupt_input` + `_data_quality_corrupt_result` removed in this PR after cron Run #71 confirmed clean"
- **`tests/test_valuation/test_ensemble.py`** — REMOVED:
  - 2 imports at the top (`_data_quality_corrupt_result`, `_has_corrupt_input`)
  - 3 tests that exercised the removed functions:
    - `test_data_quality_sanity_guard_triggers_on_extreme_method_value` (40 lines)
    - `test_data_quality_guard_boundary_exactly_at_ceiling` (11 lines)
    - `test_data_quality_guard_skipped_methods_dont_trigger` (13 lines)
  - The one-cycle retention guard `test_L2_dead_code_functions_still_callable_after_site2_deletion` (20 lines) — REPLACED with `test_L2_dead_code_functions_removed_post_one_cycle` (24 lines) that asserts `not hasattr(_ensemble, "_has_corrupt_input")` + `not hasattr(_ensemble, "_data_quality_corrupt_result")` — pins the removal so accidental re-introduction surfaces as a clear "Issue #289 retirement reverted" test failure.
  - Section "J. Step 7.5 data-quality sanity guard" header comment refreshed to "(RETIRED post-Issue #289)" with summary of removed-test purpose.
  - The 2 surviving tests (`test_site2_data_quality_guard_retired_post_issue_289` end-to-end + `test_L3_site2_ceiling_not_invoked_for_high_share_price_ticker`) keep verifying POST-RETIREMENT invariants on the NVR cohort.
- **`compute/config.py:127-148`** — `FAIR_PRICE_DATA_QUALITY_CEILING` STAYS ACTIVE (Site-1 in `compute/scoring/risk_overlay.py` shares the constant). Comment block updated: "Site-2 trigger DELETED" → "Site-2 trigger DELETED (PR #293); dead-code helpers REMOVED in the PR #293 follow-up after cron Run #71 confirmed clean."
- **`compute/valuation/applicability.py:65-78`** — reference to `_data_quality_corrupt_result` replaced with reference to the writer-parity emit at `compute/main.py` on the Site-1 veto cohort.
- **`tests/test_scoring/test_risk_overlay.py:520-528`** — `test_D4_data_quality_corruption_fires_at_boundary_strict` docstring updated: "Mirrors compute.valuation.ensemble._has_corrupt_input's strict inequality" → "Site-1 (here) is the canonical input-corruption guard. Site-2 was retired per Issue #289 Option C; the strict `>` invariant lives ONLY here now." Test logic itself UNCHANGED (it tests Site-1 risk_overlay.py veto behavior, never the removed Site-2).

**Removal-guard test design** (test_L2 renamed):

```python
def test_L2_dead_code_functions_removed_post_one_cycle():
    """Issue #289 Option C dead-code retirement is complete."""
    import compute.valuation.ensemble as _ensemble
    assert not hasattr(_ensemble, "_has_corrupt_input"), (
        "_has_corrupt_input was re-introduced — Issue #289 Option C retired ..."
    )
    assert not hasattr(_ensemble, "_data_quality_corrupt_result"), (
        "_data_quality_corrupt_result was re-introduced ..."
    )
```

The `hasattr` check catches BOTH direct re-add AND import re-add. Failure message cites the methodology anchor so a future re-introducer gets the verdict context without having to re-read the issue thread.

**Verification ladder (pre-push)**:

- `ruff check .` — PASS
- `python -m compute.output.schema_check` — PASS (no schema touched; passes trivially)
- `python -m pytest tests/test_valuation/test_ensemble.py tests/test_scoring/test_risk_overlay.py tests/test_config.py -q` — 120 PASS (was 123 — net −3 active tests as planned)
- `grep -rn "_has_corrupt_input\|_data_quality_corrupt_result" compute/ tests/` — only legitimate references remain (comments documenting retirement + new removal-guard assertion strings)

**Hard constraints honored**:

- No scoring formula change · No Rule 16 / Top-5 violation
- Schema version UNCHANGED at `0.10.10-phase4.6` (no Pydantic / TS / snapshot field touched)
- Site-1 input-corruption veto path UNCHANGED — only the dead Site-2 helpers removed
- `FAIR_PRICE_DATA_QUALITY_CEILING` constant retained (shared with Site-1)
- Writer-parity `valuation_output_anomalous` emit at `compute/main.py` UNCHANGED — UI explanation chip continues rendering for Site-1 cohort (MTB / CPT / MRNA / HBAN per PR #265)
- `test_L3_site2_ceiling_not_invoked_for_high_share_price_ticker` (PR #293's end-to-end guard) UNCHANGED — keeps verifying NVR cohort produces non-null median

**Closes the PR #293 retirement contract**: "follow-up PR removes them after ≥ 1 cron of clean operation confirms no regression" — cron Run #71 was the empirical confirm cycle.

---

## PR #303 — Phase 4.5e PR 6: Form-4 10b5-1 negation guard (residual footgun #1) (merged 2026-05-29, 847c21b)

Closes the long-standing residual of footgun #1 from
`compute/scoring/form4_signals.py` module docstring + the PR 4-eq Mode B
verdict (2026-05-23, "Q3 2026-08-19 cohort audit gates whether to
harden ``detect_10b5_1_plan`` with a negation guard against FP matches
on phrases like '10b5-1 plan terminated'"). PR 6 implements the
engineering of the pre-approved mitigation: a post-detector wrapper on
`edgar.ownership.core.detect_10b5_1_plan` that downgrades a `True`
detection to `False` when the resolved footnote text contains a
negation phrase within ±5 word tokens of the 10b5-1 mention.

**Architecture** — post-detector wrapper:

- `compute/scoring/form4_insider.py` gains
  `_NEGATION_PATTERNS: Final[frozenset[str]]` (11 tokens — `terminated`,
  `cancelled`, `canceled`, `expired`, `rescinded`, `discontinued`, `no`,
  `not in effect`, `previously`, `former`, `without`) +
  `_NEGATION_REGEX: Final[re.Pattern[str]]` (compiled bidirectional
  regex; case-insensitive, accepts both `10b5-1` and `10b-5-1`
  spellings; ±5 word-token window before AND after the mention) +
  `_has_negation(text: str) -> bool` helper.
- `_detect_10b5_1_on_transaction` now wraps the upstream detector call:
  detector returns True → check `_has_negation(resolved_text)` → on
  match return False and `_bump_negation_downgrade_count()`; detector
  returns False or None → pass through unchanged. The guard never
  fabricates a positive signal (only downgrades True → False).

**Rule 18 observability surface** —
`Metadata.form4_negation_guard_downgrade_count: int | None` ships in
the same PR. Counter is module-level + thread-safe (`threading.Lock`
around an int) so the `EDGAR_MAX_WORKERS=8` parallel form-4 fetch loop
in `compute/main.py` can accumulate downgrades across workers without
race. `compute/main.py` calls
`form4_insider.reset_negation_downgrade_count()` immediately before
the `ThreadPoolExecutor` block and
`form4_insider.get_negation_downgrade_count()` on the success path
(success-path `int`; outer-try-failure or `FORM4_FETCH_SKIP=1` →
`None`, mirroring `form4_wall_clock_seconds` semantics).

**Schema bump** `0.10.10 → 0.10.11-phase4.6` (PATCH — additive
Metadata field only). Triple touched:
- Pydantic: `compute/output/schemas.py:Metadata.form4_negation_guard_downgrade_count`
- TypeScript: `frontend/lib/types.ts:Metadata.form4_negation_guard_downgrade_count`
- Snapshot: `frontend/lib/schema-snapshot.json` regenerated via
  `python -m compute.output.schema_check --update-snapshot`; verified
  clean.

**Methodology gate** — SKIPPED per pre-approval. PR 4-eq Mode B
verdict 2026-05-23 documented in `form4_signals.py` footgun §1:
"Q3 2026-08-19 cohort audit gates whether to (a) promote
``INSIDER_SELL_CLUSTER_WEIGHT`` ... and (b) harden
``detect_10b5_1_plan`` with a negation guard against FP matches on
phrases like '10b5-1 plan terminated'". PR 6 = pure engineering of
the approved mitigation. The Q3 audit reads
`form4_negation_guard_downgrade_count` from the surfaced metadata,
no fresh methodology consultation needed.

**Expected delta firing-rate** (per Cohen 2008 §III routine-vs-
opportunistic + Jagolinzer 2009 §3.2 high-information regime):
`insider_sell_cluster` `+5% to +10% relative` on a universe-baseline
cron (absolute << 1%; most 10b5-1 disclosures are affirmative, not
negated). `c_suite_unusual_sell` similar. The negation guard
reverses the conservative bias direction noted in the original
footgun caveat: pre-PR-6, terminated/former-plan footnotes caused
over-exclusion of legitimate opportunistic trades from the cluster
cohort; PR 6 returns those trades to the cohort, increasing cluster
firing slightly toward ground truth.

**Test surface** (`tests/test_scoring/test_form4_negation_guard.py`)
— comprehensive: ~10-12 unit + 2 Hypothesis (idempotence +
monotonicity) + 1 manifest pin + thread-safety stress + integration
with `_detect_10b5_1_on_transaction` via mocked `footnotes_dict` and
duck-typed `tx`. Written by `test-engineer` parallel-spawn (sonnet).
`tests/test_config.py:test_schema_version_is_phase4_6` schema pin
bumped `0.10.10 → 0.10.11-phase4.6` with PR 6 rationale docstring.

**Footgun caveat preserved** in `form4_signals.py` module docstring
§Footguns §1: residual ~10-15% routine-but-not-10b5-1 contamination
per Jagolinzer 2009 (insiders without 10b5-1 plans but with 5y
calendar-fixed trade timing) remains the deferred follow-up. Cohen
2008 full routine-vs-opportunistic classifier needs the 5y per-
insider lookback that the current 180d cache cannot satisfy without
a structural change.

**Sanity probe** (pre-test-engineer): 14-case matrix verified
`_has_negation` returns expected True/False on all 14 positive +
negative footnote-text examples; counter reset + bump cycle works.

**quantrank-reviewer (opus) verdict** READY-TO-PUSH. 3 WARNs filed
as non-blocking; 2 addressed inline, 1 deferred:
- WARN-2 (BEFORE/AFTER asymmetry on ``no``) FIXED: added inline
  comment at ``_NEGATION_REGEX`` BEFORE branch + cross-reference at
  AFTER branch noting ``no`` is intentionally BEFORE-only (post-
  mention ambiguity FP risk: "10b5-1 plan, no shares sold").
- WARN-3 (M1 manifest test misses regex-vs-frozenset drift) FIXED:
  added `test_M3_negation_patterns_each_appear_in_compiled_regex`
  drift-detector — every token in ``_NEGATION_PATTERNS`` must appear
  in ``_NEGATION_REGEX.pattern`` source string. Tests 33 → 34.
- WARN-1 DEFERRED to follow-up PR: ``_NEGATION_REGEX`` anchor
  ``(?:rule\s+)?10b-?5-?1`` matches only 2 of upstream
  ``detect_10b5_1_plan``'s 6 substring patterns (the ones with the
  ``-1`` suffix). A footnote like "Rule 10b5 plan terminated 2022"
  triggers the upstream detector True but slips past the negation
  guard. **Bias direction remains safe** (over-includes legit
  trades in opportunistic cohort, never under-excludes); but the
  docstring claim that PR 6 closes residual footgun #1 is somewhat
  overstated. Fix path: extend regex anchor to
  ``(?:rule\s+)?10b-?5(?:-1| plan)?``. Defer rationale: next cron's
  ``form4_negation_guard_downgrade_count`` will measure whether the
  gap is material; structural change worth a separate PR with its
  own test surface walk. Tracked here pending cron Run #72+ data.

No composite-score change · No Rule 16 violation · Defense layer
emit count unchanged at 33 declared boolean flags (PR 6 hardens an
existing input filter; no new flag) · Cluster + C-suite weights
UNCHANGED (5.0 / 3.0; promotion to 7.0 still gated on Q3 audit per
PR 4-eq verdict).

---

## `expert-user-explorer` subagent — interactive app-usage tester (merged 2026-05-29 via PR #304, e070db6)

New **19th subagent** `expert-user-explorer` (Tier 2 Lifecycle,
sonnet, read-only) — the first agent that **interactively *uses*** the
QuantRank app end-to-end as a sophisticated-investor persona and
reports experiential feedback. Phase A of a 2-phase program requested
this session (Phase B = tune all 19 agents for the opus-4.8 main model
+ "dynamic workflow", one agent at a time per "ค่อยๆทำทีละ subagents").

**Mechanic (validated in-sandbox this session)**: `npm ci` (430 pkgs,
~20s; npm-registry egress allowed) → `next build` (505 static routes,
~2min) → `python3 -m http.server --directory out` → headless **node**
Playwright (`/opt/node22` bin, v1.56.1; python-playwright is NOT
installed) drives navigate → filter → sort → drill into `/stock/<T>/`
→ read charts. Real console errors = **0** once the
`ERR_CERT_AUTHORITY_INVALID` logo-CDN noise is carved out (sandbox
cert artifact, ≈1/visible-row, NOT an app bug — the agent excludes it).

**Persona panel**: P1 value-quality screener (primary, shipped fully) +
P2 risk-averse red-flag checker / P3 quant factor-comparer / P4
methodology skeptic (documented modes, expanded incrementally).
Distinct from the three nearby agents — `stock-detail-auditor` (is the
data right?) / `frontend-design-reviewer` (is the component code
on-pattern? — static) / `vercel-preview-auditor` (did it build/deploy?).
This is the only agent that *clicks*. Output = severity-ranked friction
+ a mandatory "data-right-but-display-wrong" JSON cross-check + a
per-persona accomplish-the-goal verdict; proposes issues, never files
or fixes them.

**Lockstep**: CLAUDE.md §Layout (18→19, Tier 2 5→6, 6→7 flows) +
§Auto-routing delegation + cue tables + post-cron batch · AGENTS.md
§Project structure count (2 refs) · `.claude/agents/README.md` set
header (19) + Tier 2 (6) roster row + new **Flow 7 — Experiential UX
pass**. Tools `Read, Bash, Grep, Glob` (no Edit/Write, no issue-write,
no Vercel MCP — local-first by design, sidesteps the install-specific
MCP-UUID inheritance gotcha). No compute / schema / scoring / valuation
/ frontend production-code change — agent file + doc lockstep only.

---

## `RiskFlagsCard` — render `risk_flags[]` vetoes on stock detail (merged 2026-05-29 via PR #306, 6ce7c1b)

Closes **issue #305** — surfaced by the `expert-user-explorer` agent's
first live-fire (its run on PR #304's just-merged agent).
`StockDetail.risk_flags[]` (the 7 Tier-1 hard vetoes) was typed in
`frontend/lib/types.ts` + present in the committed JSON but rendered
NOWHERE on `/stock/<T>/` — so EIX showed "Sell" + MoS +34% +
manipulation 0/100 with **no on-page reason** (the `altman_distress`
veto driving the recommendation was invisible). Scope: **137/502
tickers (27%)** carried ≥1 invisible flag (sloan 56 / altman 46 /
net_issuance 37 / beneish 12 / dqic 4 / dechow 1 / non_reliance 1).

New `frontend/components/RiskFlagsCard.tsx` mirrors `ManipulationRiskCard`
(null-when-empty, rose veto tone, paired `dark:` variants, `[flag]`
mono code) and renders just before `ManipulationRiskCard` on the detail
page. Each veto carries a human-readable label + one-line academic-
anchored detail (Altman 1968 / Sloan 1996 / Daniel-Titman 2006 /
Beneish 1999 / Dechow 2011 / Schroeder 2024 / Step-7.5 guard) sourced
from `docs/METHODOLOGY.md`; footer states Rule 16 (raw rank unchanged;
`entered_top5` forfeited). Verified: `next build` clean (506 routes);
EIX renders the card, clean AAPL does not (null-when-empty). Multi-agent
loop closing this: expert-user-explorer found it → METHODOLOGY.md
anchors → frontend-design-reviewer review → expert-user-explorer
re-validation. No schema / compute / scoring change — frontend-only
(1 new component + 2-line page wiring).

---

## Phase B — opus-4.8 orchestrator + dynamic-workflow agent tuning (merged 2026-05-29 via PR #307, bb1d7fd)

Second phase of this session's program (Phase A = the `expert-user-explorer`
agent, merged #304). Tunes all 19 subagents to work with the opus-4.8 main
session as orchestrator under a *dynamic* (composed-on-the-fly) workflow
rather than only the fixed coordination flows.

Audit finding: most agents lacked an explicit, parseable orchestrator handoff,
so the main session had to re-read full reports to route. Fix: (a) new
`.claude/agents/README.md` §"Dynamic workflow & the opus-4.8 orchestrator"
documenting the model (orchestrator composes the next step from each agent's
handoff; the 7 flows are canonical examples, not an exhaustive script) + the
4-opus/15-sonnet rationale; (b) a uniform `## Handoff` section appended to all
19 agents with the contract line `HANDOFF · status=… · next=<DONE | SPAWN
<agent>:<scope> | ESCALATE <agent> | NEEDS-USER:<decision>>`; (c) CLAUDE.md
§Spawn discipline "Route on the handoff line" bullet + AGENTS.md mirror; (d)
`expert-user-explorer` P2–P4 personas fleshed from stubs into full missions
(P2 now reads the new Risk Vetoes card). Doc/prompt-only — no compute / schema
/ scoring / frontend code change.

---

## PR #310 — stale_filing_hard pre-Step-7 injection (latent Rule-16 fix, merged 2026-05-29, a941e2e)

Closes **issue #309**. Surfaced by the opus-4.8 re-audit of the prior
opus-4.7 session work (user asked to re-check what the earlier model got
wrong). `quantrank-reviewer` flagged it during a fresh-eyes pass of #306;
`defense-layer-auditor` confirmed the execution order.

**Bug (latent):** `stale_filing_hard` was merged into `risk_flags[ticker]`
only in the Step-8 per-ticker loop (`compute/main.py`), AFTER the Step-7
Top-5 rotation had already frozen `entered_top5` from the 7
`compute_risk_flags` vetoes. A hard-stale stock (filing > 180d) ranking
top-5 by raw composite + tripping none of the 7 vetoes could be written
with both `risk_flags=["stale_filing_hard"]` AND `entered_top5=True` —
a Rule-16 violation. Fires 0× on the current S&P 500 cron (all timely
filers), so it was latent, not an active production defect; pre-existing,
not introduced by the recent RiskFlagsCard work.

**Fix:** Step-6b pre-scan injects `stale_filing_hard` before the rotation
reads `risk_flags`; `asof_date` hoisted above the rotation so the lag
check can reference it (behavior-neutral). Step-8 merge stays (idempotent,
deduped). `ensemble.py:289` docstring corrected ("Step 7" → Step 8).
Tests +5 in `tests/test_main.py` (positive/negative/boundary 180-vs-181/
exit/idempotency) via a verbatim-copy `_step6b_then_step7` helper — logic
test matching the file's convention, not a main.py regression guard (noted
honestly in the commit). Zero scoring impact, no schema change.

**Process lessons recorded this PR** (CLAUDE.md §Gotchas + AGENTS.md
§Code style): (1) lint the WHOLE repo (`ruff check .`) before push, never
per-file — the per-file pass let a second-commit test file's `UP037`
escape and turned CI red. (2) The `asof_date`-in-scope assumption from the
reviewer was wrong; `ruff` F821 caught the NameError before it shipped —
verify sub-agent claims, don't trust them. Both fixed before merge.

---

## Phase 4 tasteful-motion — app-wide entrance + signature animations (in flight, 2026-05-29)

User ask: "ออกแบบ design และทำ animation ให้ส่วนต่างๆของ app ให้ดูสนุกสนาน
น่าตื่นเต้น ดูแล้วไม่น่าเบื่อ" (make the app fun / exciting / not boring).
Grill-resolved spec (5 Qs): **tasteful** (not playful — keeps LedgerCraft
flat + finance-tool trust) · **CSS/Tailwind only** (no framer-motion;
+0 deps, +0 bundle) · **whole app** in one PR · **play once per session**
(no replay annoyance for power users) · **signature = composite-score
gauge sweep**.

Scope (9 files, +503/−50, frontend-only — no schema/compute/scoring):
- `tailwind.config.ts` + `app/globals.css`: rise-in / chip-pop / flag-pulse
  keyframes + stagger-1..12 + .gauge-arc (800ms) + .hover-lift + EXTENDED
  prefers-reduced-motion guard (every token snaps to static end-state).
  transform+opacity ONLY (Motion Rule 1) — an early box-shadow draft on
  flag-pulse/hover-lift was dropped per frontend-design-reviewer.
- `lib/useMotion.ts` (new): useCountUp (inits at target → SSR/no-JS show
  correct number; count-up is progressive enhancement) · useInViewOnce ·
  usePlayedOnce (sessionStorage, effect-based so the animate class is
  client-only — NEVER baked into the static prerender, which would replay
  on every full load + hydration-mismatch; this is Motion Rule 5).
- `ScoreGauge.tsx` (new client): signature — radial gauge sweeps 0→score +
  synchronized count-up over 800ms on first view this session, keyed PER
  TICKER (not score value — 269 uniques cover 502, would skip 46%).
- `ScoreBadge.tsx`: lg branch delegates to ScoreGauge (sm/md stay
  server-rendered across the 502 table cells).
- `RankingTable.tsx`: row stagger-in (desktop + mobile), gated to first
  home view + unfiltered page 1.
- `RiskFlagsCard.tsx`: veto-row attention pulse (rise + scale settle).
- `docs/design.md`: new §Motion (token table + 5 non-negotiable rules +
  signature note) — locks the vocabulary for docs-reviewer.

Charts: FairPriceBarChart + PillarRadarChart draw in free (Recharts default
on mount); PriceHistoryChart animation deliberately stays OFF (re-renders
on every period toggle → would re-sweep on each click).

Gates passed: frontend-design-reviewer READY-FOR-SPOT-CHECK (A–G PASS;
1 self-inflicted Rule-1 FAIL fixed). expert-user-explorer ACCOMPLISHED
("polished, not toy-like; Stripe/Linear register; 0 looping anims") — 2
MINOR fixed (per-ticker key + count-up CLS 0.026→0.0214). All motion
verified animating via headless Playwright (not just build-passes);
reduced-motion confirmed static + correct data. next build clean (506
routes); ruff + tsc clean.

---

## Responsive + a11y audit fixes (in flight, this PR · 2026-05-29)

Frontend-only fix batch from the "audit responsive ทุกขนาดทุก platform"
two-angle sweep: `frontend-design-reviewer` (code) + `expert-user-explorer`
(live headless-chromium across 22 viewports 320→2560px, 89 screenshots).
Main-agent reconciled the two and caught a false-positive in EACH (verify-
don't-trust):
- code-audit M2 (FairPriceBarChart 320px overflow) — REFUTED: parent
  `:196` already has `flex-wrap`; live measured 0 overflow there.
- live "ultrawide no max-width cap" — REFUTED: `AppShell:72` has
  `mx-auto max-w-6xl` (1152px); live measured `<main>` (the flex-1
  wrapper, correctly full-width) not the capped content div.
- live "sidebar backdrop 1px @320px" — DROPPED (not fixed): the named
  `fixed inset-0` backdrop is shared with the home page, which measured
  CLEAN, so it cannot be the differentiator; 1px sub-pixel, deferred.

6 confirmed fixes (all evidence-backed; the 7th — S5 iPad-Safari `dvh` —
was deferred during review, see the Sidebar bullet):
- `app/stock/[ticker]/page.tsx` — hero score+MoS donut pair
  `flex-nowrap → flex-wrap` (M1; EIX-style long "UNDERVALUED" MoS label
  clipped the viewport at ≤329px, confirmed by screenshot; stacks on the
  narrowest phones, side-by-side ≥375px unchanged).
- `app/globals.css` — global `:focus-visible` outline baseline,
  `2px solid rgb(99 102 241)` = indigo-500 (M4; Tailwind preflight strips
  the native outline → all ~24 buttons/links + the sortable headers had NO
  keyboard focus indicator; `:focus-visible` not `:focus` so it is
  keyboard-only; the two search inputs keep their `focus:ring` via
  specificity; intentionally outside the reduced-motion guard since it is
  not motion). Authored as `rgb()` (not hex / `theme()`) to match the
  file's house style — globals.css tokenizes nothing and uses raw
  `rgb()` / `oklch()` literals throughout, so Rule 0's "no hex in
  className" does not apply and `rgb()` is the consistent representation.
- `components/RankingTable.tsx` — sortable `<th>` keyboard parity
  (`tabIndex={0}` + Enter/Space `onKeyDown`; WCAG 2.1.1 / 4.1.2; aria-sort
  already present) + mobile card "past day" `whitespace-nowrap` (was
  breaking mid-phrase at 375px).
- `components/Disclaimer.tsx` — "more/less" toggle lifted to the WCAG
  2.5.8 (AA) 24px floor (was 28×16) via `-my-1 min-h-[24px] inline-flex`
  (negative margin absorbs the height so the line does not grow).
- `components/Sidebar.tsx` — S5 (iPad-Safari `100dvh` address-bar gap)
  **DEFERRED from this PR**: the Tailwind two-utility `h-screen` /
  `h-[100dvh]` emission order is ambiguous + uncertifiable in-sandbox
  (chromium only), and the review's "reverse the class order" fix is moot
  (class-attribute order does NOT drive CSS cascade — stylesheet source
  order + specificity do). Worst case the change was a no-op (= prior
  `md:h-screen`), so reverting loses nothing; the dvh enhancement is
  deferred to a follow-up that does it order-independently
  (`height: 100vh; height: 100dvh;` in globals.css, guaranteed order) and
  tests on real iPad Safari. Sidebar stays `md:h-screen` (unchanged from
  pre-PR).
- `tailwind.config.ts` — stale gauge comment ("driven by a CSS
  transition") corrected to the `gauge-sweep` @keyframes reality (same
  drift class PR #314 fixed in ScoreGauge.tsx, different file).

Deliberately NOT changed (per user "ชุดแนะนำ — ไม่แตะ density บน desktop"):
the broad touch-target 44px bump on Filters / pagination / chips (they
pass WCAG AA 24px; 44px would chunk up the desktop UI). PillarRadarChart
24px bar @320px is legibility not overflow (live clean) — deferred. Home
page: 0 overflow across all 22 viewports; table↔card swap @768px clean.

Verification: `next build` clean (506 routes, type-check + lint pass);
`ruff check .` clean (no Python touched). Branch rebased onto `origin/main`
(PR #314 duplicate commit auto-skipped). No schema / compute / scoring /
valuation change — className / CSS / comment diff only.

Gates (all passed): quantrank-reviewer **READY-TO-PUSH** (0 FAIL);
phase-coordinator **LOCKSTEP-SATISFIED**; frontend-design-reviewer raised
2 FAILs both reconciled by the main agent against ground truth — (1) raw
hex overruled (globals.css uses raw `rgb()` / `oklch()` throughout;
converted to `rgb()` for house-style anyway) and (2) the `h-dvh` order fix
was logically moot so S5 was reverted/deferred (above);
expert-user-explorer **ACCOMPLISHED 5/5** with measured DOM evidence —
EIX@320 `scrollWidth == clientWidth` on 4 tickers; focus ring
`2px solid rgb(99,102,241)` on all tabbed elements + suppressed on mouse
click; `<th>` Enter/Space re-sorts with `aria-sort` update; "past day"
`white-space: nowrap` (1 client rect); "more" button height 24px.
Platform caveat: chromium-only in-sandbox — mobile-Safari / Firefox not
certified.

---

## Install `web-animation-design` skill (in flight, this PR · 2026-05-29)

New top-level skill `.claude/skills/web-animation-design/SKILL.md` — a
front-end animation decision guide (easing families · sub-300 ms duration
bands · transform/opacity GPU rule · springs · `prefers-reduced-motion` +
touch-hover a11y · before/after review-table format). Ties into the
existing motion system (`docs/design.md` §Motion + `frontend/lib/useMotion.ts`
`useCountUp` / `usePlayOnMount` + the `gauge-sweep` keyframe) so new motion
matches the app's existing hand.

**License posture** — the file the maintainer uploaded was an `mcpmarket`
bundle distilled from Emil Kowalski's PAID "Animations on the Web" course
with NO declared license. Per the user's explicit choice (and matching the
project's `good-code-bad-code` / `9arm`-fallback precedent for
undeclared-license sources), the skill ships as **ORIGINAL PROSE /
INSPIRE-ONLY** — zero upstream text copied; the principles are standard
published front-end facts; Emil Kowalski + easings.net are credited as
inspiration in the skill's Attribution section. It is NOT the verbatim
mcpmarket file. (The earlier `curl … | bash` from the same marketplace was
DECLINED as an unrelated RCE vector — only inspected, hand-written content
was adopted.)

Doc updates: skill count 45 → 46 in CLAUDE.md §Layout + SKILL.md layout
table + `.claude/skills/README.md`; new THIRD_PARTY_NOTICES.md entry
documenting the inspire-only posture. No compute / schema / scoring /
valuation / frontend-code change — `.claude/` + docs only. No build / test
impact (markdown skill; not in any CI code path).

---

## Fix stock-detail hero overlap when sidebar expanded (in flight, this PR · 2026-05-29)

**Bug** (reported by maintainer with two `/stock/NVDA/` screenshots): on
the per-stock detail hero, when the left-rail **sidebar is EXPANDED** at
md-ish viewports (~768–900px CSS width — small laptop window / tablet
landscape / split-screen), the composite-score gauge donut ("74") rendered
**directly on top of** the "Information Technology" sector chip, and
"Semiconductors" truncated to "Semic…"/"S…". Clean when the sidebar was
collapsed. Confirmed visually + with bounding-box measurement.

**Root cause** (PRE-EXISTING — *not* a #315 regression): the hero's outer
row at `app/stock/[ticker]/page.tsx:87` flips to two columns at
`sm:flex-row` (640px **viewport**). But the expanded sidebar consumes 240px
(`md:w-60`), so at md the hero's *content* area can be < 470px — too narrow
for the right stats block's ~**360px intrinsic** width (two `h-16 w-16`
donuts + labels). With `nowrap` the right block claims its full width
first; the left identity block (`min-w-0 flex-1`) is crushed to **31–83px**
and, being `min-w-0` + `overflow:visible`, its 157px sector chip paints
*outside* its cell onto the gauge (measured **54×20px** collision at 820px).
The broken `sm:flex-row` predates #315 — it arrived with the sidebar
(LedgerCraft Phase 3c, PRs #232–#234). #315 only touched the *inner*
gauge-row `flex-wrap` (line 128, the 320px MoS-label fix) and never covered
the sidebar-expanded state (its sweep was viewport-only).

**Fix** (frontend className-only, 9 insert / 2 delete, 1 file): raise the
two-column breakpoint `sm → lg` on the outer hero row
(`lg:flex-row lg:items-start lg:justify-between`) + add a `min-w-0` shrink
guard on the right block (`flex min-w-0 flex-col gap-3 lg:items-end`) + a
rationale comment so it isn't "optimized" back to `sm`. Below `lg` the hero
**stacks** cleanly in BOTH sidebar states (impossible to overlap); at `lg+`
there is provably enough room (1024px expanded → left block **287px**
measured, 157px chip fits with margin). Trade-off: 640–1023px viewports
that *could* do two-column (collapsed sidebar, or below-md full-width) now
stack — clean, safe, and arguably better tablet UX.

**Verification** (local, node_modules present): `next build` green (506
routes) + `tsc --noEmit` clean + `ruff check .` clean; Playwright DOM
measurement on NVDA dark mode at 768/820/900/1024/1280 × expanded/collapsed
+ 375 mobile → gauge-vs-sector-chip overlap = **none in all 8 cases** (was
54×20px @820 expanded, 31px-crush @768). Two agents confirmed the mechanism
(`expert-user-explorer` measured + screenshotted; `frontend-design-reviewer`
code-traced + proposed the `lg`+`min-w-0` fix); main agent overruled two
sub-agent claims via verify-don't-trust: (a) the "BROKEN to 1280px"
overstatement — at 1280px expanded the left block is 543px = fine; the real
window is ~768–900px expanded; (b) the alternative "add `sm:flex-wrap` to
the outer row" idea — defeated by the left block's `min-w-0` (flexbox treats
it as fitting at 0, so the right block never wraps). No schema / compute /
scoring / valuation change.

---

## Add docs/LESSONS_LEARNED.md (agent-process dos/don'ts) (in flight, this PR · 2026-05-29)

New companion doc `docs/LESSONS_LEARNED.md` — a running "กันลืม" log of
agent-process mistakes + dos/don'ts (workflow / git / review discipline /
orchestration), complementing CLAUDE.md §Gotchas which owns code-domain
invariants. Seeded with the 2026-05-29 session: verify-don't-trust (re-derive
sub-agent numbers — the "broken to 1280px" overstatement + the no-op
`sm:flex-wrap` proposal were both caught pre-apply), don't-push-a-merged-branch
(stop-hook false positive after #317 → prune, not push), full-repo lint/test
gate (PR #310), viewport × sidebar-state responsive matrix, Read-before-Edit
after `git reset`, `curl | bash` decline, and original-prose-for-undeclared-
license. Pointer added to CLAUDE.md + AGENTS.md §Companion files (lockstep + so
future sessions find it). Doc-only — no compute / schema / scoring / valuation /
frontend code change.

---

## Fix stale skill-count (45→46) in 4 docs + correct LESSONS_LEARNED home-count (in flight, this PR · 2026-05-29)

Follow-up to #318 (caught by its `docs-reviewer` gate, which returned after
#318 had already merged). The skill-count 45→46 bump from #316 had only
updated 4 of the **7** doc homes — `PHASE_STATUS.md` §Current state +
`CONTEXT.md` (×3 mentions) + `.claude/agents/README.md` stayed stale at 45.
This PR brings all 7 homes to 46 and corrects the `docs/LESSONS_LEARNED.md`
entry that itself under-counted the homes ("4 doc homes" → "7"; bare "README"
→ "`.claude/skills/README.md`"; top-level `README.md` has no skill count). The
fix demonstrates its own lesson — the first follow-up grep still missed two of
the homes (different phrasings), needing broader passes. The 7 homes: CLAUDE.md
§Layout · AGENTS.md · SKILL.md · `.claude/skills/README.md` · PHASE_STATUS.md
§Current state · CONTEXT.md · `.claude/agents/README.md`. Doc-only — no compute
/ schema / scoring / valuation / frontend code change; `ruff` clean.

---

## Fix mobile sidebar drawer when desktop `collapsed` is set (in flight, this PR · 2026-05-29)

**Bug** (reported by the maintainer, who operates from a phone, with two
`/stock/NVDA/` screenshots): on mobile, when `localStorage['quantrank.sidebar.collapsed']`
is `'1'` (a state the user reaches by collapsing the rail on desktop — an
ordinary action — that then persists), opening the hamburger drawer renders an
**icon-only ~93px strip** — no nav labels ("Rankings"/"Methodology"/"Design"/
"GitHub"), no "NAVIGATION"/"RESOURCES" section headers, no "QuantRank" wordmark,
and **no theme toggle at all**. There is **no recovery path on mobile** (the
collapse/expand toggle is `md:inline-flex` = desktop-only). Reproduced + measured
(drawer 93px / all-false at collapsed=1 vs 256px / all-true at collapsed=0).

**Root cause** (PRE-EXISTING — shipped with the sidebar in LedgerCraft Phase 3c,
not a regression from any in-flight work): `frontend/components/Sidebar.tsx`
treats `collapsed` — a desktop-only concept — as a GLOBAL flag. The width class
`${collapsed ? 'md:w-16' : 'w-64 md:w-60'}` gives the collapsed branch **no
mobile width** (`md:w-16` is inert < md → drawer shrinks to content), and five
`{!collapsed && …}` render-guards (wordmark / section header / nav label /
external icon / version chip) plus the footer theme-toggle ternary (collapsed
branch `hidden … md:flex` → invisible on mobile) all strip content on mobile.

**Fix** (frontend className-only, 1 file, +29 / −25): make `collapsed` take
effect **only at md+** via CSS — never via the `mobileOpen` runtime state.
Width → `w-64 ${collapsed ? 'md:w-16' : 'md:w-60'}` (mobile always full 256px).
Each `{!collapsed && X}` → always render X + `md:hidden` when collapsed. Footer →
render both the row toggle (`${collapsed ? 'md:hidden' : ''}`) and the icon
toggle (`hidden ${collapsed ? 'md:flex' : ''}`) so mobile always gets a usable
row toggle; only one is visible per breakpoint (the other is `display:none`, so
a11y sees exactly one). **Chosen the CSS-`md:hidden` approach over the
`|| mobileOpen` approach** the reproduce agent proposed: it models the real
invariant ("collapsed ⇒ md+ only") declaratively, mirrors the already-correct
`md:justify-center md:px-0` pattern at the link base, keeps all content in the
DOM at every breakpoint (no hydration mismatch — `collapsed` defaults false so
SSR emits no `md:hidden`), and avoids the `mobileOpen`-leaks-into-desktop
coupling (open drawer on mobile → resize to desktop would otherwise break the
collapse).

**Verification** (local): `tsc --noEmit` clean · `next build` green (506 routes) ·
`ruff check .` clean; Playwright DOM measurement on NVDA dark mode across 4
states — **mobile collapsed=1 now 256px with wordmark + "Rankings" + section
headers + row theme toggle all visible** (was 93px / all-hidden); mobile
collapsed=0 = 256px full; **desktop collapsed=1 still 64px icon rail with labels
hidden + icon toggle** (no regression); desktop collapsed=0 = 240px full. Two
agents confirmed the bug + mechanism identically (`expert-user-explorer`
measured + screenshotted; `frontend-design-reviewer` code-traced + proposed the
exact diff); main agent reconciled the two divergent fix proposals. No schema /
compute / scoring / valuation change.

---

## Fix stale sidebar footer version chip v1.2 → v1.4.0 (in flight, this PR · 2026-05-29)

The left-rail footer hardcoded `v1.2 · MIT` while the latest release tag is
`v1.4.0-phase4.6`. Flagged as a WARN by `quantrank-reviewer` during the PR #320
gate: pre-existing staleness, but PR #320's mobile-drawer fix newly **un-hid**
the chip on mobile when `collapsed='1'` (it was previously suppressed), so more
users now see the stale string. One-character-class literal change in
`frontend/components/Sidebar.tsx` (`v1.2` → `v1.4.0`, matching the current
release tag in short form). Verified: `tsc --noEmit` clean · `next build` green
(506 routes) · `ruff check .` clean. Frontend-only; no schema / compute /
scoring / valuation change.

---

## Fix price-chart crosshair: kill drag lag + park tooltip at latest in all resting states (in flight, this PR · 2026-05-29)

**Bug** (reported by the maintainer, mobile): on the per-stock price chart
(`PriceHistoryChart.tsx`, Recharts 2.15.4 `<AreaChart>` + `<Tooltip>`), (1)
dragging fast → the tooltip box **lags behind** the finger; (2) the crosshair
line + box do not **park at the latest date** in any resting state — on page
open nothing shows, after a drag-release it freezes at the last-touched point
then vanishes when the pointer leaves, and orientation/period changes leave it
at an arbitrary point. Reproduced + measured by `expert-user-explorer`; root
cause source-traced by `frontend-design-reviewer` against the recharts source.

**Root cause:** the `<Tooltip>` used Recharts defaults — no `defaultIndex`
(so no rest state) and `isAnimationActive` unset (default true → an inline
`transition: transform 400ms` on the tooltip wrapper makes the box chase the
finger = the lag; measured target 220px vs computed 186px mid-animation). The
`<Area>` already had `isAnimationActive={false}`; the `<Tooltip>` did not.

**Fix** (frontend className/props + 2 hooks, +44 / −1, 1 file): on `<Tooltip>`,
add `defaultIndex={chartData.length - 1}` (park at latest on mount) +
`isAnimationActive={false}` (kill the lag). Recharts applies `defaultIndex`
only on mount, so re-assert it on the other resting events by **remounting
`<AreaChart>` via a `key={`${period}-${restKey}-${layoutKey}`}`**: `restKey`
bumps on `onPointerUp`/`onPointerLeave` (snap back to latest after a
drag-release / pointer-exit), `layoutKey` bumps on a `matchMedia('(orientation:
portrait)')` change (re-park after rotate). Period change is covered by
`period` already being in the key.

**Two refinements over the first proposal, both verified necessary:**
1. **Rest handlers on the wrapper `<div>`, not `<AreaChart>`** — `onPointerUp` /
   `onPointerLeave` (pointer events unify mouse+touch and bubble reliably to a
   plain div) instead of `onMouseLeave` / `onTouchEnd` on the SVG, which the
   reviewer warned can fail to bubble on mobile (the maintainer's case).
2. **Debounce the orientation key-bump ~300ms** — remounting *during* the
   ResponsiveContainer re-measure made `displayDefaultTooltip` land on index 0
   (verified: landscape parked at the FIRST point "May 28, 2025" instead of the
   latest). Debouncing so the remount lands after the width settles fixed it.

**Verification** (local, Playwright DOM on NVDA dark mobile 390×844): `tsc
--noEmit` clean · `next build` green (506 routes) · `ruff` clean. Tooltip label
across states — on-load **May 28, 2026** (latest) · during-drag updates per
hover (Aug 29 2025 / Dec 3 2025 / Mar 11 2026 — inspection still works) ·
after-pointerup **May 28, 2026** · after-pointer-leave **May 28, 2026** ·
landscape (debounced) **May 28, 2026** · back-to-portrait (debounced) **May 28,
2026** · after 6M→1Y **May 28, 2026**. Inline `transition` = none in every state
(lag gone). Cursor line + box + active dot all park at latest (screenshots
portrait + landscape). No schema / compute / scoring / valuation change.

**Bonus found, NOT bundled** (separate follow-up if wanted): `expert-user-explorer`
flagged the `PriceTimePeriodSelector` shows **1M** highlighted on initial load
while the chart renders the 1Y window (state inits to `'1Y'`) — a selector
active-chip mismatch, unrelated to the crosshair ask.

**Follow-up commit — touch-drag scrub regression (same PR #322):** the maintainer
real-device-tested the preview: park-at-latest worked but **touch-drag could not
scrub the crosshair along the line**. This was a regression the park-at-latest
handlers introduced. Two agents disagreed on cause; the EMPIRICAL reproduce won
(verify-don't-trust): `frontend-design-reviewer` source-reasoned it was a missing
`touch-action` (browser stealing the horizontal drag for page scroll) and claimed
implicit pointer capture suppresses `pointerleave` during a touch drag.
`expert-user-explorer` **refuted both with measurement** — scroll-delta = 0px
during horizontal touch-drag (no page-steal), and a recorded **3× `pointerleave`
(pointerType=touch) DURING the drag** → the `onPointerLeave → setRestKey`
remount fired ~5ms after each touchmove, resetting to `defaultIndex` and wiping
the scrub. (Implicit capture didn't apply: pointerdown lands on a child SVG, so
the wrapper never captured the pointer.) **Fix:** guard `onPointerLeave` to
ignore `e.pointerType === 'touch'` (mouse-leave still re-parks; touch re-park is
handled by `onPointerUp` at finger-lift) + add `touch-action: pan-y` defensively
(canonical for a scrub chart; preserves vertical page scroll). The reproduce
agent's secondary "Recharts touch-coords don't update" doubt was a **red herring**
(its fake-event fiber test bypassed React's synthetic events) — verified post-fix
via CDP `Input.dispatchTouchEvent`: touch-drag scrubs **Dec 23 2025 → Sep 19 2025
→ Jul 15 2025** following the finger, touchEnd re-parks **May 28 2026**, mouse
drag still scrubs + re-parks, park-at-latest intact. Lesson logged: verify in the
SAME input modality the user uses (the original verification used `page.mouse`,
which masked the touch-only regression). `tsc` + `next build` (506 routes) +
`ruff` clean.

**Follow-up commit 2 — tap (not drag) didn't reset (same PR #322):** real-device
test: drag scrub + drag-release re-park now work, but a single **tap** left the
crosshair stuck at the tapped point. Reproduced via CDP: a tap fires
`pointerdown → pointerup → click`, and the tooltip is set to the tapped point by
the compatibility **synthetic-mouse + `click` that fire AFTER `pointerup`** — so
the `onPointerUp` re-park fired too early and the tap point re-applied. (A drag
moves far enough that the browser suppresses the synthetic click, so `pointerUp`
re-park wins — which is why drag worked and tap didn't, exactly matching the
report. CDP `dispatchTouchEvent` doesn't emit the compat-mouse events, so the
earlier CDP drag test never surfaced this.) **Fix:** also re-park on `onClick`
(the last event of a tap; bubbles to the wrapper AFTER Recharts sets the tap
point, so it wins — drags don't fire click, so no double work). Verified via CDP:
pure-tap @30 → re-parks **May 28 2026**, micro-tap @60 → **May 28 2026**, drag
still scrubs (Dec 3 → Aug 5 2025) + release re-parks, mouse drag scrubs + leave
re-parks. `tsc` + `next build` (506) + `ruff` clean.

**Follow-up commit 3 — right-edge alignment (same PR #322):** the chart's drawn
area aligned flush with the content on the LEFT but stopped ~16px short on the
RIGHT (the `<AreaChart margin>` was `left: 0` / `right: 16`). Set `right: 0` to
match `left`. Measured (Playwright): area path l/r now == container l/r exactly
(leftGap = rightGap = 0); the last x-axis tick "May 26" end-anchors at the edge
so it does NOT clip; the latest dot sits at the right edge (half pokes ~4px into
the page gutter — fine, standard latest-price marker). One-character diff;
`next build` (506) + `ruff` clean.

**Follow-up commit 4 — two right-edge / scroll polish items (same PR #322):**
real-device test surfaced two after-effects. (1) The `right: 0` flush made the
latest-point **dot + crosshair line clip in half** at the edge. Inspected: NOT a
Recharts clipPath (dot has no clip ancestor) — it's the `.recharts-surface` SVG's
own `overflow: hidden` (viewBox width 358; dot center sits on the svg right edge,
right half spilled past and was cut). Fix: scope `overflow: visible` to THIS
chart's surface via the Tailwind arbitrary variant
`[&_.recharts-surface]:overflow-visible` on the wrapper (other charts keep
default clipping) — keeps `margin.right:0` flush AND lets the edge dot/cursor
render fully into the harmless page gutter. (2) A touch that STARTED on the chart
then became a vertical **page scroll** (touch-action:pan-y hands it to the
browser) fires `pointercancel`, NOT pointerup/click — so the crosshair stayed
stuck at the touched point after scrolling. Fix: add `onPointerCancel` → re-park.
Verified (CDP): surface `overflow==='visible'`; full-width screenshot shows a
complete dot at the edge; touch-scrub to Sep 15 2025 (no release) then a
`pointercancel` re-parks to **May 28 2026**; regressions intact (park-on-load,
tap→latest, drag scrub + release→latest). `tsc` + `next build` (506) + `ruff`
clean.

**Follow-up commit 5 — revert overflow:visible (it caused a page horizontal
scroll); small right margin instead (same PR #322):** the `overflow:visible`
from commit 4 (added to un-clip the edge dot at the flush `right:0` edge) let
SVG content escape the surface and **widened the whole page** — measured
`innerWidth` jumped 390 → 449 under mobile emulation, i.e. ~59px of phantom
horizontal scroll ("เลื่อน crosshair แล้วปล่อย หน้าจอเลื่อนแนวนอนได้"). This is
the flush/full-dot/no-scroll **trilemma**: a full dot at a *perfectly* flush
edge must either clip (overflow:hidden) or escape (overflow:visible → page
scroll). Resolution: remove the `[&_.recharts-surface]:overflow-visible` (back
to default clip → nothing escapes → no page scroll) and give the AreaChart a
small `margin.right: 8` so the latest-point dot + crosshair sit just *inside*
the surface, fully visible. Cost: the line ends ~8px short of the content edge
(not pixel-flush) — the necessary trade to keep the dot whole AND kill the page
scroll. `onPointerCancel` (from commit 4) is unrelated and stays. Verified
(clean viewport, no isMobile): `innerWidth==390 == docScrollWidth` (**hOverflow
= 0**, nothing past the viewport), dot fully inside (dotRight 370 <
containerRight 374), behaviours intact (park-on-load / drag-scrub + release /
tap / scrub+pointercancel all → latest). `tsc` + `next build` (506) + `ruff`
clean.

**Follow-up commit 6 — REAL root cause of "page widens right after scrub"
(same PR #322; commits 4-5 fixed the wrong spot).** The maintainer pushed back
that the dot/margin work was the wrong target — the actual symptom is the PAGE
expanding rightward after scrubbing. Found it with mobile-emulation measurement
(the no-isMobile clean viewport had hidden it — lesson: this class of layout-
viewport bug only shows under real mobile emulation): BEFORE/DURING scrub
`innerWidth==390`; AFTER release `innerWidth` jumps to **441** and the sole
element past the device width is the **`fixed inset-0` mobile sidebar backdrop**
(`Sidebar.tsx`, always-mounted for its fade) at width 441. Mechanism: the
crosshair re-park **remounts `<AreaChart>`** (the `key` bump) → a transient
horizontal overflow during the ResponsiveContainer re-measure → the mobile
layout viewport grows → the `fixed inset-0` backdrop sizes itself to the widened
ICB and, being fixed + full-width, **sustains** it = phantom right-side scroll
space. **Fix (document level):** `html, body { overflow-x: clip }` in
globals.css — `clip` (NOT `hidden`) clips the transient overflow so the layout
viewport never grows, and crucially does NOT create a scroll container so it
does NOT break the `position: sticky` sidebar + header. With the document clip
in place the dot/margin tug-of-war dissolves: reverted to `margin.right: 0`
(line truly flush) + restored `[&_.recharts-surface]:overflow-visible` (full
edge dot) — both now safe because the document clip contains any escape. The
margin:8 / overflow:hidden compromise from commit 5 is superseded. Verified
(isMobile emulation, the test that exposed the bug): before / after scrub+release
/ after tap all → `innerWidth == scrollWidth == 390`, **zero offenders** (no 441
backdrop); `areaRight == containerRight` (flush); dot full (`dotRight 378` via
overflow:visible, contained by the doc clip); sticky header `top==0` after a
600px scroll (sticky NOT broken); park / scrub / tap / pointercancel all
re-park. `tsc` + `next build` (506) + `ruff` clean.

---

## Document the global `overflow-x: clip` invariant (§Gotcha) (in flight, this PR · 2026-05-29)

Fast-follow to PR #322 (merged `fd045277`), recommended by BOTH the
`quantrank-reviewer` (opus) and `phase-coordinator` at the #322 merge gate: the
`html, body { overflow-x: clip }` added in #322 is a non-obvious **site-wide**
invariant a future frontend author will trip over, so it gets a durable home in
CLAUDE.md §Gotchas (+ AGENTS.md §Code-style mirror) rather than living only in
the globals.css comment + the (drains-over-time) INFLIGHT entry. The §Gotcha
records: keep `clip` NOT `hidden` (hidden creates a scroll container → breaks
the sticky sidebar/header; clip does not); page-level horizontal scroll is
intentionally impossible → wide content nests its own `overflow-x-auto`
(`RankingTable` pattern); the chart-remount + fixed-backdrop root cause; and the
Safari-16+/Chrome-90+ support floor (older silently degrades to prior behavior,
not a regression). Doc-only — no compute / schema / scoring / valuation /
frontend-code change; lockstep satisfied by the CLAUDE.md + AGENTS.md substance
diff. `ruff` clean.

---

## Price-chart fair/target reference-line + chip restyle (in flight, this PR · 2026-05-29)

User-requested polish on the per-stock price chart (`PriceHistoryChart.tsx`) —
four coupled tweaks to the fair-value + target reference lines and the chip row:
1. **Target line same stroke-width as the fair-value line** — both now
   `strokeWidth={1.5}` (were both implicit default 1; the user perceived a
   mismatch, reinforced by the legend swatches sitting at 1px-vs-2px).
2. **Fair-value line the same "white" as the target line** — fair `stroke`
   flips from the always-gray `#94a3b8` to the target's theme-aware
   `isDark ? '#e2e8f0' : '#0f172a'`. Both lines read near-white in dark mode
   (the user's mode) and near-black in light mode (`#0f172a` on `#FAFAFA`
   ≈ 19:1 contrast — deliberately NOT literally white, which would vanish on
   the light page bg). The two lines stay distinguishable by dash only (fair
   `5 3` dashed, target solid).
3. **In-chart text labels removed** — dropped the `label={{...}}` prop from both
   `<ReferenceLine>`s (no more "Fair $X" / "Target $X" stuck on the lines).
4. **Fair/target chips below the price headline now always shown** — the render
   condition flips from `fairOffChart`/`targetOffChart` (off-y-domain only) to
   `fairIsNumber`/`targetEligible` (always when the value exists); the chips are
   now the canonical number read. Removed the now-unused
   `fairOffChart`/`targetOffChart` consts; legend swatches updated to match the
   new line look (both near-black/white, fair `border-t-2` dashed, target solid,
   equal weight, `dark:*-slate-200` matching the line's `#e2e8f0`); chip price
   spans gained `tabular-nums` (the one pre-existing `frontend-design-reviewer`
   WARN, fixed in-block since the chips are now always visible). Each chip value
   is followed by the **signed % distance from the current price** — upside (+) /
   downside (−), e.g. `Fair $126 (-14.7%)` — with the sign matching the chip's
   green/red direction cue.

Frontend-only; no schema / compute / scoring / valuation change. Verified:
`frontend-design-reviewer` zero-FAIL (`READY-FOR-SPOT-CHECK`); DOM inspection +
3 dark-mode mobile (414×896, `isMobile`) Playwright screenshots (APH
both-in-range, AAPL both-off-chart chip-only, AMD well-separated) confirm both
`<line>`s render stroke `#e2e8f0` / width `1.5` / fair dashed / target solid /
no label, and the chips show "Fair $X" + "Target $X" in all three cases. `ruff`
+ `tsc` + `next build` (506 routes) clean.

Follow-up tweaks on the same PR (user requests): (a) each chip gained a **signed
`%` delta** from the current price after the dollar value (`Fair $125.92
(-14.7%)` / `Target $169.82 (+15.0%)`; + = upside / − = downside, sign matching
the green/red chip cue; one decimal; suppressed when current price is missing or
≤ 0). (b) the current price's **as-of date** now renders below the change
indicator (`as of May 28, 2026`) via the existing `formatTooltipLabel` helper —
the date stays constant across period switches (it's always the latest close's
date, matching the headline price + the latest-point tooltip). Both verified on
the regenerated APH/AAPL dark-mode screenshots; `tsc` + `next build` (506) clean.

---

## Price-chart: tap (no drag) moves the crosshair to the tap point (in flight, this PR · 2026-05-29)

User request: "เวลา tab ที่จุดไหนในกราฟ crosshair ต้องมาอยู่ตรงที่ tab เสมอ แม้จะไม่
ลากก็ตาม และเวลาปล่อย tab ต้องกลับไปอยู่ที่เดิม" — a tap anywhere on the chart
must move the crosshair to the tap point even WITHOUT a drag, and releasing must
snap it back to the latest date.

**Root cause (empirically reproduced via CDP touch):** Recharts 2.15
`handleTouchStart` only calls `handleMouseDown` (which never touches the
tooltip); only `handleTouchMove` updates the crosshair. So a tap-without-move
left the crosshair parked at latest the entire press
(`generateCategoricalChart.js:1061-1063`). Reset-on-release already worked (the
#322 remount-on-`onPointerUp`/`onClick`/`onPointerCancel`).

**Fix:** a touch-only `onPointerDown` on the chart wrapper dispatches a synthetic
`mousemove` at the touch point from INSIDE `.recharts-wrapper` (so it bubbles
through Recharts' `onMouseMove` → `getMouseInfo`). Two non-obvious details: (1)
`getMouseInfo` reads **`pageX`** (`:1693`), not `clientX`; (2) `pageX`/`pageY`
are NOT part of `MouseEventInit`, so a constructed `MouseEvent` leaves them at 0
→ negative chartX → Recharts CLEARS the tooltip (observed: dot vanished). Fixed
by `Object.defineProperty(ev, 'pageX'/'pageY', …)` to the pointer's page coords.
Mouse pointers already hover-track, so the handler early-returns for non-touch.

**Verified (CDP touch, mobile 414×896):** tap@30% → crosshair jumps to that date
(Sep 16 2025, dot cx 115.7) and HOLDS during the press; release → reset to latest
(May 28 2026, cx 382). No regression: drag-scrub still follows (Mar 17 2026 @
~80%), tap-then-vertical-scroll still resets via the pointercancel path. Held-tap
screenshot (Oct 13 2025 · $123.43 with crosshair + dot + tooltip at the tap)
captured. Component-local mechanism documented in-file; lockstep via this entry.
Frontend-only; no schema/compute/scoring/valuation change. `ruff` + `tsc` +
`next build` (506 routes) clean.

---

## Fluid root font-size — app-wide responsive scaling (in flight, this PR · 2026-05-29)

User request: "ตำแหน่งการจัดวางดูผิดเพี้ยน...เพราะขนาด...ตัวหนังสือและสิ่งอื่นไม่
เปลี่ยนตามขนาด[หน้าจอ]" — the layout looks off at larger screens because text +
elements don't scale with the viewport. **Empirically confirmed** (Playwright
measure across 414/600/768/834/1024/1280): root font-size was a flat **16px at
EVERY width**, price a flat 24px — phone-tuned sizes sat unchanged on a 1280px
desktop, leaving text tiny + the hero content drifting apart in the wide canvas.

**Fix (one rule, app-wide):** `frontend/app/globals.css`
`html { font-size: clamp(1rem, 0.89rem + 0.45vw, 1.25rem) }`. The app is
rem-based (Tailwind `text-*` / spacing / gaps / chart `h-64` all rem), so a
fluid ROOT font-size scales every text + layout dimension proportionally —
~16px phone (clamp floor, mobile unchanged) → ~20px desktop (ceiling) — with
ZERO per-component edits, preserving every proportion + the LedgerCraft system
+ tabular-nums. The `rem` terms (not pure `vw`) keep browser zoom / user
font-size prefs working (pure-vw breaks WCAG 1.4.4). Documented as a CLAUDE.md
§Gotcha + AGENTS.md §Code-style mirror (the fluid root is a remember-this
site-wide invariant: use rem text utilities, no second `font-size` on
html/body).

**Verified (Playwright, dark mode):** post-fix root scales 16.1 → 17.7 → 18.8
→ 20px across 414 → 768 → 1024 → 1280; price 24 → 30px. Screenshots: detail page
(414 unchanged / 768 squeeze-zone clean, hero stacks correctly / 1280 fills
proportionally) + home ranking table (414 + 1280, NO horizontal overflow,
`scrollW == docW` at both, table reads comfortably). Frontend-only; no
schema/compute/scoring/valuation change. `ruff` + `next build` (506 routes)
clean.

**Follow-up — micro-label px→rem conversion (same PR, post `frontend-design-reviewer`
PASS):** the reviewer's audit found ~44 arbitrary `text-[10px]`/`text-[11px]`
classes across 14 components (chip/badge labels, table column headers, chart
legend, the `FairPriceBarChart` headline delta % — the one PRIMARY numeric)
that, as fixed px, would NOT follow the fluid root and would drift smaller-
relative on desktop. To honor "ทั้งหมด" (everything scales) they were converted
to rem equivalents — `text-[10px]→text-[0.625rem]`, `text-[11px]→text-[0.6875rem]`
— pixel-IDENTICAL at the 16px base (zero mobile change) but now scaling with the
root on desktop (→12.5px / 13.75px at root 20px). Only the Recharts `tick
fontSize` SVG number + the StockLogo px-prop letter-avatar remain px (both
self-contained coordinate systems, intentional). Reviewer verdict overall:
PASS on all five correctness axes (WCAG 1.4.4 sound · no compounding font-size
on html/body · layout safe · design-token family intact). `tsc` + `next build`
(506) clean; 1280 detail-page screenshot confirms converted labels render
correctly + scaled.

**Follow-up 2 — cross-platform layout-density audit fixes (same PR):** user asked
to verify "ทุก platform" + audit that the UX/UI is well-arranged with balanced
whitespace (not too sparse / not too cramped). Ran TWO parallel read-only audits
— `expert-user-explorer` (empirical: live browser render across 10 widths
360→1920 × home + detail × dark/light) + `frontend-design-reviewer` (code-level
responsive-pattern review). Both PASSED the scaling itself (WCAG, no overflow at
any width, mobile/phablet excellent) and CONVERGED on the same layout-density
imbalances (all side-effects of rem growing 16→20px on desktop). Fixed in this
PR:
- **Detail hero broke at exactly 1024px** (`app/stock/[ticker]/page.tsx`): the
  2-col `lg:flex-row` fired when the sidebar left only ~666px content → left
  block crushed to ~156px. Raised the split to `xl:` (1280, ~1040px content →
  balanced) so 1024 STACKS cleanly; capped the left col `xl:max-w-2xl` so it
  doesn't spread 1000px+ on ultrawide; dropped the no-op `lg:justify-between`
  (the `flex-1` left child already ate the free space — confirmed by the
  reviewer). Verified: hero=column@1024, row@1280/1920.
- **Content `max-w-6xl` (72rem) expanded to 1440px** at the 20px root
  (`AppShell.tsx`) → sparse table/cards on 1920px. Pinned to fixed
  `max-w-[1152px]` (both main + footer) so the cap is viewport-stable while
  inner rem spacing/text still scales. Verified: content=1152px@1920 (was 1440).
- **Sidebar inflated 240→300px** at desktop (`Sidebar.tsx`): capped
  `md:max-w-[240px]` / collapsed `md:max-w-[64px]`. Verified: sidebar=240@1024/
  1280/1920 (was 300); content gains ~60px.
- **Mobile card `min-h-[112px]`** fixed-px (`RankingTable.tsx`) → `min-h-[7rem]`
  (scales). **Search wrapper** `style={{minWidth:'200px'}}` inline-px → class
  `min-w-[12.5rem]`. **Home header + detail disclaimer** gained `max-w-3xl` for
  prose line-length on ultrawide.
- **DEFERRED (flagged to user, judgment calls):** (a) the audit recommended
  lowering the fluid ceiling 1.25rem→1.125rem (20→18px) for finer data-density,
  but the user had just asked for LARGER text twice — KEPT 20px, offered the
  knob; (b) home desktop table partially clips the Sector column at 768–834px
  (7 cols in ~500px content) — a tablet-breakpoint decision (push table md→lg,
  or column-priority hide) deferred to a focused follow-up.
`tsc` + `next build` (506) clean; verified via Playwright measure (sidebar/
content/hero-direction across 1024/1280/1920/414, zero overflow) + before/after
screenshots (detail@1024 stacked, home@1920 capped 1152).

**Follow-up 3 — collapsed-sidebar Q/chevron overlap (same PR, user-reported on
real device):** on a landscape-phone / tablet (md+) with the sidebar COLLAPSED,
the green Q logo box (28px) and the expand-chevron toggle (32px) **overlapped**
in the 64px rail header (px-3 leaves only ~40px content; 28+32 don't fit).
Reproduced via Playwright (collapsed @900px: Q 14–46px, chevron 35–49px →
overlap=true). Pre-existing tightness, surfaced now. Fix (`Sidebar.tsx`): when
collapsed at md+, the Q home-link is `md:hidden` and the chevron centers
(`md:mx-auto`) as the sole header control — the Q returns the instant the rail
expands. Expanded + mobile-drawer states unchanged (Q + wordmark + chevron/close-X
all show with room). Verified: collapsed @900 overlap=false (link hidden,
chevron centered 14–49); expanded @900 Q 14–46 / chevron 189–225 (no overlap);
before/after screenshots confirm. `tsc` + `next build` (506) clean.

**Follow-up 4 — adopt the two deferred audit recommendations (user authorized
"ตามที่แนะนำ"):** (1) **Fluid ceiling 20px→18px** (`globals.css` clamp
`1.25rem → 1.125rem`) for tighter desktop data-density (audit MAJOR-3). Now caps
at ~835px so tablet+ is a flat 18px (H1 27px not 37.5px, table cells ~15.75px);
mobile 360–390 still 16px floor. §Gotcha + AGENTS.md mirror updated to match.
(2) **Ranking table↔card breakpoint `md`→`lg`** (`RankingTable.tsx`): portrait
tablets (768–1023px, ~530px content beside the sidebar) now use the mobile CARD
list instead of the 7-col table that clipped the Sector column (audit MINOR-4);
the table returns at lg (1024, ~784px content). Verified (Playwright): root
16.1→17.7→18.0px capping at 834px; view = cards @414/768/834, TABLE @1024/1280/
1920; zero overflow at all widths; screenshots confirm 768 cards clean + 1280
table dense-but-scannable. `tsc` + `next build` (506) clean.

**Follow-up 5 — keep the Q logo visible in the collapsed rail (user request,
revises Follow-up 3):** Follow-up 3 fixed the Q/chevron overlap by HIDING the Q
when collapsed (centered chevron only). User wanted the green Q to stay visible.
New approach (`Sidebar.tsx`): when collapsed at md+ the header switches to a
**vertical stack** (`md:flex-col md:h-auto md:justify-center md:gap-1.5 md:py-3`)
— the green Q logo on top (still a home link; "QuantRank" wordmark stays hidden)
+ the expand-chevron centered below. No overlap (they're stacked, not
side-by-side). Verified (Playwright, collapsed @900): qVisible=true, Q y14–45 /
chevron y52–88 (chevron below Q), overlap2D=false, both centered in the 64px
rail; expanded unchanged (header 63px, Q left / chevron right). Collapsed header
grows to ~102px (Q + chevron + py-3) vs 63px expanded — acceptable mode
difference. `tsc` + `next build` (506) clean; screenshot confirms.

**Follow-up 6 — collapsed Q + chevron side-by-side in ONE ROW (user
clarification, supersedes Follow-up 5):** user wanted them in the same row (not
stacked). A 64px rail can't fit both (the original overlap), so the collapsed
rail widens to a FIXED **96px** (`md:w-[96px]`, was `md:w-16`) and the header
stays a row but centers the group (`md:justify-center md:gap-1 md:px-2`); the
chevron drops its `ml-auto` when collapsed so it sits next to the Q rather than
at the far edge. Verified (Playwright, collapsed @900): rail 96px, Q x12–43 +
chevron x48–84 (same row, 5px gap), overlap2D=false, header back to 63px (no
more tall stack); expanded unchanged. `tsc` + `next build` (506) clean;
screenshot confirms Q + › side-by-side with a gap.

**Follow-up 7 — collapsed expand-chevron as a vertical rectangle (user
request):** the chevron button was a 32px square; user wanted a portrait
rectangle. Changed to `md:h-12 md:w-6` WHEN COLLAPSED only (`Sidebar.tsx`) — so
collapsed renders a 27×54px (@18px root) taller-than-wide button beside the Q;
expanded keeps the `h-8 w-8` square. Verified (Playwright, collapsed @900):
chevron w27×h54 (vertical), Q 32×32, still one row / no overlap / 96px rail.
`tsc` + `next build` (506) clean.

**Follow-up 8 — tune collapsed rail width for a snug fit (user "ปรับ px ...
ให้พอดี"):** with the narrower vertical chevron (27px vs the old 32px square) the
96px rail had ~7px of excess slack each side. Narrowed to a fixed **84px**
(`md:w-[84px]`) = 32px Q + gap + 27px chevron + px-2 (≈81px content). Verified
@900: rail 84px, Q x10–42 / chevron x46–73 (group fills the content area with
~1–2px slack beyond px-2), no overlap. `tsc` + `next build` (506) clean.

**Follow-up 9 — chevron height = logo height (user "ใช้ความสูงเท่ากับ logo"):**
the `md:h-12` (48px) collapsed chevron stood taller than the Q and stuck out
above/below it. Changed to `md:h-7 md:w-6` — height now matches the Q (`h-7`,
both 32px @18root, tops/bottoms flush) while staying narrower (`w-6`, 27px) so it
still reads as a slim portrait rectangle. Verified @900: Q 32×32 / chevron 27×32,
both y15–47 (aligned), no overlap. `tsc` + `next build` (506) clean.

**Follow-up 10 — revert collapsed header to the VERTICAL STACK (user "ปรับกลับ
เป็นโลโก้อยู่ข้างบน ลูกศรอยู่ข้างล่างเหมือนเดิม"):** after iterating the side-by-side
row (FU6–FU9), the user chose the earlier stack arrangement. Reverted
(`Sidebar.tsx`): collapsed header back to `md:h-auto md:flex-col md:justify-center
md:gap-1.5 md:py-3` (Q logo on TOP, square `h-8 w-8` expand-chevron centered
BELOW), rail narrowed back to a fixed **64px** (`md:w-16 md:max-w-[64px]`).
Verified @900: rail 64px, Q y14–45 (top) / chevron y52–88 (below), centered,
overlap2D=false, header ~102px (tall stack); expanded + mobile drawer unchanged.
`tsc` + `next build` (506) clean.

**Follow-up 11 — fix recurring flaky CI (shallow-clone test guard):** the
"Python (lint + test)" check failed intermittently across this PR's pushes (cold
runner → FAIL, warm-workspace runner → PASS). `ci-triage-engineer` root-caused
it (NOT this PR's code — all commits are frontend/docs): `test_validation/
test_ranking_history.py::test_list_ranking_commits_returns_real_commits` runs
`git log -- frontend/public/data/rankings.json` then `assert len(commits) >= 1`;
on CI's shallow clone (`actions/checkout@v6` → `fetch-depth: 1`) where the tip
commit doesn't touch `rankings.json`, `git log` returns empty → the assert
fails. Same bug PR #284 (`a820caee`) fixed in a sibling test but this one was
missed. Fix: add a `pytest.skip()` guard when `commits` is empty (shallow clone),
matching the #284 precedent — a full clone still exercises the real assertion.
Verified: `pytest tests/test_validation/test_ranking_history.py` 18 passed
(full clone) / would skip 1 on a shallow clone; `ruff` clean. First + only Python
touch on this PR; test-hygiene only, no compute/schema surface, no new §Gotcha
needed (pattern documented in #284).

**Follow-up 12 — collapsed expand-chevron as a full-width box matching the
nav items (user "ปรับขนาดลูกศรให้เป็นสี่เหลี่ยมผืนผ้าเหมือนข้างล่าง"):** the
collapsed chevron was a 32px square; the user wanted it sized + shaped like the
nav-item boxes below it (`SidebarLink` collapsed = `rounded-sm px-0 py-1.5`
full-width). Changed (`Sidebar.tsx`): collapsed header gains `md:px-2` (matches
the nav's `px-2`), chevron becomes `md:h-auto md:w-full md:py-1.5` + a subtle
fill (`md:bg-slate-100 md:dark:bg-slate-800`) so it renders as a full-width
rounded rectangle. Verified @900: chevron 45×28 / nav-item 45×30 — same width +
x-position (x9), same fill, rounded-sm; screenshot confirms the chevron box now
matches the nav-item box. `tsc` + `next build` (506) clean.

---

## Stability bug-fix bundle — sidebar refresh/rotate flash + chart crosshair re-park + 2 flaky-test guards (in flight, 2026-05-30)

Three stability fixes on `claude/optimistic-brown-UUcXA`, all post-#325. Two
are the user-reported sidebar/chart bugs; two are flaky-test hardening
("เก็บ flaky ให้ครบ"). Frontend + test-only — zero schema / compute / scoring /
valuation / output-JSON change.

**Bug A — "sidebar opens then shrinks back by itself" on refresh OR
portrait↔landscape rotation.** Two root causes, two-part fix:
- The static export bakes the EXPANDED rail into every page's HTML, so on
  refresh the rail painted wide, then `AppShell`'s mount effect read
  `localStorage['quantrank.sidebar.collapsed']` and collapsed it — a visible
  width shrink. Fix: a pre-paint inline `<script>` in `layout.tsx` adds
  `.sidebar-collapsed` to `<html>` BEFORE the body paints (mirrors next-themes'
  dark-mode pre-paint), and a new `globals.css` rule
  (`@media (min-width:768px) html.sidebar-collapsed aside[data-sidebar-rail]`)
  renders the rail at its collapsed 4rem width immediately → React's
  post-hydration collapse is a no-op. `AppShell` keeps the class in lockstep
  with the live state (removed on expand) so the rule never fights React.
- The aside carried a permanent `width 200ms` transition, so the
  hydration-collapse AND the breakpoint cross on rotation both ANIMATED the
  shrink. Fix: a new `animate` flag (owned by `AppShell`, passed to `Sidebar`)
  is true only for ~250ms around an EXPLICIT user toggle (collapse chevron /
  mobile hamburger / backdrop); at rest the aside is `transition-none`, so
  refresh + rotation + resize switch width/position INSTANTLY (no shrink
  motion). Explicit toggles still animate smoothly.

**Bug B — chart crosshair jumps to the far LEFT when the sidebar is
expanded/collapsed.** Toggling the rail reflows the main-content width →
`ResponsiveContainer` re-measures the chart, but Recharts applies `defaultIndex`
(latest-point park) only on MOUNT, so the crosshair drifted to a stale/left x.
Fix (`PriceHistoryChart.tsx`): replaced the orientation-only `matchMedia`
re-park with a width-delta `ResizeObserver` on the chart wrapper that
debounce-bumps the remount key (`layoutKey`) ~300ms after any width change
settles → `<AreaChart>` remounts → re-parks at the latest point AFTER the
re-measure. Subsumes the old orientation listener (rotation changes width too)
and now also catches sidebar toggle + window resize. A width-only delta gate
(`<1px → ignore`) prevents height-only / crosshair-render churn from triggering
spurious remounts. Empirically: cursor x-ratio before=1.0, transient@120ms=0.0
(the bug), after-repark=1.0 (fixed).

**Flaky-test hardening (เก็บ flaky ให้ครบ):**
- `test_ranking_history.py::test_load_ranking_history_smoke_recent_window` —
  added an explicit `if df.empty: pytest.skip(...)` guard (mirrors the
  `list_ranking_commits` guard from #325 + PR #284). On a shallow CI clone
  (`actions/checkout` fetch-depth=1) `rankings.json` history may be unreachable
  → empty frame; the populated-MultiIndex-shape assertions need a full clone.
  The test previously passed-on-empty only by coincidence of the empty-return
  path's `.set_index(...)`; the guard makes the shallow-safety explicit +
  edit-proof (proven via a real depth-1 clone: 46/46 git-dependent tests pass).
- `test_osap.py::test_package_imports_and_exposes_openap_class` — was a
  default-lane (non-`@network`) test that instantiated
  `openassetpricing.OpenAP()`, whose 0.0.2 constructor does a LIVE Google-Drive
  metadata fetch → flaky whenever Drive rate-limits (returns a "Quota exceeded"
  HTML page; polars then raises `ColumnNotFoundError` on the missing "Acronym"
  column — hit live in this session's pre-push gate). Fix: check the API surface
  on the OpenAP CLASS (`hasattr(openassetpricing.OpenAP, method)`) instead of an
  instance — the 4 methods are class-level defs, so the scout signal (import
  resolves + class exposed + methods present) stays in the default offline lane
  with ZERO network dependency. The live instantiation+fetch path remains
  covered by the `@network test_fetch_osap_returns_live` in the same file.

**Files** (7): `frontend/app/layout.tsx` (pre-paint script) ·
`frontend/app/globals.css` (pre-hydration width rule) ·
`frontend/components/AppShell.tsx` (`animate` flag + class sync) ·
`frontend/components/Sidebar.tsx` (`animate` prop + `data-sidebar-rail` +
gated transition) · `frontend/components/PriceHistoryChart.tsx` (ResizeObserver
re-park) · `tests/test_validation/test_ranking_history.py` +
`tests/test_ingest/test_osap.py` (flaky guards).

**Verification**: `ruff check .` clean · `pytest -m "not network"` → 1407
passed (was 1406 + 1 OSAP-flake; now deterministic) · `tsc --noEmit` clean on
edited files · `next build` → 506 routes · Playwright empirical: A.1 no-flash
(rail 72px across 62 frames, never wide) / A.2 transition gated (rest→none,
toggle→width, settle→none) / A.3 rotation instant (transition none, rail 72px) /
B crosshair re-park (ratio before=1 / transient=0 / after=1) — all PASS.

PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with every PR"
lockstep per PR #237 convention. No CLAUDE.md / AGENTS.md substance change
required — the fixes don't introduce a new invariant future authors must
remember beyond what the existing §Gotchas (`overflow-x: clip`, fluid root
font-size, chart remount-key) already frame.

---

## Docs housekeeping — CLAUDE.md §Phase status drain + A-L label fix + 2 PR #326 §Gotchas (in flight, 2026-05-30)

Doc-only housekeeping on `claude/docs-housekeep-phase-status` (off `main`
`b82b845c`). Surfaced by a full `docs-reviewer` substance pass on CLAUDE.md
(5 MUST-FIX + 4 SHOULD-FIX). Fixes all 9 in one focused diff — CLAUDE.md only,
no code / schema / compute / frontend change.

**MUST-FIX (factual / contradiction):**
1. §Phase status "In flight" block marked PR #312 (tasteful-motion) as "THIS PR
   / not yet merged" — it merged as `e602485`. Replaced with "No current
   in-flight PR on this branch" + pointer to this side-file.
2. §Phase status "Recently merged (PR #303 → PR #310)" was 16 PRs stale.
   Refreshed header to "PR #303 → PR #326, 2026-05-29 → 2026-05-30" and
   inserted the 16 missing entries (#311–#326) newest-first with SHAs.
3. §Phase status "Next deliverables" listed "Issue #67 flip PR" as pending —
   `USE_SECTOR_COE = True` already flipped via PR #294 (`config.py` confirms).
   Replaced with "Issue #67 — DONE (PR #294)".
4. §Commands + §"After every workflow_dispatch green" said "Section A-H" — the
   verify-production-output helper is Section A-L (PR #221 extended A-J → A-L).
   Fixed both labels.
5. §Cue table defense-layer-auditor row said "Section A-J" → A-L. (The
   edgar-debugger HISTORICAL narrative at the old ~line 829 keeps its
   self-contained "A=…/…/J=annotate inventory" legend — a point-in-time
   4.5-era record, preserved per the doc's historical-narrative convention.)

**SHOULD-FIX (staleness):**
6. §Stack "Phase 3b on this PR" → "Phase 3b (merged)" (no dangling "this PR").
7. §Gotchas `compute/main.py` line refs re-anchored to the current file
   (840→879 · 1965-1966→2084-2085 · 717→728 · 785→805 · 972→1025).
8. §Gotchas gained 2 new entries for the PR #326 invariants (below).
9. §Stack edgartools `5.31` → `5.32` (installed version).

**The 2 new §Gotchas (item 8)** codify PR #326 invariants previously only in
this side-file: (a) Sidebar `data-rail` attrs ↔ `globals.css`
`html.sidebar-collapsed [data-rail=…]` pre-paint rules move in lockstep (drift
→ refresh text-flash returns); (b) the price-chart crosshair re-park MUST
debounce the `<AreaChart>` remount ≥ ~300ms so it lands after
`ResponsiveContainer` re-measures (immediate remount → crosshair parks at
index 0 / far-left).

**Confirmed no drift:** schema `0.10.11-phase4.6` (config.py) · skills 46 ·
agents 19 · hooks 3 · defense-layer 33 declared — all §Layout counts accurate.

**Verification:** Markdown-only; no ruff / pytest / build surface. Edits
verified via sentinel grep (all 6 old strings → 0 occurrences; all 5 new
strings → 1). `docs-reviewer` re-check spawned at the push gate.

PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with every PR"
lockstep per PR #237 convention. AGENTS.md substance mirror of the 2 frontend
gotchas deferred — they live in CLAUDE.md §Gotchas (the canonical home);
AGENTS.md is the cross-tool surface and carries no §Gotchas mirror today.

---

## PR #330 — feat(frontend): app-wide ease-in-out motion curve (in flight, 2026-05-30)

Per user direction "เปลี่ยนไปใช้ animation ขยับแบบ ease in and out ทั้ง app" —
unify every discrete move / entrance / slide / sweep animation in the app onto
a single `ease-in-out` timing curve (accelerate out of the start, decelerate
into the end — one calm, symmetric feel). Replaces the prior mix of `ease-out`,
ease-out `cubic-bezier(0.22,1,0.36,1)`, back-out `cubic-bezier(0.34,1.56,0.64,1)`,
and `easeOutCubic`.

**Touched (6 files, timing-function-only diff)**:

- `tailwind.config.ts` `animation` block — `fade-in` / `rise-in` / `chip-pop` /
  `flag-pulse` timing → `ease-in-out`. `shimmer` DELIBERATELY kept
  `linear infinite` (ease-in-out on a seamless background-position loop stutters
  at the wrap boundary — slow-end meets slow-start = a visible stall).
- `app/globals.css` — `.gauge-sweep` (was ease-out `cubic-bezier(0.22,1,0.36,1)`)
  + `.hover-lift` (was `ease-out`) → `ease-in-out`; 2 stale comments corrected.
- `components/FilterDrawer.tsx` — slide-over `duration-300 ease-out` →
  `ease-in-out`.
- `components/Sidebar.tsx` — collapse/expand
  `[transition:transform_200ms_ease-out,width_200ms_ease-out]` → `ease-in-out`.
- `components/PriceHistoryChart.tsx` — intro-sweep rAF `easeOutCubic` →
  `easeInOutCubic`. **NOTE**: supersedes the prior-session "เร็วไปช้า"
  (fast→slow) ask for this specific sweep — the new "ทั้ง app" directive makes
  it match the rest, so the left→right reveal now starts gently. One-line
  revert (`easeInOut` → `easeOut`) if the user prefers the chart keep fast→slow.
- `lib/useMotion.ts` — `useCountUp` rAF `easeOutCubic` → `easeInOutCubic`
  (pairs with the gauge-sweep arc, which the comment already cross-references).

`chip-pop`'s overshoot + `flag-pulse`'s settle still read (the overshoot lives
in the keyframe %-stops — 70% → 1.04 / 55% → 1.012 — not the timing curve, so
ease-in-out just eases INTO them). Reduced-motion guard untouched — every
animation still snaps to its end state under `prefers-reduced-motion: reduce`.
Bare Tailwind `transition-*` (no explicit ease) already defaults to
`cubic-bezier(0.4,0,0.2,1)` ≈ ease-in-out, left as-is.

**Verification**: `next build` → 502 routes; `tsc --noEmit` clean on edited
files; compiled CSS confirms `ease-in-out` on every `animation:` /
`transition:` rule (`chip-pop`/`rise-in`/`flag-pulse`/`gauge-sweep .8s`/
`hover-lift .16s`/Sidebar `.2s,width .2s`) + `linear` preserved on `shimmer`;
`node frontend/components/downsample.test.mjs` → 14/14; `ruff check .` clean
(no Python touched). `frontend-design-reviewer` (sonnet) spawned at the push gate.

Companion CLAUDE.md §Gotchas entry ("App-wide motion uses ONE `ease-in-out`
timing curve") documents the convention for future components — a new animated
component must use ease-in-out, not a one-off `ease-out`. No schema / Python /
scoring / valuation / output JSON change — frontend timing-function-only.

**Follow-up commit (same PR) — desktop sidebar collapse smoothness**: the
ease-in-out swap alone did NOT make the desktop sidebar collapse/expand feel
smooth (user 2026-05-30 "แถบด้านข้าง animation เลื่อนเข้าออกยังดูไม่ smooth").
Root cause was NOT the easing — the aside's `[transition:…]` listed `transform`
+ `width` but NOT `max-width`, while the collapsed state toggles `md:max-w-[64px]`
(and the `globals.css` pre-paint rule sets `max-width:4rem`). On collapse the
un-transitioned `max-width` snapped to the 64px cap the instant `collapsed`
flipped → clamped the rendered width to 64px → the `width` animation was
nullified → collapse "snapped" while expand (a growing max-width never clamps)
looked smooth = asymmetric jank. Fix: add `max-width_200ms_ease-in-out` to the
`Sidebar.tsx` transition list so width + max-width animate in lockstep. Verified
via Playwright frame-sampling at 1280px viewport: collapse now interpolates
240→72px across **13 distinct steps** `[240, 238, 231, 218, 201, 180, 156, 132,
111, 94, 81, 74, 72]` (was a 1-2 frame snap), expand 72→240px across **10 steps**.
`max-width` kept (NOT removed) — it's load-bearing: it caps the fluid-rem
`md:w-60` (~270px at the font-size ceiling) to a stable 240px. Companion note
appended to the CLAUDE.md §Gotchas sidebar-`data-rail` entry. `next build` → 502
routes; compiled CSS confirms `transition:transform .2s,width .2s,max-width .2s
ease-in-out`.

**Follow-up commit (same PR) — remove the risk-flags card entrance animation**:
user 2026-05-31 "ช่อง risk flag เอา animation ออก". `RiskFlagsCard.tsx` dropped
the `animate-flag-pulse stagger-*` veto-row entrance beat (+ the now-unused
`usePlayOnMount` hook / import / `i` index). The veto rows render STATICALLY; the
card's rose ring + tone already carry the "look here" weight without motion. The
`flag-pulse` keyframe + Tailwind `animation` entry are RETAINED as defined
tasteful-motion vocabulary (PR #312 / `docs/design.md` §Motion /
`web-animation-design` skill all still cite it) — RiskFlagsCard was its only
runtime consumer, so the `.animate-flag-pulse{…}` UTILITY is no longer emitted
(verified: 0 occurrences in compiled CSS) while the keyframe stays available for
reuse. The explanatory comment writes the token WITHOUT the `animate-` prefix on
purpose — else Tailwind's content scanner re-emits the unused utility from the
comment itself. Verified via Playwright on `/stock/AEP` (1 veto = altman_distress):
card renders, row className is exactly `flex items-start gap-2 rounded-sm`,
`anyAnimated:false`, no new console errors. `next build` → 502 routes; `tsc` clean.

**Follow-up commit (same PR) — price chart: drop the headline period label + move
the 1D–5Y selector below the date axis**: user 2026-05-31 "ตรงหัวข้อ price เอา (1Y)
ออก และย้าย 1D-5Y ลงมาไว้ใต้เส้นแนวนอนวันที่ด้านล่างกราฟ". (1) Removed the
`PERIOD_LABEL[period]` span ("past year" / "year-to-date" / …) from the price-change
row in `PriceHistoryChart.tsx`, plus the now-unused `scrubbing` local + the
module-level `PERIOD_LABEL` map + 2 stale comments. (2) Moved
`<PriceTimePeriodSelector>` from ABOVE the chart canvas to BELOW the chart wrapper
(under the X-axis date labels). Verified via Playwright on `/stock/AAPL` at 1280px:
`selectorTop=1019 > chartBottom=1006 > xAxisBottom=994` (selector sits below the
date axis) and the headline change row renders no period word (only the
`FairPriceBarChart` "today" copy remains, unrelated). `next build` → 502 routes;
`tsc` clean; screenshot captured.

**Correction (same PR) — the `(1Y)` the user wanted gone was the BIG SECTION
HEADING, not the change-row label**: the prior commit `a974c824` removed the
WRONG "(1Y)" — it stripped the `PERIOD_LABEL` ("past year") from the price-change
ROW, but the user meant the big `<h2>Price (1y)</h2>` SECTION HEADING in
`app/stock/[ticker]/page.tsx`. This commit (1) removes `(1y)` from that `h2` → just
"Price", and (2) RESTORES the change-row `PERIOD_LABEL` map + `scrubbing` local +
the conditional span + 2 comments that `a974c824` wrongly deleted. The
selector-below-the-chart move from `a974c824` was CORRECT and is kept. Verified via
Playwright on `/stock/AAPL`: `h2` text = "Price" (no `1y`), change row shows "past
year" again, selector still below the date axis. `next build` → 502 routes; `tsc`
clean; screenshot captured.

**Follow-up commit (same PR) — keep the period label visible WHILE scrubbing**:
user 2026-05-31 "ตอนกำลังเลื่อน crosshair แล้ว past year มันหายไป … ช่วยทำให้ past
year ไม่หายตอนกำลังเลื่อน". The change-row period label was gated by
`{!scrubbing && …}` (hidden during a scrub, restored on release). Removed the gate
so the label renders UNCONDITIONALLY, and dropped the now-unused `scrubbing` local +
updated 3 comments. Semantically safe: `headlineAt` always measures the change from
the window START (`price[i] − price[0]`), so the baseline is constant and "past
year" correctly names the window at any scrubbed point ("+X% over the past year up
to the hovered point"). `next build` → 502 routes; `tsc` clean. (Headless Playwright
couldn't trigger a real Recharts hover to exercise the scrub path, so the label was
verified present + unconditionally rendered in source; live scrub-verify on device.)

PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with every PR"
lockstep per PR #237 convention; AGENTS.md carries no §Gotchas mirror (per the
PR #327 precedent — frontend gotchas live in CLAUDE.md, the canonical home).

---
**20th subagent `financial-engineer` + #311–#330 doc-drain housekeeping (this PR)**
— adds the team's first **generative quant-design** seat and drains the
documentation drift the session-start orientation surfaced. Two coupled
deliverables in one PR (they share the same six current-state doc homes, so
splitting them would force a rebase on each merge — the §Phase-status-collision
lesson).

**(a) New 20th subagent `financial-engineer`** (`.claude/agents/financial-engineer.md`)
— Tier 3 Specialized, **opus**, read-only (Read/Bash/Grep/Glob — no Edit/Write,
mirrors `methodology-scientist`). This is the DESIGN counterpart to the existing
VALIDATION layer: QuantRank already has `methodology-scientist` (ratifies priors),
`defense-layer-auditor` + `stock-detail-auditor` (check output) — what it lacked
was the seat that PROPOSES a new construct in the first place. The agent emits a
structured design proposal (problem → academic anchor → math spec → architecture
fit → annotate-before-veto rollout → observability fields → test plan →
orthogonality check → footguns) for a new valuation method / factor signal /
scoring pillar / risk-overlay defense flag / cost-of-equity refinement, then hands
off down the canonical chain: `methodology-scientist` (ratify the academic prior —
can REJECT) → `test-engineer` (tests) → `quantrank-reviewer` (implementation
review the main agent + user write). New **README Flow 8 (quant-design flow)** is
the generative complement to Flow 3 (new-defense flow): Flow 3 starts at
validation; Flow 8 starts one step earlier at design. Designer proposes, validator
gates — deliberately separate seats so no agent both invents and ratifies its own
prior. The agent carries the project's non-negotiable design discipline in-prompt:
academic-anchor-or-labeled-gut-feel (Phase 2.5 provenance), annotate-before-veto
(Rule 16), observability-before-wiring (Rule 18), scout-then-integrate for new
deps, orthogonality (φ vs nearest signal), sum-to-1 + no-retroactive-composite
invariants, graceful-degradation try/except.

**User-locked decisions (this session, via AskUserQuestion):** model = **opus**
(the 5th opus agent; generative quant design is breadth-of-judgment per README
authoring-conv #3, and the agent is rare-fire so the all-models-pool impact is
small); charter = **broad, Phase 4–7** (factor consolidation / ML meta-learner /
sentiment v2 / regime + portfolio construction, plus the core valuation/scoring
surface) — staying inside the fundamentals-equity-ranking research framework (NOT
technical-indicator / options-flow / HFT, the same boundary `methodology-scientist`
holds). Roster **19 → 20** (now **5 opus / 15 sonnet**); coordination flows
**7 → 8**.

**(b) Doc-drain housekeeping** — session-start orientation found the docs trailing
the repo: `PHASE_STATUS.md` §Recently merged stopped at **#310** (8 PRs behind
HEAD = #330) and CLAUDE.md §Recently merged stopped at **#326**. Drained PRs
#311–#330 into PHASE_STATUS.md (demoted #303–#310 to a new "Earlier" sub-block) and
#327–#330 into CLAUDE.md; bumped the PHASE_STATUS.md "Current state" snapshot date
2026-05-28 → 2026-05-31. The 20th-agent + 5-opus + 8-flows counts were updated in
**lockstep across all six current-state doc homes** (the stale-count trap PR #319
had to fix): CLAUDE.md §Layout + §Auto-routing (delegation-pattern row + cue-table
row + "four/five opus" + "4-vs-15/5-vs-15 split" + "7/8 flows"), AGENTS.md
§Project-structure tree + §Phase+version-state + gate-moment line, CONTEXT.md (3
rows: roster / catalog / layout), WORKFLOW.md §Agentic-6-Phase-Cadence,
PHASE_STATUS.md §Subagent-inventory, and `.claude/agents/README.md` (set count +
Tier 3 header + Tier 3 row + Tier rationale + Flow 8 + model-split paragraph).
Historical PR-note counts ("14 in 4 tiers", "18-subagent topology", PR #307's "all
19 agents") were left untouched — they record what was true at the time.

**(c) `frontend/node_modules` installed** — the second "thing to know before
starting" from session orientation. `npm install` ran clean (5 known
`next@14.2.x` advisories, all zero-exploitability on the static-export deployment
per issue #41 — not addressed here). Not committable (gitignored); this is local
env-prep so a future frontend task can run `tsc --noEmit` / `next build` without a
cold install.

Doc + agent-infra only — **no compute / schema / scoring / valuation / frontend
code change**. `ruff check .` + `pytest -m "not network"` trivially pass (no Python
touched); `schema_check` not applicable (no schema field moved). The new agent file
follows all six README authoring conventions (one job · sharp TRIGGER description
with skip-guards · opus model selection justified · restricted read-only tool
allowlist · project-anchored references · pinned output format + Handoff line).

PHASE_STATUS_INFLIGHT.md side-file satisfies §Conventions "ship with every PR"
lockstep per PR #237 convention; CLAUDE.md + AGENTS.md both carry the substance
diff (roster counts + §Phase-status / §Phase+version-state in-flight entries) per
the lockstep rule.

---

**Two §Gotchas entries documenting the PR #332 hero rework (this PR)** —
post-merge doc backstop for the stock-detail hero changes that shipped as a
fast UI iteration (PR #332, merged `43838c6`, frontend-only, no schema/compute).
That PR skipped the CLAUDE.md/AGENTS.md substance lockstep because it was a
rapid spot-check-driven iteration; this PR adds the two invariants future
editors need so they don't regress them:

1. **Hero splits on a CSS CONTAINER QUERY, not a viewport breakpoint**
   (`frontend/app/stock/[ticker]/page.tsx` + `globals.css` `.hero-card` /
   `@container hero (min-width: 46rem)`). The left Sidebar eats a
   viewport-variable width slice (expanded 240 / collapsed 64 / drawer 0), so a
   `md:`/`lg:` viewport gate left a dead band where the sidebar was a desktop
   rail but the hero still stacked. The container query measures the hero's real
   inline-size after the sidebar's cut. JSX default = stacked `flex-col`; the
   `@container` rule only ADDS the row (pre-2023 browsers degrade to the safe
   stack). Raw CSS — no `@tailwindcss/container-queries` plugin/dep.
2. **MoS gauge arc is SIGN-AWARE** (`frontend/components/MoSBadge.tsx`):
   MoS ≥ 0 sweeps clockwise (like the score gauge), MoS < 0 sweeps
   counter-clockwise via `-scale-x-100` on the gauge container, with the number
   `<span>` carrying its own `-scale-x-100` to un-mirror back to readable. 329/502
   of the universe is negative MoS → CCW is the common case. Both mirrors move in
   lockstep.

CLAUDE.md §Gotchas carries the full rationale for both; AGENTS.md §Code style
mirrors each as a one-paragraph pointer (the PR #327 precedent — frontend
gotchas live in CLAUDE.md, AGENTS.md points at them). Doc-only PR — no compute /
schema / scoring / valuation / frontend CODE change (the hero code already
landed via PR #332; this is the documentation backstop only).

---

**All 20 subagents set to `effort: max` (this PR)** — added the `effort`
frontmatter field (value `max`) to every agent file under `.claude/agents/`.
Per the official Claude Code subagent docs the field is `effort` with the value
ladder `low / medium / high / xhigh / max`; `max` overrides the session's
inherited effort while the subagent is active and is ORTHOGONAL to `model`
(`model` = which model opus/sonnet, `effort` = how hard it reasons). Confirmed
the field name + value + override semantics via the `claude-code-guide` agent
before editing so no dead config ships. Rationale: every one of the 20 agents is
a correctness / judgment gate (code review · schema drift · defense audit ·
academic-prior validation · quant design · incident triage · …), so the top
reasoning level pays back; and sonnet-at-max still drains the separate Max-plan
"Weekly · Sonnet only" pool, not the all-models pool, so the cost lands on the
under-utilized budget. Lockstep doc updates: README §"Model split" gains an
**Effort** paragraph + §Authoring conventions #3 gains an `effort: max` bullet
(so a future agent inherits the convention); CLAUDE.md §Spawn discipline
model-assignments block gains the effort sentence; AGENTS.md §Project-structure
`.claude/agents/` tree comment notes "(5 opus / 15 sonnet, all `effort: max`)"
+ a §Phase+version-state in-flight entry. Agent-infra + doc only — no compute /
schema / scoring / valuation / frontend code change; `ruff` / `pytest` /
`schema_check` trivially unaffected (no Python / TS touched).

---

**Subagent model-downgrade guard added (same PR as effort:max)** — answers the
user's question "are the agents always on the latest Opus/Sonnet, and is there
protection against a self-inflicted downgrade?". Findings (confirmed via
`claude-code-guide` against the official Claude Code docs): the 20 agents use
bare `model: opus` / `model: sonnet` aliases, which RESOLVE TO THE LATEST
Opus/Sonnet at runtime and FLOAT FORWARD automatically on a CLI update — so the
project is "always latest" by design, no action needed. The real downgrade
vector is NOT the agent files but the ENVIRONMENT: a `CLAUDE_CODE_SUBAGENT_MODEL`
or `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL` committed into
`.claude/settings.json` would pin every subagent to a fixed (possibly older)
version WITHOUT changing a single agent file — invisible in a diff. Audited the
current `.claude/settings.json`: no `env` block, no override var → clean today.

New `tools/check_model_pin.py` (wired into `.github/workflows/ci.yml` Python job
as the "Subagent model-pin guard" step, mirroring the existing
`check_doc_test_counts.py` precedent) fails CI if (a) committed settings carry
any of the 6 override env vars — the one benign value being
`CLAUDE_CODE_SUBAGENT_MODEL='inherit'` — or (b) any agent frontmatter pins a
dated/numbered model ID (`claude-opus-4-8`) instead of the floating alias.
Guard runs clean locally (exit 0); negative test confirmed it rejects a pinned
ID. Lockstep docs: CLAUDE.md §Gotchas "Subagent model aliases float forward"
(full rationale) + AGENTS.md §Security considerations + a §Phase-status entry.
`.claude/settings.local.json` (gitignored, per-user) is out of scope — a local
override can't land on `main`. CI + agent-infra + doc only — no compute / schema
/ scoring / valuation / frontend code change.

---


## Merge RiskFlagsCard + ManipulationRiskCard → RiskSummaryCard (frontend, this PR)

**Scope**: frontend-only. Combines the two adjacent stock-detail cards
(`RiskFlagsCard` + `ManipulationRiskCard`) into ONE `RiskSummaryCard`
container with two clearly-labelled sub-sections — **RANK GATES**
(`risk_flags[]`, Rule-16 Top-5 disqualifiers) and **MANIPULATION INDEX**
(the 0-100 informational rollup). User request 2026-05-31: the two cards
showed partially-overlapping flag lists so the manipulation-linked vetoes
(`sloan_accruals_top_decile` / `beneish_manipulation_veto` / …) rendered
TWICE on screen and read like duplicated data.

**Why restructure not flatten**: the overlap is asymmetric BOTH ways —
`altman_distress` / `data_quality_input_corruption` / `net_issuance_top_decile`
/ `stale_filing_hard` are rank gates NOT in the manipulation index; the
annotate-only flags (`accruals_momentum_high`, `beneish_high`,
`restatement_history`, `rem_suspect`, …) are in the index but never in
`risk_flags`. A flat merge under one "Manipulation Risk" header would
mislabel `altman_distress` (financial distress, not earnings manipulation).
The two sub-sections preserve the gating-vs-informational semantic.

**De-dup contract**: a flag that is BOTH a rank gate and a fired
manipulation component is shown ONLY in RANK GATES; the manipulation
sub-section lists only the annotate-only SURPLUS (`alsoFired =
firedComponents − gateSet`) under "Also fired — not rank-gating". Same
flag never renders twice. Outer ring = worst-case (rose if any rank gate,
else the manipulation band tone); the Low/Moderate/High band chip moves
into the manipulation sub-header when gates own the outer-header count
chip so it's never lost. Returns `null` only when BOTH halves are empty.

**Verification (real data, no fixture)**: `tsc --noEmit` clean · `next
build` 506/506 pages · grep-verified the generated HTML of 5 real
tickers covering every branch — NVDA / SMCI / STX (gate + surplus: each
shared flag renders EXACTLY ONCE, deduped into rank gates; annotate
surplus under "Also fired") · COF (gate-only, idx 0 → no manipulation
sub-section) · KIM (index-only, no gates → "Fired components" label, not
"Also fired"). 82/502 of the current universe carry both a gate and a
manipulation component (the de-dup target cohort).

**No schema / Python / scoring / valuation / output-JSON change** —
component merge + page wiring + doc lockstep only. Props are the union of
the two old cards' props (same `risk_flags` / `manipulation_index` /
`composite_score` / `composite_score_adjusted` / `manipulation_components`
fields; `types.ts` touched for a COMMENT-only consumer-name update — no
field shape change, snapshot + Pydantic untouched). Net +1 / −2 components.

## Background-run hygiene §Gotcha — prevent zombie panel tasks (docs, this PR)

**Scope**: doc-only. Adds a CLAUDE.md §Gotchas entry (+ AGENTS.md
§Claude-Code-specific-tooling mirror) codifying how to avoid the
perpetually-"Running" Background-tasks panel entries the user hit
2026-05-31 (a "chevron review" sub-agent + an `npm install` bash both
showing Running across a `/compact`).

**Two zombie classes documented**:
1. **Background AGENT orphaned by `/compact`** — an async sub-agent
   (`Agent run_in_background:true`) is tracked by an `agentId` the harness
   returns at spawn. A `/compact` drops that id from the live transcript →
   the post-compact main agent can't `SendMessage`/stop it → it sits
   "Running" billing tokens. It is NOT an OS process (`ps`/`pgrep` only see
   Bash — so "ps shows nothing" does NOT prove it's dead; that was my
   mis-call earlier in the session). Prevention: default SYNC agent spawns;
   reserve background for a long job collected in the SAME session pre-compact;
   if it must straddle a compact, tell the user (only the panel Stop can kill it).
2. **Background BASH with no exit** — `next dev` / `tail -f` / `while true` /
   a lingering `npm install` parked with `run_in_background:true`. Prevention:
   deterministic-exit background Bash only (`until grep -q …; do sleep …; done`);
   if you must serve, kill it the same turn with a TARGETED `kill` (NOT a broad
   `pkill` — a `pkill` catching the harness shell returns exit 144 and cancels
   the rest of the parallel tool batch, which is the batch-nuke that happened
   during PR #337's verify step).

**No code / schema / scoring / valuation / frontend change** — CLAUDE.md +
AGENTS.md + this INFLIGHT entry only. The discipline is behavioral
(applies to the main agent's own spawn/Bash choices), enforced by
documentation, not a new hook (per user direction: "บันทึกเป็น discipline
ถาวร", not "สอบสวน hook กัน zombie เพิ่ม").

## De-dup the fair-price detail pair — drop FairPriceCard method table (frontend, this PR)

**Scope**: frontend-only. The stock-detail page renders two adjacent
fair-price cards that both read the SAME `detail.fair_price` object:
`FairPriceBarChart` ("Fair price check", first) + `FairPriceCard`
("Fair price ensemble", second). They showed the SAME six per-method
dollar values twice — Card A in its narrative ("estimates $379.81, …")
and Card B in a METHOD→VALUE table. User asked whether to merge them.

**Verdict (frontend-design-reviewer): DON'T-MERGE, targeted de-dup**
— unlike the RiskFlags+Manipulation merge (PR #337, same question →
merged), these two cards answer DIFFERENT questions: Card A =
INTERPRETATION (verdict banner + cheap/fair/pricey badges + plain-English
narrative + tally), Card B = REFERENCE/metadata (Median/MoS/Max/BVPS stat
grid + warning chips + methodology footnote). A full merge was rejected
for three reasons: (1) the two cards carry DIFFERENT MoS formulas —
Card B `mos_pct = (median−price)/median` vs fair value (official scoring
field, ensemble.py) vs Card A `(median−price)/price` vs market price; for
NVDA that's −175% (clamped "< −99%") vs −64%, which would look
contradictory side-by-side; (2) a merged card would be ~900-1100px tall on
mobile (longest on the page); (3) different reading-mode audiences.

**Change**: removed the per-method METHOD→VALUE table (+ `MethodRow`,
`METHOD_LABELS`, `METHOD_ORDER`, unused `FairPriceMethodResult` import)
from `FairPriceCard`. Card B now = stat grid + warning chips + footnote
(metadata only). Per-method dollars live in Card A exclusively; Card B's
footnote cross-references "the Fair price check above". No data lost —
Card A already renders every applicable method's estimate (DCF, the only
skipped method on NVDA, has no value to show anyway).

**Verification (real data, no fixture)**: `tsc --noEmit` clean · `next
build` 506/506 · grep of generated NVDA HTML: Card B method table gone
(`<table>`/`>Method</th>` absent — the remaining `>Value</th>` is
`RawMetricsTable`'s "Metric|Value", a different table), Card B stat grid
(Median/MoS/Max/BVPS) + 3 warning chips intact, Card A still shows all 5
applicable per-method dollar values ($379.81/$77.59/$65.38/$243.67/$32.41),
footnote cross-ref present.

**No schema / Python / scoring / valuation / output-JSON change** — Card B
className/JSX diff only (net deletion). `FairPriceMethodResult` stays
exported from `types.ts` (still used by `FairPriceBarChart`); Card B just
stops importing it. CLAUDE.md §Gotcha + AGENTS.md inventory + this entry.

## Stock-detail reading-order pass — pillar-up reorder + hero risk chip (frontend, this PR)

**Scope**: frontend-only (`frontend/app/stock/[ticker]/page.tsx`). End-of-
session reading-order audit of the detail page by TWO agents in parallel
(`frontend-design-reviewer` IA pass + `expert-user-explorer` 3-persona pass).
Both concluded the order is "largely sound" — hero surfaces score+MoS at
zero scroll, fair-price pair ordered correctly (verdict→reference). Two
actionable, low-risk improvements landed; one proposal deliberately NOT taken.

**Change 1 — move `PillarRadarChart` up** (was below both fair-price cards →
now right after the price chart, before the warning group). Rationale: the
pillar breakdown answers "why is the composite score X?" (NVDA value-pillar
35 vs quality 91) and belongs near the hero's score donut, not stranded
~1000px below it (expert-user-explorer single-highest-impact move). New
order: hero → price → PillarRadarChart → Tier2EventCard → RiskSummaryCard →
FairPriceBarChart → FairPriceCard → RawMetricsTable → data-quality → footnote.

**Change 2 — hero "N risk vetoes" chip: TRIED then REVERTED in this PR**
(user call on the live preview, 2026-05-31 — "2 risk vetoes ไม่เอาอันนี้
เอากลับเป็นเหมือนเดิม"). The chip (rose count next to the RecommendationBadge,
rendered when `risk_flags.length > 0`, anchored to `#risk-summary` via a
`scroll-mt-20` wrapper) was built + verified on the preview, but the user
decided the hero should stay visually quiet: the recommendation badge
("Hold") already carries the cautious signal, the MoS donut conveys
overvaluation, and the rank-gate detail lives in RiskSummaryCard below. The
chip + its `rankGateCount` var + the `#risk-summary` wrapper div were ALL
removed — only Change 1 (the pillar reorder) ships in this PR.

**NOT taken** (per main-agent synthesis of the two-agent split): the
`frontend-design-reviewer` suggestion to move the warning group
(Tier2+Risk) ABOVE the price chart. `expert-user-explorer` showed the
current position optimizes the risk-checker persona correctly. Moving
PillarRadar further up (ahead of price) was also declined — it would push
the fair-price pair (what the primary value-screener persona wants after
seeing MoS) further from the hero.

**Verification (real data, no fixture)**: `tsc --noEmit` clean · `next
build` 506/506. The pillar reorder is confirmed in the NVDA HTML (section
order Price < Pillar < Risk < FP-check < FP-ensemble). The hero chip was
verified rendering "2 risk vetoes" on NVDA / absent on HST BEFORE the
revert; post-revert the hero is back to its prior shape (no chip on any
stock). **No schema / Python / scoring / valuation / output-JSON change** —
JSX reorder only (the additive chip was added then removed in-PR, net zero).
CLAUDE.md §Gotcha + AGENTS.md inventory note + this entry.

## Price-chart 5Y monthly resolution (frontend, this PR)

**Scope**: frontend-only (`frontend/components/PriceHistoryChart.tsx`). User
spec: 1D=1-min · 5D=15-min · 1M/6M/YTD/1Y=daily · 5Y=monthly. Of these,
1M-1Y were ALREADY daily (no change), 5Y was daily-even-stride-downsampled
to 260 points, and 1D/5D are intraday (disabled, separate v1.3 feature). This
PR ships ONLY the 5Y→monthly change per the user's "ทำแค่ 5Y รายเดือนก่อน".

**Change**: new `aggregateMonthly()` helper — yields one point per calendar
month (the close of that month's FIRST trading day, per user follow-up
"ปรับเป็นวันแรกของเดือน") from the ascending daily series, and ALWAYS appends
the real latest daily point last (de-duped) so the right edge + park-at-latest
crosshair show the current price, not the weeks-stale 1st-of-this-month close.
The `chartData` memo now routes `period === '5Y'` through
`aggregateMonthly(sliced)` instead of `downsample(sliced, 260)`; every shorter
window stays daily + keeps the `downsample` render-cost cap. NVDA 5Y: 1254
daily → 61 points (60 month-firsts 2021-06-01 … 2026-05-01 + the real latest
2026-05-28 $214.25). The 5Y X-axis label stays `YYYY` (page.tsx) — still
appropriate at ~60 points / 12 year ticks.

**Intraday (1D 1-min / 5D 15-min) NOT done this PR** — user deferred ("ทำแค่
5Y รายเดือนก่อน"). It's a v1.3 feature: NEW compute/ingest path (yfinance
`1m`=7-day cap / `15m`=60-day cap) + `StockHistory` schema-triple bump + cron
volume + the static-site freshness caveat (daily post-close cron ⇒ "1D" would
be the last cron's session, not real-time). The on-disk history file has no
intraday data, so 1D/5D stay disabled in `PriceTimePeriodSelector`.

**Verification (real data)**: `tsc --noEmit` clean · `next build` 506/506 ·
`aggregateMonthly` unit-checked against the real NVDA daily series (61 points:
every non-final sample is an early-of-month first trading day, last point ==
the real latest daily 2026-05-28 $214.25, current month 2026-05 carries 2
samples = its 1st + the latest by the de-dup rule).
**No schema / Python / scoring / valuation / output-JSON change** — pure
frontend render logic + 1 new exported helper. CLAUDE.md §Gotcha + AGENTS.md
ingest note + this entry.

## Hero: remove recommendation-badge animation + count-up the metric values (frontend, this PR)

**Scope**: frontend-only. Two coupled hero changes per user request
2026-05-31 ("เอา animation ตรง hold buy strong buy sell ออก และเพิ่ม
animation ตัวเลขวิ่งให้ fair value target loss chance แบบ ease in and out").

**Change 1 — RecommendationBadge is now STATIC**. Removed the `animateOnce`
prop + the `usePlayOnMount` chip-pop gate + the `'use client'` directive — the
badge is a pure server component again (hero badge + all 502 ranking-table
cells render with no motion). The `chip-pop` keyframe stays defined in
`tailwind.config.ts` + `globals.css` as a reusable utility but now has ZERO
consumers (Tailwind purges it from the bundle); the tailwind comment +
`docs/design.md` §Motion row updated to mark it unused (not deleted — kept
for any future chip surface).

**Change 2 — Fair value / Target / Loss chance count-up**. New `HeroMetric`
client leaf wraps the existing `useCountUp(value, play, 800)` (easeInOutCubic
— the SAME app-wide ease-in-out curve as the Score/MoS gauge sweep). `page.tsx`
stays a Server Component; `HeroMetric` is the small `'use client'` leaf that
holds the hook (lifting it into the page would force the whole detail page
client-side). The loss-chance 5-band tone is computed server-side in `page.tsx`
(`lossChanceTone`, verified byte-for-byte parity with the old inline rubric at
every boundary 0/25/40/60/80) and passed as a prop. `useCountUp` inits at the
target → SSR / no-JS / reduced-motion render the exact value (count-up is
progressive enhancement, never a visibility gate). The unused `formatPrice`
helper was removed from `page.tsx` (HeroMetric formats internally).

**Verification (real data)**: `tsc --noEmit` clean · `next build` 506/506 ·
NVDA HTML — no `animate-chip-pop` on the page, "Hold" badge still renders,
Fair value $77.59 / Target $379.81 / Loss chance 55% all present (static
prerender = exact value), loss-chance band parity PASS (55% → slate, matches
the screenshot grey). `HeroMetric` confirmed a separate `'use client'` chunk;
`page.tsx` still server. **No schema / Python / scoring / valuation / output-
JSON change** — 1 new client component + badge simplification + page wiring.
CLAUDE.md §Gotcha + AGENTS.md inventory + tailwind/design.md comment fixes.

## Hero attribute tiles — 4-box category grid + lucide-react (frontend, this PR)

**Scope**: frontend. User asked for "กรอบสี่เหลี่ยมสี่อันในภาพ" — a reference
stock app's 4 category tiles (icon-over-label boxes). A `/grill-me` session
locked the spec (6 decisions): (1) match the STRUCTURE (grid/icon-top/label-
bottom) but reskin to the QuantRank theme — light slate / dark slate, NOT the
reference app's black boxes (break in light mode); (2) 2 tiles have data
(Size = market-cap tier, Sector), 2 don't; (3) the empty tiles render as
"reserved" placeholders (dashed border + "Coming soon" sub-line) NOT a bare
"—" — so they read as intentional, not broken; (4) icons via a NEW dep
`lucide-react`; (5) supersede + CLOSE the earlier inline-chip attempt (PR #343
closed — the user wanted the BOX grid, not a compact chip row); (6) own section
under the hero, info tiles (not filters).

**New dep — `lucide-react@^1.17.0`** (the project's first icon library).
dependency-auditor + security-reviewer both SAFE: ISC license (MIT-tier),
React-18.3 peer, 0 transitive deps, 0 install-scripts, SLSA-attested, 0 CVE.
Tree-shakes to ~1.5-2 KB gzipped for 4 named-imported icons (stock-detail
route 113 → 115 KB First Load JS, as predicted). NAMED imports only — never
the `import * as Icons` barrel (224 KB). NOT added to the dependabot
ignore-list (normal flow). NOT added to THIRD_PARTY_NOTICES.md (that file
tracks vendored sources/skills only — next/react/recharts aren't listed
either, so a runtime npm dep doesn't belong there; auditor suggested adding
it but the project convention is the opposite — noted here for the record).

**New component** `HeroAttributeTiles.tsx` (pure server component): `grid
grid-cols-2 sm:grid-cols-4`, 4 fixed tiles via a `Tile` sub-component. A tile
with a `null` value flips to the dashed "reserved" treatment. Wired as its own
section in `page.tsx` directly under the hero `</header>`, above the Price
chart.

**Verification (real data)**: `tsc --noEmit` clean · `next build` 506/506 ·
NVDA HTML — Size→"Mega cap", Sector→"Information Technology", 2 "Coming soon"
placeholders, `grid-cols-2`+`sm:grid-cols-4` present, lucide icons render as
inline SVG (tree-shaken, +2 KB route). **No schema / Python / scoring /
valuation / output-JSON change** — 1 new dep + 1 new server component + hero
wiring. CLAUDE.md §Gotcha ×2 (lucide import discipline + the tiles) + AGENTS.md
inventory + this entry.
