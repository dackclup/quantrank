import { formatFairPrice, formatMosPct, mosColorClass } from '@/lib/format';
import type { FairPriceEnsemble } from '@/lib/types';
import { CHIP_BASE } from '@/components/Chip';

interface Props {
  ensemble: FairPriceEnsemble | null;
  currentPrice: number;
  warnings: string[];
  tangibleBookValue: number | null;
}

// "Fair price ensemble" — the REFERENCE-DATA half of the fair-price pair.
// The sibling `FairPriceBarChart` ("Fair price check", rendered directly
// above this on the detail page) owns the INTERPRETATION layer: the
// per-method dollar values + verdict badges + plain-English narrative.
//
// This card deliberately does NOT repeat the per-method dollar table
// (removed 2026-05-31). Card A already renders every applicable method's
// estimate ($379.81 / $77.59 / …) with a cheap/fair/pricey badge, so a
// second METHOD→VALUE table here was pure on-screen duplication. What
// stays is what Card A does NOT show and Card B uniquely owns:
//   • the canonical ensemble outputs — Median / Margin-of-Safety / Max
//     (ex-outliers) / Tangible BVPS
//   • the defense-flag warning chips (extreme_*_estimate, beneish_high, …)
//   • the methodology footnote
// One important formula caveat the two cards keep DISTINCT by living in
// separate cards: this card's "Margin of safety" is the schema
// `mos_pct = (median − price)/median` (vs FAIR VALUE, the Damodaran/Graham
// definition, the official scoring field); Card A's "−X% vs today" is
// `(median − price)/price` (vs MARKET PRICE). Both are correct for their
// own anchor; the card boundary does the labelling so the two %'s never
// sit side-by-side looking contradictory.

export default function FairPriceCard({
  ensemble,
  currentPrice,
  warnings,
  tangibleBookValue,
}: Props) {
  // No ensemble at all (snapshot was missing entirely).
  if (!ensemble) {
    return (
      <section className="rounded border border-slate-200 bg-slate-50/60 p-4 dark:border-slate-800 dark:bg-slate-900/40">
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
    <section className="rounded border border-slate-200 bg-slate-50/60 p-4 dark:border-slate-800 dark:bg-slate-900/40">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-[0.14em] text-slate-600 dark:text-slate-400">
        Fair price ensemble
      </h2>

      {/* Headline median + MoS — a real `<dl>` so the dt/dd pairs are a
          valid description list (the grid classes apply identically on a dl). */}
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <div>
          <dt className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Median fair
          </dt>
          <dd className="mt-1 font-mono text-lg font-semibold tabular-nums leading-none text-slate-900 dark:text-slate-100">
            {dataQualityIssue ? '—' : formatFairPrice(ensemble.median)}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Margin of safety
            <span className="ml-1 normal-case tracking-normal text-slate-500 dark:text-slate-400">
              (vs fair value)
            </span>
          </dt>
          <dd
            className={`mt-1 font-mono text-lg font-semibold tabular-nums leading-none ${mosColorClass(ensemble.mos_pct)}`}
            title={mos.tooltip ?? undefined}
          >
            {mos.display}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Max (ex-outliers)
          </dt>
          <dd className="mt-1 font-mono text-lg font-semibold tabular-nums leading-none text-slate-700 dark:text-slate-300">
            {dataQualityIssue ? '—' : formatFairPrice(ensemble.max)}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">
            Tangible BVPS
          </dt>
          <dd className="mt-1 font-mono text-lg font-semibold tabular-nums leading-none text-slate-700 dark:text-slate-300">
            {tangibleBookValue !== null
              ? formatFairPrice(tangibleBookValue)
              : '—'}
          </dd>
        </div>
      </dl>

      {/* Warnings — flex-wrap with gap-2 so adjacent chips have visible
          breathing room (user feedback 2026-05-14: pills were touching
          when multiple fired on the same stock). Outlined-light chip
          pattern matches SectorChip / RecommendationBadge — see
          `.claude/skills/frontend-design-system/SKILL.md` Rule 2. */}
      {warnings.length > 0 && (
        <ul className="mt-4 flex flex-wrap gap-2 text-xs">
          {warnings.map((w) => (
            <li
              key={w}
              className={`${CHIP_BASE} bg-amber-50 px-2 py-0.5 font-medium text-amber-800 ring-amber-200 dark:bg-amber-900/30 dark:text-amber-200 dark:ring-amber-800`}
            >
              {w.replace(/_/g, ' ')}
            </li>
          ))}
        </ul>
      )}

      <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
        Median of all applicable methods (current price{' '}
        <span className="font-mono tabular-nums">${currentPrice.toFixed(2)}</span>).
        Per-method estimates + each method&rsquo;s cheap/fair/pricey read are in
        the Fair price check above. Outliers above 5× or below 0.2× current
        price are excluded from the max but kept in the median. See methodology
        for the 6-method ensemble + 7 defenses.
      </p>
    </section>
  );
}
