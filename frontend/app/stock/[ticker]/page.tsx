import Link from 'next/link';
import { notFound } from 'next/navigation';

import RawMetricsTable from '@/components/RawMetricsTable';
import { getStockDetail, listAvailableTickers } from '@/lib/data';

export const dynamicParams = false;

export async function generateStaticParams() {
  return listAvailableTickers().map((ticker) => ({ ticker }));
}

function scoreColorClasses(score: number): string {
  if (score >= 80) return 'bg-emerald-100 text-emerald-800 ring-emerald-200';
  if (score >= 60) return 'bg-lime-100 text-lime-800 ring-lime-200';
  if (score >= 40) return 'bg-amber-100 text-amber-800 ring-amber-200';
  if (score >= 20) return 'bg-orange-100 text-orange-800 ring-orange-200';
  return 'bg-red-100 text-red-800 ring-red-200';
}

function filingLagBadgeClasses(days: number | null): string {
  if (days === null) return 'bg-slate-100 text-slate-600 ring-slate-200';
  if (days < 60) return 'bg-emerald-50 text-emerald-700 ring-emerald-200';
  if (days < 180) return 'bg-amber-50 text-amber-700 ring-amber-200';
  return 'bg-red-50 text-red-700 ring-red-200';
}

function formatPrice(p: number): string {
  return p.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 2,
  });
}

export default function StockDetailPage({
  params,
}: {
  params: { ticker: string };
}) {
  const { ticker } = params;
  const detail = getStockDetail(ticker);
  if (!detail) {
    notFound();
  }

  const filingLag = detail.data_quality.filing_lag_days;
  const missingCount = detail.data_quality.missing_metrics.length;

  return (
    <article className="space-y-8">
      <Link
        href="/"
        className="inline-block text-sm text-slate-500 hover:text-slate-900"
      >
        ← Back to ranking
      </Link>

      <header className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-baseline gap-3">
            <h1 className="font-mono text-3xl font-bold tracking-tight sm:text-4xl">
              {detail.ticker}
            </h1>
            <span className="text-sm text-slate-500">#{detail.rank}</span>
          </div>
          <p className="mt-1 text-lg text-slate-700">{detail.name}</p>
          <p className="text-sm text-slate-500">
            {detail.sector}
            {detail.industry && <> · {detail.industry}</>}
          </p>
        </div>
        <div className="flex flex-col items-start gap-2 sm:items-end">
          <span
            className={`inline-flex items-center justify-center rounded-full px-3 py-1 text-base font-semibold tabular-nums ring-1 ring-inset ${scoreColorClasses(
              detail.composite_score,
            )}`}
          >
            Score {detail.composite_score.toFixed(1)}
          </span>
          <span className="text-sm tabular-nums text-slate-700">
            {formatPrice(detail.current_price)}
          </span>
        </div>
      </header>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
          Raw fundamentals (SEC EDGAR)
        </h2>
        <RawMetricsTable metrics={detail.raw_metrics} />
        <p className="mt-2 text-xs text-slate-400">
          TTM = trailing twelve months. Balance sheet items are point-in-time
          (latest filing).
        </p>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
          Data quality
        </h2>
        <dl className="grid grid-cols-1 gap-y-2 text-sm sm:grid-cols-2">
          <dt className="text-slate-500">Latest filed date</dt>
          <dd className="font-mono text-slate-900">
            {detail.data_quality.latest_filed_date ?? 'N/A'}
          </dd>
          <dt className="text-slate-500">Latest period end</dt>
          <dd className="font-mono text-slate-900">
            {detail.data_quality.latest_period_end ?? 'N/A'}
          </dd>
          <dt className="text-slate-500">Filing lag</dt>
          <dd>
            <span
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${filingLagBadgeClasses(
                filingLag,
              )}`}
            >
              {filingLag === null ? 'N/A' : `${filingLag} days`}
            </span>
          </dd>
          <dt className="text-slate-500">Missing metrics</dt>
          <dd className="text-slate-900">
            {missingCount === 0 ? (
              'none'
            ) : (
              <span className="text-amber-700">
                {missingCount}
                {missingCount > 0 && (
                  <span className="ml-2 text-xs text-slate-500">
                    ({detail.data_quality.missing_metrics.join(', ')})
                  </span>
                )}
              </span>
            )}
          </dd>
        </dl>
      </section>

      <p className="text-xs text-slate-400">
        Phase 2 — composite is still momentum-only; raw fundamentals shown
        above are sourced from SEC EDGAR. Real fundamental pillars land in
        Phase 3.
      </p>
    </article>
  );
}
