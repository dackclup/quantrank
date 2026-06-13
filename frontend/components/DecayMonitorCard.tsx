// IC-decay monitor surface — Issue #75 §3.
//
// Transparency card for the McLean-Pontiff (2016) out-of-sample IC-decay
// monitor. Three UX states drive the rendering:
//
//   1. "insufficient_history" — the monitor has not yet accumulated
//      ≥ min_history_months of post-publication monthly IC data.
//      ALL pillar numeric values are 0 in this state (preliminary=true).
//      We render a quiet "accumulating baseline" state — NOT fake zeros
//      and NOT a false "all healthy" green badge.
//
//   2. "monitoring" — baseline established. Per-pillar table shows real
//      rolling IC vs historical mean, decay ratio, months below threshold.
//      Non-preliminary pillars only; preliminary pillars render as "—".
//
//   3. "alert" — ≥ 1 pillar appears in anomalies_alerted. Decayed pillars
//      are highlighted in the negative (rose) tone.
//
// IMPORTANT: this surface never changes scores or rankings. It is a
// methodology-integrity transparency surface only (monitor + manual review).
//
// Design tokens: outlined-light chip family (Chip primitive), emerald-700
// primary, slate-500/400 muted text, rose-*/amber-* for negative/warn,
// tabular-nums on all numerics, paired dark: variants on every surface.
// No new tokens introduced. Matches Tier2EventCard / FairPriceCard card shell.

import type { DecayReport, PillarDecay } from '@/lib/types';
import { Chip } from '@/components/Chip';

// Canonical display name map for the 10 pillars.
const PILLAR_LABELS: Record<string, string> = {
  quality: 'Quality',
  value: 'Value',
  growth: 'Growth',
  momentum: 'Momentum',
  health: 'Health',
  profitability: 'Profitability',
  technical: 'Technical',
  risk: 'Risk',
  sentiment: 'Sentiment',
  ml: 'ML',
};

function pillarLabel(key: string): string {
  return PILLAR_LABELS[key] ?? key.charAt(0).toUpperCase() + key.slice(1);
}

// Format a decimal IC value to 3 decimal places for display.
// Returns "—" (em-dash) for preliminary / zero-data pillars.
function fmtIC(value: number, preliminary: boolean): string {
  if (preliminary) return '—'; // em-dash
  return value.toFixed(3);
}

// Format decay ratio as a % with 1 decimal place, or "—" for preliminary.
function fmtRatio(value: number, preliminary: boolean): string {
  if (preliminary) return '—';
  return `${(value * 100).toFixed(1)}%`;
}

// Status chip tone constants — outlined-light, no new tokens.
const STATUS_CHIP: Record<
  DecayReport['status'],
  { tone: string; dot: string; label: string }
> = {
  insufficient_history: {
    tone: 'bg-slate-100 text-slate-700 ring-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700',
    dot: 'bg-slate-400 dark:bg-slate-500',
    label: 'Accumulating baseline',
  },
  monitoring: {
    tone: 'bg-emerald-50 text-emerald-900 ring-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-100 dark:ring-emerald-800',
    dot: 'bg-emerald-600 dark:bg-emerald-400',
    label: 'Monitoring',
  },
  alert: {
    tone: 'bg-red-50 text-red-900 ring-red-200 dark:bg-red-900/30 dark:text-red-100 dark:ring-red-800',
    dot: 'bg-rose-500 dark:bg-rose-400',
    label: 'Decay alert',
  },
};

// Row highlight for alerted pillars in the "alert" state.
function alertedRowTone(alerted: boolean): string {
  if (!alerted) return '';
  // Muted rose tint on the row background (not a chip — just a row highlight).
  return 'bg-red-50/60 dark:bg-red-900/10';
}

// Decay ratio chip — neutral for healthy, warn/negative for elevated decay.
// Used only in "monitoring" and "alert" states (not for preliminary pillars).
function decayRatioChipTone(decayRatio: number, alerted: boolean): string {
  if (alerted || decayRatio < 0.5) {
    // Below-threshold (decayed) — negative tone.
    return 'bg-red-50 text-red-900 ring-red-200 dark:bg-red-900/30 dark:text-red-100 dark:ring-red-800';
  }
  if (decayRatio < 0.8) {
    // Mild decay — amber warn tone.
    return 'bg-amber-50 text-amber-900 ring-amber-200 dark:bg-amber-900/30 dark:text-amber-200 dark:ring-amber-800';
  }
  // Healthy — neutral slate tone (no false-positive green).
  return 'bg-slate-100 text-slate-700 ring-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700';
}

