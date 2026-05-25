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

## PR (this PR) — EMERGENCY: cron-rankings.yml add `FORM4_FETCH_SKIP=1` to unblock 2h30m timeout (in flight, 2026-05-25)

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

## PR (this PR) — Animation polish PR 1: micro-interactions (Tier 1 P1, 10 className edits) (in flight, 2026-05-25)

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

## PR (this PR) — Post-LedgerCraft polish bundle A1-A10 (dark variants + sort affordance + a11y + stale copy) (in flight, 2026-05-25)

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
