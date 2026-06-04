import type { Metadata } from 'next';

import { ComingSoon } from '@/components/ComingSoon';

export const metadata: Metadata = {
  title: 'Portfolio · QuantRank',
  description:
    'A personal watchlist of QuantRank names — save tickers and track their composite scores. Coming soon.',
};

export default function PortfolioPage() {
  return (
    <ComingSoon
      title="Portfolio"
      lead="Coming soon"
      detail="A personal watchlist — save the names you're tracking and watch their composite scores and prices move week to week — is coming. It'll live entirely in your browser (no account, no sign-in needed)."
    />
  );
}
