/**
 * Pure-logic contract tests for RankingTable interaction behaviour.
 *
 * RankingTable.tsx uses `useDeferredValue(search)` + `useTransition`-wrapped
 * `onSort` to prevent INP regressions on the 1504-row S&P 1500 list.  The
 * React concurrent-mode hooks are opaque to a node-environment test runner, but
 * the two pure computations they protect — the search filter and the sort
 * comparator — are extractable as standalone functions.  This file:
 *
 *   1. Transcribes those predicates *verbatim* from the component source
 *      (same technique as `downsample.test.mjs` for PriceHistoryChart).
 *   2. Asserts the behavioral contracts PR #608 ships:
 *      - Free-text search by ticker OR name, case-insensitive; empty → all rows.
 *      - A search that matches nothing produces an empty result set.
 *      - Numeric sort (rank / composite_score) orders correctly; asc/desc toggle flips.
 *      - String sort (name / ticker) uses localeCompare; asc/desc toggle flips.
 *      - Null values always sort after non-null values regardless of direction.
 *      - The window resets to WINDOW_SIZE on a search or sort change (via
 *        visibleRows = sorted.slice(0, visibleCount) — asserted via slice semantics).
 *      - Default sort direction for score-oriented keys is `desc`; for
 *        rank/ticker/name/sector it is `asc` — the `onSort` first-click policy.
 *
 * Run:  cd frontend && npm run test:unit
 *
 * WHY NO @testing-library/react:
 *   vitest.config.ts sets `environment: 'node'`; there is no jsdom in
 *   package.json devDependencies.  Adding RTL + jsdom for concurrent-mode
 *   component rendering is a heavy dep that requires a separate PR and
 *   security-reviewer gate.  The pure-function approach covers all the
 *   *behaviorally observable* contracts without DOM rendering, matching the
 *   project's existing test conventions.  If RTL is added in a future PR,
 *   these tests remain valid (they test a different slice of the behaviour).
 *
 * CONCURRENT TIMING NOTE:
 *   The deferred-value / transition timing ("typing is never swallowed") is a
 *   React runtime guarantee, not something a synchronous unit test can assert
 *   deterministically.  That invariant is covered by the architectural comment
 *   in the source (the `<input value>` binds to the immediate `search` state,
 *   not `deferredSearch`); a flaky assertion is worse than no assertion.
 *   This is called out per the spec so future maintainers don't add one.
 */

import { describe, it, expect } from 'vitest';
import type { StockSummary, Recommendation } from '../lib/types';

// ---------------------------------------------------------------------------
// Constants — verbatim from RankingTable.tsx
// ---------------------------------------------------------------------------

const WINDOW_SIZE = 50;

// Keys whose *first* click defaults to descending order.
const DESC_BY_DEFAULT = ['composite_score', 'fair_price', 'margin_of_safety_pct'] as const;

// ---------------------------------------------------------------------------
// Pure helpers — verbatim transcriptions from the `useMemo` bodies in
// RankingTable.tsx.  Keep these in sync when the component changes.
// ---------------------------------------------------------------------------

type SortKey =
  | 'rank'
  | 'ticker'
  | 'name'
  | 'sector'
  | 'composite_score'
  | 'current_price'
  | 'fair_price'
  | 'margin_of_safety_pct'
  | 'loss_chance_pct';
type SortDir = 'asc' | 'desc';

/**
 * Verbatim transcription of the `filtered` useMemo body (lines 135-141).
 * Empty query returns the full array; non-empty queries match ticker OR name,
 * case-insensitively, after trimming the query.
 */
function filterRows(data: StockSummary[], query: string): StockSummary[] {
  const q = query.trim().toLowerCase();
  if (!q) return data;
  return data.filter(
    (row) => row.ticker.toLowerCase().includes(q) || row.name.toLowerCase().includes(q),
  );
}

