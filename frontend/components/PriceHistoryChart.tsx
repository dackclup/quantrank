'use client';

import { useEffect, useState } from 'react';
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { StockHistory } from '@/lib/types';

interface Props {
  ticker: string;
}

type ChartPoint = { date: string; close: number };

// Lazy-loaded ~1y OHLCV chart. Fetches from the static
// /data/stocks/history/{TICKER}.json files written by Phase 3c
// Step 5 — keeps these out of the SSR bundle (~30KB × 502 stocks)
// since most users only view the chart on the detail page they
// navigate to, not all 502 at once.
export function PriceHistoryChart({ ticker }: Props) {
  const [data, setData] = useState<StockHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);

    // Use NEXT_PUBLIC_BASE_PATH if the static export is mounted under a
    // sub-path (e.g., GitHub Pages). Falls back to root for the standard
    // Vercel deployment.
    const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? '';
    const url = `${basePath}/data/stocks/history/${ticker}.json`;

    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<StockHistory>;
      })
      .then((json) => {
        if (!cancelled) {
          setData(json);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [ticker]);

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-slate-400">
        Loading price history…
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-slate-400">
        Price history unavailable
      </div>
    );
  }

  // Transform column-major (dates[], closes[]) → row-major for recharts.
  // Skip rows where close is null (preserves the gap rather than drawing
  // a line through it).
  const chartData: ChartPoint[] = [];
  for (let i = 0; i < data.dates.length; i += 1) {
    const c = data.closes[i];
    if (c !== null && Number.isFinite(c)) {
      chartData.push({ date: data.dates[i], close: c });
    }
  }

  if (chartData.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-slate-400">
        Price history unavailable
      </div>
    );
  }

  const formatTick = (raw: string) => raw.slice(5); // YYYY-MM-DD → MM-DD

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={chartData}
          margin={{ top: 8, right: 12, left: 0, bottom: 0 }}
        >
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: '#64748b' }}
            tickFormatter={formatTick}
            minTickGap={32}
          />
          <YAxis
            domain={['auto', 'auto']}
            tick={{ fontSize: 10, fill: '#64748b' }}
            tickFormatter={(v: number) => `$${v.toFixed(0)}`}
            width={48}
          />
          <Tooltip
            formatter={(v: number) => [`$${v.toFixed(2)}`, 'Close']}
            labelFormatter={(label: string) => label}
            contentStyle={{
              fontSize: '0.75rem',
              borderRadius: '0.375rem',
              border: '1px solid #e2e8f0',
            }}
          />
          <Line
            type="monotone"
            dataKey="close"
            stroke="#10b981"
            strokeWidth={2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
