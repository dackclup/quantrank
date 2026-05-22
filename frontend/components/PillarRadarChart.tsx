'use client';

import type { JSX } from 'react';

import type { PillarBaseline, PillarScores } from '@/lib/types';

// "Pillar breakdown" — horizontal bar list from the QuantRank.html
// design. The previous Recharts polar radar was hard to read for
// non-expert users (the design canvas feedback called it out
// specifically). Bar list is more legible for the "compare 8
// dimensions on a 0-100 scale" task because each pillar gets its
// own row with name, description, value, and tier label.
//
// Optional sector-median overlay renders as a small vertical notch
// on each bar. Only shown when peer count ≥5 to avoid noisy notches
// on thinly-populated sectors.

const ACTIVE_PILLARS: ReadonlyArray<readonly [keyof PillarScores, string]> = [
  ['quality', 'Quality'],
  ['value', 'Value'],
  ['growth', 'Growth'],
  ['momentum', 'Momentum'],
  ['health', 'Health'],
  ['profitability', 'Profitability'],
  ['technical', 'Technical'],
  ['risk', 'Risk'],
];

const PILLAR_DESCRIPTIONS: Record<string, string> = {
  Quality: 'Profit margins & asset efficiency',
  Value: 'Price vs fundamentals',
  Growth: 'Revenue & earnings trajectory',
  Momentum: 'Recent price strength',
  Health: 'Balance sheet & solvency',
  Profitability: 'ROE, ROA, ROIC',
  Technical: 'Trend & volatility signals',
  Risk: 'Volatility & drawdown profile',
};

// 4-step color ramp — same direction as ScoreBadge (sage at top,
// terracotta at bottom). The soft-color overrides in globals.css
// remap emerald/rose at render time so these RGB values produce
// the muted palette.
const colorFor = (v: number): string =>
  v >= 70 ? 'rgb(5 150 105)' :
  v >= 50 ? 'rgb(16 185 129)' :
  v >= 30 ? 'rgb(245 158 11)' :
  'rgb(225 29 72)';

const tierLabel = (v: number): string =>
  v >= 70 ? 'Strong' :
  v >= 50 ? 'Decent' :
  v >= 30 ? 'Weak' :
  'Poor';

