// BacktestValidationBadge — OOS-validation credibility panel for the AI-pick
// home page (Phase 7.0 backtest honesty work). Renders the Bailey-López de
// Prado 2014 Deflated Sharpe Ratio result + optional PBO + optional holdout
// block in the outlined-light chip design language.
//
// Graceful-absent contract: returns null when meta.validation is absent or null
// (current artifact pre-dates the validation block; badge is invisible).
// All data is purely data-driven — no hardcoded DSR/PBO/holdout numbers.
//
// Design discipline (frontend-design-system SKILL.md):
// - Chip primitive for all indicators; outlined-light pattern only (Rule 2)
// - Paired dark: variants on every colored surface (Rule 4)
// - tabular-nums on every numeric display (Rule 5)
// - Soft palette: emerald for pass, amber for caveat, red-50 for fail (Rule 1)
// - Quiet / secondary to the hero — section label + sm chips, not a second hero
// - No min-h-[44px] needed — no interactive controls in this component
// - No per-badge legal disclaimer — global Disclaimer banner covers it (Rule 9)
//
// Pure Server Component — no 'use client' needed (no hooks, no browser APIs).

import { Chip } from '@/components/Chip';
import type { BacktestValidation } from '@/lib/types';

// ---------------------------------------------------------------------------
// Tone maps — pass/fail + caveat aligned to the design system soft palette.
// ---------------------------------------------------------------------------

const PASS_CHIP = 'bg-emerald-50 text-emerald-900 ring-emerald-300 dark:bg-emerald-900/30 dark:text-emerald-100 dark:ring-emerald-800';
const PASS_DOT  = 'bg-emerald-700 dark:bg-emerald-400';

const FAIL_CHIP = 'bg-red-50 text-red-900 ring-red-200 dark:bg-red-900/30 dark:text-red-100 dark:ring-red-800';
const FAIL_DOT  = 'bg-rose-500 dark:bg-rose-400';

const CAVEAT_CHIP = 'bg-amber-50 text-amber-900 ring-amber-200 dark:bg-amber-900/30 dark:text-amber-100 dark:ring-amber-700';
const CAVEAT_DOT  = 'bg-amber-500 dark:bg-amber-400';

const NEUTRAL_CHIP = 'bg-slate-100 text-slate-700 ring-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-500';
const NEUTRAL_DOT  = 'bg-slate-500 dark:bg-slate-400';

// ---------------------------------------------------------------------------
// Small helpers
// ---------------------------------------------------------------------------

function fmtPhi(v: number): string {
  // A probability < 1 must NEVER display as "1.0000" — on a credibility surface
  // a skeptic reads a perfect 1.0 as impossible (or as a hidden value).
  // Widen precision (then cap) so a sub-1 Φ keeps meaningful resolution:
  // 0.99998458 → "0.99998"; an extreme 0.9999997 → ">0.9999" rather than "1.0000".
  if (v >= 1) return '1.0000';
  const four = v.toFixed(4);
  if (four !== '1.0000') return four;
  const five = v.toFixed(5);
  return five === '1.00000' ? '>0.9999' : five;
}

