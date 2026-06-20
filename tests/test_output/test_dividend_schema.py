"""Schema contract + round-trip tests for the Dividend signal PR-1 fields
(schema ``0.10.27-phase8pilot``).

New fields in this PR:
  On ``StockDetail``:
    dividend_yield_pct: float | None = None
    pays_dividend: bool | None = None
    payout_ratio: float | None = None

  On ``Metadata``:
    dividend_coverage_pct: float | None = None

Coverage policy (AGENTS.md §Testing): "add a test when a new contract is added
to the output schema" — this file satisfies that policy for all four fields.

All fields are additive optional with ``= None`` defaults (PATCH-bump backward-
compat guarantee): legacy JSON files (pre-0.10.27) deserialise cleanly under
``extra="forbid"`` without any ValidationError.

Style mirrors tests/test_output/test_exchange_schema.py (the closest sibling
that covers per-StockDetail fields + a Metadata coverage-pct field together).
"""

from __future__ import annotations

from compute.output.schemas import Metadata, StockDetail

# ---------------------------------------------------------------------------
# Canonical minimal payloads (7 required Metadata fields; minimum required
# StockDetail fields). Each test layers in exactly what it needs.
# ---------------------------------------------------------------------------


def _base_metadata_payload() -> dict:
    """Minimal Metadata payload — 7 required fields only.

    Version pinned to the schema that introduced dividend_coverage_pct.
    """
    return {
        "version": "0.10.27-phase8pilot",
        "last_update_utc": "2026-06-19T22:00:00Z",
        "next_update_utc": "2026-06-26T22:00:00Z",
        "universe": "sp900",
        "universe_size": 903,
        "compute_run_id": "local-dividend-pr1-test",
        "git_commit": "c" * 40,
    }


def _base_stock_detail_payload() -> dict:
    """Minimal StockDetail payload — required fields only."""
    return {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "sector": "Information Technology",
        "current_price": 182.50,
        "rank": 1,
        "composite_score": 82.0,
    }


# ---------------------------------------------------------------------------
# DIV_S1 — StockDetail.dividend_yield_pct round-trip
# ---------------------------------------------------------------------------


def test_stock_detail_dividend_yield_pct_round_trips() -> None:
    """dividend_yield_pct accepts a positive float and survives serialise/deserialise.

    2.0 represents 2% annualised yield (stored as PERCENT, NOT fraction).
    The schema does not re-scale — the exact value written to disk is what
    the frontend receives.
    """
    payload = _base_stock_detail_payload()
    payload["dividend_yield_pct"] = 2.0

    detail = StockDetail.model_validate(payload)
    assert detail.dividend_yield_pct == 2.0

    serialised = detail.model_dump(mode="json")
    assert serialised["dividend_yield_pct"] == 2.0

    restored = StockDetail.model_validate(serialised)
    assert restored.dividend_yield_pct == 2.0


def test_stock_detail_dividend_yield_pct_zero_is_valid() -> None:
    """0.0 is a valid dividend_yield_pct (confirmed non-payer — distinct from None).

    The tri-state semantics: 0.0 = confirmed non-payer; None = data unavailable.
    Both must deserialise under extra="forbid".
    """
    payload = _base_stock_detail_payload()
    payload["dividend_yield_pct"] = 0.0

    detail = StockDetail.model_validate(payload)
    assert detail.dividend_yield_pct == 0.0

    serialised = detail.model_dump(mode="json")
    assert serialised["dividend_yield_pct"] == 0.0


def test_stock_detail_dividend_yield_pct_defaults_none() -> None:
    """Pre-0.10.27 per-stock JSON (no dividend_yield_pct) deserialises cleanly.

    backward-compat: the field must default to None under extra="forbid"
    with no ValidationError.
    """
    payload = _base_stock_detail_payload()
    assert "dividend_yield_pct" not in payload

    detail = StockDetail.model_validate(payload)
    assert detail.dividend_yield_pct is None

    serialised = detail.model_dump(mode="json")
    assert "dividend_yield_pct" in serialised
    assert serialised["dividend_yield_pct"] is None


# ---------------------------------------------------------------------------
# DIV_S2 — StockDetail.pays_dividend round-trip
# ---------------------------------------------------------------------------


def test_stock_detail_pays_dividend_true_round_trips() -> None:
    """pays_dividend=True round-trips (dividend-paying ticker)."""
    payload = _base_stock_detail_payload()
    payload["pays_dividend"] = True

    detail = StockDetail.model_validate(payload)
    assert detail.pays_dividend is True

    serialised = detail.model_dump(mode="json")
    assert serialised["pays_dividend"] is True

    restored = StockDetail.model_validate(serialised)
    assert restored.pays_dividend is True


