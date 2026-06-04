import type { Metadata } from 'next';

import { ComingSoon } from '@/components/ComingSoon';

export const metadata: Metadata = {
  title: 'Analysis · QuantRank',
  description:
    'Deeper analysis of the QuantRank universe — score distributions, factor breakdowns, and methodology. Coming soon.',
};

export default function AnalysisPage() {
  return (
    <ComingSoon
      title="Analysis"
      lead="Coming soon"
      detail="Deeper analysis — composite-score distributions, per-pillar breakdowns, and the academic methodology behind the defense layer — is on the way. For now, explore the full ranking and the per-sector view."
    />
  );
}