function fmt2(v: number | null | undefined): string {
  return v == null ? '—' : v.toFixed(2);
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '—';
  const abs = Math.abs(v);
  const sign = v >= 0 ? '+' : '−';
  return `${sign}${(abs * 100).toFixed(1)}%`;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** DSR headline chip — "Deflated Sharpe survives N-trial correction" + Φ value. */
function DsrChip({ v }: { v: BacktestValidation }) {
  const pass = v.phi_passes === true;
  const fail = v.phi_passes === false;
  const nTrials = v.n_trials;
  const phi = v.dsr_confidence_phi;

  const label = [
    'Deflated Sharpe',
    nTrials != null ? `${nTrials}-trial correction` : 'correction',
  ].join(' · ');

  const phiStr = phi != null
    ? `Φ=${fmtPhi(phi)}`
    : 'Φ=—';

  const tone  = pass ? PASS_CHIP : fail ? FAIL_CHIP : NEUTRAL_CHIP;
  const dot   = pass ? PASS_DOT  : fail ? FAIL_DOT  : NEUTRAL_DOT;
  const title = [
    `Bailey-López de Prado 2014 Deflated Sharpe Ratio.`,
    phi != null ? `Φ(DSR)=${fmtPhi(phi)}.` : '',
    v.dsr != null ? `DSR=${fmt2(v.dsr)}.` : '',
    v.annualized_sharpe != null ? `Annualized Sharpe=${fmt2(v.annualized_sharpe)}.` : '',
    v.n_observations != null ? `N obs=${v.n_observations}.` : '',
    pass
      ? `Gate PASSED (Φ ≥ 0.95).`
      : fail
        ? `Gate FAILED (Φ < 0.95).`
        : 'Gate result unknown.',
  ].filter(Boolean).join(' ');

  return (
    <Chip
      tone={tone}
      dot={dot}
      size="sm"
      title={title}
      aria-label={`${label} ${phiStr}. ${pass ? 'Passed' : fail ? 'Failed' : 'Unknown'}.`}
    >
      <span className="tabular-nums">
        {label} — <span className="font-mono tabular-nums">{phiStr}</span>
        {pass && <span className="ml-1 font-mono tabular-nums text-emerald-700 dark:text-emerald-300">PASS</span>}
        {fail && <span className="ml-1 font-mono tabular-nums text-red-700 dark:text-red-300">FAIL</span>}
      </span>
    </Chip>
  );
}

/** PBO chip — "PBO 0.23 · PASS" with config_correlation_note accessible via title. */
function PboChip({ pbo }: { pbo: NonNullable<BacktestValidation['pbo']> }) {
  const pass = pbo.passes;
  const tone = pass ? PASS_CHIP : FAIL_CHIP;
  const dot  = pass ? PASS_DOT  : FAIL_DOT;

  const label = `PBO ${pbo.pbo.toFixed(2)} (${pbo.n_configs} configs, ${pbo.n_partitions} splits)`;
  const title = [
    `Probability of Backtest Overfitting (Bailey et al. 2017).`,
    `PBO=${pbo.pbo.toFixed(4)}.`,
    `N partitions=${pbo.n_partitions}, N configs=${pbo.n_configs}, N obs=${pbo.n_observations}.`,
    pass ? `Gate PASSED.` : `Gate FAILED.`,
    pbo.config_correlation_note,
  ].filter(Boolean).join(' ');

  return (
    <Chip
      tone={tone}
      dot={dot}
      size="sm"
      title={title}
      aria-label={`${label}. ${pass ? 'Passed' : 'Failed'}. ${pbo.config_correlation_note}`}
    >
      <span className="font-mono tabular-nums">
        {label} — {pass ? 'PASS' : 'FAIL'}
      </span>
    </Chip>
  );
}

/** Holdout chip — the ONLY in_sample=false block; labeled accordingly. */
function HoldoutChip({ holdout }: { holdout: NonNullable<BacktestValidation['holdout']> }) {
  const passed = !holdout.falsified;
  const tone = passed ? PASS_CHIP : FAIL_CHIP;
  const dot  = passed ? PASS_DOT  : FAIL_DOT;

  const label = `OOS holdout: ${holdout.falsified ? 'FAILED' : 'held'}`;
  const title = [
    `Out-of-sample holdout (the ONLY in_sample=false block).`,
    `Train winner: ${holdout.train_winner_config}.`,
    `Test return=${fmtPct(holdout.test_return)}, test Sharpe=${fmt2(holdout.test_sharpe)}.`,
    `Benchmark test return=${fmtPct(holdout.benchmark_test_return)}.`,
    `${holdout.embargo_quarters} quarter(s) purged between train and test.`,
    holdout.caveat,
  ].filter(Boolean).join(' ');

  return (
    <Chip
      tone={tone}
      dot={dot}
      size="sm"
      title={title}
      aria-label={`${label}. Test return ${fmtPct(holdout.test_return)}, Sharpe ${fmt2(holdout.test_sharpe)}. ${holdout.caveat}`}
    >
      <span className="font-mono tabular-nums">
        {label} — test{' '}
        <span className={passed ? 'text-emerald-700 dark:text-emerald-300' : 'text-red-700 dark:text-red-300'}>
          {fmtPct(holdout.test_return)}
        </span>
        {' '}/ Sharpe{' '}
        <span className="tabular-nums">{fmt2(holdout.test_sharpe)}</span>
      </span>
    </Chip>
  );
}

// ---------------------------------------------------------------------------
// Public export
// ---------------------------------------------------------------------------

/**
 * OOS-validation credibility panel for the AI-pick home page.
 *
 * Returns null when `validation` is absent or null — the current artifact
 * pre-dates the block; the badge is invisible until the next backfill rerun.
 */
export function BacktestValidationBadge({
  validation,
}: {
  validation: BacktestValidation | null | undefined;
}) {
  // Graceful-absent: render nothing when the validation block is missing.
  if (validation == null) return null;

  const {
    phi_passes,
    selection_footprint_note,
    pbo,
    holdout,
    walk_forward_sharpe_stability,
  } = validation;

  // If every meaningful field is null/absent, still return null (degenerate
  // partial artifact with an empty validation object).
  const hasContent =
    phi_passes != null ||
    selection_footprint_note != null ||
    pbo != null ||
    holdout != null;
  if (!hasContent) return null;

  return (
    <section
      aria-label="Backtest OOS validation"
      className="rounded border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/50"
    >
      {/* Section header — quiet secondary label, not a second hero */}
      <h3 className="mb-3 text-[0.625rem] font-semibold uppercase tracking-[0.08em] text-slate-500 dark:text-slate-400">
        Backtest validation
      </h3>

      {/* Chip row — DSR headline + optional PBO + optional holdout */}
      <div className="flex flex-wrap gap-2">
        {/* DSR headline chip — always shown when phi_passes is present */}
        {validation.phi_passes != null && (
          <DsrChip v={validation} />
        )}

        {/* PBO chip — only when pbo block is present */}
        {pbo != null && <PboChip pbo={pbo} />}

        {/* Holdout chip — the ONLY genuine OOS read */}
        {holdout != null && <HoldoutChip holdout={holdout} />}

        {/* Walk-forward stability chip — informational, neutral tone */}
        {walk_forward_sharpe_stability != null &&
          walk_forward_sharpe_stability.sharpe_mean != null && (
            <Chip
              tone={NEUTRAL_CHIP}
              dot={NEUTRAL_DOT}
              size="sm"
              title={[
                'Walk-forward Sharpe stability (all k windows, in-sample).',
                walk_forward_sharpe_stability.sharpe_min != null
                  ? `Min=${fmt2(walk_forward_sharpe_stability.sharpe_min)}`
                  : '',
                walk_forward_sharpe_stability.sharpe_max != null
                  ? `Max=${fmt2(walk_forward_sharpe_stability.sharpe_max)}`
                  : '',
                `Mean=${fmt2(walk_forward_sharpe_stability.sharpe_mean)}.`,
                walk_forward_sharpe_stability.sharpe_dispersion != null
                  ? `Dispersion=${fmt2(walk_forward_sharpe_stability.sharpe_dispersion)}.`
                  : '',
                walk_forward_sharpe_stability.label ?? '',
              ].filter(Boolean).join(' ')}
              aria-label={`Walk-forward Sharpe mean ${fmt2(walk_forward_sharpe_stability.sharpe_mean)}`}
            >
              <span className="font-mono tabular-nums">
                Walk-fwd Sharpe{' '}
                {walk_forward_sharpe_stability.sharpe_min != null &&
                 walk_forward_sharpe_stability.sharpe_max != null
                  ? `${fmt2(walk_forward_sharpe_stability.sharpe_min)}–${fmt2(walk_forward_sharpe_stability.sharpe_max)}`
                  : `mean ${fmt2(walk_forward_sharpe_stability.sharpe_mean)}`}
              </span>
            </Chip>
          )}
      </div>

      {/* Selection-footprint caveat — the key honesty line. Always shown when
          present: the +127.7pp / ~16% tuning-artifact note from the methodology
          audit. Styled as secondary disclaimer text, amber-toned chip for salience. */}
      {selection_footprint_note != null && (
        <div className="mt-3 flex flex-wrap items-start gap-2">
          <Chip
            tone={CAVEAT_CHIP}
            dot={CAVEAT_DOT}
            size="sm"
            aria-label={`Selection footprint caveat: ${selection_footprint_note}`}
          >
            Selection footprint
          </Chip>
          <p className="flex-1 text-xs leading-relaxed text-slate-600 dark:text-slate-400 min-w-0">
            {selection_footprint_note}
          </p>
        </div>
      )}

      {/* Holdout caveat — the 9-leg weak-floor note, accessible below the chip */}
      {holdout?.caveat != null && (
        <p className="mt-2 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          <span className="font-medium text-slate-600 dark:text-slate-300">OOS caveat:</span>{' '}
          {holdout.caveat}
        </p>
      )}

      {/* PBO config_correlation_note — surfaces why a low PBO shouldn't be
          over-read (e.g., high correlation between configs means the test has
          less discriminating power than the raw PBO number suggests). */}
      {pbo?.config_correlation_note != null && (
        <p className="mt-1.5 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
          <span className="font-medium text-slate-600 dark:text-slate-300">PBO note:</span>{' '}
          {pbo.config_correlation_note}
        </p>
      )}
    </section>
  );
}