/**
 * Verbatim transcription of the `sorted` useMemo comparator (lines 158-172).
 * Null values sort LAST regardless of direction.  Numbers use subtraction;
 * strings use localeCompare.
 */
function sortRows(
  rows: StockSummary[],
  sortKey: SortKey,
  sortDir: SortDir,
): StockSummary[] {
  const arr = [...rows];
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
}

/**
 * Verbatim transcription of the next-direction logic in `onSort` (lines 255-266).
 * When the column is already active, toggles direction.  When switching to a
 * new column, applies the first-click default (desc for score-oriented keys).
 */
function nextSortDir(
  key: SortKey,
  currentKey: SortKey,
  currentDir: SortDir,
): SortDir {
  if (currentKey === key) {
    return currentDir === 'asc' ? 'desc' : 'asc';
  }
  return (DESC_BY_DEFAULT as readonly string[]).includes(key) ? 'desc' : 'asc';
}

// ---------------------------------------------------------------------------
// Synthetic fixture builder
//
// Matches the StockSummary shape from frontend/lib/types.ts.  Only the fields
// exercised by the filter/sort logic need to be populated; the rest carry
// minimal defaults so TypeScript is satisfied.
// ---------------------------------------------------------------------------

const SENTINEL_PILLAR_SCORES = {
  quality: null,
  value: null,
  growth: null,
  momentum: null,
  health: null,
  profitability: null,
  technical: null,
  risk: null,
  sentiment: null,
  ml: null,
};

function _row(
  overrides: Pick<StockSummary, 'rank' | 'ticker' | 'name'> &
    Partial<StockSummary>,
): StockSummary {
  return {
    sector: 'Technology',
    composite_score: 70,
    current_price: 100,
    fair_price: null,
    max_fair_price: null,
    margin_of_safety_pct: null,
    pillar_scores: SENTINEL_PILLAR_SCORES,
    risk_flags: [],
    valuation_warnings: [],
    recommendation: 'neutral' as Recommendation,
    loss_chance_pct: null,
    price_change_1d_pct: null,
    manipulation_index: null,
    composite_score_adjusted: null,
    entered_top5: false,
    exited_top5: false,
    index_membership: 'sp500',
    index_memberships: ['sp500'],
    ...overrides,
  };
}

// A small synthetic universe used across multiple test groups.
const ROWS: StockSummary[] = [
  _row({ rank: 1, ticker: 'AAPL', name: 'Apple Inc.', composite_score: 85, current_price: 195.5 }),
  _row({ rank: 2, ticker: 'MSFT', name: 'Microsoft Corporation', composite_score: 80, current_price: 415.0 }),
  _row({ rank: 3, ticker: 'GOOGL', name: 'Alphabet Inc.', composite_score: 75, current_price: 178.3 }),
  _row({ rank: 4, ticker: 'NVDA', name: 'NVIDIA Corporation', composite_score: 72, current_price: 128.0 }),
  _row({ rank: 5, ticker: 'META', name: 'Meta Platforms Inc.', composite_score: 68, current_price: 590.0 }),
];

// ---------------------------------------------------------------------------
// A. Search filter
// ---------------------------------------------------------------------------

describe('filterRows — empty / whitespace query passes all rows', () => {
  it('returns the full array unchanged for an empty query', () => {
    expect(filterRows(ROWS, '')).toBe(ROWS);
  });

  it('returns the full array for a whitespace-only query', () => {
    // `query.trim()` makes "   " equivalent to "".
    expect(filterRows(ROWS, '   ')).toBe(ROWS);
  });

  it('returns the full array when the query is a tab character', () => {
    expect(filterRows(ROWS, '\t')).toBe(ROWS);
  });
});

