'use client';

import { useEffect, useState } from 'react';
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

  useEffect(() => {
    const stored = typeof window !== 'undefined' && window.localStorage.getItem(STORAGE_KEY);
    if (stored === '1') setCollapsed(true);
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    window.localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0');
  }, [collapsed, hydrated]);

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
        onToggleCollapse={() => setCollapsed((c) => !c)}
        mobileOpen={mobileOpen}
        onMobileClose={() => setMobileOpen(false)}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-white/95 px-4 py-2 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95 md:px-6">
          <button
            type="button"
            aria-label="Open navigation"
            onClick={() => setMobileOpen(true)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-md text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100 md:hidden"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>
          <span className="font-slab text-base font-semibold tracking-tight text-slate-900 dark:text-slate-100 md:hidden">QuantRank</span>
          <span className="ml-auto text-xs text-slate-500 dark:text-slate-400">US equity stock ranking</span>
          <ThemeToggle layout="icon" />
        </header>
        <Disclaimer />
        <main className="flex-1 px-4 py-8 md:px-8 md:py-10">
          <div className="mx-auto max-w-6xl">{children}</div>
        </main>
        <footer className="border-t border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
          <div className="mx-auto max-w-6xl px-4 py-6 text-xs text-slate-500 dark:text-slate-400 md:px-8">
            QuantRank · MIT licensed · Data refreshed every US trading day via GitHub Actions.
          </div>
        </footer>
      </div>
    </div>
  );
}
