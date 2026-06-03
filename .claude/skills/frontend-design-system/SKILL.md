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

## Rule 2 — One chip pattern: outlined-light everywhere

QuantRank uses **a single chip / badge surface pattern** for every metadata
indicator: SectorChip, ScoreBadge tier, MoSCell bucket, RecommendationBadge,
active-filter chips, and any future exchange-pill or loss-chance pill.

History (2026-05-14): An earlier iteration of this skill defined two
patterns (solid inline badge vs outlined chip). User feedback found the
mix visually noisy — the recommendation badge stood out from the
neighboring sector pill in a way that made the row feel inconsistent.
Resolution: collapse to **one pattern** with optional saturation gradient
for hierarchy.

### Canonical chip pattern

Use the shared **`Chip` primitive** (`frontend/components/Chip.tsx`) — do NOT
hand-roll the shell string. `<Chip tone={…} size="sm" dot={…}>label</Chip>`
renders exactly the markup below (it owns the `inline-flex … rounded-sm
font-medium ring-1 ring-inset` shell + the `gap-1.5` + the 6px dot + the size
scale). `RecommendationBadge` / `LossChanceBadge` / `ListingChips` /
`Tier2EventCard`'s severity badge all render through it. For a bespoke surface
that deviates on font-weight or text-size — `ScoreBadge`'s `font-semibold
tabular-nums` numeric pill, `SectorChip`'s inline-rgb sector dot + 1px-larger
`xs` text — compose the exported `CHIP_BASE` + `CHIP_DOT` constants and the
`CHIP_SIZES` scale by hand instead of duplicating the literal strings (routing
those through the `size`/`dot` props would emit a conflicting Tailwind
utility). The primitive passes tone classes through verbatim so the
`globals.css` soft-OKLCH override (a class allowlist) still applies — never
pre-resolve a tone to hex. It expands to:

```tsx
// Outlined-light chip — same shape across sector / recommendation /
// score-tier / MoS-bucket / future exchange / loss-chance.
<span className="inline-flex items-center gap-1.5 rounded-sm
                 ring-1 ring-inset px-2 py-0.5 text-xs font-medium
                 bg-emerald-50 text-emerald-800 ring-emerald-300
                 dark:bg-emerald-900/30 dark:text-emerald-100 dark:ring-emerald-800">
  <span className="inline-block h-1.5 w-1.5 rounded-full
                   bg-emerald-700 dark:bg-emerald-300" aria-hidden="true" />
  Strong Buy
