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
  // ManipulationRiskCard renders as a sorted-by-weight component grid.
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
