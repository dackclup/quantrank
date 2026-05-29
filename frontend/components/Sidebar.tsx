'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ThemeToggle } from './ThemeToggle';

// LedgerCraft Phase 3c — left-rail navigation. Desktop: sticky 240px
// column with collapse-to-rail-icons (64px) toggle. Mobile: hidden by
// default, slides in as overlay drawer when AppShell opens it.
//
// Active route detection: usePathname() returns `/` for home and
// `/stock/<ticker>/` for detail pages — both highlight "Rankings"
// since the detail pages are descendants of the rankings view.

const NAV_ITEMS: Array<{ label: string; href: string; isActive: (p: string) => boolean; icon: JSX.Element }> = [
  {
    label: 'Rankings',
    href: '/',
    isActive: (p) => p === '/' || p.startsWith('/stock/'),
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <line x1="3" y1="12" x2="3" y2="21" />
        <line x1="9" y1="3" x2="9" y2="21" />
        <line x1="15" y1="8" x2="15" y2="21" />
        <line x1="21" y1="14" x2="21" y2="21" />
      </svg>
    ),
  },
];

const RESOURCE_ITEMS: Array<{ label: string; href: string; external: true; icon: JSX.Element }> = [
  {
    label: 'Methodology',
    href: 'https://github.com/dackclup/quantrank/blob/main/docs/METHODOLOGY.md',
    external: true,
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
      </svg>
    ),
  },
  {
    label: 'Design',
    href: 'https://github.com/dackclup/quantrank/blob/main/docs/design.md',
    external: true,
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="13.5" cy="6.5" r="1.5" />
        <circle cx="17.5" cy="10.5" r="1.5" />
        <circle cx="8.5" cy="7.5" r="1.5" />
        <circle cx="6.5" cy="12.5" r="1.5" />
        <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125 0-.937.75-1.687 1.688-1.687h1.937c2.766 0 5.012-2.246 5.012-5.012C21.41 6.151 17.169 2 12 2z" />
      </svg>
    ),
  },
  {
    label: 'GitHub',
    href: 'https://github.com/dackclup/quantrank',
    external: true,
    icon: (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.11.79-.25.79-.56 0-.27-.01-1-.02-1.96-3.2.7-3.87-1.54-3.87-1.54-.52-1.32-1.28-1.68-1.28-1.68-1.05-.71.08-.7.08-.7 1.16.08 1.77 1.19 1.77 1.19 1.03 1.77 2.7 1.26 3.36.96.1-.75.4-1.26.73-1.55-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.18-3.09-.12-.29-.51-1.47.11-3.06 0 0 .97-.31 3.18 1.18a11 11 0 0 1 5.79 0c2.21-1.49 3.18-1.18 3.18-1.18.63 1.59.23 2.77.12 3.06.73.8 1.18 1.83 1.18 3.09 0 4.42-2.69 5.39-5.25 5.68.41.35.78 1.05.78 2.12 0 1.53-.01 2.77-.01 3.14 0 .31.21.67.79.55C20.21 21.39 23.5 17.08 23.5 12 23.5 5.65 18.35.5 12 .5z" />
      </svg>
    ),
  },
];

interface SidebarProps {
  collapsed: boolean;
  onToggleCollapse: () => void;
  mobileOpen: boolean;
  onMobileClose: () => void;
}

