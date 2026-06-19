"""Offline unit tests for the on-disk cache layer in
``compute.ingest.filing_text``.

The existing ``test_filing_text.py`` tests only the BeautifulSoup
HTML-extraction helper (``_extract_text_from_html``).  This file covers the
cache-read/write/invalidate contract and the ``_ensure_edgar_identity`` guard
— all without any live EDGAR network call.

Contract summary (from filing_text.py module docstring):
- JSON cache at ``compute/cache/edgar_10k_text/<ticker>.json``.
- 90-day TTL keyed on ``fetched_at`` (UTC ISO-8601) stored in the JSON.
- ``_cache_read`` returns the payload dict on a hit; ``None`` on miss /
  expired / corrupt.
- ``fetch_latest_10k_text`` returns the cached ``text`` string on a hit
  WITHOUT calling any EDGAR API.
- On an EDGAR failure / missing env-var, ``fetch_latest_10k_text`` returns
  ``None`` (non-blocking, Tier-2 feature).
- ``invalidate_cache`` removes the cache file idempotently.
- ``_ensure_edgar_identity`` returns ``False`` (and does NOT raise) when
  ``EDGAR_USER_AGENT`` is absent.

Test IDs mirror the P0 splits-cache style (F1-F7) for cross-module
consistency.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Module under test — import before any monkeypatching so the module-level
# globals (_IDENTITY_SET) are initialised.
# ---------------------------------------------------------------------------
import compute.ingest.filing_text as filing_text_mod
from compute.ingest.filing_text import (
    _cache_read,
    _cache_write,
    _ensure_edgar_identity,
    fetch_latest_10k_text,
    invalidate_cache,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TICKER = "AAPL"
_SAMPLE_TEXT = "The Company does not have substantial doubt about its ability to continue."


def _fresh_payload(ticker: str, text: str = _SAMPLE_TEXT) -> dict:
    """Return a well-formed cache payload whose ``fetched_at`` is now."""
    return {
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "filing_date": "2025-11-01",
        "filing_url": "https://www.sec.gov/Archives/edgar/data/1234/000123/10k.htm",
        "text": text,
    }


def _write_cache_file(cache_dir: Path, ticker: str, payload: dict) -> Path:
    """Write ``payload`` to ``<cache_dir>/<ticker>.json`` and return the path."""
    path = cache_dir / f"{ticker}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _backdate_fetched_at(path: Path, age_seconds: float) -> None:
    """Rewrite ``fetched_at`` in the JSON to ``age_seconds`` in the past."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    past = datetime.now(UTC) - timedelta(seconds=age_seconds)
    payload["fetched_at"] = past.strftime("%Y-%m-%dT%H:%M:%SZ")
    path.write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# F1 — Fresh cache hit → text returned WITHOUT an EDGAR call
# ---------------------------------------------------------------------------


