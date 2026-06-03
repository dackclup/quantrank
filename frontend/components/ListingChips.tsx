import type { JSX } from 'react';
import { Landmark } from 'lucide-react';
import US from 'country-flag-icons/react/3x2/US';
import { Chip } from '@/components/Chip';

// Listing-metadata chips for the stock-detail hero (PR-B) — a country chip
// (flag + ISO tag, e.g. 🇺🇸 US) and an exchange chip (generic Landmark icon +
// display name, e.g. NASDAQ). Replaces the former sector + industry chips on
// the #rank row; sector still shows in the Sector attribute tile below, and the
// fields are populated by PR-A2's main.py wiring (display-only, from yfinance
// fast_info). Both chips are independently null-safe — they render nothing
// until a cron populates `country` / `exchange` (the pre-wiring production data
// has them null), so the row degrades to just the #rank chip rather than
// breaking.
//
// FLAG RENDERING — per-country STATIC imports via a lookup table ONLY. The
// universe is US-only today; add a non-US country by importing its component
// here and adding one FLAG_BY_COUNTRY row. NEVER use a barrel import
// (`import { US } from 'country-flag-icons/react/3x2'`), `import * as Flags`,
// or a dynamic `Flags[code]` — each pulls the full ~330 KB / 267-country
// monolith and defeats tree-shaking (same discipline as lucide-react §Gotchas).

const FLAG_BY_COUNTRY: Record<string, typeof US> = {
  US,
};

// Full country names for the chip tooltip (hover + screen-reader context).
// Parallels FLAG_BY_COUNTRY — add a row when a non-US country lands.
const COUNTRY_NAME: Record<string, string> = {
  US: 'United States',
};

// LedgerCraft neutral-steel tone (mirrors SectorChip): slate-100 bg /
// slate-600 fg / slate-200 ring, paired dark variants. Rendered through the
// shared `Chip` primitive at the default `sm` size (2px radius, font-medium).
const STEEL_TONE =
  'bg-slate-100 text-slate-600 ring-slate-200 ' +
  'dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700';

export function ListingChips({
  country,
  exchange,
}: {
  country: string | null;
  exchange: string | null;
}): JSX.Element | null {
  if (!country && !exchange) return null;
  const Flag = country ? FLAG_BY_COUNTRY[country] : undefined;
  return (
    <>
      {country && (
        <Chip
          tone={STEEL_TONE}
          title={`Country: ${COUNTRY_NAME[country] ?? country}`}
          leading={
            Flag ? (
              <Flag
                aria-hidden="true"
                className="h-3.5 w-auto rounded-[1px] ring-1 ring-inset ring-black/10 dark:ring-white/15"
              />
            ) : undefined
          }
        >
          <span className="truncate">{country}</span>
        </Chip>
      )}
      {exchange && (
        <Chip
          tone={STEEL_TONE}
          title={`Exchange: ${exchange}`}
          leading={
            <Landmark
              aria-hidden="true"
              className="h-3.5 w-3.5 shrink-0 text-slate-500 dark:text-slate-400"
            />
          }
        >
          <span className="truncate">{exchange}</span>
        </Chip>
      )}
    </>
  );
}
