// 4-tier recommendation per PR 4d (Option B locked 2026-05-14 — neutral
// terminology, no FINRA/SEC-regulated sell-side labels). Derived
// deterministically from composite_score + risk_flags +
// valuation_warnings + fair_price MoS by
// `compute.scoring.recommendation.derive_recommendation`. null on
// legacy outputs from before this field was added.
export type Recommendation = 'bullish' | 'lean_bullish' | 'neutral' | 'cautious';

export type PillarScores = {
  quality: number | null;
  value: number | null;
  growth: number | null;
  momentum: number | null;
  health: number | null;
  profitability: number | null;
  technical: number | null;
  risk: number | null;
  sentiment: number | null;
  ml: number | null;
};

export type StockSummary = {
  rank: number;
  ticker: string;
  name: string;
  sector: string;
  composite_score: number;
  current_price: number;
  fair_price: number | null;
  max_fair_price: number | null;
  margin_of_safety_pct: number | null;
  pillar_scores: PillarScores;
  risk_flags: string[];
  valuation_warnings: string[];
  recommendation: Recommendation | null;
  // Loss Chance % heuristic chip — 5-95 clipped, null when MoS missing.
  // See `compute/scoring/loss_chance.py` for the rubric. Display via
  // `LossChanceBadge` with small italic "heuristic" qualifier (Option D
  // locked per `phase-4-kickoff-checklist/PLAN.md` §1).
  loss_chance_pct: number | null;
  // Day-over-day percent change from the prior trading-day close
  // (compute/main.py _fetch_prices_one). Null when only one close
  // is available (newly-IPO'd tickers).
  price_change_1d_pct: number | null;
  // PR 4.5f — manipulation_index rollup of the 4.5a-d defense flags
  // into a 0-100 risk score. composite_score_adjusted = composite_score
  // − soft penalty (max 10 composite points at index=100). RANK STILL
  // USES THE RAW composite_score per SKILL.md Rule 16; the adjusted
  // value is informational. See `compute/scoring/manipulation_index.py`.
  manipulation_index: number | null;
  composite_score_adjusted: number | null;
  entered_top5: boolean;
  exited_top5: boolean;
  // Phase 8 pilot PR 3a (0.10.21-phase8pilot) — which index this stock
  // belongs to: "sp500" or "sp400". Default "sp500" so legacy outputs and
  // sp500-path runs deserialize cleanly without schema-breaking changes.
  // Annotate-only — does not affect composite rank or vetoes.
  index_membership: string;
  // Multi-index membership — Dow 30 / NDX 100 overlap tabs (0.10.23-phase8pilot).
  // Contains the primary cohort code ("sp500" | "sp400") PLUS every overlapping
  // index the stock is currently in ("dow30", "ndx"). Empty array [] on legacy
  // outputs (pre-0.10.23) and on sp500-path runs before the first Dow/NDX fetch.
  // `index_membership` (singular) is KEPT UNCHANGED — MidcapChip depends on it
  // as the sp500/sp400 partition signal.
  index_memberships: string[];
};

