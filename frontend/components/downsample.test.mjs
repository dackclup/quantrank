/**
 * Regression guard for the `downsample` pure helper exported from
 * PriceHistoryChart.tsx.
 *
 * Run with:  node frontend/components/downsample.test.mjs
 *
 * No test framework required.  The logic below is a verbatim JS
 * transcription of the TypeScript source (types stripped; behaviour
 * identical).  When PriceHistoryChart.tsx changes the implementation
 * this file must be kept in sync — the guard in the CI "Frontend
 * (build)" job does NOT run this script automatically because the
 * project has no frontend unit-test harness yet.  See AGENTS.md
 * §Testing and the frontend-design-reviewer escalation note that
 * created this file for the rationale.
 *
 * NOTE TO FUTURE AUTHORS: if vitest is ever added to package.json
 * (separate PR), delete this file and replace it with a proper
 * frontend/components/PriceHistoryChart.test.ts that imports
 * `downsample` directly from the TypeScript source.
 */

// ── verbatim transcription of downsample from PriceHistoryChart.tsx ──────────

/**
 * @param {{ date: string; close: number }[]} points
 * @param {number} maxPoints
 * @returns {{ date: string; close: number }[]}
 */
function downsample(points, maxPoints) {
  const n = points.length;
  if (n <= maxPoints || maxPoints < 2) return points;
  const out = [];
  const stride = (n - 1) / (maxPoints - 1);
  for (let i = 0; i < maxPoints - 1; i += 1) {
    out.push(points[Math.round(i * stride)]);
  }
  out.push(points[n - 1]); // exact last point
  return out;
}

// ── helpers ───────────────────────────────────────────────────────────────────

/** Build a strictly-increasing series of n ChartPoints. */
function series(n) {
  return Array.from({ length: n }, (_, i) => ({
    date: `2024-01-${String(i + 1).padStart(2, "0")}`,
    close: i + 1,
  }));
}

let passed = 0;
let failed = 0;

function assert(label, condition) {
  if (condition) {
    console.log(`  PASS  ${label}`);
    passed += 1;
  } else {
    console.error(`  FAIL  ${label}`);
    failed += 1;
  }
}

// ── test cases ────────────────────────────────────────────────────────────────

console.log("downsample regression guard\n");

// Case 1 — n <= maxPoints → identity (same reference)
{
  const pts = series(5);
  const out = downsample(pts, 10);
  assert("n <= maxPoints returns same reference", out === pts);
}

// Case 2 — maxPoints < 2 → identity (same reference)
{
  const pts = series(100);
  assert("maxPoints=1 returns same reference", downsample(pts, 1) === pts);
  assert("maxPoints=0 returns same reference", downsample(pts, 0) === pts);
}

// Case 3 — n=261, maxPoints=260 → length 260, first and last preserved
{
  const pts = series(261);
  const out = downsample(pts, 260);
  assert("n=261 maxPoints=260 → length 260", out.length === 260);
  assert("n=261 maxPoints=260 → first point preserved", out[0] === pts[0]);
  assert("n=261 maxPoints=260 → last point is pts[260]", out[259] === pts[260]);
}

// Case 4 — n=1260, maxPoints=260 → length 260, first and last preserved
{
  const pts = series(1260);
  const out = downsample(pts, 260);
  assert("n=1260 maxPoints=260 → length 260", out.length === 260);
  assert("n=1260 maxPoints=260 → first point preserved", out[0] === pts[0]);
  assert("n=1260 maxPoints=260 → last point is pts[1259]", out[259] === pts[1259]);
}

// Case 5 — maxPoints=2, n=100 → length 2, [input[0], input[99]]
{
  const pts = series(100);
  const out = downsample(pts, 2);
  assert("maxPoints=2 n=100 → length 2", out.length === 2);
  assert("maxPoints=2 n=100 → first is pts[0]", out[0] === pts[0]);
  assert("maxPoints=2 n=100 → last is pts[99]", out[1] === pts[99]);
}

// Case 6 — no duplicate of the last point for a strictly-increasing series
{
  const pts = series(1260);
  const out = downsample(pts, 260);
  // For a distinct series the penultimate and final output points must differ
  assert(
    "no duplicate last point (penultimate.close !== last.close)",
    out[out.length - 2].close !== out[out.length - 1].close,
  );
}

// Case 7 — all output points are members of the input (no fabricated points)
{
  const pts = series(500);
  const inputSet = new Set(pts);
  const out = downsample(pts, 260);
  const allInInput = out.every((p) => inputSet.has(p));
  assert("all output points are references from the input array", allInInput);
}

// ── summary ───────────────────────────────────────────────────────────────────

console.log(`\n${passed + failed} assertions — ${passed} passed, ${failed} failed`);

if (failed > 0) {
  process.exit(1);
}
