'use client';

// Risk Summary — ONE container merging the former RiskFlagsCard +
// ManipulationRiskCard (2026-05-31, user request "รวม risk flags + risk
// index เป็น container เดียว"). The two were separate cards that showed
// PARTIALLY-OVERLAPPING flag lists, so the manipulation-linked vetoes
// (sloan / beneish / dechow / non-reliance) appeared TWICE on screen and
// read like duplicated data. They are not duplicates — they are two
// different CONSEQUENCES of the same fact, and the overlap is asymmetric
// in BOTH directions, which is why a flat merge would mislead:
//
//   risk_flags[]  (rank gates — Rule 16)      manipulation_index (informational)
//   ─────────────────────────────────────     ──────────────────────────────────
//   altman_distress            ← NOT in idx    sloan_accruals_top_decile   ┐ also
//   data_quality_input_corrupt ← NOT in idx    beneish_manipulation_veto   ┘ a gate
//   net_issuance_top_decile    ← NOT in idx    accruals_momentum_high   ← annotate-only
//   sloan_accruals_top_decile  ─┐ shared       beneish_high             ← annotate-only
//   beneish_manipulation_veto  ─┘ (both)       restatement_history …    ← annotate-only
//
// So the layout is restructured, NOT flattened:
//   • RANK GATES sub-section   = risk_flags[]  → these forfeit entered_top5
//     (and altman_distress / data_quality_input_corruption force cautious).
//   • MANIPULATION INDEX sub-section = the 0-100 rollup → soft penalty,
//     rank UNCHANGED per SKILL.md Rule 16.
// De-dup is by cross-reference: a flag that is BOTH a rank gate and a
// manipulation component is shown ONLY in RANK GATES; the manipulation
// list shows only the annotate-only SURPLUS under an "Also fired
// (not rank-gating)" label. Same flag never appears twice.
//
// Severity / outer ring: worst-case — rose if any rank gate fires (the
// highest band), else the manipulation band tone (rose/amber/emerald by
// index). Returns null only when BOTH halves are empty. Mirrors the
// Tier2EventCard convention (no layout space on clean stocks), keeps the
// rounded / ring-1 ring-inset / rounded-sm chip / tabular-nums /
// paired dark: family from both originals — no new design tokens.

interface FlagMeta {
  label: string;
  detail: string;
}

// Rank-gate flags carry the academic anchor (rendered with the detail
// line). Academic anchors from docs/METHODOLOGY.md §Active vetoes.
// Unknown flags fall through to the raw key (forward-safe if a new veto
// lands before this map is updated).
const RANK_GATE_META: Record<string, FlagMeta> = {
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
  // forfeit entered_top5 the way the vetoes do. Fires 0× in the current
  // cron but is structurally reachable; labelled so it never renders raw.
  stale_filing_hard: {
    label: 'Stale filing — fair-price suppressed',
    detail: 'Most recent filing older than 180 days — all 6 fair-price methods skipped (practitioner freshness guard, not a veto).',
  },
};

// Annotate-only manipulation components — label only (no rank-gate detail
// line; these never forfeit entered_top5). Used for the "Also fired"
// surplus list.
const MANIPULATION_FLAG_LABELS: Record<string, string> = {
  sloan_accruals_top_decile: 'Sloan accruals top decile',
  beneish_manipulation_veto: 'Beneish M-score active veto',
  dechow_manipulation_veto: 'Dechow F-score active veto',
  non_reliance_filing: '8-K Item 4.02 non-reliance',
  manipulation_triple_flag: 'Triple-stack (Sloan + Beneish + Dechow)',
  rem_suspect: 'Real Earnings Management (Roychowdhury 2006)',
  restatement_history: 'Restatement history (10-K/A, 5y)',
  restatement_high_confidence: 'Restatement — high confidence (10-K/A + 8-K 4.02)',
  late_filing_notification: 'Late-filing notification (Form 12b-25, 1y)',
  accruals_momentum_high: 'Accruals momentum (Δ TATA > 0.05 over 3y)',
  loss_avoidance_pattern: 'Loss-avoidance pattern (Burgstahler-Dichev 1997)',
  loss_avoidance_pattern_size_invariant: 'Loss-avoidance — size-invariant (Roychowdhury 2006)',
  beneish_high: 'Beneish M-score warning band',
  dechow_high: 'Dechow F-score warning band',
  insider_sell_cluster: 'Insider sell cluster (Cohen-Malloy-Pomorski 2012)',
  c_suite_unusual_sell: 'C-suite unusual selling (Jeng-Metrick-Zeckhauser 2003)',
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
      ring: 'ring-rose-300 dark:ring-rose-800',
      bg: 'bg-rose-50 dark:bg-rose-900/30',
      text: 'text-rose-900 dark:text-rose-200',
      dot: 'bg-rose-600 dark:bg-rose-400',
      label: 'High',
    };
  }
  if (index >= 20) {
    return {
      ring: 'ring-amber-300 dark:ring-amber-800',
      bg: 'bg-amber-50 dark:bg-amber-900/30',
      text: 'text-amber-900 dark:text-amber-200',
      dot: 'bg-amber-600 dark:bg-amber-400',
      label: 'Moderate',
    };
  }
  return {
    ring: 'ring-emerald-300 dark:ring-emerald-800',
    bg: 'bg-emerald-50 dark:bg-emerald-900/30',
    text: 'text-emerald-900 dark:text-emerald-200',
    dot: 'bg-emerald-600 dark:bg-emerald-400',
    label: 'Low',
  };
}

