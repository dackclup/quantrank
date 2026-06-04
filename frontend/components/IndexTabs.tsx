// Index / universe sub-selector — the SECOND row beneath the CountryTabs market
// row (user request 2026-06-04: "below the country buttons, split into All
// stocks | S&P 500 | NASDAQ 100 …, and it changes per country"). It is SECONDARY
// to the country tabs, so it uses a quieter PILL idiom (filled-emerald active,
// muted disabled "soon") rather than repeating the 44px underline-tab treatment
// — the two-tier hierarchy (primary underline tabs → secondary pills) keeps the
// rows visually distinct.
//
// Only the US market is reachable today (the country tabs are non-interactive
// placeholders), and within US only the S&P 500 universe has data — so S&P 500
// is the ACTIVE pill and the rest are non-actionable "soon" placeholders. The
// index list is keyed per country so it can switch when the country selector
// becomes interactive in the multi-country expansion (Phase 5+).
//
// The pills are NON-ACTIONABLE (active = current selection as a <span>; the rest
// are `disabled`), so the 44px tappable-target rule does not apply — they sit at
// a compact secondary-row height under the 44px country tabs.

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
const ACTIVE_COUNTRY = 'US';

const PILL =
  'inline-flex min-h-[36px] shrink-0 items-center gap-1.5 whitespace-nowrap rounded-sm px-3 py-1.5 text-sm font-medium';

export function IndexTabs() {
  const indices = INDICES_BY_COUNTRY[ACTIVE_COUNTRY] ?? [];
  if (indices.length === 0) return null;

  return (
    <div
      role="group"
      aria-label="Index"
      className="flex items-center gap-1.5 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      {indices.map(({ code, label, name, active }) =>
        active ? (
          // Filled-emerald active pill — emerald-700 (#047857) is the canonical
          // brand fill (Q-logo / ComingSoon CTA). NOT in the globals.css soft-OKLCH
          // allowlist, so it renders raw in both modes; `dark:` pair is explicit
          // (white-on-emerald-700 = 5.5:1, the documented dark-fill pattern).
          <span
            key={code}
            aria-current="true"
            className={`${PILL} bg-emerald-700 text-white dark:bg-emerald-700 dark:text-white`}
          >
            {label}
          </span>
        ) : (
          <button
            key={code}
            type="button"
            disabled
            title={`${name} — coming soon`}
            className={`${PILL} cursor-not-allowed text-slate-500 ring-1 ring-inset ring-slate-200 dark:text-slate-400 dark:ring-slate-700`}
          >
            {label}
            <span className="text-[0.625rem] font-semibold uppercase tracking-wide">soon</span>
          </button>
        ),
      )}
    </div>
  );
}
