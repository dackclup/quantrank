'use client';

import { useEffect } from 'react';

import { DualRange } from '@/components/DualRange';
import {
  RECOMMENDATION_LABELS,
  RECOMMENDATION_VALUES,
} from '@/components/RecommendationBadge';
import type { Recommendation } from '@/lib/types';
import { MOS_BUCKETS, TIERS, sectorStyle } from '@/lib/visual';

// Slide-in panel from the right with a backdrop. Holds the full filter
// surface: search, dual-range composite-score slider, score-tier
// pills, valuation pills, sector chips.
//
// The drawer mounts always so the open/close transitions animate.
// Esc closes; backdrop click closes; body scroll locks while open.

export type FilterState = {
  search: string;
  sectorSet: Set<string>;
  scoreRange: [number, number];
  tierSet: Set<string>;
  mosSet: Set<string>;
  recommendationSet: Set<Recommendation>;
};

export type FilterSetters = {
  setSearch: (v: string) => void;
  toggleSector: (s: string) => void;
  setScoreRange: (r: [number, number]) => void;
  toggleTier: (t: string) => void;
  toggleMos: (m: string) => void;
  toggleRecommendation: (r: Recommendation) => void;
  clearAll: () => void;
};

// Soft-palette tone classes mirroring RecommendationBadge.tsx, but
// muted slightly for the drawer-chip surface (drawer uses subtler tones
// than the inline badge in the ranking-table row).
const RECOMMENDATION_CHIP_CLS: Record<Recommendation, string> = {
  bullish: 'bg-emerald-600 text-white ring-emerald-700',
  lean_bullish: 'bg-emerald-100 text-emerald-900 ring-emerald-300',
  neutral: 'bg-slate-200 text-slate-700 ring-slate-300',
  cautious: 'bg-red-500 text-white ring-red-700',
};
const RECOMMENDATION_DOT_CLS: Record<Recommendation, string> = {
  bullish: 'bg-emerald-700',
  lean_bullish: 'bg-emerald-500',
  neutral: 'bg-slate-500',
  cautious: 'bg-red-600',
};

export function FilterDrawer({
  open,
  onClose,
  state,
  setters,
  sectors,
  totalCount,
  filteredCount,
}: {
  open: boolean;
  onClose: () => void;
  state: FilterState;
  setters: FilterSetters;
  sectors: string[];
  totalCount: number;
  filteredCount: number;
}) {
  const { search, sectorSet, scoreRange, tierSet, mosSet, recommendationSet } = state;
  const {
    setSearch,
    toggleSector,
    setScoreRange,
    toggleTier,
    toggleMos,
    toggleRecommendation,
    clearAll,
  } = setters;

  // Esc-to-close + body scroll lock while drawer is open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);

  return (
    <>
      <div
        className={`fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-[2px] transition-opacity duration-200 ${
          open ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Filter stocks"
        className={`fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col bg-white shadow-2xl transition-transform duration-300 ease-out ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              Filters
            </div>
            <div className="mt-0.5 font-mono text-sm tabular-nums">
              <span className="font-semibold text-slate-900">
                {filteredCount.toLocaleString()}
              </span>
              <span className="text-slate-400"> / {totalCount.toLocaleString()} stocks</span>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close filters"
            className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.75">
              <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
            </svg>
          </button>
        </header>

        <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5">
          <div>
            <label className="mb-2 block text-[11px] font-semibold uppercase tracking-wider text-slate-700">
              Search
            </label>
            <div className="relative">
              <input
                type="search"
                placeholder="Ticker or company name…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full rounded-md border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
              />
              <svg
                className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
                viewBox="0 0 20 20"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.75"
              >
                <circle cx="9" cy="9" r="6" />
                <path d="M14 14l4 4" strokeLinecap="round" />
              </svg>
            </div>
          </div>

          <div>
            <div className="mb-2 flex items-baseline justify-between">
              <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-700">
                Composite score
              </label>
              <span className="font-mono text-xs tabular-nums text-slate-700">
                {scoreRange[0]}–{scoreRange[1]}
              </span>
            </div>
            <DualRange min={0} max={100} value={scoreRange} onChange={setScoreRange} />
          </div>

          <div>
            <label className="mb-2 block text-[11px] font-semibold uppercase tracking-wider text-slate-700">
              Score tier
            </label>
            <div className="flex flex-wrap gap-1.5">
              {TIERS.map((t) => {
                const on = tierSet.has(t.id);
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => toggleTier(t.id)}
                    className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset transition ${
                      on ? t.cls : 'bg-white text-slate-600 ring-slate-300 hover:bg-slate-50'
                    }`}
                  >
                    <span className={`inline-block h-1.5 w-1.5 rounded-full ${t.dot}`} />
                    {t.label}
                    <span className="font-mono text-[10px] tabular-nums opacity-60">
                      {t.min}–{t.max === 101 ? '100' : t.max}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <label className="mb-2 block text-[11px] font-semibold uppercase tracking-wider text-slate-700">
              Recommendation
            </label>
            <div className="flex flex-wrap gap-1.5">
              {RECOMMENDATION_VALUES.map((rec) => {
                const on = recommendationSet.has(rec);
                return (
                  <button
                    key={rec}
                    type="button"
                    onClick={() => toggleRecommendation(rec)}
                    className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset transition ${
                      on
                        ? RECOMMENDATION_CHIP_CLS[rec]
                        : 'bg-white text-slate-600 ring-slate-300 hover:bg-slate-50'
                    }`}
                  >
                    <span className={`inline-block h-1.5 w-1.5 rounded-full ${RECOMMENDATION_DOT_CLS[rec]}`} />
                    {RECOMMENDATION_LABELS[rec]}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <label className="mb-2 block text-[11px] font-semibold uppercase tracking-wider text-slate-700">
              Valuation
            </label>
            <div className="flex flex-wrap gap-1.5">
              {MOS_BUCKETS.map((b) => {
                const on = mosSet.has(b.id);
                return (
                  <button
                    key={b.id}
                    type="button"
                    onClick={() => toggleMos(b.id)}
                    className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset transition ${
                      on ? b.cls : 'bg-white text-slate-600 ring-slate-300 hover:bg-slate-50'
                    }`}
                  >
                    <span className={`inline-block h-1.5 w-1.5 rounded-full ${b.dot}`} />
                    {b.label}
                    <span className="text-[10px] opacity-60">{b.help}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <div className="mb-2 flex items-baseline justify-between">
              <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-700">
                Sectors
              </label>
              <span className="text-[11px] text-slate-400">
                {sectorSet.size === 0 ? 'All' : `${sectorSet.size} selected`}
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {sectors.map((s) => {
                const on = sectorSet.has(s);
                const sty = sectorStyle(s);
                return (
                  <button
                    key={s}
                    type="button"
                    onClick={() => toggleSector(s)}
                    className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset transition ${
                      on ? `${sty.bg} ${sty.fg} ${sty.ring}` : 'bg-white text-slate-600 ring-slate-300 hover:bg-slate-50'
                    }`}
                  >
                    <span
                      className="inline-block h-1.5 w-1.5 rounded-full"
                      style={{ backgroundColor: sty.dot }}
                    />
                    {s}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <footer className="flex items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-5 py-3">
          <button
            type="button"
            onClick={clearAll}
            className="rounded-md px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900"
          >
            Clear all
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md bg-slate-900 px-4 py-1.5 text-sm font-medium text-white hover:bg-slate-800"
          >
            View {filteredCount.toLocaleString()} stock{filteredCount === 1 ? '' : 's'}
          </button>
        </footer>
      </aside>
    </>
  );
}
