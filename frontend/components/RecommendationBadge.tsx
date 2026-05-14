'use client';

import type { Recommendation } from '@/lib/types';

// 4-tier recommendation badge. Outlined-light tone family matching
// SectorChip / score-tier / MoS-bucket chips — one consistent visual
// language across all chip surfaces. See `.claude/skills/frontend-
// design-system/SKILL.md` Rule 2 (a 2026-05-14 user feedback iteration
// retired the "two patterns" approach in favor of one outlined-light
// pattern for every chip/badge surface).
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
    'bg-emerald-50 text-emerald-800 ring-emerald-300 dark:bg-emerald-900 dark:text-emerald-100 dark:ring-emerald-700',
  lean_bullish:
    'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-900 dark:text-emerald-200 dark:ring-emerald-700',
  neutral:
    'bg-slate-100 text-slate-700 ring-slate-300 dark:bg-slate-700 dark:text-slate-200 dark:ring-slate-600',
  cautious:
    'bg-red-50 text-red-800 ring-red-300 dark:bg-red-900 dark:text-red-100 dark:ring-red-700',
};

// Small colored-dot indicator paired with the chip — same shape as
// SectorChip / score-tier / MoS-bucket chips.
const DOTS: Record<Recommendation, string> = {
  bullish: 'bg-emerald-700 dark:bg-emerald-300',
  lean_bullish: 'bg-emerald-500 dark:bg-emerald-400',
  neutral: 'bg-slate-500 dark:bg-slate-400',
  cautious: 'bg-red-600 dark:bg-red-400',
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
  const dotCls = DOTS[recommendation];
  const sizeCls = SIZE_CLASSES[size];
  const label = short ? SHORT_LABELS[recommendation] : LABELS[recommendation];
  // The `gap-1.5` + dot shape mirrors SectorChip / score-tier chips
  // so a row of "Materials [dot] · Buy [dot]" reads as one family.
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-medium ring-1 ring-inset ${tone} ${sizeCls} ${className}`}
      title={LABELS[recommendation]}
      aria-label={`Recommendation: ${LABELS[recommendation]}`}
    >
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${dotCls}`} aria-hidden="true" />
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

// Re-exports for callers that build their own chip surfaces (e.g.,
// RankingTable's active-filter chip bar) and want to reuse the same
// tones the badge uses inline. One tone family per recommendation —
// see Rule 2 in `.claude/skills/frontend-design-system/SKILL.md`.
export const RECOMMENDATION_CHIP_TONES = TONES;
export const RECOMMENDATION_CHIP_DOTS = DOTS;
