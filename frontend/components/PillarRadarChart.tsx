'use client';

import type { JSX } from 'react';

import type { PillarBaseline, PillarScores } from '@/lib/types';
import { TIERS } from '@/lib/visual';

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

// 5-step color ramp keyed to the SAME score-tier boundaries as the composite
// `TIERS` (25 / 40 / 55 / 70 — visual.ts). P3 vocabulary consolidation
// (2026-06-02): pillars previously used a SEPARATE 4-band Strong/Decent/Weak/
// Poor rubric at 30/50/70, which collided with the composite score tiers —
// "Strong" meant 55-70 on the score gauge but ≥70 on a pillar, same word for
// two different ranges. Now a pillar at 60 reads the SAME tier WORD + tone as a
// composite score of 60. These are INLINE style rgb() values, so the
// globals.css soft-color overrides (which remap utility CLASSES only) do NOT
// reach them — the bars render at full saturation BY DESIGN, echoing the
// score-gauge accent palette; the amber / dark-amber mid-bands have no
// soft-token equivalent in globals.css anyway. Color boundaries == label
// boundaries == gridlines == legend (all 25/40/55/70) so the pillar is
// internally coherent.
const colorFor = (v: number): string =>
  v >= 70 ? 'rgb(5 150 105)' :
  v >= 55 ? 'rgb(16 185 129)' :
  v >= 40 ? 'rgb(245 158 11)' :
  v >= 25 ? 'rgb(180 83 9)' :
  'rgb(225 29 72)';