export interface RiskSummaryCardProps {
  // risk_flags is non-nullable in the schema (`list[str]`, default_factory=
  // list) but stays `| null` as defensive cover for legacy snapshots that
  // predate the field — the `== null` runtime guard below relies on it.
  riskFlags: string[] | null;
  manipulationIndex: number | null;
  compositeScore: number | null;
  compositeScoreAdjusted: number | null;
  components: Record<string, boolean> | null;
}

export function RiskSummaryCard({
  riskFlags,
  manipulationIndex,
  compositeScore,
  compositeScoreAdjusted,
  components,
}: RiskSummaryCardProps) {
  // `== null` catches both null and undefined (legacy snapshots predating
  // either field).
  const rankGates = riskFlags ?? [];
  const hasGates = rankGates.length > 0;
  const hasIndex = manipulationIndex != null && manipulationIndex > 0;

  // Clean stocks (no gates AND no index) take no layout space — matches
  // the Tier2EventCard / former two-card convention.
  if (!hasGates && !hasIndex) return null;

  const tone = bandTone(manipulationIndex ?? 0);

  // De-dup: fired manipulation components that are NOT already shown as a
  // rank gate above. The shared flags (sloan / beneish_veto / …) live only
  // in the RANK GATES sub-section; this surplus is the annotate-only set.
  const gateSet = new Set(rankGates);
  const alsoFired = components
    ? Object.entries(components)
        .filter(([flag, fired]) => fired && !gateSet.has(flag))
        .map(([flag]) => flag)
    : [];

  const penalty =
    compositeScore != null && compositeScoreAdjusted != null
      ? Math.max(0, compositeScore - compositeScoreAdjusted)
      : null;

  // Worst-case outer ring: rose when any rank gate fires; otherwise the
  // manipulation band tone.
  const outerRing = hasGates ? 'ring-rose-300 dark:ring-rose-800' : tone.ring;

  // Exactly ONE status chip in the outer header (rose gate-count when gates
  // fire, else the band chip) so the band label still surfaces when it's
  // the only signal. When gates fire, the band chip moves into the
  // manipulation sub-header so "Moderate/High/Low" isn't lost.
  return (
    <section
      className={`rounded border border-slate-200 bg-white p-4 ring-1 ring-inset dark:border-slate-800 dark:bg-slate-900 ${outerRing}`}
    >
      <header className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-[0.14em] text-slate-600 dark:text-slate-400">
          Risk Summary
        </h2>
        {hasGates ? (
          <span className="inline-flex items-center gap-1.5 rounded-sm bg-rose-50 px-2.5 py-0.5 text-xs font-medium tabular-nums text-rose-900 ring-1 ring-inset ring-rose-300 dark:bg-rose-900/30 dark:text-rose-200 dark:ring-rose-800">
            <span
              className="inline-block h-1.5 w-1.5 rounded-full bg-rose-600 dark:bg-rose-400"
              aria-hidden="true"
            />
            {rankGates.length} active
          </span>
        ) : (
          <span
            className={`inline-flex items-center gap-1.5 rounded-sm px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${tone.bg} ${tone.text} ${tone.ring}`}
          >
            <span
              className={`inline-block h-1.5 w-1.5 rounded-full ${tone.dot}`}
              aria-hidden="true"
            />
            {tone.label}
          </span>
        )}
      </header>

      {/* ── Sub-section 1: RANK GATES (rank-eligibility, Rule 16) ── */}
      {hasGates && (
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-[0.14em] text-rose-700 dark:text-rose-300">
            Rank gates
          </div>
          <ul className="space-y-2 text-sm text-slate-700 dark:text-slate-300">
            {rankGates.map((flag) => {
              const meta = RANK_GATE_META[flag];
              return (
                <li key={flag} className="flex items-start gap-2">
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
          <p className="mt-3 text-xs text-slate-400 dark:text-slate-500">
            These flags keep the raw composite rank (project Rule 16) but
            forfeit the <span className="font-mono">entered_top5</span> badge.
            Two of them — <span className="font-mono">altman_distress</span> and{' '}
            <span className="font-mono">data_quality_input_corruption</span> —
            additionally force a cautious recommendation; the others act as
            Top-5 disqualifiers without dictating the buy/hold/sell label on
            their own.
          </p>
        </div>
      )}

      {/* ── Sub-section 2: MANIPULATION INDEX (informational penalty) ── */}
      {hasIndex && (
        <div
          className={
            hasGates ? 'mt-4 border-t border-slate-100 pt-4 dark:border-slate-800' : ''
          }
        >
          <div className="mb-2 flex items-center justify-between gap-2">
            <div className="min-w-0 text-xs font-medium uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
              Manipulation index
            </div>
            {/* Band chip lives here when gates already own the outer-header
                chip — so the Moderate/High/Low label is never lost.
                `shrink-0` protects the chip from being compressed by the
                label at 320px / large system font (per design review). */}
            {hasGates && (
              <span
                className={`inline-flex shrink-0 items-center gap-1.5 rounded-sm px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${tone.bg} ${tone.text} ${tone.ring}`}
              >
                <span
                  className={`inline-block h-1.5 w-1.5 rounded-full ${tone.dot}`}
                  aria-hidden="true"
                />
                {tone.label}
              </span>
            )}
          </div>

          <div className={`text-3xl font-semibold tabular-nums ${tone.text}`}>
            {manipulationIndex!.toFixed(0)}
            <span className="text-base font-normal text-slate-400 dark:text-slate-500">
              /100
            </span>
          </div>
          {penalty !== null && penalty > 0 ? (
            <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Composite penalty:{' '}
              <span className="font-mono tabular-nums text-slate-700 dark:text-slate-300">
                −{penalty.toFixed(2)}
              </span>{' '}
              pts (informational; rank uses raw composite)
            </div>
          ) : (
            <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              No composite-score penalty applied at this index.
            </div>
          )}

          {alsoFired.length > 0 ? (
            <div className="mt-3">
              <div className="mb-2 text-xs font-medium uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">
                {hasGates
                  ? `Also fired — not rank-gating (${alsoFired.length})`
                  : `Fired components (${alsoFired.length})`}
              </div>
              <ul className="space-y-1.5 text-sm text-slate-700 dark:text-slate-300">
                {alsoFired.map((flag) => (
                  <li key={flag} className="flex items-start gap-2">
                    <span
                      className={`mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full ${tone.dot}`}
                      aria-hidden="true"
                    />
                    <span>
                      {MANIPULATION_FLAG_LABELS[flag] ?? flag}
                      <span className="ml-1.5 font-mono text-xs text-slate-400 dark:text-slate-500">
                        [{flag}]
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : hasGates ? (
            // Every fired component is already shown as a rank gate above —
            // tell the user so the index number doesn't look unexplained.
            <p className="mt-2 text-xs text-slate-400 dark:text-slate-500">
              Driven entirely by the rank-gate flag(s) above — no additional
              annotate-only components fired.
            </p>
          ) : null}

          <p className="mt-3 text-xs text-slate-400 dark:text-slate-500">
            Rolls up Phase 4.5 earnings-manipulation defenses (Sloan ·
            Beneish · Dechow · REM · restatement · late-filing · earnings-
            quality time-series) into a single 0-100 risk index. The soft
            composite penalty (max 10 pts) is informational only — the
            ranking uses the raw composite score per project Rule 16.
          </p>
        </div>
      )}
    </section>
  );
}