export type Metadata = {
  version: string;
  last_update_utc: string;
  next_update_utc: string;
  universe: string;
  universe_size: number;
  compute_run_id: string;
  git_commit: string;
  mos_trailing_ic_smoke: number | null;
  tier2_coverage_pct: number | null;
  // PR 3d Part 2 — observability for SEC EDGAR throttling diagnostics.
  // coverage_pct = % of universe with non-null FundamentalsSnapshot.
  // p50/p95 = per-stock fetch wall-clock distribution. All null on
  // older outputs from before this field was added.
  fundamentals_coverage_pct: number | null;
  fundamentals_latency_p50_seconds: number | null;
  fundamentals_latency_p95_seconds: number | null;
  // Phase 4h — OSAP signal observability. `osap_signals_used` lists
  // the 100-signal manifest subset that PASSED the PBO/DSR gate
  // (`pbo_dsr.factor_passes_gates`); `osap_excluded_signals` lists
  // the rest. `osap_signals_ic_12m` is rolling-12m Spearman IC per
  // accepted signal (observability only — NOT a hard gate; full
  // walk-forward IC-decay is the Phase 5 stronger version).
  // `osap_signals_coverage_pct` reports per-signal S&P 500 coverage.
  // All null on legacy outputs from before 0.9.0-phase4h.
  osap_signals_used: string[] | null;
  osap_excluded_signals: string[] | null;
  osap_signals_ic_12m: Record<string, number> | null;
  osap_signals_coverage_pct: Record<string, number> | null;
  // Phase 4h.2 Part 1 — observability for the manifest-vs-dataset gap
  // and per-signal gate decisions surfaced by issue #116.
  // `osap_signals_missing_from_dataset` lists OSAP_SIGNALS_100 entries
  // that the OSAP fetch returned no rows for (silent drops in
  // 0.9.0-phase4h; visible here). `osap_gate_diagnostics` carries the
  // per-signal PBO/DSR/Sharpe/rejection_reason for every signal that
  // reached the gate. Both null on legacy outputs from before
  // 0.9.1-phase4h.2.
  osap_signals_missing_from_dataset: string[] | null;
  osap_gate_diagnostics: Record<string, OsapGateDiagnostic> | null;
  // Phase 4h.2 Part 2 — signals present in the OSAP dataset but with
  // fewer than 2 distinct port buckets (no long-short pair possible).
  // Closes the 100-signal accounting equation:
  //   OSAP_SIGNALS_100.length === osap_signals_missing_from_dataset
  //                             + osap_signals_dropped_no_long_short
  //                             + osap_signals_used + osap_excluded_signals
  // Null on legacy outputs from before 0.9.2-phase4h.2.
  osap_signals_dropped_no_long_short: string[] | null;
  // Phase 4j.1 (0.10.15-phase4.6, Rule 18) — Qlib Alpha158 factor
  // integration, OBSERVABILITY-ONLY. The adapter
  // (`compute/features/alpha158_replicate.py`) converts the 158 per-stock
  // Alpha158 feature values into the (date × signal) long-short return
  // contract so the existing PBO/DSR gate applies unchanged (n_trials=158).
  // 4j.1 blends NOTHING — composite_score is byte-identical to pre-4j.1
  // (Δscore = 0); the rank-influencing blend is deferred to 4j.2. Null on
  // legacy outputs (pre-0.10.15) and when the Alpha158 pipeline degrades.
  // The 158-feature accounting equation MUST close:
  //   158 === alpha158_features_missing_from_compute
  //         + alpha158_features_dropped_no_long_short
  //         + alpha158_features_used + alpha158_excluded_features
  alpha158_features_used?: string[] | null;
  alpha158_excluded_features?: string[] | null;
  alpha158_features_ic_12m?: Record<string, number> | null;
  alpha158_features_missing_from_compute?: string[] | null;
  alpha158_features_dropped_no_long_short?: string[] | null;
  // Per-feature PBO/DSR/Sharpe/rejection_reason — reuses OsapGateDiagnostic
  // verbatim (the gate-verdict shape is signal-agnostic).
  alpha158_gate_diagnostics?: Record<string, OsapGateDiagnostic> | null;
  // % of the universe with ≥1 non-null Alpha158 feature at the latest date
  // (feature-compute health canary; parity with tier2_coverage_pct).
  alpha158_coverage_pct?: number | null;
  // Survivorship honesty: true only when the per-month ranking universe
  // came from the point-in-time membership snapshot AND every consumed
  // month was complete; a single degraded month flips it false. Null when
  // the pipeline degraded.
  alpha158_survivorship_bias_corrected?: boolean | null;
  // Wall-clock seconds for the Alpha158 Step 7.6 block (feature compute +
  // adapter + gate). Null on full-pipeline failure. Parity with
  // osap_wall_clock_seconds.
  alpha158_wall_clock_seconds?: number | null;
  // Epic #150 Phase 1.6 (issue #155) — explicit compute-time state of
  // the Tier-2 8-K defenses (`compute/scoring/tier2._EIGHT_K_DEFENSES_ENABLED`).
  // Optional + nullable: absent / null on legacy outputs written before
  // 0.9.3-phase4h.3; consumers should treat both as "assume enabled"
  // (matches the Pydantic default). The static site doesn't currently
  // render this; the verify-helper Section B branch is the primary
  // consumer.
  tier2_enabled?: boolean | null;
  // Phase 4b (0.9.5-phase4h.5) — count of tickers where
  // `loss_avoidance_pattern_size_invariant` fired on this cron run
  // (Roychowdhury 2006 §5.2 suspect-firm: NI/TotalAssets ∈ [0, 0.005]
  // for 3+ consecutive fiscal years). Optional + nullable: absent /
  // null on legacy snapshots pre-0.9.5. Rule 18 observability surface
  // shipped alongside the flag itself so the next cron's firing rate
  // is visible without grepping per-stock JSONs; not currently
  // rendered by the static site.
  loss_avoidance_size_invariant_firing_count?: number | null;
  // Issue #176 (0.9.6-phase4h.6) — count of tickers where
  // `share_count_extraction_missing` fired on this cron run
  // (snapshot has revenue + total_assets but `shares_outstanding`
  // is None — STZ 2026-05-14 partial-XBRL-extraction pattern).
  // Optional + nullable: absent / null on legacy snapshots pre-0.9.6.
  // Rule 18 observability surface shipped alongside the flag itself
  // so the next cron's firing rate is visible at-a-glance.
  share_count_extraction_missing_count?: number | null;
  // Issue #177 (0.9.7-phase4h.7) — count of tickers where
  // `extreme_estimate_majority` fired on this cron run (≥
  // `EXTREME_MAJORITY_THRESHOLD = 3` of 6 fair-price methods past
  // the Defense #4 5×/0.2× outlier guard — Huber 1981 §1.4
  // breakdown-point cohort). Optional + nullable: absent / null on
  // legacy snapshots pre-0.9.7. Rule 18 observability surface
  // shipped alongside the flag itself so the next cron's firing
  // rate is visible at-a-glance (gates the follow-up median-
  // exclusion PR per methodology-scientist Mode B 2026-05-21).
  extreme_estimate_majority_count?: number | null;
  // Phase 4.5e PR 3 (0.10.1-phase4.5e) — Rule 18 observability surface
  // for the new Form-4 insider-cluster annotates emitted from
  // `compute/scoring/form4_signals.py`. `insider_sell_cluster_firing_count`
  // counts tickers where ≥ 3 distinct insiders sold $1M+ in opportunistic
  // transactions (codes S, D per Cohen-Malloy-Pomorski 2012 §III.A) in
  // a rolling 30-day window. `c_suite_unusual_sell_firing_count` counts
  // the narrower CEO + CFO co-sell subset (Jeng-Metrick-Zeckhauser 2003
  // §V — strict subset of the cluster flag). Both optional + nullable
  // on legacy snapshots pre-0.10.1. Gates the methodology-scientist
  // Q3 2026-08-19 cohort-acceptance check that may promote the cluster
  // weight from 5.0 → 10.0.
  insider_sell_cluster_firing_count?: number | null;
  c_suite_unusual_sell_firing_count?: number | null;
  // Phase 4.5e PR 4-eq (0.10.2-phase4.5e) — Rule 18 observability surface
  // for the 10b5-1 contamination filter applied in
  // `compute/scoring/form4_signals._is_opportunistic_sell`. Counts the
  // universe-wide total of Form-4 transactions that WOULD have been
  // classified as opportunistic (code ∈ {S, D}) absent the filter but
  // were dropped because `is_rule_10b5_one is True` (resolved from
  // footnote-text scan; edgartools 5.31.5 does not parse the SEC
  // structured <rule10b5_1> element added 2023-04-01). Counted within
  // the 30d cluster-detection window per ticker. Gates the Q3
  // 2026-08-19 cohort-acceptance check for the cluster-weight
  // promotion 5.0 → 7.0 (separate follow-up PR per methodology
  // Mode B 2026-05-23). Optional + nullable on legacy snapshots
  // pre-0.10.2.
  form4_rule10b5_one_excluded_count?: number | null;
  // Issue #67 (0.9.8-phase4h.8) — sector-adjusted cost of equity
  // (Damodaran 2019 *Investment Valuation* 3rd ed. Table 8.4 +
  // Damodaran NYU online betas dataset, January 2025 update).
  // Rule 18 observability surface: both counts computed every cron
  // regardless of USE_SECTOR_COE flag (default False) so the delta
  // is visible before the production flip. `sector_coe_enabled`
  // mirrors config.USE_SECTOR_COE at write time.
  // `value_trap_risk_count_without_sector_coe` = baseline flat-10%
  // count; `value_trap_risk_count_with_sector_coe` = count under
  // per-sector Ke. Delta = expected FP-reduction once flipped.
  // All three optional + nullable on legacy snapshots pre-0.9.8.
  sector_coe_enabled?: boolean | null;
  value_trap_risk_count_with_sector_coe?: number | null;
  value_trap_risk_count_without_sector_coe?: number | null;
  // Phase 4.5e PR 2 (0.10.0-phase4.5e) — Form-4 insider-transaction
  // fetch observability surface. `form4_enabled` mirrors
  // `_FORM4_FLAGS_ENABLED` in tier2.py (False in this PR; PR 3 flips
  // it). `form4_coverage_pct` = % of universe with a successful fetch.
  // p50/p95 latency fields let the cron budget be verified.
  // `form4_fetch_failures` is bounded ≤ 20 tickers. All optional +
  // nullable on legacy snapshots pre-0.10.0.
  form4_enabled?: boolean | null;
  form4_coverage_pct?: number | null;
  form4_fetch_latency_p50_seconds?: number | null;
  form4_fetch_latency_p95_seconds?: number | null;
  form4_universe_insider_count_median?: number | null;
  form4_tickers_with_recent_activity?: number | null;
  form4_fetch_failures?: string[] | null;
  // Issue #248 PR2a (0.10.3-phase4.5e) — Rule 18 observability for the
  // cross-source market-cap validator. count = # tickers above 5%
  // tolerance; histogram aggregates ALL deltas (including <5% non-fire
  // and yfinance-unavailable cases) across 9 buckets. See
  // compute/output/schemas.py::Metadata for the bucket-boundary table.
  cross_source_disagreement_count?: number | null;
  cross_source_delta_histogram?: Record<string, number> | null;
  // Listing-metadata observability (0.10.12-phase4.6) — % of universe whose
  // StockDetail.exchange resolved to a non-null display name. Ships before the
  // hero country/exchange chips read the field (observability-before-wiring).
  exchange_coverage_pct?: number | null;
  // country_coverage_pct (0.10.13-phase4.6) — % of universe whose
  // StockDetail.country resolved (US-tagged). NOT redundant with
  // exchange_coverage_pct: exchange passes unknown codes through (counts as
  // covered) while country resolves only known US codes, so the two diverge on
  // a raw passthrough code (the CBOE/BTS canary; exchange 100% / country 99.8%
  // on the 2026-06-02 cron before the BTS fix).
  country_coverage_pct?: number | null;
  // benchmark_coverage_pct (0.10.14-phase4.6) — % of the benchmark index
  // proxies (SPY/QQQ/DIA/IWM) whose ~5y close series exported to
  // public/data/portfolio/benchmarks.json. Observability-before-wiring: ships
  // before the Phase 7 AI-pick home page reads benchmarks.json. Display-only.
  benchmark_coverage_pct?: number | null;
  // Issue #246 PR2a (0.10.3-phase4.5e) — Rule 18 retrofit for the
  // `_fetch_shares_from_per_filing_xbrl` fallback trigger extended in
  // PR #253. triggered_count = total fired (None-primary + too_low-
  // primary); too_low_count = subset where the new < MIN_PLAUSIBLE_SHARE_COUNT
  // (100K) trigger fired (ERIE-class).
  shares_fallback_triggered_count?: number | null;
  shares_fallback_too_low_count?: number | null;
  // Issue #248 PR2b (0.10.4-phase4.5e) — Rule 18 observability for the
  // multi-class dimensional override path. Counts tickers where the
  // primary `companyfacts` shares_outstanding was overridden by the
  // per-filing XBRL dimensional sum (V/NWS/NWSA/FOX/FOXA/BRK-B/STZ
  // allowlist). Disjoint from triggered_count above.
  shares_fallback_dimensional_override_count?: number | null;
  // Issue #261 (0.10.5-phase4.5e) — Rule 18 observability for the
  // `multi_class_aggregate_shares_suspected` annotate (CIK-collision
  // detector for the GOOG/GOOGL-shape overcount pattern, opposite
  // direction to PR #257's allowlist). Expected steady-state firing
  // rate: 6 (GOOG, GOOGL, NWS, NWSA, FOX, FOXA per cron #3 cohort).
  // Gates Q3 2026-08-19 quarterly-audit cohort acceptance check on
  // the 10% × universe-median market_cap floor recalibration.
  multi_class_aggregate_shares_suspected_count?: number | null;
  // Issue #261 PR-B (0.10.6-phase4.5e) — Rule 18 observability for the
  // structural per-class XBRL extraction path that overrides the
  // companyfacts aggregate with a single class member's count for
  // GOOG / GOOGL. Disjoint from `shares_fallback_dimensional_override_count`
  // (which is the OPPOSITE-direction sum-all path for V/NWS/NWSA/FOX/
  // FOXA/BRK-B/STZ). Expected steady-state firing rate: 2.
  multi_class_per_class_override_count?: number | null;
  // Issue #288 (0.10.8-phase4.6) — Rule-18 disambiguator on the per-class
  // override path. Increments each time Branch 3 enters the XBRL call
  // regardless of success. Pre-fix this would be 2 with override = 0
  // (surfacing the silent XBRL lookup failure PR #269 missed).
  // Post-fix expected steady-state: attempt = override = 2.
  multi_class_per_class_attempt_count?: number | null;
  // Issue #261 PR-B (0.10.6-phase4.5e) — Defensive sanity-check counter
  // on the per-class override path. Fires when per-class is outside the
  // expected 5-95% fraction of primary, or when per-class >= primary
  // (override skipped). Expected steady-state firing rate = 0; non-zero
  // signals possible XBRL shape drift or stale allowlist entry per
  // methodology-scientist Q3 verdict 2026-05-26 (Damodaran 2019 Ch. 16
  // identity check Σ per-class MC = aggregate MC).
  multi_class_mc_reconcile_failure_count?: number | null;
  // Phase 4.6 (0.10.7-phase4.6) — survivorship-bias visibility per
  // Research Report v1.0 §7.4 + Hou-Xue-Zhang 2020 RFS replication
  // crisis evidence. `universe_membership_as_of` is the ISO date of
  // the historical S&P 500 membership snapshot used for this compute
  // run; forward weekly cron = current; backtests = as-of date.
  // `survivorship_bias_corrected` = true when a non-current lookup
  // was used or when current membership matched; false when fallback
  // to current happened for a historical date (data-quality degraded).
  // Both nullable on legacy snapshots (pre-0.10.7); not currently
  // rendered by the static site.
  universe_membership_as_of?: string | null;
  survivorship_bias_corrected?: boolean | null;
  // Issue #287 PR A (0.10.9-phase4.6) — per-loop wall-clock observability.
  // Total elapsed wall-clock seconds for the entire loop start-to-end
  // (parity with `fundamentals_latency_p95_seconds` but measures whole-
  // loop duration not per-ticker p95). null when the loop was skipped
  // via escape-hatch env-var (`FORM4_FETCH_SKIP` only) OR when the loop
  // failed before the end marker. `QR_SKIP_OSAP` is NOT a skip-to-null
  // — that env-var only bypasses the OSAP freshness gate; the try block
  // still runs and `osap_wall_clock_seconds` populates with a small float
  // on a cache-hit fast return. `cross_source_wall_clock_seconds`
  // measures the ENTIRE Step 8 per-ticker loop, not just cross-source.
  tier2_wall_clock_seconds?: number | null;
  form4_wall_clock_seconds?: number | null;
  osap_wall_clock_seconds?: number | null;
  cross_source_wall_clock_seconds?: number | null;
  // Issue #67 follow-up (0.10.10-phase4.6) — per-sector delta
  // instrumentation per methodology-scientist Mode B Q2 verdict
  // (deferred from PR #294 sector-CoE flip). Keys: GICS sector names;
  // values: `without_sector_coe[sector] - with_sector_coe[sector]`.
  // Positive = sector dropped flags after flip (Damodaran predicts
  // Utilities/Real Estate/Consumer Staples); negative = sector gained
  // flags (Information Technology/Energy). Computed every cron for
  // Q3 cohort audit prep. null on legacy pre-0.10.10 snapshots.
  value_trap_risk_delta_by_sector?: Record<string, number> | null;
  // Phase 4.5e PR 6 (0.10.11-phase4.6) — count of True → False
  // downgrades applied by the post-detector 10b5-1 negation guard
  // during cache build (residual footgun #1 from PR 4-eq). Tracks
  // universe-wide cohort of footnote disclosures matching phrases
  // like "10b5-1 plan terminated" / "no 10b5-1 plan in effect" /
  // "previously had a 10b5-1 plan" — where the upstream substring
  // detector returns True even though the affirmative defense is
  // NOT in force. Null semantics mirror `form4_wall_clock_seconds`:
  // null when FORM4_FETCH_SKIP=1 OR outer try/except fired before
  // end marker. Warm-cache runs report 0 (detector didn't run);
  // cold-cache runs populate real cohort number for Q3 2026-08-19
  // cohort-acceptance check (issue #130) alongside
  // `form4_rule10b5_one_excluded_count`. Null on legacy pre-0.10.11
  // snapshots.
  form4_negation_guard_downgrade_count?: number | null;
  // Issue #75 §3 (Rule 18 observability-before-wiring) — URL of the
  // IC-decay monitor artifact (`/data/decay_report.json`,
  // McLean-Pontiff 2016). The report is a transparency surface
  // (monitor + manual review; NEVER vetoes / changes scores). Null
  // when the monitor is skipped (`QR_SKIP_DECAY_MONITOR`), degrades, or
  // on legacy outputs from before this field was added. The report
  // densifies only as the cron's git-history depth allows (currently a
  // shallow checkout — see #478); until ≥ MIN_HISTORY_MONTHS of
  // out-of-sample IC history are visible it stays
  // `status="insufficient_history"` with every pillar `preliminary`.
  decay_report_url?: string | null;
  // Phase 8 pilot PR 1 (0.10.19-phase8pilot, Rule 18) —
  // observability-before-wiring diagnostics for the S&P 900 universe
  // expansion pilot. All four fields are null on the default sp500 path
  // (QR_UNIVERSE=sp500, unchanged cron); populated only when
  // QR_UNIVERSE=sp900 and the diagnostic probe ran successfully.
  // Ranked output (rankings.json + stocks/*.json) is byte-identical
  // to a 500 run — the probe loop does NOT feed the writer. PR 3 will
  // wire the ranked output once coverage is verified.
  //
  // `universe_cohort_sizes` — count per cohort after de-dup:
  //   keys "sp500" (≤502) and "sp400" (≤400; sp500 wins on overlap).
  universe_cohort_sizes?: Record<string, number> | null;
  // `midcap_fundamentals_coverage_pct` — % of sp400 tickers with a
  // non-null FundamentalsSnapshot from the diagnostic probe.
  midcap_fundamentals_coverage_pct?: number | null;
  // `midcap_null_rate_pct` — % of sp400 tickers returning null.
  // Complement of midcap_fundamentals_coverage_pct (sums ≈ 100%).
  midcap_null_rate_pct?: number | null;
  // `midcap_cik_resolution_pct` — % of sp400 tickers whose CIK
  // resolved (Wikipedia page or Company(ticker).cik lookup).
  midcap_cik_resolution_pct?: number | null;
  // OZK/PBF flip-blocker (0.10.22-phase8pilot) — count of tickers whose
  // FundamentalsSnapshot was None (complete EDGAR ingest failure) on this
  // cron run. Rule-18 observability surface for the new
  // `fundamentals_unavailable` direct veto. Optional + nullable: absent /
  // null on legacy snapshots pre-0.10.22. A non-zero value on a production
  // sp500 cron is a data-pipeline health signal requiring investigation.
  fundamentals_unavailable_count?: number | null;
  // Issue #177 follow-up (0.10.24-phase8pilot) — count of tickers whose
  // MoS (margin-of-safety) SIGN would FLIP under the shadow trimmed-median
  // (i.e. the trim would move them across the mos_pct=0 line). Rule-18
  // blast-radius metric for the fair-value trimmed-median feature; the live
  // `mos_pct` is byte-identical (shadow only). Optional + nullable: absent /
  // null on legacy snapshots pre-0.10.24. NOT currently rendered by the static
  // site (UI-bridge chip is a separate later task).
  median_trim_delta_count?: number | null;
  // PR-2 post-split share-lag defense (0.10.25-phase8pilot) — Rule-18
  // observability counters for the three stages of the defense:
  //   `post_split_share_lag_count` = tickers where the raw EDGAR share count
  //     was detected as pre-split (lag pattern fires; Tier-1 annotate
  //     `post_split_share_lag` surfaces in `valuation_warnings`, NOT
  //     `risk_flags`, so a corrected ticker stays Top-5-eligible).
  //   `post_split_correction_applied_count` = subset where a corrected count
  //     was successfully substituted (split ratio resolved, correction applied).
  //   `post_split_veto_count` = subset where reconciliation FAILED and the
  //     Tier-2 veto `post_split_share_lag_unreconciled` fired (cautious +
  //     Top-5 suppress). All optional + nullable: absent / null on legacy
  //     snapshots pre-0.10.25.
  post_split_share_lag_count?: number | null;
  post_split_correction_applied_count?: number | null;
  post_split_veto_count?: number | null;
  // PR-1 cross-source share-count corruption shadow observability
  // (0.10.26-phase8pilot, Rule 18 observability-first). All 4 fields are
  // null by default so legacy snapshots (pre-0.10.26) deserialize cleanly.
  // PR-2 will wire the actual veto/correction once the first cron confirms
  // the grades on real data. NOT currently rendered by the static site.
  //
  // Grading is by `compute/scoring/risk_overlay.grade_cross_source_corruption`:
  //   NO_FIRE            : cross_source_delta < 0.50 (normal noise)
  //   CORRECT_CANDIDATE  : delta ≥ 0.50 + near-integer mc_ratio + dual-ratio
  //                        corroboration (share_ratio rounds to SAME integer)
  //   VETO_CANDIDATE     : delta ≥ 0.50 + NOT CORRECT_CANDIDATE (incl. the
  //                        COKE-class ratio_disagreement case)
  //
  // `cross_source_corruption_correct_candidate_count` — universe tickers where
  // the grade is CORRECT_CANDIDATE: the inferred integer ratio is consistent
  // across both mc and share channels (first candidates for PR-2 Tier-1 CORRECT).
  cross_source_corruption_correct_candidate_count?: number | null;
  // `cross_source_corruption_veto_candidate_count` — universe tickers where
  // the grade is VETO_CANDIDATE: delta ≥ 0.50 but ratio is non-integer,
  // uncorroborated (no yf_shares), or ratio_disagreement=True (first candidates
  // for PR-2 Tier-2 VETO, analogous to `post_split_veto_count`).
  cross_source_corruption_veto_candidate_count?: number | null;
  // `cross_source_corruption_ratio_disagreement_count` — subset of VETO_CANDIDATEs
  // where ratio_disagreement=True: mc_ratio and share_ratio are BOTH near-integer
  // but round to DIFFERENT integers. This is the COKE-class detector where
  // yfinance marketCap is stale (mc_ratio ≈ 7 → 7) while sharesOutstanding may
  // reflect a different factor (share_ratio ≈ 10 → 10) or vice versa. Non-zero
  // means the dual-ratio corroboration guard is load-bearing for ≥ 1 ticker.
  cross_source_corruption_ratio_disagreement_count?: number | null;
  // `cross_source_corruption_inferred_ratio_by_ticker` — shadow integer factor
  // per CORRECT_CANDIDATE ticker. Keys = ticker symbols; values = inferred
  // integer ratio (e.g. {"CVNA": 5.0}). Lets the methodology-scientist verify
  // the ratio is plausible and no clean stock spuriously inferred a factor.
  // Informational only — NOT a correction input until PR-2 literature anchor.
  cross_source_corruption_inferred_ratio_by_ticker?: Record<string, number> | null;
};

