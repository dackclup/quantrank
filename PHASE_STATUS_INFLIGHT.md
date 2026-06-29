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

## feat(backtest) — extend the AI-pick backtest 5y → 10y (in flight, 2026-06-08)

**Request (user).** The chart's "Max" button still shows only 5 years; make it 10.

**Finding.** The frontend "Max" button is NOT the cap — `PERIODS` Max = `years:100`,
which `startIndexForYears` resolves to index 0 (the full `nav.dates` span). It shows 5y
because the DATA is 5y. The survivorship ledger is already 10y-ready
(`historical_universe.EARLIEST_EVENT_DATE` = 2016-01). `performance-engineer` scoped the
extension at **MODERATE** — config bumps + a load-bearing cache-key bump, no novel work.

**Change (5 edits).**
- `compute/config.py` — `PRICES_PERIOD` `"5y"→"10y"` (drives prices AND benchmarks fetch).
- `compute/ingest/fundamentals.py` — `ANNUAL_HISTORY_YEARS` `5→10` (10-K facts back to ~2015
  for the 2016 rebalances).
- `scripts/backfill_portfolio_pit.py` — `--start` default `today.year-5 → today.year-10`
  (the cron's folded step uses this default).
- **cache-key bumps `cache-v5 → cache-v6` on BOTH period-blind caches** (load-bearing — the
  `prices` + `fundamentals_history` parquets are keyed with no period, so a 5y→10y change is
  invisible without a vN bump → a warm run silently returns stale 5y data): (a)
  `.github/workflows/compute-rankings.yml` fast cache (`cache-v5-fast → v6`); (b)
  `.github/workflows/backfill-portfolio.yml` the dispatch path's cache (`cache-v5- → v6-`, key +
  restore-keys). The slow-text cache (filing text) + the **pre-merge-prod-sim** cache stay v5 —
  the simulate validates 1y-window live scoring and doesn't consume the extra history, so no
  forced cold-fetch needed there.
- `compute/output/writer.py` `write_benchmarks_json` — write the **FULL** series instead of
  the `HISTORY_TAIL_DAYS` (~5y) cap (a gap not in the original scope: a 5y-capped benchmarks.json
  would blank the 10y Max chart's SPY/QQQ line pre-2021). benchmarks.json is backfill-only (the
  frontend uses `nav.benchmark`), so no payload cost; per-stock history STAYS 5y via the
  unchanged `HISTORY_TAIL_DAYS` (no stock-chart payload doubling).
- `compute/features/risk.py` `max_drawdown` — **5y window cap** (`s.tail(TRADING_DAYS_PER_YEAR*5)`).
  THIS was a live-scoring-regression gap `quantrank-reviewer` caught: `max_drawdown` was the ONE
  risk metric with no window (it spanned "available history"), and it IS a live risk-pillar metric
  (`pillars.py:194`) — so 10y prices would have captured deeper troughs (2020 COVID) → shifted the
  cross-sectional risk pillar → changed live composite ranks (a Rule-16 retroactive-score change).
  The 5y cap preserves today's full-5y semantics → live `max_dd` is invariant to PRICES_PERIOD.
  (`calmar` was already 3y-capped — safe.) +2 regression tests pin the invariance.

**Zero live-scoring impact (verified — including the reviewer-caught gap).** Every live consumer
of the extra history is windowed: `_cagr_from_history` slices `series[-(years+1):]` (max 5y CAGR),
vol/sharpe/sortino/beta `.tail(1y)`, calmar 3y-cap, **`max_drawdown` NOW 5y-cap (the fix)**,
momentum anchored / `distance_from_52w_high` 1y, technical indicators period-windowed, Piotroski
`iloc[-2]`, value.py point-in-time `current_price`. So the extra 5y is fetched-but-ignored — no
pillar/score change. The Pre-Merge Production Simulation (runs on this compute-touching PR) is the
REQUIRED empirical backstop — it must show composite-rank stability (data-freshness noise only).

**Caveat (disclosed).** ~15-20 tickers renamed before ~2021 (e.g. CDAY→DAY) — yfinance resolves
the CURRENT symbol, not the historical alias, so their 2016-2020 price legs return no data and
are dropped (`if cur_px is None: continue`). The 2016-2020 cohort is therefore slightly thinner
than 2021+. Pre-existing 5y limitation, just more exposed at 10y.

**Rollout.** No schema change; ruff clean; 1585 offline tests pass. The FIRST 10y backfill must
run via the manual `backfill-portfolio.yml` `workflow_dispatch` — the cold run (~60-85m: 10y
price + 10y fundamentals re-fetch + ~40 quarterly rebalances) exceeds the cron's 40m folded-step
cap; warm steady-state (~30-35m) fits afterward. Verify: `meta.as_of_start`≈2016,
`rebalance_count`≈40, the Max chart spans 10y, the benchmark line is non-blank pre-2021.

**Files**: `compute/config.py` · `compute/ingest/fundamentals.py` ·
`scripts/backfill_portfolio_pit.py` · `.github/workflows/compute-rankings.yml` ·
`.github/workflows/backfill-portfolio.yml` (cache-v6) · `compute/output/writer.py` ·
`compute/features/risk.py` (`max_drawdown` 5y-cap) · `tests/test_features/test_risk.py`
(+2 invariance pins) · `CLAUDE.md` (§In-flight + §Gotchas membership/cache/prices) ·
`AGENTS.md` (prices.py note) · `docs/GOTCHAS.md` (cache-v6 + prices) · `PHASE_STATUS_INFLIGHT.md`
(this).

---

## feat(scoring) — technical-pillar MAD factor, PR-1 CONSTRUCT (checkpoint, in flight, 2026-06-08)

**Origin.** Dead-code fix surfaced by `quantrank-reviewer` on PR #440: `pillars.py:170` expected
`macd_signal` to return a dict (`"histogram"` key) but it returns a float → `macd_hist` was always
NaN→50, an inert constant (harmless to ranks today, but a named feature contributing nothing).

**Decision (issue #441; methodology-scientist ×2 + literature-searcher, user-confirmed each fork).**
The MACD **histogram** has NO cross-sectional-factor prior; the MACD **line / MAD** does (WEAK-YES) —
Avramov-Kaplanski-Subrahmanyam 2021 *Rev.Fin.Econ.* 39(2) (MAD ~9% annualized VW alpha, incremental
beyond momentum/52w/profitability) + Han-Zhou-Zhu 2016 *JFE* 122(2) (MA-trend factor, >2× momentum
Sharpe → resolves the momentum-redundancy worry). Windows are LOAD-BEARING for the sign: the alpha is
at LONG 21/200 windows; the 12/26 MACD windows sit in Ko-Wang-Yang 2025 *FAJ*'s short-window
overreaction regime where the cross-sectional sign INVERTS. User chose ACTIVATE-as-MAD-21/200,
observe-first.

**This commit (PR-1 CONSTRUCT only — checkpoint).** Ships the verified construct
`compute/features/technical.mad_scalefree(prices, short=21, long=200) = (SMA_21 − SMA_200)/SMA_200`
(scale-free → no price-level bias in the cross-sectional percentile-rank; positive→bullish; NaN<200),
LITERATURE-ANCHORED in the docstring (Avramov 2021 + Han-Zhou-Zhu 2016 + the load-bearing-window
caveat) — a SEPARATE function from the 12/26 `macd_signal` so windows can't silently shorten. +3
construct pins (scale-invariance — the load-bearing one / sign-at-21/200 / NaN<long). **NOT wired into
the pillar** — `pillars.py` UNCHANGED (dead `macd_hist`=50 stays → pillar byte-identical → Δcomposite=0).

**Remaining (fully specced in issue #441) — NOT in this commit:**
- PR-1 diagnostic half: `main.py` emits 3 `Metadata.mad_*` fields — `mad_coverage_pct` +
  `mad_mom12_corr` + `mad_mom3_corr` (cross-sectional Spearman ρ vs the momentum-pillar metrics) —
  with the pillar unchanged; schema triple PATCH bump `0.10.15 → 0.10.16-phase4.6`.
- PR-2 (separate, after ≥1 cron): wire MAD into the technical pillar (replace dead `macd_hist`),
  GATED on `abs(mad_mom12_corr) < 0.30` AND `abs(mad_mom3_corr) < 0.30` AND `mad_coverage_pct ≥ 90%`
  AND a simulate Top-5/`entered_top5` diff (Rule 16). If either ρ ≥ 0.30 → momentum echo → REMOVE.

**Verification.** ruff clean; construct tests pass; no schema change yet (the construct is unwired).
Checkpoint commit so the verified construct isn't lost; the diagnostic+schema+PR open in a focused
next pass per #441.

**Files**: `compute/features/technical.py` (`mad_scalefree`) ·
`tests/test_features/test_technical.py` (3 construct pins) · `CLAUDE.md` (§In-flight) ·
`PHASE_STATUS_INFLIGHT.md` (this). (issue #441 carries the full spec + remaining tasks.)

---

## ci(cron) — raise folded PIT-backtest step cap 40 → 55m (in flight, 2026-06-08)

**Origin.** `performance-engineer` audit triggered by the question "will a `compute-rankings` run
advance the home-page AI-pick backtest, or hit the folded step's 40m cap now that #440 extended it
5y → 10y?". Verdict: PROPOSE-FIX-1.

**Finding.** The weekly cron's folded `Refresh portfolio backtest (PIT)` step (Phase 7.0 follow-up b)
runs WARM even on a cold-cache cron — the compute step writes all 502 current-universe prices +
fundamentals_history to disk first, in the same job, so the backfill reuses them. It pre-loads ONLY
the current universe (`backfill_portfolio_pit.py:277-284`); the **214 historical-only survivorship-
ledger members are skipped, never fetched** (zero cold-fetch cost — they have no current CIK/price).
The real cost driver is the **134 distinct picked tickers' sequential live-EDGAR amendment fetches**
(~10m), which the backfill does NOT cache-share with the compute step (`restatement_filings.py:183`
`cached_lookback < lookback_days` miss — backfill asks 10y=3719d, compute wrote 5y=1825d; plus the
7-day TTL = weekly cadence). #440's 5y→10y extension ~doubled the distinct picks (64→134) → amendment
cost ~5m→~10m, atop ~30m PIT scoring = **~35-45m warm runtime** vs the **40m** cap → only ~5-10m
headroom; a slow-SEC day (6-8s/call) could push past 40m and the step is killed at the cap.

**Failure mode is BENIGN** (why FIX, not P1): `continue-on-error: true` + the atomic writer (tmp +
os.replace) → a killed step leaves the prior `backtest_pit.json` intact and the rankings commit still
lands; only the backtest `as_of` stalls ~1 week until a SEC-favourable run. Convergence is N=1 (no
multi-run build-up — each run independently completes or is killed; the historical-only members are
never the bottleneck).

**This PR.** Raises the folded step `timeout-minutes` **40 → 55** (+ job ceiling **225 → 240** to
preserve the worst-case cold-compute ~140-160m + capped-backtest headroom) in `compute-rankings.yml`.
The budget comment block is updated with the perf arithmetic. **No code / schema / Python change** —
only a step's wall-clock budget widens, so the prior compute's green CI is unaffected.

**Deferred (NOT in this PR).** FIX-3: align the backfill's amendment lookback 10y→5y
(`config.RESTATEMENT_HISTORY_LOOKBACK_DAYS = 1825d`) so the 134 amendment fetches reuse the compute
step's `edgar_amendments` cache (~10m → ~0m; warm runtime → ~32m). Needs a `methodology-scientist`
verdict — it narrows the per-rebalance restatement-canary window (a disclosure-only field; the
disclaimer already notes the backtest's PIT limitations). FIX-2 (pre-warm `cache-v6-fast`) is moot —
cron run #88 (in progress 2026-06-08) is already warming that key.

**Files**: `.github/workflows/compute-rankings.yml` (folded step `timeout-minutes` 40→55 + comment;
job `timeout-minutes` 225→240) · `CLAUDE.md` (§In-flight rotation) · `PHASE_STATUS_INFLIGHT.md`
(this).

---

## chore(agents) — top-tier subagents opus → fable (in flight, 2026-06-10)

Branch `claude/confident-gates-pT9pu` (reused post-#439; reset onto main). The
main session moved to **Fable 5** (`/model claude-fable-5`), so the 5
judgment-gate agents — `quantrank-reviewer` · `methodology-scientist` ·
`release-captain` · `incident-commander` · `financial-engineer` — move
`model: opus` → **`model: fable`** in frontmatter. Per the standing
model-alias gotcha this is the bare FLOATING alias (resolves to Fable 5 today
and floats forward on CLI updates), NOT a pinned `claude-fable-5` ID — pinned
numbered IDs are the documented future-dated-downgrade footgun and are rejected
by CI.

Guard updated in the same PR: `tools/check_model_pin.py` adds `fable` to
`_ALLOWED_MODEL_VALUES` (else the rename itself would fail CI) and
`ANTHROPIC_DEFAULT_FABLE_MODEL` to `_OVERRIDE_VARS` (parallel to the
OPUS/SONNET/HAIKU triple — blocks the committed-env invisible-downgrade vector
for the new alias). Success/docstring text updated from "latest Opus/Sonnet" to
family-neutral phrasing.

Docs lockstep — every current-state "opus" reference flips to fable: CLAUDE.md
(delegation table · cue table · §Spawn discipline model split "5 fable / 17
sonnet" · `model: fable` override row), `.claude/agents/README.md` (tier-table
Model column ×5 · §Dynamic workflow "fable-5 orchestrator" · model-split +
authoring-conventions §3 "fable + sonnet only"), the 22 agent files' handoff
lines ("the main **fable-5** orchestrator"), AGENTS.md (roster line + alias
mention + fable-5 main session), CONTEXT.md (roster row), WORKFLOW.md (phase
5/6 rows), docs/GOTCHAS.md (alias gotcha rewritten; the `claude-opus-4-8`
BAD-pin example intentionally kept as the illustration). Historical entries in
PHASE_STATUS*/archive intentionally untouched. No production code or schema
change; ruff + check_model_pin + check_doc_test_counts pass locally.

## feat(home) — Current-picks P/L-since-entry column (replaces ScoreBadge)

**Branch**: `claude/mobile-portrait-responsive-2obzg9` (reused post-#444-merge) · **Status**: in flight

The Current-picks list on the AI-pick home page swaps the composite `ScoreBadge` for each holding's
**total return since it entered the basket** — the first rebalance of its current consecutive streak,
which is count-dependent (a recent top-3 entrant can be a long-time top-10 member), so the column
tracks the holdings slider. Build-time `lib/data.ts` samples each currently-held ticker's
adjusted-close history (`public/data/stocks/history/<T>.json`, yfinance auto-adjusted → total-return
basis, same as the NAV lines) at every rebalance date (`entryCloses`, index-aligned with `timeline`)
plus the latest close (`lastCloses`); the client walks the timeline backward to find the streak start
and derives the %. Also sorts Current picks by weight descending. `AiPickData` is the backtest
view-model — NOT part of the Pydantic↔TS↔snapshot triple (no schema bump).

**Files**: `frontend/lib/types.ts` (`entryCloses` + `lastCloses` on `AiPickData`) ·
`frontend/lib/data.ts` (price-history sampling) · `frontend/components/AiPickPortfolio.tsx`
(P/L cell + weight sort) · `PHASE_STATUS_INFLIGHT.md` (this).

---

## feat(scoring) — MAD factor diagnostics, issue #441 PR-1 (in flight, 2026-06-10)

**Origin.** The diagnostic half deferred by the #442 construct checkpoint (issue #441 carries the
ratified spec: methodology-scientist ×2 + literature-searcher; construct = `technical.mad_scalefree
(short=21, long=200)`, merged unwired).

**This PR (observability-before-wiring, Rule 18).**
- `compute/main.py` accumulates `mad_scalefree` per ticker in a NEW pass over the already-populated
  `inputs` dict between Step 7 and Step 8 (the prices DataFrame is already in hand — zero added
  fetches, ~2 `.tail().mean()` per ticker; in-memory iteration only) plus the
  momentum pillar inputs `mom_12_1` / `mom_3_1`, then emits 3 additive diagnostics on `Metadata`:
  - `mad_coverage_pct` — % of the ranked universe with finite MAD (PR-2 gate: ≥ 90%);
  - `mad_mom12_corr` / `mad_mom3_corr` — cross-sectional Spearman ρ of MAD vs `mom_12_1` / `mom_3_1`
    across tickers where both sides are finite (PR-2 gate: BOTH |ρ| < 0.30; either ≥ 0.30 = momentum
    echo → REMOVE per #441). Pandas rank-corr (no scipy / no new dep); < 3 finite pairs or zero
    variance → `None` (JSON never carries NaN).
- Whole diagnostic block wrapped in the graceful-degradation try/except → all 3 fields `None` + one
  `logger.warning`; the cron can never fail on a diagnostic.
- Schema triple PATCH bump `0.10.15 → 0.10.16-phase4.6` (`compute/config.py` + `schemas.py` +
  `frontend/lib/types.ts` + regenerated `schema-snapshot.json`).
- **Pillar UNTOUCHED**: `compute/scoring/pillars.py` zero-diff (dead `macd_hist`=50 stays inert) →
  Δcomposite = 0; pre-merge-prod-sim movers must be data-drift-only (same proof shape as #442).

**Remaining after this PR (issue #441).** PR-2 wires MAD into the technical pillar (replacing dead
`macd_hist`) ONLY if the gate passes after ≥ 1 real cron of `mad_*` data, with a simulate
Top-5/`entered_top5` diff (Rule 16) at wiring time.

**Files**: `compute/config.py` (SCHEMA_VERSION) · `compute/output/schemas.py` (3 fields) ·
`compute/main.py` (accumulate + emit) · `compute/features/technical.py` (the pure
`mad_diagnostics` helper, co-located with `mad_scalefree`; rank-then-Pearson because pandas ≥ 2.2
delegates `method="spearman"` to scipy, which is not a dep) · `frontend/lib/types.ts` (mirror) ·
`frontend/lib/schema-snapshot.json` (regen) · `tests/` (helper pins) · `CLAUDE.md` (§Phase status
schema rotation + §In-flight; drained the merged #443 + #446 entries) · `PHASE_STATUS_INFLIGHT.md`
(this).

---

## docs(roadmap) — roadmap-fit re-scope, user-confirmed (in flight, 2026-06-10)

Branch `claude/confident-thompson-y58bhe`. A `financial-engineer` roadmap-fit
assessment (verified against the repo, not taken from the plan docs) found the
documented roadmap diverged from shipped reality on 8 fronts; the user confirmed
ALL adjustments and delegated sequencing. Docs-only — no production code /
schema / workflow change.

**Re-sequencing decisions** (now encoded in PHASE_STATUS.md §Next deliverables
+ phase table, WORKFLOW.md per-phase blocks, CLAUDE.md §Phase status):

1. **Phase 7.0c PIT veto-replay PROMOTED to next-up** — it is Phase 5 entry
   gate (a). The 10Y backtest shows the raw composite underperforming SPX at
   every N=1-10 with `veto_layer_replayed=False`; the veto-rescue question
   precedes the ~10-12w ML spend (cheapest highest-information experiment:
   ~1-2 PRs + one backfill dispatch).
2. **#441 `macd_hist` fix MUST precede MAD PR-2** — verified in code:
   `technical.macd_signal()` returns a float; `pillars.py` checks
   `isinstance(macd, dict)` which is never True → `macd_hist` always NaN →
   technical pillar effectively 4-of-5 inputs. Wiring MAD (scout #442) before
   the fix makes the MAD-vs-MACD IC comparison meaningless.
3. **NEW data-integrity hardening sprint** (~1-2w) — #248 (V shares ~4× off,
   NO veto fired) · #374 (per-class XBRL override never fires warm) · #376
   (BF-B) · #379 (GEV) · #375 (SNDK) · #385 (APA revenue=None) · #261
   (multi-class overcount) · #247/#289 (NVR DQIC → `risk_flags` gap / empty
   fair price). Phase 5 entry gate (b) — labels trained on silently corrupted
   composites learn noise.
4. **v1.1.0-phase4 tag RE-GATED** — JKP 4i.1 dropped from the hard gate
   (CC BY-NC review #115 unresolved since 2026-05-14; WORKFLOW.md fallback
   clause invoked). New gate: OSAP 4h.1 (#113) + the 4j.2 Qlib blend decision
   on ≥ 1 real cron of `Metadata.alpha158_*` IC evidence (PBO ≤ 0.5 + DSR > 0).
   IPCA 4k.1 (#122) additive, non-blocking.
5. **Phase 6 re-scoped TEXT-ONLY** — §6.0 priority order (Lazy Prices → 8-K →
   FinBERT); Whisper VDQ → **Phase 6.1** (Modal paid infra + IR audio scraping
   + ~250m inference ≈ the 240m cron ceiling; FinBERT batch runs
   monthly/quarterly outside the weekly cron).
6. **Phase 7 remainder renamed Phase 7.1** — gated on (a) the 7.0c veto-replay
   baseline and (b) a longer fit window (3-state Student-t HMM / TDA on a
   single-macro-cycle ~5-10y window = overfit risk; TDA needs external monthly
   compute per §7.11).
7. **Phase 8 staged** — S&P 900 pilot (500 + 400 mid-caps) before 1500;
   off-cycle pre-cache (#249) a hard prerequisite (cold 1500-ticker
   fundamentals ≈ 125m alone at ~1 req/s sustained vs the 240m job ceiling).
   Acceptance criteria gain the pilot + pre-cache checkboxes.
8. **Phase 4.5e PR 5 marked UNBLOCKED** — #287 PR B (FORM4_FETCH_SKIP revert)
   merged as PR #431; needs ≥ 1 cron of `form4_rule10b5_one_excluded_count`
   (and ≥ 4 crons ahead of the 2026-08-19 Q3 cohort audit). #287 itself is a
   close-candidate once a cron confirms `form4_wall_clock_seconds` populates.

**Doc-drift fixes folded in:** PHASE_STATUS.md Phase-7 table row ("not started"
→ 7.0 SHIPPED / 7.1 gated) · Phase 4/5/6/8 row gate notes · subagent row
20/4-tier/opus → 22/5-tier/fable (+ Tier 5 Builders) · Current-state date bump ·
stale "In flight (none through #310)" marker replaced · Recently-merged
extended #431-#446 · §Next deliverables stale items (the "IN FLIGHT" #287-PR-B
entry — merged as #431 — and the long-merged PR #300) replaced by the new
ordering · §Open issues line rebuilt as-of 2026-06-10 (29 open issues, grouped
by track; #120 annotated "4j.1 DONE #426, re-scoped to the 4j.2 blend
decision") · WORKFLOW.md session-start schema pointer 0.10.13 → 0.10.15 ·
"Opus agents" → "Fable agents" in the cadence invariants (missed in #446) ·
Phase-7 deps `gtda` "(AGPL — verify)" → Apache 2.0 (now matches the §License
re-verification block in the same file) · per-phase original-plan "Tag vX.Y"
strings marked superseded by the real release ladder · Phase 5 acceptance
Supabase row cross-linked to the §Connectors explicit-client-PR rule.
Post-rebase note: branch rebased over #447 (MAD diagnostics, schema `0.10.16`)
— schema pointers in this PR updated 0.10.15 → 0.10.16 and the #441 item
re-worded to "fix gates the PR-2 WIRING" (the #447 diagnostics deliberately
kept the dead `macd_hist`).

**Deliberately NOT in this PR:** the veto-replay implementation (compute
change, own PR) · the #441 fix (compute change, own PR) · SKILL.md (no
constant moved — schema/veto counts unchanged) · METHODOLOGY.md (different
lifecycle per phase-status-bump skill).

**Files**: PHASE_STATUS.md · WORKFLOW.md · CLAUDE.md · PHASE_STATUS_INFLIGHT.md
(this).

---

## refactor(scoring) — issue #441 close-out: REMOVE MAD + dead `macd_hist` (in flight, 2026-06-10)

**The gate fired.** First real cron with the #447 diagnostics (2026-06-10, commit `1d12b097`,
manual dispatch) populated: `mad_coverage_pct` = 99.6 · `mad_mom12_corr` = **0.834** ·
`mad_mom3_corr` = **0.807**. The pre-registered PR-2 wiring gate (BOTH |ρ| < 0.30 AND
coverage ≥ 90%) FAILS decisively on the redundancy arm — coverage passes (clean measurement),
both correlations sit ~20 / ~18 SE above the 0.30 line (Fisher SE ≈ 0.045 at n≈500).

**methodology-scientist RATIFY-REMOVE** (one cron decision-grade):
- Mechanically expected: MAD 21/200 is algebraically a trapezoid-kernel-weighted sum of ~200
  trading days (~9.5 months) of returns — nearly the `mom_12_1` window; the skip-month
  difference did not de-correlate.
- Every candidate artifact (rank-then-Pearson, winsorize-rank normalization, large-cap range
  restriction) biases ρ DOWNWARD → 0.83 is a floor, not an inflation.
- NO literature contradiction: Avramov-Kaplanski-Subrahmanyam 2021 / Han-Zhou-Zhu 2016 measured
  CONDITIONAL incremental alpha (the orthogonal component, broad CRSP, small-cap-concentrated);
  ρ² ≈ 0.70 still leaves ~30% orthogonal variance — both facts coexist. But QuantRank's
  fixed-weight LINEAR pillar mean has no orthogonalization machinery, so wiring raw MAD at
  ρ = 0.83 re-counts momentum past its declared 0.10 weight (Daniel-Moskowitz 2016 crash-risk
  style) instead of importing the papers' alpha. The |ρ| < 0.30 gate is the right test FOR THIS
  ARCHITECTURE. (HZZ's incrementality also needed multi-horizon machinery we never built —
  the WEAK-YES prior label was correct.)

**This PR (scope a, full cleanup; schema PATCH `0.10.16 → 0.10.17-phase4.6`).**
- DELETE `technical.mad_scalefree` + `technical.mad_diagnostics` + the main.py diagnostic pass
  + the 3 `Metadata.mad_*` fields + TS mirror + snapshot regen + the 15 MAD tests + the
  `test_config.py` pin bump.
- DELETE the dead `macd_hist` slot in `pillars.py` (premise corrected by methodology-scientist:
  NOT a constant-50 diluter — `macd_signal` returns float, the `isinstance(macd, dict)` check
  never fired, the all-NaN column defeats sector-median imputation and `average_pillar_score`
  skipna-drops it; the pillar was ALREADY a clean 4-metric mean). Residue removed = the falsified
  metric inventory + the Rule-7 coverage-denominator edge (3-of-5 → 2-of-4 for a ticker with
  exactly 2 finite technical metrics; expected Δrank = 0 since all 4 live metrics come from the
  same OHLCV frame). Simulate must show data-drift-only movers.
- `technical.macd_signal` itself STAYS (an available indicator; only the dead consumption goes).
- NO replacement 5th input — "fill the hole" is backwards factor design. If appetite arises:
  short-term reversal (Jegadeesh 1990; lives in the skip-month, low mechanical overlap) or
  idiosyncratic vol (Ang-Hodrick-Xing-Zhang 2006 *JF*; must also clear the risk pillar) via the
  same design → literature → pre-registered diagnostic → gate ladder #441 just validated.

**Evidence preserved**: this entry + the issue #441 close-out comment (values, commit, the
ratification) — NOT in live schema (the one-shot decision is consumed; unlike `alpha158_*`
there is no remaining consumer).

**Files**: `compute/features/technical.py` · `compute/main.py` · `compute/output/schemas.py` ·
`compute/config.py` (0.10.17) · `compute/scoring/pillars.py` (dead slot) · `frontend/lib/types.ts`
· `frontend/lib/schema-snapshot.json` · `tests/test_features/test_technical.py` ·
`tests/test_output/test_mad_diagnostics_schema.py` (deleted) · `tests/test_config.py` ·
`tests/test_scoring/*` (macd_hist shape pins, as found) · `CLAUDE.md` · `SKILL.md` ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## chore(agents) — 3 NEW data subagents: data-pipeline-engineer + data-analyst + data-scientist (in flight, 2026-06-10)

Branch `claude/confident-gates-pT9pu` (reused, reset onto main `bac8a80`). User asked to add the
data-discipline agents the project needs (Data Engineering / Data Analyst / "all data roles").
Rather than bolt on ~5 generic roles (which would violate the one-job-per-agent discipline + create
dead config a reviewer would flag), mapped the request to QuantRank's REAL data surfaces and added
the 2 genuinely-needed, NON-overlapping roles — both read-only sonnet `effort: max`, Tier 3:

- **`data-pipeline-engineer`** (Data Engineering) — holistic health of the INPUT + data layer: all
  three sources (SEC EDGAR via edgartools · yfinance prices+info · Wikipedia constituents), the
  on-disk parquet caches + cache-key versions, the survivorship membership ledger
  (`scripts/verify_membership_ledger.py` add/remove balance + 498-506 band + rename-awareness), data
  freshness/staleness (`fundamentals_latency_p95_seconds`, `*_wall_clock_seconds`, `as_of` dates),
  cross-source `*_coverage_pct`, and backtest data artifacts (`backtest_pit.json` / `benchmarks.json`
  structural integrity). DISTINCT from edgar-debugger (EDGAR-only reactive) / performance-engineer
  (latency) / stock-detail-auditor (per-stock output) / compute-builder (writes code).
- **`data-analyst`** (Data Analyst / BI) — exploratory / descriptive analytics over the OUTPUT
  (rankings.json + metadata.json + stocks/*.json + backtest NAV): score-tier histograms,
  sector/industry breakdowns, recommendation mix, MoS + valuation-method distributions, factor
  spreads, Top-N composition, aggregate outliers, week-over-week drift. Uses jq + Python stdlib (no
  pandas dep). DISTINCT from stock-detail-auditor (per-ticker correctness) / defense-layer-auditor
  (defense-flag firing) / methodology-scientist (academic/normative).

- **`data-scientist`** (Data Science / ML — added mid-PR on explicit user request, overriding the
  initial "premature until Phase 5" call) — the EMPIRICAL seat: signal predictive power (Spearman
  IC, IC decay, forward returns), backtest statistical scrutiny (PBO/DSR, deflated Sharpe,
  leakage/look-ahead probes), interpretation of `compute/validation/**` + `compute/features/**`
  (OSAP / Qlib Alpha158 / IPCA) diagnostics, and Phase-5 ML meta-learner scoping (purged
  time-series CV, baseline-first, Rule-18 rollout). Seats stay separate by design:
  financial-engineer DESIGNS → data-scientist EVALUATES → methodology-scientist RATIFIES.
  DISTINCT from data-analyst (descriptive vs inferential/predictive).

STILL DELIBERATELY SKIPPED (documented for the next maintainer): data-quality-engineer (output QC
already covered by stock-detail-auditor + defense-layer-auditor + schema-sentinel; input QC folded
into data-pipeline-engineer), data-governance/catalog/lineage (overkill for a static-site project;
dependency-auditor + THIRD_PARTY_NOTICES cover license posture), data-viz/BI
(frontend-design-reviewer + the Next.js site).

Tier 3 Specialized 6 → 9; roster 22 → 25 (5 fable / 20 sonnet; 23 at `effort: max`, 2 at `high`).
Both auto-spawn post-cron (added to the `workflow_dispatch`-green batch) + on their on-demand cues.
Docs lockstep: CLAUDE.md (layout · delegation table · cue table · post-cron batch · model-split),
`.claude/agents/README.md` (Tier 3 table + header + counts + rationale + model split), AGENTS.md,
CONTEXT.md, WORKFLOW.md (Monitoring phase), docs/GOTCHAS.md (count), tools/check_model_pin.py (count).
No production code or schema change; ruff + check_model_pin + check_doc_test_counts pass locally.
## feat(backtest) — Phase 7.0c PIT veto-layer replay + artifact exports (in flight, 2026-06-10)

Branch `claude/confident-thompson-y58bhe` (reset onto main `bac8a803` post-#449;
the interim PR #450 macd_hist-restore was closed as superseded by #449's
evidence-ratified REMOVE — see the #450 close comment). Ratified roadmap
item 1 (PR #448) — **Phase 5 entry gate (a)**.

**Veto replay (scripts/backfill_portfolio_pit.py only):** replays **6 of 7**
active vetoes point-in-time at every one of the 40 rebalances, from the PIT
data the backfill already loads — `altman_distress` · `sloan_accruals_top_decile`
(within-PIT-cohort cross-section at T) · `net_issuance_top_decile` (`today=T`
so the 12m lookback anchors to the rebalance date) · `beneish_manipulation_veto`
+ `dechow_manipulation_veto` (PIT prior-year history filed ≤ T) ·
`data_quality_input_corruption`. `non_reliance_filing` is **EXCLUDED with
disclosure** — its 8-K Item 4.02 history is not in the preloaded PIT data and
would need per-name EDGAR fetching; recorded as
`meta.vetoes_not_replayed=[{name, reason}]`. `meta.veto_layer_replayed`
False → True; `meta.vetoes_replayed` lists the six; `RULE_VERSION` →
`phase3-effective-weights+veto-replay`; `DISCLAIMER_BASE` rewritten to the
honest 6-replayed/1-excluded state. Vetoed names are excluded from pick
eligibility exactly like live (`select_picks`; next-ranked clean name fills
the slot); their composite is NEVER modified (Rule 16) and they still appear
in `full_ranked` with their honest score.

**New per-rebalance artifact exports** (the Iteration-1 experiment backlog;
artifact is self-carried — NO schema-triple change, `schema_check` clean):
`vetoed_pick_candidates` (would-have-been-picked names + flags — the
selection-effect headline) · `full_ranked` top-40
`{ticker, composite_score, sector, mos_pct, recommendation}` ·
`holdings[].mos_pct` · `sector_weights_by_count` · `high_conviction_count`.
Size +~550KB → ~1.85MB (< 2MB budget); warm runtime +60-90s.

**Tests:** 3 wiring-isolation repairs (the new `_compute_pit_risk_flags`
fires DQIC on synthetic fixtures → zero picks; now mocked for wiring tests +
the wellformed-artifact test asserts the new meta shape) + 7 new (rule-version
suffix ×2 · vetoed-candidate excluded-from-picks + Rule-16 composite parity ·
full_ranked 5-field schema + descending order · sector-weights sum-to-1 ·
high_conviction_count bounds · today=T forwarding spy). Plus a fix to the
PRE-EXISTING `test_weights.py::test_hc_gate_subset_of_veto_only_property`
Hypothesis property whose invariant was wrong (HC top-N ⊄ veto-only top-N in
general; corrected to the gate-level eligibility subset).

**Post-merge step:** one `backfill-portfolio.yml` dispatch produces the first
`veto_layer_replayed=True` artifact; then the quarterly beat-rate board is
re-run against the Iteration-1 baseline (N=5 45% · N=9 70% · N=18 72.5% vs
SPY) — the Phase 5 gate (a) measurement.

**Review-round additions (quantrank-reviewer FIX-AND-RE-REVIEW + frontend-design-reviewer):**
round-once-per-sector fix in `_sector_weights_by_count` (kills the boundary
flake at root) + honest test tolerance 1e-3 · a REAL-wrapper
`_compute_pit_risk_flags` unit test (kwarg-drift would otherwise green-suite
but kill the dispatch) · an `ACTIVE_VETO_FLAGS` set-equality drift guard (an
8th veto can't silently under-claim `veto_layer_replayed=True`) · DATA-DRIVEN
veto-replay captions (`getAiPickData()` forwards `vetoLayerReplayed` +
`vetoesNotReplayed`; AnnualReturnsTable footnote + AiPickPortfolio caveat
branch on it — mandatory, not optional: the weekly cron auto-refreshes the
artifact post-merge, so hardcoded captions would go false on their own) ·
`flagLabel()` on the excluded-veto names ("8-K Item 4.02 non-reliance", not
snake_case) · the stale CLAUDE.md/docs/GOTCHAS.md AnnualReturnsTable gotcha
rewritten window-neutral + flag-neutral (the old text pinned BOTH
`veto_layer_replayed=False` AND the superseded 5y "loses at every N" result).

**Files**: scripts/backfill_portfolio_pit.py ·
tests/test_portfolio/test_backfill_integration.py ·
tests/test_portfolio/test_weights.py · frontend/lib/data.ts ·
frontend/lib/types.ts (non-schema section) ·
frontend/components/AnnualReturnsTable.tsx ·
frontend/components/AiPickPortfolio.tsx · docs/GOTCHAS.md · CLAUDE.md
(§In-flight rotation + item-1 marker + gotcha line) · PHASE_STATUS.md
(§In-flight rotation + Recently-merged #448/#449 backfill) ·
PHASE_STATUS_INFLIGHT.md (this).

---

## chore(analysis) — veto-counterfactual tool + the gate (a) verdict (2026-06-10)

**Branch**: `claude/confident-thompson-y58bhe` · **Status**: in flight

Ships the counterfactual analysis tool
(`scripts/analysis_veto_counterfactual.py`, dev-only, network) + the gate (a)
verdict docs. The verdict was measured on the FIRST
`meta.veto_layer_replayed=true` `backtest_pit.json` (cold backfill dispatch
on this branch, run 2026-06-10 16:12 UTC, post-#451 code: 40 rebalances
2016-08-14 → 2026-05-15, 6-of-7 vetoes replayed, `non_reliance_filing`
disclosed-excluded). That cold artifact commit was SUPERSEDED before this PR
merged — the 2026-06-10 23:51 UTC cron warm refresh landed an equivalent
veto-replayed artifact directly on `main`, so the branch copy was dropped on
rebase and this PR carries only the tool + docs.

**Phase 5 entry-gate (a) verdict — "does the defense layer rescue the
composite?" → NO on returns, PARTIAL on drawdown protection.** The
counterfactual rebuilds the veto book and a no-veto book per rebalance from
the artifact's own `holdings` + `vetoed_pick_candidates` + `full_ranked`
(conviction-side-qualified re-insertion) and prices BOTH through the real
engine fns on identical yfinance data — validation: rebuilt veto-book net
CAGR matches `nav.by_count[N].net` to 0.1pp at every N. Results:
CAGR delta (veto − no-veto) mean **−1.21pp**, negative at **16/20 N**
(ex-N1-2 mean −0.65pp; lone large positive +4.7pp at N=5 is a boundary
outlier between ~0 neighbors N=4/N=6). Year pattern is a clean
**anti-growth tilt**: veto HELPS every drawdown-ish year (2018 / 2022 /
2025 / 2026 at every N inspected) and HURTS every growth-led year (2019 /
2020 / 2023 / 2024). Bite is **97% one flag** — `sloan_accruals_top_decile`
(159/164 in-range candidacies), firing repeatedly on structural compounders
(NVDA 14×, FAST 11×, NRG 10×, LRCX 9×, ANET 7×, LLY 4×); only 82/164
candidacies clear the conviction-side gate, so the true bite ≈ 2/rebalance.
2025's miss is NOT veto-caused — the no-veto book lost 2025 HARDER (N=5
−9.4% vs veto −0.0% vs SPY +17.7%): the failure is in the composite signal.
Follow-up routed to `methodology-scientist` via issue (Sloan veto → Q3
2026-08-19 cohort audit; candidate outcomes: demote-to-annotate for pick
eligibility per Rule 16, growth-conditioned percentile, or keep-as-is
accepting the documented cost as drawdown insurance). Per pre-registration
discipline NO threshold/flag change ships from this in-sample evidence alone.

**Files**: scripts/analysis_veto_counterfactual.py ·
PHASE_STATUS_INFLIGHT.md (this) · CLAUDE.md (§In-flight rotation).
(The cold artifact commit `29c665cf` was dropped on rebase — superseded by
the cron's warm veto-replayed copy on `main`.)

---

## fix(ingest) — issue #374 RATIFY-B dual-class share-count fix (in flight, 2026-06-11)

**Schema `0.10.17 → 0.10.18-phase4.6`** (additive PATCH). Closes the
warm-cache silently-wrong `shares_outstanding` for the 6 dual-class S&P 500
tickers (GOOG/GOOGL · FOX/FOXA · NWS/NWSA, all on
`MULTI_CLASS_OVERCOUNT_ALLOWLIST`).

**Origin** — surfaced this session by a post-cron audit cascade on the
2026-06-10 cron (`data-pipeline-engineer` → `stock-detail-auditor`): metadata
`multi_class_per_class_attempt_count=0` flagged the per-class override not
firing on warm crons; the per-stock audit found GOOG=GOOGL=5,438M (and
NWS=NWSA, FOX=FOXA carrying byte-identical `fair_price.median` within each
pair) = shared-CIK-parquet contamination. `data-analyst` counterfactual:
the fix moves GOOGL rank 42→~85 (per-class) or the convention determines
4-vs-43 swing. `methodology-scientist` ruled **RATIFY-B** (all-classes
company-total divisor) on four unanimous anchors (US GAAP ASC 260 ·
issuer's own filed combined EPS · Graham/Ohlson-RIM/Penman per-share theory ·
Damodaran 2019 Ch.16), correcting one brief error (Altman X4 here is Z″
book-equity, not MVE → outside blast radius).

**Root cause** — the fundamentals cache is keyed by CIK
(`compute/cache/fundamentals/<CIK>.parquet`); both tickers of a dual-class
pair share one file. PR #269's Branch 3 OVERWROTE `shares_outstanding` with
the listed line's per-class count → (a) a category error for the per-share
chain (company NI ÷ one class ≈ 2.2× EPS inflation; GOOGL EPS 29.46 vs
Alphabet's filed ≈13.2), and (b) on warm crons the last-writer-wins race
served one class's count to both lines (9/11 cron commits wrong).

**Fix** (compute/** + schema triple + tests):
- `compute/ingest/fundamentals.py` — Branch 3 line
  `balance_values["shares_outstanding"] = per_class_shares` →
  `_shares_outstanding_listed_class = per_class_shares`. `shares_outstanding`
  retains the companyfacts COMPANY-TOTAL aggregate (class-invariant → the
  CIK-cache collision **can no longer corrupt it**: the structural close of
  #374, not a re-pin). New `FundamentalsSnapshot.shares_outstanding_listed_class`
  attribute carries the per-class value (cold-path-only; `None` on warm —
  documented, no scoring consumer).
- `compute/output/schemas.py` — additive `RawMetrics.shares_outstanding_listed_class:
  float | None = None`; `compute/main.py` `_build_raw_metrics` wires it through.
- `compute/config.py` — `MULTI_CLASS_OVERCOUNT_ALLOWLIST` docstring rewritten
  (now drives the per-class FIELD, not a `shares_outstanding` override; BRK-B
  1500:1 deferral retained).
- Series-consistency SELF-HEAL: `compute/scoring/risk_overlay.py`
  `_net_stock_issuance` + `compute/scoring/dechow_f.py` `_issuance_dummy` —
  invariant comments; the annual share-count history is already the companyfacts
  aggregate, so the revert does NOT fabricate a one-time ln(5.4B/12.1B)≈−0.80
  issuance spike (the transition hazard the methodology pinned).
- Schema triple: `frontend/lib/types.ts` mirror + `schema-snapshot.json`
  regenerated (`schema_check` green).

**Expected production effect** (latent until a cache-key bump / cold backfill
repopulates the 6 parquets — PR #298 cache-v5 precedent): GOOGL's ~7%
EPS/fair-price overstatement removed (rank 42→~85, GOOG converges adjacent —
both honest, artifact removal); NWS/NWSA/FOX/FOXA UNCHANGED (their aggregate
counts were accidentally ASC-260-correct, confirming RATIFY-B over the rejected
per-class RATIFY-A which would have standardized the artifact onto four more
lines). Defense layer UNCHANGED (Sloan/Beneish/Altman share-count-independent;
`multi_class_aggregate_shares_suspected` annotate still fires ≈6 as the
new-entrant discovery signal). No manipulation_index weight change, no new flag.

**Verify** (deps installed in-container this session — network policy allows
PyPI): `ruff check .` clean · `schema_check` in-sync (snapshot regenerated) ·
`pytest -m "not network"` 1603 pass / 0 fail (+10: `test_issue374_ratifyb.py`
×7 [GOOG/GOOGL aggregate-retained · non-allowlist None ×2 · `_build_raw_metrics`
wiring ×2 · NSI series-consistency] + 3 reversed-semantics repairs in
`test_fundamentals.py`/`test_issue288_xbrl_concept_tuple.py`) · `test_config.py`
SCHEMA_VERSION assertion bumped.

**Tests** were green on first run (production landed before the test pass), so
they document RATIFY-B rather than driving it red→green — noted honestly.

**Spun off**: **#455** (Phase 7.1 — CIK-level Top-N dedup; the methodology Q5
flag: post-convergence GOOG+GOOGL can both rank into Top-N = doubled
single-issuer exposure that inverse-vol won't dedupe; also affects the 7.0c
PIT backtest `nav.by_count[N]`).

**Open follow-ups** (NOT this PR): (1) the cache-key bump / cold backfill to
manifest the fix in production; (2) `no_fundamentals_filing` annotate for new
index entrants with `snap=None` (FDXF pattern, surfaced in the same audit
cascade — display-legibility gap, fold into the data-integrity hardening
sprint).

**Files**: compute/ingest/fundamentals.py · compute/output/schemas.py ·
compute/main.py · compute/config.py · compute/scoring/risk_overlay.py ·
compute/scoring/dechow_f.py · frontend/lib/types.ts ·
frontend/lib/schema-snapshot.json · tests/test_ingest/test_issue374_ratifyb.py
(new) · tests/test_ingest/test_fundamentals.py ·
tests/test_ingest/test_issue288_xbrl_concept_tuple.py · tests/test_config.py ·
CLAUDE.md (§Gotchas one-liner + §In-flight rotation) · AGENTS.md (§Boundaries
🚫 Never) · SKILL.md (schema-version table) · docs/GOTCHAS.md (full detail) ·
PHASE_STATUS_INFLIGHT.md (this).
## feat(portfolio) — ADAPTIVE AI-sized basket; user count slider retired (2026-06-11)

**Branch**: `claude/confident-thompson-y58bhe` · **Status**: in flight

User decision: AI picks now sizes its OWN basket each rebalance — the
holding count is no longer a user choice. Bounds 1-20 (cap = MAX_PICKS),
count varies by quarter. Rule: every high-conviction-gated pick with
`composite_score >= 65`, floor 5 names. Constants `ADAPTIVE_COMPOSITE_MIN`
/ `ADAPTIVE_MIN_PICKS` live in ONE place (`scripts/backfill_portfolio_pit.py`)
`methodology-scientist` Mode-B verdict: **RATIFY 2026-06-11** — all three
constants as proposed, conditional on C1 (provenance comment on the
constants block — landed) + C2 (test pins incl. the inclusive-65.0
boundary — landed) + C3 (gates A1 score-drought / A2 inflation / B
relative-vs-by_count[8]-and-SPY @ 8th live rebalance / C freeze-lock
registered on issue #130 — landed). The in-sample-sweep concern was
explicitly disclosed in the dossier (65 is not a
canonical TIERS boundary; mitigants = coarse 4-point grid, monotone
dose-response 55→60→65 in BOTH window halves with a documented cliff at 70,
floor-5 chosen from {1,3,5} where it binds only in tiny-count quarters, and
consistency with the independent fixed-N sweet spot at N=8-14).

Evidence (production veto-replayed artifact, real engine fns, yfinance Adj
Close, net 10bps/side, 40 rebalances 2016-08 → 2026-05; SPY 14.8% CAGR):
adaptive book CAGR **22.8%**, quarterly beat **27/40 (68%)**, maxDD
**−32.0%** (best of every rule tested), split-half x2.90 / x2.60 vs SPY
x2.24 / x1.73; counts 5-13, mean 8.0. Rejected alternatives: hold-all-HC
(degenerates to always-20 — every rebalance had ≥ 20 eligible; 17.0% CAGR),
canonical ≥55 (inert, mean 19.5 names), canonical ≥70 (0-8 names, −47.4%
DD, 11.5% CAGR), parameter-free largest-gap elbow (ten 1-name quarters).

Artifact contract (self-carried, no schema-triple change):
`meta.adaptive_rule = {composite_min, min_picks, max_picks}` ·
`nav.adaptive = {gross, net, net_conservative, turnover_by_rebalance}`
(same axis/pad contract as by_count entries) ·
`rebalances[*].adaptive_count` (adaptive book = `holdings[:adaptive_count]`
prefix; weights = `weights_by_count[adaptive_count]`, reused not
recomputed). `by_count` + `default_count` retained for analytics +
fallback. Frontend renders the adaptive book with NO slider when
`nav.adaptive` is present, and falls back to the legacy slider UI when
absent — deploy-safe across the artifact regeneration boundary (the same
two-step as PR #451 → #453: code first, then a backfill dispatch / cron
regenerates the artifact).

**Files**: scripts/backfill_portfolio_pit.py · frontend/lib/data.ts ·
frontend/lib/types.ts (non-schema section) ·
frontend/components/AiPickPortfolio.tsx ·
frontend/components/HoldingsTimeline.tsx (per-quarter adaptive counts) ·
frontend/app/page.tsx (hero + metadata branch) ·
tests/test_portfolio/ (adaptive-book tests) · docs/GOTCHAS.md (slider
gotcha rewritten adaptive-first) · CLAUDE.md (§In-flight rotation + gotcha
index line) · PHASE_STATUS_INFLIGHT.md (this).

---

## chore(ci) — cache-v7 bump: manifest the #374 RATIFY-B fix (in flight, 2026-06-11)

The deploy step #456 deliberately deferred: the RATIFY-B source fix is latent
on warm crons because the 6 `MULTI_CLASS_OVERCOUNT_ALLOWLIST` tickers'
CIK-keyed parquets still carry pre-fix per-class / cross-contaminated values
(`fetch_fundamentals` short-circuits at `_is_fresh()` before Branch 3; the
#456 pre-merge sim proved it live — all 6 tickers absent from the movers on a
warm restore). PR #298 cache-v5 precedent; bump-taxonomy trigger 3
("value-correctness fix inside a live-fetch-only code path that cache replay
short-circuits past"), second firing — same Branch 3 both times.

**Changes** (key-string bumps only, no workflow logic):
- `compute-rankings.yml` fast bundle `cache-v6-fast → cache-v7-fast` — next
  weekday cron (22:00 UTC) cold-fetches fundamentals (~25-50 min, inside
  `timeout-minutes: 195`) and repopulates all parquets on the ratified
  company-total basis. Slow-text `cache-v5-text` untouched (run-id idiom, no
  share data, governed separately).
- `backfill-portfolio.yml` `cache-v6 → cache-v7` — its prefix restore-keys
  keep matching the cron's `cache-v7-fast-*` saves (the stated "same cache
  key as compute-rankings" design).
- `pre-merge-prod-sim.yml` `cache-v5 → cache-v7` — heals a real drift: the
  sim was stuck on the dead v5 family (last shared with the cron pre-#416),
  which post-#456 would have recomputed GOOG/GOOGL on stale shares against a
  corrected main baseline → phantom ±4.5 movers on EVERY future PR sim. On
  the v7 family the sim restores the cron's corrected saves
  (basis-consistent + warm). First sim on this PR runs cold — expected to
  SHOW the fix manifesting (GOOGL ≈ −4.5 composite, rank → ~85).
- `tests/test_workflow_cache_coverage.py` — `test_workflow_cache_key_is_v5`
  was ROTTED: after the v6-fast bump it kept passing by matching the
  slow-text key substring (`key: cache-v5-text-…`). Rewritten as
  `test_workflow_fast_cache_key_is_v7` pinning the FAST key explicitly,
  with the full v4→v5→v6-fast→v7-fast bump history + taxonomy in the
  docstring.

**Expected first-cold-cron evidence** (next weekday cron after merge):
`multi_class_per_class_override_count` = `…attempt_count` = 2 ·
GOOG = GOOGL `shares_outstanding` ≈ 12.09B (class-invariant) ·
`shares_outstanding_listed_class` populated (GOOG 5.43B / GOOGL 5.82B) ·
GOOGL EPS ≈ 13.2 (Alphabet's filed figure) · GOOGL rank ≈ 85, GOOG adjacent ·
NWS/NWSA/FOX/FOXA |Δrank| ≤ ~2 · `cross_source_disagreement` −2 fires
(GOOG/GOOGL reconcile with yfinance company-total marketCap).

**Verify**: ruff clean · `pytest tests/test_workflow_cache_coverage.py
tests/test_config.py` green (rewritten test passes against the bumped YAML) ·
YAML parse check on all 3 workflows · security-reviewer pass on the
workflow diff (key-strings only; permissions/triggers/steps untouched).

**Files**: .github/workflows/compute-rankings.yml ·
.github/workflows/backfill-portfolio.yml ·
.github/workflows/pre-merge-prod-sim.yml ·
tests/test_workflow_cache_coverage.py · CLAUDE.md (§In-flight rotation —
drained merged #453 + #456 bullets — + §Next-deliverables item-1 pointer
fix) · PHASE_STATUS_INFLIGHT.md (this).

---

## docs(portfolio) — adaptive-artifact verification + first A1/A2 gate baseline (2026-06-11)

**Branch**: `claude/confident-thompson-y58bhe` · **Status**: in flight

Durable record of the FIRST post-#457 adaptive artifact verification. The
branch's backfill-dispatch copy (04:04 UTC) was SUPERSEDED before merge by
the rankings-dispatch warm refresh that landed directly on `main`
(`65bfd335`, 04:20 UTC, post-#456 share-count fix + post-#458 cache-v7) —
the branch artifact commit was dropped; main's copy is canonical. Both
artifacts verified identically: `meta.adaptive_rule = {composite_min: 65.0,
min_picks: 5, max_picks: 20}` · `nav.adaptive` (gross/net/net_conservative/
turnover) · `rebalances[*].adaptive_count` + `adaptive_count_raw` · counts
5-13 (mean 8.0) · adaptive net CAGR 22.8% vs SPY 14.9% — matches the #457
ratified evaluation to the decimal · `veto_layer_replayed` stays true.

**First official A1/A2 gate read** (gates registered on issue #130):
neither fires on history; 3 raw<5 drought quarters in 10y (2020-02 raw 3 ·
2025-11 raw 3 · 2026-02 raw 2) — the two most-recent quarters are droughts
and the current book (2026-05-15) holds the FLOOR 5 (ALL · APA · LULU ·
IBKR · ACGL; raw back to 5 at 2026-05). Conviction is currently thin —
watch A1 at the next cron/cohort audit. Frontend flip verified on a local
static export against the adaptive artifact: home renders the adaptive
branch (no slider, varying-count caption, veto-replay caption intact),
510 pages. **Production is LIVE on the adaptive basket as of `65bfd335`.**

**Files**: PHASE_STATUS_INFLIGHT.md (this).

---

## docs(agents) — 25-agent model+effort audit: fix stale model references (in flight, 2026-06-11)

**Branch**: `claude/friendly-rubin-liav05` · **Scope**: docs / agent-defs only —
no code / workflow / schema surface.

Full 25-agent `model:`/`effort:` frontmatter audit vs `.claude/agents/README.md`
§Model split + authoring convention #3: **all 25 assignments confirmed
appropriate** (5 fable+max judgment gates · 18 sonnet+max · 2 sonnet+high
deterministic script-runner carve-outs). No frontmatter changes. Two stale-doc
fixes shipped:

1. `release-captain.md` description said "Opus model" — predates the fable
   migration; frontmatter was already `model: fable`. → "Fable model".
2. CLAUDE.md cue-table row "`quantrank-reviewer` with `model: fable` override ·
   user authorization required" — stale since the reviewer became fable by
   default; there is no override left to authorize. → reworded, clause dropped.

Side observation (no change): `vercel-preview-auditor`'s UUID-pinned MCP tool
names are the documented install-specific limitation (docs/GOTCHAS.md
§"Sub-agent `tools:` frontmatter") with the gap-surfacing mitigation already in
place.

**Files**: .claude/agents/release-captain.md · CLAUDE.md (§Auto-routing cue
table row) · PHASE_STATUS_INFLIGHT.md (this).

---

## docs(infra) — token-economy optimization: CLAUDE.md re-drain + description tightening + reviewer gate-narrowing (in flight, 2026-06-11)

**Branch**: `claude/friendly-rubin-liav05` (same PR #459 as the model-ref fixes —
the session is branch-locked, so the confirmed optimization batch lands on the
same PR). **Scope**: docs + `.claude/**` only — no code / workflow / schema
surface.

User-confirmed batch (5 items) after the measured-baseline report (~28K tok of
always-loaded context per session):

1. **CLAUDE.md re-drain 14.0K → ~7.8K tok (−44%)** — §Stack LedgerCraft PR
   narrative → pointer to docs/design.md; §Layout fat cells compressed;
   §Conventions rebase-history compressed; §Auto-routing Delegation-patterns +
   Cue tables (70% overlap) MERGED into one routing table; §Gotchas paragraph
   entries → true one-liners (detail verified present in docs/GOTCHAS.md;
   missing `pillarColor`/`flagLabel` entry APPENDED there first); §Phase status
   currency-fixed (0.10.18 on main; #453/#456 in-flight entries rotated out —
   both merged; done Next-deliverables items 1-2 dropped, renumbered) with the
   drained prose archived VERBATIM in docs/PHASE_STATUS_ARCHIVE.md; §Agent
   skills compressed. CLAUDE.md loads into every session AND every sub-agent
   spawn, so the saving multiplies (~6.2K × (1 + spawns)).
2. **Agent `description:` tightening, all 25 defs (23.1K → 13.3K chars ≈
   −2.5K tok/session)** — every original description preserved VERBATIM in the
   agent body under "## Boundary & trigger reference" (paid only at spawn);
   new descriptions keep ALL trigger cues incl. Thai phrases.
   `quantrank-reviewer`'s preserved long-form got a SUPERSEDED banner on the
   every-push clause.
3. **First-party skill descriptions, 18 files (~17.6K → ~7.7K chars ≈ −2.5K
   tok/session)** — same preserve-in-body pattern ("## Long-form description").
   Vendored skills (mattpocock-* / 9arm-* / impeccable / portable-karpathy /
   good-code) untouched per vendor-sync discipline. **3 dead skills REMOVED**:
   `karpathy-llm-wiki` (vendored gist, never fires for finance scope —
   THIRD_PARTY_NOTICES entry retained with REMOVED banner; vendor-sync source
   row marked skip), `doc-coauthoring` + `mcp-builder` (Anthropic snapshot,
   unused; phase-11 PLAN.md pointer annotated to re-vendor when Phase 11
   starts). skills README index updated.
4. **`quantrank-reviewer` (fable) narrowed to gate-fire only** — Draft→Ready /
   "ready to push" / "open PR" / explicit "full review"; NO LONGER fires on
   every `git push` or non-trivial edit set (the documented cue contradicted
   the stated "fable agents wait for gate" split and cost 5+ fable reviews per
   polish-heavy PR). Sonnet on-edit agents are unchanged and cover the interim.
   CLAUDE.md routing table + agent description both updated.
5. **Connector policy** — Supabase / Sentry / Gmail / Google Drive marked
   ⏸ toggle-OFF in CLAUDE.md §Connectors + AGENTS.md (token economy; re-enable
   per phase). NOTE: the actual toggle is a USER action in Claude app Settings
   → Connectors — repo files cannot flip it.

Deferred (flagged, not executed — outside the confirmed list): deleting the
remaining ~15 unused vendored-Anthropic-snapshot skills (docx · pptx · pdf ·
canvas-design (~5MB fonts) · slack-gif-creator · algorithmic-art ·
brand-guidelines · internal-comms · theme-factory · web-artifacts-builder …) —
next candidate batch if further savings wanted.

**Measured result**: always-loaded per-session context ~28K → ~17K tok
(CLAUDE.md 14.0→7.8K · agent descs 5.8→3.3K · skill descs 8.5→~6K) and each
sub-agent spawn carries ~6.2K tok less CLAUDE.md.

**Files**: CLAUDE.md · AGENTS.md · docs/GOTCHAS.md (+pillarColor entry) ·
docs/PHASE_STATUS_ARCHIVE.md (drain archive) · .claude/agents/*.md (25) ·
.claude/skills/<18 first-party>/SKILL.md · .claude/skills/README.md ·
.claude/skills/vendor-sync/SKILL.md · .claude/skills/phase-11/public-api-docs/PLAN.md ·
THIRD_PARTY_NOTICES.md · 3 skill dirs removed · PHASE_STATUS_INFLIGHT.md (this).

---

### Addendum (same PR, 2026-06-11): agentic-workflow audit round

User-requested audit of the agentic + dynamic workflow (correct / complete /
non-redundant / token-fit). `docs-reviewer` walked WORKFLOW.md + agents/README
+ TEAMS.md vs the new routing table. Verdict: mechanics SOUND (HANDOFF routing
live-verified; all multi-agent events complementary, not duplicative; cadence
maps the 25-roster with no orphan phase). Fixes shipped: WORKFLOW Step-6
roster (drop `vercel-preview-auditor` — deploy-gate agent, guaranteed-GO waste
post-cron; add missing `expert-user-explorer`); README gate-only trigger ×2;
TEAMS.md "22"→25 ×4 + AGENTS.md ×2; **defense-layer-auditor false-FAIL bug**
(hardcoded `0.9.4-phase4h.4` → read CLAUDE.md at run time) + A-J→A-L ×5 (K/L
findings were silently dropped from reports); **quantrank-reviewer false-FAIL
bug** (`EDGAR_MAX_WORKERS=5` pin → canonical 8); `delegate-first.sh` hook
injection slimmed ~195→~80 tok/turn. Deferred recommendation: drain
PHASE_STATUS.md §Current state (8.6K-tok forced read every session-start) to
~2K — separate PR (collision-prone file).

---

### Addendum (same PR, 2026-06-11): PHASE_STATUS.md §Current state drain

User-confirmed follow-through of the workflow-audit recommendation: §Current
state (the forced-read session-start section) drained 244 lines / ~8.6K tok →
92 lines / ~2.1K tok. All merged-PR lists + closed next-deliverables entries +
stale table prose MOVED VERBATIM (python slice, not retyped) into
§Chronological history §"Relocated from §Current state". Currency fixes folded
in: schema row → 0.10.18 (#456 + #458 manifest, verification pending on the
2026-06-11 artifact), skill inventory 47→45, subagent inventory 22→25,
production-run pointer → `65bfd335`, in-flight → PR #459 single entry,
next-deliverables renumbered (DONE items relocated; 7a/7b spec retained as
item 5 — CLAUDE.md pointer updated item 7→5).

---

## feat(portfolio) — V55 hysteresis hold-band (entry 65 / hold 55) (2026-06-11)

**Branch**: `claude/confident-thompson-y58bhe` · **Status**: in flight

Iteration-2 outcome. Exact rule: an incumbent stays while composite
>= 55 AND it is still present in the rebalance's top-MAX_PICKS HC
`holdings` (a >= 55 incumbent can still exit by rank/eligibility).
Pre-registered experiment (grid {60,55} declared
before running; criteria: turnover −30% / CAGR ≥ −0.5pp / beats ≥ −2q):
**V55 passes all three** — annualized Σ|Δw| 3.508 → 2.324 (−33.8%), net
CAGR 22.7% → 22.4% (−0.27pp), beats vs SPY 26/40 → 29/40, maxDD −32.0% →
−31.4%. Per-half (neutral record): beats improved in both halves
(15/20→17/20 · 11/20→12/20); growth +H1 (x2.89→x3.35) / −H2
(x2.57→x2.17). V60 FAIL recorded (−27.7% turnover, −0.8pp).
`methodology-scientist` **RATIFY-WITH-CONDITIONS** — hysteresis is a
canonical implementation-cost device (Constantinides 1986 JPE no-trade
region · Davis-Norman 1990 · Garleanu-Pedersen 2013 JF ·
Novy-Marx-Velikov 2016 RFS buy/hold spread · Russell banding precedent);
C0 strict tenure (entered-via-65 only; floor-pads no tenure; re-entry
needs 65) disambiguated by an identical-result strict re-run; C1
provenance comment on `ADAPTIVE_HOLD_BAND_MIN = 55.0`; C2 test pins; C3
artifact contract — the band BREAKS the holdings-prefix property, so the
artifact gains `rebalances[*].band_book` + `band_weights` +
`band_held_count` + `band_carry_count` + `band_carry_weight_share`,
`nav.adaptive` regenerates from band legs, `meta.adaptive_rule` gains
`hold_band_min`. H-gates H1/H2/H3/H-B/H-C registered on issue #130
(incl. freeze lock on 55). **Claim discipline**: the band is a TURNOVER
device only — beat/maxDD deltas are within-noise, never marketed.
Frontend: 3-state graceful degradation (band artifact → adaptive-prefix
artifact → legacy slider) so the deploy is safe across regeneration;
carried names get an sr-only "(held)" suffix + the canonical muted token
(AA both modes); the timeline renders the exact `band_book` membership
(never a prefix slice). As-landed extras: the C2 e2e pin caught an
int-vs-float `band_carry_weight_share` contract bug (float() guard
landed); `band_carry_names` exported per rebalance (exact H2 cohort);
`RULE_VERSION` gains `+hold-band-55` per the `+veto-replay` precedent.

Companion analyses recorded on issue #461: 2025 attribution (value-trap
capture DECK/BLDR/LULU/DVA + structural MoS-gate growth exclusion —
top-10-composite capture 1/10 mid-2025 + score compression to the floor;
composite 10y cross-sectional IC ≈ +0.025, nil) and the TTM-vs-annual
lag hypothesis KILLED (2TP/1FP/2FN on 5 PIT-clean cases; a TTM filter
would have ejected 2025's biggest winner STLD; live pipeline already
TTM-aware — backtest-proxy property only).

**Files**: scripts/backfill_portfolio_pit.py ·
frontend/lib/data.ts · frontend/lib/types.ts (non-schema) ·
frontend/components/AiPickPortfolio.tsx ·
frontend/components/HoldingsTimeline.tsx ·
tests/test_portfolio/ (C2 pins) · CLAUDE.md (§In-flight rotation) ·
PHASE_STATUS_INFLIGHT.md (this).

---

## docs(portfolio) — band-artifact verification record (2026-06-11)

**Branch**: `claude/confident-thompson-y58bhe` · **Status**: in flight

First post-#462 band artifact (backfill dispatch, 10:18 UTC). **Engine
matches the ratified experiment to the decimal**: band-adaptive net CAGR
22.4% (experiment 22.4) · annualized Σ|Δw| 2.324 (experiment 2.324
EXACT) · book 5-15 mean 10.7 · `rule_version` carries both markers.
Contract complete (band_book/weights/held_count/carry_count/carry_names/
carry_weight_share); reconcile invariants hold artifact-wide; first
rebalance band-inert. **First H-gate input read**: carries at 38/40
rebalances (mean 2.85 names); carry weight-share mean 0.273, max 0.624
(single quarter — H2's >50%×2-consecutive does NOT fire on history).
The live book demonstrates the feature: 2026-05-15 holds 6 names — the
floor 5 + **SYF carried via the band** (score in 55-65). Local static
export against this artifact renders STATE-1: band caption, sr-only
"(held)" on SYF, no slider, veto caption intact.

**Files**: frontend/public/data/portfolio/backtest_pit.json (workflow
commit `4bfcdb32`) · PHASE_STATUS_INFLIGHT.md (this).

---

## feat(portfolio) — adaptive-book cap removal (max_picks 20 → unbounded) (2026-06-11)

**Branch**: `claude/confident-thompson-y58bhe` · **Status**: in flight

User decision after evidence review (the AskUserQuestion offered uncap-both
/ uncap-ceiling-only / keep — user chose ceiling-only; floor 5 retained as
the evidence-backed left-tail guard: floor-0/1 measured at CAGR −1.2pp +
maxDD ~3pp worse). `methodology-scientist` Mode B re-ratification:
**RATIFY-WITH-CONDITIONS U1-U6** — the cap had NO academic anchor (a
display-ladder constant reuse), was never in the swept grid, and bound
0/40 in-sample (max raw 13 / max band book 15); removal violates neither
freeze lock (no new hypothesis tested against the data). No replacement
ceiling — a silent clamp would mask exactly the anomaly a human should
inspect; guards move to the gate layer: **A2 re-pointed to the full
deduped HC-eligible pool** (the old top-20-slice statistic was censored
and would blind the gate in its own patrol regime) + **NEW A2-S spike
tripwire** (full-pool raw ≥ 25 in any single rebalance → immediate
reopen, scoring-regression hypothesis first) — both registered on issue
#130 BEFORE any uncapped data exists.

Conditions landed: U2 `select_picks(count=None)` (clamp skipped, same
ordering + dual-class canonical-class dedup; `picks =
full_order[:MAX_PICKS]` keeps holdings / by_count / weights_by_count
byte-identical) · U3 σ loop covers every band-book member (a rank-21+
name can never silently zero-weight) · U4 `adaptive_count_raw` counts the
full pool uncensored; legacy clamped `adaptive_count` documented as
analytics-only; `band_held_count` authoritative · U5
`meta.adaptive_rule.max_picks: null` (key kept, explicit-null
disclosure convention; `meta.max_holdings` stays 20) + C1 provenance
update + `RULE_VERSION` += `+uncapped` + the 3 contract pins updated
(uncap book pin replaces the cap pin) + UI captions three-way data-driven
("min 5, no cap" when null) · U6 gate registration (#130).

**Merge gate U1 — FIRED (non-empty)**: the regen diff (`3dbe4798` vs
`4bfcdb32`) showed 12/40 rebalances with different band books (72 field
diffs; first instance BF-B 2016-11-14; zero same-key weight drift — pure
selection law). The cap was inert as a COUNT clamp (fresh leg, max raw
13) but BOUND as a rank-slice membership test on the CARRY leg. Mode B
re-entry verdict: **RATIFY-AMENDED-WITH-CONDITIONS (U7-U13)** — the
uncapped domain is adopted as a **post-results protocol amendment V55.0 →
V55.1** (not a defect-erasure): the V55.0 registered text was internally
ambiguous (slice vs eligibility reading) and the slice exit keyed
retention to an undesigned display constant + third-party score crowding,
which none of the band's anchors (Constantinides/Davis-Norman/
Garleanu-Pedersen) support. U11 re-verification vs the same no-band
counterfactual: turnover **−35.8%** / CAGR **+0.33pp** / beats **+4** —
all three V55 criteria pass under BOTH protocols (both rows retained in
the C1 block). U10 reads: H2 zero consecutive >0.50 carry-share pairs
under both domains; H3's trailing-4 wire (>14) is exceeded IN-SAMPLE
under BOTH domains (capped max 14.25 / uncapped 14.75, the 2017-18
high-count regime) — pre-existing finding, recorded not recalibrated
(H-C lock), Q3 2026-08-19 cohort-audit agenda. Capped-vs-uncapped
scoreboard claim-quarantined (U8): CAGR 22.4 → 23.0, turnover 2.324 →
2.251, beats 30/40 both, maxDD −31.4% both. +1 multiplicity charged
(U9). U12 rank-free carry pins landed (rank-25 carry retained; vetoed
inverse). Reopen criteria U13: any live H-gate breach attributable to
the diff-cohort carries reopens the domain question; Q3 audit reviews
the first live uncapped carry-cohort health as a standing item.
USER COUNTERSIGNED the V55.0 → V55.1 amendment framing 2026-06-11
(post-U10/U11 reads); H-gate baselines re-base on `3dbe4798`; `4bfcdb32`
archived as the U1 counterfactual record.

**Files**: compute/portfolio/weights.py · scripts/backfill_portfolio_pit.py ·
tests/test_portfolio/ (pins + uncap coverage) · frontend/lib/types.ts ·
frontend/components/AiPickPortfolio.tsx · CLAUDE.md (§In-flight rotation) ·
PHASE_STATUS_INFLIGHT.md (this).

---

## fix(backtest) — rolling-window anchors pinned + pre-2016 scout record (2026-06-11)

**Branch**: `claude/confident-thompson-y58bhe` · **Status**: in flight

User question "ไตรมาสแรกมีข้อมูลพอไหม / ควรดึงย้อนหลังเพิ่มไหม" surfaced
two silent run-date-relative time bombs:
1. `--start` default = today−10y (ROLLING) — the cron passes no --start,
   so the artifact window slid daily and would have silently dropped the
   canonical 2016-08 first rebalance around Aug 2026. Fixed:
   `BACKTEST_CANONICAL_START = date(2016, 6, 1)` (ledger-Track-B-anchored,
   never run-date-relative; changing it gates on a ledger-coverage check +
   methodology sign-off).
2. `fetch_prices(period="10y")` reached back 10y from the RUN date with a
   PERIOD-BLIND parquet cache — the first rebalance's trailing-90d sigma
   was computed on ~45 trading days (silent; the function accepts >= 3
   points), degrading toward zero as the window slid. Fixed: `min_start`
   param on fetch_prices (None = byte-identical legacy; a fresh-but-shallow
   cache triggers an at-most-once deeper refetch with period="max" that
   overwrites the cache; new listings whose full history starts after the
   floor are cached as-is — no retry loop). The backfill passes
   `min_start = start − 185d` (90 trading ≈ 130 calendar + margin) for the
   universe + benchmarks; compute/main.py never passes it (live unchanged).

Fundamentals depth was verified NOT to be a problem: the pillars already
consume every 10-K filed <= T (XBRL back to ~2009-2011), independent of
the backtest start — "pull more history" is already maximal on that axis.

Companion scout (data-pipeline-engineer) on extending the window pre-2016
recorded on issue #465: ledger extendable (fja05680 to ~1996) and XBRL
coverage ~90% at 2013-Q1 / 100% by 2013-Q3 — but **yfinance has ZERO
price data for pre-~2021 delisted tickers** (SWY/FDO/DTV/JDSU verified
empty), so a 2013-2015 extension would silently drop ~58 names/rebalance
(~12% of the cross-section) = the exact survivorship bias the ledger
prevents. **2016 is the honest floor on the free stack**; 2013-Q3 (+12
rebalances) requires a licensed delisted-price source — owner decision,
parked on #465. Side finding: fundamentals_latency_p95 28.12s > 15s on
the latest run — watch next cron.

**Design A (round-2, the cron-cost fix)**: the reviewer traced that the
min_start backstop alone would have cost EVERY warm cron a sequential
~500-ticker `period="max"` refetch (+5-15 min vs the 55m folded cap,
silent stall risk) because the quarter-keyed fast cache only saves on the
first run of a quarter and the compute step re-downloads SHALLOW 10y
frames daily. data-pipeline-engineer design verdict (4 options ranked):
**shared fixed floor** — `config.PRICES_FETCH_START = date(2015, 11, 29)`
(= BACKTEST_CANONICAL_START − 185d, equality asserted by test pin A5);
`_yf_download` gains `start=` and `fetch_prices` always downloads from
the floor (period vestigial on the live path); cache family bumped
v7-fast → v8-fast in BOTH workflows (backfill key aligned to the same
family). Per-run extra cost: ZERO (the compute step's existing daily
re-download is simply ~6 months deeper, +5.4% rows); the min_start
backstop stays and is a verified no-op on warm cache. FREE side-fix: the
benchmarks.json late-rebase cliff (QQQ/DIA/IWM lines were rolling-10y and
would silently rebase after the portfolio start ~Aug 2026) is eliminated
— benchmarks now start at the floor, before the first NAV date. Growth
policy: revisit if the window exceeds ~15y (≈2031). Live consumers
re-verified deeper-frame-safe (everything tail/iloc-capped).

Tests: 22 mock-signature repairs (`fetch_prices` now receives kwargs) + 12
new pins — min_start contract (shallow-refetch-once / deep-no-download /
new-listing-no-loop / None-bypass) + anchor pins (canonical-start value &
type / A2 exercising main()'s REAL parser / buffer 185 / A4 full-window
magnitude ≥130d) + Design-A pins (A5 cross-layer floor equality · A6
fetch_prices downloads from the fixed floor · A7 period-branch regression
· v8-fast key pin covering BOTH workflows). Full suite 1650 passed (osap modules excluded — sandbox env gap,
CI installs .[factors]).

**Files**: compute/ingest/prices.py · scripts/backfill_portfolio_pit.py ·
tests/test_portfolio/test_backfill_integration.py ·
tests/test_ingest/test_prices_min_start.py (new) · CLAUDE.md (§In-flight
rotation) · PHASE_STATUS_INFLIGHT.md (this).

---

## feat(scripts) — Phase-8 universe-expansion scout (S&P 400 + ADR, free-stack) (2026-06-12)

Owner direction (2026-06-12, after #465 closed not-planned): widen the
universe as far as the FREE stack honestly allows — no licensed data. The
roadmap ceiling stands: staged 500 → S&P 900 pilot → S&P 1500 (#249
pre-cache prerequisite; explicit stop before Russell-2000 territory).
This PR lands the measure-first scout tool
(`scripts/scout_universe_expansion.py`, dev-only, no production wiring;
raw outputs gitignored under `scout_out/`), four modes:

- `sp400-stage1` — scores the S&P 400 through the PRODUCTION ingest +
  scoring path inside a combined ~900-name cross-section (falls back to
  midcap-only cohort with a loud caveat when the 500's caches are cold);
  JSONL append/resume.
- `adr-probe` — measures EDGAR form mix + US-GAAP tag resolution per
  foreign issuer through the production extractor.
- `sp400-stage2` — per-ticker defense flags on the ≥60-composite band
  (sloan_accruals / net_issuance percentile vetoes excluded — they need
  full-universe artifacts; stage-2 verdicts are optimistic by those two).
- `report` — synthesis + book-impact vs the uncapped adaptive rule
  (composite ≥ 65 + HC-clean enters; floor 5, no cap).

First probe result (26 large US-listed foreign issuers): **25/26
ANNUAL_ONLY** (20-F/6-K filers, no quarterlies → no TTM; most resolve
only 2-3 US-GAAP tags, BP = 0), **1/26 SCOREABLE_FULL (MELI — a
10-K/10-Q domestic-style filer)** → ADRs are effectively un-scoreable
on the free stack; any ADR surface would need the Phase-8 20-F/6-K IFRS
ingest build and still lack TTM comparability.

**Rider — rebalance-frequency experiment (owner ask mid-scout)**:
`scripts/experiment_rebalance_frequency.py` (dev-only) replays the
shipped `backtest_pit.json` books on filtered anchor sets (quarterly
40 / semiannual 20 / annual 10; identical first rebalance) with a
baseline-faithfulness gate (quarterly reconstruction matched the
artifact: 0.000% NAV error, 0.0071pp CAGR) + per-side cost model
0/10/20bps on traded notional. Verdict per the pre-registered rule
(switch only if the variant wins BOTH gross AND net CAGR with no worse
maxDD): **KEEP QUARTERLY** — annual loses gross 23.01% vs 23.30%, loses
net@10bps, maxDD worse (32.2% vs 31.3%) despite turnover −54%
(2.34 → 1.08); semiannual loses everything (21.94% gross — small-N
anchor-timing noise explains the non-monotonicity). Caveat recorded in
the output meta: variant books are quarterly-derived holds (band logic
NOT re-run at the new frequency); veto-latency between rebalances IS
faithfully modeled. Production unchanged.

**Files**: scripts/scout_universe_expansion.py (new) ·
scripts/experiment_rebalance_frequency.py (new) · .gitignore
(scout_out/) · PHASE_STATUS_INFLIGHT.md (this).
---

## 2026-06-12 — Scout results addendum (same PR): S&P 400 verdict — midcaps WOULD reshape the book

Stage-1 full run (400/400 scored, combined 900-name cross-section
confirmed in-record): **24 midcaps ≥ 65** (entry bar) + 31 in the 60-65
band; cohort mean 50.6. Two scout defects found + fixed before trusting
numbers (commit `025eaa83`): (1) summary cross-section note read
`records[0]` — stale midcap-only smoke rows; scoring itself was
combined for 392/400, `--force-rescore` wiped the 8 stale rows;
(2) `fetch_fundamentals_history` called with empty CIK — history failed
for ALL 400 (growth pillar imputed); root cause `Company("")` resolves
to a RANDOM company under an identity (dangerous bug class — failed
neutral here); fixed via snapshot-CIK harvest → `Company(ticker).cik`
fallback, both stages. Post-fix composites shifted +0.7..+1.5 and the
top-8-alphabet stale names (AAL et al.) fell out of the ≥65 set.

Stage-2 defense pass on all 55 (≥60): **all 24 book candidates clean on
every evaluable flag** (`filing_lag_days` is numeric-informational; 38d
typical). NOT evaluated: `sloan_accruals_top_decile` +
`net_issuance_top_decile` (full-universe percentiles) — sloan is 97% of
historical veto bite, expect ~2-3 of 24 trimmed in a real 900 run.

Book impact (today-snapshot, NOT a backtest — pre-2016-style history
for midcaps stays impossible free, #465): current S&P 500 has 23 names
≥ 65 → a 900 universe roughly **doubles the eligible pool**; EXEL 76.8
/ MLI 72.8 / SSD 72.7 would outrank today's #1 (HST 71.8); the live
book (6 names, drought regime) would thicken. Caveat: the 500's own
percentiles would shift slightly under a true 900 re-rank (held fixed
from rankings.json here). → Proceeds to the staged ladder: #249
pre-cache → S&P 900 pilot (forward-only picks + disclosure) → 1500.
ADRs stay out (25/26 ANNUAL_ONLY).
---

## 2026-06-12 — Stage-2 CORRECTION (fable-gate catch, same PR): Beneish/Dechow were silently un-evaluated; corrected verdict 23/24 clean, SSD vetoed

Gate review found nonexistent attribute reads in scout stage-2
(`.beneish_manipulation` / `.dechow_high`; real API: `.is_high` +
`.m_score` / `.f_score`) swallowed by a bare except — all 55 stage-2
records carried `*_compute_failed`, so the prior addendum's "all 24 clean
on every evaluable flag" OVERSTATED the evaluated set (the two
manipulation models behind 2 of the 7 active vetoes never ran). Fixed
mirroring production semantics (Beneish veto m > −1.78, annotate
−2.22..−1.78; Dechow is_high > 2.45, veto > 3.0), excepts narrowed to
record the exception class in flag_notes, stage-2 re-run on all 55:
**23/24 clean; SSD (72.7) VETOED — Beneish m = −1.17; SON (67.4)
m = −2.04 + GEF (66.8) m = −1.98 annotate-only; zero Dechow fires.**
N/A scores = missing annual-history ratios (model returns None — honest
insufficiency, not a crash). sloan + net-issuance remain unevaluable
pre-pilot. Rider WARN fixes: report-mode records[0] → dominant-note
helper + `cross_section_note_counts` histogram; experiment vacuous gate
condition fixed + missing-NAV loud-fail; cost docstring ×2 corrected;
comment honesty (empty-CIK cache bypass, local import); 500-side
history=None cross-section deviation disclosed. Gotcha pre-registered:
CLAUDE.md §Gotchas + docs/GOTCHAS.md "edgartools Company(\"\")".
---

## 2026-06-12 — ci(precache): Issue #249 Options B+C — Saturday EDGAR pre-cache workflow + cache-restore canary

Durable fix for the 2026-05-25 P1 (full-cold 5-loop run blew the cron's
`timeout-minutes`; warm ~12-25 min, cold > 2.5 h). (B) NEW
`precache-edgar.yml`: Sat 08:00 UTC + `workflow_dispatch`, no trading-day
gate, runs the REAL `compute.main` with ALL loops enabled (no skip vars)
and discards outputs; restores BOTH bundles with the cron's EXACT keys —
fast `cache-v8-fast-<quarter>` exact-hit-skips-save (warm Saturdays
~free; post-eviction Saturdays eat the cold rebuild and SAVE so Monday's
cron restores warm), slow-text run-id key always saves a fresh snapshot;
`timeout-minutes: 240`, `permissions: contents: read`; end-of-job
per-loop wall-clock + fundamentals p50/p95 step summary with a
stale-committed-metadata guard (`git diff --quiet` on metadata.json so an
aborted compute can't report the prior cron's numbers). (C) Post-restore
canary upgraded in `compute-rankings.yml` + mirrored in precache:
per-layer size / file count / newest-file age into log +
`$GITHUB_STEP_SUMMARY` table; empty/absent Form-4 or 10-K-text layer →
`::warning::cache cold — expect a long run (see #249)` — warning NOT
fail-fast (deliberate deviation from the issue's C: with B in place a
cold dispatch is usually an intentional rebuild; rationale in YAML
comment). NEW shared concurrency group `edgar-cache-writers`
(`cancel-in-progress: false`) on BOTH workflows so the two cache writers
never overlap (additive on the cron — schedules can't collide by
construction; the group covers the dispatch paths). Guard test now
quad-file: cache-path parametrization × both warming workflows
(+ `edgar_form4` / `osap` added to the required list — pre-existing guard
rot), `cache-v8-fast-` present / `cache-v7-` absent pinned in precache,
NEW version-agnostic slow-text family lockstep test + run-id-key idiom
pin. Sandbox-verified: YAML parse, canary execution on warm / cold /
empty-form4 / stale-metadata paths, 24/24 guard tests, ruff clean.
Doc fixes riding along: AGENTS.md cache-section stale `cache-v5-fast-`
→ v8 + precache second-writer note; CLAUDE.md §Stack CI line + §In
flight rotation. Follow-up (out of scope): `universe=sp900` dispatch
input for Phase-8 S&P-400 warming — separate PR on the pilot's timeline.
This workflow is also the **Phase 8 prerequisite** (#249 listed as the
hard gate before the S&P 900 pilot).
---

## 2026-06-13 — feat(backtest): backtest-honesty hardening — prove the AI-pick +789% is real, fair, and not overfit

Triggered by "prove the home-page +789.1% is real / fair / no cheat /
no calc error". A multi-agent audit (data-scientist + data-pipeline-
engineer + methodology-scientist) verified the number is arithmetically
exact, total-return-fair vs SPY, and PIT-clean — and surfaced the real
residual risks, each now closed:

1. **Overfitting (the #1 risk).** The adaptive thresholds (composite_min
   65 / hold_band 55 / floor 5 / uncapped) were grid-swept IN-SAMPLE on
   the same 40-leg window shown as the track record. New
   `compute/validation/basket_rule_validation.py` runs the ratified OOS
   protocol on the produced NAV: **Deflated Sharpe** (Bailey-López de
   Prado 2014, `n_trials=15` = the 12-config grid + uncap + 2 hold-band
   sweeps) is the primary gate — it CLEARS (DSR≈3.98, Φ(DSR)≈0.9999
   quarterly / 0.969 daily ≥ 0.95), so the adaptive number stays as the
   hero with a credibility badge. Confirmatory layers: a **score-once
   12-config grid** ({55,60,65,70}×{1,3,5}, emitted from ONE scoring
   pass — the `by_count` ladder generalized to 2-D, <2 min added) feeds
   **PBO** (CSCV, n_partitions=16, config-correlation caveated) and a
   **purged-embargo holdout** (train[0,30)/purge{30}/test[31,40), the
   ONE `in_sample=false` block, falsification-only). All land in
   `meta.validation` via Rule-18 try/except (null on failure). DSR +
   walk-forward stay `in_sample=true`; never relabel.
2. **Survivorship (scoring universe).** Membership was PIT-correct but
   the pre-fetch only loaded today's 502 names, so ~213 ledger-REMOVE
   tickers were silently dropped at scoring. `run_backfill` now
   pre-fetches the `current ∪ ledger-REMOVE-since-start` union with
   real-CIK resolution (guards the `Company("")` gotcha) + graceful
   degradation + Rule-18 counters.
3. **`sector_from_today` PIT gap.** NEW `scripts/backfill_historical_
   sector.py` → `data/historical_sector.parquet` (19,661 rows, 39
   dates, 726 tickers) from Wikipedia revision history (CC BY-SA /
   Feist; sector NAMES only). Captures the 2018 Communication-Services
   reclassification (GOOGL/NFLX IT→Comm-Svcs). `sector_at()` PIT lookup
   wired into the backfill; `meta.sector_from_today` now dynamic.
4. **8-K Item 4.02 veto not replayed.** NEW `scripts/backfill_item402_
   history.py` (SEC EFTS) → `data/pit_item402_history.parquet` (17
   real S&P-500 non-reliance events 2016-2026). `item402_filings_for()`
   PIT slice feeds `check_non_reliance`; the 7th veto now replays when
   the parquet is present; `meta.vetoes_replayed/not_replayed` dynamic.
   (Fixed an EFTS-parser silent-drop along the way: the `_source` keys
   are `ciks`/`adsh`/`items`, NOT `entity_id`/`file_num`; retry on 5xx.)
5. **Minor refinements (disclosure-only).** Restatement-canary
   period-map gate (tightens the over-counted `restatement_contamination_
   pct`); ticker-rename micro-leakage assessed → documented (impact ~0:
   merger-renamed names have no pre-merger 10-K → null-fundamentals PIT
   → never clear the gate) + meta note, follow-up issue to file.
6. **Frontend.** `BacktestValidationBadge` (data-driven, graceful-
   absent) surfaces the DSR / PBO / holdout verdict + the +127.7pp
   (~16%) selection-footprint caveat on the AI-pick home card.

Both parquets are committed (whitelisted past the global `*.parquet`
gitignore, tracked alongside `data/sp500_membership_historical.csv`).
GRACEFUL DEGRADATION is the load-bearing invariant: with both parquets
absent the backtest output is byte-identical, so the new code is inert
until the data is present + the rerun runs. Full offline suite 1773
passed; ruff + tsc + next build + schema_check clean.

**Gate to merge:** a `backfill-portfolio.yml` `workflow_dispatch` on this
branch (warm cache; survivorship cold-fetches ~213 removed tickers) to
MANIFEST `meta.validation` + the survivorship/sector/8-K deltas + the
real PBO/holdout numbers into `backtest_pit.json`, then post-rerun
verify (`defense-layer-auditor` Section A-L + `expert-user-explorer`
Playwright on the now-visible badge) + a fable `quantrank-reviewer`
pass. The displayed +789% WILL move (survivorship + PIT sector + 8-K
veto change the historical books) — that movement is the proof the
closures are live, not a regression.
## 2026-06-13 — fix(scoring+ci): Issue #469 — de-sync the 8-K cache cohort + canary TTL-proximity warning

Root-caused from the 2026-06-12 manual cron dispatch (forensics, run
27413437138): `tier2_wall_clock_seconds = 4826` (~80 min) vs the ~11s
warm baseline. The 502-ticker 8-K cache, written in ONE cold-rebuild
burst (~June 6), crosses its flat 144h (6-day) TTL *simultaneously* — so
one tier2 pass straddling the cliff refetches all 502 tickers live,
recomputing byte-identical `gc=5/nr=1/ac=9` flags. Recurs every ~6 days
(next ~June 18). No infra fault — the #468 canary actually reported the
143h cache age that closed the case.

**Part 1 (compute)** — `compute/scoring/eight_k_events.py` `_cache_read`
effective TTL = `EDGAR_8K_CACHE_TTL_SECONDS + _ttl_jitter_seconds(ticker)`;
new pure helper `_ttl_jitter_seconds(ticker) -> int` returns a
SHA-256-stable offset in `[0, EDGAR_8K_CACHE_TTL_JITTER_SECONDS)` (new
config constant = 24h). MUST be SHA-256, not builtin `hash()`
(PYTHONHASHSEED-salted → would re-randomize per process and defeat the
de-sync). Only the TTL comparison line changes; event-detection,
730-day lookback, warm-hit no-restamp, and cache write are untouched —
zero scoring-output change. 6 unit tests (determinism, [0,24h) bounds,
≥10-distinct-bucket non-degenerate spread, effective-TTL widening both
sides of the cliff, zero-window guard); pre-existing `test_B3` margin
widened from `+100s` to `+JITTER_WINDOW+100s` (ticker-agnostic).

**Part 2 (observability, both workflows byte-identical)** — the
post-restore canary in `compute-rankings.yml` + `precache-edgar.yml` now
(a) echoes the restored slow-text key via a new `id: restore-slow-text`
on the slow-text restore step (identical in both files →
`steps.restore-slow-text.outputs.cache-matched-key`), and (b) emits
`::warning::edgar_8k cache within 24h of its 144h TTL ... (~80 min); see
#469` when the `edgar_8k` newest-file age > 120h (pure shell, warning
only, can't fail the job). 2 new guard tests
(`test_canary_emits_edgar_8k_ttl_warning` +
`test_canary_echoes_restored_slow_text_key`); the existing canary
byte-equality test stays green (28→ tests pass).

**Verify**: ruff whole-repo PASS · scoring + workflow suites 654 passed ·
schema triple untouched. **Honest caveat**: de-sync is only fully
observable over ~2 cold-rebuild cycles (~1 week of crons) — single-cron
confirmation can't prove it; watch `tier2_wall_clock_seconds` for the
spike's disappearance across consecutive weeks.
## 2026-06-13 — fix(ingest): filing-date precheck to skip wasteful companyfacts refetch (#471, closes parent #15)

**Branch**: `claude/sweet-turing-d46aw2`
**Type**: fix(ingest) + perf — COMPUTE-ONLY; no schema change, no frontend change,
no workflow change; no schema bump.

**Problem**: stale-but-cached tickers (latest SEC filing >45d old — e.g. big filers
in the quiet period between 10-Qs) triggered a full `Company.get_facts()` companyfacts
pull on EVERY cron run even when the data was unchanged. Observed on the 2026-06-12
cron: `fundamentals_latency_p95 = 19.27s`, 84/502 tickers >= 15s, p50 = 0.0s — a
bimodal histogram dominated by this wasteful refetch loop.

**Fix — Design B (filing-date precheck)**: a new `_latest_filing_date(cik)` helper
(reuses `Company.get_filings("10-K"/"10-Q")`, cheap) is called BEFORE the heavy
`_build_snapshot`. If SEC shows no new filing since the cached snapshot date, the
cache is served directly and `get_facts()` is skipped. Falls through to the live build
on ANY uncertainty (helper returns `None`, or a newer filing exists), so a genuine new
filing is always captured and the precheck can never produce stale output.

**Why Design B over Design C (parquet-mtime gate)**: the cron's FAST cache uses an
exact quarter key (`cache-v8-fast-<quarter>`) — `actions/cache` skips the post-job
save on an exact-key hit, making the fast cache FROZEN-IMMUTABLE within a quarter.
Parquet mtimes and fetch-recency signals are therefore NO-OPs across cron runs. Design
C would serve stale output. Design B re-verifies filing date against SEC each run —
no staleness, less SEC load (skips only the heavy companyfacts blob).

**Invariant recorded** (new §Gotchas entry): frozen-fast-cache-immutability + the
filing-precheck as the only safe skip path — see CLAUDE.md §Gotchas +
docs/GOTCHAS.md.

**Diagnostic**: log-only thread-safe counter `fundamentals_filing_precheck_skip_count`
(reset in `main.py` before the fetch loop, logged after the histogram). No schema
change; the counter is internal only.

**Tests**: 17 new offline tests in `tests/test_ingest/test_filing_precheck.py`.
CI-validated; edgartools/pandas-2.2 absent in the authoring sandbox so the full suite
ran in CI only (noted in PR body per CLAUDE.md §Conventions verification ladder).

**Files**: `compute/ingest/fundamentals.py` · `compute/config.py` (doc-comment only) ·
`compute/main.py` (import + reset + diagnostic log) ·
`tests/test_ingest/test_filing_precheck.py` (new, 17 tests) ·
`CLAUDE.md` (§Gotchas index) · `docs/GOTCHAS.md` (detail) ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## chore(agents) — revert 5 judgment-gate subagents `fable` → `opus` (in flight, 2026-06-13)

Branch `claude/festive-cerf-zlc94q`. Reverts PR #446 (2026-06-10): the main
session is back on **Opus 4.8**, so the 5 judgment-gate agents —
`quantrank-reviewer` · `methodology-scientist` · `release-captain` ·
`incident-commander` · `financial-engineer` — move `model: fable` →
**`model: opus`** in frontmatter. Per the standing model-alias gotcha this is
the bare FLOATING alias (resolves to Opus 4.8 today, floats forward on CLI
updates), NOT a pinned `claude-opus-4-8` ID — pinned numbered IDs are the
documented future-dated-downgrade footgun and are rejected by CI.

Guard `tools/check_model_pin.py` is functionally unchanged: `opus` was already
in `_ALLOWED_MODEL_VALUES`, and `fable` + `ANTHROPIC_DEFAULT_FABLE_MODEL` are
**intentionally KEPT** as harmless defensive entries (re-introducing either
alias later never trips CI). Only the docstring / failure-message examples flip
`fable` → `opus` for accuracy.

Docs lockstep — every current-state "fable" reference flips to opus: CLAUDE.md
(routing intro · cue table ×5 · §Spawn discipline "5-opus / 20-sonnet"),
`.claude/agents/README.md` (tier-table Model column ×5 · flow diagrams ×3 ·
§Dynamic workflow "Opus 4.8 orchestrator" · model-split + authoring §3), the 25
agent files' handoff lines ("the main **Opus 4.8** orchestrator") + cross-ref
model tags (ci-triage-engineer · literature-searcher · vercel-preview-auditor ·
compute-builder · data-scientist) + the 2 self-descriptions (quantrank-reviewer ·
release-captain), AGENTS.md (layout roster · alias mention · main-session
framing · "Opus agents" rare-fire note), CONTEXT.md (roster row), WORKFLOW.md
(phase 5/6 rows · cadence invariant), PHASE_STATUS.md (current-state inventory
row), docs/GOTCHAS.md (alias gotcha updated — the fable run is preserved as
history and the `claude-opus-4-8` BAD-pin example is intentionally kept as the
illustration). Historical entries in PHASE_STATUS*/archive intentionally
untouched (incl. the PR #446 `opus` → `fable` log line). No production code or
schema change; `ruff check .` + `python tools/check_model_pin.py` pass locally
(guard OK: 5 opus + 20 sonnet, all floating aliases).

---

## Issue #75 §3 — wire the IC-decay monitor into the cron + /analysis transparency surface (in flight, 2026-06-13)

Closes the last 2 of 8 acceptance criteria on issue #75 (PR 4b
defense-infrastructure) under the observability-before-wiring convention
(Rule 18). §1 (cross-source) + §2 (PBO/DSR) shipped + production-wired in PR
#60; the §3 IC-decay *library* shipped there too but was left uncalled
(logged as a Phase-5 tracker because the decay `alert` needs a regular
monthly IC panel). This PR production-wires the plumbing now, honestly
labeled (schema 0.10.19-phase8pilot → 0.10.20-phase4.6, layered on #479):

- **compute** — `compute/validation/ic_decay.py` gains
  `pillar_entries_to_monthly_panel` (per-commit `historical_ic` IC →
  calendar-month panel), `build_decay_report` (bounded 39-mo walk → panel →
  `check_all_pillars` → honest top-level `status`), a per-pillar
  `preliminary` flag that FORCE-suppresses `alert` until ≥
  `MIN_HISTORY_MONTHS` (12) monthly points, and additive `emit_decay_report`
  fields (`status`, `horizon_months`, `min_history_months`,
  `n_dates_with_ic`). `compute/main.py` calls it before the `Metadata(...)`
  build, try/except graceful-degrade (never blocks the cron), skip-safe via
  `QR_SKIP_DECAY_MONITOR`, and sets the new `Metadata.decay_report_url`. The
  artifact emits every cron even when empty.
- **schema triple** — additive `Metadata.decay_report_url: str | None`
  (schemas.py + types.ts mirror + regenerated snapshot; schema_check
  in-sync). `decay_report.json` itself is dataclass-emitted and deliberately
  NOT in the snapshot guard (the frontend `DecayReport`/`PillarDecay`
  interfaces are hand-written, separate from the schema-mirrored types).
- **frontend** — `/analysis` renders `DecayMonitorCard` (3 honest states),
  gated on `Metadata.decay_report_url`. The current real state is
  `status="insufficient_history"` (≈1 wk of git history): a quiet
  "accumulating baseline" panel + 10 pending pillars — NO fabricated zeros,
  NO false "0 decaying" badge — plus the "monitor only — never changes
  scores/ranks" disclaimer and the McLean-Pontiff (2016) citation.
  `monitoring`/`alert` render the per-pillar 12m-IC-vs-historical-mean table.
- **honesty** — informational ONLY; never vetoes or changes the composite.
  The `alert` becomes meaningful only once the panel densifies (≥12 monthly
  IC points/pillar). NOTE: the cron currently checks out shallow
  (`fetch-depth: 1`), so the git-walk sees only the tip commit and the report
  stays `insufficient_history` until the checkout is deepened — tracked as
  follow-up #478 (Phase 5's walk-forward harness is the longer-term
  densification source). The honest `/analysis` "accumulating baseline" state
  is correct under this constraint.
- **docs** — also corrected an inaccurate PHASE_STATUS.md §2 claim (the PBO
  tests are property/behavioral anchors, NOT a "Bailey 2014 Table-1 golden
  fixture within 5%").

Verification: `ruff` clean · 945 passed / 6 skipped offline (27 ic_decay
tests, 16 new) · `schema_check` in-sync · `tsc --noEmit` + `next build`
(510/510 static pages) green. Design-reviewer honesty audit PASS; its one
FAIL (neutral-chip dark camouflage) + 3 WARN fixed.

---
## 2026-06-13 — fix(scoring+ci): #469 follow-up — widen 8-K jitter 24h→72h + canary housekeeping

The #469 jitter shipped at 24h; the same-day performance-engineer
sufficiency analysis proved that insufficient on TWO independent axes:
(1) **weekday cliff** — the next cohort cliff lands Thu 2026-06-19 22:00
UTC; the binding cron gap on a weekday is 24h, so W=24h lets ~471/502
tickers refetch in that single Thursday run = the original ~75-min tier2
spike, essentially unmitigated (the 24h jitter rescues only ~6%);
(2) **re-bunching** — per-cycle spread grows as k·W, but the cron cadence
has a 62h Sat-08:00→Mon-22:00 gap, so any W≤62h lets Monday re-absorb the
whole cohort (W=24h re-bunches through cycle 2; doesn't escape until
cycle 3+, slow descent). Fix: `EDGAR_8K_CACHE_TTL_JITTER_SECONDS`
24h→**72h** (config.py). 72h > the 62h gap → never re-bunches from cycle
1; the 2026-06-19 cliff → ~157 tickers/+25min instead of 471/+75min; max
new-8-K visibility delay 72h, negligible vs the 365/730-day 4.01/4.02
lookback + weekly ranking cadence. Companion: canary TTL-proximity
threshold 120h→72h (= 144−72) in BOTH byte-identical workflows + warning
message "within 24h"→"within 72h". Also removed the broken
`restored slow-text key` canary echo — it referenced
`steps.restore-slow-text.outputs.cache-matched-key`, an output
`actions/cache@v5` does NOT expose (only `actions/cache/restore` does) →
rendered blank in the #249 verification run; the native "Cache restored
from key:" log line already carries it, so the echo + its
`test_canary_echoes_restored_slow_text_key` guard + the now-unused
`id: restore-slow-text` were dropped. Folded in post-merge doc
housekeeping (Mode C): CLAUDE.md §In-flight rotated off the merged #469
entry, §Next-deliverables + WORKFLOW.md §Phase-8 checkbox + PHASE_STATUS.md
mark #249 DONE (#468). Cache family NOT bumped (read-TTL param change,
existing entries stay valid). **TIME-SENSITIVE: must merge before the Thu
2026-06-19 22:00 UTC cron** or the spike recurs that night. Verify: ruff
PASS, scoring+workflow suites green, canary byte-identical.
---

## 2026-06-13 — fix(ci): pre-merge-prod-sim cold-cancel — restore both cache bundles + timeout 90→240

The pre-merge-prod-sim `simulate` job was CANCELLED at its 90-min
`timeout-minutes` cap on PR #475's run #98 (run 27471644445 / job
81203525304), killed mid per-stock write
(`Wrote .../stocks/history/DOW.json` → `##[error]The operation was
canceled`). DIAGNOSIS from the job log (downloaded the run-logs zip for
the restore-step head the job-log API tail couldn't reach): the
cache-restore step MISSED — the step log reads verbatim
`Cache not found for input keys: cache-v8-fast-2026Q2-Linux,
cache-v8-fast-2026Q2-, cache-v8-fast-` (restored in 1s = nothing
downloaded). With an empty cache, all 5 QR_SKIP_* escape hatches fell
through their documented "no cache → live fetch" paths: 502/502 tickers
cold-fetched fundamentals (`QR_SKIP_FUNDAMENTALS set but no cached parquet
for A … YUM — falling through to live EDGAR fetch`, ~20 min 15:58→16:18)
+ cold `fundamentals_history` (2 live EDGAR round-trips per stock through
the writer phase, ~1400 `edgar.core: Identity … set` calls @ ~5.9s/stock,
~50 min) + a cold OSAP download (`Cached 1226794 rows`, ~10 min). This is
cause (a) cache-restore MISS, not a genuinely-heavy warm run. Two
contributing root causes, two fixes:

1. **Structural restore bug (the high-value fix).** The cron
   (`compute-rankings.yml`) saves its cache as TWO bundles under DIFFERENT
   keys — fast (`cache-v8-fast-<q>-<os>`) + slow-text
   (`cache-v5-text-<os>-<run_id>`). The sim listed all 11 paths under the
   single fast key, so the 5 slow-text paths (edgar_10k_text / edgar_8k /
   osap / amendments / late_filings) were NEVER restored — they live in a
   cache the sim never requested. That is why OSAP cold-downloaded on EVERY
   sim even with `QR_SKIP_OSAP=1` (the skip falls through to a live fetch
   when the parquet is absent). Split the sim's one restore step into TWO
   `actions/cache/restore@v5` steps mirroring the cron's two bundles
   (restore-only on both — the sim must never SAVE); the slow-text step
   uses restore-keys prefix `cache-v5-text-<os>-` since the cron's save key
   is run-id-unique. A warm restore is now ~15-25 min.
2. **Timeout safety net (must-have regardless of cache).** A PR-context
   cache MISS is INHERENT — GitHub scopes caches per branch, so a fresh
   `main` save is not always visible to a PR run (run #100's main cron
   saved cache-v8-fast-2026Q2-Linux at 15:50 yet this PR run missed it 8
   min later). And the upcoming S&P 900 pilot's first cold run can't finish
   in 90 min by construction. Bumped `timeout-minutes` 90→**240** to match
   the weekly cron (raised in the #249 era + Phase 7.0 folded backtest);
   the sim runs FEWER loops than the cron (5 skip vars, no committed output,
   no PIT backtest) so 240 is an upper bound it never approaches warm, but
   it must not be LESS or the silent cancellation recurs.

Regression guard: added two tests to
`tests/test_workflow_cache_coverage.py` —
`test_sim_timeout_at_least_cron_timeout` (sim timeout must be ≥ the
cron's, so a future cron bump can't strand the sim again) and
`test_sim_restores_both_cron_cache_families` (sim must request BOTH the
fast and the `cache-vN-text-<os>-` slow-text families). Both fail on the
pre-fix sim (positive-control verified). No production code / schema
change; cache family NOT bumped (restore-key plumbing only). Verify:
`ruff check .` PASS, `tests/test_workflow_cache_coverage.py` 29 passed,
all 3 workflow YAMLs parse.

---

## 2026-06-14 — feat(ingest+schema): S&P 900 pilot PR 1 — 900-universe ingest + per-cohort diagnostic Metadata

Phase 8 pilot, first slice — **observability-first (Rule 18)**: ship the
900-universe ingest + a per-cohort diagnostic `Metadata` surface with the
ranked output BYTE-IDENTICAL to a 500 run (midcaps NOT ranked — that is
PR 3, gated on ≥ 1 cron confirming midcap coverage). Mirrors the project's
own discipline for every new data cohort (Form-4 PR 2, Alpha158 4j.1).

**Build:** `compute/ingest/universe.py` — promoted the scout's
`fetch_sp400_constituents` (Wikipedia S&P 400, cached parquet) +
`_parse_sp400_html` + `_resolve_cik_for_midcap` (`Company(ticker).cik`
zfill(10), graceful — log+skip on failure, never crash) +
`get_sp900_constituents` (concat 500+400, `drop_duplicates(keep="first")`
with sp500 tagged first → sp500 wins transient overlap, `cohort` column
"sp500"/"sp400"). `compute/config.py` — `QR_UNIVERSE` env constant
(default `"sp500"`), `WIKIPEDIA_SP400_URL`, `SP400_UNIVERSE_CACHE`,
`SP900_UNIVERSE_CACHE`, `SP400_CACHE_MAX_AGE_DAYS`; SCHEMA_VERSION
`0.10.18-phase4.6` → `0.10.19-phase8pilot`. `compute/main.py` —
`_run_midcap_coverage_probe()` (iterates ONLY `cohort=="sp400"`, calls
`fetch_fundamentals`, counts non-null GAAP coverage + null-rate + CIK
resolution pct; exception-in-fetch counted as null), guarded by
`if config.QR_UNIVERSE == "sp900"`; the 4 `_pilot_*` vars init to `None`
BEFORE the guard so the `sp500` path is byte-identical. Schema triple:
4 additive nullable `Metadata` fields (`universe_cohort_sizes`,
`midcap_fundamentals_coverage_pct`, `midcap_null_rate_pct`,
`midcap_cik_resolution_pct`) mirrored in `types.ts` + `schema-snapshot.json`
regenerated; `schema_check` green.

**Byte-identical proof:** the probe never touches `summaries`,
`write_rankings_json`, `write_stock_detail`, or any scoring function — it
is a pure read-side coverage probe over the midcap cohort. On `sp500` the
4 fields serialize `null`. ADRs excluded at source (S&P 400 is domestic;
20-F/6-K is the 1500 phase).

**Verify:** ruff PASS · `schema_check` PASS · full offline suite **1830
passed / 12 skipped** (OSAP modules need `[factors]`) · 30 new tests
(`tests/test_ingest/test_universe_sp900.py`: sp400 parse, sp900
dedup/cohort/CIK, probe arithmetic, byte-identical-500 guard).

**Decisions in effect (issue #130 / pilot):** eligibility — midcaps in
rankings day-1, AI-pick-eligible after 2 green crons; Bonferroni +
liquidity-backstop deferred to the 1500 cutover; defense set FROZEN;
thresholds held at 500-calibration; methodology-scientist ratifies before
PR 3. Follow-ups (NOT this PR): `universe=sp900` precache dispatch input
(PR 5); `config.UNIVERSE` string + ranked midcap output (PR 3);
`verify_membership_ledger.py` cohort-filter (PR 2, the required R6 fix).
---

## 2026-06-14 — ci(workflow): S&P 900 pilot PR 2 — `universe` workflow_dispatch input (enable the sp900 diagnostic run)

PR 1 (#479, merged) added `config.QR_UNIVERSE` (env, default `"sp500"`) +
a midcap coverage probe that fires only on `sp900`, but nothing could SET
`QR_UNIVERSE=sp900` in CI → the diagnostic couldn't run, so PR 3 (ranking
midcaps) had no empirical coverage gate. This PR closes that: adds a
`workflow_dispatch.inputs.universe` choice input (`sp500` | `sp900`,
default `sp500`) to `compute-rankings.yml`, wired to the top-level `env:`
as `QR_UNIVERSE: ${{ github.event.inputs.universe || 'sp500' }}`. The
`|| 'sp500'` fallback is load-bearing: the SCHEDULED cron trigger has
`github.event.inputs == null`, so it resolves to `sp500` → byte-identical
to today. The assignment is an `env:`-block expression, NOT a `run:`-line
`${{ }}` interpolation, so it carries no shell script-injection surface
(AGENTS.md §Security; mirrors backfill-portfolio.yml's env-proxy
discipline). Operator flow: Actions → Compute Rankings → Run workflow →
`universe: sp900` → the run executes the midcap probe and the writer
commits rankings.json (500, byte-identical) + metadata.json WITH the 4
`midcap_*` coverage fields populated — that committed metadata.json is the
diagnostic artifact gating PR 3. Budget: the first sp900 dispatch
cold-probes ~400 midcaps sequentially (~40-167m) on top of warm-500
compute (~16m) + backtest (~40m); fits the 240-min ceiling if the 500
caches are warm (recent cron/precache). Guard test
(`test_compute_rankings_has_universe_dispatch_input`) pins the input,
both choices, `default: sp500`, the `QR_UNIVERSE` fallback wiring, and the
no-run-line-interpolation invariant. Verify: ruff PASS, workflow guard
suite 30 passed, 3 workflow YAMLs parse. Out of scope (follow-ups):
precache `universe=sp900` warming (PR 5); ranking midcaps + R6 verifier
cohort-filter + backfill guard + forward-only Metadata flags (PR 3).
---

## 2026-06-15 — feat(ingest+schema): S&P 900 pilot PR 3a — rank midcaps (gated) + index_membership marker

> **MERGED 2026-06-15** — squash `9ea26527` (#482). Schema `0.10.21-phase8pilot` now on `main`; cron default still `sp500` (gated). Next: a manual `universe: sp900` validation dispatch.

The integration slice: midcaps ENTER the ranked output on `QR_UNIVERSE=sp900`,
but the SCHEDULED cron default stays `sp500` (owner chose gated-validate-first;
`compute-rankings.yml` UNTOUCHED). 3a's 900-rank path activates only on a
manual `universe: sp900` dispatch. The empirical gate already passed (sp900
diagnostic 2026-06-14: midcap coverage 99.5%, CIK resolution 99.75%).

**Decisive reframe (from the PR-3 plan):** the home-page AI-pick book is
sourced ONLY from `backtest_pit.json` (500-only via
`scripts/backfill_portfolio_pit.py get_sp500_constituents()`); `compute/main.py`
has NO live forward-pick. So "AI-pick-eligible after 2 green crons" is enforced
STRUCTURALLY as long as the backfill stays 500-only → the Task-5 backfill
assertion is what keeps it true; NO stateful first_seen ledger (PR 3b dropped).

**Build:** `compute/main.py` universe-load seam — `QR_UNIVERSE=="sp900"` →
`universe = get_sp900_constituents()` (all ~903 ranked, `cohort` column from
the loader); else `get_sp500_constituents()` + `universe["cohort"]="sp500"`
(unconditional column); probe reuses the loaded frame (dedupe). `cohort`
propagates: `_fetch_prices_one` returns `"cohort"` → `df` → `cohort_by_ticker`
dict → `index_membership=` on both `StockSummary`/`StockDetail`. `Metadata.universe`
→ "SP900" on sp900; `universe_cohort_sizes` now populated on the scored path.
Schema triple: `index_membership: str = "sp500"` (schemas.py + types.ts +
snapshot regen); `SCHEMA_VERSION 0.10.20-phase4.6 → 0.10.21-phase8pilot`
(restores the phase-8 label #477's bump reverted). R6:
`verify_membership_ledger.current_universe()` filters
`r.get("index_membership","sp500")=="sp500"` (900 rows no longer false-fail
BAND 498-506). Backfill: assertion `set(members["cohort"].unique()) <= {"sp500"}`
+ WHY comment (issue #130 forward-only honesty). cron default UNTOUCHED (gated).
19 new tests (`test_universe_sp900_pr3a.py`) + test_config version pin. Verify:
ruff PASS, offline suite 1866 passed/0 failed, schema_check PASS.

**methodology-scientist RATIFY (APPROVED-AS-ANNOTATE)** — the defense set frozen
at 500-calibration is literature-sound for 900: only Sloan + NSI recompute
(within-sector population-relative deciles, self-adjusting; Sloan 1996 /
Pontiff-Woodgate 2008 documented on cohorts BROADER than the S&P 500 incl.
midcaps); absolute thresholds (Altman/Beneish/Dechow) are population-invariant.
Bonferroni + liquidity-backstop correctly deferred to 1500 (Bonferroni governs
the absolute tests, population-invariant; the deciles don't multiple-compare).
Floors (SLOAN_MIN_POPULATION_SECTOR=15 / NSI_MIN_POPULATION=10) stay — raising
them would reintroduce the #7 over-firing. No #130-frozen item moves.
**Pre-registered validation bands** (the gated sp900 dispatch is measured
against these): `sloan_accruals_top_decile` 8-12% univ; `net_issuance_top_decile`
5-10% univ; **sp400 cohort fired-share tilt 1.0-1.4×** of its 44.3% universe
share (HARD ALARM at 1.6-1.7× → midcap distribution not sector-homogeneous →
size-tercile grouping is the 1500-cutover fix, NOT a pilot threshold change);
Beneish veto expected modestly hotter on the sp400 cohort (documented
size-effect FP drift toward broad-market ~30%, NOT a recalibration trigger).
φ-matrix re-run on the 900 cohort is a 1500-cutover prerequisite, not a 3a gate.

**Gated sequence to "midcaps live":** 3a merge → dispatch `universe: sp900`
validation → check actual firing vs the bands above + the 240m cron budget warm
→ precache-900 PR (data-pipeline; warm the 400 before any flip) + frontend PR 4
(copy + midcap badge) → one-line `compute-rankings.yml` cron-default flip →
midcaps live. PR 3b (first_seen ledger) DROPPED — structurally enforced.

Note: cross-session #477 (IC-decay) merged between #480 and this branch and
left two stale doc lines on main (§In-flight described merged #477;
§Phase-status "Current schema" still says 0.10.18 though main is 0.10.20) —
§In-flight rotated here; the current-schema line is a pre-existing drift for
Mode C to correct post-merge.
---

## 2026-06-15 — ci(precache): S&P 900 pilot precache-900 Phase A — edgar_form4 fast→slow + universe dispatch input

precache-900 prerequisite for the eventual sp900 cron-default flip. Two parts:

1. **Move `edgar_form4` from the FAST cache bundle to the SLOW-TEXT bundle** in BOTH
   `compute-rankings.yml` + `precache-edgar.yml` (lockstep). The fast bundle's exact
   quarter-key (`cache-v8-fast-${quarter}`) makes `actions/cache` SKIP the post-job save on a
   warm hit, so an sp900 precache could never persist midcap Form-4 (the sp500 cron already
   populated the quarter key). The slow-text bundle's run-id key
   (`cache-v5-text-${os}-${run_id}`) is unique per run → the save is never skipped → midcap
   Form-4 now persists. data-pipeline-engineer DATA-HEALTHY (Form-4's 7-day TTL fits the
   weekly run-id cadence; the original fast-bundle placement was accidental, not principled).
   One-time transition cost: ~7-10 min cold Form-4 on the first post-merge cron.
2. **Add a `universe` workflow_dispatch input** (sp500/sp900, default sp500) +
   `QR_UNIVERSE: ${{ github.event.inputs.universe || 'sp500' }}` env to `precache-edgar.yml`,
   mirroring #480. Lets a manual Saturday `universe: sp900` precache warm the 400 midcap
   caches off-cycle.

NO v8→v9 cache-key bump — that is **Phase B**, deferred to the flip PR (where the v9 bump is
semantically justified as universe-expansion cache invalidation: the fast bundle's exact-key
save-skip means sp400 fundamentals/prices ALSO won't persist via a warm-key precache, so the
v9 cold-seed is what makes the full sp900 fast bundle warm). New test
`test_precache_has_universe_dispatch_input`; the canary step stays byte-identical
(`test_canary_step_identical_in_both_workflows` green); 31 cache-coverage tests pass; ruff
clean. compute-builder BUILT-CLEAN.

Validation context: lands after the gated sp900 dispatch #103 (902 rows) PASSED the
pre-registered bands (Sloan 10.4% / NSI 7.9% universe-wide; sp400 tilts in-band except NSI
1.46× < the 1.6× alarm) — methodology pre-ratified at #482; stock-detail-auditor GREEN on
data-integrity (extreme midcap MoS = real outliers, not #248-V corruption) with 2 flip-blockers
routed separately (OZK/PBF null-fundamentals ingest failures). Warm sp900 cron estimate
post-precache: ~60 min (Phase A) → ~25 min (Phase B), both within the 240-min budget.

---

## 2026-06-15 — fix+test: open-issue cleanup batch (#385 revenue extraction + #207 form4 retry + #377/#208/#378 test coverage)

Cleanup batch landing five small, unblocked open issues found in a full
open-issue triage (29 open → this PR `Closes` 5 on merge; the same triage
separately confirmed 9 others already-fixed and closed them, and produced
the #261 CLOSE-AS-CORRECT verdict — see below).

**#385 (live bug — APA, rank #19, `revenue=None`):** APA and other E&P
filers (COP, OXY) tag consolidated revenue under
`us-gaap:OilAndGasRevenue`, absent from both revenue tag chains, so APA
scored on a silently-missing revenue input (value / profitability
pillars). Appended `"us-gaap:OilAndGasRevenue"` as a fallback to
`_TTM_REVENUE_TAGS` + `_ANNUAL_TAGS["revenue"]`
(`compute/ingest/fundamentals.py`). **Selection semantics (pinned by
tests):** the TTM path is MAX-of-fresh (largest fresh value wins,
ORDER-INDEPENDENT — a co-reporter's consolidated total always exceeds any
segment line, so the right number wins; the production comment was
corrected to say so, not "placed last"); the annual path is first-non-
null `break`, so last placement keeps standard filers from reaching it.
The fast-cache is frozen-immutable within a quarter (parquet mtimes are
no-ops), so the new tag only takes effect on a cache-key bump:
`cache-v8-fast → cache-v9-fast` in **ALL FOUR** cache-warming workflows
(`compute-rankings.yml`, `precache-edgar.yml`, `backfill-portfolio.yml`
incl. its `-bf-` save key, `pre-merge-prod-sim.yml`) per the
`test_workflow_cache_coverage.py` 4-file lockstep guard, which was
updated to pin v9 (+ a new bump-history entry). **Op cost:** the next
cron after merge cold-rebuilds the fast cache. **Rebase note (on #486):**
#486 moved `edgar_form4` fast→slow but stayed v8, reserving v9 for its
Phase B; this PR takes v9 now for the #385 fundamentals invalidation, so
the deferred Phase-B bump shifts to v10. **Scoped out:** APA
`capex=None` needs a `--run-network` probe for the E&P capex concept →
follow-up.

**#207 (form4 retry):** `compute/scoring/form4_insider.py` had no retry on
its SEC Form-4 fetch — a 429 throttle was indistinguishable from a parse
error. Added `_fetch_form4_filings_with_retry` wrapping ONLY the SEC
round-trip with the canonical project tenacity policy
(`stop=(stop_after_delay(30) | stop_after_attempt(2))`,
`wait=wait_exponential(min=2, max=8)`, `reraise=True`, mirroring
`fundamentals.py`); graceful-degrade (return `None`) preserved; 429-vs-
generic log split.

**#377 / #208 / #378 (test coverage, +83 tests, all green):** #377 — 23
tests over 10 previously-uncovered `manipulation_index` rollup flags; #208
— form4 main-loop diagnostics (None/empty/exception never abort the cron)
+ verify-helper Section K accounting-equation tests; #378 — RE-SCOPED (the
issue's `fetch_prices_one` no longer exists → now `_fetch_prices_one` in
`compute/main.py`): split into a `fetch_prices` offline smoke file + a
pure-math `price_change_1d_pct` file.

**#261 (closed separately, not in this diff):** methodology-scientist
verdict = CLOSE-AS-CORRECT. The substantive PE contamination was fixed by
RATIFY-B (#456); the residual GOOG/GOOGL fair-price gap is an expected
conservative-ensemble artifact (same pattern on single-class AAPL), and
aggregate-share EPS is correct under ASC 260 — the listed-class count
would REINTRODUCE the #456 bug. Two cosmetic items (stale
`multi_class_shares.py` docstring premise + relabel the
`multi_class_aggregate_shares_suspected` annotate corruption→informational)
routed to a Q3 2026-08-19 cohort-audit follow-up issue.

**Schema triple:** untouched (no field changes; APA revenue flows through
existing `RawMetrics.revenue`). **Rule 16 / Rule 18:** n/a (extraction-
chain + retry hardening, not a new scoring layer or external source).
**Verify:** ruff PASS (whole repo) · +83 new tests green · cache-coverage
guard 30 passed · `schema_check` in-sync · full offline suite — the only
non-passes are the 30 pre-existing sandbox dep-import failures/errors
(`edgar`/`yfinance`/`bs4`/`openassetpricing` not installed locally; they
run in CI under `[dev,factors]`), confirmed by a before/after diff to be
unchanged by this batch. **Out of scope (follow-ups):** APA capex
network-probe; #261 Q3 docstring/annotate relabel.

---

## 2026-06-15 — fix(ingest+scoring+schema): fundamentals_unavailable veto + PBF EDGAR-identity fix (OZK/PBF sp900 flip-blocker)

> **MERGED 2026-06-15** — squash `a0000f42` (#487); rebased onto #485. Schema `0.10.22-phase8pilot` + defense layer 34 now on `main`.

The sp900 dispatch #103 exposed 2 sp400 midcaps (OZK, PBF) with COMPLETE EDGAR ingest
failures (`snapshot is None`, all 34 fundamentals null) ranked `recommendation=lean_bullish`
on a price-only composite (~51-53 from the neutral-50 fundamental-pillar imputation) with NO
warning — DQIC did not fire (`_data_quality_input_corruption(None)` returns False per issue
#18, which needs some field present). Flip-blocker for the sp900 live flip. edgar-debugger
root-caused; methodology-scientist **RATIFY-AS-VETO**.

**Part A — PBF ingest fix** (`compute/ingest/universe.py`): set the EDGAR identity before the
midcap CIK lookup in `_resolve_cik_for_midcap`, so the live SEC ticker→CIK fallback succeeds
for sp400 names absent from the bundled `company_tickers.parquet` (the identity-ordering race —
`_resolve_cik_for_midcap` is the only sp900 path that calls `Company(ticker)` before
`fundamentals.py::_require_identity` runs).

**Part B — `fundamentals_unavailable` defense flag (DIRECT veto):**
- `risk_overlay.py::compute_risk_flags` emits `"fundamentals_unavailable"` when `snap is None`
  → `cautious` + Top-5 suppression. **Direct-veto, no annotate-first staging**: the FP rate is
  structurally zero (fires on input-absence, not a calibrated threshold); DQIC (issue #18) is
  the governing direct-veto precedent; annotate-before-veto (Rule 16) does not bind (a null
  snapshot has zero usable fundamentals → no legitimate stock it can wrongly suppress). Does
  NOT touch the `_data_quality_input_corruption(None)→False` contract (`test_D3` stays green;
  the new flag locks the DQIC/`fundamentals_unavailable` null-domain partition).
- `recommendation.py`: `"fundamentals_unavailable"` added to `_CAUTIOUS_FORCING_RISK`.
- **Rule-18 counter**: `Metadata.fundamentals_unavailable_count` (schema triple: `schemas.py` +
  `types.ts` + `schema-snapshot.json` regenerated); `SCHEMA_VERSION` `0.10.21-phase8pilot` →
  **`0.10.22-phase8pilot`**; `main.py` counts None snapshots.
- Defense layer **33 → 34** declared boolean flags (additive; academic flags + pre-registered
  sp900 bands UNAFFECTED — a null snapshot makes every academic computation NaN, so φ ≈ 0 with
  all of them by construction).

methodology RATIFY-AS-VETO; compute-builder BUILT-CLEAN (ruff + schema_check in-sync + 201
tests + tsc; `test_D3` green). On-merge: Mode C bumps the CLAUDE.md current-schema line →
0.10.22 + the defense-layer count 33→34 + a §Gotchas one-liner for the direct-veto invariant.

---

## 2026-06-15 — docs(Mode C): canonical-tracker reconciliation post-#485 + #486 (reworked onto 0.10.22)

Mode C bump after #485 + #486 merged, reworked onto current main (#487
schema 0.10.22 + #488's partial Mode C). Strikes #385/#261 (+ #207/#208/
#377/#378) from the data-integrity sprint cluster + open-issues list
(closed by #485); adds #485/#486 (+ #483/#487/#488) to PHASE_STATUS +
CLAUDE recent-merges; Phase 8 row/tail + WORKFLOW AC tick #486
precache-900 Phase A; WORKFLOW cadence pointer 0.10.17→0.10.22 + defense
33→34. #486's deferred cache bump = Phase B v10 (since #485 took v9).
SKILL.md + schema headers untouched (owned by #487/#488). Docs-only.
---

## 2026-06-15 — feat(frontend): S&P 900 pilot PR 4 — per-index tab cohort filter

Makes the index tabs FUNCTIONALLY separate the universe by `index_membership` cohort, so the
S&P 400 mid-caps get their OWN tab rather than being combined into the S&P 500 list (owner
feedback on the first cut). Prepares the frontend for the eventual sp900 cron flip without
breaking the current sp500 (502) display.

- NEW `frontend/components/RankingView.tsx` (`'use client'`) — holds the active-tab state
  (default `ALL` = All stocks, the leading landing tab; `safeTab` falls back to `SPX` on
  single-cohort sp500 data where `ALL` is not in `availableCodes`), derives the cohort filter +
  re-numbered display rank (1..N per tab) + per-tab h1/count, composes with the existing search.
  Data passed as props from the Server-Component page (no `fs` in a client component).
- `IndexTabs.tsx` — rewritten as an interactive `role="tablist"`; **data-driven availability**:
  a tab is clickable iff `rankings.json` has rows for that cohort, else it keeps its "SOON"
  marker. "All stocks" LEADS as the first/leftmost tab. So on the 502 sp500-cron data the
  S&P 400 + All-stocks tabs read "SOON" (the page lands on S&P 500 via the fallback); on sp900
  data they activate and the page opens on All stocks. Indices with no data (S&P 600 / Dow 30 /
  NASDAQ / Russell) stay "SOON". The active tab carries `tabIndex={0}` for `role="tablist"`
  keyboard reachability (full roving-tabindex deferred — matches the CountryTabs baseline).
- Per-tab h1/count: "S&P 500 ranking" / 502 · "S&P MidCap 400 ranking" / 400 · "All US stocks
  ranking" / 902. `lib/visual.ts::universeLabel` de-combined (SP900 → "All US stocks"; the old
  "S&P 500 + 400 mid-caps" wording removed).
- `RankingTable.tsx` + `StockListCard.tsx` — `cohortSize` (X / N denominator) + `showMidcapChip`
  props; the Mid-cap chip shows ONLY in the "All stocks" mixed tab (redundant in single-cohort
  tabs). `MidcapChip.tsx` stays for the stock-detail hero.
- Composite SCORES stay 902-universe (cross-sectional — the pilot's point); the tabs separate
  the DISPLAY + re-number ranks only. Per-index standalone re-scoring = a separate compute
  change if wanted. Schema triple untouched.

frontend-builder BUILT-CLEAN (tsc + next build + schema_check PASS). Supersedes the first cut
(combined "S&P 500 + 400 mid-caps" list, owner-rejected). Gate: quantrank-reviewer (opus) PASS
on code invariants + phase-coordinator Mode B LOCKSTEP-SATISFIED + frontend-design-reviewer
GO-WITH-NITS (tabindex nit applied). Lands before the sp900 flip PR.

---

## 2026-06-16 — fix+test: FDXF empty-snap veto widening + post-scoring cohort-size counter (sp900 pre-flip data-integrity)

Closes the one user-facing data-quality bug surfaced by the post-cron audit of the sp900
validation run #107 (stock-detail-auditor). Owner chose **fix-first, then flip**: this PR
lands before the cron-default flip PR. The #107 run itself PASSED the pre-registered defense
bands (NSI fired-share **1.461× < 1.6× hard alarm** — identical to the passing run #103; Sloan
10.42% univ / 1.032× tilt in-band; Section A-L 0 fail) and methodology RATIFIED **PROCEED-WITH-DOC**;
the gate is clear once this fix lands.

**Bug 1 (user-facing) — `fundamentals_unavailable` empty-snap widening.** FDXF (FedEx Freight,
sp500, spun off 2025, rank 408) had ALL 34 fundamentals null / `market_cap=None` / `fair_price=None`
yet showed `recommendation=lean_bullish` (neutral-50 pillar imputation) with NO veto. Root cause:
the #487 `fundamentals_unavailable` direct veto fires only on `snap is None` (OZK/PBF case); FDXF
got a NON-None snapshot that extracted ZERO fields ("empty snap") and slipped through. Fix:
- NEW `risk_overlay.py::_snapshot_has_no_usable_fundamentals(snap)` — predicate
  `len(snap.missing_fields()) == len(ALL_METRIC_KEYS)` (ALL 34 metrics null). Most-conservative:
  one non-None field → does NOT fire (never catches partial data).
- Guard widened `if snap is None:` → `if snap is None or _snapshot_has_no_usable_fundamentals(snap):`
  — same flag, same action (cautious + Top-5 suppress). Unified semantic: "no usable fundamentals"
  whether or not the snap object exists.
- **Partition preserved** (test_D3 UNCHANGED): `fundamentals_unavailable` = ABSENCE (None OR all-null);
  `data_quality_input_corruption` = a PRESENT field internally inconsistent. Mutually exclusive by
  construction. FP rate for the empty-snap case is structurally zero (input-absence, not a threshold),
  so annotate-before-veto does NOT bind — same #487 / DQIC direct-veto rationale. **Defense layer
  stays 34** (domain widening, NOT a new flag). `Metadata.fundamentals_unavailable_count` counter
  extended (OZK + FDXF = 2 on #107 data).

**Bug 2 (minor surface) — `universe_cohort_sizes` post-scoring recompute.** Was computed pre-scoring
in `_run_midcap_coverage_probe` (sp500=503, incl. one delisted name dropped before write) →
`sum=903 ≠ universe_size=902`. Fix: `main.py` recomputes `_pilot_cohort_sizes` from the post-scoring
`summaries` (sp900 path only; default sp500 path unchanged) so the per-cohort counts always sum to
`universe_size`.

Schema triple **untouched** (`fundamentals_unavailable_count` already exists). compute-builder
BUILT-CLEAN: ruff pass · pytest offline **1950 passed / 12 skipped** (+12: 9 E-series partition
tests + 3 cohort-sum-invariant tests) · schema_check pass · test_D3 green. Gate: quantrank-reviewer
(opus) + methodology-scientist (ratify the veto-domain widening) + schema-sentinel + phase-coordinator
Mode B. Lands before the sp900 cron-default flip PR.

---

## 2026-06-16 — ci(phase8): S&P 900 cron-default flip — precache-900 Phase B

Makes midcaps **permanently live** on the weekday compute cron. All gates cleared:
- sp900 validation run #107 PASSED pre-registered defense bands (NSI fired-share **1.461× < 1.6×**
  hard alarm; Sloan 10.42% univ / 1.032× tilt in-band; Section A-L 0 fail)
- Methodology **RATIFIED PROCEED-WITH-DOC**
- FDXF empty-snap blocker fixed + merged (#491, on main)

**Changes:**

1. **Cron-default flip** (`compute-rankings.yml` env:29): `|| 'sp500'` → `|| 'sp900'`. The weekday
   writer now ranks the full S&P 900 universe by default. Dispatch input default also flipped
   `sp500` → `sp900`; `sp500` stays as a manual dispatch option for diagnostics.

2. **`precache-edgar.yml` default flip** (env:62): `|| 'sp500'` → `|| 'sp900'`. The Saturday off-cycle
   precache now warms sp900 so it matches the weekday cron — Monday's cron restores warm. Consistent
   with the cron by design; keeping precache at sp500 would force Monday cold-seed on the midcap paths
   every week.

3. **Pre-merge-prod-sim mirroring decision**: Added explicit `QR_UNIVERSE: sp900` to
   `pre-merge-prod-sim.yml`'s `env:` block. The compute/config.py code default stays `'sp500'` for
   local-dev safety (no change there) — the sim cannot rely on the code default since the flip is
   workflow-only. Sim cost: sp900 cold-cache ~131 min vs sp500 ~43 min; the existing 240-min timeout
   (already matching the cron's budget) provides adequate headroom. No timeout bump needed.

4. **Fast bundle bump `cache-v9-fast` → `cache-v10-fast`** in all four workflows in lockstep:
   `compute-rankings.yml`, `precache-edgar.yml`, `pre-merge-prod-sim.yml`, `backfill-portfolio.yml`
   (including `cache-v9-bf-` → `cache-v10-bf-` in backfill). Rationale: the fast bundle's exact-key
   save-skip means sp400 fundamentals/prices won't persist via a warm-key precache; v10 forces a
   cold-seed of the full sp900 fast bundle on the first post-flip cron. Slow-text bundle
   (`cache-v5-text-`) left **UNCHANGED** (per the gotcha: text key bumps only on text-cache schema
   changes).

5. **sp400/sp900 universe parquets added** to fast `path:` blocks in all four workflows:
   - `compute/cache/universe_sp400-v1.parquet` (config.SP400_UNIVERSE_CACHE)
   - `compute/cache/universe_sp900-v1.parquet` (config.SP900_UNIVERSE_CACHE)
   Without these, the constituent-list parquets don't persist across runs and Wikipedia gets
   re-scraped every cron.

6. **`docs/GOTCHAS.md` Phase B reference updated**: stale `cache-v8 → v9` description in the
   `edgar_form4` gotcha updated to reflect the actual `cache-v9 → v10` bump done in this PR, with
   the sp400/sp900 parquet path additions noted.

7. **Test updates** (`tests/test_workflow_cache_coverage.py`):
   - `test_workflow_fast_cache_key_is_v9` → renamed `test_workflow_fast_cache_key_is_v10` + updated
     all v9 → v10 assertions + added the universe-expansion trigger to the taxonomy comment.
   - `test_workflow_fast_cache_key_full_shape_pinned`: updated v9 → v10 in the expected key shape.
   - `test_sim_restores_both_cron_cache_families`: updated v9 → v10 assertion.
   - `test_compute_rankings_has_universe_dispatch_input`: updated to assert `default: sp900` +
     `|| 'sp900'` fallback (was sp500).
   - `test_precache_has_universe_dispatch_input`: same update — sp500 → sp900 default.
   - NEW `test_sp900_universe_parquets_in_fast_path_blocks`: asserts sp400/sp900 universe parquets
     appear in fast-bundle `path:` blocks in compute-rankings, precache-edgar, pre-merge-prod-sim.
   - NEW `test_sim_mirrors_cron_universe_default`: asserts `QR_UNIVERSE: sp900` is set explicitly
     in pre-merge-prod-sim.yml's env block.
   - Total: 31 → 33 tests; all green.

**What was NOT changed:**
- `compute/config.py` — code default `QR_UNIVERSE = "sp500"` stays (local-dev safety; the flip is
  workflow-only).
- Schema triple — no schema change; `Metadata` fields unchanged.
- Slow-text bundle `cache-v5-text-` — unchanged (no text-cache schema change).
- Canary step — intentionally NOT edited; remains byte-identical between the two cache-warming
  workflows (`test_canary_step_identical_in_both_workflows` stays green).

**Gate lineage:** sp900 run #107 PASS + methodology PROCEED-WITH-DOC + #491 FDXF fix on main.
**Next cron after this lands:** first sp900 cron will cold-seed ~400 midcap fundamentals/prices
under cache-v10-fast (expect ~240 min cold budget); subsequent runs warm (~15-25 min sp500 + ~25-40
min additional for midcap incremental).

Schema triple: **untouched**. compute-builder BUILT-CLEAN: ruff pass · pytest offline
**33 passed** (workflow-cache tests; full suite verified) · schema_check not applicable (no schema
change) · `compute/config.py` untouched. Gate: security-reviewer (workflow changes) +
phase-coordinator Mode B (doc lockstep) + quantrank-reviewer.

**NSI tilt methodology note (PROCEED-WITH-DOC condition #1):** the sp400 NSI raw-rate
ratio measured ~2.31× (sp400 firing rate ÷ sp500 firing rate) — this is NOT the
pre-registered metric. The pre-registered metric is the **fired-share tilt = 1.461×**
(in-band: registered 1.0-1.4× center, hard alarm 1.6×; 1.461× < 1.6× → PASS, = run #103).
The rate-ratio elevation is consistent with Fama-French 2008 (NSI monotonically stronger
in smaller caps) and is NOT a miscalibration. Future Q3 2026-08-19 cohort audits MUST use
the fired-share tilt, NOT the raw-rate ratio, to avoid a false alarm.

---

## PR #493 — feat(compute+frontend+schema): multi-index membership — Dow 30 / NASDAQ 100 overlap tabs (in flight, 2026-06-16)

**Branch**: `claude/confident-thompson-y58bhe` · **Type**: feat(compute+frontend+schema); schema bump
`0.10.22-phase8pilot` → **`0.10.23-phase8pilot`**. Defense layer UNCHANGED at 34.

- **`index_memberships: list[str]`** — additive field on `StockSummary` + `StockDetail`
  (`default_factory=list` so pre-0.10.23 JSONs deserialize cleanly under `extra="forbid"`).
  Contains the primary cohort ("sp500"|"sp400") PLUS every overlapping index the stock is
  currently in ("dow30", "ndx").
- **`index_membership` (singular) KEPT UNCHANGED** — `MidcapChip` + `verify_membership_ledger.py`
  read it as the sp500/sp400 partition. The two fields are NOT consolidated; `test_ledger_unchanged`
  regression locks it.
- **Dow 30 + NASDAQ 100 Wikipedia sources** (`fetch_dow30_constituents` + `fetch_ndx_constituents`
  in `compute/ingest/universe.py`, 7-day cache, graceful-degradation → empty set on failure,
  sanity bands Dow==30 / NDX 95-105) + `derive_index_memberships` pure helper. `compute/main.py`
  fetches both sets once per run (both sp500 + sp900 paths, non-fatal). `compute/config.py` adds the
  URL/cache/band constants.
- **Dynamic derivation**: membership re-derived each run from the Wikipedia sets (NOT a frozen
  list / ledger) → a stock MOVING between indices (sp400→sp500, Dow/NDX reconstitution) reflects
  automatically. Display-only (no scoring/veto), so no survivorship-ledger integrity needed; the
  sp500/sp400 ledger (`data/sp500_membership_historical.csv`) is UNTOUCHED.
- **`frontend/components/RankingView.tsx`** — DJI + NDX tabs: `filterAndRerank` on
  `index_memberships?.includes('dow30'|'ndx')`; `computeAvailableCodes` lights a tab iff ≥1 row
  carries the code; `FULL_INDEX_SIZE={DJI:30,NDX:100}` drives an "N of M (overlap)" honesty note.
  `IndexTabs` unchanged (data-driven). **Russell deferred** (RUI/RUT/RUA/COMP stay SOON).
- **Schema triple** in lockstep (schema-sentinel verified). **Tests**: `test_index_memberships.py`
  (new — derivation units + Hypothesis, parser fixtures offline, graceful-degradation, sanity-band,
  schema round-trip/legacy/forbid, ledger-unchanged regression); `test_config.py` pinned 0.10.23.

Gate: quantrank-reviewer (opus) READY-TO-PUSH (code, no FAIL) + schema-sentinel SCHEMA-IN-SYNC +
frontend-design-reviewer + phase-coordinator Mode B/C. NOTE: the first compute PR post-flip — its
pre-merge-prod-sim runs sp900 (~131-240 min cold v10).

---

## PR #494 — feat(compute+frontend): Russell 1000 (RUI) overlap tab via market-cap proxy (in flight, 2026-06-17)

**Branch**: `claude/confident-thompson-y58bhe` · **Type**: feat(compute+frontend); **NO schema bump** —
`index_memberships: list[str]` already exists (#493); this only adds a new VALUE `"russell1000"`.
SCHEMA_VERSION stays `0.10.23-phase8pilot`; defense layer UNCHANGED at 34.

- **Reverses the #493 "Russell deferred" note** — owner chose the **market-cap proxy** (2026-06-17),
  accepting that RUI over the sp900 universe is ~redundant with All-stocks (a labeled cohort view,
  ~900 rows, NOT a distinct ranking). Composite scores remain the 902-universe cross-section; the tab
  separates display only.
- **`russell1000` market-cap proxy** — `derive_index_memberships` gains a keyword-only
  `market_cap: float | None = None`; appends `"russell1000"` iff `market_cap is not None and market_cap > 0`.
  Ordering: cohort → dow30 → ndx → russell1000. Rationale: the S&P MidCap 400 eligibility floor
  (~$6-7B) sits ABOVE the Russell 1000 inclusion cutoff (~$3-4B), so **every S&P 900 constituent is a
  Russell 1000 member by construction** — the cap-presence gate is the predicate; NO hardcoded dollar
  floor (a moving FTSE target), NO external fetch, NO FTSE list. Pure proxy over data we already have.
- **`compute/main.py`** — `market_cap=market_cap_by_ticker.get(ticker)` threaded into the
  `memberships_by_ticker` comprehension. `market_cap_by_ticker` (price × shares, `None` on missing
  snapshot) is already computed upstream in the CIK-collision pre-compute block → zero structural
  change; the `.get()→None` miss leaves the tag off (correct).
- **`index_membership` (singular) UNCHANGED** — still the sp500/sp400 partition from `cohort_by_ticker`.
  **RUT/RUA stay SOON** (Russell 2000 needs small-cap / S&P 600 ingest we don't do; Russell 3000 redundant).
- **`frontend/components/RankingView.tsx`** — RUI tab: `filterAndRerank` on
  `index_memberships?.includes('russell1000')`; `computeAvailableCodes` lights RUI iff ≥1 row carries
  the code; `tabConfig` ("Russell 1000 ranking"); `FULL_INDEX_SIZE={…,RUI:1000}`; honesty-note IIFE —
  "N of 1000 … the entire S&P 900 universe falls within the Russell 1000 … (partial overlap)".
  `IndexTabs` UNCHANGED (RUI already in `INDICES_US`; data-driven SOON→active).
- **Schema triple UNTOUCHED** (no schema change → schema-sentinel N/A). **Tests**:
  `test_index_memberships.py` +9 (`TestRussell1000Membership`: positive/None/zero/negative-cap gates,
  cohort→dow30→ndx→russell1000 ordering contract, sp400 path, dow30/ndx regression guard,
  additive-only semantics, main.py wiring contract) + Hypothesis `valid_codes` now includes
  `"russell1000"` and the strategy exercises the `market_cap` branch. 54 → 63.

Gate: quantrank-reviewer (opus) + frontend-design-reviewer + phase-coordinator Mode B. No
schema-sentinel (schema untouched); no methodology-scientist (display-only tag — no defense/scoring change).

---

## PR #495 — docs(Mode C): reconcile PHASE_STATUS / SKILL / WORKFLOW after #493 + #494 (in flight, 2026-06-17)

**Branch**: `claude/confident-thompson-y58bhe` · **Type**: docs-only (Mode C triple-doc reconciliation); NO code / schema / workflow change.

phase-coordinator Mode C reconciliation after #493 (multi-index membership, schema `0.10.23`) + #494
(Russell 1000 RUI market-cap proxy, NO bump) BOTH merged 2026-06-17 — neither had a Mode C pass.

- **PHASE_STATUS.md**: Phase 8 row appends #493/#494 DONE; §Current state date 06-15→06-17; Schema cell
  adds #494 + corrects stale "Cron default still sp500" → `sp900` (since #492); **Active vetoes 7→8**
  (added `fundamentals_unavailable` — stale since #487, internal-inconsistency fix caught by Mode C);
  In-flight cleared; new 2026-06-17 §Chronological history entry (incl. the first post-#494 cron
  `768c35f16` validated counts russell1000 900/902, dow30 30, ndx 88, 0 empty).
- **SKILL.md**: the `0.10.23-phase8pilot` schema-version row gets the #494 note (RUI via market-cap
  proxy, no bump); stale "Russell deferred" corrected.
- **WORKFLOW.md**: session-start schema pointer `0.10.22`→`0.10.23`; Phase 8 acceptance criteria tick
  Dow/NDX (#493) + Russell (#494); RUT/RUA/SML/COMP remain SOON.
- **CLAUDE.md** §Phase status: #494 moved from in-flight to merged-since list; "nothing in flight".
- **AGENTS.md** §Phase + version state: schema pointer reflects #493 + #494 both merged.
- **PHASE_STATUS_INFLIGHT.md**: #493/#494 entries left append-only (per the file's own
  MERGED→housekeeping-drain convention; not annotated in-place).

Gate: phase-coordinator Mode C (designed the diffs) + docs-reviewer substance. Docs-only → no
ruff/tests/schema_check/tsc impact.

---

## PR #496/PR-A — feat(valuation+schema): trimmed-median diagnostic — shadow `median_trimmed` + `median_trim_delta_count` (in flight, 2026-06-18)

**Branch**: `claude/confident-thompson-y58bhe` · **Type**: feat(valuation+schema); **SCHEMA BUMP**
`0.10.23-phase8pilot` → `0.10.24-phase8pilot` (additive PATCH). Issue #177 follow-up.
methodology-scientist RATIFIED-WITH-CONDITIONS. User-authorized as frozen pre-registration.

**What**: OBSERVABILITY-FIRST (Rule 18) diagnostic half of the fair-value ensemble trimmed-median
change — the root-cause fix for "the MoS gate kicks out growth/tech" (the even-n median + the
majority-extreme collapse drag the central fair value negative for asset-light / IP / high-growth
structures, producing false-negative MoS).

- **`compute/valuation/ensemble.py`** — SHADOW `median_trimmed` + `methods_excluded_from_median`
  (two-regime trim: minority-extreme → median of non-extreme subset; majority-collapse <2 survivors
  → null). Reuses the existing SYMMETRIC `_classify_outliers` (trims extreme-HIGH too). **Live
  `median`/`mos_pct` BYTE-IDENTICAL** — `median_trimmed` feeds nothing in scoring/recommendation/
  portfolio/loss_chance; the AI-pick `is_high_conviction` gate still consumes the untrimmed `mos_pct`.
- **`compute/output/schemas.py`** — `Metadata.median_trim_delta_count: int | None` (count of universe
  tickers whose MoS SIGN would flip under the trim — the blast-radius metric).
- **`compute/config.py`** — `SCHEMA_VERSION` `0.10.23-phase8pilot` → `0.10.24-phase8pilot`.
- **`frontend/lib/types.ts`** — mirrored `median_trim_delta_count` on Metadata (snapshot-tracked) +
  `median_trimmed`/`methods_excluded_from_median` on `FairPriceEnsemble` (untyped fair_price dict
  keys, not snapshot-tracked). NO UI surface (types-only).
- **Blast-radius (offline, 2026-06-18 cron data)**: 33 tickers (3.8%) would flip MoS sign (FFIV
  −27.6%→+15.8% confirmed; flippers span sectors — KTOS/BALL not just tech — confirming the rule is
  structure-driven, not tech-flattering).

**Staged sequence**: PR-A (this, diagnostic) → after ≥1 cron + data-scientist V55.1-gauntlet
validation (PBO ≤ 0.5 / DSR > 0 / purged-embargo holdout; non-inferiority framing) → the BEHAVIORAL
flip PR (median actually trims `mos_pct`) → a UI-bridge chip ("bullish but below margin-of-safety —
not AI-pick-eligible") + the METHODOLOGY.md "Why median, not mean" even-n correction.

Gate: compute-builder BUILT-CLEAN · frontend-builder · test-engineer (72 tests, +8, methodology's
symmetry hard-gate `test_shadow_trimmed_symmetry_high` satisfied) · schema-sentinel PASS ·
quantrank-reviewer PASS (8/8 invariants, byte-identical confirmed) · phase-coordinator Mode B.

---

## PR #497 — docs(methodology): Path C amendment — #177 behavioral flip → Q3 forward-OOS gate + U9 trial charge (in flight, 2026-06-18)

**Branch**: `claude/confident-thompson-y58bhe` · **Type**: docs(methodology) + 1-constant (validation);
NO schema change. Records the methodology-scientist **PATH-C** ruling (user-confirmed) on the #177
trimmed-median BEHAVIORAL flip — the honest amendment, NOT a silent relaxation.

**The decision — V55.1 condition-(2) substitution.** The behavioral flip's pre-registered validation
condition (2) — `(PBO ≤ 0.5, DSR > 0, purged-embargo holdout, non-inferiority, flip-audit)` — is
satisfied by a **forward-OOS shadow record + structural non-inferiority IN LIEU OF a synthetic
`backfill_portfolio_pit` holdout replay**, because: (a) the shipped `backtest_pit.json` is NOT
trim-replayable (stores only scalar `mos_pct` per holding, not the per-method breakdown needed to
recompute `median_trimmed` historically → the synthetic holdout would need a multi-hour networked
backfill); (b) the trim is a **frozen-threshold-inheriting estimator correctness fix** (reuses
Defense #4 `EXTREME_ESTIMATE_HIGH/LOW`, zero new tunable params), Huber-1981 even-n root cause,
enormous DSR headroom (3.07 @ n_trials=15), directionally-dominant 1-name swap (FFIV-in / BBY-out).

**Why NOT bare Path B, NOT Path A.** Path B (skip the holdout, assert structural non-inferiority) was
a SILENT relaxation — the pre-registration names the holdout + non-inferiority as CO-EQUAL
sub-elements, and dropping the only `in_sample=False` OOS block AFTER observing the lever is small +
evidence favorable is the hindsight protocol-erosion the U9 rule polices. Path A (full backfill) is
disproportionate for a 1-name swap + the 9-leg holdout is a self-described WEAK FLOOR. **Path C** =
observability-first forward OOS: the merged #496 shadow `median_trimmed` ALREADY accrues the record →
convert "asserted" non-inferiority into "measured" across live crons → flip at the **Q3 2026-08-19
cohort audit**.

**The U9 charge (anti-silent-relaxation).** The amendment is charged **+1 trial →
`BASKET_RULE_N_TRIALS` 15 → 16** (booked even though immaterial — DSR headroom is large — per
"immaterial charges still get booked"). Applied in this PR if artifact-consistency-safe, else recorded
here and applied with the Q3 flip backtest — per the compute-builder assessment.

**Q3 flip preconditions (frozen).** (1) ≥1 green sp900 cron confirming `median_trim_delta_count` holds
near 33 / 3.8% (> ~1.5× drift → re-audit root cause); (2) forward-OOS shadow non-inferiority across
crons to 2026-08-19 (trim-book vs live-book realized return, ε margin); (3) flip-ticker audit
refreshed (flips are structure-driven — may NOT stay 1 name as the universe drifts); (4) METHODOLOGY.md
"Why median, not mean" even-n correction (THIS PR); (5) a test pinning `mos_pct` derives from
`median_trimmed` (at flip time, `test-engineer`); (6) a forward AUTO-REVERT monitor (IC-decay-monitor
pattern — reverts the trim to shadow if the trim-book trails the live book by ε).

**This PR**: METHODOLOGY.md §Aggregation + §"Why median, not mean" even-n correction (Huber 1981 +
FFIV/APP examples) + `BASKET_RULE_N_TRIALS` 15→16 (U9 charge) + this amendment record. **#496 stays
shadow-only on main; live `mos_pct`/AI-pick book UNCHANGED.**

Gate: methodology-scientist PATH-C (this records its ruling) · compute-builder (constant +
artifact-consistency) · docs-reviewer (substance) · phase-coordinator Mode B.

---

## PR #498 — fix(ingest): prices.py last-bar-date recency guard — mtime-TTL dead on GHA (in flight, 2026-06-18)

**Branch**: `claude/confident-thompson-y58bhe` · **Type**: fix(ingest); compute-only, **NO schema change**,
defense layer UNCHANGED (34). Live weekly-cron behavior **BYTE-IDENTICAL when prices are fresh**.

**Root cause**: `compute/ingest/prices.py` gated price-cache freshness on file MTIME
(`age_hours < PRICES_CACHE_MAX_AGE_HOURS`). On GitHub Actions, `actions/cache` restore resets every
parquet's mtime to "now" each run → `age_hours ≈ 0` always → the TTL **never fires** → a cached frame
with stale DATA (an old last-bar date) but fresh mtime persists indefinitely. Same failure class as
the fundamentals frozen-immutable-cache gotcha (#471).

- **Fix**: added `_latest_date(df)` (last-bar sibling of `_earliest_date`) + a data-recency guard inside
  the cache-hit block — if the cached frame's LAST BAR DATE is > `PRICES_CACHE_MAX_STALE_DAYS`
  (= **7** calendar days, ≈ 5 trading + holiday buffer) old → fall through to a fresh re-download
  REGARDLESS of mtime. The mtime `age_hours` check stays as a cheap pre-filter. Byte-identical for
  ≤7-day-old caches; fail-closed (None last-bar → return cached; refetch failure → existing None).
- **NOT this PR**: the active KLAC corruption (post-split EDGAR share lag) is a SEPARATE PR (the
  `post_split_share_lag` CORRECT/veto defense, methodology-ratified HYBRID, defense 34→35). #498 only
  closes the latent prices-cache-recency gap.
- **Tests**: `test_prices_recency_guard.py` (R1-R6) + surgical `PRICES_CACHE_MAX_STALE_DAYS=999999`
  monkeypatch on 3 pre-existing tests (old-dated fixtures). ruff PASS · pytest 2027 passed.

Gate: quantrank-reviewer FUNCTIONAL-PASS (7/7 invariants; the doc-lockstep FAIL is closed by this
entry) · phase-coordinator Mode B (file-touch).

---

## PR #499 — feat(ingest+scoring+schema): `post_split_share_lag` HYBRID defense — Tier-1 CORRECT + Tier-2 veto, schema `0.10.25-phase8pilot`, defense 34→35 (in flight, 2026-06-18)

**Branch**: `claude/confident-thompson-y58bhe` · **Type**: feat(ingest+scoring+schema); **SCHEMA BUMP**
`0.10.24-phase8pilot` → `0.10.25-phase8pilot`; **defense layer 34 → 35**. Data-integrity sprint item —
the active KLAC rank-2 corruption (post-split EDGAR `shares_outstanding` lag). methodology-scientist
RATIFIED the HYBRID (CORRECT-if-high-confidence / VETO-on-mismatch); the ruling IS the gate (FP ~0,
no Mode B re-gate). LIVE RANKING CHANGE on the next cron (KLAC de-inflates).

**Root cause**: post-split price × pre-split EDGAR shares → wrong EPS / P/E / market_cap. yfinance
auto-split-adjusts prices, so the bug is ONLY in EDGAR `shares_outstanding` until the next 10-Q/10-K.

- **`compute/ingest/splits.py`** (NEW) — yfinance `.splits` fetcher, 24h cache, `QR_SKIP_SPLITS`,
  graceful-degradation → None. **`compute/config.py`**: `POST_SPLIT_WINDOW_DAYS=100`,
  `POST_SPLIT_MIN_RATIO=2.0`, `POST_SPLIT_RATIO_TOLERANCE=0.10`.
- **Detection (3 legs)**: split ≤100d · ratio ≥2× · `|yf_implied/EDGAR − ratio|/ratio ≤ 0.10`.
- **Tier-1 CORRECT** (`post_split_share_lag`, ANNOTATE): `corrected_shares = EDGAR × ratio` at
  `main.py` Step 3b BEFORE scoring → EPS/MC/value-pillar/composite recompute; raw kept in
  `RawMetrics.shares_outstanding_pre_split_raw` (Rule 9). KLAC: 130.6M → 1306M, P/E 6.68 → ~66.8.
  The Tier-1 annotate lands in `valuation_warnings` (NOT `risk_flags`) — a corrected ticker at
  rank ≤ 5 stays `entered_top5`-eligible (no double-penalty on data that is now correct; the
  Top-5 rotation gate keys on `risk_flags`).
- **Tier-2 VETO** (`post_split_share_lag_unreconciled`, DIRECT veto, the 9th): legs 1+2 fire, leg-3
  fails → `cautious` + Top-5 suppress (`_CAUTIOUS_FORCING_RISK`) + null fair-price (DQIC contract).
- **Order**: runs BEFORE DQIC (Step-3b correction de-inflates TBVPS so DQIC doesn't double-fire).
- **Leg-3 override (robustness increment, post-base, option B)**: `main.py` Step 3b passes the direct
  yfinance `sharesOutstanding` (`fetch_yfinance_shares_outstanding` — a pure cache-read priming off the
  existing `fetch_yfinance_market_cap` single `.info` round-trip; merge-write so `_exchange_cache_write`
  doesn't clobber it) as `yf_shares_outstanding_override`, so leg-3 compares share COUNTS directly
  instead of `market_cap/price` (split-adjusted-price sensitive — could degrade KLAC to a Tier-2 veto on
  a cache straddle). KLAC now lands Tier-1 CORRECT regardless of prices/info cache timing; graceful →
  `None` (QR_SKIP_CROSS_SOURCE / cold / old-format) falls back to the price path; no new external fetch;
  no schema change. Live probe: KLAC override 1306M vs EDGAR 130.6M → ratio 10.000, delta 0%.
- **Schema `0.10.25`**: `RawMetrics.shares_outstanding_pre_split_raw: float|None` + 3 `Metadata.*`
  counters (`post_split_share_lag_count` / `post_split_correction_applied_count` / `post_split_veto_count`;
  `count == applied + veto`). Frontend `types.ts` mirrored + `flag-labels.ts` 2 labels.
- **Tests**: `test_post_split_share_lag.py` (PSL1-7 + SPLITS1 + rotation-gate ROT1/2/3 + annotate-channel
  VW1/2/3 + leg-3 override LEG3_OVERRIDE1/2/3) + `test_post_split_schema.py` (5, `count == applied + veto`) +
  `test_cross_source_shares.py` (8, cache/skip/merge/backward-compat) + `test_main.py` (2 Step-3b wiring) +
  `test_config.py` pin 0.10.25 + 4 frozen-constant value-pins; 3 `test_cross_source.py` mock-target swaps
  (`_yf_info_market_cap`→`_yf_info_fetch` seam move). **Full offline suite 2079 passed** (pre-existing
  unrelated reds only: alpha158 Hypothesis DeadlineExceeded on a slow box + OSAP missing-dep collection
  errors — both green/handled on CI), ruff clean, schema_check in-sync, tsc + next build 910.

Gate: compute-builder BUILT-CLEAN · frontend-builder · test-engineer (methodology pins incl. the
before-DQIC ordering invariant + ROT/VW rotation-channel pins) · schema-sentinel (folded into
schema_check) · methodology-scientist RATIFIED HYBRID · phase-coordinator Mode B · quantrank-reviewer
(push gate — new flag + ranking change; FIX-AND-RE-REVIEW caught a Tier-1 Top-5 double-penalty →
channel-moved `post_split_share_lag` to `valuation_warnings`, re-review READY-TO-PUSH). Leg-3 override
increment (data-pipeline-engineer live-probe verified KLAC→Tier-1 / CVNA→Tier-2 dual-class / COKE→Tier-0;
compute-builder + test-engineer +13 tests; quantrank-reviewer re-review READY-TO-PUSH).
Cohort-audit band added (~0.5-2% Tier-1; <0.5% Tier-2, re-gate if >5/cron).

---

## PR (cross-source-corruption-obs) — feat(scoring+schema): cross-source share-count-corruption shadow observability, schema `0.10.26-phase8pilot` (in flight, 2026-06-19)

> **MERGED 2026-06-19** — squash `72ee8667d` (#501). Schema `0.10.26-phase8pilot` now on `main`; defense layer UNCHANGED at 35; PR-2 veto/correction wiring gated on yfinance `.splits` corroboration + methodology re-anchor Q3 2026-08-19.

**Branch**: `claude/cross-source-corruption-obs` · **Type**: feat(scoring+schema); **SCHEMA BUMP**
`0.10.25-phase8pilot` → `0.10.26-phase8pilot`; **defense layer UNCHANGED (35)**.
Methodology-scientist **RATIFIED-WITH-CONDITIONS** 2026-06-19 (per #114 audit).
**PR-1 is SHADOW ONLY** — `rankings.json` + `stocks/*.json` ranking/score/flag fields stay BYTE-IDENTICAL.
The ONLY output change is 4 new `Metadata.*` shadow fields.  PR-2 wires the veto/correction.

**Background**: `cross_source_delta = |sec_mc − yf_mc| / sec_mc` (already in `StockDetail.cross_source_delta`).
The #114 audit showed delta ≥ 50% is the corruption tail (COKE 6.07, CVNA 3.89) with structurally zero FP rate
on clean stocks (BKNG ≈0, KLAC-post-#499 ≈0).  The dual-ratio corroboration is the load-bearing guard:
COKE's yf marketCap is ALSO stale (mc_ratio≈7.07 ≠ true 10), so a bare round(mc_ratio) would infer a wrong
factor.  Both mc_ratio and share_ratio must round to the SAME integer for CORRECT_CANDIDATE.

**Changes** (`compute/**` only):
- **`compute/scoring/risk_overlay.py`** — new `CorruptionGradeResult` dataclass + `grade_cross_source_corruption()`
  pure function (NO_FIRE / CORRECT_CANDIDATE / VETO_CANDIDATE with dual-ratio corroboration) +
  `compute_cross_source_corruption_shadow()` universe aggregator. GUT-FEEL provenance label on the
  round(R) integer-recovery mechanism per methodology prior 6 (Q3 2026-08-19 follow-up).
- **`compute/config.py`** — `DELTA_CORRUPTION_THRESHOLD=0.50` (LITERATURE-ANCHORED on #114 histogram
  daylight: 95.45% <5%, corruption tail ≥50%) + `INTEGER_RATIO_TOLERANCE=POST_SPLIT_RATIO_TOLERANCE` (0.10).
  SCHEMA_VERSION bumped `0.10.25` → `0.10.26`.
- **`compute/output/schemas.py`** — 4 new `Metadata` fields (all `| None`, default None):
  `cross_source_corruption_correct_candidate_count`, `cross_source_corruption_veto_candidate_count`,
  `cross_source_corruption_ratio_disagreement_count`, `cross_source_corruption_inferred_ratio_by_ticker`.
- **`compute/main.py`** — imports `compute_cross_source_corruption_shadow`; collects yf_market_cap +
  yf_shares_outstanding as zero-cost cache-read side-channels in Step 8; aggregates after Step 8 loop
  inside a graceful-degradation try/except; writes 4 fields to Metadata.
- **`compute/ingest/splits.py`** — docstring corrected: the splits cache is NOT in any GHA bundle
  (cold-every-run live fetch is the freshness mechanism; mtime-TTL is dead under actions/cache restore,
  same class as #471/#498; bundling would freeze split detection per-quarter).
- **`frontend/lib/schema-snapshot.json`** — regenerated (schema sentinel: TS types.ts mirror NEEDED for
  the 4 new Metadata fields; they are dict-typed in Python → will be added as optional fields in TS).

**Gold fixtures**: COKE → VETO_CANDIDATE + ratio_disagreement=True (load-bearing: mc_ratio≈7.07→7 ≠ share_ratio=10→10) ·
CVNA → CORRECT_CANDIDATE inferred_ratio=5 · BKNG → NO_FIRE · KLAC → NO_FIRE. All 4 verified by python -c smoke.

**Tests**: `test_config.py::test_schema_version_pinned` updated to `0.10.26` · `test_schema_check.py::test_F1` regenerated.
Full offline suite: **2080 passed, 0 failed**. ruff clean, schema_check in-sync.

Gate: schema-sentinel (TS mirror for 4 new Metadata fields — `cross_source_corruption_*`) ·
test-engineer (shadow grading unit tests: NO_FIRE/CORRECT_CANDIDATE/VETO_CANDIDATE branches +
dual-ratio-corroboration edge + ratio_disagreement edge + missing-yf_shares fallback to VETO +
universe aggregator counts + graceful-degradation on None inputs) ·
quantrank-reviewer (push gate — schema bump; byte-identical ranking invariant; Rule 18 obs-first).

---

## PR (test) — Test-coverage hardening: splits cache + filing_text cache + feature None-propagation (in flight, 2026-06-19)

Test-only PR (no production code / schema / workflow change) closing the highest-value
coverage gaps surfaced by a `test-engineer` coverage analysis of the suite at schema
`0.10.25-phase8pilot` (rebased onto `main` past #501 + #507). Three areas, all offline-first:

- **P0 · `compute/ingest/splits.py` cache** — `tests/test_ingest/test_splits_cache.py` (new, 9
  tests). The newest defense's (`post_split_share_lag` #499) yfinance split-event fetcher had
  ZERO dedicated tests (only indirect coverage that monkeypatched `_yf_fetch_splits` out before
  the cache ran). Locks: fresh-hit-no-live-fetch · expired-TTL-refetch · corrupt-JSON graceful
  None · write/read atomic round-trip · warm-cache skips `_yf_fetch_splits` · `QR_SKIP_SPLITS=1`
  stale-present returns events / cold returns None · `[]` vs None contract. The tests exercise the
  in-process mtime-TTL code path via `os.utime()` backdating. NOTE per merged #501: the splits cache
  is NOT in any GHA bundle — it is cold-every-run live fetch in CI/cron (mtime-TTL is dead under
  `actions/cache` restore, same class as #471/#498), so these tests lock the LOCAL/in-run TTL logic,
  not a cross-run freshness guarantee.
- **P0 · orchestrator wall-clock harness — SUPERSEDED by #507, DROPPED from this PR.** The 3
  deferred `pytest.skip` wall-clock stubs in `test_wall_clock_schema.py` were implemented in
  parallel by merged #507 (`test(output): implement deferred wall-clock orchestrator tests`) using a
  full `run_weekly_compute` orchestrator harness — more robust than this PR's block-level mirror
  (which `quantrank-reviewer` flagged as a keep-in-sync brittleness). On rebase the file conflict was
  resolved by taking #507's version; this PR no longer touches `test_wall_clock_schema.py`. Net effect:
  the P0-2 invariant (form4/osap/tier2 wall-clock fields) is locked on `main` via #507.
- **P1 · `compute/ingest/filing_text.py` cache** — `tests/test_ingest/test_filing_text_cache.py`
  (new, 11 offline + 1 `@network` smoke). Previously only HTML extraction was tested; the
  `fetch_latest_10k_text` cache read/write/TTL(90d)/corrupt/`invalidate_cache`/`_ensure_edgar_identity`
  paths (the `going_concern_disclosure` Tier-2 data source) had no offline coverage. Graceful-degradation
  return value confirmed `None` on every failure path.
- **P1 · `compute/features/` None-propagation** — `tests/test_features/test_features_none_propagation.py`
  (new, 57 tests: 30 `@given` + 27 parametrized). Locks "returns finite float / nan, never raises" across
  all 27 public pillar-math functions in growth/health/profitability/quality/value; FIRST coverage for
  `quality.msci_3descriptor`; all-None snapshot (the `fundamentals_unavailable` #487 scenario) confirmed
  safe across every function. Hypothesis surfaced a subnormal-denominator `inf` (non-bug: unreachable at
  EDGAR magnitudes, and `pillars.py:_safe()` already coerces non-finite → nan before scoring).

Full offline suite green (this PR adds the splits-cache, filing_text-cache, and feature
None-propagation files; the wall-clock additions came via #507). Ruff clean. No schema triple touch
(test-only), so the schema_check / tsc / next-build rungs are N/A.

Gate: test-engineer (authored, red-green verified) — no production behavior change.

---

## PR (test) — Test-coverage hardening P2-P3: triple-flag gate + pre_split_raw writer + manipulation-index properties (in flight, 2026-06-19)

Test-only PR (no production code / schema / workflow change) — the P2-P3 follow-up to #506,
closing the remaining Python-side gaps from the `test-engineer` coverage analysis. Branched off
`main` at `8a9b5774` (post-#506/#507). +15 tests, all offline:

- **P2-1 · manipulation triple-flag joint-gate** — `tests/test_scoring/test_triple_flag_gate.py`
  (new, 6 tests). Locks the `manipulation_triple_flag` / `TRIPLE_FLAG_WEIGHT=10.0` semantics:
  all-three-co-fire reaches the documented ≥70 (Sloan+beneish_veto+dechow_veto=60 +10 gate) ·
  two-of-three does NOT reach the triple level · the gate label alone contributes exactly the
  weight · Sloan is required for gate injection. **Contract note**: the joint-gate CONDITION lives
  in `compute/main.py` Step 5 (injects the label into `valuation_warnings`); `compute_manipulation_index`
  treats it as a regular `FLAG_WEIGHTS` table entry — the tests exercise the weight-table wiring +
  the bonus math, and confirm the two-flag path has no auto-bonus.
- **P2-2 · `RawMetrics.shares_outstanding_pre_split_raw` writer round-trip** —
  `tests/test_output/test_writer.py` (+2 tests). The #499 audit-trail field survives
  `write_stock_detail` → JSON → exact float, and is null on a normal (non-split) row.
- **P3-1 · manipulation-index properties** — `tests/test_scoring/test_manipulation_index_properties.py`
  (new, 4 `@given`). Locks `compute_adjusted_composite` ∈ [0,100] · ≤ composite (penalty never
  raises) · anti-monotone in index · `compute_manipulation_index` ∈ [0,MAX_INDEX] (clip contract).
  **Contract finding (Hypothesis-caught)**: `compute_adjusted_composite` applies `round(x,2)` for
  display, so the `adjusted ≤ composite` invariant holds against `round(composite,2)`, NOT the raw
  float (e.g. 1.875 → 1.88 by banker's rounding). Callers comparing `composite_score_adjusted` vs
  raw `composite_score` directly (e.g. the frontend Manipulation Risk card) must account for it.
- **P3-2 · `fetch_benchmarks` graceful-degradation — ALREADY COVERED** by `test_benchmarks.py`
  (shipped in #506); no new tests needed.

Affected-scope suite green (manipulation index + writer + prices); ruff clean. The full offline
suite carries one PRE-EXISTING unrelated red — `test_alpha158_replicate.py::test_C1` Hypothesis
`DeadlineExceeded` (a known slow-box timing flake per §Gotchas, green on CI), untouched by this PR.
No schema triple touch (test-only), so schema_check / tsc / next-build rungs are N/A. frontend
`flagLabel` contract + vitest is a SEPARATE follow-up PR (dep-adding review path).

Gate: test-engineer (authored, red-green verified; safety-classifier was down on the subagent pass
so the orchestrator hand-verified the two new files + ruff + targeted run) — no production behavior change.

---

## PR (dividend-signal-obs) — Dividend signal PR-1: observability-first display metadata (in flight, 2026-06-19)

Roadmap item #5 / 7a. Branch `claude/dividend-signal-obs`. Schema `0.10.26-phase8pilot` →
`0.10.27-phase8pilot` (additive PATCH — optional fields, default `None`, backward-compatible
under `extra="forbid"`).

**What ships**: 3 new `StockDetail` fields (`dividend_yield_pct: float | None`,
`pays_dividend: bool | None`, `payout_ratio: float | None`) + 1 new `Metadata` field
(`dividend_coverage_pct: float | None`). All default `None`; legacy per-stock JSONs
deserialize cleanly. A new `fetch_yfinance_dividend(ticker)` function in
`compute/ingest/cross_source.py` — a pure cache-read off the existing
`yfinance_info/<ticker>.json` populated by `fetch_yfinance_market_cap` (zero new network
round-trips; dividend fields written as a side-channel of `_yf_info_fetch`). Wired into
the Step-8 per-ticker loop in `compute/main.py`; `dividend_coverage_pct` aggregated after
the loop and written to `Metadata`.

**Normalization decision**: yfinance `.info["dividendYield"]` is a fraction (0.0123 = 1.23%);
stored as `dividend_yield_pct` in PERCENT (×100). `payoutRatio` is a 0-1 fraction, stored
as-is. `pays_dividend = True iff dividend_yield_pct > 0`.

**Invariant gates**: Rankings/scores/pillar scores/risk_flags/recommendation/vetoes are
byte-identical (no scoring consumer reads the 3 new fields). Defense layer UNCHANGED at 35.
Rule 16 annotate-before-veto: N/A (not a defense flag). Rule 18 observability-before-wiring:
`dividend_coverage_pct` ships as the Metadata canary BEFORE any frontend tile wires the
display — the UI tile is a SEPARATE follow-up PR after ≥ 1 cron confirms coverage.

**Schema triple**: `compute/output/schemas.py` + `frontend/lib/types.ts` (frontend-builder mirror) +
`frontend/lib/schema-snapshot.json` (regenerated via `--update-snapshot`) — all three in lockstep
(`schema_check` in sync). `StockDetail`: `dividend_yield_pct: number | null`, `pays_dividend:
boolean | null`, `payout_ratio: number | null`; `Metadata`: `dividend_coverage_pct: number | null`.

---

## docs — S&P 900 pilot milestone reconciliation (in flight, 2026-06-19)

**Docs-only.** No code / schema / workflow touched — the verification ladder's
`schema_check` / `tsc` / `next-build` / `pytest` rungs are N/A.

Reconciles a **stale "next" pointer** that had survived the pilot's own
completion. `CLAUDE.md` §Phase status + §Next deliverables, `WORKFLOW.md`
§Phase 8 acceptance criteria, and `PHASE_STATUS.md` (Phase 8 row + Next bullet)
all still read `next = ≥ 2 green sp900 crons → frontend PR 4 (midcap badge)` —
but **both gates have since closed**:

- **frontend PR 4 (midcap badge) shipped as #490** (`feat(frontend): S&P 900
  pilot PR 4 — per-index tab cohort filter`, `3533bc596`). `MidcapChip.tsx`
  renders the "Mid-cap" badge iff `index_membership === 'sp400'` and is wired
  into `RankingTable.tsx` (rows + mobile cards), `StockListCard.tsx`, the
  per-index `RankingView.tsx` (SPX / MID / ALL tabs, chip shown only in the
  mixed ALL view), and the stock-detail page. #493 / #494 later extended the
  same tab surface with Dow 30 / NDX / Russell 1000.
- **≥ 2 green sp900 crons confirmed** — 3 green scheduled `compute-rankings.yml`
  runs since the #492 cron-default flip: 2026-06-16, 06-17, 06-18 (all
  `event=schedule`, `conclusion=success`); current production `metadata.json`
  is `universe=SP900`, `universe_size=902`.

Net effect: marks the **S&P 900 pilot milestone COMPLETE 2026-06-19** and
re-points the universe-expansion "next" at the **S&P 1500 cutover** (S&P 600
small-cap ingest + virtualized 1500-row table + Bonferroni / liquidity guards
per WORKFLOW.md §8.6). No content change to any merged-PR history entry — only
the forward-looking "next" pointers.

Gate: docs-reviewer (substance) + phase-coordinator Mode C (triple-doc
consistency). CLAUDE.md / AGENTS.md lockstep satisfied via this INFLIGHT entry
(AGENTS.md carries no Phase-8 "next" pointer — it delegates to
CLAUDE.md / PHASE_STATUS.md — so no AGENTS.md substance diff applies).

---

## PR (test+ci+fix) — frontend vitest runner + flagLabel contract test + fundamentals_unavailable label fix (in flight, 2026-06-19)

The frontend test-coverage follow-up to #506/#508 (which closed the Python-side gaps). Adds the
frontend's FIRST real test runner + a contract guard for the Python↔TS defense-flag label boundary,
and fixes a drift bug the new test surfaced. Branched off `main` post-#508.

- **vitest runner** — `frontend/package.json` adds `vitest ^2.1.9` (devDependency) + a `test:unit`
  script (`vitest run`, one-shot CI mode); new `frontend/vitest.config.ts` (node env, no jsdom — pure
  pure-function contract tests). Replaces the un-wired `downsample.test.mjs` precedent with a real
  runner. Dependency-auditor GO (dev-only, all MIT/Apache, no reachable CVE — vite/esbuild dev-server
  CVEs don't apply to `vitest run`); security-reviewer SAFE (devDep correctly scoped, never in the
  static export).
- **`flagLabel` contract test** — `frontend/lib/flag-labels.test.ts` (new, 17 tests). Guards the
  `flag-labels.ts` map (the SHARED Python-flag-string → UI-label token, AGENTS.md §Gotchas): all 9
  active-veto flag literals have an EXPLICIT curated entry (not the Title-Case fallback), representative
  annotates resolve, and the unknown-key Title-Case fallback is pinned. A Python flag rename without a
  matching map update now fails CI.
- **DRIFT FIX** — `frontend/lib/flag-labels.ts`: the test surfaced that `fundamentals_unavailable`
  (active veto since #487, schema 0.10.22+) was MISSING from `FLAG_LABELS` and fell back to Title Case
  silently. Added `fundamentals_unavailable: 'Fundamentals unavailable'` + corrected the stale header
  comment (`7 → 9 active vetoes`). UI display unchanged in practice (the fallback already read
  "Fundamentals Unavailable"); now it's a curated, rename-guarded entry.
- **CI wiring** — `.github/workflows/ci.yml`: a `Unit tests (vitest)` step (`npm run test:unit`) added
  to the `Frontend (build)` job, BEFORE the build (tests gate the build). No `permissions:` change, no
  new secret/env surface, triggers on the safe `pull_request` event (security-reviewer confirmed).

Verify: `npm run test:unit` 17/17 pass · `tsc --noEmit` clean · no schema triple touch. Gate:
frontend-builder BUILT-CLEAN · dependency-auditor GO · security-reviewer SAFE-TO-PUSH. frontend
`flagLabel`/vitest was the LAST remaining item from the test-coverage analysis — the coverage sweep
(P0-P3 Python via #506/#508 + this frontend PR) is now complete.

---

## PR (test+ci) — frontend vitest coverage expansion + hermetic CI (vitest exact-pin + npm ci) (in flight, 2026-06-19)

Follow-up to #511 (which added the vitest runner + flagLabel contract test). Two parts, frontend/CI only:

- **vitest coverage expansion** — `frontend/lib/format.test.ts` (new, 31 tests) + `frontend/lib/visual.test.ts`
  (new, 90 tests). +121 tests (total frontend now 138 incl. the 17 flag-labels). Locks the pure-function
  display layer: `format.ts` (`formatMosPct` clamps ±99/±500 + boundaries · `formatFairPrice` absurd-value
  ≥$1M + sub-penny guards · `mosColorClass` 4 tiers) and `visual.ts` (`TIERS` contiguity + dark-pair
  invariant · `getTier`/`scoreTierLabel` 5 boundaries · `MOS_BUCKETS` · `sectorStyle` all 11 GICS +
  neutral-chip-body Phase-4-A1 invariant · `scoreColorClasses`/`scoreAccentColor` · `pillarColor`
  composite-TIERS alignment §Gotchas invariant · `mosVisualFraction` · `universeLabel` ·
  `filingLagBadgeClasses`). `data.ts` skipped (all exports fs-dependent Server-Component fns; pure helpers
  are unexported). Two EDGE FINDINGS documented (not bugs, structurally unreachable from compute):
  `getMosBucket(Infinity) → null` (cheap bucket upper bound is `< Infinity`, exclusive) and `TIERS` is
  ordered highest-first so contiguity is `TIERS[i].min === TIERS[i+1].max`.
- **Hermetic CI** — `frontend/package.json` pins `vitest` `^2.1.9` → exact `2.1.9` (lockfile regenerated);
  `.github/workflows/ci.yml` Frontend job `npm install` → `npm ci` (installs strictly from the committed
  lockfile, fails on drift). Net supply-chain hardening — no new dep, no permission/secret/trigger change.

Verify: `npm ci` clean (lockfile in sync) · `npm run test:unit` 138/138 · `tsc --noEmit` clean. Gate:
frontend-builder BUILT-CLEAN · security-reviewer GO/SAFE-TO-PUSH (npm ci is a hardening improvement; vitest
pin is the same already-audited 2.1.9 from #511). No schema triple touch. No `.tsx`/UI surface touched, so
no design review needed (pure test files + dep pin + workflow verb).

---

## feat(compute): S&P 1500 cutover Slice 2 — sp1500 seam + small-cap coverage probe (in flight, 2026-06-20)

**Compute + schema + tests. Observability-first (Rule 18). Cron unchanged (stays sp900). NO sp600
ranked exposure yet.** Second slice of the S&P 1500 universe-expansion epic — wires the `sp1500`
universe seam into `compute/main.py` and ships the sp600 small-cap coverage probe so EDGAR ingest
readiness is visible before ranked production exposure is allowed.

**Rule-18 fix applied (2026-06-20, compute-builder)**: The original Slice 2 draft had a
Rule-18 violation — `universe = get_sp1500_constituents()` (including ~600 sp600 rows) flowed
straight into Step 1 (prices) → Step 2 (fundamentals) → composite scoring → JSON write with no
filter. This was corrected: the full ~1500-row frame is loaded as `_sp1500_full_frame` (probes run
on it), then sp600 rows are dropped BEFORE Step 1 so the scored/written set is sp500 + sp400 only
(≈ sp900). A second fix was applied in `derive_index_memberships` to suppress the russell1000
proxy tag for `cohort == "sp600"` (the S&P 900 ⊂ Russell 1000 structural argument does NOT hold
for S&P 600 small-caps). One test requires updating by test-engineer (see below).

What lands, pure-additive (rankings byte-identical on the sp500/sp900 cron paths):
- `compute/main.py` — (a) imports `get_sp1500_constituents`; (b) new `_run_smallcap_coverage_probe`
  function (sp600 sibling of `_run_midcap_coverage_probe`: iterates sp600 rows, calls
  `fetch_fundamentals`, counts coverage/null/CIK — sequential, cache-safe, never feeds scoring);
  (c) `elif config.QR_UNIVERSE == "sp1500":` branch at the universe-load seam → loads the full
  SP1500 frame as `_sp1500_full_frame`, runs both probes (midcap sp400 cohort stats + smallcap
  sp600 cohort stats) on the full frame, then filters out sp600 rows (`cohort != "sp600"`) BEFORE
  assigning to `universe` (the variable consumed by Step 1 onwards); merges sp600 key into
  `_pilot_cohort_sizes`; (d) new `_pilot_smallcap_*` variables (3 float|None, initialised to None
  before the probe block); (e) `universe=` label → `"SP1500-probe"` when `QR_UNIVERSE=sp1500`
  (signals probe-only run to downstream consumers — NOT the eventual `"SP1500"` label which
  requires sp600 to be scored); (f) 3 new `Metadata` keyword args wired.
- `compute/ingest/universe.py` — `derive_index_memberships`: russell1000 proxy tag now suppressed
  for `cohort in {"sp600"}` — S&P 600 small-caps sit below the Russell 1000 cutoff; the proxy
  was never valid for this cohort. (The `russell1000` code is annotate-only so Rule 16 does not
  mandate a prior annotate; suppressing an incorrect tag is a data-quality fix, not a veto.)
- `compute/output/schemas.py` — 3 additive `Metadata` fields: `smallcap_fundamentals_coverage_pct`,
  `smallcap_null_rate_pct`, `smallcap_cik_resolution_pct` (all `float | None`, detailed docstrings
  mirroring the midcap field style). Schema version bumped `0.10.26` → `0.10.27-phase8pilot`.
- `frontend/lib/types.ts` — 3 matching optional fields mirrored onto the `Metadata` TS interface.
- `frontend/lib/schema-snapshot.json` — regenerated via `--update-snapshot`.
- `compute/config.py` — SCHEMA_VERSION bump + QR_UNIVERSE comment updated to mention sp1500.
- `tests/test_ingest/test_sp1500_seam.py` — 21 offline tests (original 16 + 5 added for seam
  correctness). **One test needs updating by test-engineer**: `test_sp1500_universe_label_present_in_sp1500_branch`
  currently checks for the literal `'"SP1500"'` via source inspection — must be updated to check
  for `'"SP1500-probe"'` (and the companion error message). Also needed (test-engineer):
  - `test_sp600_rows_absent_from_universe_after_sp1500_seam` — assert `cohort="sp600"` rows not
    in `universe` after the sp1500 elif branch executes (the Rule-18 filter invariant)
  - `test_russell1000_not_tagged_for_sp600_cohort` — assert `derive_index_memberships` does NOT
    include `"russell1000"` when `cohort="sp600"`, regardless of market_cap value
  - `test_russell1000_tagged_for_sp500_sp400_cohorts` — regression: sp500/sp400 still get
    `"russell1000"` when market_cap > 0

Verify: `ruff check .` clean · `pytest -m "not network"` 2235 passed / 3 failed (2 pre-existing:
`test_C1_accounting_equation_holds_for_all_inputs` + `test_R6_boundary_exact_threshold`; 1 test
needing test-engineer update: `test_sp1500_universe_label_present_in_sp1500_branch`) ·
`schema_check` in-sync · `tsc --noEmit` clean. Gate: compute-builder BUILT-CLEAN →
test-engineer (label fix + 3 new coverage tests) → quantrank-reviewer (pending) →
schema-sentinel (schema triple touched). Staging context: Slice 2 of 8 (seam+probe →
3 Bonferroni-shadow ∥ 4 ADV-guard ∥ 6 SML-tab → 5 precache v11 → 7 cron flip → 8 v2.0).

---

## feat(ingest) — S&P 1500 cutover Slice 1: S&P 600 fetcher + S&P 1500 loader (in flight, 2026-06-19)

**Compute ingest only.** No schema triple, no `compute/main.py` wiring, no workflow change — the
`schema_check` / `tsc` / `next-build` rungs are N/A. First slice of the **S&P 1500 universe-expansion
epic** (the next universe step after the S&P 900 pilot milestone closed #510). Mirrors the proven
sp900 ingest ladder (`fetch_sp400_constituents` / `get_sp900_constituents`).

Adds, pure-additive with **no production caller yet** (the `sp1500` universe seam in `main.py` is
Slice 2):
- `compute/ingest/universe.py` — `_parse_sp600_html` (mirrors `_parse_sp400_html`: Symbol/Ticker
  column variants, dot→dash normalize, CIK zero-pad, sector fallback), `fetch_sp600_constituents`
  (Wikipedia + parquet cache + graceful-degradation try/except → empty DataFrame, never raises into
  the cron), `get_sp1500_constituents` (concats sp500+sp400+sp600, tags `cohort`, dedup keeps the
  larger-cap cohort on collision, runs the CIK-resolution loop; ~1500 rows).
- `compute/config.py` — `WIKIPEDIA_SP600_URL`, `SP600_UNIVERSE_CACHE` (`universe_sp600-v1.parquet`),
  `SP1500_UNIVERSE_CACHE` (`universe_sp1500-v1.parquet`), `SP600_CACHE_MAX_AGE_DAYS`.
- `tests/test_ingest/test_universe_sp1500.py` — 33 tests (32 offline + 1 `@network` Wikipedia smoke):
  parser column/CIK/dedup/malformed-HTML paths, fetch cache + graceful-degradation, loader
  cohort-tag + cross-cohort dedup + CIK-resolution-call assertions.

Verify: `ruff check .` clean · `pytest -m "not network"` 460 passed / new file 32/32 offline green ·
no schema touch. Gate: compute-builder BUILT-CLEAN → quantrank-reviewer (pending). Staging context:
Slice 1 of 8 (1 fetcher → 2 seam+probe → 3 Bonferroni-shadow ∥ 4 ADV-guard ∥ 6 SML-tab → 5 precache
v11 → 7 cron flip → 8 v2.0). WORKFLOW §8.3 react-virtual note found OBSOLETE (RankingTable paginates
50 rows/page — 1500 rows need no virtualization).

---

## PR (fix) — test_R6 prices-recency boundary: weekend-robust last-bar pin (in flight, 2026-06-19)

Test-only fix. `tests/test_ingest/test_prices_recency_guard.py::test_R6_boundary_exact_threshold`
failed every weekend/holiday and was actively red on `main` (2026-06-20 Sat) — blocking CI on ALL
open PRs (CI runs the full `pytest -v`). Root cause is in the TEST, not the #498 guard: the boundary
frames were built with `pd.bdate_range(end=today-7)`, which snaps a weekend `end` back to the prior
Friday, so `today-7` on a Saturday became `today-8` → `calendar_days_stale` flipped 7→8 → the strict
`>` edge tripped a spurious refetch → assertion failure. The production recency guard (`prices.py`,
`PRICES_CACHE_MAX_STALE_DAYS=7`) is CORRECT.

Fix: new test helper `_frame_last_bar_on(end, periods)` that builds via `_bday_frame` then pins the
final index entry to exactly `end` (any weekday), used for R6 sub-cases A (today-7) and B (today-8).
Boundary is now exact regardless of which day the suite runs. No production code touched.

Verify: `pytest tests/test_ingest/test_prices_recency_guard.py` 6/6 · ruff clean. Gate: orchestrator
hand-fix (confirmed pre-existing on clean origin/main, weekend date-boundary). Discovered while
building the pytest-cov coverage PR; split out as a standalone unblock.

---

## PR #521 — chore(ui): design-kit alignment polish pass (in flight, 2026-06-20)

Frontend-only polish PR aligning 15 live components to the idealized design kit
(`/tmp/qr_design/quantrank-design-system/`). No schema bump, no schema-triple touch,
no defense-layer change, no new feature added or removed — pure visual alignment.

Changes (all `frontend/**` only):
- **AppShell.tsx**: footer dark bg `dark:bg-slate-950` → `dark:bg-slate-900` (kit
  `--surface` dark = slate-900); header chrome row `h-14` → `h-[52px] sm:h-14` (kit
  mobile 52px / desktop 56px).
- **Chip.tsx**: `CHIP_SIZES.xs` adds `h-[18px]`; `CHIP_SIZES.sm` adds `h-5` — makes
  explicit the kit's 18/20px heights (was height-by-content).
- **lib/visual.ts** + **ScoreBadge.tsx**: retire the last solid emerald-600 fill (score
  ≥80); all score tiers now use the kit's outlined-light emerald tint. Heat dot always
  renders at every tier; Exceptional vs Strong distinguished by the darker accent color
  (rgb(5 150 105) vs rgb(16 185 129)).
- **ScoreGauge.tsx**: side-label value changed from `shown.toFixed(0)}/100` → the
  STATIC `score.toFixed(1)` (no "/100" suffix — kit shows 1-decimal without the
  denominator; the count-up animation lives only in the donut-center integer, kit
  alignment). "Composite Score" label text kept (more explicit than kit's bare
  "Composite").
- **MoSBadge.tsx**: remove visible `(vs fair value)` parenthetical span from the side
  label in both branches; SR `aria-label` already says "versus fair value" — stays intact.
- **RecommendationBadge.tsx**: `bullish` tone `text-emerald-900` → `text-emerald-800`
  (mapped in globals.css allowlist); `cautious` tone `text-red-900` → `text-rose-800`
  (mapped → `var(--c-neg-strong)`). Neither `text-emerald-900` nor `text-red-900` were
  on the soft-color allowlist.
- **LossChanceBadge.tsx**: High band `text-red-900` → `text-rose-800` and Low band
  `text-emerald-900` → `text-emerald-800` (same allowlist fix — both were un-mapped).
- **HeroAttributeTiles.tsx**: tile padding `p-3` → `p-4` (kit `--space-md` = 16px);
  dark bg `dark:bg-slate-800/40` → `dark:bg-slate-800` (kit solid `--surface-alt` dark).
- **PillarRadarChart.tsx**: bar track `h-5` → `h-[14px]`; fill inset `inset-y-0.5` →
  `inset-y-[1px]`; pillar value `text-sm` → `text-base`; label column `8rem` → `9.5rem`;
  legend row gains `border-t border-slate-200 dark:border-slate-800 pt-3` top divider.
- **FairPriceCard.tsx**: `<dd>` values `text-lg` → `text-xl`; `<dt>` labels `text-xs
  tracking-wider` → `text-[0.5625rem] tracking-[0.08em]`; card bg `bg-slate-50/60
  dark:bg-slate-900/40` → `bg-slate-50 dark:bg-slate-800`.
- **FairPriceBarChart.tsx**: verdict banner headline `text-lg font-semibold` →
  `font-slab text-lg font-semibold` (kit uses `var(--font-slab)` for this label).
- **RankingTable.tsx**: `<thead>` label size `text-xs` → `text-[0.625rem]`; rank `<td>`
  adds `font-mono`; empty-state icon `h-8 w-8` → `h-6 w-6`.
- **StockListCard.tsx**: price number and loss-chance number `text-base` →
  `text-[0.8125rem]` (kit 13px supporting data). Day-change chip treatment kept (live
  exceeds kit; not downgraded).
- **app/stock/[ticker]/page.tsx**: hero ticker `text-4xl sm:text-5xl` → `text-[2rem]
  sm:text-[2.5rem]`; company name `text-2xl sm:text-3xl` → `text-xl sm:text-2xl`.
  Container-query hero-split classes untouched.
- **HeroMetric.tsx**: label `tracking-wider` → `tracking-[0.08em]` (kit small-caption
  register 0.08em).

- **lib/visual.test.ts**: updated the `scoreColorClasses(80)` assertion to expect the
  new outlined-light emerald tint (solid fill retired) instead of `bg-emerald-600`/`text-white`.

Verify: `tsc --noEmit` clean · `next build` clean (910 static pages) ·
`vitest run` 138/138 passed (visual + format + flag-labels) · `downsample.test.mjs`
14/14 passed · schema triple untouched · defense layer unchanged.

---

## PR #517 — feat(frontend): Vercel Web Analytics integration (in flight, 2026-06-20)

**Frontend-only, no schema/compute touch.** Adds `@vercel/analytics@^2.0.1`
(MIT, 0 runtime transitive deps, small unpacked footprint, locked `2.0.1`) and renders
`<Analytics />` in `frontend/app/layout.tsx` after the ThemeProvider; also
adds `frontend/.eslintrc.json` (`extends: next/core-web-vitals`). Originated
as duplicate bot PRs #516 + #517 from `vercel[bot]`; **#516 closed as a
duplicate**, #517 (the superset — it carries the `.eslintrc.json`) is the
surviving PR.

Reviews: `dependency-auditor` GO-WITH-NOTES (clean license/CVE/footprint;
`--legacy-peer-deps` masks an OPTIONAL+unused SvelteKit peer chain — runtime
identical; CI `Frontend (build)` confirmed green so `npm ci` accepts the lock).
`security-reviewer` GO-WITH-NOTES (no secrets/env/workflow/schema; telemetry is
cookieless, no IP storage, no PII, Vercel-edge-served not third-party CDN).

The ONE FAIL was process, now resolved by this doc-lockstep commit: the
`AGENTS.md` §Security pledge "no telemetry … no analytics in v1.0" directly
contradicted the change. Per explicit owner decision (2026-06-20) the pledge is
**lifted** — `AGENTS.md` §Security + `CLAUDE.md` §Frontend rendering updated to
record Vercel Web Analytics as the one sanctioned cookieless beacon. Defense
layer UNCHANGED (35); no schema bump.

Follow-ups (not blocking merge): (1) enable Web Analytics in the Vercel
dashboard or `<Analytics />` 404s silently; (2) optional one-line privacy note
in the `Disclaimer` component; (3) `.eslintrc.json` makes `next build` enforce
core-web-vitals — no current violations found. Branch rebased onto `origin/main`
so it carries the #515 test_R6 weekend-boundary fix (the `test_R6` red that hit
the pre-rebase base `08a74c09` is resolved on the rebased tip).

---

## PR (Speed Insights) — feat(frontend): Vercel Speed Insights integration (in flight, 2026-06-20)

**Frontend-only, no schema/compute touch.** Companion to #517 (Web Analytics).
Adds `@vercel/speed-insights@^2.0.0` (Apache-2.0, framework-optimized for Next.js,
no novel transitive deps beyond the package itself) and renders
`<SpeedInsights />` in `frontend/app/layout.tsx` (after the ThemeProvider/AppShell
block, alongside where #517 places `<Analytics />`). Speed Insights tracks Core
Web Vitals (LCP/CLS/INP/TTFB/FCP); Web Analytics (#517) tracks page views — the
two are siblings. `npm install --legacy-peer-deps` (same optional-peer chain as
#517). Beacon posts to Vercel-edge `/_vercel/speed-insights/`, renders null,
static-export-safe (Suspense-wrapped `/next` entry).

Doc-lockstep: `AGENTS.md` §Security + `CLAUDE.md` §Frontend rendering updated to
the TWO-beacon end state (Web Analytics + Speed Insights, both cookieless,
no IP, Vercel-edge). Defense layer UNCHANGED (35); no schema bump.

Verify (frontend-builder BUILT-CLEAN): `tsc --noEmit` clean · `next build` 910
static pages pass (output: export unaffected). Gate (quantrank-reviewer +
phase-coordinator Mode B + dependency/security) runs at Draft→Ready.

Parallel-PR note: branch is off `origin/main` (pre-#517 merge), so the AGENTS.md
pledge + CLAUDE.md note overlap #517's same-line edits. When #517 merges first,
rebase resolves the shared-line conflict "keep the two-beacon version"; the
PHASE_STATUS_INFLIGHT append is collision-free by design.

Follow-up (not blocking merge): enable Speed Insights in the Vercel dashboard
(Settings → Speed Insights) or `<SpeedInsights />` 404s silently.

---

## PR (test+tooling) — pytest-cov coverage tooling + P-low coverage tests (in flight, 2026-06-20)

Adds the project's FIRST real coverage measurement + closes the remaining P-low Python gaps from the
test-coverage analysis. Test/tooling only — no production code, schema, or workflow logic touched.
Coverage runs ON-DEMAND via `pytest --cov=compute --cov-report=term-missing` (the pyproject config makes
it work); it is deliberately NOT folded into the blocking CI `pytest` step — coverage instrumentation
~2x's full-suite runtime (12→24 min) and that slowdown tipped the pre-existing `test_alpha158_replicate`
Hypothesis `deadline=4000` property test over its per-example budget. Tooling without the CI-time tax.

- **pytest-cov tooling** — `pyproject.toml`: `pytest-cov>=6.0,<7` added to `[dev]` + `[tool.coverage.run]`
  (`source=["compute"]`, `branch=true`, omit tests/`__init__`/optional-extra modules osap·qlib·jkp·ml) +
  `[tool.coverage.report]` (`show_missing`, standard `exclude_lines`). **No `--cov-fail-under` gate**
  (baseline-first; a hard gate could red CI before we know the floor). **Baseline measured: 85% statement**
  (6937/8160). 10 lowest modules are the network/optional-dep fetch layers (osap 11%, filing_text 49%,
  restatement_filings 58%, …) — expected (offline suite can't reach live-fetch paths).
- **P-low coverage tests (+22)** — `tests/test_scoring/test_risk_overlay_coverage.py` (11: defense-#35
  graceful-degradation branches — `fetch_splits` None → tier0, future-dated split skip, legs-1+2-hold →
  Tier-2 veto, Sloan zero-total-assets NaN guard, `_shares_at_lookback` None/NaN/negative/non-castable
  guards) lifts risk_overlay 95→97% · `tests/test_valuation/test_applicability_coverage.py` (10:
  `_finite_positive` edge cases + ev_ebitda peer-median gate) lifts applicability 96→100% ·
  `tests/test_main.py` (+1: `test_step4_sectors_dict_passed_to_compute_risk_flags` — the P-low orchestrator
  gap, locks Step-4 sector-map construction + verbatim forward to `compute_risk_flags`).
- **Finding (documented, NOT patched — user disposition: document-only)**: `_finite_positive(math.inf)`
  returns `True` despite the "finite" docstring (no `math.isfinite` guard). Zero production impact — peer
  EV/EBITDA medians from real S&P data cannot be infinite. Behavior pinned in
  `test_finite_positive_infinity_behavior` so a future change surfaces; docstring-vs-impl gap left for a
  separate disposition if ever desired.

Verify: `ruff check .` clean · `pytest -m "not network"` green (the pre-existing test_R6 weekend flake was
fixed first in #515; the alpha158 `test_C1` Hypothesis DeadlineExceeded remains a known slow-box flake,
green on CI). Gate: test-engineer (authored). No schema triple touch.
---
## ci(precache) — S&P 1500 cutover Slice 5: cache-v11-fast bump + sp1500 dispatch + sp600/sp1500 parquet paths (in flight, 2026-06-20)

**Workflow YAML + cache-coverage test only.** No compute code change. No schema triple touched.
Off-cycle precache prep — enables the precache and cron workflows to COLD-SEED and WARM the
+600 small-cap cohort. The **cron default stays `sp900`** — the cron-default flip to `sp1500`
is Slice 7, NOT this slice.

Changes (4 workflow files + 1 test file):

- `.github/workflows/precache-edgar.yml` — adds `sp1500` to the `universe` dispatch `choice` list
  (as a manual-dispatch option for cold-seeding, NOT as the scheduled default); adds
  `universe_sp600-v1.parquet` + `universe_sp1500-v1.parquet` to the fast-bundle `path:` block;
  bumps `cache-v10-fast` → `cache-v11-fast` with an explanatory YAML comment.
- `.github/workflows/compute-rankings.yml` — same `sp1500` choice addition + same parquet additions
  + same key bump; adds v11 to the bump-history comment in the fast-cache step.
- `.github/workflows/pre-merge-prod-sim.yml` — fast-bundle restore path + key bumped to v11 in
  lockstep (the sim must mirror the cron's key family or goes cold on every PR run after archive
  eviction — the run #98 precedent). Cron default still `QR_UNIVERSE: sp900`.
- `.github/workflows/backfill-portfolio.yml` — fast-bundle restore path + `cache-v10-bf-` →
  `cache-v11-bf-` + restore-keys bumped to `cache-v11-fast-` in lockstep.
- `tests/test_workflow_cache_coverage.py` — extends `_REQUIRED_CACHE_PATHS` with
  `config.SP600_UNIVERSE_CACHE` + `config.SP1500_UNIVERSE_CACHE`; updates
  `test_workflow_fast_cache_key_full_shape_pinned` + `test_workflow_fast_cache_key_is_v11`
  (renamed from `_is_v10`) + `test_sim_restores_both_cron_cache_families` +
  `test_sp900_universe_parquets_in_fast_path_blocks` to cover sp600/sp1500 and expect v11;
  adds `- sp1500` choice assertion to `test_compute_rankings_has_universe_dispatch_input` +
  `test_precache_has_universe_dispatch_input`.

**WHY the key bump is required:** the fast bundle's exact-quarter-key save-skip means sp600
fundamentals/prices written under a warm v10 sp900 key would be silently dropped (save skipped
on an exact-key hit — the FROZEN-IMMUTABLE-within-a-quarter gotcha). The v11 bump forces a
cold-seed of the new paths on the first post-bump cron so all ~1500 tickers warm correctly once
the sp1500 dispatch or Slice 7 cron-default flip fires. Identical mechanism to the v9→v10 bump
(precache-900 Phase B, #492). Do NOT bump the slow-text bundle key — it is run-id-keyed and
always saves.

**PREP PR gating note:** this PR is designed to MERGE AFTER Slice 2 (the sp1500 `main.py` seam +
universe probe) lands on main, not before. Merging before Slice 2 would allow a manual
`universe: sp1500` dispatch that fails silently because `main.py` does not yet route that value.
The two-bundle cache split remains intact; `timeout-minutes` is NOT lowered (cold-1500 risk noted
in YAML comments only).

Verify: `ruff check .` clean · `pytest tests/test_workflow_cache_coverage.py` 37/37 green ·
`pytest -m "not network"` 2220 passed (1 pre-existing unrelated failure:
`test_R6_boundary_exact_threshold` in `test_prices_recency_guard.py`) · YAML valid (Python
`yaml.safe_load` on all 4 files) · zero `cache-v10-fast` occurrences remaining in workflow files.

---

## feat(ui): design-handoff structural gap-fill — Stock-detail · Home · Ranking (in flight, PR #523)

Branch `claude/redesign-preserve-details-q80fq8` → **PR #523**. Follow-up
to #521 (token/proportion polish pass): #521 aligned 15 components to the
QuantRank design kit at the token level but explicitly added/removed no
feature, so the handoff's STRUCTURAL refinements were out of its scope.
This series adds those remaining refinements WITHOUT removing any
existing detail ("redesign โดยไม่ลดทอนรายละเอียดเดิม"). Scope = the three
signature surfaces (Stock detail · Home · Ranking), delivered as ONE PR
(#523) with a separate commit per surface (the session's branch
constraint kept all work on this branch rather than a branch-per-surface).

PR-1 = **Stock detail**. Audit finding: 4 of 5 handoff refinements were
already present post-#521 (fair-price per-method plain-English list in
`FairPriceBarChart`, pillar sublabel/tier/median-tick/axis/legend in
`PillarRadarChart`, attribute tiles in `HeroAttributeTiles`, brand polish
across `ListingChips`/`Chip`). The one genuine gap was the standing
defense-layer caution callout the handoff `StockDetailScreen` renders
below the forensic-screen card — added here.

- **DefenseLayerNote.tsx** (NEW): standing amber soft-band caution
  ("Defense layer. Flags mark elevated risk, never confirmed fraud…").
  `TriangleAlert` lucide named import, strokeWidth 1.75; 1px ring + 4px
  radius (borders carry depth, no shadow); paired light/dark
  (amber-50 / amber-900-30, amber-200 / amber-800 ring); honest-voice
  verbatim copy. Pure presentational server component.
- **app/stock/[ticker]/page.tsx**: render `<DefenseLayerNote />` UNGATED
  between the valuation zone and the Supporting-data drawer; rides the
  article's default 16px rhythm (no new `!mt-8` seam). +1 import.

PR-1 also dropped the callout's redundant inset ring (single 1px border,
matching the page's own amber detail-pending fallback) per a
frontend-design-reviewer WARN.

**Surface 2 = Home (AI-pick backtest).** Additive handoff refinements —
no feature/data removed:
- **AiPickPortfolio.tsx**: Outperformance hero figure (AI net − benchmark,
  `font-mono tabular-nums`, sage tone via `toneClass`, gated on both inputs
  non-null); per-row buy/hold action dot keyed to the existing `isCarried`
  state (sage = new buy / steel = held; adaptive branch only — the slider
  branch has no carried signal, not mocked); "View the full ranking"
  primary CTA + educational caveat footer row; Current-picks + Calendar-year
  returns 2-col grid on `md+` (stacks on mobile).
- **SegmentedSelector.tsx**: opt-in `variant="primary"` (emerald-fill active
  segment); default `subtle` preserved — only call sites are
  AiPickPortfolio's 4. **BacktestValidationBadge.tsx**: section label →
  "Validation gates · how we know it isn't luck".

**Surface 3 = Ranking** (incl. an AUTHORIZED re-introduction of the
previously-removed filter screener — explicit user sign-off):
- **RankingView.tsx**: same-row h1 + "N / M stocks" count + Filters button
  (R-8); visible sort-chip row (Rank · Score · Loss chance, R-3) bound to a
  lifted sort state shared 1:1 with RankingTable's column headers; sectors
  for the drawer derived from REAL cohort rows.
- **FilterDrawer.tsx** (NEW) + **Switch.tsx** (NEW): the one floating-overlay
  surface (`shadow-xl`), focus-trapped + Escape/backdrop close + focus
  restore + `aria-modal`; Signal switches (`role="switch"`, 44px,
  reduced-motion guard) + multi-select sector chips (outlined-light pattern)
  + draft-state Apply/Reset. Committed filters (MoS ≥ 0 / composite ≥ 55 /
  sector) feed `filteredRows` UPSTREAM of search.
- **RankingTable.tsx**: optional controlled sort props (backward-compatible
  standalone fallback) + `loss_chance_pct` added to `SortKey`; filter-aware
  empty state (Clear search + Clear filters); page-reset on filter change;
  FLIP reshuffle stays search-scoped. **globals.css** + **tailwind.config.ts**:
  `drawer-in`/`scrim-in` keyframes (transform+opacity, ≤320ms,
  reduced-motion off-switch).

No schema-triple touch · defense layer unchanged · no dependency added ·
no existing feature removed (Ranking filters are an authorized RE-add, not a
removal). Verify (all three surfaces): `tsc --noEmit` clean · `next build`
clean (910 pages).

---

---

## PR (test) — offline coverage for the PIT parquet readers (historical_8k + historical_sector) (in flight, 2026-06-20)

Test-only follow-up to the #518 coverage baseline (85%). Lifts the two PIT-parquet ingest readers'
`_load_parquet` present/cache/corrupt branches + the parquet-hit / fallback paths — uncovered offline
because the `data/*.parquet` files don't ship in the repo. Both modules' tests point the module path
constant at a `tmp_path` parquet (+ reset the mtime cache, + stub the Wikipedia fallback) so every
branch runs offline with NO network and NO real `data/` file.

- **`compute/ingest/historical_8k.py` 63% → 88%** — `tests/test_ingest/test_historical_8k_parquet.py`
  (new, 9 tests): `_load_parquet` present-read + mtime-cache-hit + absent + corrupt-file graceful None ·
  `item402_filings_for` present-parquet filter/sort/shape + absent → `[]` · `item402_parquet_row_count`
  present/absent · `_accession_to_url` leading-zero strip + all-zero CIK segment.
- **`compute/ingest/historical_sector.py` 60% → 90%** — `tests/test_ingest/test_historical_sector_parquet.py`
  (new, 10 tests): `_load_parquet` present/cache/absent/corrupt · `sector_at` parquet-hit closest-prior ·
  parquet-present-no-prior-row → today's-sector fallback · absent → fallback · fallback-miss → `"Unknown"` ·
  raising-fallback swallowed → `"Unknown"` · `historical_sector_parquet_stats` present (rows + unique dates)
  / absent.

Remaining uncovered in both = the hard-to-reach defensive `except` guards (stat `OSError`, `itertuples`/
`idxmax`/`len` raising on a well-formed frame) — left as defensive belt-and-suspenders. Universe-scrape
parsing coverage (`universe.py` 80%) deferred to a separate follow-up (larger surface).

Verify: `ruff` clean · `pytest tests/test_ingest -m "not network"` 487 passed (+19, 0 regressions; only the
known optional-`[factors]` osap collection error remains). No production code / schema / workflow touched.
Gate: orchestrator-authored inline (sub-agent pool was rate-limited).

---

## PR (test) — offline coverage for universe.py Wikipedia-scrape parsing (in flight, 2026-06-20)

Test-only follow-up in the coverage sweep (after #518 baseline 85%, #525 PIT parquet readers). Lifts
`compute/ingest/universe.py` (the S&P 500/400/600/900/1500 + Dow30/NDX constituent scrape/loader) from
**80% → 93%** (+13 pp) by exercising the PURE parsing / normalization / cache branches offline — the
actual `requests.get` / `pd.read_html` fetch stays network-gated; tests monkeypatch the fetch boundary
and feed synthetic wikitable HTML / cache fixtures.

`tests/test_ingest/test_universe_parsing.py` (new, **+42 tests**, 13 classes): sp500/sp400/sp600 parse
errors (no wikitable / missing Symbol / missing CIK → ValueError) + sub_industry mapping + name→ticker
fallback + `_safe_cik` non-numeric → None · fetch_sp400/sp600/dow30/ndx cache-hit / force-refresh /
parquet-or-JSON write / write-OSError-non-fatal / corrupt-JSON-re-fetch · get_sp900/sp1500 CIK-resolution
success+failure (unresolved → None, no crash) + sp1500 cache-hit skips the three constituent fetchers ·
dow30/ndx multi-table fallthrough + skip-table-without-Symbol · `_normalize_ticker` strip/upper/dot-to-dash.

**No real bug found.** One structural note (NOT patched): lines 199 & 481 (`if "wiki_ticker" not in
df.columns`) are defensive DEAD CODE — unreachable given the col-map loop only runs after the
symbol/ticker guard always maps that column. Harmless; flagged so a future reader doesn't mistake it for
a reachable error path. Remaining ~27 uncovered lines are network-only (`_fetch_wikipedia_html` body,
`_resolve_cik_for_midcap` edgar import, `pd.read_html` raise-continue) + branch-arc partials.

Verify: `ruff` clean · `pytest tests/test_ingest -m "not network"` 554 passed (+42, 0 regressions; only the
known optional-`[factors]` osap collection error remains). No production code / schema / workflow touched.
Gate: test-engineer authored.

---
---
---

## PR #TBD — S&P 1500 Slice 4: low_liquidity ADV annotate (defense 36, obs-first, 0.10.29-phase8pilot) (in flight, 2026-06-20)

Ships the `<$5M ADV liquidity backstop` (WORKFLOW.md §8.6) for the S&P 1500
cutover as an **ANNOTATE-ONLY** flag per Rule 16 (portable-annotate-before-veto)
+ Rule 18 (observability-before-wiring).  Rankings and composite scores are
byte-identical; no `cautious`, no Top-5 suppression, no fair-price null, no
composite change.  Veto promotion is gated on ≥ 1 cron of firing-rate data +
methodology ratification.

**Academic anchor**: Amihud 2002 *J. Financial Markets* §2 — trailing-30-day
mean dollar volume < $5M places a stock in the bottom decile of the US-equity
Amihud illiquidity measure; microstructure noise dominates any fundamental signal
at that scale.  Expected base rate for S&P 900: near-zero (large-caps all clear
$5M/day comfortably); the flag is designed for S&P 1500 small-cap exposure where
thinly-traded names may appear.

**Schema bump**: `0.10.28-phase8pilot` → `0.10.29-phase8pilot` (additive PATCH;
backward-compatible — all new fields default to `None`/`0`).

**New fields** (all additive; legacy snapshots deserialize cleanly under
`extra="forbid"`):
- `StockDetail.average_dollar_volume: float | None` — trailing-30d mean of
  (close × volume) in USD.  Sourced from the existing OHLCV price cache in the
  Step-1 prices loop; zero new network round-trips.  Graceful degradation to
  `None` when price DataFrame unavailable or missing Close/Volume column.
- `Metadata.low_liquidity_annotate_count: int | None` — universe-wide count of
  tickers where the `low_liquidity` annotate fired on this cron run.

**New compute module**: `compute.ingest.prices.compute_average_dollar_volume` —
pure function; never raises; returns `None` on any failure (Rule 18).

**New constants** (config.py): `ADV_FLOOR_USD = 5_000_000.0` + `ADV_LOOKBACK_DAYS = 30`.

**New annotate flag**: `low_liquidity` emitted to `valuation_warnings` (NOT
`risk_flags`) in the per-ticker Step-8 loop — placed in `valuation_warnings`
following the same convention as `post_split_share_lag`, `share_count_extraction_missing`,
`goodwill_heavy`, etc.  This placement is load-bearing for the annotate-only
invariant: `valuation_warnings` is NOT checked by the Top-5 rotation skip
(`if risk_flags.get(ticker): continue` in Step 7).

**New flag label**: `frontend/lib/flag-labels.ts` → `low_liquidity: 'Low liquidity (<$5M ADV)'`.

**Schema triple**: all three parts updated in lockstep — `compute/output/schemas.py` +
`frontend/lib/types.ts` + `frontend/lib/schema-snapshot.json` (regenerated;
`python -m compute.output.schema_check` passes).

**Verify**: `ruff check .` clean · `pytest -m "not network"` 2287 passed, 0 failed ·
`schema_check` in sync · `tsc --noEmit` pre-existing failures only (missing `node_modules`
in worktree; no new TS errors from this PR).

**Defense layer**: 35 → **36** declared boolean flags (27 annotates incl. `low_liquidity`,
9 active vetoes; ~29 emit now).

**Follow-up gate** (not in this PR): veto promotion requires ≥ 1 cron of
`Metadata.low_liquidity_annotate_count` firing-rate data + methodology-scientist
ratification per WORKFLOW.md §8.6.  Expected approval path: Q3 2026-08-19
cohort audit if the S&P 1500 small-cap expansion (Slice 3+) is underway by then.

---

## docs(phase-status) — Mode C: reconcile trackers to 0.10.29 (S&P 1500 Slices 2/4/5, defense 36) (in flight, 2026-06-20)

**Branch**: `claude/mode-c-sp1500-slices-2-4` · **Type**: docs-only (no code /
schema / workflow touched).

**Why**: the canonical doc trackers had drifted behind `main` — `config.py`
read `0.10.29-phase8pilot` (#527 merged) while CLAUDE.md §Phase status,
AGENTS.md schema line, SKILL.md schema-version table, and PHASE_STATUS.md
§Current state still showed `0.10.27` / defense **35**.  The last tracker
sweep (#524, 2026-06-20 reconcile to 0.10.27) and #526 (no-schema-bump sweep
covering #514/#515/#518/#521) did not fold the three S&P 1500 cutover slices
that bumped the schema (#519 → 0.10.28, #527 → 0.10.29) or the no-bump
precache slice (#520).

**What this Mode C folds in** (S&P 1500 cutover epic):
- **#519** (squash `5e49dca0a`) — Slice 2: `sp1500` universe seam +
  `_run_smallcap_coverage_probe`; 3 additive `Metadata.smallcap_*` fields;
  sp600 PROBE-ONLY (label `SP1500-probe`, NOT ranked); WORKFLOW.md §8.6
  Beneish Bonferroni sign-fix (−2.22→−2.50) + Slice 3 (Bonferroni shadow)
  DEFERRED to Slice-8; schema `0.10.27` → **`0.10.28-phase8pilot`**; defense
  UNCHANGED at 35.
- **#520** (squash `b2bffde3e`) — Slice 5: `cache-v10-fast` → `cache-v11-fast`
  precache cold-seed across 4 workflows + `sp1500` dispatch + sp600/sp1500
  parquet paths; cron default UNCHANGED (stays sp900); NO schema bump.
- **#527** (squash `2e45a33bf`) — Slice 4: `low_liquidity` ANNOTATE flag
  (<$5M ADV, Amihud 2002; rank-neutral — `valuation_warnings`, not
  `risk_flags`) + `compute_average_dollar_volume()` + `StockDetail.average_dollar_volume`
  + `Metadata.low_liquidity_annotate_count`; schema `0.10.28` →
  **`0.10.29-phase8pilot`**; **defense 35 → 36** (new annotate); dormant on
  sp900, lights up on sp600; methodology RATIFY-SHADOW.
- **#525** / **#528** — offline coverage tests (PIT parquet readers /
  `universe.py` scrape parsing); no schema / defense touch.

**Defense-layer accounting**: 35 → **36** = the new `low_liquidity` annotate
(9 active vetoes UNCHANGED; annotates 26 → 27).

**Files changed** (docs only): `CLAUDE.md` (§Scoring model defense count,
§Phase status current-schema + defense + merged-since list + next-universe-step
notes, §Gotchas +3 entries) · `AGENTS.md` (schema-version line) · `SKILL.md`
(schema-version table +2 rows) · `PHASE_STATUS.md` (§Current state schema +
defense rows, Phase 8 row, +1 chronological section) · this file.

**Verify**: no code/test/schema/workflow files touched → ruff / pytest /
schema_check N/A; `git diff --stat` confirms docs-only.  CLAUDE.md + AGENTS.md
moved in lockstep (the "ship with every PR" rule).

**Next**: open as Draft, `quantrank-reviewer` + `docs-reviewer` at the push
gate, then user-authorized Mark-Ready (no push / no PR from this session per
the handoff).

---

## PR (test) — offline coverage for the EDGAR-fetch scoring modules (eight_k_events + restatement_filings) (in flight, 2026-06-20)

Test-only follow-up in the coverage sweep (after #518 baseline 85%, #525 PIT parquet readers, #528
universe.py 80→93%). Lifts the two EDGAR-fetch scoring modules' PURE parsing + cache + graceful-
degradation branches by MOCKING the edgartools/EFTS boundary — the live fetch stays network-gated; no
live `@network` tests added (they don't run in offline CI). Both modules **→ 96%**.

- **`compute/scoring/eight_k_events.py` 68% → 96%** — `tests/test_scoring/test_eight_k_events_offline.py`
  (new, 39 tests): `_ttl_jitter_seconds` zero-window + SHA-256 determinism · `_ensure_edgar_identity` all
  3 outcomes · `_cache_read` error branches (missing/invalid `fetched_at`, filings-not-list) + `_cache_write`
  OSError no-raise + roundtrip · `_filing_to_dict` all attr paths (date/datetime/str, html callable/raises,
  url/filing_url fallback, header-raises→None) · `_fetch` ImportError / Company()-raises / mid-loop-partial /
  None-entry-skip · `_filing_date_within` future + malformed + boundary · `_check_item` non-dict/empty/missing
  items · `get_non_reliance_filing_dates` None-fetch / non-dict / malformed-date / custom-lookback / wrong-item ·
  `check_non_reliance`+`check_auditor_change` no-identity graceful · `invalidate_cache` idempotent.
- **`compute/scoring/restatement_filings.py` 55% → 96%** — `tests/test_scoring/test_restatement_filings_offline.py`
  (new, 49 tests): identity 3 outcomes · `_cache_read` 8 error/expiry branches + write roundtrip ·
  `invalidate_cache` both-subdirs / idempotent / OSError-swallow · `_filing_to_dict` 8 attr/fallback/exception
  paths · `_fetch_filings` ImportError / Company-raises / per-form-raises-continue / iteration-raises-continue /
  None-skip · `fetch_amendments`+`fetch_late_filings` default-lookback wiring · `check_restatement_history`+
  `check_late_filing` None-fetch + default-lookback + all-out-of-window · `_parse_iso_date` non-string/malformed/
  valid/truncate · `get_amendment_filing_dates` None-fetch / out-of-window / parse-None-skip · frozen dataclasses.

**No real bug found** — every graceful-degradation path behaves as documented (the `_cache_write` OSError
path correctly cleans up the `.tmp` file and does not propagate). Remaining ~uncovered = live-fetch
network-only paths (`from edgar import Company`, real EFTS calls) + a couple of structurally-dead inner
guards already short-circuited upstream.

Verify: `ruff` clean · `pytest tests/test_scoring -m "not network"` 828 passed (+88, 0 regressions). No
production code / schema / workflow touched. Gate: test-engineer authored.

---

## PR #TBD — S&P 1500 cutover Slice 6 — SmallcapChip + SML tab activation (in flight, 2026-06-20)

**Branch**: `claude/sp1500-slice6-sml-tab`
**Type**: feat(frontend) — frontend-only, NO schema bump, NO compute change.

**Summary**: Implements the small-cap membership chip (`SmallcapChip`) and wires
the `SML` (S&P 600) tab in `IndexTabs` to go from a hardcoded "SOON" placeholder
to a fully data-driven active path — exactly mirroring the MidcapChip + MID-tab
pattern shipped in #490.

**Changes**:
- `frontend/components/SmallcapChip.tsx` (NEW) — renders "Small-cap" chip iff
  `index_membership === 'sp600'`, else null. Violet outlined-light tone
  (`bg-violet-50 / text-violet-700 / ring-violet-200` + paired `dark:` variants)
  — distinct from MidcapChip's neutral-steel slate, same chip family. Uses the
  shared `Chip` primitive.
- `frontend/components/RankingView.tsx` — `filterAndRerank` gains `SML` branch
  (filters to `index_membership === 'sp600'`); `computeAvailableCodes` adds
  `'SML'` when `memberships.has('sp600')`; `showSmallcapChip = safeTab === 'ALL'`
  mirrors `showMidcapChip`; `tabConfig` gains `SML` → "S&P SmallCap 600 ranking";
  SML honesty note in the descriptive paragraph; `showSmallcapChip` wired to
  `<RankingTable>`.
- `frontend/components/RankingTable.tsx` — `showSmallcapChip` prop added;
  `<SmallcapChip>` rendered beside `<MidcapChip>` in desktop table rows and
  passed to `<StockListCard>`.
- `frontend/components/StockListCard.tsx` — `showSmallcapChip` prop added;
  `<SmallcapChip>` rendered beside `<MidcapChip>` in mobile card header.
- `frontend/lib/sml-tab.test.ts` (NEW) — vitest contract tests: `filterAndRerank`
  SML branch (returns only sp600, re-numbered, empty on sp900-only data),
  `computeAvailableCodes` (SML present iff ≥1 sp600 row; absent on sp900-only),
  `SmallcapChip` render contract (VIOLET_TONE design-system compliance + guard logic).

**Data-driven dormancy**: on the current ~902-row sp900 production data
(sp500 + sp400 only, sp600 probe-only/not-ranked), the SML tab stays "SOON"
(`availableCodes` does not contain 'SML') and no SmallcapChip renders in any row.
The tab and chip light up automatically once sp600 rows appear in `rankings.json`
after the Slice 7 cron flip — no frontend code change required.

**Schema triple**: UNTOUCHED. `index_membership` (singular) already exists as
`'sp500' | 'sp400' | 'sp600'` per Slice 2; this PR only adds the consumer UI.

**Verification**: `tsc --noEmit` clean · `npm run test:unit` green (new tests +
existing) · `next build` succeeds.

---

## PR (test) — final clean coverage pass: pure-logic features + scoring + output modules (in flight, 2026-06-20)

Capstone of the coverage sweep (after #506/#508/#525/#528/#529). Lifts the remaining PURE-LOGIC
compute modules that were < 90% — all OFFLINE (no network, no production touch). +143 tests, 8 new files.

Per-module coverage delta:
- `compute/scoring/pillars.py` 88% → **100%** · `compute/features/risk.py` 79% → **98%** ·
  `compute/features/technical.py` 85% → **98%** · `compute/output/writer.py` 86% → **98%** ·
  `compute/scoring/rem.py` 88% → **98%** · `compute/scoring/earnings_quality.py` 89% → **96%** ·
  `compute/scoring/composite.py` 89% → **95%** · `compute/features/quality.py` 84% → **89%** (remaining
  = `@given` None-propagation branch-arcs already locked by #506's `test_features_none_propagation.py`).

New files: `tests/test_features/test_risk_coverage.py` · `test_quality_coverage.py` ·
`test_technical_coverage.py` · `tests/test_scoring/test_composite_coverage.py` · `test_pillars_coverage.py`
· `test_rem_coverage.py` · `test_earnings_quality_coverage.py` · `tests/test_output/test_writer_coverage.py`.
Cover: pillar-math edge/NaN/None branches, technical-indicator boundaries, risk metrics (Sharpe/Sortino/
max-drawdown short-series guards), REM proxy + index branches, composite normalization + adjusted-score
clamps, earnings-quality loss-avoidance walker edges, writer atomic-write / null-pad / orphan-prune /
optional-field round-trip.

**No real bug found.** Authored partly under a sub-agent rate-limit cutoff, then orchestrator-verified:
4 agent-drafted tests asserted wrong contracts (pre-verification) — 1 fixed to the real behavior
(`write_benchmarks_json` NULL-PADS a no-price-column benchmark as `[None,None]`, it does not drop it),
3 dropped (piotroski all-fail fixture didn't fire all 9 criteria; sortino sd≈1e-16 float-noise not exact-0;
rem dsales-lag fixture supplied a t-1 row) rather than ship guessed assertions. `valuation/graham.py`
(89%) was NOT reached before the cutoff — deferred.

Verify: `ruff` clean · the 8 new files 143 passed · `pytest tests/test_features tests/test_scoring
tests/test_output -m "not network"` green apart from the two KNOWN pre-existing items (alpha158
`test_C1` Hypothesis DeadlineExceeded slow-box flake + optional-`[factors]` osap collection error). No
production code / schema / workflow touched. Gate: test-engineer (drafted) + orchestrator (verified/cleaned).

## S&P 1500 cutover Slice 7 — cron-default flip sp900→sp1500 (in flight, 2026-06-20)

The production cutover slice of the S&P 1500 epic. Flips the scheduled-cron universe default
`sp900`→`sp1500` across both compute workflows and lifts the Slice-2 probe-only guard so the
weekday cron RANKS the full ~1500 names instead of scoring 901 + probing sp600.

- **`compute/main.py`** — removes the Slice-2 `cohort != "sp600"` filter on the scored frame
  (`universe = _sp1500_full_frame.reset_index(drop=True)`); `Metadata.universe` label
  `"SP1500-probe"` → `"SP1500"`. The `_run_smallcap_coverage_probe` call and the
  `derive_index_memberships` russell1000-proxy suppression for sp600 are **retained** (the
  smallcap_* coverage Metadata fields keep emitting; sp600 still excluded from the market-cap
  Russell proxy).
- **`.github/workflows/compute-rankings.yml`** — dispatch input `default: sp900`→`sp1500`,
  env fallback `|| 'sp900'`→`|| 'sp1500'`, with an inline rollback comment.
- **`.github/workflows/precache-edgar.yml`** — scheduled default flipped to `sp1500`.
- **`.github/workflows/pre-merge-prod-sim.yml`** — pinned `QR_UNIVERSE: sp900`→`sp1500` so the
  pre-merge sim keeps mirroring the cron (the documented "sim mirrors the cron" invariant); this
  also makes the `simulate` CI check measure the ranked-1500 path end-to-end (conservative upper
  bound — the sim is heavier than the warm cron). Cost note updated: ~175 min warm (extrapolated
  from the sp900 ~105 min observed on this PR × 1.66), 240-min timeout holds headroom on a warm
  cache-v11 hit (sp600/sp1500 paths seeded #520); rollback = the compute-rankings.yml sp1500→sp900 hatch.
- **Tests** — `test_sp1500_seam.py` reconciled to ranked behavior (sp600 rows now PRESENT in
  the scored universe; label `SP1500`); `test_workflow_cache_coverage.py` dispatch-default
  assertions updated to `sp1500`.

NO schema bump (stays `0.10.29-phase8pilot`); defense layer unchanged at 36. Mirrors the #492
sp500→sp900 production flip precedent. **GATED — DO NOT MERGE** until a warm ranked-1500 timing
run confirms total wall-clock < 90 min (cron `timeout-minutes` headroom) AND explicit owner go;
this is the 902→~1500 ranked production cutover. Slice 3 (Bonferroni shadow) stays DEFERRED to
the Slice-8 calibration; Slice 6 SML tab/chip merged as #531; Slice 8 = v2.0 tag after ≥1-2
green sp1500 crons.

---

## PR (test) — offline coverage for valuation/graham.py → 100% (in flight, 2026-06-20)

The deferred tail of the coverage sweep (graham.py was not reached before the #532 sub-agent cutoff).
Test-only — no production/schema/workflow touched. `compute/valuation/graham.py` **89% → 100%**.

`tests/test_valuation/test_graham_coverage.py` (new, 10 tests) covers the single remaining branch — the
post-gate `if product <= 0 or not math.isfinite(product)` guard (line 111): inf-EPS / inf-TBVPS / both-inf
/ float-overflow → inf product → returns `(None, "graham_product_non_positive_post_gate")`; subnormal
underflow → product 0.0 (the `<= 0` arm); + regression guards (valid inputs bypass the post-gate; soft-lag
normal path; hard-lag applicability gate fires BEFORE the post-gate); + locks the `22.5` Graham multiplier
constant + the post-gate reason string. The inf-passthrough is the same `_finite_positive` no-`isfinite`-guard
finding already DOCUMENTED (document-only) in `test_applicability_coverage.py::test_finite_positive_infinity_behavior`;
graham.py's post-gate guard is the correct compensating control — **no bug**.

Verify: `ruff` clean · `pytest tests/test_valuation -m "not network"` 238 passed (+10, 0 regressions).
Gate: test-engineer authored. With this, every pure-logic compute module the offline suite can reach is
≥ 95% (most 96-100%); the residual sub-90% modules are network/optional-dep fetch layers only.

---

## PR (frontend) — Current-picks status indicator: bare color dot → labeled "New"/"Held" chip (in flight, 2026-06-21)

The AI-pick home page ("Current picks" table in `frontend/components/AiPickPortfolio.tsx`)
marked each holding's status with a bare 7px color dot — emerald = newly entered this
quarter, slate = "held" (carried: composite dipped below the entry cutoff but stays above
the hold floor). Color was the SOLE signal with no label or legend, so users couldn't
decode it — a direct violation of the design-system Rule 10 ("color is never the sole
signal — chips always pair color with a short text label"). User-reported the dot
"can't convey its meaning."

Fix: replace the dot with a labeled outlined-light **status chip** via the shared `Chip`
primitive (`size="xs"`) — **"New"** (positive-light emerald tone) / **"Held"** (neutral
slate tone), each with the canonical paired `dark:` variants. The table header's 7px
spacer becomes a real **"Status"** column label. The now-redundant `sr-only " (held)"`
span on the score cell is removed — the visible chip text announces the state to screen
readers directly. No explainer caption added (per owner: labels are self-explanatory).

**Semantic fix (2nd pass, same PR):** the original dot drove New/Held off the score-band
`carried` flag (composite < `composite_min` 65 but ≥ `hold_band_min` 55), which DISAGREED
with the app's own "Rotation history" panel (`HoldingsTimeline`), which uses the PORTFOLIO
sense (in this quarter's basket AND the prior quarter's). User caught the mismatch: for the
2026-05-15 basket the score-band flag marked only SYF "Held" (1) while Rotation history
correctly shows 3 held. Per owner decision, the Status chip now uses the **portfolio sense**:
a new local `heldSetForEntry(entry)` helper mirrors `HoldingsTimeline`'s per-entry membership
derivation exactly (bandBook short-circuit, else `bandHeldCount ?? adaptiveCount` prefix
slice), and `priorHeldSet` (from `timeline[timeline.length - 2]`, empty when `timeline.length
< 2` → all New) drives `isHeld = priorHeldSet.has(h.ticker)`. The muted held-row score tone is
**removed** (decoupled) — under the portfolio sense, healthy-score Held names (LULU 66.9 /
ACGL 65.5) would otherwise be wrongly dimmed; all scores now render in the normal tone. Latest
quarter now resolves Held = LULU/ACGL/SYF (3), New = ALL/DECK/APA/IBKR (4) — byte-matches
Rotation history. The data-layer `carried` field is untouched (no longer consumed here).
Frontend-only — schema triple untouched, rankings/scores unaffected.

Verify: `tsc --noEmit` clean · `next build` clean (909/909 static pages) · New/Held split
cross-checked against the artifact (`backtest_pit.json`) = 3 Held / 4 New, matches Rotation
history. Gate: frontend-builder (built, both passes) + orchestrator (verified). Design
grounded in the `frontend-design-system` skill (Rule 2 outlined-light + Rule 10
label-not-color-alone); semantics aligned to `HoldingsTimeline` to kill the cross-surface
"Held" ambiguity.

**Sort pass (3rd, same PR):** per owner request, the "Current picks" table is now ordered by
portfolio `weight` **descending** (heaviest holding first) instead of composite-score order. A
new `weightSortedHoldings` `useMemo` derives a sorted copy of `displayHoldings` (non-mutating,
so the held-set / New-Held logic is unaffected); non-finite weights sort to the bottom and
equal weights keep composite order as a stable tiebreak. The `#` column now reads as the weight
rank. Latest quarter resolves ACGL 23.0% → ALL 20.7% → SYF 14.0% → IBKR 12.0% → LULU 10.7% →
DECK 9.8% → APA 9.8%. Consistent with the historical `feat(home) — Current-picks P/L-since-entry`
intent (which also sorted by weight desc). `HoldingsTimeline` / Rotation history ordering is
untouched. Frontend-only — schema triple untouched. Verify: `tsc --noEmit` clean · `next build`
clean (909/909). Commit `88358e63`.

---

## PR (frontend) — Current-picks: append rotated-out "Sold" rows (in flight, 2026-06-21)

Follow-up to the merged #536 Current-picks status redesign. Per owner request, the "Current
picks" table now appends the tickers SOLD this quarter (rotated out of the basket) below the
holdings rows, continuing the same `#` sequence (so with 7 holdings the sold names are #8, #9).
Each sold row carries a new **"Sold"** status chip — mirrors the SELL group already shown in the
Rotation-history panel.

Derivation reuses the existing `priorHeldSet` (prior quarter's basket, from
`timeline[timeline.length - 2]` via `heldSetForEntry`): a new `soldRows` `useMemo` filters
`priorHeldSet` against the current basket's ticker set, resolves sectors from the prior timeline
entry's `holdings`, sorts alphabetically, and guards the empty / `timeline.length < 2` cases
(renders nothing). Latest quarter (2026-05-15): prior band_book `[CF, TRV, LULU, ACGL, SYF]` −
current `[ALL, DECK, APA, LULU, IBKR, ACGL, SYF]` = **CF, TRV** → rows #8, #9.

Design grounded in the `frontend-design-system` skill: the "Sold" chip is the Negative
outlined-light tone (`bg-red-50 text-red-900 ring-red-200` + paired `dark:` + `bg-rose-500` dot)
via the shared `Chip` primitive (Rule 2, one chip family New/Held/Sold), label-not-color-alone
(Rule 10), paired light/`dark:` (Rule 4). Sold rows are de-emphasized (`text-slate-500
dark:text-slate-400`) with a marginally stronger top-border separator (`border-t-slate-300
dark:border-t-slate-600`); the ticker stays a `<Link>`. **Data limit (by design):** the frontend
`timeline` carries only ticker+sector per quarter, so sold names have no score/weight — those
cells render "—" (no `data.ts` change to plumb stale prior-quarter scores). The holdings count /
"7 stocks this quarter" copy is unchanged — sold rows are an informational appendix.

Frontend-only — schema triple untouched, rankings/scores/flags unaffected. Verify: `tsc
--noEmit` clean · `next build` clean (909/909 static pages) · sold set cross-checked against the
artifact (`backtest_pit.json`) = CF, TRV. Gate: frontend-builder (built) + frontend-design-reviewer
(design/WCAG) + orchestrator (verified).

---

## PR #533 — fix(ingest): `dividend_yield_pct` ×100 double-scaling removal (in flight, 2026-06-21)

Bug fix for the Dividend signal landed in #512. `_yf_info_fetch` in
`compute/ingest/cross_source.py` read yfinance `.info["dividendYield"]` and
multiplied by 100 to convert fraction → percent. yfinance changed
`dividendYield` to return PERCENT directly (e.g. `2.67` = 2.67% for KO), so the
`×100` over-scaled every value 100× — the first sp1500 probe cron (#533 trigger)
wrote `dividend_yield_pct = 267.0` for KO, `36.0` for AAPL, `184.0` for JPM,
`47.0` for NVDA into the per-stock JSONs. `dividend_yield_pct` is a display-only
`StockDetail` field (NOT a pillar / veto input), so rankings, composite scores,
risk flags and recommendations are byte-identical and unaffected — the corruption
was confined to the not-yet-wired Dividend tile.

Fix: drop the `* 100.0` (assign `float(dy_val)` as-is) + add a format-reversion
guard — any `dividend_yield_pct > 100.0` is discarded to `None` with a warning
log, so a future yfinance revert-to-fraction surfaces as missing data rather than
a 100× inflated number. `pays_dividend` logic (`True iff > 0`) is unchanged.
Tests CS_DIV7A–D added to `tests/test_ingest/test_cross_source_dividend.py`
(normal percent pass-through / zero non-payer / missing-key None / >100 guard
discard); +4 tests, full ingest suite 583 passed. NO schema bump (no field
added/removed/retyped — schema stays `0.10.29-phase8pilot`). CLAUDE.md §Gotchas
dividend entry + AGENTS.md in-flight note updated in lockstep.

Follow-up: re-cron (sp1500 on `main` after merge) to repopulate the per-stock
JSONs with CORRECTED dividend values → then wire the `HeroAttributeTiles`
"Dividend" tile (the Rule-18 gate now requires ≥ 1 cron of corrected — not
inflated — `dividend_coverage_pct`).

---

## PR (roadmap-prep) — roadmap grooming + Slice 8 / display-tile issue scaffold (in flight, 2026-06-21)

Docs-only roadmap-preparation pass on branch `claude/roadmap-preparation-ycaqf8`.
No code / schema / workflow change — schema stays `0.10.29-phase8pilot`, defense
layer 36, rankings/scores untouched.

Reconciled the forward roadmap to post-Slice-7 reality and filed the
previously-untracked next-work as GitHub issues so each track has a tracker:

- **epic #545** — S&P 1500 cutover Slice 8 / v2.0, with sub-issues:
  - **#540** — frontend(perf): virtualize the ~1500-row ranking table for
    mobile (the open WORKFLOW.md acceptance gate now that the cron ranks ~1504).
  - **#542** — feat: Bonferroni multi-test shadow counter (Slice 3, deferred →
    Slice-8 calibration; FWER α/n over the ~1500-name cross-section, Harvey-Liu-Zhu 2016).
  - **#544** — methodology: `low_liquidity` annotate → veto promotion decision
    (gated on ≥ 1 sp600 cron firing-rate data + methodology ratification; the
    annotate now fires since Slice 7 ranks sp600).
- **#541** — feat: Security-type (Type) HeroAttributeTile signal 7b
  (observability-first ingest PR-1; yfinance `fast_info.quote_type` + SEC
  20-F/`entityType` for ADR detection).
- **#543** — feat(frontend): wire the `HeroAttributeTiles` "Dividend" tile 7a
  PR-2 (gated on ≥ 1 post-#533 sp1500 cron of CORRECTED `dividend_coverage_pct`).

Doc edits: CLAUDE.md + PHASE_STATUS.md §Next deliverables refreshed with the
issue refs (Slice 8 item + the 7a/7b display-tile status incl. the #533 ×100
fix); AGENTS.md in-flight note updated in lockstep. Per §Conventions this entry
satisfies the "ship with every PR" rule.

---

## PR (compute) — Research warehouse Slice 1: per-run PIT Parquet snapshot writer (in flight, 2026-06-21)

First slice of the point-in-time "research warehouse" — a per-cron historical store of all
computed stock data to power factor/IC research, walk-forward validation, and Phase-5 ML,
WITHOUT changing the static-site runtime (the site still reads JSON; the warehouse is an
offline research store). Owner-decided shape: Parquet-first Hybrid (build the in-repo Parquet
leg now; defer a Supabase sync leg to Phase 5), full per-ticker snapshot, maximum backfill
(Slice 2). This Slice 1 is WRITE-ONLY + observability-first — nothing reads the warehouse yet.

New `compute/warehouse/` package: `flatten.py` (pure Pydantic `StockDetail`/`StockSummary` →
one flat row, 126 deterministic columns: `pillar_*`/`raw_*`/`dq_*`/`fp_*` + per-flag
`flag_*`/`warn_*` booleans + `*_json` for nested/variable fields + a `row_provenance` sentinel
= `"live"` here, `"pit_replay"` for the Slice-2 backfill); `flag_registry.py` (KNOWN_RISK_FLAGS
9 + KNOWN_VALUATION_WARNINGS 28 + `assert_flags_known`); `writer.py` (`write_run_snapshot` →
`data/warehouse/snapshots/year=<YYYY>/run_date=<ISO>/part-0.parquet`, zstd, idempotent re-run, +
a run-level `_manifest.parquet` row from `Metadata`); `warehouse_schema_check.py` (a drift guard
modeled on `schema_check.py` — introspects the models + flag registry, compares to the committed
`data/warehouse/warehouse_schema.json`, `--update` regenerates). `config.py`: `WAREHOUSE_DIR =
PROJECT_ROOT / "data" / "warehouse"` (repo root, NOT `frontend/public/data/` — research data must
never ship in the static deploy). `main.py`: an `all_details` accumulator in the Step-8 loop + a
Step-13.5 write GATED by `QR_SKIP_WAREHOUSE` (mirrors the `QR_SKIP_DECAY_MONITOR` idiom) wrapped
in try/except so a failure logs a warning and NEVER blocks the cron
(`portable-graceful-degradation-try-except`).

Persistence: forward per-cron snapshots + `_manifest.parquet` are gitignore-whitelisted and
committed (the cron's added `git add data/warehouse/` rides the existing "chore: update rankings"
commit) so the panel accumulates in-repo (~0.5 MB/run); the maximum-history backfill (Slice 2,
~300 MB) ships as a CI/release artifact, NOT committed. `warehouse_schema.json` is committed.

**The JSON schema triple is UNTOUCHED** — the warehouse manifest is a separate artifact guarded
by `warehouse_schema_check`, NOT the Pydantic↔TS↔snapshot triple. No `SCHEMA_VERSION` bump
(surfacing the row count into `metadata.json` via `Metadata.warehouse_*` is deferred to a later
slice). Honest backfill limits (Slice 2): maximum history is SP500-only before sp900/sp1500
go-live (no historical mid/small-cap membership ledger); event-driven flags (8-K / Form-4 /
tier2 / cross-source / post-split / OSAP) are NOT PIT-reconstructable → stored NULL (not False)
in replayed rows, disambiguated by `row_provenance`.

Verify: `ruff check .` clean · `pytest tests/test_warehouse/ -m "not network"` = 35 passed ·
`python -m compute.warehouse.warehouse_schema_check` = 126 columns in sync · full offline suite
2646 passed (2 pre-existing Hypothesis `DeadlineExceeded` flakes in test_alpha158_replicate +
cash-conversion, unrelated). Gate: compute-builder (built) + orchestrator (assembled
workflow/.gitignore/docs); quantrank-reviewer + test-engineer + security-reviewer (workflow
touch) at the pre-Ready gate.

---

## PR (compute) — Research warehouse Slice 2: maximum-history PIT backfill (in flight, 2026-06-21)

Slice 2 of the research warehouse — the maximum-history point-in-time BACKFILL that replays the
per-run snapshot panel back to ~2016, complementing the Slice-1 forward cron snapshots. Unlike
the committed forward snapshots, the historical backfill is a ONE-OFF CI/RELEASE ARTIFACT —
written to the GITIGNORED `data/warehouse/backfill/` (blanket `*.parquet` ignores it; NOT
whitelisted) and uploaded by `backfill-warehouse.yml`, NEVER committed.

`scripts/backfill_warehouse.py` (new) — weekly PIT replay reusing the mature `backfill_portfolio_pit.py`
scaffolding: `members_at(T)` survivorship, `pit_snapshot_fields` (filed≤T, no look-ahead),
`_price_at`, the 6 PIT-recoverable vetoes, the `BACKTEST_HARD_STALE_DAYS=455` annual-cadence
relaxation. Re-scores via the existing frozen pillar/composite/ensemble functions (no reimplemented
math). Each row gets `row_provenance="pit_replay"`.

NULL-discipline (the key PIT-honesty rule): `compute/warehouse/flag_registry.py` gains
`FORWARD_ONLY_FLAGS` (11: the non-PIT-reconstructable 8-K/non_reliance, Form-4, tier2,
cross_source, post_split, low_liquidity, OSAP family) + an import-time sanity guard;
`compute/warehouse/flatten.py` gains keyword-only `null_flags` + `row_provenance` params and a
`replay_completeness` column (float ∈ [0,1] on replay rows, None on live) — replay rows write
those `flag_*`/`warn_*` columns as **NULL not False** so ML never reads an unconfirmed flag's
absence as a confirmed False. The LIVE path default (no kwargs) is byte-identical to Slice 1.
`warehouse_schema.json` 127 → 128 cols (`replay_completeness`).

`backfill-warehouse.yml` (`workflow_dispatch`, `start`/`end` inputs via shell-safe `IN_*` env):
`contents: read` only (uploads an `actions/upload-artifact`, does NOT commit — the cron stays the
sole writer to main), restores the cron's v11-fast cache family (re-scores from warm caches, no
new EDGAR calls when warm), `if-no-files-found: error`.

HONEST LIMITS (encoded in the script docstring): maximum history is SP500-only before sp900/sp1500
go-live (no historical mid/small-cap membership ledger); GICS sectors assumed stable-from-today;
recommendation/loss-chance in replay rows differ from live precisely because the forward-only flags
are absent (disclosed via `row_provenance` + `replay_completeness`).

The JSON schema triple is UNTOUCHED (`schemas.py`/`types.ts`/`schema-snapshot.json` unchanged);
rankings/scores/flags unaffected (the live path is byte-identical). Verify: ruff clean ·
`pytest tests/test_warehouse/ -m "not network"` = 100 passed (Slice-1 57 + Slice-2 43) ·
`warehouse_schema_check` 128 cols in sync. Gate: compute-builder (built) + quantrank-reviewer +
test-engineer (incl. a recurring test-isolation fix) + security-reviewer (new workflow) +
orchestrator (assembled workflow/docs).

---

## PR #TBD — ci(compute): bump cron + precache timeout-minutes 240→270 for S&P 1500 scale (in flight, 2026-06-21)

**Branch**: `claude/sp1500-cron-timeout-bump`
**Type**: ci(compute) — workflow-only; NO schema bump, NO compute/scoring/frontend change.

**Problem**: The first cold sp1500 cron (run 27902140692, commit 177485d16, 2026-06-21) ran
~223 min against a 240-min job timeout — only ~7% headroom. The data-pipeline-engineer flagged
this as a MEDIUM structural risk: a >10% SEC throttle spike on a cold run (tier2 ~89 min +
form4 ~72 min dominate) would blow the budget and produce no output.

**S&P 1500 empirical cold-compute breakdown (measured, run 27902140692)**:
- Tier-2 (10-K + 8-K): ~89 min cold
- Form-4 fetch (EDGAR): ~72 min cold
- OSAP + cross-source yfinance.info: ~13 min cold
- Prices + fundamentals + scoring + writes: ~22 min cold
- **Total cold compute: ~196 min**
- + Folded PIT backtest (warm caches): ~22-55 min
- Worst-case cold total: ~250 min

**Fix**: bump `timeout-minutes` from 240 → 270 in both `compute-rankings.yml` (the weekday
cron) and `precache-edgar.yml` (the Saturday cache warmer), lockstep. The 270-min ceiling
gives ~20 min buffer over the cold worst-case cold compute + backtest for the cron, and
~45 min buffer for the precache (which has no backtest step). Budget comments in both files
updated from the stale sp900-era "~100-115 min cold" numbers to the sp1500 empirical baseline.

The `concurrency: group: edgar-cache-writers` group comment that referenced "both jobs ≤ 240 min"
is still correct by construction (Mon-Fri 22:00 vs Sat 08:00 cannot overlap); the bump is
noted in the per-job budget comment only.

**Files**: `.github/workflows/compute-rankings.yml` · `.github/workflows/precache-edgar.yml` ·
`.github/workflows/pre-merge-prod-sim.yml` (bumped in lockstep — the `test_sim_timeout_at_least_cron_timeout` guard requires sim timeout ≥ cron timeout) ·
`PHASE_STATUS_INFLIGHT.md` (this).

**Schema triple**: UNTOUCHED.
**Gate**: security-reviewer pass on the workflow diff (CLAUDE.md routing: non-trivial edit to
`.github/workflows/*` → `security-reviewer`). DRAFT PR — do NOT merge or mark ready until
that review clears.
## PR #554 (compute) — payout_ratio format-reversion guard (in flight, 2026-06-21)

**Branch**: `claude/sp1500-dataquality-fixes`
**Type**: fix(ingest) — one data-quality bug fix surfaced by the first production sp1500 cron
(commit `177485d16`); NO schema bump; rankings and composite scores are byte-identical.

**Scope (narrowed per quantrank-reviewer FIX-AND-RE-REVIEW):** Originally this PR included two
fixes — the payout_ratio guard (approved) and a `_balance_sheet_closure_check` in
`fundamentals.py` (removed). The balance-sheet check had false-positive risk on real thin
insurance equity (EQH), nulled the wrong component for GPK, had only 2/4 cache paths wired,
and zero direct tests. Its real remedy is a separate upstream edgartools XBRL-context fix being
routed to edgar-debugger. The PR is now a single-fix, clean scope.

**Fix — payout_ratio > 20 clamp in `compute/ingest/cross_source.py`.**
yfinance occasionally returns `payoutRatio` in percent-format for companies with negative /
near-zero earnings (observed: SLG=153.75 on the first sp1500 cron, meaning 15,375% payout).
The field is documented as a 0-1 fraction; `> 20` (i.e. > 2,000%) is structurally impossible.
Guard ceiling 20.0 chosen conservatively: a real REIT at 1.5 (150%) passes through; only garbage
values are discarded. Mirrors exactly the `dividend_yield_pct > 100.0` guard added in PR #533.
Applied to all three extraction paths: `_yf_info_fetch` (live), `_dividend_cache_read`
(TTL-gated), and `fetch_yfinance_dividend` QR_SKIP branch. Three new offline tests CS_DIV9A/B/C
verify each path.

**Deferred:** `_balance_sheet_closure_check` REMOVED from this PR per opus review.
The XBRL dimensional-context issue (HASI/LGIH/GPK equity/liabilities corruption) is escalated
to `edgar-debugger` for a proper upstream edgartools fix before any in-process accounting-identity
correction lands.

**Schema triple**: UNTOUCHED (`schemas.py` / `types.ts` / `schema-snapshot.json` unchanged).
**Rule 16 (annotate-before-veto)**: N/A — no new flags.
**Rule 18 (observability-before-wiring)**: N/A — no new external data sources.
Verify: `ruff check .` clean · `pytest tests/test_ingest/test_cross_source_dividend.py -m "not network"` all passing (CS_DIV9A/B/C green).
## PR #TBD — fix(ingest): XBRL balance-sheet context mis-pick (HASI/LGIH/GPK) (in flight, 2026-06-21)

`compute/ingest/fundamentals.py` `_try_balance_tags` was a single `get_fact(tag)` call that used
edgartools' default `max(all_facts, key=(filing_date, period_end))` sort — allowing a more-recently-
filed 8-K / S-3 / S-4 event fact to beat the real 10-K consolidated balance-sheet value.  Three
confirmed victims on the first sp1500 production cron: HASI `stockholders_equity` $1,000 (S-3
preferred-share tranche vs. real ~$2-3B), LGIH `stockholders_equity` $25.2M (duration Q-change
vs. real >$2B cumulative), GPK `total_liabilities` $10.8M (8-K event vs. real >$8B consolidated).

**Fix** (`_try_balance_tags` replacement via edgar-debugger spec): walks `EntityFacts.get_all_facts()`
(public API, not private `_fact_index`) and applies a three-tier selection:
  Tier 1 — `period_type=='instant'` + form in `_BALANCE_SHEET_FORM_TYPES` (10-K/10-Q/20-F family;
             excludes 8-K/S-type) + `unit=='USD'`
  Tier 2 — `period_type=='instant'` + `unit=='USD'` (drop form-type; odd-filer safety net)
  Tier 3 — raw `get_fact()` (original behavior, last resort)
Within each tier, sort key is `(period_end DESC, filing_date tiebreaker)` — inverted from
`get_fact`'s `(filing_date, period_end)` so 8-K event facts filed more recently than the 10-K
no longer win.  `getattr` with safe defaults on every fact attribute so a future edgartools
shape change degrades gracefully (returns None, never raises into the cron).

New module-level constant `_BALANCE_SHEET_FORM_TYPES: Final[frozenset[str]]` + drift-guard
manifest tuples `_FINANCIAL_FACT_REQUIRED_ATTRS` / `_ENTITY_FACTS_REQUIRED_ATTRS` (mirroring the
`_FORM4_REQUIRED_ATTRS` hasattr pattern in `form4_insider.py`) + module-load check via
`edgar.entity.models.FinancialFact` + `edgar.entity.EntityFacts`.  `_try_balance_tags_most_recent`
(shares path) left AS-IS.  No schema bump (pure ingest-logic fix; same fields, correct values).

offline + `@network` regression tests in `tests/test_ingest/test_fundamentals_balance_tag_fix.py` (HASI `stockholders_equity > 2e9`, LGIH `stockholders_equity > 2e9`,
GPK `total_liabilities > 8e9`) for `--run-network` confirmation.  Verify: ruff clean ·
`pytest tests/test_ingest/test_fundamentals*.py -m "not network"` = 53 passed.

**Gate:** quantrank-reviewer (opus, core ingest change) + `--run-network` confirmation before
marking ready.  Schema triple: UNTOUCHED.  Rankings/scores: CORRECTED (HASI/LGIH/GPK fix).

---

## PR (compute) — drop free-text post-split valuation_warning + correct stale DQIC docstrings (in flight, 2026-06-21)

A stock-detail-auditor pass on the latest production output surfaced two defects.

**Fix 1 (real display bug):** the Tier-1 post-split correction path in `compute/main.py` appended a
DYNAMIC FREE-TEXT string (`"share count adjusted for N:1 split <date>, pending EDGAR refresh"`) into
`valuation_warnings` alongside the structured `post_split_share_lag` key. On the frontend `flagLabel`'s
Title-Case fallback rendered it as an awkward DUPLICATE amber chip ("…Pending Edgar Refresh") next to
the clean "Post-split share count adjusted" chip — and the free-text literal is unregistered /
unparseable by `flag_registry.py` / the warehouse / search. Removed the free-text block (kept only the
structured `post_split_share_lag` key); the ratio/date detail is intentionally dropped for now (a
structured `post_split_event` field is the future path). Affects KLAC/CVNA/COKE-class post-split rows.

**Fix 2 (stale docs):** two `compute/scoring/risk_overlay.py` docstrings (module §31-46 + the
`_data_quality_input_corruption` fn §150-158) still claimed DQIC "nulls all 6 fair-price methods" — a
pre-PR-#289 behavior (the Site-2 output ceiling guard was retired in #289 after the NVR false positive).
Corrected to the CURRENT behavior: DQIC fires input-side → `data_quality_input_corruption` in
`risk_flags` → `cautious` + Top-5 suppress; the ensemble runs INDEPENDENTLY (not nulled by DQIC); the
writer-parity path emits `valuation_output_anomalous` and `FairPriceCard` suppresses the median/max
summary on that annotate (the partition with `fundamentals_unavailable` per #487 is unchanged). Also
removed a stale TODO in `compute/warehouse/flag_registry.py` referencing the deleted free-text format,
and corrected two stale `docs/GOTCHAS.md` lines (the free-text transparency mention + the
"DQIC null-all-methods contract" attribution on the Tier-2 `post_split_share_lag_unreconciled` veto,
which actually nulls fair-price via its OWN explicit `ensemble = None`, not the retired DQIC guard).

Test: `tests/test_scoring/test_post_split_share_lag.py::test_PSL_VW4_no_free_text_warning_in_valuation_warnings`
asserts the structured key is present and NO `valuation_warnings` entry contains "share count adjusted".
Behavior: rankings/scores/composite UNAFFECTED (only a display-string drop on post-split rows +
docstring/doc accuracy); schema triple untouched. Verify: ruff clean · `pytest tests/test_scoring/` =
901 passed · grep confirms it was the only free-text `valuation_warnings` emitter in `compute/`.

---

## PR #540 — frontend(perf): infinite-scroll the ~1500-row ranking table (in flight, 2026-06-21)

S&P 1500 cutover Slice 8 acceptance gate (epic #545). Slice 7 (#534) flipped the
cron to `sp1500` so production `rankings.json` now carries ~1504 names; the
ranking table's Prev/Next pagination (50 rows/page, ~30 pages) was the open
"handles 1500 rows smoothly on mobile" gate in WORKFLOW.md.

Change (frontend-only, `RankingTable.tsx`): replace Prev/Next pagination with an
**IntersectionObserver-based infinite-scroll append** — `WINDOW_SIZE = 50` rows
on first paint, a zero-height bottom sentinel grows `visibleCount` by 50 each time
it enters the viewport (`rootMargin: 200px`), plus a "Showing X of N" `aria-live`
progress indicator. Rows are **append-only** (never unmounted) so the a11y tree,
keyboard nav, and FLIP `prevPos` map are all preserved.

Deliberately NOT true DOM-windowing (`@tanstack/react-virtual`): true windowing
unmounts off-screen rows, which conflicts with the search-scoped FLIP reshuffle
(it measures surviving-row positions across the full visible set) and would need
both the desktop `<table>` + mobile `<ul>` paths virtualized. For ~1500 lightweight
rows the real-world win is marginal; true windowing is deferred to a profiling-gated
follow-up (noted on #540).

FLIP-search-scoped invariant preserved: `filterKey = search` gates `useFlip`;
scroll-driven `visibleCount` changes `orderKey` (silent re-baseline) but not
`filterKey`, so no FLIP fires on scroll — only on a search keystroke. Per-index
tabs (SPX/MID/SML/ALL/DJI/NDX/RUI) reset the window via the `data`-keyed effect;
the warm "no matches" empty-state is now gated on `visibleRows.length === 0`.

Schema triple UNTOUCHED (frontend-only); rankings/scores/flags unaffected; schema
stays `0.10.29-phase8pilot`, defense layer 36. Verify: `tsc --noEmit` clean ·
`next build` clean (909 static pages, identical count). Gates: frontend-builder
(built) + frontend-design-reviewer (in progress) + Playwright/expert-user spot-check
of mobile scroll smoothness + FLIP-on-search (deferred to preview).

---

## PR #549 — feat(frontend): wire HeroAttributeTiles Dividend tile to real data (in flight, 2026-06-21)

UI follow-up (PR-2) to the dividend signal. The stock-detail hero's `HeroAttributeTiles`
tile #3 (Dividend) was a hardcoded `value={null}` "Coming soon" placeholder; it now shows
real `StockDetail.dividend_yield_pct` data. Ships AFTER the Rule-18 gate cleared: cron #121
(`workflow_dispatch` universe=sp1500, committed `177485d1` 2026-06-21) confirmed CORRECTED
dividend values (KO 2.67% / AAPL 0.36% / JPM 1.84% / NVDA 0.47% / F 4.27%; the pre-#533
×100-inflated 267.0/36.0/184.0 are gone), `Metadata.dividend_coverage_pct = 67.29%`.

New `formatDividendYield(dividendYieldPct, paysDividend)` in `frontend/lib/format.ts` with
three display states: payer `"2.67%"` (toFixed(2)) / confirmed non-payer (`pays_dividend ===
false` or yield 0) `"None"` / unavailable (`null`) `"—"` (em-dash, matches the app's
`formatFairPrice`/`formatMosPct` null sentinel). `HeroAttributeTiles` gains `dividendYieldPct`
+ `paysDividend` props; tile #3 always renders FILLED via the helper, tile #4 (Type) stays the
dashed "Coming soon" reserved state; `tabular-nums` on the value span. Call site in
`app/stock/[ticker]/page.tsx` passes `detail.dividend_yield_pct` + `detail.pays_dividend`.

Frontend-only — NO schema change (fields exist from #512; `types.ts`/`schemas.py`/snapshot
untouched), rankings/scores unaffected. Verify: `tsc --noEmit` clean · `next build` 1512
static pages (full sp1500) · `vitest run` 179/179 (+14 `formatDividendYield` assertions).
Gate: frontend-builder (BUILT-CLEAN) + frontend-design-reviewer (PASS-WITH-NITS — diff clean
across all 6 design sections; 2 deferred optional nits: over-broad `tabular-nums` harmless +
no `title` on the `"—"` state). Closes the Dividend half of CLAUDE.md §Next deliverable 5.
## PR #TBD — feat(compute): Bonferroni multi-test shadow counter (#542, Slice 8) (in flight, 2026-06-22)

**Branch**: `claude/slice8-bonferroni-shadow`
**Type**: feat(compute) — schema `0.10.29-phase8pilot` → `0.10.30-phase8pilot`. Additive PATCH bump; backward-compatible. SHADOW / OBSERVABILITY-ONLY. Live composite scores, risk_flags, rankings, and vetoes are BYTE-IDENTICAL.

**What**: Slice 8 acceptance criterion "Bonferroni adjustments documented and applied" (WORKFLOW.md §8.6). Ships the shadow counter infrastructure — observability-first, NOT the live threshold promotion.

**Three new `Metadata` fields** (all `int | None = None`, nullable on legacy snapshots pre-0.10.30):
- `bonferroni_shadow_flip_count` — tickers where live Beneish threshold (−2.22) fires but the provisional Bonferroni-tightened threshold (−1.94) does NOT. These are the false positives the tighter threshold would suppress.
- `bonferroni_shadow_live_fire_count` — tickers with M-score > −2.22 (matches the existing `beneish_high` annotate count; surfaced for self-contained shadow report).
- `bonferroni_shadow_provisional_fire_count` — tickers with M-score > −1.94 (provisional Bonferroni threshold, PROVISIONAL pending empirical SD from real sp1500 cron). Always ≤ live_fire_count.

**Sign correction** (WORKFLOW.md §8.6, 2026-06-19): −2.50 was WRONG (looser than −2.22, flags more names). Tighter FWER control moves the cutoff UP toward 0 (less negative). Provisional −1.94 is an ARBITRARY PLACEHOLDER between live −2.22 and soft-veto −1.78; exact value DEFERRED to re-derivation from empirical sp1500 M-score SD.

**methodology-scientist REVISE applied (2026-06-22)**:
- Fix 1 — `m = valid_count` (data-driven): removed the hardcoded `BONFERRONI_M = 1500` and `BONFERRONI_ALPHA_STAR` module-level constants. `compute_bonferroni_shadow()` now counts valid (non-None) M-scores at runtime and uses `α* = 0.05 / valid_count`. Controls the per-ticker family-wise false-flag rate across the N valid Beneish M-score decisions for THIS cron run (distinct from Harvey-Liu-Zhu multi-SIGNAL FWER). `valid_count == 0` → returns (0, 0, 0) gracefully, no ZeroDivisionError. `alpha_star` is logged per run for methodology-scientist re-derivation.
- Fix 2 — false derivation removed: the `−1.94 ← −4.84 + z*×1.8` formula in the original docstring was methodologically unsound (−4.84 is the regression intercept, not a distribution mean; 1.8 is not a Beneish 1999 pooled-M SD; and the computation yields ≈ −1.81 not −1.94). The formula is DELETED. The threshold is now documented honestly as an arbitrary placeholder strictly between −2.22 and −1.78, with re-derivation explicitly DEFERRED to the empirical sp1500 M-score SD after ≥1 real cron.
- 20 new offline tests in `tests/test_scoring/test_bonferroni_shadow.py` covering the m=valid_count semantics, flip-count invariants, zone classification, and valid_count=0 graceful path.

**Constants** (in `compute/scoring/bonferroni_shadow.py`): `BONFERRONI_ALPHA = 0.05` · `BENEISH_BONFERRONI_PROVISIONAL = -1.94` · `BENEISH_LIVE_THRESHOLD = -2.22`. `m` = data-driven `valid_count`, NOT frozen 1500. Reads `beneish_m_scores` already computed in main.py Step 5 — zero new computation. NEVER blocks the cron (try/except → None).

**Files**: `compute/scoring/bonferroni_shadow.py` (new) · `compute/output/schemas.py` · `compute/config.py` · `compute/main.py` · `frontend/lib/types.ts` · `frontend/lib/schema-snapshot.json` (snapshot regenerated) · `tests/test_config.py` (schema pin updated) · `tests/test_scoring/test_bonferroni_shadow.py` (new, 20 tests) · `CLAUDE.md` · `AGENTS.md` · `PHASE_STATUS_INFLIGHT.md` (this).

**Gates**: methodology-scientist re-confirm of m=valid_count + placeholder labeling + provisional −1.94 · quantrank-reviewer (opus) · schema-sentinel (triple). DO NOT MERGE before methodology-scientist RATIFY-SHADOW on the first sp1500 cron's `bonferroni_shadow_flip_count`.

---

## PR (compute) — warehouse flatten: populate per-method fp_* + lock numeric dtype (in flight, 2026-06-22)

Two real warehouse defects found by querying a REAL SP1500 snapshot (1504 names, flattened from the
committed production JSON) via DuckDB — the kind of bug only a real-data query surfaces.

**Defect 1 — per-method `fp_*` + `fp_methods_applicable` were ALL-NULL (flatten bug).** `flatten.py`'s
`_FP_SCALAR_KEYS` assumed `graham`/`multiples_pe`/`multiples_pb`/`multiples_ev_ebitda`/`rim`/`dcf` +
`methods_applicable` lived at the TOP LEVEL of the `fair_price` dict. The real shape nests per-method
values under `fair_price["methods"][<name>]["value"]`, and the count key is
`valuation_methods_applicable`. So the six SQL-friendly per-method columns + `fp_methods_applicable`
came out NULL for every row — the columnar per-method fair-price research the warehouse advertises was
unusable (the data only survived in the `fair_price_json` blob). Fix: split `_FP_SCALAR_KEYS` into
top-level scalars / the nested per-method set (sourced from `METHOD_NAMES` in `ensemble.py`) /
the `valuation_methods_applicable → fp_methods_applicable` remap; section 6 of `flatten_stock` now
reads the nested `methods[*]["value"]`. Column NAME SET unchanged (still 128). Real-data proof:
`fp_graham` 0→916, `fp_dcf` 0→780, `fp_rim` 0→627, `fp_multiples_pe` 0→1318, `fp_methods_applicable`
0→1497 non-null; ABR shows `fp_graham=19.46`/`fp_multiples_pe=5.64`/`fp_dcf=NaN` (DCF sector-excluded
for financials) / `fp_methods_applicable=3`.

**Defect 2 — all-null numeric columns inferred parquet INTEGER (unstable dtype).** Columns all-null in
a snapshot (`pillar_sentiment`/`pillar_ml` — Phase 5 unwired — and any still-null `fp_*`) wrote as
parquet INTEGER, then would re-infer DOUBLE once real values land — a dtype flip that could break a
typed consumer. Fix: `writer.py` builds an EXPLICIT pyarrow schema before `Table.from_pandas`
(`flag_*`/`warn_*`→bool, `*_json`→large_string, numeric/all-null-numeric→float64). Real-data proof:
`pillar_sentiment`/`pillar_ml`/`fp_dcf`/`fp_graham` all land DOUBLE.

Tests: `tests/test_warehouse/test_warehouse.py` gains `TestFlattenFpNestedMethods` (nested extraction,
non-applicable→None, methods_applicable remap, absent-key→None, top-level scalars intact,
`fair_price_json` complete) + `TestWriterNumericDtypes` (all-null numeric round-trips DOUBLE) — 121
warehouse tests pass. Schema triple UNTOUCHED; rankings/scores unaffected (offline transform fix).
`warehouse_schema.json` still 128 cols, in sync. Verify: ruff clean · 121 warehouse tests · real-data
duckdb proof. Provenance: the "test analyst against the real DB" probe (owner request 2026-06-22).

**Follow-on (review WARN#1):** the dtype-lock is extracted into a shared `build_locked_schema(df)` helper in `writer.py`, applied in BOTH `write_run_snapshot` and `scripts/backfill_warehouse.py::_write_backfill_partition` (so the gitignored backfill artifact gets the same float64/bool discipline), and `pays_dividend` is locked to `bool` BY NAME (stable even when all-null). Forward output byte-unchanged (fp_graham still 916 non-null); 121 warehouse tests pass.

---

## PR (compute+frontend) — Security-type (Type) HeroAttributeTile signal (7b) ingest PR-1 (in flight, 2026-06-22)

Issue #541. Second of the two reserved `HeroAttributeTiles` display slots (the Dividend
tile 7a shipped via #512/#533/#549). Observability-first ingest PR-1 (Rule 18): adds the
field + diagnostic coverage canary, **NO UI wiring** (a later PR-2 promotes the "Type" tile
out of its "Coming soon" placeholder once the canary confirms). Display-only descriptive
metadata — does NOT touch ranking, scoring, pillars, or the defense layer.

Schema triple (one additive bump `0.10.30`→`0.10.31-phase8pilot`):
- `StockDetail.security_type: str | None` — categorical label (`"Common stock"` / `"ETF"` /
  `"Fund"` / …) from yfinance `fast_info.quote_type`, mapped via `_QUOTE_TYPE_LABEL` in
  `cross_source.py` (unknown codes pass through verbatim, forward-safe).
- `Metadata.security_type_coverage_pct: float | None` — Rule-18 coverage canary, modeled
  exactly on `dividend_coverage_pct`.
- `compute/config.py` `SCHEMA_VERSION` bump; `types.ts` + `schema-snapshot.json` mirrored;
  `schema_check` IN SYNC.

Ingest: extends the warm `yfinance_info` cache surface (same pattern as the #512 dividend
cache-read; zero new round-trips). `fetch_yfinance_security_type` pure cache-read;
`_yf_fast_exchange` widened to a 2-tuple `(exchange_code, quote_type)` (single caller
`fetch_yfinance_exchange` updated). `compute/main.py` Step-8 per-ticker populate + post-loop
coverage aggregation (mirrors dividend). Graceful try/except → `None` at every call site.

HONEST LIMIT — **ADR detection is `TODO(#541 PR-1b)`**: yfinance returns `EQUITY` for most
ADRs; the SEC override (`dei:DocumentType == "20-F"` OR EDGAR submissions-JSON `entityType`
= foreign private issuer) is deferred because `sec_health.py` doesn't cache the submissions
JSON (clean wiring needs a new round-trip / cache surface). PR-1 ships yfinance `quote_type`
as the primary signal with the override hook commented in `_QUOTE_TYPE_LABEL`.

Verify: ruff clean · `schema_check` IN SYNC · `tsc --noEmit` clean · `next build` 1512 static
pages · full offline pytest 2774 passed / 10 skipped (env-gated) / 0 failed (+17 new
`test_cross_source_security_type.py` CS_ST1–CS_ST10 + version-string updates in test_config /
test_warehouse). Gates: compute-builder (BUILT-CLEAN) + frontend-builder (types.ts + snapshot
regen, BUILT-CLEAN) + schema-sentinel (triple lockstep PASS). Follow-up: PR-2 wires the
`HeroAttributeTiles` "Type" tile after ≥ 1 sp1500 cron confirms `security_type_coverage_pct`.

---

## PR #TBD — ci(frontend): bump CI Node 20 → 22 (pairs @types/node 26 #560, in flight, 2026-06-22)

ci(frontend): bump the `Frontend (build)` job's `setup-node` pin from Node 20 to
Node 22 in `.github/workflows/ci.yml`. Node 20 reached end-of-life 2026-04-30, and
Dependabot PR #560 (`@types/node` 25.9.3 → 26.0.0) ships type definitions that
describe the Node 22+ API surface — keeping CI on Node 20 while the types describe
22 is the inconsistency the dependency-auditor flagged. Bumping CI to 22 aligns the
runtime with the type surface and clears an already-EOL LTS line. NO schema bump;
defense layer UNCHANGED; no compute/scoring/frontend-source change — workflow-only.
The `Unit tests (vitest)` + `Build (static export)` steps validate the bump on the
new runner. Sequencing: this PR merges first, then #560 (@types/node 26) merges on
top so the type bump never lands ahead of the runtime it describes. Chore-PR review
batch (this session): #559/#557/#556 already merged green; #561 (vitest 2→4) closed
(required `vite ^6` peer the project doesn't carry); #558 (pytest-cov <8) simulate
re-run pending.

---

## PR #TBD — ci(simulate): skip SEC health probe on Dependabot PRs via QR_SKIP_SEC_HEALTH (in flight, 2026-06-22)

ci(simulate): add `QR_SKIP_SEC_HEALTH: "1"` to the `env:` block of
`.github/workflows/pre-merge-prod-sim.yml`, alongside the five existing skip
vars (`FORM4_FETCH_SKIP` + `QR_SKIP_TIER2` + `QR_SKIP_FUNDAMENTALS` +
`QR_SKIP_OSAP` + `QR_SKIP_CROSS_SOURCE`). Fixes a pre-existing infra gap surfaced
by the #558 pytest-cov bump: Dependabot PRs pass the job's
`head.repo.full_name == github.repository` fork guard (they are not forks) but,
since GitHub's 2021 Dependabot secret-isolation change, cannot read repository
secrets — `secrets.EDGAR_USER_AGENT` expands to empty. `run_weekly_compute`
opens with a SEC health probe (`assert_sec_api_usable`) that hard-aborts on an
empty user-agent → RuntimeError → exit 1 → `COMPUTE_OUTCOME=failure` in ~90s, on
ANY Dependabot PR touching a `paths:` trigger file (e.g. `pyproject.toml`). The
probe is meaningless for simulate (synthetic/cached data, never a live SEC
fetch), so `QR_SKIP_SEC_HEALTH` (the documented `sec_health.py` escape hatch)
short-circuits it to a healthy `error="skipped"` result. ci-triage-engineer
classified #558's double `simulate` failure as infra-pre-existing, NOT caused by
the dep (which is `[dev]`-only, never installed by the job's `.[factors]`
install); #558 was merged as-is. NO schema bump; defense layer UNCHANGED;
workflow-only. Follow-up: a `docs/GOTCHAS.md` entry for the Dependabot
secret-isolation vs fork-guard mismatch may land in a later housekeeping pass.

---

## PR (frontend) — Security-type "Type" HeroAttributeTile wiring PR-2 (in flight, 2026-06-22)

UI follow-up (PR-2) to the security-type ingest #565 (issue #541) — mirrors the Dividend
tile PR-2 (#549). The stock-detail hero's 4-tile grid had tile #4 (Type) as the last
hardcoded "Coming soon" placeholder; it now shows `StockDetail.security_type` via a new
`formatSecurityType(securityType)` helper in `frontend/lib/format.ts`: the label verbatim
(`"Common stock"` / `"ETF"` / `"Fund"` / …, already mapped server-side by `_QUOTE_TYPE_LABEL`)
when present, `"—"` (em-dash) when null/empty. Tile #4 always renders FILLED now — the
"Coming soon" reserved state is no longer used by any tile, so the **4-tile hero grid
(Size / Sector / Dividend / Type) is complete**.

No `tabular-nums` (prose label, not numeric — unlike the Dividend tile). `securityType` prop
added; `app/stock/[ticker]/page.tsx` passes `detail.security_type`. Frontend-only — NO schema
change (the field exists from #565, schema `0.10.31-phase8pilot`; `types.ts`/snapshot
untouched). +8 vitest assertions (187/187).

Ships after cron #125 (sp1500, committed 2026-06-22) confirmed the Rule-18 gate:
`Metadata.security_type_coverage_pct = 40.09%` populates with CORRECT values (603 tickers
`"Common stock"`, the EQUITY→label mapping verified). Coverage is ~40% on the first cron
(warm-cache `quote_type` accumulation — the field is only captured on a fresh `_yf_fast_exchange`
fetch); `"—"` is the honest no-data state and climbs over future crons. (If coverage proves
stuck on the mtime-reset GHA cache, a `cache-v11-fast` key bump is the lever — tracked as a
follow-up, does NOT block the tile.)

Verify: `tsc --noEmit` clean · `next build` 1512 static pages · `vitest run` 187/187 (+8
`formatSecurityType`). Gate: frontend-builder (BUILT-CLEAN) + frontend-design-reviewer (pending).
Closes the Display-tiles (7b) UI half of CLAUDE.md §Next deliverable 5 — both hero tiles
(Dividend 7a + Type 7b) now live.

---

## PR (TBD) — fix(valuation): null median/mos_pct when valuation_methods_applicable == 0 (in flight, 2026-06-22)

EQH-class fair-price display fix. When **every** applicable fair-price method is itself flagged
`extreme_*_estimate` (so `valuation_methods_applicable == 0`), the untrimmed `median` was still
populated from the outlier values and `mos_pct` computed off it — producing absurd display
values (EQH = Equitable Holdings rendered `mos_pct = −2942.42%` on `/stock/EQH`: GAAP equity
$273M on $310B assets, AOCI-compressed insurance book; sole applicable method `multiples_pb`
gave $1.50 vs $45.50 market, correctly flagged `extreme_multiples_pb_estimate`). Found by the
stock-detail-auditor during the post-#570 warehouse-probe follow-up.

Fix (`compute/valuation/ensemble.py`): when `n_applicable == 0`, null `aggregates["median"]` +
`aggregates["mos_pct"]` before `EnsembleResult` construction — a Tier-1-style "null on corrupt
inputs rather than print garbage" guard, aligning the LIVE fields with `median_trimmed` (already
`None` at < 2 non-extreme survivors). **All other fields preserved** (per-method `value`s,
`extreme_*` warnings, `valuation_methods_applicable` itself, `low`/`high`/`max`) so the UI still
surfaces individual method outputs + their extreme annotations. **Display-only, ZERO scoring
impact** — `composite.py`/`pillars.py` never read `mos_pct`/`fair_price.median` (grep-proven);
`recommendation.py`/`loss_chance.py` accept `mos_pct` but already handle `None` gracefully.
**Schema triple UNTOUCHED** (`median`/`mos_pct` already `float | None`; `schema_check` IN SYNC).
The EMBC 2/3-extreme case (`valuation_methods_applicable == 1`, median still on the PE outlier)
is the separate #177 trimmed-median question — explicitly OUT OF SCOPE. Deeper methodology
follow-ups (P/B applicability guard for AOCI-compressed insurance equity + `EXTREME_MAJORITY_
THRESHOLD` for sub-6 method pools) tracked in issue **#572** for the Q3 2026-08-19 cohort audit.

Verify: ruff clean · `schema_check` IN SYNC · `pytest tests/test_valuation/ -m "not network"`
241 passed (+3 new `test_ensemble.py` section-N tests: N1 EQH-exact regression / N2 control
populated / N3 preservation invariant). Gate: compute-builder BUILT-CLEAN.

---

## PR #566 — fix(ingest): MC / pure-advisory IB revenue+shares extraction (in flight, 2026-06-22)

Closes the #566 data-quality gap surfaced by the first full sp1500 cron (#123, commit
`364ad003`) post-cron audit: MC (Moelis, sp600) rendered a `lean_bullish` recommendation with
`market_cap=null` + `fair_price=null` because BOTH `revenue` and `shares_outstanding` came back
null, and `fundamentals_unavailable` does not fire (8 other metrics present, so the snapshot is
non-null). Root cause (edgar-debugger): pure-advisory investment banks tag fee revenue under the
ASC 942 broker-dealer concept `us-gaap:NoninterestIncome` — absent from `_TTM_REVENUE_TAGS` — and
the per-filing XBRL shares fallback was gated on `revenue>0`, so a revenue-null snapshot never
recovered shares.

Two surgical ingest changes in `compute/ingest/fundamentals.py` (no schema change, no scoring
change, no new flag):
1. Add `us-gaap:NoninterestIncome` + `us-gaap:BrokerageCommissionsRevenue` as a NEW
   **fallback-only** chain `_TTM_REVENUE_ADVISORY_FALLBACK_TAGS` (deliberately NOT in the
   MAX-of-fresh `_TTM_REVENUE_TAGS`). New `_resolve_ttm_revenue` helper: standard chain via
   MAX-of-fresh FIRST; consult the ASC 942 fallback ONLY when no standard concept resolves a
   fresh value. **Precedence carve-out per methodology-scientist RATIFY-WITH-CONDITIONS (#571):**
   `NoninterestIncome` is a COMPONENT of `RevenuesNetOfInterestExpense` and exceeds the
   consolidated total whenever NetInterestIncome < 0 (net-interest-negative diversified banks,
   e.g. GS/MS/SCHW/RJF in an inverted-curve year) — an unguarded MAX chain would SILENTLY inflate
   their revenue + contaminate the value pillar / sector-peer fair-price median. Fallback-only
   confines the recovery to PURE-advisory filers (MC/EVR/HLI/PJT/LAZ) that tag revenue exclusively
   under the ASC 942 concept. Adversarial test pin added (consolidated 30B + larger NoninterestIncome
   50B → consolidated wins). `_TTM_REVENUE_TAGS` unchanged (OilAndGasRevenue-is-last preserved).
2. Drop the revenue condition from the per-filing XBRL shares-fallback guard:
   `revenue>0 AND total_assets>0` → `total_assets>0` ALONE, so a revenue-null-but-asset-present
   snapshot (the MC case) still reaches the shares fallback. Revenue presence is irrelevant to
   recovering shares; `total_assets>0` still blocks firing on a fully-empty/corrupt snapshot
   (assets=0 → no fire). (The two `test_fallback_does_not_fire_when_too_low_but_*` tests in
   `test_fundamentals.py` pinned the old AND-gate — the `revenue_zero` one is repurposed to assert
   the fallback now FIRES (the MC case); the `assets_zero` one is unchanged and still green.)

Blast radius (data-correctness improvement): EVR / HLI / PJT / LAZ and other pure-advisory
Financials that previously missed revenue. OUT OF SCOPE (deferred): the methodology-gated
annotate-before-veto guard for the "scoreable-but-shares-null" case (#566 item 3), MC
`MULTI_CLASS_SHARE_ALLOWLIST` (needs a live multi-class probe). Tests: new offline
`tests/test_ingest/test_advisory_revenue_tag.py` (tag-presence guard + advisory-only filer
resolves revenue + diversified-bank-consolidated-wins no-regression + OilAndGasRevenue-last
invariant). Local verify: `ruff check .` clean; full pytest deferred to CI (local env lacks
pandas). Real confirmation is the next sp1500 cron repopulating MC with non-null market_cap +
fair-price. Gate: orchestrator inline (compute-builder hit a session limit); recommend
quantrank-reviewer + methodology-scientist review on the MAX-of-fresh blast radius before merge.

---

## PR #TBD — feat(warehouse): SEC filing pointer index — Slice 1 (issue #579, in flight, 2026-06-22)

feat(warehouse): SEC filing pointer index foundation (Slice 1 of the Hybrid
filing-archive design, issue #579). OBSERVABILITY-FIRST / WRITE-ONLY (Rule 18):
the static site never reads `data/warehouse/`, there is NO read path, and this
slice DELIBERATELY does NOT wire into the weekday cron — it ships a module +
manual/dispatch backfill script ONLY, so the ~1500-ticker EDGAR enumeration cost
(~1500 submissions-JSON round-trips) can be measured before touching the cron's
critical path (same separate-script precedent as `scripts/backfill_warehouse.py`
vs the cron's Step-13.5 write). New `compute/warehouse/filing_index.py`
(`fetch_filing_index_rows` → one row/filing: `accession · cik · edgar_url ·
fetched_utc · filing_date · form_type · period_of_report · primary_doc_url ·
row_provenance · ticker`; default forms `{10-K, 10-Q, 8-K}`, widen via
`form_types=None`; graceful try/except → `[]` on any EDGAR error; honors the
empty-CIK gotcha). `writer.py` gains `write_filing_index_partition` (atomic
tmp+os.replace Parquet at `data/warehouse/filing_index/year=/run_date=/part-0.parquet`,
all-`large_string` schema). `warehouse_schema_check.py` gains
`derive_filing_index_columns` + `check_filing_index_schema` (the index gets the
warehouse's OWN drift guard via new baseline `data/warehouse/filing_index_schema.json`
— NOT the Pydantic↔TS↔snapshot triple). New `scripts/backfill_filing_index.py`
(manual entry; parallelizes across `EDGAR_MAX_WORKERS`; `QR_SKIP_FILING_INDEX=1`
opt-out; try/except non-fatal; canary summary). `.gitignore` whitelists
`!data/warehouse/filing_index/**/*.parquet` (forward partitions committed like
snapshots). +27 offline tests (`tests/test_warehouse/test_filing_index.py`).
NO schema-triple bump (warehouse is its own guard); defense layer UNCHANGED at 36;
rankings/scores/flags BYTE-IDENTICAL (no compute/main.py wiring). Verify: ruff
whole-repo `pass` · offline pytest `27 passed` (filing index) / `148 passed`
(full warehouse suite) · main schema triple in-sync. PR-review gate (this session,
pre-Mark-Ready): quantrank-reviewer (opus) READY-TO-PUSH, no FAIL · security-reviewer
PASS on all security surfaces (no secrets, EDGAR identity/rate-limit clean, gitignore
scoped, nothing ships to Vercel) · test-engineer COVERAGE-GAPS-FILLED (+6 graceful-
degradation / dry-run tests → 33 offline) · phase-coordinator Mode B doc-lockstep.
FOLLOW-UP edits folded in this PR per the gate: (1) CLAUDE.md §Layout + §Commands +
§Gotchas and AGENTS.md §Security-considerations document the new `filing_index`
module + `QR_SKIP_FILING_INDEX` opt-out (closes the security-reviewer doc FAIL +
Mode B lockstep); (2) the pre-existing #541 `security_type` flat-column drift in
`warehouse_schema.json` was regenerated (`--update`, +1 line) so the warehouse guard
is GREEN end-to-end (was short-circuiting red before the filing-index check) —
`filing_index_schema.json` baseline unchanged. Next slices (gated on owner
object-store decision in #579): Layer 2 lazy full-text archive + Layer 3 PIT-freeze,
then weekday-cron wiring after the EDGAR cost is measured.
## Housekeeping note — 2026-06-22 Mode C reconciliation (pre-v2.0)

This file is append-only — entries above are never deleted. The following
entries were "in flight" as of the last Mode C (#538, reconciled 0.10.29 /
Slice 7, 2026-06-21) but are now **MERGED on `main`**. Their detail has been
incorporated into `PHASE_STATUS.md` §Chronological history (2026-06-22 entry)
and the schema lineage in CLAUDE.md / AGENTS.md / SKILL.md.

Merged since the last Mode C:

- **#565** (squash `2c9dc1371`) — feat(compute): Security-type (Type) ingest PR-1 (schema 0.10.30→**0.10.31-phase8pilot**)
- **#564** (squash `62dbf4f89`) — feat(compute): Bonferroni multi-test shadow counter (schema 0.10.29→**0.10.30-phase8pilot**)
- **#548** (squash `e0ea07dc1`) — feat(frontend): infinite-scroll the ~1500-row ranking table (Slice 8 §8.3 gate)
- **#549** (squash `a7fd57b18`) — feat(frontend): Dividend tile PR-2 (live data)
- **#539 / #547 / #570** (squashes `b2e899159` / `bca926d9d` / `0b11f6415`) — research warehouse Slices 1/2 + per-method fp_* dtype fix
- **#555** (squash `100f0f549`) — fix(ingest): XBRL balance-sheet tag selection (HASI/LGIH/GPK)
- **#554** (squash `c38829362`) — fix(ingest): payout_ratio >20→None format-reversion guard
- **#553** (squash `dbf59ed26`) — ci(compute): timeout-minutes 240→270
- **#552** (squash `70b5f60fd`) — fix(compute): drop free-text post-split valuation_warning + DQIC docstrings
- **#537** (squash `a1a0bbc49`) — feat(frontend): Sold rows in Current-picks table
- **#533** (squash `3df2ba5f8`) — fix(ingest): dividend ×100 double-scaling removal + >100 guard
- **#546** — docs: groom Next deliverables + scaffold Slice 8 issues
- **#556 / #557 / #559 / #560 / #575** — dependabot + CI Node 20→22 bumps

**Currently in flight (as of 2026-06-22):**

- **v2.0 release PR** (`claude/release-v2.0.0-phase8`) — `pyproject` 1.4.0→2.0.0
  + `docs/release-notes/v2.0.0-phase8.md` + the Mode C doc reconciliation above.
  All Phase 8 WORKFLOW.md acceptance gates met; `release-captain` owns the
  `v2.0.0-phase8` tag (DRAFT PR; HOLD the tag until ≥1 green scheduled sp1500
  cron). Deferred post-v2.0: `low_liquidity` annotate→veto promotion (#544,
  KEEP-ANNOTATE for v2.0) + Bonferroni provisional-threshold re-derivation (#542).
## PR (roadmap-restructure) — chronological tags + Lane A/B + §Current-state reconcile (in flight, 2026-06-22)

Docs-only roadmap restructure on branch `claude/roadmap-restructure-2lane`. NO code /
schema / workflow change. Built on a 100%-verified fact sweep (git tags + live GitHub
issues + `compute/config.py` SCHEMA_VERSION) — the prior `PHASE_STATUS.md` §Current
state was ~2 schema bumps stale (read 0.10.29; real is `0.10.31-phase8pilot`).

Three structural fixes to the "version-leapfrog + jumping-around" friction the owner
flagged:
1. **Tags decoupled from phase numbers → chronological.** Next tag = `v2.0` regardless
   of phase; `v1.1.0-phase4` is declared RETIRED/superseded (it sits below the live
   `v1.4` because Phase 4.5/4.6 were tagged first while Phase 4's factor-integration
   gate stayed open-ended) — its #113/#120 work lands in the then-current tag when the
   cron IC clears. `v1.5.0` folded into the Q3 evidence harvest.
2. **Two-lane §Next deliverables.** Lane A = Ship-now (deterministic: #569/#567/#568/
   #574/#550/#551/#259/#478/#41/#455/#137); Lane B = Evidence-gated (#544/#581/#130/
   #454/#484/#461/#562/#113/#120/#122/#260/#563/#579) carrying a data-ready date, OFF
   the tag critical path.
3. **One evidence checkpoint** — the Lane-B cohort items converge on the Q3 2026-08-19
   audit (#130) as a single harvest, not scattered "rate-after-1-cron" blockers.

Edits: `PHASE_STATUS.md` §Next deliverables (full 2-lane rewrite + release ladder +
phase-position) + §Current state (schema 0.10.29→0.10.31 reconcile + date + merged-
since-#534 list) + retired the stale 2026-06-10 inline Open-issues snapshot (GitHub is
canonical); CLAUDE.md + AGENTS.md schema headlines reconciled to 0.10.31 (lockstep);
housekeeping: closed #541 + #543 (work merged via #565/#578 + #549 but never closed).
Verify: docs-only diff; CLAUDE.md + AGENTS.md both moved (lockstep). Gate: docs-reviewer
+ orchestrator; DRAFT PR for review before merge.

**Rebase reconciliation (2026-06-22, vs `origin/main`):** rebased after **#577 cut
`v2.0.0-phase8`** + #580 (SEC filing-index Slice 1) landed. Two reconciles folded in:
(1) the §Next-deliverables Release ladder updated from "next = v2.0" → **"v2.0.0-phase8
SHIPPED (#577) · next = v2.1"** (v2.0 is no longer the upcoming tag); (2) the CLAUDE.md
+ AGENTS.md schema-headline edits were SUPERSEDED by #577's fuller release reconcile
(both already read `0.10.31`) — this PR keeps main's headlines, dropping the redundant
lighter edit. The 2-lane backlog + retire-v1.1 + §Current-state reconcile remain this
PR's substance.

---

## PR (ci-efficiency) — GitHub Actions efficiency pass (in flight, 2026-06-22)

CI-only workflow efficiency pass (no compute/frontend/schema change), from a read-only
`general-purpose` audit of `.github/workflows/`. Headline waste removed: a version/dep/docs
PR could trigger the `pre-merge-prod-sim` `simulate` job (paths included `pyproject.toml`),
which then ran a COLD sp1500 compute ~204 min; and `ci.yml` ran the full ~20-min pytest on
every PR regardless of changed paths.

Changes:
1. **`pre-merge-prod-sim.yml`** — drop `pyproject.toml` from the `on.pull_request.paths`
   trigger. The sim is informational-only + NOT a required check, so a version/dep bump no
   longer pays a ~200-min cold sim.
2. **`ci.yml`** — (a) add a workflow-level `concurrency` group (`cancel-in-progress` on PR
   refs only) so re-pushes cancel stale ~20-min runs instead of stacking; (b) add
   `dorny/paths-filter@v3` to BOTH jobs with a **job-internal skip** — the job always runs
   (required check stays green) but the heavy steps are gated: pytest skips when no
   `compute/**`/`tests/**`/`tools/**`/`pyproject.toml` change (ruff + the doc/model/schema
   guards STILL run, so the doc-test-count guard fires on doc edits), and the frontend
   vitest+build skip when no `frontend/**` change; (c) `pytest -v` → `pytest -q`; (d) add
   `cache: npm` to the frontend `setup-node`.
3. **`compute-monthly.yml`** — disable the no-op monthly `schedule:` (keep `workflow_dispatch`)
   + drop the unused `pip install`; **`manual-trigger.yml`** — drop the unused `pip install`
   (both are Phase-0 echo-only stubs).

New third-party action: `dorny/paths-filter@v3` (widely-used, reputable) — flagged for
`security-reviewer`. YAML validated (`yaml.safe_load` all four). Lockstep: this entry.
Gate: security-reviewer (workflow + new action) before Mark-Ready; DRAFT PR.

---

## PR (ci-sha-pin) — SHA-pin the third-party dorny/paths-filter action (in flight, 2026-06-22)

CI hardening follow-up to #583 (the `security-reviewer` GO-WITH-CONDITIONS recommendation).
SHA-pins the ONE genuinely third-party action — `dorny/paths-filter` — in both `ci.yml`
jobs: `@v3` → `@d1c1ffe0248fe513906c8e24db8ea791d46f8590 # v3.0.3`. The SHA was
cross-verified from two independent GitHub HTML pages (the `releases/tag/v3` page + the
`commits/v3` page both report `d1c1ffe…` = "Update CHANGELOG for v3.0.3", 2026-03-12);
api.github.com is 403 in the CI env so the authoritative JSON ref wasn't available — the
double-page cross-check is the substitute. The `# v3.0.3` trailing comment keeps Dependabot's
`github-actions` ecosystem able to bump the pin.

SCOPE: only the third-party action is pinned. The first-party `actions/*` actions
(checkout/setup-python/setup-node/cache/upload-artifact/github-script) stay on Dependabot-managed
`@vN` tags — same GitHub org as the runner, low supply-chain risk, and the reviewer-endorsed
"consistent posture". (Pinning those too is deferred — it needs authoritative SHA resolution the
403'd env can't provide reliably; a future `gh`/API-enabled chore can do the uniform set.)

CI-only, no code/schema/compute change. YAML validated. Lockstep: this entry. Gate: the prior
#583 security review already cleared dorny/paths-filter; this is its recommended pin.

---

## PR (ci-sha-pin-actions) — SHA-pin all remaining first-party actions/* (in flight, 2026-06-22)

Completes the uniform SHA-pin hardening (follow-up to #584 which pinned the third-party
dorny/paths-filter). Pins all 25 remaining `actions/*` `uses:` across the 8 workflows to
verified commit SHAs (`@vN` → `@<40-hex> # vN`), so the OpenSSF "pinned-dependencies"
posture is uniform across the whole workflow set:

- `actions/checkout@v7`        → `9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0`  (v7.0.0, ×7)
- `actions/setup-python@v6`    → `a309ff8b426b58ec0e2a45f0f869d46889d02405`  (v6.2.0, ×6)
- `actions/setup-node@v6`      → `48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e`  (v6.4.0, ×1)
- `actions/cache@v5` + `/restore@v5` → `27d5ce7f107fe9357f9df03efb73ab90386fccae` (v5.0.5, ×8)
- `actions/upload-artifact@v7` → `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`  (v7.0.1, ×2)
- `actions/github-script@v9`   → `3a2844b7e9c422d3c10d287c895573f7108da1b3`  (v9.0.0, ×1)

Every SHA was **cross-verified from TWO independent github.com HTML pages** (`commits/<tag>`
top commit + the `releases`/`tags` page) — api.github.com is 403 in this env so the
double-page agreement substitutes for the authoritative ref JSON (one mis-read outlier on
setup-node was caught and discarded). The `# vN` trailing comments keep Dependabot's
`github-actions` ecosystem able to bump every pin.

CI-only, no code/schema/compute change; YAML validated (`yaml.safe_load` all 8). The PR's own
CI run is the live validation that every pinned SHA resolves. Lockstep: this entry.
Gate: security-reviewer (workflow-wide pin) before Mark-Ready; DRAFT PR.
## PR #587 — `extreme_estimate_majority` low-applicability floor (issue #587, in flight 2026-06-23)

**Branch:** `claude/issue-587-extreme-majority-floor`
**Schema:** `0.10.31-phase8pilot` → **`0.10.32-phase8pilot`**
**Rule 16 invariant:** annotate-only — no composite change, no veto, no Top-5 suppression
**Defense layer:** UNCHANGED at 36

**Summary:** RE-BASE-WITH-FLOOR recalibration of the `extreme_estimate_majority` annotate.
The S&P 1500 small-cap cutover exposed a false-negative dead-zone: tickers with ≤ 3
applicable ensemble methods could have a strict majority be extreme (GFF MoS −1143.9% /
SMTC −938.7%: 2 of 3 applicable) without reaching the 3-of-6 baseline threshold.

**Changes (compute/** only, per ownership contract):**
- `compute/config.py` — 2 new constants (`EXTREME_MAJORITY_LOWAPP_MAX=3` /
  `EXTREME_MAJORITY_LOWAPP_MIN=2`) + schema version bump to `0.10.32-phase8pilot`
- `compute/valuation/ensemble.py` — new `_extreme_majority_fires(n_extreme, n_applicable) -> bool`
  pure helper (directly pinnable by test-engineer); `EnsembleResult.extreme_majority_lowapp: bool`
  per-ticker signal; firing site updated to use the helper (OR logic: baseline 3-of-6 OR
  low-applicability floor)
- `compute/output/schemas.py` — new `Metadata.extreme_estimate_majority_lowapp_count: int | None`
  (Rule-18 counter for floor-only delta fires)
- `compute/main.py` — counter init + per-ticker increment + Metadata wiring
- `frontend/lib/types.ts` — mirror `extreme_estimate_majority_lowapp_count?: number | null`
- `frontend/lib/schema-snapshot.json` — regenerated via `--update-snapshot`
- `docs/METHODOLOGY.md` — `extreme_estimate_majority` section expanded with floor rationale
- `SKILL.md` — `0.10.32-phase8pilot` row added to schema-version table
- `tests/test_config.py` — schema version pin updated to `0.10.32-phase8pilot`

**Replay validation (cron 8c89a5af0 ground truth):**
- Old-rule fires: 56 ✓
- New-rule fires: 72 ✓
- Floor-only delta: 16 ✓ (GFF, SMTC, DD, NRG, LGIH, GEV, BILL, TTWO, HASI, HIMS,
  CRWD, MSGS, NABL, CHTR, COKE, EMBC — exact match)

**Verify:** ruff PASS · pytest offline PASS (K1-K9 green; `test_C1_alpha158` is a
pre-existing Hypothesis DeadlineExceeded timing flake — fails identically on pre-change
`main`) · schema_check PASS (IN SYNC)

**Coverage needed (for test-engineer):**
- Pin `_extreme_majority_fires(2, 3)` → True (2-of-3 strict-majority floor)
- Pin `_extreme_majority_fires(2, 2)` → True (2-of-2 all-extreme)
- Pin `_extreme_majority_fires(1, 2)` → False (1-of-2, below LOWAPP_MIN=2)
- Pin `_extreme_majority_fires(1, 3)` → False (1-of-3, below LOWAPP_MIN=2 AND not majority)
- Pin `_extreme_majority_fires(2, 4)` → False (floor excluded: n_applicable=4 > LOWAPP_MAX=3)
- Pin `_extreme_majority_fires(3, 4)` → True (baseline 3-of-6 rule still fires regardless of n_applicable)
- Integration: full ensemble with 2-of-3-applicable extreme → `extreme_estimate_majority` fires + `extreme_majority_lowapp=True`
- Integration: full ensemble with 1-of-3-applicable extreme → flag silent
- Integration: full ensemble with 3-of-6-applicable extreme → flag fires + `extreme_majority_lowapp=False` (baseline, not floor)
- `EnsembleResult.extreme_majority_lowapp` is False when flag did not fire
- Metadata counter increments only for floor-only fires, not baseline fires

**Next:** test-engineer for K10+ coverage, then quantrank-reviewer for gate.

---

## PR (claude/sp1500-frontend-polish) — SP1500 universe label + a11y skip-link (#550, #551) (in flight, 2026-06-23)

Two small frontend polish fixes, NO schema change, NO compute change.

**Issue #550 — `universeLabel()` missing SP1500 case** (`frontend/lib/visual.ts` line ~228):
`universeLabel()` had no case for `SP1500` / `SP1500-probe`, so the live
`Metadata.universe = "SP1500"` heading rendered the raw string "SP1500 ranking".
Fix: `if (universe.startsWith('SP1500')) return 'S&P 1500';` inserted BEFORE the SP500 check
to avoid any startsWith/substring ordering pitfall. Covers both `SP1500` (live cron since
Slice 7 #534) and `SP1500-probe` (Slice-2 label from manual dispatch runs).

**Issue #551 — a11y skip-link to the "Load more" button** (`frontend/components/RankingTable.tsx`):
With ~1500 rows split into 50-row batches, a keyboard user must Tab through every row link
before reaching the "Show 50 more" button (WCAG 2.4.1 Bypass Blocks violation). Fix:
(1) A `sr-only` skip-link "Skip to load more" appears on `:focus-visible` between the search
toolbar and the first row, focusing `loadMoreButtonRef.current` via `onClick` — no visible
chrome unless the link has keyboard focus. (2) The load-more `<div>` gains `id="ranking-load-more"`,
`role="region"`, and `aria-label="Load more stocks"` so screen-reader users can jump to it
directly from the landmarks list (JAWS/NVDA "R" key). Both are gated on `hasMore` (no-ops
when all rows are shown). The button receives `ref={loadMoreButtonRef}`. No design-system
tokens added; `sr-only` + `focus:not-sr-only` is Tailwind built-in; the focused skip-link
uses the emerald-700 border + emerald-800 text (LedgerCraft brand positive) with paired
`dark:` variants.

Frontend-only, NO schema bump, defense layer UNCHANGED at 36. Lockstep: this entry.

---

## PR (fix/ccc-zerodiv-guard) — guard cash_conversion_cycle denormal-COGS divide-by-zero (issue #574, in flight, 2026-06-23)

Bug: `compute/features/profitability.py::cash_conversion_cycle` divided by
`snap.revenue / 365` on the DSO leg without guarding against IEEE-754 underflow.
A denormal `revenue=5e-324` causes `revenue / 365 → 0.0` → `ZeroDivisionError`.
The COGS fallback to revenue means the same underflow could hit the DIO/DPO legs too.

Fix: compute `daily_revenue = snap.revenue / 365` and `daily_cogs = cogs / 365` once
each; guard both with `if not <daily>: return float("nan")` (falsy catches 0.0 / underflow).
Normal-path semantics are byte-identical. Regression pinned as an explicit `@example` on
the existing Hypothesis test `test_cash_conversion_cycle_never_raises` (issue #574 falsifying
example: `revenue=5e-324, accounts_receivable=None, inventory=0.0, accounts_payable=None,
cost_of_revenue=None`) so CI finds it from a cold Hypothesis DB.

SCOPE: `compute/features/profitability.py` (observability factor layer, Rule 18 — NOT
production scoring, NOT the defense layer). `tests/test_features/test_features_none_propagation.py`
(pinned regression). NO schema change. Defense layer UNCHANGED at 36.

Lockstep: this entry.

---

## PR (ingest-cik-shares-fix) — NE stale-CIK override + shares-path form-type filter (in flight, 2026-06-23)

Two compute/ingest data-quality fixes on one branch (issues #567 + #569). NO schema change.
Defense layer UNCHANGED at 36. Rankings/scores/flags unaffected until NE is re-fetched on
the next cron with the corrected CIK.

**Fix 1 (#567) — NE stale-CIK override:**
edgartools' bundled `company_tickers.parquet` maps ticker `NE` to the pre-bankruptcy Noble
Corp entity (CIK 1458891, last 10-Q 2020-06-30). The current Noble Corporation plc
(post-2021 Ch.11 + Maersk Drilling merger) is CIK 0001895262, verified against live SEC
`company_tickers.json` + `data.sec.gov/submissions/CIK0001895262.json` (10-K filed 2026-02-12).

Three-part fix: (a) `compute/config.py` — new `TICKER_CIK_OVERRIDES: dict[str, str]` dict
near `MULTI_CLASS_OVERCOUNT_ALLOWLIST`, with `"NE": "0001895262"` as the anchor entry.
(b) `compute/ingest/universe.py::_resolve_cik_for_midcap` — checks the override FIRST,
before the edgartools `Company(ticker)` lookup; returns the override CIK directly when
present (edgartools call skipped entirely for NE). (c) `compute/ingest/fundamentals.py::
fetch_fundamentals` — applies `config.TICKER_CIK_OVERRIDES.get(ticker.upper(), cik) or cik`
immediately after `_require_identity()` so that a stale CIK passed in from the universe
layer is corrected before the cache-load, filing-precheck, and `_build_snapshot` call.

FUN and SMC were NOT added — those need separate live verification (deferred to follow-up).

**Fix 2 (#569) — shares-path form-type filter:**
`_try_balance_tags_most_recent` previously used a bare `facts.get_fact(tag)` with no
form-type filter — the same sort-key trap PR #555 fixed for USD balance items in
`_try_balance_tags`. The fix mirrors the REAL `get_all_facts()` API used by `_try_balance_tags`
(confirmed in the installed edgartools; NOT the pseudocode `get_all_facts()` the debugger
assumed — it IS the public API). Three-tier structure:
  Tier 1 — `_BALANCE_SHEET_FORM_TYPES` + unit `"shares"` + most-recent `period_end` wins
  Tier 2 — unit `"shares"`, any form-type (odd-filer safety net)
  Tier 3 — original `get_fact()` fallback (backward-compat; only fires if Tier 1+2 are empty)

BKNG CAVEAT: BKNG's ~774M shares come from a DEI tag in a valid **10-Q** filing (which
passes the form filter). This fix does NOT change BKNG — its post-split count is defended by
the existing `post_split_share_lag` veto (#499). Do NOT add a per-ticker guard here.

This PR closes the 8-K/S-type/DEI cover-page contaminant gap for OTHER tickers (e.g. where
an 8-K cover-page `EntityCommonStockSharesOutstanding` fact filed more recently would have
previously won by recency over the consolidated 10-Q value).

New test file: `tests/test_ingest/test_cik_override_and_shares_filter.py` (17 tests, all
offline). Verified: `ruff check .` clean · ingest suite 638 passed · full offline suite
2855 passed, 0 failures.

---

## PR (claude/annual-returns-layout-566vaf) — AI-pick home layout: full-width Current picks + Annual returns | Performance grid (in flight, 2026-06-23)

Frontend-only layout restructure of the AI-pick home (`AiPickPortfolio.tsx`,
both the adaptive and the legacy slider branch, applied symmetrically). The
"Current picks" card is lifted OUT of the 2-col grid it previously shared with
`AnnualReturnsTable` and now renders FULL-WIDTH on top. Below it, a new
`md:grid-cols-2` returns grid pairs `AnnualReturnsTable` (left) with a new
`PerformanceTable` (right). New vertical order per branch: headline/chart card
→ Current picks (full width) → Annual returns | Performance → HoldingsTimeline
→ footer CTA/disclaimer.

New component `frontend/components/PerformanceTable.tsx` (a Seeking-Alpha-style
trailing-period table) structurally mirrors `AnnualReturnsTable` (same Props,
helpers, design tokens) but shows 9 TRAILING-PERIOD returns — 1M / 3M / 6M / 9M
/ YTD / 1Y / 3Y / 5Y / 10Y — for the portfolio vs the benchmark. Each window =
`lastFin(series) / navAtOrBefore(window-start) − 1` (UTC-safe `setUTCMonth` /
`setUTCFullYear` date math; YTD base = prior year-end NAV, falling back to
inception when history starts in the current year). Windows that predate
inception (e.g. 10Y on a ~9.9y backtest) render "—" honestly, no clamping. No
CAGR/TOTAL footer row. All figures derive in-browser from the same NAV series
the page already ships — no schema/compute change. (An intermediate
`TotalReturnTable` cumulative-per-year variant was built then replaced by this
Performance table in the same branch before merge.)

SCOPE: `frontend/components/AiPickPortfolio.tsx` + new
`frontend/components/PerformanceTable.tsx`. NO schema change (triple untouched).
Defense layer UNCHANGED at 36. Verified: `tsc --noEmit` clean + `next build`
(1512 static pages).

Lockstep: this entry.

---

## PR (claude/annual-returns-layout-566vaf) — Current picks weight column sums to exactly 100% (Hamilton apportionment) (in flight, 2026-06-23)

Frontend-only display fix. The AI-pick home "Current picks" table rendered each
holding's weight with an independent `(weight * 100).toFixed(1)` — the raw
inverse-vol weights sum to exactly 1.0, but per-row 1-decimal rounding drifts
the VISIBLE column to 99.9 / 100.1 / 100.2% (21 of 40 backtest rebalances),
which reads as "~101%". The data was always correct; only the rendering drifted.

Fix: a module-level `apportionWeightLabels(weights)` helper in
`AiPickPortfolio.tsx` applies largest-remainder (Hamilton) apportionment to
tenths-of-a-percent so the displayed labels sum to exactly the basket total
(100.0% for a normalized book; non-finite weights render '—' and are excluded,
target honestly tracks the finite-weight sum). Wired in BOTH branches (adaptive
`weightSortedHoldings` + slider `holdings`) via a `useMemo`. Sold rows untouched
(already literal '—'). Verified the apportionment yields exactly 100.0% on all
40 rebalances.

ROOT CAUSE (2nd commit): the real corruption was UPSTREAM in `frontend/lib/data.ts`
— the adaptive `weight` field was passed through `round2` (2dp: 0.207 -> 0.21),
so the basket already summed to ~1.01 before the display layer saw it, and the
Hamilton helper faithfully reproduced that 1.01 (showed 21.0/10.0/... = 101.0%).
Fix: a new `roundWeight` helper (6dp) replaces `round2` on the two adaptive
weight assignments (latest-holdings + band-book), keeping the raw inverse-vol
weights summing to 1.0 so the apportionment lands on exactly 100.0%. Verified
OLD path 101.0% vs NEW path 100.0% on the latest basket; 0/40 rebalances drift.

SOLD-ROW SCORE (3rd commit): the Current-picks "Sold" rows showed `—` for score;
they now show the rotated-out name's CURRENT composite score (consistent with the
Held/New rows). New frontend-only `AiPickData.latestScores: Record<string, number>`
(built from the latest rebalance's `full_ranked` in `data.ts`); the adaptive
Sold row reads `data.latestScores[ticker].toFixed(1)` (em-dash fallback). Weight
cell stays `0.0%` (sold names have no weight). `AiPickData` is a frontend-only
view model — NOT the Pydantic↔TS↔snapshot triple, so no schema_check.

WEIGHT-CHANGE COLUMN (later commit): a new "Change" column after Weight shows the
relative weight delta vs the PRIOR quarter — New = ↑100.00% (emerald), Sold =
↓−100.00% (rose), Held = ↑/↓ (cur−prior)/prior (emerald/rose), no-change = →0.00%
(slate). New frontend-only `AiPickData.priorWeights: Record<string, number>` (from
the second-to-last rebalance's `band_weights`/`weights_by_count`) + a `weightChange`
helper in `AiPickPortfolio.tsx`, rendered on both holding + sold rows (adaptive
branch only). Mobile note: the extra `w-20` column is tight at ~360px (sector
already hidden on mobile); revisit width/format if it crowds.

SCOPE: `frontend/components/AiPickPortfolio.tsx` + `frontend/lib/data.ts` +
`frontend/lib/types.ts`. NO schema change (triple untouched). Defense layer
UNCHANGED at 36. Verified: `tsc --noEmit` clean + `next build` (1512 static pages).

Lockstep: this entry.

---

## PR — Current-picks adaptive branch: Score column → Return column (in flight, 2026-06-23)

**Branch**: `claude/current-picks-return-calc-h48u3x`
**Type**: feat(frontend) — display-only; no schema change, no compute change.

Replaces the Score column in the adaptive branch (`AiPickAdaptiveBranch`) of
the "Current picks" table with a Return column showing each holding's total
return since it entered the basket. The slider branch (`AiPickSliderBranch`)
already has a Return column and is unchanged.

**Changes**:
- `frontend/components/AiPickPortfolio.tsx`: header label "Score"→"Return";
  Return track widened 3.25rem→4.25rem in BOTH the header grid and every `<li>`
  (held/new AND sold rows, both mobile 6-track and sm+ 7-track templates);
  new `adaptivePlSince` `useMemo` keyed on `[timeline, weightSortedHoldings,
  soldRows, data.entryCloses, data.lastCloses]` — for held/new rows walks
  timeline backward via `heldSetForEntry()` to find the streak-start index
  (entry→today), for sold rows walks backward within the prior basket to find
  the streak-start index then compares to the sell rebalance close (entry→exit);
  Return cell renders `pctStr` + `toneClass` with `font-semibold` matching the
  slider branch; sold-row Return cell carries full emerald/rose tone (it is the
  row's headline). Caption `<p>` appended: "Return = total return since each
  holding entered the basket (sold names: through their exit rebalance)." The
  now-unused `data.latestScores[s.ticker]` read on sold rows is removed (the
  field itself remains in `AiPickData` as it may be used elsewhere).
- `frontend/lib/data.ts`: extends `entryCloses`/`lastCloses` price-coverage loop
  to include the prior rebalance's basket tickers (via the same
  `band_weights`/`weights_by_count` derivation as the `priorWeights` block),
  so sold-ticker return through their exit date is computable. Additive — existing
  held-ticker behavior is byte-identical. Guard: only runs when `rebalances.length >= 2`.

**Schema triple**: untouched. `entryCloses`/`lastCloses`/`latestScores`/
`priorWeights` are frontend-only view-model fields on `AiPickData`, NOT part of
the Pydantic↔TS↔snapshot triple. No `schema_check` run required.

Rankings/scores/defense layer: byte-identical (display-only change).

**Follow-up (2026-06-23) — UI declutter on same branch**: Removed the
redundant "Change" column (arrows + ±100% text) from the adaptive "Current
picks" table — the Status chip (New/Held/Sold) already conveys the same
information and competed visually with the colored Return column. Changes:
- Dropped the trailing `_4.5rem` Change track from all three grid containers
  (header, held/new `<li>`, sold `<li>`); mobile is now 5-track, sm+ 6-track.
- Removed the `<span className="text-right">Change</span>` header cell.
- Removed the Change-IIFE trailing cell from both held/new and sold `<li>`s.
- Removed the now-unused `weightChange` helper function (and its doc comment)
  after confirming zero remaining references (`grep weightChange` → 0 hits).
- Trimmed the picks-card caption `<p>`: removed the score-threshold `isBand ?
  (...) : (...)` clause (redundant with the larger basket-rule paragraph
  above); kept the "AI-sized basket — N stocks this quarter,
  inverse-volatility weighted." opener, the "Top sector: X — n of N." clause,
  and the "Return = total return..." sentence.
- No schema change; `data.priorWeights` field in `AiPickData` / `data.ts`
  untouched (view-model field, harmless now unreferenced in this component).

Lockstep: this entry.

---

### Follow-up 2 — Performance table "Max" → "Total return" (2026-06-23)

Renamed the trailing-period `PerformanceTable` since-inception row label from
`Max` to `Total return` (clearer — that row IS the full-window total return).
Label-string only; no logic / type / schema change.

Lockstep: this entry.

---

### Follow-up 3 — Performance "Total return" highlighted footer (2026-06-23)

Broke the since-inception "Total return" row out of the trailing `<tbody>`
into a highlighted `<tfoot>` — `border-t-2 border-slate-200 bg-slate-50
dark:border-slate-700 dark:bg-slate-800/50`, uppercase label, bold portfolio
value — mirroring AnnualReturnsTable's CAGR footer so the two side-by-side
cards read as a family. Presentation only; row values unchanged.

Lockstep: this entry.

---

## PR (TBD) — feat(compute): value_trap_risk two-factor LSV shadow counter (in flight, 2026-06-23)

Issue #586 PR-1 (shadow). The live `value_trap_risk` annotate over-fires on **36.4%** of the
S&P 1500 (`Metadata.value_trap_risk_count_with_sector_coe = 548`) vs a < 10% academic band,
because it fires on a SINGLE leg — Penman 2013 `avg_3y_roe <= Ke` (a RIM-applicability condition
*misnamed* as an LSV value-trap signal). The over-fire is dominated by loss-making / pre-revenue
growth (IT 50% / Health Care 50% fire rate) whose ROE is structurally negative — the opposite of
an LSV cheap-and-deteriorating trap. methodology-scientist RATIFY-WITH-AMENDMENT: add the LSV 1994
"cheap" leg — emit the warning only when ROE<=Ke AND trailing P/E (eps_ttm>0) is below the stock's
sector-peer median P/E; loss-making/undefined-P/E firms are EXEMPT. data-scientist measured the
two-factor P/E gate at ~10.2%; literature-searcher confirmed AF-2013 ("Devil in HML's Details")
carries zero value-trap content (drop from the SKILL.md anchor) and LSV-1994 substantiates a
5-12% tail band.

This PR ships OBSERVABILITY-ONLY (Rule 18): new `Metadata.value_trap_risk_two_factor_shadow_count:
int | None` counts the two-factor gate WITHOUT touching live emission — live `valuation_warnings`
for every ticker is BYTE-IDENTICAL (the shadow gate is a strict subset of the live single-leg
count). Schema bump `0.10.31` -> `0.10.32-phase8pilot` (schema triple in lockstep:
schemas.py + types.ts + snapshot regen, `schema_check` IN SYNC). `check_rim_applicability`
docstring rewritten to separate the (unchanged) Penman RIM method-skip from the legacy single-leg
warning and the shadow two-factor gate. The RIM method-skip at `<= Ke` is UNCHANGED (correct
Penman). Defense layer UNCHANGED at 36 (shadow counter, not a flag).

Rollout gate: a follow-up PR-2 flips the live emission to the two-factor gate ONLY after >=1
sp1500 cron confirms the shadow count lands in the 5-12% band (75-180 names), and reconciles the
quarterly-cohort-audit SKILL.md + docs/METHODOLOGY.md to a single LSV-1994 anchor + 5-12% band
(dropping the unsubstantiated Asness-Frazzini 2013 cite). Warehouse `flatten.py` ROE-trajectory
diagnostics (`diag_avg_3y_roe` / `diag_roe_3y_slope` / `diag_pe_ttm` / `diag_sector_median_pe`)
were SCOPED OUT of PR-1 (all-None stubs would land an unstable NoneType warehouse dtype — same
class as the #570 dtype-lock fix); they ship in the wiring PR with real float64 values.

Verify: ruff clean · `schema_check` IN SYNC · `tsc --noEmit` clean · `pytest tests/test_valuation/
tests/test_warehouse/ tests/test_config.py tests/test_output/test_schema_check.py -m "not network"`
446 passed (+13 new `test_value_trap_shadow.py`: S1 loss-maker-exempt ×4 / S2 cheap-below-hurdle
fires ×2 / S3 premium-P/E or empty-panel does-not-fire ×3 / S4 live single-leg warning unchanged
×4). Gates: methodology-scientist RATIFY-WITH-AMENDMENT + literature-searcher CITATION-CONFIRMED +
data-scientist evidence + compute-builder BUILT-CLEAN; quantrank-reviewer at the push gate.

---

## PR (TBD) — feat(compute): warehouse coverage extension — full Metadata + AI-pick portfolio capture (in flight, 2026-06-24)

Branch `claude/warehouse-home-ai-data-353brg`. Closes two confirmed warehouse coverage
gaps surfaced by a data-pipeline audit (the warehouse captured per-ticker rankings/scoring
in full but persisted only 5 manifest fields and ZERO portfolio/AI-pick state). Extends
`compute/warehouse/` in two directions:

1. **Full-run Metadata persistence** — `_manifest.parquet` now stores the complete
   run-level `Metadata` as an additive `metadata_json` string column
   (`model_dump(mode="json")`). The prior inline scalar columns are retained; the JSON
   blob is forward-safe (future `Metadata` fields flow through with no column-list edit);
   serialization failure degrades to `None` + warning. `warehouse_schema_check.py` +
   the regenerated `warehouse_schema.json` baseline track the new column.

2. **AI-pick portfolio artifact capture** — new `compute/warehouse/portfolio_writer.py`
   reads the home AI-pick artifact `frontend/public/data/portfolio/backtest_pit.json` at
   Step 13.5b and writes per-rebalance×holding rows (incl. `weight_default` +
   `holding_json`/`rebalance_json` blobs) into a committed Hive partition
   `data/warehouse/portfolio/year=/run_date=/part-0.parquet` + a flat
   `portfolio_manifest.parquet` (run-level meta/nav blobs). `.gitignore` whitelists both;
   guarded by `warehouse_schema_check.py`'s own `portfolio_partition_schema.json` (11 cols)
   + `portfolio_manifest_schema.json` (5 cols) baselines. Write-only/offline research store
   — the static site NEVER reads it from the warehouse. Absent/malformed artifact degrades
   to 0 rows (never raises); `QR_SKIP_WAREHOUSE=1` skips it alongside the snapshot; the
   Step-13.5b try/except keeps it non-fatal so it never blocks the cron.

Schema triple (`schemas.py` / `types.ts` / `schema-snapshot.json`) UNTOUCHED — the
warehouse is guarded by its own drift checker, not the Pydantic↔TS↔snapshot triple.
Defense layer UNCHANGED at 36. NO schema-version bump (warehouse is not the Pydantic
triple). Rankings/scores/flags BYTE-IDENTICAL (write-only observability extension).
21 new tests (`tests/test_warehouse/test_warehouse_new_gaps.py`: M1-M4 manifest metadata,
P1-P13 portfolio writer + graceful no-op + drift).

Lockstep: this entry + CLAUDE.md §Gotchas warehouse bullet (manifest-Metadata +
portfolio-capture sentences appended) + AGENTS.md `QR_SKIP_WAREHOUSE=1` block (mirror)
updated in parallel.

Verify: ruff clean · `pytest -m "not network"` 2901 passed / 10 skipped (pre-existing
network skips) · `python -m compute.warehouse.warehouse_schema_check` IN SYNC (warehouse
129 / filing_index 10 / portfolio_partition 11 / portfolio_manifest 5). Gate:
quantrank-reviewer READY-TO-PUSH (6/6 invariants, 0 FAIL, 4 non-blocking WARN);
phase-coordinator Mode B lockstep satisfied by this entry + the two doc diffs.

---

---

## PR (low-liquidity-preregister) — pre-register the `low_liquidity` annotate→veto promotion plan (issue #544, DOCS-ONLY, in flight, 2026-06-23)

methodology-scientist evaluated #544 and returned **RATIFY-WITH-CONDITIONS**:
the promotion gate is satisfied (5 full-sp1500 crons of firing data,
`low_liquidity_annotate_count`=5 stable, set {BFS,CENT,CPF,SBSI,SMP}, 0% churn,
blast radius = 5 deep-table names changing ZERO badges) but a low-ADV veto
suppresses names that carry an Amihud-2002 illiquidity *premium*, so it is an
**investability-policy** veto requiring owner sign-off — NOT a silent
auto-promote. Owner chose **pre-register now, promote at the Q3 2026-08-19
cohort audit**.

This PR is **DOCS-ONLY** — it changes NO scoring, adds NO live veto constant,
mutates NO rankings. It records the pre-registered plan + acceptance bands so
the Q3 promotion has a clean ratification record:

- `docs/METHODOLOGY.md` §low_liquidity — full pre-registration block: re-derived
  sp600 ADV distribution (p0.5≈$4.64M / p1≈$5.05M / p2.5≈$6.30M; $5M floor at
  ≈ sp600 p0.8), the annotate-$5M / veto-$3M two-tier design, and acceptance
  bands B1-B5.
- `compute/config.py` — ADV provenance comment updated from "RATIFY-SHADOW /
  to-be-re-derived" to the ratified pre-registration (still annotate-only; the
  live `ADV_VETO_FLOOR_USD` constant + cautious/Top-5 wiring land in the Q3 PR).
- CLAUDE.md + AGENTS.md §Gotchas / deferred — lockstep note on the pre-registered
  plan.

Acceptance bands a future PROMOTE must clear (locked here): **B1** firing ∈
[3,15] · **B2** ≤30% population churn · **B3** ZERO fired in rank ≤ 10 / AI-pick
basket (HARD gate) · **B4** ADV coverage ≥ 99% · **B5** ≥ 8 sp1500 crons (5
observed). Veto cutoff at promotion: `ADV_VETO_FLOOR_USD = $3M` (flips only the
BFS/CENT/SBSI tail; $4.6-5.0M band keeps the $5M annotate).

NO schema change. Defense layer UNCHANGED at 36 (the veto does not exist yet).
Lockstep: this entry + CLAUDE.md + AGENTS.md substance diffs. Gate: docs-reviewer.

---

## PR (TBD) — feat(compute): value_trap_risk two-factor LSV gate LIVE flip (#586 PR-2) (in flight, 2026-06-24)

Issue #586 PR-2 (LIVE flip). PR-1 (#588, schema 0.10.33) shipped the two-factor gate as a SHADOW
counter; the first sp1500 cron (d4da17e3, 2026-06-24) confirmed the acceptance gate —
`value_trap_risk_two_factor_shadow_count = 155` (10.3% of 1504), squarely in the
methodology-ratified **5-12% LSV band**. This PR FLIPS the live emission from the single-leg
Penman gate (ROE≤Ke alone, ~548/36.4%) to the two-factor LSV gate (~155/10.3%).

New live gate: `value_trap_risk` fires iff (a) RIM skips on `avg_3y_roe ≤ Ke` (Penman 2013) AND
(b) `eps_ttm > 0` AND ticker P/E < sector-peer median P/E (LSV 1994 cheap leg); loss-making /
undefined-P/E firms are EXEMPT. The RIM **method-skip** at `≤ Ke` is UNCHANGED (correct Penman) —
only the user-facing WARNING emission gets the second leg. Emission MOVED from `ensemble.py`
(pure-function layer, no sector-peer P/E context) to `compute/main.py` Step-8 per-ticker loop
(where `sector_panel` + `universe_metrics` are in scope; appends to the same `valuation_warnings`
local that every other annotate uses, before StockDetail construction — dedup-guarded).

Schema `0.10.33` → `0.10.34-phase8pilot` (version-only bump, NO new field; triple in sync).
`value_trap_risk_two_factor_shadow_count` is KEPT for one more cron as a structural cross-check
(it now equals the live count; docstring updated). `value_trap_risk_count_with_sector_coe` /
`_without_sector_coe` stay the Issue-#67 single-leg RIM-skip diagnostic (548/616) — distinct from
the emitted two-factor warning (155); NOT renamed (the #67 CoE-effect diagnostic is still
meaningful). Defense layer UNCHANGED at 36 (value_trap_risk was already an annotate; this changes
WHICH gate triggers it, not its annotate status). RANK / scores unaffected (annotate, rank-neutral).
RIPPLE (intended, rank-neutral): `value_trap_risk` feeds `VALUE_TRAP_PENALTY` into
`derive_loss_chance`, so the ~393 stocks dropping out of the firing set lose that penalty → their
displayed `loss_chance_pct` shifts down this cron (`loss_chance_pct` is display-derived;
`composite_score` is pre-computed and unaffected). Post-cron `stock-detail-auditor` should treat
this one-time `loss_chance_pct` shift as the expected flip effect, NOT data drift.

Docs reconciled (methodology-scientist RATIFY-WITH-AMENDMENT + literature-searcher
CITATION-CONFIRMED): `quarterly-cohort-audit/SKILL.md` anchor → LSV-1994 + Penman-2013, band →
5-12%, drop Asness-Frazzini 2013 ("Devil in HML's Details" — no value-trap content);
`docs/METHODOLOGY.md` cohort-audit entry + the `value_trap_risk` skip-reason line updated to the
two-factor gate.

Verify: ruff clean · `schema_check` IN SYNC · `pytest tests/test_valuation/ tests/test_config.py
-m "not network"` 282 passed (test_E2 inverted to assert ensemble silence; S4 class → post-flip
ensemble-silence tests; test_config pin 0.10.34). Gates: compute-builder BUILT-CLEAN;
quantrank-reviewer at the push gate. Acceptance: shadow 10.3% ∈ 5-12% (PR-1 cron d4da17e3).

---


## PR (TBD) — fix(data): 2026-Q2 S&P 500 rebalance ledger + dual-class band widen (in flight, 2026-06-24)

Post-cron data-pipeline audit (run d4da17e3) found the survivorship ledger
(`data/sp500_membership_historical.csv`) failed `scripts/verify_membership_ledger.py` with two
issues: (1) **POOL (Pool Corporation) ADD 2020-10-07 with no REMOVE** — flagged as an
ADDED-in-window-never-removed-not-in-universe consistency violation (net +1 ADD/REMOVE imbalance,
survivorship-bias exposure: the backtest counted POOL as an S&P 500 member through today); (2) a
**507-stock band breach 2016-2018** (23 months out of the `BAND=(498,506)` ceiling).

literature-searcher VERIFIED (S&P Dow Jones Indices, ann. 2026-06-05): the 2026-06-22 quarterly
rebalance moved **POOL → S&P SmallCap 600** (market-cap decline) and removed **CPB (Campbell's)**,
adding **MRVL (Marvell)** + **FLEX (Flex)**. This PR records the full size-neutral 6/22 rebalance
(MRVL ADD + FLEX ADD + POOL REMOVE + CPB REMOVE, eff. 2026-06-22) — clearing the POOL consistency
violation. The 507 breach is a REAL dual-class co-membership (Under Armour: UA Class C ADD
2016-04-08 co-existed with the baseline UAA Class A until REMOVE 2022-06-21), NOT a ledger error;
`BAND` ceiling widened `506 → 508` (one slot of headroom for the documented dual-class set
GOOG/GOOGL · FOX/FOXA · NWS/NWSA · UA/UAA) with an inline rationale comment.

`scripts/verify_membership_ledger.py` now exits 0 (RESULT: CLEAN; current universe 502, 489
ledger events, monthly reconstruction in-band 498-508). Data/script-only — NO schema change, NO
compute/scoring change, defense layer UNCHANGED at 36. KNOWN FOLLOW-UP (separate, self-healing):
POOL moved INTO the S&P 600 on 2026-06-22 but does not yet appear in the cron's sp600 slice — the
Wikipedia S&P 600 scrape / 7-day `universe_sp600` cache lags the just-executed rebalance; expected
to self-heal on the next sp600 cache refresh (MRVL+FLEX were correctly picked up in the sp500
scrape, confirming the sp500 path is fresh).

Verify: `scripts/verify_membership_ledger.py` exit 0 (CLEAN) · ruff clean · ADD/REMOVE balanced.

---

## PR (TBD) — feat(warehouse): historical run-metadata + portfolio backfill scripts (in flight, 2026-06-24)

Branch `claude/warehouse-backfill-history` (based on origin/main with the merged PR #597).
Two MANUAL one-shot historical backfills for the research warehouse — COMPUTE/SCRIPTS-ONLY,
no schema triple change, no cron wiring, no frontend change. Closes the historical-coverage
half of the warehouse gap PR #597 opened forward (PR #597 captured Metadata + portfolio
going forward only).

1. **`scripts/backfill_warehouse_metadata.py`** replays the git history of
   `frontend/public/data/metadata.json` (~9 commits → 4 unique run_dates) into a NEW
   COMMITTED dedicated store `data/warehouse/run_metadata/year=/run_date=/part-0.parquet`
   (cols: `run_date` / `schema_version` / `universe` / `source_commit` /
   `row_provenance="metadata_backfill"` / `metadata_json` verbatim-from-git-show). A
   SEPARATE store from `_manifest.parquet` (historical runs have no committed snapshot
   partition — injecting phantom manifest rows would mislead readers). Idempotent
   (disk-discovery dedup; same-day → newest-commit-first wins). Guarded by a new
   `data/warehouse/run_metadata_schema.json` baseline via `warehouse_schema_check.py`'s
   new `check_run_metadata_schema()` (folded into `main()` --update/verify `max(...)`).
   `.gitignore` whitelists `!data/warehouse/run_metadata/**/*.parquet`.

2. **`scripts/backfill_warehouse_portfolio.py`** is a thin wrapper REUSING PR #597's
   `compute/warehouse/portfolio_writer.write_portfolio_snapshot` to materialize the
   committed `data/warehouse/portfolio/` partition (800 rows = 40 rebalances × 20 holdings,
   2016→2026) + `portfolio_manifest.parquet` NOW from the already-committed
   `backtest_pit.json`, rather than waiting for the next cron. No new warehouse module; the
   #597 writer + its schema guards + gitignore whitelists are reused as-is.

Committed artifacts are REPRODUCIBLE from committed sources (git history / backtest_pit.json),
NOT fabricated scoring data. Schema triple (`schemas.py` / `types.ts` / `schema-snapshot.json`)
UNTOUCHED. Rankings/scores/flags BYTE-IDENTICAL. Defense UNCHANGED at 36. NO schema-version
bump. 26 new tests (`tests/test_warehouse/test_backfill_metadata.py`, BM1-BM15).

Verify: ruff clean · `pytest -m "not network"` 2926 passed / 10 skipped (1 pre-existing
alpha158 Hypothesis-deadline flake, unrelated) · `warehouse_schema_check` IN SYNC (6/6:
warehouse 129 / filing_index 10 / portfolio_partition 11 / portfolio_manifest 5 /
run_metadata 6). Gates: compute-builder BUILT-CLEAN; quantrank-reviewer FIX-AND-RE-REVIEW
→ FIXED (reverted a stray synthetic clobber of the live `_manifest.parquet` + 2026-06-24
snapshot back to HEAD's real 1504-row data; added this lockstep entry); phase-coordinator
Mode B LOCKSTEP-SATISFIED.

Lockstep: this entry + CLAUDE.md §Commands (2 new rows) + §Gotchas warehouse bullet
(`run_metadata/` store sentence) + AGENTS.md `QR_SKIP_WAREHOUSE` block mirror.

---

## PR (TBD) — fix(warehouse): backfill_warehouse_metadata robustness polish (in flight, 2026-06-25)

Branch `claude/warehouse-metadata-backfill-polish` (off origin/main with the merged #603).
Three non-blocking WARNs quantrank-reviewer raised on #603's
`scripts/backfill_warehouse_metadata.py` — SCRIPTS/TESTS-ONLY logic polish, no schema triple
change, no warehouse column change, no cron wiring, no frontend. Defense layer UNCHANGED at 36.

1. **Partial-success exit code** — `main()` now returns exit 1 when the run summary's
   `errors > 0` (was always 0, so a partially-failed history backfill looked fully green in
   CI). Emits a prominent `logger.error("PARTIAL FAILURE — N written, M errors ...")` before
   exit. Happy path (`errors == 0`) → exit 0 UNCHANGED; the pre-existing fatal-exception path
   still returns 1. Exit 1 is a pure CI signal — already-written partitions persist (no
   rollback); an idempotent re-run re-attempts exactly the failed commits.
2. **Empty-string `version` diagnostic** — a PRESENT-but-empty `version` key now logs a
   `WARNING` before storing `schema_version=None`; an ABSENT key stays silently None (the
   documented default). Guard: `if "version" in meta_dict and not _raw_version`.
3. **Full-string `last_update_utc` validation** — `_derive_run_date` was slicing `[:10]` then
   `date.fromisoformat`, so `"2026-06-24Tgarbage"` passed. Now validates the FULL string via
   `datetime.fromisoformat(last_update)` → `.date().isoformat()` (Python 3.11 handles a
   trailing `Z`), falling back to the committer-date path (log upgraded debug→warning) on a
   malformed full value. Import swap `from datetime import date` → `datetime` (no other
   runtime `date` use in the file). Return contract (ISO date string) preserved.

7 new tests (`tests/test_warehouse/test_backfill_metadata.py` BM16-BM18: partial/all-error
exit + happy-path exit 0 · empty-version warning + None / absent-key silent · malformed-full-UTC
fallback + valid-value + date-only no-regression).

Schema triple UNTOUCHED. Verify: ruff clean · `pytest tests/test_warehouse/test_backfill_metadata.py
-m "not network"` 37 passed · `warehouse_schema_check` 5/5 IN SYNC (no column change). Gates:
compute-builder BUILT-CLEAN; quantrank-reviewer READY-TO-PUSH (3/3 fixes correct, 0 FAIL,
idempotence + import-swap regression-checked). Lockstep: this entry only (the §Commands backfill
row + warehouse §Gotchas description are UNCHANGED — internal robustness, no behavior the docs
describe changed).
## PR #604 — feat(compute): IC half-life monitor (Proposal F, in flight, 2026-06-25)

Branch `claude/fund-performance-rankings-f8x4o1`. First implementation slice
of the legendary-fund deep-research 6-proposal program (methodology-scientist
RATIFY-SHADOW). Extends `compute/validation/ic_decay.py` to fit a per-pillar IC
decay half-life — fits BOTH an exponential and a power-law curve to |IC| over
the monthly panel and reports the half-life of whichever has the better R²
(Di Mascio 2022 found power-law fits alpha decay slightly better). Surfaced
write-only as two new optional `Metadata` fields.

SHADOW / OBSERVABILITY-ONLY (Rule 18): never feeds scoring, vetoes, rankings,
or the composite. Live rankings/scores/flags BYTE-IDENTICAL. Defense layer
UNCHANGED at 36. With the project's thin IC history every pillar fits `None`
on launch day (honest preliminary gate at `MIN_HALF_LIFE_FIT_MONTHS=12`) — same
posture as `bonferroni_shadow_*` / `cross_source_corruption_*`. Feeds the
deferred shrinkage composite (Proposal A) once ≥12 monthly IC points accrue.

- `compute/validation/ic_decay.py` — `fit_pillar_half_life` +
  `build_pillar_half_lives` + `MIN_HALF_LIFE_FIT_MONTHS` + `PillarHalfLife`;
  exp/power fits, graceful `None` on thin/degenerate series, never raises
- `compute/output/schemas.py` — `Metadata.pillar_ic_half_life_months:
  dict[str, float | None] | None` + `pillar_ic_decay_fit_model:
  dict[str, str | None] | None` (both optional, default None)
- `compute/main.py` — write-only wiring co-located with the
  `QR_SKIP_DECAY_MONITOR` guard, try/except non-fatal (never blocks the cron)
- `compute/config.py` — schema `0.10.34` → `0.10.35-phase8pilot`
- `frontend/lib/{types.ts,schema-snapshot.json}` — schema-triple mirror
- `docs/METHODOLOGY.md` + `.claude/agents/literature-searcher.md` —
  McLean-Pontiff 2016 promoted from prose to a canonical anchor; Di Mascio 2022
- tests — +17 (exp recovery λ=0.05→13.86m, power-law win, preliminary boundary
  n=11/12, degenerate constant/zero/growing IC, `build_pillar_half_lives`
  graceful contract, Metadata round-trip) + schema-version pin → 0.10.34

Lockstep: this entry + CLAUDE.md + AGENTS.md substance diffs. Schema triple in
sync (schema_check ✓). Gate: quantrank-reviewer at Draft→Ready.

---

## PR #609 — test(frontend): RankingTable interaction tests (in flight, 2026-06-25)

**Branch**: `claude/rankingtable-interaction-test`
**Type**: test-only — NO production code change; no schema bump; defense UNCHANGED at 36.

**Why**: PR #608 added `useDeferredValue(search)` + `useTransition`-wrapped `onSort`
to `RankingTable.tsx` to fix a desktop INP regression on the 1504-row S&P 1500 table.
`quantrank-reviewer` noted there was no test covering any RankingTable behaviour — the
deferred-search + sort-transition + FLIP-gate timing logic is exactly the kind of thing
a future refactor could silently break.

**Approach**: Pure-function verbatim-transcription pattern (same technique as
`components/downsample.test.mjs`) — the search `filterRows` predicate and the sort
`sortRows` comparator are lifted verbatim from the component's `useMemo` bodies and
tested as standalone functions. `@testing-library/react` / jsdom were NOT added
(vitest.config.ts sets `environment: 'node'`; adding RTL is a heavier dependency change
that needs a separate security-reviewer gate). The concurrent-timing invariant ("typing is
never swallowed") is a React runtime guarantee that cannot be deterministically asserted in
a synchronous unit test; that limitation is documented in the test file header.

**Coverage added (51 new tests)**:
- Group A: `filterRows` — empty/whitespace passthrough · ticker match (exact/lowercase/mixed-case/partial) · name match (substring/mid-word/multi-hit/uppercase) · no-match → empty array (empty-state) · union semantics (ticker-OR-name)
- Group B: `sortRows` — numeric column rank asc/desc · composite_score desc + asc/desc toggle · string column name asc + asc/desc toggle · ticker asc · null values sort last (asc + desc + both-null stable)
- Group C: `nextSortDir` — first-click default: asc for rank/ticker/name/sector/price; desc for composite_score/fair_price/margin_of_safety_pct · toggle: same-column asc→desc and desc→asc
- Group D: WINDOW_SIZE constant (= 50) + visible-rows slice semantics (short list / long list / search-narrows / hasMore true/false)
- Group E: filter → sort pipeline composition (filter then sort by name; filter then sort by score desc; empty filter still empty; single-row pipeline)

**Files**:
- `frontend/components/RankingTable.test.ts` (new — 51 tests)
- `PHASE_STATUS_INFLIGHT.md` (this entry)

**Test results**: 189 baseline → 240 total (+51). `tsc --noEmit` clean. No new devDependency added.

## perf(frontend): RankingTable search input uncontrolled (in flight, 2026-06-25)

**Branch**: `claude/rankingtable-search-uncontrolled`
**Type**: perf(frontend) — VIEW-LAYER ONLY. No schema change. Schema triple untouched.
Defense layer UNCHANGED at 36. Rankings/scores/flags BYTE-IDENTICAL. No new dependency.
No design-token/visual change.

**Motivation**: PR #608 shipped `useDeferredValue(search)` + `useTransition`-wrapped `onSort`,
bringing desktop INP from 496ms → 360ms. Playwright re-profile (1440×900, 4× CPU throttle)
pinned the remaining 208ms to the SEARCH FIRST-KEYSTROKE. Root cause: the search `<input>`
was CONTROLLED (`value={search}`), so every keystroke triggered a synchronous React re-render
of the input + toolbar on the interaction's critical path. `useDeferredValue` already deferred
the 1504-row filter but could not defer the controlled-input's own re-render. Desktop INP
target is < 200ms ("Good").

**Change** (`frontend/components/RankingTable.tsx` only):

1. **Uncontrolled input**: removed `value={search}` binding. The browser now owns the
   displayed text; keystrokes commit at the DOM level instantly, zero React render per
   character on the critical path. Added `ref={inputRef}` (for programmatic reset) and
   `defaultValue=""`.

2. **Deferred setSearch**: `onChange` pushes the value into React state via `startTransition`:
   `onChange={(e) => startTransition(() => setSearch(e.target.value))}`. This is safe and was
   NOT safe while controlled — because the visible input value is DOM-owned, deferring
   `setSearch` no longer makes typing feel stuck. The keystroke commits at the browser level
   instantly; only the filter state update is low-priority.

3. **useDeferredValue retained**: `deferredSearch = useDeferredValue(search)` is kept.
   `setSearch` inside `startTransition` makes `search` already low-priority, but
   `deferredSearch` is an additive second deferral (harmless) that keeps the FLIP `filterKey`
   and window-reset effects anchored to `deferredSearch` — the invariant those effects depend
   on is "fires exactly when filtered rows actually commit to the DOM", which `deferredSearch`
   guarantees independently of how `setSearch` was called.

4. **FLIP invariant preserved**: `filterKey = deferredSearch`. The FLIP gate opens exactly
   when deferred filtered rows commit; `filterKey` is never `search` (immediate). Scroll /
   sort / load-more do NOT change `filterKey` — the search-scoped FLIP invariant is intact.

5. **Clear-search wired through ref**: the empty-state "Clear search" button now resets both
   the DOM value (`inputRef.current.value = ''`) AND the React state
   (`startTransition(() => setSearch(''))`). Either alone is incomplete for an uncontrolled
   input. The `{search && ...}` guard reads React state (still correct — `setSearch` still
   populates `search`).

**Invariants confirmed**:
- Windowed infinite-scroll (WINDOW_SIZE=50), window-reset effects, `animateRows` entrance
  gate, "X / N stocks" count denominator — all untouched.
- Search filtering behavior identical (ticker + company-name, case-insensitive, empty → all).
- `tabular-nums` and accessibility (`aria-label`, `type="search"`, `min-h-[44px]`) preserved.

**Flag**: PR #609 (RankingTable vitest tests, not yet merged) also touches `RankingTable.tsx`.
Whichever merges second needs a trivial rebase — the two diffs are non-overlapping (this PR
edits state/hooks/input; #609 adds test files only, or if it patches imports those will rebase
cleanly).

**Verify**: `tsc --noEmit` PASS · `next build` PASS (1512 static pages, 0 new errors) ·
schema triple UNTOUCHED. Lockstep: this entry. No CLAUDE.md/AGENTS.md substance change
required (frontend view-layer perf, no new convention). Gate: frontend-design-reviewer +
vercel-preview-auditor + expert-user-explorer.

---

## PR — fix(frontend): AI-pick Return column history-cap for long-tenure holdings (2026-06-25)

**Branch**: `claude/aipick-sold-return-history-cap`
**Type**: fix(frontend) — display-only bug fix; no schema change, no compute change.

**Bug**: In `AiPickAdaptiveBranch`, the `adaptivePlSince` useMemo computed per-holding
total return by walking the timeline to find the streak-start index, then reading
`entryCloses[t][streakStartIdx]`. When a holding's tenure predates the 5-year
price-history window (KLAC: streak started at a 2020 rebalance, but its
`stocks/history/KLAC.json` starts 2021-06-17), `entryCloses['KLAC'][streakStartIdx]`
was `null` → `entry = null` → `pct = null` → the Return cell rendered "—" for a
stock that is fully held, has real returns, and just has a long tenure. Symmetric
bug existed for sold rows.

**Fix**: After finding `streakStart`, advance `entryIdx` forward (`streakStart + 1`,
`+2`, …) to the FIRST index where `entryCloses[t][entryIdx]` is non-null. Use that
close as the entry. Track `capped = entryIdx > streakStart` and `sinceDate =
timeline[entryIdx].date`. Genuine no-data (no non-null close anywhere in the range)
keeps `pct = null` (still "—" — correct). Applied symmetrically to both the held/new
loop and the sold loop.

**Return shape change**: `adaptivePlSince` widened from
`Record<string, number | null>` to
`Record<string, { pct: number | null; sinceDate: string | null; capped: boolean }>`.
All render call sites updated to read `.pct`.

**SR-accessibility (SKILL.md Rule 10 — color never the sole signal)**:
When `capped=true`, the Return `<span>` carries an `aria-label` reading
`"<pct> — return measured from <sinceDate>, the start of available price history;
the holding's full tenure began earlier"`. A small (`text-[10px]`) `<span aria-hidden="true">`
below the pct reads `"since YYYY-MM"` so a sighted user also sees the partial-tenure
affordance without relying on a mouse-only `title=`. Paired
`text-slate-400 dark:text-slate-500` (secondary muted tone per design system).

**Files changed** (`frontend/` only):
- `frontend/components/AiPickPortfolio.tsx` — `adaptivePlSince` useMemo +
  both Return-cell render blocks (held/new + sold).
- `PHASE_STATUS_INFLIGHT.md` — this entry.

**Invariants preserved**: non-capped rows are byte-identical in their pct value
(advancing `entryIdx` by 0 when `entryCloses[t][streakStart]` is non-null leaves
all existing tickers unchanged); total-return footer (in `PerformanceTable`) does
not consume `adaptivePlSince`; sold-row 0.0% weight column untouched; sort/order
of rows untouched; slider branch (`AiPickSliderBranch`) untouched.

**No schema change**: `entryCloses`/`lastCloses` are frontend-only view-model fields.
Defense layer UNCHANGED at 36. Rankings byte-identical.

**Note for test-engineer**: the history-cap forward-scan is a pure function over an
array-with-nulls — a good unit test candidate (no JSDOM or React render needed).

**Verify**: `tsc --noEmit` PASS · `next build` PASS (1512 static pages, 0 new
errors) · schema triple UNTOUCHED. Lockstep: this entry. Gate: frontend-design-reviewer
+ vercel-preview-auditor + expert-user-explorer.

---

## PR (TBD) — feat(compute): position return attribution PR-1 shadow/obs-first (in flight, 2026-06-25)

New pure module `compute/portfolio/position_returns.py` (mirrors `backtest.py`'s
no-I/O, no-pandas, offline-testable contract) computing three return measures per
holding in the Phase 7 PIT backtest:

- **MWR (Modified Dietz)** — money-weighted return over actual rebalance cash flows
  (CFA/GIPS standard estimator; the intended headline metric).
- **TWR (chained geometric)** — `Π(p_{i+1}/p_i) − 1` over contiguous rebalance
  sub-periods using the SAME adjusted-close series as `build_portfolio_nav`
  (Condition C1: no raw/adjusted mixing).
- **Contribution-to-NAV (Carino-linked)** — position P&L in NAV base-100 points,
  Carino-linked so Σ(contributions) reconciles to portfolio NAV return (PR-1: always
  `None` — the per-sub-period portfolio return wiring is deferred to PR-2).

Edge-case contracts shipped: re-entry-after-gap uses current streak only; weight→0
terminates the streak; null price at rebalance drops that leg (TWR) or is skipped
gracefully (MWR); current holders mark to latest close; sold rows mark to
exit-rebalance close.

**Wiring** (`scripts/backfill_portfolio_pit.py`): `_assemble_nav` signature widened
to a 6-tuple (added `closes` return value — same panel used by `build_portfolio_nav`,
satisfying C1). Call site updated. `compute_position_returns` is called right after
`_assemble_nav`, results emitted as `payload["position_returns"]` (shadow dict) plus
two reconciliation counters on `payload["meta"]`:
- `position_return_reconciliation_max_abs_error` (Carino: `None` in PR-1)
- `position_return_twr_vs_clientside_max_abs_pp` (`None` in PR-1, stub ready for PR-2)

**SHADOW-ONLY / Rule 18**: `payload["position_returns"]` is a new top-level key in
`backtest_pit.json` with no frontend reader until PR-2.  The `_assemble_nav` change
is backward-compatible (tuple position 5 = `closes`; existing callers unpack the
first 5 positions and are unaffected).  Defense layer UNCHANGED at 36.  Rankings,
NAV, and scores are byte-identical.

**Schema triple**: untouched. `backtest_pit.json` is a raw dict outside the
Pydantic↔TS↔snapshot triple; no `schemas.py` change.

**Files changed (`compute/` only)**:
- `compute/portfolio/position_returns.py` — NEW (pure module, ~450 lines)
- `scripts/backfill_portfolio_pit.py` — import + `_assemble_nav` signature/return +
  call-site unpack + position-returns wiring block after `_assemble_nav`

**Tests**: 27 offline tests in `tests/test_portfolio/test_position_returns.py` covering:
`_is_valid_price` · `_days_between` · `_carino_coefficient` (R=0, total-loss guard,
small-R) · `_modified_dietz` (single-leg HPR, empty, zero-denom, ADD-then-gain
cash-flow sign, TRIM-then-gain cash-flow sign) · `_extract_streaks`
(continuous, sell-at-zero, re-entry gap) · multi-rebalance TWR 21% · null-mid-price
partial_history=True · re-entry-current-streak · two-ticker compute · weight→0
termination · empty band_legs · current-holder mark-to-latest-close · dict
serialization keys · reconciliation_errors no-contrib.
Note: `test_backfill_integration.py::test_assemble_grid_navs_shares_price_panel` had a
CI-red regression (5-tuple unpack when `_assemble_nav` returns 6); fixed in the
test-hardening commit by switching to `out, *_ = ...` style (matching the other callers
in that file).

**Verify**: ruff PASS · pytest offline (27 tests in test_position_returns.py, 0 regressions
after 5-tuple unpack fix) · schema_check N/A
(no tracked schema change). Branch: `claude/position-returns-shadow`.

---
## PR #607 — feat(compute): Market-regime diagnostic (Proposal D, in flight, 2026-06-25)

Branch `claude/fund-performance-rankings-f8x4o1`. Second implementation slice
of the legendary-fund deep-research 6-proposal program (methodology-scientist
RATIFY-SHADOW, concur with rejection-as-tilt). Adds a write-only market-regime
diagnostic to `Metadata`, computed from the price frames already fetched in
Step 1 (NO new data source, NO new network call).

SHADOW / OBSERVABILITY-ONLY (Rule 18) with a hard Welch-Goyal 2008 rejection-
as-tilt constraint: the regime fields MUST NEVER be read by scoring, composite,
pillar computation, veto/flag logic, fair-price, `select_picks`, or the weights.
The financial-engineer explicitly rejected regime as a basket/scoring tilt
because equity-premium predictors fail OOS (Welch-Goyal 2008 *RFS* 21(4),
1455-1508 Table 3). The diagnostic seeds a future Phase-7 Student-t HMM —
the breadth field will be ONE feature in that multi-year panel, evaluated
rigorously OOS before any tilt is authorized.

Live rankings/scores/flags BYTE-IDENTICAL. Defense layer UNCHANGED at 36.

- `compute/scoring/regime.py` — new module: `compute_market_regime(prices_by_ticker)`
  pure function; takes price DataFrames already loaded in Step 1; excludes
  tickers with < 200 bars from denominator; returns `(breadth_pct, regime_state)`;
  docstring carries the full Welch-Goyal rejection rationale + HMM forward motivation;
  try/except is at the main.py call-site (module itself is clean / unit-testable)
- `compute/output/schemas.py` — `Metadata.market_breadth_above_200dma_pct:
  float | None = None` + `Metadata.market_regime_state: str | None = None`
  (both optional, default None; hard-constraint comment in docstring)
- `compute/config.py` — schema `0.10.35` → `0.10.36-phase8pilot` +
  `REGIME_RISK_ON_THRESHOLD = 60.0` + `REGIME_RISK_OFF_THRESHOLD = 40.0`
  (Tier-3 gut-feel calibration, documented as such)
- `compute/main.py` — write-only wiring after the `pillar_ic_half_life` block,
  try/except non-fatal (never blocks the cron); `prices_by_ticker` reused from
  Step 1 (zero extra I/O); import of `compute_market_regime` at top-level
- `docs/METHODOLOGY.md` — Proposal D section: Welch-Goyal anchor, Kacperczyk-
  Van Nieuwerburgh-Veldkamp 2014 forward motivation, Tier-3 threshold docs
- `frontend/lib/{types.ts,schema-snapshot.json}` — schema-triple mirror
  NEEDED (frontend-builder task)
- Tests needed (test-engineer task): pure `compute_market_regime` unit tests
  (above/below/neutral classification, < 200 bars exclusion, all-empty frames
  → None/None, Close vs Adj Close column detection, try/except non-fatal path)

Lockstep: this entry + CLAUDE.md + AGENTS.md §Phase status in-flight update.
Schema triple: 2 new fields added → TS mirror NEEDED. Gate: quantrank-reviewer
at Draft→Ready.

---

## PR — Proposal A: shrinkage composite (in flight, 2026-06-25)

**Branch**: `claude/fund-performance-rankings-f8x4o1`
**Schema**: `0.10.36` → `0.10.37-phase8pilot`
**Type**: feat(compute) — observability-first (Rule 18). Identity-at-launch: rankings/scores/flags
BYTE-IDENTICAL (SHRINKAGE_LAMBDA_PIN=1.0 + all pillars preliminary → blended_w == w0 → composite
unchanged). Defense layer UNCHANGED at 36.

**What ships:**

- NEW `compute/scoring/shrinkage.py` — pure module (numpy/pandas only). Three functions:
  `compute_shrinkage_lambda(n, τ=24)` = 1/(1+n/τ) clamped to [0,1]; `build_ic_weights(reports,
  w0, active_pillars)` → (w_ic, preliminary_mask, degenerate) reading `ICDecayReport.preliminary`
  (C1: never inline n<12); `blend_weights(w0, w_ic, λ, mask, lambda_pin=1.0)` with C-canary
  assert sum==1.0 within 1e-9 before returning. Constants: `SHRINKAGE_TAU_MONTHS=24.0` (Tier-2/3
  gut-feel, inert-at-launch, τ only bites once pin is lifted + pillar has ≥24mo) +
  `SHRINKAGE_LAMBDA_PIN=1.0` (identity pin; None = engage schedule, gated on A3-i/A3-ii).

- EDIT `compute/validation/ic_decay.py` — Proposal A #605 consolidation:
  new `walk_ic_history(*, end_date, lookback_months, horizon_months)` → `_WalkICResult`
  (entries, panels, n_dates_with_ic); ONE git-walk. `build_decay_report` gains a
  backward-compatible injected-panels path (`panels=None` = self-walk; existing callers/tests
  byte-identical). C5: walk_ic_history wraps the git call in try/except → degrade-to-empty
  (never raises, cron never blocked).

- EDIT `compute/main.py` — HOIST before line 1661 (Step 5 composite):
  walk_ic_history → build_decay_report(panels=) → build_ic_weights → compute_shrinkage_lambda
  → blend_weights → C-canary assert → `compute_composite(pillar_df, weights=_composite_weights)`.
  Decay monitor + half-life monitor (#605) now consume `_ic_walk_result.panels` (DELETE
  block-2 re-walk). QR_SKIP_DECAY_MONITOR guard covers all three.

- EDIT `compute/output/schemas.py` — 6 additive `Metadata` fields (all `| None = None`):
  `shrinkage_lambda`, `shrinkage_lambda_applied`, `ic_weight_by_pillar`,
  `shrinkage_blended_weight_by_pillar`, `n_preliminary_pillars`, `shrinkage_weights_degenerate`.

- EDIT `compute/config.py` — schema `0.10.36` → `0.10.37-phase8pilot`.

- EDIT `docs/METHODOLOGY.md` — Proposal A section: Timmermann 2006 + Grinold-Kahn 2000 +
  Ledoit-Wolf 2004 as principle. Pre-registered pin-lift gate A3-i (n ≥ 24mo) + A3-ii
  (Timmermann OOS horse-race vs fixed-w0 on purged-embargo holdout; 1/N fallback if no gain).

**Binding conditions met (methodology-scientist):**
- C1: build_ic_weights reads `ICDecayReport.preliminary`, never inline n<12.
- C2: τ docstring labels Tier-2/3 + inert-at-launch rationale + names Proposal-F follow-up.
- C5: walk_ic_history try/except → degrade-to-empty → degenerate → w_ic=w0 → blend=w0.
- C-canary: blend_weights asserts sum==1.0 within 1e-9 before returning.

**Schema triple**: 6 new fields added → TS mirror NEEDED (frontend-builder task).
**Tests needed** (test-engineer):
  λ schedule (0→1.0, 24→0.5, 72→0.25, monotone, clamp); identity at λ=1; pin holds;
  preliminary→1.0 override; w_IC sum-to-1; all-preliminary→identity+degenerate;
  all-IC≤0→identity+degenerate; max(IC,0); end-to-end byte-identity compute_composite;
  #605 injection-equivalence; Hypothesis property (non-neg, sum 1±1e-9, ==w0 when λ=1 or mask=all).

**Gate**: quantrank-reviewer + schema-sentinel + test-engineer at Draft→Ready.

---

## PR #NNN — feat(compute): per-quarter position returns (PR-2a) (in flight, 2026-06-26)

**Branch**: `claude/position-returns-per-quarter` (off `main`; PR-1 merged as #614)

**Scope**: Extends PR-1's shadow position-return attribution to cover ALL historical
rebalances.  Carino reconciliation DESCOPED to a follow-up PR (see below).  STILL
SHADOW — no frontend read.  Rankings/NAV gross+net BYTE-IDENTICAL.  Defense UNCHANGED at 36.

**FIX-FIRST revision (2026-06-26)**: quantrank-reviewer returned FIX-FIRST with three
issues; all three are resolved in this revision:

1. **Fix #3 — per-quarter PIT look-ahead (HIGH, RESOLVED)**: `compute_position_returns_per_quarter`
   now truncates the leg list to `date <= rebal_date` for all non-latest quarters before
   computing TWR/MWR.  Historical quarter r can no longer chain prices through future rebalance
   dates (look-ahead eliminated).  The latest rebalance still uses the full leg list.
   Correctness signal: `test_per_quarter_pit_no_lookahead` confirms quarter-0 TWR (10%) ≠
   quarter-1 TWR (21%) for a 3-rebalance fixture.

2. **Carino descoped — Fix #2 (RESOLVED)**: `_compute_carino_contribution_for_streak` is
   retained but NOT called from the main compute path.  All `contrib_nav_pts` values are
   `None`.  `position_return_reconciliation_max_abs_error` is `None`.  Carino re-derivation
   delegated to financial-engineer in a dedicated follow-up PR (numerator/denominator
   sub-period mismatch confirmed — see PR-2a review comments).
   `TODO(carino-reconciliation PR)` markers placed at both call sites.
   `test_carino_identity_three_quarter_book` updated to assert `contrib_nav_pts is None`
   for all positions across all quarters.

3. **Fix #1b — backward-compat flat field (RESOLVED)**: `compute_position_returns` now
   uses `_compute_flat_latest_returns` (not `per_quarter[-1]`).  The new helper covers
   BOTH current holders at the latest rebalance AND names sold at the latest rebalance
   (marked-to-exit close), preserving PR-1 semantics for Current-picks "Sold" rows.
   `test_compute_position_returns_per_quarter_latest_compat` updated to reflect the
   no-sold-names fixture (keys still agree; docstring updated).

**Files changed** (`compute/**` + `scripts/` only; no schema triple, no frontend):
- `compute/portfolio/position_returns.py` — core implementation
- `scripts/backfill_portfolio_pit.py` — wiring (imports + per-rebalance injection)
- `tests/test_portfolio/test_position_returns.py` — 14 new tests (27 → 41 total)

**What changed vs PR-1 (#614)**:

1. **Per-quarter generalization** — new public function
   `compute_position_returns_per_quarter` returns `list[dict[str, PositionReturn]]`,
   one map per entry in `band_legs_for_nav` (~40 rebalances × ~8-16 holdings).
   Each quarter's map is truncated to legs with `date <= rebal_date` (Fix #3 PIT).

2. **New `_compute_flat_latest_returns` helper** — assembles the flat top-level
   `payload["position_returns"]` for PR-1 backward compat: current holders (weight > 0
   at latest rebalance) + sold-at-latest names (weight > 0 at prior leg, 0 at last leg).

3. **Carino DESCOPED** — `contrib_nav_pts=None` for all positions; helper code retained
   but not called; `TODO(carino-reconciliation PR)` markers at both call sites.

4. **TWR vs client-side counter** — `reconciliation_errors` accepts `closes` parameter.
   When provided, computes max |engine TWR − point-to-point HPR| over clean single-streak
   names → `position_return_twr_vs_clientside_max_abs_pp` (Carino-independent, RETAINED).

5. **Artifact shape** — `backfill_portfolio_pit.py` injects
   `position_returns_to_dict(per_quarter_maps[i])` into each
   `rebalances_out[i]["position_returns"]`.  The top-level `payload["position_returns"]`
   uses `_compute_flat_latest_returns` (not `per_quarter[-1]`).

**Backward compat conditions**:
- C1: same adjusted-close series passed (no raw/adjusted mixing).
- `compute_position_returns` covers current holders + sold-at-latest names (PR-1 semantics).
- `position_return_reconciliation_max_abs_error` is `None` (Carino descoped).
- `position_return_twr_vs_clientside_max_abs_pp` is computed and retained.

**New helpers in `position_returns.py`**:
- `_compute_flat_latest_returns` — PR-1-compat flat field builder (current + sold names).
- `_close_on_or_before` — scans backward for most recent valid close (weekend/holiday handling).
- `_compute_carino_contribution_for_streak` — retained but not called (Carino descoped).
- Updated `_compute_twr` and `_compute_mwr` — added `end_date: str | None = None`
  parameter for non-latest quarter terminal marking.

**MWR cash-flow sign**: weight increase (add) = positive CF; weight decrease (trim) = negative CF.
Locked by existing `test_modified_dietz_add_then_gain_cash_flow_sign` test.

**Schema triple**: UNTOUCHED — no new `schemas.py` / `types.ts` / `schema-snapshot.json` fields.

**Tests added** (14 new; in `tests/test_portfolio/test_position_returns.py`):
- `test_close_on_or_before_exact_date` — exact hit
- `test_close_on_or_before_weekend_falls_back_to_friday` — non-trading day
- `test_close_on_or_before_no_eligible_date` — all dates after target → None
- `test_close_on_or_before_missing_ticker` — unknown ticker → None
- `test_compute_position_returns_per_quarter_length` — len == len(band_legs)
- `test_compute_position_returns_per_quarter_empty_input` — empty → []
- `test_compute_position_returns_per_quarter_latest_compat` — keys agree (no sold names fixture)
- `test_carino_identity_three_quarter_book` — UPDATED: all contrib_nav_pts must be None
- `test_per_quarter_pit_no_lookahead` — NEW: quarter-0 TWR (10%) ≠ quarter-1 TWR (21%)
- `test_reconciliation_errors_with_closes_pp_twr_near_zero` — clean name → pp_err ≈ 0
- `test_reconciliation_errors_with_closes_not_none` — partial_history=True → pp_err=None
- `test_compute_carino_contribution_basic` — single-leg manual derivation (helper retained)
- `test_compute_carino_contribution_empty_streak` — empty → None
- `test_compute_carino_contribution_no_nav` — empty date_to_nav → None

**Verify**: ruff PASS · pytest offline 41 position_returns tests passed · schema_check N/A · tsc untouched.

**SHADOW constraint**: frontend does NOT read `rebalances[i].position_returns` until
PR-2b adds a UI surface gated on ≥ 1 cron confirming the reconciliation counters.

**Unblocks**: Carino follow-up PR (financial-engineer re-derivation) + PR-2b (rotation-history drawers)

**Gate**: quantrank-reviewer + defense-layer-auditor at Draft→Ready.

---

## PR #617 — feat(compute): MoS conviction tilt shadow (Proposal C-2, in flight, 2026-06-26)

**Branch**: `claude/fund-performance-rankings-f8x4o1`
**Schema**: `0.10.37-phase8pilot` → `0.10.38-phase8pilot`
**Type**: feat(compute) — observability-first (Rule 18). SHADOW / OBSERVABILITY-ONLY.
Live `band_weights`, `band_legs_for_nav`, NAV, rankings, scores, and flags are
BYTE-IDENTICAL. Defense layer UNCHANGED at 36.

**What**: Proposal C-2 from the legendary-fund deep-research 6-proposal program
(methodology-scientist RATIFY-SHADOW). Adds a book-relative MoS-conviction tilt
on top of inverse-vol weights as a diagnostic surface:

- `compute/portfolio/weights.py` — new pure function `mos_conviction_tilt(base_weights,
  mos_by_ticker, *, kappa, cap)` + constants `MOS_TILT_KAPPA=0.25` (Tier-2 gut-feel,
  disclosed), `MOS_TILT_CLIP_LO=0.5`, `MOS_TILT_CLIP_HI=1.5`. Book-relative z-score
  (mos None→z=0); multiplier `m=clip(1+κ·z, lo, hi)`; renorm; **iterative pin-and-
  redistribute re-cap (reuses the same ≤n-pass loop as `inverse_vol_weights`)**.
  Stevens 1946 admissibility: mos_pct is ratio-scale cardinal (vs composite_score ordinal);
  Graham-Dodd MoS doctrine. Identity guards: σ_mos=0 / all-None / single-name book.

- `scripts/backfill_portfolio_pit.py` — SHADOW wire after `band_weights_map`:
  computes `mos_tilted_weights` (via the new function), exports two additive
  per-rebalance fields (`mos_tilted_weights` · `mos_tilt_max_abs_weight_delta_pp`).
  Does NOT feed `band_legs_for_nav`. Three additive `meta.*` fields:
  `mos_tilt_kappa=0.25` · `mos_tilt_clip=[0.5,1.5]` · `mos_tilt_active=false`.

- `compute/output/schemas.py` — ONE additive `Metadata` field:
  `mos_tilt_shadow_max_delta_pp: float | None = None` (max per-rebalance delta
  across all legs — the cross-universe canary).

- `compute/main.py` — C-2 canary derivation block before the `Metadata(...)` call:
  reads `backtest_pit.json` (if present), extracts `max(mos_tilt_max_abs_weight_delta_pp)`
  across all rebalance legs, passes it into `Metadata.mos_tilt_shadow_max_delta_pp`.
  try/except → None (never blocks cron).

- `compute/config.py` — schema `0.10.37` → `0.10.38-phase8pilot`.

**Flip-gate (future PR)**: re-derive κ from observed z(mos) distribution; confirm
clip-bind rate ≤ ~5%; verify MAX_WEIGHT holds post-renorm on all rebalance legs;
OOS turnover check; methodology-scientist ratify at the Q3 2026-08-19 cohort audit.

**Schema triple**: 1 new field added → TS mirror + snapshot regen NEEDED
(frontend-builder: add `mos_tilt_shadow_max_delta_pp: number | null` to `Metadata`
in `frontend/lib/types.ts` + regen `frontend/lib/schema-snapshot.json`).

**Tests needed** (test-engineer):
  - Identity guards: σ_mos=0 → returns base_weights unchanged; all-None → identity;
    single-name book (n=1) → identity; empty base_weights → `{}`.
  - Clip bounds: z such that 1+κ·z < MOS_TILT_CLIP_LO is clamped to CLIP_LO; ditto HI.
  - MAX_WEIGHT holds post-tilt: property test — Hypothesis generates random books + MoS
    values; assert max(mos_tilted_weights.values()) ≤ MAX_WEIGHT + 1e-9.
  - Sum-to-1: all non-degenerate outputs sum to 1.0 within 1e-9.
  - Byte-identity canary: higher-MoS ticker gets higher tilted weight when σ > 0.
  - Hypothesis property: non-neg weights, sum 1±1e-9, MAX_WEIGHT bound holds.
  - `mos_conviction_tilt` is pure (no I/O side effects).

**Gate**: quantrank-reviewer + schema-sentinel + test-engineer + defense-layer-auditor
at Draft→Ready.

---

## PR-2c — Carino C3 reconciliation (`claude/carino-reconciliation`, 2026-06-26)

**Scope**: Implements the Carino (1999) GROSS-identity contribution-to-NAV
reconciliation gate (C3 correctness gate) for the position-return redesign.
Builds on PR-1 (#614) + PR-2a (#618) which are merged on `main`.
STILL SHADOW / Rule-18: no frontend read; display flip is a separate PR-2b.

**Files written** (`compute/` only):
- `compute/portfolio/backtest.py` — adds `SubPeriod` frozen dataclass (fields:
  `date_from`, `date_to`, `start_weights_gross`, `price_relatives`,
  `gross_sub_return`, `net_sub_return`, `cost_drag`) + `decompose: bool = False`
  keyword arg to `build_portfolio_nav`; existing callers with default
  `decompose=False` receive BYTE-IDENTICAL output.
- `compute/portfolio/position_returns.py` — adds window-global Carino grid
  (`_build_carino_grid`, `_compute_contribution_from_sub_periods`,
  `_cost_line_contribution`); updates `compute_position_returns` with
  `sub_periods` kwarg; `reconciliation_errors` returns 4-tuple
  `(gross_identity_error, cost_line_residual, pp_twr_error, carino_clamp_count)`;
  deprecated `_compute_carino_contribution_for_streak` retained as compat stub.
- `scripts/backfill_portfolio_pit.py` — imports `SubPeriod`; calls
  `build_portfolio_nav(decompose=True)` for adaptive NAV; `_assemble_nav`
  now returns 7-tuple (added `sub_periods: list[SubPeriod]`); passes
  `sub_periods` to `_compute_flat_latest_returns` + `reconciliation_errors`;
  wires 3 new counters into `payload["meta"]`:
  `position_return_reconciliation_max_abs_error`, `position_return_cost_line_residual`,
  `carino_clamp_count` (+ retains `position_return_twr_vs_clientside_max_abs_pp`).

**Algorithm (window-global Carino grid)**:
- `k_t = ln(1+R^g_t)/R^g_t`; `K = ln(1+R^g_port)/R^g_port`
- When `1+R^g_t ≤ 0`: clamp `k_t=1`, increment `carino_clamp_count`
- `C_i = Σ_t (k_t/K) · w_{i,t} · (ρ_{i,t}−1)` (LIFETIME, not streak-scoped)
- `__cost__` synthetic line: `C_cost = Σ_t (k_t/K)·(−δ_t)` (RAW un-rounded δ_t)
- GROSS identity: `Σ_i C_i = R^g_port` (~1e-11 float floor)
- NET identity: `Σ_i C^n_i + C_cost = R^n_port` (closed by un-rounded δ_t)
- Condition C1: price relatives lifted from engine's `price_on` closure (no second price walk)

**Invariant gates**: Rule 16 annotate-only N/A (no scoring change) · Rule 18 obs-first YES
  (new counters in `meta`, no frontend read, defense UNCHANGED at 36).

**Schema triple**: untouched (`backtest_pit.json` `meta` dict is hand-built, not in the Pydantic↔TS↔snapshot triple).

**Verify**: ruff PASS · pytest offline GREEN — `tests/test_portfolio/test_position_returns.py` 199 tests pass (+13 from this PR) · schema_check PASS. The 3 prior 2-tuple→4-tuple `reconciliation_errors` unpacks are fixed (test-engineer, commit `e28e4056d`).

**Test coverage added (+13)**: the 3 contract-change unpack fixes + 13 new behaviors —
`_build_carino_grid` empty / zero-return-limit / `1+R≤0` clamp · `_compute_contribution_from_sub_periods`
absent-ticker / missing-price-relative-leg · **C3 GROSS identity** `|Σ C_i − R^g_port| < 1e-9`
(deterministic 3-ticker book + mid-window entry + a Hypothesis `@given` Dirichlet property) ·
NET identity near-zero-δ path · `carino_clamp_count` propagation · `sub_periods=None` PR-2a compat.
**NET cost-line honesty**: the geometric cross-term (`δ × R`, ~8e-5 at 20bps) is emitted as the
DIAGNOSTIC counter `position_return_cost_line_residual` with NO hard assert in production — an
inherent Carino limitation, surfaced not swallowed.

**SHADOW constraint**: frontend does NOT read `contrib_nav_pts` until PR-2b adds a UI surface
gated on ≥ 1 cron confirming the C3 reconciliation counters.

**Unblocks**: PR-2b (rotation-history drawers — can now trust GROSS identity closes to ~1e-11)

**Gate**: quantrank-reviewer + defense-layer-auditor at Draft→Ready.

### PR-2c follow-up: per-window reconciliation fix (2026-06-26)

**Bug fixed**: `reconciliation_errors()` was comparing `Σ pr.contrib_nav_pts/100` from the
flat `_pos_returns` map (ONLY current holders + names sold at the latest rebalance — ~10
tickers with MIXED partial attribution windows) against `R^g_port` (FULL 10-year gross NAV).
This window-set mismatch produced `position_return_reconciliation_max_abs_error = 7.006`
instead of the expected ~1e-11.  The Carino math was correct; the wiring paired mismatched
position-sets.

**Root cause**: the flat `position_returns` dict covers ~10 tickers whose individual
`C_i` sums to ~+131.6% (they hold partial, mixed-entry-window lifetimes), not the full
attribution universe that closes to R^g_port = +832%.  The identity
`Σ_i C_i = R^g_port` holds only when `C_i` is summed over ALL tickers that EVER held
a position in ANY sub-period.

**Fix** (`compute/portfolio/position_returns.py`):
- Replaced the buggy `contrib_sum = Σ pr.contrib_nav_pts/100` GROSS-identity leg with
  a SubPeriod-based computation that uses two checks:
  1. **Per-window BHB primitive**: `max_t |Σ_i w_{i,t}·(ρ_{i,t}−1) − R^g_t|` —
     verifies the engine's Brinson-Hood-Beebower invariant for each sub-period directly
     from `SubPeriod.start_weights_gross` / `price_relatives` / `gross_sub_return`.
  2. **Full-period Carino chain**: `|Σ_t (k_t/K)·R^g_t − R^g_port|` — verifies the
     multi-period geometric linking from sub-period gross returns to the total gross NAV.
  `gross_identity_error = max(chain_err, max_window_bhb_err)` — stricter of both.
- Fixed **cost-line residual** to use `|R^g_port + C_cost − R^n_port|` (SubPeriod-based
  R^g_port) instead of the old `|contrib_sum + C_cost − R^n_port|` which carried the
  same flat-map subset error.
- Added `compute_window_contributions(sub_periods, kt_over_K)` — new public primitive
  returning `{window_idx: {ticker: contrib_fraction}}` for the PR-2b display layer.
  Each `result[t][ticker] = (k_t/K)·w_{i,t}·(ρ_{i,t}−1)`; missing price-relative
  degrades to `None` (never raises); empty `sub_periods` returns `{}`.

**No signature change**: `reconciliation_errors()` signature is unchanged; callers in
`scripts/backfill_portfolio_pit.py` need no rewiring.

**Verify**: `ruff check .` PASS · `tests/test_portfolio/test_position_returns.py` 58 PASS ·
full offline suite 3078 PASS / 10 SKIP (pre-existing osap/ipca/qlib/shallow-clone).

**Coverage needed (for test-engineer)**:
- Positive 2-window fixture: build 2 SubPeriods with known weights/price-relatives;
  assert `gross_identity_error < 1e-9` on the fixed code.
- Negative regression guard: simulate the OLD wiring (compute flat `position_returns`
  for a partial-history subset and sum their `contrib_nav_pts`) and assert the old
  error `≥ 1.0` (i.e., the bug would have fired); confirms the fix addresses the root cause.
- Cost-line identity: single SubPeriod with cost_drag > 0; assert `cost_line_residual < 1e-9`.
- `compute_window_contributions` nominal: verify `Σ_t Σ_i result[t][i]` ≈ `R^g_port` for
  a 2-ticker, 3-window fixture.
- `compute_window_contributions` degradation: missing price-relative → `None` in that
  window's dict, no raise.
- Hypothesis Dirichlet property: random Dirichlet-weights + random price-relatives →
  `gross_identity_error < 1e-9` (replaces the 3-ticker deterministic fixture for
  property-based coverage; `deadline=None` on slow CI).

---

## agents — new `agent-output-verifier` cross-cutting fact-checker (in flight, 2026-06-26)

**Branch**: `claude/subagents-agent-validation-n579a5`

Adds a 26th subagent, `.claude/agents/agent-output-verifier.md` (Tier 4
Operations · opus · `effort: max` · read-only `Read/Bash/Grep/Glob`) — the
team's adversarial fact-checker / "จับผิด" seat. It re-derives every
*checkable* claim another agent (or the main session) emits — numbers,
`file:line` refs, coverage %, flag counts, citations, "Top-5 rotated"
verdicts, cross-report consistency — against ground truth (repo files ·
`frontend/public/data/*.json` · `git` · `schema_check` · the CLAUDE.md
academic-anchor list) and returns a per-claim CONFIRMED / REFUTED / STALE /
UNSUPPORTED / UNVERIFIABLE verdict + a TRUSTWORTHY / TRUSTWORTHY-WITH-
CORRECTIONS / DO-NOT-ACT gate. It addresses the one failure mode every
other agent shares — a confident, fluent, *wrong* sentence — and is the
backstop the orchestrator inserts before ACTING on a high-stakes claim
(release GO / destructive command / Mark-Ready) or when two reports
disagree. NOT run per-report (cost); read-only — it never fixes, only
routes the fix back to the owning agent (a mis-citation → ESCALATE
methodology-scientist). Distinct from the domain auditors
(`defense-layer-auditor` / `stock-detail-auditor` / `data-analyst` audit the
DATA; this audits an agent's CLAIMS *about* the data/code/git).

**Why opus**: catching a capable model's fluent-but-wrong output needs at
least as much reasoning headroom as producing it did. Model split moves
5 opus / 20 sonnet → **6 opus / 20 sonnet** (26 total); effort tally
23/25 max → **24/26 max** (the 2 `high` script-runners unchanged).

**Docs (lockstep)**: `.claude/agents/README.md` (Tier 4 row + count 25→26 +
model-split + effort + new **Flow 9 — Output verification** + tier
rationale) · `CLAUDE.md` (§Layout count + §Auto-routing role/table row +
opus list + §Spawn-discipline flow/split/effort counts) · `AGENTS.md`
(tree count + Tier 4 note + sonnet-pool count) · `.claude/agents/TEAMS.md`
(comparison-table + companion-docs counts) · `PHASE_STATUS.md` ·
`CONTEXT.md` · `WORKFLOW.md` · `docs/GOTCHAS.md`
(present-tense count 25→26; historical "5 fable agents" preserved).

**No code / schema / workflow touched** — agent + docs only; rankings,
schema triple, and defense layer (36) BYTE-IDENTICAL / UNCHANGED.

**Verify**: no Python / TS / schema surface touched → ruff / pytest /
schema_check / tsc N/A; doc-and-agent-frontmatter change only.

**Gate**: `docs-reviewer` (doc substance) + `phase-coordinator` Mode B
(CLAUDE.md + AGENTS.md lockstep) at Draft→Ready.

---

## agents — agent-output-verifier auto-fire hardening: MUST-invoke + verify-claims.sh hook (in flight, 2026-06-26)

**Branch**: `claude/subagents-agent-validation-n579a5` (follow-up to merged #621)

Strengthens `agent-output-verifier` from soft-proactive to **MUST-invoke at
the act-on-a-claim gates**, plus a 4th every-turn hook so the orchestrator
auto-fires it without an explicit user command (user request: "ระบบดึงมาใช้
เองอัตโนมัติได้ไหม" → MUST-invoke + hook-reminder option).

- `.claude/agents/agent-output-verifier.md` — `description:` rewritten to lead
  with "MUST be invoked (no confirmation) before the orchestrator ACTS on a
  high-stakes agent claim — a release GO, a destructive command, a Mark-Ready
  / merge flip, a 'Top-5 rotated' / 'coverage 99%' / 'threshold matches
  <paper>' assertion — and when two agent reports disagree." Still NOT
  per-report (cost); still read-only. Model/effort/tools unchanged.
- `.claude/hooks/verify-claims.sh` — NEW UserPromptSubmit hook (the SECOND
  every-turn injector alongside `delegate-first.sh`). Injects a ~70-token
  "VERIFY-BEFORE-ACTING" `hookSpecificOutput.additionalContext` pointer so
  the verify-before-acting reflex stays top-of-mind every turn. Fail-open,
  5s timeout, content-agnostic. **A hook cannot itself spawn a subagent**
  (the model does) — the hook only nudges; the MUST-invoke description is
  what makes the orchestrator actually fire it.
- `.claude/settings.json` — wires `verify-claims.sh` as the second
  UserPromptSubmit hook (validated JSON).
- Docs (lockstep): `CLAUDE.md` (§Layout hooks 3→4 + routing-table row now
  MUST-invoke) · `AGENTS.md` (tree "TWO UserPromptSubmit hooks" + hook-list
  bullet) · `.claude/agents/README.md` (MUST-invoke list + Operations-tier
  fires note) · `CONTEXT.md` (hook count 3→4). The README MUST-invoke list
  was also corrected to include ci-triage-engineer / incident-commander /
  methodology-scientist (their descriptions already say "MUST be invoked";
  the old list of 4 was stale).

**No code / schema / workflow touched** — agent + hook + settings + docs
only; rankings, schema triple, defense layer (36) BYTE-IDENTICAL / UNCHANGED.

**Verify**: `verify-claims.sh` smoke-tested (emits valid JSON); `settings.json`
parses; no Python / TS / schema surface → ruff / pytest / schema_check / tsc
N/A.

**Caveat surfaced to user**: even MUST-invoke + hook is orchestrator-driven,
not hook-enforced — hooks can inject reminders but cannot spawn agents. This
is the strongest "automatic" the harness supports short of per-report (which
was rejected on cost).

**Gate**: `docs-reviewer` + `phase-coordinator` Mode B at Draft→Ready.

---

## PR-2b — feat(frontend): MWR/Carino return redesign — frontend unify (in flight, 2026-06-26)

**Branch**: `claude/mwr-rotation-unify-pr2b`

**Unifies** the user-facing return display onto the locked MWR headline. Surfaces PR-1
(#614 MWR/TWR engine), PR-2a (#618 per-quarter) and PR-2c (#619 Carino) in the frontend.

**Current-picks "Your return" column (AiPickAdaptiveBranch)**:
- Replaced `adaptivePlSince` point-to-point useMemo (streak walk over
  `entryCloses`/`lastCloses`) with a lookup into `data.mwrByTicker[ticker]` from the
  top-level `position_returns` (PR-1 #614). The column header changes from "Return" to
  "Your return" when MWR data is present (conditional on `hasMwr`); falls back to "Return"
  with the old description text for pre-#614 artifacts.
- TWR ("Stock price return") shown as a muted secondary line under the MWR headline when
  `|twr_pct − mwr_pct| ≥ 0.05pp` — suppressed when the two are essentially identical.
- Sold rows use the same MWR lookup (engine records final MWR at rotation). Graceful
  degradation: empty `mwrByTicker` → all cells render '—' (pre-engine artifact path).
- `adaptivePlSince` useMemo completely removed from the adaptive branch. `entryCloses`/
  `lastCloses` are still consumed by the legacy slider branch (`AiPickSliderBranch`),
  which is unchanged.

**Rotation-history per-quarter drawers (HoldingsTimeline.tsx)**:
- New accordion-based rotation history: each quarter row is a `<button>` that reveals a
  slide-down `QuarterDrawer` detail table (# · Status · Ticker · Sector · Your return ·
  Weight). CSS `grid-rows: 0fr → 1fr` transition for height-correct reveal.
- Return column = `entry.mwrByTicker[ticker].mwr_pct` (per-rebalance MWR from
  `rebalances[i].position_returns`, PR-2a #618). Pre-PR-2a artifacts render Return as
  '—' with a "pre-engine artifact" notice below the drawer.
- TWR shadow ("Stock price return") shown smaller beneath MWR when they differ (same
  `≥ 0.05pp` threshold). `partial_history=true` → "(partial)" affordance note.
- Plain-text tickers in collapsed button (no `<a>` in `<button>` — invalid HTML per
  WHATWG); clickable ticker links live in the expanded QuarterDrawer only.
- `MwrReturnCell` component shared between held and sold rows within the drawer.
- `aria-expanded` / `aria-controls` a11y pair on each button. `min-h-[44px]` touch
  target. `motion-reduce:duration-0` on the grid-rows transition.

**Shared helpers (`frontend/lib/portfolio-format.ts`)**:
- Extracted `apportionWeightLabels` + `pctStr` + `toneClass` from `AiPickPortfolio.tsx`;
  added `twrToneClass` (muted emerald-600/rose-600 vs headline emerald-700/rose-700).
- Both `AiPickPortfolio.tsx` and `HoldingsTimeline.tsx` import from `portfolio-format.ts`.
- Local duplicates in `AiPickPortfolio.tsx` removed.

**Types / data pipeline**:
- `frontend/lib/types.ts`: added `MwrPositionReturn` type; extended `AiPickTimelineEntry`
  with `mwrByTicker?` + `weightByTicker?`; extended `BacktestRebalance` with
  `position_returns?`; added `mwrByTicker: Record<string, MwrPositionReturn>` to
  `AiPickData` (non-optional, may be empty `{}`).
- `frontend/lib/data.ts`: reads top-level `position_returns` from `backtest_pit.json`
  into `mwrByTicker`; maps per-rebalance `position_returns` into each `AiPickTimelineEntry`;
  resolves `weightByTicker` from `band_weights` / `weights_by_count[adaptiveCount]` /
  largest-count key fallback. Schema triple UNTOUCHED (view-model-only fields).

**Rule-18 cron gate**: DRAFT only — flip-to-Ready waits on ≥ 1 cron landing the
post-#619 per-quarter `position_returns` in `main`'s `backtest_pit.json`. Current
artifact (`generated_utc: 2026-06-26T00:30:32Z`) has top-level `position_returns` (PR-1)
but no per-rebalance `position_returns` (PR-2a not yet run). The UI gracefully degrades
in that state: Current-picks shows MWR; QuarterDrawer Return shows '—'.

**Per-window Carino CONTRIBUTION**: deferred to a future enhancement — v1 drawers show
per-quarter MWR RETURN, not per-window NAV contribution. `compute_window_contributions`
(PR-2c) exists but is not wired to the frontend yet.

**Tests** (`frontend/lib/portfolio-format.test.ts`): 35 new vitest tests covering
`apportionWeightLabels` (Hamilton apportionment, null handling, realistic 9-stock basket),
`pctStr` (formatting, typographic minus, rounding), `toneClass`, `twrToneClass` (dark:
pair invariant, muted-vs-headline structural check), and MWR feed integration scenarios
(TWR shadow threshold, graceful degradation, partial_history).

**Verify**: `schema_check` PASS · `tsc --noEmit` PASS · `next build` PASS · `vitest run`
275/275 PASS.

**A11y fixes (design-reviewer, 2026-06-26)**: (1) outer return-cell `<span>` in both held-row
and sold-row IIFEs now carry `aria-label` composing MWR + TWR + partial context; inner child
spans are `aria-hidden` — matches `MwrReturnCell` pattern already correct in
`HoldingsTimeline.tsx`. (2) "Your return" column header span gains `aria-label` paired with
existing `title=`. (3) Threshold copy aligned: "≥0.1pp" → "≥0.05pp" in header `title` text
and inline comments (code + tests already at 0.05 — copy-only fix). (4) Drawer transition
aligned: `motion-reduce:duration-0` → `motion-reduce:transition-none` for intra-component
consistency with the chevron. Commit `4587c0fad`. `tsc` PASS · `next build` PASS · `vitest`
275/275 PASS. Branch ready for PR flip-to-Ready (cron gate still applies).

---

## tooling — error-reduction toward ~0: consistency guard + preflight + ratchet + verification panel (in flight, 2026-06-26)

**Branch**: `claude/subagents-agent-validation-n579a5` (follow-up to #621/#622)

Four defense-in-depth layers to drive the SYSTEMATIC error classes toward
~0% (literal 0 unreachable — LLMs are probabilistic; this determinizes the
determinizable + adds independent layers + a ratchet). User ask: "ต่อยอด
ให้ความผิดพลาดเข้าใกล้ 0%".

**Layer 1 — deterministic consistency guard** (`tools/check_agent_hook_consistency.py`
+ `ci.yml` step + `tests/test_agent_hook_consistency.py`, 8 tests): derives
every structural count from the filesystem + agent frontmatter + settings.json
and asserts the hardcoded doc anchors (CLAUDE.md / AGENTS.md / README / CONTEXT
/ PHASE_STATUS) match — agents (26) / opus-sonnet split (6/20) / effort split
(24/2) / hooks (4) / flows (9) / tier sums. Catches the EXACT count-drift class
that `docs-reviewer` (an LLM) caught 3× across #621/#622 — now deterministic,
~0% miss, free, forever. No number lives in the guard; negative-tested (corrupt
a count → exit 1).

**Layer 2 — verification-ladder runner** (`tools/preflight.py` +
`tests/test_preflight.py`, 7 tests): one command runs the CLAUDE.md ladder;
cheap deterministic rungs (ruff + the 3 guards) always, heavy rungs (pytest /
schema_check / tsc) gated on the changed surface (mirrors the ci.yml
paths-filter; detects untracked new files; `--all` forces all). Removes the
"forgot a rung" process-skip class locally. Honest limit: no harness pre-push
hook, so it's opt-in; CI is the hard gate, preflight the fast local mirror.

**Layer 3 — Error→regression ratchet** (CLAUDE.md §Conventions bullet +
`docs/LESSONS_LEARNED.md` entry + §Commands ladder note): the standing rule —
a *mechanical* error caught by anyone becomes a deterministic guard (test or
`tools/` check) in the SAME fixing PR. LLM review is the net for *novel*
errors, never the standing defense for mechanical ones. Layer 1 IS the first
ratchet instance (count-drift → guard).

**Layer 4 — adversarial verification panel** (agent-output-verifier.md §Panel
mode + TEAMS.md recipe #6 + auto-proposal row): for irreversible / expensive-
to-undo claims (release GO / destructive command / cron-gating accounting-
equation), the orchestrator runs 3 `agent-output-verifier` lenses (re-derive ·
refute · completeness) and acts on majority (≥2/3 TRUSTWORTHY, any CRITICAL
REFUTED → DO-NOT-ACT). Kills the single-verifier-confidently-wrong SPOF.
Reserved for irreversible gates (cost / diminishing returns) — routine
verification stays a single pass.

**Lockstep**: CLAUDE.md (§Conventions ratchet bullet + §Commands preflight +
§Layout-adjacent) · AGENTS.md (deterministic-drift-guards paragraph) ·
`docs/LESSONS_LEARNED.md` · `.claude/agents/{agent-output-verifier,README}.md`
+ `TEAMS.md`. New code is `tools/` + `tests/` only — NO compute/scoring/schema
touched; rankings + schema triple + defense layer (36) BYTE-IDENTICAL.

**Verify**: ruff PASS (tools/ + new tests) · the 2 new tools' tests 15 PASS ·
`check_agent_hook_consistency.py` PASS + negative-tested · `ci.yml` adds 1
guard step. Full offline pytest = CI (local env lacks `.[dev,factors]`).

**Gate**: `quantrank-reviewer` (new tools/ logic) + `security-reviewer`
(ci.yml edit) + `test-engineer` (coverage) + `docs-reviewer` +
`phase-coordinator` Mode B at Draft→Ready.

---

## PR #624 — feat(compute): Proposal C-1 high-conviction gate counter slice 1 (observability) (in flight, 2026-06-26)

**Scope.** Proposal C-1 — measuring the marginal bite of the loss-chance leg in the
ALREADY-LIVE high-conviction gate. The `gate="high_conviction"` has been the production
selection driver in the backfill since PR #604; this PR adds PURELY ADDITIVE shadow counters
to `Metadata` so the cron reports how many universe names clear the gate and whether any
backtest rebalance leg ever starved below the 5-name floor. Rankings/scores/flags are
BYTE-IDENTICAL. Defense layer UNCHANGED at 36.

**Note on C-2 (#617).** Proposal C-2 (MoS conviction tilt, `mos_tilt_shadow_max_delta_pp`)
was merged before this PR on branch `claude/fund-performance-rankings-f8x4o1`; schema is
now `0.10.38-phase8pilot` → this PR bumps to `0.10.39-phase8pilot`.

**What is built.**

- `compute/output/schemas.py` — 3 new additive `Metadata` fields (all `int | None` or
  `bool | None`, default `None`):
  - `high_conviction_count: int | None` — full-gate pass count (all 5 legs) over the ranked
    universe.
  - `high_conviction_ex_loss_chance_count: int | None` — count passing legs 1-4 ONLY (leg 5 =
    loss_chance ≤ 45 OMITTED). This is the marginal-bite denominator:
    `bite = high_conviction_ex_loss_chance_count − high_conviction_count`.
    By construction `ex_loss_chance_count ≥ high_conviction_count` always.
    A materially positive bite → keep leg 5. A bite ≈ 0 → drop candidate.
    Implemented by `_passes_ex_loss_chance(c)` in `compute/main.py`, which reuses
    `is_eligible` / `HIGH_CONVICTION_RECOMMENDATIONS` / `HIGH_CONVICTION_COMPOSITE_MIN`
    constants from `compute.portfolio.weights` (no inlined literals).
  - `high_conviction_below_floor: bool | None` — starvation canary derived from reading
    `backtest_pit.json` (same artifact-read pattern as C-2). True if ANY rebalance leg has
    `eligible_high_conviction_count < ADAPTIVE_MIN_PICKS (5)`; None when artifact absent.

- `compute/main.py` — two new blocks before the `Metadata(...)` call:
  1. `_passes_ex_loss_chance(c)` pure predicate + `_count_high_conviction(summaries)` helper
     (try/except → None). Iterates the full ranked `summaries` list, builds a `PickCandidate`
     per row, calls `is_high_conviction(c)` (5-leg count) AND `_passes_ex_loss_chance(c)`
     (4-leg count), returns `(hc_count, ex_loss_chance_count)`.
     Log line reports all three: count, ex_loss_chance, bite.
  2. C-1 below_floor canary: reads `backtest_pit.json` artifact, extracts
     `eligible_high_conviction_count` per rebalance, checks if any leg < 5. try/except → None.
  New imports (expanded): `from compute.portfolio.weights import (HIGH_CONVICTION_COMPOSITE_MIN,
  HIGH_CONVICTION_RECOMMENDATIONS, PickCandidate, is_eligible, is_high_conviction)`.

- `compute/config.py` — schema `0.10.38` → `0.10.39-phase8pilot`.

**Byte-identity proof.** `compute/main.py` does NOT call `select_picks`,
`inverse_vol_weights`, or `_band_book`. The only additions are two try/except blocks that
read `summaries` (already fully built) and `backtest_pit.json` (already written by the
PIT-backtest refresh earlier in the cron). No summaries / StockDetail / risk_flags /
composite_score fields are mutated.

**Pre-registered gate-flip condition (methodology C-1 RATIFY-WITH-CONDITION 2026-06-26):**
hc_count ≥ `ADAPTIVE_MIN_PICKS + 2` (≥ 7) across ALL crons AND ALL backtest rebalance
legs AND the marginal-bite read (`high_conviction_ex_loss_chance_count − high_conviction_count`)
resolves the loss-chance leg — keep `loss_chance ≤ 45` if bite is materially > 0; drop the
leg if bite ≈ 0 across crons. NOT a bare below_floor gate. Issue #130.

**Schema triple**: 3 new fields added to `Metadata` → TS mirror + snapshot regen NEEDED.
frontend-builder: add to `Metadata` in `frontend/lib/types.ts`:
```
high_conviction_count: number | null;
high_conviction_ex_loss_chance_count: number | null;
high_conviction_below_floor: boolean | null;
```
Then regen `frontend/lib/schema-snapshot.json`.

**Tests needed** (test-engineer):
  - `_count_high_conviction` with an empty list → (0, 0).
  - All-pass candidates (all 5 legs pass) → `hc_count == universe_size` AND
    `ex_loss_chance_count == universe_size`.
  - Loss-chance leg bite: mix where some candidates fail ONLY leg 5 (`loss_chance_pct > 45`
    but pass legs 1-4) — verify `ex_loss_chance_count > hc_count` and the gap equals the
    blocked count; and `ex_loss_chance_count − hc_count == bite_count`.
  - Invariant: `ex_loss_chance_count ≥ hc_count` always (any list, any data).
  - `_passes_ex_loss_chance` is insensitive to `loss_chance_pct`: a candidate with
    `loss_chance_pct=99.0` but otherwise passing legs 1-4 → returns True.
  - Adapter faithfulness: verify that a `StockSummary`-equivalent input maps correctly
    to the `PickCandidate` fields and `is_high_conviction` returns the expected result.
  - `high_conviction_below_floor` from a mock `backtest_pit.json`:
    - all legs >= 5 → False.
    - one leg < 5 → True.
    - absent artifact → None.
  - `Metadata` round-trip: construct `Metadata(..., high_conviction_count=40,
    high_conviction_ex_loss_chance_count=45, high_conviction_below_floor=False)` →
    `model_dump()` → round-trip preserves values; extra="forbid" does not error.

**Files**: `compute/output/schemas.py` (+3 fields) · `compute/main.py` (+helper +
two try/except blocks + import) · `compute/config.py` (schema bump) ·
`CLAUDE.md` (§In-flight + §Gotchas) · `AGENTS.md` (§Phase status) ·
`PHASE_STATUS_INFLIGHT.md` (this) · `docs/METHODOLOGY.md` (C-1 section).

**Gate**: frontend-builder (mirror 3 fields) + test-engineer + schema-sentinel +
quantrank-reviewer + defense-layer-auditor at Draft→Ready.

---

## PR #TBD — fix(portfolio): gap-aware latest streak for per-position return display (in flight, 2026-06-26)

`compute/portfolio/position_returns.py` — `_extract_streaks` gained a new
keyword-only param `all_rebalance_dates: Sequence[str] | None = None`. When
`None` (default), behavior is BYTE-IDENTICAL to before (backward-compat).
When provided, the function also splits a streak on a **rebalance-date gap**:
if two consecutive held legs are not adjacent in `all_rebalance_dates` (ticker
was absent ≥ 1 intervening rebalances), the current streak is closed and a
new one begins. This fixes the root cause of cross-gap chaining in the
backfill, where absent quarters produce a DATE JUMP in per-ticker legs with no
weight-0 sentinel, causing `_extract_streaks` to see one continuous run spanning
the gap.

Callers updated: `_compute_flat_latest_returns` passes the full
`band_legs`-derived date axis; `compute_position_returns_per_quarter` passes a
PIT-truncated prefix (`all_dates_full[:rebal_idx+1]`) to preserve Fix-#3
look-ahead safety. The `reconciliation_errors` bare call `_extract_streaks(ticker,
legs, {})` (multi-streak skip for `pp_twr_error`) is LEFT BARE — no
`all_rebalance_dates` — so the Carino #619 reconciliation (which operates on
`sub_periods` directly) stays BYTE-IDENTICAL.

**Verified before commit**:
- Local replay on committed `backtest_pit.json`: ALL → 2026-05-15 (was 2021-05-15),
  KLAC → 2020-08-14 (was 2016-08-14), CF → 2024-05-15 (was 2023-05-15);
  SYF (single-streak, 4 legs) and IBKR (single-leg) BYTE-IDENTICAL.
- `ruff check .` PASS.
- `pytest tests/test_portfolio/test_position_returns.py -q` — 64/64 PASS.
- Offline pytest (excluding missing-module osap) — 3124 PASS / 10 SKIP.

**Schema triple**: untouched (no schema field change; `backtest_pit.json` is
a hand-built artifact, not in the Pydantic↔TS↔snapshot triple).
**Rule 16 / annotate-before-veto**: N/A (display-only fix, no scoring/veto change).
**Rule 18 / observability-first**: N/A (no new external data source).
**Defense layer**: UNCHANGED at 36. Rankings/scores/flags BYTE-IDENTICAL.

**Coverage needed (for test-engineer)**:
1. `test_extract_streaks_gap_aware_splits_on_date_gap`: verify that two
   all-positive legs with a gap in `all_rebalance_dates` produce 2 streaks.
2. `test_extract_streaks_gap_aware_none_is_byte_identical`: same legs without
   `all_rebalance_dates` produce 1 streak (backward-compat).
3. `test_flat_path_since_date_gap_ticker`: construct a band_legs where a ticker
   is absent for 1 rebalance (gap), call `compute_position_returns`, assert
   `since_date` is the re-entry date not the first entry.
4. `test_per_quarter_since_date_gap_ticker_pit_safe`: same gap scenario in
   `compute_position_returns_per_quarter`, assert the latest quarter shows
   the re-entry `since_date` and historical quarters up to the drop-date show
   the original entry date (PIT-safe).
5. `test_reconciliation_bare_call_unchanged`: multi-streak name (two real streaks
   via weight-0 leg) — assert `reconciliation_errors` still counts it as
   multi-streak (using the bare `_extract_streaks(ticker, legs, {})` call).
## PR #628 — Proposal E: turnover/hysteresis diagnostic + liquidity capacity tilt (in flight, 2026-06-26)

**Branch**: `claude/fund-performance-rankings-f8x4o1` (same branch as F/D/A/C-2/C-1; Proposal E is the final
slice of the legendary-fund 6-proposal program).

**Schema**: `0.10.39` → **`0.10.40-phase8pilot`**.
**Status**: SHADOW / OBSERVABILITY-ONLY. Live `band_book` / `band_weights` /
`band_carry_count` / `band_legs_for_nav` / `nav.adaptive.*` are BYTE-IDENTICAL.
Defense layer UNCHANGED at 36 (`low_liquidity` is an existing annotate; the capacity
tilt is a sizing device, NOT a new flag).

**What landed:**

- `compute/portfolio/weights.py` — 2 new pure functions + 1 constant:
  - `LIQ_CAPACITY_TILT = 0.5` (Tier-2 gut-feel, Amihud 2002 capacity constraint).
  - `book_turnover(curr: set[str], prev: set[str]) -> float` — symmetric-difference name
    turnover `|curr △ prev| / |prev|`; 0.0 when prev is empty.
  - `liquidity_capacity_tilt(base_weights, low_liquidity_tickers, *, haircut=LIQ_CAPACITY_TILT, cap=MAX_WEIGHT) -> dict` —
    `w_i × haircut` for low-liq holdings PRE-renorm, renorm, RE-CAP using the SAME
    iterative pin-and-redistribute routine as `inverse_vol_weights` (NOT naive clip).
    Identity guards: empty liq set → base_weights unchanged; all liq → renorm cancels.

- `scripts/backfill_portfolio_pit.py` — SHADOW wiring (per-rebalance, mirrors C-2 pattern):
  - **Stateless counterfactual**: `_band_book(full_order, scores_this, tenure=set())` each leg.
  - **DEFENSE-PRECEDENCE ASSERTION** (binding condition 1): asserts no active-veto ticker
    appears in EITHER `band_book` OR `_stateless_book`. `AssertionError` surfaces, never silenced.
    Covers BOTH books simultaneously.
  - **Turnover triple**: `_turnover_band_pct`, `_turnover_stateless_pct`, `_turnover_reduction_pp` —
    threaded via `_prev_band_book_set` / `_prev_stateless_book_set` across legs.
  - **Liq-capacity tilt shadow**: `_liq_tilted_weights` via `liquidity_capacity_tilt`; `_low_liq_set_this`
    is empty in the backfill (no PIT ADV data); identity path in practice.
  - Per-rebalance exports in `backtest_pit.json`: `stateless_book`, `turnover_band_pct`,
    `turnover_stateless_pct`, `turnover_reduction_pp`, `liq_tilted_weights`,
    `low_liquidity_holdings`, `liq_tilt_max_abs_weight_delta_pp`.
  - `meta.hysteresis_shadow`: `{enter:65, exit:60, current_live_band:[65,55], liq_haircut:0.5,
    max_weight:0.35, active:false}` — discloses the shadow probe config. `exit=60` is a
    single-DOF shadow re-param only (H-C freeze-lock; live band STAYS 65/55 UNCHANGED).
  - New imports: `ACTIVE_VETO_FLAGS`, `LIQ_CAPACITY_TILT`, `MAX_WEIGHT`, `book_turnover`,
    `liquidity_capacity_tilt`.

- `compute/output/schemas.py` — 2 new `Metadata` canaries:
  - `hysteresis_turnover_reduction_mean_pp: float | None` — mean `turnover_reduction_pp`
    over all backtest legs. H1 gate: mean >= 15pp over >= 4 live rebalances
    (Garleanu-Pedersen 2013 *JF* 68(6)).
  - `low_liquidity_held_count: int | None` — count of `low_liquidity_holdings` in the
    FINAL backtest rebalance leg (the current AI-pick book's liq exposure).

- `compute/main.py` — E canary artifact-read block (same try/except pattern as C-2 + C-1):
  reads `backtest_pit.json`, extracts `turnover_reduction_pp` per leg (mean → canary)
  and `low_liquidity_holdings` from the final leg (len → canary). Both → None on
  absent/unreadable artifact.

- `compute/config.py` — schema `0.10.39` → `0.10.40-phase8pilot`.

- `docs/METHODOLOGY.md` — §Proposal E section: turnover diagnostic, liq-capacity tilt,
  stacking order (inverse_vol → liq_tilt → mos_tilt → single re-cap), defense-precedence
  assertion, flip-gate conditions, academic anchors (Garleanu-Pedersen 2013 / Novy-Marx-
  Velikov 2016 / Amihud 2002).

**Byte-identity proof.** `scripts/backfill_portfolio_pit.py`: all E variables are
underscore-prefixed locals; none assigned to `band_book`, `band_weights_map`,
`band_legs_for_nav`, or any grid variable. `compute/main.py`: the two new canary reads
only read `backtest_pit.json`; they never mutate `summaries`, `meta` fields of scoring
types, `composite_score`, `risk_flags`, or `valuation_warnings`.

**Pre-registered flip-gate conditions (E RATIFY-WITH-CONDITION):**
(1) Defense-precedence assertion NEVER trips across all crons + backtest legs.
(2) `mean(turnover_reduction_pp) >= 15pp` over >= 4 live rebalances (H1, Garleanu-Pedersen).
(3) MAX_WEIGHT holds post-liq-tilt (test suite pins it).
(4) Sidecar tenure only at forward-decoupling.
(5) Methodology re-ratify exit=60 vs live 55 (H-C freeze-lock; H-B/H-C conditions).

**Schema triple**: 2 new fields added to `Metadata` → TS mirror + snapshot regen NEEDED.
frontend-builder: add to `Metadata` in `frontend/lib/types.ts`:
```
hysteresis_turnover_reduction_mean_pp: number | null;
low_liquidity_held_count: number | null;
```
Then regen `frontend/lib/schema-snapshot.json`.

**Tests needed** (test-engineer):
  - `book_turnover`: empty prev → 0.0; same book → 0.0; full swap → 2.0 (symmetric diff
    = |A△B| / |A|, all names replaced); partial overlap.
  - `liquidity_capacity_tilt`: empty base_weights → {}; empty liq set → identity
    (base_weights unchanged); all names flagged → identity (renorm cancels haircut);
    single low-liq holding → haircut applied, renorm correct, MAX_WEIGHT respected;
    post-cap assertion: no output weight > MAX_WEIGHT + 1e-12.
  - Defense-precedence assertion: mock a candidate carrying an ACTIVE_VETO_FLAGS member
    appearing in band_book → AssertionError raised (should NOT be silenced);
    clean book → no assertion error.
  - `Metadata` round-trip: construct with `hysteresis_turnover_reduction_mean_pp=12.5,
    low_liquidity_held_count=0` → `model_dump()` round-trip preserves values;
    extra="forbid" does not error.
  - Identity test for combined stacking order: inverse_vol → liq_capacity_tilt (empty liq
    set) → mos_conviction_tilt (all None mos) should return base weights unchanged
    (both identity guards active simultaneously).

**Files**: `compute/portfolio/weights.py` (+2 fns +1 const) · `scripts/backfill_portfolio_pit.py`
(+E shadow block + init state + meta field + expanded imports) · `compute/output/schemas.py`
(+2 fields) · `compute/main.py` (+E canary block + 2 Metadata args) · `compute/config.py`
(schema bump) · `docs/METHODOLOGY.md` (§Proposal E) · `CLAUDE.md` (§Gotchas + §In-flight) ·
`AGENTS.md` (§Phase status) · `PHASE_STATUS_INFLIGHT.md` (this).

**Gate**: frontend-builder (mirror 2 fields) + test-engineer + schema-sentinel +
quantrank-reviewer + defense-layer-auditor at Draft→Ready.

---

## PR #TBD — feat(frontend): drop per-row TWR "price" + "since" sub-lines from Current-picks return cell (in flight, 2026-06-27)

Owner-requested UI simplification on the home AI-pick Current-picks table
(`frontend/components/AiPickPortfolio.tsx`). The return cell previously rendered
the headline MWR ("Your return", e.g. `+4.7%`) PLUS two grey secondary sub-lines:
the TWR "stock price return" shadow (`+2.7% price`, shown when `|twr − mwr| ≥
0.05pp`) and a `since YYYY-MM` partial-history date. The owner decided one number
is clearer than three and that — between MWR and price-only TWR — the MWR headline
is the honest "what did my money actually earn" figure (money-weighted, total-return,
accounts for rebalance add/trim timing), so both sub-lines are removed.

Frontend-only, NO schema change (the underlying `MwrPositionReturn.twr_pct` /
`since_date` / `partial_history` fields stay on the artifact; the view simply stops
rendering them). Removed in BOTH the Held/New holdings block and the Sold-rows block:
the `twr`/`partial`/`sinceDate`/`twrDiffers` locals, both sub-`<span>`s, the
`twrToneClass` import (export retained in `portfolio-format.ts` — still used by
`HoldingsTimeline.tsx`), and the TWR clause in the column-header tooltip + the
SR aria-label announce array (now a single "Your return X%" string). The
`hasMwr`/`mwrForTicker`/`pctStr(mwr)`/`toneClass(mwr)` headline path is untouched.
Verify: tsc clean · next build 1512 pages · vitest 275/275 green.

**Files**: `frontend/components/AiPickPortfolio.tsx` · `PHASE_STATUS_INFLIGHT.md` (this).

**Gate**: frontend-design-reviewer (visual regression on Current-picks table) at Draft→Ready.

---

## PR — Option-B dividend-pool-and-redeploy shadow NAV (in flight, 2026-06-27)

**Branch**: `claude/dividend-pool-shadow`. **Schema**: `0.10.40` → `0.10.41-phase8pilot`.
**Ratified by**: financial-engineer (spec) + methodology-scientist (RATIFY-WITH-CONDITIONS)
+ data-pipeline-engineer (DATA-HEALTHY).

SHADOW-ONLY: live `nav.adaptive` / headline / rankings stay BYTE-IDENTICAL. Implements
Option-B (pool-and-redeploy): between quarterly rebalances, each holding's ex-date
dividends accumulate as idle cash (0% — methodology condition 1); at each rebalance the
full pool is redeployed into the new inverse-vol target basket. Avoids the Adj-Close
double-count footgun by pricing the shadow path on RAW split-adjusted Close only.

**New in `compute/`**:
- `compute/portfolio/backtest.py` — two new keyword-only params on `build_portfolio_nav`:
  `dividends: Mapping[str, Mapping[str, float]] | None = None` +
  `price_basis: Literal["adjusted","raw"] = "adjusted"`. `None`/`"adjusted"` path is
  BYTE-IDENTICAL. Option-B active only when both `dividends` is not None AND
  `price_basis="raw"`. Emits `cash_at_rebalance` list when active.
- `compute/ingest/prices.py` — `actions=True` added to `_yf_download` (fetches `Dividends`
  column on same HTTP round-trip, zero extra cost; `QR_SKIP_DIVIDENDS=1` escape hatch);
  new `fetch_dividends_panel` helper extracts positive-only ex-date entries from
  pre-fetched price frames, column-absent-graceful for old parquets.
- `scripts/backfill_portfolio_pit.py` — SHADOW block after validation assembly: builds
  raw-close panel, calls `fetch_dividends_panel`, shadow `build_portfolio_nav(...,
  dividends=div_panel, price_basis="raw")` → `nav.adaptive_div_pooled.{gross,net}` +
  A/B-diff artifact fields (`div_pool_nav_delta_pct`, `div_pool_turnover_cost_delta_bps`,
  `div_pool_active=false`, `div_pool_idle_cash_rate=0.0`). Live `band_weights`/NAV
  BYTE-IDENTICAL.
- `compute/output/schemas.py` — 2 new `Metadata` fields: `div_pool_shadow_terminal_nav_delta_pct`
  + `div_stream_coverage_pct` (both `float | None = None`).
- `compute/main.py` — Option-B canary read block (same artifact-read pattern as C-2/C-1/E)
  + 2 new `Metadata(...)` args.
- `compute/portfolio/position_returns.py` — docstring note on pooled-cash Modified-Dietz
  classification (documentation-only, no computation change).

**Schema triple**: `schemas.py` + `types.ts` + `schema-snapshot.json` all updated.
`schema_check` passes.

**Tests written (2)**: `test_div_pool_none_dividends_byte_identical` +
`test_div_pool_accrues_cash_before_redeploy` in `tests/test_portfolio/test_backtest.py`.

**Tests needed** (test-engineer):
  - Sold-name conservation: a name sold at rebalance T with an ex-date in its final
    sub-period has the dividend booked in cash before redeploy → no leakage.
  - Redeploy-not-to-sold-name: weights after redeploy match the new target basket, not
    the old one.
  - Hypothesis NAV≥price-only: for any valid dividend panel, shadow NAV ≥ adj-close
    baseline over same horizon (cash adds non-negative value).
  - Carino closes on B: for the shadow path, the terminal NAV matches price_value +
    cash_at_last_rebalance × (1+0%) (no leakage).
  - `fetch_dividends_panel` with no `Dividends` column → returns `{}` gracefully.
  - `fetch_dividends_panel` with `QR_SKIP_DIVIDENDS=1` env var → returns `{}`.
  - `build_portfolio_nav` with `dividends={}` (empty) + `price_basis="raw"` →
    `_div_pool_active=True` but no cash accrues; NAV differs from adj baseline
    only by carry-forward-on-raw vs adj-close drift.

**Files**: `compute/portfolio/backtest.py` · `compute/ingest/prices.py` ·
`scripts/backfill_portfolio_pit.py` · `compute/output/schemas.py` · `compute/main.py` ·
`compute/portfolio/position_returns.py` · `compute/config.py` (schema bump) ·
`frontend/lib/types.ts` · `frontend/lib/schema-snapshot.json` ·
`tests/test_portfolio/test_backtest.py` · `tests/test_config.py` (schema pin) ·
`PHASE_STATUS_INFLIGHT.md` (this entry).

**Gate**: schema-sentinel + test-engineer + quantrank-reviewer + defense-layer-auditor at
Draft→Ready.

---

## PR #TBD — docs: Mode C reconciliation to schema 0.10.41 (#631/#632 merged) (in flight, 2026-06-27)

Mode C doc-lockstep bump after #631 (Option-B dividend pool-and-redeploy SHADOW NAV,
schema 0.10.40→0.10.41) and #632 (frontend: drop per-row TWR `% price`+`since` sub-lines)
merged to main 2026-06-27. CLAUDE.md + AGENTS.md were still declaring schema 0.10.40
(the two PRs only landed INFLIGHT entries, not the §Phase status / version-state substance
bump) — this reconciles all four canonical trackers to 0.10.41:
- CLAUDE.md §Phase status: 0.10.41 promoted to current (0.10.40 → "Prior"); §In-flight
  records #631/#632 merged + the deferred Q3 items; new §Gotchas entry for the div-pool
  shadow (artifact-vs-triple split, BYTE-IDENTICAL guard, `actions=True` column-append,
  HARD-CONSTRAINT no-scoring-read, headline-flip = future owner-signed PR).
- AGENTS.md §In-flight: reconciled (was stale — still listed the merged legendary-fund
  program as in-flight); now "Nothing in flight", schema 0.10.41, #631/#632 recorded.
- SKILL.md §schema-version table: new 0.10.41 row.
- PHASE_STATUS.md §Current state: date 2026-06-27, Schema cell bumped to 0.10.41.

Docs-only — NO code/schema/workflow change; rankings byte-identical (trivially).

**Files**: `CLAUDE.md` · `AGENTS.md` · `SKILL.md` · `PHASE_STATUS.md` · `PHASE_STATUS_INFLIGHT.md` (this).

**Gate**: docs-reviewer (substance check) at Draft→Ready.

---

## PR #TBD — feat(frontend): drop TWR "% price" + "partial" sub-lines from Rotation-history drawer (in flight, 2026-06-27)

Owner-requested follow-up to #632: that PR removed the per-row TWR "stock price
return" shadow line and the partial-history note from the Current-picks table
(`AiPickPortfolio.tsx`), but the SAME two sub-lines were still rendering in the
**Rotation history** per-quarter drawer (`HoldingsTimeline.tsx` `MwrReturnCell`,
shared by held + sold rows). This applies the identical removal there so both
return surfaces show a single headline MWR ("Your return") number.

Frontend-only, NO schema change (the underlying `MwrPositionReturn.twr_pct` /
`partial_history` fields stay on the artifact; the drawer just stops rendering
them). Removed: the TWR shadow `<span>` (`{pctStr(twr)} price`), the `partial`
note `<span>`, the `twr`/`isPartial` props + their type entries on `MwrReturnCell`,
the `twr`/`isPartial` locals at both call sites (held + sold loops), the `showTwr`
computation, the `twrToneClass` import (export retained in `portfolio-format.ts` —
its own unit test still passes), the TWR clause in the column-header tooltip, and
the TWR/partial entries in the SR aria-label (now a single "Your return X%"
string). The `mwr === null && twr === null` empty-guard simplified to `mwr === null`.
Headline `pctStr(mwr)`/`toneClass(mwr)` path untouched.

Verify: tsc --noEmit clean · next build 1512 pages · vitest 275/275 green.

**Files**: `frontend/components/HoldingsTimeline.tsx` · `PHASE_STATUS_INFLIGHT.md` (this).

**Gate**: frontend-design-reviewer (rotation drawer return column, light+dark, accordion intact) at Draft→Ready.

---

## PR #TBD — feat(frontend): fill blank "—" return cells (entry-instant 0.0% + sold-row realized return) (in flight, 2026-06-27)

Owner-reported: rotation-history + Current-picks "Your return" cells were blank ("—")
in two cases. financial-engineer design (DISPLAY-ONLY-SAFE — Carino reconciliation 4.7e-16
+ headline NAV byte-identical; the artifact values are read as-is, only the rendering of
nulls changes):
- CASE A (initial basket / entry instant): every holding had `mwr_pct=null`,`legs_used=0`
  (return at the instant of purchase = 0 by identity). Display-coalesce `legs_used===0` →
  **0.0%** (neutral tone), keeping the cumulative-since-entry column definition invariant
  across all 40 baskets — alters zero already-validated numbers.
- CASE B (sold rows): the realized exit return already EXISTS in the PRIOR rebalance's
  `position_returns[ticker]` (marked-to-exit-close, PIT-safe). Frontend looks it up from
  `rebalances[i-1]` (+ flat `mwrByTicker` fallback for latest-rebalance sells). GUARD: the
  sold-row return renders in the row cell ONLY — never enters the `<tfoot>` Total-return
  footer / any current-basket aggregate (footer excludes 0-weight sold rows).

Frontend-only, NO schema change, NO compute change (`position_returns.py` untouched).
`HoldingsTimeline.tsx` (`Row.prevMwrByTicker` + `legsUsed` prop on `MwrReturnCell`) +
`AiPickPortfolio.tsx` (`priorMwrByTicker` from `timeline[-2]` + `mwrForSoldTicker`).
+16 vitest contract tests (`return-cell-display.test.ts`). Verify: tsc clean, next build
1512 pages, vitest 291 green.

**Files**: `frontend/components/HoldingsTimeline.tsx` · `frontend/components/AiPickPortfolio.tsx` · `frontend/lib/return-cell-display.test.ts` · `PHASE_STATUS_INFLIGHT.md` (this).

**Gate**: frontend-design-reviewer (return cells, dark-mode tone, no tfoot contamination) at Draft→Ready.

---

## PR #TBD — fix(backfill): PIT sector for removed-from-universe tickers (rotation-history "Unknown") (in flight, 2026-06-27)

Owner-reported: the rotation-history (and AI-pick) holdings showed sector "Unknown"
for tickers that have since dropped out of the current S&P universe (WU, RHI, HP, …).
ROOT CAUSE (verified): `data/historical_sector.parquet` HAS correct PIT sectors for
these names (WU=Information Technology, RHI=Industrials, HP=Energy; 0 "Unknown" rows
across 19,661) and the `_pit_sector(ticker, as_of)` helper reads it correctly — but the
DISPLAYED holding/candidate sector was stamped from `sector_by_ticker` (the CURRENT-universe
membership map), which omits removed tickers → falls back to "Unknown".

FIX: route the displayed sector through `_pit_sector(t, T)` at the 4 call sites that feed
the rendered output — `full_ranked[].sector` (~1253), `PickCandidate(sector=)` (~1266),
`holdings[].sector` (~1630, via `candidates_by_ticker`), and the `_sector_weights_by_count`
aggregation (~1619, fed the PIT-resolved sector map so buckets agree with per-holding labels).
SELECTION-NEUTRAL: `select_picks` / `is_high_conviction` never read `PickCandidate.sector`
(only composite/risk_flags/recommendation/mos/loss_chance/ticker) — picks + order byte-identical.
Backfill script only (offline artifact generator); live scoring loop + rankings.json untouched;
NO schema change. The displayed sector completes after the next cron regenerates the backtest
with this code (the artifact regen, not this PR, is what updates the site).

+1 test (`test_removed_ticker_gets_pit_sector_not_unknown`). Verify: ruff clean, offline
pytest 492/492 (69 backfill-integration incl. the new one).

**Files**: `scripts/backfill_portfolio_pit.py` · `tests/test_portfolio/test_backfill_integration.py` · `PHASE_STATUS_INFLIGHT.md` (this).

**Gate**: quantrank-reviewer at Draft→Ready.

---

## PR #TBD — fix(backtest): weekend/holiday rebalance entry-price lookup (rotation-history initial-basket null) (in flight, 2026-06-27)

Owner-reported: the initial basket (2016-08-14) showed blank/0.0% "Your return" for every
holding. ROOT CAUSE (proven + financial-engineer RATIFY-WITH-CONDITIONS, DISPLAY-ONLY-SAFE):
the per-quarter "Your return" is designed to show each holding's forward return (entry →
next rebalance), but `_extract_streaks` priced each leg via `_close_on` (EXACT date) while
the terminal already used `_close_on_or_before`. **2016-08-14 is a Sunday** → no exact close
→ entry price None → first leg invalid → rb[0] null (and weekend/holiday legs elsewhere
dropped as "partial"). A clean-data repro confirms rb[0] SHOULD yield a real forward return.

FIX (1 line, `compute/portfolio/position_returns.py` ~368): `_close_on` → `_close_on_or_before`
for the streak entry/leg price — symmetric with the terminal marking, on-OR-before (no
look-ahead), `_is_valid_price`-guarded. The out-of-scope `_close_on` at ~1399 (`pp_twr_error`
diagnostic) is untouched.

BLAST RADIUS — DISPLAY-ONLY-SAFE (financial-engineer traced end-to-end): the Carino
reconciliation (`position_return_reconciliation_max_abs_error` = 4.7e-16) + headline NAV
(+829%) are computed from `sub_periods` / the engine `price_on` closure, structurally disjoint
from this path → byte-identical (delta ZERO). +4 tests (WR-1 positive / WR-2 no-fabrication /
WR-3 reconciliation-invariance regression guard / WR-4 no-look-ahead Hypothesis). Full offline
suite 3206 passed; ruff + schema_check clean; NO schema change.

SEQUENCING: this backend fix + a `backtest_pit.json` regen land BEFORE the separate frontend
PR that reverts #637 Case-A (the 0.0% coalesce) — #637 Case-B (sold-row prior-rebalance
lookup) stays. Post-regen the initial basket shows real forward returns.

**Files**: `compute/portfolio/position_returns.py` · `tests/test_portfolio/test_position_returns.py` · `PHASE_STATUS_INFLIGHT.md` (this).

**Gate**: quantrank-reviewer at Draft→Ready.

---

## loop-engineering subagent — new `loop-engineer` Tier-4 Operations agent (in flight, 2026-06-27)

Adds a 27th project subagent: `loop-engineer` (`.claude/agents/loop-engineer.md`),
a **Loop Engineering** seat in Tier 4 (Operations). Given an assigned task it
DESIGNS the iterative work-loop — the Goal → Context → Action → Check/Fix →
Repeat/Review cycle — instead of answering one-shot: a machine-checkable
definition-of-done, each iteration's exact CHECK command pulled from the
verification ladder (`ruff` → `pytest` → `schema_check` → `tsc` + `next build`
→ `verify-production-output` / `tools/preflight.py`), a FIX-route to the owning
agent per the §Auto-routing table, and a mandatory convergence guard so the loop
provably halts. **Autonomy model — autonomous up to the publish boundary**
(owner decision 2026-06-27): the act→check→fix→repeat iteration self-drives with
NO human between rounds (the CHECK command is the automated arbiter); the ONLY
human gate is authorizing the final irreversible/outward-facing action — push to
`main` · merge a PR · tag a release · any destructive command — per CLAUDE.md
§Spawn discipline. A task that never crosses that boundary (e.g. a local refactor
verified by tests) is fully end-to-end autonomous. Read-only (Read/Bash/Grep/Glob,
no Edit/Write) — it COMPOSES the loop and hands it to the Opus-4.8 orchestrator
to run by dispatching the named agents; it never executes the loop or spawns
peers itself. Model `sonnet`, `effort: max` (open-ended design/planning seat,
mirrors `phase-coordinator`).

Roster bookkeeping (the agent/hook/flow consistency guard reads filesystem
ground truth, so every stated count moved in lockstep): subagents **26 → 27**,
sonnet **20 → 21**, `effort: max` **24 → 25**, Tier 4 Operations **4 → 5**,
tier-header sum 27. Synced across CLAUDE.md (layout table + orchestrator/walk-all
counts + model-split line + new §Auto-routing row), AGENTS.md (count sentences +
tree-comment tier breakdown + sonnet-pool line + Tier-4 note), CONTEXT.md (3
roster anchors), PHASE_STATUS.md (current-state row), and `.claude/agents/README.md`
(current-set header + Tier-4 table row + tier rationale + model-split + effort
headings). `tools/check_agent_hook_consistency.py` opus-split anchors bumped
`20 sonnet` → `21 sonnet` (the only number that lives in the guard regex itself).

Meta-infrastructure only — no `compute/**` / `frontend/**` / schema / workflow
change; rankings/scores/output BYTE-IDENTICAL; defense layer UNCHANGED at 36.

**Verify**: `python tools/check_agent_hook_consistency.py` PASS · `ruff check .` clean.

**Files**: `.claude/agents/loop-engineer.md` (new) · `.claude/agents/README.md` ·
`CLAUDE.md` · `AGENTS.md` · `CONTEXT.md` · `PHASE_STATUS.md` ·
`tools/check_agent_hook_consistency.py` · `PHASE_STATUS_INFLIGHT.md` (this).

---

## PR #TBD — fix(backtest): entry price on-or-after fill (supersede #638; rb[0] Sunday-rebalance null) (in flight, 2026-06-27)

Follow-up that SUPERSEDES #638's direction. The rotation-history initial basket (rb[0],
2016-08-14 = Sunday) still showed null returns after #638, because the price panel STARTS
2016-08-15 (Mon) → there is no close on-or-before the Sunday date. ROOT CAUSE (financial-engineer
DESIGN-READY, DISPLAY-ONLY-SAFE): the NAV path snaps each rebalance date to the first trading day
ON-OR-AFTER (`_snap_to_trading_day`, fills Mon Aug-15), but position_returns received the RAW
Sunday date and resolved the entry on-or-BEFORE (#638) → None. The entry must match the NAV fill:
ON-OR-AFTER. Correct asymmetric pair: entry = on-or-after (the fill), terminal = on-or-before
(last mark before rotating out, UNCHANGED).

FIX (`compute/portfolio/position_returns.py`): add `_close_on_or_after(ticker, date_iso, closes,
*, not_after=None)`; `_extract_streaks` entry (~368) `_close_on_or_before` → `_close_on_or_after`
bounded by the next leg date (new `entry_not_after` param threads `next_rebal_date` from
`compute_position_returns_per_quarter` for the PIT-truncated single-leg case, so the entry can't
leap past the terminal → no degenerate ρ=1); `reconciliation_errors` pp_twr cross-check entry
(~1399) `_close_on` → `_close_on_or_after` for coherence. Terminals UNCHANGED.

DISPLAY-ONLY-SAFE: Carino GROSS/cost identity + sub_periods + headline NAV are disjoint from
`_extract_streaks` (built from the engine `price_on` closure over snapped legs) → reconciliation
stays at the 1.78e-15 floor. Interior trading-day legs byte-identical (the 3 close helpers
coincide on a real trading day). +tests (WR-1 Monday-fill, rb[1] leg restoration, interior
invariance, no-inversion/not_after bound, reconciliation-invariance, 2 Hypothesis props).
ruff clean, offline pytest 297/297; NO schema change.

SEQUENCING: merge → regen `backtest_pit.json` (compute-rankings, Saturday=manual) → THEN merge
#639 (Case-A revert). Post-regen rb[0] shows real forward returns.

**Files**: `compute/portfolio/position_returns.py` · `tests/test_portfolio/test_position_returns.py` · `PHASE_STATUS_INFLIGHT.md` (this).

**Gate**: quantrank-reviewer at Draft→Ready.
## PR #TBD — revert(frontend): drop #637 Case-A 0.0% entry-instant coalesce (keep Case-B) (in flight, 2026-06-27)

Follow-up to the #638 backend fix. #637 Case A coalesced `legs_used === 0` (entry instant)
→ display "+0.0%" — a workaround for the initial basket's null returns. The REAL cause was
the weekend entry-price bug (#638, merged: `_close_on` → `_close_on_or_before`); post-regen
the initial basket produces REAL forward returns (`legs_used >= 1`). So the Case-A coalesce
is now unnecessary AND wrong — its `legs_used === 0` predicate would only fire on
genuinely-broken/absent rows, where a fake "+0.0%" masks real data absence
(financial-engineer + quantrank-reviewer both confirmed: revert Case A, keep Case B).

Removed in `AiPickPortfolio.tsx` (the `displayMwr = (mwr===null && legsUsed===0) ? 0 : mwr`
coalesce + `legsUsed` derivation; `mwr` used directly; genuine null → "—") and
`HoldingsTimeline.tsx` (`MwrReturnCell` `legsUsed` prop + the Case-A branch + the call-site
derivation). #637 Case B (sold-row `mwrForSoldTicker` / `prevMwrByTicker` prior-rebalance
lookup) is UNCHANGED. `return-cell-display.test.ts`: the 5 Case-A "→ +0.0%" tests replaced
with genuine-null-renders-"—" tests; Case-B + footer-exclusion guard suites preserved.

Frontend-only, NO schema change. tsc clean, next build 1512 pages, vitest 290 green.
SEQUENCING: merges AFTER the `backtest_pit.json` regen (with #635 sector + #638 weekend fix)
lands on main, so the UI never shows stale "—".

**Files**: `frontend/components/AiPickPortfolio.tsx` · `frontend/components/HoldingsTimeline.tsx` · `frontend/lib/return-cell-display.test.ts` · `PHASE_STATUS_INFLIGHT.md` (this).

**Gate**: frontend-design-reviewer at Draft→Ready.

---

## PR #TBD — feat(frontend): sold-row WEIGHT renders "—" not "0.0%" (in flight, 2026-06-27)

Owner-requested display polish: in both the Current-picks table (`AiPickPortfolio.tsx`
adaptive branch) and the Rotation-history per-quarter drawer (`HoldingsTimeline.tsx`
`QuarterDrawer`), SOLD/exited rows carry weight 0.0% (no longer held). Render that
weight cell as the muted em-dash "—" instead of "0.0%" — "0.0%" reads as a real
allocation; the dash matches the return-cell convention already used for
non-applicable cells. Held/New weight cells UNCHANGED (keep their real %).

Frontend-only, NO schema change. Both sold-row weight `<span>`s keep their full
className (`text-right font-mono text-sm tabular-nums text-slate-400 dark:text-slate-500`)
so the dash sits right-aligned in the same column slot. The slider branch has no
sold rows (no change). GUARD test `return-cell-display.test.ts` flipped: sold-row
weight asserts "—" (+ negative `not.toBe('0.0%')`) while held rows keep their %.

Verify: tsc --noEmit clean · next build 1510 pages · vitest 290/290 green.

**Files**: `frontend/components/AiPickPortfolio.tsx` · `frontend/components/HoldingsTimeline.tsx` · `frontend/lib/return-cell-display.test.ts` · `PHASE_STATUS_INFLIGHT.md` (this).

**Gate**: trivial display swap (reuses existing muted-dash convention); CI (tsc/build/vitest) is the gate.

---

## subagents — coherence/integration polish pass: drift-proof stale facts across the 27-agent roster (in flight, 2026-06-27)

Refined the `.claude/agents/**` definitions so the standing 27-agent team
stays internally coherent and integrates without acting on stale facts.
Deterministic ground truth was already clean (`check_agent_hook_consistency.py`
PASS; frontmatter names/model-split/effort uniform; the `HANDOFF · status=… ·
next=…` contract identical across all 27; every cross-agent reference resolves).
The flaws were stale **domain facts** baked into agent bodies — exactly the
drift class the count-guard does NOT cover (it guards roster counts, not
prose facts).

Fixes (all body-text only — NO frontmatter touched, so roster counts are
unaffected; guard still 27 agents / 6 opus / 21 sonnet / 25 max + 2 high · 4
hooks · 9 flows):
- **`defense-layer-auditor.md`** (highest-stakes — it audits the defense layer
  it had wrong): `7 active vetoes` → derive from `flag_registry.py`
  `KNOWN_RISK_FLAGS` at run time; `27 boolean flags` scorecard with a hardcoded
  veto/annotate enumeration → derive the inventory from the canonical registry
  + CLAUDE.md §scoring headline (the registry grows almost every scoring PR — a
  baked-in list is the drift source); `Universe size = 502` → read
  `metadata.universe` + expected size at run time (cron defaults to S&P 1500
  ~1504 since Slice 7; sp900/sp500 only on dispatch). Mirrors the file's
  existing "never hardcode a schema-version literal" pattern — drift-proof by
  construction.
- **`agent-output-verifier.md`**: stale illustrative examples `"26 agents"` →
  `"27 agents"`, `schema 0.10.33` → `0.10.41` (the fact-checker should not ship
  stale facts in its own examples).
- **`expert-user-explorer.md`**: stale Playwright anchor `Home … H1 = "S&P 500
  ranking"` → home `/` IS the AI-pick portfolio (H1 "AI picks, backtested.",
  title "QuantRank — AI stock picks, backtested"); the table lives at `/ranking`
  with a tab-driven H1 — read the active tab, don't hard-code a headline.
- **`financial-engineer.md` + `methodology-scientist.md`**: live firing-rate
  predictions on the `S&P 500 cohort/universe` → `S&P 1500` (cohort size feeds
  the firing-rate math; the historical "rescaled 10× for S&P 500 in PR #163"
  anchor was left intact as accurate history).
- **`AGENTS.md`** (adjacent drift surfaced by `phase-coordinator` Mode B at the
  Ready gate): the `compute/ingest/universe.py` tree comment said
  `S&P 500 / 400 / 900 (combined)` — stale since the S&P 1500 cutover; corrected
  to `S&P 500 / 400 / 600 + combined 900 / 1500 (QR_UNIVERSE=sp500|sp900|sp1500)`
  to match what the module actually fetches. CLAUDE.md's universe facts were
  already current, so no CLAUDE.md edit is needed for lockstep.

**Defense-layer headline reconciliation (36 → 38) + new ratchet guard.** The
`defense-layer-auditor` de-hardcoding (above) routed the auditor through the
CLAUDE.md §scoring "headline", which surfaced a pre-existing 3-way count drift:
§Layout said "7 active vetoes", §Scoring "9", METHODOLOGY "7" — while the
registry carries 10 active vetoes (`KNOWN_RISK_FLAGS`) + 28 annotates
(`KNOWN_VALUATION_WARNINGS`) = 38. `agent-output-verifier` (10 vs 11 reviewer
disagreement → REFUTED 11, CONFIRMED 10) + `methodology-scientist` (taxonomy
ruling) established the root cause: **three distinct gates with three different
membership sets** — `KNOWN_RISK_FLAGS` (10, the canonical Top-5 veto gate at
`main.py:1998`) vs `ACTIVE_VETO_FLAGS` (7, backtest AI-pick basket only) vs
`_CAUTIOUS_FORCING_RISK` (5, `cautious` label only). The headline veto count is
defined by the Top-5 gate → **10 active vetoes**. methodology-scientist ruled
**registry-true 38** (rejecting a total-preserving "10+26=36" — that would
require deleting 2 real registered warnings). NO flag was added or removed — the
defense layer was always 38; only the stale DOC headline is corrected:
  - `CLAUDE.md` §Layout `7 active vetoes after Phase 4.5a` → `10 active vetoes`;
    §Scoring + §Phase-status `36 (9 + 27)` → `38 (10 + 28)` (2 places).
  - `docs/METHODOLOGY.md` L16 `33 (7 + 26)` → `38 (10 + 28)`. (L713 "Two active
    vetoes …" is a contextual reference to 2 specific flags, not a total — left.)
  - NEW deterministic guard `tools/check_defense_layer_counts.py` (error→regression
    ratchet): derives the truth from the registry (no count literal in the guard)
    and asserts the CLAUDE.md / METHODOLOGY.md headline anchors match — wired into
    `tools/preflight.py` + `.github/workflows/ci.yml` as its own step, mirroring
    `check_agent_hook_consistency.py`.

Follow-up (NOT in this PR): the 7/5/10 three-gate semantic split is intentional
(basket conviction stricter than Top-5 suppression) but the `schemas.py:970` /
`main.py:23` docstrings name it ambiguously — a `quantrank-reviewer` docstring
pass is queued separately.

Meta-infrastructure / docs + a CI guard — no `compute/**` / `frontend/**` /
schema change; rankings/scores/output BYTE-IDENTICAL; the defense flag SET is
UNCHANGED (38 all along — the "36" headline was stale, now corrected).

**Verify**: `python tools/check_agent_hook_consistency.py` PASS ·
`python tools/check_defense_layer_counts.py` PASS.

**Files**: `.claude/agents/defense-layer-auditor.md` ·
`.claude/agents/agent-output-verifier.md` ·
`.claude/agents/expert-user-explorer.md` ·
`.claude/agents/financial-engineer.md` ·
`.claude/agents/methodology-scientist.md` · `AGENTS.md` · `CLAUDE.md` ·
`docs/METHODOLOGY.md` · `tools/check_defense_layer_counts.py` (new) ·
`tools/preflight.py` · `.github/workflows/ci.yml` ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## docs(compute): clarify the 7/4/10 three-veto-gate split in docstrings (in flight, 2026-06-27)

Follow-up to #641 (defense-layer count reconciliation). The #641 work established
that "active veto" means three DIFFERENT gates with three different membership
sets, which two compute docstrings named ambiguously. Docstring-only clarification
(zero code/behavior change; rankings/scores BYTE-IDENTICAL):
- `compute/output/schemas.py` (high-conviction gate comment): `is_eligible —
  no active rank-gate veto (7 veto flags)` → spell out it's the NARROWER
  AI-pick-basket gate (`ACTIVE_VETO_FLAGS`, 7), distinct from the 10 Top-5
  vetoes (`KNOWN_RISK_FLAGS`) and the 4 cautious-label vetoes
  (`_CAUTIOUS_FORCING_RISK`).
- `compute/main.py` (Step-12 Top-5 rotation docstring): the stale Phase-3b relic
  `any of 4 active vetoes — altman / sloan / NSI / data-quality` (the Top-5 gate
  actually skips on ANY of the 10 `KNOWN_RISK_FLAGS` via
  `if risk_flags.get(ticker): continue`) → corrected to the full 10-flag set +
  a note that this gate is BROADER than the 7-flag basket / 4-flag label gates.

Ground-truth counts confirmed at runtime: `ACTIVE_VETO_FLAGS`=7 ·
`_CAUTIOUS_FORCING_RISK`=4 · `KNOWN_RISK_FLAGS`=10 (this corrected an earlier
"5" estimate for the cautious-label set). Comment-only — no Pydantic field/type/
default changed; `schema_check` in sync; defense layer UNCHANGED at 38.

**Verify**: `python -m compute.output.schema_check` PASS · `ruff check .` clean ·
`python tools/check_defense_layer_counts.py` PASS.

**Files**: `compute/output/schemas.py` · `compute/main.py` ·
`PHASE_STATUS_INFLIGHT.md` (this).

---

## PR (tags-work-remaining) — docs(phase-status): roadmap drift sweep + extend defense-count guard to PHASE_STATUS.md (in flight, 2026-06-29)

Substance review of `PHASE_STATUS.md` (the canonical chronological tracker)
surfaced post-`v2.0.0-phase8` doc-drift in the §Current state / §Next deliverables
/ §Release ladder / §Phase-table sections. Fixes, all verified against ground truth
(`compute/warehouse/flag_registry.py`, the live git tags, and CLAUDE.md):

- **§Current state defense counts (HIGH, factual)** — `36 declared / 9 active vetoes`
  → `38 declared / 10 active vetoes` (+`stale_filing_hard`, the 10th `KNOWN_RISK_FLAGS`
  entry). The §Current state row had drifted while CLAUDE.md + METHODOLOGY (anchored by
  the guard since #641) already read 38/10; the row escaped the guard because it was not
  anchored.
- **§Next deliverables intro** — "the next tag is **v2.0**" was stale (v2.0 shipped
  2026-06-23) and self-contradicted §Release ladder ("next tag = v2.1"); rewritten to
  "v2.0.0-phase8 shipped 2026-06-23; the next tag is v2.1". Clarified the
  "no more phase-pinned tags **after v2.0**" wording (the latest tag still carries the
  `-phase8` suffix — stated-policy-vs-practice).
- **§Lane B #544** — "Needs methodology RATIFY-SHADOW … only Slice-8 / v2.0 gate left"
  → "RATIFY-WITH-CONDITIONS 2026-06-23 (DOCS-ONLY); post-v2.0 deferred, KEEP-ANNOTATE
  → Q3 audit" (matches the CLAUDE.md §Gotchas `low_liquidity` entry).
- **§Release ladder** — `v1.4.0-phase4.6` commit hash `bbca9cac` → `a820caee` (the real
  tag SHA; §Current state already had it right); Slice-8 issue refs `#540/#542` →
  landed-PR refs `#548/#564`.
- **§Phase table row 8** — status `🟡 IN PROGRESS` + "Next = Slice 8 (v2.0 — gated …)"
  → `✅ DONE — 2026-06-23 (v2.0.0-phase8)` + "Slice 8 + the tag SHIPPED" (consistent with
  §Phase position "8 cutover … all DONE").

**Error→regression ratchet** (CLAUDE.md §Conventions): the defense-count drift is a
mechanical class, so `tools/check_defense_layer_counts.py` now also anchors the
PHASE_STATUS.md §Current state rows (`**N declared boolean flags**` + `| Active vetoes |
**N**`) — phrases that appear ONLY in the current-state table, so the chronological-log
"defense UNCHANGED at 36" snapshots do not false-positive.

Docs + a CI-guard extension only — NO `compute/**` / `frontend/**` / schema change;
rankings/scores/output BYTE-IDENTICAL; the defense flag SET is UNCHANGED (38/10 — the
PHASE_STATUS headline was stale, now corrected to match the registry). Lockstep: this
entry satisfies the §Conventions "ship with every PR" rule (CLAUDE.md + AGENTS.md carry
no related drift, so no substance diff there).

**Verify**: `python tools/check_defense_layer_counts.py` PASS (now covers PHASE_STATUS.md)
· `ruff check` PASS · `python tools/preflight.py` cheap rungs PASS (pytest/tsc skipped —
sandbox lacks pandas/node; CI runs the full suite).

**Files**: `PHASE_STATUS.md` · `tools/check_defense_layer_counts.py` ·
`PHASE_STATUS_INFLIGHT.md` (this).
## PR #TBD — feat(backtest): emit rebalances[].band_sectors PIT map for full band_book (in flight, 2026-06-27)

The rotation-history drawer renders rows from each rebalance's `band_book` (the actual
adaptive basket, incl. band-CARRIED names like HP/UAL/INTC), but per-row sector was looked
up from `holdings` (top-20) / `full_ranked` (top-40) — band-carried names + ALL sold names
fall outside both, so their PIT sector existed NOWHERE in the artifact → no sector chip
(broad: every sold row + carried names). #635 only covered holdings/full_ranked.

FIX (`scripts/backfill_portfolio_pit.py`, ~1702): emit additive free-form
`rebalances[i].band_sectors = {t: _pit_sector(t, T) for t in band_book}` (empty dict when no
band_book). PIT (not today's-sector) so reclassified names are correct (WU 2017 = IT, today =
Financials). Pairs with a frontend wire (separate PR) that reads band_sectors for held rows +
the PRIOR rebalance's band_sectors for sold rows. Additive/display-only — selection, NAV,
Carino, sector_weights_by_count, band_legs_for_nav all untouched (compute-builder + reviewer
confirmed). NO schema-triple change (free-form artifact, C-2/E partition). Needs a regen to
populate. ruff clean; offline pytest 3216 passed.

**Files**: `scripts/backfill_portfolio_pit.py` · `tests/test_portfolio/test_backfill_integration.py` · `PHASE_STATUS_INFLIGHT.md` (this).

**Gate**: quantrank-reviewer at Draft→Ready.
## PR #TBD — feat(frontend): wire rebalances[].band_sectors into rotation-history drawer (in flight, 2026-06-27)

Frontend consumer for the backend `band_sectors` PIT map (paired backend PR). The
rotation-history drawer (`HoldingsTimeline.tsx` `QuarterDrawer`) built per-row
`sectorByTicker` from `entry.holdings` (top-20) — band-CARRIED held names + ALL sold
names weren't in it → no sector chip. Now: `data.ts` reads `rebalances[i].band_sectors`
(free-form cast, GRACEFUL when absent on pre-regen artifacts) → exposes `bandSectors` on
each timeline entry (`types.ts` view-model field); `QuarterDrawer` builds
`resolvedSectorByTicker = {...holdings-derived, ...entry.bandSectors}` (band_sectors wins —
PIT-accurate) for held rows, and resolves SOLD rows from the PRIOR entry's `bandSectors`
(the sold name was in last quarter's band_book). SectorChip render-guard kept (unknown →
degrade cleanly). Display-only, NO schema-triple change. +12 vitest contract tests.

Verify: tsc clean · next build 1510 pages · vitest 302/302 green.

**Files**: `frontend/lib/types.ts` · `frontend/lib/data.ts` · `frontend/components/HoldingsTimeline.tsx` · `frontend/components/HoldingsTimeline.test.ts` · `PHASE_STATUS_INFLIGHT.md` (this).

**Gate**: frontend-design-reviewer (sector chips on band-carried + sold rows; graceful when band_sectors absent) at Draft→Ready.

---

## PR (tags-work-remaining-2) — docs: re-point closed #542 Bonferroni residual to new tracker #654 (in flight, 2026-06-29)

Follow-up to the issue-tracker triage. `#542` (Bonferroni multi-test shadow counter)
was CLOSED via PR #564, but its residual — the **provisional-threshold re-derivation**
(−1.94 placeholder → empirical sp1500 M-score SD) — was still being referenced as an
"open deferred" item against the closed `#542` in CLAUDE.md / AGENTS.md / PHASE_STATUS.md.

Re-filed that residual as a fresh tracker **#654** (labels: methodology / phase-8 /
deferred; Q3 2026-08-19 cohort-audit window) and re-pointed the deferred-item references:
- `CLAUDE.md` §Phase status (2 refs: §In-flight deferred line + §Next-deliverables Slice-8 line)
- `AGENTS.md` §Phase + version state (2 refs: §In-flight + prior-chain tail)
- `PHASE_STATUS.md` §v2.0 readiness (1 ref)

Schema-version log entries that describe what #564 shipped ("(Slice 8, issue #542)") are
left untouched — those are accurate historical records, not open-deferred status claims.

Docs-only — NO `compute/**` / `frontend/**` / schema change; output BYTE-IDENTICAL;
defense layer UNCHANGED at 38/10. Lockstep: CLAUDE.md + AGENTS.md moved together + this entry.

**Verify**: `python tools/check_defense_layer_counts.py` PASS · `ruff check .` PASS.

**Files**: `CLAUDE.md` · `AGENTS.md` · `PHASE_STATUS.md` · `PHASE_STATUS_INFLIGHT.md` (this).

---

## PR #656 — chore(deps): bump Next.js 14.2→16 + React 18→19 (issue #41) (in flight, 2026-06-29)

**Branch**: `claude/next16-bump`
**Type**: chore(deps) / security — FRONTEND-ONLY (`frontend/**`); NO `compute/**` /
schema / data / workflow change; no schema bump; rankings/scores/output
BYTE-IDENTICAL. Clears issue #41 (CVE refresh on the pinned `next@14.2`).

**Bumps**: `next` 14.2.35 → **16.2.9** · `react`/`react-dom` 18.3.1 → **19.2.7**
· `@types/react` → 19.2.17 · `@types/react-dom` → 19.2.3 · `eslint` 8.57.0 →
**9.39.4** · `eslint-config-next` 14.2.35 → **16.2.9** · `postcss` unchanged at
8.5.15 (already ≥ the #41 CVE floor 8.5.10; `overrides` preserved). recharts
2.15.4 / next-themes ^0.4.6 / lucide-react ^1.21.0 / @vercel/* unchanged — all
React-19 peer-clean. Lockfile regenerated.

**Breaking-change fixes (all surgical, frontend-only)**:
- `app/globals.css` — moved the `@fontsource` `@import`s ABOVE the `@tailwind`
  directives. Next 16 / Turbopack enforces the CSS spec (`@import` must precede
  all other rules; PostCSS expands `@tailwind` into hundreds of rules first).
  Fonts load identically.
- `components/NavCompareChart.tsx` — `+import type { JSX } from 'react'` (the
  global `JSX` namespace was removed in `@types/react@19`; now `React.JSX`). Only
  file in the tree missing the import.
- `tsconfig.json` — `jsx: "preserve"` → `"react-jsx"` + `.next/dev/types/**`
  added to `include` (both auto-applied by the Next 16 build writer).
- `next-env.d.ts` — auto typed-routes reference (Next 16 writer).
- `package.json` `lint` script `next lint` → `eslint .` (`next lint` removed in
  Next 16); NEW `eslint.config.mjs` (ESLint 9 is flat-config-only; re-exports
  `eslint-config-next`'s native flat config, no `FlatCompat` shim) + removed the
  now-orphan `.eslintrc.json`.
- `/stock/[ticker]` async-`params`: NOT needed — the static-export SSG path
  builds all 1502 pages with the sync `params` type under Next 16.

**Verification (orchestrator re-ran from ground truth, not just the builder's
report)**: `npm install` clean · `tsc --noEmit` **0 errors** · `next build`
**GREEN — 1509 static pages** (5 static routes + `/stock/[ticker]` × 1502, static
export emitted) · `npm audit --omit=dev --audit-level=high` **0 prod
vulnerabilities** (issue #41's next@14 rollup + postcss CVEs cleared) · `vitest`
**290 passed**. Residual: 6 DEV-ONLY CVEs in the vitest/vite/esbuild chain
(unreachable in the static-export build/runtime) — a separate `vitest` bump PR.
dependency-auditor + security-reviewer ran before Mark-Ready.

**Files**: `frontend/package.json` · `frontend/package-lock.json` ·
`frontend/app/globals.css` · `frontend/components/NavCompareChart.tsx` ·
`frontend/tsconfig.json` · `frontend/next-env.d.ts` · `frontend/eslint.config.mjs`
(new) · `frontend/.eslintrc.json` (removed) · `PHASE_STATUS_INFLIGHT.md` (this).

---
