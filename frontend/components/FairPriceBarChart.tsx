'use client';

import type { JSX } from 'react';

import type { FairPriceEnsemble } from '@/lib/types';
import { formatFairPrice } from '@/lib/format';

// "Fair price check" — verdict card from the QuantRank.html design.
//
// The previous Recharts horizontal bar chart had a hard usability
// problem: a $1031 EV/EBITDA outlier compressed the other bars
// into 6-pixel slivers, and the "method names + $ values + reference
// lines + outlier grayscale" cocktail required a methodology-doc
// read before a user could decode it.
//
// The redesign delivers the answer in plain English first:
//   1. Headline: "Looks overvalued / Near fair value / …" with a
//      one-sentence rationale and a side-by-side "today's price →
//      median fair price" comparison.
//   2. Tally pills: "Of N methods: X say cheap, Y say fair, Z say
//      pricey" — distribution of opinion at a glance.
//   3. Per-method rows: each method gets a verdict badge + a full
//      English sentence ("estimates $98, about 48% below today")
//      instead of an unlabeled bar.
//
// Component still exported as `FairPriceBarChart` for backward
// compatibility with the existing import in the detail page. Internal
// shape is now a card list, not a chart.

const METHOD_ORDER: ReadonlyArray<readonly [MethodKey, string]> = [
  ['graham', 'Graham (defensive)'],
  ['multiples_pe', 'P/E multiples'],
  ['multiples_pb', 'P/B multiples'],
  ['multiples_ev_ebitda', 'EV/EBITDA'],
  ['rim', 'Residual Income'],
  ['dcf', 'DCF (2-stage)'],
];

type MethodKey =
  | 'graham'
  | 'multiples_pe'
  | 'multiples_pb'
  | 'multiples_ev_ebitda'
  | 'rim'
  | 'dcf';

type Verdict = 'cheap' | 'fair' | 'pricey' | 'outlier';

type Row = {
  key: MethodKey;
  label: string;
  value: number;
  pct: number;
  is_outlier: boolean;
  verdict: Verdict;
};

// Verdict thresholds:
// - "cheap" — method's fair price is at least 20% above today
// - "fair" — within ±10–20% of today
// - "pricey" — at least 10% below today
function classifyVerdict(pct: number, is_outlier: boolean): Verdict {
  if (is_outlier) return 'outlier';
  if (pct >= 20) return 'cheap';
  if (pct >= -10) return 'fair';
  return 'pricey';
}

const VERDICT_STYLE: Record<Verdict, {
  dot: string;
  text: string;
  bg: string;
  ring: string;
  label: string;
  phrase: string;
}> = {
  cheap:   { dot: 'bg-emerald-500 dark:bg-emerald-400', text: 'text-emerald-700 dark:text-emerald-300', bg: 'bg-emerald-50 dark:bg-emerald-900/30', ring: 'ring-emerald-200 dark:ring-emerald-800', label: 'Undervalued', phrase: "thinks it's a bargain" },
  fair:    { dot: 'bg-slate-400 dark:bg-slate-500',     text: 'text-slate-600 dark:text-slate-400',   bg: 'bg-slate-50 dark:bg-slate-800',         ring: 'ring-slate-200 dark:ring-slate-700',   label: 'Fair',        phrase: "thinks it's fairly priced" },
  pricey:  { dot: 'bg-rose-500 dark:bg-rose-400',       text: 'text-rose-700 dark:text-rose-300',     bg: 'bg-rose-50 dark:bg-rose-900/30',         ring: 'ring-rose-200 dark:ring-rose-800',     label: 'Overvalued',  phrase: "thinks it's expensive" },
  outlier: { dot: 'bg-slate-300 dark:bg-slate-600',     text: 'text-slate-500 dark:text-slate-400',   bg: 'bg-slate-100 dark:bg-slate-800',        ring: 'ring-slate-300 dark:ring-slate-700',   label: 'Outlier',     phrase: 'estimate looks unreliable' },
};

type Headline = {
  tag: string;
  desc: string;
  cls: string;
  bg: string;
  ring: string;
  big: string;
} | null;

