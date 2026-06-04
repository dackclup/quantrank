'use client';

import { useEffect, useRef } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { ThemeToggle } from './ThemeToggle';

// Sidebar — an overlay DRAWER (closed by default, ALL breakpoints) opened by the
// ☰ button in the AppShell header. It sits BELOW the sticky top chrome
// (top = the header height) so the header — with the ☰→✕ toggle — stays visible
// and clickable. Backdrop tap / Esc (AppShell) / a nav-link tap all close it;
// AppShell owns the `open` state. The brand lives in the header now, not here
// (user choice 2026-06-04, replacing the old collapse-to-rail model).
//
// `top-[calc(3.5rem_+_46px)]` MUST equal the AppShell header height (controls
// row h-14 = 3.5rem + the 44px tab row + 2px borders) — keep the two in lockstep.
//
// Active route: usePathname() returns `/ranking` + `/stock/<t>/`, both highlight
// Rankings (detail pages are descendants of the ranking view).

type NavItem = { label: string; href: string; isActive: (p: string) => boolean; icon: JSX.Element };

const BROWSE_ITEMS: NavItem[] = [
  {
    label: 'Rankings',
    href: '/ranking',
    isActive: (p) => p.startsWith('/ranking') || p.startsWith('/stock/'),
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <line x1="3" y1="12" x2="3" y2="21" />
        <line x1="9" y1="3" x2="9" y2="21" />
        <line x1="15" y1="8" x2="15" y2="21" />
        <line x1="21" y1="14" x2="21" y2="21" />
      </svg>
    ),
  },
  {
    label: 'Sectors',
    href: '/sectors',
    isActive: (p) => p.startsWith('/sectors'),
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
      </svg>
    ),
  },
];

const INSIGHTS_ITEMS: NavItem[] = [
  {
    label: 'Top Movers',
    href: '/movers',
    isActive: (p) => p.startsWith('/movers'),
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <polyline points="3 17 9 11 13 15 21 7" />
        <polyline points="15 7 21 7 21 13" />
      </svg>
    ),
  },
];

export function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname() ?? '/';
  const asideRef = useRef<HTMLElement>(null);

  // Modal focus management (WCAG 2.4.3, the FilterDrawer standard — docs/GOTCHAS.md):
  // make the CLOSED off-canvas drawer fully `inert` so its links aren't Tab-reachable
  // behind the page, and move focus to the first nav link when it OPENS. AppShell
  // restores focus to the toggle on close; Esc (AppShell) is the keyboard close (the
  // visible ✕ lives in the header, outside the trapped dialog).
  useEffect(() => {
    const root = asideRef.current;
    if (!root) return;
    root.inert = !open;
    if (open) root.querySelector<HTMLElement>('a[href],button:not([disabled])')?.focus();
  }, [open]);

  // Focus trap — wrap Tab / Shift+Tab within the open drawer.
  const trapTab = (e: React.KeyboardEvent) => {
    if (e.key !== 'Tab') return;
    const root = asideRef.current;
    if (!root) return;
    const f = root.querySelectorAll<HTMLElement>('a[href],button:not([disabled]),[tabindex]:not([tabindex="-1"])');
    if (f.length === 0) return;
    const first = f[0];
    const last = f[f.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  };

  return (
    <>
      {/* Backdrop — starts BELOW the header so the ☰/✕ toggle stays clickable.
          Decorative mouse close-target (aria-hidden + not a Tab stop); the modal
          is closed by Esc / the header ✕ / a backdrop tap. */}
      <button
        type="button"
        aria-hidden="true"
        tabIndex={-1}
        onClick={onClose}
        className={`fixed inset-x-0 bottom-0 top-[calc(3.5rem_+_46px)] z-30 bg-slate-900/40 transition-opacity duration-200 dark:bg-black/60 ${
          open ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
      />

      <aside
        ref={asideRef}
        id="sidebar-drawer"
        role="dialog"
        aria-modal={open}
        aria-label="Primary navigation"
        onKeyDown={trapTab}
        className={`fixed bottom-0 left-0 top-[calc(3.5rem_+_46px)] z-40 flex w-64 flex-col border-r border-slate-200 bg-white transition-transform duration-200 ease-in-out motion-reduce:transition-none dark:border-slate-800 dark:bg-slate-950 ${
          open ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <nav className="flex-1 overflow-y-auto px-2 py-4">
          <SidebarSection label="Browse">
            {BROWSE_ITEMS.map((item) => (
              <SidebarLink
                key={item.label}
                href={item.href}
                label={item.label}
                icon={item.icon}
                active={item.isActive(pathname)}
                onClick={onClose}
              />
            ))}
          </SidebarSection>

          <SidebarSection label="Insights">
            {INSIGHTS_ITEMS.map((item) => (
              <SidebarLink
                key={item.label}
                href={item.href}
                label={item.label}
                icon={item.icon}
                active={item.isActive(pathname)}
                onClick={onClose}
              />
            ))}
          </SidebarSection>
        </nav>

        {/* Footer — theme toggle + version chip (the version chip is the
            build-time NEXT_PUBLIC_APP_VERSION, never hardcoded). */}
        <div className="border-t border-slate-200 px-2 py-2 dark:border-slate-800">
          <ThemeToggle layout="row" />
          <div className="mt-2 px-2 pb-1 text-[0.6875rem] leading-snug text-slate-500 dark:text-slate-400">
            <p className="font-semibold uppercase tracking-[0.14em] text-slate-600 dark:text-slate-400">{process.env.NEXT_PUBLIC_APP_VERSION || 'dev'} · MIT</p>
            <p className="mt-1">Educational use only.</p>
          </div>
        </div>
      </aside>
    </>
  );
}

function SidebarSection({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <div className="px-2 pb-1.5 text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
        {label}
      </div>
      <ul className="space-y-0.5">{children}</ul>
    </div>
  );
}

function SidebarLink({
  href,
  label,
  icon,
  active = false,
  onClick,
}: {
  href: string;
  label: string;
  icon: React.ReactNode;
  active?: boolean;
  onClick?: () => void;
}) {
  const base = `group flex min-h-[44px] items-center gap-2.5 rounded-sm px-2 py-1.5 text-sm press ${
    active
      ? 'bg-slate-100 font-medium text-slate-900 dark:bg-slate-800 dark:text-slate-100'
      : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100'
  }`;

  return (
    <li>
      <Link href={href} onClick={onClick} className={base}>
        <span className={`shrink-0 ${active ? 'text-slate-900 dark:text-slate-100' : 'text-slate-500 group-hover:text-slate-700 dark:text-slate-400 dark:group-hover:text-slate-200'}`}>
          {icon}
        </span>
        <span className="truncate">{label}</span>
      </Link>
    </li>
  );
}