// Phase 4h.2 Part 1 — per-signal gate decision shape. Mirrors
// `compute/output/schemas.py::OsapGateDiagnostic`. All 4 fields nullable
// so legacy 0.9.0 JSONs deserialize cleanly. `rejection_reason` is one
// of "high_pbo" / "low_dsr" / "insufficient_data" / "gate_failed" for
// rejected signals; null for accepted signals.
export type OsapGateDiagnostic = {
  pbo: number | null;
  dsr: number | null;
  sharpe: number | null;
  rejection_reason: string | null;
};

// Phase 3d Tier-2 event defenses. Surfaces in StockDetail.tier2_events.
// All three boolean flags can be true simultaneously (a single 8-K can
// contain Items 4.01 + 4.02; going-concern is a separate 10-K text scan).
// non_reliance_filing is the only one wired into risk_flags as a hard
// veto; the other two are annotate-only.
export type Tier2Events = {
  going_concern_disclosure: boolean;
  non_reliance_filing: boolean;
  auditor_change: boolean;
  latest_8k_filing_date: string | null;
  latest_8k_filing_url: string | null;
};

export type RawMetrics = {
  revenue: number | null;
  net_income: number | null;
  total_assets: number | null;
  total_liabilities: number | null;
  stockholders_equity: number | null;
  cash: number | null;
  operating_cash_flow: number | null;
  capex: number | null;
  free_cash_flow: number | null;
  eps_basic: number | null;
  eps_diluted: number | null;
  shares_outstanding: number | null;
  // Issue #374 (RATIFY-B) — listed line's own per-class share count;
  // company-total (all classes) lives in `shares_outstanding`. Checksum/
  // display only, no scoring consumer. May be null on warm-cache crons.
  shares_outstanding_listed_class: number | null;
  // PR-2 post-split share-lag defense (0.10.25-phase8pilot) — the raw
  // EDGAR share count BEFORE the post-split correction was applied. Null
  // when no correction was needed, when the defense didn't fire, or on
  // legacy outputs from before this field was added. Rule-9 audit trail:
  // lets downstream consumers verify the magnitude of the correction.
  shares_outstanding_pre_split_raw?: number | null;
  market_cap: number | null;
  pe_ratio_ttm: number | null;
  goodwill: number | null;
};

