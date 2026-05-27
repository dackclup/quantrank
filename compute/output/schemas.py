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
    # Phase 4.5e PR 3 (0.10.1-phase4.5e) — Rule 18 observability surface
    # for the new Form-4 insider-cluster annotates emitted from
    # ``compute/scoring/form4_signals.py``. ``insider_sell_cluster_firing_count``
    # counts tickers where ≥ 3 distinct insiders sold $1M+ in opportunistic
    # transactions (codes S, D — per Cohen-Malloy-Pomorski 2012 §III.A) in
    # a rolling 30-day window. ``c_suite_unusual_sell_firing_count`` counts
    # the narrower CEO + CFO co-sell subset (Jeng-Metrick-Zeckhauser 2003
    # §V — strict subset of the cluster flag). Both nullable on legacy
    # snapshots (pre-0.10.1). The next cron's universe-wide firing rate
    # is the gate for the methodology-scientist Q3 2026-08-19 cohort-
    # acceptance check that may promote ``INSIDER_SELL_CLUSTER_WEIGHT``
    # from 5.0 → 10.0; expected base rate is ~2-5% per CMP 2012 quarterly
    # cohort, possibly lower after the 30d window tightening per
    # Jagolinzer 2009 §3.2 signal-decay curve.
    insider_sell_cluster_firing_count: int | None = None
    c_suite_unusual_sell_firing_count: int | None = None
    # Phase 4.5e PR 4-eq (0.10.2-phase4.5e) — Rule 18 observability surface
    # for the 10b5-1 contamination filter applied in
    # ``compute/scoring/form4_signals._is_opportunistic_sell``. Counts
    # the universe-wide total of Form-4 transactions that WOULD have been
    # classified as opportunistic (code ∈ {S, D}) absent the filter but
    # were dropped because ``is_rule_10b5_one is True`` (resolved from
    # footnote-text scan per ``form4_insider._detect_10b5_1_on_transaction``;
    # edgartools 5.31.5 does not parse the SEC structured <aff10b5One>
    # element added in the 2023-04-01 mandate). Counted within the
    # ``INSIDER_SELL_CLUSTER_LOOKBACK_DAYS`` (30) window per ticker so
    # the metric directly tracks contamination eliminated from the
    # cluster-detection input, not 10b5-1 trades in general. Gates the
    # Q3 2026-08-19 cohort-acceptance check (issue #130) for the
    # ``INSIDER_SELL_CLUSTER_WEIGHT`` 5.0 → 7.0 promotion (separate
    # follow-up PR per methodology-scientist Mode B 2026-05-23).
    # Nullable on legacy snapshots (pre-0.10.2).
    form4_rule10b5_one_excluded_count: int | None = None
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
    # Issue #248 PR2a (0.10.3-phase4.5e) — Rule 18 observability surface for
    # the cross-source market-cap validator (compute/ingest/cross_source.py).
    # Per the methodology-scientist Mode B verdict 2026-05-25, the existing
    # `cross_source_disagreement` annotate has shipped without a universe-
    # wide counter since Phase 4b §1 — a Rule 18 violation. This PR closes
    # the gap.
    #
    # ``cross_source_disagreement_count`` = # tickers where SEC-derived
    # mcap (shares × price) diverged > CROSS_SOURCE_MARKET_CAP_TOLERANCE
    # (5%) from yfinance .info marketCap. Direct counter for the existing
    # per-ticker `valuation_warnings: ["cross_source_disagreement"]` flag.
    # Pre-fix universe baseline (Sat 9015748): 22/502 = 4.4% (within
    # expected 3-8% band per quarterly-cohort-audit/SKILL.md).
    #
    # ``cross_source_delta_histogram`` = universe-wide distribution of the
    # delta (|sec_mc − yf_mc| / sec_mc) across 9 buckets:
    #   - "<5"          delta < 5% (no fire; would fire if tolerance lowered)
    #   - "5-25"        annotate-only band
    #   - "25-50"       annotate-only band
    #   - "50-75"       annotate-only band
    #   - "75-100"      candidate severe threshold floor (methodology Q1)
    #   - "100-150"     methodology Mode B proposed severe threshold (100%)
    #   - "150-200"     above proposed severe — clear data corruption
    #   - ">200"        extreme corruption (V at 276%)
    #   - "unavailable" yfinance fetch returned None (no validation possible)
    # Gates the PR2b severe-threshold decision (75% vs 100% vs 150%) with
    # empirical 1-cron data instead of gut-feel calibration. Buckets are
    # half-open intervals `[lower, upper)` (exact-floor = next bucket).
    cross_source_disagreement_count: int | None = None
    cross_source_delta_histogram: dict[str, int] | None = None
    # Issue #246 PR1 retrofit (0.10.3-phase4.5e) — Rule 18 observability for
    # the `_fetch_shares_from_per_filing_xbrl` fallback trigger extended in
    # PR #253. ``shares_fallback_triggered_count`` = total tickers where the
    # fallback fired (union of None-primary + too-low-primary cases).
    # ``shares_fallback_too_low_count`` = subset where the trigger fired
    # because primary returned `< MIN_PLAUSIBLE_SHARE_COUNT (100K)` — the
    # new ERIE-class path added by PR #253. Separation lets the audit chain
    # track ERIE-pattern growth distinct from the original STZ pattern.
    # Nullable on legacy snapshots (pre-0.10.3).
    shares_fallback_triggered_count: int | None = None
    shares_fallback_too_low_count: int | None = None
    # Issue #248 PR2b (0.10.4-phase4.5e) — Rule 18 observability for the
    # multi-class dimensional override path added in fundamentals.py. Counts
    # the universe-wide total of tickers where the primary `companyfacts`
    # ``shares_outstanding`` value was overridden by a per-filing XBRL
    # dimensional sum (the V / NWS / NWSA / FOX / FOXA / BRK-B / STZ
    # allowlist gate fired AND the summed value exceeded primary). Disjoint
    # from `shares_fallback_triggered_count` — that counter covers the
    # None / too-low trigger paths; this counter covers the allowlist
    # plausible-primary path. Expected steady-state firing rate: 6-7
    # (the allowlist size; STZ may not fire here because its primary path
    # returns None and the None-trigger path captures it first).
    shares_fallback_dimensional_override_count: int | None = None
    # Issue #261 (0.10.5-phase4.5e) — Rule 18 observability for the
    # ``multi_class_aggregate_shares_suspected`` annotate. Counts the
    # universe-wide total of tickers where the per-ticker emit fired —
    # the CIK-collision signature of a multi-class issuer reporting the
    # AGGREGATE share count on each per-class ticker (the GOOG/GOOGL
    # overcount pattern, opposite direction to PR #257's allowlist which
    # corrects companyfacts-undercount via per-filing XBRL dimensional
    # sum). Expected steady-state firing rate: 6 (GOOG, GOOGL, NWS,
    # NWSA, FOX, FOXA per 2026-05-23 cron #3 cohort). Nullable on
    # legacy snapshots (pre-0.10.5). Gates the Q3 2026-08-19 quarterly-
    # audit cohort acceptance check for the threshold recalibration
    # (10% × universe median market_cap) per methodology-scientist
    # Mode B 2026-05-26 verdict.
    multi_class_aggregate_shares_suspected_count: int | None = None
    # Issue #261 PR-B (0.10.6-phase4.5e) — Rule 18 observability for the
    # structural per-class XBRL extraction path. Counts tickers where
    # the primary `companyfacts` aggregate ``shares_outstanding`` was
    # OVERRIDDEN by a per-filing XBRL filter against the
    # ``MULTI_CLASS_OVERCOUNT_ALLOWLIST`` (GOOG → goog:CapitalClassCMember,
    # GOOGL → us-gaap:CommonClassAMember). Disjoint from
    # ``shares_fallback_dimensional_override_count`` — that counter
    # covers the UNDERCOUNT path (PR #257 sums all dimensional contexts
    # for V/NWS/NWSA/FOX/FOXA/BRK-B/STZ); this counter covers the
    # OVERCOUNT path (filters one specific class member for GOOG/GOOGL).
    # Expected steady-state firing rate: 2 (GOOG + GOOGL).
    multi_class_per_class_override_count: int | None = None
    # Issue #261 PR-B (0.10.6-phase4.5e) — Defensive Rule-18 sanity
    # check on the per-class override path. Fires when the extracted
    # per-class share count falls OUTSIDE the expected 5%-95% fraction
    # of the aggregate primary (signals possible XBRL shape drift,
    # stale allowlist entry, or a wrong-member match) OR when per-class
    # >= primary (the override is skipped in that case but the failure
    # is counted so the operator notices). Methodology-scientist Q3
    # 2026-05-26 recommended this as a defensive diagnostic alongside
    # the structural fix (per Damodaran 2019 Ch. 16 identity check —
    # Σ per-class MC = aggregate MC). Expected steady-state firing rate
    # = 0; non-zero is a signal for cohort-audit investigation.
    multi_class_mc_reconcile_failure_count: int | None = None
    # Phase 4.6 (0.10.7-phase4.6) — survivorship-bias visibility per
    # Research Report v1.0 §7.4 + Hou-Xue-Zhang 2020 RFS replication
    # crisis evidence. ``universe_membership_as_of`` is the ISO date
    # of the historical S&P 500 membership snapshot used for THIS
    # compute run; for the forward weekly cron this is the same as
    # ``last_update_utc`` date (current membership). For backtests +
    # validation, it's the as-of date being evaluated.
    # ``survivorship_bias_corrected`` is True when a non-current
    # membership lookup was used (or when the universe is forward-
    # date and matches current membership exactly); False when the
    # lookup fell back to current membership for a historical date
    # (data-quality degraded — operator should investigate).
    # Both nullable on legacy snapshots (pre-0.10.7).
    universe_membership_as_of: str | None = None
    survivorship_bias_corrected: bool | None = None


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
    # Issue #248 PR2a (0.10.3-phase4.5e) — per-ticker cross-source delta
    # surfaced from `compute/ingest/cross_source.validate_market_cap`'s
    # tuple-return refactor (this PR). Value is the absolute relative
    # delta ``|sec_mc - yf_mc| / sec_mc`` where ``sec_mc = shares × price``
    # — a fraction (NOT percent); UI/audit consumers multiply by 100 for
    # display. ``None`` when validator couldn't compute (snapshot/price
    # missing, yfinance fetch returned None, or pre-0.10.3 legacy
    # snapshots). Populated for ALL tickers with a successful validator
    # run, including those below the 5% tolerance threshold — so post-hoc
    # threshold-sweep analysis on the universe is possible without
    # re-running the validator.
    cross_source_delta: float | None = None
