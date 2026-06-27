"""Smoke tests for compute.config constants.

Locks the values of Tier-2 defense constants (PR 3d Step 1) so an
accidental edit surfaces as a test failure rather than silent drift
into production.
"""

from __future__ import annotations

from compute import config


def test_schema_version_pinned():
    """Phase 4.5e PR 6 (0.10.11-phase4.6, 2026-05-28) — PATCH bump for
    the new ``Metadata.form4_negation_guard_downgrade_count: int | None``
    field. Tracks the universe-wide count of True → False downgrades
    applied by the post-detector 10b5-1 negation guard during Form-4
    cache build (residual footgun #1 from PR 4-eq). Pre-PR-4-eq Mode B
    verdict (2026-05-23) pre-approved the hardening; PR 6 implements
    the engineering: an 8-pattern bidirectional ±5-token regex wrapping
    ``edgar.ownership.core.detect_10b5_1_plan`` that downgrades a True
    detection to False when the resolved footnote text contains a
    negation phrase (``terminated`` / ``cancelled`` / ``no`` /
    ``previously`` / ``former`` / etc.) within ±5 word tokens of the
    10b5-1 mention. Gates the Q3 2026-08-19 cohort-acceptance check
    (issue #130) for the ``INSIDER_SELL_CLUSTER_WEIGHT`` 5.0 → 7.0
    promotion alongside ``form4_rule10b5_one_excluded_count``.
    Supersedes Issue #67 follow-up's 0.10.10-phase4.6 bump.

    PR-A1 (0.10.12-phase4.6) — MINOR bump for the additive listing-metadata
    fields: ``StockDetail.exchange`` + ``StockDetail.country`` (yfinance
    ``fast_info.exchange`` → display name + derived country) and the Rule-18
    observability field ``Metadata.exchange_coverage_pct``. Display-only;
    frontend wiring (hero country/exchange chips) lands in PR-B after ≥ 1 cron
    confirms coverage (observability-before-wiring).

    Listing-metadata canary (0.10.13-phase4.6, 2026-06-02 post-cron audit) —
    PATCH bump for the additive ``Metadata.country_coverage_pct: float | None``.
    The 0.10.12 design assumed country tracked exchange 1:1; the audit
    disproved it (CBOE's ``BTS`` code passed through as exchange but resolved
    to no country → exchange 100% / country 99.8%). The new field is the
    strict-resolution canary, paired with the ``BTS → Cboe BZX`` fix in
    ``cross_source._EXCHANGE_NAME_BY_CODE`` and a main.py divergence WARNING.
    Locks the version against accidental revert.

    PR-1 (0.10.14-phase4.6) — Phase 7.0 PR-1 PATCH bump for the additive
    ``Metadata.benchmark_coverage_pct`` (benchmark index export observability;
    SPY/QQQ/DIA/IWM → portfolio/benchmarks.json).

    Phase 4j.1 (0.10.15-phase4.6) — PATCH bump for the additive Qlib
    Alpha158 observability surface: 9 ``Metadata.alpha158_*`` fields
    (features_used / excluded_features / features_ic_12m /
    features_missing_from_compute / features_dropped_no_long_short /
    gate_diagnostics [reuses ``OsapGateDiagnostic``] / coverage_pct /
    survivorship_bias_corrected / wall_clock_seconds). Observability-only
    (Rule 18) — the feature→long-short-return adapter + the reused
    PBO/DSR gate are wired but blend NOTHING (``composite_score``
    unchanged, Δscore = 0); the rank-influencing blend is deferred to
    4j.2.

    Issue #441 close-out (0.10.17-phase4.6) — MAD factor REMOVED after
    pre-registered acceptance gate failure (rho=0.834/0.807 vs 0.30
    threshold — momentum echo; methodology-scientist RATIFY-REMOVE).
    ``mad_scalefree`` + ``mad_diagnostics`` + the 3 ``Metadata.mad_*``
    fields + the dead ``macd_hist`` pillar slot are deleted. Schema
    bumped 0.10.16 → 0.10.17 (breaking removal → PATCH under the
    additive-only MINOR convention).

    Issue #374 (0.10.18-phase4.6) — RATIFY-B dual-class share-count fix.
    Additive ``RawMetrics.shares_outstanding_listed_class`` field (the
    listed line's own per-class count); ``shares_outstanding`` reverts to
    the SEC companyfacts company-total aggregate (ASC 260, class-invariant,
    so the CIK-keyed parquet cache can no longer corrupt it). PATCH bump
    per the additive-optional-field convention.

    Phase 8 pilot PR 1 (0.10.19-phase8pilot) — S&P 900 universe expansion
    observability slice (Rule 18). Adds four additive nullable Metadata
    fields for the diagnostic coverage probe over the 400 mid-cap cohort:
    ``universe_cohort_sizes``, ``midcap_fundamentals_coverage_pct``,
    ``midcap_null_rate_pct``, ``midcap_cik_resolution_pct``. All None on
    the default sp500 path; populated only when QR_UNIVERSE=sp900.
    Ranked output (rankings.json + stocks/*.json) is byte-identical to a
    500 run — the probe is a separate loop that does NOT feed the writer.

    Issue #75 §3 (0.10.20-phase4.6) — IC-decay monitor production wiring.
    Additive ``Metadata.decay_report_url: str | None`` (URL of the
    ``/data/decay_report.json`` IC-decay artifact), layered on top of
    #479's 0.10.19-phase8pilot. PATCH bump per the additive-optional-field
    convention.

    Phase 8 pilot PR 3a (0.10.21-phase8pilot) — S&P 900 integration seam.
    Adds additive ``index_membership: str = "sp500"`` to ``StockSummary`` +
    ``StockDetail`` (default "sp500" so legacy sp500 JSONs deserialise under
    ``extra="forbid"`` unchanged). Restores the ``-phase8pilot`` label
    (reverted by #479's 0.10.20 bump). PATCH bump per the additive-field
    convention.

    OZK/PBF flip-blocker (0.10.22-phase8pilot) — new ``fundamentals_unavailable``
    direct veto in ``compute_risk_flags`` (fires when ``snap is None``;
    FP rate structurally zero; DQIC issue #18 governing precedent) + its
    Rule-18 counter ``Metadata.fundamentals_unavailable_count: int | None``.
    Additive PATCH bump.

    Multi-index membership (0.10.23-phase8pilot) — additive
    ``index_memberships: list[str]`` on ``StockSummary`` + ``StockDetail``.
    Contains the primary cohort code ("sp500" | "sp400") PLUS "dow30" /
    "ndx" for Dow 30 / Nasdaq-100 overlap members.  Default
    ``default_factory=list`` so legacy JSONs (pre-0.10.23) deserialize
    cleanly under ``extra="forbid"``.  ``index_membership`` (singular)
    is kept unchanged — MidcapChip + the membership-ledger script depend
    on it as the sp500/sp400 partition.  Additive PATCH bump.

    Issue #177 PR-A (0.10.24-phase8pilot) — shadow observability-first
    trimmed-median. Adds ``Metadata.median_trim_delta_count`` (int | None):
    count of universe tickers whose MoS SIGN would flip under the shadow
    trimmed median vs the live median. Diagnostic only; live mos_pct is
    byte-identical. Also adds ``EnsembleResult.median_trimmed`` +
    ``EnsembleResult.methods_excluded_from_median`` diagnostic fields.

    PR-2 (0.10.25-phase8pilot) — post-split share-lag defense (defense layer 35).
    Adds four new fields:
    - ``Metadata.post_split_share_lag_count: int | None`` — tickers where the
      flag fired (either tier); equals correction_applied + veto.
    - ``Metadata.post_split_correction_applied_count: int | None`` — Tier-1
      (CORRECT) subset: split confirmed + ratio reconciled → shares corrected.
    - ``Metadata.post_split_veto_count: int | None`` — Tier-2 (VETO) subset:
      split confirmed but ratio unreconcilable → cautious + Top-5 suppression.
    - ``RawMetrics.shares_outstanding_pre_split_raw: float | None`` — the raw
      EDGAR share count before the Tier-1 correction (Rule 9 audit trail);
      non-null only when the Tier-1 correction applied (``post_split_share_lag``
      annotate in ``valuation_warnings``, NOT ``risk_flags``).

    S&P 1500 cutover Slice 2 (0.10.28-phase8pilot, Rule 18
    observability-before-wiring) — adds three additive nullable
    ``Metadata`` fields for the sp600 small-cap coverage diagnostic probe.
    Populated ONLY when ``QR_UNIVERSE=sp1500``; None on the default
    sp900/sp500 paths.  Rankings are byte-identical on non-sp1500 paths.
    Also wires the ``sp1500`` branch in ``run_weekly_compute`` (universe
    seam) + ``_run_smallcap_coverage_probe()`` helper.  sp600 is
    PROBE-ONLY — filtered out of the scored frame (label ``SP1500-probe``);
    no ranked sp600 exposure until a later slice (gated on ≥ 1 cron of
    coverage data).

    New ``Metadata`` fields (additive PATCH bump; backward-compatible):
    - ``Metadata.smallcap_fundamentals_coverage_pct: float | None`` — % of
      sp600 tickers for which ``fetch_fundamentals`` returned non-null.
    - ``Metadata.smallcap_null_rate_pct: float | None`` — complement of
      the above (coverage + null_rate ≈ 100%, small float-rounding allowed).
    - ``Metadata.smallcap_cik_resolution_pct: float | None`` — % of sp600
      tickers whose CIK was resolved (either from Wikipedia or via
      ``Company(ticker).cik``).

    S&P 1500 Slice 4 (0.10.29-phase8pilot, Rule 16 annotate-before-veto +
    Rule 18 observability-before-wiring) — ADV liquidity backstop (defense
    layer 36, ANNOTATE-ONLY).  Adds two additive nullable fields:
    - ``Metadata.low_liquidity_annotate_count: int | None`` — universe-wide
      count of tickers where the ``low_liquidity`` annotate fired (trailing-
      30-day mean dollar volume < $5M ADV floor).  Expected near-zero for
      S&P 900 (large-caps clear $5M/day comfortably); designed for S&P 1500
      small-cap exposure.  ANNOTATE-ONLY: no cautious, no Top-5 suppression,
      no fair-price null, no composite change.
    - ``StockDetail.average_dollar_volume: float | None`` — trailing-30-day
      mean of (close × volume) in USD.  Sourced from the existing price cache;
      zero new network round-trips.  Graceful degradation to None when the
      price DataFrame is unavailable or missing Close/Volume column.

    Proposal D (0.10.36-phase8pilot, market-regime diagnostic, 2026-06-25) —
    two additive nullable ``Metadata`` fields (``market_breadth_above_200dma_pct``
    / ``market_regime_state``); WRITE-ONLY / OBSERVABILITY-ONLY (Rule 18,
    Welch-Goyal 2008 rejection-as-tilt); seeds future Phase-7 Student-t HMM;
    live rankings/scores/flags byte-identical; defense layer UNCHANGED at 36.

    Proposal A shrinkage composite (0.10.37-phase8pilot, issue #605, 2026-06-25)
    — 6 additive nullable ``Metadata`` fields for the Timmermann (2006) +
    Grinold-Kahn (2000) shrinkage weight-blending layer:
    ``shrinkage_lambda`` / ``shrinkage_lambda_applied`` /
    ``ic_weight_by_pillar`` / ``shrinkage_blended_weight_by_pillar`` /
    ``n_preliminary_pillars`` / ``shrinkage_weights_degenerate``.
    SHADOW / OBSERVABILITY-ONLY at launch (``SHRINKAGE_LAMBDA_PIN=1.0`` identity
    guard); live rankings/composite byte-identical; defense UNCHANGED at 36.
    Pin-lift gate requires A3-i/A3-ii OOS horse-race + methodology-scientist
    RATIFY-PROCEED.

    Proposal E turnover / hysteresis diagnostic + liquidity capacity tilt
    (0.10.40-phase8pilot, 2026-06-26) — 2 additive nullable ``Metadata``
    fields (SHADOW / OBSERVABILITY-ONLY, Rule 18):
    ``hysteresis_turnover_reduction_mean_pp: float | None`` — mean per-rebalance
    turnover-reduction (pp) of the hysteresis band vs the stateless counterfactual
    over ALL backtest legs. Positive values confirm the band reduces churn.
    H1 gate (pre-registered): mean >= 15pp over >= 4 live rebalances (Garleanu-
    Pedersen 2013 *JF* 68(6)).
    ``low_liquidity_held_count: int | None`` — count of low-liq holdings in the
    FINAL backtest rebalance leg's banded book. Capacity-constraint exposure canary
    (Amihud 2002 *JFM* 5(1)). None when artifact absent / unreadable.
    New pure functions: ``book_turnover(curr, prev) -> float`` (symmetric-diff
    name-count turnover) + ``liquidity_capacity_tilt(base, low_liq_tickers)``
    (haircut ×0.5 PRE-renorm → renorm → iterative pin-redistribute re-cap).
    Live band_book / NAV / rankings / scores / flags BYTE-IDENTICAL. Defense
    layer UNCHANGED at 36. ``LIQ_CAPACITY_TILT = 0.5`` constant pin.

    Proposal C-1 high-conviction gate counter (0.10.39-phase8pilot, 2026-06-26)
    — 3 additive nullable ``Metadata`` fields for the marginal-bite denominator
    of the loss-chance leg in the high-conviction gate:
    ``high_conviction_count: int | None`` — stocks clearing ALL 5 HC legs
    (is_eligible + rec ∈ {bullish, lean_bullish} + MoS > 0 + composite ≥ 50 +
    loss_chance ≤ 45); ``high_conviction_ex_loss_chance_count: int | None`` —
    stocks passing ONLY legs 1-4 (loss-chance leg OMITTED; ≥ hc_count always;
    the marginal-bite denominator: bite = ex − hc; corrected from tautological
    field ``high_conviction_mos_positive_count`` by methodology-scientist
    2026-06-26); ``high_conviction_below_floor: bool | None`` — True if ANY
    rebalance leg in ``backtest_pit.json`` has
    eligible_high_conviction_count < 5 (ADAPTIVE_MIN_PICKS); None when artifact
    is absent or unreadable. SHADOW / OBSERVABILITY-ONLY (Rule 18); defense
    UNCHANGED at 36; live rankings/scores byte-identical.

    Proposal C-2 MoS conviction tilt (0.10.38-phase8pilot, 2026-06-26) —
    1 additive nullable ``Metadata`` field:
    ``mos_tilt_shadow_max_delta_pp: float | None`` — the maximum per-rebalance
    ``max_t |mos_tilted_weight_t − base_weight_t| × 100`` across ALL rebalance
    legs in the refreshed ``backtest_pit.json`` artifact. Cross-universe canary
    for κ=0.25 calibration. SHADOW / OBSERVABILITY-ONLY (Rule 18); live NAV
    path byte-identical; defense UNCHANGED at 36. Nullable on legacy snapshots
    (pre-0.10.38); None when the ``backtest_pit.json`` artifact is absent.

    IC half-life monitor (0.10.35-phase8pilot, Proposal F, issue #604) — two
    additive nullable ``Metadata`` fields (``pillar_ic_half_life_months`` /
    ``pillar_ic_decay_fit_model``); SHADOW / OBSERVABILITY-ONLY (Rule 18),
    live rankings/scores byte-identical, defense layer UNCHANGED at 36.

    value_trap_risk two-factor LIVE gate flip (0.10.34-phase8pilot, issue #586
    PR-2) — NO new schema fields (only version bump).  The LIVE
    ``value_trap_risk`` warning is flipped from the single-leg ROE<=Ke gate
    to the methodology-ratified two-factor LSV gate (first sp1500 cron
    confirmed shadow count = 155 / 10.3% of 1504, squarely in the 5-12%
    LSV 1994 band).  The live warning now fires iff: (a) ROE<=Ke AND (b)
    eps_ttm > 0 AND (c) ticker P/E < sector-peer median P/E.  Loss-making
    firms are EXEMPT.  ``value_trap_risk_two_factor_shadow_count`` now equals
    the live count; kept for one more cron as a structural cross-check.
    Expected live count ~155 (was ~548 under single-leg).

    Prior version (0.10.33-phase8pilot, issue #586 PR-1): two-factor shadow
    counter (``Metadata.value_trap_risk_two_factor_shadow_count``); SHADOW
    ONLY; live single-leg emission byte-identical.

    Prior version (0.10.32-phase8pilot, issue #587): ``extreme_estimate_majority``
    low-applicability floor shadow counter (``Metadata.extreme_estimate_majority_
    lowapp_count``) — RE-BASE-WITH-FLOOR recalibration; annotate-only, defense
    layer UNCHANGED at 36.

    Security-type signal PR-1 (0.10.31-phase8pilot, roadmap item #5 / 7b,
    Rule 18 observability-first) — adds two additive nullable fields:
    - ``Metadata.security_type_coverage_pct: float | None`` — % of the ranked
      universe with a non-null ``StockDetail.security_type`` after the Step-8
      per-ticker loop.  Coverage canary modelled on ``dividend_coverage_pct``.
    - ``StockDetail.security_type: str | None`` — categorical label from
      yfinance ``fast_info.quote_type`` (e.g. ``"Common stock"`` / ``"ETF"``).
      Descriptive metadata only — NOT a scoring input, NOT a defense flag.

    Prior version (0.10.30-phase8pilot): Bonferroni multi-test shadow counter
    (issue #542, Slice 8, Rule 18 observability-before-wiring) — SHADOW /
    OBSERVABILITY-ONLY.  Adds three additive nullable ``Metadata`` fields
    (``bonferroni_shadow_flip_count`` / ``bonferroni_shadow_live_fire_count`` /
    ``bonferroni_shadow_provisional_fire_count``).  Live scores, flags, and
    rankings are byte-identical.  Methodology-scientist must review first cron
    counts before any threshold promotion.
    Before that (0.10.29-phase8pilot): S&P 1500 Slice 4 ADV liquidity backstop.
    Before that (0.10.28-phase8pilot): S&P 1500 Slice 2 smallcap probe.
    Before that (0.10.27-phase8pilot, #512): Dividend-signal observability.
    Before that (0.10.26, #501): four shadow
    ``Metadata.cross_source_corruption_*`` fields (SHADOW ONLY)."""
    assert config.SCHEMA_VERSION == "0.10.41-phase8pilot"


