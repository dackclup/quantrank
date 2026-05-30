import type { JSX } from 'react';

// Donut variant of the Margin-of-Safety display, modeled on ScoreBadge
// size="lg". Used in the stock detail hero row next to the composite
// donut so the two summary stats — composite (quality) and MoS (price
// vs fair value) — share a visual family.
//
// Color rule (per user spec):
//   MoS >= 0  → emerald (undervalued = good)
//   MoS  < 0  → rose    (overvalued  = bad)
//
// Arc length: |MoS| / 100, clamped to [0, 1] so values beyond ±100%
// simply max out the ring (deeply over- or under-valued tickers all
// show the same full ring; the numeric label below carries the
// magnitude).

const tierLabel = (mos: number): string => {
  if (mos >= 50) return 'Cheap';
  if (mos >= 20) return 'Undervalued';
  if (mos >= -10) return 'Fair value';
  if (mos >= -50) return 'Overvalued';
  return 'Expensive';
};

// Match the visual weight of ScoreBadge's accent (mid-saturation
// 600-tier). Using soft emerald + rose per the design-system Rule 1
// "no pure red / no pure green" guideline.
const accentColor = (mos: number): string =>
  mos >= 0 ? '#059669' /* emerald-600 */ : '#e11d48'; /* rose-600 */

export function MoSBadge({ mos }: { mos: number | null | undefined }): JSX.Element {
  if (mos == null || Number.isNaN(mos)) {
    return (
      <div className="flex items-center gap-2">
        <div className="relative h-16 w-16 shrink-0">
          <svg viewBox="0 0 64 64" className="h-16 w-16 -rotate-90">
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
        <div className="flex flex-col">
          <span className="text-[0.625rem] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Margin of safety
          </span>
          <span className="font-mono text-lg font-semibold tabular-nums text-slate-300 dark:text-slate-600">
            —
          </span>
          <span className="text-[0.625rem] uppercase tracking-wider text-slate-400 dark:text-slate-500">
            Unavailable
          </span>
        </div>
      </div>
    );
  }

  const r = 26;
  const circumference = 2 * Math.PI * r;
  const frac = Math.max(0, Math.min(1, Math.abs(mos) / 100));
  const accent = accentColor(mos);

  // Compact center label: sign + integer (max 4 chars: "+99", "−99",
  // ">+99", "<−99"). Avoids overflowing the 64×64 donut.
  const sign = mos < 0 ? '−' : '+';
  const centerLabel =
    mos < -99 ? '<−99' :
    mos > 99 ? '>+99' :
    `${sign}${Math.abs(Math.round(mos))}`;

  // Right-side big label: matches ScoreBadge's `tabular-nums text-lg`
  // weight; clamps the same long-tail values the rankings table uses.
  const fullLabel =
    mos < -99 ? '<−99%' :
    mos > 500 ? '>+500%' :
    `${sign}${Math.abs(mos).toFixed(0)}%`;

  return (
    <div className="flex items-center gap-2" title={`${mos.toFixed(1)}% margin of safety`}>
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
            strokeDasharray={`${circumference * frac} ${circumference}`}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="font-mono text-sm font-semibold tabular-nums text-slate-900 dark:text-slate-100">
            {centerLabel}
          </span>
        </div>
      </div>
      <div className="flex flex-col">
        <span className="text-[0.625rem] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
          Margin of safety
        </span>
        <span className="font-mono text-lg font-semibold tabular-nums text-slate-900 dark:text-slate-100">
          {fullLabel}
        </span>
        <span className="text-[0.625rem] uppercase tracking-wider" style={{ color: accent }}>
          {tierLabel(mos)}
        </span>
      </div>
    </div>
  );
}
