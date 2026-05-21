# Phase 3 flag-correlation analysis

- Universe: **502 stocks**
- Active flags observed: **25**
- Dead flags (firing-rate = 0): **0** — prune-or-recal candidates
- Rare flags (0 < firing-rate < 1%): **6** — excluded from heatmap (low variance)

## Firing rates

| Flag | Fired | Base rate |
|---|---:|---:|
| `value_trap_risk` | 176 | 35.1% |
| `goodwill_heavy` | 90 | 17.9% |
| `extreme_rim_estimate` | 78 | 15.5% |
| `extreme_graham_estimate` | 69 | 13.7% |
| `restatement_history` | 59 | 11.8% |
| `sloan_accruals_top_decile` | 56 | 11.2% |
| `extreme_dcf_estimate` | 53 | 10.6% |
| `accruals_momentum_high` | 50 | 10.0% |
| `altman_distress` | 46 | 9.2% |
| `net_issuance_top_decile` | 37 | 7.4% |
| `extreme_multiples_pb_estimate` | 35 | 7.0% |
| `beneish_high` | 26 | 5.2% |
| `cross_source_disagreement` | 23 | 4.6% |
| `rem_suspect` | 16 | 3.2% |
| `extreme_multiples_pe_estimate` | 14 | 2.8% |
| `beneish_manipulation_veto` | 11 | 2.2% |
| `extreme_multiples_ev_ebitda_estimate` | 10 | 2.0% |
| `auditor_change` | 9 | 1.8% |
| `data_quality_input_corruption` | 7 | 1.4% |
| `going_concern_disclosure` | 5 | 1.0% |
| `dechow_high` | 2 | 0.4% |
| `manipulation_triple_flag` | 2 | 0.4% |
| `late_filing_notification` | 2 | 0.4% |
| `dechow_manipulation_veto` | 1 | 0.2% |
| `non_reliance_filing` | 1 | 0.2% |

## Redundancy candidates (|φ| ≥ 0.3)

| Flag A | Flag B | φ | Rate A | Rate B |
|---|---|---:|---:|---:|
| `dechow_high` | `manipulation_triple_flag` | +1.000 | 0.4% | 0.4% |
| `dechow_high` | `dechow_manipulation_veto` | +0.706 | 0.4% | 0.2% |
| `dechow_manipulation_veto` | `manipulation_triple_flag` | +0.706 | 0.2% | 0.4% |
| `beneish_high` | `beneish_manipulation_veto` | +0.640 | 5.2% | 2.2% |
| `extreme_graham_estimate` | `extreme_rim_estimate` | +0.515 | 13.7% | 15.5% |
| `extreme_rim_estimate` | `goodwill_heavy` | +0.445 | 15.5% | 17.9% |
| `beneish_manipulation_veto` | `manipulation_triple_flag` | +0.423 | 2.2% | 0.4% |
| `beneish_manipulation_veto` | `dechow_high` | +0.423 | 2.2% | 0.4% |
| `extreme_graham_estimate` | `goodwill_heavy` | +0.417 | 13.7% | 17.9% |
| `extreme_multiples_ev_ebitda_estimate` | `extreme_multiples_pe_estimate` | +0.409 | 2.0% | 2.8% |
| `dechow_high` | `rem_suspect` | +0.349 | 0.4% | 3.2% |
| `manipulation_triple_flag` | `rem_suspect` | +0.349 | 0.4% | 3.2% |
| `auditor_change` | `dechow_manipulation_veto` | +0.331 | 1.8% | 0.2% |
| `extreme_rim_estimate` | `value_trap_risk` | -0.315 | 15.5% | 35.1% |
| `accruals_momentum_high` | `sloan_accruals_top_decile` | +0.305 | 10.0% | 11.2% |

## Diversity-confirmed pairs (|φ| ≤ 0.05, both rates ≥ 5%)

