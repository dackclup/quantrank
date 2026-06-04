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
  //
  // Thumb FILL contrasts the PANEL, not matches it: a slate-900 (dark) knob on
  // the light panel, a white knob on the dark panel. The earlier `bg-white` /
  // `dark:bg-slate-900` fill was the SAME color as the panel it sat on
  // (`bg-white dark:bg-slate-900`), so the handles camouflaged into the
  // background and a user couldn't see them (reported 2026-06-03). The 2px
  // border is the INVERSE of the fill (white on the dark knob, slate-900 on the
  // light knob) so the handle still separates from the same-colored active fill
  // bar (slate-900 light / slate-100 dark) where it rides. `shadow-subtle` adds
  // the hairline lift (the raw Tailwind `shadow` it replaced is off-system per
  // design.md "Borders-As-Depth").
  //
  // Keyboard focus rides the THUMB, not the input. Each handle is a
  // full-width transparent `<input type=range>`, so the global
  // `:focus-visible` outline (globals.css) wrapped the entire 0→100 track —
  // a keyboard user got an indigo line spanning the whole slider with no cue
  // which handle was active. `focus-visible:outline-none` (on the input,
  // below) suppresses that; the indigo halo here lands on the actual thumb
  // instead. Indigo-500 (#6366f1) matches the app-wide focus color; a soft
  // 3px halo reads as focus over both the slate-900 (light) and white (dark)
  // thumb fills without a theme-specific offset color.
  const thumb =
    '[&::-webkit-slider-thumb]:pointer-events-auto ' +
    '[&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:w-5 ' +
    '[&::-webkit-slider-thumb]:appearance-none ' +
    '[&::-webkit-slider-thumb]:rounded-full ' +
    '[&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-white dark:[&::-webkit-slider-thumb]:border-slate-900 ' +
    '[&::-webkit-slider-thumb]:bg-slate-900 dark:[&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:shadow-subtle ' +
    '[&::-webkit-slider-thumb]:cursor-grab ' +
    '[&:focus-visible::-webkit-slider-thumb]:[box-shadow:0_0_0_3px_rgba(99,102,241,0.55)] ' +
    '[&::-moz-range-thumb]:pointer-events-auto ' +
    '[&::-moz-range-thumb]:h-5 [&::-moz-range-thumb]:w-5 ' +
    '[&::-moz-range-thumb]:appearance-none ' +
    '[&::-moz-range-thumb]:rounded-full ' +
    '[&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-white dark:[&::-moz-range-thumb]:border-slate-900 ' +
    '[&::-moz-range-thumb]:bg-slate-900 dark:[&::-moz-range-thumb]:bg-white [&::-moz-range-thumb]:shadow-subtle ' +
    '[&:focus-visible::-moz-range-thumb]:[box-shadow:0_0_0_3px_rgba(99,102,241,0.55)]';

  return (
    <div className="space-y-2">
      <div className="relative h-11">
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
          aria-label="Minimum composite score"
          onChange={(e) => onChange([Math.min(+e.target.value, hi - 1), hi])}
          className={`pointer-events-none absolute inset-0 h-11 w-full appearance-none bg-transparent focus-visible:outline-none ${thumb}`}
        />
        <input
          type="range"
          min={min}
          max={max}
          value={hi}
          aria-label="Maximum composite score"
          onChange={(e) => onChange([lo, Math.max(+e.target.value, lo + 1)])}
          className={`pointer-events-none absolute inset-0 h-11 w-full appearance-none bg-transparent focus-visible:outline-none ${thumb}`}
        />
      </div>
      <div className="flex justify-between text-[0.625rem] font-mono tabular-nums text-slate-500 dark:text-slate-400">
        <span>0</span>
        <span>25</span>
        <span>50</span>
        <span>75</span>
        <span>100</span>
      </div>
    </div>
  );
}
