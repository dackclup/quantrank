'use client';

// Switch — a small accessible boolean toggle (used by the ranking FilterDrawer's
// signal switches). Translated from the handoff `core/Switch.jsx` into the
// project's Tailwind idiom: a flat 2px-radius track (sharp like the rest of the
// system, NOT a pill) with a sliding knob. On = emerald track (brand primary);
// off = steel. The whole control is a single `role="switch"` button so the
// label + track share one 44px hit target and one keyboard activation (Enter /
// Space toggle natively on a <button>).
//
// `bg-emerald-700` is the project brand primary and is intentionally NOT
// remapped by the globals.css soft-OKLCH allowlist — it keeps its committed-on
// saturation. The knob slide is transform-only + reduced-motion-guarded via the
// global `motion-reduce:` variant so it snaps for users who opt out.

export function Switch({
  checked,
  onChange,
  label,
  disabled = false,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  /** Visible + accessible label (rendered after the track, also the aria-label). */
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => !disabled && onChange(!checked)}
      className="press inline-flex min-h-[44px] w-full items-center gap-3 rounded-sm px-1 text-left disabled:cursor-not-allowed disabled:opacity-50"
    >
      <span
        aria-hidden="true"
        className={`relative inline-block h-5 w-9 shrink-0 rounded-sm ring-1 ring-inset transition-colors duration-150 ${
          checked
            ? 'bg-emerald-700 ring-emerald-700 dark:bg-emerald-700 dark:ring-emerald-600'
            : 'bg-slate-200 ring-slate-300 dark:bg-slate-700 dark:ring-slate-600'
        }`}
      >
        <span
          className={`absolute top-0.5 h-4 w-4 rounded-[1px] bg-white shadow-sm transition-[left] duration-150 motion-reduce:transition-none ${
            checked ? 'left-[18px]' : 'left-0.5'
          }`}
        />
      </span>
      <span className="text-sm text-slate-700 dark:text-slate-300">{label}</span>
    </button>
  );
}
