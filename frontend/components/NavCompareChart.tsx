'use client';

import { useEffect, useState } from 'react';
import { useTheme } from 'next-themes';
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

// AI-pick home: portfolio NAV (net of cost) vs a chosen index, both rebased to
// 100 at the selected window's start, so the line shows relative performance
// from that point. Recharts is the project's chart engine; per design-system
// Rule 0, hex literals are the sanctioned exception for Recharts adapters — they
// are sourced from the soft Tailwind palette (emerald / indigo / slate) and
// theme-swapped via next-themes.

export interface NavChartPoint {
  date: string;
  portfolio: number | null;
  benchmark: number | null;
}

export interface Props {
  data: NavChartPoint[];
  portfolioLabel: string;
  benchmarkLabel: string;
}

// emerald-700 / emerald-400 · indigo-500 / indigo-400 (soft palette, Rule 1)
const PORTFOLIO = { light: '#047857', dark: '#34d399' };
const BENCHMARK = { light: '#6366f1', dark: '#818cf8' };

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function fmtTick(d: string): string {
  const parts = d.split('-');
  const mon = MONTHS[Number(parts[1]) - 1] ?? '';
  const yy = (parts[0] ?? '').slice(2);
  return `${mon} '${yy}`;
}

interface TooltipItem {
  dataKey?: string | number;
  name?: string | number;
  value?: number | string | null;
  color?: string;
}

interface NavTooltipProps {
  active?: boolean;
  payload?: TooltipItem[];
  label?: string | number;
}

function NavTooltip({ active, payload, label }: NavTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="rounded-sm border border-slate-200 bg-white/95 px-3 py-2 shadow-medium dark:border-slate-700 dark:bg-slate-900/95">
      <div className="mb-1 font-mono text-[0.625rem] text-slate-500 dark:text-slate-400">
        {fmtTick(String(label))}
      </div>
      <div className="space-y-0.5">
        {payload.map((item) => (
          <div key={String(item.dataKey)} className="flex items-center gap-2 text-xs">
            <span
              className="inline-block h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: item.color }}
              aria-hidden="true"
            />
            <span className="text-slate-600 dark:text-slate-300">{item.name}</span>
            <span className="ml-auto pl-3 font-mono font-semibold tabular-nums text-slate-900 dark:text-slate-100">
              {item.value === null || item.value === undefined ? '—' : Number(item.value).toFixed(1)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function NavCompareChart({ data, portfolioLabel, benchmarkLabel }: Props) {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const isDark = mounted && resolvedTheme === 'dark';

  const axis = isDark ? '#94a3b8' : '#64748b'; // slate-400 / slate-500
  const grid = isDark ? '#1e293b' : '#e2e8f0'; // slate-800 / slate-200
  const pColor = isDark ? PORTFOLIO.dark : PORTFOLIO.light;
  const bColor = isDark ? BENCHMARK.dark : BENCHMARK.light;

  return (
    <div className="h-72 w-full" aria-hidden="true">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid stroke={grid} strokeDasharray="3 3" vertical={false} />
          <ReferenceLine y={100} stroke={grid} strokeWidth={1} />
          <XAxis
            dataKey="date"
            tickFormatter={fmtTick}
            minTickGap={48}
            tick={{ fontSize: 11, fill: axis }}
            stroke={grid}
            tickLine={false}
          />
          <YAxis
            domain={['auto', 'auto']}
            tick={{ fontSize: 11, fill: axis }}
            stroke={grid}
            tickLine={false}
            width={40}
          />
          <Tooltip content={<NavTooltip />} cursor={{ stroke: axis, strokeDasharray: '3 3' }} />
          <Line
            type="monotone"
            dataKey="benchmark"
            name={benchmarkLabel}
            stroke={bColor}
            strokeWidth={1.5}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="portfolio"
            name={portfolioLabel}
            stroke={pColor}
            strokeWidth={2}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
