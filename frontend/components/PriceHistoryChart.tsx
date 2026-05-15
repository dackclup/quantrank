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
// - Off-chart fair/target values surface as chip annotations so they
//   don't warp the y-axis when far from the stock's price range.
export function PriceHistoryChart({
  ticker,
  fairPriceMedian,
  fairPriceMax,
  recommendation,
}: Props) {
  const [data, setData] = useState<StockHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<TimePeriod>('1Y');

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

  const chartData = useMemo(
    () => sliceByPeriod(fullChartData, period),
    [fullChartData, period],
  );

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
  const fmtY = (v: number) => `$${v.toFixed(0)}`;
  const fmtTooltip = (v: number) => `$${v.toFixed(2)}`;
  const fmtPrice = (v: number) => `$${v.toFixed(2)}`;

  // PR 4f post-spot-check: compute a y-axis domain anchored on the
  // stock's own price range (with a ±10% pad). Reference lines render
  // INSIDE this domain only — they never "extend" the axis. When the
  // fair / target value falls outside it, the line is suppressed and
  // we surface the price as a chip annotation below the period selector
  // instead. This keeps the stock's price action filling the chart
  // (vs the prior version where a 2-3× target compressed the line to
  // ~20% of vertical space).
  let yDomain: [number, number] | ['auto', 'auto'] = ['auto', 'auto'];
  let stockMin = 0;
  let stockMax = 0;
  if (chartData.length > 0) {
    stockMin = chartData[0].close;
    stockMax = chartData[0].close;
    for (const p of chartData) {
      if (p.close < stockMin) stockMin = p.close;
      if (p.close > stockMax) stockMax = p.close;
    }
    const range = stockMax - stockMin || stockMax || 1;
    const pad = range * 0.1;
    yDomain = [stockMin - pad, stockMax + pad];
  }

  const fairIsNumber =
    typeof fairPriceMedian === 'number' && Number.isFinite(fairPriceMedian);
  const targetIsNumber =
    typeof fairPriceMax === 'number' && Number.isFinite(fairPriceMax);
  const targetEligible =
    targetIsNumber &&
    (recommendation === 'bullish' || recommendation === 'lean_bullish');

  const fairInRange =
    fairIsNumber &&
    (fairPriceMedian as number) >= (yDomain as [number, number])[0] &&
    (fairPriceMedian as number) <= (yDomain as [number, number])[1];
  const targetInRange =
    targetEligible &&
    (fairPriceMax as number) >= (yDomain as [number, number])[0] &&
    (fairPriceMax as number) <= (yDomain as [number, number])[1];

  // Off-chart prices get surfaced as a chip annotation row instead of
  // a reference line that would force the y-axis to stretch.
  const fairOffChart = fairIsNumber && !fairInRange;
  const targetOffChart = targetEligible && !targetInRange;

  return (
    <div className="space-y-3">
      <PriceTimePeriodSelector value={period} onChange={setPeriod} />

      {/* Off-chart reference price chips — surfaces fair / target
          values that fall outside the stock's visible price range so
          the user still sees the number, without warping the chart. */}
      {(fairOffChart || targetOffChart) && (
        <div className="flex flex-wrap gap-1.5 text-xs">
          {fairOffChart && (
            <span className="inline-flex items-center gap-1 rounded-full bg-slate-50 px-2 py-0.5 ring-1 ring-inset ring-slate-200 text-slate-600">
              <span className="h-0 w-3 border-t border-dashed border-slate-400" />
              <span>Fair {fmtPrice(fairPriceMedian as number)}</span>
              <span className="text-slate-400">
                ({(fairPriceMedian as number) < stockMin ? 'below' : 'above'} range)
              </span>
            </span>
          )}
          {targetOffChart && (
            <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 ring-1 ring-inset ring-slate-300 text-slate-800 font-medium">
              <span className="h-0.5 w-3 bg-slate-900" />
              <span>Target {fmtPrice(fairPriceMax as number)}</span>
              <span className="text-slate-500 font-normal">
                ({(fairPriceMax as number) < stockMin ? 'below' : 'above'} range)
              </span>
            </span>
          )}
        </div>
      )}

      {/* Inline legend — beginner-friendly, doesn't require hover to
          decode the line styles. */}
      <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-3.5 rounded-full bg-emerald-500" />
          Price
        </span>
        {fairIsNumber && (
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0 w-3.5 border-t border-dashed border-slate-400" />
            Fair value
          </span>
        )}
        {targetEligible && (
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-3.5 bg-slate-900" />
            Target
          </span>
        )}
      </div>

      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart
            data={chartData}
            margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
          >
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: '#64748b' }}
              tickFormatter={formatTick}
              minTickGap={32}
            />
            <YAxis
              domain={yDomain}
              tick={{ fontSize: 10, fill: '#64748b' }}
              tickFormatter={fmtY}
              width={52}
            />
            <Tooltip
              formatter={(v: number) => [fmtTooltip(v), 'Close']}
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
            {fairInRange && (
              <ReferenceLine
                y={fairPriceMedian as number}
                stroke="#94a3b8"
                strokeDasharray="5 3"
                ifOverflow="hidden"
                label={{
                  value: `Fair ${fmtPrice(fairPriceMedian as number)}`,
                  position: 'insideTopRight',
                  fill: '#64748b',
                  fontSize: 11,
                }}
              />
            )}
            {targetInRange && (
              <ReferenceLine
                y={fairPriceMax as number}
                stroke="#1e293b"
                strokeWidth={1.25}
                strokeDasharray="8 4"
                ifOverflow="hidden"
                label={{
                  value: `Target ${fmtPrice(fairPriceMax as number)}`,
                  position: 'insideTopRight',
                  fill: '#1e293b',
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
