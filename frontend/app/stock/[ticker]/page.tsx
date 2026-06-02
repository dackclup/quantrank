import Link from 'next/link';

import { CurrentPriceLine } from '@/components/CurrentPriceLine';
import FairPriceCard from '@/components/FairPriceCard';
import { FairPriceBarChart } from '@/components/FairPriceBarChart';
import { HeroAttributeTiles } from '@/components/HeroAttributeTiles';
import { HeroMetric } from '@/components/HeroMetric';
import { MoSBadge } from '@/components/MoSBadge';
import { PillarRadarChart } from '@/components/PillarRadarChart';
import { PriceHistoryChartLazy } from '@/components/PriceHistoryChartLazy';
import RawMetricsTable from '@/components/RawMetricsTable';
import { RiskSummaryCard } from '@/components/RiskSummaryCard';
import { ScoreBadge } from '@/components/ScoreBadge';
import { RecommendationBadge } from '@/components/RecommendationBadge';
import { ListingChips } from '@/components/ListingChips';
import { StockLogo } from '@/components/StockLogo';
import { Tier2EventCard } from '@/components/Tier2EventCard';
import { getMetadata, getStockDetail, listTickersForStaticBuild } from '@/lib/data';
import { filingLagBadgeClasses } from '@/lib/visual';

export const dynamicParams = false;

