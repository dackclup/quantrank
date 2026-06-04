'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

// TopNav — the Seeking-Alpha-style primary horizontal tab bar (Home · Ranking ·
// Analysis · Portfolio) that sits in the sticky app header, ALONGSIDE the
// left-rail Sidebar (user chose "keep both"). Active tab gets an emerald
// underline; the row scrolls horizontally on a narrow viewport. Client
// component — `usePathname` drives the active state.

type Tab = { label: string; href: string; isActive: (p: string) => boolean };

const TABS: Tab[] = [
  { label: 'Home', href: '/', isActive: (p) => p === '/' },
  // Ranking owns the table + every per-stock detail page (descendants of it).
  { label: 'Ranking', href: '/ranking', isActive: (p) => p.startsWith('/ranking') || p.startsWith('/stock/') },
  { label: 'Analysis', href: '/analysis', isActive: (p) => p.startsWith('/analysis') },
  { label: 'Portfolio', href: '/portfolio', isActive: (p) => p.startsWith('/portfolio') },
];

export function TopNav() {
  const pathname = usePathname() ?? '/';

  return (
    <nav
      aria-label="Top navigation"
      className="flex items-center gap-1 overflow-x-auto px-2 md:px-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      {TABS.map((t) => {
        const active = t.isActive(pathname);
        return (
          <Link
            key={t.href}
            href={t.href}
            aria-current={active ? 'page' : undefined}
            className={`inline-flex min-h-[44px] shrink-0 items-center whitespace-nowrap border-b-2 px-3 text-sm font-medium press transition-colors ${
              active
                ? 'border-emerald-700 text-slate-900 dark:border-emerald-400 dark:text-slate-100'
                : 'border-transparent text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100'
            }`}
          >
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}
