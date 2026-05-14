'use client';

import type { Recommendation } from '@/lib/types';

// 4-tier recommendation badge. Soft-palette tones — matches the
// QuantRank design language (no pure-saturated reds/greens) and adds
// dark-mode variants per the existing Tailwind dark: prefix pattern
// used in SectorChip / MoSCell.
//
// Hybrid terminology (locked 2026-05-14 after user review of PR 4d):
//   - Internal IDs (`bullish` / `lean_bullish` / `neutral` / `cautious`)
//     stay neutral in the schema / JSON / Python code — keeps the
//     compute layer free of regulated terms and lets future API
//     consumers map labels to their own jurisdiction's UX conventions.
//   - User-facing display labels use the familiar sell-side analyst
//     terminology ("Strong Buy" / "Buy" / "Hold" / "Sell") that the
//     user originally requested.
// The global "Educational use only. Not investment advice." Disclaimer
// banner at the top of every page covers the legal posture. See
// `phase-4-kickoff-checklist/PLAN.md` §1 + `recommendation-badge/
// PLAN.md` for the full decision trail.

const TONES: Record<Recommendation, string> = {
  bullish:
    'bg-emerald-700 text-white ring-emerald-800 dark:bg-emerald-400 dark:text-emerald-950 dark:ring-emerald-300',
  lean_bullish:
    'bg-emerald-200 text-emerald-900 ring-emerald-300 dark:bg-emerald-900 dark:text-emerald-100 dark:ring-emerald-700',
  neutral:
    'bg-slate-200 text-slate-700 ring-slate-300 dark:bg-slate-700 dark:text-slate-200 dark:ring-slate-600',
  cautious:
    'bg-red-600 text-white ring-red-700 dark:bg-red-400 dark:text-red-950 dark:ring-red-300',
};

const LABELS: Record<Recommendation, string> = {
  bullish: 'Strong Buy',
  lean_bullish: 'Buy',
  neutral: 'Hold',
  cautious: 'Sell',
};

const SHORT_LABELS: Record<Recommendation, string> = {
  bullish: 'SB',
  lean_bullish: 'B',
  neutral: 'H',
  cautious: 'S',
};

const SIZE_CLASSES: Record<'xs' | 'sm' | 'md' | 'lg', string> = {
  xs: 'px-1.5 py-0 text-[10px]',
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-2.5 py-0.5 text-sm',
  lg: 'px-3 py-1 text-base',
};

export function RecommendationBadge({
  recommendation,
  size = 'sm',
  short = false,
  className = '',
}: {
  recommendation: Recommendation | null;
  size?: 'xs' | 'sm' | 'md' | 'lg';
  // `short` shows 2-letter code (BU/LB/NT/CA) for ultra-tight layouts
  // like the ranking-table ticker row on mobile. Default = full label.
  short?: boolean;
  className?: string;
}) {
  // Legacy data (pre-PR-4d) has no recommendation field — render
  // nothing rather than a confusing placeholder. Once a few weekly
  // computes land, the null path is unreachable in production.
  if (!recommendation) return null;
  const tone = TONES[recommendation];
  const sizeCls = SIZE_CLASSES[size];
  const label = short ? SHORT_LABELS[recommendation] : LABELS[recommendation];
  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ring-1 ring-inset ${tone} ${sizeCls} ${className}`}
      title={LABELS[recommendation]}
      aria-label={`Recommendation: ${LABELS[recommendation]}`}
    >
      {label}
    </span>
  );
}

export const RECOMMENDATION_LABELS = LABELS;
export const RECOMMENDATION_VALUES: Recommendation[] = [
  'bullish',
  'lean_bullish',
  'neutral',
  'cautious',
];

// "Active filter chip" tone classes — used by the toolbar chip bar in
// RankingTable.tsx. Outlined-light pattern matching SectorChip /
// score-tier / MoS-bucket active chips (bg-50 + text-700 + ring-200/300)
// so a row of active filters reads as one consistent visual family.
// This is distinct from `TONES` above, which is the bold inline-badge
// styling used next to the ticker symbol.
export const RECOMMENDATION_CHIP_TONES: Record<Recommendation, string> = {
  bullish: 'bg-emerald-50 text-emerald-800 ring-emerald-300',
  lean_bullish: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  neutral: 'bg-slate-100 text-slate-700 ring-slate-300',
  cautious: 'bg-red-50 text-red-800 ring-red-300',
};

export const RECOMMENDATION_CHIP_DOTS: Record<Recommendation, string> = {
  bullish: 'bg-emerald-700',
  lean_bullish: 'bg-emerald-400',
  neutral: 'bg-slate-500',
  cautious: 'bg-red-600',
};
