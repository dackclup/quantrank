'use client';

// RankingView — the interactive shell that wraps IndexTabs + h1/count header +
// RankingTable. Lives as a 'use client' component because it holds the
// selectedTab state.
//
// Architecture (PR 4 rework, 2026-06-16):
//   - app/ranking/page.tsx (Server Component) loads all ~902 rows + metadata at
//     BUILD TIME via getRankings() / getMetadata() and passes them here as props.
//     No fs-import occurs inside this client component (build-time-data rule).
//   - This component derives the cohort filter + re-numbered rank + tab
//     availability entirely in-browser from the passed data — static-export-safe
//     (no server round-trip on tab switch).
//   - RankingTable receives the filtered+re-ranked slice and a `cohortSize` so
//     its "X / N stocks" denominator reflects the selected cohort, not the
//     raw 902-row dataset.
//
// Tab / cohort mapping:
//   'SPX' → index_membership === 'sp500'  (large-caps, e.g. 502)
//   'MID' → index_membership === 'sp400'  (mid-caps, e.g. 400)
//   'SML' → index_membership === 'sp600'  (small-caps, e.g. 600, Slice 6)
//   'ALL' → all rows                       (e.g. 902 sp900 / 1502 sp1500)
//   Any other code → empty (future expansion; tab stays SOON)
//
// Re-numbering: displayed `rank` is re-sequenced 1..N within the selected
// cohort. Composite SCORES are unchanged — a smallcap that outscores a large-cap
// on the cross-sectional universe keeps its score, only the per-tab rank number
// is local. This is the pilot's explicit design intent.
//
// MidcapChip / SmallcapChip visibility: shown ONLY in the "All stocks" mixed
// view; hidden in single-cohort tabs (the tab itself communicates the cohort).

import { useMemo, useState } from 'react';
import { SlidersHorizontal } from 'lucide-react';

import { Chip } from '@/components/Chip';
import { CountryTabs } from '@/components/CountryTabs';
import {
  countActiveFilters,
  EMPTY_FILTERS,
  FilterDrawer,
  type RankingFilters,
} from '@/components/FilterDrawer';
import { IndexTabs, type IndexCode } from '@/components/IndexTabs';
import RankingTable, { type SortDir, type SortKey } from '@/components/RankingTable';
import type { Metadata, StockSummary } from '@/lib/types';
import { universeLabel } from '@/lib/visual';

// Sort keys exposed by the visible sort-chip row. These are a 3-key SUBSET of
// RankingTable's full SortKey union (the column headers still expose all 8);
// the chip row binds to the same lifted sort state so the two stay in sync.
type ChipSortKey = Extract<SortKey, 'rank' | 'composite_score' | 'loss_chance_pct'>;

const SORT_CHIPS: { key: ChipSortKey; label: string }[] = [
  { key: 'rank', label: 'Rank' },
  { key: 'composite_score', label: 'Score' },
  { key: 'loss_chance_pct', label: 'Loss chance' },
];

// Per-tab display config — label used in h1, description used in the count line.
type TabConfig = {
  h1: string;
  countLabel: string;
};

// Definitional sizes for indices that are PARTIAL overlaps with the S&P 900
// ingested universe. Used to render an honesty note under the count line.
// DJI = 30, NDX = 100, RUI = 1000. Any index whose full size equals our row count gets no note.
const FULL_INDEX_SIZE: Partial<Record<IndexCode, number>> = {
  DJI: 30,
  NDX: 100,
  RUI: 1000,
};

function tabConfig(code: IndexCode, universeCode: string): TabConfig {
  switch (code) {
    case 'SPX': return { h1: 'S&P 500 ranking',              countLabel: 'S&P 500 companies' };
    case 'MID': return { h1: 'S&P MidCap 400 ranking',       countLabel: 'S&P 400 mid-caps' };
    case 'SML': return { h1: 'S&P SmallCap 600 ranking',     countLabel: 'S&P 600 small-caps' };
    case 'DJI': return { h1: 'Dow 30 ranking',               countLabel: 'Dow 30 companies' };
    case 'NDX': return { h1: 'NASDAQ 100 ranking',           countLabel: 'NASDAQ 100 companies' };
    case 'RUI': return { h1: 'Russell 1000 ranking',         countLabel: 'Russell 1000 companies' };
    case 'ALL': return { h1: `${universeLabel(universeCode)} ranking`, countLabel: 'companies' };
    // For future tabs (RUT / RUA / COMP / …) — should never be reachable as
    // active while still SOON, but guard defensively.
    default:    return { h1: 'Ranking',                      countLabel: 'companies' };
  }
}

