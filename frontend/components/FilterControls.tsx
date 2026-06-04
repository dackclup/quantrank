'use client';

import type { CSSProperties } from 'react';

import { DualRange } from '@/components/DualRange';
import {
  RECOMMENDATION_CHIP_DOTS,
  RECOMMENDATION_CHIP_TONES,
  RECOMMENDATION_LABELS,
  RECOMMENDATION_VALUES,
} from '@/components/RecommendationBadge';
import type { Recommendation } from '@/lib/types';
import { ACTIVE_FILTER_CHIP_TONE, MOS_BUCKETS, TIERS, sectorStyle } from '@/lib/visual';

// The shared filter BODY — the "Active filters" remove-one summary strip + search
// + dual-range composite-score slider + score-tier / recommendation / valuation /
// sector chips. Rendered by BOTH the mobile `FilterDrawer` (modal shell, < lg) and
// the desktop `FilterRail` (persistent left rail, lg+) so the six filter groups
// live in ONE place. The controlled-view pattern: `state` + `setters` are owned by
// RankingTable and threaded through both shells.
//
// Selected-state chip tones reuse the canonical `RECOMMENDATION_CHIP_TONES` /
// `RECOMMENDATION_CHIP_DOTS` (SKILL.md Rule 2 — one outlined-light family across the
// badge + selection surfaces). Every toggle carries `min-h-[44px]` (mobile touch
// target) + `lg:min-h-0` (compact on the desktop rail and the lg+ drawer). Unselected
// chips use the `dark:bg-slate-800` fill that matches the active-summary chips in both
// themes (the #401 dark-mode fix — slate-900 had vanished into the panel).

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

const UNSELECTED_CHIP =
  'bg-slate-100 text-slate-600 ring-slate-200 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700 dark:hover:bg-slate-700';

// Toggle chip className composer. The SELECTED state needs a clear,
// color-INDEPENDENT signal: the pale tone tint alone vanished in dark mode and
// was indistinguishable for the slate-toned options (Near fair / Hold), where
// "selected" used the same slate as "unselected" — a user couldn't tell a chip
// was on ($impeccable round 3, user-chosen "heavier ring + bold, no checkmark").
// Selected = the chip's tone tint + bold label + a 2px NEUTRAL inset ring drawn
// via `box-shadow`. box-shadow (not a Tailwind `ring-*`) sidesteps the
// globals.css soft-color override that remaps every `ring-*` color, so the
// selected ring is reliable and the SAME on every tone. slate-400 reads on both
// the light pale tint and the dark slate-800 surface, so one value covers both
// themes. Unselected keeps the thin pale `ring-1`.
const TOGGLE_BASE =
  'inline-flex min-h-[44px] items-center gap-1.5 rounded-sm px-2.5 py-1 text-xs press lg:min-h-0';
const TOGGLE_OFF = `ring-1 ring-inset font-medium ${UNSELECTED_CHIP}`;
const TOGGLE_ON = 'font-semibold [box-shadow:inset_0_0_0_2px_rgb(148,163,184)]';

function toggleChipClass(on: boolean, tone: string): string {
  return `${TOGGLE_BASE} ${on ? `${tone} ${TOGGLE_ON}` : TOGGLE_OFF}`;
}


