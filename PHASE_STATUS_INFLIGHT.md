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

## Flag-label single-source fold — RANK_GATE_META.label → flagLabel (in flight, 2026-06-03)

**Branch**: `claude/busy-newton-L6J56`
**Type**: refactor(frontend) — FRONTEND-ONLY, behavior-preserving; no schema / compute
/ data change; no schema bump. Closes the #395 single-source debt (quantrank-reviewer
WARN on #396).

`RiskSummaryCard.RANK_GATE_META` no longer carries a per-entry `label` — it holds only
the academic `detail` line, and the rank-gate label renders via the shared `flagLabel()`
(`lib/flag-labels.ts`). #396 had added the rank-gate veto labels to `FLAG_LABELS`
mirroring `RANK_GATE_META` verbatim (fixing the e2e-found compare↔detail drift) but left
the two as a "keep in sync" duplication; this fold makes the match STRUCTURAL — `FLAG_LABELS`
is the single source, so a future veto added without a `FLAG_LABELS` entry can't silently
regress the compare matrix to Title-Case (the detail page would Title-Case it identically
rather than diverge). Behavior-preserving for known flags (flagLabel returns the same
verbatim strings — confirmed: detail-page chunk still ships "Altman financial distress" /
"Beneish M-score veto" / "Sloan accruals — top decile"); an unknown flag now Title-Cases
(+ no detail) instead of rendering the raw key — a strict readability gain, and the raw
`[key]` monospace annotation still shows the key.

**#395 housekeeping**: the row-height NIT is resolved **won't-do** — frontend-design-reviewer
chose VISIBLE=3 on #396 and argued VISIBLE=2-at-4-columns is too aggressive ("+7 more"
useless as a preview). Jargon-help (`clarify`) + bulk-add (`harden`) remain deferred (features).

**Verification**: `tsc --noEmit` clean (no leftover `.label` access on `RANK_GATE_META`);
`next build` GREEN (507 pages); detail-page chunk grep confirms the canonical veto labels
still ship via `flagLabel`.

**Files**: `frontend/components/RiskSummaryCard.tsx` (`RANK_GATE_META` → `{detail}` +
`flagLabel(flag)`) · `frontend/lib/flag-labels.ts` (comment) · `PHASE_STATUS_INFLIGHT.md`
(this).

---

## Compare jargon-help — methodology ? link on group headers (in flight, 2026-06-03)

**Branch**: `claude/busy-newton-L6J56`
**Type**: feat(frontend) — FRONTEND-ONLY, no schema / compute / data change; no schema
bump. #395 item #2 (jargon inline-help), shaped via `$impeccable`.

The critique flagged that a first-timer on the compare matrix sees "Manipulation index
12 ▲" with no in-context "what's this?". Recon found the metric rows already carry
directional `sub` clarifiers (MoS "vs fair value, higher is better", etc.) and that
there IS a methodology target — the Sidebar's "Methodology" resource link →
docs/METHODOLOGY.md on GitHub (no in-app /methodology page). Shape-confirmed affordance
(user choice): a `?` link on the jargon-heavy group headers → methodology, NOT per-term
tooltips (mouse-only, off-pattern) and NOT a full in-app page (out of scope).

- `CompareMatrix.GroupHeader` gains an optional `help` prop; the **Valuation** + **Risk ·
  defense layer** group headers render a small `HelpCircle` `?` link → the methodology
  doc (new tab, real `<a>`, aria-labelled, 44px touch target on mobile / compact on
  desktop per the × precedent).
- `CompareView` footnote: the existing "methodology" prose is now an actual link.
- New `lib/links.ts` `METHODOLOGY_URL` is the SINGLE source — `Sidebar` (was an inline
  URL), `CompareMatrix`, and `CompareView` all import it (no 3rd copy to drift).

**Verification**: `tsc --noEmit` clean; `next build` GREEN (507 pages); built-chunk grep
confirms the `?`-link aria-label shipped.

**Files**: `frontend/lib/links.ts` (new) · `frontend/components/CompareMatrix.tsx`
(`GroupHeader` help) · `frontend/components/CompareView.tsx` (footnote link) ·
`frontend/components/Sidebar.tsx` (URL → shared const) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## Compare bulk-add — paste a comma-separated ticker list (in flight, 2026-06-03)

**Branch**: `claude/busy-newton-L6J56`
**Type**: feat(frontend) — FRONTEND-ONLY, no schema / compute / data change; no schema
bump. #395 item #3 (bulk-add, `$impeccable harden`) — the LAST backlog item.

The /compare add-input added one ticker at a time; a power-user arriving via a shared
URL had no bulk path (the ranking-table multi-select was the only one). Now `CompareView`'s
add handler (`addTicker` → `addFromInput`) splits the input on `[\s,]+` (comma / whitespace
/ newline) and adds the valid, not-already-selected tickers in order up to the cap (4); the
rest surface as ONE concise note (`not in the universe: … · max 4 — … didn't fit · already
added: …`) rather than failing the whole paste. `commit()` fires only when ≥1 was added,
else the input is kept for editing. The single-ticker case is the degenerate path (unchanged
behavior). Placeholder/label/button reworded to signal the bulk capability ("Add tickers…",
"Add").

**Verification**: `tsc --noEmit` clean; `next build` GREEN (507 pages, /compare 7.55 kB).

**Files**: `frontend/components/CompareView.tsx` · `PHASE_STATUS_INFLIGHT.md` (this).

---

## Compare bulk-add — clear stale URL-parse notes on a zero-add submit (in flight, 2026-06-03)

**Branch**: `claude/busy-newton-L6J56`
**Type**: fix(frontend) — FRONTEND-ONLY, no schema / compute / data change; no schema
bump. #395 nit 2 (the dual-note edge from the #402 quantrank-reviewer WARN).

When an add-input submit added NOTHING (all dupe / invalid / over-cap), `commit()` did
not run, so the initial `?compare=` URL-parse hydrate notes (`notFound` / `truncated`)
were NOT cleared and rendered alongside the fresh `addError` caveat — two notes about
overlapping ticker sets. Fix: `addFromInput` now clears `setNotFound([])` /
`setTruncated(false)` in the zero-add branch too (those hydrate notes are stale once the
user actively submits the picker), so a zero-add paste surfaces ONLY its own caveat.

**Verification**: `tsc --noEmit` clean; `next build` GREEN (507 pages).

**Files**: `frontend/components/CompareView.tsx` · `PHASE_STATUS_INFLIGHT.md` (this).

---

## Filter dark/light theme contrast fixes — impeccable colorize (in flight, 2026-06-03)

**Branch**: `claude/optimistic-fermat-lUTnF`
**Type**: fix(frontend) — FRONTEND-ONLY, no schema / compute / data change; no schema
bump. Implements the AA-contrast fixes from the `$impeccable critique` filter theme audit
(snapshot `.impeccable/critique/2026-06-03T10-57-25Z__frontend-components-filterdrawer-tsx.md`,
merged via #398 + #400).

**Fixes (dark + light):**
- **[P1] Dark CTA** — `View N stocks` (FilterDrawer) + `Compare N` (RankingTable) used
  `dark:bg-emerald-600`; white label ~3.8:1, under AA. Root cause: the `globals.css`
  soft-color `!important` override keys on LITERAL Tailwind classes, so it never reaches
  `dark:` variants → dark rendered raw `emerald-600`. Fixed to `dark:bg-emerald-700`
  (white ~5:1). Light `bg-emerald-700` was already safe. (Rationale recorded as a code
  comment at the FilterDrawer CTA so the pattern isn't reintroduced.)
- **[P1] Help/range text** — dropped `opacity-60` (failed both modes: light ~1.9:1,
  dark ~3.7:1) on the tier-range + MoS-help chip text, bumped 10px→11px; now inherits
  the chip's full color (slate-600 unselected ~7:1; the SELECTED-chip tone is the
  deferred shared-token item below).
- **[P2] Unselected toggle chips in dark** — `dark:bg-slate-900` equaled the drawer panel,
  so chips read ring-only. Changed to `dark:bg-slate-800 dark:text-slate-300` (matches the
  active-summary chips → now consistent in BOTH modes).
- **[P2] Light placeholder** — added `placeholder-slate-500` to both search inputs
  (FilterDrawer + RankingTable toolbar); dark already had it.
- **[P3] Backdrop scrim** — added `dark:bg-black/60` (`slate-900/40` under-dimmed the
  near-black dark page).

**Deferred (NOT in this PR — need broader review):** selected-chip label ~3.4:1 in light
(shared `visual.ts` TIERS/MOS tokens → app-wide blast radius; measure in-browser first) ·
desktop filter IA (modal-drawer-only at all widths → architectural) · `Sidebar`/`AppShell`
"Q" logo `dark:bg-emerald-600` (decorative `aria-hidden`, not WCAG text) · the general
"soft-override doesn't reach `dark:` solid-fill" sweep (formalize as a §Gotchas entry).

**Verification**: Tailwind-class-only edits, design-token palette (slate/emerald scale).
`next build` / `tsc` NOT run locally (`node_modules` absent in this env) — CI Frontend
build + `frontend-design-reviewer` static review cover it.

**Files**: `frontend/components/FilterDrawer.tsx` · `frontend/components/RankingTable.tsx` ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## Filter contrast sweep completion — selected-chip + Q-mark + §Gotchas (in flight, 2026-06-03)

**Branch**: `claude/optimistic-fermat-lUTnF`
**Type**: fix(frontend) + docs — completes the dark/light AA-contrast sweep the #401
filter theme audit deferred. No schema / compute / data change; no schema bump.

**#1 — Selected-chip + solid-badge AA (light).** The soft-color override mapped
`.text-emerald-600` / `.text-emerald-700` AND `.bg-emerald-600` to `--c-pos-medium`
oklch(56%); on the `--c-pos-bg` oklch(97%) tint that text is **4.08:1** and white-on-the-
solid-badge is **4.40:1** — both under AA (WCAG-verified by `frontend-design-reviewer`
via sRGB linearisation, since `node_modules` is absent / no in-browser). Remapped those
3 override rules → `--c-pos-strong` oklch(50%) → **5.22:1** (text) / **5.64:1** (badge),
fixing TIERS exceptional/strong + MOS "Undervalued" + Rec "Buy" chips + filingLag <60d +
ScoreBadge ≥80 + the positive metric-delta text in ONE 3-line `globals.css` edit. Rose +
amber chips already passed (4.77 / 4.84:1) → untouched; bg-darkening was REJECTED (it
lowers the ratio — the tint is the lighter end). Dark side-effect: those classes now
resolve to dark `--c-pos-strong` oklch(72%) vs medium oklch(66%) — slightly brighter
emerald text on the deep dark chip bg, no contrast risk; flagged for a Vercel-preview eyeball.

**#2 — "Q" brand-mark dark sweep.** `Sidebar` + `AppShell` Q-logo used
`dark:bg-emerald-600` (decorative `aria-hidden`, contrast-exempt) → `dark:bg-emerald-700`,
so it reads as the brand primary `emerald-700` (`#047857`) in both themes (consistency, not a blocker).

**#3 — §Gotchas formalized.** New CLAUDE.md index line + `docs/GOTCHAS.md` detail for the
systemic finding behind #401's dark CTA: the `globals.css` soft-color `!important`
override is LITERAL-class-keyed → never reaches `dark:bg-emerald-*` / `dark:bg-rose-*`
solid-fills; a dark CTA / brand mark uses `dark:bg-emerald-700` or a `--c-*` token.

**Still deferred:** desktop filter IA (modal-drawer-only at every width → architectural;
its own PR with a design pass).

**Verification**: token/class-level edits; `next build` / `tsc` not run locally (no
`node_modules`) — CI Frontend build + the reviewer's WCAG computation cover it.

**Files**: `frontend/app/globals.css` (3-line override remap + comment) ·
`frontend/components/Sidebar.tsx` · `frontend/components/AppShell.tsx` · `CLAUDE.md`
(§Gotchas index) · `docs/GOTCHAS.md` (detail) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## Desktop filter IA — persistent left rail (in flight, 2026-06-03)

**Branch**: `claude/optimistic-fermat-lUTnF`
**Type**: feat(frontend) — FRONTEND-ONLY, no schema / compute / data change; no schema
bump. The last deferred item from the #401 filter critique (P1: a 502-row screener hid
filtering behind a modal drawer at EVERY width). Designed via `$impeccable shape`; user
chose Option A (persistent left rail).

**What**: on `xl+` (≥1280) the filter controls render as a PERSISTENT left rail beside the
ranking table (no modal / backdrop / scroll-lock) — the screener-canonical "filters always
visible" pattern. Below `xl` the existing modal `FilterDrawer` + its toolbar trigger are
unchanged. Breakpoint is xl not lg: at lg (1024-1279) a 288px rail squeezed the 7-col table
below its ~700px floor → immediate horizontal scroll (frontend-design-reviewer WARN; user
picked xl).

**Refactor (pure presentation; no filter LOGIC moved)**: the filter BODY (active-chips strip
+ search + composite `DualRange` + tier/rec/valuation/sector chips) was extracted into a new
`FilterControls.tsx` shared by BOTH shells, so the six groups live in ONE place.
`FilterDrawer.tsx` is now only the modal shell (focus-trap / scroll-lock / Esc / restore-focus
/ header count / footer Clear-all + "View N" CTA) wrapping `<FilterControls>`; it re-exports
`FilterState`/`FilterSetters` (canonical defs moved to FilterControls). New `FilterRail.tsx` =
`hidden xl:flex` `<aside aria-label="Filters">`, `w-72 xl:sticky xl:top-14
xl:max-h-[calc(100vh-4.5rem)]`, header count + scroll body + footer Clear-all (no modal
behaviors). `RankingTable` wraps `[FilterRail | content]` in an `xl:flex xl:items-start xl:gap-6`
row; the toolbar + page-level active-chips row get `xl:hidden` (rail replaces them at xl+); the
FilterDrawer + compare bar stay at the root (both `fixed`). The CLOSED drawer is set `.inert`
imperatively (a11y FAIL fix from review — without it the xl+ rail + the never-opened drawer
expose every filter button TWICE to a screen-reader / keyboard user). `FilterState`/`FilterSetters`
stay owned by RankingTable and threaded into both shells (controlled-view pattern).

**Verification**: `next build` / `tsc` NOT run locally (`node_modules` absent) — CI Frontend
build + `frontend-design-reviewer` static review + a Vercel-preview spot-check across
1440 / 1280 / 1024 / 768 / 375 (light + dark) before Mark-Ready. Lockstep satisfied via this
entry. (A §Gotchas line for the "FilterControls shared by FilterRail(xl+)/FilterDrawer(<xl)"
split is a candidate follow-up; the three component headers document it inline for now.)

**Files**: `frontend/components/FilterControls.tsx` (new) · `frontend/components/FilterRail.tsx`
(new) · `frontend/components/FilterDrawer.tsx` (rewritten as shell) ·
`frontend/components/RankingTable.tsx` (2-col layout + `xl:hidden` toolbar/chips) ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## docs: correct brand-primary hex mislabel (emerald-700 = #047857, not #15803D) (in flight, 2026-06-03)

**Branch**: `claude/optimistic-fermat-lUTnF`
**Type**: docs — DOC/COMMENT-ONLY, no code / schema / compute / data change; the one
`frontend/app/globals.css` edit is comment-only (no CSS rule / visual change).

The #401 filter theme audit surfaced (via `frontend-design-reviewer`) that the project
docs labeled the brand primary `#15803D` as `emerald-700` — but `#15803D` is Tailwind
**green-700**; `emerald-700` is `#047857`. `tailwind.config.ts` has no emerald override,
so `bg-emerald-700` (the View/Compare CTAs + the Q-mark) ships `#047857` (cooler emerald),
not the spec's forest `#15803D`. **Decision (user, 2026-06-03): Option A — bless the
shipped emerald**; fix the docs to the real hex rather than re-tint the app. No visual
change. Corrected: `docs/design.md` Primary `#15803D → #047857` + hover `#166534 → #065F46`
(green-800 → emerald-800) + a Hex note; `CLAUDE.md` §Stack + `AGENTS.md` §Phase-3d brand-
primary hex; `globals.css` soft-positive comment (the OKLCH band genuinely leans toward
forest `#15803D` = green-700 for CHIP surfaces — kept, now clearly distinguished from the
emerald-700 `#047857` SOLID CTAs). Lockstep: CLAUDE.md + AGENTS.md both carry the substance
edit (+ this entry).

**docs-reviewer follow-ups folded**: also corrected the ROOT `DESIGN.md` (impeccable
design doc — the same mislabel set was there: YAML `primary`/`primary-hover` + the "Forest
Green"/"Pine" names → Emerald + `#047857`/`#065F46`), fixed the inverted `#15803D` claim in
the #404 Q-mark inflight entry (→ emerald-700 `#047857`), and refreshed the stale
`docs/design.md` OKLCH table (hue 155 → 152 + chroma → current globals.css values) that sat
one section below the new Hex note. Pre-existing + tracked-not-fixed: the `docs/design.md`
Neutral row `#9CA3AF` (labeled ≈ slate-400, actually gray-400) and the merged
`.impeccable/critique/` snapshot's hex-ratio line (vendored output).

**Files**: `DESIGN.md` (root) · `docs/design.md` · `CLAUDE.md` · `AGENTS.md` ·
`frontend/app/globals.css` (comment-only) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## docs: design-doc cleanup — Neutral-row hex + 3-doc role map (in flight, 2026-06-03)

**Branch**: `claude/optimistic-fermat-lUTnF`
**Type**: docs + tool-config — `docs/design.md` + `.impeccable/design.json` (generated
config); no code / schema / compute / data change. Closes the pre-existing items the #406
brand-hex correction left tracked + the new one docs-reviewer found this round.

- **Neutral row**: the `docs/design.md` color table had `#9CA3AF` labeled `≈ slate-400`,
  but `#9CA3AF` is Tailwind **gray-400**; slate-400 is `#94A3B8`. The design system is
  slate-based throughout → corrected to `#94A3B8` / `slate-400` (label "(gray)" → "(slate)").
- **3-doc role map**: added a "Related design docs" note to `docs/design.md` (the canonical
  spec) clarifying the distinct roles of the repo's THREE design docs — `docs/design.md`
  (canonical), `DESIGN.md` (impeccable skill doc, machine-read subset), `ledgercraft-DESIGN.md`
  (upstream LedgerCraft source spec, provenance) — to head off the cross-doc drift that
  produced the brand-hex mislabel. NOT merged/deleted: each serves a distinct purpose.
- **`.impeccable/design.json`** (docs-reviewer follow-up — a tracked, generated tool-config
  carrying the SAME stale brand color, distinct from the `critique/` archive): `canonical` +
  `displayName` "Forest Green" `#15803D` → "Emerald" `#047857`; the `.ds-btn-primary` CSS
  (`#15803D`/`#166534` → `#047857`/`#065F46`); and the stale positive/negative OKLCH canonicals
  + tonal-ramp hues → current globals.css values (155 → 152; primary ramp hue 150 → emerald 165).
  Hand-fixed to match the now-correct `DESIGN.md` (a future `$impeccable document` regen derives
  the same); JSON re-validated.

**Left intentionally** (stated, not edited): the merged `.impeccable/critique/` snapshot's
stale hex-ratio line — that dir is an append-only timestamped archive, so editing it would
rewrite a historical record; the current canonical docs supersede it.

Lockstep: DOC-ONLY (not code / workflow / schema) — this entry covers it; no CLAUDE.md /
AGENTS.md substance change needed (no convention / gotcha / phase change).

**Files**: `docs/design.md` · `.impeccable/design.json` · `PHASE_STATUS_INFLIGHT.md` (this).

---

## Filter polish — dark placeholder AA + dual-range thumb focus (in flight, 2026-06-03)

**Branch**: `claude/beautiful-goldberg-ktA03`
**Type**: fix(frontend) — FRONTEND-ONLY, no schema / compute / data change; no schema bump.
`$impeccable polish` pass on the filter surfaces, layered on TOP of the merged #398–#407 filter
overhaul. Two net-new findings the #401 theme audit + #405 rail work did not cover (verified
against the merged code, not a duplicate — only open-PR check: none).