// Filter + re-rank data for the selected tab.
// Returns a new array with rank re-numbered 1..N; original data is not mutated.
// Objects are reused (shallow copy of the array only) for render performance.
function filterAndRerank(data: StockSummary[], code: IndexCode): StockSummary[] {
  let filtered: StockSummary[];
  if (code === 'ALL') {
    filtered = data;
  } else if (code === 'SPX') {
    filtered = data.filter((r) => r.index_membership === 'sp500');
  } else if (code === 'MID') {
    filtered = data.filter((r) => r.index_membership === 'sp400');
  } else if (code === 'DJI') {
    // Dow 30 overlap: all 30 Dow members are S&P 500 companies.
    // Optional-chain so legacy/empty index_memberships ([]) yields empty → tab stays SOON.
    filtered = data.filter((r) => r.index_memberships?.includes('dow30'));
  } else if (code === 'NDX') {
    // NASDAQ 100 overlap: of the 100 members, only those also in the S&P 900
    // ingested universe are tagged 'ndx' (the exact count is data-driven and
    // surfaced in the "N of 100" note below).
    // Optional-chain so legacy/empty index_memberships ([]) yields empty → tab stays SOON.
    filtered = data.filter((r) => r.index_memberships?.includes('ndx'));
  } else if (code === 'SML') {
    // S&P 600 SmallCap (Slice 6): filter to index_membership === 'sp600'.
    // Produces an empty array on the current sp900 dataset (no sp600 rows yet)
    // → tab stays SOON until the Slice 7 cron flip populates sp600 rows.
    filtered = data.filter((r) => r.index_membership === 'sp600');
  } else if (code === 'RUI') {
    // Russell 1000 overlap: the entire S&P 900 universe falls within the
    // Russell 1000 (the 1000 largest US companies by market cap). The
    // remaining ~98-100 Russell 1000 members are companies below our S&P 900
    // ingestion line that we don't ingest. The "N of 1000" honesty note
    // below surfaces the partial-overlap count.
    // Optional-chain so legacy/empty index_memberships ([]) yields empty → tab stays SOON.
    filtered = data.filter((r) => r.index_memberships?.includes('russell1000'));
  } else {
    // Not yet wired (future: RUT / RUA / COMP).
    filtered = [];
  }

  // Re-sequence rank 1..N in the order already established by the
  // compute layer (which sorts by composite_score DESC within the full
  // 902-universe). Within each cohort that order is preserved, so the
  // re-numbered ranks are a clean 1..N cross-section.
  return filtered.map((row, i) => ({ ...row, rank: i + 1 }));
}

// Compute which IndexCode values actually have data in the loaded dataset.
// 'ALL' is available iff the dataset has more than one distinct membership
// value (i.e. it is a mixed universe, not a pure sp500-only run).
// DJI / NDX are available iff ≥1 row carries their code in index_memberships.
function computeAvailableCodes(data: StockSummary[]): ReadonlySet<IndexCode> {
  const memberships = new Set(data.map((r) => r.index_membership));
  const available = new Set<IndexCode>();

  if (memberships.has('sp500')) available.add('SPX');
  if (memberships.has('sp400')) available.add('MID');
  // SML: available iff ≥1 row has index_membership === 'sp600'.
  // Stays absent on the current sp900 dataset (no sp600 rows) so the SML tab
  // remains "SOON" until the Slice 7 cron flip produces sp600 membership rows.
  if (memberships.has('sp600')) available.add('SML');
  // 'ALL' is meaningful only when there is more than one distinct cohort.
  if (memberships.size > 1) available.add('ALL');

  // Multi-index overlaps: a tab lights up purely because the loaded data has
  // rows carrying that code — no hardcoded membership here. Optional-chain so
  // legacy/empty index_memberships ([]) produces false without crashing.
  if (data.some((r) => r.index_memberships?.includes('dow30'))) available.add('DJI');
  if (data.some((r) => r.index_memberships?.includes('ndx'))) available.add('NDX');
  if (data.some((r) => r.index_memberships?.includes('russell1000'))) available.add('RUI');

  return available;
}

