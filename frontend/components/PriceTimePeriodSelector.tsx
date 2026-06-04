'use client';

// PR 4f — 7-button time-period toggle above the price chart.
// 1D / 5D / 5Y are disabled in Phase 4.1 (data not yet ingested);
// they render greyed-out with a hover tooltip explaining when to
// expect them. 1M / 6M / YTD / 1Y are sliced client-side from the
// existing 1Y daily history JSON.
//
// Default selection: 1Y (matches the prior chart behavior so the
// first-paint chart is unchanged).

export type TimePeriod = '1D' | '5D' | '1M' | '6M' | 'YTD' | '1Y' | '5Y';

export const TIME_PERIODS: readonly TimePeriod[] = [
  '1D',
  '5D',
  '1M',
  '6M',
  'YTD',
  '1Y',
  '5Y',
] as const;

// Phase 4.1 + 4.2 ship 1M / 6M / YTD / 1Y / 5Y. 1D / 5D need an
// intraday data source (deferred to Phase 4.3 — separate architecture
// decision per price-chart-enhancements/PLAN.md).
const ENABLED_PERIODS: ReadonlySet<TimePeriod> = new Set([
  '1M',
  '6M',
  'YTD',
  '1Y',
  '5Y',
]);

const DISABLED_TOOLTIP: Record<'1D' | '5D', string> = {
  '1D': 'Intraday data — coming soon',
  '5D': 'Intraday data — coming soon',
};

interface Props {
  value: TimePeriod;
  onChange: (period: TimePeriod) => void;
}

export function PriceTimePeriodSelector({ value, onChange }: Props) {
  return (
    <div
      role="radiogroup"
      aria-label="Price chart time period"
      className="flex w-full gap-1"
    >
      {TIME_PERIODS.map((period) => {
        const enabled = ENABLED_PERIODS.has(period);
        const selected = period === value;
        const tooltip = !enabled
          ? DISABLED_TOOLTIP[period as '1D' | '5D']
          : undefined;

        // Outlined-light chip pattern (Rule 2 of frontend-design-system).
        // Selected: slate-100 fill + slate-700 text + slate-300 ring.
        // Unselected enabled: bg-white + slate-600 text + slate-200 ring.
        // Disabled: bg-slate-50 + slate-400 text + slate-200 ring +
        //   cursor-not-allowed.
        // `flex-1` + `justify-center` makes every button take an equal
        // share of the row so the whole selector spans the chart width
        // (PR 4f post-spot-check — user wanted "ปุ่ม 1D ถึง 5Y ปรับให้
        // ยาวพอดีกับ ความยาวของกราฟราคา").
        const base =
          'flex min-h-[44px] flex-1 items-center justify-center rounded-sm ring-1 ring-inset ' +
          'px-2 py-1 text-xs font-medium';
        const stateClasses = !enabled
          ? 'bg-slate-50 text-slate-400 ring-slate-200 cursor-not-allowed dark:bg-slate-900 dark:text-slate-500 dark:ring-slate-500'
          : selected
            ? 'press bg-slate-100 text-slate-800 ring-slate-300 dark:bg-slate-800 dark:text-slate-100 dark:ring-slate-500'
            : 'press bg-white text-slate-600 ring-slate-200 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-500 dark:hover:bg-slate-800';

        return (
          <button
            key={period}
            type="button"
            role="radio"
            aria-checked={selected}
            aria-disabled={!enabled}
            disabled={!enabled}
            title={tooltip}
            onClick={() => {
              if (enabled) onChange(period);
            }}
            className={`${base} ${stateClasses}`}
          >
            {period}
          </button>
        );
      })}
    </div>
  );
}
