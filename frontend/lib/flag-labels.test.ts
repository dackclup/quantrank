/**
 * Contract tests for frontend/lib/flag-labels.ts
 *
 * Guard: every active-veto flag string (as emitted by compute/scoring/risk_overlay.py
 * `compute_risk_flags`) must map to a human-readable label — NOT the raw snake_case
 * string echoed back — so the UI never silently shows a raw identifier after a Python
 * rename without a corresponding update here.
 *
 * Run:  cd frontend && npm run test:unit
 */

import { describe, it, expect } from 'vitest';
import { FLAG_LABELS, flagLabel } from './flag-labels';

// ---------------------------------------------------------------------------
// Active-veto flag literals from compute/scoring/risk_overlay.py
// `compute_risk_flags()` — 9 vetoes as of schema 0.10.26-phase8pilot.
//
// Source cross-reference:
//   "fundamentals_unavailable"           risk_overlay.py:1039 (snap is None OR all-null)
//   "post_split_share_lag_unreconciled"  risk_overlay.py:1071 (Tier-2 VETO)
//   "data_quality_input_corruption"      risk_overlay.py:1081
//   "altman_distress"                    risk_overlay.py:1084
//   "sloan_accruals_top_decile"          risk_overlay.py:1113
//   "net_issuance_top_decile"            risk_overlay.py:1135
//   "non_reliance_filing"                risk_overlay.py:1145
//   "beneish_manipulation_veto"          risk_overlay.py:1156
//   "dechow_manipulation_veto"           risk_overlay.py:1165
// ---------------------------------------------------------------------------
const ACTIVE_VETO_FLAGS = [
  'fundamentals_unavailable',
  'post_split_share_lag_unreconciled',
  'data_quality_input_corruption',
  'altman_distress',
  'sloan_accruals_top_decile',
  'net_issuance_top_decile',
  'non_reliance_filing',
  'beneish_manipulation_veto',
  'dechow_manipulation_veto',
] as const;

// A representative set of annotate flags (emit to valuation_warnings / risk_flags
// but do not hard-veto Top-5). Source: manipulation_index.py FLAG_WEIGHTS table
// + risk_overlay.py annotate paths.
const REPRESENTATIVE_ANNOTATE_FLAGS = [
  'beneish_high',
  'dechow_high',
  'manipulation_triple_flag',
  'rem_suspect',
  'restatement_history',
  'restatement_high_confidence',
  'late_filing_notification',
  'accruals_momentum_high',
  'loss_avoidance_pattern',
  'loss_avoidance_pattern_size_invariant',
  'share_count_extraction_missing',
  'insider_sell_cluster',
  'c_suite_unusual_sell',
  'post_split_share_lag',
  'going_concern_disclosure',
  'non_reliance_filing',
  'stale_filing_hard',
  'stale_filing_soft',
  'goodwill_heavy',
  'value_trap_risk',
  'extreme_graham_estimate',
  'extreme_dcf_estimate',
  'extreme_estimate_majority',
] as const;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * True when `label` looks like a raw Python snake_case identifier echoed back.
 * A valid human label should NOT be all-lowercase with underscores.
 * (The Title-Case fallback produces "Fundamentals Unavailable" — which is
 * snake_case-free but NOT a manually curated label. We want explicit entries
 * for vetoes so a rename surfaces immediately.)
 */
function isRawSnakeCase(label: string): boolean {
  return label === label.toLowerCase() && label.includes('_');
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('FLAG_LABELS map', () => {
  it('has no empty-string values', () => {
    for (const [flag, label] of Object.entries(FLAG_LABELS)) {
      expect(label, `FLAG_LABELS["${flag}"] must not be empty`).not.toBe('');
      expect(label.trim(), `FLAG_LABELS["${flag}"] must not be blank`).not.toBe('');
    }
  });

  it('has no raw snake_case values (every entry is human-readable)', () => {
    for (const [flag, label] of Object.entries(FLAG_LABELS)) {
      expect(
        isRawSnakeCase(label),
        `FLAG_LABELS["${flag}"] = "${label}" looks like a raw identifier, not a human label`,
      ).toBe(false);
    }
  });
});

describe('flagLabel() — active-veto flags', () => {
  // This is the drift guard: each active-veto flag must have an EXPLICIT entry
  // in FLAG_LABELS, not just the title-case fallback. If `flagLabel(flag)` returns
  // a value NOT in FLAG_LABELS, the key is missing and the UI falls back to the
  // auto-generated Title Case. That is a contract violation for vetoes.
  //
  // ('fundamentals_unavailable' — veto since #487 — was missing from FLAG_LABELS
  // and only got the Title-Case fallback; this test surfaced the drift and the
  // curated entry was added alongside it.)

  for (const flag of ACTIVE_VETO_FLAGS) {
    it(`"${flag}" has an explicit label in FLAG_LABELS`, () => {
      // Every active veto must have an explicit curated entry.
      expect(FLAG_LABELS).toHaveProperty(flag);
      const label = flagLabel(flag);
      expect(label, `flagLabel("${flag}") must not be empty`).not.toBe('');
      expect(
        isRawSnakeCase(label),
        `flagLabel("${flag}") = "${label}" looks like a raw identifier`,
      ).toBe(false);
    });
  }

  it('returns non-empty human labels for all active vetoes (batch)', () => {
    for (const flag of ACTIVE_VETO_FLAGS) {
      const label = flagLabel(flag);
      expect(label, `flagLabel("${flag}") must be non-empty`).not.toBe('');
    }
  });
});

describe('flagLabel() — annotate flags', () => {
  it('returns non-empty human labels for representative annotate flags', () => {
    for (const flag of REPRESENTATIVE_ANNOTATE_FLAGS) {
      const label = flagLabel(flag);
      expect(label, `flagLabel("${flag}") must be non-empty`).not.toBe('');
    }
  });

  it('returns explicit map entries (not fallback) for known annotate flags', () => {
    // Spot-check a few high-traffic annotate flags that are in FLAG_LABELS.
    const knownAnnotates = [
      'beneish_high',
      'dechow_high',
      'rem_suspect',
      'restatement_history',
      'late_filing_notification',
      'accruals_momentum_high',
      'loss_avoidance_pattern',
      'insider_sell_cluster',
      'post_split_share_lag',
      'stale_filing_hard',
      'going_concern_disclosure',
    ] as const;
    for (const flag of knownAnnotates) {
      expect(FLAG_LABELS, `"${flag}" must have an explicit entry`).toHaveProperty(flag);
    }
  });
});

describe('flagLabel() — unknown-key fallback', () => {
  it('returns Title Case (not the raw snake_case string) for an unknown flag', () => {
    // The contract: unknown keys are title-cased, NOT echoed as-is.
    // This means a renamed Python flag silently gets a tolerable (not garbled) label,
    // but the contract tests above ensure KNOWN active-veto flags are explicitly mapped.
    const result = flagLabel('some_unknown_flag_xyz');
    expect(result).toBe('Some Unknown Flag Xyz');
    // Confirm it is NOT the raw snake_case string.
    expect(result).not.toBe('some_unknown_flag_xyz');
  });

  it('produces Title Case for a multi-word unknown flag', () => {
    expect(flagLabel('a_b_c_d')).toBe('A B C D');
  });

  it('returns a non-empty string for any input', () => {
    const unknownFlags = [
      'brand_new_future_flag',
      'hypothetical_phase9_veto',
      'single',
    ];
    for (const flag of unknownFlags) {
      expect(flagLabel(flag)).not.toBe('');
    }
  });
});
