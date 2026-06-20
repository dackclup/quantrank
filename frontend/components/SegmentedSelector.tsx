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

/**
 * Active-segment styling.
 * - `subtle` (default, backward-compatible): the original slate-tinted active
 *   state — a quiet selected fill matching the outlined-light chip family.
 * - `primary`: the handoff `Toggle` look — an emerald-fill active segment
 *   (`bg-emerald-700` + white text, the brand primary) so the *current*
 *   selection reads as a committed, on-brand choice rather than a faint tint.
 *   Inactive segments stay transparent + subdued in both variants.
 */
export type SegmentedVariant = 'subtle' | 'primary';

interface Props {
  options: readonly SegmentOption[];
  value: string;
  onChange: (value: string) => void;
  ariaLabel: string;
  /** Active-segment styling. Defaults to `subtle` (the pre-existing look). */
  variant?: SegmentedVariant;
}

export function SegmentedSelector({
  options,
  value,
  onChange,
  ariaLabel,
  variant = 'subtle',
}: Props) {
  return (
    <div role="radiogroup" aria-label={ariaLabel} className="flex w-full gap-1">
      {options.map((opt) => {
        const selected = opt.value === value;
        const base =
          'flex min-h-[44px] flex-1 items-center justify-center rounded-sm ring-1 ring-inset ' +
          'px-2 py-1 text-xs font-medium';
        // `primary` active = emerald-fill (brand primary, white text); inactive
        // unchanged from the subtle variant. `bg-emerald-700` is the project
        // brand primary and is NOT remapped by the globals.css soft-OKLCH
        // allowlist (intentional — keeps the committed-choice saturation).
        const activeClasses =
          variant === 'primary'
            ? 'press bg-emerald-700 text-white ring-emerald-700 hover:bg-emerald-800 dark:bg-emerald-700 dark:text-white dark:ring-emerald-600 dark:hover:bg-emerald-800'
            : 'press bg-slate-100 text-slate-800 ring-slate-300 dark:bg-slate-800 dark:text-slate-100 dark:ring-slate-500';
        const stateClasses = selected
          ? activeClasses
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
