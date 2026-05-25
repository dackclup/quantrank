import Link from 'next/link';

import FairPriceCard from '@/components/FairPriceCard';
import { CurrentPriceLine } from '@/components/CurrentPriceLine';
import { FairPriceBarChart } from '@/components/FairPriceBarChart';
import { ManipulationRiskCard } from '@/components/ManipulationRiskCard';
import { MoSBadge } from '@/components/MoSBadge';
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
          className="inline-block text-sm text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
        >
          ← Back to ranking
        </Link>
        <header>
          <h1 className="font-mono text-3xl font-bold tracking-tight sm:text-4xl">
            {ticker}
          </h1>
        </header>
        <div className="rounded border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-200">
          <p className="font-medium">Detail data pending</p>
          <p className="mt-1">
            The latest compute hasn&rsquo;t produced data for{' '}
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
        className="inline-block text-sm text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
      >
        ← Back to ranking
      </Link>

      {/* Hero header card — new layout from QuantRank.html design:
          rank badge + sector chip on top row, big mono ticker, serif
          company name, radial-gauge ScoreBadge + price + MoSCell on
          the right side. */}
      <header className="rounded border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900 sm:p-6">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="inline-flex items-center rounded-sm bg-slate-100 px-1.5 py-0.5 font-mono font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                #{detail.rank}
              </span>
              <SectorChip sector={detail.sector} />
              {detail.industry && (
                <span className="truncate text-slate-400 dark:text-slate-500">· {detail.industry}</span>
              )}
            </div>
            <h1 className="mt-2 flex flex-wrap items-center gap-3">
              <StockLogo ticker={detail.ticker} size={48} />
              <span className="font-mono text-4xl font-bold tracking-tight text-slate-900 dark:text-slate-100 sm:text-5xl">
                {detail.ticker}
              </span>
              <RecommendationBadge recommendation={detail.recommendation} size="md" />
            </h1>
            {/* LedgerCraft Phase 2 — company name in slab-serif gives
                the "editorial finance" register (Bloomberg / WSJ
                headline) at hero scale. Ticker stays in mono (line
                99); the slab handles the wordmark-style name read. */}
            <p className="mt-1 font-slab text-2xl text-slate-700 dark:text-slate-300 sm:text-3xl">
              {detail.name}
            </p>
            <CurrentPriceLine
              ticker={detail.ticker}
              fallbackPrice={detail.current_price}
            />
          </div>
          <div className="flex flex-col gap-3 sm:items-end">
            {/* Top row: composite donut + MoS donut — paired because
                both are summary statistics ("how good overall" / "how
                cheap"). Both badges share the radial-gauge family
                (ScoreBadge "lg" + MoSBadge); arc length = score/100
                or |MoS|/100, color = sign-driven for MoS. `flex-nowrap`
                keeps them on a single row even at narrow mobile
                viewports (the badge widths are sized to fit a 375 px
                card with `gap-3`). */}
            <div className="flex flex-nowrap items-center gap-3 sm:gap-5">
              <ScoreBadge score={detail.composite_score} size="lg" />
              <MoSBadge mos={mosPct} />
            </div>
            {/* 3-column metric row. `justify-evenly` distributes
                equal space BEFORE / BETWEEN / AFTER the three columns
                so the left edge of Price + the right edge of Loss
                Chance feel equally inset from the card. Single
                baseline: label + h-6 value box. */}
            <div className="flex flex-wrap items-start justify-evenly gap-3">
              <div className="flex flex-col items-center gap-1 text-center">
                <span className="text-xs font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Fair value
                </span>
                <span className="flex h-6 items-center font-mono text-lg font-semibold tabular-nums leading-none text-slate-900 dark:text-slate-100">
                  {detail.fair_price?.median != null
                    ? formatPrice(detail.fair_price.median)
                    : <span className="text-slate-300 dark:text-slate-600">—</span>}
                </span>
              </div>
              <div className="flex flex-col items-center gap-1 text-center">
                <span className="text-xs font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Target
                </span>
                <span className="flex h-6 items-center font-mono text-lg font-semibold tabular-nums leading-none text-slate-900 dark:text-slate-100">
                  {detail.fair_price?.max != null
                    ? formatPrice(detail.fair_price.max)
                    : <span className="text-slate-300 dark:text-slate-600">—</span>}
                </span>
              </div>
              <div className="flex flex-col items-center gap-1 text-center">
                <span className="text-xs font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Loss chance
                </span>
                {(() => {
                  const pct = detail.loss_chance_pct;
                  if (pct == null) {
                    return (
                      <span className="flex h-6 items-center font-mono text-lg font-semibold tabular-nums leading-none text-slate-300 dark:text-slate-600">
                        —
                      </span>
                    );
                  }
                  // Mirror the 5-band rubric used by the mobile ranking
                  // card (frontend/components/RankingTable.tsx) so the
                  // detail page and the front page agree on tone.
                  const tone =
                    pct < 25 ? 'text-emerald-700 dark:text-emerald-300' :
                    pct < 40 ? 'text-emerald-700 dark:text-emerald-300' :
                    pct < 60 ? 'text-slate-700 dark:text-slate-300' :
                    pct < 80 ? 'text-red-700 dark:text-red-300' :
                               'text-red-700 dark:text-red-300';
                  return (
                    <span className={`flex h-6 items-center font-mono text-lg font-semibold tabular-nums leading-none ${tone}`}>
                      {Math.round(pct)}%
                    </span>
                  );
                })()}
              </div>
            </div>
          </div>
        </div>
      </header>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-slate-600 dark:text-slate-400">
          Price (1y)
        </h2>
        {detail.has_history ? (
          <PriceHistoryChart
            ticker={detail.ticker}
            fairPriceMedian={detail.fair_price?.median ?? null}
            fairPriceMax={detail.fair_price?.max ?? null}
            recommendation={detail.recommendation}
          />
        ) : (
          <div className="flex h-64 items-center justify-center rounded border border-slate-200 bg-white text-sm text-slate-400 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-500">
            No price history available
          </div>
        )}
      </section>

      <Tier2EventCard
        tier2_events={detail.tier2_events}
        ticker={detail.ticker}
      />

      <ManipulationRiskCard
        manipulationIndex={detail.manipulation_index}
        compositeScore={detail.composite_score}
        compositeScoreAdjusted={detail.composite_score_adjusted}
        components={detail.manipulation_components}
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
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-slate-600 dark:text-slate-400">
          Raw fundamentals (SEC EDGAR)
        </h2>
        <RawMetricsTable metrics={detail.raw_metrics} />
        <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">
          TTM = trailing twelve months. Balance sheet items are point-in-time
          (latest filing).
        </p>
      </section>

      <section className="rounded border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-slate-600 dark:text-slate-400">
          Data quality
        </h2>
        <dl className="grid grid-cols-1 gap-y-2 text-sm sm:grid-cols-2">
          <dt className="text-slate-500 dark:text-slate-400">Latest filed date</dt>
          <dd className="font-mono text-slate-900 dark:text-slate-100">
            {detail.data_quality.latest_filed_date ?? 'N/A'}
          </dd>
          <dt className="text-slate-500 dark:text-slate-400">Latest period end</dt>
          <dd className="font-mono text-slate-900 dark:text-slate-100">
            {detail.data_quality.latest_period_end ?? 'N/A'}
          </dd>
          <dt className="text-slate-500 dark:text-slate-400">Filing lag</dt>
          <dd>
            <span
              className={`inline-flex items-center rounded-sm px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${filingLagBadgeClasses(
                filingLag,
              )}`}
            >
              {filingLag === null ? 'N/A' : `${filingLag} days`}
            </span>
          </dd>
          <dt className="text-slate-500 dark:text-slate-400">Missing metrics</dt>
          <dd className="text-slate-900 dark:text-slate-100">
            {missingCount === 0 ? (
              'none'
            ) : (
              <span className="text-amber-700 dark:text-amber-300">
                {missingCount}
                {missingCount > 0 && (
                  <span className="ml-2 text-xs text-slate-500 dark:text-slate-400">
                    ({detail.data_quality.missing_metrics.join(', ')})
                  </span>
                )}
              </span>
            )}
          </dd>
        </dl>
      </section>

      <p className="text-xs text-slate-400 dark:text-slate-500">
        Composite is the 8-pillar weighted score over quality, value, growth,
        momentum, health, profitability, technical, and risk. Sentiment + ML
        pillars are reserved for a later phase; until then their weight
        redistributes pro-rata. Fair price is the median of 6 valuation
        methods (Graham, P/E / P/B / EV-EBITDA multiples, RIM, DCF) with
        outliers above 5× current price excluded from the max. Risk-overlay
        flags annotate only — they suppress the entered-top-5 badge but do
        not modify the composite.
      </p>
    </article>
  );
}