export type DataQuality = {
  missing_metrics: string[];
  imputed_metrics: string[];
  filing_lag_days: number | null;
  latest_period_end: string | null;
  latest_filed_date: string | null;
};

// Per-method fair-price result (one entry per method in
// FairPriceEnsemble.methods).
//
// Reason taxonomy (subset; see compute/valuation/applicability.py
// SKIP_REASONS for the full list):
// - sector_excluded_financials, sector_excluded_utilities — sector-rule gates
// - non_positive_or_missing_tangible_book, non_positive_eps_3y_avg,
//   non_positive_or_missing_eps_ttm, non_positive_or_missing_bvps,
//   non_positive_or_missing_ebitda — input-precondition gates
// - missing_or_non_positive_peer_pe / pb / ev_ebitda — peer-tier walk fell off
// - value_trap_risk_roe_below_cost_of_equity — RIM short-circuit
// - non_positive_fcf_5y_median, terminal_g_unsafe_g_too_close_to_wacc,
//   dcf_negative_equity_post_debt — DCF-specific gates
// - stale_filing_hard — Defense #3 hard-stale (entire ensemble nulled)
// - data_quality_input_corruption — Defense #7 (Step 7.5) sanity guard.
//   Surfaced when upstream fundamentals ingestion produces clearly
//   broken inputs (e.g., shares_outstanding off by 6+ orders of
//   magnitude, causing a method to compute > $10,000/share). When this
//   fires, all 6 methods are nulled. Tracking issue filed; the Phase-3
//   fundamentals ingest layer needs an audit.
export type FairPriceMethodResult = {
  value: number | null;
  applicable: boolean;
  reason: string | null;
  tier_used: string | null;
};