export function Sidebar({ collapsed, onToggleCollapse, mobileOpen, onMobileClose }: SidebarProps) {
  const pathname = usePathname() ?? '/';

  return (
    <>
      {/* Mobile overlay backdrop — always-mounted opacity toggle (not
          conditional render) so the fade-in/out animates instead of
          snap-appearing. Mirrors the FilterDrawer backdrop pattern.
          tabIndex flips to -1 when closed so the invisible backdrop
          can't trap keyboard focus. */}
      <button
        type="button"
        aria-label="Close navigation"
        onClick={onMobileClose}
        aria-hidden={!mobileOpen}
        tabIndex={mobileOpen ? 0 : -1}
        className={`fixed inset-0 z-30 bg-slate-900/40 transition-opacity duration-200 md:hidden ${
          mobileOpen ? 'opacity-100' : 'pointer-events-none opacity-0'
        }`}
      />

      <aside
        aria-label="Primary navigation"
        className={`fixed inset-y-0 left-0 z-40 flex flex-col border-r border-slate-200 bg-white [transition:transform_200ms_ease-out,width_200ms_ease-out] dark:border-slate-800 dark:bg-slate-950 md:sticky md:top-0 md:h-screen md:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        } w-64 ${collapsed ? 'md:w-16' : 'md:w-60'}`}
      >
        {/* Wordmark + collapse toggle */}
        <div className="flex h-14 items-center gap-2 border-b border-slate-200 px-3 dark:border-slate-800">
          <Link
            href="/"
            onClick={onMobileClose}
            className="flex min-w-0 items-center gap-2 text-slate-900 hover:opacity-80 dark:text-slate-100"
            aria-label="QuantRank home"
          >
            <span aria-hidden="true" className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-sm bg-emerald-700 font-mono text-xs font-semibold text-white dark:bg-emerald-600 dark:text-white">Q</span>
            {/* Mobile drawer always shows the wordmark; `collapsed` is a
                desktop-only (md+) concept, so it only hides at md+ via CSS. */}
            <span className={`font-slab text-lg font-semibold tracking-tight${collapsed ? ' md:hidden' : ''}`}>QuantRank</span>
          </Link>
          <button
            type="button"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            onClick={onToggleCollapse}
            className="ml-auto hidden h-8 w-8 items-center justify-center rounded-sm text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100 md:inline-flex"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className={`transition-transform duration-200 ${collapsed ? 'rotate-180' : ''}`}
              aria-hidden="true"
            >
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
          <button
            type="button"
            aria-label="Close navigation"
            onClick={onMobileClose}
            className="ml-auto inline-flex h-8 w-8 items-center justify-center rounded-sm text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100 md:hidden"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Nav sections */}
        <nav className="flex-1 overflow-y-auto px-2 py-4">
          <SidebarSection label="Navigation" collapsed={collapsed}>
            {NAV_ITEMS.map((item) => (
              <SidebarLink
                key={item.label}
                href={item.href}
                label={item.label}
                icon={item.icon}
                active={item.isActive(pathname)}
                collapsed={collapsed}
                onClick={onMobileClose}
              />
            ))}
          </SidebarSection>

          <SidebarSection label="Resources" collapsed={collapsed}>
            {RESOURCE_ITEMS.map((item) => (
              <SidebarLink
                key={item.label}
                href={item.href}
                label={item.label}
                icon={item.icon}
                external
                collapsed={collapsed}
              />
            ))}
          </SidebarSection>
        </nav>

        {/* Footer block — theme toggle + version chip.
            `collapsed` is a DESKTOP-only (md+) feature — its toggle button is
            `md:inline-flex` and unreachable on mobile. So the mobile drawer
            ALWAYS shows the full row toggle + version chip; `collapsed` only
            swaps to the icon toggle / hides the chip at md+, via CSS only.
            Driving this off `collapsed` alone (not a JS/`mobileOpen` branch)
            keeps content in the DOM at all breakpoints → no hydration mismatch
            and no `mobileOpen`-leaks-into-desktop coupling. The two toggles are
            mutually exclusive per breakpoint (the hidden one is display:none,
            so a11y sees exactly one). 2026-05-29 mobile-drawer fix. */}
        <div className="border-t border-slate-200 px-2 py-2 dark:border-slate-800">
          <div className={collapsed ? 'md:hidden' : ''}>
            <ThemeToggle layout="row" />
          </div>
          <div className={`hidden justify-center${collapsed ? ' md:flex' : ''}`}>
            <ThemeToggle layout="icon" />
          </div>
          <div className={`mt-2 px-2 pb-1 text-[11px] leading-snug text-slate-500 dark:text-slate-400${collapsed ? ' md:hidden' : ''}`}>
            <p className="font-semibold uppercase tracking-[0.14em] text-slate-600 dark:text-slate-400">v1.4.0 · MIT</p>
            <p className="mt-1">Educational use only.</p>
          </div>
        </div>
      </aside>
    </>
  );
}

function SidebarSection({
  label,
  collapsed,
  children,
}: {
  label: string;
  collapsed: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-4">
      <div className={`px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400${collapsed ? ' md:hidden' : ''}`}>
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
  external = false,
  collapsed,
  onClick,
}: {
  href: string;
  label: string;
  icon: React.ReactNode;
  active?: boolean;
  external?: boolean;
  collapsed: boolean;
  onClick?: () => void;
}) {
  const base = `group flex items-center gap-2.5 rounded-sm px-2 py-1.5 text-sm transition-colors ${
    active
      ? 'bg-slate-100 font-medium text-slate-900 dark:bg-slate-800 dark:text-slate-100'
      : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100'
  } ${collapsed ? 'md:justify-center md:px-0' : ''}`;

  const content = (
    <>
      <span className={`shrink-0 ${active ? 'text-slate-900 dark:text-slate-100' : 'text-slate-500 group-hover:text-slate-700 dark:text-slate-400 dark:group-hover:text-slate-200'}`}>
        {icon}
      </span>
      <span className={`truncate${collapsed ? ' md:hidden' : ''}`}>{label}</span>
      {external && (
        <svg
          width="11"
          height="11"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`ml-auto text-slate-400 dark:text-slate-500${collapsed ? ' md:hidden' : ''}`}
          aria-hidden="true"
        >
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
          <polyline points="15 3 21 3 21 9" />
          <line x1="10" y1="14" x2="21" y2="3" />
        </svg>
      )}
    </>
  );

  return (
    <li>
      {external ? (
        <a href={href} target="_blank" rel="noreferrer" className={base} title={collapsed ? label : undefined}>
          {content}
        </a>
      ) : (
        <Link href={href} onClick={onClick} className={base} title={collapsed ? label : undefined}>
          {content}
        </Link>
      )}
    </li>
  );
}
