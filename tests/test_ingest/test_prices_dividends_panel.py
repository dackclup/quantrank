"""Tests for ``fetch_dividends_panel`` (issue #620, Option-B shadow NAV).

Coverage policy (AGENTS.md §Testing): add a test when a new behavior ships.
``fetch_dividends_panel`` is a new function in ``compute/ingest/prices.py``
extracted from the Step-1 dividend panel build for the Option-B SHADOW NAV
series (``nav.adaptive_div_pooled``).

Tests
-----
DP1 — ``Dividends`` column absent from all frames → returns ``{}`` (old-parquet back-compat).
DP2 — ``QR_SKIP_DIVIDENDS=1`` env var → returns ``{}`` regardless of frame content.
DP3 — frame is ``None`` → skipped silently, returns ``{}``.
DP4 — single positive ex-date → correct ``{ticker: {iso_date: float}}`` output.
DP5 — zero-value rows dropped; only positive ex-dates survive.
DP6 — multiple tickers, mixed presence: frames with and without Dividends column.
DP7 — non-finite / NaN dividend values → dropped silently (graceful degradation).
DP8 — timestamp index is converted to ISO date string (YYYY-MM-DD).

Style mirrors ``tests/test_ingest/test_prices_smoke.py`` (the closest sibling):
synthetic ``pd.DataFrame`` fixtures, ``monkeypatch`` for env vars, no real
yfinance calls, no ``@settings(deadline=None)``, no ``@pytest.mark.network``.
"""

from __future__ import annotations

import sys
import types

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# yfinance stub — allows prices.py to import without yfinance installed
# ---------------------------------------------------------------------------


def _stub_yfinance() -> None:
    if "yfinance" in sys.modules:
        return
    yf_stub = types.ModuleType("yfinance")

    def _download(*args, **kwargs):  # noqa: ARG001
        return pd.DataFrame()

    yf_stub.download = _download
    sys.modules["yfinance"] = yf_stub


_stub_yfinance()

from compute.ingest.prices import fetch_dividends_panel  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bday_frame_with_dividends(
    start: str,
    periods: int,
    div_on_day: int | None = None,  # 0-based index of day with a dividend
    div_amount: float = 0.50,
    include_dividends_col: bool = True,
) -> pd.DataFrame:
    """Minimal daily price DataFrame, optionally with a Dividends column.

    Parameters
    ----------
    start:
        pandas-compatible date string for business day range start.
    periods:
        Number of business days.
    div_on_day:
        If set, the Dividends column will have ``div_amount`` on that day index
        and 0.0 elsewhere.  If None, all dividend rows are 0.0 (non-payer).
    include_dividends_col:
        When False, the column is omitted entirely (simulates old cached parquet
        without actions=True data).
    """
    idx = pd.bdate_range(start, periods=periods)
    closes = [100.0 + i * 0.5 for i in range(periods)]
    data: dict = {
        "Open": closes,
        "High": [c + 1.0 for c in closes],
        "Low": [c - 1.0 for c in closes],
        "Close": closes,
        "Adj Close": closes,
        "Volume": [1_000_000] * periods,
    }
    if include_dividends_col:
        divs = [0.0] * periods
        if div_on_day is not None and 0 <= div_on_day < periods:
            divs[div_on_day] = div_amount
        data["Dividends"] = divs
    return pd.DataFrame(data, index=idx)


# ---------------------------------------------------------------------------
# DP1 — Dividends column absent from all frames → returns {} (back-compat)
# ---------------------------------------------------------------------------


def test_DP1_no_dividends_column_returns_empty_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    """Frames without a ``Dividends`` column (old cached parquets) → empty dict.

    This locks in the graceful-degradation contract: ``fetch_dividends_panel``
    must return ``{}`` — not a crash, not a KeyError — when the column is absent.
    This is the dominant state on the FIRST cron after a cold-seed bump (the
    cached parquets were downloaded without ``actions=True``).
    """
    monkeypatch.delenv("QR_SKIP_DIVIDENDS", raising=False)

    frames = {
        "AAPL": _bday_frame_with_dividends("2025-01-02", 10, include_dividends_col=False),
        "MSFT": _bday_frame_with_dividends("2025-01-02", 10, include_dividends_col=False),
    }

    result = fetch_dividends_panel(frames)

    assert result == {}, (
        f"Expected empty dict when Dividends column absent from all frames, got {result}"
    )