// Top-level fair_price object on StockDetail. Mirrors
// compute.valuation.ensemble.EnsembleResult.
export type FairPriceEnsemble = {
  methods: {
    graham: FairPriceMethodResult;
    multiples_pe: FairPriceMethodResult;
    multiples_pb: FairPriceMethodResult;
    multiples_ev_ebitda: FairPriceMethodResult;
    rim: FairPriceMethodResult;
    dcf: FairPriceMethodResult;
  };
  median: number | null;
  max: number | null;
  low: number | null;
  high: number | null;
  mos_pct: number | null;
  valuation_warnings: string[];
  // Epic #150 Phase 2.1 (issue #150) — positive-framed count of
  // valuation methods that produced a non-outlier applicable estimate.
  // Inverse of the count of `extreme_*_estimate` warnings emitted.
  // Optional + null on legacy outputs from before 0.9.4-phase4h.4.
  valuation_methods_applicable?: number | null;
  // Issue #177 follow-up (0.10.24-phase8pilot) — trimmed-median result
  // and the list of method keys excluded from it. These are keys of the
  // untyped fair_price dict (not a Pydantic-schema field), so they are
  // NOT in the schema-snapshot triple, but typed here for the UI-bridge
  // chip that will consume them in a later task.
  median_trimmed?: number | null;
  methods_excluded_from_median?: string[];
};

// Sector-median overlay for the per-stock pillar bars (#34).
// Rendered as a vertical notch + header label by PillarRadarChart.
// `values` is keyed by display label ("Quality", "Value", ...) so the
// frontend component can index it directly from its ACTIVE_PILLARS
// loop without case conversion.
export type PillarBaseline = {
  label: string;
  values: Record<string, number | null>;
};

// Per-stock 1-year price history JSON (column-major). Lazy-loaded by
// the detail page chart in Step 10.
export type StockHistory = {
  ticker: string;
  dates: string[];
  opens: (number | null)[];
  highs: (number | null)[];
  lows: (number | null)[];
  closes: (number | null)[];
  volumes: (number | null)[];
};

