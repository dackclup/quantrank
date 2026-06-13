import type { Metadata } from 'next';

import { getDecayReport, getMetadata } from '@/lib/data';
import { DecayMonitorCard } from '@/components/DecayMonitorCard';

export const metadata: Metadata = {
  title: 'Analysis · QuantRank',
  description:
    'Methodology transparency — IC-decay monitor, factor diagnostics, and the academic evidence behind the QuantRank composite score.',
};

// Server Component: reads decay_report.json + metadata at build time.
// Follows the build-time-data rule: data is resolved here in the Server
// Component and passed as props — never fs-imported into a 'use client'
// component. `getDecayReport()` uses a static import (the file is always
// emitted by the cron and is small); `getMetadata()` uses the same pattern.
export default function AnalysisPage() {
  const meta = getMetadata();
  const report = getDecayReport();

  return (
    <section className="space-y-4" aria-label="Analysis">
      <header>
        <h1 className="font-slab text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
          Analysis
        </h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Methodology transparency — factor diagnostics and the academic evidence behind the QuantRank composite score.
        </p>
      </header>

      {/* IC-decay monitor — gated on metadata.decay_report_url being non-null.
          null means QR_SKIP_DECAY_MONITOR was set, the monitor degraded, or the
          output predates this field. In that case the section is omitted entirely
          (no empty card, no false "healthy" state). */}
      {meta.decay_report_url != null && (
        <DecayMonitorCard report={report} />
      )}
    </section>
  );
}
