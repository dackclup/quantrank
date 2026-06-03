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

_All entries below the convention header were drained 2026-06-03 in the Claude
token-economy PR (they had grown to ~5,680 lines / ~95K tok, almost entirely
merged PRs whose labels were never updated from "(in flight, this PR)"). The
merged narrative is preserved in git history + summarized in PHASE_STATUS.md.
This file restarts lean per its own "Merged -> housekeeping move" convention._

## PR #391 — Claude token-economy optimization (in flight, 2026-06-03)

**Branch**: `claude/dreamy-heisenberg-4IfRj`
**Type**: chore(infra) — docs + agent infrastructure only; no compute / schema /
scoring / valuation / frontend / dependency change; no schema bump.

**Goal**: cut Claude token usage with zero capability loss.

- **P0** — drained CLAUDE.md §Gotchas detail -> `docs/GOTCHAS.md` (kept a 53-line
  index) + §Phase status merged-PR log -> `PHASE_STATUS.md` /
  `docs/PHASE_STATUS_ARCHIVE.md`. CLAUDE.md 3232->~560 lines, ~55.8K->~9.7K tok
  (-82%; ~46K saved per session AND per sub-agent spawn — sub-agents inherit
  project context).
- **P1** — collapsed AGENTS.md §"Phase + version state" ~1,068-line mirror ->
  pointer; reset this file to its header.
- **P2** — shortened `delegate-first.sh` injection (~220->~83 tok/turn) +
  `effort: max->high` on deterministic script-runners (`schema-sentinel`,
  `vercel-preview-auditor`).
- **New skill** `.claude/skills/thai-token-economy/SKILL.md` — Thai I/O <-> English
  internals discipline (honest: Thai is ~2-4x/char at the tokenizer, so keep
  reasoning/code/logs/commits in English, reply in concise Thai).
- New CLAUDE.md §Conventions bullet "CLAUDE.md is an INDEX" guards re-bloat.

**Files**: `CLAUDE.md` · `AGENTS.md` · `PHASE_STATUS_INFLIGHT.md` (this) ·
`docs/GOTCHAS.md` (new) · `docs/PHASE_STATUS_ARCHIVE.md` (new) ·
`.claude/hooks/delegate-first.sh` · `.claude/agents/schema-sentinel.md` ·
`.claude/agents/vercel-preview-auditor.md` · `.claude/skills/thai-token-economy/SKILL.md` (new).

---

## Sidebar version-chip auto-wire + FairPriceCard warning labels (in flight, 2026-06-03)

**Branch**: `claude/version-chip-flag-labels`
**Type**: fix(frontend) — FRONTEND-ONLY, no schema / compute / data change; no schema bump. Resolves 2 of the 3 items the #392 whole-app polish pass deferred.

**#1 — Sidebar version chip auto-wire.** The footer chip was hardcoded `v1.4.0`
(the last release tag) while `main` ran 30+ PRs ahead → misleading. `next.config.js`
now computes `NEXT_PUBLIC_APP_VERSION` at build via an `env:` block:
explicit override → `git describe --tags --always --dirty` (reformatted
`TAG-N-gSHA` → `TAG+N`) → `VERCEL_GIT_COMMIT_SHA` / `GITHUB_SHA` short → `'dev'`.
`Sidebar.tsx` reads `process.env.NEXT_PUBLIC_APP_VERSION` (inlined at build).
Local dev with tags shows `v1.4.0-phase4.6+N`; shallow CI/Vercel clones (no tags)
show the 7-char commit SHA — both honest, never stale. (User-chosen approach:
"Auto build version".)

**#2 — FairPriceCard warning labels.** The valuation-ensemble warning chips
humanized flags with a raw `w.replace(/_/g,' ')` ("extreme graham estimate") while
`RiskSummaryCard` uses proper labels — the same flag read two ways. Added a
`VALUATION_WARNING_LABELS` map (the `extreme_{method}_estimate` family +
`extreme_estimate_majority` / `stale_filing_soft` / `goodwill_heavy` /
`value_trap_risk` / `data_quality_input_corruption` / `valuation_output_anomalous` /
`insufficient_history_for_roe`) with a Title-Case fallback for unknown flags
(forward-safe per `compute/valuation/ensemble.py:142`).

**Still deferred:** the P3 cross-stock COMPARE view (product-scope feature, not polish).

**Verification**: `next build` GREEN locally (506 pages, lint + types valid); the
version wire resolves at config-load (verified `node -e require('./next.config.js')`).

**Files**: `frontend/next.config.js` · `frontend/components/Sidebar.tsx` ·
`frontend/components/FairPriceCard.tsx` · `CLAUDE.md` (§Gotchas index) ·
`docs/GOTCHAS.md` (detail) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## Cross-stock COMPARE view — /compare + ranking-table multi-select (in flight, 2026-06-03)

**Branch**: `claude/busy-newton-L6J56`
**Type**: feat(frontend) — FRONTEND-ONLY, no schema / compute / data change; no
schema bump. Ships the P3 cross-stock COMPARE view deferred by the #392 whole-app
polish pass (the last open item from it; designed via `$impeccable shape`, brief
re-audited + confirmed before craft).

