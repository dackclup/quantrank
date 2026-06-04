import type { Metadata } from 'next';
import Link from 'next/link';

import { ScoreBadge } from '@/components/ScoreBadge';
import { getMetadata, getRankings } from '@/lib/data';
import { sectorStyle } from '@/lib/visual';

export const metadata: Metadata = {
  title: 'QuantRank — equity rankings',
  description:
    'A static-site equity ranking — companies scored by an 8-pillar composite with an academic defense layer. Overview dashboard.',
};

function signedPct(v: number): string {
  const sign = v >= 0 ? '+' : '−';
  return `${sign}${Math.abs(v).toFixed(2)}%`;
}

type Mover = { ticker: string; name: string; chg: number };

export default function HomePage() {
  const rankings = getRankings();
  const meta = getMetadata();

  if (meta.universe_size === 0 || rankings.length === 0) {
    return (
      <section className="space-y-6">
        <h1 className="font-slab text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100">QuantRank</h1>
        <div className="rounded border border-amber-200 bg-amber-50 p-6 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-200">
          <p className="font-medium">Compute pending.</p>
          <p className="mt-1">The first compute hasn&rsquo;t run yet. Scheduled cron: Mon-Fri 22:00 UTC (after US market close).</p>
        </div>
      </section>
    );
  }

  // All previews derive from the build-imported rankings.json — no new data.
  const top = rankings.slice(0, 5);

  const changes = rankings
    .map((r) => ({ ticker: r.ticker, name: r.name, chg: r.price_change_1d_pct }))
    .filter((x): x is Mover => typeof x.chg === 'number');
  const gainers = [...changes].sort((a, b) => b.chg - a.chg).slice(0, 3);
  const losers = [...changes].sort((a, b) => a.chg - b.chg).slice(0, 3);

  const bySector = new Map<string, number[]>();
  for (const r of rankings) {
    const k = r.sector || 'Unknown';
    const arr = bySector.get(k);
    if (arr) arr.push(r.composite_score);
    else bySector.set(k, [r.composite_score]);
  }
  const sectors = Array.from(bySector, ([sector, scores]) => ({
    sector,
    count: scores.length,
    avg: scores.reduce((a, b) => a + b, 0) / scores.length,
  }))
    .sort((a, b) => b.avg - a.avg)
    .slice(0, 4);

  return (
    <section className="space-y-8">
      {/* Hero */}
      <header className="max-w-3xl space-y-3">
        <h1 className="text-balance font-slab text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100 sm:text-4xl">
          Equities, ranked.
        </h1>
        <p className="max-w-2xl text-pretty text-base text-slate-600 dark:text-slate-300">
          All{' '}
          <span className="font-mono font-semibold tabular-nums text-emerald-800 dark:text-emerald-300">{meta.universe_size}</span>{' '}
          companies scored by an 8-pillar composite with an academic defense layer.
        </p>
        <div className="flex flex-wrap items-center gap-3 pt-1">
          <Link
            href="/ranking"
            className="inline-flex min-h-[44px] items-center rounded-sm bg-emerald-700 px-4 text-sm font-semibold text-white press hover:bg-emerald-800 dark:bg-emerald-700 dark:hover:bg-emerald-800"
          >
            View full ranking
          </Link>
          <span className="text-xs text-slate-500 dark:text-slate-400">
            Updated <span className="font-mono">{meta.last_update_utc}</span>
          </span>
        </div>
      </header>

      {/* Preview cards — all derived inline from rankings.json. "Top ranked"
          links to /ranking; Movers / Sectors have no standalone page (removed
          2026-06-04), so they show their top rows inline without a "see all" link. */}
      <div className="grid gap-4 lg:grid-cols-3">
        <OverviewCard title="Top ranked" href="/ranking" linkLabel="Full ranking">
          <ol className="divide-y divide-slate-100 dark:divide-slate-800">
            {top.map((r) => (
              <li key={r.ticker}>
                <Link href={`/stock/${r.ticker}/`} className="press flex items-center gap-3 py-2 hover:opacity-80">
                  <span className="w-5 shrink-0 font-mono text-xs tabular-nums text-slate-500 dark:text-slate-400">{r.rank}</span>
                  <span className="font-mono text-sm font-semibold text-slate-900 dark:text-slate-100">{r.ticker}</span>
                  <span className="min-w-0 flex-1 truncate text-sm text-slate-500 dark:text-slate-400">{r.name}</span>
                  <ScoreBadge score={r.composite_score} />
                </Link>
              </li>
            ))}
          </ol>
        </OverviewCard>

        <OverviewCard title="Movers today">
          <div className="space-y-3">
            <MoverGroup label="Gainers" rows={gainers} tone="pos" />
            <MoverGroup label="Losers" rows={losers} tone="neg" />
          </div>
        </OverviewCard>

        <OverviewCard title="Top sectors">
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {sectors.map((s) => {
              const sty = sectorStyle(s.sector);
              return (
                <li key={s.sector} className="flex items-center gap-2 py-2">
                  <span className="inline-block h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: sty.dot }} aria-hidden="true" />
                  <span className="min-w-0 flex-1 truncate text-sm text-slate-700 dark:text-slate-300">{s.sector}</span>
                  <span className="font-mono text-xs tabular-nums text-slate-500 dark:text-slate-400">{s.count}</span>
                  <span className="font-mono text-sm font-semibold tabular-nums text-slate-900 dark:text-slate-100">{s.avg.toFixed(1)}</span>
                </li>
              );
            })}
          </ul>
        </OverviewCard>
      </div>
    </section>
  );
}

function OverviewCard({
  title,
  href,
  linkLabel,
  children,
}: {
  title: string;
  // Optional: cards without a dedicated full page (Movers / Sectors, whose
  // standalone routes were removed 2026-06-04) render the header without a link.
  href?: string;
  linkLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded border border-slate-200 bg-white p-4 shadow-subtle dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">{title}</h2>
        {href && linkLabel && (
          <Link href={href} className="press text-xs font-medium text-emerald-700 hover:underline dark:text-emerald-300">
            {linkLabel} →
          </Link>
        )}
      </div>
      {children}
    </section>
  );
}

function MoverGroup({ label, rows, tone }: { label: string; rows: Mover[]; tone: 'pos' | 'neg' }) {
  const toneText = tone === 'pos' ? 'text-emerald-700 dark:text-emerald-300' : 'text-rose-700 dark:text-rose-300';
  return (
    <div>
      <div className="mb-1 text-[0.625rem] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">{label}</div>
      <ul className="space-y-0.5">
        {rows.map((m) => (
          <li key={m.ticker}>
            <Link href={`/stock/${m.ticker}/`} className="press flex items-center gap-2 hover:opacity-80">
              <span className="font-mono text-sm font-semibold text-slate-900 dark:text-slate-100">{m.ticker}</span>
              <span className="min-w-0 flex-1 truncate text-xs text-slate-500 dark:text-slate-400">{m.name}</span>
              <span className={`font-mono text-xs font-semibold tabular-nums ${toneText}`}>{signedPct(m.chg)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
