import type { Metadata } from 'next';

import { WatchlistView } from '@/components/WatchlistView';
import { getRankings } from '@/lib/data';

export const metadata: Metadata = {
  title: 'Watchlist · QuantRank',
  description:
    'Your personal watchlist of QuantRank names — save tickers and track their composite scores. Lives entirely in your browser.',
};

// Server Component: reads the full ranking snapshot at build time (the
// build-time data rule — lib/data.ts must never be imported by a client
// component) and hands it to the client WatchlistView, which filters it to the
// tickers the visitor has starred into browser localStorage. The saved set
// never leaves the browser; the server only ships the public ranking rows
// (the same payload the /ranking page already sends).
export default function PortfolioPage() {
  const rankings = getRankings();
  return <WatchlistView rankings={rankings} />;
}
