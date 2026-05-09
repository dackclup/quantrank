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
  entered_top5: boolean;
  exited_top5: boolean;
};