**#1 — Dark-mode search placeholder AA fail.** All THREE placeholder-bearing text inputs on these
surfaces (`FilterControls` rail/drawer search + `RankingTable` mobile-toolbar search + the
`CompareView` "Add tickers" input) carried `dark:placeholder-slate-500`; slate-500 on the
`dark:bg-slate-900` field is **3.75:1**, under the 4.5:1 AA floor PRODUCT.md mandates in BOTH
themes. (The #401 audit added the LIGHT `placeholder-slate-500` to the two filter inputs but read
the dark one as "already present" without measuring it; the CompareView input had neither token
audited.) Fixed all three to `dark:placeholder-slate-400` → **6.96:1** — the documented muted-text
pair (`text-slate-500 dark:text-slate-400`). The CompareView input also gained the LIGHT
`placeholder-slate-500` it was missing (light slate-500 = 4.76:1; matches the two filter inputs).
The third instance was folded in per the `quantrank-reviewer` WARN so the systematic AA fix isn't
left 2-of-3 done.

**#2 — DualRange keyboard focus + off-system thumb shadow.** Each handle is a full-width
transparent `<input type=range>`, so the global `:focus-visible` outline (globals.css) wrapped the
ENTIRE 0→100 track — a keyboard user saw an indigo line spanning the whole slider with no cue which
handle was active (WCAG 2.4.7 focus-visible, weak). Added `focus-visible:outline-none` on both
inputs + a soft indigo-500 halo (`box-shadow:0 0 0 3px rgba(99,102,241,.55)`) on the
`::-webkit-slider-thumb` / `::-moz-range-thumb` pseudo on `:focus-visible`, so focus now lands on the
actual thumb (verified light + dark — the halo reads on both the white and slate-900 thumb fills
with no theme-specific offset). Also replaced the thumb's raw Tailwind `shadow` (off-system per
design.md "Borders-As-Depth" — the 4 formal elevation tiers only) with `shadow-subtle`, the
hairline-lift tier, on both engines.

**#3 — Active-filter count badge `tabular-nums`.** The `FilterControls` "Active filters" header
count (a bare integer) rendered without `font-mono tabular-nums`, off the project's "every
number" / Tabular-Nums rule and inconsistent with the rail/drawer header counts; added them to
match (`frontend-design-reviewer` WARN, surfaced by this pass).

**Design-review WARN triage** (`frontend-design-reviewer` = READY-FOR-SPOT-CHECK, all 3 core
changes PASS): folded in #3 above. SKIPPED `dark:shadow-none` on the thumb (reviewer: "not
required" — `shadow-subtle` is perceptually invisible on the slate-900 dark thumb and the 2px
border carries the depth per Borders-As-Depth; a no-op). SKIPPED flipping the two search inputs'
`focus:outline-none` → `focus-visible:` (pre-existing, behavior-identical here — the only outline
in play is the global `:focus-visible` one and the inputs already carry a replacement
`focus:ring-1`; the slider needed the flip only because it had NO ring). REJECTED adding
`shadow-medium` to the FilterRail container — post-LedgerCraft NO resting surface carries a shadow
(design.md §Elevation: only the Overlay tier is live, on the FilterDrawer; the RankingTable
container is border-only too), so a resting shadow would violate the "Don't add shadow-medium to a
card/table" invariant.

**Verification**: `tsc --noEmit` clean; `next build` GREEN (507 pages, lint + types valid);
production-CSS grep confirms the focus-halo rule + `placeholder-slate-400` survive the purge;
Playwright contrast probe confirms dark placeholder 3.75 → 6.96:1, and light + dark slider-focus
screenshots confirm the halo on the thumb (full-width outline suppressed).

**Lockstep**: code PR, no new convention / gotcha → this entry satisfies the minimum (no CLAUDE.md /
AGENTS.md substance change). The DualRange focus mechanism is documented inline in the component.

**Files**: `frontend/components/DualRange.tsx` · `frontend/components/FilterControls.tsx` ·
`frontend/components/RankingTable.tsx` · `frontend/components/CompareView.tsx` ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## Filter polish round 2 — active-filter chip language + interaction-state audit (in flight, 2026-06-03)

