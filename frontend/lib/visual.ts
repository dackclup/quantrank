// Shared visual constants used across multiple components.
// Pulled out of individual component files so the design tokens stay
// in one place and any future palette tweak is a single-file edit.
//
// Color decisions follow the QuantRank.html design package:
// - Score tiers map to a 5-step sequential ramp (emerald → teal →
//   amber → orange → rose) which then gets softened by the
//   --c-pos-* / --c-neg-* CSS variables in globals.css.
// - MoS buckets are 3-way (undervalued / near fair / overvalued)
//   tuned to the population (most S&P 500 stocks land in "near fair"
//   or "overvalued").
// - Sector palette is 11 GICS sectors plus a slate fallback for
//   anything unmatched (e.g., new-listing entries).

export type ScoreTier = 'exceptional' | 'strong' | 'average' | 'weak' | 'poor';

export type ScoreTierMeta = {
  id: ScoreTier;
  label: string;
  min: number;
  max: number;
  cls: string;
  dot: string;
};

// Score-tier thresholds match the QuantRank design package.
// `max` is exclusive except for `exceptional` (top open bound = 101).
// Each tone carries paired light + `dark:` variants — LedgerCraft
// Phase 3b adds the dark variants behind a class-strategy toggle.
export const TIERS: readonly ScoreTierMeta[] = [
  { id: 'exceptional', label: 'Exceptional', min: 70, max: 101,
    cls: 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:ring-emerald-800',
    dot: 'bg-emerald-500 dark:bg-emerald-400' },
  { id: 'strong', label: 'Strong', min: 55, max: 70,
    cls: 'bg-emerald-50 text-emerald-600 ring-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-300 dark:ring-emerald-800',
    dot: 'bg-emerald-400 dark:bg-emerald-300' },
  { id: 'average', label: 'Average', min: 40, max: 55,
    cls: 'bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:ring-amber-800',
    dot: 'bg-amber-500 dark:bg-amber-400' },
  { id: 'weak', label: 'Weak', min: 25, max: 40,
    cls: 'bg-amber-50 text-amber-800 ring-amber-300 dark:bg-amber-900/30 dark:text-amber-200 dark:ring-amber-700',
    dot: 'bg-amber-600 dark:bg-amber-400' },
  { id: 'poor', label: 'Poor', min: 0, max: 25,
    cls: 'bg-rose-50 text-rose-700 ring-rose-200 dark:bg-rose-900/30 dark:text-rose-300 dark:ring-rose-800',
    dot: 'bg-rose-500 dark:bg-rose-400' },
];

export function getTier(score: number | null | undefined): ScoreTier | null {
  if (score === null || score === undefined || Number.isNaN(score)) return null;
  return TIERS.find((t) => score >= t.min && score < t.max)?.id ?? null;
}

export type MosBucket = 'cheap' | 'fair' | 'over';

export type MosBucketMeta = {
  id: MosBucket;
  label: string;
  range: [number, number];
  help: string;
  cls: string;
  dot: string;
};

export const MOS_BUCKETS: readonly MosBucketMeta[] = [
  { id: 'cheap', label: 'Undervalued', range: [10, Infinity], help: 'MoS ≥ +10%',
    cls: 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:ring-emerald-800',
    dot: 'bg-emerald-500 dark:bg-emerald-400' },
  { id: 'fair', label: 'Near fair', range: [-10, 10], help: '±10% MoS',
    cls: 'bg-slate-50 text-slate-700 ring-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700',
    dot: 'bg-slate-400 dark:bg-slate-500' },
  { id: 'over', label: 'Overvalued', range: [-Infinity, -10], help: 'MoS < −10%',
    cls: 'bg-rose-50 text-rose-700 ring-rose-200 dark:bg-rose-900/30 dark:text-rose-300 dark:ring-rose-800',
    dot: 'bg-rose-500 dark:bg-rose-400' },
];

export function getMosBucket(mosPct: number | null | undefined): MosBucket | null {
  if (mosPct === null || mosPct === undefined || Number.isNaN(mosPct)) return null;
  return MOS_BUCKETS.find((b) => mosPct >= b.range[0] && mosPct < b.range[1])?.id ?? null;
}

export type SectorStyle = {
  dot: string;
  bg: string;
  fg: string;
  ring: string;
};

// LedgerCraft Phase 4 A1 (2026-05-24) — sector chip body collapses to
// a single neutral "steel" surface per LedgerCraft Filter Chip spec
// (#F1F5F9 bg / #475569 fg / #E2E8F0 ring, expressed via Tailwind
// `slate-100` / `slate-600` / `slate-200` here). Only the colored
// dot retains sector identity; the chip body no longer competes with
// the ranking-table data for attention. This matches the design-spec
// "restrained palette" rule (forest / amber / steel / red only) while
// preserving sector-glance affordance via the dot.
//
// The 11 `dot` rgb() values are kept verbatim from the previous palette
// so a returning user still associates each sector with its familiar
// color cue (e.g. IT → indigo, Energy → orange) at the dot level. Only
// the surrounding tinted background + matching ring change.
const NEUTRAL_CHIP_BG = 'bg-slate-100 dark:bg-slate-800';
const NEUTRAL_CHIP_FG = 'text-slate-600 dark:text-slate-300';
const NEUTRAL_CHIP_RG = 'ring-slate-200 dark:ring-slate-700';

