import type { Metadata } from 'next';
import Link from 'next/link';

import { getRankings } from '@/lib/data';

export const metadata: Metadata = {
  title: 'Top movers · QuantRank',
  description:
    "The universe's biggest one-day price moves — top gainers and losers from the most recent trading day captured by the weekly compute.",
};

type Mover = { ticker: string; name: string; chg: number };

// Derived from the build-imported rankings.json. price_change_1d_pct is null on
// newly IPO'd names (only one close available), so filter before sorting.
function selectMovers(): { gainers: Mover[]; losers: Mover[] } {
  const rows = getRankings()
    .map((r) => ({ ticker: r.ticker, name: r.name, chg: r.price_change_1d_pct }))
    .filter((x): x is Mover => typeof x.chg === 'number');
  const gainers = [...rows].sort((a, b) => b.chg - a.chg).slice(0, 10);
  const losers = [...rows].sort((a, b) => a.chg - b.chg).slice(0, 10);
  return { gainers, losers };
}

function signedPct(v: number): string {
  const sign = v >= 0 ? '+' : '−';
  return `${sign}${Math.abs(v).toFixed(2)}%`;
}

function PageHeader() {
  return (
    <header className="space-y-1">
      <h1 className="font-slab text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">Top movers</h1>
      <p className="text-sm text-slate-500 dark:text-slate-400">
        The biggest one-day price moves in the universe, from the most recent trading day captured by the weekly compute. Not a live feed.
      </p>
    </header>
  );
}

function MoverList({ title, rows, tone }: { title: string; rows: Mover[]; tone: 'pos' | 'neg' }) {
  const toneText = tone === 'pos' ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400';
  return (
    <section className="overflow-hidden rounded border border-slate-200 bg-white shadow-subtle dark:border-slate-800 dark:bg-slate-900">
      <h2 className="border-b border-slate-200 px-4 py-3 text-sm font-semibold text-slate-900 dark:border-slate-800 dark:text-slate-100">
        {title}
      </h2>
      <ul className="divide-y divide-slate-100 dark:divide-slate-800">
        {rows.map((m) => (
          <li key={m.ticker}>
            <Link
              href={`/stock/${m.ticker}`}
              className="press flex min-h-[44px] items-center gap-3 px-4 py-2.5 hover:bg-slate-50 dark:hover:bg-slate-800/50"
            >
              <span className="font-mono text-sm font-semibold text-slate-900 dark:text-slate-100">{m.ticker}</span>
              <span className="min-w-0 flex-1 truncate text-sm text-slate-500 dark:text-slate-400">{m.name}</span>
              <span className={`font-mono text-sm font-semibold tabular-nums ${toneText}`}>{signedPct(m.chg)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function MoversPage() {
  const { gainers, losers } = selectMovers();

  if (gainers.length === 0) {
    return (
      <div className="space-y-6">
        <PageHeader />
        <p className="rounded border border-slate-200 bg-white p-6 text-sm text-slate-500 shadow-subtle dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
          No day-over-day price changes are available in the latest compute.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <MoverList title="Top gainers" rows={gainers} tone="pos" />
        <MoverList title="Top losers" rows={losers} tone="neg" />
      </div>
    </div>
  );
}
