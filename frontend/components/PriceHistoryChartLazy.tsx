'use client';

import dynamic from 'next/dynamic';

// Type-only import (erased at compile time) — does NOT pull PriceHistoryChart
// or Recharts into this wrapper's bundle, so the lazy split is preserved.
import type { Props } from './PriceHistoryChart';

// Lazy boundary for the price chart so Recharts (the dominant chunk on the
// stock-detail First Load JS) code-splits into an async chunk instead of the
// initial bundle ($impeccable optimize, audit P3). Safe + near-invisible:
// PriceHistoryChart is ALREADY a `'use client'` leaf that fetches its history
// JSON on mount and renders a shimmer skeleton until then (see its header
// comment, "keeps these out of the SSR bundle"), so today's static HTML already
// shows a skeleton, not the chart. `ssr: false` defers the Recharts JS the same
// way, behind an IDENTICAL skeleton (same shimmer stack + `h-64`) — zero CLS,
// and no skeleton the user wasn't already seeing. `next/dynamic` with
// `ssr: false` must live in a Client Component, hence this thin wrapper, which
// the Server Component page imports in place of the chart.

function ChartSkeleton() {
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

const PriceHistoryChartImpl = dynamic(
  () => import('./PriceHistoryChart').then((m) => m.PriceHistoryChart),
  { ssr: false, loading: () => <ChartSkeleton /> },
);

export function PriceHistoryChartLazy(props: Props) {
  return <PriceHistoryChartImpl {...props} />;
}
