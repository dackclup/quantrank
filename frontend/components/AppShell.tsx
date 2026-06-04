import Link from 'next/link';

import { ThemeToggle } from './ThemeToggle';
import { TopNav } from './TopNav';

// App shell — a FULL-WIDTH top chrome (brand + theme-toggle row, then the tab
// nav) over a full-width content column, plus the footer disclaimer. The former
// overlay Sidebar drawer (and its ☰ toggle + focus-trap state) was removed
// 2026-06-04 at user request ("เอาแถบด้านข้างออก"); the TopNav tab bar is now the
// SOLE navigation surface, so this shell has no client state and is a plain
// Server Component. The build-version chip that lived in the drawer footer moved
// into the page footer below (still the build-time NEXT_PUBLIC_APP_VERSION).

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      {/* Full-width top chrome — brand + theme toggle, then the tab nav; spans
          edge-to-edge. */}
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95">
        <div className="flex h-14 items-center gap-2 px-4 md:px-6">
          {/* Brand — Q logo + wordmark. */}
          <Link
            href="/"
            aria-label="QuantRank home"
            className="flex min-w-0 items-center gap-2 text-slate-900 press hover:opacity-80 dark:text-slate-100"
          >
            <span aria-hidden="true" className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-sm bg-emerald-700 font-mono text-xs font-semibold text-white dark:bg-emerald-700 dark:text-white">Q</span>
            <span className="font-slab text-base font-semibold tracking-tight">QuantRank</span>
          </Link>
          <div className="ml-auto flex items-center">
            <ThemeToggle layout="icon" />
          </div>
        </div>
        {/* Primary tab nav (Home · Ranking · News · Analysis · Portfolio). */}
        <div className="border-t border-slate-200 dark:border-slate-800">
          <TopNav />
        </div>
      </header>
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
          {/* Build-version chip (relocated from the removed Sidebar footer) — the
              build-time NEXT_PUBLIC_APP_VERSION, never a hardcoded version. */}
          <p>
            QuantRank{' '}
            <span className="font-mono">{process.env.NEXT_PUBLIC_APP_VERSION || 'dev'}</span> · MIT
            licensed · Data refreshed every US trading day via GitHub Actions.
          </p>
        </div>
      </footer>
    </div>
  );
}