function decayRatioDot(decayRatio: number, alerted: boolean): string {
  if (alerted || decayRatio < 0.5) return 'bg-rose-500 dark:bg-rose-400';
  if (decayRatio < 0.8) return 'bg-amber-600 dark:bg-amber-400';
  return 'bg-slate-400 dark:bg-slate-500';
}

// The per-pillar table row — shared across monitoring and alert states.
function PillarRow({
  p,
  alerted,
}: {
  p: PillarDecay;
  alerted: boolean;
}) {
  return (
    <tr className={`border-t border-slate-100 dark:border-slate-800 ${alertedRowTone(alerted)}`}>
      <td className="py-2 pl-2 pr-3 text-sm font-medium text-slate-700 dark:text-slate-300">
        {pillarLabel(p.pillar)}
        {alerted && (
          <span
            className="ml-1.5 inline-block h-1.5 w-1.5 rounded-full bg-rose-500 dark:bg-rose-400 align-middle"
            aria-label="decay alert"
          />
        )}
      </td>
      {/* Rolling 12m IC */}
      <td className="py-2 px-3 text-right text-sm font-mono tabular-nums text-slate-700 dark:text-slate-300">
        {fmtIC(p.rolling_12m_ic, p.preliminary)}
      </td>
      {/* Historical mean IC */}
      <td className="py-2 px-3 text-right text-sm font-mono tabular-nums text-slate-700 dark:text-slate-300">
        {fmtIC(p.historical_mean_ic, p.preliminary)}
      </td>
      {/* Decay ratio chip — only rendered for non-preliminary pillars */}
      <td className="py-2 pl-3 pr-2 text-right">
        {p.preliminary ? (
          <span className="text-sm text-slate-400 dark:text-slate-500">&mdash;</span>
        ) : (
          <Chip
            tone={decayRatioChipTone(p.decay_ratio, alerted)}
            dot={decayRatioDot(p.decay_ratio, alerted)}
            size="xs"
            className="tabular-nums"
            title={`Decay ratio: ${fmtRatio(p.decay_ratio, p.preliminary)} — rolling 12m IC / historical mean IC`}
          >
            {fmtRatio(p.decay_ratio, p.preliminary)}
          </Chip>
        )}
      </td>
    </tr>
  );
}

export interface DecayMonitorCardProps {
  report: DecayReport;
}

