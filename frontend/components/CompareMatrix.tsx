import Link from 'next/link';
import type { ReactNode } from 'react';

import { CHIP_BASE } from '@/components/Chip';
import { LossChanceBadge } from '@/components/LossChanceBadge';
import { RecommendationBadge } from '@/components/RecommendationBadge';
import { ScoreBadge } from '@/components/ScoreBadge';
import { SectorChip } from '@/components/SectorChip';
import { StockLogo } from '@/components/StockLogo';
import { flagLabel } from '@/lib/flag-labels';
import { formatFairPrice, formatMosPct, mosColorClass } from '@/lib/format';
import type { PillarScores, StockSummary } from '@/lib/types';
import { pillarColor } from '@/lib/visual';

// Cross-stock comparison matrix — a SEMANTIC <table> (rows = metric, columns =
// stock) so a screen reader associates each value with both its metric (row
// header) and its stock (column header). The "read like a ledger" topology: a
// reader scans one row left-to-right to see which name leads on that metric.
//
// Data is the focused decision-set, ALL of which lives on `StockSummary`
// (rankings.json) — composite + the 8 active pillars + fair-price median + MoS +
// the risk/defense-flag load. The full 6-method fair-price breakdown +
// manipulation-component breakdown are deliberately NOT here (they live only on
// the per-stock StockDetail JSON); the per-column ticker links out to the full
// detail page for that depth.

// Mirror of PillarRadarChart.ACTIVE_PILLARS (the 8 active pillars; sentiment + ml
// are Phase-5 reserved). Kept local so this presentational module doesn't import
// from the `'use client'` chart; the SET is stable (adding a pillar is a
// Phase-5 event that touches both call sites anyway).
const ACTIVE_PILLARS: ReadonlyArray<readonly [keyof PillarScores, string]> = [
  ['quality', 'Quality'],
  ['value', 'Value'],
  ['growth', 'Growth'],
  ['momentum', 'Momentum'],
  ['health', 'Health'],
  ['profitability', 'Profitability'],
  ['technical', 'Technical'],
  ['risk', 'Risk'],
];

// Which column(s) lead a row. Metric-aware: `max` for "higher is better"
// (composite, pillars, margin of safety), `min` for "lower is better" (loss
// chance, flag count, manipulation index). Returns empty when fewer than 2
// columns carry a value, or when every present value ties (no standout to mark).
// Raw price / 1d-change / fair-median get NO best-mark — they are not a quality
// ranking, and marking "highest price = best" would be dishonest.
function bestIndices(
  values: ReadonlyArray<number | null | undefined>,
  dir: 'max' | 'min',
): Set<number> {
  const valid: Array<[number, number]> = [];
  values.forEach((v, i) => {
    if (v != null && !Number.isNaN(v)) valid.push([v, i]);
  });
  if (valid.length < 2) return new Set();
  const best =
    dir === 'max'
      ? Math.max(...valid.map(([v]) => v))
      : Math.min(...valid.map(([v]) => v));
  const winners = valid.filter(([v]) => v === best).map(([, i]) => i);
  if (winners.length === valid.length) return new Set(); // all present tie
  return new Set(winners);
}

// Quiet "leads this row" mark — a small sage triangle (the app's positive
// soft-band token, never bright/alarm) + an sr-only phrase, so the signal is
// NEVER color-only (a colorblind / SR user still gets "best of N").
function BestMark({ count }: { count: number }) {
  return (
    <>
      <span
        aria-hidden="true"
        className="ml-1 text-[0.5rem] leading-none text-emerald-700 dark:text-emerald-400"
      >
        ▲
      </span>
      <span className="sr-only"> (best of {count})</span>
    </>
  );
}

function Dash() {
  return <span className="font-mono text-sm text-slate-300 dark:text-slate-600">—</span>;
}

// Per-stock cells CENTER their value. design.md mandates `text-right` for a
// ranked LIST column, but this is a cross-sectional matrix (cols = stocks, rows =
// metric) — centering reads better across 2–4 equal columns, and every value
// still carries `tabular-nums` so digits align within a column.
const CELL = 'px-2 py-2 text-center align-middle';

