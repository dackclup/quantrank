'use client';

import type { CSSProperties, JSX } from 'react';
import { useCountUp, usePlayOnMount } from '@/lib/useMotion';

// Donut variant of the Margin-of-Safety display, modeled on ScoreGauge (the
// composite-score donut) so the two hero summary stats — composite (quality)
// and MoS (price vs fair value) — share one visual AND motion family. On every
// visit the arc sweeps empty → |MoS|/100 and the number counts 0 → MoS over the
// same 800ms ease-in-out window (the `gauge-sweep` @keyframes + useCountUp,
// identical to ScoreGauge). Reduced-motion → static final state (hooks resolve
// to the target at mount, the keyframe is disabled in globals.css).
//
// DIRECTION (user spec 2026-05-31): the arc starts at 12 o'clock like the score
// gauge. Unlike the score (0–100, always one way), MoS is SIGNED:
//   • MoS ≥ 0  → sweeps CLOCKWISE, the SAME direction as the score gauge
//                (positive margin = upside; reads like a high score).
//   • MoS < 0  → sweeps COUNTER-CLOCKWISE, the OPPOSITE direction
//                (overvalued/downside visibly "runs the other way").
// Implemented by horizontally mirroring the gauge container (`-scale-x-100`)
// only when negative; the centered number is mirrored back so it stays
// readable. Reflecting the FINAL rendered ring is robust — it turns a clockwise
// sweep into a counter-clockwise one regardless of the svg's internal
// `-rotate-90`, with no fragile rotate∘scale transform composition. The
// gauge-sweep keyframe (dashoffset empty→final) plays inside the mirrored frame,
// so the sweep itself runs counter-clockwise.
//
// Color rule: MoS ≥ 0 → emerald (undervalued = good) / MoS < 0 → rose. Arc
// length = |MoS|/100 clamped to [0, 1]; values beyond ±100% max out the ring
// and the numeric label carries the magnitude.

const tierLabel = (mos: number): string => {
  if (mos >= 50) return 'Cheap';
  if (mos >= 20) return 'Undervalued';
  if (mos >= -10) return 'Fair value';
  if (mos >= -50) return 'Overvalued';
  return 'Expensive';
};

// Mid-saturation accent for the MoS gauge ring + tier label, matching
// ScoreBadge's inline gauge accent. Used INLINE (svg `stroke` / inline
// `color`), so the globals.css soft-color class overrides do NOT reach
// it — kept a touch punchier than the soft chip tokens so the thin 6px
// ring reads (emerald-600 / rose-600; no pure red/green per Rule 1).
const accentColor = (mos: number): string =>
  mos >= 0 ? '#059669' /* emerald-600 */ : '#e11d48'; /* rose-600 */

// Center label from a (possibly mid-count) value: sign + integer, clamped so it
// never overflows the 64×64 donut. Past ±99 the donut shows a CAPPED-gauge glyph
// "≤−99" / "≥+99" (NOT "<−99" / ">+99"): the ≤/≥ reads as "the ring is maxed,
// the real figure is in the text column" rather than a bare comparison that
// looked like it contradicted the unclamped −189% beside it (2026-06-02 audit).
const centerOf = (v: number): string =>
  v <= -99 ? '≤−99' : v >= 99 ? '≥+99' : `${v < 0 ? '−' : '+'}${Math.abs(Math.round(v))}`;

// Right-side big label from a (possibly mid-count) value: matches ScoreGauge's
// `tabular-nums text-lg` weight. Shows the REAL percentage with no clamp (the
// center label inside the 64px donut carries the compact ≤−99 / ≥+99 cap;
// out here there's room for the true value, e.g. −1362%), so deeply over-/
// under-valued tickers read their actual margin. Rounded to a whole percent.
const fullOf = (v: number): string =>
  `${v < 0 ? '−' : '+'}${Math.abs(v).toFixed(0)}%`;

