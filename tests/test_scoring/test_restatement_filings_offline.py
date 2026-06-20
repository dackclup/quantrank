"""Offline coverage tests for compute.scoring.restatement_filings.

Covers the previously-uncovered lines (baseline ~55%):
- Lines 152-159: _ensure_edgar_identity — UA set + set_identity raises
- Lines 174-195: _cache_read — missing/invalid fetched_at, stale window,
  malformed datetime, expired TTL, filings not a list
- Lines 204-211: _cache_write — happy path roundtrip
- Lines 216-222: invalidate_cache — both subdirs removed, OSError swallowed
- Lines 236-255: _filing_to_dict — all attribute paths (accession fallback,
  isoformat path, str fallback, None required fields, exception path)
- Lines 276, 281-325: _fetch_filings — edgartools ImportError,
  Company() raises, per-form iteration raises, per-form fetch raises
- Lines 337, 354-356: fetch_amendments/fetch_late_filings — default
  lookback_days kwarg None path
- Line 397, 398->401: check_restatement_history — None-fetch + filings None
- Line 442, 443->446: check_late_filing — None-fetch path + filings None
- Lines 500, 503-504: _parse_iso_date — non-string input + ValueError path
- Lines 522-532, 539->535: get_amendment_filing_dates — None-fetch path,
  out-of-window filter, _parse_iso_date returns None

Design: monkeypatch the EDGAR boundary (edgartools / edgar module) so ALL
tests run offline. No @pytest.mark.network markers here. Each test targets
a previously-uncovered branch so the red phase would expose the gap clearly.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from compute import config
from compute.scoring import restatement_filings
from compute.scoring.restatement_filings import (
    CACHE_TTL_DAYS,
    HighConfidenceRestatementResult,
    LateFilingResult,
    RestatementHistoryResult,
    _cache_read,
    _cache_write,
    _filing_to_dict,
    _parse_iso_date,
    check_late_filing,
    check_restatement_history,
    fetch_amendments,
    fetch_late_filings,
    get_amendment_filing_dates,
    invalidate_cache,
)

ASOF = date(2026, 5, 16)

# ---------------------------------------------------------------------------
# _ensure_edgar_identity — lines 152-159
# ---------------------------------------------------------------------------


def test_ensure_edgar_identity_missing_ua_returns_false(monkeypatch):
    """No EDGAR_USER_AGENT → returns False without raising (lines 147-151)."""
    monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)
    result = restatement_filings._ensure_edgar_identity()
    assert result is False


def test_ensure_edgar_identity_set_identity_raises_returns_false(monkeypatch):
    """set_identity() raising → exception caught → returns False (lines 152-158)."""
    monkeypatch.setenv("EDGAR_USER_AGENT", "Test Agent test@example.com")

    fake_edgar = SimpleNamespace(
        set_identity=lambda ua: (_ for _ in ()).throw(RuntimeError("boom")),
        Company=MagicMock(),
    )
    monkeypatch.setitem(sys.modules, "edgar", fake_edgar)
    result = restatement_filings._ensure_edgar_identity()
    assert result is False


def test_ensure_edgar_identity_success_returns_true(monkeypatch):
    """Happy path: UA set + set_identity succeeds → returns True (line 159)."""
    monkeypatch.setenv("EDGAR_USER_AGENT", "Test Agent test@example.com")

    fake_edgar = SimpleNamespace(
        set_identity=lambda ua: None,
        Company=MagicMock(),
    )
    monkeypatch.setitem(sys.modules, "edgar", fake_edgar)
    result = restatement_filings._ensure_edgar_identity()
    assert result is True


# ---------------------------------------------------------------------------
# _cache_read — lines 174-195
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_cache(tmp_path: Path, monkeypatch):
    """Redirect config.CACHE_DIR to a tmp dir for cache tests."""
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    return tmp_path


def _write_cache(tmp_path: Path, subdir: str, ticker: str, payload: dict) -> Path:
    p = tmp_path / subdir / f"{ticker}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_cache_read_file_absent_returns_none(isolated_cache):
    """No cache file → returns None immediately (line 173)."""
    assert _cache_read("edgar_amendments", "TST", 365) is None


def test_cache_read_corrupt_json_returns_none(isolated_cache):
    """JSON decode error → logged and returns None (lines 176-178)."""
    p = isolated_cache / "edgar_amendments" / "TST.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ not valid json", encoding="utf-8")
    assert _cache_read("edgar_amendments", "TST", 365) is None


def test_cache_read_missing_fetched_at_returns_none(isolated_cache):
    """fetched_at key absent (not a string) → returns None (line 181-182)."""
    _write_cache(isolated_cache, "edgar_amendments", "TST",
                 {"lookback_days": 365, "filings": []})
    assert _cache_read("edgar_amendments", "TST", 365) is None


def test_cache_read_missing_lookback_returns_none(isolated_cache):
    """lookback_days key absent (not an int) → returns None (line 181-182)."""
    _write_cache(isolated_cache, "edgar_amendments", "TST",
                 {"fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "filings": []})
    assert _cache_read("edgar_amendments", "TST", 365) is None


def test_cache_read_stale_lookback_window_returns_none(isolated_cache):
    """Cached lookback_days < requested → stale window → returns None (lines 183-185)."""
    _write_cache(isolated_cache, "edgar_amendments", "TST", {
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lookback_days": 365,
        "filings": [],
    })
    assert _cache_read("edgar_amendments", "TST", 1825) is None


def test_cache_read_invalid_fetched_at_datetime_returns_none(isolated_cache):
    """fetched_at is a string but not a valid ISO datetime → ValueError →
    returns None (lines 186-188 + ValueError path)."""
    _write_cache(isolated_cache, "edgar_amendments", "TST", {
        "fetched_at": "not-a-datetime",
        "lookback_days": 365,
        "filings": [],
    })
    assert _cache_read("edgar_amendments", "TST", 365) is None


def test_cache_read_expired_ttl_returns_none(isolated_cache):
    """Cache entry older than CACHE_TTL_DAYS → returns None (lines 190-191)."""
    expired_dt = datetime.now(UTC) - timedelta(days=CACHE_TTL_DAYS + 1)
    _write_cache(isolated_cache, "edgar_amendments", "TST", {
        "fetched_at": expired_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lookback_days": 365,
        "filings": [],
    })
    assert _cache_read("edgar_amendments", "TST", 365) is None


def test_cache_read_filings_not_list_returns_none(isolated_cache):
    """filings value is not a list → returns None (lines 192-194)."""
    _write_cache(isolated_cache, "edgar_amendments", "TST", {
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lookback_days": 365,
        "filings": "should-be-a-list",
    })
    assert _cache_read("edgar_amendments", "TST", 365) is None


def test_cache_read_valid_hit_returns_filings(isolated_cache):
    """Happy-path cache hit returns the filings list (line 195)."""
    filings = [{"accession": "x", "form": "10-K/A",
                "filing_date": "2025-01-01", "filing_url": "u"}]
    _write_cache(isolated_cache, "edgar_amendments", "TST", {
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lookback_days": 1825,
        "filings": filings,
    })
    result = _cache_read("edgar_amendments", "TST", 1825)
    assert result is not None
    assert result[0]["accession"] == "x"


# ---------------------------------------------------------------------------
# _cache_write — lines 204-211
# ---------------------------------------------------------------------------


def test_cache_write_creates_json_file(isolated_cache):
    """_cache_write creates the file with the expected shape (lines 204-211)."""
    filings = [{"accession": "a", "form": "10-K/A",
                "filing_date": "2025-03-01", "filing_url": "u"}]
    _cache_write("edgar_amendments", "TST", 1825, filings)
    p = isolated_cache / "edgar_amendments" / "TST.json"
    assert p.exists()
    payload = json.loads(p.read_text())
    assert payload["lookback_days"] == 1825
    assert isinstance(payload["fetched_at"], str)
    assert len(payload["filings"]) == 1


def test_cache_write_read_roundtrip(isolated_cache):
    """Write then read returns the same data."""
    filings = [{"accession": "b", "form": "NT 10-K",
                "filing_date": "2026-02-01", "filing_url": "v"}]
    _cache_write("edgar_late_filings", "TST2", 365, filings)
    result = _cache_read("edgar_late_filings", "TST2", 365)
    assert result is not None
    assert result[0]["form"] == "NT 10-K"


# ---------------------------------------------------------------------------
# invalidate_cache — lines 216-222
# ---------------------------------------------------------------------------


def test_invalidate_cache_removes_both_entries(isolated_cache):
    """invalidate_cache deletes both edgar_amendments and edgar_late_filings
    cache files for a ticker (lines 216-222)."""
    for subdir in ("edgar_amendments", "edgar_late_filings"):
        p = isolated_cache / subdir / "TST.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}", encoding="utf-8")
        assert p.exists()

    invalidate_cache("TST")

    for subdir in ("edgar_amendments", "edgar_late_filings"):
        assert not (isolated_cache / subdir / "TST.json").exists()


def test_invalidate_cache_nonexistent_ticker_does_not_raise(isolated_cache):
    """Idempotent: no file present → no exception raised."""
    invalidate_cache("NONEXISTENT_XYZ")


def test_invalidate_cache_oserror_swallowed(isolated_cache, monkeypatch):
    """OSError during unlink is swallowed (lines 220-222 except OSError: pass)."""
    for subdir in ("edgar_amendments", "edgar_late_filings"):
        p = isolated_cache / subdir / "TST3.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}", encoding="utf-8")

    def boom_unlink(self, *args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "unlink", boom_unlink)
    # Must not propagate the OSError.
    invalidate_cache("TST3")


# ---------------------------------------------------------------------------
# _filing_to_dict — lines 236-255
# ---------------------------------------------------------------------------


def test_filing_to_dict_accession_no_fallback():
    """Uses accession_no attribute when accession_number is absent (line 237)."""
    obj = SimpleNamespace(
        accession_no="0001234567-25-000001",
        form="10-K/A",
        filing_date=date(2025, 3, 15),
        filing_url="https://sec.gov/foo",
    )
    result = _filing_to_dict(obj)
    assert result is not None
    assert result["accession"] == "0001234567-25-000001"


def test_filing_to_dict_accession_number_fallback():
    """Uses accession_number when accession_no is None (line 237 fallback)."""
    obj = SimpleNamespace(
        accession_no=None,
        accession_number="0001234567-25-000002",
        form="10-Q/A",
        filing_date=date(2025, 6, 15),
        filing_url="https://sec.gov/bar",
    )
    result = _filing_to_dict(obj)
    assert result is not None
    assert result["accession"] == "0001234567-25-000002"


def test_filing_to_dict_missing_required_fields_returns_none():
    """accession/form/filing_date any of them None → returns None (line 241-242)."""
    # Missing accession.
    obj_no_acc = SimpleNamespace(
        accession_no=None, accession_number=None,
        form="10-K/A", filing_date=date(2025, 1, 1),
        filing_url="u"
    )
    assert _filing_to_dict(obj_no_acc) is None

    # Missing form.
    obj_no_form = SimpleNamespace(
        accession_no="x", accession_number=None,
        form=None, filing_date=date(2025, 1, 1),
        filing_url="u"
    )
    assert _filing_to_dict(obj_no_form) is None

    # Missing filing_date.
    obj_no_date = SimpleNamespace(
        accession_no="x", accession_number=None,
        form="10-K/A", filing_date=None,
        filing_url="u"
    )
    assert _filing_to_dict(obj_no_date) is None


def test_filing_to_dict_date_with_isoformat():
    """filing_date has an isoformat() method → uses isoformat() (lines 243-244)."""
    obj = SimpleNamespace(
        accession_no="x", form="10-K/A",
        filing_date=date(2025, 3, 15),
        filing_url="https://sec.gov/z",
    )
    result = _filing_to_dict(obj)
    assert result is not None
    assert result["filing_date"] == "2025-03-15"


def test_filing_to_dict_date_without_isoformat_str_fallback():
    """filing_date has no isoformat() → str(filing_date) path (lines 245-246)."""
    obj = SimpleNamespace(
        accession_no="x", form="10-K/A",
        filing_date="2025-03-15",  # plain string, no isoformat() method
        filing_url="https://sec.gov/z",
    )
    result = _filing_to_dict(obj)
    assert result is not None
    assert result["filing_date"] == "2025-03-15"


def test_filing_to_dict_homepage_url_fallback():
    """falls back to homepage_url when filing_url absent (line 240)."""
    obj = SimpleNamespace(
        accession_no="y", form="NT 10-K",
        filing_date=date(2025, 5, 1),
        filing_url=None,
        homepage_url="https://sec.gov/index.htm",
    )
    result = _filing_to_dict(obj)
    assert result is not None
    assert result["filing_url"] == "https://sec.gov/index.htm"


def test_filing_to_dict_empty_filing_url_when_all_absent():
    """When filing_url AND homepage_url both absent/None → filing_url defaults
    to empty string via the 'or ""' guard (line 240)."""
    obj = SimpleNamespace(
        accession_no="z", form="10-Q/A",
        filing_date=date(2025, 7, 1),
        filing_url=None,
        homepage_url=None,
    )
    result = _filing_to_dict(obj)
    assert result is not None
    assert result["filing_url"] == ""


def test_filing_to_dict_exception_returns_none():
    """If any attribute access raises, the outer except returns None (lines 253-255)."""
    class BrokenFiling:
        @property
        def accession_no(self):
            raise AttributeError("broken")

    assert _filing_to_dict(BrokenFiling()) is None


# ---------------------------------------------------------------------------
# _fetch_filings — lines 276-325 (the network-boundary mock)
# ---------------------------------------------------------------------------


def test_fetch_filings_edgartools_import_error_returns_none(
    isolated_cache, monkeypatch
):
    """edgartools ImportError → logs warning and returns None (lines 281-285)."""
    monkeypatch.setattr(
        restatement_filings, "_ensure_edgar_identity", lambda: True
    )
    monkeypatch.setitem(sys.modules, "edgar", None)  # type: ignore[arg-type]
    result = fetch_amendments("TST", lookback_days=365)
    assert result is None


def test_fetch_filings_company_init_raises_returns_none(
    isolated_cache, monkeypatch
):
    """Company(ticker) raises → outer except catches → returns None (lines 318-320)."""
    monkeypatch.setattr(
        restatement_filings, "_ensure_edgar_identity", lambda: True
    )

    class ExplodingCompany:
        def __init__(self, ticker):
            raise ConnectionError("rate limited")

    fake_edgar = SimpleNamespace(Company=ExplodingCompany, set_identity=lambda *a: None)
    monkeypatch.setitem(sys.modules, "edgar", fake_edgar)

    result = fetch_amendments("TST_TOP", lookback_days=365)
    assert result is None


def test_fetch_filings_per_form_fetch_raises_continues(isolated_cache, monkeypatch):
    """Per-form get_filings() raises → logged + continue to next form
    (lines 300-304). The other form may still succeed."""
    monkeypatch.setattr(
        restatement_filings, "_ensure_edgar_identity", lambda: True
    )

    form_fetch_calls: list[str] = []

    class FakeCompany:
        def __init__(self, ticker):
            pass

        def get_filings(self, *, form, filing_date):
            form_fetch_calls.append(form)
            if form == "10-K/A":
                raise RuntimeError("per-form fetch failed")
            # 10-Q/A succeeds with an empty list.
            return []

    fake_edgar = SimpleNamespace(Company=FakeCompany, set_identity=lambda *a: None)
    monkeypatch.setitem(sys.modules, "edgar", fake_edgar)

    result = fetch_amendments("TST_PFORM", lookback_days=365)
    # Should succeed (empty merged list) and not raise.
    assert result is not None
    assert result == []
    # Both forms were attempted.
    assert "10-K/A" in form_fetch_calls
    assert "10-Q/A" in form_fetch_calls


def test_fetch_filings_iteration_raises_continues(isolated_cache, monkeypatch):
    """Filing iteration raises for one form → logged + continue (lines 310-317).
    The overall _fetch_filings still succeeds (returns partial result)."""
    monkeypatch.setattr(
        restatement_filings, "_ensure_edgar_identity", lambda: True
    )

    good_filing = SimpleNamespace(
        accession_no="0001-25-001",
        form="10-Q/A",
        filing_date=date(2025, 3, 15),
        filing_url="https://sec.gov/10qa.htm",
        homepage_url=None,
    )

    class BoomIterable:
        def __iter__(self):
            yield good_filing
            raise RuntimeError("iteration error")

    call_count = {"n": 0}

    class FakeCompany:
        def __init__(self, ticker):
            pass

        def get_filings(self, *, form, filing_date):
            call_count["n"] += 1
            if form == "10-K/A":
                return BoomIterable()
            return []

    fake_edgar = SimpleNamespace(Company=FakeCompany, set_identity=lambda *a: None)
    monkeypatch.setitem(sys.modules, "edgar", fake_edgar)

    result = fetch_amendments("TST_ITER2", lookback_days=365)
    # Partial result returned — good_filing survived from the BoomIterable.
    assert result is not None


def test_fetch_filings_none_entry_from_filing_to_dict_skipped(
    isolated_cache, monkeypatch
):
    """_filing_to_dict returning None → entry skipped, not added to merged
    (lines 307-309 'if entry is not None' branch)."""
    monkeypatch.setattr(
        restatement_filings, "_ensure_edgar_identity", lambda: True
    )

    broken = SimpleNamespace(
        accession_no=None, accession_number=None,
        form=None, filing_date=None, filing_url=None,
    )

    class FakeCompany:
        def __init__(self, ticker):
            pass

        def get_filings(self, *, form, filing_date):
            return [broken]

    fake_edgar = SimpleNamespace(Company=FakeCompany, set_identity=lambda *a: None)
    monkeypatch.setitem(sys.modules, "edgar", fake_edgar)

    result = fetch_amendments("TST_SKIP", lookback_days=365)
    assert result == []


# ---------------------------------------------------------------------------
# fetch_amendments / fetch_late_filings — default lookback_days path
# ---------------------------------------------------------------------------


def test_fetch_amendments_uses_default_lookback_when_none(
    isolated_cache, monkeypatch
):
    """Calling fetch_amendments(ticker) without lookback_days sets the
    default from config.RESTATEMENT_HISTORY_LOOKBACK_DAYS (lines 336-337)."""
    calls: list[int] = []

    def fake_fetch_filings(ticker, forms, lookback_days, cache_subdir):
        calls.append(lookback_days)
        return []

    monkeypatch.setattr(restatement_filings, "_fetch_filings", fake_fetch_filings)
    fetch_amendments("TST")
    assert calls == [config.RESTATEMENT_HISTORY_LOOKBACK_DAYS]


def test_fetch_late_filings_uses_default_lookback_when_none(
    isolated_cache, monkeypatch
):
    """Calling fetch_late_filings(ticker) without lookback_days sets the
    default from config.LATE_FILING_LOOKBACK_DAYS (lines 354-355)."""
    calls: list[int] = []

    def fake_fetch_filings(ticker, forms, lookback_days, cache_subdir):
        calls.append(lookback_days)
        return []

    monkeypatch.setattr(restatement_filings, "_fetch_filings", fake_fetch_filings)
    fetch_late_filings("TST")
    assert calls == [config.LATE_FILING_LOOKBACK_DAYS]


# ---------------------------------------------------------------------------
# check_restatement_history — None-fetch path (line 397, 398->401)
# ---------------------------------------------------------------------------


def test_check_restatement_history_fetch_none_returns_clean(monkeypatch):
    """fetch_amendments returns None → check_restatement_history returns
    RestatementHistoryResult(fired=False) without raising (lines 407-410)."""
    monkeypatch.setattr(restatement_filings, "fetch_amendments", lambda *a, **k: None)
    result = check_restatement_history("TST", asof=ASOF)
    assert isinstance(result, RestatementHistoryResult)
    assert result.fired is False
    assert result.count == 0
    assert result.latest_filing_date is None


def test_check_restatement_history_default_lookback_uses_config(monkeypatch):
    """lookback_days=None → defaults to config.RESTATEMENT_HISTORY_LOOKBACK_DAYS.
    Covers the 'if lookback_days is None:' branch (line 399-400)."""
    captured: list[int] = []

    def fake_fetch(ticker, lookback_days=None):
        if lookback_days is not None:
            captured.append(lookback_days)
        return []

    monkeypatch.setattr(restatement_filings, "fetch_amendments", fake_fetch)
    check_restatement_history("TST", asof=ASOF)  # lookback_days not provided
    assert captured == [config.RESTATEMENT_HISTORY_LOOKBACK_DAYS]


# ---------------------------------------------------------------------------
# check_late_filing — None-fetch path (line 442, 443->446)
# ---------------------------------------------------------------------------


def test_check_late_filing_fetch_none_returns_clean(monkeypatch):
    """fetch_late_filings returns None → check_late_filing returns
    LateFilingResult(fired=False) without raising (lines 452-459)."""
    monkeypatch.setattr(restatement_filings, "fetch_late_filings", lambda *a, **k: None)
    result = check_late_filing("TST", asof=ASOF)
    assert isinstance(result, LateFilingResult)
    assert result.fired is False
    assert result.count == 0
    assert result.latest_form is None


def test_check_late_filing_default_lookback_uses_config(monkeypatch):
    """lookback_days=None → defaults to config.LATE_FILING_LOOKBACK_DAYS
    (lines 443-444 branch)."""
    captured: list[int] = []

    def fake_fetch(ticker, lookback_days=None):
        if lookback_days is not None:
            captured.append(lookback_days)
        return []

    monkeypatch.setattr(restatement_filings, "fetch_late_filings", fake_fetch)
    check_late_filing("TST", asof=ASOF)
    assert captured == [config.LATE_FILING_LOOKBACK_DAYS]


# ---------------------------------------------------------------------------
# _parse_iso_date — lines 499-504
# ---------------------------------------------------------------------------


def test_parse_iso_date_non_string_returns_none():
    """Non-string input → returns None immediately (line 500)."""
    assert _parse_iso_date(None) is None
    assert _parse_iso_date(20250101) is None
    assert _parse_iso_date(date(2025, 1, 1)) is None


def test_parse_iso_date_malformed_string_returns_none():
    """Valid str but not ISO date → ValueError → returns None (lines 503-504)."""
    assert _parse_iso_date("not-a-date") is None
    assert _parse_iso_date("2025/01/01") is None  # wrong separator
    assert _parse_iso_date("") is None


def test_parse_iso_date_valid_iso_string():
    """Valid ISO date string → returns parsed date object (line 502)."""
    result = _parse_iso_date("2025-09-01")
    assert result == date(2025, 9, 1)


def test_parse_iso_date_truncates_to_10_chars():
    """String longer than 10 chars is sliced to first 10 (line 502 value[:10])."""
    result = _parse_iso_date("2025-09-01T10:30:00Z")
    assert result == date(2025, 9, 1)


# ---------------------------------------------------------------------------
# get_amendment_filing_dates — lines 521-541
# ---------------------------------------------------------------------------


def test_get_amendment_filing_dates_fetch_returns_none(monkeypatch):
    """fetch_amendments returns None → get_amendment_filing_dates returns ()
    (lines 531-532)."""
    monkeypatch.setattr(restatement_filings, "fetch_amendments", lambda *a, **k: None)
    result = get_amendment_filing_dates("TST", asof=ASOF)
    assert result == ()


def test_get_amendment_filing_dates_filters_out_of_window(monkeypatch):
    """Filings outside the lookback window are excluded (line 536 check)."""
    # 6-year-old amendment — outside RESTATEMENT_HISTORY_LOOKBACK_DAYS (5y).
    old_date = ASOF - timedelta(days=2200)
    recent_date = ASOF - timedelta(days=100)
    filings = [
        {"accession": "old", "form": "10-K/A", "filing_date": old_date.isoformat()},
        {"accession": "new", "form": "10-K/A", "filing_date": recent_date.isoformat()},
    ]
    result = get_amendment_filing_dates(
        "TST", asof=ASOF,
        lookback_days=config.RESTATEMENT_HISTORY_LOOKBACK_DAYS,
        filings_override=filings,
    )
    assert len(result) == 1
    assert result[0] == recent_date


def test_get_amendment_filing_dates_parse_none_entry_skipped():
    """_parse_iso_date returns None for a malformed date → entry skipped
    (lines 538-540 'if d is not None' branch)."""
    filings = [
        {"accession": "bad", "form": "10-K/A", "filing_date": "not-a-date"},
        {"accession": "ok", "form": "10-K/A",
         "filing_date": (ASOF - timedelta(days=30)).isoformat()},
    ]
    result = get_amendment_filing_dates(
        "TST", asof=ASOF,
        lookback_days=config.RESTATEMENT_HISTORY_LOOKBACK_DAYS,
        filings_override=filings,
    )
    assert len(result) == 1


def test_get_amendment_filing_dates_default_asof_is_today(monkeypatch):
    """When asof is not provided, defaults to date.today() (lines 521-522
    'if asof is None: asof = date.today()')."""
    # We can't easily intercept `date.today()` but we can verify the call
    # doesn't raise and returns a tuple.
    result = get_amendment_filing_dates("TST", filings_override=[])
    assert isinstance(result, tuple)
    assert result == ()


# ---------------------------------------------------------------------------
# check_restatement_history + check_late_filing — edge: no matching entries
# ---------------------------------------------------------------------------


def test_check_restatement_history_all_out_of_window_returns_clean():
    """All filings outside lookback → fired=False, count=0 (lines 418-421)."""
    asof = date(2026, 5, 16)
    # 6-year-old entry.
    old = (asof - timedelta(days=2200)).isoformat()
    result = check_restatement_history(
        "TST",
        asof=asof,
        lookback_days=1825,
        filings_override=[
            {"accession": "old", "form": "10-K/A", "filing_date": old,
             "filing_url": "u"}
        ],
    )
    assert result.fired is False
    assert result.count == 0


def test_check_late_filing_all_out_of_window_returns_clean():
    """All filings outside lookback → fired=False (lines 467-474)."""
    asof = date(2026, 5, 16)
    old = (asof - timedelta(days=400)).isoformat()
    result = check_late_filing(
        "TST",
        asof=asof,
        lookback_days=365,
        filings_override=[
            {"accession": "old", "form": "NT 10-K", "filing_date": old,
             "filing_url": "u"}
        ],
    )
    assert result.fired is False
    assert result.count == 0


# ---------------------------------------------------------------------------
# Dataclass immutability
# ---------------------------------------------------------------------------


def test_restatement_history_result_is_frozen():
    from dataclasses import FrozenInstanceError
    r = RestatementHistoryResult(
        fired=True, count=1, latest_filing_date="2026-01-01",
        latest_filing_url="u"
    )
    with pytest.raises(FrozenInstanceError):
        r.fired = False  # type: ignore[misc]


def test_late_filing_result_is_frozen():
    from dataclasses import FrozenInstanceError
    r = LateFilingResult(
        fired=True, count=1, latest_filing_date="2026-01-01",
        latest_filing_url="u", latest_form="NT 10-K"
    )
    with pytest.raises(FrozenInstanceError):
        r.count = 99  # type: ignore[misc]


def test_high_confidence_restatement_result_is_frozen():
    from dataclasses import FrozenInstanceError
    r = HighConfidenceRestatementResult(
        fired=True, co_occurrence_count=2,
        latest_amendment_date="2025-09-01",
        latest_non_reliance_date="2025-08-20"
    )
    with pytest.raises(FrozenInstanceError):
        r.co_occurrence_count = 0  # type: ignore[misc]
