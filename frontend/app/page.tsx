import RankingTable from '@/components/RankingTable';
import { getMetadata, getRankings } from '@/lib/data';

export default function HomePage() {
  const rankings = getRankings();
  const metadata = getMetadata();

  return (
    <section className="space-y-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">S&amp;P 500 ranking</h1>
        <p className="text-sm text-slate-500">
          Last updated:{' '}
          <span className="font-mono">{metadata.last_update_utc}</span>
          {' · '}
          Universe: <span className="font-mono">{metadata.universe}</span>{' '}
          ({metadata.universe_size} stocks)
          {' · '}
          Schema <span className="font-mono">{metadata.version}</span>
        </p>
        <p className="text-xs text-slate-400">
          Phase 1 — composite is momentum-only (12-1, knowledge doc §8.8).
          Real pillars land in Phase 3.
        </p>
      </header>

      {metadata.universe_size === 0 || rankings.length === 0 ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-6 text-center text-sm text-amber-900">
          <p className="font-medium">Compute pending.</p>
          <p className="mt-1">
            The first weekly compute hasn&rsquo;t run yet. Scheduled cron: every Sunday
            22:00 UTC, or trigger manually from the GitHub Actions tab.
          </p>
        </div>
      ) : (
        <RankingTable data={rankings} />
      )}
    </section>
  );
}
