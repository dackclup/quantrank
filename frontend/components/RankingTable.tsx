'use client';

import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';
import { SearchX } from 'lucide-react';

import { FilterDrawer } from '@/components/FilterDrawer';
import { LossChanceBadge } from '@/components/LossChanceBadge';
import {
  RECOMMENDATION_CHIP_DOTS,
  RECOMMENDATION_CHIP_TONES,
  RECOMMENDATION_LABELS,
  RecommendationBadge,
} from '@/components/RecommendationBadge';
import { ScoreBadge } from '@/components/ScoreBadge';
import { SectorChip } from '@/components/SectorChip';
import { StockLogo } from '@/components/StockLogo';
import {
  clearFilterSnapshot,
  loadFilterSnapshot,
  saveFilterSnapshot,
  type FilterSnapshot,
} from '@/lib/filter-storage';
import { parseFiltersFromUrl, writeFiltersToUrl } from '@/lib/filter-url';
import { formatMosPct } from '@/lib/format';
import type { Recommendation, StockSummary } from '@/lib/types';
import { useFlip } from '@/lib/useFlip';
import {
  MOS_BUCKETS,
  TIERS,
  getMosBucket,
  getTier,
  sectorStyle,
} from '@/lib/visual';

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
  // Filter state. Defaults are empty/full-range on SSR + first render
  // (avoids server/client markup mismatch); `useEffect` below rehydrates
  // from sessionStorage after mount so a user returning from a stock
  // detail page sees the same filters they left applied.
  const [search, setSearch] = useState('');
  const [sectorSet, setSectorSet] = useState<Set<string>>(() => new Set());
  const [scoreRange, setScoreRange] = useState<[number, number]>([0, 100]);
  const [tierSet, setTierSet] = useState<Set<string>>(() => new Set());
  const [mosSet, setMosSet] = useState<Set<string>>(() => new Set());
  const [recommendationSet, setRecommendationSet] = useState<Set<Recommendation>>(
    () => new Set(),
  );
  const [drawerOpen, setDrawerOpen] = useState(false);
  // `hydrated` gates the persist-on-change effect so we don't overwrite
  // the saved snapshot with the empty defaults during the first render
  // (the load effect runs after that initial render).
  const hydratedRef = useRef(false);

  // Rehydrate filters on mount (client-only, runs once). The URL query
  // string wins when present (a shared / bookmarked / reloaded filtered
  // view is an explicit intent); otherwise fall back to the within-tab
  // sessionStorage snapshot (return-from-detail navigation). A clean `/`
  // URL parses to `null`, so it never clobbers a restored snapshot.
  useEffect(() => {
    const saved = parseFiltersFromUrl() ?? loadFilterSnapshot();
    if (saved.search) setSearch(saved.search);
    if (saved.sectors.length > 0) setSectorSet(new Set(saved.sectors));
    if (saved.scoreRange[0] !== 0 || saved.scoreRange[1] !== 100) {
      setScoreRange(saved.scoreRange);
    }
    if (saved.tiers.length > 0) setTierSet(new Set(saved.tiers));
    if (saved.mos.length > 0) setMosSet(new Set(saved.mos));
    if (saved.recommendations.length > 0) {
      setRecommendationSet(new Set(saved.recommendations));
    }
    hydratedRef.current = true;
  }, []);

  // Sort + pagination
  const [sortKey, setSortKey] = useState<SortKey>('rank');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [page, setPage] = useState(1);

  const sectors = useMemo(() => {
    const s = new Set(data.map((d) => d.sector));
    return Array.from(s).sort();
  }, [data]);

  // Multi-axis filter: every active dimension AND-combines (a stock
  // has to match each non-empty filter to survive). Empty filters
  // pass everything through (sectorSet.size===0 means "all sectors").
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return data.filter((row) => {
      if (sectorSet.size > 0 && !sectorSet.has(row.sector)) return false;
      if (scoreRange[0] !== 0 || scoreRange[1] !== 100) {
        const sc = row.composite_score;
        if (sc == null || Number.isNaN(sc)) return false;
        if (sc < scoreRange[0] || sc > scoreRange[1]) return false;
      }
      if (tierSet.size > 0) {
        const t = getTier(row.composite_score);
        if (!t || !tierSet.has(t)) return false;
      }
      if (mosSet.size > 0) {
        const b = getMosBucket(row.margin_of_safety_pct);
        if (!b || !mosSet.has(b)) return false;
      }
      if (recommendationSet.size > 0) {
        if (!row.recommendation || !recommendationSet.has(row.recommendation)) {
          return false;
        }
      }
      if (!q) return true;
      return row.ticker.toLowerCase().includes(q) || row.name.toLowerCase().includes(q);
    });
  }, [data, search, sectorSet, scoreRange, tierSet, mosSet, recommendationSet]);

  // Reset page on any filter change so user doesn't end up on a
  // suddenly-empty page after narrowing results.
  useEffect(() => {
    setPage(1);
  }, [search, sectorSet, scoreRange, tierSet, mosSet, recommendationSet]);

  // Persist filter state on every change (post-hydration). Skipping the
  // initial render via `hydratedRef` avoids clobbering a saved snapshot
  // with empty defaults before the load effect has a chance to read it.
  // Mirror to BOTH sessionStorage (within-tab return nav) AND the URL
  // (shareable / bookmarkable view) so the two stay in sync; clearing the
  // last filter writes the bare pathname (no `?`).
  useEffect(() => {
    if (!hydratedRef.current) return;
    const snapshot: FilterSnapshot = {
      search,
      sectors: Array.from(sectorSet),
      scoreRange,
      tiers: Array.from(tierSet),
      mos: Array.from(mosSet),
      recommendations: Array.from(recommendationSet),
    };
    saveFilterSnapshot(snapshot);
    writeFiltersToUrl(snapshot);
  }, [search, sectorSet, scoreRange, tierSet, mosSet, recommendationSet]);

  const toggleSector = (s: string) =>
    setSectorSet((prev) => {
      const n = new Set(prev);
      if (n.has(s)) n.delete(s);
      else n.add(s);
      return n;
    });
  const toggleTier = (t: string) =>
    setTierSet((prev) => {
      const n = new Set(prev);
      if (n.has(t)) n.delete(t);
      else n.add(t);
      return n;
    });
  const toggleMos = (m: string) =>
    setMosSet((prev) => {
      const n = new Set(prev);
      if (n.has(m)) n.delete(m);
      else n.add(m);
      return n;
    });
  const toggleRecommendation = (rec: Recommendation) =>
    setRecommendationSet((prev) => {
      const n = new Set(prev);
      if (n.has(rec)) n.delete(rec);
      else n.add(rec);
      return n;
    });
  const clearAll = () => {
    setSearch('');
    setSectorSet(new Set());
    setScoreRange([0, 100]);
    setTierSet(new Set());
    setMosSet(new Set());
    setRecommendationSet(new Set());
    // Wipe the persisted snapshot too so a tab close → reopen lands on
    // the same clean state (otherwise the persist-on-change effect
    // would immediately re-save the defaults, which is correct but
    // wasteful — an explicit remove is the cleaner signal).
    clearFilterSnapshot();
  };

  const scoreActive = scoreRange[0] !== 0 || scoreRange[1] !== 100;
  // Aggregate count for the badge on the Filters button — one per
  // active dimension, not per active chip, so the user sees "2"
  // when they have any sectors + any tiers selected.
  const activeCount =
    (search ? 1 : 0) +
    (sectorSet.size ? 1 : 0) +
    (scoreActive ? 1 : 0) +
    (tierSet.size ? 1 : 0) +
    (mosSet.size ? 1 : 0) +
    (recommendationSet.size ? 1 : 0);

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

  // FLIP reshuffle ($impeccable overdrive) — when a FILTER / SEARCH change
  // reorders the visible rows, the surviving rows slide from their old
  // position to the new one (transform-only, 300ms, app ease-in-out,
  // reduced-motion guarded). Filter-scoped on purpose: a column-sort turns
  // over the whole paginated 50-row page, so a sort-triggered FLIP would fire
  // on <5% of rows and read as broken; a filter keeps survivors in the DOM, so
  // partial animation there is semantically correct ("the field responded").
  // `orderKey` re-runs the measure on ANY order change (sort / page silently
  // re-baseline); `filterKey` is what GATES the play. Both the desktop
  // <tbody> and the mobile <ul> get a hook; each animates only its visible
  // (non-zero-height) list, so the off-screen layout is a no-op.
  const orderKey = pageRows.map((r) => r.ticker).join(',');
  const filterKey = JSON.stringify([
    search,
    [...sectorSet].sort(),
    scoreRange,
    [...tierSet].sort(),
    [...mosSet].sort(),
    [...recommendationSet].sort(),
  ]);
  const tbodyFlipRef = useFlip<HTMLTableSectionElement>(orderKey, filterKey);
  const cardsFlipRef = useFlip<HTMLUListElement>(orderKey, filterKey);

  // Row stagger-entrance. The animate class is intentionally BAKED into the
  // static HTML (NOT gated behind a usePlayOnMount effect) so the rows start at
  // the `rise-in` keyframe's `from` state (opacity:0) from the very FIRST paint.
  // Why: on a static-export site the browser paints the static HTML BEFORE any
  // JS runs — so an effect that adds the animate class one frame after mount
  // leaves a window where the row is painted OPAQUE (no class yet) and then
  // snaps to invisible when the class lands (`fill-mode: both` applies `from`).
  // That snap is the refresh FLASH the user reported (2026-05-31, mobile). With
  // the class in the static HTML there is no opaque frame and no flash.
  //
  // Hydration-safe: `animateRows` derives ONLY from `safePage` (1) +
  // `firstRenderRef.current` (true) at first render, identical on the build-time
  // prerender and the client's hydration render (a fresh ref is `true` on both)
  // — so the same classes appear on both sides, no mismatch. reduced-motion is
  // still honored: globals.css `animation: none !important` disables the keyframe
  // AND its fill-mode, so rows render at their natural opacity:1 (content never
  // hidden). Plays on EVERY visit because a fresh mount (full load or client-nav
  // back to /) starts with a fresh `firstRenderRef = true`.
  //
  // "Play ONCE per mount, never on an in-page interaction" (design.md Motion
  // Rule 2): `firstRenderRef` is flipped false by an empty-dep effect that runs
  // ONCE after the first paint, BEFORE the user can interact — so EVERY later
  // render (sort / filter / search / paginate / the FLIP reshuffle) reads it as
  // false → no stagger class → the cascade never replays. This also keeps the
  // filter-driven FLIP slide the SOLE motion on a filter change (no entrance-fade
  // competing on rows that ENTER the filtered set). NOTE the precise mechanism:
  // an empty-dep MOUNT effect, NOT a filter-deps-watching effect — the latter
  // would fire AFTER each filtered render (too late, replaying the cascade once),
  // the anti-pattern the prior `interacted`-latch design warned about. The mount
  // effect fires before any interaction, so the gate is already spent by the time
  // the user does anything — a single uniform gate covering every path (including
  // the FilterDrawer-internal search box + score slider) with no per-handler wiring.
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
        // Keyboard parity for the click-to-sort header (2026-05-29 audit
        // S1 — WCAG 2.1.1 / 4.1.2). tabIndex makes the columnheader
        // focusable; Enter/Space activate the same sort. preventDefault on
        // Space stops the page from scrolling. aria-sort already announces
        // the current direction to screen readers; the global :focus-visible
        // ring (globals.css) supplies the visible focus indicator.
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
      {/* Toolbar: Filters button (with active count) + inline search + count */}
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setDrawerOpen(true)}
          className="inline-flex min-h-[44px] items-center gap-2 rounded-sm border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 press hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M2 4h12M4 8h8M6 12h4" strokeLinecap="round" />
          </svg>
          Filters
          {activeCount > 0 && (
            <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-sm bg-slate-900 px-1 text-[0.625rem] font-semibold text-white dark:bg-slate-100 dark:text-slate-900">
              {activeCount}
            </span>
          )}
        </button>
        <div className="relative min-w-[12.5rem] max-w-xs flex-1">
          <input
            type="search"
            placeholder="Search ticker or name…"
            aria-label="Search by ticker or company name"
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
        <div className="ml-auto text-xs text-slate-500 dark:text-slate-400">
          <span className="font-mono font-semibold tabular-nums text-slate-700 dark:text-slate-300">
            {sorted.length.toLocaleString()}
          </span>
          <span className="text-slate-500 dark:text-slate-400"> / {data.length.toLocaleString()} stocks</span>
        </div>
      </div>

      {/* Active filter chips — click any chip to remove that single
          filter; "Clear all" wipes everything. */}
      {activeCount > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {Array.from(sectorSet).map((s) => {
            const sty = sectorStyle(s);
            return (
              <button
                key={`f-sec-${s}`}
                type="button"
                onClick={() => toggleSector(s)}
                className={`inline-flex items-center gap-1.5 rounded-sm px-2 py-0.5 text-xs font-medium ring-1 ring-inset press hover:opacity-75 ${sty.bg} ${sty.fg} ${sty.ring}`}
              >
                <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ backgroundColor: sty.dot }} />
                {s}
                <span aria-hidden="true" className="opacity-60">×</span>
              </button>
            );
          })}
          {Array.from(tierSet).map((id) => {
            const t = TIERS.find((x) => x.id === id);
            return t ? (
              <button
                key={`f-tier-${id}`}
                type="button"
                onClick={() => toggleTier(id)}
                className={`inline-flex items-center gap-1.5 rounded-sm px-2 py-0.5 text-xs font-medium ring-1 ring-inset press hover:opacity-75 ${t.cls}`}
              >
                <span className={`inline-block h-1.5 w-1.5 rounded-full ${t.dot}`} />
                {t.label}
                <span aria-hidden="true" className="opacity-60">×</span>
              </button>
            ) : null;
          })}
          {Array.from(mosSet).map((id) => {
            const b = MOS_BUCKETS.find((x) => x.id === id);
            return b ? (
              <button
                key={`f-mos-${id}`}
                type="button"
                onClick={() => toggleMos(id)}
                className={`inline-flex items-center gap-1.5 rounded-sm px-2 py-0.5 text-xs font-medium ring-1 ring-inset press hover:opacity-75 ${b.cls}`}
              >
                <span className={`inline-block h-1.5 w-1.5 rounded-full ${b.dot}`} />
                {b.label}
                <span aria-hidden="true" className="opacity-60">×</span>
              </button>
            ) : null;
          })}
          {Array.from(recommendationSet).map((rec) => (
            <button
              key={`f-rec-${rec}`}
              type="button"
              onClick={() => toggleRecommendation(rec)}
              className={`inline-flex items-center gap-1.5 rounded-sm px-2 py-0.5 text-xs font-medium ring-1 ring-inset press hover:opacity-75 ${RECOMMENDATION_CHIP_TONES[rec]}`}
            >
              <span className={`inline-block h-1.5 w-1.5 rounded-full ${RECOMMENDATION_CHIP_DOTS[rec]}`} />
              {RECOMMENDATION_LABELS[rec]}
              <span aria-hidden="true" className="opacity-60">×</span>
            </button>
          ))}
          {scoreActive && (
            <button
              type="button"
              onClick={() => setScoreRange([0, 100])}
              className="inline-flex items-center gap-1.5 rounded-sm bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700 ring-1 ring-inset ring-slate-200 press hover:opacity-75 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700"
            >
              Score {scoreRange[0]}–{scoreRange[1]}
              <span aria-hidden="true" className="opacity-60">×</span>
            </button>
          )}
          <button
            type="button"
            onClick={clearAll}
            className="ml-1 press text-xs font-medium text-slate-500 underline-offset-2 hover:text-slate-900 hover:underline dark:text-slate-400 dark:hover:text-slate-100"
          >
            Clear all
          </button>
        </div>
      )}

      <FilterDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        state={{ search, sectorSet, scoreRange, tierSet, mosSet, recommendationSet }}
        setters={{
          setSearch,
          toggleSector,
          setScoreRange,
          toggleTier,
          toggleMos,
          toggleRecommendation,
          clearAll,
        }}
        sectors={sectors}
        totalCount={data.length}
        filteredCount={filtered.length}
      />

      {/* Desktop table (lg+). Portrait tablets (md→lg, 768–1023px) fall back
          to the card list below: the 7-col table needs ~700px but the md
          content area is only ~530px beside the sidebar, which clipped the
          Sector column (2026-05-29 layout-density audit). */}
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
              className={`hover-lift press min-h-[7rem] rounded border border-slate-200 bg-white transition-colors duration-100 hover:bg-slate-100 dark:border-slate-800 dark:bg-slate-900 dark:hover:bg-slate-800/50 ${staggerClass}`}
            >
              <Link
                href={`/stock/${row.ticker}/`}
                className="flex h-full flex-col gap-1 p-3"
              >
                {/* Mobile card header — mirrors the detail-page hero
                    cadence (frontend/app/stock/[ticker]/page.tsx:88-103):
                    rank pill + sector chip on the top line, then
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
                    supporting pill on the second line. Same shape on
                    both columns so the card stays balanced. */}
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
                        // (PRODUCT.md "calm, never urgent" + the "no gamified
                        // red-green" anti-reference). The ↗/↘ arrow is a non-color
                        // affordance so direction still reads without color (state
                        // is never color-only). Symmetric tokens also fix the prior
                        // asymmetry: globals.css softens bg-emerald-600 but has no
                        // bg-rose-600 remap, so the old down-pill rendered raw
                        // alarm-red while the up-pill was soft sage.
                        const pillCls = positive
                          ? 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:ring-emerald-800'
                          : 'bg-rose-50 text-rose-700 ring-rose-200 dark:bg-rose-900/30 dark:text-rose-300 dark:ring-rose-800';
                        const absCls = positive ? 'text-emerald-700' : 'text-rose-700';
                        // Derive absolute $ change from current_price +
                        // pct (the same identity CurrentPriceLine uses
                        // on the detail page: abs = price * pct / (100
                        // + pct)). Avoids adding a schema field for
                        // what is already implied by the two values
                        // already in StockSummary.
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
            </li>
          );
        })}
      </ul>

      {pageRows.length === 0 && (
        <div className="animate-fade-in flex flex-col items-center rounded border border-slate-200 bg-white px-6 py-10 text-center dark:border-slate-800 dark:bg-slate-900">
          {/* Empty-state delight ($impeccable delight): a REACHABLE moment (the
              user over-filtered to zero). Warm + helpful + professional, not
              wacky (finance = "read the room"): a muted anchor glyph + a human
              heading + an actionable nudge telling the user how to RECOVER, not
              just that they failed. The icon is decorative (aria-hidden) so the
              heading carries the meaning for SR; fade-in is reduced-motion
              guarded via the shared motion system. */}
          <SearchX
            aria-hidden="true"
            strokeWidth={1.5}
            className="mb-3 h-8 w-8 text-slate-300 dark:text-slate-600"
          />
          <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
            No stocks match those filters
          </p>
          <p className="mt-1 max-w-xs text-xs text-slate-500 dark:text-slate-400">
            Try a wider score range, or clear a sector or two.
          </p>
          {activeCount > 0 && (
            <button
              type="button"
              onClick={clearAll}
              className="mt-4 inline-flex min-h-[44px] items-center rounded-sm border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 press hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              Clear all filters
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
