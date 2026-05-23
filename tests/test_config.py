"""Smoke tests for compute.config constants.

Locks the values of Tier-2 defense constants (PR 3d Step 1) so an
accidental edit surfaces as a test failure rather than silent drift
into production.
"""

from __future__ import annotations

from compute import config


def test_schema_version_is_phase4_5e():
    """Phase 4.5e PR 3 (0.10.1-phase4.5e) — PATCH bump for the new
    ``insider_sell_cluster_firing_count`` + ``c_suite_unusual_sell_firing_count``
    Metadata diagnostics (Rule 18 observability shipped with the flag
    emission per ``portable-annotate-before-veto``). Supersedes PR 2's
    0.10.0-phase4.5e Form-4 observability bump. Locks the version
    against accidental revert."""
    assert config.SCHEMA_VERSION == "0.10.1-phase4.5e"


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
