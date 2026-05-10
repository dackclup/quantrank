'use client';

import type { JSX } from 'react';
import {
  Bar,
  BarChart,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { FairPriceEnsemble } from '@/lib/types';

// 6-method horizontal-bar visualization of the fair-price ensemble
// (PR 3d Step 8). Bars are sorted to match the existing FairPriceCard
// table order for visual continuity. Outlier methods (per-method
// extreme_*_estimate warnings) are grayed; the X-axis domain caps at
// 1.2× max(non-outlier value, current_price, median, max), so an
// extreme outlier value extends off-chart on the right — that's the
// visual intent.
//
// Recharts naming gotcha: `<BarChart layout="vertical">` produces
// HORIZONTAL bars (the chart's main axis is vertical, but the bars
// extend horizontally). The default `layout="horizontal"` produces
// vertical bars. We want horizontal bars here, so we pass
// `layout="vertical"` despite the visual we're building being
// horizontal-oriented. Recharts' axis terminology, not ours.

interface FairPriceBarChartProps {
  fair_price: FairPriceEnsemble | null;
  current_price: number | null;
  ticker: string;
}

type MethodKey =
  | 'graham'
  | 'multiples_pe'
  | 'multiples_pb'
  | 'multiples_ev_ebitda'
  | 'rim'
  | 'dcf';

const METHOD_ORDER: ReadonlyArray<readonly [MethodKey, string]> = [
  ['graham', 'Graham (defensive)'],
  ['multiples_pe', 'P/E multiples'],
  ['multiples_pb', 'P/B multiples'],
  ['multiples_ev_ebitda', 'EV/EBITDA'],
  ['rim', 'Residual Income'],
  ['dcf', 'DCF (2-stage)'],
] as const;

interface ChartRow {
  key: MethodKey;
  label: string;
  // The value plotted on the X-axis. Negative source values are
  // clamped to 0 here (would distort the bar otherwise). The original
  // unclamped number lives in `raw_value` for the tooltip.
  value: number;
  raw_value: number;
  is_outlier: boolean;
}

const APPLICABLE_FILL = 'rgb(99 102 241)'; // indigo-500
const OUTLIER_FILL = 'rgb(148 163 184)'; // slate-400
const CURRENT_PRICE_STROKE = 'rgb(244 63 94)'; // rose-500
const MEDIAN_STROKE = 'rgb(67 56 202)'; // indigo-700
const MAX_STROKE = 'rgb(165 180 252)'; // indigo-300

function fmtPrice(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—';
  if (value < 0.01) return '< $0.01';
  if (value >= 1_000_000) return '—';
  return `$${value.toFixed(2)}`;
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ payload: ChartRow }>;
}

function CustomTooltip({ active, payload }: TooltipProps): JSX.Element | null {
  if (!active || !payload || payload.length === 0) return null;
  const row = payload[0].payload;
  return (
    <div className="rounded-md border border-slate-200 bg-white px-3 py-2 text-xs shadow-sm">
      <p className="font-medium text-slate-900">{row.label}</p>
      <p className="mt-0.5 tabular-nums text-slate-700">{fmtPrice(row.raw_value)}</p>
      {row.is_outlier && (
        <p className="mt-1 text-rose-700">
          Outlier — excluded from MAX, kept in MEDIAN
        </p>
      )}
    </div>
  );
}

