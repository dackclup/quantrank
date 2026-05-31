'use client';

// Signature moment (2026-05-29): the composite-score radial gauge on the
// stock detail header. On every visit, the arc sweeps from
// empty → the score's percentile and the partner number counts up over
// the same 800ms window (useCountUp + the `gauge-sweep` @keyframes share
// the easing). This is the ONE place the app spends a
// longer beat — it's the headline number, so it earns the emphasis.
// Plays on every visit to a stock's detail page (usePlayOnMount), so each
// stock you open gets its signature reveal. Reduced-motion → static final
// state (hooks return the target immediately, transition disabled in
// globals.css). Extracted from ScoreBadge's 'lg' branch so the 'sm' / 'md'
// table-cell variants stay server-rendered (no client JS × 502 rows).

import type { CSSProperties, JSX } from 'react';
import { useCountUp, usePlayOnMount } from '@/lib/useMotion';

const tierLabel = (score: number): string => {
  if (score >= 80) return 'Exceptional';
  if (score >= 60) return 'Strong';
  if (score >= 40) return 'Average';
  if (score >= 20) return 'Weak';
  return 'Poor';
};

export function ScoreGauge({
  score,
  accent,
  ticker,
}: {
  score: number;
  accent: string;
  ticker?: string;
}): JSX.Element {
  const r = 26;
  const circumference = 2 * Math.PI * r;
  const frac = Math.max(0, Math.min(1, score / 100));
  const arcLen = circumference * frac;

  // Play the sweep + count-up on EVERY visit to this stock's detail page
  // (per the "animate every time" direction). The ticker key is kept for
  // clarity but no longer gates — usePlayOnMount animates on each mount.
  // reduced-motion → play=false → hooks resolve to the final value at mount.
  const play = usePlayOnMount(`score-gauge:${ticker ?? score.toFixed(1)}`);
  const shown = useCountUp(score, play, 800);

  // The arc is always rendered at its FINAL strokeDashoffset (correct on
  // SSR / no-JS / reduced-motion / replay). When `play` is true we add the
  // `gauge-sweep` class, which runs a CSS @keyframes that animates the
  // dashoffset from empty (full circumference) → 0 delta, easing into the
  // rendered final value. A keyframe (not a transition + double-rAF) is
  // used deliberately: the earlier transition approach needed two
  // committed paint frames between empty→filled, which Chromium batches
  // away, so the transition never fired (the sweep was invisible — caught
  // by the 2026-05-29 audit's transitionstart/end event probe). A keyframe
  // added via class plays reliably on mount with no frame-commit race.
  // The animation's "from" offset is the full circumference (empty); the
  // "to" is the rendered strokeDashoffset, passed as a CSS var.
  const dashOffset = circumference - arcLen;

  return (
    <div className="flex items-center gap-2">
      <div className="relative h-16 w-16 shrink-0">
        <svg viewBox="0 0 64 64" className="h-16 w-16 -rotate-90">
          <circle
            cx="32"
            cy="32"
            r={r}
            fill="none"
            className="stroke-slate-100 dark:stroke-slate-800"
            strokeWidth="6"
          />
          <circle
            cx="32"
            cy="32"
            r={r}
            fill="none"
            stroke={accent}
            strokeWidth="6"
            strokeLinecap="round"
            className={play ? 'gauge-sweep' : undefined}
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
            style={
              play
                ? ({
                    // keyframe reads these: --gauge-from = empty (full
                    // circumference), animation eases to the rendered
                    // strokeDashoffset above.
                    '--gauge-from': `${circumference}`,
                  } as CSSProperties)
                : undefined
            }
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="font-mono text-base font-semibold tabular-nums text-slate-900 dark:text-slate-100">
            {shown.toFixed(0)}
          </span>
        </div>
      </div>
      {/* min-w reserves space for the widest count-up value ("100/100") so the
          column doesn't reflow as digit count changes during the sweep
          (0/100 → 73/100). Eliminates the micro-CLS the count-up introduces. */}
      <div className="flex min-w-[4.5rem] flex-col">
        <span className="text-[0.625rem] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
          Composite Score
        </span>
        <span className="font-mono text-lg font-semibold tabular-nums text-slate-900 dark:text-slate-100">
          {shown.toFixed(0)}/100
        </span>
        <span
          className="text-[0.625rem] uppercase tracking-wider"
          style={{ color: accent }}
        >
          {tierLabel(score)}
        </span>
      </div>
    </div>
  );
}
