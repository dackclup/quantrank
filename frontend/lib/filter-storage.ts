/**
 * Session-scoped filter persistence (Phase 4 hotfix — bug report 2026-05-14).
 *
 * User flow that was broken before this module:
 *   1. Apply filters on the ranking table
 *   2. Click a stock to open the detail page
 *   3. Click "Back to ranking"
 *   4. Filters reset to defaults (because RankingTable unmounts on
 *      navigation, dropping its useState hooks)
 *
 * The fix persists filter state to `sessionStorage` so the same browser
 * tab restores filters on remount. New tabs / fresh sessions start
 * clean (different from `localStorage` which would persist across days).
 *
 * Why sessionStorage over URL query params:
 *   - The active filter dimensions would clutter the URL noticeably
 *   - Next.js 14 static export requires `<Suspense>` boundaries around
 *     `useSearchParams()` — extra boilerplate we don't need for this
 *     localized fix
 *   - Future filter chips (exchange-pill — see Phase 4 PLANs) can opt
 *     into URL params for shareability; the two approaches coexist
 *
 * Schema versioning: the key includes a version suffix. v2 (PR 4d
 * 2026-05-14) added `recommendations: Recommendation[]`. Bump again
 * when adding new dimensions; old saved payloads are cleanly ignored
 * rather than crashing the page on read.
 */

import type { Recommendation } from '@/lib/types';

const STORAGE_KEY = 'quantrank.filter.v2';

export type FilterSnapshot = {
  search: string;
  sectors: string[];
  scoreRange: [number, number];
  tiers: string[];
  mos: string[];
  recommendations: Recommendation[];
};

export const EMPTY_FILTER: FilterSnapshot = {
  search: '',
  sectors: [],
  scoreRange: [0, 100],
  tiers: [],
  mos: [],
  recommendations: [],
};

const VALID_RECOMMENDATIONS: ReadonlySet<Recommendation> = new Set([
  'bullish',
  'lean_bullish',
  'neutral',
  'cautious',
]);

function isRecommendationArray(v: unknown): v is Recommendation[] {
  return (
    Array.isArray(v) &&
    v.every(
      (x) =>
        typeof x === 'string' &&
        VALID_RECOMMENDATIONS.has(x as Recommendation),
    )
  );
}

function isStringArray(v: unknown): v is string[] {
  return Array.isArray(v) && v.every((x) => typeof x === 'string');
}

function isScoreRange(v: unknown): v is [number, number] {
  return (
    Array.isArray(v) &&
    v.length === 2 &&
    typeof v[0] === 'number' &&
    typeof v[1] === 'number' &&
    v[0] >= 0 &&
    v[1] <= 100 &&
    v[0] <= v[1]
  );
}

/**
 * Read the saved filter snapshot. Returns `EMPTY_FILTER` on any of:
 *   - SSR (no `window`)
 *   - empty `sessionStorage`
 *   - malformed JSON
 *   - shape mismatch (defensive — covers a stale v1 payload from before
 *     a field was added)
 */
export function loadFilterSnapshot(): FilterSnapshot {
  if (typeof window === 'undefined') return EMPTY_FILTER;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return EMPTY_FILTER;
    const parsed = JSON.parse(raw) as Partial<FilterSnapshot>;
    return {
      search: typeof parsed.search === 'string' ? parsed.search : '',
      sectors: isStringArray(parsed.sectors) ? parsed.sectors : [],
      scoreRange: isScoreRange(parsed.scoreRange) ? parsed.scoreRange : [0, 100],
      tiers: isStringArray(parsed.tiers) ? parsed.tiers : [],
      mos: isStringArray(parsed.mos) ? parsed.mos : [],
      recommendations: isRecommendationArray(parsed.recommendations)
        ? parsed.recommendations
        : [],
    };
  } catch {
    return EMPTY_FILTER;
  }
}

/**
 * Persist the current filter snapshot. Silently no-ops on SSR or
 * storage-full conditions — filter state is convenience, not data
 * integrity, so we never throw out of the user's flow.
 */
export function saveFilterSnapshot(snapshot: FilterSnapshot): void {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
  } catch {
    // sessionStorage full / disabled / private-mode — swallow.
  }
}

/**
 * Clear the saved snapshot (called by the Clear all button). Failure
 * is non-fatal for the same reason as `saveFilterSnapshot`.
 */
export function clearFilterSnapshot(): void {
  if (typeof window === 'undefined') return;
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}