function MetricRow({
  label,
  sub,
  children,
}: {
  label: string;
  sub?: string;
  children: ReactNode;
}) {
  return (
    <tr className="border-t border-slate-100 dark:border-slate-800/60">
      <th
        scope="row"
        className="sticky left-0 z-10 bg-slate-50 px-3 py-2 text-left align-middle dark:bg-slate-900"
      >
        <span className="text-xs font-medium text-slate-700 dark:text-slate-300">{label}</span>
        {sub && (
          <span className="block text-[0.625rem] font-normal normal-case tracking-normal text-slate-500 dark:text-slate-400">
            {sub}
          </span>
        )}
      </th>
      {children}
    </tr>
  );
}

function GroupHeader({ label, span }: { label: string; span: number }) {
  return (
    <tr>
      <th
        scope="colgroup"
        colSpan={span}
        // sticky left-0 keeps the section label visible while the stock columns
        // scroll horizontally on mobile (the row is one full-width cell, so
        // there's nothing behind it to bleed through — the /60 dark tint is safe
        // here, unlike the per-metric rail which had to go fully opaque).
        className="sticky left-0 bg-slate-100 px-3 py-1.5 text-left text-[0.6875rem] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:bg-slate-800/60 dark:text-slate-400"
      >
        {label}
      </th>
    </tr>
  );
}

function PillarCell({ value, best, count }: { value: number; best: boolean; count: number }) {
  const rounded = Math.round(value);
  const c = pillarColor(rounded);
  const w = Math.max(2, Math.min(100, value));
  return (
    <div className="flex items-center justify-center gap-1.5">
      {/* Fixed-width track (decorative) so the fill is directly comparable
          column-to-column on the shared 0–100 scale; the number carries the
          value for SR. */}
      <span
        aria-hidden="true"
        className="relative hidden h-1.5 w-12 overflow-hidden rounded-sm bg-slate-100 dark:bg-slate-800 sm:inline-block"
      >
        <span
          className="absolute inset-y-0 left-0 rounded-sm"
          style={{ width: `${w}%`, backgroundColor: c }}
        />
      </span>
      <span
        className={`font-mono text-xs tabular-nums ${best ? 'font-semibold' : 'font-medium'}`}
        style={{ color: c }}
      >
        {rounded}
      </span>
      {best && <BestMark count={count} />}
    </div>
  );
}

function Change1d({ pct }: { pct: number }) {
  const pos = pct >= 0;
  const cls = pos
    ? 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:ring-emerald-800'
    : 'bg-rose-50 text-rose-700 ring-rose-200 dark:bg-rose-900/30 dark:text-rose-300 dark:ring-rose-800';
  return (
    <span className={`${CHIP_BASE} ${cls} px-1.5 py-0 text-[0.625rem] font-semibold tabular-nums`}>
      <span aria-hidden="true" className="mr-0.5">
        {pos ? '↗' : '↘'}
      </span>
      {pos ? '+' : ''}
      {pct.toFixed(2)}%
    </span>
  );
}

function FlagsCell({ stock, best, count }: { stock: StockSummary; best: boolean; count: number }) {
  const flags = Array.from(
    new Set([...(stock.risk_flags ?? []), ...(stock.valuation_warnings ?? [])]),
  );
  const total = flags.length;
  return (
    <div className="flex flex-col items-center gap-1.5">
      <span className="inline-flex items-center">
        <span
          className={`${CHIP_BASE} px-1.5 py-0 text-[0.625rem] font-semibold tabular-nums ${
            total === 0
              ? 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:ring-emerald-800'
              : 'bg-amber-50 text-amber-800 ring-amber-200 dark:bg-amber-900/30 dark:text-amber-200 dark:ring-amber-800'
          }`}
        >
          {total === 0 ? 'Clean' : `${total} flag${total > 1 ? 's' : ''}`}
        </span>
        {best && <BestMark count={count} />}
      </span>
      {total > 0 &&
        (() => {
          // Cap the visible flag chips so a flag-laden column doesn't grow the
          // Flags row far taller than a clean column's single "Clean" chip (the
          // row-height-asymmetry the critique flagged). The count chip above +
          // the best-▲ stay the comparable signal; the overflow folds into a
          // neutral "+N more" chip (full list in `title` + sr-only). Detail page
          // has the complete list.
          const VISIBLE = 3;
          const shown = flags.slice(0, VISIBLE);
          const rest = flags.slice(VISIBLE);
          return (
            <ul className="flex flex-wrap justify-center gap-1">
              {shown.map((f) => (
                <li
                  key={f}
                  className={`${CHIP_BASE} bg-amber-50 px-1.5 py-0 text-[0.625rem] font-medium text-amber-800 ring-amber-200 dark:bg-amber-900/30 dark:text-amber-200 dark:ring-amber-800`}
                >
                  {flagLabel(f)}
                </li>
              ))}
              {rest.length > 0 && (
                <li
                  className={`${CHIP_BASE} bg-slate-100 px-1.5 py-0 text-[0.625rem] font-medium text-slate-600 ring-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700`}
                  title={rest.map(flagLabel).join(', ')}
                >
                  +{rest.length} more
                  <span className="sr-only">: {rest.map(flagLabel).join(', ')}</span>
                </li>
              )}
            </ul>
          );
        })()}
    </div>
  );
}

