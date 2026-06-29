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
    # Phase 8 pilot PR 3a — S&P 900 integration seam (0.10.21-phase8pilot).
    # "sp500" on all historical / sp500-path outputs (default so extra="forbid"
    # deserializes legacy JSONs cleanly). "sp400" for mid-cap members of the
    # S&P 400 when QR_UNIVERSE=sp900 is active. Annotate-only; does NOT affect
    # composite rank or vetoes. Source: universe DataFrame cohort column
    # (set unconditionally so the column exists on both the sp500 and sp900 paths).
    index_membership: str = "sp500"
    # Multi-index membership — Dow 30 / NDX 100 overlap tabs (0.10.23-phase8pilot).
    # Contains the primary cohort code ("sp500" | "sp400") PLUS every overlapping
    # index the stock is currently in ("dow30", "ndx"). Default empty list so
    # legacy JSON (pre-0.10.23) deserializes cleanly under extra="forbid".
    # ``index_membership`` (singular) is KEPT UNCHANGED — MidcapChip + the
    # membership-ledger script depend on it as the sp500/sp400 partition.
    # Source: derive_index_memberships() in compute/ingest/universe.py.
    index_memberships: list[str] = Field(default_factory=list)


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
    # --- Phase 4j.1 (0.10.15-phase4.6, Rule 18) — Qlib Alpha158 factor
    # integration, OBSERVABILITY-ONLY. The adapter
    # (``compute/features/alpha158_replicate.py``) converts the 158
    # per-stock Alpha158 feature values into the ``(date × signal)``
    # long-short return contract so the existing PBO/DSR gate
    # (``osap_validation.gate_osap_signals``) applies unchanged with
    # ``n_trials=158``. 4j.1 blends NOTHING — ``composite_score`` is
    # byte-identical to pre-4j.1 (Δscore = 0 on every ticker); the
    # rank-influencing blend is deferred to 4j.2 (≥ 1 cron later, after
    # the accounting equation is verified on real data). All fields
    # nullable on legacy snapshots (pre-0.10.15) and when the Alpha158
    # pipeline degrades (graceful-degradation: every ``alpha158_*`` field
    # → ``None``). The 158-feature accounting equation MUST close:
    #   158 == features_missing_from_compute + features_dropped_no_long_short
    #          + features_used + excluded_features
    alpha158_features_used: list[str] | None = None
    alpha158_excluded_features: list[str] | None = None
    alpha158_features_ic_12m: dict[str, float] | None = None
    alpha158_features_missing_from_compute: list[str] | None = None
    alpha158_features_dropped_no_long_short: list[str] | None = None
    # Per-feature PBO/DSR/Sharpe/rejection_reason. Reuses
    # ``OsapGateDiagnostic`` verbatim — the gate-verdict shape is
    # signal-agnostic (methodology-scientist: reuse-as-is to avoid a
    # gratuitous schema-snapshot churn).
    alpha158_gate_diagnostics: dict[str, OsapGateDiagnostic] | None = None
    # % of the universe with ≥ 1 non-null Alpha158 feature at the latest
    # date — feature-compute health canary, parity with
    # ``tier2_coverage_pct``.
    alpha158_coverage_pct: float | None = None
    # methodology condition #2 — survivorship honesty. ``True`` only when
    # the per-month ranking universe came from the point-in-time
    # membership snapshot AND every consumed month was complete; a single
    # degraded month flips it ``False``. ``None`` when the pipeline
    # degraded (no run).
    alpha158_survivorship_bias_corrected: bool | None = None
    # Wall-clock seconds for the Alpha158 Step 7.6 block (feature compute
    # + adapter + gate). ``None`` on full-pipeline failure. Parity with
    # ``osap_wall_clock_seconds``; gates the ``timeout-minutes`` rebaseline.
    alpha158_wall_clock_seconds: float | None = None
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
    # Issue #67 follow-up (0.10.10-phase4.6) — per-sector delta
    # instrumentation requested by methodology-scientist Mode B Q2 verdict
    # 2026-05-28 (deferred from PR #294 sector-CoE flip). Keys are GICS
    # sector names; values are `without_sector_coe[sector] - with_sector_coe[sector]`
    # so POSITIVE = sector DROPPED flags after the flip (Ke < flat 10%
    # → ROE ≥ Ke threshold relaxed → fewer false positives; expected
    # for Utilities / Real Estate / Consumer Staples per Damodaran 2019
    # Ch. 8.4 §"Industry Beta"). NEGATIVE = sector GAINED flags
    # (Ke > flat 10% → stricter; expected for Information Technology /
    # Energy). Zero = neutral (sector Ke == 10% OR same cohort flagged
    # under both baselines). Computed on EVERY cron regardless of
    # ``config.USE_SECTOR_COE`` flag-state so the shape is visible for
    # Q3 2026-08-19 quarterly cohort audit prep (~12 weekly crons of
    # post-flip data accumulating). Nullable on legacy snapshots
    # (pre-0.10.10) AND when `value_trap_risk_count_*` is None.
    value_trap_risk_delta_by_sector: dict[str, int] | None = None
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
    # Listing-metadata observability (0.10.12-phase4.6, Rule 18) —
    # ``exchange_coverage_pct`` = % of the universe whose `StockDetail.exchange`
    # resolved to a non-null display name (the rest had a cold-cache miss or an
    # unknown venue code). Ships BEFORE the hero country/exchange chips read the
    # field (observability-before-wiring) so the frontend wiring waits for ≥ 1
    # cron confirming coverage is high.
    exchange_coverage_pct: float | None = None
    # ``country_coverage_pct`` (0.10.13-phase4.6, Rule 18) — % of the universe
    # whose `StockDetail.country` resolved (US-tagged). The original 0.10.12
    # docstring claimed "country tracks exchange 1:1 — no separate counter
    # needed"; the 2026-06-02 post-cron audit DISPROVED that: `exchange` passes
    # an unknown code through verbatim (counts as covered), while `country`
    # resolves only known US codes, so the two DIVERGE exactly on a raw
    # passthrough code (CBOE's `BTS` showed exchange=100% / country=99.8%).
    # This field is therefore the strict-resolution canary that
    # `exchange_coverage_pct` structurally cannot be: a gap between them flags
    # an unknown venue code reaching production as a flagless raw-code chip.
    # main.py emits a WARNING when country < exchange so the verify-helper +
    # cron logs both catch the next divergence. Nullable on legacy snapshots
    # (pre-0.10.13).
    country_coverage_pct: float | None = None
    # Phase 7.0 PR-1 (0.10.14-phase4.6, Rule 18) — observability-before-wiring
    # surface for the benchmark index export. % of the BENCHMARK_TICKERS
    # (SPY/QQQ/DIA/IWM) whose ~5y close series exported to
    # ``frontend/public/data/portfolio/benchmarks.json``. Ships BEFORE the Phase
    # 7 AI-pick home page reads benchmarks.json: the UI wiring (PR-4) waits for
    # ≥ 1 cron confirming coverage is high. Display-only (no ranking / scoring /
    # veto impact). Nullable on legacy snapshots (pre-0.10.14) and when the
    # export loop was skipped via escape-hatch.
    benchmark_coverage_pct: float | None = None
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
    # Issue #261 PR-B (0.10.6-phase4.5e); semantics updated #374 (RATIFY-B,
    # 2026-06-11) — Rule 18 observability for the structural per-class XBRL
    # extraction path. Counts tickers where Branch 3 CAPTURED the listed
    # line's per-class count into ``shares_outstanding_listed_class`` via a
    # per-filing XBRL filter against the ``MULTI_CLASS_OVERCOUNT_ALLOWLIST``
    # (GOOG → goog:CapitalClassCMember, GOOGL → us-gaap:CommonClassAMember).
    # Since #374 ``shares_outstanding`` RETAINS the company-total aggregate
    # (ASC 260) — this counts per-class FIELD capture, NOT a shares_outstanding
    # override. Disjoint from ``shares_fallback_dimensional_override_count`` —
    # that counter covers the UNDERCOUNT path (PR #257 sums all dimensional
    # contexts for V/NWS/NWSA/FOX/FOXA/BRK-B/STZ); this counter covers the
    # per-class capture (one specific class member for GOOG/GOOGL).
    # Expected steady-state firing rate: 2 (GOOG + GOOGL).
    multi_class_per_class_override_count: int | None = None
    # Issue #288 (0.10.8-phase4.6, 2026-05-28) — Rule-18 disambiguator.
    # Increments each time Branch 3 (per-class override allowlist) enters
    # the ``_fetch_shares_from_per_filing_xbrl`` call, regardless of
    # whether XBRL lookup succeeds. Pre-fix this counter was 2 (GOOG +
    # GOOGL both entered Branch 3) while ``multi_class_per_class_override_count``
    # stayed at 0 — surfacing the silent XBRL lookup failure mode that
    # PR #269 missed (concept-name omission: `us-gaap:CommonStockSharesOutstanding`
    # was not in the XBRL fallback query tuple). Post-fix expected
    # steady-state: attempt = override = 2 (one per ticker per cron).
    # Disambiguation rule for future regressions:
    #   attempt == override == 0 : Branch 3 never triggered (allowlist empty or QR_SKIP_FUNDAMENTALS set)
    #   attempt >  0, override == 0 : XBRL lookup returned None (regression class of #288)
    #   attempt == override >  0 : normal operation
    multi_class_per_class_attempt_count: int | None = None
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
    # Issue #287 PR A (0.10.9-phase4.6) — per-loop wall-clock observability.
    # Parity with ``fundamentals_latency_p95_seconds`` but semantically
    # different: those measure per-ticker fetch p95 (tenacity-cascade
    # detector); these measure total elapsed WALL-CLOCK seconds for the
    # entire loop start-to-end (budget-overrun + cache-eviction detector).
    # Both are needed — slow p95 + short wall-clock = few slow tickers;
    # fast p95 + long wall-clock = parallelism not helping (GIL / SEC
    # queue throttle / too few workers). Gate the next ``timeout-minutes``
    # rebaseline + close the 2026-05-25 150m incident loop.
    # ``None`` when the loop was skipped via escape-hatch env-var
    # (``FORM4_FETCH_SKIP`` only) OR when the loop failed before the end
    # marker was reached. ``QR_SKIP_OSAP`` is NOT a skip-to-None — that
    # env-var only bypasses the OSAP freshness gate; the try block still
    # runs end-to-end so ``osap_wall_clock_seconds`` populates with a
    # small float (~0.5-2s) on a cache-hit fast return.
    # ``cross_source_wall_clock_seconds`` measures the ENTIRE Step 8
    # per-ticker loop (fair-price + manipulation + StockDetail write),
    # not just the cross-source validation sub-calls
    # — documented limitation; the cross-source yfinance.info fetch
    # dominates only on cold-cache (serial 2-8s/ticker × 502 = 17-67 min);
    # on warm-cache hits the rest of Step 8 dominates (~50s).
    tier2_wall_clock_seconds: float | None = None
    form4_wall_clock_seconds: float | None = None
    osap_wall_clock_seconds: float | None = None
    cross_source_wall_clock_seconds: float | None = None
    # Phase 4.5e PR 6 (0.10.11-phase4.6) — count of True → False downgrades
    # applied by the post-detector 10b5-1 negation guard during cache build
    # (residual footgun #1 from PR 4-eq). Tracks the universe-wide cohort
    # of footnote disclosures matching phrases like "10b5-1 plan terminated
    # 2022" / "no 10b5-1 plan in effect" / "previously had a 10b5-1 plan"
    # — where the upstream ``edgar.ownership.core.detect_10b5_1_plan``
    # substring match returns True even though the affirmative defense is
    # NOT in force on the transaction date. The PR 6 negation guard re-
    # scans the resolved text for negation tokens (``terminated`` /
    # ``cancelled`` / ``no`` / ``previously`` / ``former`` / etc.) within
    # ±5 word tokens of the 10b5-1 mention and downgrades the detection.
    # Pre-PR-4-eq verdict (2026-05-23) pre-approved this hardening; PR 6
    # implements the engineering.
    #
    # ``None`` semantics mirrors ``form4_wall_clock_seconds``: None when
    # FORM4_FETCH_SKIP=1 (loop didn't run; detector never invoked) OR when
    # the outer try/except fired before the end marker. On the happy path
    # the value is the integer count of downgrades across the universe-wide
    # cache-build. WARM-cache runs report 0 (no detector ran this cron —
    # cached ``is_rule_10b5_one`` is read as-is); COLD-cache runs populate
    # the real cohort number for the Q3 2026-08-19 cohort-acceptance check
    # (issue #130) alongside ``form4_rule10b5_one_excluded_count``. Expected
    # delta-firing-rate per Cohen 2008 §III + Jagolinzer 2009 §3.2:
    # ``insider_sell_cluster`` +5% to +10% relative on a universe-baseline
    # cron (absolute << 1%; most 10b5-1 disclosures are affirmative).
    # Nullable on legacy snapshots (pre-0.10.11).
    form4_negation_guard_downgrade_count: int | None = None
    # Issue #75 §3 (decay monitor, Rule 18 observability-before-wiring) —
    # URL of the IC-decay report artifact relative to the static site root.
    # Set to "/data/decay_report.json" when the decay monitor ran and the
    # file was written; ``None`` when the step was skipped via
    # ``QR_SKIP_DECAY_MONITOR=1`` or when the step failed catastrophically
    # (the failure is logged; the cron continues without blocking). The
    # file always exists on disk when non-None — the frontend can safely
    # fetch it at this URL. Nullable on legacy snapshots (pre-0.10.20).
    decay_report_url: str | None = None
    # Phase 8 pilot PR 1 (0.10.19-phase8pilot, Rule 18) — observability-before-
    # wiring diagnostics for the S&P 900 universe expansion. These fields are
    # populated ONLY when QR_UNIVERSE=sp900; on the default sp500 path they are
    # None. Ranked output (rankings.json + stocks/*.json) is BYTE-IDENTICAL to a
    # 500 run — the probe is a SEPARATE loop that does NOT feed summaries / the
    # writer. PR 3 will wire the ranked output once the coverage picture is clear.
    #
    # ``universe_cohort_sizes`` — count of tickers per cohort after de-dup:
    #   keys "sp500" and "sp400" (sp500 wins on transient overlap).
    #   None on the default sp500 path.
    universe_cohort_sizes: dict[str, int] | None = None
    # ``midcap_fundamentals_coverage_pct`` — % of sp400 midcap tickers for which
    # ``fetch_fundamentals`` returned a non-null FundamentalsSnapshot during the
    # diagnostic probe. Measures EDGAR / fundamentals-ingest readiness for the 400
    # before we commit to ranking them. None on the default sp500 path.
    midcap_fundamentals_coverage_pct: float | None = None
    # ``midcap_null_rate_pct`` — % of sp400 tickers whose FundamentalsSnapshot
    # returned None (failed, skipped due to null CIK, or timed out). Complement
    # of ``midcap_fundamentals_coverage_pct``:
    #   null_rate + coverage_pct ~= 100% (slight float rounding expected).
    # None on the default sp500 path.
    midcap_null_rate_pct: float | None = None
    # ``midcap_cik_resolution_pct`` — % of sp400 tickers whose CIK was successfully
    # resolved (either from the Wikipedia page or via Company(ticker).cik). A low
    # value here blocks EDGAR fetches for those tickers. None when probe didn't run.
    midcap_cik_resolution_pct: float | None = None
    # OZK/PBF flip-blocker (0.10.22-phase8pilot, Rule 18) — Rule-18 observability
    # surface for the new ``fundamentals_unavailable`` direct veto. Counts tickers
    # whose ``FundamentalsSnapshot`` was ``None`` (complete EDGAR ingest failure)
    # on this cron run. Unlike ``share_count_extraction_missing_count`` (annotate)
    # this fires on total input-absence: ``snap is None``. FP rate is structurally
    # zero so the flag ships as a direct veto (DQIC precedent, issue #18). A
    # non-zero value on a production sp500 cron is a data-pipeline health signal
    # requiring investigation. Nullable on legacy snapshots (pre-0.10.22).
    fundamentals_unavailable_count: int | None = None
    # Issue #177 PR-A (0.10.24-phase8pilot, Rule 18) — blast-radius metric for the
    # ratified two-regime trimmed-median change (OBSERVABILITY-FIRST; methodology-
    # scientist RATIFIED-WITH-CONDITIONS, user-authorized as frozen pre-registration).
    # Counts universe tickers whose MoS SIGN would flip under the shadow trimmed
    # median vs the live median:
    #   sign((median_trimmed - price) / median_trimmed) != sign(mos_pct)
    # Counted only where ``median_trimmed is not None`` (excludes majority-collapse
    # cases). This is the decision-critical metric that gates the follow-up PR
    # that wires median_trimmed → mos_pct (replacing the live median). A large
    # sign-flip count validates the Huber 1981 §1.4 breakdown-point rationale
    # empirically; a near-zero count would suggest the live median is already robust
    # (contra the FFIV −23.6% → +18.1% and APP −1257% audit findings). Nullable
    # on legacy snapshots (pre-0.10.24); None when the per-stock JSON loop was
    # skipped or all tickers had null median_trimmed.
    median_trim_delta_count: int | None = None
    # Post-split share-lag defense (defense layer 35, 0.10.25-phase8pilot,
    # Rule 18 observability-before-wiring).
    #
    # ``post_split_share_lag_count`` — tickers where the flag fired (either
    # tier).  Equals ``post_split_correction_applied_count +
    # post_split_veto_count``.  A non-zero value on a production cron is
    # expected immediately after any universe-wide 2:1+ split; it should
    # decay to 0 within one 10-Q EDGAR cycle (~45 days) unless the filer
    # is unusually slow to file.  Nullable on legacy snapshots
    # (pre-0.10.25).
    #
    # ``post_split_correction_applied_count`` — subset of the above where
    # Tier-1 (CORRECT) fired: split confirmed + ratio reconciled → shares
    # corrected in-flight before scoring.  Gates the first post-cron
    # audit of the corrected composite/rank deltas (expected ≥ 1 for
    # KLAC / CVNA / COKE on the first post-2026-06-18 cron).
    #
    # ``post_split_veto_count`` — subset where Tier-2 (VETO) fired: split
    # confirmed but ratio unreconcilable → ticker vetoed (cautious +
    # Top-5 suppression).  Expected steady-state near 0; non-zero
    # warrants investigation (yfinance/EDGAR both stale? M&A ticker
    # change?).  Nullable on legacy snapshots (pre-0.10.25).
    post_split_share_lag_count: int | None = None
    post_split_correction_applied_count: int | None = None
    post_split_veto_count: int | None = None
    # Dividend signal PR-1 (roadmap item #5 / 7a — observability-first,
    # Rule 18, 0.10.27-phase8pilot) — coverage diagnostic canary.
    # Modelled exactly on ``exchange_coverage_pct`` / ``country_coverage_pct``:
    # % of the ranked universe with a non-null ``StockDetail.dividend_yield_pct``
    # after the Step-8 per-ticker loop.  A low value (< 80%) on the first
    # post-merge cron would indicate that the ``yfinance_info`` cache was
    # cold and the dividend fields were not pre-populated by an earlier
    # ``fetch_yfinance_market_cap`` call.  Expected steady-state:
    # ~95-99% (same as ``exchange_coverage_pct`` since both derive from the
    # same ``yfinance_info`` cache populated during the cross-source loop).
    # Zero is a valid value (all tickers with confirmed no-dividend);
    # ``None`` means the loop was skipped or the field aggregation failed.
    dividend_coverage_pct: float | None = None
    # Cross-source share-count-corruption shadow grading (PR-1, Rule 18
    # observability-first, 0.10.26-phase8pilot).
    #
    # Methodology-scientist RATIFIED-WITH-CONDITIONS 2026-06-19.
    # PR-1 ships SHADOW METADATA ONLY — no flag emitted, no score mutated,
    # no ranking change.  All 4 fields are ``None`` by default so legacy
    # snapshots (pre-0.10.26) deserialize cleanly.  PR-2 will wire the
    # actual veto/correction once the first cron confirms the grades on real
    # data.
    #
    # Background: ``cross_source_delta = |sec_mc − yf_mc| / sec_mc`` where
    # ``sec_mc = edgar_shares × current_price``, ``yf_mc = yfinance .info
    # marketCap``.  The #114 audit showed delta ≥ 0.50 is the corruption
    # tail (COKE 6.07, CVNA 3.89, KLAC-pre-#499 ≈ 10; clean stocks < 0.05).
    #
    # Grading logic (``compute/scoring/risk_overlay.grade_cross_source_corruption``):
    # - ``NO_FIRE``            : delta < 0.50 (normal noise; BKNG/KLAC-post-#499)
    # - ``CORRECT_CANDIDATE``  : delta ≥ 0.50 + near-integer mc_ratio + dual-ratio
    #                             corroboration (share_ratio rounds to SAME integer)
    # - ``VETO_CANDIDATE``     : delta ≥ 0.50 + NOT CORRECT_CANDIDATE (includes
    #                             the COKE-class ratio_disagreement case)
    #
    # ``cross_source_corruption_correct_candidate_count`` — universe tickers where
    # the grade is CORRECT_CANDIDATE: the inferred integer ratio is consistent
    # across both mc and share channels.  These are the first candidates for
    # PR-2's Tier-1 CORRECT branch (analogous to ``post_split_correction_applied``).
    cross_source_corruption_correct_candidate_count: int | None = None
    # ``cross_source_corruption_veto_candidate_count`` — universe tickers where
    # the grade is VETO_CANDIDATE: delta ≥ 0.50 but the ratio either is
    # non-integer, uncorroborated (no yf_shares), or ratio_disagreement=True.
    # These are the first candidates for PR-2's Tier-2 VETO branch (analogous
    # to ``post_split_veto_count``).
    cross_source_corruption_veto_candidate_count: int | None = None
    # ``cross_source_corruption_ratio_disagreement_count`` — subset of VETO_CANDIDATEs
    # where ``ratio_disagreement=True``: mc_ratio and share_ratio are BOTH near-integer
    # but round to DIFFERENT integers.  This is the COKE-class detector: yfinance
    # marketCap is stale (mc_ratio ≈ 7.07 → 7) while sharesOutstanding may reflect
    # the true factor (share_ratio ≈ 10 → 10) or vice versa.  A bare round(mc_ratio)
    # alone would infer the wrong factor.  A non-zero value here means the dual-ratio
    # corroboration guard is load-bearing for at least one ticker in the universe.
    cross_source_corruption_ratio_disagreement_count: int | None = None
    # ``cross_source_corruption_inferred_ratio_by_ticker`` — shadow integer factor per
    # CORRECT_CANDIDATE ticker.  Keys are ticker symbols; values are the inferred
    # integer ratio (e.g. ``{"CVNA": 5.0}``).  Lets the methodology-scientist eyeball
    # that CVNA → 5 and that no clean stock spuriously inferred a factor.
    #
    # GUT-FEEL NOTE (methodology prior 6): the ``round(R)`` integer-recovery mechanism
    # is NOT yet literature-anchored.  The assumption that a share-count corruption
    # factor is always a near-integer is plausible (stock-split ratios are always
    # integers; unit-conversion errors like millions→raw are always powers of 10)
    # but lacks a systematic literature citation.  The literature-searcher is
    # checking in parallel; Q3 2026-08-19 will either anchor or revise this.
    # Until then treat the inferred_ratio as informational, NOT a correction input.
    cross_source_corruption_inferred_ratio_by_ticker: dict[str, float] | None = None
    # S&P 1500 cutover — Slice 2 (0.10.27-phase8pilot, Rule 18
    # observability-before-wiring).  These three fields mirror the midcap
    # equivalents (``midcap_*``), targeting the sp600 small-cap cohort.
    # They are populated ONLY when ``QR_UNIVERSE=sp1500``; on the default
    # sp900/sp500 paths they are ``None``.  No ranked exposure of sp600
    # tickers ships until Slice 3 (which requires ≥ 1 cron of coverage
    # data from these counters).
    #
    # ``smallcap_fundamentals_coverage_pct`` — % of sp600 tickers for
    # which ``fetch_fundamentals`` returned a non-null
    # ``FundamentalsSnapshot`` during the Slice-2 diagnostic probe.
    # Measures EDGAR / fundamentals-ingest readiness for the 600 before
    # ranked exposure is allowed.  None on the default sp900/sp500 paths.
    smallcap_fundamentals_coverage_pct: float | None = None
    # ``smallcap_null_rate_pct`` — % of sp600 tickers whose
    # ``FundamentalsSnapshot`` was None (failed, skipped due to null CIK,
    # or timed out).  Complement of ``smallcap_fundamentals_coverage_pct``
    # (coverage + null_rate ≈ 100%, small float-rounding expected).
    # None on the default sp900/sp500 paths.
    smallcap_null_rate_pct: float | None = None
    # ``smallcap_cik_resolution_pct`` — % of sp600 tickers whose CIK was
    # successfully resolved (either from the Wikipedia SP600 page or via
    # ``Company(ticker).cik``).  A low value blocks EDGAR fetches for those
    # tickers and is the first signal that the SP600 ingest layer needs
    # hardening before ranked production exposure.  None when the probe
    # didn't run (QR_UNIVERSE != sp1500).
    smallcap_cik_resolution_pct: float | None = None
    # Security-type signal PR-1 (roadmap item #5 / 7b, 0.10.31-phase8pilot,
    # Rule 18 observability-first) — coverage diagnostic canary.
    # Modelled exactly on ``dividend_coverage_pct``:
    # % of the ranked universe with a non-null ``StockDetail.security_type``
    # after the Step-8 per-ticker loop.  A low value (< 80%) on the first
    # post-merge cron would indicate that the ``yfinance_info`` cache was
    # cold and the ``quote_type`` field was not yet pre-populated.
    # Expected steady-state: ~95-99% (same as ``exchange_coverage_pct``
    # since both derive from the same ``yfinance_info`` cache populated via
    # the cross-source loop).
    # ``None`` means the loop was skipped or the field aggregation failed.
    security_type_coverage_pct: float | None = None
    # S&P 1500 Slice 4 — ADV liquidity backstop (defense layer 36,
    # 0.10.29-phase8pilot, Rule 18 observability-before-wiring).
    #
    # ``low_liquidity_annotate_count`` — universe-wide count of tickers
    # where the ``low_liquidity`` annotate fired on this cron run:
    # ``average_dollar_volume is not None and average_dollar_volume <
    # config.ADV_FLOOR_USD`` ($5M trailing-30-day mean dollar volume).
    #
    # The flag is ANNOTATE-ONLY (emitted to ``valuation_warnings``, NOT
    # ``risk_flags``): it does NOT set ``cautious``, does NOT suppress
    # Top-5, does NOT null fair-price, and does NOT change the composite
    # score.  Veto promotion is gated on ≥ 1 cron of firing-rate data +
    # methodology ratification (WORKFLOW.md §8.6).
    #
    # Nullable on legacy snapshots (pre-0.10.29); ``None`` when the
    # Step-1 prices loop was skipped or the ADV computation failed for
    # the entire universe.  Expected base rate for the S&P 900 universe:
    # near-zero (large-cap S&P names all clear $5M/day comfortably) —
    # the flag is designed for S&P 1500 small-cap exposure where
    # micro-cap / thinly-traded names may appear.
    low_liquidity_annotate_count: int | None = None
    # Bonferroni multi-test shadow counter (issue #542, Slice 8,
    # 0.10.30-phase8pilot, Rule 18 observability-before-wiring).
    #
    # Background: expanding the universe raises the multiple-comparison
    # burden. Tighter FWER control (Bonferroni: α* = α/m = 0.05/valid_count,
    # where valid_count = the number of non-None Beneish M-scores THIS cron —
    # data-driven, NOT a hardcoded 1500) TIGHTENS the Beneish M-Score cutoff
    # — moves it UP toward 0 (less negative), NOT down (WORKFLOW.md §8.6
    # sign correction 2026-06-19). The current live threshold is −2.22
    # (Beneish 1999); the provisional Bonferroni-tightened threshold is
    # −1.94 (PROVISIONAL placeholder — must be re-derived from empirical sp1500 SD).
    #
    # These 3 fields are SHADOW / OBSERVABILITY-ONLY. They do NOT change
    # the live ``beneish_high`` flag, the composite score, the vetoes, or
    # the rankings. Methodology-scientist must review the first cron's
    # counts before any threshold is promoted to the live layer.
    #
    # ``bonferroni_shadow_flip_count`` — tickers where the flag state
    # DIFFERS between the two thresholds. Since the provisional is
    # stricter (−1.94 > −2.22), flips are always: live fires, provisional
    # does NOT. A larger value = more false positives the tighter threshold
    # would suppress from the annotate cohort. Zero means the two
    # thresholds agree for the whole universe (all live-fires also exceed
    # the tighter threshold). Methodology-scientist gate: this count +
    # the live_fire and provisional_fire counts combined tell whether
    # the provisional −1.94 is well-calibrated for the sp1500 universe.
    #
    # ``bonferroni_shadow_live_fire_count`` — tickers with Beneish
    # M-score > −2.22 (the live threshold) on this cron run. Matches
    # the universe-wide count of ``beneish_high`` annotates. Surfaced
    # here so the shadow report is self-contained.
    #
    # ``bonferroni_shadow_provisional_fire_count`` — tickers with M-score
    # > −1.94 (the provisional Bonferroni threshold). Always ≤
    # bonferroni_shadow_live_fire_count (provisional is stricter).
    # The difference between live and provisional counts =
    # bonferroni_shadow_flip_count.
    #
    # All 3 default to None so legacy snapshots (pre-0.10.30) deserialize
    # cleanly under extra="forbid". None when the Beneish pre-compute pass
    # was skipped or failed (non-fatal).
    bonferroni_shadow_flip_count: int | None = None
    bonferroni_shadow_live_fire_count: int | None = None
    bonferroni_shadow_provisional_fire_count: int | None = None
    # Issue #587 (0.10.32-phase8pilot) — Rule 18 observability counter for the
    # ``extreme_estimate_majority`` low-applicability floor (RE-BASE-WITH-FLOOR,
    # methodology-scientist ratified). Counts tickers where the annotate fired
    # EXCLUSIVELY via the low-applicability floor (n_applicable ≤
    # EXTREME_MAJORITY_LOWAPP_MAX = 3 AND n_extreme ≥
    # EXTREME_MAJORITY_LOWAPP_MIN = 2 AND strict-majority) but NOT via the
    # baseline 3-of-6 rule (n_extreme < EXTREME_MAJORITY_THRESHOLD = 3). This
    # is the delta between the new and old firing populations — pre-measured at
    # 16 tickers on cron 8c89a5af0 (GFF, SMTC, DD, NRG, LGIH, GEV, BILL, TTWO,
    # HASI, HIMS, CRWD, MSGS, NABL, CHTR, COKE, EMBC). Annotate-only; defense
    # layer UNCHANGED at 36. Nullable on legacy snapshots (pre-0.10.32); None
    # when the Step-8 ensemble loop was skipped or failed.
    # Note: this delta is ⊆ extreme_estimate_majority_count EXCEPT on a ticker
    # that both fires the floor AND is Tier-2-vetoed (e.g. post_split_share_lag_
    # unreconciled) — the veto nulls the ensemble after the warning was captured,
    # so the total still counts it but this delta does not. ~0 expected overlap.
    extreme_estimate_majority_lowapp_count: int | None = None
    # Two-factor value_trap_risk gate counter (issue #586 PR-2,
    # 0.10.34-phase8pilot).
    #
    # PR-1 (0.10.33-phase8pilot) shipped this as a SHADOW counter while the
    # two-factor gate was observability-only.  The first sp1500 cron confirmed
    # 155 firings (10.3% of 1504) — squarely in the methodology-ratified 5-12%
    # LSV 1994 band.  PR-2 FLIPS the live emission to the two-factor gate.
    #
    # As of 0.10.34-phase8pilot, the LIVE ``value_trap_risk`` warning fires iff:
    #   (a) RIM skips under avg_3y_roe ≤ Ke  (Penman 2013 condition)
    #   AND
    #   (b) eps_ttm > 0 (positive trailing earnings, so P/E is defined)
    #   AND
    #   (c) P/E (= current_price / eps_ttm) < sector-peer median P/E
    #       (LSV 1994 "Contrarian Investment" §3 cheap-relative-to-peers leg)
    # A loss-making / pre-revenue growth stock (eps_ttm ≤ 0, P/E undefined)
    # is EXEMPT from the two-factor gate and does NOT emit the warning.
    #
    # This counter now equals the LIVE ``value_trap_risk`` warning count
    # (the two-factor firings, ~155 on the first sp1500 cron).  It is kept for
    # one additional cron as a structural cross-check.  NOTE: it does NOT
    # equal ``value_trap_risk_count_with_sector_coe`` (~548) — that field is
    # the Issue-#67 SINGLE-LEG RIM-skip diagnostic (counts every ROE ≤ Ke
    # firm under the sector CoE, the Penman superset), which is a STRICT
    # SUPERSET of this two-factor count.  The expected gap is ~393 (the
    # single-leg-only firms the LSV cheap leg now exempts — predominantly
    # loss-making / above-median-P/E growth names), NOT ~0.  A post-cron
    # auditor cross-checking these two counters should expect that ~393 delta.
    #
    # Nullable on legacy snapshots (pre-0.10.33).  None when the per-stock
    # loop was skipped or failed.  Zero is a valid value (no tickers fired).
    value_trap_risk_two_factor_shadow_count: int | None = None
    # Proposal F — IC half-life monitor (Proposal F 2026-06-24, Rule 18
    # observability-before-wiring, SHADOW / OBSERVABILITY-ONLY).
    #
    # Per-pillar fitted IC decay half-life in months, derived by fitting BOTH an
    # exponential decay model (McLean-Pontiff 2016 JF §3 characterisation) AND a
    # power-law decay model (Di Mascio 2022 SSRN Working Paper 4023689 §4 found
    # power-law fits alpha-decay slightly better — median adj-R² 0.48 vs 0.43
    # across an 80-factor panel), then selecting the winner by R².
    #
    # ``pillar_ic_half_life_months`` — per-pillar dict mapping pillar name
    # (``"value"``, ``"quality"``, …) to the half-life in months.  A value of
    # ``None`` for a specific pillar means EITHER:
    #   (a) Preliminary: fewer than MIN_HALF_LIFE_FIT_MONTHS (12) monthly
    #       observations exist for that pillar — the honest expected outcome
    #       with ~1 week of git IC history (all pillars → None on launch day),
    #       or
    #   (b) Both curve fits failed to produce a positive half-life.
    # The outer dict itself is ``None`` when the half-life computation was
    # skipped (QR_SKIP_DECAY_MONITOR=1) or failed catastrophically.
    #
    # ``pillar_ic_decay_fit_model`` — per-pillar dict mapping pillar name to the
    # winning decay model (``"exponential"`` or ``"power"``).  ``None`` for a
    # specific pillar when ``pillar_ic_half_life_months[pillar]`` is ``None``.
    # The outer dict mirrors the outer-None semantics of the half-life field.
    #
    # NEVER feeds scoring, vetoes, rankings, or composite score.  Defense layer
    # is UNCHANGED at 36.  Both fields default to None so legacy snapshots
    # (pre-0.10.34) deserialize cleanly under extra="forbid".
    pillar_ic_half_life_months: dict[str, float | None] | None = None
    pillar_ic_decay_fit_model: dict[str, str | None] | None = None
    # Proposal D — market-regime diagnostic (2026-06-25, Rule 18,
    # WRITE-ONLY / OBSERVABILITY-ONLY).
    #
    # ``market_breadth_above_200dma_pct`` — the raw breadth signal: % of the
    # ranked universe whose latest close is above its own 200-day simple moving
    # average.  Tickers with fewer than 200 trading-day bars are excluded from
    # the denominator (insufficient history for a valid SMA-200).  Range [0, 100].
    # ``None`` when no eligible tickers were found (all frames empty or < 200 bars).
    #
    # ``market_regime_state`` — categorical label derived from the breadth %:
    #   "risk_on"  (breadth >= config.REGIME_RISK_ON_THRESHOLD  = 60%)
    #   "neutral"  (40% < breadth < 60%)
    #   "risk_off" (breadth <= config.REGIME_RISK_OFF_THRESHOLD = 40%)
    # The thresholds are TIER-3 GUT-FEEL CALIBRATION (no paper pins exact
    # breadth cutoffs) — named in config.py so recalibration is a visible diff.
    # ``None`` when ``market_breadth_above_200dma_pct`` is ``None``.
    #
    # HARD CONSTRAINT (Welch-Goyal 2008 rejection-as-tilt):
    # These fields MUST NEVER be read by scoring, the composite, pillar
    # computation, veto/flag logic, fair-price, ``select_picks``, or the
    # weights.  They are computed once near the Metadata assembly and feed
    # ONLY the Metadata constructor (write-only).  Rankings/scores/flags are
    # byte-identical.  This diagnostic seeds a future Phase-7 Student-t HMM;
    # see ``compute/scoring/regime.py`` for the full rationale.
    # Defense layer UNCHANGED at 36.
    market_breadth_above_200dma_pct: float | None = None
    market_regime_state: str | None = None
    # Proposal A — shrinkage composite diagnostics (Rule 18 observability-first,
    # 0.10.37-phase8pilot).
    #
    # Identity-at-launch safety property: with ``SHRINKAGE_LAMBDA_PIN = 1.0``
    # AND every pillar currently preliminary (thin IC history), the blend
    # returns ``w0`` via two independent guards — composite is byte-identical.
    # These 6 fields are SHADOW / OBSERVABILITY-ONLY; they feed ONLY this
    # Metadata constructor.  NEVER read by scoring, composite, pillar
    # computation, veto/flag logic, fair-price, or select_picks.
    # Defense layer UNCHANGED at 36.  Rankings/scores/flags byte-identical.
    #
    # ``shrinkage_lambda`` — the schedule-derived λ = 1/(1 + n/τ) for the
    # pillar with the MOST IC history (n = max n_observations across active
    # non-preliminary pillars).  ``None`` when all pillars are preliminary
    # or the monitor was skipped.
    shrinkage_lambda: float | None = None
    # ``shrinkage_lambda_applied`` — λ actually applied to each pillar blend.
    # While ``SHRINKAGE_LAMBDA_PIN = 1.0`` (identity mode), this equals 1.0
    # for every pillar; it will differ from ``shrinkage_lambda`` once the pin
    # is lifted.  ``None`` when the shrinkage block was skipped or failed.
    shrinkage_lambda_applied: float | None = None
    # ``ic_weight_by_pillar`` — the IC-implied weight vector ``w_IC`` before
    # blending.  Per-pillar dict mapping pillar name to the IC-derived weight.
    # Keys: all 8 active pillars.  Values are 0.0 for preliminary pillars (no
    # usable IC); normalized to 1.0 over non-preliminary positive-IC pillars.
    # When ``shrinkage_weights_degenerate=True``, this equals ``w0``.
    # ``None`` when the shrinkage block was skipped or failed.
    ic_weight_by_pillar: dict[str, float] | None = None
    # ``shrinkage_blended_weight_by_pillar`` — the final blended weight vector
    # passed to ``compute_composite``.  The byte-identity canary: while
    # ``SHRINKAGE_LAMBDA_PIN = 1.0`` this must equal
    # ``PHASE3_EFFECTIVE_WEIGHTS`` (dict form) exactly within 1e-9 per pillar.
    # On the first sp1500 cron where this deviates, the methodology-scientist
    # gate (A3-i/A3-ii) must clear before the deviation can be intentional.
    # ``None`` when the shrinkage block was skipped or failed.
    shrinkage_blended_weight_by_pillar: dict[str, float] | None = None
    # ``n_preliminary_pillars`` — count of active pillars currently in the
    # ``preliminary_mask`` (ICDecayReport.preliminary == True), i.e., fewer
    # than MIN_HISTORY_MONTHS (12) monthly IC observations.  While this equals
    # len(ACTIVE_PILLARS_PHASE3) (all 8 active pillars), the blend is
    # fully pinned to ``w0`` regardless of the lambda_pin setting.  Zero means
    # all active pillars have crossed the MIN_HISTORY_MONTHS floor (but the
    # pin may still be 1.0 pending A3-i/A3-ii).  ``None`` when skipped/failed.
    n_preliminary_pillars: int | None = None
    # ``shrinkage_weights_degenerate`` — True when the IC-implied weight
    # vector could not be meaningfully constructed (all non-preliminary IC
    # was zero or negative; Σraw == 0).  In this state ``ic_weight_by_pillar``
    # equals ``w0`` and the blend returns ``w0``.  Expected value at launch:
    # True (all pillars preliminary → Σraw = 0 → degenerate).  ``None`` when
    # the shrinkage block was skipped or failed.
    shrinkage_weights_degenerate: bool | None = None
    # Proposal C-2 — MoS conviction tilt shadow canary (0.10.38-phase8pilot,
    # Rule 18 observability-first).
    #
    # ``mos_tilt_shadow_max_delta_pp`` — the maximum per-rebalance
    # ``max_t |mos_tilted_weight_t − base_weight_t| × 100`` across ALL
    # rebalance legs in the refreshed ``backtest_pit.json`` artifact.
    # This is a **cross-universe canary**: it answers "what is the largest
    # single-name weight shift the MoS tilt would produce in any rebalance?"
    # and lets the methodology-scientist calibrate whether κ=0.25 produces
    # meaningful but bounded tilts before the flip-gate is considered.
    #
    # Populated by reading ``backtest_pit.json`` after the PIT-backtest refresh
    # in ``compute/main.py`` (the same pattern as Step 13.5b), try/except → None.
    #
    # HARD CONSTRAINT: this field MUST NEVER be read by scoring, the composite,
    # pillar computation, veto/flag logic, fair-price, ``select_picks``, or
    # ``inverse_vol_weights``.  It is written to ``Metadata`` ONLY and feeds
    # the diagnostic surface.  Rankings/scores/flags are byte-identical.
    # Defense layer UNCHANGED at 36.
    #
    # Nullable on legacy snapshots (pre-0.10.38).  None when the
    # ``backtest_pit.json`` artifact is absent (first cron after a cold clone,
    # or when the backfill was not re-run since C-2 was landed).
    mos_tilt_shadow_max_delta_pp: float | None = None
    # Proposal C-1 — high-conviction gate counters (0.10.39-phase8pilot, Rule 18
    # observability-first).
    #
    # Background: the high-conviction gate (``is_high_conviction`` in
    # ``compute/portfolio/weights.py``) is ALREADY the production selection
    # driver in the backfill (``gate="high_conviction"`` wired since PR #604).
    # This C-1 slice measures the marginal bite of the loss-chance leg
    # (``loss_chance_pct <= HIGH_CONVICTION_LOSS_CHANCE_MAX = 45.0``) in the
    # ALREADY-LIVE gate.  These counters do NOT gate the wire-in — they observe
    # a gate that has been live in the backfill for multiple crons.
    #
    # Gate composition (``is_high_conviction``):
    #   (1) is_eligible  — no AI-pick-basket veto (``ACTIVE_VETO_FLAGS``, 7
    #                      flags in compute/portfolio/weights.py). This is the
    #                      NARROWER basket gate — distinct from the 10 Top-5
    #                      vetoes (``KNOWN_RISK_FLAGS``) and the 4 cautious-label
    #                      vetoes (``_CAUTIOUS_FORCING_RISK``); see CLAUDE.md
    #                      §scoring (38 declared = 10 active vetoes + 28 annotates).
    #   (2) recommendation ∈ {"bullish", "lean_bullish"}
    #   (3) margin_of_safety_pct > 0  (strict undervaluation, Graham-Dodd)
    #   (4) composite_score ≥ 50.0    (HIGH_CONVICTION_COMPOSITE_MIN)
    #   (5) loss_chance_pct ≤ 45.0    (HIGH_CONVICTION_LOSS_CHANCE_MAX —
    #                                   gut-feel, firing-rate under observation)
    # Fail-closed: any None input → not high-conviction.
    #
    # ``high_conviction_count`` — count of stocks in the full ranked universe
    # that clear ALL legs of the gate on this cron run.
    #
    # ``high_conviction_ex_loss_chance_count`` — count of stocks passing the HC
    # gate WITHOUT the loss-chance leg (legs 1-4 only; leg 5 omitted).  This
    # is the marginal-bite DENOMINATOR:
    #   bite = high_conviction_ex_loss_chance_count − high_conviction_count
    # By construction ex_loss_chance_count ≥ high_conviction_count always.
    # A materially positive bite (e.g. ≥ 5 names across crons) means leg 5
    # is doing real work — keep it.  A bite ≈ 0 across crons means leg 5 is
    # redundant and can be dropped in the gate-flip.
    # Legs 1-4 used: is_eligible + recommendation ∈ HC_RECS + MoS > 0 +
    # composite ≥ HIGH_CONVICTION_COMPOSITE_MIN.  Fail-closed on None inputs
    # for legs 1-4 (same as is_high_conviction); loss_chance_pct is
    # NEITHER required NOR fail-closed here — that is the point.
    #
    # ``high_conviction_below_floor`` — starvation canary derived from the
    # refreshed ``backtest_pit.json`` artifact (same read pattern as C-2's
    # ``mos_tilt_shadow_max_delta_pp``).  True if ANY rebalance leg in the
    # artifact has ``eligible_high_conviction_count < ADAPTIVE_MIN_PICKS (5)``
    # — the per-rebalance starvation signal (the cron's full-universe count is
    # always >> 5, so universe-level < 5 is structurally useless).  False when
    # the artifact is present + readable AND all rebalance legs clear the floor.
    # None when the artifact is absent or unreadable (first cron after a cold
    # clone; graceful-degradation path).
    #
    # HARD CONSTRAINT: all three fields MUST NEVER be read by scoring, the
    # composite, pillar computation, veto/flag logic, fair-price, ``select_picks``,
    # or ``inverse_vol_weights``.  They are written to ``Metadata`` ONLY and feed
    # the diagnostic surface.  Rankings/scores/flags are byte-identical.
    # Defense layer UNCHANGED at 36.
    #
    # Pre-registered FUTURE gate-flip condition (methodology C-1 RATIFY-WITH-
    # CONDITION): hc_count ≥ ADAPTIVE_MIN_PICKS + 2 (≥ 7) across ALL crons AND
    # ALL backtest rebalance legs AND the marginal-bite read
    # (count_passing_legs_1_2_3_4 − high_conviction_count) resolves the
    # loss-chance leg — keep loss_chance≤45 if it bites; drop the leg if ≈ 0.
    # NOT a bare below_floor gate.  Gates issue #130.
    #
    # Nullable on legacy snapshots (pre-0.10.39).  None when the helper failed
    # (non-fatal, try/except — cron never blocked).
    high_conviction_count: int | None = None
    high_conviction_ex_loss_chance_count: int | None = None
    high_conviction_below_floor: bool | None = None
    # Proposal E — Turnover / hysteresis diagnostic + liquidity capacity tilt
    # (0.10.40-phase8pilot, Rule 18 observability-first).
    #
    # Background: the hysteresis hold-band [55, 65) is ALREADY the production
    # carry rule in the backfill (V55.1, ratified 2026-06-11).  Proposal E
    # slice-1 adds SHADOW diagnostics around it — the live band and NAV are
    # byte-identical.  Defense layer UNCHANGED at 36 (``low_liquidity`` is an
    # existing annotate; the capacity tilt is a sizing device, NOT a new flag).
    #
    # ``hysteresis_turnover_reduction_mean_pp`` — mean per-rebalance
    # turnover-reduction (percentage-points) of the hysteresis band vs the
    # no-carry stateless counterfactual over ALL backtest legs:
    #     turnover_reduction_pp_per_leg = turnover_stateless_pct − turnover_band_pct
    #     hysteresis_turnover_reduction_mean_pp = mean(per_leg_reductions)
    # Positive values confirm the band reduces churn.  H1 gate (pre-registered):
    # mean >= 15pp over >= 4 live rebalances (Garleanu-Pedersen 2013 *JF* 68(6)).
    # Populated by reading ``backtest_pit.json`` after the PIT-backtest refresh
    # (same artifact-read pattern as C-2 and C-1).
    # None when the artifact is absent, unreadable, or has no legs with the
    # E shadow fields (first cron after a cold clone or before the backfill re-runs).
    #
    # HARD CONSTRAINT: this field MUST NEVER be read by scoring, the composite,
    # pillar computation, veto/flag logic, fair-price, ``select_picks``, or
    # ``inverse_vol_weights``.  Written to ``Metadata`` ONLY.
    # Rankings/scores/flags are byte-identical.  Defense layer UNCHANGED at 36.
    #
    # Nullable on legacy snapshots (pre-0.10.40).
    hysteresis_turnover_reduction_mean_pp: float | None = None
    # ``low_liquidity_held_count`` — number of holdings in the FINAL backtest
    # rebalance leg's banded book that carry the ``low_liquidity`` annotate
    # (trailing-30d mean dollar volume < ADV_FLOOR_USD = $5M).
    # This is the capacity-constraint exposure count for the live AI-pick book.
    # Populated by reading ``backtest_pit.json`` (same artifact-read pattern).
    # None when the artifact is absent, unreadable, or has no final-leg
    # ``low_liquidity_holdings`` field.
    #
    # Flip-gate contribution: zero or near-zero across crons confirms the S&P 900
    # AI-pick basket is NOT exposed to sub-$5M ADV names (dormant on S&P 900;
    # may light up on S&P 1500 small-cap books — Amihud 2002 capacity, not alpha).
    #
    # HARD CONSTRAINT: same as ``hysteresis_turnover_reduction_mean_pp`` above.
    # Defense layer UNCHANGED at 36.  Nullable on legacy snapshots (pre-0.10.40).
    low_liquidity_held_count: int | None = None
    # ``div_pool_shadow_terminal_nav_delta_pct`` — A/B-diff canary for the
    # Option-B dividend-pool-and-redeploy SHADOW NAV series (issue #620,
    # schema 0.10.41-phase8pilot).
    #
    # Formula: 100 × (NAV_div_pooled_net[-1] / NAV_adaptive_net[-1] − 1)
    # i.e. the terminal NAV uplift (%) of the dividend-pooled shadow vs the
    # live ``nav.adaptive`` series.  Positive = dividends add value once
    # redeployed; near-zero = dividend yield immaterial at the basket level.
    #
    # Populated by reading ``backtest_pit.json`` after the PIT-backtest
    # refresh (same artifact-read pattern as C-2, C-1, and Proposal E).
    # None when the artifact is absent, unreadable, or has no
    # ``nav.adaptive_div_pooled`` key (first cron after a cold clone or
    # before the backfill re-runs).
    #
    # Methodology conditions (ratified by methodology-scientist):
    #   1. Idle cash earns 0% between rebalances (conservative floor).
    #   2. Sold-name conservation: ex-date dividends on names sold at
    #      rebalance are captured in the terminal-sub-period cash bucket
    #      before redeploy — no leakage.
    #   3. Shadow-first: live ``nav.adaptive`` is BYTE-IDENTICAL; the
    #      shadow flip is gated on ≥ 1 cron confirming a plausible delta.
    #
    # Adj-Close double-count footgun: Adj Close already embeds dividend
    # reinvestment; the Option-B path prices on RAW split-adjusted Close to
    # avoid double-counting (CLAUDE.md §Gotchas).
    #
    # HARD CONSTRAINT: this field MUST NEVER be read by scoring, the
    # composite, pillar computation, veto/flag logic, fair-price,
    # ``select_picks``, or ``inverse_vol_weights``.  Written to ``Metadata``
    # ONLY.  Rankings/scores/flags BYTE-IDENTICAL.  Defense layer UNCHANGED
    # at 36.  Nullable on legacy snapshots (pre-0.10.41).
    div_pool_shadow_terminal_nav_delta_pct: float | None = None
    # ``div_stream_coverage_pct`` — fraction of tickers in the CURRENT
    # ranked universe that have at least one ex-date dividend entry in the
    # ``fetch_dividends_panel`` output, expressed as a percentage (0–100).
    # Rule-18 coverage canary: until this field populates with a plausible
    # value (expected ~40–60% of S&P 1500 names pay dividends), the Option-B
    # shadow series must NOT be promoted to the headline.
    #
    # None when ``QR_SKIP_DIVIDENDS=1`` is set, or when the ``Dividends``
    # column is absent from ALL cached price frames (old parquets — first run
    # after a cache cold-seed bump will see None here; subsequent runs after
    # the cache warms will populate it).
    #
    # Same HARD CONSTRAINT as ``div_pool_shadow_terminal_nav_delta_pct``.
    # Nullable on legacy snapshots (pre-0.10.41).
    div_stream_coverage_pct: float | None = None
    # Issue #16 — restatement_history weight-demotion delta counter
    # (Q3 2026 cohort audit, 0.10.42-phase8pilot, Rule 18 observability-first).
    #
    # Shadow counter: the number of tickers whose ``composite_score_adjusted``
    # CHANGES due to the ``RESTATEMENT_HISTORY_WEIGHT`` demotion from 5.0 → 0.0.
    #
    # These are exactly the tickers carrying ``restatement_history`` in their
    # ``valuation_warnings`` but NOT ``restatement_high_confidence`` — i.e., the
    # "plain restater" cohort whose manipulation-index contribution drops by 5.0
    # points (from 5.0 to 0.0). The ~70%-PPV "irregularity" subset carries BOTH
    # flags; for those tickers the high-confidence weight rose 3.0→8.0 so the
    # combined irregularity total is preserved at 8.0 — net manipulation-index
    # delta = 0 for that subset. The counter therefore counts only the TRUE
    # delta population (plain restaters).
    #
    # Rationale for the demotion: on SP1500 the bare flag fires at ~17.82%
    # (~268 tickers) vs the Hennes-Leone-Miller 2008 *TAR* material prior of
    # 1-3%, meaning the ~70%-PPV fraud-class content (already carried by the
    # 0.27%-base-rate high-confidence sibling) does not justify the index budget
    # for the remaining ~70% of bare-flag fires (clerical-error amendments).
    # Methodology-scientist RATIFIED 2026-06-27 (issue #16).
    #
    # HARD CONSTRAINT: this field MUST NEVER be read by scoring, the composite,
    # pillar computation, veto/flag logic, fair-price, or ``select_picks``.
    # OBSERVABILITY-ONLY. Defense layer UNCHANGED at 36.
    #
    # Nullable on legacy snapshots (pre-0.10.42). None when the per-ticker
    # summaries loop was skipped or the helper failed (non-fatal try/except).
    restatement_history_weight_demote_delta_count: int | None = None

    # ------------------------------------------------------------------ #
    #  Phase 9.1 — Broad Investable US universe coverage probe            #
    #  (Rule 18 observability-before-wiring; issue #661 follow-up)        #
    # ------------------------------------------------------------------ #
    #
    # These six fields are the ONLY "broad_universe_*" fields that live in
    # the Pydantic ↔ TS ↔ snapshot triple.  They are emitted by
    # ``_run_broad_universe_probe`` in ``compute/main.py`` and sourced from
    # ``compute/ingest/broad_universe.py``.
    #
    # HARD NAMING CONSTRAINT (legal/trademark, 2026-06-29):
    #   Call this universe "Broad Investable US" everywhere.  NEVER use the
    #   strings "Russell 3000", "Russell-3000-class", or "equivalent to
    #   Russell 3000" in any field name, label, comment, or string that
    #   ships in the repo.
    #
    # HARD RULE 18 CONSTRAINT:
    #   All six fields MUST NEVER be read by scoring, composite, pillar
    #   computation, veto/flag logic, fair-price, or ``select_picks``.
    #   They feed ONLY the ``Metadata`` constructor.
    #   Rankings/scores/flags are BYTE-IDENTICAL whether or not the probe
    #   ran.  Defense layer is UNCHANGED at 36.
    #
    # Lifecycle:
    #   Phase 9.1 (this PR) — emits the six Metadata fields, no ranked
    #   names added (SP1500 cron unchanged).
    #   Phase 9.3 (future PR) — pending ≥ 1 cron confirming plausible
    #   values, broadens the ranked universe to the full screen-passing set.
    #
    # ``broad_universe_raw_count`` — total entries returned by
    # ``fetch_broad_universe_candidates`` BEFORE any screen (i.e. after
    # exchange + name/format exclusions that happen inside the fetcher).
    # Gives a baseline for how many names survive the static exclusions.
    # None when ``QR_SKIP_BROAD_UNIVERSE=1`` or when the probe errors.
    broad_universe_raw_count: int | None = None
    # ``broad_universe_candidate_count`` — same as ``raw_count`` on the
    # 9.1 Probe slice (the exchange + name/format exclusions are applied
    # inside the fetcher, so the DataFrame handed to the screen already
    # reflects them).  Kept as a separate field so a future slice can
    # expose pre-/post-exclusion counts independently.
    # None when the probe is skipped or errors.
    broad_universe_candidate_count: int | None = None
    # ``broad_universe_screened_count`` — number of tickers in the
    # candidate pool that pass BOTH the price >= $5 AND ADV >= $5M floors
    # using the Step-1 prices already in memory.
    #
    # NOTE: The 9.1 Probe reuses only the SP1500 prices already fetched in
    # Step 1.  Tickers outside the SP1500 that have no pre-fetched prices
    # are counted in ``coverage_pct`` but NOT counted towards the screened
    # pool here.  The absolute value will therefore be depressed relative
    # to the true screen-passing size until Phase 9.3 fetches prices for
    # the full candidate pool.  Use this field as a lower-bound estimate.
    # None when the probe is skipped or the screen cannot run.
    broad_universe_screened_count: int | None = None
    # ``broad_universe_price_fail_pct`` — percentage of candidates (with
    # price data available) whose last-close price was below
    # ``BROAD_UNIVERSE_PRICE_FLOOR_USD`` ($5).  Range 0–100.
    # None when the probe is skipped, or when no candidates had prices.
    broad_universe_price_fail_pct: float | None = None
    # ``broad_universe_adv_fail_pct`` — percentage of candidates (with
    # price data available and passing the price floor) whose trailing-30d
    # mean dollar volume was below ``ADV_FLOOR_USD`` ($5M, Amihud 2002
    # illiquidity family).  Range 0–100.
    # None when the probe is skipped, or when no candidates had prices.
    broad_universe_adv_fail_pct: float | None = None
    # ``broad_universe_coverage_pct`` — percentage of the candidate pool
    # for which the Step-1 prices dict held any price data.  On the 9.1
    # Probe, this will equal roughly SP1500 ∩ Broad-universe / Broad-
    # universe total — expected ~40–45% (SP1500 ~1504 / Broad ~3545).
    # Acts as a Rule-18 gate: once Phase 9.3 extends the price-fetch to
    # the full candidate pool, this should approach ~95%+.
    # None when the probe is skipped or the candidate pool is empty.
    broad_universe_coverage_pct: float | None = None

    # ------------------------------------------------------------------ #
    #  Phase 9.1 — Broad Investable US universe coverage probe            #
    #  (Rule 18 observability-before-wiring; issue #661 follow-up)        #
    # ------------------------------------------------------------------ #
    #
    # These six fields are the ONLY "broad_universe_*" fields that live in
    # the Pydantic ↔ TS ↔ snapshot triple.  They are emitted by
    # ``_run_broad_universe_probe`` in ``compute/main.py`` and sourced from
    # ``compute/ingest/broad_universe.py``.
    #
    # HARD NAMING CONSTRAINT (legal/trademark, 2026-06-29):
    #   Call this universe "Broad Investable US" everywhere.  NEVER use the
    #   strings "Russell 3000", "Russell-3000-class", or "equivalent to
    #   Russell 3000" in any field name, label, comment, or string that
    #   ships in the repo.
    #
    # HARD RULE 18 CONSTRAINT:
    #   All six fields MUST NEVER be read by scoring, composite, pillar
    #   computation, veto/flag logic, fair-price, or ``select_picks``.
    #   They feed ONLY the ``Metadata`` constructor.
    #   Rankings/scores/flags are BYTE-IDENTICAL whether or not the probe
    #   ran.  Defense layer is UNCHANGED at 36.
    #
    # Lifecycle:
    #   Phase 9.1 (this PR) — emits the six Metadata fields, no ranked
    #   names added (SP1500 cron unchanged).
    #   Phase 9.3 (future PR) — pending ≥ 1 cron confirming plausible
    #   values, broadens the ranked universe to the full screen-passing set.
    #
    # ``broad_universe_raw_count`` — total entries returned by
    # ``fetch_broad_universe_candidates`` BEFORE any screen (i.e. after
    # exchange + name/format exclusions that happen inside the fetcher).
    # Gives a baseline for how many names survive the static exclusions.
    # None when ``QR_SKIP_BROAD_UNIVERSE=1`` or when the probe errors.
    broad_universe_raw_count: int | None = None
    # ``broad_universe_candidate_count`` — same as ``raw_count`` on the
    # 9.1 Probe slice (the exchange + name/format exclusions are applied
    # inside the fetcher, so the DataFrame handed to the screen already
    # reflects them).  Kept as a separate field so a future slice can
    # expose pre-/post-exclusion counts independently.
    # None when the probe is skipped or errors.
    broad_universe_candidate_count: int | None = None
    # ``broad_universe_screened_count`` — number of tickers in the
    # candidate pool that pass BOTH the price >= $5 AND ADV >= $5M floors
    # using the Step-1 prices already in memory.
    #
    # NOTE: The 9.1 Probe reuses only the SP1500 prices already fetched in
    # Step 1.  Tickers outside the SP1500 that have no pre-fetched prices
    # are counted in ``coverage_pct`` but NOT counted towards the screened
    # pool here.  The absolute value will therefore be depressed relative
    # to the true screen-passing size until Phase 9.3 fetches prices for
    # the full candidate pool.  Use this field as a lower-bound estimate.
    # None when the probe is skipped or the screen cannot run.
    broad_universe_screened_count: int | None = None
    # ``broad_universe_price_fail_pct`` — percentage of candidates (with
    # price data available) whose last-close price was below
    # ``BROAD_UNIVERSE_PRICE_FLOOR_USD`` ($5).  Range 0–100.
    # None when the probe is skipped, or when no candidates had prices.
    broad_universe_price_fail_pct: float | None = None
    # ``broad_universe_adv_fail_pct`` — percentage of candidates (with
    # price data available and passing the price floor) whose trailing-30d
    # mean dollar volume was below ``ADV_FLOOR_USD`` ($5M, Amihud 2002
    # illiquidity family).  Range 0–100.
    # None when the probe is skipped, or when no candidates had prices.
    broad_universe_adv_fail_pct: float | None = None
    # ``broad_universe_coverage_pct`` — percentage of the candidate pool
    # for which the Step-1 prices dict held any price data.  On the 9.1
    # Probe, this will equal roughly SP1500 ∩ Broad-universe / Broad-
    # universe total — expected ~40–45% (SP1500 ~1504 / Broad ~3545).
    # Acts as a Rule-18 gate: once Phase 9.3 extends the price-fetch to
    # the full candidate pool, this should approach ~95%+.
    # None when the probe is skipped or the candidate pool is empty.
    broad_universe_coverage_pct: float | None = None


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
    # Issue #374 (RATIFY-B, 2026-06-11) — listed line's own per-class share
    # count extracted from per-filing XBRL (e.g., GOOG Class C = 5.43B, GOOGL
    # Class A = 5.82B).  Company-total common shares across ALL classes live
    # in ``shares_outstanding`` above (the SEC companyfacts aggregate).
    # Checksum/display only — no scoring consumer reads this field.
    # On warm-cache crons the value may be None or reflect the class of
    # whichever ticker last wrote the CIK-keyed parquet (harmless; see
    # compute/ingest/fundamentals.py §CIK-keyed-parquet caveat).
    shares_outstanding_listed_class: float | None = None
    # Post-split share-lag defense (defense layer 35, 0.10.25-phase8pilot).
    # Preserves the RAW EDGAR ``shares_outstanding`` BEFORE the Tier-1
    # correction is applied (Rule 9 — audit trail).  Non-null only when
    # ``post_split_share_lag`` is in ``valuation_warnings`` (Tier-1 correct
    # path — PR-2 fix 2026-06-18: moved from risk_flags to valuation_warnings
    # so Tier-1-corrected tickers are not excluded from entered_top5);
    # always ``None`` on normal / Tier-2 / no-split rows.
    # The corrected value lives in ``shares_outstanding`` (where all
    # scoring consumers naturally read it after main.py writes it back
    # to the snapshot object).
    shares_outstanding_pre_split_raw: float | None = None
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
    # Listing metadata (0.10.12-phase4.6) — `exchange` is the human display
    # name mapped from the yfinance `fast_info.exchange` code (NMS→NASDAQ,
    # NYQ→NYSE, …) by `cross_source.exchange_name`; `country` is derived from
    # the exchange ("US" for the whole S&P 500 universe today) by
    # `cross_source.country_for_exchange`. Both `| None` — a ticker whose
    # exchange code didn't resolve (cold-cache miss / unknown venue) renders
    # no listing tag. Display-only; feeds the hero country/exchange chips.
    exchange: str | None = None
    country: str | None = None
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
    # Phase 8 pilot PR 3a — S&P 900 integration seam (0.10.21-phase8pilot).
    # Mirrors StockSummary.index_membership. Default "sp500" so legacy /
    # sp500-path per-stock JSONs deserialize under extra="forbid" unchanged.
    index_membership: str = "sp500"
    # Multi-index membership — Dow 30 / NDX 100 overlap tabs (0.10.23-phase8pilot).
    # Mirrors StockSummary.index_memberships. Default empty list so legacy
    # per-stock JSONs (pre-0.10.23) deserialize cleanly under extra="forbid".
    index_memberships: list[str] = Field(default_factory=list)
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
    # Dividend signal PR-1 (roadmap item #5 / 7a — observability-first,
    # Rule 18, 0.10.27-phase8pilot).  Display-only descriptive metadata;
    # does NOT feed the composite score, any pillar, or any defense flag.
    # Defense layer UNCHANGED at 35.
    #
    # ``dividend_yield_pct`` — annualised dividend yield expressed as a
    # PERCENT (e.g. 2.0 for 2%).  Sourced from yfinance ``.info``
    # ``dividendYield`` (a fraction) × 100.  Zero means the ticker
    # actively pays no dividend (confirmed by yfinance); ``None`` means
    # the data was unavailable.
    #
    # ``pays_dividend`` — ``True`` iff ``dividend_yield_pct > 0``;
    # ``False`` iff ``dividend_yield_pct == 0.0``; ``None`` when yield
    # is unavailable.  The tri-state lets the frontend distinguish
    # "confirmed non-payer" from "data missing".
    #
    # ``payout_ratio`` — yfinance ``.info`` ``payoutRatio`` (0-1
    # fraction; ``None`` when absent or non-positive).  The ratio is NOT
    # converted to percent — callers multiply by 100 for display.
    # Populated only when the underlying yfinance field is present and
    # non-negative; many growth stocks have NaN / None here.
    #
    # All three fields default to ``None`` so legacy per-stock JSONs
    # (pre-0.10.27) deserialise cleanly under ``extra="forbid"``.
    # Source: ``compute/ingest/cross_source.fetch_yfinance_dividend``
    # (pure cache-read off the warm ``yfinance_info/<ticker>.json``
    # populated earlier in the Step-8 cross-source loop — zero new
    # network round-trips).
    dividend_yield_pct: float | None = None
    pays_dividend: bool | None = None
    payout_ratio: float | None = None
    # S&P 1500 Slice 4 — ADV liquidity backstop (defense layer 36,
    # 0.10.29-phase8pilot, ANNOTATE-ONLY per Rule 16).
    #
    # ``average_dollar_volume`` — trailing-30-day mean of (close × volume)
    # in USD.  Sourced from ``compute.ingest.prices.compute_average_dollar_volume``
    # over the OHLCV DataFrame already cached during the Step-1 prices loop.
    # No new network round-trips; derived purely from the existing price cache.
    #
    # ``None`` when the price DataFrame was unavailable, empty, or missing
    # a Close / Volume column — graceful degradation per Rule 18 (cron never
    # blocks on a failed ADV computation).
    #
    # Academic anchor: Amihud 2002 *J. Financial Markets* §2 — dollar volume
    # < $5M/day places a stock in the bottom decile of the US-equity Amihud
    # illiquidity measure; microstructure noise dominates any fundamental
    # signal at this scale.
    #
    # The corresponding ``low_liquidity`` flag in ``valuation_warnings``
    # (emitted in ``compute.main`` per-ticker loop when
    # ``average_dollar_volume is not None and average_dollar_volume <
    # config.ADV_FLOOR_USD``) is ANNOTATE-ONLY: it does NOT set ``cautious``,
    # does NOT suppress Top-5, does NOT null fair-price, and does NOT change
    # the composite score.  Veto promotion is gated on ≥ 1 cron of
    # firing-rate data + methodology ratification (WORKFLOW.md §8.6).
    average_dollar_volume: float | None = None
    # Security-type signal PR-1 (roadmap item #5 / 7b — observability-first,
    # Rule 18, 0.10.31-phase8pilot).
    #
    # ``security_type`` — categorical label describing the instrument type:
    # ``"Common stock"`` / ``"ADR"`` / ``"ETF"`` / ``"REIT"`` /
    # ``"Preferred"`` / ``"Fund"`` / ``"Index"`` etc.  Sourced from
    # ``yfinance.Ticker(t).fast_info.quote_type`` via a pure cache-read off
    # the ``yfinance_info/<ticker>.json`` file populated by
    # ``fetch_yfinance_exchange`` during the Step-8 cross-source loop
    # (zero new network round-trips — ``quote_type`` is captured alongside
    # ``exchange`` in the same ``fast_info`` call).
    #
    # Unknown yfinance codes are passed through verbatim (forward-safe —
    # same philosophy as the exchange-code map).
    #
    # ``None`` when the ``yfinance_info`` cache was cold, the field was
    # absent from ``fast_info``, or the fetch failed (graceful degradation
    # per ``portable-graceful-degradation-try-except``).
    #
    # **DESCRIPTIVE METADATA ONLY — NOT a scoring input.** This field does
    # NOT influence the composite score, risk_flags, recommendation, or any
    # defense flag.  It is display information for the stock-detail hero
    # tile (roadmap item #5 / 7b, issue #541).  All legacy per-stock JSONs
    # (pre-0.10.31) deserialise cleanly under ``extra="forbid"`` because
    # the field defaults to ``None``.
    # Source: ``compute/ingest/cross_source.fetch_yfinance_security_type``
    # (pure cache-read; the ``quote_type`` value is written as a side-channel
    # during ``fetch_yfinance_exchange``'s ``_yf_fast_exchange`` call).
    security_type: str | None = None
