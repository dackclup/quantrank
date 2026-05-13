import type { JSX } from 'react';
import { mosVisualFraction } from '@/lib/visual';

// Micro diverging bar for the MoS column. Solves the "sea of red"
// problem the design feedback flagged: with most S&P 500 stocks
// showing MoS ≤ −20% in run #15, a column of red numbers carried
// no differentiation. The bar visualizes magnitude in a clamped
// ±100% window centered on zero, so an undervalued stock pulls
// right (sage) and an overvalued stock pulls left (terracotta).
//
// Label uses a short rounded percentage ("−25%") rather than the
// full clamp display ("< −99%") so the cell stays scannable. The
// title attribute carries the exact unclamped value for hover
// inspection.

export function MoSCell({
  mos,
  align = 'right',
}: {
  mos: number | null | undefined;
  align?: 'right' | 'left';
}): JSX.Element {
  if (mos === null || mos === undefined || Number.isNaN(mos)) {
    return <span className="text-slate-300">—</span>;
  }
  const frac = mosVisualFraction(mos);
  if (frac === null) return <span className="text-slate-300">—</span>;

  const isNeg = mos < 0;
  // Bar width from the center line. frac is 0..1 mapped from -100..+100;
  // distance from center 0.5 is |frac - 0.5|. Half-width because each
  // side of the center can use at most 50% of the track.
  const widthPct = Math.abs((frac - 0.5) * 2) * 100;

  const sign = mos >= 0 ? '+' : '';
  const label =
    mos < -99 ? '<−99%' :
    mos > 500 ? '>+500%' :
    `${sign}${mos.toFixed(0)}%`;

  // emerald-700 / emerald-600 / slate-400 / rose-600 — the
  // soft-color overrides in globals.css remap these to muted sage
  // and terracotta at render time.
  const color =
    mos >= 20 ? 'rgb(5 150 105)' :
    mos > 0 ? 'rgb(16 185 129)' :
    mos > -20 ? 'rgb(148 163 184)' :
    'rgb(225 29 72)';
  const labelColor =
    mos >= 20 ? 'text-emerald-700' :
    mos > 0 ? 'text-emerald-600' :
    mos > -20 ? 'text-slate-500' :
    'text-rose-600';

  return (
    <div
      className={`flex items-center gap-2 ${align === 'right' ? 'justify-end' : ''}`}
      title={`${mos.toFixed(1)}% margin of safety`}
    >
      <span className={`tabular-nums text-xs font-medium ${labelColor}`}>{label}</span>
      <div className="relative h-3 w-16 overflow-hidden rounded-sm bg-slate-100">
        {/* Center axis line */}
        <div className="absolute inset-y-0 left-1/2 w-px bg-slate-300" />
        {/* Diverging bar — anchored at center, extends right (positive)
            or left (negative) by widthPct/2 of the track. */}
        <div
          className="absolute inset-y-0"
          style={{
            [isNeg ? 'right' : 'left']: '50%',
            width: `${widthPct / 2}%`,
            backgroundColor: color,
          }}
        />
      </div>
    </div>
  );
}