def test_multi_class_overcount_allowlist_membership():
    """Issue #261 PR-B (0.10.6-phase4.5e) — pin the per-class XBRL
    extraction allowlist that gates the new overcount-path elif branch
    in ``compute/ingest/fundamentals.py::_build_snapshot``.

    Verified 2026-05-26 by edgar-debugger live probe on Alphabet 10-K
    accession ``0001652044-26-000018``:
    - GOOGL → us-gaap:CommonClassAMember (standard namespace, 5.822B shares)
    - GOOG → goog:CapitalClassCMember (FILER-SPECIFIC namespace gotcha,
      5.429B shares; an allowlist keyed to the standard us-gaap:
      namespace would silently return zero rows and let the overcount
      through)

    Adding a ticker without a live XBRL probe to confirm the exact
    namespace + member string is a regression risk (would silently
    fail the filter, leaving the aggregate-shape primary in place).
    Quarterly cohort audit 2026-08-19 is the canonical expansion
    venue."""
    expected = {
        "GOOGL": "us-gaap:CommonClassAMember",
        "GOOG": "goog:CapitalClassCMember",
    }
    assert config.MULTI_CLASS_OVERCOUNT_ALLOWLIST == expected


def test_overcount_and_undercount_allowlists_disjoint():
    """Issue #261 PR-B — the two allowlists encode opposite mechanisms
    (UNDERCOUNT sum-all vs OVERCOUNT per-class-filter). A ticker cannot
    plausibly be on both since the share-structure-extraction problem
    is direction-specific. Pin the disjoint invariant so a future PR
    can't accidentally add the same ticker to both paths."""
    overlap = config.MULTI_CLASS_OVERCOUNT_ALLOWLIST.keys() & config.MULTI_CLASS_SHARE_ALLOWLIST
    assert overlap == set(), f"Allowlists overlap: {overlap}"


