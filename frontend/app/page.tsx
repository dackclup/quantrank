import RankingTable from '@/components/RankingTable';
import { getMetadata, getRankings } from '@/lib/data';

export default function HomePage() {
  const rankings = getRankings();
  const metadata = getMetadata();

  return (
    <section className="space-y-6">
      <header className="max-w-3xl space-y-2">
        <h1 className="font-slab text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100 sm:text-3xl">S&amp;P 500 ranking</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Last updated:{' '}
          <span className="font-mono">{metadata.last_update_utc}</span>
          {' · '}
          Universe: <span className="font-mono">{metadata.universe}</span>{' '}
          ({metadata.universe_size} stocks)
          {' · '}
          Schema <span className="font-mono">{metadata.version}</span>
        </p>
        <p className="text-xs text-slate-400 dark:text-slate-500">
          Composite is the 8-pillar weighted score (quality, value, growth,
          momentum, health, profitability, technical, risk).{' '}
          <span className="font-mono">sentiment</span> and{' '}
          <span className="font-mono">ml</span> pillars are reserved for a
          later phase; their 0.20 weight is redistributed pro-rata across the
          active pillars. Risk-overlay flags annotate; flagged tickers cannot
          earn the entered-top-5 badge even at rank #1 by composite.
        </p>
      </header>

      {metadata.universe_size === 0 || rankings.length === 0 ? (
        <div className="rounded border border-amber-200 bg-amber-50 p-6 text-center text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-200">
          <p className="font-medium">Compute pending.</p>
          <p className="mt-1">
            The first compute hasn&rsquo;t run yet. Scheduled cron: Mon-Fri
            22:00 UTC (after US market close), or trigger manually from the GitHub Actions tab.
          </p>
        </div>
      ) : (
        <RankingTable data={rankings} />
      )}
    </section>
  );
}
