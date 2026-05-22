"""Pydantic models for JSON output. Mirrors ``frontend/lib/types.ts`` exactly."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Recommendation = Literal["bullish", "lean_bullish", "neutral", "cautious"]
"""4-tier recommendation per PR 4d (Option B locked 2026-05-14 — neutral
terminology, no FINRA/SEC-regulated sell-side labels). Derived
deterministically from composite + risk_flags + valuation_warnings +
fair_price MoS by `compute.scoring.recommendation.derive_recommendation`.
None on legacy data pre-PR-4d.
"""


class PillarScores(BaseModel):
    """Per-pillar 0-100 scores. Phase 3 introduces ``technical`` and
    ``profitability`` (additive — defaults to None for older data)."""

    model_config = ConfigDict(extra="forbid")

    quality: float | None = None
    value: float | None = None
    growth: float | None = None
    momentum: float | None = None
    health: float | None = None
    profitability: float | None = None
    technical: float | None = None
    risk: float | None = None
    sentiment: float | None = None
    ml: float | None = None


class PillarBaseline(BaseModel):
    """Sector-median overlay for the per-stock pillar bars (#34).

    Rendered as a vertical notch on each pillar bar + a header label
    (``"Information Technology median (n=72)"``) on the stock-detail
    page. The component (``frontend/components/PillarRadarChart.tsx``)
    keys ``values`` by the **display label** (``Quality``, ``Value``,
    ...), not the snake_case PillarScores field name, so the compute
    layer converts during aggregation.

    Sectors with fewer than ``PILLAR_BASELINE_MIN_PEERS`` (10) skip
    the overlay entirely — too few peers for a meaningful median.
    """

    model_config = ConfigDict(extra="forbid")

    label: str
    values: dict[str, float | None]


class StockSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rank: int
    ticker: str
    name: str
    sector: str
    composite_score: float
    current_price: float
    fair_price: float | None = None
    max_fair_price: float | None = None
    margin_of_safety_pct: float | None = None
    pillar_scores: PillarScores = Field(default_factory=PillarScores)
    risk_flags: list[str] = Field(default_factory=list)
    valuation_warnings: list[str] = Field(default_factory=list)
    recommendation: Recommendation | None = None
    loss_chance_pct: float | None = None
    price_change_1d_pct: float | None = None
    manipulation_index: float | None = None
    composite_score_adjusted: float | None = None
    entered_top5: bool = False
    exited_top5: bool = False


class OsapGateDiagnostic(BaseModel):
    """Per-signal PBO/DSR gate decision surfaced into
    ``Metadata.osap_gate_diagnostics``. Phase 4h.2 Part 1 observability
    addition (issue #116) — lets future debugging answer "why did this
    signal reject?" without a local re-run of the PBO/DSR cohort.

    All 4 fields default to ``None`` so legacy 0.9.0 JSONs without this
    field deserialize cleanly. ``rejection_reason`` taxonomy mirrors
    ``compute/validation/osap_validation.py::GateResult.rejection_reason``:
    one of ``"high_pbo"`` / ``"low_dsr"`` / ``"insufficient_data"`` /
    ``"gate_failed"`` for rejected signals; ``None`` for accepted
    signals.
    """

    model_config = ConfigDict(extra="forbid")

    pbo: float | None = None
    dsr: float | None = None
    sharpe: float | None = None
    rejection_reason: str | None = None


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    last_update_utc: str
    next_update_utc: str
    universe: str
    universe_size: int
    compute_run_id: str
    git_commit: str
    mos_trailing_ic_smoke: float | None = None
    tier2_coverage_pct: float | None = None
    fundamentals_coverage_pct: float | None = None
    fundamentals_latency_p50_seconds: float | None = None
    fundamentals_latency_p95_seconds: float | None = None
    osap_signals_used: list[str] | None = None
    osap_excluded_signals: list[str] | None = None
    osap_signals_ic_12m: dict[str, float] | None = None
    osap_signals_coverage_pct: dict[str, float] | None = None
    # Phase 4h.2 Part 1 — observability for the manifest-vs-dataset gap
    # and per-signal gate decisions surfaced by issue #116.
    # ``osap_signals_missing_from_dataset`` lists ``OSAP_SIGNALS_100``
    # entries that the OSAP fetch returned no rows for (silent drop in
    # 0.9.0-phase4h; visible here). ``osap_gate_diagnostics`` carries
    # the per-signal PBO/DSR/Sharpe/rejection_reason for every signal
    # that reached the gate.
    osap_signals_missing_from_dataset: list[str] | None = None
    osap_gate_diagnostics: dict[str, OsapGateDiagnostic] | None = None
    # Phase 4h.2 Part 2 — signals present in the OSAP dataset but with
    # fewer than 2 distinct port buckets (no long-short pair possible).
    # Closes the 100-signal accounting equation:
    #   len(OSAP_SIGNALS_100) == missing_from_dataset + dropped_no_long_short
    #                         + signals_used + excluded_signals
    # Pre-Part-2 (0.9.1-phase4h.2): the ~56 signals dropped silently at
    # the hardcoded port=01/10 filter. Surfaced here so the gap is
    # auditable. ``None`` when no signals were dropped on this dimension.
    osap_signals_dropped_no_long_short: list[str] | None = None
    # Epic #150 Phase 1.6 (issue #155) — explicit compute-time state of
    # the Tier-2 8-K defenses (`compute/scoring/tier2._EIGHT_K_DEFENSES_ENABLED`).
    # Lets `verify-production-output/helper.py` Section B branch on the
    # actual flag instead of inferring from `tier2_coverage_pct > 5%`,
    # so a future emergency-disable PR doesn't silently mask itself.
    # Defaults to ``True`` for back-compat with snapshots written before
    # 0.9.3-phase4h.3 (the field is required at the wire level but the
    # helper falls back to coverage-based inference when the key is
    # absent from a legacy `metadata.json`).
    tier2_enabled: bool = True
    # Phase 4b (0.9.5-phase4h.5) — observability surface for the new
    # Roychowdhury 2006 size-invariant loss-avoidance annotate
    # `loss_avoidance_pattern_size_invariant`. Count of tickers where
    # NI/TotalAssets ∈ [0, 0.005] for 3+ consecutive fiscal years on
    # this cron run. Nullable on legacy snapshots (pre-0.9.5); Rule 18
    # observability-before-wiring requires the diagnostic ship in the
    # same PR as the flag emission so the first cron's firing rate is
    # visible without grepping per-stock JSONs.
    loss_avoidance_size_invariant_firing_count: int | None = None
    # Issue #176 (0.9.6-phase4h.6) — observability surface for the new
    # `share_count_extraction_missing` annotate. Count of tickers where
    # ``shares_outstanding is None`` despite revenue + total_assets
    # being populated (STZ-style partial XBRL extraction). Nullable on
    # legacy snapshots (pre-0.9.6); Rule 18 observability-before-wiring
    # requires the diagnostic ship in the same PR as the flag emission
    # so the first cron's firing rate is visible at-a-glance.
    share_count_extraction_missing_count: int | None = None
    # Issue #177 (0.9.7-phase4h.7) — observability surface for the new
    # `extreme_estimate_majority` annotate. Count of tickers where
    # ≥ ``config.EXTREME_MAJORITY_THRESHOLD`` of the 6 fair-price
    # methods fired Defense #4 (``extreme_*_estimate``) on this cron —
    # i.e., the cohort whose ensemble median is past its Huber 1981
    # §1.4 breakdown point. Nullable on legacy snapshots (pre-0.9.7);
    # Rule 18 observability-before-wiring requires the diagnostic ship
    # in the same PR as the flag emission so the first cron's firing
    # rate is visible at-a-glance (gates the follow-up median-exclusion
    # PR per methodology-scientist Mode B, 2026-05-21).
    extreme_estimate_majority_count: int | None = None
    # Issue #67 (0.9.8-phase4h.8) — sector-adjusted cost of equity
    # (Damodaran 2019 *Investment Valuation* 3rd ed. Table 8.4 +
    # Damodaran NYU online betas dataset, January 2025 update).
    # Rule 18 observability surface: both counts are computed on
    # EVERY cron regardless of ``config.USE_SECTOR_COE`` (default
    # False) so the delta is visible before the flag is flipped.
    # ``sector_coe_enabled`` mirrors the config-flag state at write
    # time so the verify-helper and post-cron audit can branch on the
    # actual flag without reading source code.
    # ``value_trap_risk_count_without_sector_coe`` = tickers where
    # RIM skips on ROE ≤ flat 0.10 threshold (baseline; always
    # computed). ``value_trap_risk_count_with_sector_coe`` = same
    # count under per-sector Ke from SECTOR_COST_OF_EQUITY dict; the
    # delta is the expected reduction in false positives once
    # USE_SECTOR_COE is flipped to True.  Both nullable on legacy
    # snapshots (pre-0.9.8).
    sector_coe_enabled: bool = False
    value_trap_risk_count_with_sector_coe: int | None = None
    value_trap_risk_count_without_sector_coe: int | None = None
    # Phase 4.5e PR 2 (0.10.0-phase4.5e) — observability surface for the
    # Form-4 insider-transaction fetch loop wired in this PR.
    # ``form4_enabled`` mirrors ``_FORM4_FLAGS_ENABLED`` in
    # ``compute/scoring/tier2.py`` — False in this PR (annotate flags
    # land in PR 3). ``form4_coverage_pct`` = % of universe with a
    # successful fetch (None = no fetch attempted). The p50/p95 latency
    # fields let the cron latency budget be verified against the
    # ``FORM4_LOOKBACK_DAYS=365`` 7-day-cache window. Nullable on legacy
    # snapshots (pre-0.10.0); Rule 18 observability-before-wiring
    # requires the diagnostic ship ≥ 1 cron before PR 3 wires scoring.
    # ``form4_fetch_failures`` is bounded to max 20 tickers to keep the
    # metadata.json size stable even on a mass-fail cache-cold run.
    form4_enabled: bool = False
    form4_coverage_pct: float | None = None
    form4_fetch_latency_p50_seconds: float | None = None
    form4_fetch_latency_p95_seconds: float | None = None
    form4_universe_insider_count_median: int | None = None
    form4_tickers_with_recent_activity: int | None = None
    form4_fetch_failures: list[str] | None = None  # bounded ≤ 20 tickers


class RawMetrics(BaseModel):
    """Latest fundamentals — TTM for flow items, point-in-time for balance items."""

    model_config = ConfigDict(extra="forbid")

    revenue: float | None = None
    net_income: float | None = None
    total_assets: float | None = None
    total_liabilities: float | None = None
    stockholders_equity: float | None = None
    cash: float | None = None
    operating_cash_flow: float | None = None
    capex: float | None = None
    free_cash_flow: float | None = None
    eps_basic: float | None = None
    eps_diluted: float | None = None
    shares_outstanding: float | None = None
    market_cap: float | None = None
    pe_ratio_ttm: float | None = None
    goodwill: float | None = None


class DataQuality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    missing_metrics: list[str] = Field(default_factory=list)
    imputed_metrics: list[str] = Field(default_factory=list)
    filing_lag_days: int | None = None
    latest_period_end: str | None = None
    latest_filed_date: str | None = None


class StockDetail(BaseModel):
    """Full per-stock JSON written to ``frontend/public/data/stocks/{TICKER}.json``."""

    model_config = ConfigDict(extra="forbid")

    ticker: str
    name: str
    sector: str
    industry: str | None = None
    market_cap: float | None = None
    current_price: float
    rank: int
    composite_score: float
    pillar_scores: PillarScores = Field(default_factory=PillarScores)
    raw_metrics: RawMetrics = Field(default_factory=RawMetrics)
    fair_price: dict | None = None
    top5_factors: list = Field(default_factory=list)
    score_history: list = Field(default_factory=list)
    data_quality: DataQuality = Field(default_factory=DataQuality)
    risk_flags: list[str] = Field(default_factory=list)
    valuation_warnings: list[str] = Field(default_factory=list)
    has_history: bool = False
    tangible_book_value: float | None = None
    tier2_events: dict | None = None
    pillar_baseline: PillarBaseline | None = None
    beneish_m_score: float | None = None
    dechow_f_score: float | None = None
    recommendation: Recommendation | None = None
    loss_chance_pct: float | None = None
    price_change_1d_pct: float | None = None
    manipulation_index: float | None = None
    composite_score_adjusted: float | None = None
    manipulation_components: dict[str, bool] | None = None
    osap_signals: dict[str, float] | None = None
    osap_blended_score: float | None = None
    entered_top5: bool = False
    exited_top5: bool = False
    # Epic #150 Phase 2.1 (issue #150) — positive-framed count of
    # valuation methods that produced a non-outlier applicable estimate
    # for this ticker. Inverse of the count of ``extreme_*_estimate``
    # warnings emitted; surfaces the method-applicability signal at the
    # schema-snapshot level so it's separable from manipulation
    # warnings in downstream filtering / audits. Mirrors the
    # ``fair_price.valuation_methods_applicable`` nested field. Range
    # ``[0, 6]`` once populated; ``None`` on legacy outputs from before
    # 0.9.4-phase4h.4.
    valuation_methods_applicable: int | None = None
    # Phase 4.5e PR 2 (0.10.0-phase4.5e) — per-ticker Form-4 fetch
    # diagnostic. Keys: ``insider_count`` (distinct CIKs with ≥ 1
    # transaction in the ``FORM4_LOOKBACK_DAYS`` window),
    # ``latest_filing_date`` (ISO date string or None when no activity),
    # ``fetch_status`` ("ok" | "failed" | "skipped_no_identity").
    # Null when the outer form4 fetch loop was skipped (e.g., cold
    # cache + form4_enabled=False branch). PR 3 consumers keying on
    # ``insider_count > 0`` should prefer this over re-fetching.
    form4_diagnostics: dict | None = None
