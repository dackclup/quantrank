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
      if (showSpy && typeof p.spy === 'number' && Number.isFinite(p.spy)) {
        // In normalized mode the SPY series shares the axis with the
        // stock; include it in min/max so the lines aren't clipped.
        if (p.spy < stockMin) stockMin = p.spy;
        if (p.spy > stockMax) stockMax = p.spy;
      }
    }
    const range = stockMax - stockMin || stockMax || 1;
    const pad = range * 0.1;
    yDomain = [stockMin - pad, stockMax + pad];
  }

  // Reference lines only meaningful in absolute mode — normalized
  // mode is showing % return, where a fair-price absolute level
  // has no meaning.
  const fairIsNumber =
    typeof fairPriceMedian === 'number' && Number.isFinite(fairPriceMedian);
  const targetIsNumber =
    typeof fairPriceMax === 'number' && Number.isFinite(fairPriceMax);
  const targetEligible =
    targetIsNumber &&
    (recommendation === 'bullish' || recommendation === 'lean_bullish');

  const fairInRange =
    !normalized &&
    fairIsNumber &&
    (fairPriceMedian as number) >= (yDomain as [number, number])[0] &&
    (fairPriceMedian as number) <= (yDomain as [number, number])[1];
  const targetInRange =
    !normalized &&
    targetEligible &&
    (fairPriceMax as number) >= (yDomain as [number, number])[0] &&
    (fairPriceMax as number) <= (yDomain as [number, number])[1];

  // Off-chart prices get surfaced as a chip annotation row instead of
  // a reference line that would force the y-axis to stretch.
  const fairOffChart = !normalized && fairIsNumber && !fairInRange;
  const targetOffChart = !normalized && targetEligible && !targetInRange;

  return (
    <div className="space-y-3">
      {/* Toolbar — stacks vertically on narrow viewports so the
          7-button selector and the "vs SPY" toggle don't overflow on
          mobile (post-PR-4f spot-check, APA screenshot showed the
          SPY toggle clipped at the right edge of the chip row). */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <PriceTimePeriodSelector value={period} onChange={setPeriod} />
        <button
          type="button"
          aria-pressed={showSpy}
          onClick={() => setShowSpy((v) => !v)}
          className={
            'inline-flex w-fit items-center rounded-full ring-1 ring-inset ' +
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
          decode the three line styles. */}
      <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-0.5 w-3.5 rounded-full bg-emerald-500" />
          {normalized ? ticker : 'Price'}
        </span>
        {normalized && showSpy && (
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0 w-3.5 border-t-[1.5px] border-dashed border-teal-700" />
            SPY
          </span>
        )}
        {!normalized && fairIsNumber && (
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0 w-3.5 border-t border-dashed border-slate-400" />
            Fair value
          </span>
        )}
        {!normalized && targetEligible && (
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