def test_stock_detail_pays_dividend_false_round_trips() -> None:
    """pays_dividend=False round-trips (confirmed non-payer).

    False is the expected value for growth stocks where yfinance returned
    dividendYield=0.0 (Amazon, Google, etc.).
    """
    payload = _base_stock_detail_payload()
    payload["pays_dividend"] = False

    detail = StockDetail.model_validate(payload)
    assert detail.pays_dividend is False

    serialised = detail.model_dump(mode="json")
    assert serialised["pays_dividend"] is False


def test_stock_detail_pays_dividend_defaults_none() -> None:
    """Pre-0.10.27 per-stock JSON (no pays_dividend) deserialises to None.

    None = data unavailable (distinct from False = confirmed non-payer).
    """
    payload = _base_stock_detail_payload()
    assert "pays_dividend" not in payload

    detail = StockDetail.model_validate(payload)
    assert detail.pays_dividend is None

    serialised = detail.model_dump(mode="json")
    assert "pays_dividend" in serialised
    assert serialised["pays_dividend"] is None


# ---------------------------------------------------------------------------
# DIV_S3 — StockDetail.payout_ratio round-trip
# ---------------------------------------------------------------------------


def test_stock_detail_payout_ratio_round_trips() -> None:
    """payout_ratio accepts a 0-1 fraction and round-trips (NOT scaled to %).

    0.45 means 45% payout — stored as the raw yfinance fraction.
    The frontend multiplies by 100 for display.
    """
    payload = _base_stock_detail_payload()
    payload["payout_ratio"] = 0.45

    detail = StockDetail.model_validate(payload)
    assert detail.payout_ratio == 0.45

    serialised = detail.model_dump(mode="json")
    assert serialised["payout_ratio"] == 0.45

    restored = StockDetail.model_validate(serialised)
    assert restored.payout_ratio == 0.45


def test_stock_detail_payout_ratio_defaults_none() -> None:
    """Pre-0.10.27 per-stock JSON (no payout_ratio) deserialises to None.

    Many growth stocks (AMZN, GOOGL, META) have NaN/None payout_ratio in
    yfinance; the field must default to None under extra="forbid".
    """
    payload = _base_stock_detail_payload()
    assert "payout_ratio" not in payload

    detail = StockDetail.model_validate(payload)
    assert detail.payout_ratio is None

    serialised = detail.model_dump(mode="json")
    assert "payout_ratio" in serialised
    assert serialised["payout_ratio"] is None


# ---------------------------------------------------------------------------
# DIV_S4 — all three StockDetail dividend fields coexist (production case)
# ---------------------------------------------------------------------------


def test_stock_detail_all_dividend_fields_populated() -> None:
    """Production happy-path: AAPL with dividend_yield_pct=0.5, pays_dividend=True,
    payout_ratio=0.16 — all three fields coexist without interfering.

    Derived relationship: pays_dividend == (dividend_yield_pct > 0).
    The schema does NOT enforce this — it is a data-pipeline invariant
    maintained in compute/main.py. Both values are stored independently.
    """
    payload = _base_stock_detail_payload()
    payload["dividend_yield_pct"] = 0.5
    payload["pays_dividend"] = True
    payload["payout_ratio"] = 0.16

    detail = StockDetail.model_validate(payload)
    assert detail.dividend_yield_pct == 0.5
    assert detail.pays_dividend is True
    assert detail.payout_ratio == 0.16

    serialised = detail.model_dump(mode="json")
    assert serialised["dividend_yield_pct"] == 0.5
    assert serialised["pays_dividend"] is True
    assert serialised["payout_ratio"] == 0.16

    restored = StockDetail.model_validate(serialised)
    assert restored.dividend_yield_pct == 0.5
    assert restored.pays_dividend is True
    assert restored.payout_ratio == 0.16


def test_stock_detail_non_payer_all_fields_consistent() -> None:
    """Non-payer scenario: dividend_yield_pct=0.0, pays_dividend=False, payout_ratio=None.

    The confirmed-non-payer state round-trips without any ValidationError.
    pays_dividend=False is the schema representation of a confirmed zero-yield ticker.
    """
    payload = _base_stock_detail_payload()
    payload["dividend_yield_pct"] = 0.0
    payload["pays_dividend"] = False
    payload["payout_ratio"] = None

    detail = StockDetail.model_validate(payload)
    assert detail.dividend_yield_pct == 0.0
    assert detail.pays_dividend is False
    assert detail.payout_ratio is None

    serialised = detail.model_dump(mode="json")
    assert serialised["dividend_yield_pct"] == 0.0
    assert serialised["pays_dividend"] is False
    assert serialised["payout_ratio"] is None


