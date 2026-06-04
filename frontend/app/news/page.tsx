import type { Metadata } from 'next';

import { ComingSoon } from '@/components/ComingSoon';

export const metadata: Metadata = {
  title: 'News · QuantRank',
  description:
    'Market news and headlines for the QuantRank universe. Coming soon.',
};

export default function NewsPage() {
  return (
    <ComingSoon
      title="News"
      lead="Coming soon"
      detail="Market news and headlines for the names in the QuantRank universe are on the way. For now, explore the full ranking and the per-stock detail pages."
    />
  );
}