function headlineFor(medianPct: number | null, ticker: string): Headline {
  if (medianPct === null) return null;
  if (medianPct >= 20) {
    return {
      tag: 'Looks undervalued',
      desc: `Models suggest ${ticker} is trading below fair value`,
      cls: 'text-emerald-800 dark:text-emerald-200', bg: 'bg-emerald-50 dark:bg-emerald-900/30',
      ring: 'ring-emerald-200 dark:ring-emerald-800', big: 'text-emerald-700 dark:text-emerald-300',
    };
  }
  if (medianPct >= -10) {
    return {
      tag: 'Near fair value',
      desc: `Models suggest ${ticker} is priced roughly in line`,
      cls: 'text-slate-700 dark:text-slate-300', bg: 'bg-slate-50 dark:bg-slate-800',
      ring: 'ring-slate-200 dark:ring-slate-700', big: 'text-slate-700 dark:text-slate-300',
    };
  }
  if (medianPct >= -50) {
    return {
      tag: 'Looks overvalued',
      desc: `Models suggest ${ticker} is trading above fair value`,
      cls: 'text-rose-800 dark:text-rose-200', bg: 'bg-rose-50 dark:bg-rose-900/30',
      ring: 'ring-rose-200 dark:ring-rose-800', big: 'text-rose-700 dark:text-rose-300',
    };
  }
  return {
    tag: 'Heavily overvalued',
    desc: `Models suggest ${ticker} is far above estimated fair value`,
    cls: 'text-rose-900 dark:text-rose-100', bg: 'bg-rose-50 dark:bg-rose-900/30',
    ring: 'ring-rose-300 dark:ring-rose-800', big: 'text-rose-800 dark:text-rose-200',
  };
}