def test_multi_class_share_allowlist_membership():
    """Issue #248 PR2b (0.10.4-phase4.5e) — pin the multi-class share-
    structure allowlist that gates the per-filing XBRL dimensional override
    path in ``compute/ingest/fundamentals.py::_build_snapshot``.

    Verified 2026-05-25 by edgar-debugger via EPS cross-check on production
    output: V (4.5x undercount), NWS/NWSA (1.56x), FOX/FOXA (2.2x), BRK-B
    (1300x — Class A weighting deferred to Q3 2026-08-19 cohort audit),
    STZ (already handled by None-trigger path; included for completeness).

    GOOG/GOOGL deliberately excluded — they file non-dimensionally so
    companyfacts returns the correct total. Adding them would be a no-op
    HTTP cost.

    Adding a ticker without an EPS cross-check verification is a regression
    risk (false override of a single-class issuer). Quarterly cohort audit
    is the canonical expansion venue."""
    assert config.MULTI_CLASS_SHARE_ALLOWLIST == frozenset(
        {"V", "NWS", "NWSA", "STZ", "FOX", "FOXA", "BRK-B"}
    )


def test_form4_lookback_days_is_180():
    """Phase 4.5e PR 2 — Form-4 fetch lookback. 2026-05-22 hotfix
    dropped from 365 to 180 days to fit the 45-min cron budget on
    cold cache; Cohen-Malloy-Pomorski 2012 §3.1 used parallel
    6m / 12m windows so 180d (≈ 6m) remains literature-anchored.
    PR 3 will wire the scoring signal once a per-filing cache lands
    that lets us restore the longer window safely."""
    assert config.FORM4_LOOKBACK_DAYS == 180


