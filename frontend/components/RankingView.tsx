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
//   'ALL' → all rows                       (e.g. 902)
//   Any other code → empty (future expansion; tab stays SOON)
//
// Re-numbering: displayed `rank` is re-sequenced 1..N within the selected
// cohort. Composite SCORES are unchanged — a midcap that outscores a large-cap
// on the cross-sectional universe keeps its score, only the per-tab rank number
// is local. This is the pilot's explicit design intent.
//
// MidcapChip visibility: shown ONLY in the "All stocks" mixed view; hidden in
// the single-cohort tabs (the tab itself communicates the cohort).

import { useMemo, useState } from 'react';

import { CountryTabs } from '@/components/CountryTabs';
import { IndexTabs, type IndexCode } from '@/components/IndexTabs';
import RankingTable from '@/components/RankingTable';
import type { Metadata, StockSummary } from '@/lib/types';
import { universeLabel } from '@/lib/visual';

// Per-tab display config — label used in h1, description used in the count line.
type TabConfig = {
  h1: string;
  countLabel: string;
};

// Definitional sizes for indices that are PARTIAL overlaps with the S&P 900
// ingested universe. Used to render an honesty note under the count line.
// DJI = 30, NDX = 100. Any index whose full size equals our row count gets no note.
const FULL_INDEX_SIZE: Partial<Record<IndexCode, number>> = {
  DJI: 30,
  NDX: 100,
};

function tabConfig(code: IndexCode, universeCode: string): TabConfig {
  switch (code) {
    case 'SPX': return { h1: 'S&P 500 ranking',              countLabel: 'S&P 500 companies' };
    case 'MID': return { h1: 'S&P MidCap 400 ranking',       countLabel: 'S&P 400 mid-caps' };
    case 'DJI': return { h1: 'Dow 30 ranking',               countLabel: 'Dow 30 companies' };
    case 'NDX': return { h1: 'NASDAQ 100 ranking',           countLabel: 'NASDAQ 100 companies' };
    case 'ALL': return { h1: `${universeLabel(universeCode)} ranking`, countLabel: 'companies' };
    // For future tabs (SML / RUI / …) — should never be reachable as
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
  } else {
    // Not yet wired (future: SML / RUI / RUT / RUA / COMP).
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
  // 'ALL' is meaningful only when there is more than one cohort.
  if (memberships.size > 1) available.add('ALL');

  // Multi-index overlaps: a tab lights up purely because the loaded data has
  // rows carrying that code — no hardcoded membership here. Optional-chain so
  // legacy/empty index_memberships ([]) produces false without crashing.
  if (data.some((r) => r.index_memberships?.includes('dow30'))) available.add('DJI');
  if (data.some((r) => r.index_memberships?.includes('ndx'))) available.add('NDX');

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

  // MidcapChip is only shown in the "All stocks" mixed view.
  const showMidcapChip = safeTab === 'ALL';

  const cohortRows = useMemo(
    () => filterAndRerank(data, safeTab),
    [data, safeTab],
  );

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

      {/* Per-tab h1 + count header. Re-renders on tab switch (client-side). */}
      <header className="max-w-3xl space-y-3">
        <h1 className="text-balance font-slab text-3xl font-bold tracking-tight text-slate-900 dark:text-slate-100 sm:text-4xl">
          {cfg.h1}
        </h1>
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
          {safeTab === 'DJI' && (
            <span>
              {' '}All {FULL_INDEX_SIZE.DJI} Dow Jones Industrial Average members are
              S&amp;P 500 companies — this tab shows the complete Dow 30 cohort.
              Re-numbered 1..{cohortRows.length} within this cohort.
            </span>
          )}
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
        </p>
      </header>

      {/* Empty-universe fallback (first cron hasn't run, or a filtered cohort
          has no rows in this build artefact). */}
      {cohortRows.length === 0 ? (
        <div className="rounded border border-amber-200 bg-amber-50 p-6 text-center text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-900/30 dark:text-amber-200">
          <p className="font-medium">Compute pending.</p>
          <p className="mt-1">
            The first compute hasn&rsquo;t run yet. Scheduled cron: Mon-Fri
            22:00 UTC (after US market close), or trigger manually from the GitHub Actions tab.
          </p>
        </div>
      ) : (
        <RankingTable
          data={cohortRows}
          cohortSize={cohortRows.length}
          showMidcapChip={showMidcapChip}
        />
      )}
    </section>
  );
}
