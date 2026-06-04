import { CHIP_DOT } from './Chip';

// Index / universe sub-selector — the SECOND row beneath the CountryTabs market
// row (user request 2026-06-04: "below the country buttons, split into All
// stocks | S&P 500 | NASDAQ 100 …, and it changes per country"). It is SECONDARY
// to the country tabs, so it uses a quieter PILL idiom rather than repeating the
// 44px underline-tab treatment — the two-tier hierarchy (primary underline tabs
// → secondary pills) keeps the rows visually distinct via border-treatment +
// height, NOT via a louder color register.
//
// Tone discipline (frontend-design-system Rule 2, PR #68 anti-pattern): the
// active pill stays in the outlined-light chip FAMILY — the same emerald
// `bg-50 / ring-300 / text-900` tone as RecommendationBadge "bullish" — and
// signals "selected / live" with `font-semibold` + a leading status dot, NOT a
// `bg-emerald-700` solid fill (which would clash with the outlined-light chips
// in the ranking table directly below it). These are nav-control pills, not the
// `Chip` metadata primitive, so they compose the tone by hand (like ScoreBadge /
// SectorChip) and reuse only the canonical `CHIP_DOT` shape.
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
// TODO(Phase-5+): becomes a prop when the country selector turns interactive.
const ACTIVE_COUNTRY = 'US';

// Shared pill shape (layout + 2px radius + inset ring). Font-weight is added
// per-state (semibold active / medium disabled) so the weights don't collide.
const PILL =
  'inline-flex min-h-[36px] shrink-0 items-center gap-1.5 whitespace-nowrap rounded-sm ring-1 ring-inset px-3 py-1.5 text-sm';

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
          // Active = outlined-light emerald "bullish" tone + font-semibold + a
          // leading dot. `aria-current="true"` (not "page"): this is a selection
          // indicator in a control group, NOT a page-navigation link.
          <span
            key={code}
            aria-current="true"
            className={`${PILL} font-semibold bg-emerald-50 text-emerald-900 ring-emerald-300 dark:bg-emerald-900/30 dark:text-emerald-100 dark:ring-emerald-800`}
          >
            <span className={`${CHIP_DOT} bg-emerald-500 dark:bg-emerald-400`} aria-hidden="true" />
            {label}
          </span>
        ) : (
          <button
            key={code}
            type="button"
            disabled
            title={`${name} — coming soon`}
            className={`${PILL} font-medium cursor-not-allowed text-slate-500 ring-slate-200 dark:text-slate-400 dark:ring-slate-800`}
          >
            {label}
            <span className="text-[0.625rem] font-semibold uppercase tracking-wide">soon</span>
          </button>
        ),
      )}
    </div>
  );
}
