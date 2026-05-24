'use client';

// Loss Chance % chip (PR 4e, Phase 4 UX trio §2).
//
// 5-band color gradient — outlined-light pattern matching SectorChip /
// RecommendationBadge / score-tier / MoS-bucket chips. NO `dark:`
// variants (the site is force-light via `globals.css :root
// color-scheme: light`; Tailwind dark: triggers on SYSTEM
// `prefers-color-scheme: dark` and would make text vanish — lesson
// from PR #70). See `.claude/skills/frontend-design-system/SKILL.md`
// Rules 2 + 4.
//
// Display: "NN%" with a small leading dot in the band's accent. The
// global Disclaimer banner covers the legal "not a backtested
// probability" framing — no inline qualifier needed.

type Band = {
  max: number;            // strictly less than `max` puts the value in this band
  cls: string;            // chip tone — outlined-light, light mode only
  dot: string;            // small leading colored dot
  label: string;          // accessibility / tooltip context
};

// Strong-end uses text-{tone}-900 (~10:1 contrast vs bg-50) for the
// high-stakes "low loss / high loss" ends; middle bands use -700 for
// the visual hierarchy ramp.
const BANDS: readonly Band[] = [
  {
    max: 25,
    cls: 'bg-emerald-50 text-emerald-900 ring-emerald-300 dark:bg-emerald-900/30 dark:text-emerald-100 dark:ring-emerald-800',
    dot: 'bg-emerald-700 dark:bg-emerald-400',
    label: 'Low loss chance',
  },
  {
    max: 40,
    cls: 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-300 dark:ring-emerald-800',
    dot: 'bg-emerald-500 dark:bg-emerald-300',
    label: 'Moderate-low loss chance',
  },
  {
    max: 60,
    cls: 'bg-slate-100 text-slate-700 ring-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700',
    dot: 'bg-slate-500 dark:bg-slate-400',
    label: 'Neutral loss chance',
  },
  {
    max: 80,
    cls: 'bg-red-50 text-red-700 ring-red-200 dark:bg-red-900/30 dark:text-red-300 dark:ring-red-800',
    dot: 'bg-red-500 dark:bg-red-400',
    label: 'Moderate-high loss chance',
  },
  {
    max: 100,
    cls: 'bg-red-50 text-red-900 ring-red-300 dark:bg-red-900/30 dark:text-red-100 dark:ring-red-800',
    dot: 'bg-red-600 dark:bg-red-400',
    label: 'High loss chance',
  },
];

const SIZE_CLASSES: Record<'xs' | 'sm' | 'md', string> = {
  xs: 'px-1.5 py-0 text-[10px]',
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-2.5 py-0.5 text-sm',
};

function bandFor(pct: number): Band {
  for (const b of BANDS) {
    if (pct < b.max) return b;
  }
  // pct === 100 (impossible given clip, but safe fallback)
  return BANDS[BANDS.length - 1];
}

export function LossChanceBadge({
  lossChancePct,
  size = 'sm',
  className = '',
}: {
  lossChancePct: number | null;
  size?: 'xs' | 'sm' | 'md';
  className?: string;
}) {
  // Missing MoS → em-dash placeholder. Matches existing MoSCell
  // missing-input UI.
  if (lossChancePct == null) {
    return (
      <span
        className={`inline-flex items-center text-slate-400 dark:text-slate-500 ${SIZE_CLASSES[size]} ${className}`}
        title="Loss Chance unavailable — fair-price ensemble missing"
        aria-label="Loss Chance unavailable"
      >
        —
      </span>
    );
  }
  const band = bandFor(lossChancePct);
  const sizeCls = SIZE_CLASSES[size];
  const rounded = Math.round(lossChancePct);
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-sm font-medium ring-1 ring-inset ${band.cls} ${sizeCls} ${className}`}
      title={`Loss Chance ${rounded}% — combines composite, defense flags, MoS.`}
      aria-label={`Loss Chance ${rounded}%. ${band.label}.`}
    >
      <span className={`inline-block h-1.5 w-1.5 rounded-full ${band.dot}`} aria-hidden="true" />
      {rounded}%
    </span>
  );
}
