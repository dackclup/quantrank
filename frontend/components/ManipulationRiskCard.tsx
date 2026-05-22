'use client';

// PR 4.5f Manipulation Risk card. Renders on stock detail pages
// when manipulation_index > 0. Mirrors the Tier2EventCard pattern
// (returns null when empty, no layout space taken on clean stocks)
// and uses the Pattern B outlined-light tone family per
// `.claude/skills/frontend-design-system/SKILL.md` Rule 2 — no
// `dark:` variants so system-dark-mode users don't see invisible
// text on the forced-light background.
//
// Decision contract — rank still uses RAW composite_score per SKILL.md
// Rule 16 ("composite rank unchanged"). composite_score_adjusted is
// informational; the headline number on this card surfaces the
// penalty so users understand the gap.

const FLAG_LABELS: Record<string, string> = {
  sloan_accruals_top_decile: 'Sloan accruals top decile',
  beneish_manipulation_veto: 'Beneish M-score active veto',
  dechow_manipulation_veto: 'Dechow F-score active veto',
  non_reliance_filing: '8-K Item 4.02 non-reliance',
  manipulation_triple_flag: 'Triple-stack (Sloan + Beneish + Dechow)',
  rem_suspect: 'Real Earnings Management (Roychowdhury 2006)',
  restatement_history: 'Restatement history (10-K/A, 5y)',
  late_filing_notification: 'Late-filing notification (Form 12b-25, 1y)',
  accruals_momentum_high: 'Accruals momentum (Δ TATA > 0.05 over 3y)',
  loss_avoidance_pattern: 'Loss-avoidance pattern (Burgstahler-Dichev 1997)',
  beneish_high: 'Beneish M-score warning band',
  dechow_high: 'Dechow F-score warning band',
};

// Color bands match the recommendation-badge / score-tier ramp:
// low → green, moderate → amber, high → rose.
function bandTone(index: number): {
  ring: string;
  bg: string;
  text: string;
  dot: string;
  label: string;
} {
  if (index >= 50) {
    return {
      ring: 'ring-rose-300',
      bg: 'bg-rose-50',
      text: 'text-rose-900',
      dot: 'bg-rose-600',
      label: 'High',
    };
  }
  if (index >= 20) {
    return {
      ring: 'ring-amber-300',
      bg: 'bg-amber-50',
      text: 'text-amber-900',
      dot: 'bg-amber-600',
      label: 'Moderate',
    };
  }
  return {
    ring: 'ring-emerald-300',
    bg: 'bg-emerald-50',
    text: 'text-emerald-900',
    dot: 'bg-emerald-600',
    label: 'Low',
  };
}

export interface ManipulationRiskCardProps {
  manipulationIndex: number | null;
  compositeScore: number | null;
  compositeScoreAdjusted: number | null;
  components: Record<string, boolean> | null;
}

export function ManipulationRiskCard({
  manipulationIndex,
  compositeScore,
  compositeScoreAdjusted,
  components,
}: ManipulationRiskCardProps) {
  // Legacy data (pre-PR-4.5f, where the field is absent rather than
  // explicitly null) and clean stocks (index = 0) render nothing.
  // `== null` catches both `null` and `undefined` — the latter when
  // production JSON predates the schema field. Following the
  // Tier2EventCard pattern: surface only when there's something to
  // surface.
  if (manipulationIndex == null || manipulationIndex <= 0) return null;

  const tone = bandTone(manipulationIndex);
  const firedFlags = components
    ? Object.entries(components)
        .filter(([, fired]) => fired)
        .map(([flag]) => flag)
    : [];
  const penalty =
    compositeScore != null && compositeScoreAdjusted != null
      ? Math.max(0, compositeScore - compositeScoreAdjusted)
      : null;

  return (
    <section
      className={`rounded-lg border border-slate-200 bg-white p-4 ring-1 ring-inset ${tone.ring}`}
    >
      <header className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-slate-600">
          Manipulation Risk Index
        </h2>
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${tone.bg} ${tone.text} ${tone.ring}`}
        >
          <span
            className={`inline-block h-1.5 w-1.5 rounded-full ${tone.dot}`}
            aria-hidden="true"
          />
          {tone.label}
        </span>
      </header>

      <div className="flex items-baseline gap-4">
        <div>
          <div className={`text-3xl font-semibold tabular-nums ${tone.text}`}>
            {manipulationIndex.toFixed(0)}
            <span className="text-base font-normal text-slate-400">/100</span>
          </div>
          {penalty !== null && penalty > 0 ? (
            <div className="mt-1 text-xs text-slate-500">
              Composite penalty:{' '}
              <span className="font-mono tabular-nums text-slate-700">
                −{penalty.toFixed(2)}
              </span>{' '}
              pts (informational; rank uses raw composite)
            </div>
          ) : (
            <div className="mt-1 text-xs text-slate-500">
              No composite-score penalty applied at this index.
            </div>
          )}
        </div>
      </div>

      {firedFlags.length > 0 && (
        <div className="mt-4">
          <div className="mb-2 text-xs uppercase tracking-wide text-slate-500">
            Fired components ({firedFlags.length})
          </div>
          <ul className="space-y-1.5 text-sm text-slate-700">
            {firedFlags.map((flag) => (
              <li key={flag} className="flex items-start gap-2">
                <span
                  className={`mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full ${tone.dot}`}
                  aria-hidden="true"
                />
                <span>
                  {FLAG_LABELS[flag] ?? flag}
                  <span className="ml-1.5 font-mono text-xs text-slate-400">
                    [{flag}]
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <p className="mt-4 text-xs text-slate-400">
        Rolls up Phase 4.5 earnings-manipulation defenses (Sloan ·
        Beneish · Dechow · REM · restatement · late-filing · earnings-
        quality time-series) into a single 0-100 risk index. Soft
        composite penalty (max 10 pts) is informational only — the
        ranking uses the raw composite score per project Rule 16.
      </p>
    </section>
  );
}
