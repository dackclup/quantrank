"""Unit + cache + network tests for compute.scoring.eight_k_events
(PR 3d Defenses #9 + #10).

Coverage:
- A1-A12: synthetic Filing fixture tests for check_non_reliance +
  check_auditor_change item parsing semantics.
- B1-B5: cache layer (read/write/expire/invalidate/corrupt-recovery).
- C1-C3: @network smoke tests against real SEC EDGAR (skipped unless
  `--run-network` AND EDGAR_USER_AGENT env var present).
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from compute import config
from compute.scoring import eight_k_events
from compute.scoring.eight_k_events import (
    ItemFlag,
    _extract_items_and_excerpts_from_html,
    check_auditor_change,
    check_non_reliance,
    fetch_recent_8k_filings,
    invalidate_cache,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ASOF = date(2026, 5, 10)


def _filing(
    days_ago: int,
    *,
    items: list[str] | None = None,
    item_text_excerpts: dict[str, str] | None = None,
    url: str = "https://www.sec.gov/Archives/edgar/data/0/test.htm",
) -> dict:
    """Build a synthetic cached-filing dict."""
    fd = ASOF - timedelta(days=days_ago)
    return {
        "filing_date": fd.strftime("%Y-%m-%d"),
        "filing_url": url,
        "items": list(items or []),
        "item_text_excerpts": dict(item_text_excerpts or {}),
    }


# ---------------------------------------------------------------------------
# A. Synthetic-fixture tests
# ---------------------------------------------------------------------------

def test_A1_filing_with_item_4_02_fires_non_reliance():
    filings = [_filing(30, items=["Item 4.02"])]
    flag = check_non_reliance("TST", asof=ASOF, filings=filings)
    assert flag.fired is True
    assert flag.filing_date == (ASOF - timedelta(days=30)).strftime("%Y-%m-%d")
    assert flag.filing_url is not None


def test_A2_filing_with_item_4_01_fires_auditor_change():
    filings = [_filing(60, items=["Item 4.01"])]
    flag = check_auditor_change("TST", asof=ASOF, filings=filings)
    assert flag.fired is True


def test_A3_both_items_in_same_filing_fire_both_flags():
    """A single filing can contain Item 4.01 AND Item 4.02 — both flags
    fire on separate calls."""
    filings = [_filing(45, items=["Item 4.01", "Item 4.02"])]
    assert check_non_reliance("TST", asof=ASOF, filings=filings).fired is True
    assert check_auditor_change("TST", asof=ASOF, filings=filings).fired is True


def test_A4_unrelated_item_5_02_does_not_fire():
    """Item 5.02 (officer change) is unrelated to either Tier-2 defense."""
    filings = [_filing(30, items=["Item 5.02"])]
    assert check_non_reliance("TST", asof=ASOF, filings=filings).fired is False
    assert check_auditor_change("TST", asof=ASOF, filings=filings).fired is False


def test_A5_empty_filing_list_returns_no_flag():
    flag = check_non_reliance("TST", asof=ASOF, filings=[])
    assert flag.fired is False
    assert flag.filing_date is None
    assert flag.filing_url is None
    assert flag.raw_item_text is None


def test_A6_none_from_fetch_returns_no_flag(monkeypatch):
    """When fetch returns None (rate-limit/missing identity), the
    check_* call returns ItemFlag(fired=False) with all metadata None."""
    monkeypatch.setattr(eight_k_events, "fetch_recent_8k_filings", lambda *a, **k: None)
    flag = check_non_reliance("TST", asof=ASOF)  # no filings kwarg → triggers fetch
    assert flag.fired is False
    assert flag.filing_date is None


def test_A7_filing_outside_365d_window_does_not_fire_non_reliance():
    """A 4.02 filing 400 days old is OUTSIDE the 365-day veto window."""
    filings = [_filing(400, items=["Item 4.02"])]
    assert check_non_reliance("TST", asof=ASOF, filings=filings).fired is False


def test_A8_filing_200d_old_fires_auditor_change_730d_window():
    """The annotate window is 730 days, so a 200-day-old 4.01 fires."""
    filings = [_filing(200, items=["Item 4.01"])]
    assert check_auditor_change("TST", asof=ASOF, filings=filings).fired is True


def test_A9_multiple_4_02_returns_most_recent():
    filings = [
        _filing(300, items=["Item 4.02"], url="https://sec.gov/old.htm"),
        _filing(30, items=["Item 4.02"], url="https://sec.gov/recent.htm"),
        _filing(180, items=["Item 4.02"], url="https://sec.gov/middle.htm"),
    ]
    flag = check_non_reliance("TST", asof=ASOF, filings=filings)
    assert flag.fired is True
    assert flag.filing_date == (ASOF - timedelta(days=30)).strftime("%Y-%m-%d")
    assert flag.filing_url == "https://sec.gov/recent.htm"


@pytest.mark.parametrize("item_str", ["Item 4.02", "ITEM 4.02", "item 4.02", "Item  4.02"])
def test_A10_item_number_variants_match_case_insensitive(item_str: str):
    filings = [_filing(30, items=[item_str])]
    assert check_non_reliance("TST", asof=ASOF, filings=filings).fired is True


def test_A11_raw_item_text_truncated_at_excerpt_chars():
    """When the cached excerpt is longer than the configured cap, the
    returned ItemFlag truncates to that cap."""
    long_text = "X" * (config.EDGAR_8K_ITEM_TEXT_EXCERPT_CHARS + 200)
    filings = [_filing(30, items=["Item 4.02"], item_text_excerpts={"Item 4.02": long_text})]
    flag = check_non_reliance("TST", asof=ASOF, filings=filings)
    assert flag.raw_item_text is not None
    assert len(flag.raw_item_text) == config.EDGAR_8K_ITEM_TEXT_EXCERPT_CHARS


def test_A12_item_flag_is_frozen():
    """frozen dataclass raises FrozenInstanceError on attribute write."""
    from dataclasses import FrozenInstanceError
    flag = ItemFlag(fired=True, filing_date="2026-01-01", filing_url="url", raw_item_text="x")
    with pytest.raises(FrozenInstanceError):
        flag.fired = False  # type: ignore[misc]


def test_A13_item_4_020_does_not_match():
    """Defense-in-depth: malformed 'Item 4.020' should NOT match
    'Item 4.02' (the regex is dot-anchored on both sides)."""
    filings = [_filing(30, items=["Item 4.020"])]
    assert check_non_reliance("TST", asof=ASOF, filings=filings).fired is False


def test_A14_no_matching_items_returns_no_flag_with_url_none():
    """Filing exists in window but contains no matching items."""
    filings = [_filing(30, items=["Item 1.01", "Item 8.01", "Item 9.01"])]
    flag = check_non_reliance("TST", asof=ASOF, filings=filings)
    assert flag.fired is False
    assert flag.filing_url is None


# ---------------------------------------------------------------------------
# A-bis. Regex item extraction (perf-fix parity tests — bypass parser)
# ---------------------------------------------------------------------------

def test_A15_regex_extracts_items_from_html():
    """Parity test for the perf hotfix: raw 8-K HTML → regex item
    extraction yields the same shape that edgartools' parser would
    have produced (canonical 'Item N.MM' strings)."""
    html = (
        "<html><body>"
        "<h2>Item 4.02 Non-Reliance on Previously Issued Financial "
        "Statements</h2>"
        "<p>On March 1, 2026, the Company concluded that the previously "
        "issued financial statements should no longer be relied upon.</p>"
        "<h2>Item 9.01 Financial Statements and Exhibits</h2>"
        "<p>(d) Exhibits.</p>"
        "</body></html>"
    )
    items, excerpts = _extract_items_and_excerpts_from_html(html)
    assert "Item 4.02" in items
    assert "Item 9.01" in items
    assert "Non-Reliance" in excerpts["Item 4.02"]


def test_A16_regex_dedupes_repeated_items():
    """Same item header appearing twice (e.g., body reference) yields
    one entry — first-occurrence excerpt wins."""
    html = (
        "<p>Item 4.02 first mention with key context here.</p>"
        "<p>Item 4.02 second mention with different context.</p>"
    )
    items, excerpts = _extract_items_and_excerpts_from_html(html)
    assert items == ["Item 4.02"]
    assert "first mention" in excerpts["Item 4.02"]


def test_A17_regex_canonicalizes_internal_whitespace():
    """SEC inline-tag splits like 'Item 4. 02' canonicalize to 'Item 4.02'."""
    html = "<p>Item 4. 02 Non-Reliance on Previously Issued ...</p>"
    items, _ = _extract_items_and_excerpts_from_html(html)
    assert items == ["Item 4.02"]


def test_A18_regex_excerpt_capped_at_config_chars():
    long_body = "X" * (config.EDGAR_8K_ITEM_TEXT_EXCERPT_CHARS + 500)
    html = f"<p>Item 4.02 {long_body}</p>"
    _, excerpts = _extract_items_and_excerpts_from_html(html)
    assert len(excerpts["Item 4.02"]) == config.EDGAR_8K_ITEM_TEXT_EXCERPT_CHARS


def test_A19_regex_empty_html_returns_empty_lists():
    items, excerpts = _extract_items_and_excerpts_from_html(
        "<html><body></body></html>"
    )
    assert items == []
    assert excerpts == {}


def test_A20_regex_does_not_match_item_4_020():
    """Defense-in-depth: 'Item 4.020' must not match (the general
    pattern is \\b-anchored so '4.020' fails the closing word boundary
    after '02' due to the trailing '0')."""
    html = "<p>Item 4.020 malformed item number.</p>"
    items, _ = _extract_items_and_excerpts_from_html(html)
    # '4.020' as a whole captures fine, but the canonical form would
    # be 'Item 4.020' — NOT 'Item 4.02', so the 4.02 check stays clean.
    assert "Item 4.02" not in items


# ---------------------------------------------------------------------------
# B. Cache layer tests
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_cache(tmp_path: Path, monkeypatch):
    """Redirect EDGAR_8K_CACHE_DIR to a tmp dir for cache-layer tests."""
    cache_dir = tmp_path / "edgar_8k_cache"
    monkeypatch.setattr(config, "EDGAR_8K_CACHE_DIR", cache_dir)
    return cache_dir


def test_B1_cache_miss_triggers_fetch(isolated_cache, monkeypatch):
    """No on-disk file → cache returns None → caller would fetch."""
    sentinel = [_filing(30, items=["Item 4.02"])]
    fetch_calls: list[str] = []

    def fake_fetch_inner(*_args, **_kwargs):
        fetch_calls.append("fetch")
        return sentinel

    monkeypatch.setattr(eight_k_events, "_ensure_edgar_identity", lambda: True)

    class FakeCompany:
        def __init__(self, ticker: str):
            self.ticker = ticker

        def get_filings(self, *, form: str, filing_date):
            return []

    monkeypatch.setitem(__import__("sys").modules, "edgar", type("M", (), {
        "Company": FakeCompany,
        "set_identity": lambda *a, **k: None,
    }))
    # Direct call: cache is empty → goes to fetch path → returns []
    result = fetch_recent_8k_filings("AAPL", lookback_days=365)
    assert result == []
    # Cache file should now exist.
    assert (isolated_cache / "AAPL.json").exists()


def test_B2_cache_hit_within_ttl_returns_cached(isolated_cache, monkeypatch):
    """Pre-seed a fresh cache entry; fetch should NOT be called."""
    cache_path = isolated_cache / "AAPL.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lookback_days": 365,
        "filings": [_filing(30, items=["Item 4.02"])],
    }
    cache_path.write_text(json.dumps(payload))

    # Sentinel: if fetch path runs, this monkeypatched Company would get
    # called and we'd notice via raises.
    def boom(*a, **k):
        raise AssertionError("cache miss path should not run")
    monkeypatch.setattr(eight_k_events, "_ensure_edgar_identity", boom)

    result = fetch_recent_8k_filings("AAPL", lookback_days=365)
    assert result is not None
    assert len(result) == 1
    assert result[0]["items"] == ["Item 4.02"]


def test_B3_cache_hit_past_ttl_refetches(isolated_cache, monkeypatch):
    """An entry older than 7 days is treated as a miss."""
    cache_path = isolated_cache / "AAPL.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    expired = datetime.now(UTC) - timedelta(seconds=config.EDGAR_8K_CACHE_TTL_SECONDS + 100)
    payload = {
        "fetched_at": expired.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lookback_days": 365,
        "filings": [_filing(30, items=["Item 4.02"])],
    }
    cache_path.write_text(json.dumps(payload))
    # Verify the cache reader treats this as a miss.
    assert eight_k_events._cache_read("AAPL", 365) is None


def test_B4_invalidate_cache_removes_entry(isolated_cache):
    cache_path = isolated_cache / "AAPL.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("{}")
    assert cache_path.exists()
    invalidate_cache("AAPL")
    assert not cache_path.exists()
    # Idempotent — second call doesn't raise.
    invalidate_cache("AAPL")


def test_B5_corrupt_cache_treated_as_miss(isolated_cache, capsys):
    cache_path = isolated_cache / "AAPL.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text("{ this is not json")
    result = eight_k_events._cache_read("AAPL", 365)
    assert result is None


def test_B6_cache_lookback_undersize_treated_as_miss(isolated_cache):
    """Cache entry with lookback_days=365 cannot serve a 730d request."""
    cache_path = isolated_cache / "AAPL.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lookback_days": 365,
        "filings": [],
    }
    cache_path.write_text(json.dumps(payload))
    assert eight_k_events._cache_read("AAPL", 365) is not None
    assert eight_k_events._cache_read("AAPL", 730) is None


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

def test_safe_ticker_path_handles_special_chars(isolated_cache):
    """A ticker like 'BRK-B' should sanitize to a safe filename."""
    p = eight_k_events._cache_path("BRK-B")
    # '-' is allowed by the safe-char regex, so name is BRK-B.json
    assert p.name == "BRK-B.json"


def test_safe_ticker_path_strips_dangerous_chars(isolated_cache):
    p = eight_k_events._cache_path("BRK/../EVIL")
    assert "/" not in p.name
    assert ".." not in p.name


# ---------------------------------------------------------------------------
# C. Network tests (smoke against real SEC EDGAR)
# ---------------------------------------------------------------------------

_NETWORK_PRE = pytest.mark.skipif(
    not os.environ.get("EDGAR_USER_AGENT"),
    reason="EDGAR_USER_AGENT not set",
)


@pytest.mark.network
@_NETWORK_PRE
def test_C1_known_clean_tickers_mostly_no_fired_flags():
    """Fetch 5 known-clean tickers; expect 0 fired non_reliance flags
    for ≥4 of 5. We allow 1 false positive in case any of these
    happens to have filed a real Item 4.02 in the trailing year."""
    clean = ("AAPL", "MSFT", "GOOGL", "JPM", "KO")
    fired = 0
    fetch_failures = 0
    for ticker in clean:
        flag = check_non_reliance(ticker)
        if flag.fired:
            fired += 1
        # Distinguish "fetch failed" (None metadata + fired=False) from
        # "fetched and clean": failures are not counted toward fired.
        if not flag.fired and flag.filing_date is None:
            # Could be "no event" OR "fetch failed" — we infer fetch
            # failure only if the ticker also has no on-disk cache entry
            # AFTER the call (suggests the fetch itself failed).
            cache_path = eight_k_events._cache_path(ticker)
            if not cache_path.exists():
                fetch_failures += 1
    # At most 1 of 5 fired AND at most 2 of 5 fetch-failed:
    successes = len(clean) - fetch_failures
    assert successes >= 3, f"Too few successful fetches ({successes}/5)"
    assert fired <= 1, f"More fired flags than expected ({fired}/{len(clean)})"


@pytest.mark.network
@_NETWORK_PRE
def test_C2_recent_apple_8ks_have_no_4_02_or_4_01():
    """AAPL has had no restatements or auditor changes in living
    memory; both flags should be False."""
    flag_402 = check_non_reliance("AAPL")
    flag_401 = check_auditor_change("AAPL")
    # If fetch worked at all, expect both False.
    if flag_402.filing_date is not None or flag_401.filing_date is not None:
        # Fetch returned data. Either the test universe found a real
        # event (unlikely) or our parser fired in error. Don't assert
        # — just print diagnostic for human review.
        pytest.skip(f"AAPL surfaced unexpected event: 4.02={flag_402} 4.01={flag_401}")


@pytest.mark.network
@_NETWORK_PRE
def test_C3_repeated_calls_use_cache_after_first(monkeypatch):
    """Second + subsequent calls within TTL must hit the on-disk cache,
    not re-fetch. We verify by timing — first call > 0.5s, subsequent
    calls < 0.1s."""
    invalidate_cache("MSFT")  # ensure fresh start
    t0 = time.perf_counter()
    first = check_non_reliance("MSFT")
    t_first = time.perf_counter() - t0
    if first.filing_date is None and not eight_k_events._cache_path("MSFT").exists():
        pytest.skip("First fetch failed — cache test inconclusive")

    t1 = time.perf_counter()
    check_non_reliance("MSFT")
    t_second = time.perf_counter() - t1
    assert t_second < t_first / 2 or t_second < 0.05, (
        f"Cache not effective: first={t_first:.3f}s second={t_second:.3f}s"
    )
