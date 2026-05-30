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
  // Index the HEADLINE (price / change / date) reflects. null = the latest
  // point (rest state). Set by a scrub (Recharts onMouseMove → activeTooltipIndex)
  // so the headline tracks the crosshair the user drags; cleared on pointer
  // leave / release so it snaps back to latest. During the intro ANIMATION the
  // headline is instead written imperatively (refs below) frame-by-frame — NOT
  // via this state — so the 60fps sweep never triggers a React re-render (that
  // was the "ค้างหนัก" trap). React re-render on animation end restores the
  // latest value (= the last animated frame).
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  // Headline span refs — the rAF writes price/change/date text straight onto
  // these during the animation (imperative, zero re-render).
  const priceRef = useRef<HTMLSpanElement | null>(null);
  const changeAbsRef = useRef<HTMLSpanElement | null>(null);
  const changePctRef = useRef<HTMLSpanElement | null>(null);
  const changeArrowRef = useRef<HTMLSpanElement | null>(null);
  const changeRowRef = useRef<HTMLDivElement | null>(null);
  const asOfRef = useRef<HTMLSpanElement | null>(null);
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
  // gate that says "this remount should ANIMATE" (true only for a sweep — a
  // 1D-5Y period change — NOT for the rest/resize re-park remounts, which must
  // stay instant). Bumped together by the period effect below.
  const [sweepKey, setSweepKey] = useState(0);
  const [playDraw, setPlayDraw] = useState(false);
  // Mirror of playDraw readable from callbacks that close over a stale render
  // (the ResizeObserver's debounced timer): lets them skip work WHILE the intro
  // draw is running without re-subscribing on every playDraw flip.
  const playDrawRef = useRef(false);
  playDrawRef.current = playDraw;
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

  // Replay the draw ONLY on a period change (1D-5Y) — NOT on entering the detail
  // page or on refresh (user 2026-05-30: "ไม่ต้องเล่น animation ตอนเข้าหน้า /
  // ตอนรีเฟรช ... ให้เล่นเฉพาะตอนเปลี่ยน 1D-5Y"). `firstPeriodRender` skips the
  // initial mount (and any refresh, which is a fresh mount), so the chart paints
  // statically on arrival; only an explicit period switch sets playDraw + bumps
  // sweepKey to run the sweep. (No IntersectionObserver / scroll-into-view
  // trigger anymore — that was the on-enter behavior the user asked to drop.)
  const firstPeriodRender = useRef(true);
  useEffect(() => {
    if (firstPeriodRender.current) {
      firstPeriodRender.current = false;
      return;
    }
    setPlayDraw(true);
    setSweepKey((k) => k + 1);
  }, [period]);

  // Drive the WHOLE intro from ONE rAF so the line reveal and the crosshair
  // share a single eased progress → they reach the right edge at the exact same
  // frame (the prior version let Recharts animate the area on its own timeline
  // while a separate rAF moved the crosshair, so they desynced — "ถึงขวาสุดไม่
  // พร้อมกัน" — and Recharts' per-frame React re-render made it stutter). Here
  // Recharts' own area animation is OFF (static path), and each frame we:
  //   1. ease progress p (fast→slow), x = ease(p)·width
  //   2. reveal the price line+fill by clipping ONLY `.recharts-area` to [0,x]
  //      (a sibling of `.recharts-xAxis`, so the axis + date labels stay PUT)
  //   3. place the crosshair line + dot at x; the dot y is computed by PURE MATH
  //      from chartData close values + the y-domain (NOT getPointAtLength — see
  //      the perf note below), so per-frame cost is O(1) → smooth even on a 5Y
  //      / 1260-point series on a throttled phone.
  // At p=1 the area clip is cleared (full line, flush-right dot via overflow-
  // visible) and the overlay fades, handing the rest crosshair to Recharts.
  //
  // PERF (2026-05-30 "app ค้างหนัก" fix): the previous version sampled the dot y
  // by walking the SVG path with getPointAtLength (121 samples × 16 binary-search
  // iters ≈ 2057 calls per sweep). getPointAtLength is O(path length) PER CALL —
  // on a 5Y curve (56 KB `d` string) that was ~47 s of main-thread work under a
  // 4-6× CPU throttle → the whole page froze. Computing y from the in-memory
  // close[] array instead is O(1) per point: zero path walks, zero freeze.
  const DRAW_MS = 650;
  useEffect(() => {
    if (!playDraw) return;
    if (typeof window === 'undefined') {
      setPlayDraw(false);
      return;
    }
    const reduce =
      window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const wrap = wrapperRef.current;
    const svg = overlaySvgRef.current;
    const line = overlayLineRef.current;
    const dot = overlayDotRef.current;
    if (reduce || !wrap || !svg || !line || !dot || chartData.length < 2) {
      setPlayDraw(false);
      return;
    }

    const clearAreaClip = () => {
      const a = wrap.querySelector('.recharts-area') as SVGGElement | null;
      if (a) a.style.clipPath = '';
    };

    const yLo = (yDomain as [number, number])[0];
    const yHi = (yDomain as [number, number])[1];
    const ySpan = yHi - yLo || 1;
    const easeOut = (t: number) => 1 - Math.pow(1 - t, 3); // fast→slow
    const closes = chartData.map((d) => d.close);
    const nSeg = closes.length - 1; // x maps [0,nSeg] across the plot width
    const firstClose = closes[0];
    // Nearest data index for an eased progress e∈[0,1] (for the date label,
    // which is discrete per point — the price itself is interpolated).
    const idxAt = (e: number) => Math.round(e * nSeg);
    // Imperative headline writer — used ONLY by the rAF (scrub uses hoverIndex
    // state + JSX). Mirrors the JSX formatting exactly so the handoff to React
    // on animation end is seamless. Guards each ref (the row may be absent when
    // periodChange is null, e.g. <2 points — but then the draw effect's early
    // chartData.length<2 bail prevents this from running anyway).
    const writeHeadline = (price: number, isoDate: string) => {
      const abs = price - firstClose;
      const pct = firstClose > 0 ? (abs / firstClose) * 100 : 0;
      const positive = abs >= 0;
      const sign = positive ? '+' : '';
      if (priceRef.current) priceRef.current.textContent = `$${price.toFixed(2)}`;
      if (changeAbsRef.current)
        changeAbsRef.current.textContent = `${sign}${abs.toFixed(2)}`;
      if (changePctRef.current)
        changePctRef.current.textContent = `(${sign}${pct.toFixed(2)}%)`;
      if (changeArrowRef.current)
        changeArrowRef.current.textContent = positive ? '↑' : '↓';
      // NB: the change-row COLOR is intentionally NOT touched here. React owns
      // the row's className (the `hv.positive ? upCls : downCls` template), and
      // those classes carry an OKLCH `!important` override in globals.css — an
      // imperative classList swap would both fight React's className reconcile
      // (stale/doubled class for a frame) and lose to the !important rule. During
      // the draw hoverIndex is null, so React already paints the row in the
      // period's overall direction; the animated NUMBERS count up within that
      // steady color (Google-Finance behavior — the headline color doesn't flip
      // per frame). The arrow textContent above is on its own single-node span,
      // so it's safe to drive imperatively.
      if (asOfRef.current)
        asOfRef.current.textContent = fmtDateLabel(isoDate);
    };
    let area: SVGGElement | null = null;
    let w = 1;
    let h = 1;
    // Real plot-area vertical extent (top y + height), read ONCE from the
    // curve's bounding box — NOT assumed from margin. Recharts' plot area is
    // inset from the surface by the X-axis height (~51 px) at the bottom + an
    // auto top pad (~29 px), so a naive [marginTop, surfaceHeight] map put the
    // crosshair dot ~27 px off the line. getBBox is O(1) (no path walk like
    // getPointAtLength) so it's cheap to read once. closeToY maps a price
    // through the SAME linear y-scale Recharts uses over [plotTop, plotTop+plotH].
    let plotTop = 0;
    let plotH = 1;
    const closeToY = (close: number) =>
      plotTop + (1 - (close - yLo) / ySpan) * plotH;
    let t0 = 0;
    const startedAt = performance.now();

    // One-time prep: grab the area node + surface size + the real plot extent
    // from the curve bbox. Returns false until Recharts has painted the curve.
    const prep = (): boolean => {
      area = wrap.querySelector('.recharts-area') as SVGGElement | null;
      const surf = wrap.querySelector(
        '.recharts-surface',
      ) as SVGSVGElement | null;
      const curve = wrap.querySelector(
        '.recharts-area-curve',
      ) as SVGPathElement | null;
      if (!area || !surf || !curve) return false;
      const rect = surf.getBoundingClientRect();
      w = rect.width || 1;
      h = rect.height || 1;
      let bb: DOMRect;
      try {
        bb = curve.getBBox();
      } catch {
        return false; // not laid out yet
      }
      if (bb.height === 0 || bb.width === 0) return false;
      // The curve bbox spans the visible price range, but the y-DOMAIN is padded
      // ±10% beyond [min,max] (see yDomain), so the plot area is taller than the
      // bbox. Recover the full plot extent: the bbox top/bottom correspond to the
      // domain's data-max/data-min, which sit 10%/(120%) in from the padded
      // domain edges. plotH = bbox.h / (dataSpan/paddedSpan). Simpler + robust:
      // derive px-per-price from the bbox (price min→max over bbox.height) and
      // extend to the padded domain.
      const dataMax = Math.max(...closes);
      const dataMin = Math.min(...closes);
      const dataSpan = dataMax - dataMin || 1;
      const pxPerPrice = bb.height / dataSpan; // px per $ on the real plot
      plotH = ySpan * pxPerPrice; // full padded-domain height in px
      // bbox.y is where dataMax sits; that price is (yHi - dataMax) below the
      // padded-domain top → plotTop = bbox.y - (yHi - dataMax)*pxPerPrice.
      plotTop = bb.y - (yHi - dataMax) * pxPerPrice;
      // hide the line/fill immediately so it reveals from x=0 (no full-flash).
      // -20px vertical insets keep the stroke top/bottom from being clipped.
      area.style.clipPath = 'inset(-20px 100% -20px 0)';
      return true;
    };

    const tick = (now: number) => {
      if (t0 === 0) {
        if (now - startedAt > 500) {
          // area never painted — bail to the static chart
          clearAreaClip();
          setPlayDraw(false);
          return;
        }
        if (!prep()) {
          drawRafRef.current = requestAnimationFrame(tick);
          return;
        }
        t0 = now;
      }
      const p = Math.min(1, (now - t0) / DRAW_MS);
      const e = easeOut(p);
      const x = e * w;
      // reveal the line+fill up to x (clip the part to the RIGHT of x)
      if (area) area.style.clipPath = `inset(-20px ${Math.max(0, w - x)}px -20px 0)`;
      // crosshair dot y — interpolate the close[] array at the swept fraction,
      // then map through the y-scale. plot area height = h - marginTop.
      const fseg = e * nSeg;
      const s0 = Math.min(nSeg - 1, Math.floor(fseg));
      const frac = fseg - s0;
      const close = closes[s0] + (closes[s0 + 1] - closes[s0]) * frac;
      const y = closeToY(close);
      // Span the crosshair line over the PLOT AREA only ([plotTop, plotTop+plotH]),
      // NOT the full surface — the surface includes ~29px top pad + the ~51px
      // X-axis band below, so y1=0/y2=h overflowed the line above the chart top
      // and below into the date axis (user 2026-05-30 "เส้นล้นออกด้านบนและล่าง").
      line.setAttribute('x1', String(x));
      line.setAttribute('x2', String(x));
      line.setAttribute('y1', String(plotTop));
      line.setAttribute('y2', String(plotTop + plotH));
      dot.setAttribute('cx', String(x));
      dot.setAttribute('cy', String(y));
      svg.style.opacity = '1';
      // Drive the HEADLINE (price / change / date) to the swept point too, so it
      // counts up alongside the crosshair. IMPERATIVE writes (refs, no setState)
      // — a per-frame setState here would re-render Recharts 60×/s and re-freeze
      // the page (the "ค้างหนัก" trap). The change is measured from the window's
      // first close (same convention as the static headline). On the final frame
      // the end-of-draw setPlayDraw(false) re-render restores the same latest
      // values via JSX, so there's no visible snap.
      writeHeadline(close, chartData[idxAt(e)].date);
      if (p < 1) {
        drawRafRef.current = requestAnimationFrame(tick);
      } else {
        // full reveal: drop the clip (overflow-visible flush-right dot shows),
        // hide the overlay, hand the rest crosshair to Recharts' parked cursor.
        clearAreaClip();
        svg.style.opacity = '0';
        drawRafRef.current = null;
        setPlayDraw(false);
      }
    };
    drawRafRef.current = requestAnimationFrame(tick);
    return () => {
      if (drawRafRef.current !== null) cancelAnimationFrame(drawRafRef.current);
      // if interrupted mid-draw (e.g. a period switch), never leave the line
      // stuck hidden — clear the clip on the (old) area.
      clearAreaClip();
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
    // Downsample after slicing so the path Recharts builds stays small. A 5Y
    // window is ~1260 daily points → a ~56 KB SVG `d` string, whose ONE-TIME
    // render is a ~380 ms main-thread task on a throttled phone (the "เปิดหน้า
    // ค้างหนัก" report). At a ~360-700 px chart width there are far more points
    // than pixels, so capping to MAX_POINTS (evenly, always keeping the last
    // point so the latest price + flush-right crosshair are exact) is visually
    // lossless but cuts the path ~5× → no freeze. Shorter windows (≤ MAX_POINTS)
    // pass through untouched.
    () => downsample(sliceByPeriod(fullChartData, period), 260),
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

  // Headline values at an arbitrary point index — the price, the change vs the
  // window's FIRST close (Google-Finance convention: the change is always
  // measured from the window start, not from the previous point), the change %,
  // direction, and the date. Used to render the headline at the crosshair
  // position both on scrub (via hoverIndex state) and during the animation (via
  // the imperative writer below). Pure — no side effects.
  const headlineAt = (idx: number) => {
    const n = chartData.length;
    if (n === 0) return null;
    const i = Math.max(0, Math.min(n - 1, idx));
    const price = chartData[i].close;
    const first = chartData[0].close;
    const abs = price - first;
    const pct = first > 0 ? (abs / first) * 100 : 0;
    return {
      price,
      abs,
      pct,
      positive: abs >= 0,
      date: chartData[i].date,
    };
  };

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
      t = setTimeout(() => {
        // Don't bump layoutKey WHILE the intro draw is running — a re-park
        // remount mid-draw would reconcile the headline spans back to latest for
        // ~1 frame (fighting the rAF's imperative writes → a flicker). The draw
        // is ≤650ms; the re-park can wait for it to finish (the next genuine
        // resize, or the rest state, re-parks correctly anyway).
        if (playDrawRef.current) return;
        setLayoutKey((k) => k + 1);
      }, 300);
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
  // Tooltip / headline date label — "Mon DD, YYYY". Delegates to the
  // module-level fmtDateLabel so the rAF headline writer (which is outside this
  // render scope) formats dates identically.
  const formatTooltipLabel = (raw: string) => fmtDateLabel(raw);
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
      {chartData.length > 0 && (() => {
        // Headline reflects the crosshair: the scrubbed point (hoverIndex) when
        // dragging, else the latest. During the animation the rAF overwrites
        // these spans imperatively (hoverIndex stays null), then the end-of-draw
        // re-render restores the latest. The change row is colored by direction;
        // when scrubbing we show the date (PERIOD_LABEL is only meaningful for
        // the full window = latest), else the period label.
        const lastIdx = chartData.length - 1;
        const di = hoverIndex ?? lastIdx;
        const hv = headlineAt(di) ?? {
          price: chartData[lastIdx].close,
          abs: 0,
          pct: 0,
          positive: true,
          date: chartData[lastIdx].date,
        };
        const scrubbing = hoverIndex !== null;
        const upCls = 'text-emerald-700 dark:text-emerald-300';
        const downCls = 'text-rose-600 dark:text-rose-400';
        return (
          <div className="flex flex-col gap-1">
            <div className="flex items-baseline gap-2">
              {/* Each imperatively-written span (priceRef / changeAbsRef /
                  changePctRef / changeArrowRef / asOfRef) MUST hold exactly ONE
                  text node — a single template-literal child. The rAF does
                  `ref.textContent = …` every frame; textContent replaces ALL
                  children with one text node. If the JSX gave the span MULTIPLE
                  children (e.g. literal "$" + an expression = two text nodes),
                  the imperative write collapses them to one, but React's vdom
                  still believes there are two — so the next re-render (a scrub
                  setHoverIndex) reconciles against a detached text node: the
                  scrub silently stops updating ("เลื่อนได้บ้างไม่ได้บ้าง") and a
                  structural reconcile (insertBefore/removeChild on the missing
                  node) throws "app error". One text node per written span keeps
                  React's vdom and the live DOM in agreement (2026-05-30 crash
                  fix). */}
              <span
                ref={priceRef}
                className="font-mono text-2xl font-semibold tabular-nums leading-none text-slate-900 dark:text-slate-100"
              >
                {`$${hv.price.toFixed(2)}`}
              </span>
              <span className="text-xs font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
                USD
              </span>
            </div>
            {periodChange && (
              <div
                ref={changeRowRef}
                className={`flex flex-wrap items-baseline gap-1.5 text-sm ${hv.positive ? upCls : downCls}`}
              >
                <span ref={changeAbsRef} className="font-mono font-semibold tabular-nums">
                  {`${hv.positive ? '+' : ''}${hv.abs.toFixed(2)}`}
                </span>
                <span ref={changePctRef} className="font-mono tabular-nums">
                  {`(${hv.positive ? '+' : ''}${hv.pct.toFixed(2)}%)`}
                </span>
                <span ref={changeArrowRef}>{hv.positive ? '↑' : '↓'}</span>
                {/* Hide the period label ("past year" etc.) WHILE scrubbing — at
                    a scrubbed point the change is measured from the window start
                    to THAT point, so "past year" would mislabel it. At rest /
                    during the animation it correctly describes the full window. */}
                {!scrubbing && (
                  <span className="text-xs font-normal text-slate-500 dark:text-slate-400">
                    {PERIOD_LABEL[period]}
                  </span>
                )}
              </div>
            )}
            <div className="text-sm tabular-nums text-slate-900 dark:text-slate-100">
              as of <span ref={asOfRef}>{formatTooltipLabel(hv.date)}</span>
            </div>
          </div>
        );
      })()}

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
        onPointerUp={() => {
          setHoverIndex(null);
          setRestKey((k) => k + 1);
        }}
        onClick={() => {
          setHoverIndex(null);
          setRestKey((k) => k + 1);
        }}
        onPointerCancel={() => {
          setHoverIndex(null);
          setRestKey((k) => k + 1);
        }}
        onPointerLeave={(e) => {
          if (e.pointerType !== 'touch') {
            setHoverIndex(null);
            setRestKey((k) => k + 1);
          }
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
            onMouseMove={(state: { activeTooltipIndex?: number | null }) => {
              // Track the scrubbed point so the headline (price/change/date)
              // follows the crosshair the user drags. Ignored during the intro
              // animation — the rAF owns the headline then (and the Recharts
              // cursor is suppressed). activeTooltipIndex is null when the
              // pointer is off the plot.
              if (playDraw) return;
              const idx = state?.activeTooltipIndex;
              setHoverIndex(
                typeof idx === 'number' && idx >= 0 ? idx : null,
              );
            }}
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
              // Recharts' own draw animation is OFF — the unified intro rAF
              // (above) reveals the line by clipping `.recharts-area`, in
              // lockstep with the crosshair, so the two never desync. Keeping
              // Recharts static also avoids its per-frame React re-render
              // (the stutter source).
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

// Module-level date formatter: "YYYY-MM-DD" → "Mon DD, YYYY". Shared by the
// in-render formatTooltipLabel AND the rAF headline writer (which runs outside
// render scope), so both format the crosshair date identically.
const _MONTH_ABBR = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];
export function fmtDateLabel(raw: string): string {
  const monthIdx = Number(raw.slice(5, 7)) - 1;
  const day = Number(raw.slice(8, 10));
  const year = raw.slice(0, 4);
  const mon = _MONTH_ABBR[monthIdx];
  if (!mon || Number.isNaN(day)) return raw;
  return `${mon} ${day}, ${year}`;
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
// Cap a point series to at most `maxPoints` by even stride sampling, ALWAYS
// keeping the first and last points (so the visible price range + the latest
// price / flush-right crosshair stay exact). Series already ≤ maxPoints pass
// through unchanged. Purely for render cost — at typical chart widths there are
// far more daily points than pixels, so the dropped points are sub-pixel.
export function downsample(
  points: ChartPoint[],
  maxPoints: number,
): ChartPoint[] {
  const n = points.length;
  if (n <= maxPoints || maxPoints < 2) return points;
  const out: ChartPoint[] = [];
  const stride = (n - 1) / (maxPoints - 1);
  for (let i = 0; i < maxPoints - 1; i += 1) {
    out.push(points[Math.round(i * stride)]);
  }
  out.push(points[n - 1]); // exact last point
  return out;
}

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
