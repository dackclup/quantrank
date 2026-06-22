// Hero attribute tiles — the 4-box category grid the user asked for ("กรอบ
// สี่เหลี่ยมสี่อันในภาพ"), modeled structurally on a reference stock app's
// category tiles (icon-over-label boxes) but RESKINNED to the QuantRank
// theme: light = soft slate surface, dark = deep slate (NOT the reference
// app's black boxes, which break in light mode). LedgerCraft ≤4px radius
// (`rounded`), border-as-depth (no shadow), paired `dark:` variants.
//
// Four fixed tiles in a grid (2×2 on mobile, 1×4 on wide hero):
//   1. Market-cap tier   — DATA (raw_metrics.market_cap → Mega/Large/Mid/Small)
//   2. Sector            — DATA (detail.sector)
//   3. Dividend          — LIVE (PR-2, schema 0.10.27+): yield%/None/— from
//      detail.dividend_yield_pct + detail.pays_dividend. Always FILLED state
//      (never "Coming soon") — see formatDividendYield in lib/format.ts.
//   4. Type              — LIVE (PR-2, schema 0.10.31+): label verbatim or "—"
//      from detail.security_type. Always FILLED state (never "Coming soon") —
//      see formatSecurityType in lib/format.ts. Coverage ~60% and growing.
//
// Info tiles, NOT filters (this is a single-stock detail page — nothing to
// filter). Pure server component (computation + markup, no hooks). lucide-react
// icons via NAMED imports only (tree-shaken — never `import * as Icons`, which
// pulls the 224 KB barrel; dependency-auditor 2026-05-31).

import { Building2, Coins, Layers, ScrollText } from 'lucide-react';
import type { JSX } from 'react';
import { formatDividendYield, formatSecurityType } from '@/lib/format';

function capTierLabel(marketCap: number | null): string | null {
  if (marketCap == null) return null;
  if (marketCap >= 200_000_000_000) return 'Mega cap';
  if (marketCap >= 10_000_000_000) return 'Large cap';
  if (marketCap >= 2_000_000_000) return 'Mid cap';
  return 'Small cap';
}

// One tile. `value` null → the tile renders in its "reserved" state: dimmed
// icon + the caption acting as the headline + a small "Coming soon" sub-line,
// so an empty tile reads as intentional, never as a data bug. Reserved tiles
// share the FILLED tile's SURFACE (only the dashed border + dimmed content
// distinguish them) so the 4-tile row reads as one cohesive band — the earlier
// half-opacity `bg-slate-50/50` made the placeholders vanish against the warm
// page bg, so the row "floated" (squint-test, $impeccable layout 2026-06-02).
function Tile({
  icon,
  caption,
  value,
}: {
  icon: JSX.Element;
  caption: string;
  value: string | null;
}) {
  const filled = value != null;
  return (
    <div
      className={`flex flex-col gap-2 rounded border p-4 ${
        filled
          ? 'border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800'
          : 'border-dashed border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800'
      }`}
    >
      <span
        className={
          filled
            ? 'text-slate-500 dark:text-slate-400'
            : 'text-slate-300 dark:text-slate-600'
        }
        aria-hidden="true"
      >
        {icon}
      </span>
      {filled ? (
        <span className="min-w-0">
          <span className="block text-xs font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
            {caption}
          </span>
          <span className="mt-0.5 block truncate tabular-nums text-sm font-semibold text-slate-900 dark:text-slate-100">
            {value}
          </span>
        </span>
      ) : (
        <span className="min-w-0">
          {/* Reserved tile — same UPPERCASE caption vocabulary as a filled
              tile (so promoting a placeholder later doesn't flip the type
              treatment), de-emphasized via COLOR only. slate-500 keeps the
              caption at ~3.4:1 (WCAG large/bold floor) instead of the
              too-faint slate-400. */}
          <span className="block text-xs font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
            {caption}
          </span>
          <span className="mt-0.5 block text-xs text-slate-500 dark:text-slate-400">
            Coming soon
          </span>
        </span>
      )}
    </div>
  );
}

const ICON_CLS = 'h-5 w-5';

export function HeroAttributeTiles({
  marketCap,
  sector,
  dividendYieldPct,
  paysDividend,
  securityType,
}: {
  marketCap: number | null;
  sector: string | null;
  // Dividend tile — data from StockDetail (schema 0.10.27+).
  // `dividendYieldPct` is in PERCENT on the wire (e.g. 2.67 = 2.67%).
  // Three display states: payer "2.67%" · non-payer "None" · unavailable "—".
  dividendYieldPct: number | null;
  paysDividend: boolean | null;
  // Type tile — data from StockDetail (schema 0.10.31+).
  // Server-side `_QUOTE_TYPE_LABEL` already maps to display-ready text
  // (e.g. "Common stock", "ETF", "Fund"). null → "—" (no data yet).
  securityType: string | null;
}) {
  return (
    // `<section>` + sr-only heading completes the document outline (every
    // other detail-page block carries an <h2>); the tiles are self-labeled
    // per-tile so the heading is screen-reader-only.
    <section aria-labelledby="company-attributes-heading" className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <h2 id="company-attributes-heading" className="sr-only">Company attributes</h2>
      <Tile
        icon={<Building2 className={ICON_CLS} strokeWidth={1.75} />}
        caption="Size"
        value={capTierLabel(marketCap)}
      />
      <Tile
        icon={<Layers className={ICON_CLS} strokeWidth={1.75} />}
        caption="Sector"
        value={sector && sector.trim() !== '' ? sector : null}
      />
      {/* Dividend tile — LIVE (schema 0.10.27+). formatDividendYield resolves
          to "X.XX%" for payers, "None" for confirmed non-payers, or "—" for
          tickers with no data available. All three are passed as a non-null
          string so the tile always renders in FILLED state — the "Coming soon"
          reserved era is over for this tile. */}
      <Tile
        icon={<Coins className={ICON_CLS} strokeWidth={1.75} />}
        caption="Dividend"
        value={formatDividendYield(dividendYieldPct, paysDividend)}
      />
      {/* Type tile — LIVE (schema 0.10.31+). formatSecurityType resolves to
          the server-mapped label verbatim ("Common stock" / "ETF" / …) or
          "—" for tickers with no data yet (~40% of universe as of the first
          sp1500 crons; climbs over future crons as the yfinance_info cache
          warms). All branches return a non-null string so the tile always
          renders FILLED — the "Coming soon" reserved era is over for this tile,
          completing the 4-tile hero grid (all tiles live). */}
      <Tile
        icon={<ScrollText className={ICON_CLS} strokeWidth={1.75} />}
        caption="Type"
        value={formatSecurityType(securityType)}
      />
    </section>
  );
}
