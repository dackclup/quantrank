"""Smoke tests for compute.config constants.

Locks the values of Tier-2 defense constants (PR 3d Step 1) so an
accidental edit surfaces as a test failure rather than silent drift
into production.
"""

from __future__ import annotations

from compute import config


def test_schema_version_is_phase4_6():
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
    Locks the version against accidental revert."""
    assert config.SCHEMA_VERSION == "0.10.12-phase4.6"


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