def test_stock_detail_all_dividend_fields_none_legacy_compat() -> None:
    """Pre-0.10.27 per-stock JSON (all three fields absent) deserialises cleanly.

    The additive-optional PATCH-bump backward-compat guarantee: all three
    fields must default to None under extra="forbid" when absent from the JSON.
    """
    payload = _base_stock_detail_payload()
    assert "dividend_yield_pct" not in payload
    assert "pays_dividend" not in payload
    assert "payout_ratio" not in payload

    detail = StockDetail.model_validate(payload)
    assert detail.dividend_yield_pct is None
    assert detail.pays_dividend is None
    assert detail.payout_ratio is None

    serialised = detail.model_dump(mode="json")
    # All three must appear in the serialised JSON as null (stable JSON contract).
    for field in ("dividend_yield_pct", "pays_dividend", "payout_ratio"):
        assert field in serialised, f"Field {field} must be present in serialised output"
        assert serialised[field] is None, f"Field {field} must be None in serialised output"


# ---------------------------------------------------------------------------
# DIV_M1 — Metadata.dividend_coverage_pct round-trip
# ---------------------------------------------------------------------------


def test_metadata_dividend_coverage_pct_round_trips_with_float() -> None:
    """dividend_coverage_pct accepts a float and survives a full round-trip.

    97.6 represents 97.6% of the ranked universe having a non-null
    dividend_yield_pct — a healthy production value (expected ~95-99%
    since both derive from the same yfinance_info cache).
    """
    payload = _base_metadata_payload()
    payload["dividend_coverage_pct"] = 97.6

    meta = Metadata.model_validate(payload)
    assert meta.dividend_coverage_pct == 97.6

    serialised = meta.model_dump(mode="json")
    assert serialised["dividend_coverage_pct"] == 97.6

    restored = Metadata.model_validate(serialised)
    assert restored.dividend_coverage_pct == 97.6


def test_metadata_dividend_coverage_pct_none_legacy_compat() -> None:
    """Pre-0.10.27 metadata.json (no dividend_coverage_pct) deserialises cleanly.

    None means the loop was skipped or the field aggregation failed —
    distinct from 0.0 (loop ran, all tickers returned None dividend data).
    """
    payload = _base_metadata_payload()
    assert "dividend_coverage_pct" not in payload

    meta = Metadata.model_validate(payload)
    assert meta.dividend_coverage_pct is None

    serialised = meta.model_dump(mode="json")
    assert "dividend_coverage_pct" in serialised
    assert serialised["dividend_coverage_pct"] is None


def test_metadata_dividend_coverage_pct_zero_is_valid() -> None:
    """0.0 is a valid dividend_coverage_pct (cold-cache / simulate run).

    0.0 means the loop ran but every ticker returned None for dividend_yield_pct
    (e.g., first cron after PR merge with entirely cold yfinance_info cache).
    Distinct from None which means the aggregation step didn't run at all.
    """
    payload = _base_metadata_payload()
    payload["dividend_coverage_pct"] = 0.0

    meta = Metadata.model_validate(payload)
    assert meta.dividend_coverage_pct == 0.0

    serialised = meta.model_dump(mode="json")
    assert serialised["dividend_coverage_pct"] == 0.0


def test_metadata_dividend_coverage_pct_and_stock_detail_fields_coexist() -> None:
    """Metadata.dividend_coverage_pct and StockDetail dividend fields can both be
    populated in the same compute run without schema conflicts.

    Parity check: the Metadata-level aggregation is independent of the per-stock
    StockDetail fields. Both can be validated in isolation — this test confirms they
    don't share any name collision that could cause a Pydantic ValidationError under
    extra="forbid".
    """
    meta_payload = _base_metadata_payload()
    meta_payload["dividend_coverage_pct"] = 97.6

    meta = Metadata.model_validate(meta_payload)
    assert meta.dividend_coverage_pct == 97.6

    detail_payload = _base_stock_detail_payload()
    detail_payload["dividend_yield_pct"] = 2.0
    detail_payload["pays_dividend"] = True
    detail_payload["payout_ratio"] = 0.45

    detail = StockDetail.model_validate(detail_payload)
    assert detail.dividend_yield_pct == 2.0
    assert detail.pays_dividend is True
    assert detail.payout_ratio == 0.45