export type StockDetail = {
  ticker: string;
  name: string;
  sector: string;
  industry: string | null;
  // Listing metadata (0.10.12-phase4.6) — `exchange` = display name mapped
  // from yfinance fast_info.exchange (NASDAQ / NYSE / …); `country` = derived
  // from the exchange ("US" for the S&P 500 universe). Both null when the
  // exchange code didn't resolve. Display-only — feeds the hero listing chips.
  exchange: string | null;
  country: string | null;
  market_cap: number | null;
  current_price: number;
  rank: number;
  composite_score: number;
  pillar_scores: PillarScores;
  raw_metrics: RawMetrics;
  fair_price: FairPriceEnsemble | null;
  top5_factors: unknown[];
  score_history: unknown[];
  data_quality: DataQuality;
  risk_flags: string[];
  valuation_warnings: string[];
  has_history: boolean;
  tangible_book_value: number | null;
  tier2_events: Tier2Events | null;
  pillar_baseline: PillarBaseline | null;
  beneish_m_score: number | null;
  dechow_f_score: number | null;
  recommendation: Recommendation | null;
  loss_chance_pct: number | null;
  price_change_1d_pct: number | null;
  // PR 4.5f manipulation_index — see comment on StockSummary.
  // manipulation_components is the per-flag boolean breakdown the
  // RiskSummaryCard renders (manipulation sub-section) — keys NOT already
  // shown as a rank gate appear under "Also fired — not rank-gating".
  // Keys come from `FLAG_WEIGHTS` in
  // compute/scoring/manipulation_index.py.
  manipulation_index: number | null;
  composite_score_adjusted: number | null;
  manipulation_components: Record<string, boolean> | null;
  // Phase 4h — per-stock OSAP signal map (signalname → cross-sectional
  // rank in [0, 1]) for the accepted-by-PBO/DSR subset of the
  // 100-signal manifest. `osap_blended_score` is the 50/50 blend
  // (composite_score × 0.5 + osap_signal_aggregate × 0.5) — informational
  // observability only; Top-5 ranking still uses raw composite_score
  // per SKILL.md Rule 16. Both null on legacy outputs from before
  // 0.9.0-phase4h.
  osap_signals: Record<string, number> | null;
  osap_blended_score: number | null;
  entered_top5: boolean;
  exited_top5: boolean;
  // Phase 8 pilot PR 3a (0.10.21-phase8pilot) — which index this stock
  // belongs to: "sp500" or "sp400". Mirrors StockSummary.index_membership.
  // Default "sp500" on all legacy / sp500-path outputs; "sp400" for
  // mid-cap members when QR_UNIVERSE=sp900 is active. Annotate-only.
  index_membership: string;
  // Multi-index membership — Dow 30 / NDX 100 overlap tabs (0.10.23-phase8pilot).
  // Mirrors StockSummary.index_memberships. Empty array [] on legacy outputs
  // (pre-0.10.23). `index_membership` (singular) is KEPT UNCHANGED.
  index_memberships: string[];
  // Epic #150 Phase 2.1 (issue #150) — positive-framed count of
  // valuation methods that produced a non-outlier applicable estimate.
  // Mirrors `fair_price.valuation_methods_applicable` at the top
  // level so consumers can filter without unpacking the ensemble dict.
  // Optional + null on legacy outputs from before 0.9.4-phase4h.4.
  valuation_methods_applicable?: number | null;
  // Phase 4.5e PR 2 (0.10.0-phase4.5e) — per-ticker Form-4 fetch
  // diagnostic. Null when form4 fetch loop was skipped. PR 3 consumers
  // keying on insider_count > 0 should prefer this over re-fetching.
  form4_diagnostics?: {
    insider_count: number;
    latest_filing_date: string | null;
    fetch_status: 'ok' | 'failed' | 'skipped_no_identity';
  } | null;
  // Issue #248 PR2a (0.10.3-phase4.5e) — per-ticker cross-source delta
  // (fraction, NOT percent; multiply by 100 for display). Populated for
  // all tickers where the validator could compute a delta (snapshot +
  // price + yfinance all non-null); null otherwise. Populated for tickers
  // BELOW the 5% tolerance threshold too — so post-hoc threshold sweeps
  // are possible without re-running the validator.
  cross_source_delta?: number | null;
};

// ---------------------------------------------------------------------------
// Issue #75 §3 — IC-decay monitor artifact (frontend/public/data/decay_report.json).
// DISPLAY-ONLY transparency surface. This artifact is emitted by a dataclass (NOT
// a Pydantic schema), so it is NOT part of the schema-snapshot triple and is NOT
// guarded by the schema-snapshot CI check. Types here are plain TS interfaces that
// mirror the JSON contract exactly. Do NOT touch Metadata or the snapshot for this.
// ---------------------------------------------------------------------------

// One pillar's rolling IC decay row. `preliminary: true` means ≥ min_history_months
// of out-of-sample IC history have NOT yet accumulated (every numeric field = 0.0
// / 0 in that state — do NOT display those zeros as real metrics).
export type PillarDecay = {
  pillar: string;
  rolling_12m_ic: number;
  rolling_36m_ic: number;
  historical_mean_ic: number;
  decay_ratio: number;
  months_below_threshold: number;
  alert: boolean;
  n_observations: number;
  preliminary: boolean;
};

// Top-level decay monitor report emitted to decay_report.json each cron run.
// `status` drives the three UX states:
//   - "insufficient_history" — ≥ min_history_months of IC data not yet accrued;
//     ALL pillars are preliminary, every numeric is 0 — render pending state.
//   - "monitoring" — baseline established; per-pillar table shows real IC metrics.
//   - "alert" — ≥ 1 pillar in anomalies_alerted; highlight decayed pillars.
export type DecayReport = {
  generated_at: string;
  horizon_months: number;
  threshold: number;
  duration_months: number;
  min_history_months: number;
  status: 'insufficient_history' | 'monitoring' | 'alert';
  n_dates_with_ic: number;
  pillars: PillarDecay[];
  anomalies_alerted: string[];
};

// ---------------------------------------------------------------------------
// Phase 7.0 — point-in-time portfolio backtest (frontend/public/data/portfolio/
// backtest_pit.json). DISPLAY-ONLY: the artifact self-carries its own `meta`
// block (no Pydantic model), so these types are NOT part of the schema-snapshot
// triple — they describe a standalone workflow_dispatch artifact, not a
// schemas.py model. Consumed only by the AI-pick home page.
// ---------------------------------------------------------------------------

// OOS-validation block — Bailey-López de Prado 2014 Deflated Sharpe Ratio +
// optional PBO + optional holdout test. All top-level fields are optional/nullable
// so the badge degrades gracefully when absent (no validation block on current
// artifact; the badge returns null). Lands on meta.validation after the next
// backfill rerun.
export type BacktestWalkForwardStability = {
  k0: number | null;
  k_max: number | null;
  sharpe_min: number | null;
  sharpe_max: number | null;
  sharpe_mean: number | null;
  sharpe_dispersion: number | null;
  in_sample: true;
  label: string | null;
};

export type BacktestPboResult = {
  pbo: number;
  n_partitions: number;
  n_configs: number;
  n_observations: number;
  passes: boolean;
  config_correlation_note: string;
};

export type BacktestHoldoutResult = {
  train_legs: number[];
  test_legs: number[];
  purged_leg: number;
  embargo_quarters: number;
  embargo_leg_indices: number[];
  train_winner_config: string;
  // null when the test window is degenerate (e.g. all-None legs); the badge's
  // HoldoutChip renders "—" via the null-safe fmt helpers in that case.
  test_return: number | null;
  test_sharpe: number | null;
  benchmark_test_return: number | null;
  falsified: boolean;
  in_sample: false;
  caveat: string;
};