**What**: a new `/compare` route compares up to 4 S&P 500 names side by side
across the focused decision-set — composite + tier, the 8 active pillars,
fair-price median + margin of safety, and the risk/defense-flag load. Entry is
multi-select on the ranking table (checkbox per row, capped at `MAX_COMPARE = 4`)
→ a fixed "Compare (N)" bar → `/compare/?compare=AAPL,MSFT`. The matrix is a
semantic `<table>` (rows = metric, cols = stock) with a sticky metric-label rail
for horizontal scroll on mobile; best-in-row marking is metric-aware (max for
composite / pillars / MoS, min for loss-chance / flag-count / manipulation-index,
none for raw price) and never color-only (sage ▲ + sr-only "best of N").

**Architecture**: the `/compare` server shell build-imports `getRankings()` (the
focused set is 100% on `StockSummary`/rankings.json → no per-stock fetch, no
loading waterfall; the 6-method fair-price breakdown stays detail-page-only).
`CompareView` (client) reads/writes `?compare=` via `window.location` +
`history.replaceState` — NOT `useSearchParams` (which would force a `<Suspense>`
boundary on the static export). Selection is in-memory; the URL is the shareable
artifact.

**DRY**: `pillarColor` centralized into `lib/visual.ts` (was a local `colorFor`
in `PillarRadarChart`, now shared with the matrix) + `flagLabel` centralized into
`lib/flag-labels.ts` (was `FairPriceCard`'s local `VALUATION_WARNING_LABELS`;
`FairPriceCard` refactored to import it).

**Verification**: `next build` GREEN locally — 507 static pages (506 + `/compare`),
lint + types valid; `/compare` = `○ Static` 6.64 kB. `tsc --noEmit` clean. The
static shell renders the H1 + skeleton pre-hydration (the query is read
client-side).

**Files**: `frontend/app/compare/page.tsx` (new) · `frontend/components/CompareView.tsx`
(new) · `frontend/components/CompareMatrix.tsx` (new) · `frontend/lib/flag-labels.ts`
(new) · `frontend/components/RankingTable.tsx` (multi-select + compare bar) ·
`frontend/lib/visual.ts` (`pillarColor`) · `frontend/components/PillarRadarChart.tsx`
(use `pillarColor`) · `frontend/components/FairPriceCard.tsx` (use `flagLabel`) ·
`CLAUDE.md` (§Gotchas index) · `docs/GOTCHAS.md` (detail) · `PHASE_STATUS_INFLIGHT.md`
(this).

---

## Compare view polish — flag-label consistency + Risk-row overflow cap (in flight, 2026-06-03)

**Branch**: `claude/busy-newton-L6J56`
**Type**: fix(frontend) — FRONTEND-ONLY, no schema / compute / data change; no schema
bump. `$impeccable polish` follow-up on the merged compare view (#394), folding the
critique P2 + the post-merge e2e finding (both logged in #395).

**#1 — flag-label consistency (e2e finding).** The post-merge e2e (`expert-user-explorer`)
caught the CompareMatrix `FlagsCell` Title-Casing the rank-gate VETO `risk_flags` via
the `flagLabel` fallback ("Sloan Accruals Top Decile") while `RiskSummaryCard` rendered
the canonical label ("Sloan accruals — top decile") — same flag, two labels across
compare↔detail. Root cause: `lib/flag-labels.ts` `FLAG_LABELS` was seeded from the
valuation-warnings + manipulation flags only, missing the rank-gate vetoes. Fix: added
the 5 missing veto keys (`altman_distress` / `sloan_accruals_top_decile` /
`net_issuance_top_decile` / `beneish_manipulation_veto` / `dechow_manipulation_veto`) +
reconciled 2 conflicting shared keys (`non_reliance_filing` → "8-K Item 4.02
non-reliance"; `stale_filing_hard` → "Stale filing — fair-price suppressed") to mirror
`RiskSummaryCard.RANK_GATE_META` VERBATIM. `RiskSummaryCard` left untouched (its META
also carries an academic `detail` line; folding its label onto `flagLabel()` for a true
single-source is noted as a later PR).

**#2 — Risk-row flag-overflow cap (critique P2).** A flag-laden column grew the Flags
row far taller than a clean column's single "Clean" chip (row-height asymmetry).
`FlagsCell` now caps visible flag chips at 3 + a neutral "+N more" chip (full list in
`title` + sr-only); the count chip + best-▲ stay the comparable signal.

**Still deferred to #395**: jargon inline-help (`clarify`) + bulk-add paste (`harden`) —
features, not polish.

**Verification**: `tsc --noEmit` clean; `next build` GREEN (507 pages, `/compare` 6.83
kB); built-chunk grep confirms the canonical veto strings shipped.

**Files**: `frontend/lib/flag-labels.ts` · `frontend/components/CompareMatrix.tsx`
(`FlagsCell`) · `docs/GOTCHAS.md` (compare gotcha) · `PHASE_STATUS_INFLIGHT.md` (this).

---
