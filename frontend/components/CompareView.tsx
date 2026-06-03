'use client';

import Link from 'next/link';
import { useEffect, useMemo, useState } from 'react';

import { CompareMatrix } from '@/components/CompareMatrix';
import { METHODOLOGY_URL } from '@/lib/links';
import type { StockSummary } from '@/lib/types';

const MAX = 4;
const PARAM = 'compare';

// Read / write the `?compare=AAPL,MSFT` selection the SAME way the ranking
// table reads its filters — `window.location.search` in a mount effect +
// `history.replaceState` — NOT Next's `useSearchParams`. On a static export a
// `useSearchParams` consumer must sit behind a `<Suspense>` boundary or the
// build errors; the window.location pattern (already used by `lib/filter-url`)
// sidesteps that and keeps the URL the single shareable artifact. The selection
// is in-memory only (no sessionStorage) — it's a transient action, and the URL
// already carries the shareable state.
function parseParam(
  search: string,
  bySymbol: Map<string, StockSummary>,
): { tickers: string[]; notFound: string[]; truncated: boolean } {
  const raw = new URLSearchParams(search).get(PARAM) ?? '';
  const wanted = raw
    .split(',')
    .map((t) => decodeURIComponent(t).trim().toUpperCase())
    .filter(Boolean);
  const seen = new Set<string>();
  const tickers: string[] = [];
  const notFound: string[] = [];
  for (const t of wanted) {
    if (seen.has(t)) continue;
    seen.add(t);
    const hit = bySymbol.get(t);
    if (hit) tickers.push(hit.ticker);
    else notFound.push(t);
  }
  return { tickers: tickers.slice(0, MAX), notFound, truncated: tickers.length > MAX };
}

function writeUrl(tickers: string[]) {
  const qs = tickers.length
    ? `?${PARAM}=${tickers.map(encodeURIComponent).join(',')}`
    : '';
  window.history.replaceState(null, '', `/compare/${qs}`);
}

