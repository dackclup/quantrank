'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
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
  // `sweepKey` keys the chart on an intro replay (remounts <AreaChart> so
  // Recharts re-runs its left→right area-draw animation); `playDraw` is the
  // gate that says "this remount should ANIMATE" (true only for a sweep — IO
  // scroll-in or period change — NOT for the rest/resize re-park remounts, which
  // must stay instant). Bumped together by the sweep triggers below.
  const [sweepKey, setSweepKey] = useState(0);
  const [playDraw, setPlayDraw] = useState(false);
  // Gate so the scroll-into-view sweep fires only the FIRST time the chart
  // enters the viewport (not on every scroll up/down past it).
  const hasSwept = useRef(false);
  // Self-drawn intro crosshair overlay (a vertical line + a dot that RIDES the
  // price curve), animated left→right by rAF in sync with the area draw. During
  // the sweep the Recharts cursor + activeDot are suppressed (playDraw) so only
  // this animated crosshair shows; at the end it fades and Recharts' parked
  // cursor/dot take over at the latest point. Refs let the rAF mutate the SVG
  // attributes directly (no per-frame React re-render).
  const overlaySvgRef = useRef<SVGSVGElement | null>(null);
  const overlayLineRef = useRef<SVGLineElement | null>(null);
  const overlayDotRef = useRef<SVGCircleElement | null>(null);
  const drawRafRef = useRef<number | null>(null);
  // Chart wrapper — observed for WIDTH changes to re-park the crosshair (Bug B).
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const { resolvedTheme } = useTheme();

  useEffect(() => setMounted(true), []);

  // Fire the intro sweep the first time the chart scrolls into view on the
  // detail page ("เลื่อนลงมาเห็นกราฟแบบเต็ม"). IntersectionObserver so the
  // animation starts when the user actually sees it, not on mount (the chart is
  // below the hero fold). One-shot via hasSwept. Browser-only; deps re-attach
  // once the chart wrapper exists (after loading/error/data resolve).
  useEffect(() => {
    const el = wrapperRef.current;
    if (!el || typeof IntersectionObserver === 'undefined') return;
    if (hasSwept.current) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting && !hasSwept.current) {
          hasSwept.current = true;
          setPlayDraw(true);
          setSweepKey((k) => k + 1);
          io.disconnect();
        }
      },
      { threshold: 0.35 }, // most of the chart visible before it draws in
    );
    io.observe(el);
    return () => io.disconnect();
  }, [loading, error, data]);

  // Re-run the sweep on every period change (1D-5Y). The period state drives
  // chartData, so a new window's line draws in left→right too. Skipped on the
  // very first render (the scroll-into-view observer owns the first sweep).
  // Motion Rule 2 ("no re-firing on in-page interaction") gray zone: a period
  // switch REPLACES the entire data series (a new line arriving), not a
  // re-stagger of existing content — the case Rule 2 actually targets — so
  // re-sweeping the new series reads as "new data drawing in", which is the
  // intended affordance (user-requested 2026-05-30).
  const firstPeriodRender = useRef(true);
  useEffect(() => {
    if (firstPeriodRender.current) {
      firstPeriodRender.current = false;
      return;
    }
    setPlayDraw(true);
    setSweepKey((k) => k + 1);
  }, [period]);

  // Drive the intro crosshair left→right in sync with the area-draw animation.
  // Runs on each sweep (sweepKey bump while playDraw is true). Each frame:
  //   1. ease-out progress p (fast→slow) over DRAW_MS
  //   2. target x = p · surfaceWidth
  //   3. find the price-curve point at that x via getPointAtLength binary
  //      search → the dot RIDES the line; the vertical line spans full height
  //   4. write x/y straight onto the SVG line+dot refs (no React re-render)
  // When p reaches 1 the overlay fades and playDraw flips false, handing the
  // rest-state crosshair back to Recharts' parked cursor + activeDot at the
  // latest point. Reduced-motion: skip the rAF, leave playDraw false so the
  // Recharts cursor shows immediately (the area also renders un-animated).
  const DRAW_MS = 1100;
  useEffect(() => {
    if (!playDraw) return;
    if (typeof window === 'undefined') return;
    const reduce =
      window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) {
      setPlayDraw(false);
      return;
    }
    const wrap = wrapperRef.current;
    const svg = overlaySvgRef.current;
    const line = overlayLineRef.current;
    const dot = overlayDotRef.current;
    if (!wrap || !svg || !line || !dot) {
      setPlayDraw(false);
      return;
    }
    // Recharts renders async after the remount; poll briefly for the curve.
    let t0 = 0;
    let startedAt = performance.now();
    const easeOut = (t: number) => 1 - Math.pow(1 - t, 3); // fast→slow
    const tick = (now: number) => {
      const curve = wrap.querySelector(
        '.recharts-area-curve',
      ) as SVGPathElement | null;
      const surf = wrap.querySelector('.recharts-surface') as SVGSVGElement | null;
      if (!curve || !surf) {
        // curve not painted yet — wait up to ~400ms, then bail to Recharts
        if (now - startedAt > 400) {
          setPlayDraw(false);
          return;
        }
        drawRafRef.current = requestAnimationFrame(tick);
        return;
      }
      if (t0 === 0) t0 = now; // start the clock when the curve first exists
      const w = surf.getBoundingClientRect().width || 1;
      const h = surf.getBoundingClientRect().height || 1;
      const p = Math.min(1, (now - t0) / DRAW_MS);
      const x = easeOut(p) * w;
      // binary-search the curve length whose point.x ≈ target x
      const L = curve.getTotalLength();
      let lo = 0;
      let hi = L;
      for (let i = 0; i < 18; i += 1) {
        const mid = (lo + hi) / 2;
        if (curve.getPointAtLength(mid).x < x) lo = mid;
        else hi = mid;
      }
      const pt = curve.getPointAtLength((lo + hi) / 2);
      line.setAttribute('x1', String(x));
      line.setAttribute('x2', String(x));
      line.setAttribute('y1', '0');
      line.setAttribute('y2', String(h));
      dot.setAttribute('cx', String(x));
      dot.setAttribute('cy', String(pt.y));
      svg.style.opacity = '1';
      if (p < 1) {
        drawRafRef.current = requestAnimationFrame(tick);
      } else {
        // hand off to Recharts' parked cursor/dot, then hide the overlay
        svg.style.opacity = '0';
        drawRafRef.current = null; // no pending frame — clear the stale id
        setPlayDraw(false);
      }
    };
    drawRafRef.current = requestAnimationFrame(tick);
    return () => {
      if (drawRafRef.current !== null) cancelAnimationFrame(drawRafRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sweepKey, playDraw]);

  // Crosshair re-park on layout change (rotation / window resize / sidebar
  // expand-collapse) is handled by the ResizeObserver effect just below the
  // chartData memo — a width-driven detector that subsumes the old
  // orientation-only matchMedia listener. See that effect for the rationale.

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

  // Re-park the crosshair at the latest date after any WIDTH change settles —
  // device rotation, window resize, OR the left sidebar expanding/collapsing
  // (which reflows the main-content width). A width change makes
  // ResponsiveContainer re-measure the chart, but Recharts applies
  // `defaultIndex` only on MOUNT — so without re-asserting it the crosshair
  // drifts to a stale/left x after a re-measure (the "crosshair jumps left on
  // sidebar toggle" bug). Bumping `layoutKey` remounts <AreaChart>, re-running
  // displayDefaultTooltip(defaultIndex) at the latest point. DEBOUNCED ~300ms
  // so the remount lands AFTER the re-measure — remounting mid-resize parks on
  // index 0 (far left). The width-only delta gate ignores height-only changes
  // so the chart's own crosshair rendering can't trigger a spurious remount.
  // ResizeObserver is browser-only; wrapperRef is null during loading/error/
  // empty, so the deps re-attach the observer once the chart wrapper mounts.
  useEffect(() => {
    const el = wrapperRef.current;
    if (!el || typeof ResizeObserver === 'undefined') return;
    let lastWidth = el.getBoundingClientRect().width;
    let t: ReturnType<typeof setTimeout>;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0].contentRect.width;
      if (Math.abs(w - lastWidth) < 1) return; // height-only change → ignore
      lastWidth = w;
      clearTimeout(t);
      t = setTimeout(() => setLayoutKey((k) => k + 1), 300);
    });
    ro.observe(el);
    return () => {
      clearTimeout(t);
      ro.disconnect();
    };
    // Re-attach only when the wrapper's existence changes (loading/error/data);
    // NOT on chartData.length — the wrapper div persists across period switches
    // (only the inner <AreaChart> remounts via key), so the observer stays valid
    // and a period change needn't disconnect/re-observe.
  }, [loading, error, data]);

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

  // Dark-mode flag — drives the crosshair cursor + active-dot colors (the
  // price tooltip box was removed per user request; only the crosshair line +
  // point remain). The pre-mount default is light to match the
  // `color-scheme: light` initial value in globals.css (avoids hydration
  // flicker).
  const isDark = mounted && resolvedTheme === 'dark';

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
      <div className="flex flex-wrap items-center gap-3 text-[0.6875rem] text-slate-500 dark:text-slate-400">
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
        ref={wrapperRef}
        className="relative h-64 w-full [&_.recharts-surface]:overflow-visible"
        style={{ touchAction: 'pan-y' }}
        onPointerDown={(e) => {
          // A tap WITHOUT a drag must move the crosshair to the tap point.
          // Recharts only updates the tooltip on touch-MOVE (handleTouchMove);
          // handleTouchStart just calls handleMouseDown, which never touches the
          // tooltip — so a bare tap would leave the crosshair parked at latest.
          // Drive Recharts' onMouseMove directly: dispatch a synthetic mousemove
          // at the touch point from INSIDE .recharts-wrapper (so it bubbles
          // through Recharts' handler). getMouseInfo reads pageX, and a
          // constructed MouseEvent derives pageX = clientX + scrollX, so passing
          // clientX/clientY from the pointer is enough. Mouse pointers already
          // hover-track, so this is touch-only.
          if (e.pointerType !== 'touch') return;
          const surface = e.currentTarget.querySelector('.recharts-surface');
          if (!surface) return;
          const { pageX, pageY, clientX, clientY } = e;
          const ev = new MouseEvent('mousemove', {
            bubbles: true,
            cancelable: true,
            clientX,
            clientY,
          });
          // pageX/pageY are NOT part of MouseEventInit, so a constructed event
          // leaves them at 0 — but Recharts' getMouseInfo reads pageX. Set them
          // explicitly to the pointer's page coords or the crosshair lands
          // off-chart (negative chartX) and Recharts clears the tooltip.
          Object.defineProperty(ev, 'pageX', { get: () => pageX });
          Object.defineProperty(ev, 'pageY', { get: () => pageY });
          surface.dispatchEvent(ev);
        }}
        onPointerUp={() => setRestKey((k) => k + 1)}
        onClick={() => setRestKey((k) => k + 1)}
        onPointerCancel={() => setRestKey((k) => k + 1)}
        onPointerLeave={(e) => {
          if (e.pointerType !== 'touch') setRestKey((k) => k + 1);
        }}
      >
        {/* The intro is now driven by (a) Recharts' OWN left→right area-draw
            animation (animated only on a sweep remount via `playDraw`), which
            reveals the line + fill WITHOUT touching the X-axis or its date
            labels (the axis is a sibling layer, so it stays put — user request),
            and (b) a self-drawn crosshair overlay (below) that rides the curve
            left→right in lockstep. `sweepKey` remounts the chart to replay the
            draw; the remount is keyed together with restKey/layoutKey. */}
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            key={`${period}-${restKey}-${layoutKey}-${sweepKey}`}
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
            {/* Tooltip kept ONLY for its crosshair `cursor` (the vertical line +
                the active-point dot Recharts draws at the hovered/parked index).
                The price BOX is removed per user request — `content={() => null}`
                renders no popup, so the chart shows just the crosshair line
                tracking the finger/pointer with no obscuring panel. The cursor
                is suppressed (transparent) WHILE the intro draw plays so only
                the self-drawn animated crosshair shows; once the draw ends
                (playDraw → false) this parked cursor takes over at the latest
                point. Bolder color than before (slate-600/300 + 1.5px solid) so
                it reads clearly against both the line and the slate page bg
                (user: "crosshair กลืนกับกราฟและพื้นหลัง"). */}
            <Tooltip
              content={() => null}
              cursor={
                playDraw
                  ? false
                  : {
                      stroke: isDark ? '#cbd5e1' : '#475569',
                      strokeWidth: 1.5,
                      strokeDasharray: '4 3',
                    }
              }
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
              activeDot={
                playDraw
                  ? false
                  : {
                      r: 4,
                      fill: trendStroke,
                      stroke: isDark ? '#0f172a' : '#ffffff',
                      strokeWidth: 2,
                    }
              }
              // Animate the left→right area draw ONLY on a sweep remount
              // (playDraw). The rest/resize re-park remounts keep it instant so
              // the crosshair re-park doesn't visibly redraw the whole line.
              isAnimationActive={playDraw}
              animationDuration={DRAW_MS}
              animationEasing="ease-out"
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

        {/* Self-drawn intro crosshair overlay — absolutely positioned ON TOP of
            the chart, spanning the same box. The rAF effect above animates the
            line (full-height vertical) + the dot (riding the price curve) from
            x=0 → right edge in ease-out lockstep with the area draw, then sets
            opacity 0 and hands the rest-state crosshair back to Recharts. It is
            opacity 0 + pointer-events-none at rest so it never blocks scrubbing.
            Colors match the bolder Recharts cursor (slate-600/300) so the
            animated and parked crosshairs look identical. preserveAspectRatio
            none + a viewBox synced to the surface px size would over-engineer
            this — instead the rAF writes RAW px coords (the SVG has no viewBox,
            so user units == px), matching the surface 1:1 since margins are 0. */}
        <svg
          ref={overlaySvgRef}
          className="pointer-events-none absolute inset-0 h-full w-full"
          style={{ opacity: 0 }}
          aria-hidden="true"
        >
          <line
            ref={overlayLineRef}
            x1={0}
            x2={0}
            y1={0}
            y2={0}
            stroke={isDark ? '#cbd5e1' : '#475569'}
            strokeWidth={1.5}
            strokeDasharray="4 3"
          />
          <circle
            ref={overlayDotRef}
            cx={0}
            cy={0}
            r={4}
            fill={trendStroke}
            stroke={isDark ? '#0f172a' : '#ffffff'}
            strokeWidth={2}
          />
        </svg>
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
