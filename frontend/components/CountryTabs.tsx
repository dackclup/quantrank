import US from 'country-flag-icons/react/3x2/US';
import TH from 'country-flag-icons/react/3x2/TH';
import CN from 'country-flag-icons/react/3x2/CN';
import JP from 'country-flag-icons/react/3x2/JP';
import GB from 'country-flag-icons/react/3x2/GB';

// Country / market selector shown above the ranking. Only the US universe has
// data today (the S&P 500), so US is the ACTIVE market; the rest are
// placeholders ("Soon") for the planned multi-country expansion — UI scaffold
// ahead of the per-country ingest (a separate Phase-5+ effort: new per-country
// universes + filing sources + currency). The 5th market (UK) is a placeholder
// pick; swap freely. Flags via `country-flag-icons` per-country STATIC imports
// (the project flag-icon pattern — see ListingChips / §Gotchas).

const MARKETS = [
  { code: 'US', label: 'US', name: 'United States', Flag: US, available: true },
  { code: 'TH', label: 'TH', name: 'Thailand', Flag: TH, available: false },
  { code: 'CN', label: 'CN', name: 'China', Flag: CN, available: false },
  { code: 'JP', label: 'JP', name: 'Japan', Flag: JP, available: false },
  { code: 'GB', label: 'UK', name: 'United Kingdom', Flag: GB, available: false },
] as const;

const PILL =
  'inline-flex min-h-[44px] items-center gap-1.5 rounded-sm px-2.5 py-1.5 text-sm font-medium ring-1 ring-inset';

export function CountryTabs() {
  return (
    <div role="group" aria-label="Market" className="flex flex-wrap gap-2">
      {MARKETS.map(({ code, label, name, Flag, available }) =>
        available ? (
          <span
            key={code}
            aria-current="true"
            className={`${PILL} bg-emerald-50 text-emerald-800 ring-emerald-300 dark:bg-emerald-900/30 dark:text-emerald-200 dark:ring-emerald-800`}
          >
            <Flag title={name} className="h-4 w-6 rounded-[2px]" />
            {label} stocks
          </span>
        ) : (
          <button
            key={code}
            type="button"
            disabled
            title={`${name} — coming soon`}
            className={`${PILL} cursor-not-allowed bg-white text-slate-400 ring-slate-200 dark:bg-slate-900 dark:text-slate-500 dark:ring-slate-500`}
          >
            <Flag title={name} className="h-4 w-6 rounded-[2px] opacity-60" />
            {label}
            <span className="ml-0.5 rounded-sm bg-slate-100 px-1 text-[0.625rem] font-semibold uppercase tracking-wide text-slate-400 dark:bg-slate-800 dark:text-slate-500">
              soon
            </span>
          </button>
        ),
      )}
    </div>
  );
}
