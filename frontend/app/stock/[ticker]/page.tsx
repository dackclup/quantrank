import Link from 'next/link';

import FairPriceCard from '@/components/FairPriceCard';
import { FairPriceBarChart } from '@/components/FairPriceBarChart';
import { MoSCell } from '@/components/MoSCell';
import { PillarRadarChart } from '@/components/PillarRadarChart';
import { PriceHistoryChart } from '@/components/PriceHistoryChart';
import RawMetricsTable from '@/components/RawMetricsTable';
import { ScoreBadge } from '@/components/ScoreBadge';
import { RecommendationBadge } from '@/components/RecommendationBadge';
import { SectorChip } from '@/components/SectorChip';
import { StockLogo } from '@/components/StockLogo';
import { Tier2EventCard } from '@/components/Tier2EventCard';
import { getStockDetail, listTickersForStaticBuild } from '@/lib/data';
import { filingLagBadgeClasses } from '@/lib/visual';

export const dynamicParams = false;

export async function generateStaticParams() {
  return listTickersForStaticBuild().map((ticker) => ({ ticker }));
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
    return (
      <article className="space-y-6">
        <Link
          href="/"
          className="inline-block text-sm text-slate-500 hover:text-slate-900"
        >
          ← Back to ranking
        </Link>
        <header>
          <h1 className="font-mono text-3xl font-bold tracking-tight sm:text-4xl">
            {ticker}
          </h1>
        </header>
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900">
          <p className="font-medium">Detail data pending</p>
          <p className="mt-1">
            The latest weekly compute hasn&rsquo;t produced data for{' '}
            <span className="font-mono">{ticker}</span> yet. Trigger
            <span className="ml-1 font-mono">compute-rankings.yml</span> from
            the GitHub Actions tab; the detail page will populate after the
            next deploy.
          </p>
        </div>
      </article>
    );
  }

  const filingLag = detail.data_quality.filing_lag_days;
  const missingCount = detail.data_quality.missing_metrics.length;
  const mosPct = detail.fair_price?.mos_pct ?? null;

  return (
    <article className="space-y-8">
      <Link
        href="/"
        className="inline-block text-sm text-slate-500 hover:text-slate-900"
      >
        ← Back to ranking
      </Link>

      {/* Hero header card — new layout from QuantRank.html design:
          rank badge + sector chip on top row, big mono ticker, serif
          company name, radial-gauge ScoreBadge + price + MoSCell on
          the right side. */}
      <header className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="inline-flex items-center rounded-md bg-slate-100 px-1.5 py-0.5 font-mono font-medium text-slate-600">
                #{detail.rank}
              </span>
              <SectorChip sector={detail.sector} />
              {detail.industry && (
                <span className="truncate text-slate-400">· {detail.industry}</span>
              )}
            </div>
            <h1 className="mt-2 flex flex-wrap items-center gap-3">
              <StockLogo ticker={detail.ticker} size={48} />
              <span className="font-mono text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl">
                {detail.ticker}
              </span>
              <RecommendationBadge recommendation={detail.recommendation} size="md" />
            </h1>
            <p className="mt-1 text-2xl text-slate-700 sm:text-3xl">
              {detail.name}
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:items-end">
            <ScoreBadge score={detail.composite_score} size="lg" />
            <div className="flex gap-6 sm:justify-end">
              <div className="flex flex-col sm:items-end">
                <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
                  Price
                </span>
                <span className="font-mono text-lg font-semibold tabular-nums text-slate-900">
                  {formatPrice(detail.current_price)}
                </span>
              </div>
              <div className="flex flex-col sm:items-end">
                <span className="text-[10px] font-medium uppercase tracking-wider text-slate-500">
                  Margin of safety
                </span>
                <div className="mt-0.5">
                  <MoSCell mos={mosPct} align="right" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </header>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">
          Price (1y)
        </h2>
        {detail.has_history ? (
          <PriceHistoryChart ticker={detail.ticker} />
        ) : (
          <div className="flex h-64 items-center justify-center rounded-lg border border-slate-200 bg-white text-sm text-slate-400">
            No price history available
          </div>
        )}
      </section>

      <Tier2EventCard
        tier2_events={detail.tier2_events}
        ticker={detail.ticker}
      />

      <FairPriceBarChart
        fair_price={detail.fair_price}
        current_price={detail.current_price}
        ticker={detail.ticker}
      />

      <FairPriceCard
        ensemble={detail.fair_price}
        currentPrice={detail.current_price}
        warnings={detail.valuation_warnings}
        tangibleBookValue={detail.tangible_book_value}
      />

      <PillarRadarChart
        pillars={detail.pillar_scores}
        ticker={detail.ticker}
        baseline={detail.pillar_baseline}
      />

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
        Phase 3c — composite is the 8-pillar weighted score over quality,
        value, growth, momentum, health, profitability, technical, and risk.
        Sentiment + ML pillars land in Phases 5-6; until then their weight
        redistributes pro-rata. Fair price is the median of 6 valuation
        methods (Graham, P/E / P/B / EV-EBITDA multiples, RIM, DCF) with
        outliers above 5× current price excluded from the max. Risk-overlay
        flags annotate only — they suppress the entered-top-5 badge but do
        not modify the composite.
      </p>
    </article>
  );
}
