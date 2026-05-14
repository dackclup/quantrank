---
name: frontend-design-system
description: QuantRank frontend design tokens, component patterns, and anti-patterns. Use BEFORE adding any new UI component, badge, chip, filter control, or color so the new surface stays within the established design family (sector / score-tier / MoS / recommendation chips all share one visual language). TRIGGER when adding new UI feature, when CR feedback says "doesn't match the rest", when porting a design from a screenshot, when picking Tailwind colors / spacing / typography for a new component, or when the user says "looks different from other chips" / "ทำให้เหมือนกันหน่อย". SKIP for backend Python (use SKILL.md), schema work (use schema-check), or copy-editing existing text (no design decision required).
---

# QuantRank Frontend Design System

**Single source of truth for visual decisions on the QuantRank static site.**
When in doubt, copy an existing component's pattern and adjust tones — don't
invent a new one.

This skill exists because of an incident (2026-05-14, PR #68): the
recommendation-badge active-filter chips were rendered with the bold inline-
badge styling (solid emerald-700 / red-600 fills) while the sister chips
(sector / score-tier / MoS) were outlined-light (`bg-50 + text-700 + ring-200`).
The visual family broke; the user noticed; we fixed it in a follow-up commit.
**Capture the rules so the next contributor doesn't repeat the miss.**

## Rule 0 — Tailwind only, no hex

All colors go through Tailwind tokens. No inline `style={{ color: '#...' }}`
except for legacy Recharts components that don't accept className strings
(`StockHistoryChart`, `FairPriceBarChart`). When you must use hex, source it
from `slate-{n}` / `emerald-{n}` / `red-{n}` / `indigo-{n}` / `amber-{n}` etc.

## Rule 1 — Soft palette, no saturation

Never use:
- Pure red (`red-700`+ saturated), pure green (`green-600` browser-default)
- Pure black `#000` or `text-black` — use `text-slate-900` for "near-black"
- Pure white on dark — use `text-slate-50` or `text-{tone}-100`

Always use the soft equivalents:
- Positive: `emerald-{300,500,700}` family
- Negative: `red-{300,500,600}` (NOT `red-700`; too saturated)
- Neutral / muted: `slate-{200,500,700,900}`
- Info / link: `indigo-{500,700}`
- Warning: `amber-{300,500}`

## Rule 2 — Two badge / chip patterns, never mix

QuantRank has **two distinct chip surfaces**. Choose the right one based on
context.

### Pattern A — Solid inline badge (bold)

Used **next to the ticker symbol** on data rows and detail-page headers.
High-contrast on white card surface; carries semantic weight.

```tsx
// Bullish badge inline next to NVDA ticker
<span className="inline-flex items-center rounded-full bg-emerald-700 text-white
                 ring-1 ring-inset ring-emerald-800 px-2 py-0.5 text-xs font-medium
                 dark:bg-emerald-400 dark:text-emerald-950 dark:ring-emerald-300">
  Strong Buy
</span>
```

Tone palette for Pattern A:
- **Positive strong**: `bg-emerald-700 text-white ring-emerald-800`
- **Positive light**: `bg-emerald-200 text-emerald-900 ring-emerald-300`
- **Neutral**: `bg-slate-200 text-slate-700 ring-slate-300`
- **Negative**: `bg-red-600 text-white ring-red-700`

Each pair has a `dark:` variant — see `RecommendationBadge.tsx::TONES`.

### Pattern B — Outlined-light chip (subtle)

Used in **active-filter chip bars** (the row of removable filters below the
toolbar) and in **filter drawer chip groups**. Reads as one consistent family
across sector / score-tier / MoS / recommendation filters.

```tsx
// Active filter chip — recommendation "Strong Buy" in the toolbar row
<button className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5
                   text-xs ring-1 ring-inset hover:opacity-75
                   bg-emerald-50 text-emerald-800 ring-emerald-300">
  <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-700" />
  Strong Buy
  <span aria-hidden="true" className="opacity-60">×</span>
</button>
```

Tone palette for Pattern B (these are the canonical "active chip" tones —
copy them, don't invent):
- **Positive strong**: `bg-emerald-50 text-emerald-800 ring-emerald-300`
- **Positive light**: `bg-emerald-50 text-emerald-700 ring-emerald-200`
- **Neutral**: `bg-slate-100 text-slate-700 ring-slate-300`
- **Negative**: `bg-red-50 text-red-800 ring-red-300`

⚠️ **Anti-pattern (PR #68 mistake — don't repeat)**: embedding a Pattern A
badge inside a Pattern B chip slot. The mismatch is jarring against
neighboring Pattern B chips.

### When to use which

| Context | Pattern |
|---|---|
| Inline next to ticker on ranking row | A (solid) |
| Detail page header next to big ticker | A (solid) |
| Active filter chip bar (below toolbar) | **B** (outlined-light) |
| Filter drawer chip group selected state | use saturated solid (Pattern A-flavored) so user sees clear on/off |
| Sector tag in ranking row | **B** (outlined-light, via `SectorChip`) |
| Score tier indicator | depends — table dot uses `ScoreBadge`; chip uses B |

## Rule 3 — Existing token sources are the single source of truth

Three constants in `frontend/lib/visual.ts` are the **canonical token bank**.
Don't duplicate or hardcode tones — import them:

| Constant | Use |
|---|---|
| `TIERS` | 5 score tiers (Exceptional/Strong/Average/Weak/Poor) with `cls` + `dot` classes |
| `MOS_BUCKETS` | 3 MoS buckets (Undervalued/Near fair/Overvalued) with `cls` + `dot` |
| `sectorStyle(sector)` | 11 GICS sectors → `{bg, fg, ring, dot}` |

For recommendation-specific tones (PR 4d):
- `RecommendationBadge.tsx::TONES` — Pattern A (inline badge)
- `RecommendationBadge.tsx::RECOMMENDATION_CHIP_TONES` — Pattern B (active chip)
- `RecommendationBadge.tsx::RECOMMENDATION_CHIP_DOTS` — small dot indicator

**New dimensions** (e.g., future exchange-pill in PR 4i) follow the same
pattern: export both an inline-badge tone map and an active-chip tone map
from the badge component file. Don't put tone classes inline in `RankingTable`
or `FilterDrawer` — keep them with the badge module.

## Rule 4 — Light + dark mode parity

Every component with explicit `bg-` / `text-` / `ring-` must include
`dark:` variants:

```
bg-emerald-50 → dark:bg-emerald-900
text-emerald-800 → dark:text-emerald-100
ring-emerald-300 → dark:ring-emerald-700
```

Skip dark variants only for:
- Universally-light surfaces (Disclaimer banner — intentionally amber-50 in
  both modes for the "warning" affordance)
- Elements that inherit from parent and never set their own color

## Rule 5 — Typography

| Use case | Tailwind |
|---|---|
| Ticker symbols (NVDA, CF) | `font-mono font-semibold` |
| Composite scores, MoS, prices | `font-mono tabular-nums` |
| Company names | default sans, weight 400-500 |
| Headers | `font-bold tracking-tight` |
| Compact pill labels | `text-xs font-medium` |

Tabular-nums is critical for **right-aligned numeric columns** so the digits
stack visually. Use it everywhere a number appears in a list or table cell.

## Rule 6 — Spacing scale

Stick to Tailwind's 4-px scale. Common patterns:

| Element | Padding | Gap |
|---|---|---|
| xs chip / compact badge | `px-1.5 py-0` | n/a |
| Small chip (default) | `px-2 py-0.5` | `gap-1.5` |
| Medium chip / button | `px-2.5 py-1` | `gap-2` |
| Large button / hero badge | `px-3 py-1.5` or `px-4 py-2` | `gap-3` |
| Card / container interior | `p-3` to `p-6` | `gap-4` to `gap-6` |

Rounded scale:
- `rounded-full` — chips, pills, ring-dot indicators
- `rounded-md` — buttons, search input
- `rounded-lg` — cards, table containers
- `rounded-2xl` — hero detail-page header card

## Rule 7 — Filter UX contracts

Filters across all dimensions follow one shape (see `RankingTable.tsx` for
the canonical wire-up). Adding a new filter dimension requires touching all
of:

1. **State** in `RankingTable` — `Set<T>` for multi-select; `[number, number]`
   for range
2. **Persistence** via `frontend/lib/filter-storage.ts` — bump version key
   when adding a new field (`v1` → `v2` etc.) so old saved snapshots are
   cleanly ignored
3. **Drawer section** in `FilterDrawer.tsx` — `<label>` + chip group; chip
   uses Pattern A-flavored "on" + outlined "off" state
4. **Active chip in toolbar bar** in `RankingTable.tsx` — Pattern B styling
5. **Filter logic** in the `filtered` `useMemo` — empty-set means "pass all"
6. **activeCount** counter for the Filters button badge

Skip any of these and the filter is half-broken. The checklist is the test.

## Rule 8 — Component placement contracts

- **Recommendation badge**: immediately to the right of the ticker symbol on
  ranking-row + detail header. Hidden when `recommendation === null` (legacy).
- **Sector chip**: in the row's chip slot (table column) or detail-page
  header below the rank. Always present.
- **Score badge**: rightmost in the data row before price columns.
- **MoS bar**: rightmost column, after price + fair-price.

When adding a new badge or chip, ask: "what existing slot does this most
resemble?" Use the same neighbor + spacing as that slot.

## Rule 9 — Disclaimer + legal posture

The global `Disclaimer` banner at the top of every page is the legal-safety
surface. Any visual element that uses regulated-style terminology (Strong
Buy, Buy, Hold, Sell, %-probability labels) is covered by the banner — no
per-element popover required. Don't add disclaimer text under individual
badges; it duplicates the global banner and adds visual noise.

However:
- The **internal IDs** in code/JSON stay neutral (`bullish` / `lean_bullish`
  / `neutral` / `cautious`), separate from display labels (Strong Buy / Buy
  / Hold / Sell). This **hybrid terminology** is locked 2026-05-14 in
  `phase-4-kickoff-checklist/PLAN.md` §1.

## Rule 10 — Accessibility floor

- Every interactive element has either `aria-label` or visible text
- Badges use `title=` for tooltip context + `aria-label` for screen readers
- Buttons use semantic `<button type="button">` not `<div onClick>`
- Color is **never the sole signal** — chips always pair color with a short
  text label or icon
- Focus rings inherit from Tailwind defaults; don't strip with `focus:ring-0`

## Anti-patterns checklist (what NOT to do)

❌ **Mixing Pattern A and Pattern B** — solid badges in active-chip rows
   (the PR #68 incident)

❌ **Hard-coded hex colors** outside Recharts adapters
   `style={{ color: '#0f172a' }}` — use `text-slate-900` instead

❌ **Pure red / pure green / pure black** — always use the soft palette

❌ **Forgetting dark mode** — every new color class needs a `dark:` partner

❌ **Inlining tone tables in pages** — keep tone constants with the
   component that owns the visual identity (e.g., `RecommendationBadge.tsx`),
   not scattered across `RankingTable.tsx` / `FilterDrawer.tsx`

❌ **Skipping the filter checklist** (Rule 7 steps 1-6) — half-wired filter

❌ **Per-badge disclaimer** when the global banner already covers it

❌ **`text-black` / `bg-white`** without dark mode partner — use
   `text-slate-900 dark:text-slate-50` etc.

❌ **Mixing FINRA-regulated and unregulated terminology** in the same
   component (e.g., "Strong Buy" inline next to "model output, not advice"
   small text — pick one register)

❌ **Using saturated colors for veto / distress flags** — even Cautious /
   Sell uses `red-600` not `red-800`. Saturation eye-fatigues users
   scanning a long ranking list

## Reference component checklist (for new UI work)

Before opening a UI PR, walk this checklist:

- [ ] Tones imported from `lib/visual.ts` or sister badge component
- [ ] Light + dark mode classes both present
- [ ] Pattern A (inline) vs Pattern B (chip) chosen consistently
- [ ] Tabular-nums on numeric columns
- [ ] Aria labels + title attributes on interactive elements
- [ ] Filter checklist (Rule 7) walked end-to-end if adding a filter
- [ ] No hex colors outside Recharts adapter components
- [ ] Spacing follows the table in Rule 6
- [ ] Soft palette only (Rule 1)
- [ ] No per-badge legal disclaimer (Rule 9 — global banner covers it)
- [ ] `npx tsc --noEmit` + `npx next build` both clean before PR

## When this skill triggers

- User says "ทำให้เหมือนกันหน่อย" / "doesn't match" / "looks different"
- Designing a new chip, badge, filter chip, or UI element
- Picking Tailwind tones for a new dimension
- Reviewing a UI PR and asking "is this consistent with the rest?"
- Onboarding a new contributor to QuantRank frontend
- Porting a design from a screenshot (Jitta-style reference, etc.)

When in doubt: read `RecommendationBadge.tsx` + `SectorChip.tsx` + the
chip rendering in `RankingTable.tsx` toolbar bar. Three canonical examples
of the system in action.

## Companion docs

- `frontend/lib/visual.ts` — TIERS / MOS_BUCKETS / sectorStyle tone bank
- `frontend/components/RecommendationBadge.tsx` — both Pattern A and
  Pattern B tone exports
- `frontend/components/SectorChip.tsx` — canonical outlined-chip
  implementation
- `.claude/skills/phase-4/recommendation-badge/PLAN.md` — design lock
  (Option B internal IDs / Strong Buy display hybrid)
- `.claude/skills/phase-4/phase-4-kickoff-checklist/PLAN.md` §1 — full
  terminology + design decision trail
