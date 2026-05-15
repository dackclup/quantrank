'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
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

  // Google-Finance-style change indicator: absolute + percent move
  // across the visible window, plus direction (drives chart color).
  const periodChange = useMemo(() => {
    if (chartData.length < 2) return null;
    const first = chartData[0].close;
    const last = chartData[chartData.length - 1].close;
    if (first <= 0) return null;
    const abs = last - first;
    const pct = (abs / first) * 100;
    return { abs, pct, positive: abs >= 0 };
  }, [chartData]);

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

  // 5Y view spans multiple calendar years, so a YYYY-only label
  // reads cleanly across the axis. Shorter views all show "Mon YY"
  // (English month abbreviation + 2-digit year) — user feedback was
  // that numeric month indices were less scannable than month names
  // at a glance.
  const MONTH_ABBR = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];
  const formatTick = (raw: string) => {
    // raw is YYYY-MM-DD
    if (period === '5Y') return raw.slice(0, 4); // YYYY
    const monthIdx = Number(raw.slice(5, 7)) - 1;
    const yy = raw.slice(2, 4);
    return `${MONTH_ABBR[monthIdx] ?? raw.slice(5, 7)} ${yy}`;
  };
  // Tooltip label — "Mon DD, YYYY" reads more cleanly than the raw
  // ISO date and stays consistent with the X-axis month-abbr style.
  const formatTooltipLabel = (raw: string) => {
    const monthIdx = Number(raw.slice(5, 7)) - 1;
    const day = Number(raw.slice(8, 10));
    const year = raw.slice(0, 4);
    const mon = MONTH_ABBR[monthIdx];
    if (!mon || Number.isNaN(day)) return raw;
    return `${mon} ${day}, ${year}`;
  };
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
  // PR 4f post-spot-check: target line now renders for every
  // recommendation (was bullish / lean_bullish only). For hold /
  // sell tickers the target typically falls below current price —
  // the chip color cues that direction explicitly.
  const targetEligible = targetIsNumber;

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

  // Direction cue for the off-chart chips: green when the reference
  // sits ABOVE current price (upside to that level), red when it sits
  // below (current price has run past it). Removes the need for the
  // wordy "(below range)" / "(above range)" qualifier the user asked
  // to drop.
  const currentPrice =
    chartData.length > 0 ? chartData[chartData.length - 1].close : null;
  const fairAboveCurrent =
    fairIsNumber &&
    currentPrice !== null &&
    (fairPriceMedian as number) > currentPrice;
  const targetAboveCurrent =
    targetEligible &&
    currentPrice !== null &&
    (fairPriceMax as number) > currentPrice;

  const upChipCls =
    'bg-emerald-50 text-emerald-800 ring-emerald-300';
  const downChipCls =
    'bg-rose-50 text-rose-700 ring-rose-300';

  // Color the chart line + area fill based on direction of the
  // visible window — Google-Finance-style cue ("green = up over the
  // selected period, red = down").
  const isPositive = periodChange?.positive ?? true;
  const trendStroke = isPositive ? '#10b981' : '#e11d48'; // emerald-500 / rose-600
  const trendFillId = `priceFill-${ticker}-${isPositive ? 'up' : 'down'}`;

  return (
    <div className="space-y-3">
      <PriceTimePeriodSelector value={period} onChange={setPeriod} />

      {/* Current price + period change indicator — Google Finance
          pattern: large current quote on its own row, with the
          absolute + percent move on a second row beneath it. Mobile
          viewports were squeezing both onto a single line, leaving
          the change indicator clipped against the edge. */}
      {chartData.length > 0 && (
        <div className="flex flex-col gap-1">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-2xl font-semibold tabular-nums leading-none text-slate-900">
              ${chartData[chartData.length - 1].close.toFixed(2)}
            </span>
            <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
              USD
            </span>
          </div>
          {periodChange && (
            <div
              className={`flex flex-wrap items-baseline gap-1.5 text-sm ${isPositive ? 'text-emerald-700' : 'text-rose-600'}`}
            >
              <span className="font-mono font-semibold tabular-nums">
                {isPositive ? '+' : ''}
                {periodChange.abs.toFixed(2)}
              </span>
              <span className="font-mono tabular-nums">
                ({isPositive ? '+' : ''}
                {periodChange.pct.toFixed(2)}%)
              </span>
              <span>{isPositive ? '↑' : '↓'}</span>
              <span className="text-xs font-normal text-slate-500">
                {PERIOD_LABEL[period]}
              </span>
            </div>
          )}
        </div>
      )}

      {/* Off-chart reference price chips. Chip color cues direction:
          green when the reference sits ABOVE current price (upside to
          that level), red when it sits BELOW (current price has run
          past it — overvalued vs that yardstick). */}
      {(fairOffChart || targetOffChart) && (
        <div className="flex flex-wrap gap-1.5 text-xs">
          {fairOffChart && (
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 ring-1 ring-inset ${fairAboveCurrent ? upChipCls : downChipCls}`}
            >
              <span
                className={`h-0 w-3 border-t border-dashed ${fairAboveCurrent ? 'border-emerald-600' : 'border-rose-600'}`}
              />
              <span>Fair {fmtPrice(fairPriceMedian as number)}</span>
            </span>
          )}
          {targetOffChart && (
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 ring-1 ring-inset ${targetAboveCurrent ? upChipCls : downChipCls}`}
            >
              <span
                className={`h-[2px] w-3 ${targetAboveCurrent ? 'bg-emerald-700' : 'bg-rose-700'}`}
              />
              <span>Target {fmtPrice(fairPriceMax as number)}</span>
            </span>
          )}
        </div>
      )}

      {/* Inline legend — beginner-friendly, doesn't require hover to
          decode the line styles. The Price swatch matches the trend
          color so the legend reflects what the chart is currently
          rendering. */}
      <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500">
        <span className="inline-flex items-center gap-1.5">
          <span
            className="h-0.5 w-3.5 rounded-full"
            style={{ backgroundColor: trendStroke }}
          />
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
            <span className="h-[2px] w-3.5 bg-slate-900" />
            Target
          </span>
        )}
      </div>

      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={chartData}
            margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
          >
            <defs>
              <linearGradient id={trendFillId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={trendStroke} stopOpacity={0.22} />
                <stop offset="100%" stopColor={trendStroke} stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: '#64748b' }}
              tickFormatter={formatTick}
              minTickGap={32}
            />
            <YAxis hide domain={yDomain} />
            <Tooltip
              formatter={(v: number) => [fmtTooltip(v), 'Close']}
              labelFormatter={formatTooltipLabel}
              contentStyle={{
                fontSize: '0.75rem',
                borderRadius: '0.375rem',
                border: '1px solid #e2e8f0',
              }}
            />
            <Area
              type="monotone"
              dataKey="close"
              stroke={trendStroke}
              strokeWidth={2}
              fill={`url(#${trendFillId})`}
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
                stroke="#0f172a"
                ifOverflow="hidden"
                label={{
                  value: `Target ${fmtPrice(fairPriceMax as number)}`,
                  position: 'insideTopRight',
                  fill: '#0f172a',
                  fontSize: 11,
                }}
              />
            )}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// Plain-English period labels for the change indicator. Matches the
// Google Finance phrasing the user referenced as the desired design.
const PERIOD_LABEL: Record<TimePeriod, string> = {
  '1D': 'today',
  '5D': 'past 5 days',
  '1M': 'past month',
  '6M': 'past 6 months',
  YTD: 'year-to-date',
  '1Y': 'past year',
  '5Y': 'past 5 years',
};

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
    case '5Y':
      // PR 4f Phase 4.2 — the writer now persists ~5 trading years
      // (HISTORY_TAIL_DAYS=1260). Return the full series unsliced
      // so the chart shows the entire available history.
      return points;
    default:
      // 1D / 5D — selector disables these in Phase 4.1; return the
      // full series so the chart isn't blank if state is forced.
      return points;
  }

  const cutoffIso = cutoff.toISOString().slice(0, 10);
  return points.filter((p) => p.date >= cutoffIso);
}
