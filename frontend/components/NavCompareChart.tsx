'use client';

import { useEffect, useState } from 'react';
import { useTheme } from 'next-themes';
import {
  CartesianGrid,
  LabelList,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from 'recharts';

// AI-pick home: portfolio NAV (net of cost) vs a chosen index. In `money` mode
// both lines start at a notional initial capital ($10,000) at the selected
// window's start and grow to their final value (Jitta-style). The series is
// reduced upstream to one point per calendar year (+ the current end), drawn as
// STRAIGHT (linear) year-to-year segments with a hollow dot at each point — no
// hover tooltip (the data lives in the legend + the Annual-returns table; the
// chart is decorative / aria-hidden). Recharts is the project's chart engine;
// per design-system Rule 0, hex literals are the sanctioned exception for
// Recharts adapters — sourced from the soft Tailwind palette (emerald / indigo /
// slate) and theme-swapped via next-themes.

export interface NavChartPoint {
  date: string;
  portfolio: number | null;
  benchmark: number | null;
  /** First point of a calendar year — used for the year-only x-axis ticks. */
  yearStart?: boolean;
}

export interface Props {
  data: NavChartPoint[];
  portfolioLabel: string;
  benchmarkLabel: string;
  /** When true, format axis + end-labels as USD and draw the reference line +
   *  end-of-line value labels at the money scale. */
  money?: boolean;
  /** Reference-line value (window-start level). 100 when rebased, 10000 ($) in money mode. */
  baseline?: number;
}

// emerald-700 / emerald-400 · indigo-500 / indigo-400 (soft palette, Rule 1)
const PORTFOLIO = { light: '#047857', dark: '#34d399' };
const BENCHMARK = { light: '#6366f1', dark: '#818cf8' };

function fmtYear(d: string): string {
  return (d ?? '').slice(0, 4);
}

function fmtMoney(v: number): string {
  return `$${Math.round(v).toLocaleString('en-US')}`;
}

function fmtMoneyAxis(v: number): string {
  return Math.abs(v) >= 1000 ? `$${Math.round(v / 1000)}k` : `$${Math.round(v)}`;
}

interface EndLabelProps {
  x?: number | string;
  y?: number | string;
  value?: number | string | null;
  index?: number;
}

// Recharts LabelList content renderer — draws the final $ value only at the
// right end of the line (Jitta-style), nothing at the interior points.
function endLabel(total: number, color: string) {
  return function EndLabel({ x, y, value, index }: EndLabelProps): JSX.Element | null {
    if (
      index !== total - 1 ||
      value === null ||
      value === undefined ||
      x === undefined ||
      y === undefined
    ) {
      return null;
    }
    const num = Number(value);
    if (Number.isNaN(num)) return null;
    return (
      <text
        x={Number(x) + 6}
        y={Number(y)}
        dy={4}
        fontSize={11}
        fontWeight={600}
        fill={color}
        textAnchor="start"
      >
        {fmtMoney(num)}
      </text>
    );
  };
}

export function NavCompareChart({ data, portfolioLabel, benchmarkLabel, money = false, baseline = 100 }: Props) {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const isDark = mounted && resolvedTheme === 'dark';

  const axis = isDark ? '#94a3b8' : '#64748b'; // slate-400 / slate-500
  const grid = isDark ? '#1e293b' : '#e2e8f0'; // slate-800 / slate-200
  const pColor = isDark ? PORTFOLIO.dark : PORTFOLIO.light;
  const bColor = isDark ? BENCHMARK.dark : BENCHMARK.light;
  const surface = isDark ? '#0f172a' : '#ffffff'; // slate-900 card / white — hollow-dot fill
  const yearTicks = data.filter((d) => d.yearStart).map((d) => d.date);

  return (
    <div className="h-72 w-full" aria-hidden="true">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: money ? 60 : 8, bottom: 0, left: -12 }}>
          <CartesianGrid stroke={grid} strokeDasharray="3 3" vertical />
          <ReferenceLine y={baseline} stroke={grid} strokeWidth={1} />
          <XAxis
            dataKey="date"
            ticks={yearTicks}
            tickFormatter={fmtYear}
            tick={{ fontSize: 11, fill: axis }}
            stroke={grid}
            tickLine={false}
          />
          <YAxis
            domain={['auto', 'auto']}
            tickFormatter={money ? fmtMoneyAxis : undefined}
            tick={{ fontSize: 11, fill: axis }}
            stroke={grid}
            tickLine={false}
            width={money ? 48 : 40}
          />
          {/* No <Tooltip>: straight year-to-year line + hollow dots, no hover card (per request). */}
          <Line
            type="linear"
            dataKey="benchmark"
            name={benchmarkLabel}
            stroke={bColor}
            strokeWidth={1.5}
            dot={{ r: 3.5, fill: surface, stroke: bColor, strokeWidth: 1.5 }}
            connectNulls
            isAnimationActive={false}
          >
            {money && <LabelList content={endLabel(data.length, bColor)} />}
          </Line>
          <Line
            type="linear"
            dataKey="portfolio"
            name={portfolioLabel}
            stroke={pColor}
            strokeWidth={2}
            dot={{ r: 3.5, fill: surface, stroke: pColor, strokeWidth: 1.5 }}
            connectNulls
            isAnimationActive={false}
          >
            {money && <LabelList content={endLabel(data.length, pColor)} />}
          </Line>
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