// 11 GICS sectors. Anything outside this map falls back to the same
// neutral chip in sectorStyle() below, with a slate-400 dot for the
// "unknown sector" case (e.g., new-listing entries pre-sector-tagging).
// LedgerCraft Phase 3b: each `bg` / `fg` / `ring` carries paired light
// + `dark:` variants. Dot stays as a literal `rgb()` (inline style) so
// it doesn't need a dark variant — the lightness in OKLCH terms reads
// fine on both backgrounds at the 6px size.
export const SECTOR_COLORS: Readonly<Record<string, SectorStyle>> = {
  'Information Technology': { dot: 'rgb(99 102 241)',  bg: NEUTRAL_CHIP_BG, fg: NEUTRAL_CHIP_FG, ring: NEUTRAL_CHIP_RG },
  'Communication Services': { dot: 'rgb(168 85 247)',  bg: NEUTRAL_CHIP_BG, fg: NEUTRAL_CHIP_FG, ring: NEUTRAL_CHIP_RG },
  'Consumer Discretionary': { dot: 'rgb(236 72 153)',  bg: NEUTRAL_CHIP_BG, fg: NEUTRAL_CHIP_FG, ring: NEUTRAL_CHIP_RG },
  'Consumer Staples':       { dot: 'rgb(20 184 166)',  bg: NEUTRAL_CHIP_BG, fg: NEUTRAL_CHIP_FG, ring: NEUTRAL_CHIP_RG },
  'Energy':                 { dot: 'rgb(234 88 12)',   bg: NEUTRAL_CHIP_BG, fg: NEUTRAL_CHIP_FG, ring: NEUTRAL_CHIP_RG },
  'Financials':             { dot: 'rgb(13 148 136)',  bg: NEUTRAL_CHIP_BG, fg: NEUTRAL_CHIP_FG, ring: NEUTRAL_CHIP_RG },
  'Health Care':            { dot: 'rgb(220 38 38)',   bg: NEUTRAL_CHIP_BG, fg: NEUTRAL_CHIP_FG, ring: NEUTRAL_CHIP_RG },
  'Industrials':            { dot: 'rgb(100 116 139)', bg: NEUTRAL_CHIP_BG, fg: NEUTRAL_CHIP_FG, ring: NEUTRAL_CHIP_RG },
  'Materials':              { dot: 'rgb(180 83 9)',    bg: NEUTRAL_CHIP_BG, fg: NEUTRAL_CHIP_FG, ring: NEUTRAL_CHIP_RG },
  'Real Estate':            { dot: 'rgb(132 204 22)',  bg: NEUTRAL_CHIP_BG, fg: NEUTRAL_CHIP_FG, ring: NEUTRAL_CHIP_RG },
  'Utilities':              { dot: 'rgb(14 165 233)',  bg: NEUTRAL_CHIP_BG, fg: NEUTRAL_CHIP_FG, ring: NEUTRAL_CHIP_RG },
};

export function sectorStyle(sector: string): SectorStyle {
  return SECTOR_COLORS[sector] ?? {
    dot: 'rgb(148 163 184)',
    bg: NEUTRAL_CHIP_BG,
    fg: NEUTRAL_CHIP_FG,
    ring: NEUTRAL_CHIP_RG,
  };
}

// Score-badge color classes — matches the design's 5-step ramp.
// LedgerCraft Phase 3b: paired light + `dark:` variants. Top tier
// is solid-fill emerald (the legacy "score ≥ 80" surface predates
// Rule 2's outlined-light retire); the dark variant softens to
// `emerald-500` to avoid neon glare.
export function scoreColorClasses(score: number): string {
  if (score >= 80) return 'bg-emerald-600 text-white ring-emerald-700/20 dark:bg-emerald-500 dark:text-emerald-950 dark:ring-emerald-400/30';
  if (score >= 60) return 'bg-emerald-50 text-emerald-800 ring-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-200 dark:ring-emerald-800';
  if (score >= 40) return 'bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-900/30 dark:text-amber-200 dark:ring-amber-800';
  if (score >= 20) return 'bg-amber-50 text-amber-800 ring-amber-300 dark:bg-amber-900/30 dark:text-amber-200 dark:ring-amber-700';
  return 'bg-rose-50 text-rose-800 ring-rose-200 dark:bg-rose-900/30 dark:text-rose-200 dark:ring-rose-800';
}

// Accent for the score gauge ring + tier label + the sm-pill dot.
// Returned as a raw rgb() used INLINE (svg `stroke` / inline `color` /
// dot `backgroundColor`). The globals.css soft-color overrides remap
// utility CLASSES only, so they do NOT reach this inline value — these
// accents stay a touch punchier than the soft chip tokens on purpose
// (the thin ring + 6px dot need the saturation to read), and the amber
// mid-band has no soft-token equivalent in globals.css anyway.
export function scoreAccentColor(score: number): string {
  if (score >= 80) return 'rgb(5 150 105)';
  if (score >= 60) return 'rgb(16 185 129)';
  if (score >= 40) return 'rgb(245 158 11)';
  if (score >= 20) return 'rgb(180 83 9)';
  return 'rgb(225 29 72)';
}

// 0..1 mapped from MoS in [-100, +100], clamped to the visual range.
// Used by MoSCell to position the diverging bar relative to the
// vertical center line.
export function mosVisualFraction(mos: number | null | undefined): number | null {
  if (mos === null || mos === undefined || Number.isNaN(mos)) return null;
  const clamped = Math.max(-100, Math.min(100, mos));
  return (clamped + 100) / 200;
}

export function filingLagBadgeClasses(days: number | null): string {
  if (days === null) return 'bg-slate-100 text-slate-600 ring-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:ring-slate-700';
  if (days < 60) return 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:ring-emerald-800';
  if (days < 180) return 'bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:ring-amber-800';
  return 'bg-red-50 text-red-700 ring-red-200 dark:bg-red-900/30 dark:text-red-300 dark:ring-red-800';
}
