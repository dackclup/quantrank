'use client';

// FilterDrawer — the ranking screen's filter slide-over, translated from the
// handoff `feedback/Dialog.jsx` (variant="drawer") into the project Tailwind
// idiom. This is the ONE floating-overlay surface in the system (the only live
// shadow tier — `shadow-xl`), and the project design explicitly anticipates it
// (handoff readme: "the one floating overlay (the FilterDrawer slide-over)").
//
// Re-introduced per explicit user authorization (the ranking screen previously
// shed its multi-dimension filter screener for the "Search-only view"). It is
// ADDITIVE: the existing search + column sort + pagination are untouched; the
// committed filters feed the SAME row pipeline alongside search.
//
// Draft-state pattern: the drawer edits a `draft` copy; nothing changes in the
// table until "Apply filters" commits it (matches the handoff). "Reset" clears
// the draft to the empty filter set (does not commit until Apply).
//
// Accessibility: role="dialog" + aria-modal + aria-label; focus moves into the
// panel on open and is TRAPPED (Tab/Shift+Tab cycle within); Escape + backdrop
// click close; the trigger restores focus on close. Entrance is transform +
// opacity only, ≤ 320ms, reduced-motion-guarded (globals.css).

import { useEffect, useRef } from 'react';
import { RotateCcw, X } from 'lucide-react';

import { Chip } from '@/components/Chip';
import { SectorChip } from '@/components/SectorChip';
import { Switch } from '@/components/Switch';

export interface RankingFilters {
  /** MoS ≥ 0 only. */
  undervalued: boolean;
  /** composite_score ≥ 55 only. */
  strongOnly: boolean;
  /** Selected GICS sectors (multi-select); empty = all sectors. */
  sectors: string[];
}

export const EMPTY_FILTERS: RankingFilters = {
  undervalued: false,
  strongOnly: false,
  sectors: [],
};

export function countActiveFilters(f: RankingFilters): number {
  return (f.undervalued ? 1 : 0) + (f.strongOnly ? 1 : 0) + f.sectors.length;
}

// Focusable-element selector for the in-panel focus trap.
const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),[tabindex]:not([tabindex="-1"])';

export function FilterDrawer({
  open,
  draft,
  sectors,
  onClose,
  onChangeDraft,
  onReset,
  onApply,
}: {
  open: boolean;
  /** Working filter state edited in the drawer (committed by onApply). */
  draft: RankingFilters;
  /** Distinct GICS sectors derived from the loaded rankings (real data). */
  sectors: string[];
  onClose: () => void;
  onChangeDraft: (next: RankingFilters) => void;
  /** Clear the draft to EMPTY_FILTERS (does not commit until Apply). */
  onReset: () => void;
  /** Commit the draft to the live filters + close. */
  onApply: () => void;
}) {
  const panelRef = useRef<HTMLDivElement>(null);

  // Escape to close + move focus into the panel on open + restore on close +
  // trap Tab within the panel. One effect so the listeners are added/removed
  // together with the open state.
  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === 'Tab' && panelRef.current) {
        const nodes = panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE);
        if (nodes.length === 0) return;
        const first = nodes[0];
        const last = nodes[nodes.length - 1];
        const active = document.activeElement;
        if (e.shiftKey && active === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener('keydown', onKey);
    // Move focus to the panel (the close button is the first focusable).
    const raf = requestAnimationFrame(() => {
      const nodes = panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE);
      nodes && nodes.length > 0 ? nodes[0].focus() : panelRef.current?.focus();
    });

    return () => {
      document.removeEventListener('keydown', onKey);
      cancelAnimationFrame(raf);
      // Restore focus to the trigger so keyboard users aren't dropped at <body>.
      previouslyFocused?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  const toggleSector = (sec: string) => {
    onChangeDraft({
      ...draft,
      sectors: draft.sectors.includes(sec)
        ? draft.sectors.filter((s) => s !== sec)
        : [...draft.sectors, sec],
    });
  };

  return (
    <div
      // Backdrop — soft slate wash. Backdrop click (mousedown on the scrim
      // itself, not a bubbled child) closes.
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      className="animate-scrim-in fixed inset-0 z-50 flex items-stretch justify-end bg-slate-900/40"
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="Filter ranking"
        tabIndex={-1}
        className="animate-drawer-in flex h-full w-full max-w-[92vw] flex-col bg-white shadow-xl outline-none dark:bg-slate-900 sm:w-[380px]"
      >
        {/* Header — title + close. */}
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-5 py-4 dark:border-slate-800">
          <span className="font-slab text-base font-semibold text-slate-900 dark:text-slate-100">
            Filter ranking
          </span>
          <button
            type="button"
            aria-label="Close filter panel"
            onClick={onClose}
            className="press inline-flex h-9 w-9 items-center justify-center rounded-sm text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
          >
            <X aria-hidden="true" strokeWidth={1.75} className="h-5 w-5" />
          </button>
        </div>

        {/* Body — Signal switches + Sector chips. */}
        <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5">
          <div>
            <div className="mb-2 text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
              Signal
            </div>
            <div className="flex flex-col gap-1">
              <Switch
                checked={draft.undervalued}
                onChange={(v) => onChangeDraft({ ...draft, undervalued: v })}
                label="Undervalued only (MoS ≥ 0)"
              />
              <Switch
                checked={draft.strongOnly}
                onChange={(v) => onChangeDraft({ ...draft, strongOnly: v })}
                label="Strong composite only (≥ 55)"
              />
            </div>
          </div>

          {sectors.length > 0 && (
            <div>
              <div className="mb-2 text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
                Sector
              </div>
              <div className="flex flex-wrap gap-2">
                {sectors.map((sec) => {
                  const selected = draft.sectors.includes(sec);
                  return (
                    <button
                      key={sec}
                      type="button"
                      role="checkbox"
                      aria-checked={selected}
                      aria-label={sec}
                      onClick={() => toggleSector(sec)}
                      className="press rounded-sm"
                    >
                      {selected ? (
                        // Selected = the canonical outlined-light emerald chip
                        // with a leading dot (never a solid fill — one chip
                        // pattern).
                        <Chip
                          tone="bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:ring-emerald-800"
                          dot="bg-emerald-500 dark:bg-emerald-400"
                          size="md"
                        >
                          {sec}
                        </Chip>
                      ) : (
                        // Unselected = the live SectorChip (its sector-color dot
                        // + tint), so the picker reads as the SAME family as the
                        // table's sector cells.
                        <SectorChip sector={sec} />
                      )}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Footer — Reset (ghost) + Apply (primary). */}
        <div className="flex items-center justify-end gap-2 border-t border-slate-200 px-5 py-4 dark:border-slate-800">
          <button
            type="button"
            onClick={onReset}
            className="press inline-flex min-h-[44px] items-center gap-1.5 rounded-sm px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
          >
            <RotateCcw aria-hidden="true" strokeWidth={1.75} className="h-4 w-4" />
            Reset
          </button>
          <button
            type="button"
            onClick={onApply}
            className="press inline-flex min-h-[44px] items-center rounded-sm bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-800 dark:bg-emerald-700 dark:hover:bg-emerald-800"
          >
            Apply filters
          </button>
        </div>
      </div>
    </div>
  );
}
