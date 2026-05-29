'use client';

import { useEffect, useMemo, useState } from 'react';
import { useTheme } from 'next-themes';
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
// - Fair-value + target reference lines, both the same theme-aware
//   near-white/near-black color + weight, distinguished only by dash
//   (fair dashed, target solid) so neither line dominates the other.
// - Fair/target values always surface as chips below the price headline
//   (the canonical number read); the in-chart lines carry no text label.
//   Off-range values show as a chip only (a line can't be drawn outside
//   the chart's y-axis).
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
  const [mounted, setMounted] = useState(false);
  // Remount keys: bumping either forces <AreaChart> to remount, which
  // re-runs Recharts' componentDidMount → displayDefaultTooltip(defaultIndex),
  // re-parking the crosshair + tooltip at the latest date. `restKey` bumps
  // when the pointer is released / leaves the chart (snap back to latest
  // after a drag); `layoutKey` bumps on orientation change (re-park after
  // rotate). Recharts 2.15 applies `defaultIndex` only on mount, so a
  // remount is how we re-assert it on those events.
  const [restKey, setRestKey] = useState(0);
  const [layoutKey, setLayoutKey] = useState(0);
  const { resolvedTheme } = useTheme();

  useEffect(() => setMounted(true), []);

  // Re-park the tooltip at the latest date when the device rotates
  // portrait↔landscape. matchMedia is browser-only; the guard keeps SSR
  // clean (component is 'use client', so this never runs server-side).
  // The bump is DEBOUNCED ~300ms after the orientation event so the
  // remount lands AFTER ResponsiveContainer has re-measured the new
  // width — remounting mid-resize makes Recharts' displayDefaultTooltip
  // park on index 0 instead of the latest.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const mq = window.matchMedia('(orientation: portrait)');
    let t: ReturnType<typeof setTimeout>;
    const handler = () => {
      clearTimeout(t);
      t = setTimeout(() => setLayoutKey((k) => k + 1), 300);
    };
    mq.addEventListener('change', handler);
    return () => {
      clearTimeout(t);
      mq.removeEventListener('change', handler);
    };
  }, []);

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
    // Skeleton placeholder — shimmer blocks roughly match the layout
    // shipped after load (current-price headline + change indicator +
    // period selector + chart canvas). Visual continuity reduces
    // layout shift when the data arrives. The `sr-only` span keeps
    // the loading state announceable to screen readers; `aria-busy`
    // + `aria-live="polite"` cue the same to assistive tech. Static
    // fallback for reduced-motion users handled by the globals.css
    // `@media (prefers-reduced-motion: reduce)` guard.
    return (
      <div className="space-y-3" aria-busy="true" aria-live="polite">
        <span className="sr-only">Loading price history…</span>
        <div className="h-7 w-32 animate-shimmer rounded-sm" />
        <div className="h-4 w-24 animate-shimmer rounded-sm" />
        <div className="h-7 w-full animate-shimmer rounded-sm" />
        <div className="h-64 w-full animate-shimmer rounded-sm" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-slate-400 dark:text-slate-500">
        Price history unavailable
      </div>
    );
  }

  if (chartData.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-slate-400 dark:text-slate-500">
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

  // Direction cue for the chips: green when the reference
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

  // Signed % distance of each reference price from the current price —
  // upside when positive, downside when negative. Rendered after the chip
  // dollar value (e.g. "Fair $126 (-14.7%)"); the sign matches the chip's
  // green/red direction cue. Suppressed if current price is missing / 0.
  const fmtDeltaPct = (ref: number): string | null => {
    if (currentPrice === null || currentPrice <= 0) return null;
    const pct = ((ref - currentPrice) / currentPrice) * 100;
    return `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`;
  };
  const fairDeltaPct = fairIsNumber ? fmtDeltaPct(fairPriceMedian as number) : null;
  const targetDeltaPct = targetEligible
    ? fmtDeltaPct(fairPriceMax as number)
    : null;

  // Color the chart line + area fill based on direction of the
  // visible window — Google-Finance-style cue ("green = up over the
  // selected period, red = down").
  const isPositive = periodChange?.positive ?? true;
  const trendStroke = isPositive ? '#10b981' : '#e11d48'; // emerald-500 / rose-600
  const trendFillId = `priceFill-${ticker}-${isPositive ? 'up' : 'down'}`;

  // Dark-mode-aware tooltip surface. The pre-mount default is light
  // to match the `color-scheme: light` initial value in globals.css
  // (avoids hydration flicker). Without these explicit colors the
  // Recharts default tooltip stays white-bg in dark mode AND the date
  // label inherits the body's `rgb(226 232 240)` cascade → unreadable
  // light-text-on-white. Shadow per LedgerCraft Elevation spec
  // (overlays + dropdowns are the only surfaces that get a shadow).
  const isDark = mounted && resolvedTheme === 'dark';
  const tooltipContentStyle = {
    fontSize: '0.75rem',
    borderRadius: '0.25rem',
    border: isDark ? '1px solid #334155' : '1px solid #e2e8f0',
    backgroundColor: isDark ? '#0f172a' : '#ffffff',
    boxShadow:
      '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
  };
  const tooltipLabelStyle = {
    color: isDark ? '#f1f5f9' : '#0f172a',
    fontWeight: 600,
    marginBottom: '2px',
  };

  return (
    <div className="space-y-3">
      {/* Current price + period change indicator — Google Finance
          pattern: large current quote on its own row, with the
          absolute + percent move on a second row beneath it. Mobile
          viewports were squeezing both onto a single line, leaving
          the change indicator clipped against the edge. */}
      {chartData.length > 0 && (
        <div className="flex flex-col gap-1">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-2xl font-semibold tabular-nums leading-none text-slate-900 dark:text-slate-100">
              ${chartData[chartData.length - 1].close.toFixed(2)}
            </span>
            <span className="text-xs font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
              USD
            </span>
          </div>
          {periodChange && (
            <div
              className={`flex flex-wrap items-baseline gap-1.5 text-sm ${isPositive ? 'text-emerald-700 dark:text-emerald-300' : 'text-rose-600 dark:text-rose-400'}`}
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
              <span className="text-xs font-normal text-slate-500 dark:text-slate-400">
                {PERIOD_LABEL[period]}
              </span>
            </div>
          )}
          <div className="text-sm tabular-nums text-slate-900 dark:text-slate-100">
            as of {formatTooltipLabel(chartData[chartData.length - 1].date)}
          </div>
        </div>
      )}

      {/* Reference price chips — always shown below the price headline
          as the canonical fair-value + target number read (the in-chart
          lines carry no text label). Chip color cues direction: green
          when the reference sits ABOVE current price (upside to that
          level), red when it sits BELOW (current price has run past it —
          overvalued vs that yardstick). */}
      {(fairIsNumber || targetEligible) && (
        <div className="flex flex-wrap gap-1.5 text-xs">
          {fairIsNumber && (
            <span
              className={`inline-flex items-center gap-1 rounded-sm px-2 py-0.5 ring-1 ring-inset ${fairAboveCurrent ? upChipCls : downChipCls}`}
            >
              <span
                className={`h-0 w-3 border-t border-dashed ${fairAboveCurrent ? 'border-emerald-600' : 'border-rose-600'}`}
              />
              <span className="tabular-nums">
                Fair {fmtPrice(fairPriceMedian as number)}
                {fairDeltaPct ? ` (${fairDeltaPct})` : ''}
              </span>
            </span>
          )}
          {targetEligible && (
            <span
              className={`inline-flex items-center gap-1 rounded-sm px-2 py-0.5 ring-1 ring-inset ${targetAboveCurrent ? upChipCls : downChipCls}`}
            >
              <span
                className={`h-[2px] w-3 ${targetAboveCurrent ? 'bg-emerald-700' : 'bg-rose-700'}`}
              />
              <span className="tabular-nums">
                Target {fmtPrice(fairPriceMax as number)}
                {targetDeltaPct ? ` (${targetDeltaPct})` : ''}
              </span>
            </span>
          )}
        </div>
      )}

      {/* Inline legend — beginner-friendly, doesn't require hover to
          decode the line styles. The Price swatch matches the trend
          color so the legend reflects what the chart is currently
          rendering. */}
      <div className="flex flex-wrap items-center gap-3 text-[11px] text-slate-500 dark:text-slate-400">
        <span className="inline-flex items-center gap-1.5">
          <span
            className="h-0.5 w-3.5 rounded-full"
            style={{ backgroundColor: trendStroke }}
          />
          Price
        </span>
        {fairIsNumber && (
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0 w-3.5 border-t-2 border-dashed border-slate-900 dark:border-slate-200" />
            Fair value
          </span>
        )}
        {targetEligible && (
          <span className="inline-flex items-center gap-1.5">
            <span className="h-[2px] w-3.5 bg-slate-900 dark:bg-slate-200" />
            Target
          </span>
        )}
      </div>

      {/* Time-period selector sits directly above the chart canvas
          (post-spot-check user request — easier scan path: read the
          numbers, choose a window, see the chart). */}
      <PriceTimePeriodSelector value={period} onChange={setPeriod} />

      {/* Re-park the crosshair at the latest date when an interaction ends.
          Four triggers cover the cases:
          - onPointerUp → a drag-release (touch finger-lift or mouse-up after
            a drag). A drag moves far enough that the browser suppresses the
            synthetic click, so pointerUp is the last event and owns this case.
          - onClick → a TAP (touch) / plain click. On a tap the tooltip is set
            to the tapped point by the compatibility synthetic-mouse + click
            that fire AFTER pointerUp, so a pointerUp-only re-park fires too
            early and the tap point sticks. `click` is the last event of a tap
            and bubbles to this wrapper AFTER Recharts has set the tap point,
            so re-parking here wins. (Drags don't fire click → no double work.)
          - onPointerCancel → a touch that STARTED on the chart then became a
            vertical page scroll: touch-action:pan-y hands the gesture to the
            browser, which fires pointercancel (NOT pointerup/click), so without
            this the crosshair stays stuck at the touched point after scrolling.
          - onPointerLeave → a mouse pointer leaving the chart. GUARDED to
            ignore pointerType==='touch': during a touch scrub the browser
            fires spurious pointerleave events as the finger crosses child-SVG
            boundaries (the wrapper never gets implicit pointer capture because
            pointerdown lands on a child), and an unguarded handler would
            remount <AreaChart> mid-drag → reset to defaultIndex → the
            crosshair could never follow the finger.
          touch-action:pan-y keeps vertical page scroll while handing
          horizontal drags to the chart for scrubbing.
          [&_.recharts-surface]:overflow-visible lets the latest-point dot +
          crosshair render fully at the FLUSH right edge (margin.right is 0 so
          the last point sits on the surface edge; otherwise the SVG viewport
          clips the dot in half). This is safe because `html, body {
          overflow-x: clip }` (globals.css) clips overflow at the DOCUMENT
          level — the real "page widens right after scrub" bug was the chart
          remount transiently overflowing, which the fixed sidebar backdrop
          then sized itself to and sustained; the document clip stops the
          layout viewport from ever growing. */}
      <div
        className="h-64 w-full [&_.recharts-surface]:overflow-visible"
        style={{ touchAction: 'pan-y' }}
        onPointerUp={() => setRestKey((k) => k + 1)}
        onClick={() => setRestKey((k) => k + 1)}
        onPointerCancel={() => setRestKey((k) => k + 1)}
        onPointerLeave={(e) => {
          if (e.pointerType !== 'touch') setRestKey((k) => k + 1);
        }}
      >
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            key={`${period}-${restKey}-${layoutKey}`}
            data={chartData}
            margin={{ top: 8, right: 0, left: 0, bottom: 0 }}
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
              contentStyle={tooltipContentStyle}
              labelStyle={tooltipLabelStyle}
              defaultIndex={chartData.length - 1}
              isAnimationActive={false}
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
                stroke={isDark ? '#e2e8f0' : '#0f172a'}
                strokeWidth={1.5}
                strokeDasharray="5 3"
                ifOverflow="hidden"
              />
            )}
            {targetInRange && (
              <ReferenceLine
                y={fairPriceMax as number}
                stroke={isDark ? '#e2e8f0' : '#0f172a'}
                strokeWidth={1.5}
                ifOverflow="hidden"
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
