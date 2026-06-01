'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Sidebar } from './Sidebar';
import { Disclaimer } from './Disclaimer';
import { ThemeToggle } from './ThemeToggle';

// LedgerCraft Phase 3c — app shell with persistent left-rail sidebar
// on desktop, slide-over drawer on mobile. Manages collapsed state +
// localStorage persistence + body scroll lock when mobile drawer
// open. Layout shell stays a Server Component; this client wrapper
// owns the small slice of client state (one boolean + one effect).

const STORAGE_KEY = 'quantrank.sidebar.collapsed';

export function AppShell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  // `animate` gates the sidebar's width/transform transition. It is true ONLY
  // for the ~250ms around an explicit user toggle (collapse chevron, mobile
  // hamburger, backdrop). Hydration (refresh) and breakpoint/orientation
  // changes (rotate) leave it false → the sidebar switches width/position
  // INSTANTLY there, never animating. An animated width on those events is the
  // "sidebar opens then shrinks back by itself" flash (Bug A).
  const [animate, setAnimate] = useState(false);

  useEffect(() => {
    const stored = typeof window !== 'undefined' && window.localStorage.getItem(STORAGE_KEY);
    if (stored === '1') setCollapsed(true);
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    window.localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0');
    // Keep the <html> class in lockstep with the live state so (a) the
    // pre-paint script in layout.tsx reflects the latest choice on the NEXT
    // refresh and (b) the pre-hydration width CSS (globals.css) never fights
    // React once interactive — the class is removed the instant we expand.
    document.documentElement.classList.toggle('sidebar-collapsed', collapsed);
  }, [collapsed, hydrated]);

  // Turn the transition back off after an explicit toggle settles, so the next
  // refresh / rotation / resize switches width instantly (Bug A). Re-armed by
  // collapsed/mobileOpen so a second toggle inside the window resets the timer.
  useEffect(() => {
    if (!animate) return;
    const t = window.setTimeout(() => setAnimate(false), 250);
    return () => window.clearTimeout(t);
  }, [animate, collapsed, mobileOpen]);

  const toggleCollapse = () => {
    setAnimate(true);
    setCollapsed((c) => !c);
  };
  const openMobile = () => {
    setAnimate(true);
    setMobileOpen(true);
  };
  const closeMobile = () => {
    setAnimate(true);
    setMobileOpen(false);
  };

  useEffect(() => {
    if (mobileOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [mobileOpen]);

  return (
    <div className="flex min-h-screen">
      <Sidebar
        collapsed={collapsed}
        animate={animate}
        onToggleCollapse={toggleCollapse}
        mobileOpen={mobileOpen}
        onMobileClose={closeMobile}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-white/95 px-4 py-2 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95 md:px-6">
          <button
            type="button"
            aria-label="Open navigation"
            onClick={openMobile}
            className="inline-flex h-11 w-11 items-center justify-center rounded-sm text-slate-600 transition-colors duration-150 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100 md:hidden"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>
          <span className="font-slab text-base font-semibold tracking-tight text-slate-900 dark:text-slate-100 md:hidden">QuantRank</span>
          {/* Desktop brand — Q + wordmark live in the TOP header ONLY while the
              sidebar is COLLAPSED (the 64px rail is too narrow for them, so they
              move out here). Hidden when expanded (brand lives in the rail then)
              and on mobile (the md:hidden wordmark above covers mobile). The
              `data-rail="show"` hook makes globals.css render it from the first
              paint on a collapsed refresh — same pre-paint mechanism as the rail
              brand, so no flash. Mirror of the rail Link's `data-rail="hide"`. */}
          <Link
            href="/"
            data-rail="show"
            aria-label="QuantRank home"
            className={`hidden min-w-0 items-center gap-2 text-slate-900 transition-opacity hover:opacity-80 dark:text-slate-100 ${collapsed ? 'md:flex' : ''}`}
          >
            <span aria-hidden="true" className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-sm bg-emerald-700 font-mono text-xs font-semibold text-white dark:bg-emerald-600 dark:text-white">Q</span>
            <span className="font-slab text-base font-semibold tracking-tight">QuantRank</span>
          </Link>
          <span className="ml-auto text-xs text-slate-500 dark:text-slate-400">US equity stock ranking</span>
          <ThemeToggle layout="icon" />
        </header>
        <Disclaimer />
        {/* Top padding kept tight (pt-4/pt-6) so the page content sits higher
            under the sticky header — the user wanted the app's overview pulled
            up (2026-05-31). Bottom padding stays roomy (pb-8/pb-10) so content
            doesn't crowd the footer. */}
        <main className="flex-1 px-4 pb-8 pt-4 md:px-8 md:pb-10 md:pt-6">
          {/* Content cap is a FIXED px (not max-w-6xl=72rem): with the fluid
              root font-size, a rem max-width expands to 1440px at the 20px
              ceiling, leaving the table/cards sparse on ultrawide. Pinning to
              1152px keeps the cap viewport-stable while inner rem spacing/text
              still scales (2026-05-29 responsive layout-density audit). */}
          <div className="mx-auto max-w-[1152px]">{children}</div>
        </main>
        <footer className="border-t border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
          <div className="mx-auto max-w-[1152px] px-4 py-6 text-xs text-slate-500 dark:text-slate-400 md:px-8">
            QuantRank · MIT licensed · Data refreshed every US trading day via GitHub Actions.
          </div>
        </footer>
      </div>
    </div>
  );
}
