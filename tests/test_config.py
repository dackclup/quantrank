"""Smoke tests for compute.config constants.

Locks the values of Tier-2 defense constants (PR 3d Step 1) so an
accidental edit surfaces as a test failure rather than silent drift
into production.
"""

from __future__ import annotations

from compute import config


def test_schema_version_is_phase4_5e():
    """Issue #261 PR-B (0.10.6-phase4.5e) — PATCH bump for two new
    ``multi_class_per_class_override_count`` +
    ``multi_class_mc_reconcile_failure_count`` Metadata fields.
    Rule 18 observability for the structural per-class XBRL extraction
    path that overrides Alphabet's companyfacts aggregate with a single
    class member's count for GOOG / GOOGL. Supersedes PR-A's 0.10.5-phase4.5e
    bump. Locks the version against accidental revert."""
    assert config.SCHEMA_VERSION == "0.10.6-phase4.5e"


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
