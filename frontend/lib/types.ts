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
