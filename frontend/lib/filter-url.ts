/**
 * URL query-param serialization of the ranking-table filter state — the
 * shareable / bookmarkable counterpart to the session-scoped
 * `filter-storage.ts`. A populated filtered view (e.g. Financials + Strong
 * tier + Lean Bullish) round-trips through the URL, so a power user can
 * bookmark it, share the link, or reload without losing the filters
 * (critique P2 — Nielsen H7 "Flexibility & efficiency of use").
 *
 * Why `window.history.replaceState` + `window.location.search` (NOT
 * `next/navigation` `useSearchParams`): Next.js 14 static export requires a
 * `<Suspense>` boundary around `useSearchParams()` (see filter-storage.ts
 * header). This client-only read/write path needs no Suspense, no Next
 * router, and no extra build boilerplate. `replaceState` (not `pushState`)
 * keeps filter toggles OUT of the browser back-stack — a filter change is
 * not a navigation step.
 *
 * Precedence (RankingTable mount): the URL wins (a shared/bookmarked link is
 * an explicit intent), else fall back to the sessionStorage snapshot (a
 * within-tab return from a detail page). The persist effect writes BOTH on
 * every change so they stay in sync.
 *
 * Param scheme — every key omitted at its empty/default value:
 *   q=<search>  ·  sector=<csv>  ·  score=<min>-<max>  ·  tier=<csv>  ·
 *   mos=<csv>  ·  rec=<csv>
 * Unknown sector/tier/mos values are harmless — the table's filter
 * predicates simply match nothing for them (no crash). `rec` values are
 * validated against the known recommendation set so the typed
 * `Recommendation[]` holds.
 */

import type { FilterSnapshot } from '@/lib/filter-storage';
import type { Recommendation } from '@/lib/types';

const PARAM_KEYS = ['q', 'sector', 'score', 'tier', 'mos', 'rec'] as const;

const VALID_RECOMMENDATIONS: ReadonlySet<Recommendation> = new Set([
  'bullish',
  'lean_bullish',
  'neutral',
  'cautious',
]);

function csv(raw: string | null): string[] {
  if (!raw) return [];
  return raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
}

function parseScoreRange(raw: string | null): [number, number] {
  const m = raw?.match(/^(\d{1,3})-(\d{1,3})$/);
  if (!m) return [0, 100];
  const lo = Number(m[1]);
  const hi = Number(m[2]);
  if (lo < 0 || hi > 100 || lo > hi) return [0, 100];
  return [lo, hi];
}

/**
 * Parse filter state from the current URL query string. Returns `null` when
 * NO filter param is present (the caller then falls back to sessionStorage),
 * so a clean `/` URL never overrides a restored within-tab snapshot.
 */
export function parseFiltersFromUrl(): FilterSnapshot | null {
  if (typeof window === 'undefined') return null;
  const params = new URLSearchParams(window.location.search);
  if (!PARAM_KEYS.some((k) => params.has(k))) return null;
  return {
    search: params.get('q') ?? '',
    sectors: csv(params.get('sector')),
    scoreRange: parseScoreRange(params.get('score')),
    tiers: csv(params.get('tier')),
    mos: csv(params.get('mos')),
    recommendations: csv(params.get('rec')).filter(
      (r): r is Recommendation => VALID_RECOMMENDATIONS.has(r as Recommendation),
    ),
  };
}

/**
 * Mirror the filter snapshot into the URL query string via
 * `history.replaceState`. Omits every key at its default, so a cleared
 * filter set returns the bare pathname (no `?`). Silently no-ops on SSR or a
 * disabled History API — URL sync is convenience, never a throw out of the
 * user's flow.
 */
export function writeFiltersToUrl(s: FilterSnapshot): void {
  if (typeof window === 'undefined') return;
  const params = new URLSearchParams();
  if (s.search.trim()) params.set('q', s.search.trim());
  if (s.sectors.length) params.set('sector', s.sectors.join(','));
  if (s.scoreRange[0] !== 0 || s.scoreRange[1] !== 100) {
    params.set('score', `${s.scoreRange[0]}-${s.scoreRange[1]}`);
  }
  if (s.tiers.length) params.set('tier', s.tiers.join(','));
  if (s.mos.length) params.set('mos', s.mos.join(','));
  if (s.recommendations.length) params.set('rec', s.recommendations.join(','));
  const qs = params.toString();
  const url = qs ? `${window.location.pathname}?${qs}` : window.location.pathname;
  try {
    window.history.replaceState(null, '', url);
  } catch {
    // History API unavailable (sandboxed iframe, etc.) — swallow.
  }
}
