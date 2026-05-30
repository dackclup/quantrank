'use client';

import { useEffect, useState } from 'react';
import { useTheme } from 'next-themes';

// LedgerCraft Phase 3b — theme cycle button. Three-state cycle:
// system → light → dark → system. The `mounted` guard prevents
// hydration mismatch — `useTheme()` returns the SSR fallback on
// first render, then the real theme post-hydrate; rendering the
// icon only after mount avoids the "moon icon on initial render
// even when light is active" flicker.
//
// Two layouts:
// - "icon" — square 32px button (default, used in sidebar footer)
// - "row" — full-width row with label (used when expanded)

interface ThemeToggleProps {
  layout?: 'icon' | 'row';
}

const ICONS = {
  light: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2" />
      <path d="M12 20v2" />
      <path d="m4.93 4.93 1.41 1.41" />
      <path d="m17.66 17.66 1.41 1.41" />
      <path d="M2 12h2" />
      <path d="M20 12h2" />
      <path d="m6.34 17.66-1.41 1.41" />
      <path d="m19.07 4.93-1.41 1.41" />
    </svg>
  ),
  dark: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  ),
  system: (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="2" y="3" width="20" height="14" rx="2" />
      <line x1="8" y1="21" x2="16" y2="21" />
      <line x1="12" y1="17" x2="12" y2="21" />
    </svg>
  ),
};

const LABELS: Record<string, string> = {
  light: 'Light',
  dark: 'Dark',
  system: 'System',
};

const NEXT_THEME: Record<string, 'light' | 'dark' | 'system'> = {
  system: 'light',
  light: 'dark',
  dark: 'system',
};

export function ThemeToggle({ layout = 'icon' }: ThemeToggleProps) {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const current = mounted ? (theme ?? 'system') : 'system';
  const safeKey = current in ICONS ? current : 'system';
  const icon = ICONS[safeKey as keyof typeof ICONS];
  const label = LABELS[safeKey] ?? 'System';

  const cycle = () => setTheme(NEXT_THEME[safeKey] ?? 'system');

  if (layout === 'row') {
    return (
      <button
        type="button"
        onClick={cycle}
        aria-label={`Theme: ${label} — click to cycle`}
        className="group flex w-full items-center gap-2.5 rounded-sm px-2 py-1.5 text-sm text-slate-600 transition-colors hover:bg-slate-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
      >
        <span className="shrink-0 text-slate-500 group-hover:text-slate-700 dark:text-slate-400 dark:group-hover:text-slate-200">
          {icon}
        </span>
        <span className="truncate">Theme</span>
        <span className="ml-auto text-[0.6875rem] font-medium text-slate-500 dark:text-slate-400">
          {label}
        </span>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={cycle}
      aria-label={`Theme: ${label} — click to cycle`}
      title={`Theme: ${label}`}
      className="inline-flex h-8 w-8 items-center justify-center rounded-sm text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
    >
      {icon}
    </button>
  );
}
