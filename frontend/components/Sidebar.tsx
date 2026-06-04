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

type NavItem = { label: string; href: string; isActive: (p: string) => boolean; icon: JSX.Element };

// Primary destinations. `/` + `/stock/*` both highlight Rankings (detail pages
// are descendants of the ranking view); the other entries match on their own
// path prefix.
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

interface SidebarProps {
  collapsed: boolean;
  /** True only for the ~250ms around an explicit user toggle — gates the
   *  width/max-width/transform transition so refresh + rotation switch
   *  instantly (no "opens then shrinks back" flash). Owned by AppShell.
   *  max-width MUST be transitioned alongside width: the collapsed rail
   *  toggles `md:max-w-[64px]` (+ the globals.css pre-paint rule sets
   *  `max-width:4rem`), and an un-transitioned max-width snaps to 64px on
   *  collapse → clamps width instantly → the shrink "snaps" while expand
   *  (growing max-width never clamps) stays smooth = asymmetric jank. */
  animate: boolean;
  onToggleCollapse: () => void;
  mobileOpen: boolean;
  onMobileClose: () => void;
}

export function Sidebar({ collapsed, animate, onToggleCollapse, mobileOpen, onMobileClose }: SidebarProps) {
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
        data-sidebar-rail=""
        className={`fixed inset-y-0 left-0 z-40 flex flex-col border-r border-slate-200 bg-white ${
          animate
            ? '[transition:transform_200ms_ease-in-out,width_200ms_ease-in-out,max-width_200ms_ease-in-out]'
            : 'transition-none'
        } motion-reduce:transition-none dark:border-slate-800 dark:bg-slate-950 md:sticky md:top-0 md:h-screen md:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        } w-64 ${collapsed ? 'md:w-16 md:max-w-[64px]' : 'md:w-60 md:max-w-[240px]'}`}
      >
        {/* Header: brand (Q + "QuantRank") + collapse toggle. The expanded rail
            (240px) shows Q + wordmark on the left with the chevron pushed right
            (ml-auto). When COLLAPSED at md+ the 64px rail keeps ONLY the chevron
            (original 32px square, centered) — the brand moves OUT to the top
            header (AppShell, `data-rail="show"`), since the narrow rail has no
            room for it (2026-05-30 user request). The mobile drawer (< md) always
            shows the full horizontal row (Q + wordmark + close-X) — `data-rail`
            CSS only fires at md+, so the drawer brand never hides. */}
        <div
          data-rail="header"
          className={`flex h-14 items-center gap-2 border-b border-slate-200 px-3 dark:border-slate-800${collapsed ? ' md:justify-center md:px-2' : ''}`}
        >
          <Link
            href="/"
            onClick={onMobileClose}
            data-rail="hide"
            className="flex min-h-[44px] min-w-0 items-center gap-2 text-slate-900 press hover:opacity-80 dark:text-slate-100"
            aria-label="QuantRank home"
          >
            <span aria-hidden="true" className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-sm bg-emerald-700 font-mono text-xs font-semibold text-white dark:bg-emerald-700 dark:text-white">Q</span>
            {/* The whole brand Link carries `data-rail="hide"`, so it (Q +
                wordmark together) hides at md+ when collapsed — it lives in the
                top header then. On mobile (< md) the rule doesn't apply, so the
                drawer keeps the full brand. */}
            <span className="font-slab text-lg font-semibold tracking-tight">QuantRank</span>
          </Link>
          <button
            type="button"
            data-rail="chevron"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            onClick={onToggleCollapse}
            className={`hidden h-8 w-8 items-center justify-center rounded-sm text-slate-500 press hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100 md:inline-flex ${collapsed ? '' : 'ml-auto'}`}
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
            className="ml-auto inline-flex h-11 w-11 items-center justify-center rounded-sm text-slate-500 press hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100 md:hidden"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Nav sections */}
        <nav className="flex-1 overflow-y-auto px-2 py-4">
          <SidebarSection label="Browse" collapsed={collapsed}>
            {BROWSE_ITEMS.map((item) => (
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

          <SidebarSection label="Insights" collapsed={collapsed}>
            {INSIGHTS_ITEMS.map((item) => (
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
          <div data-rail="hide" className={collapsed ? 'md:hidden' : ''}>
            <ThemeToggle layout="row" />
          </div>
          <div data-rail="show" className={`hidden justify-center${collapsed ? ' md:flex' : ''}`}>
            <ThemeToggle layout="icon" />
          </div>
          <div data-rail="hide" className={`mt-2 px-2 pb-1 text-[0.6875rem] leading-snug text-slate-500 dark:text-slate-400${collapsed ? ' md:hidden' : ''}`}>
            <p className="font-semibold uppercase tracking-[0.14em] text-slate-600 dark:text-slate-400">{process.env.NEXT_PUBLIC_APP_VERSION || 'dev'} · MIT</p>
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
      <div data-rail="hide" className={`px-2 pb-1.5 text-[0.625rem] font-semibold uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400${collapsed ? ' md:hidden' : ''}`}>
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
  const base = `group flex min-h-[44px] items-center gap-2.5 rounded-sm px-2 py-1.5 text-sm press ${
    active
      ? 'bg-slate-100 font-medium text-slate-900 dark:bg-slate-800 dark:text-slate-100'
      : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100'
  } ${collapsed ? 'md:justify-center md:px-0' : ''}`;

  const content = (
    <>
      <span className={`shrink-0 ${active ? 'text-slate-900 dark:text-slate-100' : 'text-slate-500 group-hover:text-slate-700 dark:text-slate-400 dark:group-hover:text-slate-200'}`}>
        {icon}
      </span>
      <span data-rail="hide" className={`truncate${collapsed ? ' md:hidden' : ''}`}>{label}</span>
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
          data-rail="hide"
          className={`ml-auto text-slate-500 dark:text-slate-400${collapsed ? ' md:hidden' : ''}`}
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
        <a href={href} target="_blank" rel="noreferrer" data-rail="navlink" className={base} title={collapsed ? label : undefined}>
          {content}
        </a>
      ) : (
        <Link href={href} onClick={onClick} data-rail="navlink" className={base} title={collapsed ? label : undefined}>
          {content}
        </Link>
      )}
    </li>
  );
}