def test_extreme_majority_threshold_at_huber_breakdown_point():
    """Issue #177 — for a 6-sample median the Huber 1981 §1.4 breakdown
    point is ⌊5/2⌋ = 2 outliers; the majority annotate must fire at the
    NEXT integer (3) so the median has actually passed breakdown when
    the flag fires. Locks the threshold against gut-feel drift."""
    assert config.EXTREME_MAJORITY_THRESHOLD == 3


def test_eight_k_lookback_veto_is_one_year():
    assert config.EIGHT_K_LOOKBACK_DAYS_VETO == 365


def test_eight_k_lookback_annotate_is_two_years():
    assert config.EIGHT_K_LOOKBACK_DAYS_ANNOTATE == 730


def test_going_concern_filing_lookback_is_one_year_plus_buffer():
    assert config.GOING_CONCERN_FILING_LOOKBACK_DAYS == 400


def test_eight_k_annotate_window_outlasts_veto_window():
    """Annotate (auditor change) window must be >= veto (non-reliance)
    window — the rationale is that we want to surface a 4.01 disclosure
    even after a 4.02 veto would have lapsed."""
    assert (
        config.EIGHT_K_LOOKBACK_DAYS_ANNOTATE
        >= config.EIGHT_K_LOOKBACK_DAYS_VETO
    )


