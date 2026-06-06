'use client';

import { useEffect, useState } from 'react';

import type { StockHistory } from '@/lib/types';

// Big price-trend chart for the watchlist cards (Jitta-style). Draws the
// trailing ~1y of closes as a calm slate area with a DASHED horizontal
// reference line at the fair-value estimate (the 6-method ensemble median).
// Price below the line = undervalued (emerald dashed line); above = overvalued
// (rose) — the same "under / over the fair line" read the MoS % states in words.
// Lightweight inline SVG (NO Recharts) so N cards stay cheap; fetches the same
// /data/stocks/history/<T>.json the detail chart + CurrentPriceLine use.
// Decorative (aria-hidden): the price + MoS chip carry the data for SR.

const WINDOW = 252; // ~1 trading year of sessions
const VIEW_W = 100;
const VIEW_H = 48;
const PAD = 3;

const cache = new Map<string, number[]>();

export function WatchlistChart({
  ticker,
  fairPrice,
  currentPrice,
}: {
  ticker: string;
  fairPrice: number | null;
  currentPrice: number;
}) {
  const [closes, setCloses] = useState<number[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const cached = cache.get(ticker);
    if (cached) {
      setCloses(cached);
      return;
    }
    let cancelled = false;
    const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? '';
    fetch(`${basePath}/data/stocks/history/${ticker}.json`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<StockHistory>;
      })
      .then((json) => {
        if (cancelled) return;
        const series = (json.closes ?? [])
          .filter((c): c is number => c != null)
          .slice(-WINDOW);
        cache.set(ticker, series);
        setCloses(series);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  if (closes == null && !failed) {
    return (
      <div
        aria-hidden="true"
        className="h-28 w-full animate-pulse rounded bg-slate-100 dark:bg-slate-800"
      />
    );
  }
  if (failed || closes == null || closes.length < 2) {
    return (
      <div
        aria-hidden="true"
        className="flex h-28 w-full items-center justify-center rounded border border-dashed border-slate-200 text-[0.6875rem] text-slate-500 dark:border-slate-800 dark:text-slate-400"
      >
        price history unavailable
      </div>
    );
  }

  // The y-scale spans the closes AND the fair-value level so the dashed line is
  // always on-canvas even when fair value sits outside the recent price range.
  const lo = Math.min(...closes, fairPrice ?? Infinity);
  const hi = Math.max(...closes, fairPrice ?? -Infinity);
  const span = hi - lo || 1; // guard a perfectly flat series
  const n = closes.length;
  const yOf = (v: number) => PAD + (1 - (v - lo) / span) * (VIEW_H - 2 * PAD);
  const pts = closes.map(
    (c, i) => `${((i / (n - 1)) * VIEW_W).toFixed(2)} ${yOf(c).toFixed(2)}`,
  );
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p}`).join(' ');
  const area = `${line} L${VIEW_W} ${VIEW_H} L0 ${VIEW_H} Z`;

  const undervalued = fairPrice != null && currentPrice <= fairPrice;
  const fairY = fairPrice != null ? yOf(fairPrice) : null;

  return (
    <svg
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      preserveAspectRatio="none"
      className="h-28 w-full"
      aria-hidden="true"
    >
      <path d={area} stroke="none" className="fill-slate-400/10 dark:fill-slate-500/10" />
      <path
        d={line}
        fill="none"
        strokeWidth={1.25}
        vectorEffect="non-scaling-stroke"
        strokeLinejoin="round"
        strokeLinecap="round"
        className="stroke-slate-500 dark:stroke-slate-400"
      />
      {fairY != null && (
        <line
          x1="0"
          y1={fairY.toFixed(2)}
          x2={VIEW_W}
          y2={fairY.toFixed(2)}
          strokeWidth={1}
          strokeDasharray="3 3"
          vectorEffect="non-scaling-stroke"
          className={
            undervalued
              ? 'stroke-emerald-500 dark:stroke-emerald-400'
              : 'stroke-rose-400 dark:stroke-rose-300'
          }
        />
      )}
    </svg>
  );
}