export function FilterControls({
  state,
  setters,
  sectors,
  className = '',
}: {
  state: FilterState;
  setters: FilterSetters;
  sectors: string[];
  className?: string;
}) {
  const { search, sectorSet, scoreRange, tierSet, mosSet, recommendationSet } = state;
  const { setSearch, toggleSector, setScoreRange, toggleTier, toggleMos, toggleRecommendation } =
    setters;

  // Active-filter summary chips — the remove-ONE path (each × reuses the SAME setter
  // the per-group toggle uses). Score is "active" only when narrowed from the full
  // [0, 100]. "Clear all" (the shell footer) stays the remove-EVERYTHING path.
  const scoreActive = scoreRange[0] !== 0 || scoreRange[1] !== 100;
  // Each typed chip carries its colored leading dot (or the sector inline-rgb
  // `dotStyle`) so the neutral-body summary still reads its per-type identity at
  // a glance — the ONE active-filter chip language shared with the RankingTable
  // toolbar (`ACTIVE_FILTER_CHIP_TONE`). search / score have no type, so no dot.
  const activeChips: {
    key: string;
    label: string;
    onRemove: () => void;
    dot?: string;
    dotStyle?: CSSProperties;
  }[] = [];
  if (search.trim())
    activeChips.push({ key: 'search', label: `Search: ${search.trim()}`, onRemove: () => setSearch('') });
  if (scoreActive)
    activeChips.push({
      key: 'score',
      label: `Score ${scoreRange[0]}–${scoreRange[1]}`,
      onRemove: () => setScoreRange([0, 100]),
    });
  for (const id of tierSet)
    activeChips.push({
      key: `tier:${id}`,
      label: TIERS.find((t) => t.id === id)?.label ?? id,
      dot: TIERS.find((t) => t.id === id)?.dot,
      onRemove: () => toggleTier(id),
    });
  for (const id of mosSet)
    activeChips.push({
      key: `mos:${id}`,
      label: MOS_BUCKETS.find((b) => b.id === id)?.label ?? id,
      dot: MOS_BUCKETS.find((b) => b.id === id)?.dot,
      onRemove: () => toggleMos(id),
    });
  for (const rec of recommendationSet)
    activeChips.push({
      key: `rec:${rec}`,
      label: RECOMMENDATION_LABELS[rec],
      dot: RECOMMENDATION_CHIP_DOTS[rec],
      onRemove: () => toggleRecommendation(rec),
    });
  for (const s of sectorSet)
    activeChips.push({
      key: `sector:${s}`,
      label: s,
      dotStyle: { backgroundColor: sectorStyle(s).dot },
      onRemove: () => toggleSector(s),
    });

  return (
    <div className={`space-y-6 ${className}`}>
      {activeChips.length > 0 && (
        <div>
          <div className="mb-2 flex items-baseline justify-between">
            {/* <span>, not <label> — section heading for a GROUP of removable
                buttons, not a label for a single form control. */}
            <span className="text-[0.6875rem] font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300">
              Active filters
            </span>
            <span className="font-mono text-[0.6875rem] tabular-nums text-slate-500 dark:text-slate-400">
              {activeChips.length}
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {activeChips.map((chip) => (
              <button
                key={chip.key}
                type="button"
                onClick={chip.onRemove}
                aria-label={`Remove filter: ${chip.label}`}
                className={`group inline-flex min-h-[44px] items-center gap-1.5 rounded-sm px-2.5 py-1 text-xs font-medium ring-1 ring-inset press hover:opacity-75 lg:min-h-0 ${ACTIVE_FILTER_CHIP_TONE}`}
              >
                {/* Exactly one of `dot` (class — tier/mos/rec) or `dotStyle` (inline
                    rgb — sector) is set per chip; search/score set neither. */}
                {chip.dot && (
                  <span className={`inline-block h-1.5 w-1.5 rounded-full ${chip.dot}`} aria-hidden="true" />
                )}
                {chip.dotStyle && (
                  <span className="inline-block h-1.5 w-1.5 rounded-full" style={chip.dotStyle} aria-hidden="true" />
                )}
                {chip.label}
                <svg
                  aria-hidden="true"
                  width="12"
                  height="12"
                  viewBox="0 0 20 20"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  className="text-slate-400 group-hover:text-slate-600 dark:text-slate-500 dark:group-hover:text-slate-300"
                >
                  <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
                </svg>
              </button>
            ))}
          </div>
        </div>
      )}

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
                className={toggleChipClass(on, t.cls)}
              >
                <span className={`inline-block h-1.5 w-1.5 rounded-full ${t.dot}`} />
                {t.label}
                <span className="font-mono text-[0.6875rem] tabular-nums">
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
                className={toggleChipClass(on, RECOMMENDATION_CHIP_TONES[rec])}
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
                className={toggleChipClass(on, b.cls)}
              >
                <span className={`inline-block h-1.5 w-1.5 rounded-full ${b.dot}`} />
                {b.label}
                <span className="text-[0.6875rem]">{b.help}</span>
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
                className={toggleChipClass(on, `${sty.bg} ${sty.fg} ${sty.ring}`)}
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
  );
}