export function FairPriceBarChart({
  fair_price,
  current_price,
  ticker,
}: FairPriceBarChartProps): JSX.Element | null {
  // Loose null check — same forward-compat reason as Tier2EventCard:
  // older StockDetail JSONs (pre-PR-3c) lack `fair_price` entirely,
  // so runtime sees `undefined` not `null`.
  if (fair_price == null || current_price == null || Number.isNaN(current_price)) {
    return null;
  }

  const warnings = new Set(fair_price.valuation_warnings ?? []);
  const rows: ChartRow[] = [];
  for (const [key, label] of METHOD_ORDER) {
    const m = fair_price.methods[key];
    if (!m || !m.applicable || m.value === null || Number.isNaN(m.value)) {
      continue;
    }
    const raw = m.value;
    rows.push({
      key,
      label,
      // Clamp at 0 for the bar geometry — bars can't go negative
      // visually. The tooltip surfaces the unclamped raw_value.
      value: Math.max(raw, 0),
      raw_value: raw,
      is_outlier: warnings.has(`extreme_${key}_estimate`),
    });
  }

  if (rows.length === 0) {
    return null;
  }

  // Domain cap: 1.2× the largest "real" value we want on-chart.
  // Outliers are intentionally excluded from this cap so they extend
  // off-chart on the right — visual signal that the value is extreme.
  const realValues: number[] = [current_price];
  for (const r of rows) {
    if (!r.is_outlier) realValues.push(r.value);
  }
  if (fair_price.median !== null) realValues.push(fair_price.median);
  if (fair_price.max !== null) realValues.push(fair_price.max);
  const domainMax = Math.max(...realValues) * 1.2;

  const hasOutlier = rows.some((r) => r.is_outlier);

  return (
    <section
      aria-label={`Fair price methods for ${ticker}`}
      className="mb-4 rounded-lg border border-slate-200 bg-white p-4 sm:max-w-2xl"
    >
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
        Fair price methods
      </h2>
      <div className="h-72 w-full" role="img" aria-label="Horizontal bar chart of 6 fair-price methods">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={rows}
            layout="vertical"
            margin={{ top: 10, right: 30, bottom: 10, left: 10 }}
          >
            <XAxis
              type="number"
              domain={[0, domainMax]}
              tick={{ fontSize: 10, fill: 'rgb(71 85 105)' }}
              tickFormatter={(v: number) => `$${v.toFixed(0)}`}
            />
            <YAxis
              type="category"
              dataKey="label"
              tick={{ fontSize: 11, fill: 'rgb(71 85 105)' }}
              width={140}
            />
            <Tooltip
              content={<CustomTooltip />}
              cursor={{ fill: 'rgb(241 245 249)' }}
            />
            <Bar dataKey="value" isAnimationActive={false}>
              {rows.map((row) => (
                <Cell
                  key={row.key}
                  fill={row.is_outlier ? OUTLIER_FILL : APPLICABLE_FILL}
                />
              ))}
            </Bar>
            <ReferenceLine
              x={current_price}
              stroke={CURRENT_PRICE_STROKE}
              strokeDasharray="4 4"
              label={{
                value: `Current ${fmtPrice(current_price)}`,
                position: 'insideBottomRight',
                fill: CURRENT_PRICE_STROKE,
                fontSize: 11,
                offset: 8,
              }}
            />
            {fair_price.median !== null && (
              <ReferenceLine
                x={fair_price.median}
                stroke={MEDIAN_STROKE}
                strokeWidth={2}
              />
            )}
            {fair_price.max !== null && (
              <ReferenceLine
                x={fair_price.max}
                stroke={MAX_STROKE}
                strokeWidth={2}
              />
            )}
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
        <span className="inline-flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block h-2.5 w-2.5 rounded-sm"
            style={{ backgroundColor: APPLICABLE_FILL }}
          />
          Applicable
        </span>
        {hasOutlier && (
          <span className="inline-flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className="inline-block h-2.5 w-2.5 rounded-sm"
              style={{ backgroundColor: OUTLIER_FILL }}
            />
            Outlier
          </span>
        )}
        <span className="inline-flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block h-0.5 w-4"
            style={{ backgroundColor: MEDIAN_STROKE }}
          />
          Median
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block h-0.5 w-4"
            style={{ backgroundColor: MAX_STROKE }}
          />
          Max (excl. outliers)
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block h-0.5 w-4 border-t border-dashed"
            style={{ borderColor: CURRENT_PRICE_STROKE }}
          />
          Current
        </span>
      </div>

      {hasOutlier && (
        <p className="mt-2 text-xs text-slate-400">
          Outliers (&gt; 5× or &lt; 0.2× current price) excluded from MAX,
          retained in MEDIAN.
        </p>
      )}
    </section>
  );
}
