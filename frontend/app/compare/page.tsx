import type { Metadata } from 'next';

import CompareView from '@/components/CompareView';
import { getRankings } from '@/lib/data';

export const metadata: Metadata = {
  title: 'Compare stocks · QuantRank',
  description:
    'Compare up to four S&P 500 names side by side — composite score, the eight scoring pillars, fair-price margin of safety, and the defense-layer risk flags.',
};

// Static route. The full `StockSummary[]` is build-imported here (the SAME
// `getRankings()` the home page uses — the focused compare set lives entirely on
// rankings.json, so no per-stock fetch / no loading waterfall) and handed to the
// client view, which reads the `?compare=` selection from the URL at runtime.
export default function ComparePage() {
  return <CompareView all={getRankings()} />;
}