# ---------------------------------------------------------------------------
# DP2 — QR_SKIP_DIVIDENDS=1 → returns {} regardless of frame content
# ---------------------------------------------------------------------------


def test_DP2_skip_dividends_env_returns_empty_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    """``QR_SKIP_DIVIDENDS=1`` escape hatch → returns ``{}`` immediately.

    Frames may have dividend data (``div_on_day=0``), but the env var must
    suppress extraction entirely.  This mirrors ``QR_SKIP_SPLITS`` semantics.
    """
    monkeypatch.setenv("QR_SKIP_DIVIDENDS", "1")

    frames = {
        "KO": _bday_frame_with_dividends("2025-01-02", 10, div_on_day=2, div_amount=0.46),
        "PEP": _bday_frame_with_dividends("2025-01-02", 10, div_on_day=5, div_amount=1.26),
    }

    result = fetch_dividends_panel(frames)

    assert result == {}, (
        f"QR_SKIP_DIVIDENDS=1 must return empty dict, got {result}"
    )


# ---------------------------------------------------------------------------
# DP3 — frame is None → skipped silently, no crash
# ---------------------------------------------------------------------------


def test_DP3_none_frame_skipped_silently(monkeypatch: pytest.MonkeyPatch) -> None:
    """A ``None`` frame entry is skipped — no crash, no KeyError.

    ``fetch_prices`` returns ``None`` on failure; the dividend panel builder
    must handle this gracefully since the price loop can produce None entries.
    """
    monkeypatch.delenv("QR_SKIP_DIVIDENDS", raising=False)

    frames: dict[str, pd.DataFrame | None] = {
        "AAA": None,
        "BBB": _bday_frame_with_dividends("2025-01-02", 5, div_on_day=1, div_amount=1.0),
    }

    result = fetch_dividends_panel(frames)

    # AAA (None) must be skipped; BBB with a dividend must be included.
    assert "AAA" not in result, "None frame must not appear in the result dict"
    assert "BBB" in result, f"BBB has a dividend — must appear in result, got {result}"
    assert len(result["BBB"]) == 1, f"Expected 1 ex-date for BBB, got {result['BBB']}"


# ---------------------------------------------------------------------------
# DP4 — single positive ex-date → correct output format
# ---------------------------------------------------------------------------


def test_DP4_single_positive_exdate_correct_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Single positive ex-date dividend → ``{ticker: {iso_date: float}}``.

    The ISO date string must be ``YYYY-MM-DD`` and the value must match the
    per-share dividend amount exactly.
    """
    monkeypatch.delenv("QR_SKIP_DIVIDENDS", raising=False)

    # Business day range starting 2025-01-02; dividend on day index 2 (2025-01-06).
    frames = {
        "JNJ": _bday_frame_with_dividends("2025-01-02", 5, div_on_day=2, div_amount=1.19),
    }

    result = fetch_dividends_panel(frames)

    assert "JNJ" in result, f"JNJ must appear in result, got keys={list(result)}"
    jnj_map = result["JNJ"]
    assert len(jnj_map) == 1, f"Expected exactly 1 ex-date, got {jnj_map}"

    # Extract the one date and value.
    (ex_date, div_val) = next(iter(jnj_map.items()))

    # Date must be a valid YYYY-MM-DD ISO string.
    assert len(ex_date) == 10 and ex_date[4] == "-" and ex_date[7] == "-", (
        f"ex_date must be YYYY-MM-DD, got {ex_date!r}"
    )
    assert div_val == pytest.approx(1.19), (
        f"Dividend value must match per-share amount, got {div_val}"
    )


# ---------------------------------------------------------------------------
# DP5 — zero-value rows dropped; only positive ex-dates survive
# ---------------------------------------------------------------------------


def test_DP5_zero_rows_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rows with ``Dividends == 0.0`` (non-ex-date rows) must be excluded.

    yfinance emits 0.0 for every trading day that has no dividend. Only the
    actual ex-dates (positive values) should appear in the output dict.
    """
    monkeypatch.delenv("QR_SKIP_DIVIDENDS", raising=False)

    # 10 days: only day 3 has a positive dividend, all others are 0.0.
    frames = {
        "MSFT": _bday_frame_with_dividends("2025-01-02", 10, div_on_day=3, div_amount=0.75),
    }

    result = fetch_dividends_panel(frames)

    assert "MSFT" in result, f"MSFT with a dividend must appear in result, got {result}"
    # Only the single positive ex-date must survive; the 9 zero rows are dropped.
    assert len(result["MSFT"]) == 1, (
        f"Zero-value rows must be dropped; expected 1 ex-date, got {result['MSFT']}"
    )
    # The remaining value must be positive.
    for _date, val in result["MSFT"].items():
        assert val > 0.0, f"All retained values must be positive, got {val}"


