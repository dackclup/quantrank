'use client';

import { useEffect, useState } from 'react';

import type { StockHistory } from '@/lib/types';

// Compact "current quote" block rendered under the company name on
// the stock detail page. Lazy-fetches the per-ticker history JSON
// (same file the chart uses) and computes the day-over-day change.
// Two-row layout:
//   $21.74 USD
//   +0.12 (+0.56%) ↑ past day
//
// Falls back to a price-only display while loading and to nothing
// if the file is unavailable.

type Quote = {
  price: number;
  changeAbs: number | null;
  changePct: number | null;
};

interface Props {
  ticker: string;
  // Fallback price from the compute snapshot — used until the
  // history JSON loads and as the displayed value if the history
  // file is missing entirely.
  fallbackPrice: number;
}

export function CurrentPriceLine({ ticker, fallbackPrice }: Props) {
  const [quote, setQuote] = useState<Quote>({
    price: fallbackPrice,
    changeAbs: null,
    changePct: null,
  });

  useEffect(() => {
    let cancelled = false;
    const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? '';
    fetch(`${basePath}/data/stocks/history/${ticker}.json`)
      .then((r) => (r.ok ? (r.json() as Promise<StockHistory>) : null))
      .then((data) => {
        if (cancelled || !data) return;
        // Find the last two valid closes (skip nulls / NaN).
        let last: number | null = null;
        let prev: number | null = null;
        for (let i = data.closes.length - 1; i >= 0; i -= 1) {
          const c = data.closes[i];
          if (c === null || !Number.isFinite(c)) continue;
          if (last === null) {
            last = c;
          } else {
            prev = c;
            break;
          }
        }
        if (last === null) return;
        const next: Quote = { price: last, changeAbs: null, changePct: null };
        if (prev !== null && prev > 0) {
          next.changeAbs = last - prev;
          next.changePct = (next.changeAbs / prev) * 100;
        }
        setQuote(next);
      })
      .catch(() => {
        // Keep the fallback price; just skip the change indicator.
      });
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const positive = quote.changeAbs !== null && quote.changeAbs >= 0;

  return (
    <div className="mt-3 flex flex-col gap-1">
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-2xl font-semibold tabular-nums leading-none text-slate-900">
          ${quote.price.toFixed(2)}
        </span>
        <span className="text-xs font-medium uppercase tracking-wider text-slate-500">
          USD
        </span>
      </div>
      {quote.changeAbs !== null && quote.changePct !== null && (
        <div
          className={`flex flex-wrap items-baseline gap-1.5 text-sm ${positive ? 'text-emerald-700' : 'text-rose-600'}`}
        >
          <span className="font-mono font-semibold tabular-nums">
            {positive ? '+' : ''}
            {quote.changeAbs.toFixed(2)}
          </span>
          <span className="font-mono tabular-nums">
            ({positive ? '+' : ''}
            {quote.changePct.toFixed(2)}%)
          </span>
          <span>{positive ? '↑' : '↓'}</span>
          <span className="text-xs font-normal text-slate-500">past day</span>
        </div>
      )}
    </div>
  );
}