**Branch**: `claude/beautiful-goldberg-ktA03`
**Type**: fix(frontend) — FRONTEND-ONLY, no schema / compute / data change; no schema bump.
`$impeccable polish` round 2 on the filter surfaces (follow-up to merged #408), user-directed.

**Active-filter chip language unified.** The active-filter "remove" chips rendered in TWO visual
languages: the `FilterControls` summary (rail + drawer) used a flat NEUTRAL chip with no dot, while the
`RankingTable` mobile toolbar used FULL type-colored tints (tier `t.cls` / mos `b.cls` / rec
`RECOMMENDATION_CHIP_TONES`). On mobile, opening/closing the drawer showed the same filters two ways.
Unified BOTH on the LedgerCraft-canonical "neutral steel body + colored leading dot" treatment (the
sector-chip pattern): a new shared `ACTIVE_FILTER_CHIP_TONE` token in `lib/visual.ts`; the panel summary
gains per-type dots (tier/mos/rec class dot + sector inline-rgb dot; search/score have no type → no dot);
the toolbar tier/mos/rec chips drop their full tint → neutral body + keep their dots. Chosen over
full-tint-everywhere because the summary sits directly above the full-tint *toggle* chips — neutral+dot
keeps the remove-summary distinct from the stateful toggles (no color doubling) while preserving
at-a-glance identity via the dot (which matters most in the toolbar, where no toggles are visible).
Removed the now-unused `RECOMMENDATION_CHIP_TONES` import from `RankingTable`.

**Interaction-state audit (no fixes needed).** Drove headless Playwright through the round-2 states the
user named: drawer focus-trap (22 tabs all stayed inside ✓, order Close → remove-chips → search → slider
→ toggles), long sector names ("Communication Services" — no clip / overflow / h-scroll in the w-72 rail
✓), reduced-motion (rail renders, slider focus halo works — focus is not motion-gated ✓). All pass; no
code change.

**Verification**: `tsc --noEmit` clean; `next build` GREEN (507 pages, lint + types valid); the shared
tone token ships in the bundle; light + dark screenshots confirm the rail summary + mobile toolbar now
render the identical neutral-body + colored-dot chip.

**Review (both gates)**: `quantrank-reviewer` = READY-TO-PUSH (all invariants pass; confirmed the sector
inline-rgb dot carve-out + that the `RECOMMENDATION_CHIP_TONES` removal is scoped to RankingTable).
`frontend-design-reviewer` validated the neutral+dot direction + token placement, found 1 FAIL + WARNs —
all folded: (1) the toolbar SECTOR remove-chip still inlined `${sty.bg} ${sty.fg} ${sty.ring}` instead of
the shared token (a token-drift trap if the tone is later tuned — functionally identical today since
sectors map to neutral) → switched to `${ACTIVE_FILTER_CHIP_TONE}` (dot kept); (2) the panel summary
hover was `hover:bg-slate-200` vs the SKILL.md-canonical `hover:opacity-75` for active-filter chips →
unified to `hover:opacity-75` (both contexts now match canonical); (3) added the quantrank-reviewer's
"exactly one of `dot`/`dotStyle`" hardening comment. DEFERRED (reasoned won't-fix): `tabular-nums` on the
"Score N–N" chip — it's a label-style chip (not a numeric column that stacks across rows), and `font-mono`
would wrongly mono-ify the "Score" word; a standalone chip gains no alignment from `tabular-nums`. Pre-
Mark-Ready: `vercel-preview-auditor` on the preview (the visual gate, per the design-reviewer handoff).

**Lockstep**: code PR, no new convention / gotcha → this entry satisfies the minimum (no CLAUDE.md /
AGENTS.md substance change; the shared token is self-documenting + commented in lib/visual.ts).

**Files**: `frontend/lib/visual.ts` (`ACTIVE_FILTER_CHIP_TONE`) ·
`frontend/components/FilterControls.tsx` (summary dots + shared tone) ·
`frontend/components/RankingTable.tsx` (toolbar chips → neutral+dot) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## Filter polish round 3 — toggle selected-state visibility (in flight, 2026-06-03)

**Branch**: `claude/beautiful-goldberg-ktA03` (PR #409, additional commit)
**Type**: fix(frontend) — FRONTEND-ONLY, no schema / compute / data change; no schema bump.
User-reported: the filter TOGGLE chips (tier / rec / valuation / sector) gave almost no signal that a
chip was selected ("กดแล้วมองไม่เห็นว่ากดยัง").

**Diagnosis** (Playwright + computed-style probe): selection relied ONLY on the pale tone tint — the
dot is present on selected AND unselected, so it never signalled selection. The tint was too subtle in
light, near-invisible in dark (`emerald-900/20` over `slate-800`), and for the slate-toned options
(Near fair / Hold) the selected tone IS slate → in dark it was byte-identical to unselected (zero
change), in light `slate-50` vs `slate-100` (almost nothing).

**Fix** (user-chosen "heavier ring + bold, no checkmark"; keeps outlined-light per SKILL.md "never
solid fill"): selected toggle = the tone tint + **bold label** + a **2px neutral inset ring** drawn via
`box-shadow` (NOT a Tailwind `ring-*` — box-shadow sidesteps the globals.css soft-color override that
remaps every `ring-*` color, so the selected ring is reliable and the SAME on every tone). The ring is
`slate-400`, which reads on BOTH the light pale tint and the dark slate-800 surface (one value, both
themes), so the slate-toned options now read as clearly selected too. DRY'd the 4 toggle groups
(tier/rec/mos/sector) through a `toggleChipClass(on, tone)` helper. No shared TIERS/MOS/REC token
touched → zero app-wide blast radius (the deferred #401 concern). Confirmed in-browser: light + dark +
the slate-toned worst case all read clearly.

**Review fixes folded** (`quantrank-reviewer` = READY-TO-PUSH; `frontend-design-reviewer` =
READY-FOR-SPOT-CHECK, 1 FAIL + WARNs, all addressed): (1) **[FAIL] `aria-pressed={on}`** added to all
4 toggle button groups — the ring/weight is visual-only, so a screen-reader user got NO selected
signal (the AT-equivalent of the bug this PR fixes for sighted users); (2) **[WARN] WCAG 1.4.11** —
slate-400 ring was ~2.7:1 on the light pale tint (under the 3:1 non-text-contrast floor); switched to
**slate-500** (`rgb(100,116,139)`, ~4.6:1 light / clearly visible dark) → one value still covers both
themes, and it reads MORE clearly (better serves the goal); (3) **[WARN]** extracted the raw-rgb ring
to a named `SELECTED_RING_SHADOW` const + tightened the rationale comment (the soft-override keys only
emerald/rose ring tones, NOT *every* `ring-*` — the real reason box-shadow wins is ring-collision with
the per-tone `ring-{tone}` + the `ring-1` shell); (4) **[WARN]** documented the new selected-state
treatment in `frontend-design-system/SKILL.md` §"Filter drawer selected-state chip" (font-semibold +
2px box-shadow ring + aria-pressed; no `ring-*`) so the next contributor doesn't regress it.

**Verification**: `tsc --noEmit` clean; `next build` GREEN (507 pages); `aria-pressed` ships in the
home HTML (verified `true` on selected / `false` on unselected) + the slate-500 inset-ring class ships
in production CSS; before/after + slate-500 screenshots (light / dark / slate-toned) confirm the fix.

**Files**: `frontend/components/FilterControls.tsx` (toggle helper + selected enhancement +
aria-pressed) · `.claude/skills/frontend-design-system/SKILL.md` (selected-state addendum) ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## Filter polish round 4 — composite-score slider thumb visibility (in flight, 2026-06-03)

**Branch**: `claude/beautiful-goldberg-ktA03` (PR #409, additional commit)
**Type**: fix(frontend) — FRONTEND-ONLY, no schema / compute / data change; no schema bump.
User-reported: the Composite Score `DualRange` slider HANDLES were invisible ("สีมันกลืนกับพื้นหลัง").

**Root cause**: the thumb fill was `bg-white dark:bg-slate-900` — the SAME color as the panel it sits
on (`bg-white dark:bg-slate-900`), so each handle camouflaged into the background (only the thin border
hinted at it). Confirmed in-browser at score=40-80 (interior thumbs, not edge-clipped): light = a
near-invisible white knob on white; dark = a near-invisible slate-900 knob on slate-950.

**Fix**: invert the thumb so the FILL contrasts the PANEL — `bg-slate-900 dark:bg-white` (dark knob on
the light panel / white knob on the dark panel) — and flip the border to the INVERSE
(`border-white dark:border-slate-900`) so the handle still separates from the same-colored active fill
bar (slate-900 light / slate-100 dark) where it rides. High contrast in both themes (~17:1), well past
WCAG 1.4.11. The #408 focus halo + `shadow-subtle` are unchanged.

**Verification**: `tsc --noEmit` clean; `next build` GREEN (507 pages); before/after slider screenshots
(light + dark, interior thumbs) confirm the handles are now clearly visible, solid, draggable knobs.

**Files**: `frontend/components/DualRange.tsx` (thumb fill/border inversion + comment) ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## Filter polish round 5 — comprehensive review a11y/contrast fixes (in flight, 2026-06-03)

**Branch**: `claude/beautiful-goldberg-ktA03` (PR #409, additional commit)
**Type**: fix(frontend) — FRONTEND-ONLY, no schema / compute / data change; no schema bump.
Folds the BLOCKER + MAJOR + cheap findings from a comprehensive `frontend-design-reviewer` pass over the
WHOLE filter page (it confirmed the slider / selected-state / placeholder fixes correct, and surfaced
the same class of camouflage/a11y bug proactively):

- **[BLOCKER] B1** — the dark rail "Clear all" DISABLED text was `dark:disabled:text-slate-600` =
  **2.36:1** on the slate-900 panel (camouflaged) → `dark:disabled:text-slate-500` = **3.75:1** (matches
  the app's disabled-text convention; visible-but-muted vs the enabled slate-400).
- **[BLOCKER] B2** — the `FilterControls` search `<input>` had no programmatic label (the `<label>` was
  an unassociated sibling → SR announced an unnamed field). Added `htmlFor="filter-search"` +
  `id="filter-search"`.
- **[MAJOR] M1** — the dark UNSELECTED toggle-chip ring was `dark:ring-slate-700` = **1.41:1** on the
  slate-800 chip → invisible boundary (WCAG 1.4.11). → `dark:ring-slate-500` = **3.07:1**. Scoped to
  `UNSELECTED_CHIP` (the interactive toggle chips) ONLY — NOT the app-wide `NEUTRAL_CHIP_RG` /
  `ACTIVE_FILTER_CHIP_TONE` (the #401 blast-radius trap; deferred). Verified the slate-toned SELECTED
  state (Near fair / Hold) STILL reads distinct after the unselected ring became visible — the
  `font-semibold` + 2px box-shadow ring carry it (screenshot-confirmed).
- **[MAJOR] M2** — tier / valuation chips announced "Exceptional70–100" (label + range run together for
  SR) → added `aria-label` (e.g. "Exceptional, score 70–100" / "Near fair, ±10% MoS").
- **[NIT] N2** — toolbar "Clear all" was `text-slate-500` = 4.41:1 (0.09 under AA) → `text-slate-600`
  (~5.9:1; also matches the rail "Clear all").

**Deferred (noted)**: N1 (the 4 chip-group heading `<label>`s are semantically inert — a `<span>` /
`role=group` refactor, pre-existing) · the app-wide `dark:ring-slate-700` neutral-chip ring on sector +
active-filter chips (`NEUTRAL_CHIP_RG` / `ACTIVE_FILTER_CHIP_TONE` — app-wide, its own pass).

**Verification**: `tsc --noEmit` clean; `next build` GREEN (507 pages); Playwright contrast probe
confirms B1 **3.75:1** / M1 **3.07:1**, the search input is programmatically labeled, and the tier
aria-label reads "Exceptional, score 70–100"; dark screenshot confirms unselected chip boundaries are
now visible AND the slate-toned selected stays distinct.

**Files**: `frontend/components/FilterControls.tsx` (B2 label · M1 ring · M2 aria-labels) ·
`frontend/components/FilterRail.tsx` (B1) · `frontend/components/RankingTable.tsx` (N2) ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## docs — record the #408/#409 color/UX mistake retro (in flight, 2026-06-04)

**Branch**: `claude/beautiful-goldberg-ktA03`
**Type**: docs — DOC-ONLY, no code / schema / compute / data / workflow change. Records the recurring
color/UX mistake class from the filter-page polish (#408 + #409) per user request ("บันทึกข้อผิดพลาด
ของการใช้สีและ UX ครั้งนี้").

`docs/LESSONS_LEARNED.md` gains a dated `2026-06-04` Mistakes-log entry (9 numbered lessons) + a TL;DR
bullet + 2 DON'T rows + 2 DO rows. The core lesson: a **foreground element whose color ≈ its background
camouflaged** — 5× across the session, every one in **dark mode** and/or a **non-default state**
(selected / disabled / interior-slider / slate-toned), all missed by static + per-commit review (3
found by the user). Generalized: never set fg = the surface's own token; verify **WCAG 1.4.11**
(non-text, ≥ 3:1 for rings/borders/thumbs) in BOTH themes + every state; a comprehensive whole-surface
browser contrast audit up front beats N per-commit round-trips. The actionable rule is mirrored into
`.claude/skills/frontend-design-system/SKILL.md` §Anti-patterns checklist (2 new bullets).

**Lockstep**: doc-only (no code / workflow / schema) → this entry covers it; no CLAUDE.md / AGENTS.md
substance change owed (the design rule lives in the frontend-design-system skill, its load-bearing home).

**Files**: `docs/LESSONS_LEARNED.md` · `.claude/skills/frontend-design-system/SKILL.md` ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## Deferred filter-polish cleanup — app-wide neutral-chip ring + filter group semantics (in flight, 2026-06-04)

**Branch**: `claude/beautiful-goldberg-ktA03`
**Type**: fix(frontend) — FRONTEND-ONLY, no schema / compute / data change; no schema bump. Closes the
two items the #409 comprehensive review DEFERRED (user: "ทำส่วนที่ค้างไว้ต่อ").

**#1 — app-wide neutral-chip ring contrast (the deferred half of #409 M1).** The dark neutral-chip ring
`dark:ring-slate-700` on the `dark:bg-slate-800` chip = **1.41:1** (invisible boundary, WCAG 1.4.11) is
the *whole-app* default — #409 fixed only the scoped `UNSELECTED_CHIP` to avoid blast radius. Bumped ALL
of it → `dark:ring-slate-500` (**3.07:1**) across the 9 files that carry it, so every neutral chip in the
one outlined-light family (Rule 2) gets a consistent visible dark boundary: `lib/visual.ts`
(`NEUTRAL_CHIP_RG` sector chips · `ACTIVE_FILTER_CHIP_TONE` active-filter chips · MOS "Near fair" tone ·
`filingLagBadge`) + `RecommendationBadge` (neutral) · `LossChanceBadge` · `ListingChips` ·
`FairPriceBarChart` (fair/outlier legend) · `CompareMatrix` · `CompareView` · `RankingTable`
(compare-pill). Light ring (`ring-slate-200`) left as-is (the chip-bg-vs-page diff carries the light
boundary; reviewer deemed it fine). Verified in the densest surface (ranking table, dark): chips read as
clean defined pills, not busy.

**#2 — filter group-heading semantics (the deferred N1).** The 5 filter group headings (Composite score /
Score tier / Recommendation / Valuation / Sectors) were bare `<label>`s with no associated control —
semantically inert, and SR never announced the grouping. Each `<label>` → `<span id="filter-*-label">`
and its control container → `role="group" aria-labelledby="filter-*-label"`, so a screen reader announces
e.g. "Score tier, group" on entry. (The Search `<label htmlFor>` is a real label → untouched.)

**Verification**: `tsc --noEmit` clean; `next build` GREEN (507 pages); dark screenshot confirms the
neutral chip boundaries are now visible app-wide (table sector chips / recommendation / loss-chance) and
the 5 `role=group`s resolve to their heading text. `frontend-design-reviewer` cross-surface pass
(table / detail / compare × both themes) = READY-FOR-SPOT-CHECK ("defined chips, not heavy"; light
unchanged).

**Review follow-on folded**: the reviewer caught that `PriceTimePeriodSelector`'s SELECTED
(`dark:ring-slate-600`/`bg-slate-800` = 1.93:1) + enabled-unselected (2.36:1) rings were ALSO < 3:1 —
the sed only caught its `slate-700` disabled state, leaving the disabled ring more visible than the
selected one. Bumped both `dark:ring-slate-600` → `dark:ring-slate-500` (3.07 / 3.75:1); the
selection signal is the bg-fill + text, so the ring bump doesn't blur selected-vs-unselected.

**Files**: `frontend/lib/visual.ts` · `frontend/components/{RecommendationBadge,LossChanceBadge,ListingChips,FairPriceBarChart,CompareMatrix,CompareView,RankingTable,PriceTimePeriodSelector}.tsx` (ring bump) ·
`frontend/components/FilterControls.tsx` (ring bump + 5 group `role=group`) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## Seeking-Alpha-style top market-stats bar + richer side nav (in flight, 2026-06-04)

**Branch**: `claude/confident-ramanujan-NgV5y`
**Type**: feat(frontend) — FRONTEND-ONLY, no schema / compute / data change; no
schema bump. User reference: the Seeking Alpha mobile site (a top market-ticker
strip + a multi-section slide-out side nav). User-chosen scope (3 AskUserQuestion
answers): top bar = **QuantRank's own stats** (not a market-index/commodity feed —
QuantRank is a weekly static export and cannot show a live futures ticker); side
nav = **add menu sections + new pages**; approach = **prototype UI first**.

**What** (prototype; derives REAL stats from the already-build-imported
`rankings.json`/`metadata.json` — no mock numbers, no new ingestion / data source /
schema field):
- **Top bar** `MarketStatsBar` — a thin, horizontally-scrolling "ticker" strip
  under the app header (Seeking-Alpha shape), filled with the universe snapshot:
  universe size · avg composite · median MoS (tone) · #flagged · today's top
  gainer + top loser (real `price_change_1d_pct`, emerald/rose + directional
  caret, links to `/stock/<T>`) · last-compute date. NOT live — the "Updated"
  item is the honesty anchor.
- **Side nav** — `Sidebar` gains `Browse` (Rankings / Sectors / Compare) +
  `Insights` (Top Movers) sections (was the single "Navigation" + Rankings);
  Resources unchanged. New inline-SVG icons; reuses the existing
  `SidebarSection`/`SidebarLink` (so the `data-rail` collapsed-rail + mobile-drawer
  invariants are untouched).
- **New routes** `/sectors` (GICS-sector cards: count / avg score / top name, sorted
  by avg score) + `/movers` (top-10 gainers / losers by day change) — both derive
  from `rankings.json` at build (no per-stock fetch).

**Architecture**: `MarketStatsBar` is a SERVER component, rendered in `layout.tsx`
and handed to the `'use client'` `AppShell` as a new `topBar?: React.ReactNode`
slot — NOT imported by AppShell — so `lib/data.ts` (fs + JSON imports) never enters
the client bundle. New derivation lives in `frontend/lib/market-stats.ts`
(`getMarketStats()`).

**Verification**: `tsc --noEmit` clean; `next build` GREEN (509 static pages:
502 stocks + home + compare + `/sectors` + `/movers` + not-found; `/sectors` +
`/movers` = `○ Static`); Playwright screenshots (mobile home + open drawer,
desktop home, `/sectors`, `/movers`; light) confirm the strip + new sections +
pages render with real data and cross-check (ticker "TOP GAINER TPL +9.7%" ==
`/movers` row 1). `frontend-design-reviewer` review in flight.

**Follow-ups**: wire the two reserved-feeling stats (week-over-week deltas on the
aggregate numbers) once a prior-run snapshot loader exists; a genuinely live /
intra-week market feed would be a separate observability-before-wiring PR (new
data source), not a tweak to this bar.

**Files**: `frontend/lib/market-stats.ts` (new) · `frontend/components/MarketStatsBar.tsx`
(new) · `frontend/app/sectors/page.tsx` (new) · `frontend/app/movers/page.tsx` (new) ·
`frontend/components/AppShell.tsx` (`topBar` slot) · `frontend/app/layout.tsx`
(pass `<MarketStatsBar/>`) · `frontend/components/Sidebar.tsx` (Browse + Insights) ·
`CLAUDE.md` (§Gotchas index) · `docs/GOTCHAS.md` (detail) · `AGENTS.md` (§Gotchas mirror) ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## Strip Compare + Filter + Resources from PR #412 (in flight, 2026-06-04)

**Branch**: `claude/confident-ramanujan-NgV5y` (PR #412, follow-up commit)
**Type**: refactor(frontend) — FRONTEND-ONLY, no schema / compute / data change; no
schema bump. User-directed scope reduction on the same PR ("เอา resources และรื้อ
compare stock ออก … Compare ลบทิ้งทั้งหมด … ลบ filter ทิ้งด้วย"); search is KEPT
(user chose "เก็บช่องค้นหาไว้" via AskUserQuestion).

**Removed — Compare feature (entirely):** deleted `frontend/app/compare/page.tsx`,
`frontend/components/CompareView.tsx`, `frontend/components/CompareMatrix.tsx`; pulled
the ranking-table multi-select checkboxes + the fixed "Compare (N)" action bar +
`selected`/`goCompare` state out of `RankingTable`.

**Removed — Filter screener (entirely; free-text search KEPT):** deleted
`frontend/components/{FilterControls,FilterDrawer,FilterRail,DualRange}.tsx` +
`frontend/lib/{filter-storage,filter-url}.ts`; pulled all filter state (sector / tier /
mos / recommendation sets + composite-score range), the multi-axis `filtered` logic
(now search-only), the sessionStorage+URL persistence, the active-filter chips, and the
Filters button out of `RankingTable`.

**Removed — Sidebar Resources + Compare nav:** the `Resources` section
(Methodology / Design / GitHub) + the `Compare` `Browse` item; nav is now Browse
(Rankings · Sectors) + Insights (Top Movers). Dropped the now-unused `@/lib/links`
`METHODOLOGY_URL` import.

**`RankingTable.tsx` rewritten lean** (938 → ~430 lines): free-text search + column
sort + pagination + FLIP reshuffle (now gated on `search`) + stagger entrance + desktop
table + mobile cards + empty-state (reworded "No stocks match your search" + "Clear
search"). Same row markup, minus the compare checkbox. SHARED helpers introduced by the
removed features but used elsewhere are RETAINED: `lib/flag-labels.ts` (`flagLabel` →
RiskSummaryCard + FairPriceCard) and `pillarColor` in `lib/visual.ts` (→ PillarRadarChart).
`lib/links.ts` left in place (now an orphaned `METHODOLOGY_URL` export — harmless, not
imported anywhere).

**Cross-branch note**: the in-flight Compare/Filter polish branches (`busy-newton-L6J56`,
`beautiful-goldberg-ktA03`, `optimistic-fermat-lUTnF`) become moot / conflicting if this
merges — flagged to the user (close those PRs). Several CLAUDE.md / docs/GOTCHAS.md /
AGENTS.md gotchas documenting the removed Compare/Filter code are now stale; the
always-loaded CLAUDE.md §Gotchas index lines are pruned in this commit, a full
`docs/GOTCHAS.md` + `AGENTS.md` sweep is a noted follow-up (docs-reviewer).

**Verification**: `tsc --noEmit` clean (after clearing stale `.next/types/app/compare`);
`next build` GREEN — **508 static pages** (`/compare` gone), `/` bundle 10.6 → 5.08 kB;
Playwright screenshots (mobile home search-only toolbar + drawer Browse/Insights,
desktop full-width table no filter-rail/compare-column) confirm no stranded UI.
`quantrank-reviewer` + `frontend-design-reviewer` review in flight.

**Files**: deleted `frontend/app/compare/page.tsx` ·
`frontend/components/{CompareView,CompareMatrix,FilterControls,FilterDrawer,FilterRail,DualRange}.tsx` ·
`frontend/lib/{filter-storage,filter-url}.ts`; rewrote `frontend/components/RankingTable.tsx`;
edited `frontend/components/Sidebar.tsx` (drop Resources + Compare) · `CLAUDE.md`
(§Gotchas index prune) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## Top tab nav (Home·Ranking·News·Analysis·Portfolio) + Home overview + placeholder pages (in flight, 2026-06-04)

**Branch**: `claude/confident-ramanujan-NgV5y` (NEW PR after #412 merged; branch
rebased onto post-merge `main`)
**Type**: feat(frontend) — FRONTEND-ONLY, no schema / compute / data change; no schema
bump. User reference: the Seeking Alpha mobile top-tab nav (Home·News·Analysis·
Portfolio). User-chosen scope (4 AskUserQuestion answers): top tabs COEXIST with the
existing sidebar ("keep both"); Home = overview/dashboard (not the table); Analysis +
Portfolio = "Coming soon" placeholders for now.

**What**:
- **`TopNav`** (new, client) — Seeking-Alpha-style horizontal tab bar Home · Ranking ·
  News · Analysis · Portfolio in the sticky header; active tab = emerald underline +
  `aria-current`; horizontal-scroll on mobile; 44px targets. Mounted as a SECOND header
  row in `AppShell` (the `<header>` became a 2-row column: controls row + tabs row),
  coexisting with the left-rail `Sidebar`.
- **Home `/` rewritten** as an overview dashboard: hero (universe stat + "View full
  ranking" CTA) + 3 preview cards — Top ranked (top-5 + `ScoreBadge`), Movers today
  (3 gainers / 3 losers from real `price_change_1d_pct`), Top sectors (top-4 by avg
  composite) — each links through to `/ranking` · `/movers` · `/sectors`. All derived
  from the build-imported `rankings.json` (no new data).
- **`/ranking`** (new) — the full `RankingTable` + the old home intro, moved here off
  `/`. The Sidebar `Rankings` item now points to `/ranking` (was `/`).
- **`/news` + `/analysis` + `/portfolio`** (new) — render the shared new `ComingSoon` placeholder
  (icon + "Coming soon" + detail + a `bg-emerald-700` / `dark:bg-emerald-700` "Browse
  the ranking" CTA). Portfolio is slated to become a localStorage watchlist, Analysis a
  distributions/methodology view — both deferred per the user.

**Verification**: `tsc --noEmit` clean; `next build` GREEN (`/`, `/ranking`, `/analysis`,
`/portfolio`, `/sectors`, `/movers`, `/stock/[ticker]` all static); Playwright
screenshots (mobile + desktop · home / ranking / analysis) confirm the tab bar (active
underline), the coexisting sidebar, the real-data overview cards, and the placeholder
pages render. `frontend-design-reviewer` review in flight.

**Files**: new `frontend/components/{TopNav,ComingSoon}.tsx` ·
`frontend/app/{ranking,news,analysis,portfolio}/page.tsx`; rewrote `frontend/app/page.tsx`
(Home overview); edited `frontend/components/AppShell.tsx` (2-row header + TopNav) ·
`frontend/components/Sidebar.tsx` (Rankings → /ranking) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## Full-width top chrome — sidebar moved BELOW the top bar (in flight, 2026-06-04)

**Branch**: `claude/confident-ramanujan-NgV5y` (PR #413, follow-up commit)
**Type**: refactor(frontend) — layout-only, no schema / compute / data change. User:
"แถบด้านข้าง ต้องไม่กินพื้นที่แถบด้านบน แต่กินพื้นที่แถบ home ได้".

`AppShell` was a `[Sidebar | (header + content)]` row — the full-height rail sat in
the top-left, squeezing the header / tab nav / market-stats strip to the RIGHT of it.
Restructured to a column: the **full-width top chrome** (sticky `<header>` controls-row
+ TopNav-row, then the MarketStatsBar strip) spans edge-to-edge ABOVE a
`[Sidebar | content]` row, so the sidebar only eats into the content width, never the
top bar. The desktop rail is now `md:sticky md:top-[calc(3.5rem_+_46px)]
md:h-[calc(100vh_-_3.5rem_-_46px)]` (was `md:top-0 md:h-screen`) — the offset = the
header height (controls `h-14`=3.5rem + the 44px tab row + 2px borders) so it sticks
flush UNDER the header. **Invariant**: if the header height changes (controls/tab row
height or borders), update the rail's `md:top` + `md:h` calc to match, or the rail gaps
/overlaps the header. The mobile drawer (`fixed inset-y-0`) is unchanged — a full-height
modal overlay on hamburger tap. The globals.css sidebar pre-paint (width/max-width-only)
is untouched.

**Verification**: `tsc --noEmit` clean; `next build` GREEN (512 pages); Playwright
screenshots — desktop top + scrolled-700px confirm the top bar stays full-width + sticky
and the rail sticks flush below it (no gap/overlap); mobile drawer still slides + works.

**Files**: `frontend/components/AppShell.tsx` (return restructure: full-width top chrome
+ `[Sidebar|content]` row; controls row `py-2` → `h-14`) · `frontend/components/Sidebar.tsx`
(rail `md:top`/`md:h` calc offset) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## Sidebar → overlay drawer + brand/toggle moved to the header (in flight, 2026-06-04)

**Branch**: `claude/confident-ramanujan-NgV5y` (PR #413, follow-up commit)
**Type**: refactor(frontend) — layout/interaction, no schema / compute / data change.
User: "เอาโลโก้กับชื่อออกจากแถบด้านข้าง ... โชว์โลโก้ชื่อด้านบนตลอด ... ย้ายปุ่มเปิดแถบ
ไปไว้หน้าโลโก้ ... เปลี่ยนเป็นสามขีด ... กดเปิดแล้วเป็น x". Desktop mode:
drawer-overlay-all-sizes (user choice via AskUserQuestion).

Converted the sidebar from a desktop-persistent collapsible rail + mobile drawer into
ONE overlay drawer on EVERY breakpoint (closed by default) — the Seeking-Alpha model:
- **Brand (Q + wordmark) moved to the header, ALWAYS visible** (was rail-only /
  mobile-wordmark-only); removed from the drawer.
- **One ☰/✕ toggle in the header, BEFORE the brand**, on every breakpoint — ☰ when
  closed, ✕ when open (`aria-expanded`). Replaces the old mobile hamburger + the
  desktop collapse chevron.
- **Drawer = `fixed left-0 top-[calc(3.5rem_+_46px)] bottom-0 w-64`** (BELOW the sticky
  header so the ✕ stays visible/clickable) + a backdrop at the same top offset; slides
  on `translate-x`; Esc + backdrop tap + nav-link tap close it; body-scroll-locked while
  open. Content is full-width at all sizes (no rail).
- **Removed the entire collapse machinery**: the `collapsed` state + localStorage
  persistence + the AppShell pre-paint sync, the `data-rail` / `data-sidebar-rail`
  attribute system, the layout.tsx pre-paint `<script>` (`quantrank.sidebar.collapsed`),
  and the `html.sidebar-collapsed` + `data-rail` block in `globals.css` (~52 lines). Net
  simplification.

**Stale gotcha pruned**: CLAUDE.md §Gotchas index line "Sidebar `data-rail` attrs ↔
`globals.css` pre-paint rules move in lockstep" removed (mechanism gone). The matching
`docs/GOTCHAS.md` detail + any AGENTS.md mirror are a noted follow-up sweep.

**Verification**: `tsc --noEmit` clean; `next build` GREEN (512 pages); grep confirms
ZERO residual `data-rail` / `sidebar-collapsed` / `collapsed`-prop refs; Playwright
(mobile + desktop, closed + open) confirms the header brand + ☰, the ☰→✕ flip, the drawer
opening BELOW the header with the ✕ still visible, and the empty drawer (no brand).

**Files**: `frontend/components/AppShell.tsx` (rewrite) · `frontend/components/Sidebar.tsx`
(rewrite) · `frontend/app/layout.tsx` (drop pre-paint script) · `frontend/app/globals.css`
(drop collapse/data-rail block) · `CLAUDE.md` (§Gotchas index prune) ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## Disclaimer banner → footer (in flight, 2026-06-04)

**Branch**: `claude/confident-ramanujan-NgV5y` (PR #413, follow-up commit)
**Type**: refactor(frontend) — layout-only, no schema / compute / data change. User:
"เอาแถบนี้ออก" (the top disclaimer banner). User choice: MOVE to footer (keep legal
coverage), not delete entirely.

The `<Disclaimer />` top banner (slate-50 strip + amber alert icon + a "more/less"
toggle, between the market-stats strip and the page content) was removed. Its FULL text
— including the previously-behind-"more" detail ("Scores and 'fair prices' are model
outputs … do not use for real-money trading decisions") — was moved into the `AppShell`
`<footer>` as plain muted text, so the regulated-style badges (Strong Buy / Sell) + Loss
Chance % keep their legal-safety coverage per frontend-design-system Rule 9. The
`Disclaimer.tsx` component is now orphaned → deleted. `LossChanceBadge` /
`RecommendationBadge` still call it the "global Disclaimer banner" in comments — accurate
as the legal-coverage relationship, but the "banner"/"top" wording (incl. Rule 9 in the
frontend-design-system skill) is a NOTED follow-up to reword to "footer disclaimer" so a
contributor doesn't re-add a top banner.

**Verification**: `tsc --noEmit` clean; `next build` GREEN (512 pages); Playwright
screenshots confirm the top banner is gone (the market-stats strip now sits directly
above the page heading) and the full disclaimer renders in the footer.

**Files**: `frontend/components/AppShell.tsx` (drop banner + import; footer gains the
disclaimer text) · `frontend/components/Disclaimer.tsx` (deleted) ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## De-brand the home/ranking copy off "S&P 500" (universe-agnostic) (in flight, 2026-06-04)

**Branch**: `claude/confident-ramanujan-NgV5y` (NEW PR after #413 merged; rebased onto main)
**Type**: refactor(frontend) — COPY-only, no schema / compute / data change. User: the scope
is expanding to ~5 countries, so the home page should not be branded "S&P 500".

Generalized the prominent user-facing copy so it doesn't hard-code the current single
universe, ahead of the multi-country data expansion (a separate Phase-5+ effort — NOT in
this PR). The CURRENT coverage stays honest via the DATA-DRIVEN provenance line
(`metadata.universe` still renders "SP500" on /ranking) — only the hard-coded brand strings
changed:
- Home (`app/page.tsx`): h1 "S&P 500, ranked." → "Equities, ranked."; title/description drop
  "US-equity" / "S&P 500" / the hard-coded "502".
- Ranking (`app/ranking/page.tsx`): KEPT "S&P 500 ranking" + the original description (user
  follow-up) — the /ranking page names the ACTUAL current universe; only the Home/brand
  surfaces are universe-agnostic.
- Sectors (`app/sectors/page.tsx`): "The S&P 500 universe…" → "The ranked universe…".
- `AppShell` header tagline "US equity stock ranking" → "Equity rankings".
- `layout.tsx` root metadata "Static-site US equity ranking…" → "…equity ranking…".
- `PillarRadarChart` "percentile rank against current S&P 500" → "…against the current universe".

Code COMMENTS that mention S&P 500 (types.ts / visual.ts / MoSCell) left as-is (accurate to
the current data). The actual 5-country ingest (new per-country universes, currency, non-US
filing sources) is a major separate effort to be scoped (financial-engineer).

**Verification**: `tsc --noEmit` clean; `next build` GREEN (512 pages); Playwright screenshots
confirm the home shows "Equities, ranked." with no S&P 500, and /ranking's data-driven
provenance still shows the current universe.

**Files**: `frontend/app/{page,ranking/page,sectors/page,layout}.tsx` ·
`frontend/components/{AppShell,PillarRadarChart}.tsx` · `PHASE_STATUS_INFLIGHT.md` (this).

---

## Country/market selector scaffold above the /ranking heading (in flight, 2026-06-04)

**Branch**: `claude/confident-ramanujan-NgV5y` (PR #414, follow-up commit)
**Type**: feat(frontend) — UI-scaffold only, no schema / compute / data change. User:
"ด้านบนคำว่า s&p500 จะมีปุ่มเรียงกันอยู่ … US / TH / CH / JP / [my pick]".

New `CountryTabs` row above the `/ranking` `<h1>`: a market selector for the planned
multi-country expansion. **US is the ACTIVE market** (it's the current data = the
S&P 500, emerald outlined-light pill labelled "US stocks"); **TH · CN · JP · UK are
disabled "Soon" placeholders** (no data yet). Flags via `country-flag-icons` per-country
STATIC imports (the project pattern). Decisions noted for the user: **"CH" read as China
(`CN`)** given the Asian context (CH = Switzerland officially); **the 5th market is UK
(`GB`)** — a placeholder pick, swap freely. Pure scaffold — the actual per-country ingest
(universes + filing sources + currency) is the separate Phase-5+ effort; the disabled pills
will become real market links when that data lands.

**Follow-up 1 — restyle to TopNav idiom** (user: "ทำหน้าตาแบบเดียวกับแถบ home ด้านบน"):
`CountryTabs` moved from outlined-light pills to the TopNav underline-tab idiom
(`border-b-2 -mb-px` emerald active underline, muted disabled tabs, container `border-b`
baseline, horizontal scroll). Labels shortened "US stocks" → "US".

**Follow-up 2 — index/universe sub-row** (user: "ด้านล่างปุ่ม country stock จะมีแยกเป็น
all stock|s&p500|NASDAQ 100 และอื่นๆ จะเปลี่ยนไปในแต่ละประเทศ"): new
`frontend/components/IndexTabs.tsx` — a row beneath the country tabs listing the indices for
the active country. Full US benchmark set (user "ปรับ index list ให้ครบ"): All stocks ·
**S&P 500 (active)** · S&P 400 · S&P 600 · NASDAQ 100 · NASDAQ Composite · Dow 30 ·
Russell 1000 · Russell 2000 · Russell 3000 — the row scrolls horizontally (scrollbar hidden).
Index list keyed per country (`INDICES_BY_COUNTRY`) for the expansion; only US reachable
today, only S&P 500 has data (= the active item, honest). Idiom iterated twice: (a) first shipped as
secondary PILLS; `frontend-design-reviewer` flagged the `bg-emerald-700` solid-fill active
pill as the SKILL.md Rule 2 / PR #68 anti-pattern → swapped to the outlined-light emerald
"bullish" tone + `font-semibold` + dot (re-review PASS); (b) user then asked for the SAME
design as the buttons above ("ใช้ design แบบเดียวกับปุ่มด้านบน") → restyled to the CountryTabs /
TopNav underline-tab idiom verbatim (active = emerald `border-b-2` underline + darker text, no
fill — so it does NOT reintroduce the solid-fill anti-pattern). The two underline rows stay
distinguishable by content (countries carry flags; indices are text labels) + position.
`aria-current="true"` kept (selection indicator in a `role="group"`, not a page-nav link).

**Verification**: `tsc --noEmit` clean; `next build` GREEN (512 pages); Playwright shots
(light + dark) confirm the two-tier selector renders above "S&P 500 ranking" — country
underline tabs (US active) over index underline tabs (S&P 500 active) + the rest "soon".

**Files**: `frontend/components/CountryTabs.tsx` (new, then restyled) ·
`frontend/components/IndexTabs.tsx` (new) · `frontend/app/ranking/page.tsx`
(render both rows above the header) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## Remove the MarketStatsBar strip under the top nav (in flight, 2026-06-04)

**Branch**: `claude/confident-ramanujan-NgV5y` (PR #414, follow-up commit)
**Type**: feat(frontend) — UI removal only, no schema / compute / data change. User:
"เอาแถบใต้ home ออก" (remove the bar under the Home/top nav).

Removed the Seeking-Alpha-style universe-snapshot strip (`MarketStatsBar`) that sat
directly below the top tab nav on every page (it was added in PR #412, the same
session's earlier scope). Deleted `frontend/components/MarketStatsBar.tsx` +
`frontend/lib/market-stats.ts` (both now fully dead — grep confirms no other importer);
unwired it from `frontend/app/layout.tsx` (dropped the `<MarketStatsBar/>` import +
render) and removed the now-unused `topBar?: React.ReactNode` slot from
`frontend/components/AppShell.tsx`. The top tab nav now sits directly above the page
content; the header's `border-b` is the divider. The `/sectors` + `/movers` routes are
UNAFFECTED — they derive from `rankings.json` independently (not via `market-stats.ts`).

**Docs**: the now-stale `MarketStatsBar` gotcha was rewritten in lockstep across
`CLAUDE.md` (§Gotchas index) + `docs/GOTCHAS.md` (detail) + `AGENTS.md` (mirror) — kept the
still-valid invariant (build-time server-component stats; never `import lib/data.ts` into a
`'use client'` component; `/sectors` + `/movers` derive from `rankings.json`), dropped the
deleted-component specifics, and noted the removal. The PR #412 historical inflight entries
above are left intact (append-only record).

**Verification**: no residual `MarketStatsBar` / `market-stats` / `topBar` refs (grep clean);
`tsc --noEmit` clean; `next build` GREEN (512 pages); Playwright shots (home + ranking,
light + dark) confirm the strip is gone and the nav sits directly above the content.

**Files**: `frontend/app/layout.tsx` · `frontend/components/AppShell.tsx` ·
`frontend/components/MarketStatsBar.tsx` (deleted) · `frontend/lib/market-stats.ts` (deleted) ·
`CLAUDE.md` · `docs/GOTCHAS.md` · `AGENTS.md` · `PHASE_STATUS_INFLIGHT.md` (this).

---

## Remove the overlay Sidebar drawer — TopNav is the sole nav now (in flight, 2026-06-04)

**Branch**: `claude/confident-ramanujan-NgV5y` (PR #414, follow-up commit)
**Type**: feat(frontend) — UI removal only, no schema / compute / data change. User:
"เอาแถบด้านข้างออก" (remove the sidebar).

Removed the overlay Sidebar drawer (Browse: Rankings + Sectors · Insights: Top Movers ·
footer: theme toggle + build-version chip) and its ☰/✕ header toggle. Deleted
`frontend/components/Sidebar.tsx`; stripped ALL drawer machinery from
`frontend/components/AppShell.tsx` (the `open` state, `toggleRef` / `wasOpenRef`, the
body-scroll-lock / Esc-close / focus-restore effects, the ☰ button, the `<Sidebar/>`
render) — AppShell is now a plain **Server Component** (no `'use client'`, no hooks). The
TopNav tab bar (Home · Ranking · News · Analysis · Portfolio) is the SOLE navigation surface.

**Build-version chip relocated, NOT dropped**: the build-time `NEXT_PUBLIC_APP_VERSION`
chip moved from the Sidebar footer into the page footer (`AppShell`), so build provenance
stays visible. The `next.config.js` git-describe→SHA wiring is unchanged; the
gotcha was updated in lockstep (`CLAUDE.md` §Gotchas index + `docs/GOTCHAS.md` detail:
consumer Sidebar.tsx → AppShell footer). Stale TopNav header comment ("alongside the
left-rail Sidebar, keep both") corrected.

**Orphaned routes — OPEN QUESTION for the user**: `/sectors` + `/movers` were reachable
ONLY from the Sidebar; with it gone they build fine but have no nav entry. NOT resolved in
this commit — pending the user's call (add to TopNav / delete the pages / leave URL-only).

**Verification**: no residual `Sidebar` / `sidebar-drawer` / `topBar` import refs (grep
clean); `tsc --noEmit` clean; `next build` GREEN (512 pages); Playwright shots confirm the
header has no ☰ button (starts at the brand) and the version chip renders in the footer.

**Files**: `frontend/components/AppShell.tsx` · `frontend/components/Sidebar.tsx` (deleted) ·
`frontend/components/TopNav.tsx` (comment) · `CLAUDE.md` · `docs/GOTCHAS.md` ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## Delete the standalone /sectors + /movers routes (in flight, 2026-06-04)

**Branch**: `claude/confident-ramanujan-NgV5y` (PR #414, follow-up commit)
**Type**: feat(frontend) — route removal only, no schema / compute / data change.
User: "ลบทั้ง 2 หน้า" (delete both pages) — chosen via AskUserQuestion after the Sidebar
removal orphaned them (they were reachable ONLY from the now-deleted Sidebar nav).

Deleted `frontend/app/sectors/page.tsx` + `frontend/app/movers/page.tsx` (route count
512 → 510). Both were self-contained (only `getRankings` from `lib/data` + `sectorStyle`
from `lib/visual`, both shared + still used elsewhere — `sectorStyle` by the home Top-sectors
card + `SectorChip` on the detail page), so no exclusive component/lib was orphaned.

**Home page dead-link fix**: `frontend/app/page.tsx` had two preview cards ("Movers today"
→ `/movers`, "Top sectors" → `/sectors`) whose "All movers / All sectors →" links now point
at deleted routes. Made `OverviewCard`'s `href` + `linkLabel` OPTIONAL and dropped them from
those two cards — the cards KEEP their inline data preview (gainers/losers + top sectors,
both derived from `rankings.json`) but no longer render a dead "see all" link. The "Top
ranked" card keeps its `/ranking` link. (Kept the preview cards because the user deleted the
PAGES, not the home dashboard — flagged to the user as easily reversible.)

**Docs**: the build-time-server-component gotcha (rewritten in the prior MarketStatsBar-removal
commit to cite `/sectors` + `/movers` as the surviving example) was updated AGAIN across
`CLAUDE.md` (§Gotchas index) + `docs/GOTCHAS.md` (detail) + `AGENTS.md` (mirror) to use the
home + ranking pages as the example, and to record the `/sectors` + `/movers` removal.

**Verification**: no residual `/sectors` / `/movers` route refs (grep clean; `sectorStyle`
symbol refs are the shared lib, correctly kept); `tsc --noEmit` clean; `next build` GREEN
(510 pages, no `/sectors` or `/movers` in the route table); Playwright shot confirms the home
Movers / Sectors cards render their data inline without the dead "see all" links.

**Files**: `frontend/app/page.tsx` · `frontend/app/sectors/page.tsx` (deleted) ·
`frontend/app/movers/page.tsx` (deleted) · `CLAUDE.md` · `docs/GOTCHAS.md` · `AGENTS.md` ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## Phase 7.0 PR-0 — survivorship membership-ledger rebuild (in flight, 2026-06-04)

**Branch**: `claude/loving-clarke-kAZII`
**Type**: fix(data) + test — rebuilds `data/sp500_membership_historical.csv` (the
survivorship-bias ledger consumed by `compute/ingest/historical_universe.members_at`); no
schema / compute-logic / frontend change; no schema bump. First PR of the **Phase 7.0
AI-pick point-in-time portfolio-backtest** epic — the methodology-scientist BLOCKING PR-0
gate (the ledger must be verified before any backtest leg is trusted).

**Why**: a multi-agent design pass (financial-engineer -> methodology-scientist) found the
prior ledger materially broken, far beyond the one known BLK/BX bug: ~30 errors + ~110
missing events over 2020-2026. Confirmed defects: `BLK,ADD,Blackstone` (BLK = BlackRock, a
longtime member; Blackstone = BX) + the missing paired ABNB add; a BOGUS `2024-08-30 BLL`
removal (Ball never left -- BLL->BALL was a 2022 ticker rename); KDP/UA/UAA dates
self-contradictory; the SBNY (Signature Bank) 2023-failure removal MISSING; the 2020-06-22
add trio scrambled (real = TYL/TDY/BIO). The Phase 4.6 survivorship harness has therefore
been running on corrupt membership the whole time.

**What**: full 2020-04 -> 2026-05 rebuild, triangulated across S&P DJI press releases + the
fja05680/sp500 maintained change-CSV + Wikipedia (each load-bearing 2021-06+ event confirmed
by >=2). 214 events, ADD/REMOVE perfectly balanced (107/107). SVB->SIVB ticker + 03-13->03-15
effective-date fix. Per-row source_url normalized to the Wikipedia change-history table (the
research pass's per-event `press.spglobal.com/<date>-<title>` URLs 404 -- wrong format; the
DATA was triangulated, but we cite the source that resolves).

**Integrity gate (new)**: `scripts/verify_membership_ledger.py` reverse-walks `members_at`
from the live 502-ticker universe across every month of the 2021-06->2026-06 window and
asserts (a) the reconstructed S&P 500 size stays in band (498-506; observed worst 504) and
(b) every removed ticker is absent from / every added ticker present in the current universe.
Runs CLEAN. Two consumer tests updated for the corrected SVB->SIVB / 03-15 data; all 31
historical-universe + universe-drift tests pass; `ruff check .` clean.

**Residual / caveats**: the 2026-06-02 FedEx Freight (FDXF) spinoff / EPAM removal is DROPPED
-- it postdates the 2026-06-03 cron universe anchor (FDXF not yet in rankings.json), so
including it would corrupt the reversal; it re-enters when the cron picks it up. Pre-2021
1-sided 2020 spinoffs (OTIS/CARR) are slightly unbalanced (outside the backtest window). JBL
+ ALK placed at the web-confirmed 2023-12-18 rebalance (SEDG exit date confirmed). Renamed-
then-departed names use ONE ticker for the add/remove pair (CDAY for Ceridian/Dayforce) since
`members_at` does not apply rename aliasing.

**Files**: `data/sp500_membership_historical.csv` · `scripts/verify_membership_ledger.py`
(new) · `tests/test_ingest/test_historical_universe.py` ·
`tests/test_validation/test_universe_drift.py` · `CLAUDE.md` (§Gotchas index) ·
`docs/GOTCHAS.md` (detail) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## Phase 7.0 PR-1 — benchmark index export (in flight, 2026-06-04)

**Branch**: `claude/loving-clarke-kAZII` (PR #416, additional commit)
**Type**: feat(compute) + schema — exports the benchmark index series for the
portfolio-backtest comparison chart; schema PATCH `0.10.13 -> 0.10.14-phase4.6`
(additive `Metadata.benchmark_coverage_pct`). Observability-before-wiring: the
data file + coverage metric ship now; the home page reads them in PR-4. No
scoring / ranking / veto impact (display-only).

`compute/ingest/prices.py` gains `BENCHMARK_TICKERS = (SPY, QQQ, DIA, IWM)` +
`fetch_benchmarks()` (per-symbol graceful-degradation try/except; SPY shares the
warm price cache with the existing beta fetch). `compute/output/writer.py` gains
`write_benchmarks_json()` -> `frontend/public/data/portfolio/benchmarks.json`
(column-major `{dates, spy, qqq, dia, iwm}`, Adj-Close-preferred, ~5y tail aligned
to the union of trading dates, NaN/missing -> null), returning `(path, coverage_pct)`.
`main.py` wires the fetch+write right after the SPY beta fetch and surfaces
`benchmark_coverage_pct` on `Metadata`.

The financial-engineer's "drift-detector manifest" scout step does NOT apply here
-- yfinance is already a load-bearing dep (no new external-API surface to lock);
the lightweight `BENCHMARK_TICKERS` manifest test + the coverage metric are the
appropriate guards.

**Verification**: schema triple regenerated + in sync (`schema_check`); `ruff check .`
clean; new tests pass (`write_benchmarks_json` shape / union-dates / NaN->null /
all-empty->None + `fetch_benchmarks` per-symbol / exception-swallow + `test_config`
version bump) -- 32 passed locally. The live SPY/QQQ/DIA/IWM fetch + the actual
benchmarks.json run on the weekly cron (sandbox has no network / price cache). The
remaining offline-suite collection errors are pre-existing missing-dep (edgar/scipy),
unrelated to this change.

**Files**: `compute/ingest/prices.py` · `compute/output/writer.py` · `compute/main.py`
· `compute/config.py` (version) · `compute/output/schemas.py` · `frontend/lib/types.ts`
· `frontend/lib/schema-snapshot.json` · `tests/test_output/test_writer.py` ·
`tests/test_ingest/test_benchmarks.py` (new) · `tests/test_config.py` ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## Phase 7.0 PR-2a — AI-pick selection + inverse-vol weighting engine (in flight, 2026-06-04)

**Branch**: `claude/loving-clarke-kAZII` (PR #416, additional commit)
**Type**: feat(compute) — new pure `compute/portfolio/` package; no schema /
frontend / data change; no schema bump. The deterministic, I/O-free CORE of the
"fair AI-pick + auto-weight" — the same functions serve the forward cron pick and
the point-in-time backfill (PR-2b). methodology-scientist RATIFIED the priors
(2026-06-04).

`compute/portfolio/weights.py`:
- `select_picks(candidates, count)` — composite desc -> exclude the 7 active
  rank-gate VETOES (annotate flags don't exclude) -> cap 2/GICS-sector for
  count>=5 -> backfill if the cap leaves the basket short; tiebreak
  `composite_score_adjusted` desc then ticker asc; count clamped [1, 10]. Reads
  ONLY ranking+detail fields (`PickCandidate`).
- `inverse_vol_weights(sigmas, cap=0.35)` — w_i prop 1/sigma_i, capped +
  renormalized to sum 1 via PERMANENT pinning (a capped name never re-absorbs
  residual -> no above-cap oscillation); infeasible cap (N*cap<1, e.g. N<3)
  degrades to equal weight. Anchors: AFP 2012 / Frazzini-Pedersen 2014 BAB /
  DGU 2009. NOT composite-proportional (ordinal-scale error).
- `trailing_return_sigma(closes, window=90)` — sample stdev of trailing daily
  returns (stdlib `statistics`; null / non-positive prices dropped).

**Verification**: 19 offline tests pass (selection ordering / veto exclusion /
sector-cap binding at count>=5 / count clamp / tiebreak; inverse-vol sum=1 / cap /
infeasible-degrade / bad-sigma-drop + a Hypothesis property `sum(w)=1 & w<=cap when
feasible`; sigma edge cases). `ruff check .` clean. Pure functions -> no look-ahead
surface (the leak-probe lives in PR-2b's point-in-time backfill).

**Next (PR-2b)**: wire the forward pick into main.py (`StockSummary.suggested_weight`
from the warm price cache) + the `Metadata.portfolio_backtest_*` diagnostics +
`scripts/backfill_portfolio_pit.py` (point-in-time NAV backfill; runs on
`workflow_dispatch`, needs the 5y price cache — cron-side).

**Files**: `compute/portfolio/__init__.py` (new) · `compute/portfolio/weights.py`
(new) · `tests/test_portfolio/test_weights.py` (new) · `PHASE_STATUS_INFLIGHT.md`
(this).

---

## Phase 7.0 PR-2b — point-in-time portfolio backtest engine (in flight, 2026-06-04)

**Branch**: `claude/loving-clarke-kAZII`
**Type**: feat(compute) — backtest engine modules + tests; no schema bump YET (the
`Metadata.portfolio_backtest_*` observability fields + the `backtest_pit.json` model land
with the orchestrator). Builds on the merged Phase 7.0 foundation (#416).

**Goal**: the offline-verifiable HEART of the point-in-time 5-year backtest backfill, built
ahead of the (locally-unverifiable) orchestrator that wires the caches.

- **NAV engine** (`compute/portfolio/backtest.py`) — pure, pandas-free: `quarterly_rebalance_dates`
  + `build_portfolio_nav` (buy-and-hold drift, gross + net-of-turnover-cost per NMV 2016,
  delisting carry-forward, weight renormalization) + `rebase`. 10 tests.
- **PIT-fundamentals guardrail** (`compute/portfolio/pit_fundamentals.py`) — the
  methodology-scientist's #1 silent-look-ahead point: select only annual 10-K facts with
  `filing_date <= T` (amendments excluded, latest FY), so re-scoring at a historical date
  can't read a later filing. Pure + offline-testable; 9 tests incl. the mandated
  future-blockbuster leak-probe.

**Methodology re-ratification (2026-06-04)**: the full live 8-pillar composite is NOT
point-in-time reconstructable (its flow pillars read a TTM snapshot assembled from the
LATEST filings — unreplayable offline without paid vintage data). methodology-scientist
RATIFIED **Option A**: rebuild a synthetic snapshot from ANNUAL (10-K) fundamentals filed<=T
and re-run the EXISTING pillar pipeline (the only cross-sectional op, `normalize_metric`, is
within-cohort -> point-in-time honest). All 8 pillars included; two mandatory guardrails
(history filed<=T before Piotroski/CAGR; `current_price` = price-at-T). Relabel as a
"point-in-time proxy" (annual-not-TTM, sector-stable-from-today) + the McLean-Pontiff decay
banner.

**Now COMPLETE in this PR** (was "remaining"): the orchestrator
`scripts/backfill_portfolio_pit.py` (`members_at(T)` cohort -> synthetic PIT snapshot +
filed<=T history frame [guardrail 1] + price-at-T [guardrail 2] -> `compute_all_pillars` ->
frozen composite -> `select_picks` (10 holdings, sigma stored) -> `inverse_vol_weights` ->
`build_portfolio_nav` (headline-5; gross/net/conservative) vs benchmark NAVs -> write via
`writer.write_backtest_pit_json`), the `align_benchmark_nav` helper, and the
`.github/workflows/backfill-portfolio.yml` `workflow_dispatch` (warm-cache restore, env-proxy
inputs, `if: github.ref_name != 'main'` guard — security-reviewer FAIL fixed + W1 docs). The
artifact SELF-CARRIES its `meta` block (window + canaries + disclaimer) so NO schema-triple
change / version bump is needed (standalone dispatch, not the cron).

**Validation**: `ruff check .` clean; FULL offline suite **1510 passed / 13 skipped** (deps
installable in-env); 42 `tests/test_portfolio/` pass — incl. `test_backfill_integration.py`
that runs `run_backfill` end-to-end on a synthetic universe through the REAL pillar pipeline
(the wiring the sandbox couldn't exercise before). quantrank-reviewer READY-TO-PUSH (0 FAIL).

**Deferred to follow-up (PR-2c / disclosed)**: the actual 5y `backtest_pit.json` DATA comes
from a CI `workflow_dispatch` run AFTER this merges (a dispatch trigger only registers once
the workflow file is on `main`); the point-in-time defense-layer VETO replay
(`meta.veto_layer_replayed = False` today — composite-rank + sector-cap only); the optional
`Metadata.portfolio_backtest_*` mirror; and a methodology-scientist check that
`restatement_contamination_pct` lands low on the first real run.

**Files**: `compute/portfolio/backtest.py` (new · NAV engine · 15 tests) ·
`compute/portfolio/pit_fundamentals.py` (new · PIT guardrail · 10 tests) ·
`scripts/backfill_portfolio_pit.py` (new · orchestrator) · `compute/output/writer.py`
(`write_backtest_pit_json`) · `.github/workflows/backfill-portfolio.yml` (new) ·
`tests/test_portfolio/{test_backtest,test_pit_fundamentals,test_backfill_integration}.py`
(new · 27 tests) · `CLAUDE.md` + `AGENTS.md` (§Commands + §Security · W1) ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## Phase 7.0 PR-4 — AI-pick home page (backfill self-sufficiency + real data + frontend) (in flight, 2026-06-05)

**Branch**: `claude/loving-clarke-kAZII` (continues post-#417-merge)
**Type**: ci + feat(frontend) — starts with a backfill-workflow tweak so a SINGLE dispatch
yields a benchmark-complete artifact; grows to the real 5y `backtest_pit.json` data + the
AI-pick home page that renders it. No schema bump (the artifact self-carries its `meta`).

**Step 1 (this commit) — backfill self-sufficiency.** The merged backfill workflow READS
`frontend/public/data/portfolio/benchmarks.json` for the SPY/QQQ/DIA/IWM comparison lines
but does NOT produce it — that file is a weekly-cron output (`compute/main.py`
`write_benchmarks_json`), and the cron that introduced the writer (#416) has not committed
it yet (last data commit `531b4a5d` predates the writer). A dispatch today would emit a
backtest with EMPTY comparison lines; the next cron is ~17h out. Fix: a new
`Generate benchmark series (benchmarks.json)` workflow step regenerates it via the SAME
trusted code path as the cron (`fetch_benchmarks()` + `write_benchmarks_json()`, 4 yfinance
close-series) right before the backfill runs, and the commit step's `git add` is broadened
from the single `backtest_pit.json` to the whole `portfolio/` dir so BOTH artifacts land.
Self-contained, no cron-timing dependency, no merged-orchestrator code touched.

**Step 2 — NAV per holding count (Option A, user-chosen).** The user chose the faithful
reading of "ปรับ 1-10 ตัวแล้ววัดผล": the 1-10 slider re-runs the backtest LINE, not just the
holdings list. The orchestrator now, at each rebalance, inverse-vol weights the top-N picks
for EVERY N=1..MAX_PICKS, and the artifact stores a daily NAV series per count —
`nav.by_count["1".."10"]`, each `{gross, net, net_conservative, turnover_by_rebalance}` —
sharing one `dates` axis + the rebased `benchmark` lines. Each rebalance also stores its
ranked `holdings` (ticker/score/sector/sigma_90d) + `weights_by_count`, so the picks panel
needs no client-side weight re-derivation. Also fixes a latent NAV bug: a rebalance dated on
a weekend (quarter-end + 45d) is now SNAPPED to the next trading day (decide-at-T,
trade-next-open) instead of being silently dropped by `build_portfolio_nav` (which requires
the as-of date to be in the price calendar). `HEADLINE_COUNT` → `DEFAULT_COUNT` (5, the
slider's landing position, not a cap); the restatement-contamination canary now tracks the
full top-`MAX_PICKS` selectable set. +5 net-new tests (per-N alignment + down-name drag,
weekend-snap, sigma-empty leg-skip distinct from the membership-degraded skip, snap
fallback-to-last + empty→None — the last three from the test-engineer pre-push gate); the
integration test updated to the new shape. `ruff` clean; full offline suite green.

**Next on this branch**: dispatch the backfill (`ref=claude/loving-clarke-kAZII`) → review
the canaries (`incomplete_membership_count` / `restatement_contamination_pct` /
`rebalance_count` / NAV sanity, methodology-scientist on the contamination figure) → build
the AI-pick home (`frontend/app/page.tsx`: count slider 1-10, benchmark selector,
multi-timeframe NAV-vs-index chart, McLean-Pontiff disclaimer) consuming `backtest_pit.json`
+ `benchmarks.json` + new `frontend/lib/types.ts` backtest types.

**Files (steps 1-2)**: `.github/workflows/backfill-portfolio.yml` (benchmark-gen step +
`git add` broadened) · `scripts/backfill_portfolio_pit.py` (per-N NAV + trading-day snap +
`weights_by_count`) · `tests/test_portfolio/test_backfill_integration.py` (new-shape asserts
+ 5 net-new tests: per-N alignment, weekend-snap, sigma-empty skip, snap fallback/empty) ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## Phase 7.0 PR-3 — re-source restatement canary + dynamic disclaimer + first real 5y backtest data (in flight, 2026-06-05)

**Branch**: `claude/loving-clarke-kAZII` (post-#418-merge; carries the workflow_dispatch data commit)
**Type**: fix(compute) + data — orchestrator canary re-source + result-dependent disclaimer +
the committed `backtest_pit.json` / `benchmarks.json`. No schema change (artifact self-carries meta).

The FIRST real backfill dispatch (run #2, branch ref, green 11m58s) produced a complete artifact:
20 quarterly rebalances 2021-08→2026-06, NAV per count N=1..10 + SPY/QQQ/DIA/IWM benchmarks
(100% coverage). methodology-scientist validated it **PUBLISHABLE WITH 2 fixes** (NAV / selection /
survivorship / PIT-guardrails APPROVED-AS-HONEST — the default N=5 net 132.8 lagging SPY 180.8 is
the EXPECTED quality/value-tilt + 2-per-sector-cap lag in a 2021-26 mega-cap-momentum regime per
Lakonishok-Shleifer-Vishny 1994, not a bug; N=1 −62% is the sane concentration tail; N=5 default
is the pre-committed, non-cherry-picked landing). The 2 required fixes (user chose the accurate
option — re-source + re-dispatch):

1. **Restatement canary re-sourced** — `_restatement_at_risk` previously scanned companyfacts-XBRL
   `10-K/A` annual-fact rows, which only see amendments that re-filed a pulled XBRL concept →
   systematically under-counted partial / non-financial amendments → a misleading
   `restatement_contamination_pct = 0.0` (contradicts Hennes-Leone-Miller 2008). Now fetches the
   SAME EDGAR filings-index feed the live `restatement_history` flag uses
   (`restatement_filings.fetch_amendments`, lazy per-picked-name + memoized so only the ~50-80
   selected names hit EDGAR, not the ~500 universe; 5y lookback). Conservative (any 10-K/A or
   10-Q/A filed after the as-of date; no period-map so it over- not under-counts). New meta:
   `restatement_canary_source: "edgar-filings-index"` + `restatement_canary_unresolved_count` (picks
   whose amendment fetch failed — counted separately, not as at-risk).
2. **Dynamic disclaimer** — `DISCLAIMER` → `DISCLAIMER_BASE` (method caveats, dropped the misleading
   "treat as an upper bound" tail) + a result-dependent in-sample lead/lag sentence computed from the
   actual NAV (`_insample_lag_clause`), so the disclaimer can never claim a win the chart contradicts
   (it now states the default-count net line under/out-performed SPY with the real figures).

Workflow: `compute/cache/edgar_amendments` added to the cache-restore paths. +3 tests (canary fires
on a post-as-of amendment, unresolved-on-fetch-failure, `_restatement_at_risk` filings-index
semantics); **50 `tests/test_portfolio` pass; 1520 offline**. ruff clean. `quantrank-reviewer` gate +
a re-dispatch (regenerates the artifact with the accurate non-zero canary + dynamic disclaimer) +
methodology-scientist re-bless of the real canary value before Mark-Ready. Frontend AI-pick home is
the NEXT PR.

**Files**: `scripts/backfill_portfolio_pit.py` (canary re-source + dynamic disclaimer) ·
`.github/workflows/backfill-portfolio.yml` (edgar_amendments cache) ·
`tests/test_portfolio/test_backfill_integration.py` (+3 tests) ·
`frontend/public/data/portfolio/{backtest_pit,benchmarks}.json` (the committed artifact, refreshed by
re-dispatch) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## Phase 7.0 PR-4 — AI-pick portfolio home page (in flight, 2026-06-06)

**Branch**: `claude/loving-clarke-kAZII` (post-#419-merge)
**Type**: feat(frontend) — rebuilds `frontend/app/page.tsx` into the AI-pick portfolio the
user asked for, consuming the merged `backtest_pit.json`. No schema / compute change; the
artifact self-carries its meta so no schema triple.

Replaces the rankings-preview home (the full ranking lives on at `/ranking`, linked from the
hero). The page renders: a **1-10 holdings slider** that re-runs the backtest LINE (the
artifact stores one NAV series per count, so performance-vs-index changes with the count, not
just the displayed picks); a **benchmark selector** (SPY/QQQ/DIA/IWM); a **multi-timeframe
NAV-vs-index chart** (1Y/3Y/5Y, portfolio net vs the chosen index, both rebased to 100 at the
window start; Recharts, lazy-split, theme-aware); the **full-window headline** (net return vs
the index — honest: the N=5 default lags SPY, shown not buried, per the methodology verdict);
the **gross / net / higher-slippage cost band**; the **current top-N picks** (inverse-vol
weights + sector chip + composite, linking to `/stock/<ticker>`); and the artifact's own
**result-dependent disclaimer**.

**Architecture / footgun handling**: `lib/data.ts` `getAiPickData()` (build-time server) reads
the 1.3 MB `backtest_pit.json` via `fs` (NOT a static `import` — that would make tsc infer a
giant literal + bundle a server blob) and **trims + rounds (2dp)** it to a small client view
model (net line per count + benchmark lines + per-count finals + the latest rebalance), so the
full artifact never ships in the page payload. Returns `null` → "backtest pending" state when
the backfill hasn't run. The server page resolves the data; the `'use client'`
`AiPickPortfolio` receives it as PROPS (never imports `lib/data.ts` — the build-time-data
gotcha). `SegmentedSelector` mirrors `PriceTimePeriodSelector` (outlined-light radiogroup);
`NavCompareChart` follows the Recharts hex-exception + next-themes pattern.

**Validation**: node_modules absent locally → no local tsc/build. **CI Frontend (build) =
SUCCESS** (next build + tsc compiled clean); Vercel preview deployed green. Gated:
`frontend-design-reviewer` (static design/a11y) + a Vercel-preview spot-check + an
`expert-user-explorer` experiential pass before Mark-Ready.

**Deferred / follow-up**: the `/portfolio` tab still points at the ComingSoon watchlist stub
(reconcile vs the now-portfolio home in a later PR); CLAUDE.md §Phase status is still frozen at
pre-Phase-7 (schema 0.10.13-phase4.6) — a housekeeping bump to reflect the Phase 7.0 ladder is
its own pass.

**Files**: `frontend/app/page.tsx` (rewritten) · `frontend/components/AiPickPortfolio.tsx` +
`NavCompareChart.tsx` + `NavCompareChartLazy.tsx` + `HoldingsCountSlider.tsx` +
`SegmentedSelector.tsx` (new) · `frontend/lib/data.ts` (`getBacktestPIT` + `getAiPickData`) ·
`frontend/lib/types.ts` (`Backtest*` + `AiPickData`) · `CLAUDE.md` §Gotchas index +
`docs/GOTCHAS.md` (detail) + `AGENTS.md` (lockstep) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## Phase 7.0 follow-up — nav reconcile + §Phase status housekeeping (in flight, 2026-06-06)

**Branch**: `claude/loving-clarke-kAZII` (post-#420-merge)
**Type**: chore — frontend (one nav label) + docs only; no schema / compute change.

Two cleanups deferred from the PR-4 merge:

1. **Nav reconcile.** Home is now the AI-pick *portfolio* (Phase 7.0), but the TopNav
   "Portfolio" tab pointed at the coming-soon personal-*watchlist* stub (`/portfolio`) —
   two things both called "portfolio". Relabelled the tab **"Portfolio" → "Watchlist"**
   (the stub already describes itself as a personal watchlist; distinct feature from the
   algorithmic AI-pick on Home) + updated the `/portfolio` page title/heading to
   "Watchlist". Route unchanged (`/portfolio`, low-churn — it's a coming-soon stub).

2. **§Phase status housekeeping.** CLAUDE.md §Phase status had been frozen at pre-Phase-7
   (schema `0.10.13`, in-flight = the long-merged token-economy PR #391). Updated: current
   schema → **`0.10.14-phase4.6`** (the actual `main` value; `Metadata.benchmark_coverage_pct`
   from #416 PR-1 — Phase 7 added no schema bump, the backtest artifact self-carries its
   meta) + a Phase 7.0-shipped summary (#416→#420); refreshed the in-flight entry + added
   Phase 7.0 follow-ups to Next deliverables (Watchlist feature · scheduling the backfill ·
   PR-2c PIT veto replay). AGENTS.md AI-pick bullet gains the Watchlist-relabel note (lockstep).

**Files**: `frontend/components/TopNav.tsx` · `frontend/app/portfolio/page.tsx` · `CLAUDE.md`
(§Phase status) · `AGENTS.md` (AI-pick bullet) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## Phase 7.0 follow-up — remove the 2-per-sector cap from AI-pick selection (in flight, 2026-06-06)

**Branch**: `claude/loving-clarke-kAZII`
**Type**: feat(compute) — selection-rule change to `select_picks` + paired honesty/copy
updates. No schema change (artifact self-carries meta). **Needs a backfill re-run** to
regenerate `backtest_pit.json` with the uncapped selection.

User decision: drop the `MAX_PER_SECTOR = 2` diversification cap so the AI-pick basket is
purely the top-N eligible names by composite (it can concentrate in one sector). methodology-
scientist **APPROVED (defensible — proceed)**: a concentrated factor book is a valid
construct (concentration/diversification tradeoff; DGU 2009 governs *weighting* not sector
breadth; the composite already does sector-relative + neutralized scoring, so picks stay
merit-based). The remaining controls (inverse-vol + the 0.35 single-name cap) bound single-
NAME risk only — single-SECTOR concentration is now intentional, so it MUST be disclosed.

Changes:
- `compute/portfolio/weights.py` — removed `MAX_PER_SECTOR` / `MIN_COUNT_FOR_SECTOR_CAP`;
  `select_picks` is now `top-N eligible by composite` (veto filter + tiebreak unchanged);
  module docstring + comments updated.
- `scripts/backfill_portfolio_pit.py` — `_insample_lag_clause` drops the now-false
  "per-sector-capped" wording → "sector-CONCENTRATED (no per-sector cap) … can diverge in
  either direction"; adds the concentration- + regime-driven / McLean-Pontiff overfitting
  caveat (any in-sample edge from concentrating into the regime's winning sector is not a
  free lunch). v1-scope docstring updated.
- `frontend/components/AiPickPortfolio.tsx` — picks copy "max 2 per sector" → "(no sector
  cap)"; **new sector-concentration disclosure** ("Top sector: X — N of count", computed
  from `holdings[].sector`, no schema change) per methodology's required honesty add.
- `tests/test_portfolio/test_weights.py` — the 2 sector-cap tests replaced by a no-cap
  "top-N by composite, sector-blind" test. ruff clean; 50 `tests/test_portfolio` pass.

**Expected**: removing the cap likely IMPROVES the 2021-26 in-sample return (loads the
regime's tech winners the cap had blocked) — but that is the McLean-Pontiff overfitting
signature, framed as such in the disclaimer, NOT read as validation.

**Files**: `compute/portfolio/weights.py` · `scripts/backfill_portfolio_pit.py` ·
`frontend/components/AiPickPortfolio.tsx` · `tests/test_portfolio/test_weights.py` ·
`CLAUDE.md` (§Phase status in-flight) · `AGENTS.md` (AI-pick bullet) ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## AI-pick "Rotation history" timeline (in flight, 2026-06-06)

Surfaces the backtest's point-in-time holdings at EVERY quarterly rebalance, not just the
latest "Current picks" card. Directly answers the user's request: "show what was held 5
years ago + how it rotated each quarter" — explicitly NOT "today's picks back-projected"
(which would be the look-ahead / survivorship bias the PIT engine exists to avoid). The
per-rebalance holdings already live in `backtest_pit.json.rebalances`; this PR just trims +
exposes them to the frontend and renders the rotation. No compute / schema / Python change,
so **no backfill re-run is required** (unlike #422).

Changes:
- `frontend/lib/types.ts` — new DISPLAY-ONLY `AiPickTimelineHolding` / `AiPickTimelineEntry`
  types + an `AiPickData.timeline` field. NOT part of the Pydantic↔TS↔snapshot triple (the
  Phase 7 artifact self-carries its meta); `schema_check` green (in sync, no drift).
- `frontend/lib/data.ts` — `getAiPickData()` now emits `timeline`: every rebalance trimmed
  to `{ticker, sector}` in composite order. Tiny payload (~20 × 10 × 2 strings) vs the 1.3MB
  raw artifact; weights are intentionally omitted (the live "Current picks" card owns
  weights — the timeline is the rotation STORY, not a per-quarter weight table).
- `frontend/components/HoldingsTimeline.tsx` (new) — renders all rebalances newest-first at
  the current basket size, with per-quarter entered (emerald dot + SR aria-label) / exited
  (muted sub-line) markers + an avg-turnover stat. Reactive to the count slider (slices each
  entry to top-`count`, the same cut `select_picks` makes). a11y: each ticker is a
  `/stock/<T>/` link whose aria-label carries entered-state + sector (not colour-only).
- `frontend/components/AiPickPortfolio.tsx` — renders `<HoldingsTimeline>` below "Current
  picks", passing the shared `count` state so the slider drives both the chart and the
  timeline.

`schema_check` green. tsc / `next build` not runnable locally (no `node_modules`) → CI
Frontend build + the Vercel preview are the compile gate (display-only TS, no Python).

**Files**: `frontend/lib/types.ts` · `frontend/lib/data.ts` ·
`frontend/components/HoldingsTimeline.tsx` (new) · `frontend/components/AiPickPortfolio.tsx` ·
`CLAUDE.md` (§Phase status in-flight) · `AGENTS.md` (AI-pick bullet) ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## ci(cron) — auto-refresh the PIT backtest in the weekly cron (in flight, 2026-06-06)

User ask: "รันอัตโนมัติพร้อมกับ cron" — make the AI-pick backtest refresh automatically with
the weekly cron instead of needing a manual `backfill-portfolio.yml` dispatch. Today
`compute-rankings.yml` writes `rankings.json` / `metadata.json` / `stocks/*` / `benchmarks.json`
but NOT `backtest_pit.json` (the home page's NAV + Current picks + Rotation history all read
that artifact), so the whole AI-pick surface stays frozen to the last manual backfill.

**Why fold into the cron (not a separate scheduled workflow):** `backfill-portfolio.yml` carries
the `if: github.ref_name != 'main'` guard (security-reviewer FAIL 2026-06-05) precisely so a
dispatch can't commit straight to the protected `main`. A *new* scheduled workflow would run on
`main` and hit the same wall. The weekly cron is already the SOLE trusted writer to `main`, so
the correct move is to widen what the trusted cron commits — NOT to weaken the guard.

Change (`.github/workflows/compute-rankings.yml`):
- New step after "Run weekly compute", before "Commit JSON outputs":
  `python -m scripts.backfill_portfolio_pit`. It reuses the SAME prices +
  fundamentals_history + benchmarks.json the compute step just refreshed (warm ~15-20m). The
  existing "Commit JSON outputs" step already `git add frontend/public/data/`, so
  `backtest_pit.json` commits alongside the rankings — no commit-step change.
- `continue-on-error: true` + `timeout-minutes: 40` (step-level) so a backtest stall / failure
  can NEVER block the rankings commit. The writer is atomic (tmp + os.replace), so a failed run
  leaves the prior `backtest_pit.json` intact.
- Job `timeout-minutes` 195 → 225 for headroom over a worst-case cold compute (~140-160m) PLUS
  the 40m-capped backtest step.
- `FORM4_FETCH_SKIP=1` is irrelevant to the backfill — its veto set is the 7 active rank-gates,
  none Form-4.

Result: every weekday cron now refreshes the AI-pick home page (NAV tail + headline return stay
current; new quarterly rebalances auto-appear when their +45d filing-lag date passes). Closes
CLAUDE.md §Next deliverables 7.0(b). Manual `backfill-portfolio.yml` stays as the on-demand /
custom-window path.

**Files**: `.github/workflows/compute-rankings.yml` · `CLAUDE.md` (§Stack CI line + §Phase
status in-flight + §Next deliverables 7.0(b)) · `AGENTS.md` (AI-pick bullet) ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## ci(cron) — trading-day holiday gate (in flight, 2026-06-06)

User ask: "รันทุกวันยกเว้นวันตลาดปิด" — run on trading days only (skip market-closed days).
Context: the cron already fires Mon-Fri (`cron: "0 22 * * 1-5"`), so weekends are excluded for
free at the schedule level. The remaining gap is the ~9-10 NYSE full-day holidays that fall on a
weekday — the cron still fires on those, and since #424 folded the backtest in, every run now
moves the backtest's `generated_utc`, so a holiday run lands a timestamp-only no-op commit rather
than the old clean "No JSON changes to commit". GitHub cron syntax can't express "skip NYSE
holidays", so this needs a guard.

Change (`.github/workflows/compute-rankings.yml`):
- New `trading-day-gate` job — stdlib-only (no checkout, no pip install, ~15s). Computes the
  US/Eastern date and outputs `run=false` iff it is a weekday in a hardcoded NYSE-holiday set
  (2026-2028), else `run=true`.
- The `compute` job gains `needs: trading-day-gate` +
  `if: needs.trading-day-gate.outputs.run == 'true' || github.event_name == 'workflow_dispatch'`.
- **Safety by design:** the default is "run" and ANY error fails OPEN (`run=true`), so a
  stale / missing holiday entry degrades to a harmless no-op run — it can NEVER skip a real
  trading day. A manual `workflow_dispatch` bypasses the gate entirely (forced regen on a holiday
  / after a fix still works). Gate job runs at the workflow-default `contents: read` (the
  `compute` job keeps its scoped `contents: write`).
- Maintenance: extend `NYSE_HOLIDAYS` every year or two (failure mode is a no-op run, not a
  missed update). Half-day sessions (1pm closes) are intentionally NOT listed — the market traded.

Cost: the gate adds ~1 billable runner-minute per scheduled weekday run (~250/yr) and removes
~9-10 holiday compute runs (~30m each) — roughly cost-neutral; the real win is correctness
(trading-days-only) + no timestamp-only no-op commits on holidays.

**Files**: `.github/workflows/compute-rankings.yml` · `CLAUDE.md` (§Stack CI line + §Phase
status in-flight) · `AGENTS.md` (AI-pick bullet) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## perf(cron) — tier2 cache split + per-stage timing summary (in flight, 2026-06-06)

User ask: "แก้ tier 2" + "แยก run ... รู้ว่าช้าตรงไหน failed ตรงไหน" (fix the slow tier2 + add
per-stage visibility). Two specialists ran:

**edgar-debugger ROOT-CAUSE-CONFIRMED — self-reinforcing cold-cache trap.** The single 11-path
`actions/cache` bundle (~250-500 MB) was too large to save in the post-job window once the job
ran 100-180 min; the save truncated and the largest layers (`edgar_10k_text` ~50-150 MB,
`edgar_8k`) never persisted → next run restored an older bundle WITHOUT them → Tier-2 ran COLD
(~80 min full SEC re-fetch) → runtime climbed → next save failed again. Evidence (committed
metadata.json, cron #82 = run 27044959194): `fundamentals_latency_p95`=11.3s (warm) but
`tier2_wall_clock_seconds`=4835.6 (80.6 min, cold) on the SAME run — the partial-cold signature.

**performance-engineer — cross-job parallelism is the WRONG fix** (SEC 10 req/s per-UA ceiling →
running fundamentals+tier2+form4 in parallel jobs = 429 cascade → worse cold runs; + artifact
overhead + a multi-week compute refactor). The user's real goal is VISIBILITY, delivered by
Tier 1 (Step Summary, this PR) + Tier 2 (prefetch step-split, deferred follow-up).

Changes (this PR = the cache fix + Tier-1 visibility, workflow + 1 config line — no schema):
- `.github/workflows/compute-rankings.yml`:
  - Split the single "Restore compute caches" step into TWO independent `actions/cache` steps —
    **fast** (`fundamentals`/`fundamentals_history`/`prices`/`universe`/`yfinance_info`/`edgar_form4`,
    `cache-v5-fast-<quarter>-<os>`, unchanged semantics: fundamentals is proven warm) + **slow-text**
    (`edgar_10k_text`/`edgar_8k`/`edgar_amendments`/`edgar_late_filings`/`osap`,
    `cache-v5-text-<os>-<run_id>` + `restore-keys: cache-v5-text-<os>-`). The run-id key guarantees
    each run's freshly-fetched text PERSISTS (a unique key is never skipped by actions/cache
    immutability) and the prefix restores last-good — fixing "text never persists" AND avoiding both
    the static-key 90-day cliff and the quarter-rollover cold run.
  - New "Stage timing summary" step after compute: reads metadata.json's wall-clock fields →
    `$GITHUB_STEP_SUMMARY` markdown table (tier2 / Step-8 / OSAP / Form-4), `if: always()` so a
    compute abort still shows what ran. Answers "ช้าตรงไหน" per run (prices/fundamentals/scoring/
    writes timing = a follow-up PR needing new hooks + schema bump).
- `compute/config.py`: `EDGAR_8K_CACHE_TTL_SECONDS` 7→6 days (a 7-day TTL equals the cron cadence →
  boundary re-fetch on drift; 6 days adds a 24h buffer). No test pins it absolutely
  (test_eight_k_events uses `TTL + 100` relative).

Expected: warm cron ~95 min → ~15-20 min once the text cache persists. Self-validating — the next
cron's Stage-timing-summary will show tier2 drop from 80m to ~3-5m + the canary will show
`edgar_10k_text` warm.

Validation: `ruff` clean; 180 ingest + 139 scoring/output offline tests pass; YAML parses.
(test_osap / test_qlib collection errors are local-env `.[factors]` deps, not this change.)

Deferred follow-ups (performance-engineer roadmap): Tier-1 gap fields (5 new wall-clock hooks in
`compute/main.py` for prices/fundamentals-snap/fundamentals-hist/scoring/JSON-write + schema bump
0.10.15) → Tier-2 prefetch step-split (6 new ingest `__main__` entrypoints → per-stage graph nodes
+ pass/fail + single-step rerun; do AFTER this cache fix lands so the step timing is validated warm).

**Files**: `.github/workflows/compute-rankings.yml` · `compute/config.py` · `CLAUDE.md` (§Gotchas
index + §Phase status in-flight) · `AGENTS.md` (cache-split gotcha) · `docs/GOTCHAS.md` (full
cache-split detail) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## Phase 4j.1 — Qlib Alpha158 observability surface (in flight, 2026-06-06)

**Branch**: `claude/sleepy-lovelace-1D1bt`. The FIRST Phase-4 factor-INTEGRATION PR (the 4h OSAP /
4i JKP / 4j Qlib / 4k IPCA scouts all merged; this lands the 4j.1 slice of CLAUDE.md §Next
deliverables "Phase 4i.1 / 4j.1 / 4k.1"). Flow-8 design→ratify→implement: `financial-engineer`
designed it, `literature-searcher` pulled the Alpha158 source facts, `methodology-scientist`
returned GO-WITH-CONDITIONS.

**What ships (observability-only, SKILL.md Rule 18 — Δscore = 0 on every ticker):**
- `compute/features/alpha158_replicate.py` — a feature→long-short-return adapter. Alpha158 yields
  per-stock-per-date feature VALUES, not portfolio returns; the PBO/DSR gate needs a
  `(date × signal)` return matrix. The adapter, per feature per month, cross-sectionally ranks the
  universe and forms a top-decile-minus-bottom-decile portfolio on the NEXT month's forward return
  (Grinold-Kahn 2000 Ch.6 Fundamental-Law construction; zero free parameters). It OWNS the lag
  (shifts the trailing-return panel forward internally) so feature@m only ever pairs with the
  return over (m, m+1] — never a contemporaneous leak.
- The Phase-4h gate is REUSED verbatim: `osap_validation.gate_osap_signals(...,
  requested_signals=ALPHA158_FEATURE_NAMES)` with `n_trials=158` (Harvey-Liu-Zhu 2016 t≥3.0
  multiple-testing posture). No PBO/DSR math reimplemented.
- 9 additive `Metadata.alpha158_*` fields (schema PATCH `0.10.14 → 0.10.15-phase4.6`;
  `alpha158_gate_diagnostics` reuses `OsapGateDiagnostic`): features_used · excluded_features ·
  features_ic_12m · features_missing_from_compute · features_dropped_no_long_short ·
  gate_diagnostics · coverage_pct · survivorship_bias_corrected · wall_clock_seconds. The
  158-feature accounting equation `158 == missing + dropped + used + excluded` is closed +
  Hypothesis-property-tested (the invariant whose absence hid Phase 4h's ~78-signal silent drop).
- `compute/main.py` Step 7.6 mirrors the OSAP Step 7.5 try/except graceful-degradation block;
  blends NOTHING, writes no `StockDetail` field.

**Deferred (named follow-ups):**
- *Live feature source* — the Qlib `.bin` BYO `dump_bin` adapter (Qlib ships no public US bundle).
  Step 7.6's `_acquire_alpha158_inputs` raises until the bin cache is wired → every `alpha158_*`
  field nulls. methodology-scientist pre-ratified `used=0` / all-None on the early crons as honest
  (insufficient monthly history < `MIN_OBS_PER_SIGNAL=16`), NOT a bug. The adapter + gate are
  verified offline by synthetic fixtures regardless.
- *4j.2 — the blend* — a PBO/DSR survivor may influence rank only if it ALSO clears `|φ| < 0.30`
  (Cohen 1988 / `docs/phase3-correlation/findings.md` redundancy threshold) vs the accepted-OSAP +
  momentum/technical exposures. 4j.1 surfaces but gates nothing on φ.

**Citation discipline (methodology condition #1):** Yang et al. 2020 (arXiv:2009.11189, the Qlib
whitepaper) is cited as the IMPLEMENTATION reference only — arXiv-only, no standalone per-feature
IC, self-describes Alpha158 as a re-expression of classical TA. NOT promoted to the CLAUDE.md
canonical anchor list; per-family anchors are the classical literature (Jegadeesh-Titman 1993
momentum · Frazzini-Pedersen 2014 BAB · candlestick / volume-flow lit). The PBO/DSR gate is the
empirical defense, not any paper claim. A surfaced |IC| > 0.05 = overfit alarm.

**Docs-lockstep note:** code+schema PR; satisfies CLAUDE.md §Conventions via the "EITHER a
`PHASE_STATUS_INFLIGHT.md` entry OR a CLAUDE.md+AGENTS.md substance diff" rule — this entry +
the CLAUDE.md §Phase status in-flight substance diff. AGENTS.md §Phase+version is a pointer-only
section (the parallel log was collapsed 2026-06-03), so no parallel AGENTS.md entry is added.

**Files**: `compute/features/alpha158_replicate.py` (new) · `compute/main.py` (Step 7.6 +
`_acquire_alpha158_inputs`) · `compute/output/schemas.py` (+9 `Metadata.alpha158_*`) ·
`compute/config.py` (`SCHEMA_VERSION` → 0.10.15) · `frontend/lib/types.ts` +
`frontend/lib/schema-snapshot.json` (schema triple) ·
`tests/test_features/test_alpha158_replicate.py` (new) · `tests/test_config.py` (version pin) ·
`CLAUDE.md` (§Phase status in-flight) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## feat(frontend) — Phase 7.0 personal Watchlist (in flight, 2026-06-06)

**Branch** `claude/sleepy-lovelace-1D1bt`. Turns the `/portfolio` coming-soon stub into a real
**browser-local watchlist** — save tickers from the ranking + stock pages and see them on
`/portfolio`. localStorage-only (key `quantrank:watchlist`), no account / no backend / nothing
leaves the device. FRONTEND-ONLY: no schema / compute / scoring change (`composite_score` + every
JSON byte untouched).

**What ships:**
- `frontend/lib/useWatchlist.ts` (new) — the hook. localStorage-backed `string[]` of tickers with
  a `mounted` guard mirroring `ThemeToggle`/next-themes (SSR + first client render emit "not
  saved"; the real set reads post-hydration → no star-fill hydration mismatch) + cross-tab (native
  `storage`) + same-tab (custom-event) sync. Defensive parse (de-dupes, drops non-strings);
  quota / private-mode writes degrade silently.
- `frontend/components/WatchlistButton.tsx` (new) — the star toggle. Icon-only square (ranking
  rows) + `labeled` "Save to watchlist" pill (stock-detail hero). `aria-pressed` + dynamic
  `aria-label`; `e.stopPropagation()` + `e.preventDefault()` so a tap on the star inside a row
  `<Link>` (un)saves without navigating. Saved tone = emerald (NOT amber — amber is the project's
  warning/caution semantic, per design-review).
- `frontend/components/WatchlistView.tsx` (new) — the `/portfolio` client view. Filters the
  server-passed rankings to saved tickers, sorts by rank, renders cards (reusing
  `ScoreBadge` / `SectorChip` / `RecommendationBadge` / `StockLogo`); pre-mount loading branch (no
  empty-state flash) + a warm empty-state matching the ranking empty-state anatomy.
- `frontend/app/portfolio/page.tsx` (rewrite) — Server Component reads `getRankings()` and passes
  rankings to `<WatchlistView>` per the build-time-data rule (`lib/data.ts` never imported into a
  client component; the saved set lives only in the browser).
- `frontend/components/RankingTable.tsx` (edit) — trailing star column (desktop table) + mobile
  card restructured to a flex-row `[<Link> + star right-rail]` (a `<button>` can't validly nest in
  the row `<a>`); `data-flip-key` + `animate-rise-in stagger-*` kept on the `<li>` so the
  search-scoped FLIP reshuffle is intact.
- `frontend/app/stock/[ticker]/page.tsx` (edit) — back-link row wrapped in `justify-between` + the
  labeled `WatchlistButton`.

**Review:** `frontend-design-reviewer` returned 1 FAIL (inverted muted pair on the loading text →
fixed to `text-slate-500 dark:text-slate-400`) + 4 WARN (labeled-pill `border-emerald-300` →
`-200` per the soft-OKLCH allowlist · icon `h-11` → `min-h-[44px]` convention · count
`tabular-nums` · pill `py-2`) — all applied. Architecture (hydration guard / a11y / FLIP /
empty-state-CTA-not-disabled / emerald-not-amber) validated. `tsc --noEmit` + `next build` green
(510 / 510 static pages).

**Docs housekeeping folded in (post-4j.1):** CLAUDE.md schema `0.10.14 → 0.10.15` + §In-flight
refresh (4j.1 → this) + §Next-deliverables (4j.1 DONE, Watchlist in-flight); PHASE_STATUS.md
merged-log reflect of #424 / #425 / #426 / #427. The #424 / #425 / #427 / 4j.1 INFLIGHT entries
STAY (append-only "do NOT move on merge" convention — periodic housekeeping drains them, not this
PR).

**Files**: `frontend/lib/useWatchlist.ts` (new) · `frontend/components/WatchlistButton.tsx` (new) ·
`frontend/components/WatchlistView.tsx` (new) · `frontend/app/portfolio/page.tsx` (rewrite) ·
`frontend/components/RankingTable.tsx` · `frontend/app/stock/[ticker]/page.tsx` · `CLAUDE.md`
(schema + §In-flight + §Next-deliverables) · `PHASE_STATUS.md` (merged-log + current-state) ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## chore(output) — orphan per-stock-file prune (in flight, 2026-06-06)

**Problem.** Production output drifted to **503 detail / 504 history files vs 502 ranked** — a
release-blocking count mismatch (it trips `verify-production-output`). Root cause: the weekly cron
rewrites the JSON of every CURRENT constituent and runs `git add frontend/public/data/`, but
`git add <pathspec>` only stages a *deletion* when the file is gone from the working tree — and
nothing removed the files of tickers compute simply stopped writing. Two real orphan sources:

- **De-listing** — `EPAM` left the S&P 500 → `stocks/EPAM.json` + `stocks/history/EPAM.json` lingered.
- **Ticker rename** — BNY Mellon `BK → BNY` → live `BNY.*` written each run, stale
  `stocks/history/BK.json` (no detail counterpart) lingered.

**Fix.** New `prune_orphan_stock_files(keep_tickers, data_dir)` in `compute/output/writer.py`, called
in `compute/main.py` **right after `write_rankings_json`** — removes detail + history for any ticker
not in the just-written rankings. The cron's existing `git add frontend/public/data/` stages the
deletions (git ≥ 2.0 records removals under a directory pathspec) → **no `compute-rankings.yml`
change**. `_PRUNE_SAFETY_FLOOR = 50` skips the prune entirely on a degraded run (empty / truncated
rankings) so it can never wipe `stocks/`; per-file `unlink` is wrapped (one bad file ≠ abort); walks
BOTH `stocks/*.json` and `stocks/history/*.json` (so history-only orphans like `BK` are caught);
returns the sorted pruned-ticker list for the log line. Plus a one-time `git rm` of the 3 current
orphans (EPAM detail+history, BK history) → **502/502, zero orphans now**.

**Scope.** NO schema / scoring / frontend change. The orphan never rendered a page
(`generateStaticParams` reads `rankings.json`, `dynamicParams=false` → `/stock/<dropped>` 404'd) —
this is deploy-size + verify-count hygiene. Verification ladder: `ruff` clean · 9 new prune tests in
`tests/test_output/test_writer.py` (happy-path / multiple-sorted + history-only / safety-floor /
empty-keep / missing-dir / 49-50 floor boundary / non-JSON survival / unlink-failure resilience —
the last 4 folded from the test-engineer review) · full offline suite **1544 passed, 13 skipped**
(skips all pre-existing: optional deps qlib/ipca + shallow-clone git history; osap collection errors
are a sandbox missing-dep, not this change) · `verify-production-output` helper **0 failures, 1
pre-existing warning** (502/502 parity restored). Unblocks **release v1.5.0-phase7.0**.

**Docs housekeeping folded in (post-#428):** replaced the merged Watchlist §In-flight entry in
CLAUDE.md with this one + §Next-deliverables (Watchlist DONE #428); added the orphan-prune §Gotchas
one-liner (CLAUDE.md) + full detail (docs/GOTCHAS.md); annotated `writer.py` in AGENTS.md
§Project-structure. (The #428 INFLIGHT entry above STAYS — append-only "do NOT move on merge".)

**Files**: `compute/output/writer.py` (new `prune_orphan_stock_files` + `_PRUNE_SAFETY_FLOOR`) ·
`compute/main.py` (import + call after `write_rankings_json`) ·
`tests/test_output/test_writer.py` (9 prune tests) · 3 `git rm` (EPAM detail+history, BK history) ·
`CLAUDE.md` (§Gotchas + §In-flight + §Next-deliverables) · `AGENTS.md` (§Project-structure
writer.py annotation) · `docs/GOTCHAS.md` (full detail) · `PHASE_STATUS.md` (#428 merged-log reflect
+ range bump) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## ci(cron) — revert emergency FORM4_FETCH_SKIP=1 (Issue #287 PR B, in flight, 2026-06-06)

**What.** Re-enables the Form-4 bulk fetch on the weekly cron by removing
`FORM4_FETCH_SKIP: "1"` (+ its 2026-05-25 emergency comment) from the
`.github/workflows/compute-rankings.yml` top-level `env:` block.

**Why now.** PR #245 set the skip as an EMERGENCY when the 5th SEC EDGAR loop
(Form-4, added PR #205) went cold simultaneously with the other 4 over a 44h
Fri→Sun cache-eviction gap and the manual dispatch hit the 2h30m cap. The
workflow comment + Issue #287 PR B both prescribed reverting once the durable
cron-time fixes landed: **PR #297** (timeout rebaseline 150→195→225m +
cache-restore canary + 4 per-loop `*_wall_clock_seconds`) and **PR #427** (the
tier2 cache split that actually fixed the cold-cache root cause). The Issue #287
PR B gate — "≥ 1 cron < 195m green" — is met with wide margin: cron **run #87 =
15m49s warm, `tier2_wall_clock_seconds` 11.2s** (462× faster than run #86's
86-min cold bootstrap), leaving ample headroom for Form-4's ~2-3m. edgar-debugger
confirmed worst-case cold ~180m vs the 225m ceiling (45m headroom — the original
150m-ceiling timeout cannot recur) + edgartools 5.35.1 drift-detector green.

**Impact — ZERO scoring change.** Form-4 is observability-only
(`form4_enabled=False` at `compute/main.py:2460`; `_FORM4_FLAGS_ENABLED=False`):
the `insider_sell_cluster` flag is computed but NOT wired into composite / risk /
rankings. The revert simply resumes the `form4_*` Metadata observability surface
(`form4_wall_clock_seconds`, `form4_rule10b5_one_excluded_count`,
`form4_negation_guard_downgrade_count`) so the data accumulates toward the
2026-08-19 Q3 cohort audit (issue #130) + the eventual
`INSIDER_SELL_CLUSTER_WEIGHT` 5.0 → 7.0 promotion gate. Defense-layer counts
UNCHANGED (33 declared flags; 7 active vetoes).

**Scope discipline.** `compute-rankings.yml` ONLY. The CI escape-hatch
`FORM4_FETCH_SKIP=1` STAYS on `pre-merge-prod-sim.yml` (its 45-min synthetic-cap
combo, PRs #230/#238/#241 — by design). No code change (the reader is
`os.environ.get("FORM4_FETCH_SKIP", "")` at `compute/main.py:959`, already
revert-ready). As a bonus the revert RE-ALIGNS the docs/GOTCHAS.md + AGENTS.md
"NONE set in the weekly cron" invariant that the silent emergency exception had
violated since 2026-05-25. Folds 3 reviewer-surfaced pre-existing drifts on the
same topic: stale `FORM4_FETCH_SKIP` reader line numbers in docs/GOTCHAS.md +
AGENTS.md (→ `compute/main.py:959`) and WORKFLOW.md's stale
`form4_enabled=True` roadmap row (→ `False`, matching the code).

**Validation gate (post-merge).** A cron dispatch must confirm
`form4_wall_clock_seconds` populates (not None) + the cron stays green/warm
BEFORE tagging release v1.5.0-phase7.0. (Run #87's metadata still shows
`form4_wall_clock_seconds=null` because the skip was active; the next post-merge
cron is the proof. First-cron watch per edgar-debugger: `form4_coverage_pct`
85-95%, `fundamentals_latency_p95` < 15s, `form4_fetch_failures` < 10.)

**Files**: `.github/workflows/compute-rankings.yml` (remove `FORM4_FETCH_SKIP`
env + emergency comment, add a short revert note) · `CLAUDE.md` (§In-flight) ·
`AGENTS.md` (§escape-hatch revert note + line-number fix) · `docs/GOTCHAS.md`
(reader line-number fix) · `WORKFLOW.md` (`form4_enabled` roadmap row fix) ·
`PHASE_STATUS.md` (#429 merged-log reflect + Issue #287 PR B → IN FLIGHT) ·
`PHASE_STATUS_INFLIGHT.md` (this). The orphan-prune (#429) INFLIGHT entry above
STAYS — append-only.

---

## feat(frontend) — Jitta-style backtest home: annual-returns table + CAGR + $-growth chart (in flight, 2026-06-07)

**What.** Reshapes the AI-pick home (`AiPickPortfolio`) toward a Jitta-Wealth-style backtest view
(user request from two Jitta screenshots — a growth chart with $ end-values + an annual-returns
table with a CAGR row). Layout = **augment** (chosen): the Jitta-style chart + table lead; Current
picks + Rotation history stay below. Chart framing = **$10,000 → $X** (chosen over rebased-100).

**Changes (3 frontend files, no schema / compute / backtest change):**
- `components/NavCompareChart.tsx` — new `money?: boolean` + `baseline?: number` props. In money mode:
  USD axis (`fmtMoneyAxis` → `$12k`) + tooltip (`fmtMoney` → `$12,340`), `ReferenceLine` at the
  baseline, and **end-of-line $ labels** via a `<LabelList>` `content` renderer that draws only the
  final point (right margin widened 8→60px). Non-money path byte-identical.
- `components/AnnualReturnsTable.tsx` (NEW, ~200 lines) — derives calendar-year returns
  (`NAV(yr-end)/NAV(prev-yr-end)-1`) + CAGR (`(last/first)^(1/elapsed_yrs)-1`) in-browser from the
  NAV series; real `<table>` + `<th scope>`; reuses the home's emerald/rose/slate `toneClass` +
  `tabular-nums` + `+`/`−` sign (Rule 10); highlighted CAGR `<tfoot>` row; partial-first-year `*`
  flag; a caveat note (raw composite · vetoes not replayed · not the live Top-5's record).
- `components/AiPickPortfolio.tsx` — rebases chart points to `CHART_BASE=10_000`, passes
  `money + baseline`, reframes the legend to $ end-values + `money$()` helper, inserts
  `<AnnualReturnsTable>` (full `netByCount[count]` + `benchmark[bench]` series) after the chart card.
  `NavCompareChartLazy` forwards the new props automatically (spreads `Props`).

**Honest result (by design).** The AI-pick UNDERperforms the S&P 500 at EVERY count over the shipped
2021-2026 (4.8y) window — count-5 net CAGR ≈ +0.2% vs SPY +12.5%; best (count-10) ≈ +11.2% vs +12.5%;
worst (count-1) ≈ −17.9%. This is already disclosed in `meta.disclaimer` ("the default 5-holding net
line underperformed the S&P 500 … defense-layer vetoes are not replayed"). Per user decision
(Ship + caveat), a caveat sits beside the CAGR row: the backtest is the **raw top-composite signal,
`veto_layer_replayed=False`** — NOT the live veto-filtered Top-5's record. On-brand for QuantRank's
honest harness (McLean-Pontiff 2016 decay; survivorship-corrected).

**Verification.** Frontend deps installed; `tsc --noEmit` clean; `next build` 510/510 green; home `/`
6.25 kB / 105 kB First Load. Derivation numbers validated against the raw `backtest_pit.json` NAV
(annual + CAGR replicated in python — match). Reviewer gate (`frontend-design-reviewer` +
`expert-user-explorer` Playwright) running; `vercel-preview-auditor` post-push.

**Files**: `frontend/components/NavCompareChart.tsx` · `frontend/components/AnnualReturnsTable.tsx`
(new) · `frontend/components/AiPickPortfolio.tsx` · `CLAUDE.md` (§In-flight + §Gotchas) · `AGENTS.md`
(§Project-structure) · `docs/GOTCHAS.md` (full detail) · `PHASE_STATUS_INFLIGHT.md` (this). The
FORM4-revert (#431, merged) + orphan-prune (#429, merged) INFLIGHT entries above STAY — append-only.

---

## feat(data) — Track B: 10-year survivorship ledger rebuild (fja05680 snapshot-diff, in flight, 2026-06-07)

**Goal.** Enable a real 10-year AI-pick backtest (user request — Jitta shows 10y).
The prior `data/sp500_membership_historical.csv` only covered 2020-04 onward, so a
pre-2020 reconstruction returned the anchor with `is_complete=False` (survivorship-
degraded — the exact bias the ledger exists to fix).

**What.** Full-rebuilt the ledger from the **fja05680 "S&P 500 Historical Components
& Changes"** dataset via **snapshot-diff** (consecutive point-in-time constituent
sets → ADD/REMOVE per change date) for 2016-01-04 .. 2026-01-14, plus the prior
ledger's hand-curated tail for > 2026-01-14 (fja05680's coverage ends there).
**485 events, 2016-01-04 .. 2026-06-02.** Tickers normalized to the yfinance dash
form (BRK-B / BF-B). `EARLIEST_EVENT_DATE` (`historical_universe.py`) + the verify
`WINDOW_START` both moved **2020-01 → 2016-01/2016-06**.

**Rename-aware (convention shift, documented in the ledger header).** Unlike the
prior "renames out of scope" hand-built rows, the snapshot-diff records a symbol
change as REMOVE old + ADD new (e.g. CDAY→DAY 2024-02), so `members_at` returns the
correct historical ticker at each date — MORE accurate for fetching as-of data.

**Boundary reconciliation.** (a) The curated tail removed Ceridian as `CDAY`
(2026-02-09); rewritten to `DAY` (the post-2024-rename live ticker). (b) Added the
**EPAM→FDXF 2026-06-02 swap** (EPAM → S&P SmallCap 600, replaced by FedEx Freight;
S&P DJI press release) — neither fja05680 (ends 2026-01-14) nor the prior ledger
had it; this is the **latent gap behind the #429 EPAM orphan**.

**Validation.** `scripts/verify_membership_ledger.py` **CLEAN across the full 10y**
— size band 498-506, **0 months out of band** (2016-06 .. 2026-06); Invariant-1
(removed-gone / added-present vs the live 502 universe) holds. fja05680 was
cross-validated against the prior hand-built 2020-2026 ledger at the boundary
(agreement on the 2020-04 CARR/OTIS + 2020-05 DXCM/AGN events). 2 floor-dependent
tests updated (`test_historical_universe` coverage-size + is_complete; backfill
pre-coverage window 2018→2014). `ruff` clean; offline suite **1547 passed** (1
pre-existing `test_alpha158_replicate` Hypothesis-`DeadlineExceeded` flake —
confirmed failing on the pre-change state too, env-slow, unrelated).

**STILL PENDING (heavy, user-gated).** A `backfill_portfolio_pit` re-run with a
**2016 start** to regenerate the 10Y `backtest_pit.json` (needs 2016+ EDGAR
fundamentals + prices — cold, long; some 2016-era filings may have gaps). Only then
does the home's "Max" button show a true 10 years. Methodology review of the
rebuild recommended before merge (survivorship-honesty = a core product claim).

**Files**: `data/sp500_membership_historical.csv` (rebuilt — 485 events + updated
header/provenance) · `compute/ingest/historical_universe.py` (`EARLIEST_EVENT_DATE`
2020→2016) · `scripts/verify_membership_ledger.py` (`WINDOW_START` 2021→2016 +
comments) · `tests/test_ingest/test_historical_universe.py` ·
`tests/test_portfolio/test_backfill_integration.py` · `CLAUDE.md` (§Gotchas +
§In-flight) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## feat — AI-pick holdings slider 1→20 + endpoint labels flanking the track (in flight, 2026-06-07)

**What.** (1) Holdings range 1-10 → **1-20**: `compute/portfolio/weights.py`
`MAX_PICKS` 10 → 20. (2) `HoldingsCountSlider` layout — the `min`/`max` endpoint
numbers moved from a separate row below the track to FLANK the slider on one row
(`[1] [====track====] [20]`).

**Zero live-ranking impact.** `MAX_PICKS` is backtest-only — the live forward
compute (`compute/main.py` → `rankings.json` / Top-5) does NOT import
`compute/portfolio/weights.py` (verified: `grep MAX_PICKS compute/main.py` empty).
It drives the backtest's `by_count[1..MAX_PICKS]` + the home slider max via
`meta.max_holdings`. `DEFAULT_COUNT` stays 5. No schema change.

**Verification.** ruff clean; 50 portfolio tests pass (no test hardcodes 10 —
`test_weights` imports `MAX_PICKS`, `select_picks(99)` clamps to it); `tsc` +
`next build` green (510/510).

**Backfill re-run PENDING.** The slider shows 1-10 until `backfill_portfolio_pit`
regenerates `backtest_pit.json` with `by_count[1..20]` + `max_holdings=20` (5y
window, same data → moderate). Seeded via a user `backfill-portfolio.yml`
dispatch on this branch (`if: ref != main` guard → CI commits the artifact to the
branch). Then the slider goes 1-20 live; merge after verify.

**Files**: `compute/portfolio/weights.py` (`MAX_PICKS` 10→20) ·
`frontend/components/HoldingsCountSlider.tsx` (endpoint-flanking layout) ·
`scripts/backfill_portfolio_pit.py` (comment 1-10→1-20) · `CLAUDE.md` (§In-flight)
· `AGENTS.md` (AI-pick slider note) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## fix(portfolio) — AI-pick dedups dual-class issuers + canonicalizes the class (GOOG/GOOGL bug + cross-quarter churn, in flight, 2026-06-08)

**Bug 1 (user-reported).** `select_picks` (`compute/portfolio/weights.py`) picked
BOTH share classes of a dual-class issuer — Alphabet **GOOG + GOOGL** (also Fox
FOX/FOXA, News Corp NWS/NWSA) — burning two basket slots on ONE company. The A/C
classes share fundamentals → near-identical composites → they rank adjacent and
both got selected. Confirmed in **6 of 20 historical rebalances** (2021-2022),
e.g. 2022-02-14: GOOGL #1 + GOOG #2 → at count-2 the entire basket was a single
issuer.

**Bug 2 (user-reported follow-up).** The first dedup pass kept the FIRST class
seen per issuer = the **higher-composite** one *that quarter*. But the two classes'
near-equal composites flip which ranks higher quarter to quarter → the basket
churned **GOOG↔GOOGL** for the SAME company across rebalances (rotation-history
showed Nov21 GOOG, Feb22 GOOGL, May22 GOOGL, Aug22 GOOG) — spurious turnover for
zero economic change.

**Fix.** A `_DUAL_CLASS_GROUP` map (each dual-class ticker → one **canonical**
issuer key — the Class-A voting ticker GOOGL/FOXA/NWSA) + a dedup pass in
`select_picks`: iterate composite-desc-sorted eligible, keep the FIRST class seen
per issuer, skip its sibling, fill the freed slot with the next distinct name —
AND **emit the canonical class** (not the held one) whenever it is eligible, so
the issuer is represented by the SAME ticker every rebalance (no cross-quarter
churn). Falls back to the held class only if the canonical class is itself
ineligible (e.g. vetoed). Verified against the live universe (only GOOG/GOOGL,
FOX/FOXA, NWS/NWSA have both classes in the index today). One choke point — the
backfill's `picks` + `weights_by_count[n]` (`picks[:n]`) + NAV all derive from
`select_picks`, so the single fix dedups + stabilizes the whole chain.

**Scope.** Backtest-only — `compute/main.py` (live forward compute → rankings.json
/ Top-5) does NOT import `weights.py`, so ZERO live-ranking impact. No schema
change. ruff clean; **54 portfolio tests pass** (+4 dual-class: dedup keeps
higher-composite class + fills next distinct; all-three-pairs collapse;
canonicalizes to the fixed class even when the sibling ranks higher → no churn;
veto×dedup edge keeps the clean sibling).

**Backfill re-run PENDING.** The committed `backtest_pit.json` still has the
duplicated/churning baskets until a `backfill_portfolio_pit` run regenerates it
(5y, same data → moderate). Seed via a user `backfill-portfolio.yml` dispatch on
this branch (`if: ref != main` → CI commits the deduped artifact); verify (no
dual-class co-occurrence AND no GOOG↔GOOGL flip across rebalances — each issuer
shows the SAME canonical ticker every quarter) → merge → stable baskets live.

**Files**: `compute/portfolio/weights.py` (`_DUAL_CLASS_GROUP` + `_company_key`
+ dedup + canonicalize in `select_picks`) · `tests/test_portfolio/test_weights.py`
(3 dedup + 1 veto-edge test) · `CLAUDE.md` (§In-flight) · `AGENTS.md` (select_picks
dedup+canonicalize note) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## fix(portfolio/ui) — AI-pick honest-presentation refinements (calc audit-verified, in flight, 2026-06-08)

**Trigger (user, Thai).** "ตรวจสอบหลักการคำนวณแบบละเอียดว่าคำนวณถูกต้องไหม ทำไมต่างจาก
ดัชนีเยอะจัง" — verify the backtest calculation is correct, and explain why the AI-pick
diverges so far below the S&P 500.

**Audit verdict (`methodology-scientist`, opus, deep).** The backtest NAV math is
**CORRECT — no bug**. 8/8 correctness checks PASS, verified against code + the 54-test
suite + a hand-computed reconstruction: (A1) per-day return = Σ wᵢ·rᵢ; (A2) NAV chaining
continuous across the rebalance seam (mark-to-market THEN reallocate at same NAV — no
gap/double-count/off-by-one); (A3) inverse-vol weights applied to the right holdings;
(A4) NO look-ahead (fundamentals `filing_date <= T`, prices `.loc[:T]`, trades snap to
first trading day ≥ T — pinned by `test_leak_probe_future_blockbuster_is_ignored`);
(A5) **dividend / total-return comparability — the prime suspect — RULED OUT**: both the
portfolio AND the SPY benchmark use `"Adj Close"` from one `fetch_prices(auto_adjust=False)`
path → both total-return; empirically SPY = 1.76× (TR) not 1.38× (price-only), symmetric,
no drag; (A6) costs charged on turnover at rebalance only; (A7) PIT survivorship via
`members_at` (`incomplete_membership_count=0`); (A8) benchmark rebased to 100 at the same
first date.

**Why so far from the index (count=5 −10.1%/yr net gap, ranked).** ~96% pre-cost (cost is
only ~0.41%/yr at 10bps). Drivers: (1) **concentration / idiosyncratic risk at small N**
(~6-9%/yr, dominant — N=1 is −19.8%/yr, N=11 is +13.7% and BEATS SPY, mean-reverts to +9%
at N=20); (2) raw composite signal with `veto_layer_replayed=False` (~2-4%/yr — holds
names the live product would veto; `restatement_contamination_pct=7.5`); (3) no per-sector
cap (~1-3%/yr); (4) annual 10-K instead of live TTM (~1-2%/yr); (5) 2021-26 mega-cap
cap-weighted regime (~1-3%/yr); (6) McLean-Pontiff decay (~0.5-1%/yr); (7) cost (~0.41%/yr,
smallest). The monotone net-CAGR rise with N that converges to / beats SPY at N≈11 is
itself evidence the NAV chain is sound — a broken calc would not coherently converge.

**Refinements (user-authorized via AskUserQuestion 2026-06-08).** Both are PRESENTATION,
not methodology: (1) `AiPickPortfolio.tsx` — an inline **count-reactive concentration
caveat** directly below the headline so the "vs index" number (−64% at count=5) is never
read without "this is a concentrated N-stock book; slide right to diversify, read the full
ladder"; <10 holdings shows the strong concentration line, ≥10 the milder factor-tilt /
proxy-not-live-product line. (2) `scripts/backfill_portfolio_pit.py` `DISCLAIMER_BASE` —
"Figures are gross of slippage" → "Net figures charge a modeled per-side spread cost
(10-25 bps on turnover) but are gross of additional market-impact slippage" (the old
phrasing contradicted the net lines actually shown).

**Scope / rollout.** No schema change. Frontend caveat is immediate on deploy; the
disclaimer text is baked into `backtest_pit.json` `meta.disclaimer`, so it re-bakes on the
**next weekly-cron backfill step** (or a manual `backfill-portfolio.yml` dispatch) — no
re-dispatch is strictly required to merge (it self-heals on the next cron). tsc + build
clean; ruff clean; 54 portfolio tests unchanged (no engine change).

**Files**: `frontend/components/AiPickPortfolio.tsx` (inline caveat) ·
`scripts/backfill_portfolio_pit.py` (`DISCLAIMER_BASE` wording) · `CLAUDE.md` (§In-flight)
· `AGENTS.md` (AI-pick audit + caveat note) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## chore(agents) — agent-team layer + 2 write-capable builders (in flight, 2026-06-08)

Branch `claude/confident-gates-pT9pu`. Studied the experimental Claude Code
**agent-teams** feature ([docs](https://code.claude.com/docs/en/agent-teams) +
[settings](https://code.claude.com/docs/en/settings)) and designed how it maps
onto QuantRank. **Key finding:** agent teams ≠ the existing report-back
subagents — a team is multiple full Claude sessions whose teammates message each
other + share a task list, and it **reuses subagent definitions as teammate
roles**. So almost nothing needs replacing; the durable artifacts are team
recipes + the two write-capable builders the read-only roster lacked. (User
explicitly chose build scope "B" = Layer-0 + 2 implementers, no `red-team-skeptic`.
User is mobile-only, so every recipe carries a web/mobile **subagent fallback**.)

Ships:
- `.claude/settings.json` — `env.CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (inert
  unless a team is created; NOT a model-override var, so `tools/check_model_pin.py`
  is unaffected — verified against its `_OVERRIDE_VARS` list).
- `.claude/agents/TEAMS.md` — 5 team recipes (Methodology Debate · Incident War
  Room · Feature Squad · PR Review Crew · Release Readiness Board), each a desktop
  team form + a mobile/web subagent fallback; teammate protocol (file-ownership,
  schema-triple lockstep, plan-approval, cleanup); limitations from the docs.
- `.claude/agents/compute-builder.md` + `frontend-builder.md` — NEW Tier-5
  write-capable builders owning `compute/**` / `frontend/**` (the layer owners in
  a cross-layer Feature Squad; also usable as scoped write-subagents). NOT on-edit
  auto-spawns — review stays with the existing reviewer agents.
- `.claude/hooks/delegate-first.sh` — **auto-trigger** (added per user request):
  extends the every-turn UserPromptSubmit nudge so the orchestrator
  **auto-proposes** the matching team recipe on team-fit tasks (propose-not-create
  — the feature still needs a user confirm; web/mobile → subagent fallback). Cue→
  recipe table added to CLAUDE.md §Auto-routing "Agent-team auto-proposal" +
  TEAMS.md §Auto-proposal.

Roster 20 → 22 (5 opus / 17 sonnet; 20 at `effort: max`, 2 at `high`). Docs
lockstep: CLAUDE.md (layout + delegation table + model-split/effort + §Gotchas
index + §In flight + §Companion files), AGENTS.md, `.claude/agents/README.md`
(Tier 5 + counts + companion), CONTEXT.md, WORKFLOW.md, docs/GOTCHAS.md (count +
full-detail gotcha), tools/check_model_pin.py (docstring/message count). No
production code or schema change; `check_model_pin.py` passes (new agents carry
floating `model: sonnet` aliases + a `model:` line).

---

## feat(portfolio) — AI-pick high-conviction gate PR-1 (observability) (in flight, 2026-06-08)

**Request (user, Thai).** The AI-pick should select ONLY Strong Buy / Buy names (the
/ranking + /stock recommendation), never Hold/Sell; evict a holding that decays to Sell
at rebalance and replace it; prioritize MoS + require fair-value upside positive (MoS>0);
keep composite score + loss-chance within standard bands.

**Design + ratification.** `financial-engineer` designed the gate; `methodology-scientist`
RATIFIED-WITH-CONDITION (2026-06-08). Gate = `recommendation ∈ {bullish, lean_bullish}`
(Strong Buy/Buy) AND `mos_pct > 0` (strict — Graham-Dodd margin of safety; ~top 30% of the
S&P 500) AND `composite_score ≥ 50` (= `LEAN_BULLISH_COMPOSITE_MIN`) AND
`loss_chance_pct ≤ 45` (below the universe median ≈49; additive via its MoS+flag inputs)
AND the existing 7-veto `is_eligible`. **Fail-closed** on any missing input. Sell-eviction
is automatic (the backtest rebuilds holdings each quarter, so a name that drops below the
gate simply isn't re-selected).

**This PR = the OBSERVABILITY half (Rule 18 / observability-before-wiring).** The backtest
(`scripts/backfill_portfolio_pit.py`) now replays the valuation + recommendation layer
**point-in-time** — reusing the LIVE cross-sectional builders (`_build_universe_metrics` /
`_build_peer_groupings` / `_build_historical_metrics`, imported from `compute.main` so the
live path stays untouched) + `compute_fair_price_ensemble` → `derive_recommendation` /
`derive_loss_chance` — and COUNTS how many cohort names clear the gate per rebalance
(`is_high_conviction` in `weights.py`). **Selection is UNCHANGED** (`select_picks` still
gates on `is_eligible` only); PR-2 wires the gate only after the per-rebalance eligible
count is confirmed to clear `DEFAULT_COUNT` (5) on a real cron (condition **C1**).

**Option B stale-window (condition C2).** The backtest has ANNUAL 10-K data only, so
Defense #3's 180d hard-stale gate would null the ensemble ~3 of 4 quarters. The hard
ceiling is relaxed to **`BACKTEST_HARD_STALE_DAYS = 455`** (= SEC 75d 10-K deadline + 365 +
15d buffer = worst-case legitimate 10-K-to-next gap; a skipped annual cycle still nulls),
threaded as `compute_fair_price_ensemble(hard_stale_days=…)` → `stale_filing_status(hard_days=…)`.
The live path passes nothing → keeps `config.FILING_STALE_HARD_DAYS` = 180; the config
constant is **never mutated**. The real PIT filing lag is computed from the rows
(`_pit_filing_lag`) — NOT left None — so the gate is honest. Look-ahead guard
(`filing_date ≤ T`) unaffected (relaxing how OLD a filing may be ≠ admitting future ones).

**Artifact / scope.** New diagnostics: per-rebalance `eligible_high_conviction_count` +
`mos_positive_count`; `meta.high_conviction_eligible_median` (the C1 acceptance metric),
`meta.recommendation_layer_replayed = True`, `meta.high_conviction_gate_active = False`,
`meta.high_conviction_gate` descriptor. No `schemas.py` model (the artifact self-carries
its meta), no frontend change, **`compute/main.py` untouched** (PR-3 wires the easier
wall-free LIVE forward pick later). risk_flags / valuation_warnings stay empty PIT (the
cross-source manipulation layer is still not replayed — `veto_layer_replayed` stays False).
Deferred watch-items: **C3** (disclose the relaxed window in `meta.disclaimer` when the gate
drives output, i.e. PR-2 — PR-1 changes no shown number); **C4** (Mode B post-cron check of
whether LC≤45 is binding-vs-inert). Perf watch: ~10k PIT ensemble runs/backfill —
`performance-engineer` to confirm under the 40m step cap on the real cron.

**Verification.** ruff clean; **1552 offline tests pass** (no regression); `test-engineer`
adds gate + 455-boundary + threading pins. **Backfill re-run PENDING** to populate the
diagnostics → verify the median eligible count clears 5 → THEN authorize PR-2.

**Files**: `scripts/backfill_portfolio_pit.py` (PIT valuation+recommendation step,
`BACKTEST_HARD_STALE_DAYS`, `_pit_filing_lag`, diagnostics) · `compute/portfolio/weights.py`
(`PickCandidate` +3 fields, `is_high_conviction`, gate constants) ·
`compute/valuation/ensemble.py` (`hard_stale_days` param) · `compute/valuation/applicability.py`
(`stale_filing_status(hard_days=)`) · `tests/test_portfolio/test_weights.py` +
`tests/test_valuation/test_applicability.py` (+ `test_ensemble.py`) · `CLAUDE.md` (§In-flight)
· `AGENTS.md` (AI-pick gate note) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## feat(portfolio) — AI-pick high-conviction gate PR-2 (wire selection) (in flight, 2026-06-08)

**C1 cleared on PR-1's backfill.** PR-1 (#437, merged `3e4f3b23`) shipped the observability
half and its backfill emitted the eligible-count series: `meta.high_conviction_eligible_median
= 52`, per-rebalance min 31 / max 86, **all 20 rebalances ≥ 31 ≫ `DEFAULT_COUNT`=5**. So the
gate is comfortably fillable and methodology-scientist's condition C1 (median eligible ≥
default_count before wiring) is satisfied — PR-2 wires it.

**Change.** `select_picks` gains a keyword `gate: str = "veto_only"`:
- `"veto_only"` (DEFAULT, UNCHANGED): eligible = `is_eligible(c.risk_flags)` — the legacy
  composite-rank basket; every existing caller/test is byte-identical.
- `"high_conviction"`: eligible = `is_high_conviction(c)` (Strong Buy/Buy + MoS>0 +
  composite≥50 + loss-chance≤45 + no veto), then the SAME composite-desc sort + dual-class
  canonicalize + top-N.
The backfill calls `select_picks(candidates, count=MAX_PICKS, gate="high_conviction")`.
**Sell-eviction is implicit** — the backtest rebuilds holdings from scratch each rebalance,
so a name that decays out of the gate at quarter T is absent from the eligible set and not
re-picked (no separate eviction path needed). `meta.high_conviction_gate_active` flips to
**True**; `DISCLAIMER_BASE` now discloses the gate (Strong Buy/Buy + undervalued + score/loss
bands) AND the ~15-month annual fair-value-staleness window vs the live 180d (condition C3).

**Scope.** Backtest-only — `select_picks` is imported ONLY by the backfill; `compute/main.py`
(the live forward compute) is untouched, so ZERO live-ranking impact. No schema model (the
artifact self-carries its meta). The cross-source manipulation vetoes are still NOT replayed
(`veto_layer_replayed` stays False). PR-3 (wire the same gate into the LIVE forward pick — the
wall-free target, ensemble already runs every cron) is the deferred follow-up.

**Verification.** ruff clean; `test-engineer` reframes the PR-1 default-unchanged pin + adds
gate-filters / top-N-by-composite / subset-property (`high_conviction ⊆ veto_only`) /
empty-eligible / dual-class×gate tests. **Backfill re-run PENDING** — the gated
NAV/holdings/rotation only appear after a `backfill_portfolio_pit` run regenerates
`backtest_pit.json`; then verify the gated baskets (only Strong Buy/Buy names, no Sell) +
sanity-check the gated NAV result before merge.

**Files**: `compute/portfolio/weights.py` (`select_picks` `gate` param) ·
`scripts/backfill_portfolio_pit.py` (`gate="high_conviction"` call, `gate_active=True`,
`DISCLAIMER_BASE` gate+staleness disclosure) · `tests/test_portfolio/test_weights.py`
(gate tests) · `CLAUDE.md` (§In-flight) · `AGENTS.md` (AI-pick gate note) ·
`PHASE_STATUS_INFLIGHT.md` (this).

---
