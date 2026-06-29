/**
 * Regression guard: Next.js 15/16 Promise-params contract for dynamic routes.
 *
 * ROOT CAUSE (PR #656, Next 14→16 migration):
 *   In Next.js 15/16 the App-Router `params` prop for dynamic-route page
 *   components is a PROMISE, not a plain object. Destructuring it synchronously
 *   (`const { ticker } = params` where params is a Promise) yields
 *   `ticker = undefined`, which then silently renders the "Detail data pending"
 *   empty-state on every stock page.  `next build` still reports green because
 *   the empty-state is valid HTML — making the regression completely silent.
 *
 * THE FIX:
 *   - The page component must be `async`.
 *   - The params type must be `Promise<{ ticker: string }>`.
 *   - The destructure must be `const { ticker } = await params`.
 *
 * WHY OPTION (b) — source text scan — rather than option (a) full invocation:
 *   vitest.config.ts sets `environment: 'node'` with no jsdom and no
 *   @testing-library/react in package.json. The stock-detail page is a React
 *   Server Component that returns JSX; rendering it meaningfully requires either
 *   a full Next.js RSC runtime or jsdom + RTL — neither is present. Additionally,
 *   the page's heavy import graph (Recharts, country-flag-icons, Lucide, etc.)
 *   includes modules that call browser globals at import time in some versions,
 *   making a node-environment module import unreliable. The source-text approach
 *   is hermetic, zero-dependency, and encodes the contract precisely:
 *   "every dynamic-route page that reads params must await it inside an async
 *   component" — the exact invariant Next.js 15/16 requires.
 *   If jsdom/RTL is added in a future PR, upgrade to option (a) at that point.
 *
 * FAIL CONDITION (pre-fix):
 *   Source contains `params: { ticker: string }` (sync type) and
 *   `const { ticker } = params` (no await) inside a non-async component.
 *
 * PASS CONDITION (post-fix):
 *   Source contains `params: Promise<{ ticker: string }>` and
 *   `const { ticker } = await params` inside an `async` component.
 *
 * Run:  cd frontend && npm run test:unit
 */

import fs from 'fs';
import path from 'path';
import { describe, it, expect } from 'vitest';

// ---------------------------------------------------------------------------
// Read the source file under test
// ---------------------------------------------------------------------------

const PAGE_PATH = path.resolve(
  __dirname,
  // __dirname resolves to frontend/app/stock/[ticker]/ at runtime
  'page.tsx',
);

const source = fs.readFileSync(PAGE_PATH, 'utf-8');

// ---------------------------------------------------------------------------
// Next.js 15/16 Promise-params contract guards
// ---------------------------------------------------------------------------

describe('Next.js 15/16 Promise-params contract — stock/[ticker]/page.tsx', () => {
  it('default export is an async component (function keyword with async)', () => {
    // Guards: `export default async function StockDetailPage`
    // Pre-fix the component was non-async: `export default function StockDetailPage`
    // The async keyword is required so Next.js can await the params Promise.
    expect(
      source,
      'StockDetailPage must be declared async — non-async default export destructures ' +
        'params as a Promise object, yielding ticker=undefined on Next.js 15/16',
    ).toMatch(/export\s+default\s+async\s+function\s+StockDetailPage/);
  });

  it('params type is Promise<{ ticker: string }>', () => {
    // Guards: `params: Promise<{ ticker: string }>`
    // Pre-fix the type was `params: { ticker: string }` (sync object) — the
    // sync type misleads the compiler into accepting the wrong destructure.
    expect(
      source,
      'params prop must be typed as Promise<{ ticker: string }> to match the Next.js ' +
        '15/16 App-Router contract; sync object type allows the silent undefined bug',
    ).toMatch(/params\s*:\s*Promise\s*<\s*\{\s*ticker\s*:\s*string\s*\}\s*>/);
  });

  it('params is destructured with await (not sync)', () => {
    // Guards: `const { ticker } = await params`
    // Pre-fix the destructure was `const { ticker } = params` (no await) which
    // assigned a Promise-iteration result (undefined) to ticker.
    expect(
      source,
      'params must be destructured with await — sync destructure on a Promise yields ' +
        'ticker=undefined, causing every stock page to render the empty-state',
    ).toMatch(/const\s+\{\s*ticker\s*\}\s*=\s*await\s+params/);
  });

  it('does NOT contain sync params destructure (no raw `= params` without await)', () => {
    // Belt-and-suspenders: the old pattern `const { ticker } = params` (without
    // await) must not appear anywhere in the file — not even in comments.
    // Note: This checks the live source, so a commented-out example would also
    // surface here. If a comment legitimately needs the old pattern, move it to
    // this test file instead. The invariant is too important to allow exceptions.
    const syncDestructurePattern = /const\s+\{\s*ticker\s*\}\s*=\s*params(?!\s*;?\s*\/\/)/;
    // Only flag if NOT preceded by `await` — use a negative-lookbehind free approach:
    // extract all `const { ticker } = ...params` occurrences and assert none lack `await`.
    const matches = source.match(/const\s+\{\s*ticker\s*\}\s*=\s*(?:await\s+)?params/g) ?? [];
    const syncMatches = matches.filter((m) => !m.includes('await'));
    expect(
      syncMatches,
      `Found sync params destructure(s) without await: ${syncMatches.join(', ')} — ` +
        'this is the Next.js 15/16 Promise-params bug; add await before params',
    ).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Scope guard: generateStaticParams is unchanged (returns plain objects)
// ---------------------------------------------------------------------------

describe('generateStaticParams — Next.js 16 compatible shape', () => {
  it('still returns plain { ticker } objects (not Promises)', () => {
    // generateStaticParams must return an array of plain { ticker: string }
    // objects — NOT Promise<...>. Under Next.js 16 this is correct and must
    // NOT change (the framework resolves static params itself).
    // Guard: the function returns { ticker } map (not a Promise-wrapped one).
    expect(source).toMatch(/\.map\(\(ticker\)\s*=>\s*\(\s*\{\s*ticker\s*\}\s*\)\)/);
  });
});
