// Index / universe sub-selector — the SECOND row beneath the CountryTabs market
// row (user request 2026-06-04: "below the country buttons, split into All
// stocks | S&P 500 | NASDAQ 100 …, and it changes per country"). User then asked
// for it to use the SAME design as the buttons above ("ใช้ design แบบเดียวกับปุ่ม
// ด้านบน"), so it mirrors the CountryTabs / TopNav underline-tab idiom verbatim:
// active = emerald `border-b-2` underline + darker text, inactive = muted text.
// The two rows stay distinguishable by content (countries carry flags; indices
// are text labels) and position (index always sits under country).
//
// No solid fill anywhere — the active state is an underline, not a `bg-*` chip —
// so this does NOT reintroduce the PR #68 solid-fill anti-pattern.
//
// DATA-DRIVEN AVAILABILITY (PR 4 rework, 2026-06-16): a tab is interactive iff
// the loaded rankings.json actually has rows for that cohort (`availableCodes`
// prop). Tabs without data keep the "SOON" marker + are non-interactive. So on
// the current sp500-only data (502 rows, all sp500) the S&P 400 + All-stocks
// tabs stay "SOON"; on sp900 data (502 sp500 + 400 sp400 = 902) they become
// active.

'use client';

export type IndexCode = 'SPX' | 'MID' | 'SML' | 'NDX' | 'COMP' | 'DJI' | 'RUI' | 'RUT' | 'RUA' | 'ALL';

type IndexOption = { code: IndexCode; label: string; name: string };

// Per-country index universes. US is the only reachable market today.
// 'All stocks' LEADS as the default landing view (the mixed-universe
// aggregate); the named indices follow, ordered largest to smallest universe.
const INDICES_US: IndexOption[] = [
  { code: 'ALL',  label: 'All stocks',        name: 'All US-listed stocks' },
  { code: 'SPX',  label: 'S&P 500',          name: 'S&P 500 (large-cap)' },
  { code: 'MID',  label: 'S&P 400',           name: 'S&P MidCap 400' },
  { code: 'SML',  label: 'S&P 600',           name: 'S&P SmallCap 600' },
  { code: 'NDX',  label: 'NASDAQ 100',        name: 'NASDAQ 100' },
  { code: 'COMP', label: 'NASDAQ Composite',  name: 'NASDAQ Composite' },
  { code: 'DJI',  label: 'Dow 30',            name: 'Dow Jones Industrial Average' },
  { code: 'RUI',  label: 'Russell 1000',      name: 'Russell 1000 (large-cap)' },
  { code: 'RUT',  label: 'Russell 2000',      name: 'Russell 2000 (small-cap)' },
  { code: 'RUA',  label: 'Russell 3000',      name: 'Russell 3000 (broad market)' },
];

// Mirrors the CountryTabs / TopNav tab shape: 44px target, border-b-2 underline
// pulled onto the container's baseline via -mb-px.
const TAB =
  'inline-flex min-h-[44px] shrink-0 items-center gap-1.5 whitespace-nowrap border-b-2 -mb-px px-3 text-sm font-medium';

export function IndexTabs({
  activeTab,
  availableCodes,
  onTabChange,
}: {
  /** Currently selected tab code. */
  activeTab: IndexCode;
  /**
   * Set of index codes that have at least one row in the loaded data.
   * Tabs whose code is NOT in this set stay non-interactive ("SOON").
   */
  availableCodes: ReadonlySet<IndexCode>;
  onTabChange: (code: IndexCode) => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="Index"
      className="flex items-center gap-1 overflow-x-auto border-b border-slate-200 dark:border-slate-800 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      {INDICES_US.map(({ code, label, name }) => {
        const isActive = code === activeTab;
        const isAvailable = availableCodes.has(code);

        if (isActive) {
          // Active tab — `aria-current="true"` (selection in a control group,
          // NOT a page-navigation link). `tabIndex={0}` keeps the selected tab
          // keyboard-focusable as `role="tablist"` requires once interactive
          // peer tabs exist (sp900 data); full roving tabindex is deferred to
          // match the CountryTabs baseline.
          return (
            <span
              key={code}
              role="tab"
              aria-selected="true"
              aria-current="true"
              tabIndex={0}
              className={`${TAB} border-emerald-700 text-slate-900 dark:border-emerald-400 dark:text-slate-100`}
            >
              {label}
            </span>
          );
        }

        if (isAvailable) {
          // Interactive tab — has data, not currently selected.
          return (
            <button
              key={code}
              type="button"
              role="tab"
              aria-selected="false"
              title={name}
              onClick={() => onTabChange(code)}
              className={`${TAB} press border-transparent text-slate-600 hover:border-slate-300 hover:text-slate-900 dark:text-slate-400 dark:hover:border-slate-600 dark:hover:text-slate-100`}
            >
              {label}
            </button>
          );
        }

        // No data — non-interactive "SOON" placeholder.
        return (
          <button
            key={code}
            type="button"
            role="tab"
            aria-selected="false"
            disabled
            title={`${name} — coming soon`}
            className={`${TAB} cursor-not-allowed border-transparent text-slate-500 dark:text-slate-400`}
          >
            {label}
            <span className="text-[0.625rem] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">soon</span>
          </button>
        );
      })}
    </div>
  );
}