export function PillarRadarChart({
  pillars,
  ticker,
  baseline,
}: {
  pillars: PillarScores | null;
  ticker: string;
  baseline?: PillarBaseline | null;
}): JSX.Element | null {
  if (pillars == null) return null;

  // Drop pillars whose data is null (e.g., for the current ticker
  // some inputs may have failed) — surface the dropped names in the
  // footer so the user knows which dimensions are missing.
  type RowData = {
    key: keyof PillarScores;
    label: string;
    value: number;
    baselineValue: number | null;
  };
  const rows: RowData[] = [];
  const droppedActive: string[] = [];
  for (const [key, label] of ACTIVE_PILLARS) {
    const v = pillars[key];
    if (v == null || Number.isNaN(v)) {
      droppedActive.push(label);
      continue;
    }
    rows.push({
      key,
      label,
      value: v,
      baselineValue: baseline?.values?.[label] ?? null,
    });
  }
  if (rows.length === 0) return null;

  const footer: string[] = [];
  if (droppedActive.length > 0) {
    footer.push(`${droppedActive.join(', ')} (data quality issue this run)`);
  }
  footer.push('Sentiment, ML (Phase 5+)');

  return (
    <section
      aria-label={`Pillar score breakdown for ${ticker}`}
      className="mb-4 rounded-xl border border-slate-200 bg-white p-5 shadow-medium"
    >
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-slate-600">
            Pillar breakdown
          </h2>
          <p className="mt-1 text-xs text-slate-500">
            0–100 percentile rank against current S&amp;P 500 (sector-relative for Quality / Value / Growth / Profitability)
          </p>
        </div>
        {baseline && (
          <div className="inline-flex items-center gap-1.5 text-[11px] text-slate-500">
            <span aria-hidden="true" className="inline-block h-3 w-0.5 bg-slate-400" />
            {baseline.label}
          </div>
        )}
      </div>

      <ul className="space-y-2">
        {rows.map((r) => {
          const widthClamped = Math.max(2, Math.min(100, r.value));
          const c = colorFor(r.value);
          const baselineClamped =
            r.baselineValue !== null ? Math.max(0, Math.min(100, r.baselineValue)) : null;
          return (
            <li
              key={r.key as string}
              className="grid grid-cols-[8rem_1fr_4.5rem] items-center gap-3"
              title={`${r.label}: ${r.value.toFixed(1)} (${tierLabel(r.value)})${
                r.baselineValue !== null && baseline
                  ? ` — ${baseline.label.toLowerCase()}: ${r.baselineValue.toFixed(1)}`
                  : ''
              }`}
            >
              <div className="min-w-0">
                <div className="text-sm font-medium text-slate-800">{r.label}</div>
                <div className="truncate text-[10px] text-slate-400">
                  {PILLAR_DESCRIPTIONS[r.label]}
                </div>
              </div>
              <div className="relative h-7 rounded-md bg-slate-100">
                {/* Tier-boundary tick lines at 30 / 50 / 70 — visually
                    show which tier the bar lands in. */}
                <div className="absolute inset-y-0 left-[30%] w-px bg-slate-200" />
                <div className="absolute inset-y-0 left-[50%] w-px bg-slate-200" />
                <div className="absolute inset-y-0 left-[70%] w-px bg-slate-200" />
                <div
                  className="absolute inset-y-1 left-1 rounded-sm"
                  style={{ width: `calc(${widthClamped}% - 8px)`, backgroundColor: c }}
                />
                {/* Sector-median notch — vertical mark slightly taller
                    than the bar so it's visible on top of the fill. */}
                {baselineClamped !== null && (
                  <div
                    className="absolute inset-y-[-2px] w-0.5 bg-slate-600"
                    style={{ left: `${baselineClamped}%` }}
                  />
                )}
              </div>
              <div className="text-right">
                <div
                  className="font-mono text-sm font-semibold tabular-nums"
                  style={{ color: c }}
                >
                  {r.value.toFixed(0)}
                </div>
                <div className="text-[10px] text-slate-400">{tierLabel(r.value)}</div>
              </div>
            </li>
          );
        })}
      </ul>

      {/* Axis ticks — labels under the bar column only (the bar
          width is 1fr in the grid, so the absolute-positioned spans
          inside align with the bars above). */}
      <div className="mt-2 grid grid-cols-[8rem_1fr_4.5rem] items-center gap-3">
        <div />
        <div className="relative h-4 text-[10px] text-slate-400">
          <span className="absolute left-0">0</span>
          <span className="absolute left-[30%] -translate-x-1/2">30</span>
          <span className="absolute left-[50%] -translate-x-1/2">50</span>
          <span className="absolute left-[70%] -translate-x-1/2">70</span>
          <span className="absolute right-0">100</span>
        </div>
        <div />
      </div>

      {/* Legend — explains the 4-tier color ramp. */}
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-500">
        <span className="inline-flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-3 rounded-sm"
            style={{ backgroundColor: 'rgb(5 150 105)' }}
          />
          Strong (70+)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-3 rounded-sm"
            style={{ backgroundColor: 'rgb(16 185 129)' }}
          />
          Decent (50–70)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-3 rounded-sm"
            style={{ backgroundColor: 'rgb(245 158 11)' }}
          />
          Weak (30–50)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-3 rounded-sm"
            style={{ backgroundColor: 'rgb(225 29 72)' }}
          />
          Poor (&lt;30)
        </span>
      </div>

      <p className="mt-3 text-xs text-slate-400">Pillars not shown: {footer.join('; ')}.</p>
    </section>
  );
}
