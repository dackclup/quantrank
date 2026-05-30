import type { JSX } from 'react';
import { scoreAccentColor, scoreColorClasses } from '@/lib/visual';
import { ScoreGauge } from '@/components/ScoreGauge';

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
  ticker,
}: {
  score: number;
  size?: 'sm' | 'md' | 'lg';
  // Only the 'lg' (detail-header) variant uses this — passed to ScoreGauge
  // so the once-per-session sweep gate is keyed PER TICKER (502 keys), not
  // per score value (~269 unique → 46% of stocks would otherwise share a
  // key and silently skip the signature sweep). expert-user-explorer catch.
  ticker?: string;
}): JSX.Element {
  if (size === 'lg') {
    // Signature gauge sweep + count-up lives in the client ScoreGauge
    // sub-component (the only animated score surface; sm/md stay
    // server-rendered for the 502 table cells). See docs/design.md §Motion.
    return <ScoreGauge score={score} accent={scoreAccentColor(score)} ticker={ticker} />;
  }

  if (size === 'md') {
    // Compact "label-above-number" stack for mobile cards. No donut
    // (saves vertical height vs the lg variant), but the number is
    // larger than the sm pill and gets the same tier-color caption
    // the lg variant uses below.
    const accent = scoreAccentColor(score);
    return (
      <div className="flex flex-col items-end gap-0.5 leading-none">
        <span className="text-[0.625rem] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
          Composite Score
        </span>
        <span className="font-mono text-2xl font-bold tabular-nums text-slate-900 dark:text-slate-100">
          {score.toFixed(1)}
        </span>
        <span className="text-[0.625rem] font-medium uppercase tracking-wider" style={{ color: accent }}>
          {tierLabel(score)}
        </span>
      </div>
    );
  }

  const accent = scoreAccentColor(score);
  return (
    <span
      className={`inline-flex min-w-[3.25rem] items-center justify-center gap-1.5 rounded-sm px-2 py-0.5 text-sm font-semibold tabular-nums ring-1 ring-inset ${scoreColorClasses(score)}`}
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
