'use client';

import { useEffect, useState } from 'react';

import type { StockHistory } from '@/lib/types';

// Mini price-trend sparkline for the watchlist rows. Fetches the same per-ticker
// history JSON the detail-page chart uses (`/data/stocks/history/<T>.json`) and
// draws a lightweight inline-SVG path from the trailing ~90 closes — NO Recharts,
// so N rows don't pull the chart library into the /portfolio bundle. Sign-aware
// MUTED color (emerald if the window closed up, rose if down) per the "calm,
// never a trading floor" register — not a hot dopamine line. Decorative
// (`aria-hidden`): the price + %-change chip beside it carry the data for SR.

const WINDOW = 90; // trailing sessions drawn
const VIEW_W = 100;
const VIEW_H = 32;
const PAD = 2; // viewBox top/bottom padding so the stroke never clips

// Module-level cache so a re-mount (navigate away + back, re-filter) doesn't
// refetch a file already loaded this session.
const cache = new Map<string, number[]>();

export function Sparkline({ ticker }: { ticker: string }) {
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

  // Loading — a faint pulse bar that holds the row height steady (no layout
  // shift when the chart arrives).
  if (closes == null && !failed) {
    return (
      <div
        aria-hidden="true"
        className="h-9 w-full animate-pulse rounded bg-slate-100 dark:bg-slate-800"
      />
    );
  }

  // Fetch failed or too few points to draw a trend — hold the space, draw nothing.
  if (failed || closes == null || closes.length < 2) {
    return <div aria-hidden="true" className="h-9 w-full" />;
  }

  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const span = max - min || 1; // guard a perfectly flat line
  const n = closes.length;
  const pts = closes.map((c, i) => {
    const x = (i / (n - 1)) * VIEW_W;
    const y = PAD + (1 - (c - min) / span) * (VIEW_H - 2 * PAD);
    return `${x.toFixed(2)} ${y.toFixed(2)}`;
  });
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p}`).join(' ');
  const area = `${line} L${VIEW_W} ${VIEW_H} L0 ${VIEW_H} Z`;
  const up = closes[n - 1] >= closes[0];

  return (
    <svg
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      preserveAspectRatio="none"
      className="h-9 w-full"
      aria-hidden="true"
    >
      <path
        d={area}
        stroke="none"
        className={up ? 'fill-emerald-500/10 dark:fill-emerald-400/10' : 'fill-rose-500/10 dark:fill-rose-400/10'}
      />
      <path
        d={line}
        fill="none"
        strokeWidth={1.5}
        vectorEffect="non-scaling-stroke"
        strokeLinejoin="round"
        strokeLinecap="round"
        className={up ? 'stroke-emerald-600 dark:stroke-emerald-400' : 'stroke-rose-500 dark:stroke-rose-400'}
      />
    </svg>
  );
}