export function FairPriceBarChart({
  fair_price,
  current_price,
  ticker,
}: {
  fair_price: FairPriceEnsemble | null;
  current_price: number | null;
  ticker: string;
}): JSX.Element | null {
  if (fair_price == null || current_price == null || Number.isNaN(current_price)) {
    return null;
  }

  const warnings = new Set(fair_price.valuation_warnings ?? []);
  const rows: Row[] = [];
  for (const [key, label] of METHOD_ORDER) {
    const m = fair_price.methods[key];
    if (!m || !m.applicable || m.value === null || Number.isNaN(m.value)) continue;
    const pct = ((m.value - current_price) / current_price) * 100;
    const is_outlier = warnings.has(`extreme_${key}_estimate`);
    rows.push({
      key,
      label,
      value: m.value,
      pct,
      is_outlier,
      verdict: classifyVerdict(pct, is_outlier),
    });
  }
  if (rows.length === 0) return null;

  // Sort: cheap first (most positive %), then fair, then pricey
  // (most negative %), outliers last. Within a verdict bucket, more
  // extreme estimates surface first.
  const verdictOrder: Record<Verdict, number> = { cheap: 0, fair: 1, pricey: 2, outlier: 3 };
  rows.sort((a, b) =>
    verdictOrder[a.verdict] - verdictOrder[b.verdict] || b.pct - a.pct,
  );

  const tally: Record<Verdict, number> = { cheap: 0, fair: 0, pricey: 0, outlier: 0 };
  rows.forEach((r) => {
    tally[r.verdict]++;
  });
  const nonOutlier = rows.length - tally.outlier;
  const medianPct = fair_price.median !== null
    ? ((fair_price.median - current_price) / current_price) * 100
    : null;
  const headline = headlineFor(medianPct, ticker);

  return (
    <section
      aria-label={`Fair price methods for ${ticker}`}
      className="mb-4 rounded border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"
    >
      <div className="mb-4">
        <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-slate-600 dark:text-slate-400">
          Fair price check
        </h2>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          {rows.length} different valuation methods each estimate what{' '}
          <span className="font-mono font-semibold text-slate-700 dark:text-slate-300">{ticker}</span> should be
          worth, then we compare to today&apos;s price.
        </p>
      </div>

      {/* Headline summary — plain-English verdict + side-by-side
          today-vs-median comparison. Color of the surround tracks
          the verdict. */}
      {headline && (
        <div className={`mb-4 rounded border border-slate-200 p-4 dark:border-slate-800 ${headline.bg}`}>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className={`text-lg font-semibold ${headline.cls}`}>{headline.tag}</div>
              <div className="mt-0.5 text-xs text-slate-600 dark:text-slate-400">{headline.desc}</div>
            </div>
            <div className="flex items-baseline gap-5">
              <div>
                <div className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Today&apos;s price
                </div>
                <div className="font-mono text-xl font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                  {formatFairPrice(current_price)}
                </div>
              </div>
              <div className="text-slate-400 dark:text-slate-500" aria-hidden="true">
                →
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider text-slate-500 dark:text-slate-400">
                  Median fair price
                </div>
                <div
                  className={`font-mono text-xl font-semibold tabular-nums ${headline.big}`}
                >
                  {fair_price.median !== null ? formatFairPrice(fair_price.median) : '—'}
                </div>
                {medianPct !== null && (
                  <div className={`text-[11px] font-medium tabular-nums ${headline.cls}`}>
                    {medianPct >= 0
                      ? `+${medianPct.toFixed(0)}%`
                      : `${medianPct.toFixed(0)}%`}{' '}
                    vs today
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tally pills — "Of N methods: X say cheap…" */}
      <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
        <span className="text-slate-500 dark:text-slate-400">Of {nonOutlier} methods:</span>
        {tally.cheap > 0 && (
          <span
            className={`inline-flex items-center gap-1.5 rounded-sm px-2.5 py-1 font-medium ${VERDICT_STYLE.cheap.bg} ${VERDICT_STYLE.cheap.text} ring-1 ring-inset ${VERDICT_STYLE.cheap.ring}`}
          >
            <span className={`inline-block h-1.5 w-1.5 rounded-full ${VERDICT_STYLE.cheap.dot}`} />
            <span className="font-mono tabular-nums">{tally.cheap}</span> say cheap
          </span>
        )}
        {tally.fair > 0 && (
          <span
            className={`inline-flex items-center gap-1.5 rounded-sm px-2.5 py-1 font-medium ${VERDICT_STYLE.fair.bg} ${VERDICT_STYLE.fair.text} ring-1 ring-inset ${VERDICT_STYLE.fair.ring}`}
          >
            <span className={`inline-block h-1.5 w-1.5 rounded-full ${VERDICT_STYLE.fair.dot}`} />
            <span className="font-mono tabular-nums">{tally.fair}</span> say fair
          </span>
        )}
        {tally.pricey > 0 && (
          <span
            className={`inline-flex items-center gap-1.5 rounded-sm px-2.5 py-1 font-medium ${VERDICT_STYLE.pricey.bg} ${VERDICT_STYLE.pricey.text} ring-1 ring-inset ${VERDICT_STYLE.pricey.ring}`}
          >
            <span className={`inline-block h-1.5 w-1.5 rounded-full ${VERDICT_STYLE.pricey.dot}`} />
            <span className="font-mono tabular-nums">{tally.pricey}</span> say pricey
          </span>
        )}
        {tally.outlier > 0 && (
          <span className="text-slate-400 dark:text-slate-500">
            ({tally.outlier} outlier{tally.outlier > 1 ? 's' : ''} excluded)
          </span>
        )}
      </div>

      {/* Per-method rows — accent bar (verdict color) + name + verdict
          badge + descriptive sentence in plain English. */}
      <ul className="divide-y divide-slate-100 overflow-hidden rounded border border-slate-200 dark:divide-slate-800/60 dark:border-slate-800">
        {rows.map((r) => {
          const v = VERDICT_STYLE[r.verdict];
          const pctRounded = Math.abs(r.pct) > 999
            ? r.pct > 0
              ? '>+999%'
              : '<−999%'
            : r.pct >= 0
              ? `+${r.pct.toFixed(0)}%`
              : `${r.pct.toFixed(0)}%`;
          const compare = r.is_outlier ? (
            <>
              estimates{' '}
              <span className="font-mono font-semibold tabular-nums text-slate-700 dark:text-slate-300">
                {formatFairPrice(r.value)}
              </span>{' '}
              — likely unreliable
            </>
          ) : r.pct >= 0 ? (
            <>
              estimates{' '}
              <span className="font-mono font-semibold tabular-nums text-slate-700 dark:text-slate-300">
                {formatFairPrice(r.value)}
              </span>
              , about{' '}
              <span className="font-semibold text-emerald-700 dark:text-emerald-300">
                {pctRounded.replace('+', '')} above
              </span>{' '}
              today
            </>
          ) : (
            <>
              estimates{' '}
              <span className="font-mono font-semibold tabular-nums text-slate-700 dark:text-slate-300">
                {formatFairPrice(r.value)}
              </span>
              , about{' '}
              <span className="font-semibold text-rose-700 dark:text-rose-300">
                {Math.abs(r.pct) > 999 ? '>999%' : `${Math.abs(r.pct).toFixed(0)}%`} below
              </span>{' '}
              today
            </>
          );
          return (
            <li key={r.key} className="flex items-center gap-3 px-3 py-3 transition-colors duration-100 hover:bg-slate-50 dark:hover:bg-slate-800/30 sm:px-4">
              <span
                className={`inline-flex h-8 w-1 shrink-0 rounded-sm ${v.dot}`}
                aria-hidden="true"
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">{r.label}</span>
                  <span
                    className={`inline-flex items-center rounded-sm px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${v.bg} ${v.text} ring-1 ring-inset ${v.ring}`}
                  >
                    {v.label}
                  </span>
                </div>
                <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                  {v.phrase} — {compare}
                </div>
              </div>
            </li>
          );
        })}
      </ul>

      <p className="mt-3 text-[11px] text-slate-400 dark:text-slate-500">
        <span className="font-medium text-slate-500 dark:text-slate-400">How to read this:</span>{' '}
        &ldquo;Cheap&rdquo; = method&apos;s fair price is at least 20% above today.
        &ldquo;Fair&rdquo; = within ±10–20%. &ldquo;Pricey&rdquo; = at least 10% below
        today. Outliers (values more than 5× or less than 0.2× today&apos;s price) are
        excluded.
      </p>
    </section>
  );
}
