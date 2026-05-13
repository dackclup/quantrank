"""Unit + integration tests for compute.scoring.tier2 (PR 3d Step 5).

Coverage:
- A1-A4: fetch_tier2_for_ticker orchestration (10-K + 8-K success/fail
  permutations + total failure).
- B1-B3: tier2_events_dict construction + latest_8k_filing date/url
  preference rules.
- C1-C5: coverage_pct computation including edge cases.

The orchestrator monkeypatches the underlying fetchers
(fetch_latest_10k_text + fetch_recent_8k_filings) to test isolation
without network or cache dependence.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from compute.scoring import tier2
from compute.scoring.eight_k_events import ItemFlag
from compute.scoring.tier2 import (
    Tier2Result,
    coverage_pct,
    fetch_tier2_for_ticker,
    tier2_events_dict,
)

ASOF = date(2026, 5, 10)


@pytest.fixture
def eight_k_enabled(monkeypatch):
    """Re-enable the 8-K Defenses #9/#10 wiring for tests that exercise it.

    The module-level ``_EIGHT_K_DEFENSES_ENABLED`` ships False in PR 3d
    (deferred to Phase 4 — see issue tracker). Tests that lock the
    integration shape need to flip the flag so the wiring stays
    exercised pre-Phase-4. New tests in section E exercise the
    deferred-default mode.
    """
    monkeypatch.setattr(tier2, "_EIGHT_K_DEFENSES_ENABLED", True)


def _filing(days_ago: int, items: list[str]) -> dict:
    """Synthetic 8-K filing dict (matches eight_k_events.py cache shape)."""
    fd = ASOF - timedelta(days=days_ago)
    return {
        "filing_date": fd.strftime("%Y-%m-%d"),
        "filing_url": f"https://www.sec.gov/Archives/test_{days_ago}.htm",
        "items": list(items),
        "item_text_excerpts": {},
    }


# ---------------------------------------------------------------------------
# A. fetch_tier2_for_ticker orchestration
# ---------------------------------------------------------------------------

def test_A1_all_three_defenses_clean_returns_succeeded(monkeypatch, eight_k_enabled):
    """10-K text is clean (no phrases) + 8-K has no matching items →
    fetch_succeeded=True, all three flags False.

    Uses ``eight_k_enabled`` fixture to flip the deferral flag so the
    full integration shape stays under test pre-Phase-4.
    """
    monkeypatch.setattr(
        tier2, "fetch_latest_10k_text",
        lambda t: "Revenue grew 12% year-over-year. The Company is healthy.",
    )
    monkeypatch.setattr(
        tier2, "fetch_recent_8k_filings",
        lambda t, lookback_days: [_filing(30, ["Item 5.02"])],
    )
    result = fetch_tier2_for_ticker("TST", asof=ASOF)
    assert result.fetch_succeeded is True
    assert result.going_concern_disclosure is False
    assert result.non_reliance_flag.fired is False
    assert result.auditor_change_flag.fired is False


def test_A2_10k_fetch_fails_8k_succeeds_partial(monkeypatch, eight_k_enabled):
    """10-K text fetch returns None (rate-limit / not-found) but 8-K
    succeeds → going_concern=False, 8-K flags computed normally,
    fetch_succeeded=False (Step 5 spec: BOTH must succeed)."""
    monkeypatch.setattr(tier2, "fetch_latest_10k_text", lambda t: None)
    monkeypatch.setattr(
        tier2, "fetch_recent_8k_filings",
        lambda t, lookback_days: [_filing(30, ["Item 4.02"])],
    )
    result = fetch_tier2_for_ticker("TST", asof=ASOF)
    assert result.going_concern_disclosure is False
    assert result.non_reliance_flag.fired is True  # 8-K parsed despite 10-K fail
    assert result.fetch_succeeded is False  # 10-K failed


def test_A3_8k_fetch_fails_10k_succeeds_partial(monkeypatch, eight_k_enabled):
    """8-K returns None (rate-limit) → both flags False, going-concern
    still scans the 10-K text. fetch_succeeded=False."""
    monkeypatch.setattr(
        tier2, "fetch_latest_10k_text",
        lambda t: "We have substantial doubt about the Company's ability to continue.",
    )
    monkeypatch.setattr(tier2, "fetch_recent_8k_filings", lambda t, lookback_days: None)
    result = fetch_tier2_for_ticker("TST", asof=ASOF)
    assert result.going_concern_disclosure is True  # phrase matched
    assert result.non_reliance_flag.fired is False
    assert result.auditor_change_flag.fired is False
    assert result.fetch_succeeded is False  # 8-K failed


def test_A4_total_fetch_failure_returns_all_defaults(monkeypatch):
    """Both fetches fail → all flags False, fetch_succeeded=False.
    Failure isolation: orchestrator never raises."""
    monkeypatch.setattr(tier2, "fetch_latest_10k_text", lambda t: None)
    monkeypatch.setattr(tier2, "fetch_recent_8k_filings", lambda t, lookback_days: None)
    result = fetch_tier2_for_ticker("TST", asof=ASOF)
    assert result.going_concern_disclosure is False
    assert result.non_reliance_flag.fired is False
    assert result.auditor_change_flag.fired is False
    assert result.fetch_succeeded is False


def test_A5_underlying_exception_caught_per_defense(monkeypatch):
    """If a per-defense fetcher raises (not just returns None), the
    orchestrator catches it. One bad ticker can never crash the run."""
    def raise_anything(*a, **k):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(tier2, "fetch_latest_10k_text", raise_anything)
    monkeypatch.setattr(tier2, "fetch_recent_8k_filings", raise_anything)
    result = fetch_tier2_for_ticker("TST", asof=ASOF)
    assert result.going_concern_disclosure is False
    assert result.non_reliance_flag.fired is False
    assert result.fetch_succeeded is False


def test_A6_both_8k_items_present_both_flags_fire(monkeypatch, eight_k_enabled):
    """A single 8-K with both 4.01 + 4.02 items → both flags fire."""
    monkeypatch.setattr(tier2, "fetch_latest_10k_text", lambda t: "clean")
    monkeypatch.setattr(
        tier2, "fetch_recent_8k_filings",
        lambda t, lookback_days: [_filing(30, ["Item 4.01", "Item 4.02"])],
    )
    result = fetch_tier2_for_ticker("TST", asof=ASOF)
    assert result.non_reliance_flag.fired is True
    assert result.auditor_change_flag.fired is True


# ---------------------------------------------------------------------------
# B. tier2_events_dict construction
# ---------------------------------------------------------------------------

def _result_with_flags(
    *,
    going_concern: bool = False,
    nr_fired: bool = False,
    nr_date: str | None = None,
    nr_url: str | None = None,
    ac_fired: bool = False,
    ac_date: str | None = None,
    ac_url: str | None = None,
    fetch_ok: bool = True,
) -> Tier2Result:
    return Tier2Result(
        going_concern_disclosure=going_concern,
        non_reliance_flag=ItemFlag(
            fired=nr_fired, filing_date=nr_date, filing_url=nr_url, raw_item_text=None
        ),
        auditor_change_flag=ItemFlag(
            fired=ac_fired, filing_date=ac_date, filing_url=ac_url, raw_item_text=None
        ),
        fetch_succeeded=fetch_ok,
    )


def test_B1_both_8k_flags_fire_prefers_non_reliance():
    """When both 4.02 + 4.01 fired, latest_8k_filing_date / url come
    from the non_reliance flag (hard-veto signal is more important)."""
    r = _result_with_flags(
        nr_fired=True, nr_date="2026-03-15", nr_url="https://sec.gov/nr.htm",
        ac_fired=True, ac_date="2026-04-20", ac_url="https://sec.gov/ac.htm",
    )
    d = tier2_events_dict(r)
    assert d["non_reliance_filing"] is True
    assert d["auditor_change"] is True
    assert d["latest_8k_filing_date"] == "2026-03-15"
    assert d["latest_8k_filing_url"] == "https://sec.gov/nr.htm"


def test_B2_only_auditor_change_uses_its_metadata():
    """auditor_change alone → date/url from that flag."""
    r = _result_with_flags(
        ac_fired=True, ac_date="2026-04-20", ac_url="https://sec.gov/ac.htm",
    )
    d = tier2_events_dict(r)
    assert d["non_reliance_filing"] is False
    assert d["auditor_change"] is True
    assert d["latest_8k_filing_date"] == "2026-04-20"
    assert d["latest_8k_filing_url"] == "https://sec.gov/ac.htm"


def test_B3_neither_8k_flag_fires_dates_url_none():
    r = _result_with_flags()
    d = tier2_events_dict(r)
    assert d["latest_8k_filing_date"] is None
    assert d["latest_8k_filing_url"] is None
    assert d["non_reliance_filing"] is False
    assert d["auditor_change"] is False


def test_B4_dict_shape_matches_typescript_interface():
    """Five required keys, no extras. Locks the contract per
    frontend/lib/types.ts::Tier2Events."""
    r = _result_with_flags(going_concern=True)
    d = tier2_events_dict(r)
    assert set(d.keys()) == {
        "going_concern_disclosure",
        "non_reliance_filing",
        "auditor_change",
        "latest_8k_filing_date",
        "latest_8k_filing_url",
    }


# ---------------------------------------------------------------------------
# C. coverage_pct
# ---------------------------------------------------------------------------

def test_C1_all_succeeded_returns_100():
    results = {f"T{i}": _result_with_flags(fetch_ok=True) for i in range(502)}
    assert coverage_pct(results) == 100.0


def test_C2_none_succeeded_returns_zero():
    results = {f"T{i}": _result_with_flags(fetch_ok=False) for i in range(502)}
    assert coverage_pct(results) == 0.0


def test_C3_partial_coverage_rounded_to_2dp():
    """250 of 502 succeeded → 49.80%."""
    results = {}
    for i in range(502):
        results[f"T{i}"] = _result_with_flags(fetch_ok=(i < 250))
    pct = coverage_pct(results)
    assert pct == 49.80


def test_C4_empty_universe_returns_none():
    """Empty input → None (we 'didn't try'), not 0.0 or ZeroDivisionError."""
    assert coverage_pct({}) is None


def test_C5_single_ticker_succeeded_returns_100():
    results = {"TST": _result_with_flags(fetch_ok=True)}
    assert coverage_pct(results) == 100.0


# ---------------------------------------------------------------------------
# D. End-to-end smoke (orchestrator + dict + coverage together)
# ---------------------------------------------------------------------------

def test_D1_full_pipeline_synthetic(monkeypatch, eight_k_enabled):
    """Mock 10 tickers, 3 of which trip various flags. Verify the full
    pipeline (orchestrator → dict → coverage) produces sensible output."""
    universe = [f"T{i:02d}" for i in range(10)]
    # 3 tickers with flags (different combinations); 7 clean.
    flag_tickers = {
        "T00": ("substantial doubt about the Company's ability", []),
        "T01": ("clean", ["Item 4.02"]),
        "T02": ("clean", ["Item 4.01"]),
    }

    def fake_10k(t):
        return flag_tickers.get(t, ("clean", []))[0] if t in flag_tickers else "clean"

    def fake_8k(t, lookback_days):
        items = flag_tickers.get(t, ("clean", []))[1] if t in flag_tickers else []
        return [_filing(30, items)] if items else []

    monkeypatch.setattr(tier2, "fetch_latest_10k_text", fake_10k)
    monkeypatch.setattr(tier2, "fetch_recent_8k_filings", fake_8k)

    results = {t: fetch_tier2_for_ticker(t, asof=ASOF) for t in universe}

    # All 10 succeeded.
    assert coverage_pct(results) == 100.0

    # Going-concern fires on T00.
    assert results["T00"].going_concern_disclosure is True
    assert results["T00"].non_reliance_flag.fired is False

    # Non-reliance fires on T01.
    assert results["T01"].non_reliance_flag.fired is True

    # Auditor change fires on T02.
    assert results["T02"].auditor_change_flag.fired is True

    # The other 7 are clean.
    for t in ("T03", "T04", "T05", "T06", "T07", "T08", "T09"):
        assert results[t].going_concern_disclosure is False
        assert results[t].non_reliance_flag.fired is False
        assert results[t].auditor_change_flag.fired is False

    # tier2_events_dict for T01 (non_reliance only) carries that date/url.
    d = tier2_events_dict(results["T01"])
    assert d["non_reliance_filing"] is True
    assert d["latest_8k_filing_date"] == (ASOF - timedelta(days=30)).strftime("%Y-%m-%d")


def test_D2_tier2_result_is_frozen():
    """Frozen dataclass — guard against accidental mutation."""
    from dataclasses import FrozenInstanceError
    r = _result_with_flags()
    with pytest.raises(FrozenInstanceError):
        r.fetch_succeeded = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# E. 8-K deferred-mode default (PR 3d Phase 4 hand-off)
# ---------------------------------------------------------------------------

def test_E1_deferred_mode_skips_8k_fetch_entirely(monkeypatch):
    """With ``_EIGHT_K_DEFENSES_ENABLED=False`` (PR 3d default), the 8-K
    fetcher MUST NOT be called even when the 10-K fetch succeeds. Locks
    the perf contract: deferring 8-K means zero 8-K-related EDGAR calls."""
    eight_k_calls: list[str] = []

    def boom(*a, **k):
        eight_k_calls.append("called")
        raise AssertionError("8-K fetch must not run in deferred mode")

    monkeypatch.setattr(tier2, "fetch_latest_10k_text", lambda t: "clean text")
    monkeypatch.setattr(tier2, "fetch_recent_8k_filings", boom)
    result = fetch_tier2_for_ticker("TST", asof=ASOF)
    assert eight_k_calls == []
    # 8-K flags emit the empty ItemFlag.
    assert result.non_reliance_flag.fired is False
    assert result.non_reliance_flag.filing_date is None
    assert result.auditor_change_flag.fired is False
    assert result.auditor_change_flag.filing_date is None


def test_E2_deferred_mode_fetch_succeeded_collapses_to_text_only(monkeypatch):
    """With 8-K deferred, ``fetch_succeeded`` is True iff the 10-K
    text fetched OK (the 8-K leg is not part of the success criterion)."""
    monkeypatch.setattr(tier2, "fetch_latest_10k_text", lambda t: "clean text")
    monkeypatch.setattr(tier2, "fetch_recent_8k_filings", lambda t, **k: None)
    result = fetch_tier2_for_ticker("TST", asof=ASOF)
    assert result.fetch_succeeded is True


def test_E3_deferred_mode_10k_failure_still_marks_unsucceeded(monkeypatch):
    """10-K fetch failure → fetch_succeeded=False, regardless of 8-K
    branch (which is skipped in deferred mode)."""
    monkeypatch.setattr(tier2, "fetch_latest_10k_text", lambda t: None)
    result = fetch_tier2_for_ticker("TST", asof=ASOF)
    assert result.fetch_succeeded is False
    assert result.going_concern_disclosure is False


def test_E4_deferred_mode_going_concern_still_works(monkeypatch):
    """Defense #8 (the only Tier-2 defense active in PR 3d) fires
    correctly in deferred mode — the 10-K text scan is independent of
    the 8-K wiring."""
    monkeypatch.setattr(
        tier2, "fetch_latest_10k_text",
        lambda t: "We have substantial doubt about the Company's ability to continue as a going concern.",
    )
    result = fetch_tier2_for_ticker("TST", asof=ASOF)
    assert result.going_concern_disclosure is True
    assert result.non_reliance_flag.fired is False
    assert result.auditor_change_flag.fired is False


def test_E5_deferred_mode_dict_shape_unchanged(monkeypatch):
    """Schema contract: tier2_events dict still emits all 5 keys with
    safe defaults in deferred mode. Frontend doesn't notice a difference."""
    monkeypatch.setattr(tier2, "fetch_latest_10k_text", lambda t: "clean")
    result = fetch_tier2_for_ticker("TST", asof=ASOF)
    d = tier2_events_dict(result)
    assert set(d.keys()) == {
        "going_concern_disclosure",
        "non_reliance_filing",
        "auditor_change",
        "latest_8k_filing_date",
        "latest_8k_filing_url",
    }
    assert d["non_reliance_filing"] is False
    assert d["auditor_change"] is False
    assert d["latest_8k_filing_date"] is None
    assert d["latest_8k_filing_url"] is None


# ---------------------------------------------------------------------------
# F. QR_SKIP_TIER2 operational kill-switch
# ---------------------------------------------------------------------------

def test_F1_qr_skip_tier2_bypasses_all_fetches(monkeypatch):
    """When QR_SKIP_TIER2 is set, neither the 10-K fetch nor the 8-K
    fetch is invoked. Returns an empty Tier2Result with
    fetch_succeeded=False. Used by operators to cut ~10-15 min off a
    cold-cache compute run when going-concern annotation is not needed."""
    monkeypatch.setenv("QR_SKIP_TIER2", "1")

    def boom_text(*a, **k):
        raise AssertionError("10-K fetch must not run when QR_SKIP_TIER2 set")

    def boom_eightk(*a, **k):
        raise AssertionError("8-K fetch must not run when QR_SKIP_TIER2 set")

    monkeypatch.setattr(tier2, "fetch_latest_10k_text", boom_text)
    monkeypatch.setattr(tier2, "fetch_recent_8k_filings", boom_eightk)

    result = fetch_tier2_for_ticker("TST", asof=ASOF)
    assert result.going_concern_disclosure is False
    assert result.non_reliance_flag.fired is False
    assert result.auditor_change_flag.fired is False
    assert result.fetch_succeeded is False


def test_F2_qr_skip_tier2_unset_runs_normally(monkeypatch):
    """Sanity: without the env var, the normal deferred-mode path runs
    (10-K fetch happens, 8-K skipped per feature flag). Guards against
    accidentally short-circuiting when the env var is empty/missing."""
    monkeypatch.delenv("QR_SKIP_TIER2", raising=False)
    monkeypatch.setattr(
        tier2, "fetch_latest_10k_text",
        lambda t: "We have substantial doubt about the Company's ability to continue as a going concern.",
    )
    result = fetch_tier2_for_ticker("TST", asof=ASOF)
    assert result.going_concern_disclosure is True
    assert result.fetch_succeeded is True