export type BacktestValidationGrid = {
  configs: string[];
  freq: 'monthly';
  dates: string[];
  net: Record<string, number[]>;
};

// The full validation block shape. ALL fields are optional/nullable so a
// partially-generated artifact degrades gracefully to the "validation pending"
// state (renders null chip). phi_passes = Φ(DSR) >= 0.95 gate.
export type BacktestValidation = {
  dsr?: number | null;
  dsr_confidence_phi?: number | null;
  n_trials?: number | null;
  annualization_basis?: string | null;
  annualized_sharpe?: number | null;
  n_observations?: number | null;
  dsr_passes?: boolean | null;
  phi_passes?: boolean | null;
  walk_forward_sharpe_stability?: BacktestWalkForwardStability | null;
  selection_footprint_note?: string | null;
  grid?: BacktestValidationGrid | null;
  pbo?: BacktestPboResult | null;
  holdout?: BacktestHoldoutResult | null;
};

export type BacktestHolding = {
  ticker: string;
  composite_score: number;
  sector: string;
  sigma_90d: number | null;
};

export type BacktestRebalance = {
  date: string;
  members_complete: boolean;
  holdings: BacktestHolding[];
  // { "1": { TICKER: weight, ... }, ..., "10": {...} } — inverse-vol weights
  // for each selectable basket size N. Weights within a count sum to ~1.
  weights_by_count: Record<string, Record<string, number>>;
  // Phase 7.0 ADAPTIVE — the number of holdings selected by the adaptive rule
  // (composite >= 65, floor 5, cap 20) at this rebalance. The adaptive book is
  // the PREFIX holdings[:adaptive_count] with weights_by_count[String(adaptive_count)].
  // Present only when the artifact was generated with the adaptive rule.
  adaptive_count?: number;
  // V55 hysteresis hold-band (hold_band_min present in adaptive_rule) — the
  // ACTUAL book after the band is applied. NOT a prefix of `holdings`; includes
  // both new entries (composite >= composite_min) and carried names (composite
  // >= hold_band_min). band_weights is a per-ticker weight map (same inv-vol
  // contract as weights_by_count but keyed on the banded book, not a count).
  // band_held_count = len(band_book); band_carry_count = names kept by the band
  // below composite_min; band_carry_weight_share = fraction of total weight
  // carried from the prior basket. All absent on pre-band artifacts.
  band_book?: string[];
  band_weights?: Record<string, number>;
  band_held_count?: number;
  band_carry_count?: number;
  // Engine writes explicit JSON null on degenerate legs (empty band_book) —
  // typed as `number | null` so the TS consumer doesn't widen to `number`
  // and get a false-positive on a null leg.
  band_carry_weight_share?: number | null;
  // V55 band carry names — names kept by the hysteresis filter that are
  // below composite_min. Exported by the engine alongside band_book so the
  // frontend can label them as "carried" without inferring from score alone.
  // Absent on pre-band artifacts and on legs with no carry names.
  band_carry_names?: string[];
};

export type BacktestNavCountSeries = {
  gross: (number | null)[];
  net: (number | null)[];
  net_conservative: (number | null)[];
  turnover_by_rebalance: number[];
};

export type BacktestNav = {
  // Shared trading-day axis (ISO YYYY-MM-DD) from the first rebalance onward.
  dates: string[];
  // Rebased-to-100 index NAVs aligned to `dates`; null before a series starts.
  benchmark: Record<'spy' | 'qqq' | 'dia' | 'iwm', (number | null)[]>;
  // Daily NAV per holding count N=1..max_holdings, all on `dates`.
  by_count: Record<string, BacktestNavCountSeries>;
  default_count: number;
  // Phase 7.0 ADAPTIVE book — composite >= 65, floor 5, cap 20. Present only
  // when the artifact was generated with the adaptive rule (parallel compute
  // change). The series shape matches any by_count entry.
  adaptive?: BacktestNavCountSeries;
};

// Phase 7.0 ADAPTIVE — the threshold rule that sizes the basket each rebalance.
// Present only when the artifact was generated with the adaptive rule.
export type AdaptiveRule = {
  composite_min: number;
  min_picks: number;
  // null on NEW artifacts (cap removed — AI sizes freely above the floor).
  // number on legacy artifacts that carried an explicit max (e.g. 20).
  // Key is always present; never absent.
  max_picks: number | null;
  // V55 hold-band minimum — composite threshold below which a name exits the
  // basket. When present the basket is the band_book (not a prefix of holdings).
  // Absent on pre-band artifacts.
  hold_band_min?: number;
};

export type BacktestMeta = {
  generated_utc: string;
  rule_version: string;
  as_of_start: string;
  as_of_end: string;
  rebalance_count: number;
  max_holdings: number;
  default_count: number;
  default_benchmark: string;
  cost_bps_per_side: number;
  cost_bps_conservative: number;
  incomplete_membership_count: number;
  restatement_contamination_pct: number | null;
  restatement_canary_source: string;
  restatement_canary_unresolved_count: number;
  sector_from_today: boolean;
  veto_layer_replayed: boolean;
  // PR #451 — when veto_layer_replayed=true, lists the vetoes that
  // could NOT be replayed point-in-time (names only; full reason in
  // the artifact). Absent / null on old artifacts (veto_layer_replayed=false).
  vetoes_not_replayed?: { name: string; reason?: string }[] | null;
  // Phase 7.0 ADAPTIVE — present when the artifact was generated with the
  // adaptive basket-sizing rule.
  adaptive_rule?: AdaptiveRule | null;
  // OOS-validation block (Bailey-López de Prado 2014 DSR + optional PBO +
  // optional holdout). Absent on the current artifact; lands after the next
  // backfill rerun. The BacktestValidationBadge degrades gracefully to null
  // when this field is absent or null.
  validation?: BacktestValidation | null;
  // New meta counters (optional; absent on pre-validation artifacts).
  // Scoring-universe candidate accounting — how many tickers were removed
  // from the scoring universe this run (removed_candidates), how many of
  // those had been successfully fetched (removed_fetched), and how many
  // had no data available at the point-in-time membership date
  // (removed_unavailable). Observability-only; not rendered by the site.
  scoring_universe_removed_candidates_count?: number | null;
  scoring_universe_removed_fetched_count?: number | null;
  scoring_universe_removed_unavailable_count?: number | null;
  // Item 402 (executive-compensation proxy) PIT rows fetched and veto
  // fired count. Observability-only.
  item402_pit_rows?: number | null;
  item402_veto_fired_count?: number | null;
  // Historical sector coverage — % of universe where the historical sector
  // was known at the point-in-time date, and how many fell back to today's
  // sector assignment. Observability-only.
  historical_sector_coverage_pct?: number | null;
  historical_sector_fallback_count?: number | null;
  // Restatement canary: true when the period map was gated (all legs that
  // contained a restatement-canary ticker were excluded). Absent/null when
  // the canary gate was not active.
  restatement_canary_period_map_gated?: boolean | null;
  // Ticker rename micro-leakage note — free-text caveat from the engine
  // when a rename event is detected that may have caused a minor PIT leak.
  ticker_rename_microleakage_note?: string | null;
  disclaimer: string;
};

