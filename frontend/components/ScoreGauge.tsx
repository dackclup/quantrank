'use client';

// Signature moment (2026-05-29): the composite-score radial gauge on the
// stock detail header. On first view this session, the arc sweeps from
// empty → the score's percentile and the partner number counts up over
// the same 800ms window (useCountUp + the .gauge-arc stroke-dashoffset
// transition share the easing). This is the ONE place the app spends a
// longer beat — it's the headline number, so it earns the emphasis.
// Replays are suppressed per session (usePlayedOnce) so navigating across
// 502 stocks doesn't re-trigger it every time. Reduced-motion → static
// final state (hooks return the target immediately, transition disabled
// in globals.css). Extracted from ScoreBadge's 'lg' branch so the 'sm' /
// 'md' table-cell variants stay server-rendered (no client JS × 502 rows).

import { useEffect, useState, type JSX } from 'react';
import { useCountUp, usePlayedOnce } from '@/lib/useMotion';

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
}: {
  score: number;
  accent: string;
}): JSX.Element {
  const r = 26;
  const circumference = 2 * Math.PI * r;
  const frac = Math.max(0, Math.min(1, score / 100));
  const arcLen = circumference * frac;

  // Gate the sweep + count-up to the first view this session. After that,
  // `play` is false → hooks resolve to the final value at mount (no anim).
  const play = usePlayedOnce(`score-gauge:${score.toFixed(1)}`);
  const shown = useCountUp(score, play, 800);

  // Two-phase render for the stroke-dashoffset transition. Default
  // `filled = true` so SSR / pre-hydration / replay / reduced-motion all
  // paint the arc at its correct final length. Only on first view this
  // session do we briefly set it EMPTY then flip back to filled across
  // two animation frames, giving the .gauge-arc CSS transition two
  // distinct values to ease between (a single frame can batch into one
  // paint and skip the transition — the double-rAF guarantees a paint at
  // the empty state first).
  const [filled, setFilled] = useState(true);
  useEffect(() => {
    if (!play) return; // replay / reduced-motion / not-yet-resolved: stay filled
    setFilled(false); // empty now…
    const id = requestAnimationFrame(() =>
      requestAnimationFrame(() => setFilled(true)),
    ); // …filled after a guaranteed paint → transition eases the sweep
    return () => cancelAnimationFrame(id);
  }, [play]);

  const dashOffset = filled ? circumference - arcLen : circumference;

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
            className="gauge-arc"
            strokeDasharray={circumference}
            strokeDashoffset={dashOffset}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="font-mono text-base font-semibold tabular-nums text-slate-900 dark:text-slate-100">
            {shown.toFixed(0)}
          </span>
        </div>
      </div>
      <div className="flex flex-col">
        <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
          Composite Score
        </span>
        <span className="font-mono text-lg font-semibold tabular-nums text-slate-900 dark:text-slate-100">
          {shown.toFixed(1)}
        </span>
        <span
          className="text-[10px] uppercase tracking-wider"
          style={{ color: accent }}
        >
          {tierLabel(score)}
        </span>
      </div>
    </div>
  );
}
