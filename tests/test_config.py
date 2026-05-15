"""Smoke tests for compute.config constants.

Locks the values of Tier-2 defense constants (PR 3d Step 1) so an
accidental edit surfaces as a test failure rather than silent drift
into production.
"""

from __future__ import annotations

from compute import config


def test_schema_version_is_phase4g():
    assert config.SCHEMA_VERSION == "0.7.0-phase4g"


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
