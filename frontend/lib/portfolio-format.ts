// Shared display helpers extracted from AiPickPortfolio.tsx.
// Consumed by BOTH AiPickPortfolio.tsx (Current picks table) and
// HoldingsTimeline.tsx (per-quarter drawer detail table) so the two
// tables stay in visual lockstep without duplication.

function isFinite_(v: number | null | undefined): v is number {
  return v !== null && v !== undefined && !Number.isNaN(v);
}

/**
 * Largest-remainder (Hamilton) apportionment so the DISPLAYED 1-decimal weight
 * percentages sum to exactly the basket total (100.0% for a normalized
 * inverse-vol book). Raw weights sum to 1.0, but independent toFixed(1)
 * rounding drifts the visible column to 99.9 / 100.1 / 100.2% — this removes
 * that drift. Non-finite weights render '—' and are excluded; the target total
 * honestly tracks the finite-weight sum.
 */
export function apportionWeightLabels(
  weights: (number | null | undefined)[],
): string[] {
  const labels = weights.map(() => '—');
  const finiteIdx: number[] = [];
  weights.forEach((w, i) => { if (isFinite_(w)) finiteIdx.push(i); });
  if (finiteIdx.length === 0) return labels;
  const sumFinite = finiteIdx.reduce((s, i) => s + (weights[i] as number), 0);
  const target = Math.round(sumFinite * 1000); // tenths of a percent
  const tenths = finiteIdx.map((i) => (weights[i] as number) * 1000);
  const floors = tenths.map((t) => Math.floor(t));
  const used = floors.reduce((s, f) => s + f, 0);
  let remaining = Math.max(0, target - used);
  const order = floors
    .map((_, k) => k)
    .sort((a, b) => (tenths[b] - floors[b]) - (tenths[a] - floors[a]));
  const add = floors.map(() => 0);
  for (let k = 0; k < order.length && remaining > 0; k += 1) {
    add[order[k]] = 1;
    remaining -= 1;
  }
  finiteIdx.forEach((i, k) => {
    labels[i] = `${((floors[k] + add[k]) / 10).toFixed(1)}%`;
  });
  return labels;
}

/**
 * Format a percentage value with sign. Returns '—' for null.
 * e.g. 12.3 → '+12.3%', -5.7 → '−5.7%'.
 */
export function pctStr(v: number | null): string {
  if (v === null) return '—';
  const sign = v >= 0 ? '+' : '−';
  return `${sign}${Math.abs(v).toFixed(1)}%`;
}

/**
 * Tailwind tone class for a signed numeric value.
 * Positive → emerald, negative → rose, null → muted slate.
 */
export function toneClass(v: number | null): string {
  if (v === null) return 'text-slate-500 dark:text-slate-400';
  return v >= 0
    ? 'text-emerald-700 dark:text-emerald-300'
    : 'text-rose-700 dark:text-rose-300';
}
