import type { Metadata } from 'next';
import Link from 'next/link';

import { getRankings } from '@/lib/data';
import { sectorStyle } from '@/lib/visual';

export const metadata: Metadata = {
  title: 'Sectors · QuantRank',
  description:
    'The S&P 500 universe broken down by GICS sector — name count, average composite score, and the top-ranked name in each sector.',
};

type SectorAgg = {
  sector: string;
  count: number;
  avgScore: number;
  best: { ticker: string; score: number };
};

// Derived from the build-imported rankings.json — no new data source. Grouped
// by GICS sector and ranked by average composite score.
function aggregateSectors(): SectorAgg[] {
  const bySector = new Map<string, { scores: number[]; best: { ticker: string; score: number } }>();
  for (const r of getRankings()) {
    const key = r.sector || 'Unknown';
    const entry = bySector.get(key) ?? { scores: [], best: { ticker: r.ticker, score: r.composite_score } };
    entry.scores.push(r.composite_score);
    if (r.composite_score > entry.best.score) entry.best = { ticker: r.ticker, score: r.composite_score };
    bySector.set(key, entry);
  }
  return Array.from(bySector, ([sector, { scores, best }]) => ({
    sector,
    count: scores.length,
    avgScore: scores.reduce((a, b) => a + b, 0) / scores.length,
    best,
  })).sort((a, b) => b.avgScore - a.avgScore);
}

export default function SectorsPage() {
  const sectors = aggregateSectors();

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="font-slab text-2xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">Sectors</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          The universe grouped by GICS sector, ranked by average composite score. Figures are as of the latest weekly compute.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {sectors.map((s) => {
          const style = sectorStyle(s.sector);
          return (
            <div
              key={s.sector}
              className="rounded border border-slate-200 bg-white p-4 shadow-subtle dark:border-slate-800 dark:bg-slate-900"
            >
              <div className="flex items-center gap-2">
                <span
                  className="inline-block h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: style.dot }}
                  aria-hidden="true"
                />
                <h2 className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{s.sector}</h2>
              </div>
              <dl className="mt-3 grid grid-cols-2 gap-y-2 text-sm">
                <dt className="text-slate-500 dark:text-slate-400">Names</dt>
                <dd className="text-right font-mono tabular-nums text-slate-900 dark:text-slate-100">{s.count}</dd>
                <dt className="text-slate-500 dark:text-slate-400">Avg score</dt>
                <dd className="text-right font-mono tabular-nums text-slate-900 dark:text-slate-100">{s.avgScore.toFixed(1)}</dd>
                <dt className="text-slate-500 dark:text-slate-400">Top name</dt>
                <dd className="text-right">
                  <Link
                    href={`/stock/${s.best.ticker}`}
                    className="press font-mono font-semibold text-emerald-700 hover:underline dark:text-emerald-400"
                  >
                    {s.best.ticker}
                  </Link>
                </dd>
              </dl>
            </div>
          );
        })}
      </div>
    </div>
  );
}
