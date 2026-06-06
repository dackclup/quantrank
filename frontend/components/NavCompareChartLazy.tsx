'use client';

import dynamic from 'next/dynamic';

// Type-only import (erased at compile time) — keeps Recharts out of this
// wrapper's bundle so the lazy split holds. Mirrors PriceHistoryChartLazy.
import type { Props } from './NavCompareChart';

// Code-split Recharts into an async chunk (it is the dominant dependency of this
// chart) behind a fixed-height skeleton, so the home page's initial JS stays
// lean. `next/dynamic` with `ssr: false` must live in a Client Component.

function ChartSkeleton() {
  return (
    <div className="space-y-3" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading performance chart…</span>
      <div className="h-72 w-full animate-shimmer rounded-sm" />
    </div>
  );
}

const NavCompareChartImpl = dynamic(
  () => import('./NavCompareChart').then((m) => m.NavCompareChart),
  { ssr: false, loading: () => <ChartSkeleton /> },
);

export function NavCompareChartLazy(props: Props) {
  return <NavCompareChartImpl {...props} />;
}
