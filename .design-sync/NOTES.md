# design-sync notes

Seed prepared 2026-06-19 from a Claude Code **web/remote** session. The
`DesignSync` tool + `/design-login` are **not available** in that
environment, so no sync ran — this file only records repo facts so a
future `/design-sync` run from **desktop/local Claude Code** (where the
DesignSync connector is provisioned) starts faster and more
deterministically. `config.json` holds only `{"shape": "package"}` and
**no `projectId`/`pkg`**, so the next run correctly gets first-time
treatment and creates a fresh Claude Design project.

## Shape & layout

- **shape = `package`** (non-storybook). No Storybook exists: no
  `.storybook/main.*`, no `*.stories.*` anywhere (node_modules
  excluded). Do not look for one.
- The design system lives in **`frontend/`** — a **private Next.js 14.2
  app** (`"private": true`, scripts are `next dev/build`, no
  component-library `dist/` export). Run the converter from
  `frontend/`, not repo root. This is an app, not a published component
  library, so expect package-shape (absolute-rubric) grading, not
  screenshot pairs.
- Stack: React 18.3 · TypeScript 5.9 · Tailwind 3.4 · `next-themes`
  0.4 (class-strategy dark mode) · Recharts 2.15 · `lucide-react`
  (icons) · `country-flag-icons` (flags). Fonts via @fontsource:
  **IBM Plex Sans** (body) · **JetBrains Mono** (tabular numerics) ·
  **Roboto Slab** (headlines).

## Recommended scope (`componentSrcMap`)

`frontend/components/` has ~46 components, but most are **app**
components coupled to Next.js and/or the JSON data contract and are not
cleanly bundlable standalone. Recommended: scope the sync to the
**presentational subset** below (no `next/*`, no `recharts`, no
`lib/types` import — they take plain props and render in isolation):

```
AnnualReturnsTable · Chip · CountryTabs · HeroAttributeTiles ·
HeroMetric · HoldingsCountSlider · IndexTabs · ListingChips ·
LossChanceBadge · MidcapChip · MoSBadge · MoSCell ·
PriceTimePeriodSelector · RiskSummaryCard · ScoreBadge · ScoreGauge ·
SectorChip · SegmentedSelector · StockLogo · WatchlistButton
```

The **`Chip` family** is the design-system core — `Chip.tsx` is the
shared primitive; `ScoreBadge` / `MoSBadge` / `SectorChip` /
`RecommendationBadge` / `MidcapChip` / `ListingChips` all share its
visual language. Highest-value cards to ship first.

**Exclude** (Next.js- or data-contract-coupled; bundling needs work or
is out of scope):

- `next/*` imports: AiPickPortfolio · AppShell · ComingSoon ·
  HoldingsTimeline · NavCompareChart(+Lazy) · PriceHistoryChart(+Lazy) ·
  RankingTable · ThemeProvider · ThemeToggle · TopNav · WatchlistView
- `recharts`-heavy charts: NavCompareChart · PriceHistoryChart
  (+ FairPriceBarChart · PillarRadarChart · WatchlistChart use Recharts
  too)
- `lib/types`-coupled (need the JSON data contract to render):
  AiPickPortfolio · BacktestValidationBadge · CurrentPriceLine ·
  DecayMonitorCard · FairPriceBarChart · FairPriceCard ·
  HoldingsTimeline · PillarRadarChart · PriceHistoryChart · RankingTable ·
  RankingView · RawMetricsTable · RecommendationBadge · StockListCard ·
  Tier2EventCard · WatchlistChart · WatchlistView

(`RecommendationBadge` is presentational but imports a type from
`lib/types` — easy to include if you inline its prop type or alias the
import.)

## Tokens & styling truth (for `tokensGlob` + conventions header)

- **`frontend/lib/visual.ts`** — shared visual tokens (`pillarColor`,
  score `TIERS` vocabulary + boundaries). Don't re-inline these.
- **`frontend/lib/flag-labels.ts`** — `flagLabel` shared token.
- **`frontend/tailwind.config.*`** + **`frontend/app/globals.css`** —
  the Tailwind preset + soft-color override allowlist. globals.css
  soft-color `!important` overrides are **literal-class-keyed** and never
  reach `dark:` solid-fills (theme audit #401).
- **`docs/design.md`** — the LedgerCraft visual / design-system spec
  (brand primary `emerald-700` `#047857`; 4-tier shadow tokens; ONE
  `ease-in-out` motion curve; fluid root font-size).
- Idiom = **Tailwind utility classes** + `next-themes` class-strategy
  dark mode with **paired `dark:` variants on every surface**. The
  conventions header (`.design-sync/conventions.md`, authored on the
  first real run) should enumerate the Chip family classes + the
  ThemeProvider wrap requirement (components rendered without a
  `next-themes` provider + the `dark`/light class on a root will show
  light-only styling).

## Render gotchas worth pre-loading (from docs/GOTCHAS.md)

- Components assume a theme-class root (`next-themes`); without it,
  `dark:` variants never apply.
- `lucide-react` named imports ONLY (first icon lib in the project).
- `country-flag-icons` flag SVGs = per-country STATIC imports ONLY
  (StockLogo / ListingChips / CountryTabs).
- Every large numeric display carries `tabular-nums`; chips carry
  `font-medium`; interactive controls carry `min-h-[44px]` touch target.
- Press feedback = the global `.press` utility (globals.css).

## When you run it for real (desktop)

1. `/design-sync` from desktop Claude Code with the DesignSync connector on.
2. It reads this `config.json` (`shape: package`) → skips detection.
3. Set `componentSrcMap` to the presentational subset above (or accept
   the full set and let low-grade cards be excluded).
4. Point `tokensGlob` at `frontend/lib/visual.ts` + the Tailwind
   preset; author `conventions.md` per the skill's "Author the
   conventions header" section (Chip class family + ThemeProvider wrap).