export function MoSBadge({ mos }: { mos: number | null | undefined }): JSX.Element {
  // Hooks run unconditionally (before any early return) per the Rules of Hooks.
  // For the null/NaN case the target is a harmless 0 and the result is ignored.
  const play = usePlayOnMount(`mos-gauge:${mos ?? 'na'}`);
  const shown = useCountUp(mos ?? 0, play, 800);

  if (mos == null || Number.isNaN(mos)) {
    return (
      <div
        className="flex items-center gap-2"
        role="img"
        aria-label="Margin of safety versus fair value: unavailable"
      >
        <div className="relative h-16 w-16 shrink-0">
          <svg viewBox="0 0 64 64" className="h-16 w-16 -rotate-90" aria-hidden="true">
            <circle
              cx="32"
              cy="32"
              r={26}
              fill="none"
              className="stroke-slate-100 dark:stroke-slate-800"
              strokeWidth="6"
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-base text-slate-300 dark:text-slate-600">—</span>
          </div>
        </div>
        <div className="flex min-w-[3.5rem] flex-col">
          <span className="text-[0.625rem] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Margin of safety
            <span className="ml-1 normal-case tracking-normal text-slate-500 dark:text-slate-400">
              (vs fair value)
            </span>
          </span>
          <span className="font-mono text-lg font-semibold tabular-nums text-slate-300 dark:text-slate-600">
            —
          </span>
          <span className="text-[0.625rem] uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Unavailable
          </span>
        </div>
      </div>
    );
  }

  const r = 26;
  const circumference = 2 * Math.PI * r;
  const frac = Math.max(0, Math.min(1, Math.abs(mos) / 100));
  const arcLen = circumference * frac;
  // Arc renders at its FINAL dashoffset (correct on SSR / no-JS / reduced-motion
  // / replay); when `play` flips true the `gauge-sweep` keyframe eases from the
  // empty state (--gauge-from = full circumference) into this offset.
  const dashOffset = circumference - arcLen;
  const accent = accentColor(mos); // final sign drives color (no mid-count flicker)
  const reverse = mos < 0; // negative → mirror the gauge to counter-clockwise

  return (
    // role="img" + a single comprehensive aria-label so SR announces one clean
    // string ("Margin of safety versus fair value: +12%, Undervalued") instead
    // of the donut center digit + the text column separately — and so the
    // basis ("vs fair value") reaches SR/keyboard, which the mouse-only `title`
    // on this non-interactive div never did ($impeccable a11y minor). The label
    // is built from the FINAL `mos` (not the count-up `shown`), so it never
    // animates. The visual children are presentational under role="img".
    <div
      className="flex items-center gap-2"
      role="img"
      aria-label={`Margin of safety versus fair value: ${fullOf(mos)}, ${tierLabel(mos)}`}
      title={`${mos.toFixed(1)}% margin of safety vs fair value`}
    >
      {/* Negative MoS mirrors the whole gauge horizontally so the arc sweeps
          counter-clockwise (opposite the score gauge); the number span is
          mirrored back below so it stays readable. */}
      <div className={`relative h-16 w-16 shrink-0${reverse ? ' -scale-x-100' : ''}`}>
        <svg viewBox="0 0 64 64" className="h-16 w-16 -rotate-90" aria-hidden="true">
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
            style={play ? ({ '--gauge-from': `${circumference}` } as CSSProperties) : undefined}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          {/* text-sm here (vs ScoreGauge's text-base center) on purpose: the
              MoS center label carries a sign char (+/−), so it needs the extra
              room to stay inside the 64px donut at the fluid font-size ceiling. */}
          <span
            className={`font-mono text-sm font-semibold tabular-nums text-slate-900 dark:text-slate-100${
              reverse ? ' -scale-x-100' : ''
            }`}
          >
            {centerOf(shown)}
          </span>
        </div>
      </div>
      {/* min-w reserves space for the widest count-up value so the column
          doesn't reflow as the digit count changes during the sweep
          (mirrors ScoreGauge). */}
      <div className="flex min-w-[3.5rem] flex-col">
        <span className="text-[0.625rem] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
          Margin of safety
          <span className="ml-1 normal-case tracking-normal text-slate-500 dark:text-slate-400">
            (vs fair value)
          </span>
        </span>
        <span className="font-mono text-lg font-semibold tabular-nums text-slate-900 dark:text-slate-100">
          {fullOf(shown)}
        </span>
        <span className="text-[0.625rem] uppercase tracking-wider" style={{ color: accent }}>
          {tierLabel(mos)}
        </span>
      </div>
    </div>
  );
}
