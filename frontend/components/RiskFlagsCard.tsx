'use client';

// Risk Vetoes card. Renders on stock detail pages when risk_flags[] is
// non-empty. Surfaces the Tier-1 HARD VETOES (Altman distress, Sloan
// accruals, net issuance, Beneish / Dechow manipulation, 8-K
// non-reliance, data-quality corruption) that drive a cautious
// recommendation and forfeit entered_top5 per SKILL.md Rule 16.
//
// Why this exists: risk_flags[] was typed in lib/types.ts and present
// in the JSON but rendered NOWHERE (issue #305) — so a "Sell" with
// MoS +34% and manipulation 0/100 (e.g. EIX, risk_flags
// ["altman_distress"]) looked like an app error. This card is the
// on-page "why". Mirrors ManipulationRiskCard: returns null when empty,
// rose tone (vetoes are the highest-severity band), paired dark:
// variants, [flag] mono code for the raw key.
//
// Motion (2026-05-29): on every visit the veto rows enter with a single
// attention beat (animate-flag-pulse, rise + scale settle) — communicates
// "look here" without a permanent blink. Gated client-side via
// usePlayOnMount + reduced-motion-safe (see docs/design.md §Motion).

import { usePlayOnMount } from '@/lib/useMotion';

interface FlagMeta {
  label: string;
  detail: string;
}

// Academic anchors from docs/METHODOLOGY.md §Active vetoes. Unknown
// flags fall through to the raw key (forward-safe if a new veto lands
// before this map is updated).
const RISK_FLAG_META: Record<string, FlagMeta> = {
  altman_distress: {
    label: 'Altman financial distress',
    detail: 'Altman Z″ below 1.10 — financial-distress zone (Altman 1968).',
  },
  sloan_accruals_top_decile: {
    label: 'Sloan accruals — top decile',
    detail: 'Within-sector top decile of accruals / assets (Sloan 1996).',
  },
  net_issuance_top_decile: {
    label: 'Net share issuance — top decile',
    detail: 'Top-decile net issuance over the trailing year (Pontiff-Woodgate 2008 / Daniel-Titman 2006).',
  },
  non_reliance_filing: {
    label: '8-K Item 4.02 non-reliance',
    detail: 'Prior financials flagged not-to-be-relied-upon within the trailing year (Schroeder 2024).',
  },
  beneish_manipulation_veto: {
    label: 'Beneish M-score veto',
    detail: 'Beneish M-score above −1.78 — earnings manipulation likely (Beneish 1999).',
  },
  dechow_manipulation_veto: {
    label: 'Dechow F-score veto',
    detail: 'Dechow F-score above 3.0 — elevated misstatement risk (Dechow et al. 2011).',
  },
  data_quality_input_corruption: {
    label: 'Data-quality guard',
    detail: 'Upstream input out of range (e.g. share-count units) — fair-price methods suppressed (Step 7.5 sanity guard).',
  },
  // Not a compute_risk_flags veto — a fair-price ensemble GUARD merged into
  // risk_flags[] at compute/main.py after Step-7 rotation, so it does NOT
  // forfeit entered_top5 the way the 7 vetoes do. Fires 0× in the current
  // cron but is structurally reachable; labelled so it never renders raw.
  stale_filing_hard: {
    label: 'Stale filing — fair-price suppressed',
    detail: 'Most recent filing older than 180 days — all 6 fair-price methods skipped (practitioner freshness guard, not a veto).',
  },
};

export interface RiskFlagsCardProps {
  // Schema field is non-nullable (`list[str]`, default_factory=list), but the
  // prop stays `| null` as defensive cover for legacy snapshots that predate
  // the field — the `== null` runtime guard below relies on it.
  riskFlags: string[] | null;
}

export function RiskFlagsCard({ riskFlags }: RiskFlagsCardProps) {
  // Hook BEFORE the early return (rules-of-hooks). Pulses on every visit to
  // a stock's detail page (usePlayOnMount). Effect-based so the animate
  // class is client-only (never in the static prerender).
  const pulse = usePlayOnMount(`risk-flags:${(riskFlags ?? []).join(',')}`);

  // `== null` catches both null and undefined (legacy snapshots predating
  // the field). Clean stocks (empty array) take no layout space —
  // matches the ManipulationRiskCard / Tier2EventCard convention.
  if (riskFlags == null || riskFlags.length === 0) return null;

  return (
    <section className="rounded border border-slate-200 bg-white p-4 ring-1 ring-inset ring-rose-300 dark:border-slate-800 dark:bg-slate-900 dark:ring-rose-800">
      <header className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-slate-600 dark:text-slate-400">
          Risk Flags
        </h2>
        <span className="inline-flex items-center gap-1.5 rounded-sm bg-rose-50 px-2.5 py-0.5 text-xs font-medium tabular-nums text-rose-900 ring-1 ring-inset ring-rose-300 dark:bg-rose-900/30 dark:text-rose-200 dark:ring-rose-800">
          <span
            className="inline-block h-1.5 w-1.5 rounded-full bg-rose-600 dark:bg-rose-400"
            aria-hidden="true"
          />
          {riskFlags.length} active
        </span>
      </header>

      <ul className="space-y-2 text-sm text-slate-700 dark:text-slate-300">
        {riskFlags.map((flag, i) => {
          const meta = RISK_FLAG_META[flag];
          // First view this session: each veto row rises + pulses once,
          // staggered so a multi-veto stock (e.g. SMCI: 3) cascades.
          const pulseClass = pulse
            ? `animate-flag-pulse stagger-${Math.min(12, i + 1)}`
            : '';
          return (
            <li key={flag} className={`flex items-start gap-2 rounded-sm ${pulseClass}`}>
              <span
                className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-rose-600 dark:bg-rose-400"
                aria-hidden="true"
              />
              <span>
                <span className="font-medium text-slate-900 dark:text-slate-100">
                  {meta?.label ?? flag}
                </span>
                <span className="ml-1.5 font-mono text-xs text-slate-400 dark:text-slate-500">
                  [{flag}]
                </span>
                {meta?.detail ? (
                  <span className="mt-0.5 block text-xs text-slate-500 dark:text-slate-400">
                    {meta.detail}
                  </span>
                ) : null}
              </span>
            </li>
          );
        })}
      </ul>

      <p className="mt-4 text-xs text-slate-400 dark:text-slate-500">
        Risk-overlay flags. A stock carrying any of these keeps its raw
        composite rank (project Rule 16) but forfeits its{' '}
        <span className="font-mono">entered_top5</span> badge. Two of them —{' '}
        <span className="font-mono">altman_distress</span> and{' '}
        <span className="font-mono">data_quality_input_corruption</span> —
        additionally force a cautious recommendation; the others act as Top-5
        disqualifiers without dictating the buy/hold/sell label on their own.
      </p>
    </section>
  );
}
