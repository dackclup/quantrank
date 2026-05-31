// Hero attribute chips — at-a-glance "what is this company" tags under the
// stock name (added 2026-05-31 per user request "ยากมีกล่องสี่เหลี่ยมแบบนี้
// บ้าง" — the category tiles a reference stock app shows). NOT the reference
// app's big dark squares: these are the QuantRank `rounded-sm` outlined-light
// chip family (matches SectorChip / the rank chip already in the hero).
//
// Three chips, computed from real per-stock fields — each renders ONLY when
// its data is present (a missing field = silent, never a "—" placeholder):
//   1. Market-cap tier (Mega/Large/Mid/Small) — the analog of the reference
//      app's "ขนาดใหญ่มาก" (mega cap) tile. Neutral slate (size is a
//      structural fact, not a +/- signal).
//   2. Net-margin tier — High margin (≥20%) / Profitable / Loss-making. The
//      ONLY semantic-colored chip (emerald / slate / rose) so the hero keeps
//      one informative accent without competing with the Score / MoS donuts.
//   3. Valuation tone — Value (value pillar ≥65) / Growth (≤35). Driven by the
//      app's OWN value pillar (not raw P/E) so it never contradicts the radar
//      below; neutral slate (cheap multiples ≠ unconditionally "good" in this
//      model — coloring it would mislead next to the Recommendation badge).
//
// No `dividend` chip — that data isn't in the schema. No sector/industry chip —
// already shown in the hero's top meta row. Pure server component (computation
// + markup, no hooks) per the project's "static badge" direction.

import type { PillarScores, RawMetrics } from '@/lib/types';

// Shared chip shell — exact match to SectorChip / rank-chip family.
const CHIP =
  'inline-flex items-center rounded-sm px-2 py-0.5 text-xs font-medium ring-1 ring-inset';
const NEUTRAL =
  'bg-slate-100 text-slate-600 ring-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700';
const POSITIVE =
  'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:ring-emerald-800';
const NEGATIVE =
  'bg-rose-50 text-rose-700 ring-rose-200 dark:bg-rose-900/30 dark:text-rose-300 dark:ring-rose-800';

// Market-cap tier — GICS-style index-provider thresholds ($10B large / $2B
// mid are canonical). `market_cap` is in raw USD (not billions).
function capTier(marketCap: number | null): string | null {
  if (marketCap == null) return null;
  if (marketCap >= 200_000_000_000) return 'Mega cap';
  if (marketCap >= 10_000_000_000) return 'Large cap';
  if (marketCap >= 2_000_000_000) return 'Mid cap';
  return 'Small cap';
}

// Net-margin tier — returns [label, toneClass] or null when the inputs can't
// form a margin. revenue === 0 is an extraction error on an S&P 500 name, not
// a legacy-snapshot field, so the strict guard is safe.
function marginChip(
  netIncome: number | null,
  revenue: number | null,
): [string, string] | null {
  if (netIncome == null || revenue == null || revenue === 0) return null;
  const margin = netIncome / revenue;
  if (margin >= 0.2) return ['High margin', POSITIVE];
  if (margin >= 0) return ['Profitable', NEUTRAL];
  return ['Loss-making', NEGATIVE];
}

// Valuation tone — only the high-signal bands of the value pillar earn a chip;
// the neutral middle (36–64) stays silent.
function valuationTone(valuePillar: number | null): string | null {
  if (valuePillar == null) return null;
  if (valuePillar >= 65) return 'Value';
  if (valuePillar <= 35) return 'Growth';
  return null;
}

export function HeroAttributeChips({
  marketCap,
  rawMetrics,
  pillarScores,
}: {
  marketCap: number | null;
  rawMetrics: RawMetrics;
  pillarScores: PillarScores;
}) {
  const cap = capTier(marketCap);
  const margin = marginChip(rawMetrics.net_income, rawMetrics.revenue);
  const valuation = valuationTone(pillarScores.value);

  // All three silent → render nothing (no empty row).
  if (!cap && !margin && !valuation) return null;

  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {cap && <span className={`${CHIP} ${NEUTRAL}`}>{cap}</span>}
      {margin && <span className={`${CHIP} ${margin[1]}`}>{margin[0]}</span>}
      {valuation && <span className={`${CHIP} ${NEUTRAL}`}>{valuation}</span>}
    </div>
  );
}
