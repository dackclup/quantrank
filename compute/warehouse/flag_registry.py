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

        # TODO: verify the exact literal for the share-count adjustment detail note:
        # "share count adjusted for N:1 split <date>, pending EDGAR refresh"
        # This is a formatted-string warning, NOT a fixed literal, so it is NOT
        # registered here as a flag column. It will land in valuation_warnings_json.
    }
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
