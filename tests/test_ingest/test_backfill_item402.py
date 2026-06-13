"""Regression tests for ``scripts.backfill_item402_history``.

All tests are offline — all network calls are mocked.  No live SEC
EDGAR or EFTS requests are made.

The CRITICAL test is ``test_efts_parse_sp500_cik_hit_written``, which
pins the silent-drop bug where the old code read ``_source["entity_id"]``
and ``_source["file_num"]`` (fields that DO NOT EXIST in EFTS _source),
so every hit was silently dropped (68 hits → 0 rows).  The fix reads
``ciks`` (list) + ``adsh`` (accession) + ``file_date`` + ``items``
from the real EFTS _source structure verified 2026-06-13.

This test MUST FAIL against old code that reads entity_id / file_num,
and PASS against the fixed code that reads ciks / adsh / items.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Realistic EFTS _source shapes (2026-06-13 live-verified structure)
# ---------------------------------------------------------------------------

_CIK_IN_MAP = "0001792941"   # a CIK that IS in the synthetic cik_map
_CIK_NOT_IN_MAP = "0009999999"  # a CIK that is NOT in cik_map
_TICKER_IN_MAP = "GNVR"

# A hit whose CIK is in the universe and items confirms Item 4.02 — should
# be WRITTEN.
_HIT_MATCHED = {
    "_id": "0001493152-24-002926:0001493152-24-002926.htm",
    "_source": {
        "ciks": [_CIK_IN_MAP],
        "adsh": "0001493152-24-002926",
        "items": ["4.02"],
        "file_date": "2024-01-18",
        "display_names": [f"Genvor Inc  (GNVR)  (CIK {_CIK_IN_MAP})"],
    },
}

# A hit whose CIK is NOT in the synthetic cik_map — should be SKIPPED.
_HIT_CIK_MISSING = {
    "_id": "0009999999-24-000001:0009999999-24-000001.htm",
    "_source": {
        "ciks": [_CIK_NOT_IN_MAP],
        "adsh": "0009999999-24-000001",
        "items": ["4.02"],
        "file_date": "2024-02-10",
        "display_names": ["NoMatch Corp (NMC)"],
    },
}

# A hit whose CIK is in the map but `items` does NOT contain "4.02" — should
# be SKIPPED even though the CIK matches.
_HIT_WRONG_ITEM = {
    "_id": "0001792941-24-003000:0001792941-24-003000.htm",
    "_source": {
        "ciks": [_CIK_IN_MAP],
        "adsh": "0001792941-24-003000",
        "items": ["1.01", "9.01"],   # no 4.02
        "file_date": "2024-03-05",
        "display_names": [f"Genvor Inc  (GNVR)  (CIK {_CIK_IN_MAP})"],
    },
}

# A hit with no `adsh` field — accession must fall back to `_id` prefix.
_HIT_NO_ADSH = {
    "_id": "0001792941-24-003999:0001792941-24-003999.htm",
    "_source": {
        "ciks": [_CIK_IN_MAP],
        # no "adsh" key
        "items": ["4.02"],
        "file_date": "2024-04-01",
        "display_names": [f"Genvor Inc  (GNVR)  (CIK {_CIK_IN_MAP})"],
    },
}

# Synthetic cik_map: maps the padded CIK → ticker symbol.
_FAKE_CIK_MAP = {_CIK_IN_MAP: _TICKER_IN_MAP}

# User-agent string required by run() (else sys.exit(1))
_UA = "TestAgent test@example.com"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_cik_map(cik_map: dict = _FAKE_CIK_MAP):
    """Patch _build_cik_map to return a fixed in-memory dict."""
    import scripts.backfill_item402_history as mod
    return patch.object(mod, "_build_cik_map", return_value=cik_map)


def _patch_iter_efts_hits(hits: list[dict]):
    """Patch _iter_efts_hits to yield a fixed list of hit dicts."""
    import scripts.backfill_item402_history as mod
    return patch.object(mod, "_iter_efts_hits", return_value=iter(hits))


def _patch_verify_html(return_value: bool = True):
    """Patch _verify_filing_html (avoids network; defaults to accept)."""
    import scripts.backfill_item402_history as mod
    return patch.object(mod, "_verify_filing_html", return_value=return_value)


def _patch_efts_session():
    """Return a nulled session (prevents real socket use)."""
    import scripts.backfill_item402_history as mod
    return patch.object(mod, "_efts_session", return_value=MagicMock())


# ---------------------------------------------------------------------------
# Test 1 (CRITICAL — pins entity_id→ciks bug fix)
# ---------------------------------------------------------------------------

class TestEftsParseRegression:
    """CRITICAL: pins the entity_id/file_num silent-drop bug.

    The old code read ``_source["entity_id"]`` and ``_source["file_num"]``,
    neither of which exists in real EFTS responses.  Every hit was silently
    dropped.  The fix reads ``ciks`` (list), ``adsh``, ``file_date``, and
    ``items``.  These four assertions together constitute the regression pin:
    a test that passes against the fixed code and would FAIL against the old.
    """

    def test_sp500_cik_hit_written_with_correct_fields(self, tmp_path: Path) -> None:
        """(a) Hit whose CIK is in cik_map and items contains '4.02' is WRITTEN.

        Asserts ticker, cik, accession_number, and filing_date are correct,
        extracted from ciks / adsh / file_date — not from entity_id / file_num.
        """
        from scripts.backfill_item402_history import run

        out = tmp_path / "out.parquet"
        with (
            _patch_cik_map(),
            _patch_iter_efts_hits([_HIT_MATCHED]),
            _patch_verify_html(),
            _patch_efts_session(),
        ):
            run(
                start="2024-01-01",
                end="2024-12-31",
                out=out,
                html_verify=False,
                user_agent=_UA,
            )

        assert out.exists(), "parquet must be written for a matched hit"
        df = pd.read_parquet(out)
        assert len(df) == 1, f"expected 1 row, got {len(df)}"
        row = df.iloc[0]
        assert row["ticker"] == _TICKER_IN_MAP,   f"ticker mismatch: {row['ticker']}"
        assert row["cik"] == _CIK_IN_MAP,         f"cik mismatch: {row['cik']}"
        assert row["accession_number"] == "0001493152-24-002926", (
            f"accession_number mismatch: {row['accession_number']}"
        )
        assert row["filing_date"] == "2024-01-18", f"filing_date mismatch: {row['filing_date']}"

    def test_hit_cik_not_in_map_is_skipped(self, tmp_path: Path) -> None:
        """(b) Hit whose ciks are all outside cik_map is SKIPPED → no parquet written."""
        from scripts.backfill_item402_history import run

        out = tmp_path / "out.parquet"
        with (
            _patch_cik_map(),
            _patch_iter_efts_hits([_HIT_CIK_MISSING]),
            _patch_verify_html(),
            _patch_efts_session(),
        ):
            run(
                start="2024-01-01",
                end="2024-12-31",
                out=out,
                html_verify=False,
                user_agent=_UA,
            )

        assert not out.exists(), (
            "parquet must NOT be written when no hit's CIK matches cik_map"
        )

    def test_hit_items_lacks_402_is_skipped(self, tmp_path: Path) -> None:
        """(c) Hit whose CIK matches but items lacks '4.02' is SKIPPED.

        This verifies the items-field guard: EFTS full-text search may return
        a filing that merely MENTIONS Item 4.02 in body text; the items field
        is authoritative (it lists actual section codes).
        """
        from scripts.backfill_item402_history import run

        out = tmp_path / "out.parquet"
        with (
            _patch_cik_map(),
            _patch_iter_efts_hits([_HIT_WRONG_ITEM]),
            _patch_verify_html(),
            _patch_efts_session(),
        ):
            run(
                start="2024-01-01",
                end="2024-12-31",
                out=out,
                html_verify=False,
                user_agent=_UA,
            )

        assert not out.exists(), (
            "parquet must NOT be written when items field does not contain '4.02'"
        )

    def test_accession_falls_back_to_id_prefix_when_adsh_absent(self, tmp_path: Path) -> None:
        """(d) When adsh is absent, accession is parsed from _id prefix."""
        from scripts.backfill_item402_history import run

        out = tmp_path / "out.parquet"
        with (
            _patch_cik_map(),
            _patch_iter_efts_hits([_HIT_NO_ADSH]),
            _patch_verify_html(),
            _patch_efts_session(),
        ):
            run(
                start="2024-01-01",
                end="2024-12-31",
                out=out,
                html_verify=False,
                user_agent=_UA,
            )

        assert out.exists(), "parquet must be written even when adsh is absent"
        df = pd.read_parquet(out)
        assert len(df) == 1
        # _id prefix before ":" is "0001792941-24-003999"
        assert df.iloc[0]["accession_number"] == "0001792941-24-003999", (
            f"expected _id-derived accession, got: {df.iloc[0]['accession_number']}"
        )

    def test_mixed_hits_only_matched_row_written(self, tmp_path: Path) -> None:
        """Combined: one matched + one cik-missing + one wrong-item → one row written."""
        from scripts.backfill_item402_history import run

        out = tmp_path / "out.parquet"
        all_hits = [_HIT_MATCHED, _HIT_CIK_MISSING, _HIT_WRONG_ITEM]
        with (
            _patch_cik_map(),
            _patch_iter_efts_hits(all_hits),
            _patch_verify_html(),
            _patch_efts_session(),
        ):
            run(
                start="2024-01-01",
                end="2024-12-31",
                out=out,
                html_verify=False,
                user_agent=_UA,
            )

        assert out.exists()
        df = pd.read_parquet(out)
        assert len(df) == 1, f"expected exactly 1 matched row, got {len(df)}"
        assert df.iloc[0]["ticker"] == _TICKER_IN_MAP


# ---------------------------------------------------------------------------
# Test 2: 5xx + 429 retry in _fetch_efts_page
# ---------------------------------------------------------------------------

class TestFetchEftsPageRetry:
    """_fetch_efts_page retries on 429 (rate-limit) and 500 (flaky backend)."""

    def _make_response(self, status_code: int, json_body: dict | None = None):
        r = MagicMock()
        r.status_code = status_code
        r.ok = status_code < 400
        if status_code >= 400:
            r.raise_for_status.side_effect = __import__(
                "requests"
            ).exceptions.HTTPError(response=r)
        else:
            r.raise_for_status.return_value = None
            r.json.return_value = json_body or {}
        return r

    def test_retries_on_500_then_succeeds(self) -> None:
        """A single 500 response is retried; the next 200 is returned."""
        from scripts.backfill_item402_history import _efts_session, _fetch_efts_page

        good_body = {"hits": {"total": {"value": 0}, "hits": []}}
        fail_resp = self._make_response(500)
        ok_resp = self._make_response(200, good_body)

        session = _efts_session(_UA)
        with (
            patch.object(session, "get", side_effect=[fail_resp, ok_resp]),
            patch("time.sleep"),
        ):
            result = _fetch_efts_page(session, "2024-01-01", "2024-12-31", 0, max_retries=3)

        assert result == good_body, f"expected good_body, got {result}"

    def test_retries_on_429_then_succeeds(self) -> None:
        """A 429 rate-limit response is retried; the next 200 is returned."""
        from scripts.backfill_item402_history import _efts_session, _fetch_efts_page

        good_body = {"hits": {"total": {"value": 1}, "hits": [_HIT_MATCHED]}}
        fail_resp = self._make_response(429)
        ok_resp = self._make_response(200, good_body)

        session = _efts_session(_UA)
        with (
            patch.object(session, "get", side_effect=[fail_resp, ok_resp]),
            patch("time.sleep"),
        ):
            result = _fetch_efts_page(session, "2024-01-01", "2024-12-31", 0, max_retries=3)

        assert result == good_body

    def test_exhausted_retries_raises(self) -> None:
        """When all retries are 500, the final HTTPError propagates."""
        import requests as _requests

        from scripts.backfill_item402_history import _efts_session, _fetch_efts_page

        fail_resp = self._make_response(500)
        session = _efts_session(_UA)
        with (
            patch.object(session, "get", return_value=fail_resp),
            patch("time.sleep"),
            pytest.raises(_requests.exceptions.HTTPError),
        ):
            _fetch_efts_page(session, "2024-01-01", "2024-12-31", 0, max_retries=2)

    def test_non_retryable_4xx_raises_immediately(self) -> None:
        """A 403 (non-retryable) is NOT retried — raises on first attempt."""
        import requests as _requests

        from scripts.backfill_item402_history import _efts_session, _fetch_efts_page

        fail_resp = self._make_response(403)
        session = _efts_session(_UA)
        # Capture the mock INSIDE the patch.object scope; once the context exits
        # patch.object restores the original method and .call_count is gone.
        get_mock = MagicMock(return_value=fail_resp)
        with (
            patch.object(session, "get", get_mock),
            patch("time.sleep"),
            pytest.raises(_requests.exceptions.HTTPError),
        ):
            _fetch_efts_page(session, "2024-01-01", "2024-12-31", 0, max_retries=3)

        # Only 1 call should have been made (no retry).  The mock survives the
        # patch.object exit because we hold a direct reference to it.
        assert get_mock.call_count == 1, (
            f"expected 1 attempt for non-retryable 4xx, got {get_mock.call_count}"
        )


# ---------------------------------------------------------------------------
# Test 3: Idempotent merge — dedup on (cik, accession_number)
# ---------------------------------------------------------------------------

class TestIdempotentMerge:
    """run() called twice with overlapping hits deduplicates on (cik, accession_number)."""

    def test_double_run_does_not_duplicate_rows(self, tmp_path: Path) -> None:
        """Calling run() twice with the same hit results in exactly 1 row in the parquet."""
        from scripts.backfill_item402_history import run

        out = tmp_path / "out.parquet"
        common_kwargs = dict(
            start="2024-01-01",
            end="2024-12-31",
            out=out,
            html_verify=False,
            user_agent=_UA,
        )
        with (
            _patch_cik_map(),
            _patch_iter_efts_hits([_HIT_MATCHED]),
            _patch_verify_html(),
            _patch_efts_session(),
        ):
            run(**common_kwargs)

        assert out.exists()
        df_first = pd.read_parquet(out)
        assert len(df_first) == 1

        # Second run with the same hit — should dedup
        with (
            _patch_cik_map(),
            _patch_iter_efts_hits([_HIT_MATCHED]),
            _patch_verify_html(),
            _patch_efts_session(),
        ):
            run(**common_kwargs)

        df_second = pd.read_parquet(out)
        assert len(df_second) == 1, (
            f"expected 1 row after idempotent re-run, got {len(df_second)}"
        )

    def test_double_run_with_new_hit_adds_row(self, tmp_path: Path) -> None:
        """Second run with an additional (different accession) hit appends one new row."""
        from scripts.backfill_item402_history import run

        out = tmp_path / "out.parquet"

        # Build a second hit with a different accession but same CIK + ticker
        hit2 = {
            "_id": "0001792941-24-005000:0001792941-24-005000.htm",
            "_source": {
                "ciks": [_CIK_IN_MAP],
                "adsh": "0001792941-24-005000",
                "items": ["4.02"],
                "file_date": "2024-06-15",
                "display_names": [f"Genvor Inc  (GNVR)  (CIK {_CIK_IN_MAP})"],
            },
        }

        with (
            _patch_cik_map(),
            _patch_iter_efts_hits([_HIT_MATCHED]),
            _patch_verify_html(),
            _patch_efts_session(),
        ):
            run(start="2024-01-01", end="2024-12-31", out=out, html_verify=False, user_agent=_UA)

        with (
            _patch_cik_map(),
            _patch_iter_efts_hits([_HIT_MATCHED, hit2]),
            _patch_verify_html(),
            _patch_efts_session(),
        ):
            run(start="2024-01-01", end="2024-12-31", out=out, html_verify=False, user_agent=_UA)

        df = pd.read_parquet(out)
        assert len(df) == 2, f"expected 2 rows after second run with new hit, got {len(df)}"
        accessions = set(df["accession_number"].tolist())
        assert "0001493152-24-002926" in accessions
        assert "0001792941-24-005000" in accessions
