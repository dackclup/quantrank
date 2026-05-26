import { formatFairPrice, formatMosPct, mosColorClass } from '@/lib/format';
import type { FairPriceEnsemble, FairPriceMethodResult } from '@/lib/types';

interface Props {
  ensemble: FairPriceEnsemble | null;
  currentPrice: number;
  warnings: string[];
  tangibleBookValue: number | null;
}

const METHOD_LABELS: Record<keyof FairPriceEnsemble['methods'], string> = {
  graham: 'Graham (defensive)',
  multiples_pe: 'P/E multiples',
  multiples_pb: 'P/B multiples',
  multiples_ev_ebitda: 'EV/EBITDA',
  rim: 'Residual Income',
  dcf: 'DCF (2-stage)',
};

const METHOD_ORDER: Array<keyof FairPriceEnsemble['methods']> = [
  'graham',
  'multiples_pe',
  'multiples_pb',
  'multiples_ev_ebitda',
  'rim',
  'dcf',
];

function MethodRow({
  label,
  result,
}: {
  label: string;
  result: FairPriceMethodResult;
}) {
  return (
    <tr className="transition-colors duration-100 hover:bg-slate-100 dark:hover:bg-slate-800/50">
      <td className="px-3 py-2 text-slate-700 dark:text-slate-300">
        {label}
        {result.tier_used && (
          <span className="ml-2 text-xs text-slate-400 dark:text-slate-500">
            (vs {result.tier_used.replace(/_/g, ' ')} peers)
          </span>
        )}
      </td>
      <td className="px-3 py-2 text-right tabular-nums">
        {result.applicable && result.value !== null ? (
          <span className="text-slate-900 dark:text-slate-100">{formatFairPrice(result.value)}</span>
        ) : (
          <span
            className="italic text-slate-400 dark:text-slate-500"
            title={result.reason ?? undefined}
          >
            skipped
          </span>
        )}
      </td>
    </tr>
  );
}

export default function FairPriceCard({
  ensemble,
  currentPrice,
  warnings,
  tangibleBookValue,
}: Props) {
  // No ensemble at all (snapshot was missing entirely).
  if (!ensemble) {
    return (
      <section className="rounded border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-[0.14em] text-slate-600 dark:text-slate-400">
          Fair price ensemble
        </h2>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Not computed — fundamentals snapshot unavailable for this ticker.
        </p>
      </section>
    );
  }

  // Issue #262 rename (2026-05-26) — check BOTH the legacy
  // `data_quality_input_corruption` (still emitted by the writer-parity
  // path in compute/main.py for the veto cohort AND present on pre-rename
  // legacy snapshots) and the new `valuation_output_anomalous` identifier
  // (emitted by compute/valuation/ensemble.py post-rename). Either flag
  // surfaces the all-null fair-price ensemble UI placeholder.
  const dataQualityIssue =
    warnings.includes('data_quality_input_corruption') ||
    warnings.includes('valuation_output_anomalous');
  const mos = formatMosPct(ensemble.mos_pct);

  return (
    <section className="rounded border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-slate-600 dark:text-slate-400">
        Fair price ensemble
      </h2>

      {/* Headline median + MoS */}
      <div className="mb-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Median fair
          </dt>
          <dd className="mt-1 font-mono text-lg font-semibold tabular-nums leading-none text-slate-900 dark:text-slate-100">
            {dataQualityIssue ? '—' : formatFairPrice(ensemble.median)}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Margin of safety
          </dt>
          <dd
            className={`mt-1 font-mono text-lg font-semibold tabular-nums leading-none ${mosColorClass(ensemble.mos_pct)}`}
            title={mos.tooltip ?? undefined}
          >
            {mos.display}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Max (ex-outliers)
          </dt>
          <dd className="mt-1 font-mono text-lg font-semibold tabular-nums leading-none text-slate-700 dark:text-slate-300">
            {dataQualityIssue ? '—' : formatFairPrice(ensemble.max)}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Tangible BVPS
          </dt>
          <dd className="mt-1 font-mono text-lg font-semibold tabular-nums leading-none text-slate-700 dark:text-slate-300">
            {tangibleBookValue !== null
              ? formatFairPrice(tangibleBookValue)
              : '—'}
          </dd>
        </div>
      </div>

      {/* Per-method breakdown */}
      <div className="overflow-hidden rounded border border-slate-200 dark:border-slate-800">
        <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-slate-800">
          <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-[0.14em] text-slate-600 dark:bg-slate-900/60 dark:text-slate-400">
            <tr>
              <th className="px-3 py-2 text-left">Method</th>
              <th className="px-3 py-2 text-right">Value</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800/60">
            {METHOD_ORDER.map((key) => (
              <MethodRow
                key={key}
                label={METHOD_LABELS[key]}
                result={ensemble.methods[key]}
              />
            ))}
          </tbody>
        </table>
      </div>

      {/* Warnings — flex-wrap with gap-2 so adjacent chips have visible
          breathing room (user feedback 2026-05-14: pills were touching
          when multiple fired on the same stock). Outlined-light chip
          pattern matches SectorChip / RecommendationBadge — see
          `.claude/skills/frontend-design-system/SKILL.md` Rule 2. */}
      {warnings.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2 text-xs">
          {warnings.map((w) => (
            <li
              key={w}
              className="inline-flex items-center rounded-sm bg-amber-50 px-2 py-0.5 text-amber-800 ring-1 ring-inset ring-amber-200 dark:bg-amber-900/30 dark:text-amber-200 dark:ring-amber-800"
            >
              {w.replace(/_/g, ' ')}
            </li>
          ))}
        </ul>
      )}

      <p className="mt-3 text-xs text-slate-400 dark:text-slate-500">
        Median of all applicable methods (current price ${currentPrice.toFixed(2)}).
        Outliers above 5× or below 0.2× current price are excluded from the
        max but kept in the median. See methodology for the 6-method ensemble
        + 7 defenses.
      </p>
    </section>
  );
}
