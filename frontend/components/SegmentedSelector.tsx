'use client';

// Generic segmented (radio-group) selector — the outlined-light chip pattern
// (frontend-design-system Rule 2), mirroring PriceTimePeriodSelector. Used for
// the AI-pick home's benchmark (SPY/QQQ/DIA/IWM) and timeframe (1Y/3Y/5Y)
// pickers so both read as the same control family as the price chart's period
// toggle. `flex-1` makes the buttons share the row width.

export interface SegmentOption {
  value: string;
  label: string;
}

interface Props {
  options: readonly SegmentOption[];
  value: string;
  onChange: (value: string) => void;
  ariaLabel: string;
}

export function SegmentedSelector({ options, value, onChange, ariaLabel }: Props) {
  return (
    <div role="radiogroup" aria-label={ariaLabel} className="flex w-full gap-1">
      {options.map((opt) => {
        const selected = opt.value === value;
        const base =
          'flex min-h-[44px] flex-1 items-center justify-center rounded-sm ring-1 ring-inset ' +
          'px-2 py-1 text-xs font-medium';
        const stateClasses = selected
          ? 'press bg-slate-100 text-slate-800 ring-slate-300 dark:bg-slate-800 dark:text-slate-100 dark:ring-slate-500'
          : 'press bg-white text-slate-600 ring-slate-200 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-500 dark:hover:bg-slate-800';
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(opt.value)}
            className={`${base} ${stateClasses}`}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
