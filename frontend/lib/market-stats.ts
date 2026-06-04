import { getMetadata, getRankings } from './data';

// Universe-snapshot stats for the top `MarketStatsBar`. Derived ENTIRELY from
// the already-build-imported rankings.json + metadata.json (getRankings /
// getMetadata) — NO new ingestion, data source, or schema field. QuantRank is
// a weekly static export, so this is NOT a live market ticker: every number is
// "as of" the last compute run, and the trailing "Updated" item carries that
// date as the honesty anchor. Wiring a genuinely live feed (or new index /
// commodity data) is a separate observability-before-wiring PR, not a tweak
// here.

export type MarketStatTone = 'pos' | 'neg' | 'neutral';

export type MarketStatItem = {
  /** Short uppercase label, e.g. "Avg score". */
  label: string;
  /** Primary value string (already formatted). For mover items this is the ticker. */
  value: string;
  /** Optional secondary delta string (already signed + formatted), e.g. "+8.2%". */
  delta?: string | null;
  /** Color intent for the delta — or for the value itself when there is no delta. */
  tone?: MarketStatTone;
  /** Optional internal link target, e.g. "/stock/NVDA". */
  href?: string | null;
};

function mean(xs: number[]): number | null {
  if (xs.length === 0) return null;
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}

function median(xs: number[]): number | null {
  if (xs.length === 0) return null;
  const sorted = [...xs].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

// Signed percent with a real minus sign (U+2212) so it lines up under the
// app-wide tabular-nums numeric treatment instead of the narrower hyphen.
function signedPct(v: number, digits = 1): string {
  const sign = v >= 0 ? '+' : '−';
  return `${sign}${Math.abs(v).toFixed(digits)}%`;
}

function toneOf(v: number): MarketStatTone {
  if (v > 0) return 'pos';
  if (v < 0) return 'neg';
  return 'neutral';
}

function formatUpdated(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

export function getMarketStats(): MarketStatItem[] {
  const rows = getRankings();
  const meta = getMetadata();
  const items: MarketStatItem[] = [];

  // Universe size — metadata is canonical; fall back to the row count.
  const universeSize = meta.universe_size || rows.length;
  if (universeSize > 0) {
    items.push({ label: 'Universe', value: `${universeSize}` });
  }

  // Average composite score across the universe.
  const avg = mean(rows.map((r) => r.composite_score));
  if (avg !== null) {
    items.push({ label: 'Avg score', value: avg.toFixed(1) });
  }

  // Median margin of safety — median (not mean) so the extreme-overvalued tail
  // (e.g. NVDA at −176%) doesn't drag the headline number.
  const med = median(
    rows.map((r) => r.margin_of_safety_pct).filter((n): n is number => typeof n === 'number'),
  );
  if (med !== null) {
    items.push({ label: 'Median MoS', value: signedPct(med), tone: toneOf(med) });
  }

  // Stocks carrying at least one defense-layer risk flag.
  const flagged = rows.filter((r) => Array.isArray(r.risk_flags) && r.risk_flags.length > 0).length;
  items.push({ label: 'Flagged', value: `${flagged}` });

  // Best / worst day-over-day mover. price_change_1d_pct is null on newly
  // IPO'd names (only one close available), so filter before reducing.
  const changes = rows
    .map((r) => ({ ticker: r.ticker, chg: r.price_change_1d_pct }))
    .filter((x): x is { ticker: string; chg: number } => typeof x.chg === 'number');
  if (changes.length > 0) {
    const best = changes.reduce((a, b) => (b.chg > a.chg ? b : a));
    const worst = changes.reduce((a, b) => (b.chg < a.chg ? b : a));
    items.push({
      label: 'Top gainer',
      value: best.ticker,
      delta: signedPct(best.chg),
      tone: toneOf(best.chg),
      href: `/stock/${best.ticker}`,
    });
    items.push({
      label: 'Top loser',
      value: worst.ticker,
      delta: signedPct(worst.chg),
      tone: toneOf(worst.chg),
      href: `/stock/${worst.ticker}`,
    });
  }

  // Last compute timestamp — the anchor for the "as of, not live" caveat.
  const updated = formatUpdated(meta.last_update_utc);
  if (updated) {
    items.push({ label: 'Updated', value: updated });
  }

  return items;
}
