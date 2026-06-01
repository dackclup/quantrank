'use client';

import { useEffect, useRef } from 'react';

import { DualRange } from '@/components/DualRange';
import {
  RECOMMENDATION_CHIP_DOTS,
  RECOMMENDATION_CHIP_TONES,
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

// Selected-state chip tones reuse the canonical
// `RECOMMENDATION_CHIP_TONES` + `RECOMMENDATION_CHIP_DOTS` exports
// from RecommendationBadge.tsx — one outlined-light pattern shared
// across the badge surface and the drawer-selection surface per
// SKILL.md Rule 2 (the 2026-05-14 user-feedback iteration retired
// the prior solid-fill pattern A in favor of one unified outlined-
// light family). Pre-2026-05-21 the drawer carried local solid-fill
// overrides (`bg-emerald-600 text-white` for bullish + `bg-red-500
// text-white` for cautious) — flagged by `frontend-design-reviewer`
// and consolidated here.

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

  const asideRef = useRef<HTMLElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  // Esc-to-close + body scroll lock + FOCUS TRAP while the drawer is open.
  // A modal dialog must contain keyboard focus (WCAG 2.4.3 / 2.1.2): on open
  // we remember the element that opened it, move focus into the drawer, and
  // cycle Tab/Shift+Tab within it; on close we restore focus to the trigger.
  // Without this, Tab escaped to the page behind the backdrop (audit P1).
  useEffect(() => {
    if (!open) return;
    triggerRef.current = document.activeElement as HTMLElement | null;
    const aside = asideRef.current;
    const focusables = (): HTMLElement[] =>
      aside
        ? Array.from(
            aside.querySelectorAll<HTMLElement>(
              'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
            ),
          ).filter((el) => el.offsetParent !== null)
        : [];
    // Move focus into the drawer (first focusable = the Close button).
    focusables()[0]?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      if (e.key !== 'Tab') return;
      const els = focusables();
      if (els.length === 0) return;
      const firstEl = els[0];
      const lastEl = els[els.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && active === firstEl) {
        e.preventDefault();
        lastEl.focus();
      } else if (!e.shiftKey && active === lastEl) {
        e.preventDefault();
        firstEl.focus();
      } else if (aside && active instanceof Node && !aside.contains(active)) {
        // Focus escaped the drawer (e.g. via the address bar) — pull it back.
        e.preventDefault();
        firstEl.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
      // Restore focus to whatever opened the drawer.
      triggerRef.current?.focus?.();
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
        ref={asideRef}
        role="dialog"
        aria-modal="true"
        aria-label="Filter stocks"
        className={`fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col bg-white shadow-overlay transition-transform duration-300 ease-in-out dark:bg-slate-900 ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-800">
          <div>
            <div className="text-[0.6875rem] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Filters
            </div>
            <div className="mt-0.5 font-mono text-sm tabular-nums">
              <span className="font-semibold text-slate-900 dark:text-slate-100">
                {filteredCount.toLocaleString()}
              </span>
              <span className="text-slate-500 dark:text-slate-400"> / {totalCount.toLocaleString()} stocks</span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close filters"
            className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-sm text-slate-500 transition-colors duration-150 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.75">
              <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
            </svg>
          </button>
        </header>

        <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5">
          <div>
            <label className="mb-2 block text-[0.6875rem] font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300">
              Search
            </label>
            <div className="relative">
              <input
                type="search"
                placeholder="Ticker or company name…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="min-h-[44px] w-full rounded-sm border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:placeholder-slate-500 dark:focus:border-slate-500 dark:focus:ring-slate-500"
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
          </div>

          <div>
            <div className="mb-2 flex items-baseline justify-between">
              <label className="text-[0.6875rem] font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300">
                Composite score
              </label>
              <span className="font-mono text-xs tabular-nums text-slate-700 dark:text-slate-300">
                {scoreRange[0]}–{scoreRange[1]}
              </span>
            </div>
            <DualRange min={0} max={100} value={scoreRange} onChange={setScoreRange} />
          </div>

          <div>
            <label className="mb-2 block text-[0.6875rem] font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300">
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
                    className={`inline-flex min-h-[44px] items-center gap-1.5 rounded-sm px-2.5 py-1 text-xs font-medium ring-1 ring-inset transition-colors lg:min-h-0 ${
                      on ? t.cls : 'bg-slate-100 text-slate-600 ring-slate-200 hover:bg-slate-50 dark:bg-slate-900 dark:text-slate-400 dark:ring-slate-700 dark:hover:bg-slate-800'
                    }`}
                  >
                    <span className={`inline-block h-1.5 w-1.5 rounded-full ${t.dot}`} />
                    {t.label}
                    <span className="font-mono text-[0.625rem] tabular-nums opacity-60">
                      {t.min}–{t.max === 101 ? '100' : t.max}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <label className="mb-2 block text-[0.6875rem] font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300">
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
                    className={`inline-flex min-h-[44px] items-center gap-1.5 rounded-sm px-2.5 py-1 text-xs font-medium ring-1 ring-inset transition-colors lg:min-h-0 ${
                      on
                        ? RECOMMENDATION_CHIP_TONES[rec]
                        : 'bg-slate-100 text-slate-600 ring-slate-200 hover:bg-slate-50 dark:bg-slate-900 dark:text-slate-400 dark:ring-slate-700 dark:hover:bg-slate-800'
                    }`}
                  >
                    <span className={`inline-block h-1.5 w-1.5 rounded-full ${RECOMMENDATION_CHIP_DOTS[rec]}`} />
                    {RECOMMENDATION_LABELS[rec]}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <label className="mb-2 block text-[0.6875rem] font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300">
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
                    className={`inline-flex min-h-[44px] items-center gap-1.5 rounded-sm px-2.5 py-1 text-xs font-medium ring-1 ring-inset transition-colors lg:min-h-0 ${
                      on ? b.cls : 'bg-slate-100 text-slate-600 ring-slate-200 hover:bg-slate-50 dark:bg-slate-900 dark:text-slate-400 dark:ring-slate-700 dark:hover:bg-slate-800'
                    }`}
                  >
                    <span className={`inline-block h-1.5 w-1.5 rounded-full ${b.dot}`} />
                    {b.label}
                    <span className="text-[0.625rem] opacity-60">{b.help}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <div className="mb-2 flex items-baseline justify-between">
              <label className="text-[0.6875rem] font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300">
                Sectors
              </label>
              <span className="text-[0.6875rem] text-slate-500 dark:text-slate-400">
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
                    className={`inline-flex min-h-[44px] items-center gap-1.5 rounded-sm px-2.5 py-1 text-xs font-medium ring-1 ring-inset transition-colors lg:min-h-0 ${
                      on ? `${sty.bg} ${sty.fg} ${sty.ring}` : 'bg-slate-100 text-slate-600 ring-slate-200 hover:bg-slate-50 dark:bg-slate-900 dark:text-slate-400 dark:ring-slate-700 dark:hover:bg-slate-800'
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

        <footer className="flex items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-5 py-3 dark:border-slate-800 dark:bg-slate-950">
          <button
            type="button"
            onClick={clearAll}
            className="inline-flex min-h-[44px] items-center rounded-sm px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors duration-150 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
          >
            Clear all
          </button>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex min-h-[44px] items-center rounded-sm bg-emerald-700 px-4 py-1.5 text-sm font-medium text-white transition-colors duration-150 hover:bg-emerald-800 dark:bg-emerald-600 dark:text-white dark:hover:bg-emerald-500"
          >
            View {filteredCount.toLocaleString()} stock{filteredCount === 1 ? '' : 's'}
          </button>
        </footer>
      </aside>
    </>
  );
}