def test_use_sector_coe_flipped_true():
    """Issue #67 (2026-05-28) — `USE_SECTOR_COE` flipped True after
    methodology-scientist Mode B verdict + cron #69 empirical
    confirmation (`value_trap_risk_count_with_sector_coe = 109` vs
    `_without_sector_coe = 132`, 17.4% reduction landing within the
    original target band [80, 110]). The 11-sector GICS Ke table at
    `compute/scoring/cost_of_equity.py::SECTOR_COST_OF_EQUITY` (Damodaran
    2019 Ch. 8.4 + NYU January 2025 dataset, LITERATURE-ANCHORED per
    PR #204) replaces the flat `COST_OF_EQUITY = 0.10` at the RIM
    applicability check.

    Flipping back to False requires a separate methodology-scientist
    Mode B verdict (load-bearing default; not a feature toggle).
    Pin protects against accidental revert."""
    assert config.USE_SECTOR_COE is True


# ---------------------------------------------------------------------------
# Post-split share-lag defense constants (PR-2, defense layer 35).
#
# These three constants are METHODOLOGY-FROZEN per the pre-registration ruling
# (methodology-scientist 2026-06-18).  Citations:
#   POST_SPLIT_WINDOW_DAYS  — CRSP CFACSHR / Damodaran 2019 *Investment
#       Valuation* 3rd ed. Ch. 16: one missed 10-Q/A cycle = 45-day EDGAR
#       refetch cadence × 2 quarters + buffer → 100 days.
#   POST_SPLIT_MIN_RATIO    — 2:1 materiality floor; prevents noise from
#       rounding-lot adjustments (Damodaran 2019 Ch. 16).
#   POST_SPLIT_RATIO_TOLERANCE — 10% tolerance on yf/EDGAR ratio-match for
#       Tier-1 (CORRECT) vs Tier-2 (VETO) classification.
#
# A silent retune of any of these constants MUST trip CI.  Changing them
# requires a new methodology-scientist Mode B ruling + METHODOLOGY.md update.
# ---------------------------------------------------------------------------