export function CompareMatrix({
  stocks,
  onRemove,
}: {
  stocks: StockSummary[];
  onRemove: (ticker: string) => void;
}) {
  const n = stocks.length;
  const span = n + 1;
  // Fixed rail + equal stock columns; min-width forces horizontal scroll on
  // mobile rather than crushing the columns (the rail stays sticky-left).
  const minWidth = `${7.5 + n * 8.5}rem`;

  const compBest = bestIndices(
    stocks.map((s) => s.composite_score),
    'max',
  );
  const lossBest = bestIndices(
    stocks.map((s) => s.loss_chance_pct),
    'min',
  );
  const mosBest = bestIndices(
    stocks.map((s) => s.margin_of_safety_pct),
    'max',
  );
  const flagCounts = stocks.map(
    (s) =>
      new Set([...(s.risk_flags ?? []), ...(s.valuation_warnings ?? [])]).size,
  );
  const flagsBest = bestIndices(flagCounts, 'min');
  const miBest = bestIndices(
    stocks.map((s) => s.manipulation_index),
    'min',
  );

  return (
    <div className="overflow-x-auto rounded border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <table className="w-full table-fixed border-collapse text-sm" style={{ minWidth }}>
        <caption className="sr-only">
          Side-by-side comparison of {stocks.map((s) => s.ticker).join(', ')} across composite
          score, the eight scoring pillars, fair-price margin of safety, and the risk/defense
          flag load.
        </caption>
        <thead>
          <tr className="border-b border-slate-200 dark:border-slate-800">
            <th
              scope="col"
              className="sticky left-0 z-20 w-[7.5rem] bg-slate-50 px-3 py-3 text-left align-bottom text-[0.625rem] font-medium uppercase tracking-wider text-slate-400 dark:bg-slate-900 dark:text-slate-500 sm:w-[9rem]"
            >
              {n} stocks
            </th>
            {stocks.map((s) => (
              <th key={s.ticker} scope="col" className="relative align-top">
                <button
                  type="button"
                  onClick={() => onRemove(s.ticker)}
                  aria-label={`Remove ${s.ticker} from comparison`}
                  className="press absolute right-0 top-0 inline-flex h-11 w-11 items-center justify-center rounded-sm text-slate-400 hover:bg-slate-100 hover:text-slate-700 dark:text-slate-500 dark:hover:bg-slate-800 dark:hover:text-slate-200 lg:h-6 lg:w-6"
                >
                  <span aria-hidden="true" className="text-base leading-none">
                    ×
                  </span>
                </button>
                <span className="flex flex-col items-center gap-1 px-2 pb-2 pt-3">
                  <Link
                    href={`/stock/${s.ticker}/`}
                    className="group flex flex-col items-center gap-1"
                  >
                    <StockLogo ticker={s.ticker} size={28} />
                    <span className="font-mono text-sm font-semibold text-slate-900 group-hover:underline dark:text-slate-100">
                      {s.ticker}
                    </span>
                  </Link>
                  <span className="line-clamp-1 max-w-[8rem] text-[0.625rem] font-normal normal-case tracking-normal text-slate-500 dark:text-slate-400">
                    {s.name}
                  </span>
                  <RecommendationBadge recommendation={s.recommendation} size="xs" />
                  <SectorChip sector={s.sector} size="xs" />
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <GroupHeader label="Overview" span={span} />
          <MetricRow label="Composite" sub="0–100 score">
            {stocks.map((s, i) => (
              <td key={s.ticker} className={CELL}>
                <span className="inline-flex items-center">
                  <ScoreBadge score={s.composite_score} size="md" />
                  {compBest.has(i) && <BestMark count={n} />}
                </span>
              </td>
            ))}
          </MetricRow>
          <MetricRow label="Recommendation">
            {stocks.map((s) => (
              <td key={s.ticker} className={CELL}>
                <RecommendationBadge recommendation={s.recommendation} size="sm" />
              </td>
            ))}
          </MetricRow>
          <MetricRow label="Loss chance" sub="heuristic, lower is better">
            {stocks.map((s, i) => (
              <td key={s.ticker} className={CELL}>
                <span className="inline-flex items-center">
                  <LossChanceBadge lossChancePct={s.loss_chance_pct} size="sm" />
                  {lossBest.has(i) && <BestMark count={n} />}
                </span>
              </td>
            ))}
          </MetricRow>

          <GroupHeader label="Pillars · 0–100 percentile rank" span={span} />
          {ACTIVE_PILLARS.map(([key, label]) => {
            const vals = stocks.map((s) => s.pillar_scores?.[key] ?? null);
            const best = bestIndices(vals, 'max');
            return (
              <MetricRow key={key} label={label}>
                {stocks.map((s, i) => {
                  const v = vals[i];
                  return (
                    <td key={s.ticker} className={CELL}>
                      {v == null ? (
                        <Dash />
                      ) : (
                        <PillarCell value={v} best={best.has(i)} count={n} />
                      )}
                    </td>
                  );
                })}
              </MetricRow>
            );
          })}

          <GroupHeader label="Valuation" span={span} />
          <MetricRow label="Price" sub="latest close">
            {stocks.map((s) => (
              <td key={s.ticker} className={CELL}>
                <span className="flex flex-col items-center gap-1">
                  <span className="font-mono text-sm font-semibold tabular-nums text-slate-900 dark:text-slate-100">
                    ${s.current_price.toFixed(2)}
                  </span>
                  {s.price_change_1d_pct != null && <Change1d pct={s.price_change_1d_pct} />}
                </span>
              </td>
            ))}
          </MetricRow>
          <MetricRow label="Fair (median)" sub="6-method ensemble">
            {stocks.map((s) => (
              <td key={s.ticker} className={CELL}>
                <span className="font-mono text-sm font-medium tabular-nums text-slate-700 dark:text-slate-300">
                  {formatFairPrice(s.fair_price)}
                </span>
              </td>
            ))}
          </MetricRow>
          <MetricRow label="Margin of safety" sub="vs fair value, higher is better">
            {stocks.map((s, i) => {
              const m = formatMosPct(s.margin_of_safety_pct);
              return (
                <td key={s.ticker} className={CELL}>
                  <span className="inline-flex items-center">
                    <span
                      className={`font-mono text-sm tabular-nums ${mosColorClass(
                        s.margin_of_safety_pct,
                      )} ${mosBest.has(i) ? 'font-semibold' : 'font-medium'}`}
                      title={m.tooltip ?? undefined}
                    >
                      {m.display}
                    </span>
                    {mosBest.has(i) && <BestMark count={n} />}
                  </span>
                </td>
              );
            })}
          </MetricRow>

          <GroupHeader label="Risk · defense layer" span={span} />
          <MetricRow label="Flags" sub="fewer is better">
            {stocks.map((s, i) => (
              <td key={s.ticker} className={CELL}>
                <FlagsCell stock={s} best={flagsBest.has(i)} count={n} />
              </td>
            ))}
          </MetricRow>
          <MetricRow label="Manipulation index" sub="0–100, lower is better">
            {stocks.map((s, i) => {
              const mi = s.manipulation_index;
              return (
                <td key={s.ticker} className={CELL}>
                  {mi == null ? (
                    <Dash />
                  ) : (
                    <span className="inline-flex items-center">
                      <span
                        className={`font-mono text-sm tabular-nums text-slate-700 dark:text-slate-300 ${
                          miBest.has(i) ? 'font-semibold' : 'font-medium'
                        }`}
                      >
                        {Math.round(mi)}
                      </span>
                      {miBest.has(i) && <BestMark count={n} />}
                    </span>
                  )}
                </td>
              );
            })}
          </MetricRow>
        </tbody>
      </table>
    </div>
  );
}
