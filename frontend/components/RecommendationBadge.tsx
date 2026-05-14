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

// Tones match `SectorChip` / score-tier / MoS-bucket pattern: light-mode
// only (NO `dark:` variants). `globals.css` sets `color-scheme: light`
// to force the entire site to render in light mode, but Tailwind's
// `dark:` variants are gated on `prefers-color-scheme: dark` at the
// SYSTEM level, not the page's color-scheme. Users with system dark
// mode would otherwise see `dark:text-{tone}-50` (very light text) on
// the still-light `bg-{tone}-50` background — invisible label.
// Lesson learned 2026-05-14 (PR #70 second iteration): adopting the
// existing chip pattern means matching its absence of dark: variants.
//
// Strong-end (bullish + cautious) uses `text-{tone}-900` for max
// contrast vs `bg-{tone}-50` (~10:1, well above WCAG AA 4.5:1).
// Middle tones (lean_bullish + neutral) use `text-{tone}-700` so the
// 4-tier ramp still has visual hierarchy via text shade.
const TONES: Record<Recommendation, string> = {
  bullish: 'bg-emerald-50 text-emerald-900 ring-emerald-300',
  lean_bullish: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  neutral: 'bg-slate-100 text-slate-700 ring-slate-300',
  cautious: 'bg-red-50 text-red-900 ring-red-300',
};

// Small colored-dot indicator paired with the chip — same shape as
// SectorChip / score-tier / MoS-bucket chips.
const DOTS: Record<Recommendation, string> = {
  bullish: 'bg-emerald-700',
  lean_bullish: 'bg-emerald-500',
  neutral: 'bg-slate-500',
  cautious: 'bg-red-600',
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
