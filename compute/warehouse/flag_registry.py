"""Authoritative registry of all flag strings the pipeline can emit.

Sources cross-referenced from:
  - compute/scoring/risk_overlay.py (compute_risk_flags)
  - compute/scoring/manipulation_index.py (FLAG_WEIGHTS)
  - compute/valuation/ensemble.py (valuation_warnings)
  - compute/main.py (per-ticker Step 8 loop)

KNOWN_RISK_FLAGS: strings appended to StockDetail.risk_flags / StockSummary.risk_flags.
KNOWN_VALUATION_WARNINGS: strings appended to StockDetail.valuation_warnings /
  StockSummary.valuation_warnings.

The ``extreme_<method>_estimate`` family is template-keyed — one entry per
METHOD_NAMES tuple in compute/valuation/ensemble.py. They are registered here
individually rather than as a wildcard so the drift-guard in
warehouse_schema_check detects a method addition.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Risk flags  (emitted into StockDetail.risk_flags / StockSummary.risk_flags)
# ---------------------------------------------------------------------------
# These are the direct veto flags that set recommendation=cautious and
# suppress entered_top5. Source: compute/scoring/risk_overlay.compute_risk_flags.

KNOWN_RISK_FLAGS: frozenset[str] = frozenset(
    {
        # Defense #487 / FDXF domain-widening — no usable fundamentals.
        # Fires on: (a) snap is None (complete EDGAR ingest failure) OR
        # (b) snap present but ALL 34 ALL_METRIC_KEYS fields are null.
        "fundamentals_unavailable",
        # Issue #18 — TBVPS > $10K/share / TTM revenue < $50M / |NI| > |revenue|.
        "data_quality_input_corruption",
        # Altman Z'' < 1.1 (Altman 2003).
        "altman_distress",
        # Sloan accruals top decile within sector (Sloan 1996 TAR).
        "sloan_accruals_top_decile",
        # Net Stock Issuance top decile within sector (Pontiff-Woodgate 2008 JF).
        "net_issuance_top_decile",
        # 8-K Item 4.02 within trailing 365 days (Schroeder 2024 SSRN).
        "non_reliance_filing",
        # Beneish M-Score > -1.78 veto (Beneish 1999 FAJ).
        "beneish_manipulation_veto",
        # Dechow F-Score > 3.0 veto (Dechow et al. 2011 CAR).
        "dechow_manipulation_veto",
        # Post-split share-lag: Tier-2 (legs 1+2 hold, leg 3 fails — unreconciled).
        # Defense layer 35, #499. Tier-1 CORRECT goes to valuation_warnings only.
        "post_split_share_lag_unreconciled",
        # Stale 10-K/10-Q: filing date > 180 days old — hard veto (drives Top-5
        # suppression exactly like the other active vetoes).
        # Emission sites:
        #   compute/main.py:1752  (Step 6b pre-scan, injects into risk_flags list)
        #   compute/valuation/ensemble.py:379  (returned as extra_flags to caller)
        "stale_filing_hard",
    }
)

# ---------------------------------------------------------------------------
# Valuation warnings  (emitted into StockDetail.valuation_warnings /
#                       StockSummary.valuation_warnings)
# ---------------------------------------------------------------------------
# These are annotate-only flags. They do NOT set cautious or suppress Top-5
# (except when consumed by the manipulation_index soft-penalty path).
# Sources: compute/main.py Step 8 per-ticker loop + compute/valuation/ensemble.py.

KNOWN_VALUATION_WARNINGS: frozenset[str] = frozenset(
    {
        # --- Valuation-ensemble flags (compute/valuation/ensemble.py) ---
        # Defense #3 — stale filing soft (>120d lag, method still runs but annotated).
        "stale_filing_soft",
        # Defense #2 — goodwill heavy (TBVPS/BVPS < 0.5; Penman 2013 anchor).
        "goodwill_heavy",
        # Defense #4 — per-method extreme estimate (5× or 0.2× of current price).
        # Template: extreme_<method>_estimate where method is from METHOD_NAMES.
        "extreme_graham_estimate",
        "extreme_multiples_pe_estimate",
        "extreme_multiples_pb_estimate",
        "extreme_multiples_ev_ebitda_estimate",
        "extreme_rim_estimate",
        "extreme_dcf_estimate",
        # Majority collapse (≥3 of 6 methods fire extreme_*_estimate; Huber 1981 §1.4).
        "extreme_estimate_majority",
        # RIM value-trap risk (ROE < sector cost of equity; Damodaran 2019 Ch. 8).
        "value_trap_risk",
        # UI parity for data_quality_input_corruption veto (writer-parity annotate).
        "valuation_output_anomalous",

        # --- Main.py per-ticker loop flags ---
        # Beneish M-Score ∈ [-2.22, -1.78] warning band (Beneish-Lee-Nichols 2013 FAJ).
        "beneish_high",
        # Dechow F-Score ∈ [2.45, 3.0] warning band (Dechow et al. 2011 CAR).
        "dechow_high",
        # Joint-gate badge: Sloan + Beneish-high + Dechow-high co-fire.
        "manipulation_triple_flag",
        # Cross-source market-cap disagreement > 5% (SEC-derived vs yfinance).
        "cross_source_disagreement",
        # Post-split Tier-1 annotate (shares corrected; transparency flag).
        # Routing: valuation_warnings only (not risk_flags) — PR-2 fix 2026-06-18.
        "post_split_share_lag",
        # Multi-class aggregate shares suspected (GOOG/GOOGL CIK-collision pattern).
        "multi_class_aggregate_shares_suspected",
        # PR 4.5b — amendment-based restatement history (10-K/A, 10-Q/A, 5y window).
        "restatement_history",
        # PR 4.5b + Epic #150 Phase 2.2 — amendment + Item 4.02 co-occurrence (90d).
        "restatement_high_confidence",
        # Bartov-Konchitchki 2017 Accounting Horizons — NT-10K/NT-10Q (365d window).
        "late_filing_notification",
        # Roychowdhury 2006 JAE — abnormal CFO + production + disc. expenses (REM).
        "rem_suspect",
        # Sloan 1996 TAR extended over 4 quarters — sustained high accruals.
        "accruals_momentum_high",
        # Burgstahler-Dichev 1997 JAE — loss-avoidance kink (absolute $).
        "loss_avoidance_pattern",
        # Roychowdhury 2006 JAE Table 1 — loss-avoidance size-invariant (NI/TA ∈ [0, 0.005], 3y+).
        "loss_avoidance_pattern_size_invariant",
        # STZ-pattern: shares_outstanding None while revenue + total_assets present.
        "share_count_extraction_missing",
        # S&P 1500 Slice 4 — ADV < $5M trailing-30d (Amihud 2002; ANNOTATE-ONLY, Rule 16).
        "low_liquidity",
        # Form-4 — ≥3 insiders selling $1M+ in 30d (Cohen-Malloy-Pomorski 2012 JF).
        "insider_sell_cluster",
        # Form-4 — CEO + CFO co-sell subset (Jeng-Metrick-Zeckhauser 2003 RFS).
        "c_suite_unusual_sell",
    }
)

# ---------------------------------------------------------------------------
# Forward-only flags: flags that CANNOT be reconstructed PIT.
#
# These are flags derived from sources with no historical record available
# for the backfill: EDGAR 8-K Item-4.02 feeds, Form-4 insider data,
# live-ADV from the price cache, cross-source yfinance comparison,
# post-split yfinance reconciliation, and ML/OSAP factor signals that
# require a multi-month trailing window not loaded by the PIT replay.
#
# In ``pit_replay`` rows these columns are written as NULL (not False) so
# that downstream ML models never read an unconfirmed absence as a
# confirmed negative.  Live rows always carry True/False (never None).
#
# Adding a new forward-only flag:
#   1. Add its string literal to this frozenset.
#   2. It must also be present in KNOWN_RISK_FLAGS or KNOWN_VALUATION_WARNINGS
#      (the union, not a separate registry).
#   3. Run warehouse_schema_check --update after any net-new flag addition.
# ---------------------------------------------------------------------------
FORWARD_ONLY_FLAGS: frozenset[str] = frozenset(
    {
        # ---- Risk flags (KNOWN_RISK_FLAGS) ----
        # 8-K Item 4.02 non-reliance: no historical filing feed in PIT data.
        "non_reliance_filing",
        # Post-split share-lag (Tier-2 veto): requires live yfinance split
        # reconciliation that is not PIT-replayable.
        "post_split_share_lag_unreconciled",
        # Stale filing hard: driven by live filing-date proximity; the
        # historical staleness window differs from the live 180d gate and the
        # backfill uses BACKTEST_HARD_STALE_DAYS relaxation explicitly.
        # Write as NULL so replay rows do not appear to have a known staleness
        # verdict from the live gate.
        "stale_filing_hard",
        # Fundamentals unavailable: fires when snap is None. In the backfill
        # tickers with no PIT snapshot are simply omitted (no row written),
        # so this flag never fires in replay rows — write NULL to be explicit.
        "fundamentals_unavailable",

        # ---- Valuation warnings (KNOWN_VALUATION_WARNINGS) ----
        # Cross-source market-cap disagreement: requires live yfinance query.
        "cross_source_disagreement",
        # Post-split Tier-1 annotate: requires live yfinance split data.
        "post_split_share_lag",
        # Multi-class aggregate shares: requires live cross-source check.
        "multi_class_aggregate_shares_suspected",
        # Low liquidity (ADV): requires the live trailing-30d price window
        # that is not computed during the backfill's per-date PIT pass.
        "low_liquidity",
        # Form-4 insider cluster: no historical Form-4 feed in PIT replay.
        "insider_sell_cluster",
        # Form-4 CEO/CFO co-sell: same as above.
        "c_suite_unusual_sell",
        # Stale filing soft: same reasoning as stale_filing_hard; replay uses
        # a widened staleness gate so the live 120d soft flag is not PIT-valid.
        "stale_filing_soft",
    }
)

# ---------------------------------------------------------------------------
# Backfill-uncomputed annotates: valuation_warnings that are PIT-recoverable
# in principle but are NOT recomputed by the current backfill.
#
# These flags derive from the per-ticker loop in compute/main.py (restatement
# history EDGAR calls, REM/accrual-momentum computations, snapshot checks) or
# from the post-ensemble DQIC co-fire path — none of which are executed during
# the PIT replay.  Because the backfill does NOT re-run them, writing False
# would be a SILENT CONFIRMED-NEGATIVE (the flag was never evaluated).  NULL
# is correct: "not evaluated — not known to be absent".
#
# These are distinct from FORWARD_ONLY_FLAGS:
#   FORWARD_ONLY_FLAGS       = sources with NO historical record (8-K feeds,
#                              Form-4, live-ADV, live cross-source yfinance).
#   BACKFILL_UNCOMPUTED_ANNOTATES = PIT-recoverable sources that the backfill
#                              script simply does not recompute (future
#                              enhancement to genuinely replay them).
#
# In ``pit_replay`` rows callers union this set with FORWARD_ONLY_FLAGS so
# that ALL unconfirmed columns are NULL (not False).  Live rows are
# unaffected — they always carry True/False.
#
# Adding a genuinely-replayed annotate:
#   1. Remove it from this set.
#   2. Ensure the backfill code actually computes it PIT.
#   3. Run warehouse_schema_check to confirm no column drift.
# ---------------------------------------------------------------------------
BACKFILL_UNCOMPUTED_ANNOTATES: frozenset[str] = frozenset(
    {
        # PR 4.5b — amendment-based restatement history (10-K/A, 10-Q/A, 5y
        # window): requires additional EDGAR amendment fetches not loaded in
        # the backfill's PIT history.
        "restatement_history",
        # PR 4.5b + Epic #150 Phase 2.2 — amendment + Item 4.02 co-occurrence
        # (90d): same as restatement_history — EDGAR amendments not fetched.
        "restatement_high_confidence",
        # Bartov-Konchitchki 2017 Accounting Horizons — NT-10K/NT-10Q (365d
        # window): requires live NT filing detection not in the PIT replay.
        "late_filing_notification",
        # Roychowdhury 2006 JAE — abnormal CFO + production + disc. expenses
        # (REM): computed in the main.py per-ticker loop; not in backfill.
        "rem_suspect",
        # Sloan 1996 TAR extended over 4 quarters — sustained high accruals:
        # requires multi-quarter accrual time-series not recomputed in backfill.
        "accruals_momentum_high",
        # Burgstahler-Dichev 1997 JAE — loss-avoidance kink (absolute $):
        # computed in main.py per-ticker loop; not in backfill.
        "loss_avoidance_pattern",
        # Roychowdhury 2006 JAE Table 1 — loss-avoidance size-invariant
        # (NI/TA ∈ [0, 0.005], 3y+): same — not recomputed in backfill.
        "loss_avoidance_pattern_size_invariant",
        # Beneish M-Score ∈ [-2.22, -1.78] warning band: replayed Beneish
        # score is computed but the WARNING BAND annotation (distinct from the
        # veto beneish_manipulation_veto) is added in main.py Step 5, not in
        # the backfill's replay path.
        "beneish_high",
        # Dechow F-Score ∈ [2.45, 3.0] warning band: same as beneish_high —
        # warning band annotation not replayed (the veto IS replayed).
        "dechow_high",
        # Joint-gate badge: Sloan + beneish_high + dechow_high co-fire:
        # depends on beneish_high + dechow_high which are not replayed.
        "manipulation_triple_flag",
        # STZ-pattern: shares_outstanding None while revenue + total_assets
        # present: snapshot-derived but emitted in main.py per-ticker loop,
        # not in the backfill path (RawMetrics is all-None in replay rows).
        "share_count_extraction_missing",
        # UI parity for data_quality_input_corruption veto (writer-parity
        # annotate): emitted in the main.py writer step, not in backfill.
        "valuation_output_anomalous",
    }
)

# Sanity check at import time: every forward-only flag must be registered.
_all_known_at_import = KNOWN_RISK_FLAGS | KNOWN_VALUATION_WARNINGS
_unregistered_forward_only = FORWARD_ONLY_FLAGS - _all_known_at_import
if _unregistered_forward_only:
    raise ValueError(
        f"FORWARD_ONLY_FLAGS contains entries not in KNOWN_RISK_FLAGS or "
        f"KNOWN_VALUATION_WARNINGS: {sorted(_unregistered_forward_only)}.  "
        f"Add the flag string to the appropriate registry first."
    )

# Sanity check: every backfill-uncomputed annotate must be in KNOWN_VALUATION_WARNINGS.
# (These are annotate-only flags — none should be risk flags.)
_unregistered_uncomputed = BACKFILL_UNCOMPUTED_ANNOTATES - KNOWN_VALUATION_WARNINGS
if _unregistered_uncomputed:
    raise ValueError(
        f"BACKFILL_UNCOMPUTED_ANNOTATES contains entries not in "
        f"KNOWN_VALUATION_WARNINGS: {sorted(_unregistered_uncomputed)}.  "
        f"Add the flag string to KNOWN_VALUATION_WARNINGS first."
    )

# Cross-check: no flag should appear in BOTH FORWARD_ONLY_FLAGS and
# BACKFILL_UNCOMPUTED_ANNOTATES (they are mutually exclusive categories).
_overlap = FORWARD_ONLY_FLAGS & BACKFILL_UNCOMPUTED_ANNOTATES
if _overlap:
    raise ValueError(
        f"Flags appear in both FORWARD_ONLY_FLAGS and BACKFILL_UNCOMPUTED_ANNOTATES "
        f"(mutually exclusive sets): {sorted(_overlap)}.  "
        f"Each flag belongs to exactly one category."
    )


# ---------------------------------------------------------------------------
# Validation helper
# ---------------------------------------------------------------------------

def assert_flags_known(
    flags: list[str],
) -> list[str]:
    """Return a list of flag strings not registered in either registry.

    Used at runtime (warn-only) and in tests (assert-zero). Returns the
    unregistered strings so callers can surface them in logs or fail tests.

    Does NOT raise — the caller decides whether unregistered = fatal.
    A zero-length return means all flags are registered.
    """
    all_known = KNOWN_RISK_FLAGS | KNOWN_VALUATION_WARNINGS
    return [f for f in flags if f not in all_known]
