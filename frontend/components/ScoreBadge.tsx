import type { JSX } from 'react';
import { scoreAccentColor, scoreColorClasses } from '@/lib/visual';

// Two-size component: the pill ('sm' default) for rankings table cells
// + mobile cards, and the radial-gauge variant ('lg') for the stock
// detail header.
//
// The radial gauge SVG renders a soft sage-to-terracotta arc whose
// arc length is the score percentile. Tier label ("Exceptional",
// "Strong", etc.) sits below the numeric score for context — addresses
// the design feedback that "64.0" alone lacks meaning.

const tierLabel = (score: number): string => {
  if (score >= 80) return 'Exceptional';
  if (score >= 60) return 'Strong';
  if (score >= 40) return 'Average';
  if (score >= 20) return 'Weak';
  return 'Poor';
};

export function ScoreBadge({
  score,
  size = 'sm',
}: {
  score: number;
  size?: 'sm' | 'lg';
}): JSX.Element {
  if (size === 'lg') {
    const r = 26;
    const circumference = 2 * Math.PI * r;
    const frac = Math.max(0, Math.min(1, score / 100));
    const accent = scoreAccentColor(score);
    return (
      <div className="flex items-center gap-3">
        <div className="relative h-16 w-16 shrink-0">
          <svg viewBox="0 0 64 64" className="h-16 w-16 -rotate-90">
            <circle cx="32" cy="32" r={r} fill="none" stroke="rgb(241 245 249)" strokeWidth="6" />
            <circle
              cx="32"
              cy="32"
              r={r}
              fill="none"
              stroke={accent}
              strokeWidth="6"
              strokeLinecap="round"
              strokeDasharray={`${circumference * frac} ${circumference}`}
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="font-mono text-base font-semibold tabular-nums text-slate-900">
              {score.toFixed(0)}
            </span>
          </div>
        </div>
        <div className="flex flex-col">
          <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
            Composite
          </span>
          <span className="font-mono text-lg font-semibold tabular-nums text-slate-900">
            {score.toFixed(1)}
          </span>
          <span className="text-[10px] uppercase tracking-wider" style={{ color: accent }}>
            {tierLabel(score)}
          </span>
        </div>
      </div>
    );
  }

  const accent = scoreAccentColor(score);
  return (
    <span
      className={`inline-flex min-w-[3.25rem] items-center justify-center gap-1.5 rounded-full px-2 py-0.5 text-sm font-semibold tabular-nums ring-1 ring-inset ${scoreColorClasses(score)}`}
    >
      {/* Skip the dot for top-tier (≥80) where the badge already has
          a solid color fill — the dot would be invisible anyway. */}
      {score < 80 && (
        <span
          aria-hidden="true"
          className="inline-block h-1.5 w-1.5 rounded-full"
          style={{ backgroundColor: accent }}
        />
      )}
      {score.toFixed(1)}
    </span>
  );
}
