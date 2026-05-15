'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { Recommendation, StockHistory } from '@/lib/types';

import {
  PriceTimePeriodSelector,
  type TimePeriod,
} from '@/components/PriceTimePeriodSelector';

interface Props {
  ticker: string;
  fairPriceMedian?: number | null;
  fairPriceMax?: number | null;
  recommendation?: Recommendation | null;
}

type ChartPoint = {
  date: string;
  close: number;
  spy?: number | null;
};

// Lazy-loaded ~1y OHLCV chart. Fetches from the static
// /data/stocks/history/{TICKER}.json files written by Phase 3c
// Step 5 — keeps these out of the SSR bundle (~30KB × 502 stocks)
// since most users only view the chart on the detail page they
// navigate to, not all 502 at once.
//
// PR 4f extends this with:
// - 7-button time-period selector (1D/5D/5Y disabled with tooltip)
// - Gray dashed fair-price line at fair_price.median (all tickers)
// - Black solid target-price line at fair_price.max
//   (bullish / lean_bullish only)
// - "vs SPY" overlay toggle — normalizes both lines to 100 at the
//   window start so % return is comparable.
export function PriceHistoryChart({
  ticker,
  fairPriceMedian,
  fairPriceMax,
  recommendation,
}: Props) {
  const [data, setData] = useState<StockHistory | null>(null);
  const [spyData, setSpyData] = useState<StockHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<TimePeriod>('1Y');
  const [showSpy, setShowSpy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);

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

  // SPY fetched once; toggled by `showSpy`. Failing this fetch
  // silently disables the SPY overlay (graceful degrade) — common
  // case is the static export hasn't shipped SPY.json yet.
  useEffect(() => {
    if (!showSpy || spyData !== null) return;
    let cancelled = false;
    const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? '';
    fetch(`${basePath}/data/stocks/history/SPY.json`)
      .then((r) => (r.ok ? (r.json() as Promise<StockHistory>) : null))
      .then((json) => {
        if (!cancelled && json) setSpyData(json);
      })
      .catch(() => {
        // Silent — toggle just doesn't draw anything if SPY.json missing.
      });
    return () => {
      cancelled = true;
    };
  }, [showSpy, spyData]);

  const fullChartData: ChartPoint[] = useMemo(() => {
    if (!data) return [];
    const out: ChartPoint[] = [];
    for (let i = 0; i < data.dates.length; i += 1) {
      const c = data.closes[i];
      if (c !== null && Number.isFinite(c)) {
        out.push({ date: data.dates[i], close: c });
      }
    }
    return out;
  }, [data]);

  const slicedData = useMemo(
    () => sliceByPeriod(fullChartData, period),
    [fullChartData, period],
  );

  // Build the chart series. If SPY toggle is on AND SPY.json
  // available, normalize both lines to 100 at the start of the
  // visible window. Otherwise, render the stock in absolute dollars.
  const { chartData, normalized } = useMemo(() => {
    if (showSpy && spyData) {
      const spyClosesByDate = new Map<string, number>();
      for (let i = 0; i < spyData.dates.length; i += 1) {
        const c = spyData.closes[i];
        if (c !== null && Number.isFinite(c)) {
          spyClosesByDate.set(spyData.dates[i], c);
        }
      }
      // Find the first stock-date that also has an SPY close so the
      // two lines anchor at the same x.
      let stockBase: number | null = null;
      let spyBase: number | null = null;
      for (const row of slicedData) {
        const s = spyClosesByDate.get(row.date);
        if (s !== undefined) {
          stockBase = row.close;
          spyBase = s;
          break;
        }
      }
      if (stockBase !== null && spyBase !== null) {
        const norm: ChartPoint[] = slicedData.map((row) => {
          const s = spyClosesByDate.get(row.date) ?? null;
          return {
            date: row.date,
            close: (row.close / stockBase) * 100,
            spy: s !== null ? (s / spyBase) * 100 : null,
          };
        });
        return { chartData: norm, normalized: true };
      }
    }
    return { chartData: slicedData, normalized: false };
  }, [slicedData, showSpy, spyData]);

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

  if (chartData.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-slate-400">
        Price history unavailable
      </div>
    );
  }

  const formatTick = (raw: string) => raw.slice(5); // YYYY-MM-DD → MM-DD
  const fmtY = (v: number) =>
    normalized ? `${v.toFixed(0)}` : `$${v.toFixed(0)}`;
  const fmtTooltip = (v: number) =>
    normalized ? `${v.toFixed(2)}` : `$${v.toFixed(2)}`;

  // Reference lines only meaningful in absolute mode — normalized
  // mode is showing % return, where a fair-price absolute level
  // has no meaning.
  const showFairLine =
    !normalized &&
    typeof fairPriceMedian === 'number' &&
    Number.isFinite(fairPriceMedian);
  const showTargetLine =
    !normalized &&
    typeof fairPriceMax === 'number' &&
    Number.isFinite(fairPriceMax) &&
    (recommendation === 'bullish' || recommendation === 'lean_bullish');

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <PriceTimePeriodSelector value={period} onChange={setPeriod} />
        <button
          type="button"
          aria-pressed={showSpy}
          onClick={() => setShowSpy((v) => !v)}
          className={
            'inline-flex items-center rounded-full ring-1 ring-inset ' +
            'px-2.5 py-1 text-xs font-medium transition-colors ' +
            (showSpy
              ? 'bg-emerald-50 text-emerald-800 ring-emerald-300'
              : 'bg-white text-slate-600 ring-slate-200 hover:bg-slate-50')
          }
          title={
            showSpy
              ? 'Toggle off to return to absolute price'
              : 'Show SPY benchmark normalized to 100 at window start'
          }
        >
          vs SPY
        </button>
      </div>
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={chartData}
            margin={{ top: 8, right: 56, left: 0, bottom: 0 }}
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
              tickFormatter={fmtY}
              width={48}
            />
            <Tooltip
              formatter={(v: number, name: string) => [
                fmtTooltip(v),
                name === 'close' ? (normalized ? ticker : 'Close') : 'SPY',
              ]}
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
              isAnimationActive={false}
            />
            {normalized && (
              <Line
                type="monotone"
                dataKey="spy"
                stroke="#0f766e"
                strokeWidth={1.5}
                strokeDasharray="4 2"
                dot={false}
                isAnimationActive={false}
              />
            )}
            {showFairLine && (
              <ReferenceLine
                y={fairPriceMedian as number}
                stroke="#94a3b8"
                strokeDasharray="5 3"
                ifOverflow="extendDomain"
                label={{
                  value: `Fair $${(fairPriceMedian as number).toFixed(2)}`,
                  position: 'right',
                  fill: '#64748b',
                  fontSize: 11,
                }}
              />
            )}
            {showTargetLine && (
              <ReferenceLine
                y={fairPriceMax as number}
                stroke="#0f172a"
                strokeWidth={1.5}
                ifOverflow="extendDomain"
                label={{
                  value: `Target $${(fairPriceMax as number).toFixed(2)}`,
                  position: 'right',
                  fill: '#0f172a',
                  fontSize: 12,
                  fontWeight: 600,
                }}
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// Pure helper: slice the (already-loaded, ascending-date) point
// array down to the visible window for the selected period. 1D / 5D
// / 5Y are deferred (selector disables them) so they never reach
// here, but the function returns the full series as a safe fallback.
export function sliceByPeriod(
  points: ChartPoint[],
  period: TimePeriod,
): ChartPoint[] {
  if (points.length === 0) return points;

  const lastDate = points[points.length - 1].date;
  // YYYY-MM-DD parses cleanly via Date.parse; the data is already in
  // that format (see write_stock_history).
  const last = new Date(`${lastDate}T00:00:00Z`);

  let cutoff: Date | null = null;
  switch (period) {
    case '1M':
      cutoff = new Date(last);
      cutoff.setUTCMonth(cutoff.getUTCMonth() - 1);
      break;
    case '6M':
      cutoff = new Date(last);
      cutoff.setUTCMonth(cutoff.getUTCMonth() - 6);
      break;
    case 'YTD':
      cutoff = new Date(Date.UTC(last.getUTCFullYear(), 0, 1));
      break;
    case '1Y':
      cutoff = new Date(last);
      cutoff.setUTCFullYear(cutoff.getUTCFullYear() - 1);
      break;
    default:
      // 1D / 5D / 5Y — selector disables these in Phase 4.1; return
      // the full series so the chart isn't blank if state is forced.
      return points;
  }

  const cutoffIso = cutoff.toISOString().slice(0, 10);
  return points.filter((p) => p.date >= cutoffIso);
}
