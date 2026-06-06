'use client';

import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';
import { SearchX } from 'lucide-react';

import { LossChanceBadge } from '@/components/LossChanceBadge';
import { RecommendationBadge } from '@/components/RecommendationBadge';
import { ScoreBadge } from '@/components/ScoreBadge';
import { SectorChip } from '@/components/SectorChip';
import { StockLogo } from '@/components/StockLogo';
import { WatchlistButton } from '@/components/WatchlistButton';
import { formatMosPct } from '@/lib/format';
import type { StockSummary } from '@/lib/types';
import { useFlip } from '@/lib/useFlip';

type SortKey =
  | 'rank'
  | 'ticker'
  | 'name'
  | 'sector'
  | 'composite_score'
  | 'current_price'
  | 'fair_price'
  | 'margin_of_safety_pct';
type SortDir = 'asc' | 'desc';

const PAGE_SIZE = 50;

function formatPrice(p: number): string {
  return p.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 });
}

export default function RankingTable({ data }: { data: StockSummary[] }) {
  // Search-only view. The multi-dimension filter screener + the cross-stock
  // compare multi-select were removed; the table keeps free-text search, column
  // sort, and pagination.
  const [search, setSearch] = useState('');

  // Sort + pagination
  const [sortKey, setSortKey] = useState<SortKey>('rank');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [page, setPage] = useState(1);

  // Free-text search over ticker + company name. Empty query passes everything.
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return data;
    return data.filter(
      (row) => row.ticker.toLowerCase().includes(q) || row.name.toLowerCase().includes(q),
    );
  }, [data, search]);

  // Reset page on a search change so the user doesn't land on a now-empty page.
  useEffect(() => {
    setPage(1);
  }, [search]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    arr.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      let cmp = 0;
      if (typeof av === 'number' && typeof bv === 'number') cmp = av - bv;
      else cmp = String(av).localeCompare(String(bv));
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return arr;
  }, [filtered, sortKey, sortDir]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pageRows = sorted.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);

  // FLIP reshuffle ($impeccable overdrive) — when a SEARCH change reorders the
  // visible rows, the surviving rows slide from their old position to the new
  // one (transform-only, 300ms, app ease-in-out, reduced-motion guarded).
  // Search-scoped on purpose: a column-sort turns over the whole paginated
  // 50-row page, so a sort-triggered FLIP would fire on <5% of rows and read as
  // broken; a search keeps survivors in the DOM, so partial animation there is
  // semantically correct ("the field responded"). `orderKey` re-runs the
  // measure on ANY order change (sort / page silently re-baseline); `filterKey`
  // is what GATES the play.
  const orderKey = pageRows.map((r) => r.ticker).join(',');
  const filterKey = search;
  const tbodyFlipRef = useFlip<HTMLTableSectionElement>(orderKey, filterKey);
  const cardsFlipRef = useFlip<HTMLUListElement>(orderKey, filterKey);

  // Row stagger-entrance. The animate class is intentionally BAKED into the
  // static HTML (NOT gated behind a usePlayOnMount effect) so the rows start at
  // the `rise-in` keyframe's `from` state (opacity:0) from the very FIRST paint
  // (a one-frame-opaque-then-snap flash otherwise). Hydration-safe: `animateRows`
  // derives ONLY from `safePage` (1) + `firstRenderRef.current` (true) at first
  // render, identical on the build-time prerender and the client's hydration
  // render. Plays ONCE per mount (`firstRenderRef` flipped false by an empty-dep
  // effect that runs before any interaction), never on an in-page interaction
  // (sort / search / paginate / FLIP reshuffle).
  const firstRenderRef = useRef(true);
  useEffect(() => {
    firstRenderRef.current = false;
  }, []);
  const animateRows = safePage === 1 && firstRenderRef.current;

  const onSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      const descByDefault: SortKey[] = [
        'composite_score',
        'fair_price',
        'margin_of_safety_pct',
      ];
      setSortDir(descByDefault.includes(key) ? 'desc' : 'asc');
    }
    setPage(1);
  };

  const headerCell = (key: SortKey, label: string, extraClass = '') => {
    const active = sortKey === key;
    return (
      <th
        scope="col"
        aria-sort={active ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
        tabIndex={0}
        className={`cursor-pointer select-none px-3 py-2 text-left font-semibold text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100 ${extraClass}`}
        onClick={() => onSort(key)}
        // Keyboard parity for the click-to-sort header (WCAG 2.1.1 / 4.1.2).
        // tabIndex makes the columnheader focusable; Enter/Space activate the
        // same sort. preventDefault on Space stops the page from scrolling. The
        // visible focus indicator comes from the global `:focus-visible` ring in
        // globals.css — do NOT add `focus:outline-none` here without a replacement.
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onSort(key);
          }
        }}
      >
        {label}
        <span className="ml-1 inline-block text-slate-500 dark:text-slate-400" aria-hidden="true">
          {active ? (
            <svg
              width="10"
              height="10"
              viewBox="0 0 10 10"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              className={`transition-transform duration-150 ${sortDir === 'desc' ? 'rotate-180' : ''}`}
            >
              <polyline points="2 3 5 7 8 3" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          ) : (
            <svg
              width="10"
              height="10"
              viewBox="0 0 10 10"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              className="text-slate-300 opacity-60 dark:text-slate-700"
            >
              <polyline points="2 3 5 5 8 3" strokeLinecap="round" strokeLinejoin="round" />
              <polyline points="2 7 5 5 8 7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          )}
        </span>
      </th>
    );
  };

  return (
    <div className="space-y-3">
      {/* Toolbar: inline search + result count. */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[12.5rem] max-w-xs flex-1">
          <input
            type="search"
            placeholder="Search ticker or name…"
            aria-label="Search by ticker or company name"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="min-h-[44px] w-full rounded-sm border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm placeholder-slate-500 focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:placeholder-slate-400 dark:focus:border-slate-500 dark:focus:ring-slate-500"
          />
          <svg
            aria-hidden="true"
            className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500 dark:text-slate-400"
            viewBox="0 0 20 20"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
          >
            <circle cx="9" cy="9" r="6" />
            <path d="M14 14l4 4" strokeLinecap="round" />
          </svg>
        </div>
        <div className="ml-auto text-xs text-slate-500 dark:text-slate-400">
          <span className="font-mono font-semibold tabular-nums text-slate-700 dark:text-slate-300">
            {sorted.length.toLocaleString()}
          </span>
          <span className="tabular-nums text-slate-500 dark:text-slate-400"> / {data.length.toLocaleString()} stocks</span>
        </div>
      </div>

      {/* Desktop table (lg+). Portrait tablets (md→lg, 768–1023px) fall back
          to the card list below: the 6-col table needs ~700px but the md
          content area is only ~530px beside the sidebar. */}
      <div className="hidden overflow-x-auto rounded border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 lg:block">
        <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
          <thead className="bg-slate-50 text-xs uppercase tracking-[0.14em] dark:bg-slate-900/60">
            <tr>
              {headerCell('rank', 'Rank')}
              {headerCell('ticker', 'Ticker')}
              {headerCell('name', 'Name')}
              {headerCell('sector', 'Sector')}
              {headerCell('composite_score', 'Score', 'text-right')}
              {headerCell('current_price', 'Price', 'text-right')}
              <th scope="col" className="px-3 py-2 text-right font-semibold text-slate-600 dark:text-slate-400">
                Loss Chance
              </th>
              <th scope="col" className="px-2 py-2">
                <span className="sr-only">Watchlist</span>
              </th>
            </tr>
          </thead>
          <tbody ref={tbodyFlipRef} className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {pageRows.map((row, i) => {
              // Stagger entrance on first home view this session — rows
              // cascade in (cap at 12 steps so the tail never waits > ~480ms;
              // rows beyond share the last delay). Replay-suppressed +
              // reduced-motion-safe via the shared motion system.
              const staggerClass = animateRows
                ? `animate-rise-in stagger-${Math.min(12, i + 1)}`
                : '';
              return (
                <tr key={row.ticker} data-flip-key={row.ticker} className={`hover-lift transition-colors duration-100 odd:bg-white even:bg-slate-100 hover:bg-slate-200 dark:odd:bg-slate-900 dark:even:bg-slate-900/50 dark:hover:bg-slate-800 ${staggerClass}`}>
                  <td className="px-3 py-2 tabular-nums text-slate-700 dark:text-slate-300">{row.rank}</td>
                  <td className="px-3 py-2 font-mono font-semibold text-slate-900 dark:text-slate-100">
                    <Link
                      href={`/stock/${row.ticker}/`}
                      className="inline-flex items-center gap-2 hover:text-slate-700 hover:underline dark:hover:text-slate-300"
                    >
                      <StockLogo ticker={row.ticker} size={22} />
                      <span>{row.ticker}</span>
                      <RecommendationBadge recommendation={row.recommendation} size="xs" />
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{row.name}</td>
                  <td className="px-3 py-2"><SectorChip sector={row.sector} /></td>
                  <td className="px-3 py-2 text-right">
                    <ScoreBadge score={row.composite_score} />
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-700 dark:text-slate-300">
                    {formatPrice(row.current_price)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <LossChanceBadge lossChancePct={row.loss_chance_pct} size="xs" />
                  </td>
                  <td className="px-1 text-center">
                    <WatchlistButton ticker={row.ticker} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile + tablet cards (below lg) */}
      <ul ref={cardsFlipRef} className="space-y-2 lg:hidden">
        {pageRows.map((row, i) => {
          const mos = formatMosPct(row.margin_of_safety_pct);
          const staggerClass = animateRows
            ? `animate-rise-in stagger-${Math.min(12, i + 1)}`
            : '';
          return (
            <li
              key={row.ticker}
              data-flip-key={row.ticker}
              className={`hover-lift flex items-stretch overflow-hidden min-h-[7rem] rounded border border-slate-200 bg-white transition-colors duration-100 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900 dark:hover:bg-slate-800/50 ${staggerClass}`}
            >
              <Link
                href={`/stock/${row.ticker}/`}
                className="press flex h-full min-w-0 flex-1 flex-col gap-1 p-3"
              >
                {/* Mobile card header — mirrors the detail-page hero
                    cadence: rank pill + sector chip on the top line, then
                    [logo] TICKER [recommendation] on the next line,
                    then company name. ScoreBadge floats on the right. */}
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5 text-xs">
                      <span className="inline-flex items-center rounded-sm bg-slate-100 px-1.5 py-0.5 font-mono font-medium text-slate-600 tabular-nums dark:bg-slate-800 dark:text-slate-300">
                        #{row.rank}
                      </span>
                      <SectorChip sector={row.sector} size="xs" />
                    </div>
                    <div className="mt-1 flex items-center gap-2">
                      <StockLogo ticker={row.ticker} size={32} />
                      <span className="font-mono text-xl font-semibold">{row.ticker}</span>
                      <RecommendationBadge recommendation={row.recommendation} size="xs" />
                    </div>
                    <div className="truncate text-sm text-slate-700 dark:text-slate-300">{row.name}</div>
                  </div>
                  <div className="shrink-0">
                    <ScoreBadge score={row.composite_score} size="md" />
                  </div>
                </div>
                {/* 2-column symmetric quote block — label sits inline
                    BEFORE the number ("PRICE $123.01 USD"), with the
                    supporting pill on the second line. */}
                <div className="mt-1 grid grid-cols-2 gap-3">
                  <div className="flex flex-col items-start gap-1">
                    <div className="flex items-baseline gap-1.5">
                      <span className="text-[0.625rem] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
                        Price
                      </span>
                      <span className="font-mono text-base font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                        ${row.current_price.toFixed(2)}
                      </span>
                      <span className="text-[0.625rem] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
                        USD
                      </span>
                    </div>
                    {row.price_change_1d_pct != null && (() => {
                        const pct = row.price_change_1d_pct;
                        const positive = pct >= 0;
                        // Daily change reads as an outlined-light chip in the one
                        // shared chip family — NOT a solid green/red dopamine pill
                        // (PRODUCT.md "calm, never urgent"). The ↗/↘ arrow is a
                        // non-color affordance so direction still reads without
                        // color (state is never color-only).
                        const pillCls = positive
                          ? 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:ring-emerald-800'
                          : 'bg-rose-50 text-rose-700 ring-rose-200 dark:bg-rose-900/30 dark:text-rose-300 dark:ring-rose-800';
                        const absCls = positive
                          ? 'text-emerald-700 dark:text-emerald-300'
                          : 'text-rose-700 dark:text-rose-300';
                        // Derive absolute $ change from current_price + pct (the
                        // same identity CurrentPriceLine uses on the detail page:
                        // abs = price * pct / (100 + pct)).
                        const abs = (row.current_price * pct) / (100 + pct);
                        return (
                          <div className="flex items-center gap-1.5 text-[0.6875rem]">
                            <span className={`font-mono font-semibold tabular-nums ${absCls}`}>
                              {positive ? '+' : ''}
                              {abs.toFixed(2)}
                            </span>
                            <span
                              className={`inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 font-semibold tabular-nums ring-1 ring-inset ${pillCls}`}
                            >
                              <span aria-hidden="true">{positive ? '↗' : '↘'}</span>
                              {positive ? '+' : ''}
                              {pct.toFixed(2)}%
                            </span>
                            <span className="whitespace-nowrap text-slate-500 dark:text-slate-400">past day</span>
                          </div>
                        );
                      })()}
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    {row.loss_chance_pct != null ? (
                      (() => {
                        const pct = row.loss_chance_pct;
                        const rounded = Math.round(pct);
                        // Match LossChanceBadge band rubric (band thresholds
                        // mirror frontend/components/LossChanceBadge.tsx).
                        const band =
                          rounded < 25 ? { tone: 'text-emerald-700 dark:text-emerald-300', dot: 'bg-emerald-700 dark:bg-emerald-400', label: 'Low' } :
                          rounded < 40 ? { tone: 'text-emerald-700 dark:text-emerald-300', dot: 'bg-emerald-500 dark:bg-emerald-400', label: 'Moderate-low' } :
                          rounded < 60 ? { tone: 'text-slate-700 dark:text-slate-300', dot: 'bg-slate-500 dark:bg-slate-400', label: 'Neutral' } :
                          rounded < 80 ? { tone: 'text-red-700 dark:text-red-300',     dot: 'bg-rose-500 dark:bg-rose-400',   label: 'Moderate-high' } :
                                     { tone: 'text-red-700 dark:text-red-300',     dot: 'bg-rose-500 dark:bg-rose-400',   label: 'High' };
                        return (
                          <>
                            <div className="flex items-baseline gap-1.5">
                              <span className="text-[0.625rem] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
                                Loss Chance
                              </span>
                              <span className={`font-mono text-base font-semibold tabular-nums ${band.tone}`}>
                                {rounded}%
                              </span>
                            </div>
                            <span className="inline-flex items-center gap-1 text-[0.6875rem] text-slate-500 dark:text-slate-400">
                              <span className={`inline-block h-1.5 w-1.5 rounded-full ${band.dot}`} aria-hidden="true" />
                              {band.label}
                            </span>
                          </>
                        );
                      })()
                    ) : (
                      <>
                        <div className="flex items-baseline gap-1.5">
                          <span className="text-[0.625rem] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
                            Loss Chance
                          </span>
                          <span className="font-mono text-base font-semibold tabular-nums text-slate-300 dark:text-slate-600">—</span>
                        </div>
                        <span className="text-[0.6875rem] text-slate-500 dark:text-slate-400">Unavailable</span>
                      </>
                    )}
                  </div>
                </div>
                {mos.tooltip && <span className="sr-only">{mos.tooltip}</span>}
              </Link>
              {/* Star sits in its own right rail — an interactive <button> can't
                  validly nest inside the row's <a>. */}
              <div className="flex shrink-0 items-center border-l border-slate-100 pl-1 pr-1.5 dark:border-slate-800">
                <WatchlistButton ticker={row.ticker} />
              </div>
            </li>
          );
        })}
      </ul>

      {pageRows.length === 0 && (
        <div className="animate-fade-in flex flex-col items-center rounded border border-slate-200 bg-white px-6 py-10 text-center dark:border-slate-800 dark:bg-slate-900">
          {/* Empty-state delight ($impeccable delight): a REACHABLE moment (the
              user searched for a name that isn't in the universe). Warm + helpful,
              not wacky (finance = "read the room"): a muted glyph + a human
              heading + an actionable nudge on how to RECOVER. The icon is
              decorative (aria-hidden); fade-in is reduced-motion guarded. */}
          <SearchX
            aria-hidden="true"
            strokeWidth={1.5}
            className="mb-3 h-8 w-8 text-slate-300 dark:text-slate-600"
          />
          <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
            No stocks match your search
          </p>
          <p className="mt-1 max-w-xs text-xs text-slate-500 dark:text-slate-400">
            Try a different ticker or company name.
          </p>
          {search && (
            <button
              type="button"
              onClick={() => setSearch('')}
              className="mt-4 inline-flex min-h-[44px] items-center rounded-sm border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 press hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              Clear search
            </button>
          )}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={safePage === 1}
            className="inline-flex min-h-[44px] items-center gap-1 rounded-sm border border-slate-300 bg-white px-3 py-1 text-slate-700 press enabled:hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:enabled:hover:bg-slate-800"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <polyline points="15 18 9 12 15 6" />
            </svg>
            Prev
          </button>
          <span className="text-slate-500 tabular-nums dark:text-slate-400">
            Page {safePage} of {totalPages}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={safePage === totalPages}
            className="inline-flex min-h-[44px] items-center gap-1 rounded-sm border border-slate-300 bg-white px-3 py-1 text-slate-700 press enabled:hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:enabled:hover:bg-slate-800"
          >
            Next
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
        </div>
      )}
    </div>
  );
}
