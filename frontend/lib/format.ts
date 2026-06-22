// Display helpers for the fair-price ensemble + sanity-guard outputs.
//
// formatMosPct implements the bounded rendering recommended in the
// PR-3c Issue 3 draft (143 stocks have mos_pct outside [-99%, +500%]
// post-Step-7). Math is correct upstream; we just clamp the visual.
//
// formatFairPrice is defensive against pre-Step-7.5 corruption — Step
// 7.5's data-quality guard sets fair_price to null in the corrupted
// cases, but we still guard against absurd numbers in case a future
// regression slips through.

export type FormattedMos = {
  display: string;
  tooltip: string | null;
  isClamped: boolean;
};

export function formatMosPct(mos: number | null): FormattedMos {
  if (mos === null || Number.isNaN(mos)) {
    return { display: '—', tooltip: null, isClamped: false };
  }
  if (mos < -99) {
    return {
      display: '< −99%',
      tooltip: `${mos.toFixed(1)}% (clamped for display)`,
      isClamped: true,
    };
  }
  if (mos > 500) {
    return {
      display: '> +500%',
      tooltip: `${mos.toFixed(1)}% (clamped for display)`,
      isClamped: true,
    };
  }
  const sign = mos >= 0 ? '+' : '';
  return {
    display: `${sign}${mos.toFixed(1)}%`,
    tooltip: null,
    isClamped: false,
  };
}

export function formatFairPrice(value: number | null): string {
  if (value === null || Number.isNaN(value)) return '—';
  // Defensive — should never happen post-Step-7.5 sanity guard which
  // nulls fair_price when any method computes > $10,000/share. If a
  // future regression slips through, render as em-dash rather than
  // ship a million-dollar fair price to the UI.
  if (value >= 1_000_000) return '—';
  if (value < 0.01) return '< $0.01';
  return `$${value.toFixed(2)}`;
}

// formatDividendYield — three display states for the Dividend tile.
//
//   Payer        (yield > 0):             "2.67%"  (2 decimal places, tabular-nums)
//   Confirmed non-payer (pays_dividend === false OR yield === 0): "None"
//   Unavailable  (yield === null):         "—"      (em-dash, missing-data convention)
//
// The caller owns the pays_dividend / dividend_yield_pct partitioning from
// StockDetail. We accept them separately so the function is pure and testable.
//
// IMPORTANT: dividend_yield_pct is already in PERCENT on the wire
// (e.g. 2.67 = 2.67%, NOT 0.0267). Do NOT multiply by 100.
export function formatDividendYield(
  dividendYieldPct: number | null,
  paysDividend: boolean | null,
): string {
  if (dividendYieldPct === null) return '—';
  // A zero yield or an explicit false pays_dividend = confirmed non-payer.
  if (dividendYieldPct === 0 || paysDividend === false) return 'None';
  // Positive yield — render as "X.XX%".
  return `${dividendYieldPct.toFixed(2)}%`;
}

// formatSecurityType — display helper for the Type tile (tile #4).
//
//   Present (non-empty string): return the label verbatim — the server-side
//     `_QUOTE_TYPE_LABEL` map already produces display-ready text
//     (e.g. "Common stock", "ETF", "Fund", "Index"). No further mapping needed.
//   Unavailable (null or empty string): return "—" (em-dash), the standard
//     missing-data convention. Coverage is ~60% right now and climbs over
//     future crons; "—" is the honest "no data yet" state, consistent with
//     formatFairPrice / formatMosPct / the Dividend tile null branch.
export function formatSecurityType(securityType: string | null): string {
  if (!securityType || securityType.trim() === '') return '—';
  return securityType;
}

export function mosColorClass(mos: number | null): string {
  if (mos === null || Number.isNaN(mos)) return 'text-slate-400';
  if (mos >= 20) return 'text-emerald-700';
  if (mos > 0) return 'text-emerald-600';
  if (mos > -20) return 'text-slate-500';
  return 'text-rose-600';
}
