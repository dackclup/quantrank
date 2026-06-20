"""Offline coverage tests for compute.scoring.eight_k_events.

Covers the previously-uncovered lines (baseline ~68%):
- Line 112: _ttl_jitter_seconds zero-window branch
- Lines 166-182: _ensure_edgar_identity (UA unset + set_identity failure)
- Lines 208, 211-212: _cache_read invalid fetched_at + ValueError branch
- Line 223: _cache_read filings not a list
- Lines 241-247: _cache_write OSError cleanup path
- Lines 316-341: _filing_to_dict — date object, datetime object, missing url,
  html as property (not callable), html raises
- Lines 372, 376-378, 388-390, 395-399: fetch_recent_8k_filings —
  edgartools ImportError, Company() raises, iteration raises, partial-result
- Lines 415-416, 418: _filing_date_within future-date guard + ValueError
- Line 446: _check_item non-dict entry guard
- Lines 522-527, 529, 534, 542-543: get_non_reliance_filing_dates —
  None fetch path, non-dict entry, malformed date

Design: monkeypatch the EDGAR boundary (edgartools / edgar module) so ALL
tests run offline. No @pytest.mark.network markers here — this file is
pure offline. Each test targets a specific previously-uncovered branch.
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
from compute.scoring import eight_k_events
from compute.scoring.eight_k_events import (
    _cache_read,
    _cache_write,
    _filing_date_within,
    _filing_to_dict,
    _ttl_jitter_seconds,
    check_auditor_change,
    check_non_reliance,
    fetch_recent_8k_filings,
    get_non_reliance_filing_dates,
    invalidate_cache,
)

ASOF = date(2026, 5, 10)


def _filing(
    days_ago: int,
    *,
    items: list[str] | None = None,
    item_text_excerpts: dict[str, str] | None = None,
    url: str = "https://www.sec.gov/Archives/edgar/data/0/test.htm",
) -> dict:
    """Build a synthetic cached-filing dict — mirrors the sibling test builder."""
    fd = ASOF - timedelta(days=days_ago)
    return {
        "filing_date": fd.strftime("%Y-%m-%d"),
        "filing_url": url,
        "items": list(items or []),
        "item_text_excerpts": dict(item_text_excerpts or {}),
    }


# ---------------------------------------------------------------------------
# _ttl_jitter_seconds — zero-window branch (line 112)
# ---------------------------------------------------------------------------


def test_ttl_jitter_zero_window_returns_zero(monkeypatch):
    """When EDGAR_8K_CACHE_TTL_JITTER_SECONDS is 0, the function must
    return 0 without hashing (the short-circuit branch at line 112)."""
    monkeypatch.setattr(config, "EDGAR_8K_CACHE_TTL_JITTER_SECONDS", 0)
    assert _ttl_jitter_seconds("AAPL") == 0
    assert _ttl_jitter_seconds("MSFT") == 0


def test_ttl_jitter_positive_window_deterministic():
    """With a positive window the jitter is deterministic (SHA-256, not
    PYTHONHASHSEED-salted), stable across calls."""
    j1 = _ttl_jitter_seconds("AAPL")
    j2 = _ttl_jitter_seconds("AAPL")
    assert j1 == j2
    assert 0 <= j1 < config.EDGAR_8K_CACHE_TTL_JITTER_SECONDS


def test_ttl_jitter_different_tickers_differ():
    """Different tickers should (almost always) produce different jitter
    values due to SHA-256 entropy."""
    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
    values = [_ttl_jitter_seconds(t) for t in tickers]
    # Allow at most 1 collision in 5 — SHA-256 over 5 values should spread.
    unique = len(set(values))
    assert unique >= 4, f"Suspiciously low jitter diversity: {values}"


# ---------------------------------------------------------------------------
# _ensure_edgar_identity — lines 166-182
# ---------------------------------------------------------------------------


def test_ensure_edgar_identity_missing_ua_returns_false(monkeypatch):
    """No EDGAR_USER_AGENT → _ensure_edgar_identity returns False without
    raising. Covers lines 169-174 (warning + return False)."""
    # Reset the module-level _IDENTITY_SET flag so the function doesn't
    # short-circuit via the 'if _IDENTITY_SET: return True' branch.
    monkeypatch.setattr(eight_k_events, "_IDENTITY_SET", False)
    monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)
    result = eight_k_events._ensure_edgar_identity()
    assert result is False


def test_ensure_edgar_identity_set_identity_raises_returns_false(monkeypatch):
    """set_identity() raising → function logs warning and returns False.
    Covers the except branch at lines 178-180."""
    monkeypatch.setattr(eight_k_events, "_IDENTITY_SET", False)
    monkeypatch.setenv("EDGAR_USER_AGENT", "Test Agent test@example.com")

    # Inject a fake edgar module whose set_identity raises.
    fake_edgar = SimpleNamespace(
        set_identity=lambda ua: (_ for _ in ()).throw(RuntimeError("boom")),
        Company=MagicMock(),
    )
    monkeypatch.setitem(sys.modules, "edgar", fake_edgar)
    result = eight_k_events._ensure_edgar_identity()
    assert result is False


def test_ensure_edgar_identity_success_sets_flag(monkeypatch):
    """Happy-path: UA set + set_identity succeeds → returns True and
    sets the module-level _IDENTITY_SET flag (line 181-182)."""
    monkeypatch.setattr(eight_k_events, "_IDENTITY_SET", False)
    monkeypatch.setenv("EDGAR_USER_AGENT", "Test Agent test@example.com")

    fake_edgar = SimpleNamespace(
        set_identity=lambda ua: None,
        Company=MagicMock(),
    )
    monkeypatch.setitem(sys.modules, "edgar", fake_edgar)
    result = eight_k_events._ensure_edgar_identity()
    assert result is True
    assert eight_k_events._IDENTITY_SET is True

    # Clean up so other tests that manipulate _IDENTITY_SET don't see stale True.
    monkeypatch.setattr(eight_k_events, "_IDENTITY_SET", False)


def test_ensure_edgar_identity_already_set_returns_true_immediately(monkeypatch):
    """When _IDENTITY_SET is already True, function returns True without
    touching os.environ or edgar — covers the early-return branch line 167."""
    monkeypatch.setattr(eight_k_events, "_IDENTITY_SET", True)
    monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)
    result = eight_k_events._ensure_edgar_identity()
    assert result is True
    # Restore.
    monkeypatch.setattr(eight_k_events, "_IDENTITY_SET", False)


# ---------------------------------------------------------------------------
# _cache_read — lines 208, 211-212, 223
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_cache(tmp_path: Path, monkeypatch):
    """Redirect EDGAR_8K_CACHE_DIR to a tmp dir for cache tests."""
    cache_dir = tmp_path / "edgar_8k_cache"
    monkeypatch.setattr(config, "EDGAR_8K_CACHE_DIR", cache_dir)
    return cache_dir


def test_cache_read_missing_fetched_at_returns_none(isolated_cache):
    """Cache file present but lacks 'fetched_at' key → returns None (line 208)."""
    cache_path = isolated_cache / "TST.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({"lookback_days": 365, "filings": []}))
    assert _cache_read("TST", 365) is None


def test_cache_read_invalid_fetched_at_iso_returns_none(isolated_cache):
    """'fetched_at' present but not a valid ISO datetime → ValueError caught →
    returns None (lines 211-212)."""
    cache_path = isolated_cache / "TST.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"fetched_at": "not-a-datetime", "lookback_days": 365, "filings": []})
    )
    assert _cache_read("TST", 365) is None


def test_cache_read_filings_not_list_returns_none(isolated_cache):
    """Cache hit within TTL but 'filings' is not a list → returns None (line 223)."""
    cache_path = isolated_cache / "TST.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "lookback_days": 365,
                "filings": "not-a-list",
            }
        )
    )
    assert _cache_read("TST", 365) is None


# ---------------------------------------------------------------------------
# _cache_write — OSError cleanup path (lines 241-247)
# ---------------------------------------------------------------------------


def test_cache_write_oserror_does_not_raise(isolated_cache, monkeypatch):
    """When the file write raises OSError, _cache_write logs and returns
    without propagating. The tmp file cleanup path is also exercised (lines 241-247)."""
    cache_dir = isolated_cache
    cache_dir.mkdir(parents=True, exist_ok=True)

    real_open = open

    def boom_open(path, mode="r", **kwargs):
        # Raise only on the .tmp write path.
        if "tmp" in str(path) and "w" in mode:
            raise OSError("disk full")
        return real_open(path, mode, **kwargs)

    monkeypatch.setattr("builtins.open", boom_open)
    # Should not raise even though the write fails.
    _cache_write("TST", 365, [{"filing_date": "2026-01-01"}])


# ---------------------------------------------------------------------------
# _filing_to_dict — uncovered branches (lines 316-341)
# ---------------------------------------------------------------------------


def test_filing_to_dict_returns_none_when_no_filing_date():
    """filing_date attribute is None → returns None early (line 319-320)."""
    obj = SimpleNamespace(filing_date=None, url="https://sec.gov/x.htm")
    assert _filing_to_dict(obj) is None


def test_filing_to_dict_returns_none_when_no_url():
    """Both url and filing_url attributes absent → returns None (line 319-320)."""
    obj = SimpleNamespace(filing_date=date(2026, 1, 1))
    # No url / filing_url attribute at all.
    assert _filing_to_dict(obj) is None


def test_filing_to_dict_date_object_formats_correctly():
    """filing_date is a datetime.date instance → strftime path (lines 321-322)."""
    obj = SimpleNamespace(
        filing_date=date(2026, 3, 15),
        url="https://sec.gov/x.htm",
        html=None,
    )
    result = _filing_to_dict(obj)
    assert result is not None
    assert result["filing_date"] == "2026-03-15"


def test_filing_to_dict_datetime_object_formats_correctly():
    """filing_date is a datetime.datetime instance → strftime path (line 322)."""
    obj = SimpleNamespace(
        filing_date=datetime(2026, 3, 15, 10, 30, 0),
        url="https://sec.gov/x.htm",
        html=None,
    )
    result = _filing_to_dict(obj)
    assert result is not None
    assert result["filing_date"] == "2026-03-15"


def test_filing_to_dict_string_date_sliced_to_10():
    """filing_date is a plain string → str(filing_date)[:10] path (line 324)."""
    obj = SimpleNamespace(
        filing_date="2026-03-15T10:30:00Z",  # longer than 10 chars
        url="https://sec.gov/x.htm",
        html=None,
    )
    result = _filing_to_dict(obj)
    assert result is not None
    assert result["filing_date"] == "2026-03-15"


def test_filing_to_dict_html_as_non_callable_property():
    """html is a non-callable attribute (already a string, not a method).
    Exercises the 'html_attr() if callable(html_attr) else html_attr' else-branch
    (line 333)."""
    html = "<p>Item 4.02 Non-Reliance disclosure text here.</p>"
    obj = SimpleNamespace(
        filing_date=date(2026, 3, 15),
        url="https://sec.gov/x.htm",
        html=html,  # attribute, not method
    )
    result = _filing_to_dict(obj)
    assert result is not None
    assert "Item 4.02" in result["items"]


def test_filing_to_dict_html_raises_gracefully():
    """html() callable raises → exception caught, items stays [] (lines 338-339)."""
    def boom_html():
        raise ValueError("parse error")

    obj = SimpleNamespace(
        filing_date=date(2026, 3, 15),
        url="https://sec.gov/x.htm",
        html=boom_html,
    )
    result = _filing_to_dict(obj)
    assert result is not None
    assert result["items"] == []
    assert result["item_text_excerpts"] == {}


def test_filing_to_dict_header_attribute_raises_returns_none():
    """If getattr on filing_date itself raises (pathological object), the
    outer except returns None (lines 325-327)."""
    class BrokenFiling:
        @property
        def filing_date(self):
            raise RuntimeError("broken attribute")

        @property
        def url(self):
            return "https://sec.gov/x.htm"

    assert _filing_to_dict(BrokenFiling()) is None


def test_filing_to_dict_uses_filing_url_when_url_absent():
    """Falls back to filing.filing_url when filing.url is absent
    (getattr fallback at line 318)."""
    obj = SimpleNamespace(
        filing_date=date(2026, 3, 15),
        filing_url="https://sec.gov/filing.htm",  # note: filing_url not url
        html=None,
    )
    # url attribute doesn't exist → getattr returns None → tries filing_url.
    result = _filing_to_dict(obj)
    assert result is not None
    assert result["filing_url"] == "https://sec.gov/filing.htm"


# ---------------------------------------------------------------------------
# fetch_recent_8k_filings — uncovered branches (lines 372-399)
# ---------------------------------------------------------------------------


def test_fetch_recent_edgartools_import_error_returns_none(isolated_cache, monkeypatch):
    """edgartools not importable → logs warning and returns None (lines 375-378)."""
    monkeypatch.setattr(eight_k_events, "_IDENTITY_SET", False)
    monkeypatch.setattr(eight_k_events, "_ensure_edgar_identity", lambda: True)
    # Make 'edgar' un-importable.
    monkeypatch.setitem(sys.modules, "edgar", None)  # type: ignore[arg-type]
    result = fetch_recent_8k_filings("TST", lookback_days=365)
    assert result is None


def test_fetch_recent_company_init_raises_returns_none(isolated_cache, monkeypatch):
    """Company(ticker) raises → logged and returns None (lines 388-390)."""
    monkeypatch.setattr(eight_k_events, "_ensure_edgar_identity", lambda: True)

    class ExplodingCompany:
        def __init__(self, ticker):
            raise ConnectionError("rate limited")

    fake_edgar = SimpleNamespace(Company=ExplodingCompany, set_identity=lambda *a: None)
    monkeypatch.setitem(sys.modules, "edgar", fake_edgar)

    result = fetch_recent_8k_filings("TST", lookback_days=365)
    assert result is None


def test_fetch_recent_iteration_raises_returns_partial(isolated_cache, monkeypatch):
    """Filing iteration raises mid-loop → partial result cached and returned
    (lines 395-400). The function must NOT propagate the exception."""
    monkeypatch.setattr(eight_k_events, "_ensure_edgar_identity", lambda: True)

    good_filing = SimpleNamespace(
        filing_date=date(2026, 1, 10),
        url="https://sec.gov/good.htm",
        html=lambda: "<p>Item 4.02 Good filing.</p>",
    )

    class BoomIterable:
        def __init__(self):
            self._yielded = False

        def __iter__(self):
            yield good_filing
            raise RuntimeError("iteration error mid-loop")

    class FakeCompany:
        def __init__(self, ticker):
            pass

        def get_filings(self, *, form, filing_date):
            return BoomIterable()

    fake_edgar = SimpleNamespace(Company=FakeCompany, set_identity=lambda *a: None)
    monkeypatch.setitem(sys.modules, "edgar", fake_edgar)

    result = fetch_recent_8k_filings("TST_ITER", lookback_days=365)
    # Must not be None (partial result is returned and cached).
    assert result is not None
    # The good filing that landed before the exception should be in the result.
    assert len(result) >= 1


def test_fetch_recent_none_entry_from_filing_to_dict_skipped(isolated_cache, monkeypatch):
    """_filing_to_dict returning None for an entry causes that entry to be
    skipped (not added to 'out'). Covers the 'if entry is not None' branch
    (lines 396-397) for the False path."""
    monkeypatch.setattr(eight_k_events, "_ensure_edgar_identity", lambda: True)

    # A filing object that will produce None from _filing_to_dict.
    broken_filing = SimpleNamespace(filing_date=None, url=None)

    class FakeCompany:
        def __init__(self, ticker):
            pass

        def get_filings(self, *, form, filing_date):
            return [broken_filing]

    fake_edgar = SimpleNamespace(Company=FakeCompany, set_identity=lambda *a: None)
    monkeypatch.setitem(sys.modules, "edgar", fake_edgar)

    result = fetch_recent_8k_filings("TST_SKIP", lookback_days=365)
    assert result == []  # broken entry skipped, empty list returned + cached


# ---------------------------------------------------------------------------
# _filing_date_within — future date and ValueError branches (lines 415-418)
# ---------------------------------------------------------------------------


def test_filing_date_within_future_date_returns_false():
    """Filing date in the future → fd > asof → returns False (lines 417-418)."""
    asof = date(2026, 5, 10)
    assert _filing_date_within("2026-12-31", asof, 365) is False


def test_filing_date_within_malformed_date_string_returns_false():
    """Malformed date string → ValueError caught → returns False (lines 415-416)."""
    asof = date(2026, 5, 10)
    assert _filing_date_within("not-a-date", asof, 365) is False
    assert _filing_date_within("", asof, 365) is False
    assert _filing_date_within("2026/05/10", asof, 365) is False  # wrong separator


def test_filing_date_within_on_boundary_inclusive():
    """Exactly on the boundary (days_ago == lookback_days) is inclusive."""
    asof = date(2026, 5, 10)
    boundary = asof - timedelta(days=365)
    assert _filing_date_within(boundary.strftime("%Y-%m-%d"), asof, 365) is True


# ---------------------------------------------------------------------------
# _check_item — non-dict entry guard (line 446)
# ---------------------------------------------------------------------------


def test_check_item_skips_non_dict_entries_in_filings():
    """Non-dict entries in the filings list are silently skipped (line 446
    'if not isinstance(entry, dict): continue')."""
    filings = [
        None,          # None entry
        "garbage",     # string entry
        42,            # int entry
        _filing(30, items=["Item 4.02"]),  # valid entry that fires
    ]
    # _check_item is used internally via check_non_reliance with filings kwarg.
    flag = check_non_reliance("TST", asof=ASOF, filings=filings)  # type: ignore[arg-type]
    assert flag.fired is True  # the valid entry fired


def test_check_item_empty_items_list_in_entry():
    """Filing dict with 'items': [] (or key absent) does not fire."""
    filings = [
        {"filing_date": (ASOF - timedelta(days=30)).strftime("%Y-%m-%d"),
         "filing_url": "https://sec.gov/x.htm",
         "items": [],
         "item_text_excerpts": {}},
    ]
    flag = check_non_reliance("TST", asof=ASOF, filings=filings)
    assert flag.fired is False


def test_check_item_missing_items_key_in_entry():
    """Filing dict with no 'items' key behaves like empty items list."""
    filings = [
        {"filing_date": (ASOF - timedelta(days=30)).strftime("%Y-%m-%d"),
         "filing_url": "https://sec.gov/x.htm"},
    ]
    flag = check_non_reliance("TST", asof=ASOF, filings=filings)
    assert flag.fired is False


# ---------------------------------------------------------------------------
# get_non_reliance_filing_dates — uncovered paths (lines 522-543)
# ---------------------------------------------------------------------------


def test_get_non_reliance_filing_dates_fetch_returns_none(monkeypatch):
    """When fetch_recent_8k_filings returns None (identity missing),
    get_non_reliance_filing_dates returns () (lines 527-529)."""
    monkeypatch.setattr(eight_k_events, "fetch_recent_8k_filings", lambda *a, **k: None)
    result = get_non_reliance_filing_dates("TST", asof=ASOF)
    assert result == ()


def test_get_non_reliance_filing_dates_non_dict_entry_skipped():
    """Non-dict entries in the filings list are skipped (line 534 isinstance check)."""
    filings = [
        None,
        "string",
        _filing(20, items=["Item 4.02"]),
        _filing(50, items=["Item 4.02"]),
    ]
    result = get_non_reliance_filing_dates("TST", asof=ASOF, filings=filings)  # type: ignore[arg-type]
    assert len(result) == 2
    assert all(isinstance(d, date) for d in result)


def test_get_non_reliance_filing_dates_malformed_date_string_skipped():
    """A filing with Item 4.02 but a malformed filing_date is skipped via
    the ValueError-catching continue branch (lines 541-543)."""
    filings = [
        {
            "filing_date": "bad-date",
            "filing_url": "https://sec.gov/x.htm",
            "items": ["Item 4.02"],
            "item_text_excerpts": {},
        },
        _filing(10, items=["Item 4.02"]),  # valid
    ]
    result = get_non_reliance_filing_dates("TST", asof=ASOF, filings=filings)
    # Only the valid entry is returned; malformed date skipped.
    assert len(result) == 1


def test_get_non_reliance_filing_dates_custom_lookback_window(monkeypatch):
    """custom lookback_days overrides the default EIGHT_K_LOOKBACK_DAYS_VETO.
    Exercises the 'if lookback_days is None: lookback_days = ...' else-path
    (lines 523-524 for the else branch when lookback_days is provided)."""
    filings = [
        _filing(days_ago=500, items=["Item 4.02"]),  # inside 730d but outside 365d
        _filing(days_ago=10, items=["Item 4.02"]),
    ]
    # With default 365d window: only the 10-day entry.
    result_default = get_non_reliance_filing_dates("TST", asof=ASOF, filings=filings)
    assert len(result_default) == 1

    # With 730d window: both entries.
    result_wide = get_non_reliance_filing_dates(
        "TST", asof=ASOF, lookback_days=730, filings=filings
    )
    assert len(result_wide) == 2


def test_get_non_reliance_filing_dates_no_item_4_02_in_entry():
    """Filing within window but no Item 4.02 → not added to dates (line 539 check)."""
    filings = [
        _filing(days_ago=30, items=["Item 5.02", "Item 9.01"]),
    ]
    result = get_non_reliance_filing_dates("TST", asof=ASOF, filings=filings)
    assert result == ()


# ---------------------------------------------------------------------------
# Graceful degradation — check_* callers when fetch returns None
# ---------------------------------------------------------------------------


def test_check_non_reliance_no_identity_no_filings_kwarg_returns_clean(monkeypatch):
    """When called without filings kwarg and identity is absent, the function
    gracefully returns a fired=False flag (vs raising)."""
    monkeypatch.setattr(eight_k_events, "_IDENTITY_SET", False)
    monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)
    flag = check_non_reliance("TST", asof=ASOF)
    assert flag.fired is False
    assert flag.filing_date is None
    assert flag.filing_url is None
    assert flag.raw_item_text is None


def test_check_auditor_change_no_identity_no_filings_kwarg_returns_clean(monkeypatch):
    """Same graceful path for check_auditor_change."""
    monkeypatch.setattr(eight_k_events, "_IDENTITY_SET", False)
    monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)
    flag = check_auditor_change("TST", asof=ASOF)
    assert flag.fired is False


# ---------------------------------------------------------------------------
# invalidate_cache — idempotent on already-absent file
# ---------------------------------------------------------------------------


def test_invalidate_cache_nonexistent_file_is_idempotent(isolated_cache):
    """Calling invalidate_cache on a ticker with no cache file does not raise."""
    invalidate_cache("NONEXISTENT_TICKER_XYZ")  # must not raise


# ---------------------------------------------------------------------------
# _cache_write — happy path roundtrip
# ---------------------------------------------------------------------------


def test_cache_write_and_read_roundtrip(isolated_cache):
    """_cache_write followed by _cache_read returns the same filings list."""
    filings = [
        {"filing_date": "2026-01-15", "filing_url": "https://sec.gov/x.htm",
         "items": ["Item 4.02"], "item_text_excerpts": {}},
    ]
    _cache_write("RDT", 365, filings)
    result = _cache_read("RDT", 365)
    assert result is not None
    assert result[0]["filing_date"] == "2026-01-15"
    assert result[0]["items"] == ["Item 4.02"]