| Flag A | Flag B | φ | Rate A | Rate B |
|---|---|---:|---:|---:|
| `extreme_graham_estimate` | `net_issuance_top_decile` | -0.002 | 13.7% | 7.4% |
| `accruals_momentum_high` | `restatement_history` | +0.003 | 10.0% | 11.8% |
| `altman_distress` | `goodwill_heavy` | -0.004 | 9.2% | 17.9% |
| `restatement_history` | `sloan_accruals_top_decile` | +0.008 | 11.8% | 11.2% |
| `altman_distress` | `restatement_history` | -0.009 | 9.2% | 11.8% |
| `altman_distress` | `net_issuance_top_decile` | -0.010 | 9.2% | 7.4% |
| `extreme_multiples_pb_estimate` | `extreme_rim_estimate` | +0.012 | 7.0% | 15.5% |
| `extreme_rim_estimate` | `sloan_accruals_top_decile` | -0.012 | 15.5% | 11.2% |
| `extreme_multiples_pb_estimate` | `net_issuance_top_decile` | +0.013 | 7.0% | 7.4% |
| `goodwill_heavy` | `net_issuance_top_decile` | -0.013 | 17.9% | 7.4% |
| `extreme_graham_estimate` | `sloan_accruals_top_decile` | -0.013 | 13.7% | 11.2% |
| `accruals_momentum_high` | `altman_distress` | -0.013 | 10.0% | 9.2% |
| `net_issuance_top_decile` | `restatement_history` | +0.015 | 7.4% | 11.8% |
| `accruals_momentum_high` | `goodwill_heavy` | -0.017 | 10.0% | 17.9% |
| `altman_distress` | `beneish_high` | +0.019 | 9.2% | 5.2% |
| `net_issuance_top_decile` | `sloan_accruals_top_decile` | +0.021 | 7.4% | 11.2% |
| `accruals_momentum_high` | `value_trap_risk` | -0.021 | 10.0% | 35.1% |
| `altman_distress` | `extreme_multiples_pb_estimate` | +0.021 | 9.2% | 7.0% |
| `accruals_momentum_high` | `extreme_rim_estimate` | +0.023 | 10.0% | 15.5% |
| `beneish_high` | `extreme_rim_estimate` | +0.024 | 5.2% | 15.5% |
| `extreme_dcf_estimate` | `restatement_history` | -0.025 | 10.6% | 11.8% |
| `extreme_dcf_estimate` | `goodwill_heavy` | +0.025 | 10.6% | 17.9% |
| `altman_distress` | `extreme_dcf_estimate` | +0.026 | 9.2% | 10.6% |
| `extreme_multiples_pb_estimate` | `goodwill_heavy` | -0.026 | 7.0% | 17.9% |
| `extreme_graham_estimate` | `extreme_multiples_pb_estimate` | +0.027 | 13.7% | 7.0% |
| `extreme_multiples_pb_estimate` | `restatement_history` | -0.027 | 7.0% | 11.8% |
| `extreme_multiples_pb_estimate` | `sloan_accruals_top_decile` | +0.027 | 7.0% | 11.2% |
| `goodwill_heavy` | `value_trap_risk` | -0.028 | 17.9% | 35.1% |
| `goodwill_heavy` | `sloan_accruals_top_decile` | -0.034 | 17.9% | 11.2% |
| `extreme_graham_estimate` | `restatement_history` | +0.034 | 13.7% | 11.8% |
| `extreme_rim_estimate` | `restatement_history` | -0.037 | 15.5% | 11.8% |
| `beneish_high` | `net_issuance_top_decile` | +0.037 | 5.2% | 7.4% |
| `beneish_high` | `goodwill_heavy` | -0.039 | 5.2% | 17.9% |
| `goodwill_heavy` | `restatement_history` | +0.039 | 17.9% | 11.8% |
| `beneish_high` | `value_trap_risk` | -0.040 | 5.2% | 35.1% |
| `accruals_momentum_high` | `extreme_graham_estimate` | +0.041 | 10.0% | 13.7% |
| `extreme_dcf_estimate` | `sloan_accruals_top_decile` | +0.043 | 10.6% | 11.2% |
| `extreme_rim_estimate` | `net_issuance_top_decile` | +0.047 | 15.5% | 7.4% |
| `net_issuance_top_decile` | `value_trap_risk` | +0.048 | 7.4% | 35.1% |
| `extreme_dcf_estimate` | `value_trap_risk` | -0.049 | 10.6% | 35.1% |

## Methodology

- φ-coefficient (Matthews correlation coefficient for the 2×2 case) is the boolean analog of Pearson; defined on {0,1} variables, reads -1 to +1, 0 = independent.
- Sources merged into the flag matrix: `risk_flags` (active vetoes + numerical guards), `valuation_warnings` (annotates + method-applicability + informational), `tier2_events` (boolean keys).
- Heatmap subset: flags with firing-rate ≥ 1% (sub-1% flags carry too little variance for stable φ).
- Reproduce: `python scripts/phase3_flag_correlation.py --data-dir frontend/public/data/stocks --output-dir <dest>`.