def test_F1_fresh_cache_returns_text_without_edgar_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F1: a cache file whose ``fetched_at`` is well within the 90-day TTL
    must be returned by ``fetch_latest_10k_text`` without invoking any
    EDGAR API function.

    The warm-cron path: every ticker within 90 days is served from disk.
    """
    cache_dir = tmp_path / "edgar_10k_text"
    cache_dir.mkdir()
    monkeypatch.setattr(filing_text_mod.config, "EDGAR_10K_TEXT_CACHE_DIR", cache_dir)

    _write_cache_file(cache_dir, _TICKER, _fresh_payload(_TICKER))
    # fetched_at is "now" — age ≈ 0s — well within 90 * 86400s TTL.

    identity_calls: list[str] = []

    def fake_ensure_identity() -> bool:
        identity_calls.append("called")
        return True

    monkeypatch.setattr(filing_text_mod, "_ensure_edgar_identity", fake_ensure_identity)
    # Reset the module-level _IDENTITY_SET so _ensure_edgar_identity would
    # actually be consulted if the cache path is not taken.
    monkeypatch.setattr(filing_text_mod, "_IDENTITY_SET", False)

    result = fetch_latest_10k_text(_TICKER)

    assert result == _SAMPLE_TEXT, (
        f"Fresh cache must return the cached text; got {result!r}"
    )
    assert len(identity_calls) == 0, (
        "fetch_latest_10k_text must NOT call _ensure_edgar_identity on a cache hit; "
        f"it was called {len(identity_calls)} time(s)"
    )


# ---------------------------------------------------------------------------
# F2 — Stale/expired cache triggers an EDGAR re-fetch
# ---------------------------------------------------------------------------


def test_F2_expired_cache_triggers_edgar_refetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F2: when ``fetched_at`` is beyond the 90-day TTL, ``_cache_read``
    must return ``None``, causing ``fetch_latest_10k_text`` to attempt a
    live EDGAR fetch.

    The live fetch is stubbed to return ``None`` (simulates EDGAR failure)
    so the test doesn't need network access; the point is that
    ``_ensure_edgar_identity`` IS called (the expired path was taken).
    """
    cache_dir = tmp_path / "edgar_10k_text"
    cache_dir.mkdir()
    monkeypatch.setattr(filing_text_mod.config, "EDGAR_10K_TEXT_CACHE_DIR", cache_dir)

    cache_file = _write_cache_file(cache_dir, _TICKER, _fresh_payload(_TICKER))
    # Backdate fetched_at by TTL + 1 second → expired.
    ttl = filing_text_mod.config.EDGAR_10K_TEXT_CACHE_TTL_SECONDS
    _backdate_fetched_at(cache_file, ttl + 1)

    identity_calls: list[str] = []

    def fake_ensure_identity() -> bool:
        identity_calls.append("called")
        return False  # Abort early so no real EDGAR call is attempted.

    monkeypatch.setattr(filing_text_mod, "_ensure_edgar_identity", fake_ensure_identity)
    monkeypatch.setattr(filing_text_mod, "_IDENTITY_SET", False)

    result = fetch_latest_10k_text(_TICKER)

    assert result is None, (
        "When _ensure_edgar_identity returns False, fetch must return None"
    )
    assert len(identity_calls) == 1, (
        "Expired cache must cause _ensure_edgar_identity to be called exactly once; "
        f"got {len(identity_calls)} call(s)"
    )


# ---------------------------------------------------------------------------
# F3 — Cache miss triggers an EDGAR fetch
# ---------------------------------------------------------------------------


def test_F3_cache_miss_triggers_edgar_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F3: when no cache file exists for the ticker, ``_cache_read`` returns
    ``None`` and ``fetch_latest_10k_text`` proceeds to call
    ``_ensure_edgar_identity``.

    The identity function is stubbed to return ``False`` (no env-var) so the
    function returns ``None`` without a real network call.
    """
    cache_dir = tmp_path / "edgar_10k_text"
    cache_dir.mkdir()
    monkeypatch.setattr(filing_text_mod.config, "EDGAR_10K_TEXT_CACHE_DIR", cache_dir)
    # No cache file written → cold miss.

    identity_calls: list[str] = []

    def fake_ensure_identity() -> bool:
        identity_calls.append("called")
        return False  # Abort without EDGAR.

    monkeypatch.setattr(filing_text_mod, "_ensure_edgar_identity", fake_ensure_identity)
    monkeypatch.setattr(filing_text_mod, "_IDENTITY_SET", False)

    result = fetch_latest_10k_text("MSFT")

    assert result is None
    assert len(identity_calls) == 1, (
        "Cold cache miss must trigger _ensure_edgar_identity; "
        f"got {len(identity_calls)} call(s)"
    )


# ---------------------------------------------------------------------------
# F4 — Corrupt cache file falls back gracefully (returns None from _cache_read)
# ---------------------------------------------------------------------------


def test_F4_corrupt_json_cache_read_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F4a: a cache file containing invalid JSON must cause ``_cache_read``
    to return ``None`` without raising.

    Graceful-degradation contract: cache corruption is logged and treated
    as a cache miss (the ``except (json.JSONDecodeError, OSError)`` guard
    in ``_cache_read``).
    """
    cache_dir = tmp_path / "edgar_10k_text"
    cache_dir.mkdir()
    monkeypatch.setattr(filing_text_mod.config, "EDGAR_10K_TEXT_CACHE_DIR", cache_dir)

    corrupt_path = cache_dir / f"{_TICKER}.json"
    corrupt_path.write_text("not valid JSON {{{{", encoding="utf-8")

    result = _cache_read(_TICKER)

    assert result is None, (
        "_cache_read must return None on corrupt JSON, not raise"
    )