describe('filterRows — ticker match', () => {
  it('matches an exact ticker (case-sensitive input, case-insensitive match)', () => {
    const result = filterRows(ROWS, 'AAPL');
    expect(result).toHaveLength(1);
    expect(result[0].ticker).toBe('AAPL');
  });

  it('matches a lowercase ticker input', () => {
    const result = filterRows(ROWS, 'aapl');
    expect(result).toHaveLength(1);
    expect(result[0].ticker).toBe('AAPL');
  });

  it('matches a mixed-case ticker input', () => {
    const result = filterRows(ROWS, 'Aapl');
    expect(result).toHaveLength(1);
    expect(result[0].ticker).toBe('AAPL');
  });

  it('matches a partial ticker substring', () => {
    // "GO" matches "GOOGL" only (not NVDA/AAPL/MSFT/META).
    const result = filterRows(ROWS, 'go');
    expect(result.map((r) => r.ticker)).toContain('GOOGL');
  });

  it('matches multiple tickers when the substring is common', () => {
    // "m" appears in MSFT and META and also in "Apple Inc." (lowercase "m").
    const result = filterRows(ROWS, 'M');
    const tickers = result.map((r) => r.ticker);
    expect(tickers).toContain('MSFT');
    expect(tickers).toContain('META');
  });
});

describe('filterRows — company name match', () => {
  it('matches a company name substring, case-insensitively', () => {
    // "apple" should match "Apple Inc." (name) — case-insensitive.
    const result = filterRows(ROWS, 'apple');
    expect(result.map((r) => r.ticker)).toContain('AAPL');
  });

  it('matches a word in the middle of a multi-word name', () => {
    const result = filterRows(ROWS, 'platforms');
    expect(result).toHaveLength(1);
    expect(result[0].ticker).toBe('META');
  });

  it('matches "corporation" across multiple company names', () => {
    // "corporation" appears in "Microsoft Corporation" and "NVIDIA Corporation".
    const result = filterRows(ROWS, 'corporation');
    const tickers = result.map((r) => r.ticker);
    expect(tickers).toContain('MSFT');
    expect(tickers).toContain('NVDA');
  });

  it('is case-insensitive on name (uppercase query)', () => {
    const result = filterRows(ROWS, 'MICROSOFT');
    expect(result).toHaveLength(1);
    expect(result[0].ticker).toBe('MSFT');
  });
});

describe('filterRows — no match → empty result (empty-state)', () => {
  it('returns an empty array when no ticker or name matches', () => {
    const result = filterRows(ROWS, 'ZZZZZ');
    expect(result).toHaveLength(0);
  });

  it('returns empty for a query that is a number not present in tickers/names', () => {
    const result = filterRows(ROWS, '9999999');
    expect(result).toHaveLength(0);
  });

  it('returns empty for special characters absent from the data', () => {
    const result = filterRows(ROWS, '@#$%');
    expect(result).toHaveLength(0);
  });
});

describe('filterRows — union semantics (ticker OR name)', () => {
  it('a ticker-only hit is returned even when the name does not match', () => {
    const unique = [_row({ rank: 1, ticker: 'XYZ', name: 'Completely Different Corp' })];
    const result = filterRows(unique, 'XYZ');
    expect(result).toHaveLength(1);
    expect(result[0].ticker).toBe('XYZ');
  });

  it('a name-only hit is returned even when the ticker does not match', () => {
    const unique = [_row({ rank: 1, ticker: 'XYZ', name: 'Completely Different Corp' })];
    const result = filterRows(unique, 'different');
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe('Completely Different Corp');
  });
});

// ---------------------------------------------------------------------------
// B. Sort comparator
// ---------------------------------------------------------------------------

describe('sortRows — numeric column (rank), asc', () => {
  it('sorts by rank ascending: lowest rank first', () => {
    const shuffled = [ROWS[4], ROWS[0], ROWS[2], ROWS[1], ROWS[3]];
    const result = sortRows(shuffled, 'rank', 'asc');
    expect(result.map((r) => r.rank)).toEqual([1, 2, 3, 4, 5]);
  });
});