export type BacktestPIT = {
  meta: BacktestMeta;
  rebalances: BacktestRebalance[];
  nav: BacktestNav;
};

// Trimmed + rounded view model the SERVER page derives from BacktestPIT and
// passes to the client AI-pick component — so the 1.3 MB raw artifact (full
// unrounded NAV floats + all 20 rebalances) never ships in the page payload.
// Only the net line per count + the benchmark lines + per-count final values +
// the latest rebalance's holdings are needed client-side.
export type AiPickFinals = {
  gross: number | null;
  net: number | null;
  conservative: number | null;
};

// One quarterly rebalance trimmed to just the rotation view: ticker + sector,
// holdings ordered by composite desc (so the client slices [0, count) to mirror
// `select_picks(count)` and diffs consecutive entries for the entered / exited
// markers). Weights are intentionally NOT carried here — the per-quarter weight
// table would be noise; the live "Current picks" card owns weights. Keeping this
// to two strings per holding is what lets all 20 rebalances ship in the page
// payload without re-bloating it toward the 1.3 MB raw artifact.
export type AiPickTimelineHolding = {
  ticker: string;
  sector: string;
};

export type AiPickTimelineEntry = {
  date: string;
  holdings: AiPickTimelineHolding[];
  // Per-rebalance adaptive basket count — present when the artifact was generated
  // with the adaptive rule (rebalances[*].adaptive_count). Absent/undefined on
  // legacy slider-mode artifacts. When present, HoldingsTimeline slices this
  // entry to adaptiveCount rather than the fixed `count` prop.
  adaptiveCount?: number;
  // V55 hold-band — per-rebalance band_held_count (may differ from adaptiveCount
  // when carry names are present). When present, HoldingsTimeline shows this as
  // the displayed count rather than adaptiveCount. Absent on pre-band artifacts.
  bandHeldCount?: number;
  // V55 hold-band — the EXACT band book for this rebalance (band_book from the
  // raw artifact). When present, HoldingsTimeline renders THIS set as the held
  // membership instead of slicing `holdings` by count (the band book is NOT a
  // prefix). Sectors looked up from `holdings`. Absent on pre-band artifacts.
  bandBook?: string[];
  // V55 carry names — names in the band book that were kept below composite_min.
  // Carried when present so HoldingsTimeline can tag the correct tickers without
  // re-inferring from scores. Absent on pre-band artifacts and on legs with no
  // carry names.
  bandCarryNames?: string[];
};

// Adaptive-mode view model — present when the artifact carries nav.adaptive.
// null when the artifact predates the adaptive rule contract (current artifact).
export type AiPickAdaptive = {
  // The threshold rule that sized the basket each rebalance.
  rule: AdaptiveRule;
  // Rounded net NAV series for the adaptive book, aligned to `dates`.
  net: (number | null)[];
  // Rounded gross NAV series for the adaptive book.
  gross: (number | null)[];
  // Rounded conservative-cost NAV series for the adaptive book.
  conservative: (number | null)[];
  // Final (last-finite) gross/net/conservative for the adaptive book.
  finals: AiPickFinals;
  // Number of picks at the latest rebalance (from rebalances[-1].adaptive_count).
  latestCount: number;
  // Latest-rebalance adaptive holdings: the prefix holdings[:latestCount],
  // sorted by weight descending (same order as the "Current picks" card for
  // fixed-count books), each with ticker + sector + composite_score + weight.
  // weight is null when the inverse-vol weight was unavailable for a name
  // (sigma_90d missing); rendered as "—" (em-dash) in the UI.
  // STATE 2 (adaptive-but-pre-band): this is the actual book.
  // STATE 1 (band): see latestBandHoldings — this field is still populated
  // (from holdings prefix) but the component renders latestBandHoldings instead.
  latestHoldings: Array<{
    ticker: string;
    sector: string;
    composite_score: number;
    weight: number | null;
  }>;
  // V55 hold-band fields — only present in STATE 1 (band artifact).
  // Absent in STATE 2 (pre-band adaptive) and STATE 3 (legacy slider).
  //
  // hold_band_min: the hold threshold from meta.adaptive_rule.hold_band_min.
  // latestBandHoldings: the band_book-ordered list with band_weights; `carried`
  //   is true when composite < composite_min (held by the band only).
  holdBandMin?: number;
  latestBandHoldings?: Array<{
    ticker: string;
    sector: string;
    composite_score: number;
    weight: number | null;
    carried: boolean;
  }>;
};

export type AiPickData = {
  meta: BacktestMeta;
  dates: string[];
  // net NAV per holding count N (rounded), aligned to `dates`.
  netByCount: Record<string, (number | null)[]>;
  // gross NAV per count (no cost deducted), aligned to `dates`.
  grossByCount: Record<string, (number | null)[]>;
  // conservative-cost NAV per count (25bps/side), aligned to `dates`.
  conservativeByCount: Record<string, (number | null)[]>;
  // rebased benchmark NAVs per symbol (rounded), aligned to `dates`.
  benchmark: Record<string, (number | null)[]>;
  // final (last-finite) gross/net/conservative per count, for the summary.
  finalsByCount: Record<string, AiPickFinals>;
  // the most-recent rebalance's ranked holdings + per-count weights.
  latest: {
    date: string;
    holdings: BacktestHolding[];
    weightsByCount: Record<string, Record<string, number>>;
  } | null;
  // every quarterly rebalance (oldest → newest), trimmed to ticker + sector, for
  // the rotation-history timeline. The client slices each entry to [0, count) so
  // the timeline tracks the count slider, then diffs neighbours for entered /
  // exited markers.
  timeline: AiPickTimelineEntry[];
  // Adjusted close at each rebalance date (index-aligned with `timeline`) for
  // each CURRENTLY-held ticker, plus the latest close per ticker — lets the
  // client show P/L since a holding's entry rebalance (streak start depends on
  // the count slider) without shipping full per-ticker price series. null where
  // the price-history file doesn't reach back that far.
  entryCloses: Record<string, (number | null)[]>;
  lastCloses: Record<string, number | null>;
  // Forwarded from BacktestMeta for caption branching — avoids passing the
  // full meta object into every sub-component (AnnualReturnsTable /
  // AiPickPortfolio captions only need these two fields).
  vetoLayerReplayed: boolean;
  // Names of vetoes excluded from the replay (only meaningful when
  // vetoLayerReplayed=true; undefined on old artifacts).
  vetoesNotReplayed: { name: string }[] | undefined;
  // Phase 7.0 ADAPTIVE — non-null when the artifact carries nav.adaptive.
  // null when the artifact predates the adaptive rule contract (backward-compat
  // fallback: render the slider UI exactly as today).
  adaptive: AiPickAdaptive | null;
};