export function RankingView({
  data,
  meta,
}: {
  data: StockSummary[];
  meta: Metadata;
}) {
  // Default selected tab = 'ALL' (All stocks — the mixed-universe landing
  // view). Falls back to 'SPX' via `safeTab` below when the loaded data is
  // single-cohort (sp500-only), where 'ALL' is not in `availableCodes`.
  const [activeTab, setActiveTab] = useState<IndexCode>('ALL');

  // Lifted sort state (shared by the visible sort-chip row + RankingTable's
  // column headers — ONE source of truth). Defaults match RankingTable's prior
  // internal defaults (rank ascending).
  const [sortKey, setSortKey] = useState<SortKey>('rank');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  // FilterDrawer state: committed `filters` feed the row pipeline; `draft` is
  // edited inside the drawer and committed on Apply (draft-state pattern).
  const [filters, setFilters] = useState<RankingFilters>(EMPTY_FILTERS);
  const [draft, setDraft] = useState<RankingFilters>(EMPTY_FILTERS);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const availableCodes = useMemo(() => computeAvailableCodes(data), [data]);

  // If the default tab has no data (e.g. an empty build artefact), fall back to
  // whatever is available first.
  const safeTab: IndexCode = availableCodes.has(activeTab)
    ? activeTab
    : availableCodes.has('SPX')
      ? 'SPX'
      : availableCodes.size > 0
        ? [...availableCodes][0]
        : 'SPX';

  // MidcapChip / SmallcapChip are only shown in the "All stocks" mixed view —
  // in a single-cohort tab (SPX / MID / SML) the tab header already communicates
  // the cohort, so the per-row chip would be redundant noise.
  const showMidcapChip = safeTab === 'ALL';
  const showSmallcapChip = safeTab === 'ALL';

  const cohortRows = useMemo(
    () => filterAndRerank(data, safeTab),
    [data, safeTab],
  );

  // Distinct GICS sectors present in the CURRENT cohort, sourced from the real
  // loaded rows (never a hardcoded list). Sorted alphabetically for a stable
  // chip order; empties skipped.
  const cohortSectors = useMemo(() => {
    const set = new Set<string>();
    for (const row of cohortRows) {
      if (row.sector) set.add(row.sector);
    }
    return [...set].sort((a, b) => a.localeCompare(b));
  }, [cohortRows]);

  // Apply the committed drawer filters to the cohort. Keeps `rank` as already
  // re-numbered by filterAndRerank (the rank column stays the cohort rank, not
  // a post-filter re-sequence — matches the handoff, which filters without
  // re-ranking). Search is applied DOWNSTREAM inside RankingTable.
  const filteredRows = useMemo(() => {
    let rows = cohortRows;
    if (filters.undervalued) {
      rows = rows.filter(
        (r) => r.margin_of_safety_pct != null && r.margin_of_safety_pct >= 0,
      );
    }
    if (filters.strongOnly) {
      rows = rows.filter((r) => r.composite_score >= 55);
    }
    if (filters.sectors.length > 0) {
      rows = rows.filter((r) => filters.sectors.includes(r.sector));
    }
    return rows;
  }, [cohortRows, filters]);

  const activeFilterCount = countActiveFilters(filters);

  // Sort-chip handler — shares the same lifted state the column headers drive.
  // Re-tap on the active chip flips direction; a new key picks a sensible
  // default direction (composite_score / loss desc; rank asc).
  const onSortChip = (key: ChipSortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir(key === 'rank' ? 'asc' : 'desc');
    }
  };

  const openDrawer = () => {
    setDraft(filters);
    setDrawerOpen(true);
  };

  const cfg = tabConfig(safeTab, meta.universe);

  return (
    <section className="space-y-6">
      {/* Two-tier market selector: country row + index row. Grouped tightly
          so they read as one control unit. CountryTabs has no client state
          so it is safe to call from a 'use client' component. */}
      <div className="space-y-3">
        <CountryTabs />
        <IndexTabs
          activeTab={safeTab}
          availableCodes={availableCodes}
          onTabChange={setActiveTab}
        />
      </div>

      {/* Per-tab h1 + count header. Re-renders on tab switch (client-side).
          R-8: the h1 and the cohort "N / M stocks" count sit on the SAME
          horizontal row (handoff layout); the Filters button trails on the
          right. Wraps to stacked on narrow widths. */}
      <header className="max-w-3xl space-y-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <h1 className="text-balance font-slab text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100 sm:text-4xl">
            {cfg.h1}
          </h1>
          {/* Same-row count: filtered N out of cohort M. tabular-nums so the
              digits don't jitter as the filter narrows. Shown ONLY when a
              drawer filter is active — otherwise it duplicates the unfiltered
              cohort count already in the descriptive caption below (avoids the
              "502 / 502" triple-count on the default view). */}
          {activeFilterCount > 0 && (
            <span className="text-sm text-slate-500 dark:text-slate-400">
              <span className="font-mono font-semibold tabular-nums text-emerald-800 dark:text-emerald-300">
                {filteredRows.length.toLocaleString()}
              </span>
              <span className="font-mono tabular-nums"> / {cohortRows.length.toLocaleString()}</span>{' '}
              stocks
            </span>
          )}
          <button
            type="button"
            onClick={openDrawer}
            aria-haspopup="dialog"
            aria-expanded={drawerOpen}
            className={`press ml-auto inline-flex min-h-[44px] items-center gap-2 rounded-sm border px-3 py-1.5 text-sm font-medium ${
              activeFilterCount > 0
                ? 'border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100 dark:border-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300 dark:hover:bg-emerald-900/50'
                : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800'
            }`}
          >
            <SlidersHorizontal aria-hidden="true" strokeWidth={1.75} className="h-4 w-4" />
            Filters
            {activeFilterCount > 0 && (
              <span className="font-mono tabular-nums">· {activeFilterCount}</span>
            )}
          </button>
        </div>
        <p className="max-w-2xl text-pretty text-base text-slate-600 dark:text-slate-300">
          {/* Count reflects the selected cohort, not the raw dataset size. */}
          <span className="font-mono font-semibold tabular-nums text-emerald-800 dark:text-emerald-300">
            {cohortRows.length.toLocaleString()}
          </span>{' '}
          {cfg.countLabel}, ranked by an 8-pillar composite score.
        </p>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          <span className="font-mono">{meta.universe}</span>
          {' · updated '}
          <span className="font-mono">{meta.last_update_utc}</span>
          {' · schema '}
          <span className="font-mono">{meta.version}</span>
        </p>
        <p className="max-w-2xl text-pretty text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          Composite is the 8-pillar weighted score (quality, value, growth,
          momentum, health, profitability, technical, risk).{' '}
          <span className="font-mono">sentiment</span> and{' '}
          <span className="font-mono">ml</span> pillars are reserved for a
          later phase; their 0.20 weight is redistributed pro-rata across the
          active pillars. Risk-overlay flags annotate; flagged tickers cannot
          earn the entered-top-5 badge even at rank #1 by composite.
          {safeTab === 'MID' && (
            <span>
              {' '}Composite scores are cross-sectional (midcaps ranked against
              large-caps in the full universe), so a midcap can outrank a
              large-cap. Re-numbered 1..{cohortRows.length} within this cohort.
            </span>
          )}
          {safeTab === 'SML' && (
            <span>
              {' '}Composite scores are cross-sectional (small-caps ranked against
              large- and mid-caps in the full universe), so a small-cap can outrank
              a large-cap. Re-numbered 1..{cohortRows.length} within this cohort.
            </span>
          )}
          {safeTab === 'DJI' && (() => {
            const full = FULL_INDEX_SIZE.DJI ?? 30;
            const isPartial = cohortRows.length < full;
            return (
              <span>
                {isPartial
                  ? ` ${cohortRows.length} of ${full} Dow Jones Industrial Average members — the rest aren't in the ingested universe yet (partial overlap).`
                  : ` All ${full} Dow Jones Industrial Average members are S&P 500 companies — the complete Dow 30 cohort.`}
                {' '}Re-numbered 1..{cohortRows.length} within this cohort.
              </span>
            );
          })()}
          {safeTab === 'NDX' && (() => {
            const full = FULL_INDEX_SIZE.NDX ?? 100;
            const isPartial = cohortRows.length < full;
            return (
              <span>
                {isPartial
                  ? ` ${cohortRows.length} of ${full} NASDAQ‑100 members — the rest aren’t in the S&P 900 ingested universe yet (partial overlap).`
                  : ` All ${full} NASDAQ‑100 members are represented in the ingested universe.`}
                {' '}Re-numbered 1..{cohortRows.length} within this cohort.
              </span>
            );
          })()}
          {safeTab === 'RUI' && (() => {
            const full = FULL_INDEX_SIZE.RUI ?? 1000;
            const isPartial = cohortRows.length < full;
            return (
              <span>
                {isPartial
                  ? ` ${cohortRows.length} of ${full} Russell 1000 members — the entire S&P 900 universe falls within the Russell 1000 (the 1000 largest US companies by market cap); the rest aren’t in our ingested universe (partial overlap).`
                  : ` All ${full} Russell 1000 members are represented in the ingested universe.`}
                {' '}Re-numbered 1..{cohortRows.length} within this cohort.
              </span>
            );
          })()}
        </p>
      </header>

      {/* R-3: visible sort-chip row — a fast affordance for the 3 headline
          sorts (Rank · Score · Loss chance), bound to the SAME lifted sort
          state the column headers drive. Active chip = emerald outlined-light
          chip + leading dot (the handoff `tone={active?'emerald':'slate'}
          dot={active}` treatment). The column-header sort still works for the
          other keys. Hidden when the cohort is empty (the compute-pending
          panel takes over). */}
      {cohortRows.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-slate-500 dark:text-slate-400">Sort</span>
          {SORT_CHIPS.map(({ key, label }) => {
            const active = sortKey === key;
            return (
              <button
                key={key}
                type="button"
                aria-pressed={active}
                onClick={() => onSortChip(key)}
                className="press inline-flex min-h-[44px] items-center rounded-sm"
              >
                <Chip
                  tone={
                    active
                      ? 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:ring-emerald-800'
                      : 'bg-white text-slate-600 ring-slate-200 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-700 dark:hover:bg-slate-800'
                  }
                  dot={active ? 'bg-emerald-500 dark:bg-emerald-400' : undefined}
                  size="md"
                >
                  {label}
                </Chip>
              </button>
            );
          })}
        </div>
      )}

      {/* Empty-universe fallback (first cron hasn't run, or a filtered cohort
          has no rows in this build artefact). */}
      {cohortRows.length === 0 ? (
        <div className="rounded border border-amber-200 bg-amber-50 p-6 text-center text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-200">
          <p className="font-medium">No rankings yet</p>
          <p className="mt-1">
            The first compute run hasn&rsquo;t finished. It runs Mon–Fri at
            22:00 UTC, after US markets close — or trigger it from the GitHub
            Actions tab.
          </p>
        </div>
      ) : (
        <RankingTable
          data={filteredRows}
          cohortSize={cohortRows.length}
          showMidcapChip={showMidcapChip}
          showSmallcapChip={showSmallcapChip}
          sortKey={sortKey}
          sortDir={sortDir}
          onSortChange={(key, dir) => {
            setSortKey(key);
            setSortDir(dir);
          }}
          hasActiveFilters={activeFilterCount > 0}
          onClearFilters={() => setFilters(EMPTY_FILTERS)}
        />
      )}

      {/* FilterDrawer (authorized re-introduction) — the one floating-overlay
          surface. Draft-state: edits stay in `draft` until Apply commits. */}
      <FilterDrawer
        open={drawerOpen}
        draft={draft}
        sectors={cohortSectors}
        onClose={() => setDrawerOpen(false)}
        onChangeDraft={setDraft}
        onReset={() => setDraft(EMPTY_FILTERS)}
        onApply={() => {
          setFilters(draft);
          setDrawerOpen(false);
        }}
      />
    </section>
  );
}
