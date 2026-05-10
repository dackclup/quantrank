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

export function mosColorClass(mos: number | null): string {
  if (mos === null || Number.isNaN(mos)) return 'text-slate-400';
  if (mos >= 20) return 'text-emerald-700';
  if (mos > 0) return 'text-emerald-600';
  if (mos > -20) return 'text-slate-500';
  return 'text-rose-600';
}