export default function CompareView({ all }: { all: StockSummary[] }) {
  const bySymbol = useMemo(
    () => new Map(all.map((s) => [s.ticker.toUpperCase(), s])),
    [all],
  );

  const [mounted, setMounted] = useState(false);
  const [tickers, setTickers] = useState<string[]>([]);
  const [notFound, setNotFound] = useState<string[]>([]);
  const [truncated, setTruncated] = useState(false);
  const [input, setInput] = useState('');
  const [error, setError] = useState<string | null>(null);
  // Amber when the note is a pure miss (nothing added); calm slate when it's a
  // success-with-footnote (some tickers landed, some were skipped).
  const [errorIsWarn, setErrorIsWarn] = useState(false);

  // Hydrate the selection from the URL once, after mount (client-only). The
  // build-time HTML can't know the query, so it renders the skeleton; this fills
  // it in — same hydration model as RankingTable's filter rehydrate.
  useEffect(() => {
    const parsed = parseParam(window.location.search, bySymbol);
    setTickers(parsed.tickers);
    setNotFound(parsed.notFound);
    setTruncated(parsed.truncated);
    setMounted(true);
  }, [bySymbol]);

  const stocks = useMemo(
    () => tickers.map((t) => bySymbol.get(t.toUpperCase())).filter(Boolean) as StockSummary[],
    [tickers, bySymbol],
  );
  const atMax = tickers.length >= MAX;
  const available = useMemo(
    () => all.filter((s) => !tickers.includes(s.ticker)),
    [all, tickers],
  );

  const commit = (next: string[]) => {
    setTickers(next);
    setNotFound([]);
    setTruncated(false);
    writeUrl(next);
  };

  // Bulk-add: the input takes one ticker OR a comma / whitespace / newline
  // separated list (paste a shortlist). Adds the valid, not-already-selected
  // ones in order up to the cap; the rest (not-found / over-cap / already-added)
  // surface as ONE concise note rather than failing the whole paste.
  const addFromInput = () => {
    const raw = input.trim();
    if (!raw) return;
    const wanted = Array.from(
      new Set(raw.split(/[\s,]+/).map((t) => t.toUpperCase()).filter(Boolean)),
    );
    const next = [...tickers];
    const added: string[] = [];
    const notInUniverse: string[] = [];
    const already: string[] = [];
    const overflow: string[] = [];
    for (const t of wanted) {
      const hit = bySymbol.get(t);
      if (!hit) notInUniverse.push(t);
      else if (next.includes(hit.ticker)) already.push(hit.ticker);
      else if (next.length >= MAX) overflow.push(hit.ticker);
      else {
        next.push(hit.ticker);
        added.push(hit.ticker);
      }
    }
    const caveats: string[] = [];
    if (notInUniverse.length) caveats.push(`not in the S&P 500: ${notInUniverse.join(', ')}`);
    if (overflow.length) caveats.push(`over the ${MAX}-stock cap: ${overflow.join(', ')}`);
    if (already.length) caveats.push(`already added: ${already.join(', ')}`);
    if (added.length > 0) {
      commit(next); // updates tickers + URL; clears the URL-parse notes
      setInput('');
    } else {
      // Nothing added → commit() didn't run; still clear the stale URL-parse
      // hydrate notes (notFound / truncated from the initial ?compare= parse) so
      // a zero-add paste surfaces ONLY its own caveat, not a leftover "not in the
      // universe" note left over from page load (#395 nit 2 — the dual-note edge).
      setNotFound([]);
      setTruncated(false);
    }
    setErrorIsWarn(added.length === 0); // pure miss → amber; partial success → slate
    setError(caveats.length > 0 ? caveats.join(' · ') : null);
  };

  const removeTicker = (ticker: string) => commit(tickers.filter((t) => t !== ticker));

  const picker = (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        addFromInput();
      }}
      className="flex flex-wrap items-center gap-2"
    >
      <label htmlFor="compare-add" className="sr-only">
        Add tickers to compare (one, or several comma-separated)
      </label>
      <div className="relative">
        <input
          id="compare-add"
          list="compare-add-options"
          value={input}
          onChange={(e) => {
            setInput(e.target.value);
            if (error) setError(null);
          }}
          disabled={atMax}
          placeholder={atMax ? 'Max 4 reached' : 'Add tickers…'}
          aria-describedby={error ? 'compare-add-error' : undefined}
          className="min-h-[44px] w-44 rounded-sm border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:placeholder-slate-500"
        />
        <datalist id="compare-add-options">
          {available.map((s) => (
            <option key={s.ticker} value={s.ticker}>
              {s.name}
            </option>
          ))}
        </datalist>
      </div>
      <button
        type="submit"
        disabled={atMax || input.trim() === ''}
        className="press inline-flex min-h-[44px] items-center rounded-sm border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 enabled:hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:enabled:hover:bg-slate-800"
      >
        Add
      </button>
    </form>
  );

  // The add-feedback live region is rendered OUTSIDE `picker` so it survives the
  // `atMax` transition. A bulk paste that fills the cap (adds 4 + skips some)
  // flips `atMax` true in the same commit, which replaces `picker` with the
  // "Comparing N (max)" line — keeping the note inside `picker` would silently
  // swallow the "X didn't fit" caveat exactly when it matters most (#402
  // spot-check). Always-mounted (a freshly-inserted, already-populated
  // role="status" node isn't reliably announced); amber only for a pure miss,
  // calm slate for a success-with-footnote.
  const addError = (
    <span
      id="compare-add-error"
      role="status"
      className={`text-xs ${errorIsWarn ? 'text-amber-700 dark:text-amber-400' : 'text-slate-500 dark:text-slate-400'}`}
    >
      {error ?? ''}
    </span>
  );

  const notes = (
    <>
      {notFound.length > 0 && (
        <p className="text-xs text-amber-700 dark:text-amber-400">
          Not in the current universe, skipped:{' '}
          <span className="font-mono">{notFound.join(', ')}</span>.
        </p>
      )}
      {truncated && (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Showing the first {MAX} — remove one to add another.
        </p>
      )}
    </>
  );

  return (
    <section className="space-y-6">
      <header className="space-y-3">
        <h1 className="font-slab text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
          Compare stocks
        </h1>
        <p className="max-w-2xl text-pretty text-sm text-slate-600 dark:text-slate-300">
          Up to four S&amp;P 500 names side by side — composite score, the eight scoring pillars,
          fair-price margin of safety, and the defense-layer flags. A small{' '}
          <span className="text-emerald-700 dark:text-emerald-400">▲</span> marks the leader in each
          comparable row. Open any ticker for its full detail.
        </p>
        <Link
          href="/"
          className="press inline-flex items-center gap-1 text-sm font-medium text-slate-600 underline-offset-2 hover:text-slate-900 hover:underline dark:text-slate-400 dark:hover:text-slate-100"
        >
          <span aria-hidden="true">←</span> Back to ranking
        </Link>
      </header>

      {!mounted ? (
        // Skeleton — the URL query is read client-side, so the static HTML can't
        // know which stocks yet. Calm placeholder, not a spinner.
        <div className="animate-fade-in space-y-2" aria-hidden="true">
          <div className="h-32 rounded border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900/40" />
          <div className="h-64 rounded border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900/40" />
        </div>
      ) : stocks.length < 2 ? (
        <div className="animate-fade-in space-y-4 rounded border border-slate-200 bg-white p-6 dark:border-slate-800 dark:bg-slate-900">
          <div className="space-y-1">
            <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
              Select 2 to {MAX} stocks to compare
            </p>
            <p className="max-w-md text-xs text-slate-500 dark:text-slate-400">
              Add tickers below, or pick stocks from the ranking table (tick the boxes, then
              &ldquo;Compare&rdquo;).
            </p>
          </div>
          {tickers.length > 0 && (
            <ul className="flex flex-wrap gap-1.5">
              {tickers.map((t) => (
                <li key={t}>
                  <span className="inline-flex items-center gap-1.5 rounded-sm bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700 ring-1 ring-inset ring-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700">
                    <span className="font-mono">{t}</span>
                    <button
                      type="button"
                      onClick={() => removeTicker(t)}
                      aria-label={`Remove ${t}`}
                      className="press opacity-60 hover:opacity-100"
                    >
                      <span aria-hidden="true">×</span>
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          )}
          {picker}
          {addError}
          {notes}
          <Link
            href="/"
            className="press inline-flex text-sm font-medium text-emerald-700 underline-offset-2 hover:underline dark:text-emerald-400"
          >
            Browse the full ranking →
          </Link>
        </div>
      ) : (
        <div className="animate-fade-in space-y-4">
          <CompareMatrix stocks={stocks} onRemove={removeTicker} />
          <div className="flex flex-wrap items-center justify-between gap-3">
            {atMax ? (
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Comparing {MAX} stocks (the max). Remove one to swap in another.
              </p>
            ) : (
              picker
            )}
            <button
              type="button"
              onClick={() => commit([])}
              className="press text-xs font-medium text-slate-500 underline-offset-2 hover:text-slate-900 hover:underline dark:text-slate-400 dark:hover:text-slate-100"
            >
              Clear all
            </button>
          </div>
          {addError}
          {notes}
          <p className="max-w-2xl text-pretty text-xs leading-relaxed text-slate-500 dark:text-slate-400">
            Educational use only — not investment advice; flags mark elevated risk, never confirmed
            fraud. Figures are from the latest weekly compute. See the{' '}
            <a
              href={METHODOLOGY_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="press font-medium text-slate-600 underline underline-offset-2 hover:text-slate-900 dark:text-slate-300 dark:hover:text-slate-200"
            >
              methodology
            </a>{' '}
            for the 8-pillar composite, the 6-method fair-price ensemble, and each defense
            flag&rsquo;s academic prior.
          </p>
        </div>
      )}
    </section>
  );
}