export async function generateStaticParams() {
  return listTickersForStaticBuild().map((ticker) => ({ ticker }));
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
          className="inline-flex min-h-[44px] items-center gap-1 text-sm text-slate-900 press hover:opacity-70 dark:text-slate-100"
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <polyline points="15 18 9 12 15 6" />
          </svg>
          Back to ranking
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

  // Loss-chance band — mirror the 5-band rubric used by the mobile ranking
  // card (RankingTable.tsx) so the detail hero and the front page agree on
  // BOTH the number tone AND the plain-English band word ("Neutral",
  // "Moderate-high", …). Computed here (server) and passed to the HeroMetric
  // client leaf so the band logic stays in one place and the leaf stays
  // presentation-only. Round before banding so the band matches the displayed
  // integer: HeroMetric prints `${Math.round(v)}%`, so a raw 59.7 shows "60%"
  // and must read in the 60-79 "Moderate-high" band, not the <60 "Neutral"
  // tone the raw value would pick (the "60% · Neutral" bug — see §Gotchas
  // band-from-rounded). The five `{ tone, dot, label }` rows are an exact
  // copy of the RankingTable mobile-card ternary; they move in lockstep.
  // Compute freshness date (UTC date portion of the cron's last_update_utc)
  // for the hero "Data as of" line — the same source the home page shows
  // ($impeccable harden minor: the detail page previously surfaced a date
  // only inside the collapsed Supporting-data drawer). Server-read, no client cost.
  const dataAsOf = getMetadata().last_update_utc?.slice(0, 10) ?? null;

  const lc =
    detail.loss_chance_pct == null ? null : Math.round(detail.loss_chance_pct);
  const lossBand =
    lc == null ? null
    : lc < 25 ? { tone: 'text-emerald-700 dark:text-emerald-300', dot: 'bg-emerald-700 dark:bg-emerald-400', label: 'Low' }
    : lc < 40 ? { tone: 'text-emerald-700 dark:text-emerald-300', dot: 'bg-emerald-500 dark:bg-emerald-400', label: 'Moderate-low' }
    : lc < 60 ? { tone: 'text-slate-700 dark:text-slate-300', dot: 'bg-slate-500 dark:bg-slate-400', label: 'Neutral' }
    : lc < 80 ? { tone: 'text-red-700 dark:text-red-300', dot: 'bg-rose-500 dark:bg-rose-400', label: 'Moderate-high' }
    : { tone: 'text-red-700 dark:text-red-300', dot: 'bg-rose-500 dark:bg-rose-400', label: 'High' };

  // Does the WARNINGS zone (Tier2EventCard + RiskSummaryCard) render anything?
  // This is the EXACT union of the two cards' own null-guards — Tier2 renders
  // iff tier2_events present AND ≥1 of going_concern / non_reliance / auditor
  // is set; Risk renders iff risk_flags non-empty OR manipulation_index > 0.
  // Used to render the warnings zone wrapper ONLY when it has content, so its
  // `!mt-8` zone-seam never strands a 32px gap on a clean stock (both cards
  // null-collapse to no DOM node). Keep in lockstep with the cards' null
  // conditions (§Gotchas "detail-page zone-grouping").
  const t2 = detail.tier2_events;
  const hasWarningZone =
    (t2 != null &&
      (t2.going_concern_disclosure || t2.non_reliance_filing || t2.auditor_change)) ||
    (detail.risk_flags?.length ?? 0) > 0 ||
    (detail.manipulation_index ?? 0) > 0;

  return (
    <article className="space-y-4">
      <Link
        href="/"
        className="inline-flex min-h-[44px] items-center gap-1 text-sm text-slate-900 press hover:opacity-70 dark:text-slate-100"
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <polyline points="15 18 9 12 15 6" />
        </svg>
        Back to ranking
      </Link>

      {/* Hero header card — new layout from QuantRank.html design:
          rank badge + sector chip on top row, big mono ticker, serif
          company name, radial-gauge ScoreBadge + price + MoSCell on
          the right side. */}
      <header className="hero-card rounded border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900 sm:p-6">
        {/* Two-column split driven by a CSS CONTAINER QUERY, not a viewport
            breakpoint (globals.css `.hero-card`/`.hero-split`/`.hero-left`/
            `.hero-right` under `@container hero (min-width: 46rem)`). Why a
            container query: the sidebar (expanded 240px / collapsed 64px /
            mobile-drawer 0px) changes the hero's ACTUAL width independently of
            the viewport, so a viewport `md:`/`lg:` gate left a dead band where
            the sidebar was a desktop rail but the hero still stacked (the bug
            the user reported 2026-05-31). The container query measures the
            hero's real inline-size AFTER the sidebar takes its cut, so the
            split fires exactly when there's room — and when space is squeezed
            (narrow viewport OR expanded sidebar) it falls back to the SAME
            vertical mobile-portrait stack, per the user's "if it's squeezed,
            just drop to the mobile layout" direction. Default (no @container
            support / below threshold) = the stacked `flex flex-col`; the query
            flips it to a `justify-between` row, caps the left at `max-w-2xl`,
            and right-aligns the stats block. Inner guards (`min-w-0`,
            `flex-wrap`, `truncate`) keep a long name/chip wrapping instead of
            overflowing onto the gauges in the tight band. ~46rem threshold
            chosen so both columns clear their min-content (left name block +
            the ~290px stats block) before the row engages. */}
        <div className="hero-split flex flex-col gap-5">
          <div className="hero-left min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="inline-flex items-center rounded-sm bg-slate-100 px-1.5 py-0.5 font-mono font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                #{detail.rank}
              </span>
              <ListingChips country={detail.country} exchange={detail.exchange} />
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
            {/* Current quote (price + day-over-day change) — re-wired
                CurrentPriceLine, which was orphaned after a hero refactor;
                its removal is why the detail page lost the daily change the
                rankings cards still show ($impeccable critique #2 P1). Client
                leaf rendered fine by this Server Component page. */}
            <CurrentPriceLine ticker={detail.ticker} fallbackPrice={detail.current_price} />
            {dataAsOf && (
              <p className="mt-1 text-[0.6875rem] text-slate-500 dark:text-slate-400">
                Data as of {dataAsOf}
              </p>
            )}
          </div>
          <div className="hero-right flex min-w-0 flex-col gap-3">
            {/* Top row: composite donut + MoS donut — paired summary stats
                ("how good overall" / "how cheap"). Side-by-side on EVERY width
                via `grid-cols-2` (2026-05-31 — user wants them sharing one row
                on mobile portrait, not stacking). Both badges share the
                radial-gauge family AND the 800ms gauge-sweep + count-up motion
                (ScoreBadge "lg" + MoSBadge); arc length = score/100 or
                |MoS|/100, color = sign-driven for MoS. MoS sweeps clockwise
                like the score when ≥ 0 and mirrors to counter-clockwise when
                < 0 (overvalued reads as "runs the other way"). The grid tracks
                (1fr 1fr) bound each badge so its label wraps WITHIN its track
                instead of pushing the row wider — this is what fixes the 320px
                clip the old `flex-nowrap` had (EIX-style long "UNDERVALUED"
                label) without falling back to the `flex-wrap` vertical stack.
                The two donuts are pulled TOGETHER at the card centerline:
                score is `justify-self-end` in the left 1fr track, MoS is
                `justify-self-start` in the right — so they sit adjacent in the
                middle (just the grid gap between them) with equal, symmetric
                outer margins on both edges. The 1fr tracks still bound each
                label's wrap so nothing clips at 320px; `w-full` keeps the
                centerline = the card's at every width, overriding the parent's
                `hero-right` end-alignment for this row (2026-05-31). */}
            <div className="grid w-full grid-cols-2 items-center gap-3 sm:gap-5">
              <div className="justify-self-end">
                <ScoreBadge score={detail.composite_score} size="lg" ticker={detail.ticker} />
              </div>
              <div className="justify-self-start">
                <MoSBadge mos={mosPct} />
              </div>
            </div>
            {/* 3-column metric row. `justify-evenly` distributes
                equal space BEFORE / BETWEEN / AFTER the three columns
                so the left edge of Price + the right edge of Loss
                Chance feel equally inset from the card. Single
                baseline: label + h-6 value box. Each value count-ups on
                visit via HeroMetric (ease-in-out, shared useCountUp curve). */}
            <div className="flex flex-wrap items-start justify-evenly gap-3">
              <HeroMetric
                label="Fair value"
                value={detail.fair_price?.median ?? null}
                format="price"
              />
              <HeroMetric
                label="Target"
                value={detail.fair_price?.max ?? null}
                format="price"
              />
              <HeroMetric
                label="Loss chance"
                value={detail.loss_chance_pct ?? null}
                format="percent"
                tone={lossBand?.tone ?? 'text-slate-900 dark:text-slate-100'}
                caption={lossBand}
              />
            </div>
          </div>
        </div>
      </header>

      {/* Attribute tiles — the 4-box "what is this company" grid (cap tier ·
          sector · 2 reserved placeholders). Its own section under the hero,
          above the price chart — see HeroAttributeTiles.tsx. */}
      <HeroAttributeTiles marketCap={detail.market_cap} sector={detail.sector} />

      <section aria-label={`Price history for ${detail.ticker}`}>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-slate-600 dark:text-slate-400">
          Price
        </h2>
        {detail.has_history ? (
          <>
            {/* Screen-reader summary — the Recharts SVG below carries no
                accessible data, so this sr-only line gives a non-visual reader
                the headline the chart conveys (audit P3). */}
            <p className="sr-only">
              Interactive 5-year price history chart for {detail.ticker}. Latest
              close ${detail.current_price.toFixed(2)}.
            </p>
            <PriceHistoryChartLazy
              ticker={detail.ticker}
              fairPriceMedian={detail.fair_price?.median ?? null}
              fairPriceMax={detail.fair_price?.max ?? null}
              recommendation={detail.recommendation}
            />
          </>
        ) : (
          <div className="flex h-64 items-center justify-center rounded border border-slate-200 bg-white text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
            No price history available
          </div>
        )}
      </section>

      {/* Pillar breakdown sits directly after the price chart, near the
          hero's score donut — it answers "why is the composite score what
          it is?" (e.g. NVDA's value pillar 35 vs quality 91) while the score
          is still fresh, instead of being stranded below both fair-price
          cards (expert-user-explorer + frontend-design-reviewer reading-order
          pass, 2026-05-31). The warning group (Tier2 + Risk) stays just
          ABOVE the fair-price pair so red flags frame the valuation read. */}
      <PillarRadarChart
        pillars={detail.pillar_scores}
        ticker={detail.ticker}
        baseline={detail.pillar_baseline}
      />

      {/* WARNINGS zone — Tier2 (8-K events) + Risk (rank gates + manipulation).
          `!mt-8` opens a 32px zone-seam above the group (the sharpest gear-shift:
          "what are the pillar scores" → "are there red flags"), overriding the
          article's default 16px `space-y-4`. Gated on `hasWarningZone` (the exact
          union of both cards' null-guards) so the seam never strands a void on a
          clean stock — both cards null-collapse, so an always-rendered wrapper
          would leave an empty 32px gap. Inner `space-y-4` keeps the pair at 16px
          when both fire. */}
      {hasWarningZone && (
        <div className="space-y-4 !mt-8">
          <Tier2EventCard
            tier2_events={detail.tier2_events}
            ticker={detail.ticker}
          />

          <RiskSummaryCard
            riskFlags={detail.risk_flags}
            manipulationIndex={detail.manipulation_index}
            compositeScore={detail.composite_score}
            compositeScoreAdjusted={detail.composite_score_adjusted}
            components={detail.manipulation_components}
          />
        </div>
      )}

      {/* VALUATION zone — the interpretation+reference fair-price pair (coupled
          per §Gotchas, kept tight at 16px by inner `space-y-4`). `!mt-8` opens
          the second 32px zone-seam (the gear-shift risk → "what's it worth").
          Always present, so no gate: on a clean stock this is the single seam
          right after the pillars; on a flagged stock it follows the warnings
          zone. */}
      <div className="space-y-4 !mt-8">
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
      </div>

      {/* Supporting data — the reference/audit zone (raw fundamentals +
          data-quality provenance), grouped into ONE collapsible card and
          collapsed by default ($impeccable distill P1, 2026-06-01). The
          decision signals (hero -> pillars -> risk -> fair price) are
          everything ABOVE; these are verification, one click away — so the
          dense 14-row balance sheet no longer flattens the page hierarchy or
          adds ~600px of mobile scroll before the methodology note. Native
          <details> keeps the page a Server Component (no JS) and is keyboard +
          screen-reader accessible (announces expanded/collapsed); the recessed
          slate-50 surface + collapsed state mark it as the demoted zone vs the
          white decision cards above. */}
      <details className="group rounded border border-slate-200 bg-slate-50/60 dark:border-slate-800 dark:bg-slate-900/40">
        <summary
          aria-label="Supporting data"
          className="flex min-h-[44px] cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 [&::-webkit-details-marker]:hidden"
        >
          <span className="min-w-0">
            <span className="block font-slab text-base font-semibold text-slate-900 dark:text-slate-100">
              Supporting data
            </span>
            <span className="mt-0.5 block text-xs text-slate-600 dark:text-slate-400">
              Raw fundamentals &amp; data-quality provenance behind the scores above
            </span>
          </span>
          <svg
            className="h-4 w-4 shrink-0 text-slate-500 transition-transform duration-200 group-open:rotate-180 dark:text-slate-400"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </summary>

        <div className="space-y-6 border-t border-slate-200 px-4 py-4 dark:border-slate-800">
          <section aria-label="Raw fundamentals">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-slate-600 dark:text-slate-400">
              Raw fundamentals (SEC EDGAR)
            </h2>
            <RawMetricsTable metrics={detail.raw_metrics} />
            <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
              TTM = trailing twelve months. Balance sheet items are point-in-time
              (latest filing).
            </p>
          </section>

          <section aria-label="Data quality">
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
        </div>
      </details>

      <p className="max-w-3xl text-xs text-slate-500 dark:text-slate-400">
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