describe('sortRows — numeric column (rank), desc', () => {
  it('sorts by rank descending: highest rank first', () => {
    const shuffled = [ROWS[4], ROWS[0], ROWS[2], ROWS[1], ROWS[3]];
    const result = sortRows(shuffled, 'rank', 'desc');
    expect(result.map((r) => r.rank)).toEqual([5, 4, 3, 2, 1]);
  });
});

describe('sortRows — numeric column (composite_score), desc', () => {
  it('sorts by composite_score descending: highest score first', () => {
    const shuffled = [...ROWS].reverse();
    const result = sortRows(shuffled, 'composite_score', 'desc');
    expect(result.map((r) => r.composite_score)).toEqual([85, 80, 75, 72, 68]);
  });
});

describe('sortRows — numeric column (composite_score), asc/desc toggle', () => {
  it('asc/desc toggle flips the numeric order', () => {
    const shuffled = [...ROWS];
    const resultAsc = sortRows(shuffled, 'composite_score', 'asc');
    const resultDesc = sortRows(shuffled, 'composite_score', 'desc');
    expect(resultAsc.map((r) => r.composite_score)).toEqual([68, 72, 75, 80, 85]);
    expect(resultDesc.map((r) => r.composite_score)).toEqual([85, 80, 75, 72, 68]);
  });
});

describe('sortRows — string column (name), asc', () => {
  it('sorts by name ascending (localeCompare A→Z)', () => {
    const result = sortRows(ROWS, 'name', 'asc');
    const names = result.map((r) => r.name);
    // Alphabet Inc. < Apple Inc. < Meta Platforms Inc. < Microsoft Corporation < NVIDIA Corporation
    expect(names[0]).toBe('Alphabet Inc.');
    expect(names[1]).toBe('Apple Inc.');
    expect(names[names.length - 1]).toBe('NVIDIA Corporation');
  });
});

describe('sortRows — string column (name), asc/desc toggle', () => {
  it('asc/desc toggle on a string column flips the localeCompare order', () => {
    const resultAsc = sortRows(ROWS, 'name', 'asc');
    const resultDesc = sortRows(ROWS, 'name', 'desc');
    // Descending should be the reverse of ascending.
    expect(resultDesc.map((r) => r.name)).toEqual(
      [...resultAsc.map((r) => r.name)].reverse(),
    );
  });
});

describe('sortRows — string column (ticker), asc', () => {
  it('sorts by ticker ascending (localeCompare)', () => {
    const result = sortRows(ROWS, 'ticker', 'asc');
    const tickers = result.map((r) => r.ticker);
    // AAPL < GOOGL < META < MSFT < NVDA
    expect(tickers[0]).toBe('AAPL');
    expect(tickers[tickers.length - 1]).toBe('NVDA');
  });
});

describe('sortRows — null values always sort last', () => {
  const rowsWithNull: StockSummary[] = [
    _row({ rank: 1, ticker: 'A', name: 'A Corp', fair_price: null }),
    _row({ rank: 2, ticker: 'B', name: 'B Corp', fair_price: 50 }),
    _row({ rank: 3, ticker: 'C', name: 'C Corp', fair_price: 200 }),
    _row({ rank: 4, ticker: 'D', name: 'D Corp', fair_price: null }),
  ];

  it('null fair_price rows sort LAST in asc order', () => {
    const result = sortRows(rowsWithNull, 'fair_price', 'asc');
    const last = result.slice(-2).map((r) => r.fair_price);
    expect(last).toEqual([null, null]);
  });

  it('null fair_price rows sort LAST in desc order', () => {
    const result = sortRows(rowsWithNull, 'fair_price', 'desc');
    const last = result.slice(-2).map((r) => r.fair_price);
    expect(last).toEqual([null, null]);
  });

  it('two non-null entries appear in the first two positions after asc sort', () => {
    const result = sortRows(rowsWithNull, 'fair_price', 'asc');
    const nonNull = result.slice(0, 2).map((r) => r.fair_price);
    expect(nonNull.every((v) => v !== null)).toBe(true);
  });

  it('two ALL-null rows return 0 comparator (stable relative order)', () => {
    const twoNulls: StockSummary[] = [
      _row({ rank: 1, ticker: 'A', name: 'A Corp', fair_price: null }),
      _row({ rank: 2, ticker: 'B', name: 'B Corp', fair_price: null }),
    ];
    const result = sortRows(twoNulls, 'fair_price', 'asc');
    // Both null — stable sort should preserve insertion order.
    expect(result.map((r) => r.ticker)).toEqual(['A', 'B']);
  });
});