# ---------------------------------------------------------------------------
# DP6 — multiple tickers: mixed presence of Dividends column
# ---------------------------------------------------------------------------


def test_DP6_mixed_column_presence_partial_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Frames with and without Dividends column coexist; only present-and-positive survive.

    AAPL: has the column with a positive dividend → in result.
    GOOGL: has the column but all zeros → NOT in result (no ex-dates).
    META: no Dividends column at all → NOT in result (back-compat skip).
    """
    monkeypatch.delenv("QR_SKIP_DIVIDENDS", raising=False)

    frames = {
        "AAPL": _bday_frame_with_dividends("2025-01-02", 8, div_on_day=4, div_amount=0.25),
        "GOOGL": _bday_frame_with_dividends("2025-01-02", 8, div_on_day=None),  # all zeros
        "META": _bday_frame_with_dividends("2025-01-02", 8, include_dividends_col=False),
    }

    result = fetch_dividends_panel(frames)

    assert "AAPL" in result, "AAPL has a positive ex-date — must appear in result"
    assert "GOOGL" not in result, "GOOGL has only zero dividends — must NOT appear in result"
    assert "META" not in result, "META has no Dividends column — must NOT appear in result"


# ---------------------------------------------------------------------------
# DP7 — non-finite / NaN dividend values → dropped silently
# ---------------------------------------------------------------------------


def test_DP7_nonfinite_dividend_values_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    """NaN / inf dividend values are silently dropped (graceful degradation).

    If yfinance returns a NaN or inf for a dividend row, the ticker-map must
    not contain those entries — the output must be empty (no ex-dates) for
    a frame that only has non-finite values.
    """
    monkeypatch.delenv("QR_SKIP_DIVIDENDS", raising=False)

    idx = pd.bdate_range("2025-01-02", periods=5)
    frame_nan = pd.DataFrame(
        {
            "Close": [100.0] * 5,
            "Adj Close": [100.0] * 5,
            "Volume": [1_000_000] * 5,
            # All non-finite dividend values.
            "Dividends": [float("nan"), float("inf"), float("-inf"), float("nan"), 0.0],
        },
        index=idx,
    )

    frames: dict[str, pd.DataFrame | None] = {"XYZ": frame_nan}

    result = fetch_dividends_panel(frames)

    # XYZ must not appear (no finite positive ex-dates survived).
    assert "XYZ" not in result, (
        f"Non-finite dividend values must be dropped; 'XYZ' should not appear, got {result}"
    )


# ---------------------------------------------------------------------------
# DP8 — timestamp index → ISO date string conversion
# ---------------------------------------------------------------------------


def test_DP8_timestamp_index_converted_to_iso_string(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pandas Timestamp index entries are converted to ISO YYYY-MM-DD strings.

    ``fetch_dividends_panel`` calls ``ts.date().isoformat()`` on Timestamp
    index entries. This test verifies the output key format is correct when the
    DataFrame is built with a ``DatetimeIndex`` (the standard yfinance output).
    """
    monkeypatch.delenv("QR_SKIP_DIVIDENDS", raising=False)

    # Use a specific known date so we can pin the expected key.
    specific_date = pd.Timestamp("2025-03-17")  # a Monday
    idx = pd.DatetimeIndex([
        pd.Timestamp("2025-03-13"),
        pd.Timestamp("2025-03-14"),
        specific_date,
        pd.Timestamp("2025-03-18"),
        pd.Timestamp("2025-03-19"),
    ])
    frame = pd.DataFrame(
        {
            "Close": [100.0] * 5,
            "Adj Close": [100.0] * 5,
            "Volume": [1_000_000] * 5,
            "Dividends": [0.0, 0.0, 0.88, 0.0, 0.0],  # ex-date on 2025-03-17
        },
        index=idx,
    )

    result = fetch_dividends_panel({"VZ": frame})

    assert "VZ" in result, f"VZ must appear in result, got {list(result)}"
    vz_map = result["VZ"]
    assert "2025-03-17" in vz_map, (
        f"Expected ISO date '2025-03-17' as key, got keys={list(vz_map)}"
    )
    assert vz_map["2025-03-17"] == pytest.approx(0.88)
