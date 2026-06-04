'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';

import { Sidebar } from './Sidebar';
import { ThemeToggle } from './ThemeToggle';
import { TopNav } from './TopNav';

// App shell — a FULL-WIDTH top chrome (controls row + tab nav + the market-stats
// strip) over a full-width content column. The Sidebar is an overlay DRAWER
// (closed by default, every breakpoint) opened by the ☰ button in the header,
// which flips to ✕ while open (the Seeking-Alpha model — user choice 2026-06-04).
// The drawer sits BELOW the sticky header, so the toggle stays visible/usable.

export function AppShell({ children, topBar }: { children: React.ReactNode; topBar?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const toggleRef = useRef<HTMLButtonElement>(null);
  const wasOpenRef = useRef(false);

  // Lock body scroll while the drawer overlays the page.
  useEffect(() => {
    document.body.style.overflow = open ? 'hidden' : '';
    return () => {
      document.body.style.overflow = '';
    };
  }, [open]);

  // Esc closes the drawer.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  // Restore focus to the toggle when the drawer closes (WCAG 2.4.3); the guard
  // skips the initial render so focus isn't stolen on mount.
  useEffect(() => {
    if (!open && wasOpenRef.current) toggleRef.current?.focus();
    wasOpenRef.current = open;
  }, [open]);

  return (
    <div className="flex min-h-screen flex-col">
      {/* Full-width top chrome — the controls + tab nav + the market-stats strip
          span edge-to-edge; the sidebar overlays BELOW this, never the top bar. */}
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95">
        <div className="flex h-14 items-center gap-2 px-4 md:px-6">
          {/* Sidebar toggle — ☰ when closed, ✕ when open. Sits BEFORE the brand
              and shows on every breakpoint (the sidebar is a drawer at all sizes). */}
          <button
            ref={toggleRef}
            type="button"
            aria-label={open ? 'Close navigation' : 'Open navigation'}
            aria-expanded={open}
            aria-controls="sidebar-drawer"
            onClick={() => setOpen((v) => !v)}
            className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-sm text-slate-600 press hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
          >
            {open ? (
              <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            ) : (
              <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            )}
          </button>
          {/* Brand — Q logo + wordmark, ALWAYS visible (every breakpoint). */}
          <Link
            href="/"
            aria-label="QuantRank home"
            className="flex min-w-0 items-center gap-2 text-slate-900 press hover:opacity-80 dark:text-slate-100"
          >
            <span aria-hidden="true" className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-sm bg-emerald-700 font-mono text-xs font-semibold text-white dark:bg-emerald-700 dark:text-white">Q</span>
            <span className="font-slab text-base font-semibold tracking-tight">QuantRank</span>
          </Link>
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden text-xs text-slate-500 dark:text-slate-400 sm:inline">Equity rankings</span>
            <ThemeToggle layout="icon" />
          </div>
        </div>
        {/* Primary tab nav (Home · Ranking · News · Analysis · Portfolio). */}
        <div className="border-t border-slate-200 dark:border-slate-800">
          <TopNav />
        </div>
      </header>
      {/* Universe-snapshot ticker strip (server-rendered) — full-width, below the
          sticky header, scrolls away. */}
      {topBar}
      <main className="flex-1 px-4 pb-8 pt-4 md:px-8 md:pb-10 md:pt-6">
        {/* Content cap is a FIXED px (not max-w-6xl): with the fluid root
            font-size a rem max-width expands too far on ultrawide. */}
        <div className="mx-auto max-w-[1152px]">{children}</div>
      </main>
      <footer className="border-t border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
        <div className="mx-auto max-w-[1152px] space-y-2 px-4 py-6 text-xs text-slate-500 dark:text-slate-400 md:px-8">
          {/* Legal-safety disclaimer (design-system Rule 9) — moved here from the
              top banner per user request; full text kept so the regulated-style
              badges (Strong Buy/Sell) + Loss Chance % stay covered. */}
          <p>
            <span className="font-medium text-slate-600 dark:text-slate-300">Educational use only.</span>{' '}
            Not investment advice. Past performance does not predict future results. Scores and &ldquo;fair prices&rdquo; are model outputs from public data — they can be wrong, stale, or misleading; do not use for real-money trading decisions.
          </p>
          <p>QuantRank · MIT licensed · Data refreshed every US trading day via GitHub Actions.</p>
        </div>
      </footer>
      {/* Overlay drawer (fixed) — rendered last so it stacks above the content. */}
      <Sidebar open={open} onClose={() => setOpen(false)} />
    </div>
  );
}