// ---------------------------------------------------------------------------
// C. Sort direction: first-click default (onSort policy)
// ---------------------------------------------------------------------------

describe('nextSortDir — switching to a new column', () => {
  it('defaults to ASC for rank (new column)', () => {
    expect(nextSortDir('rank', 'composite_score', 'desc')).toBe('asc');
  });

  it('defaults to ASC for ticker (new column)', () => {
    expect(nextSortDir('ticker', 'rank', 'asc')).toBe('asc');
  });

  it('defaults to ASC for name (new column)', () => {
    expect(nextSortDir('name', 'rank', 'asc')).toBe('asc');
  });

  it('defaults to ASC for sector (new column)', () => {
    expect(nextSortDir('sector', 'rank', 'asc')).toBe('asc');
  });

  it('defaults to ASC for current_price (new column, not in desc-by-default list)', () => {
    expect(nextSortDir('current_price', 'rank', 'asc')).toBe('asc');
  });

  it('defaults to DESC for composite_score (score-oriented, new column)', () => {
    expect(nextSortDir('composite_score', 'rank', 'asc')).toBe('desc');
  });

  it('defaults to DESC for fair_price (score-oriented, new column)', () => {
    expect(nextSortDir('fair_price', 'rank', 'asc')).toBe('desc');
  });

  it('defaults to DESC for margin_of_safety_pct (score-oriented, new column)', () => {
    expect(nextSortDir('margin_of_safety_pct', 'rank', 'asc')).toBe('desc');
  });
});

describe('nextSortDir — toggling the active column', () => {
  it('toggles asc → desc when the same column is clicked again', () => {
    expect(nextSortDir('rank', 'rank', 'asc')).toBe('desc');
  });

  it('toggles desc → asc when the same column is clicked again', () => {
    expect(nextSortDir('rank', 'rank', 'desc')).toBe('asc');
  });

  it('toggles composite_score asc → desc', () => {
    expect(nextSortDir('composite_score', 'composite_score', 'asc')).toBe('desc');
  });

  it('toggles composite_score desc → asc (asc IS reachable via toggle)', () => {
    expect(nextSortDir('composite_score', 'composite_score', 'desc')).toBe('asc');
  });

  it('toggles ticker desc → asc', () => {
    expect(nextSortDir('ticker', 'ticker', 'desc')).toBe('asc');
  });
});

// ---------------------------------------------------------------------------
// D. Window / visible-rows slice semantics
//
// RankingTable.tsx:  `const visibleRows = sorted.slice(0, visibleCount);`
// On any search or sort change, `visibleCount` resets to WINDOW_SIZE via
// `useEffect([deferredSearch])` / `useEffect([sortKey, sortDir])`.
// We verify the WINDOW_SIZE constant and the slice contract directly.
// ---------------------------------------------------------------------------

