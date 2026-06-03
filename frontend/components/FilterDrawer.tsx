'use client';

import { useEffect, useRef } from 'react';

import { FilterControls, type FilterSetters, type FilterState } from '@/components/FilterControls';

// MOBILE / TABLET (< lg) filter surface: a modal slide-in panel from the right with
// a backdrop. The filter BODY itself lives in `FilterControls` (shared with the
// desktop `FilterRail`); this component is only the modal SHELL — backdrop + focus
// trap + body-scroll-lock + Esc-to-close + the header (count) + footer (Clear all /
// "View N stocks" submit). On lg+ the persistent `FilterRail` replaces this and the
// trigger button is hidden, so the drawer simply never opens.
//
// Re-exported types keep existing importers (`@/components/FilterDrawer`) working;
// the canonical definition now lives in `FilterControls`.
export type { FilterState, FilterSetters };

export function FilterDrawer({
  open,
  onClose,
  state,
  setters,
  sectors,
  totalCount,
  filteredCount,
}: {
  open: boolean;
  onClose: () => void;
  state: FilterState;
  setters: FilterSetters;
  sectors: string[];
  totalCount: number;
  filteredCount: number;
}) {
  const { clearAll } = setters;

  const asideRef = useRef<HTMLElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  // Remove the CLOSED drawer (and the `FilterControls` inside it) from the
  // accessibility tree + Tab order via `.inert`. Critical now that the xl+
  // `FilterRail` renders the SAME controls: without this, a screen-reader /
  // keyboard user would meet every filter button TWICE (once in the rail, once in
  // the never-opened drawer), and at xl+ a phantom "Filter stocks" dialog would sit
  // permanently in the a11y tree. Set imperatively (the DOM `.inert` property is
  // typed in lib.dom + cross-browser, and sidesteps the React-18 boolean-attribute
  // footgun where a JSX `inert={false}` still renders the attribute → stays inert).
  // MUST run BEFORE the focus-trap effect below: on open it clears inert first so
  // the focus-trap's `.focus()` lands on a now-focusable element (focusing a still-
  // inert subtree is a no-op). Effects fire in definition order, so this stays first.
  useEffect(() => {
    const aside = asideRef.current;
    if (aside) aside.inert = !open;
  }, [open]);

  // Esc-to-close + body scroll lock + FOCUS TRAP while the drawer is open.
  // A modal dialog must contain keyboard focus (WCAG 2.4.3 / 2.1.2): on open
  // we remember the element that opened it, move focus into the drawer, and
  // cycle Tab/Shift+Tab within it; on close we restore focus to the trigger.
  // Without this, Tab escaped to the page behind the backdrop (audit P1).
  useEffect(() => {
    if (!open) return;
    triggerRef.current = document.activeElement as HTMLElement | null;
    const aside = asideRef.current;
    const focusables = (): HTMLElement[] =>
      aside
        ? Array.from(
            aside.querySelectorAll<HTMLElement>(
              'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
            ),
          ).filter((el) => el.offsetParent !== null)
        : [];
    // Move focus into the drawer (first focusable = the Close button).
    focusables()[0]?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      if (e.key !== 'Tab') return;
      const els = focusables();
      if (els.length === 0) return;
      const firstEl = els[0];
      const lastEl = els[els.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && active === firstEl) {
        e.preventDefault();
        lastEl.focus();
      } else if (!e.shiftKey && active === lastEl) {
        e.preventDefault();
        firstEl.focus();
      } else if (aside && active instanceof Node && !aside.contains(active)) {
        // Focus escaped the drawer (e.g. via the address bar) — pull it back.
        e.preventDefault();
        firstEl.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
      // Restore focus to whatever opened the drawer.
      triggerRef.current?.focus?.();
    };
  }, [open, onClose]);

  return (
    <>
      <div
        className={`fixed inset-0 z-40 bg-slate-900/40 dark:bg-black/60 backdrop-blur-[2px] transition-opacity duration-200 ${
          open ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        ref={asideRef}
        role="dialog"
        aria-modal="true"
        aria-label="Filter stocks"
        className={`fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col bg-white shadow-overlay transition-transform duration-300 ease-in-out dark:bg-slate-900 ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <header className="flex items-center justify-between border-b border-slate-200 px-5 py-4 dark:border-slate-800">
          <div>
            <div className="text-[0.6875rem] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Filters
            </div>
            <div className="mt-0.5 font-mono text-sm tabular-nums">
              <span className="font-semibold text-slate-900 dark:text-slate-100">
                {filteredCount.toLocaleString()}
              </span>
              <span className="text-slate-500 dark:text-slate-400"> / {totalCount.toLocaleString()} stocks</span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close filters"
            className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-sm text-slate-500 press hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.75">
              <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
            </svg>
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-5">
          <FilterControls state={state} setters={setters} sectors={sectors} />
        </div>

        <footer className="flex items-center justify-between gap-3 border-t border-slate-200 bg-slate-50 px-5 py-3 dark:border-slate-800 dark:bg-slate-950">
          <button
            type="button"
            onClick={clearAll}
            className="inline-flex min-h-[44px] items-center rounded-sm px-3 py-1.5 text-xs font-medium text-slate-600 press hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
          >
            Clear all
          </button>
          {/* Disabled + de-emphasized when the filter set matches nothing, so a
              bright emerald CTA never invites a click toward a 0-result screen
              (expert-user-explorer MAJOR). The Close button / "Clear all" /
              backdrop remain the recovery paths; the focus-trap drops a disabled
              button automatically. Dark uses emerald-700 (not -600): the
              globals.css soft-color override keys on literal class names and
              never reaches dark: variants, so dark:bg-emerald-600 would render
              raw emerald-600 (white ~3.8:1, under AA — impeccable theme audit). */}
          <button
            type="button"
            onClick={onClose}
            disabled={filteredCount === 0}
            className={`inline-flex min-h-[44px] items-center rounded-sm px-4 py-1.5 text-sm font-medium tabular-nums press ${
              filteredCount === 0
                ? 'cursor-not-allowed bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500'
                : 'bg-emerald-700 text-white hover:bg-emerald-800 dark:bg-emerald-700 dark:text-white dark:hover:bg-emerald-800'
            }`}
          >
            {filteredCount === 0
              ? 'No matching stocks'
              : `View ${filteredCount.toLocaleString()} stock${filteredCount === 1 ? '' : 's'}`}
          </button>
        </footer>
      </aside>
    </>
  );
}
