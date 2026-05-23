'use client';

// Two-handle range slider built on overlapping native <input type="range">
// elements. The native UA thumbs are hidden via the pointer-events:none
// container; only the WebKit/Moz thumb pseudo-elements re-enable
// pointer events, so the two handles can be dragged independently.
//
// Why native inputs instead of a slider library? Zero extra dependency,
// touch + keyboard support for free, accessible by default.

export function DualRange({
  min,
  max,
  value,
  onChange,
}: {
  min: number;
  max: number;
  value: [number, number];
  onChange: (next: [number, number]) => void;
}) {
  const [lo, hi] = value;
  const pct = (v: number) => ((v - min) / (max - min)) * 100;

  // Each thumb gets pointer-events back, with consistent styling
  // across WebKit and Mozilla engines.
  const thumb =
    '[&::-webkit-slider-thumb]:pointer-events-auto ' +
    '[&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 ' +
    '[&::-webkit-slider-thumb]:appearance-none ' +
    '[&::-webkit-slider-thumb]:rounded-full ' +
    '[&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-slate-900 dark:[&::-webkit-slider-thumb]:border-slate-100 ' +
    '[&::-webkit-slider-thumb]:bg-white dark:[&::-webkit-slider-thumb]:bg-slate-900 [&::-webkit-slider-thumb]:shadow ' +
    '[&::-webkit-slider-thumb]:cursor-grab ' +
    '[&::-moz-range-thumb]:pointer-events-auto ' +
    '[&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 ' +
    '[&::-moz-range-thumb]:appearance-none ' +
    '[&::-moz-range-thumb]:rounded-full ' +
    '[&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-slate-900 dark:[&::-moz-range-thumb]:border-slate-100 ' +
    '[&::-moz-range-thumb]:bg-white dark:[&::-moz-range-thumb]:bg-slate-900';

  return (
    <div className="space-y-2">
      <div className="relative h-5">
        <div className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-slate-200 dark:bg-slate-700" />
        <div
          className="absolute top-1/2 h-1 -translate-y-1/2 rounded-full bg-slate-900 dark:bg-slate-100"
          style={{ left: `${pct(lo)}%`, right: `${100 - pct(hi)}%` }}
        />
        <input
          type="range"
          min={min}
          max={max}
          value={lo}
          onChange={(e) => onChange([Math.min(+e.target.value, hi - 1), hi])}
          className={`pointer-events-none absolute inset-0 h-5 w-full appearance-none bg-transparent ${thumb}`}
        />
        <input
          type="range"
          min={min}
          max={max}
          value={hi}
          onChange={(e) => onChange([lo, Math.max(+e.target.value, lo + 1)])}
          className={`pointer-events-none absolute inset-0 h-5 w-full appearance-none bg-transparent ${thumb}`}
        />
      </div>
      <div className="flex justify-between text-[10px] font-mono tabular-nums text-slate-400 dark:text-slate-500">
        <span>0</span>
        <span>25</span>
        <span>50</span>
        <span>75</span>
        <span>100</span>
      </div>
    </div>
  );
}
