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
- Ranking (`app/ranking/page.tsx`): h1 "S&P 500 ranking" → "Equity ranking"; description generalized.
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