export function DecayMonitorCard({ report }: DecayMonitorCardProps) {
  const {
    status,
    pillars,
    anomalies_alerted,
    min_history_months,
    n_dates_with_ic,
    generated_at,
    threshold,
    duration_months,
  } = report;

  const statusChip = STATUS_CHIP[status];
  const alertedSet = new Set(anomalies_alerted);

  // Count non-preliminary pillars for the "N pillars monitored" line.
  const monitoredCount = pillars.filter((p) => !p.preliminary).length;

  // Format generated_at as a human-readable UTC date (ISO 8601 input).
  const generatedDate = generated_at.startsWith('20')
    ? generated_at.slice(0, 10)
    : generated_at;

  return (
    <section
      aria-label="IC-decay monitor"
      className="rounded border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
    >
      {/* Card header */}
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-slate-600 dark:text-slate-400">
          IC-decay monitor
        </h2>
        <Chip
          tone={statusChip.tone}
          dot={statusChip.dot}
          size="sm"
          aria-label={`Status: ${statusChip.label}`}
        >
          {statusChip.label}
        </Chip>
        {status === 'alert' && anomalies_alerted.length > 0 && (
          <Chip
            tone="bg-red-50 text-red-900 ring-red-200 dark:bg-red-900/30 dark:text-red-100 dark:ring-red-800"
            dot="bg-rose-500 dark:bg-rose-400"
            size="sm"
            aria-label={`${anomalies_alerted.length} pillar${anomalies_alerted.length !== 1 ? 's' : ''} decaying`}
          >
            {anomalies_alerted.length} pillar{anomalies_alerted.length !== 1 ? 's' : ''} decaying
          </Chip>
        )}
        {status === 'monitoring' && monitoredCount > 0 && (
          <Chip
            tone="bg-slate-100 text-slate-700 ring-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700"
            dot="bg-slate-400 dark:bg-slate-500"
            size="sm"
            aria-label={`${monitoredCount} pillars monitored`}
          >
            {monitoredCount} pillars monitored
          </Chip>
        )}
      </div>

      {/* Disclaimer — always shown */}
      <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
        Monitor only — this surface never changes scores or rankings. Informational transparency only.
      </p>

      {/* STATE 1: insufficient_history */}
      {status === 'insufficient_history' && (
        <div className="mt-4 rounded border border-slate-100 bg-slate-50/60 px-4 py-4 dark:border-slate-800 dark:bg-slate-800/30">
          <p className="text-sm text-slate-700 dark:text-slate-300">
            Out-of-sample IC-decay monitoring begins once ≥{min_history_months} months of
            post-publication IC history accrue
            {n_dates_with_ic > 0 ? (
              <>
                {' ('}
                <span className="font-mono tabular-nums">{n_dates_with_ic}</span>
                {` month${n_dates_with_ic !== 1 ? 's' : ''} recorded so far — currently accumulating).`}
              </>
            ) : (
              ' (currently accumulating).'
            )}
          </p>
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
            Until the baseline is established, no per-pillar IC metrics are available.
            The 10 monitored pillars are listed below in pending state.
          </p>
          {/* Pending pillar list — shows names only, no false metrics */}
          <ul className="mt-3 flex flex-wrap gap-2" aria-label="Pending pillars">
            {pillars.map((p) => (
              <li key={p.pillar}>
                <Chip
                  tone="bg-slate-100 text-slate-500 ring-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:ring-slate-700"
                  size="sm"
                  aria-label={`${pillarLabel(p.pillar)} — pending`}
                >
                  {pillarLabel(p.pillar)}
                </Chip>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* STATE 2 & 3: monitoring or alert — per-pillar table */}
      {(status === 'monitoring' || status === 'alert') && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[440px] text-left" aria-label="Per-pillar IC decay metrics">
            <thead>
              <tr>
                <th scope="col" className="py-2 pl-2 pr-3 text-xs font-semibold uppercase tracking-[0.1em] text-slate-500 dark:text-slate-400">
                  Pillar
                </th>
                <th scope="col" className="py-2 px-3 text-right text-xs font-semibold uppercase tracking-[0.1em] text-slate-500 dark:text-slate-400">
                  12m IC
                </th>
                <th scope="col" className="py-2 px-3 text-right text-xs font-semibold uppercase tracking-[0.1em] text-slate-500 dark:text-slate-400">
                  Hist. mean IC
                </th>
                <th scope="col" className="py-2 pl-3 pr-2 text-right text-xs font-semibold uppercase tracking-[0.1em] text-slate-500 dark:text-slate-400">
                  Decay ratio
                </th>
              </tr>
            </thead>
            <tbody>
              {pillars.map((p) => (
                <PillarRow
                  key={p.pillar}
                  p={p}
                  alerted={alertedSet.has(p.pillar)}
                />
              ))}
            </tbody>
          </table>
          {/* Parameter legend */}
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
            Alert condition: decay ratio (rolling 12m IC ÷ historical mean IC) &lt;{' '}
            <span className="font-mono tabular-nums font-medium">{threshold.toFixed(2)}</span>{' '}
            for ≥{' '}
            <span className="font-mono tabular-nums font-medium">{duration_months}</span>{' '}
            consecutive months.
          </p>
        </div>
      )}

      {/* Citation + footer */}
      <div className="mt-4 border-t border-slate-100 pt-3 dark:border-slate-800">
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Methodology: McLean &amp; Pontiff (2016) &ldquo;Does Publishing Research Destroy Stock Return
          Predictability?&rdquo; — tests whether each pillar&apos;s factor IC decays after inclusion
          in the ranking model.
          Horizon:{' '}
          <span className="font-mono tabular-nums font-medium text-slate-700 dark:text-slate-300">
            {report.horizon_months}m
          </span>
          . Last computed:{' '}
          <span className="font-mono tabular-nums font-medium text-slate-700 dark:text-slate-300">
            {generatedDate}
          </span>
          .
        </p>
      </div>
    </section>
  );
}