def test_F4b_corrupt_cache_fetch_falls_through_to_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F4b: when ``_cache_read`` returns None due to JSON corruption,
    ``fetch_latest_10k_text`` proceeds to call ``_ensure_edgar_identity``
    (i.e., the corruption is treated as a cache miss).

    The identity stub returns False so no real EDGAR call is made.
    """
    cache_dir = tmp_path / "edgar_10k_text"
    cache_dir.mkdir()
    monkeypatch.setattr(filing_text_mod.config, "EDGAR_10K_TEXT_CACHE_DIR", cache_dir)

    corrupt_path = cache_dir / f"{_TICKER}.json"
    corrupt_path.write_text("{broken json", encoding="utf-8")

    identity_calls: list[str] = []

    def fake_ensure_identity() -> bool:
        identity_calls.append("called")
        return False

    monkeypatch.setattr(filing_text_mod, "_ensure_edgar_identity", fake_ensure_identity)
    monkeypatch.setattr(filing_text_mod, "_IDENTITY_SET", False)

    result = fetch_latest_10k_text(_TICKER)

    assert result is None
    assert len(identity_calls) == 1, (
        "Corrupt cache must fall through to _ensure_edgar_identity"
    )


# ---------------------------------------------------------------------------
# F5 — _cache_write / _cache_read round-trip
# ---------------------------------------------------------------------------


def test_F5_cache_write_read_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F5: ``_cache_write`` followed by ``_cache_read`` must return a payload
    dict containing the exact text, filing_date, and filing_url passed in.

    Verifies:
    - ISO-8601 ``fetched_at`` is stored and parsed correctly.
    - ``text`` field survives JSON round-trip.
    - Atomic rename completed (no ``.tmp`` file leftover).
    - ``_cache_read`` returns the payload (not None).
    """
    cache_dir = tmp_path / "edgar_10k_text"
    cache_dir.mkdir()
    monkeypatch.setattr(filing_text_mod.config, "EDGAR_10K_TEXT_CACHE_DIR", cache_dir)

    text_in = "Revenue grew 12% year-over-year."
    filing_date_in = "2025-11-01"
    filing_url_in = "https://www.sec.gov/Archives/test.htm"

    _cache_write(
        _TICKER,
        filing_date=filing_date_in,
        filing_url=filing_url_in,
        text=text_in,
    )

    # No .tmp file should linger after atomic rename.
    tmp_file = cache_dir / f"{_TICKER}.json.tmp"
    assert not tmp_file.exists(), "Atomic rename must remove the .tmp file"

    final_path = cache_dir / f"{_TICKER}.json"
    assert final_path.exists(), "Cache file must exist after _cache_write"

    payload = _cache_read(_TICKER)

    assert payload is not None, "_cache_read must succeed immediately after _cache_write"
    assert payload["text"] == text_in, (
        f"Round-trip text mismatch: expected {text_in!r}, got {payload['text']!r}"
    )
    assert payload["filing_date"] == filing_date_in
    assert payload["filing_url"] == filing_url_in
    assert "fetched_at" in payload


# ---------------------------------------------------------------------------
# F6 — invalidate_cache removes the cache file; idempotent on missing file
# ---------------------------------------------------------------------------


def test_F6_invalidate_cache_removes_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F6a: ``invalidate_cache`` must remove the on-disk cache file for the
    ticker.  After invalidation, ``_cache_read`` must return ``None``.
    """
    cache_dir = tmp_path / "edgar_10k_text"
    cache_dir.mkdir()
    monkeypatch.setattr(filing_text_mod.config, "EDGAR_10K_TEXT_CACHE_DIR", cache_dir)

    _cache_write(_TICKER, filing_date="2025-11-01", filing_url="", text=_SAMPLE_TEXT)
    assert _cache_read(_TICKER) is not None, "Pre-condition: cache must exist before invalidate"

    invalidate_cache(_TICKER)

    assert _cache_read(_TICKER) is None, (
        "_cache_read must return None after invalidate_cache"
    )
    cache_file = cache_dir / f"{_TICKER}.json"
    assert not cache_file.exists(), "Cache file must be removed by invalidate_cache"


def test_F6b_invalidate_cache_is_idempotent_on_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F6b: calling ``invalidate_cache`` on a ticker that has no cache file
    must NOT raise any exception (idempotent contract).
    """
    cache_dir = tmp_path / "edgar_10k_text"
    cache_dir.mkdir()
    monkeypatch.setattr(filing_text_mod.config, "EDGAR_10K_TEXT_CACHE_DIR", cache_dir)

    # No file exists for "NONEXISTENT" — should not raise.
    invalidate_cache("NONEXISTENT")


