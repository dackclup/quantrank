import US from 'country-flag-icons/react/3x2/US';
import TH from 'country-flag-icons/react/3x2/TH';
import CN from 'country-flag-icons/react/3x2/CN';
import JP from 'country-flag-icons/react/3x2/JP';
import GB from 'country-flag-icons/react/3x2/GB';

// Country / market selector shown above the ranking, styled to MATCH the TopNav
// tab bar (underline-active, muted-inactive) — user request 2026-06-04. Only the
// US universe has data today (the S&P 500), so US is the ACTIVE tab; TH · CN · JP
// · UK are disabled "soon" placeholders for the planned multi-country expansion
// (a separate Phase-5+ effort: per-country universes + filing sources + currency).
// "CH" was read as China (CN); UK (GB) is a placeholder 5th pick — both swap
// freely. Flags via `country-flag-icons` per-country STATIC imports.

const MARKETS = [
  { code: 'US', label: 'US', name: 'United States', Flag: US, available: true },
  { code: 'TH', label: 'TH', name: 'Thailand', Flag: TH, available: false },
  { code: 'CN', label: 'CN', name: 'China', Flag: CN, available: false },
  { code: 'JP', label: 'JP', name: 'Japan', Flag: JP, available: false },
  { code: 'GB', label: 'UK', name: 'United Kingdom', Flag: GB, available: false },
] as const;

// Mirrors the TopNav tab shape: 44px target, border-b-2 underline pulled onto the
// container's baseline via -mb-px.
const TAB =
  'inline-flex min-h-[44px] shrink-0 items-center gap-1.5 whitespace-nowrap border-b-2 -mb-px px-3 text-sm font-medium';

export function CountryTabs() {
  return (
    <div
      role="group"
      aria-label="Market"
      className="flex items-center gap-1 overflow-x-auto border-b border-slate-200 dark:border-slate-800 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      {MARKETS.map(({ code, label, name, Flag, available }) =>
        available ? (
          <span
            key={code}
            aria-current="true"
            className={`${TAB} border-emerald-700 text-slate-900 dark:border-emerald-400 dark:text-slate-100`}
          >
            <Flag title={name} className="h-3.5 w-5 rounded-[2px]" />
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
            <Flag title={name} className="h-3.5 w-5 rounded-[2px] opacity-60" />
            {label}
            <span className="text-[0.625rem] font-semibold uppercase tracking-wide">soon</span>
          </button>
        ),
      )}
    </div>
  );
}