describe('WINDOW_SIZE constant and visible-rows slice', () => {
  it('WINDOW_SIZE is 50', () => {
    expect(WINDOW_SIZE).toBe(50);
  });

  it('a list shorter than WINDOW_SIZE is fully visible', () => {
    const short = ROWS; // 5 rows
    const visibleRows = short.slice(0, WINDOW_SIZE);
    expect(visibleRows).toHaveLength(5);
  });

  it('a list longer than WINDOW_SIZE is sliced to WINDOW_SIZE on reset', () => {
    // Synthetic 100-row universe.
    const longList = Array.from({ length: 100 }, (_, i) =>
      _row({ rank: i + 1, ticker: `T${i}`, name: `Company ${i}` }),
    );
    const visibleRows = longList.slice(0, WINDOW_SIZE);
    expect(visibleRows).toHaveLength(WINDOW_SIZE);
    // The visible slice is the FIRST WINDOW_SIZE rows (no offset).
    expect(visibleRows[0].rank).toBe(1);
    expect(visibleRows[WINDOW_SIZE - 1].rank).toBe(WINDOW_SIZE);
  });

  it('a search that narrows the result to <WINDOW_SIZE rows is entirely visible', () => {
    // Build a 100-row universe; search for a unique prefix that matches only 3.
    const longList = Array.from({ length: 100 }, (_, i) =>
      _row({ rank: i + 1, ticker: `TICK${i}`, name: i < 3 ? `Unique Corp ${i}` : `Boring Corp ${i}` }),
    );
    const filtered = filterRows(longList, 'unique');
    expect(filtered).toHaveLength(3);
    // After search, window resets to WINDOW_SIZE; but filtered.length < WINDOW_SIZE
    // so all 3 are visible.
    const visibleRows = filtered.slice(0, WINDOW_SIZE);
    expect(visibleRows).toHaveLength(3);
  });

  it('hasMore is true when sorted.length > visibleCount (WINDOW_SIZE)', () => {
    const longList = Array.from({ length: 100 }, (_, i) =>
      _row({ rank: i + 1, ticker: `T${i}`, name: `Company ${i}` }),
    );
    const sorted = sortRows(longList, 'rank', 'asc');
    const visibleCount = WINDOW_SIZE;
    const hasMore = visibleCount < sorted.length;
    expect(hasMore).toBe(true);
  });

  it('hasMore is false when all rows fit within WINDOW_SIZE', () => {
    const sorted = sortRows(ROWS, 'rank', 'asc'); // 5 rows
    const hasMore = WINDOW_SIZE < sorted.length;
    expect(hasMore).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// E. Filter + sort composition
//
// The component chains: data → filtered → sorted → sliced.
// Verify the composed pipeline behaves correctly end-to-end.
// ---------------------------------------------------------------------------

describe('filter → sort pipeline composition', () => {
  it('filtering then sorting by name asc returns only matched rows in alpha order', () => {
    // "Corporation" matches MSFT and NVDA.
    const filtered = filterRows(ROWS, 'corporation');
    const sorted = sortRows(filtered, 'name', 'asc');
    expect(sorted.map((r) => r.ticker)).toEqual(['MSFT', 'NVDA']);
  });

  it('filtering then sorting by composite_score desc returns highest score first', () => {
    // "Inc." matches Apple, Alphabet, Meta (all have "Inc." in their names).
    const filtered = filterRows(ROWS, 'Inc.');
    const sorted = sortRows(filtered, 'composite_score', 'desc');
    const scores = sorted.map((r) => r.composite_score);
    // Should be descending: 85 (AAPL), 75 (GOOGL), 68 (META).
    expect(scores[0]).toBeGreaterThan(scores[1]);
    expect(scores[1]).toBeGreaterThan(scores[2]);
  });

  it('an empty filter result sorted by any key is still empty', () => {
    const filtered = filterRows(ROWS, 'ZZZZZ');
    const sorted = sortRows(filtered, 'rank', 'asc');
    expect(sorted).toHaveLength(0);
  });

  it('filtering to a single row and sorting returns that row', () => {
    const filtered = filterRows(ROWS, 'AAPL');
    const sorted = sortRows(filtered, 'composite_score', 'desc');
    expect(sorted).toHaveLength(1);
    expect(sorted[0].ticker).toBe('AAPL');
  });
});
