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
export const TIERS: readonly ScoreTierMeta[] = [
  { id: 'exceptional', label: 'Exceptional', min: 70, max: 101,
    cls: 'bg-emerald-50 text-emerald-700 ring-emerald-200', dot: 'bg-emerald-500' },
  { id: 'strong', label: 'Strong', min: 55, max: 70,
    cls: 'bg-teal-50 text-teal-700 ring-teal-200', dot: 'bg-teal-500' },
  { id: 'average', label: 'Average', min: 40, max: 55,
    cls: 'bg-amber-50 text-amber-700 ring-amber-200', dot: 'bg-amber-500' },
  { id: 'weak', label: 'Weak', min: 25, max: 40,
    cls: 'bg-orange-50 text-orange-700 ring-orange-200', dot: 'bg-orange-500' },
  { id: 'poor', label: 'Poor', min: 0, max: 25,
    cls: 'bg-rose-50 text-rose-700 ring-rose-200', dot: 'bg-rose-500' },
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
    cls: 'bg-emerald-50 text-emerald-700 ring-emerald-200', dot: 'bg-emerald-500' },
  { id: 'fair', label: 'Near fair', range: [-10, 10], help: '±10% MoS',
    cls: 'bg-slate-50 text-slate-700 ring-slate-200', dot: 'bg-slate-400' },
  { id: 'over', label: 'Overvalued', range: [-Infinity, -10], help: 'MoS < −10%',
    cls: 'bg-rose-50 text-rose-700 ring-rose-200', dot: 'bg-rose-500' },
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

// 11 GICS sectors. Anything outside this map falls back to the slate
// neutral chip in sectorStyle() below — see fallback in that function.
export const SECTOR_COLORS: Readonly<Record<string, SectorStyle>> = {
  'Information Technology': { dot: 'rgb(99 102 241)', bg: 'bg-indigo-50', fg: 'text-indigo-700', ring: 'ring-indigo-200' },
  'Communication Services': { dot: 'rgb(168 85 247)', bg: 'bg-purple-50', fg: 'text-purple-700', ring: 'ring-purple-200' },
  'Consumer Discretionary': { dot: 'rgb(236 72 153)', bg: 'bg-pink-50', fg: 'text-pink-700', ring: 'ring-pink-200' },
  'Consumer Staples': { dot: 'rgb(20 184 166)', bg: 'bg-teal-50', fg: 'text-teal-700', ring: 'ring-teal-200' },
  'Energy': { dot: 'rgb(234 88 12)', bg: 'bg-orange-50', fg: 'text-orange-700', ring: 'ring-orange-200' },
  'Financials': { dot: 'rgb(13 148 136)', bg: 'bg-teal-50', fg: 'text-teal-800', ring: 'ring-teal-200' },
  'Health Care': { dot: 'rgb(220 38 38)', bg: 'bg-red-50', fg: 'text-red-700', ring: 'ring-red-200' },
  'Industrials': { dot: 'rgb(100 116 139)', bg: 'bg-slate-100', fg: 'text-slate-700', ring: 'ring-slate-300' },
  'Materials': { dot: 'rgb(180 83 9)', bg: 'bg-amber-50', fg: 'text-amber-800', ring: 'ring-amber-200' },
  'Real Estate': { dot: 'rgb(132 204 22)', bg: 'bg-lime-50', fg: 'text-lime-800', ring: 'ring-lime-200' },
  'Utilities': { dot: 'rgb(14 165 233)', bg: 'bg-sky-50', fg: 'text-sky-700', ring: 'ring-sky-200' },
};

export function sectorStyle(sector: string): SectorStyle {
  return SECTOR_COLORS[sector] ?? { dot: 'rgb(148 163 184)', bg: 'bg-slate-50', fg: 'text-slate-700', ring: 'ring-slate-200' };
}

// Score-badge color classes — matches the design's 5-step ramp.
export function scoreColorClasses(score: number): string {
  if (score >= 80) return 'bg-emerald-600 text-white ring-emerald-700/20';
  if (score >= 60) return 'bg-emerald-50 text-emerald-800 ring-emerald-200';
  if (score >= 40) return 'bg-amber-50 text-amber-800 ring-amber-200';
  if (score >= 20) return 'bg-orange-50 text-orange-800 ring-orange-200';
  return 'bg-rose-50 text-rose-800 ring-rose-200';
}

// Accent color for the radial gauge ring + tier-label text in
// ScoreBadge size=lg. The soft-color overrides in globals.css will
// remap these to oklch sage/terracotta at render time.
export function scoreAccentColor(score: number): string {
  if (score >= 80) return 'rgb(5 150 105)';
  if (score >= 60) return 'rgb(16 185 129)';
  if (score >= 40) return 'rgb(245 158 11)';
  if (score >= 20) return 'rgb(249 115 22)';
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
  if (days === null) return 'bg-slate-100 text-slate-600 ring-slate-200';
  if (days < 60) return 'bg-emerald-50 text-emerald-700 ring-emerald-200';
  if (days < 180) return 'bg-amber-50 text-amber-700 ring-amber-200';
  return 'bg-red-50 text-red-700 ring-red-200';
}