</span>
```

Tone palette (paired light + `dark:` — see Rule 4):

| Tier | Background | Text | Ring | Dot |
|---|---|---|---|---|
| Positive strong | `bg-emerald-50` | `text-emerald-900` | `ring-emerald-300` | `bg-emerald-700` |
| Positive light | `bg-emerald-50` | `text-emerald-700` | `ring-emerald-200` | `bg-emerald-500` |
| Neutral | `bg-slate-100` | `text-slate-700` | `ring-slate-200` | `bg-slate-500` |
| Negative | `bg-red-50` | `text-red-900` | `ring-red-200` | `bg-rose-500` |
| Info (sector blue/purple/etc.) | `bg-{tone}-50` | `text-{tone}-700` | `ring-{tone}-200` | `bg-{tone}-500` |

**Strong-end text uses -900** (positive strong + negative) so high-stakes
labels like "Strong Buy" / "Sell" stay readable against `bg-50` even on
low-contrast displays. WCAG AA target ≥ 4.5:1; text-900 on bg-50 gives
~10:1.

**Why paired `dark:` variants** (see Rule 4): since Phase 3b the site ships
class-strategy dark mode (`darkMode: 'class'` + `next-themes`), so `dark:`
activates ONLY on the `.dark` class next-themes writes on an explicit user
toggle — never on bare system `prefers-color-scheme`. Every chip therefore
carries a paired `dark:` tone (strong-end → `dark:text-{tone}-100`, middle →
`dark:text-{tone}-300`, over a translucent `dark:bg-{tone}-900/30`). A
light-only surface is now the bug (near-invisible on the dark band).

### Visual hierarchy via dot color (not by switching patterns)

When you need a chip to stand out within a row of chips (e.g.,
recommendation chip should feel "more important" than sector chip):

- Use a **darker dot** (`emerald-700` vs `emerald-500`)
- Use the **strong text** variant (`text-emerald-800` vs `text-emerald-700`)
- Keep the same `bg-50` background — never switch to `bg-700` solid

This preserves visual consistency while still ranking importance subtly.

### Active filter chip variant (clickable + dismissable)

For the toolbar active-filter chip bar (below filters button), add:

- `cursor: button` semantics via `<button type="button">`
- `hover:opacity-75` for hover affordance
- `<span aria-hidden="true" className="opacity-60">×</span>` close indicator
- Click handler that removes the filter

Same tones, same dots. Adding the × and hover state doesn't justify a new
visual pattern.

### Filter drawer selected-state chip

When showing "selected" vs "unselected" in the filter drawer chip group,
use the **same outlined-light tone for selected** + `bg-white text-slate-600
ring-slate-300` for unselected. NEVER use saturated solid for selected —
the drawer chip should match the active-toolbar chip exactly so a user can
trace "this chip is selected → it shows up there as an active filter".

⚠️ **Anti-pattern (PR #68 second iteration mistake — don't repeat)**:
solid inline badge (`bg-emerald-700 text-white`) next to outlined sector
pill (`bg-{tone}-50`). User-reported the inconsistency on screenshot review.
Fix: badge and pill use SAME tone family.

### When chip shape changes (rare)

Pass `size` to the `Chip` primitive — the four steps live in `CHIP_SIZES`
(`Chip.tsx`), so the variations are a prop, not a re-typed string:
- **`size="xs"`** for ultra-tight layouts (mobile data row, ticker prefix):
  `px-1.5 py-0 text-[0.625rem]` + dot is still rendered
- **`size="lg"`** for detail page hero header: `px-3 py-1 text-base` + bigger dot

The shape is the same chip — only `px` / `py` / `text-{size}` change.

## Rule 3 — Existing token sources are the single source of truth

Three constants in `frontend/lib/visual.ts` are the **canonical token bank**.
Don't duplicate or hardcode tones — import them:

| Constant | Use |
|---|---|
| `TIERS` | 5 score tiers (Exceptional/Strong/Average/Weak/Poor) with `cls` + `dot` classes |
| `MOS_BUCKETS` | 3 MoS buckets (Undervalued/Near fair/Overvalued) with `cls` + `dot` |
| `sectorStyle(sector)` | 11 GICS sectors → `{bg, fg, ring, dot}` |

The chip SHELL (not the tones) lives in `frontend/components/Chip.tsx`: the
`Chip` component + `CHIP_BASE` / `CHIP_DOT` / `CHIP_SIZES` exports are the single
source for the outlined-light shape + size scale. Pass a tone from the table
above (or a sister badge's tone map) INTO `<Chip tone={…}>`; don't re-hardcode
`inline-flex … ring-1 ring-inset` or the `px-/text-` size strings.

For recommendation-specific tones (PR 4d) — one outlined-light family, two
usage CONTEXTS (not two visual patterns; see Rule 2):
- `RecommendationBadge.tsx::TONES` — static badge tones
- `RecommendationBadge.tsx::RECOMMENDATION_CHIP_TONES` — selection-state filter-chip tones
- `RecommendationBadge.tsx::RECOMMENDATION_CHIP_DOTS` — small dot indicator

**New dimensions** (e.g., future exchange-pill in PR 4i) follow the same
pattern: export both an inline-badge tone map and an active-chip tone map
from the badge component file. Don't put tone classes inline in `RankingTable`
or `FilterDrawer` — keep them with the badge module.

## Rule 4 — Paired light + `dark:` variants (class-strategy dark mode)

> Updated 2026-06-01. This rule was the INVERSE ("light-mode only, NO `dark:`
> variants") until Phase 3b shipped a real dark mode; it was stale and is
> rewritten here. The original PR #70 lesson is preserved in the History block
> at the bottom so it isn't lost.

QuantRank ships **class-strategy dark mode** since Phase 3b:
`tailwind.config.ts` sets `darkMode: 'class'`, and `next-themes`
(`ThemeProvider attribute="class"`) writes a `.dark` class on `<html>` from a
three-state (light / dark / system) toggle in the sidebar footer + AppShell
header. `frontend/app/globals.css` carries a `.dark` block (OKLCH dark band +
near-black page bg).

**So every chip / badge / colored surface carries a PAIRED `dark:` variant.**
A light-only surface is now the bug (near-invisible text on the dark band) —
the exact opposite of the pre-Phase-3b rule. Canonical pairing (see
`RecommendationBadge` / `LossChanceBadge` / `TIERS` / `MOS_BUCKETS`):

| Light | Paired dark |
|---|---|
| `bg-{tone}-50` | `dark:bg-{tone}-900/30` (translucent band) |
| `text-{tone}-900` (strong end) | `dark:text-{tone}-100` |
| `text-{tone}-700` (middle) | `dark:text-{tone}-300` |
| `ring-{tone}-200/300` | `dark:ring-{tone}-800` |
| dot `bg-{tone}-500/600/700` | `dark:bg-{tone}-300/400` (brighter on the dark band) |

**Why this is safe now (it wasn't pre-Phase-3b)**: `darkMode: 'class'` gates
`dark:` on the `.dark` class next-themes controls — NOT on bare system
`prefers-color-scheme`. So `dark:` activates only when the user (or their
"system" choice) actually selects dark, in lockstep with the page bg. The old
invisible-label failure required `darkMode: 'media'` (system-gated) on a
force-light page — that combination no longer exists.

**Rule**: ship a paired `dark:` variant on every new colored surface, and
verify it reads on the dark band (WCAG-AA in BOTH themes). The soft-OKLCH
`!important` overrides in `globals.css` remap the base utility classes
per-theme via the CSS variables, so the `dark:` variant and the var override
agree — keep both.

<details><summary>History — the original (now-retired) Rule 4</summary>

Pre-Phase-3b the site was force-light (`:root { color-scheme: light }`) with
Tailwind's default `darkMode: 'media'`. In that combo a `dark:` class fired on
system `prefers-color-scheme: dark` even though the page stayed white, so
`dark:text-{tone}-50` on a `bg-{tone}-50` made labels vanish. Lesson
2026-05-14 (PR #70 second iteration): the recommendation badge shipped `dark:`
variants and a system-dark user saw blank "Strong Buy" / "Sell" labels; the
fix THEN was to REMOVE them. Phase 3b's switch to `darkMode: 'class'` +
`next-themes` inverted the rule — `dark:` is now correct and required.

</details>

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

Rounded scale (LedgerCraft — data surfaces ≤ 4px; borders carry depth, not radius):
- `rounded-sm` (2px) — chip BODY, buttons, inputs, search field
- `rounded` (4px) — cards, table containers, the stock-detail hero
- `rounded-full` — status dots inside chips + toggle switches ONLY

## Rule 7 — Filter UX contracts

Filters across all dimensions follow one shape (see `RankingTable.tsx` for
the canonical wire-up). Adding a new filter dimension requires touching all
of:

1. **State** in `RankingTable` — `Set<T>` for multi-select; `[number, number]`
   for range
2. **Persistence** via `frontend/lib/filter-storage.ts` — bump version key
   when adding a new field (`v1` → `v2` etc.) so old saved snapshots are
   cleanly ignored
3. **Drawer section** in `FilterDrawer.tsx` — `<label>` + chip group; selected
   and unselected both use the outlined-light pattern (differ by ring/tint)
4. **Active chip in toolbar bar** in `RankingTable.tsx` — the same outlined-light chip
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

❌ **Solid-fill badge next to an outlined chip** (the PR #68 incident) — every
   chip/badge is the one outlined-light pattern, never a solid fill

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
- [ ] Outlined-light pattern used consistently (no solid-fill badge)
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

When in doubt: read `Chip.tsx` (the primitive) + `RecommendationBadge.tsx`
(component-form caller) + `SectorChip.tsx` (bespoke `CHIP_BASE` caller) + the
chip rendering in `RankingTable.tsx` toolbar bar (a selection-state caller that
still hand-rolls the shell with `RECOMMENDATION_CHIP_TONES`). Canonical examples
of the system in action.

## Companion docs

- `frontend/components/Chip.tsx` — the outlined-light chip primitive +
  `CHIP_BASE` / `CHIP_DOT` / `CHIP_SIZES` shell exports
- `frontend/lib/visual.ts` — TIERS / MOS_BUCKETS / sectorStyle tone bank
- `frontend/components/RecommendationBadge.tsx` — the static-badge +
  selection-state chip tone exports
- `frontend/components/SectorChip.tsx` — canonical outlined-chip
  implementation
- `.claude/skills/phase-4/recommendation-badge/PLAN.md` — design lock
  (Option B internal IDs / Strong Buy display hybrid)
- `.claude/skills/phase-4/phase-4-kickoff-checklist/PLAN.md` §1 — full
  terminology + design decision trail
