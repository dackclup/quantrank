'use client';

import type { Recommendation } from '@/lib/types';

// 4-tier recommendation badge. Soft-palette tones — matches the
// QuantRank design language (no pure-saturated reds/greens) and adds
// dark-mode variants per the existing Tailwind dark: prefix pattern
// used in SectorChip / MoSCell.
//
// Terminology locked per Option B (Bullish / Lean Bullish / Neutral /
// Cautious). See `.claude/skills/phase-4/recommendation-badge/PLAN.md`
// + `phase-4-kickoff-checklist/PLAN.md` §1 for the rationale.

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
  bullish: 'Bullish',
  lean_bullish: 'Lean Bullish',
  neutral: 'Neutral',
  cautious: 'Cautious',
};

const SHORT_LABELS: Record<Recommendation, string> = {
  bullish: 'BU',
  lean_bullish: 'LB',
  neutral: 'NT',
  cautious: 'CA',
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