def test_post_split_window_days_is_100():
    """POST_SPLIT_WINDOW_DAYS = 100 (methodology-frozen pre-registration constant).

    Covers one missed 10-Q/A EDGAR refetch cycle (45-day cadence × 2 + buffer).
    Changing this without a methodology-scientist ruling must fail CI.
    """
    assert config.POST_SPLIT_WINDOW_DAYS == 100


def test_post_split_min_ratio_is_2():
    """POST_SPLIT_MIN_RATIO = 2.0 (methodology-frozen pre-registration constant).

    Only material splits (≥ 2:1) trigger the defense; prevents noise from
    tiny rounding-lot adjustments.  Changing this without a methodology-
    scientist ruling must fail CI.
    """
    assert config.POST_SPLIT_MIN_RATIO == 2.0


def test_post_split_ratio_tolerance_is_10_pct():
    """POST_SPLIT_RATIO_TOLERANCE = 0.10 (methodology-frozen pre-registration constant).

    The yfinance-implied share count must match EDGAR × split_ratio to within
    10% for Tier-1 (CORRECT) classification; outside this band → Tier-2 (VETO).
    Changing this without a methodology-scientist ruling must fail CI.
    """
    assert config.POST_SPLIT_RATIO_TOLERANCE == 0.10


def test_post_split_constants_are_consistent():
    """Cross-constant sanity: window > 0, min_ratio >= 2, 0 < tolerance < 1.

    Structural invariants — any combination violating these is incoherent
    regardless of the individual constant values.
    """
    assert config.POST_SPLIT_WINDOW_DAYS > 0, (
        "POST_SPLIT_WINDOW_DAYS must be positive"
    )
    assert config.POST_SPLIT_MIN_RATIO >= 2.0, (
        "POST_SPLIT_MIN_RATIO must be >= 2.0 (materiality floor)"
    )
    assert 0.0 < config.POST_SPLIT_RATIO_TOLERANCE < 1.0, (
        "POST_SPLIT_RATIO_TOLERANCE must be in (0, 1)"
    )