# ---------------------------------------------------------------------------
# F7 — _ensure_edgar_identity returns False when env-var absent (no raise)
# ---------------------------------------------------------------------------


def test_F7_ensure_edgar_identity_returns_false_without_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """F7: when ``EDGAR_USER_AGENT`` is NOT set in the environment,
    ``_ensure_edgar_identity`` must return ``False`` and MUST NOT raise.

    This is the non-blocking Tier-2 contract: absence of the env-var
    silently disables Defense #8 rather than crashing the compute run.
    """
    # Reset the module-level cache so we don't get a spurious True from
    # a previously-set identity.
    monkeypatch.setattr(filing_text_mod, "_IDENTITY_SET", False)
    monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)

    result = _ensure_edgar_identity()

    assert result is False, (
        "_ensure_edgar_identity must return False when EDGAR_USER_AGENT is absent"
    )


# ---------------------------------------------------------------------------
# F8 — _cache_read returns None when payload has no "text" key
# ---------------------------------------------------------------------------


def test_F8_cache_read_returns_none_when_text_field_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F8: a cache payload that is valid JSON and fresh but lacks the ``text``
    key (or has a non-string ``text``) must cause ``_cache_read`` to return
    ``None``.

    Guards against a partially-written or schema-migrated cache entry being
    returned as a valid payload.
    """
    cache_dir = tmp_path / "edgar_10k_text"
    cache_dir.mkdir()
    monkeypatch.setattr(filing_text_mod.config, "EDGAR_10K_TEXT_CACHE_DIR", cache_dir)

    # Write a payload that is otherwise well-formed but missing "text".
    payload_no_text = {
        "fetched_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "filing_date": "2025-11-01",
        "filing_url": "",
        # "text" key deliberately absent
    }
    _write_cache_file(cache_dir, _TICKER, payload_no_text)

    result = _cache_read(_TICKER)

    assert result is None, (
        "_cache_read must return None when 'text' field is absent from payload"
    )


# ---------------------------------------------------------------------------
# F9 — _cache_read returns None when fetched_at is malformed
# ---------------------------------------------------------------------------


def test_F9_cache_read_returns_none_when_fetched_at_malformed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F9: a cache payload whose ``fetched_at`` field cannot be parsed as an
    ISO-8601 datetime must cause ``_cache_read`` to return ``None`` without
    raising.
    """
    cache_dir = tmp_path / "edgar_10k_text"
    cache_dir.mkdir()
    monkeypatch.setattr(filing_text_mod.config, "EDGAR_10K_TEXT_CACHE_DIR", cache_dir)

    bad_ts_payload = {
        "fetched_at": "not-a-date",
        "filing_date": "2025-11-01",
        "filing_url": "",
        "text": _SAMPLE_TEXT,
    }
    _write_cache_file(cache_dir, _TICKER, bad_ts_payload)

    result = _cache_read(_TICKER)

    assert result is None, (
        "_cache_read must return None when 'fetched_at' is malformed"
    )


# ---------------------------------------------------------------------------
# Live EDGAR test (network-gated) — smoke-tests the full public API
# ---------------------------------------------------------------------------


@pytest.mark.network
def test_live_fetch_latest_10k_text_returns_string_or_none() -> None:
    """Network smoke test: ``fetch_latest_10k_text("AAPL")`` returns either a
    non-empty string (10-K text found + parsed) or ``None`` (graceful
    degradation).  Never raises.

    Requires ``--run-network`` and ``EDGAR_USER_AGENT`` env-var.
    """
    result = fetch_latest_10k_text("AAPL")
    assert result is None or isinstance(result, str), (
        "fetch_latest_10k_text must return str or None, never raise"
    )
    if result is not None:
        assert len(result) > 0, "Non-None result must be a non-empty string"
