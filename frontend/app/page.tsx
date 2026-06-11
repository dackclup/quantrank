import type { Metadata } from 'next';
import Link from 'next/link';

import { AiPickPortfolio } from '@/components/AiPickPortfolio';
import { getAiPickData, getMetadata } from '@/lib/data';

export const metadata: Metadata = {
  title: 'QuantRank — AI stock picks, backtested',
  description:
    'A deterministic, point-in-time backtested portfolio drawn from the QuantRank 8-pillar composite — AI-sized basket, inverse-volatility weighted, measured against the S&P 500 and other US indices.',
};

export default function HomePage() {
  const aiPick = getAiPickData();
  const meta = getMetadata();
  const isAdaptive = aiPick?.adaptive !== null && aiPick?.adaptive !== undefined;
  const adaptiveRule = aiPick?.meta.adaptive_rule ?? null;

  return (
    <section className="space-y-8">
      {/* Hero */}
      <header className="max-w-3xl space-y-3">
        <h1 className="text-balance font-slab text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100 sm:text-4xl">
          AI picks, backtested.
        </h1>
        <p className="max-w-2xl text-pretty text-base text-slate-600 dark:text-slate-300">
          {isAdaptive && adaptiveRule ? (
            <>
              A point-in-time portfolio drawn only from the QuantRank 8-pillar composite — the AI
              sizes its own basket each quarter, holding every pick that scores{' '}
              <span className="font-mono font-semibold tabular-nums text-emerald-800 dark:text-emerald-300">
                ≥{adaptiveRule.composite_min.toFixed(0)}
              </span>{' '}
              (between{' '}
              <span className="font-mono font-semibold tabular-nums text-emerald-800 dark:text-emerald-300">
                {adaptiveRule.min_picks}
              </span>{' '}
              and{' '}
              <span className="font-mono font-semibold tabular-nums text-emerald-800 dark:text-emerald-300">
                {adaptiveRule.max_picks}
              </span>{' '}
              names), inverse-volatility weighted.
            </>
          ) : (
            <>
              A point-in-time portfolio drawn only from the QuantRank 8-pillar composite, inverse-volatility
              weighted, and tracked against the S&P 500 and other US indices over the past decade.
            </>
          )}
        </p>
        <div className="flex flex-wrap items-center gap-3 pt-1">
          <Link
            href="/ranking"
            className="press inline-flex min-h-[44px] items-center rounded-sm bg-emerald-700 px-4 text-sm font-semibold text-white hover:bg-emerald-800 dark:bg-emerald-700 dark:hover:bg-emerald-800"
          >
            View the full ranking
          </Link>
          <span className="text-xs text-slate-500 dark:text-slate-400">
            Rankings updated <span className="font-mono">{meta.last_update_utc}</span>
          </span>
        </div>
      </header>

      {aiPick ? (
        <AiPickPortfolio data={aiPick} />
      ) : (
        <div className="rounded border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-200">
          <p className="font-medium">Backtest pending.</p>
          <p className="mt-1">
            The 5-year point-in-time backtest hasn&rsquo;t been produced yet. Meanwhile, the{' '}
            <Link href="/ranking" className="font-medium underline">
              full ranking
            </Link>{' '}
            is live.
          </p>
        </div>
      )}
    </section>
  );
}