# ---------------------------------------------------------------------------
# Proposal A shrinkage composite (0.10.37-phase8pilot, issue #605).
#
# Six additive nullable Metadata fields for the Timmermann (2006) /
# Grinold-Kahn (2000) shrinkage weight-blending layer.
# All six default to None (backward-compatible with pre-0.10.37 JSON).
# ---------------------------------------------------------------------------

def test_shrinkage_metadata_fields_default_to_none():
    """Proposal A (0.10.37-phase8pilot): the 6 new Metadata shrinkage fields
    exist and default to None — backward-compatible with all pre-0.10.37
    JSON artifacts (which have no shrinkage keys).

    Fields:
    - shrinkage_lambda: float | None
    - shrinkage_lambda_applied: float | None
    - ic_weight_by_pillar: dict[str, float] | None
    - shrinkage_blended_weight_by_pillar: dict[str, float] | None
    - n_preliminary_pillars: int | None
    - shrinkage_weights_degenerate: bool | None
    """
    from compute.output.schemas import Metadata

    # Minimal required Metadata construction (mirrors test_warehouse.py pattern)
    m = Metadata(
        version="0.10.37-phase8pilot",
        last_update_utc="2026-06-25T22:00:00Z",
        next_update_utc="2026-06-26T22:00:00Z",
        universe="SP1500",
        universe_size=1504,
        compute_run_id="test-shrinkage-001",
        git_commit="cafebabe",
    )
    assert m.shrinkage_lambda is None
    assert m.shrinkage_lambda_applied is None
    assert m.ic_weight_by_pillar is None
    assert m.shrinkage_blended_weight_by_pillar is None
    assert m.n_preliminary_pillars is None
    assert m.shrinkage_weights_degenerate is None


def test_shrinkage_metadata_fields_round_trip():
    """Proposal A: Metadata serializes and deserializes the 6 new shrinkage
    fields without data loss (Pydantic model_dump → model_validate round-trip).

    Populated values:
    - shrinkage_lambda = 1.0 (pin active)
    - shrinkage_lambda_applied = 1.0 (same — pin overrides schedule)
    - ic_weight_by_pillar = {"quality": 0.35, "value": 0.65}
    - shrinkage_blended_weight_by_pillar = {"quality": 0.275, "value": 0.275, ...}
    - n_preliminary_pillars = 8 (all preliminary at launch)
    - shrinkage_weights_degenerate = True
    """
    from compute.output.schemas import Metadata

    ic_w = {"quality": 0.35, "value": 0.65}
    blended_w = {
        "quality": 0.275,
        "value": 0.225,
        "growth": 0.125,
        "momentum": 0.125,
        "health": 0.100,
        "profitability": 0.063,
        "technical": 0.050,
        "risk": 0.037,
    }

    m = Metadata(
        version="0.10.37-phase8pilot",
        last_update_utc="2026-06-25T22:00:00Z",
        next_update_utc="2026-06-26T22:00:00Z",
        universe="SP1500",
        universe_size=1504,
        compute_run_id="test-shrinkage-002",
        git_commit="deadbeef",
        shrinkage_lambda=1.0,
        shrinkage_lambda_applied=1.0,
        ic_weight_by_pillar=ic_w,
        shrinkage_blended_weight_by_pillar=blended_w,
        n_preliminary_pillars=8,
        shrinkage_weights_degenerate=True,
    )

    payload = m.model_dump(mode="json")
    m2 = Metadata.model_validate(payload)

    assert m2.shrinkage_lambda == 1.0
    assert m2.shrinkage_lambda_applied == 1.0
    assert m2.ic_weight_by_pillar == ic_w
    assert m2.shrinkage_blended_weight_by_pillar == blended_w
    assert m2.n_preliminary_pillars == 8
    assert m2.shrinkage_weights_degenerate is True


