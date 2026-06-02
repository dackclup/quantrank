import RankingTable from '@/components/RankingTable';
import { getMetadata, getRankings } from '@/lib/data';

export default function HomePage() {
  const rankings = getRankings();
  const metadata = getMetadata();

  return (
    <section className="space-y-6">
      <header className="max-w-3xl space-y-3">
        <h1 className="text-balance font-slab text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100 sm:text-4xl">
          S&amp;P 500 ranking
        </h1>
        {/* Sub-headline carries the one figure that earns presence — the
            universe count — as a heavier, brand-emerald number inside an
            otherwise medium-weight sentence (weight + one-accent contrast, the
            product-bolder levers). The page's front door had zero brand accent
            before; this is the single deliberate one. */}
        <p className="max-w-2xl text-pretty text-base text-slate-600 dark:text-slate-300">
          All{' '}
          <span className="font-mono font-semibold tabular-nums text-emerald-800 dark:text-emerald-300">
            {metadata.universe_size}
          </span>{' '}
          companies, ranked by an 8-pillar composite score.
        </p>
        {/* Provenance — clearly tertiary. Universe name + freshness + schema all
            sit at the standard muted tier; the schema version is demoted by
            POSITION (last) rather than a fainter (AA-failing) color. */}
        <p className="text-xs text-slate-500 dark:text-slate-400">
          <span className="font-mono">{metadata.universe}</span>
          {' · updated '}
          <span className="font-mono">{metadata.last_update_utc}</span>
          {' · schema '}
          <span className="font-mono">{metadata.version}</span>
        </p>
        {/* Methodology fine print — content unchanged, clearly subordinate. */}
        <p className="max-w-2xl text-pretty text-xs leading-relaxed text-slate-500 dark:text-slate-400">
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
