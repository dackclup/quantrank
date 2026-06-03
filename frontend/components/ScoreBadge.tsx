import type { JSX } from 'react';
import { scoreAccentColor, scoreColorClasses, scoreTierLabel } from '@/lib/visual';
import { ScoreGauge } from '@/components/ScoreGauge';
import { CHIP_BASE, CHIP_DOT } from '@/components/Chip';

// Two-size component: the pill ('sm' default) for rankings table cells
// + mobile cards, and the radial-gauge variant ('lg') for the stock
// detail header.
//
// The radial gauge SVG renders a soft sage-to-terracotta arc whose
// arc length is the score percentile. Tier label ("Exceptional",
// "Strong", etc.) sits below the numeric score for context — addresses
// the design feedback that "64.0" alone lacks meaning. The tier WORD
// comes from the canonical `scoreTierLabel` (lib/visual.ts TIERS), shared
// with ScoreGauge + the pillar bars; `scoreAccentColor` (its COLOR) stays
// on its own heat-signal boundaries by design.

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
          {scoreTierLabel(Number(score.toFixed(1)))}
        </span>
      </div>
    );
  }

  const accent = scoreAccentColor(score);
  // Composes the shared chip shell + dot by hand (not the `Chip` component):
  // this numeric pill is `font-semibold tabular-nums` (vs the chip family's
  // `font-medium`) at `text-sm` with `sm` padding + a min-width + an inline-rgb
  // accent dot, so it can't route through the canonical `size`/`dot` props.
  return (
    <span
      className={`${CHIP_BASE} min-w-[3.25rem] justify-center gap-1.5 px-2 py-0.5 text-sm font-semibold tabular-nums ${scoreColorClasses(score)}`}
    >
      {/* Skip the dot for top-tier (≥80) where the badge already has
          a solid color fill — the dot would be invisible anyway. */}
      {score < 80 && (
        <span
          aria-hidden="true"
          className={CHIP_DOT}
          style={{ backgroundColor: accent }}
        />
      )}
      {score.toFixed(1)}
    </span>
  );
}
