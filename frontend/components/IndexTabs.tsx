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
// Only the US market is reachable today (the country tabs are non-interactive
// placeholders), and within US only the S&P 500 universe has data — so S&P 500
// is the ACTIVE tab and the rest are non-actionable "soon" placeholders. The
// index list is keyed per country so it can switch when the country selector
// becomes interactive in the multi-country expansion (Phase 5+).

type IndexOption = { code: string; label: string; name: string; active?: boolean };

// Per-country index universes. US is the only reachable market today; the TH /
// CN / JP / GB lists land with the multi-country expansion, so the structure
// documents the per-country intent even though only US renders right now.
const INDICES_BY_COUNTRY: Record<string, IndexOption[]> = {
  US: [
    { code: 'ALL', label: 'All stocks', name: 'All US-listed stocks' },
    { code: 'SPX', label: 'S&P 500', name: 'S&P 500', active: true },
    { code: 'NDX', label: 'NASDAQ 100', name: 'NASDAQ 100' },
    { code: 'DJI', label: 'Dow 30', name: 'Dow Jones Industrial Average' },
  ],
};

// Active country mirrors CountryTabs (US is the live universe today).
// TODO(Phase-5+): becomes a prop when the country selector turns interactive.
const ACTIVE_COUNTRY = 'US';

// Mirrors the CountryTabs / TopNav tab shape: 44px target, border-b-2 underline
// pulled onto the container's baseline via -mb-px.
const TAB =
  'inline-flex min-h-[44px] shrink-0 items-center gap-1.5 whitespace-nowrap border-b-2 -mb-px px-3 text-sm font-medium';

export function IndexTabs() {
  const indices = INDICES_BY_COUNTRY[ACTIVE_COUNTRY] ?? [];
  if (indices.length === 0) return null;

  return (
    <div
      role="group"
      aria-label="Index"
      className="flex items-center gap-1 overflow-x-auto border-b border-slate-200 dark:border-slate-800 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      {indices.map(({ code, label, name, active }) =>
        active ? (
          // `aria-current="true"` (not "page"): a selection indicator in a
          // control group, NOT a page-navigation link.
          <span
            key={code}
            aria-current="true"
            className={`${TAB} border-emerald-700 text-slate-900 dark:border-emerald-400 dark:text-slate-100`}
          >
            {label}
          </span>
        ) : (
          <button
            key={code}
            type="button"
            disabled
            title={`${name} — coming soon`}
            className={`${TAB} cursor-not-allowed border-transparent text-slate-500 dark:text-slate-400`}
          >
            {label}
            <span className="text-[0.625rem] font-semibold uppercase tracking-wide">soon</span>
          </button>
        ),
      )}
    </div>
  );
}
