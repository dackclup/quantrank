import type { Metadata } from 'next';

import { RankingView } from '@/components/RankingView';
import { getMetadata, getRankings } from '@/lib/data';

// generateMetadata runs at build time (static export) so getMetadata() is safe.
// The SEO description reflects the total universe size (all cohorts combined).
// Per-tab h1 / count are rendered client-side by RankingView.
export function generateMetadata(): Metadata {
  const meta = getMetadata();
  return {
    title: 'Ranking · QuantRank',
    description: `US equity rankings — ${meta.universe_size} names across S&P 500${
      meta.universe_size > 502 ? ' and S&P MidCap 400' : ''
    }, scored by an 8-pillar composite, searchable and sortable.`,
  };
}

// Server Component: loads all rows at build time and passes them to the
// interactive RankingView client wrapper. No fs-import occurs inside any
// 'use client' component (build-time-data rule).
export default function RankingPage() {
  const rankings = getRankings();
  const meta = getMetadata();

  return <RankingView data={rankings} meta={meta} />;
}
