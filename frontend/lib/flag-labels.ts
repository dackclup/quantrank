// Shared human labels for the defense-layer flags that surface across the app:
//   • `valuation_warnings` (compute/valuation/ensemble.py + the manipulation
//     flags compute/main.py ALSO appends — beneish/dechow/… at main.py:1650+)
//   • `risk_flags` (the 9 active vetoes + the annotate cohort)
//
// One map so the SAME flag never reads two ways across two surfaces (the
// FairPriceCard valuation chips, the cross-stock CompareMatrix risk row, and any
// future consumer). Unknown flags fall back to Title Case — forward-safe if a
// new flag string lands in compute/ before this map is updated (cf. the
// `extreme_{method}_estimate` family at ensemble.py:142).
//
// NOTE: `RiskSummaryCard.RANK_GATE_META` routes its rank-gate LABEL through
// `flagLabel()` (the #397 single-source fold) and keeps only the academic
// `detail` line — so the rank-gate vetoes read the SAME string here and on the
// stock-detail Risk Summary. Its SEPARATE `MANIPULATION_FLAG_LABELS` (the "Also
// fired" surplus list) keeps its own richer academic-anchored strings and does
// NOT route through here. This module is the label source the chip surfaces share.
export const FLAG_LABELS: Record<string, string> = {
  // Valuation-method extremeness + valuation-specific guards (ensemble.py).
  extreme_graham_estimate: 'Extreme Graham estimate',
  extreme_multiples_pe_estimate: 'Extreme P/E estimate',
  extreme_multiples_pb_estimate: 'Extreme P/B estimate',
  extreme_multiples_ev_ebitda_estimate: 'Extreme EV/EBITDA estimate',
  extreme_rim_estimate: 'Extreme Residual-Income estimate',
  extreme_dcf_estimate: 'Extreme DCF estimate',
  extreme_estimate_majority: 'Majority of methods extreme',
  stale_filing_soft: 'Stale filing',
  goodwill_heavy: 'Goodwill-heavy balance sheet',
  value_trap_risk: 'Value-trap risk (RIM)',
  data_quality_input_corruption: 'Data-quality guard',
  valuation_output_anomalous: 'Valuation output anomalous',
  // Manipulation / earnings-quality flags (compute/main.py + manipulation_index).
  beneish_high: 'Beneish M-score (warning band)',
  dechow_high: 'Dechow F-score (warning band)',
  manipulation_triple_flag: 'Triple-stack (Sloan + Beneish + Dechow)',
  rem_suspect: 'Real Earnings Management',
  restatement_history: 'Restatement history',
  restatement_high_confidence: 'Restatement — high confidence',
  late_filing_notification: 'Late-filing notification',
  accruals_momentum_high: 'Accruals momentum',
  loss_avoidance_pattern: 'Loss-avoidance pattern',
  loss_avoidance_pattern_size_invariant: 'Loss-avoidance — size-invariant',
  share_count_extraction_missing: 'Share-count extraction missing',
  insider_sell_cluster: 'Insider-sell cluster',
  c_suite_unusual_sell: 'C-suite unusual selling',
  multi_class_aggregate_shares_suspected: 'Multi-class share aggregation suspected',
  cross_source_disagreement: 'Cross-source price disagreement',
  post_split_share_lag: 'Post-split share count adjusted',
  post_split_share_lag_unreconciled: 'Post-split share count unreliable',
  low_liquidity: 'Low liquidity (<$5M ADV)',
  // Tier-2 8-K / going-concern event vetoes + annotates (tier2.py).
  going_concern_disclosure: 'Going-concern disclosure',
  going_concern: 'Going-concern disclosure',
  auditor_change: 'Auditor change',
  // Rank-gate VETO flags (compute/scoring/risk_overlay.py). `FLAG_LABELS` is the
  // SINGLE source for these labels: `RiskSummaryCard.RANK_GATE_META` renders its
  // rank-gate label via `flagLabel()` and holds only the academic `detail` line,
  // so the cross-stock compare matrix (FlagsCell) and the stock-detail Risk Summary
  // read the SAME string with no duplicate to drift. (The post-merge e2e on #394
  // found the matrix Title-Casing these via the fallback while the detail page
  // showed the precise label; #396 added them here, and the single-source fold
  // made the match structural.)
  altman_distress: 'Altman financial distress',
  sloan_accruals_top_decile: 'Sloan accruals — top decile',
  net_issuance_top_decile: 'Net share issuance — top decile',
  non_reliance_filing: '8-K Item 4.02 non-reliance',
  beneish_manipulation_veto: 'Beneish M-score veto',
  dechow_manipulation_veto: 'Dechow F-score veto',
  fundamentals_unavailable: 'Fundamentals unavailable',
  stale_filing_hard: 'Stale filing — fair-price suppressed',
};

export function flagLabel(flag: string): string {
  return (
    FLAG_LABELS[flag] ??
    flag.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  );
}
