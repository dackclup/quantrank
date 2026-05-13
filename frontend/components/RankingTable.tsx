'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';

import { MoSCell } from '@/components/MoSCell';
import { ScoreBadge } from '@/components/ScoreBadge';
import { SectorChip } from '@/components/SectorChip';
import { formatFairPrice, formatMosPct } from '@/lib/format';
import type { StockSummary } from '@/lib/types';

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
  const [search, setSearch] = useState('');
  const [sector, setSector] = useState<string>('All');
  const [sortKey, setSortKey] = useState<SortKey>('rank');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [page, setPage] = useState(1);

  const sectors = useMemo(() => {
    const s = new Set(data.map((d) => d.sector));
    return ['All', ...Array.from(s).sort()];
  }, [data]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return data.filter((row) => {
      if (sector !== 'All' && row.sector !== sector) return false;
      if (!q) return true;
      return row.ticker.toLowerCase().includes(q) || row.name.toLowerCase().includes(q);
    });
  }, [data, search, sector]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    arr.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      // Nulls sort last regardless of direction — they're "no data",
      // not "infinitely small", so they shouldn't fight for the top
      // of an ascending sort.
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
        className={`cursor-pointer select-none px-3 py-2 text-left font-medium text-slate-600 hover:text-slate-900 ${extraClass}`}
        onClick={() => onSort(key)}
      >
        {label}
        <span className="ml-1 text-slate-400">{active ? (sortDir === 'asc' ? '▲' : '▼') : ''}</span>
      </th>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-1 flex-col gap-3 sm:flex-row">
          <input
            type="search"
            placeholder="Search ticker or name…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500 sm:max-w-xs"
          />
          <select
            value={sector}
            onChange={(e) => {
              setSector(e.target.value);
              setPage(1);
            }}
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500 sm:max-w-xs"
          >
            {sectors.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div className="text-xs text-slate-500">
          {sorted.length.toLocaleString()} of {data.length.toLocaleString()} stocks
        </div>
      </div>

      {/* Desktop / tablet table */}
      <div className="hidden overflow-x-auto rounded-lg border border-slate-200 bg-white md:block">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide">
            <tr>
              {headerCell('rank', 'Rank')}
              {headerCell('ticker', 'Ticker')}
              {headerCell('name', 'Name')}
              {headerCell('sector', 'Sector')}
              {headerCell('composite_score', 'Score', 'text-right')}
              {headerCell('current_price', 'Price', 'text-right')}
              {headerCell('fair_price', 'Fair price', 'text-right')}
              {headerCell('margin_of_safety_pct', 'MoS', 'text-right')}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {pageRows.map((row) => {
              const dataQualityIssue = row.valuation_warnings.includes(
                'data_quality_input_corruption',
              );
              return (
                <tr key={row.ticker} className="hover:bg-slate-50">
                  <td className="px-3 py-2 tabular-nums text-slate-700">{row.rank}</td>
                  <td className="px-3 py-2 font-mono font-semibold">
                    <Link
                      href={`/stock/${row.ticker}/`}
                      className="hover:text-slate-700 hover:underline"
                    >
                      {row.ticker}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-slate-700">{row.name}</td>
                  <td className="px-3 py-2"><SectorChip sector={row.sector} /></td>
                  <td className="px-3 py-2 text-right">
                    <ScoreBadge score={row.composite_score} />
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-700">
                    {formatPrice(row.current_price)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-700">
                    {dataQualityIssue ? (
                      <span
                        className="inline-flex items-center gap-1 text-slate-400"
                        title="Fair price unavailable: data quality issue (Step 7.5 sanity guard)"
                      >
                        <span aria-hidden="true">⚠</span>—
                      </span>
                    ) : (
                      formatFairPrice(row.fair_price)
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {dataQualityIssue ? (
                      <span className="flex justify-end text-slate-300">—</span>
                    ) : (
                      <MoSCell mos={row.margin_of_safety_pct} />
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile cards */}
      <ul className="space-y-2 md:hidden">
        {pageRows.map((row) => {
          const mos = formatMosPct(row.margin_of_safety_pct);
          const dataQualityIssue = row.valuation_warnings.includes(
            'data_quality_input_corruption',
          );
          return (
            <li
              key={row.ticker}
              className="min-h-[112px] rounded-lg border border-slate-200 bg-white shadow-sm hover:bg-slate-50"
            >
              <Link
                href={`/stock/${row.ticker}/`}
                className="flex h-full flex-col gap-1 p-3"
              >
                {/* Top row: ticker + name on left, score top-aligned on right */}
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                      <span className="text-xs text-slate-500 tabular-nums">#{row.rank}</span>
                      <span className="font-mono text-base font-semibold">{row.ticker}</span>
                    </div>
                    <div className="truncate text-sm text-slate-700">{row.name}</div>
                  </div>
                  <div className="shrink-0">
                    <ScoreBadge score={row.composite_score} />
                  </div>
                </div>
                {/* Sector | price */}
                <div className="flex items-center justify-between gap-2 text-xs text-slate-500">
                  <SectorChip sector={row.sector} size="xs" />
                  <span className="tabular-nums">{formatPrice(row.current_price)}</span>
                </div>
                {/* Fair | MoS */}
                <div className="flex items-center justify-between text-xs">
                  {row.fair_price !== null ? (
                    <span className="text-slate-500">
                      Fair{' '}
                      <span className="tabular-nums text-slate-700">
                        {formatFairPrice(row.fair_price)}
                      </span>
                    </span>
                  ) : (
                    <span
                      className="inline-flex items-center gap-1 text-slate-400"
                      title={
                        dataQualityIssue
                          ? 'Fair price unavailable: data quality issue (Step 7.5 sanity guard)'
                          : 'Fair price unavailable for this stock'
                      }
                    >
                      Fair <span aria-hidden="true">⚠</span> N/A
                    </span>
                  )}
                  <MoSCell mos={row.margin_of_safety_pct} align="right" />
                </div>
                {/* Tooltip backup for clamped MoS values */}
                {mos.tooltip && <span className="sr-only">{mos.tooltip}</span>}
              </Link>
            </li>
          );
        })}
      </ul>

      {pageRows.length === 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-6 text-center text-sm text-slate-500">
          No stocks match the current filters.
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={safePage === 1}
            className="rounded-md border border-slate-300 bg-white px-3 py-1 text-slate-700 shadow-sm enabled:hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            ← Prev
          </button>
          <span className="text-slate-500 tabular-nums">
            Page {safePage} of {totalPages}
          </span>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={safePage === totalPages}
            className="rounded-md border border-slate-300 bg-white px-3 py-1 text-slate-700 shadow-sm enabled:hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  );
}