# ---------------------------------------------------------------------------
# Proposal C-2 — MoS conviction tilt (0.10.38-phase8pilot).
#
# 1 additive nullable Metadata field:
#   mos_tilt_shadow_max_delta_pp: float | None
#
# SHADOW / OBSERVABILITY-ONLY (Rule 18); live NAV path byte-identical;
# defense UNCHANGED at 36.  Nullable on pre-0.10.38 artifacts; None when
# backtest_pit.json is absent (cold clone or skipped backfill).
# ---------------------------------------------------------------------------


def test_mos_tilt_metadata_field_defaults_to_none():
    """Proposal C-2 (0.10.38-phase8pilot): ``mos_tilt_shadow_max_delta_pp``
    exists on Metadata and defaults to None — backward-compatible with all
    pre-0.10.38 JSON artifacts (which have no such key).

    Field type: ``float | None`` — holds the maximum per-rebalance
    single-name weight shift (in percentage points) that the MoS tilt
    would produce in ``backtest_pit.json``.  None when the artifact is
    absent or the backfill was not re-run since C-2 landed.
    """
    from compute.output.schemas import Metadata

    m = Metadata(
        version="0.10.38-phase8pilot",
        last_update_utc="2026-06-26T22:00:00Z",
        next_update_utc="2026-06-27T22:00:00Z",
        universe="SP1500",
        universe_size=1504,
        compute_run_id="test-c2-default-none",
        git_commit="c2c2c2c2",
    )
    assert m.mos_tilt_shadow_max_delta_pp is None, (
        "mos_tilt_shadow_max_delta_pp must default to None (backward-compat)"
    )


def test_mos_tilt_metadata_field_round_trips():
    """Proposal C-2: ``mos_tilt_shadow_max_delta_pp`` survives a Pydantic
    model_dump → model_validate round-trip with a realistic value.

    A value of 8.4 means the largest weight shift seen across all rebalance
    legs was 8.4 pp (e.g., a holding went from 20% base weight to 28.4%
    or 11.6% after the MoS tilt) — a plausible calibration output for κ=0.25.
    """
    from compute.output.schemas import Metadata

    m = Metadata(
        version="0.10.38-phase8pilot",
        last_update_utc="2026-06-26T22:00:00Z",
        next_update_utc="2026-06-27T22:00:00Z",
        universe="SP1500",
        universe_size=1504,
        compute_run_id="test-c2-round-trip",
        git_commit="deadc2c2",
        mos_tilt_shadow_max_delta_pp=8.4,
    )
    assert m.mos_tilt_shadow_max_delta_pp == 8.4

    payload = m.model_dump(mode="json")
    assert payload["mos_tilt_shadow_max_delta_pp"] == 8.4

    m2 = Metadata.model_validate(payload)
    assert m2.mos_tilt_shadow_max_delta_pp == 8.4


def test_mos_tilt_metadata_field_zero_is_valid():
    """Proposal C-2: 0.0 is a valid ``mos_tilt_shadow_max_delta_pp`` value.

    Means the tilt produced zero weight shift on all rebalances — occurs when
    all MoS values are equal (identity case) or the book has a single name.
    Distinct from None (field absent / backfill not run).
    """
    from compute.output.schemas import Metadata

    m = Metadata(
        version="0.10.38-phase8pilot",
        last_update_utc="2026-06-26T22:00:00Z",
        next_update_utc="2026-06-27T22:00:00Z",
        universe="SP1500",
        universe_size=1504,
        compute_run_id="test-c2-zero",
        git_commit="00c2c2c2",
        mos_tilt_shadow_max_delta_pp=0.0,
    )
    assert m.mos_tilt_shadow_max_delta_pp == 0.0

    payload = m.model_dump(mode="json")
    assert payload["mos_tilt_shadow_max_delta_pp"] == 0.0