// Tier WORD from the shared composite `TIERS` rubric (Exceptional / Strong /
// Average / Weak / Poor) so the pillar and the score gauge speak ONE
// vocabulary — single source of truth in visual.ts, so a threshold change
// there flows to both surfaces. Matches `getTier` semantics (min inclusive,
// max exclusive; top open bound 101).
const tierLabel = (v: number): string =>
  TIERS.find((t) => v >= t.min && v < t.max)?.label ?? 'Poor';

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
      className="mb-4 rounded border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"
    >
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-slate-600 dark:text-slate-400">
            Pillar breakdown
          </h2>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            0–100 percentile rank against current S&amp;P 500 (sector-relative for Quality / Value / Growth / Profitability)
          </p>
        </div>
        {baseline && (
          <div className="inline-flex items-center gap-1.5 text-[0.6875rem] text-slate-500 dark:text-slate-400">
            <span aria-hidden="true" className="inline-block h-3 w-0.5 bg-slate-400 dark:bg-slate-500" />
            {baseline.label}
          </div>
        )}
      </div>

      <ul className="space-y-3 sm:space-y-2">
        {rows.map((r) => {
          const widthClamped = Math.max(2, Math.min(100, r.value));
          // Band + display off the ROUNDED integer (the badge shows `rounded`),
          // so a 54.6 doesn't render "55" next to an "Average" tone while the
          // legend says Strong starts at 55 (§Gotchas band-from-rounded). The
          // bar FILL width stays on the raw float — it's a continuous element.
          const rounded = Math.round(r.value);
          const c = colorFor(rounded);
          const baselineClamped =
            r.baselineValue !== null ? Math.max(0, Math.min(100, r.baselineValue)) : null;
          return (
            <li
              key={r.key as string}
              className="grid grid-cols-[1fr_auto] grid-rows-[auto_auto] gap-x-3 gap-y-1.5 sm:grid-cols-[8rem_1fr_4.5rem] sm:grid-rows-1 sm:items-center sm:gap-3"
              title={`${r.label}: ${r.value.toFixed(1)} (${tierLabel(rounded)})${
                r.baselineValue !== null && baseline
                  ? ` — ${baseline.label.toLowerCase()}: ${r.baselineValue.toFixed(1)}`
                  : ''
              }`}
            >
              <div className="min-w-0">
                <div className="text-sm font-medium text-slate-800 dark:text-slate-200">{r.label}</div>
                <div className="line-clamp-1 text-[0.625rem] text-slate-500 dark:text-slate-400 sm:truncate">
                  {PILLAR_DESCRIPTIONS[r.label]}
                </div>
              </div>
              <div className="relative order-last col-span-2 h-5 rounded-sm bg-slate-100 dark:bg-slate-800 sm:order-none sm:col-span-1">
                {/* Tier-boundary tick lines at 25 / 40 / 55 / 70 (the shared
                    composite TIERS boundaries) — show which tier the bar lands in. */}
                <div className="absolute inset-y-0 left-[25%] w-px bg-slate-200 dark:bg-slate-700" />
                <div className="absolute inset-y-0 left-[40%] w-px bg-slate-200 dark:bg-slate-700" />
                <div className="absolute inset-y-0 left-[55%] w-px bg-slate-200 dark:bg-slate-700" />
                <div className="absolute inset-y-0 left-[70%] w-px bg-slate-200 dark:bg-slate-700" />
                <div
                  className="absolute inset-y-0.5 left-1 rounded-sm"
                  style={{ width: `calc(${widthClamped}% - 8px)`, backgroundColor: c }}
                />
                {/* Sector-median notch — vertical mark slightly taller
                    than the bar so it's visible on top of the fill. */}
                {baselineClamped !== null && (
                  <div
                    className="absolute inset-y-[-2px] w-0.5 bg-slate-600 dark:bg-slate-300"
                    style={{ left: `${baselineClamped}%` }}
                  />
                )}
              </div>
              <div className="self-start text-right sm:self-auto">
                <div
                  className="font-mono text-sm font-semibold tabular-nums"
                  style={{ color: c }}
                >
                  {rounded}
                </div>
                <div className="text-[0.625rem]" style={{ color: c }}>{tierLabel(rounded)}</div>
                {/* Sector-median value is otherwise only in the mouse `title`
                    + the visual notch on the bar — surface it to keyboard/SR
                    too ($impeccable a11y minor). */}
                {r.baselineValue !== null && baseline && (
                  <span className="sr-only">
                    {baseline.label} {Math.round(r.baselineValue)}
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      {/* Axis ticks — labels under the bar column only (the bar
          width is 1fr in the grid, so the absolute-positioned spans
          inside align with the bars above). */}
      <div className="mt-2 grid grid-cols-[1fr_auto] items-center gap-x-3 sm:grid-cols-[8rem_1fr_4.5rem] sm:gap-3">
        <div className="hidden sm:block" />
        <div className="relative col-span-2 h-4 text-[0.625rem] text-slate-500 dark:text-slate-400 sm:col-span-1">
          <span className="absolute left-0">0</span>
          <span className="absolute left-[25%] -translate-x-1/2">25</span>
          <span className="absolute left-[40%] -translate-x-1/2">40</span>
          <span className="absolute left-[55%] -translate-x-1/2">55</span>
          <span className="absolute left-[70%] -translate-x-1/2">70</span>
          <span className="absolute right-0">100</span>
        </div>
        <div className="hidden sm:block" />
      </div>

      {/* Legend — explains the 5-tier color ramp (shared composite TIERS
          vocabulary + boundaries, so a pillar tier reads the same as a
          composite score tier). */}
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[0.6875rem] text-slate-500 dark:text-slate-400">
        <span className="inline-flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-3 rounded-sm"
            style={{ backgroundColor: 'rgb(5 150 105)' }}
          />
          Exceptional (70+)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-3 rounded-sm"
            style={{ backgroundColor: 'rgb(16 185 129)' }}
          />
          Strong (55–70)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-3 rounded-sm"
            style={{ backgroundColor: 'rgb(245 158 11)' }}
          />
          Average (40–55)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-3 rounded-sm"
            style={{ backgroundColor: 'rgb(180 83 9)' }}
          />
          Weak (25–40)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            className="inline-block h-2 w-3 rounded-sm"
            style={{ backgroundColor: 'rgb(225 29 72)' }}
          />
          Poor (&lt;25)
        </span>
      </div>

      <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">Pillars not shown: {footer.join('; ')}.</p>
    </section>
  );
}
