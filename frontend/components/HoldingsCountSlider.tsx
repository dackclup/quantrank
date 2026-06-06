'use client';

// The 1-N holdings-count slider for the AI-pick home. Sliding re-selects the
// backtest NAV line for that basket size (the artifact stores one per count), so
// the performance-vs-index line genuinely changes with the count — not just the
// displayed holdings list.

interface Props {
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}

export function HoldingsCountSlider({ value, min, max, onChange }: Props) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <label
          htmlFor="holdings-count"
          className="text-xs font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400"
        >
          Holdings
        </label>
        <span className="font-mono text-lg font-semibold tabular-nums text-slate-900 dark:text-slate-100">
          {value}
          <span className="ml-1 text-xs font-normal text-slate-500 dark:text-slate-400">
            {value === 1 ? 'stock' : 'stocks'}
          </span>
        </span>
      </div>
      <div className="flex min-h-[44px] items-center">
        <input
          id="holdings-count"
          type="range"
          min={min}
          max={max}
          step={1}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          aria-label={`Number of holdings: ${value} of ${max}`}
          className="h-2 w-full cursor-pointer appearance-none rounded-full bg-slate-200 accent-emerald-700 dark:bg-slate-700 dark:accent-emerald-400"
        />
      </div>
      <div className="flex justify-between font-mono text-[0.625rem] tabular-nums text-slate-400 dark:text-slate-500">
        <span>{min}</span>
        <span>{max}</span>
      </div>
    </div>
  );
}
