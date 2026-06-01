"""Schema + round-trip tests for the PR-A2 listing-metadata fields.

Three fields land across two models at schema ``0.10.12-phase4.6``:

On ``Metadata``:
- ``exchange_coverage_pct: float | None = None``
  Rule-18 observability: % of the universe whose StockDetail.exchange
  resolved to a non-None display name (e.g. "NASDAQ", "NYSE").

On ``StockDetail``:
- ``exchange: str | None = None``   — display name (NMS→"NASDAQ", NYQ→"NYSE")
- ``country: str | None = None``    — derived country tag ("US" for all
  known S&P-500 exchange codes; None for unknown/cold-cache-miss)

All three are additive optional with ``= None`` defaults, following the
PATCH-bump "add optional field, default None" contract (SKILL.md Rule:
additive optional → PATCH), so legacy JSON files (pre-0.10.12)
deserialise cleanly.

Coverage policy (AGENTS.md §Testing): "add a test when a new contract
is added to the output schema" — this file satisfies that policy for
all three fields.
"""

from __future__ import annotations

from compute.output.schemas import Metadata, StockDetail

# ---------------------------------------------------------------------------
# Canonical minimal payloads
# Mirrors the pattern from test_wall_clock_schema.py + test_value_trap_delta_by_sector_schema.py
# ---------------------------------------------------------------------------


def _base_metadata_payload() -> dict:
    """Minimal Metadata payload — 7 required fields only.

    No exchange_coverage_pct included; each test layers in exactly what it
    needs to verify, following the synthetic-fixture pattern used throughout
    tests/test_output/.
    """
    return {
        "version": "0.10.12-phase4.6",
        "last_update_utc": "2026-06-01T22:00:00Z",
        "next_update_utc": "2026-06-08T22:00:00Z",
        "universe": "sp500",
        "universe_size": 502,
        "compute_run_id": "local",
        "git_commit": "b" * 40,
    }


def _base_stock_detail_payload() -> dict:
    """Minimal StockDetail payload — required fields only.

    No exchange or country included; each test layers in exactly what it
    needs. Required fields derived from the class definition.
    """
    return {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "sector": "Information Technology",
        "current_price": 182.50,
        "rank": 1,
        "composite_score": 82.0,
    }


# ---------------------------------------------------------------------------
# Metadata.exchange_coverage_pct — happy path
# ---------------------------------------------------------------------------


def test_exchange_coverage_pct_exists_on_metadata_with_float() -> None:
    """PR-A2 (0.10.12-phase4.6) — exchange_coverage_pct accepts a float and
    survives a model_dump(mode='json') round-trip with exact value preservation.

    Invariant: the field is plain ``float | None`` with no coercion or
    truncation — the exact float written to disk is what the operator sees
    in metadata.json.
    """
    payload = _base_metadata_payload()
    payload["exchange_coverage_pct"] = 97.81

    meta = Metadata.model_validate(payload)
    assert meta.exchange_coverage_pct == 97.81

    serialised = meta.model_dump(mode="json")
    assert serialised["exchange_coverage_pct"] == 97.81

    restored = Metadata.model_validate(serialised)
    assert restored.exchange_coverage_pct == meta.exchange_coverage_pct


def test_exchange_coverage_pct_zero_is_valid() -> None:
    """0.0 is a valid coverage value (all None — cold cache / simulate).

    Distinct from None (field absent / not computed); 0.0 means the loop
    ran but every ticker returned None from fetch_yfinance_exchange.
    """
    payload = _base_metadata_payload()
    payload["exchange_coverage_pct"] = 0.0

    meta = Metadata.model_validate(payload)
    assert meta.exchange_coverage_pct == 0.0

    serialised = meta.model_dump(mode="json")
    assert serialised["exchange_coverage_pct"] == 0.0


# ---------------------------------------------------------------------------
# Metadata.exchange_coverage_pct — optional / backward-compat
# ---------------------------------------------------------------------------


def test_exchange_coverage_pct_optional_default_none() -> None:
    """PR-A2 (0.10.12-phase4.6) — exchange_coverage_pct is optional with a
    ``= None`` default.  A Metadata constructed without supplying it raises
    no ValidationError and serialises as ``null``.

    This is the PATCH-bump backward-compat guarantee: a legacy metadata.json
    (pre-0.10.12) deserialises cleanly with the new field silently defaulting
    to None.
    """
    payload = _base_metadata_payload()
    assert "exchange_coverage_pct" not in payload

    meta = Metadata.model_validate(payload)
    assert meta.exchange_coverage_pct is None

    serialised = meta.model_dump(mode="json")
    assert "exchange_coverage_pct" in serialised
    assert serialised["exchange_coverage_pct"] is None


# ---------------------------------------------------------------------------
# StockDetail.exchange — happy path + backward-compat
# ---------------------------------------------------------------------------


def test_stock_detail_exchange_field_accepts_display_name() -> None:
    """PR-A2 (0.10.12-phase4.6) — StockDetail.exchange accepts a display name
    string ("NASDAQ", "NYSE", …) and round-trips intact.

    The mapping NMS→"NASDAQ" / NYQ→"NYSE" is performed by
    cross_source.exchange_name before the StockDetail constructor is called;
    by the time it reaches the schema the value is already the display form.
    """
    payload = _base_stock_detail_payload()
    payload["exchange"] = "NASDAQ"

    detail = StockDetail.model_validate(payload)
    assert detail.exchange == "NASDAQ"

    serialised = detail.model_dump(mode="json")
    assert serialised["exchange"] == "NASDAQ"

    restored = StockDetail.model_validate(serialised)
    assert restored.exchange == detail.exchange


def test_stock_detail_exchange_field_accepts_passthrough_unknown_code() -> None:
    """PR-A2 — exchange_name() passes through unknown codes verbatim.

    A ticker on a non-S&P-500 venue (e.g. "XLON") would appear in the
    StockDetail as the raw code — the forward-safe design prefers showing
    the raw code to dropping the field entirely.
    """
    payload = _base_stock_detail_payload()
    payload["exchange"] = "XLON"

    detail = StockDetail.model_validate(payload)
    assert detail.exchange == "XLON"


def test_stock_detail_exchange_field_optional_default_none() -> None:
    """PR-A2 — StockDetail.exchange is optional with a ``= None`` default.

    Legacy stock JSON (pre-0.10.12) deserialises cleanly; cold-cache misses
    produce None (no display chip rendered in the frontend).
    """
    payload = _base_stock_detail_payload()
    assert "exchange" not in payload

    detail = StockDetail.model_validate(payload)
    assert detail.exchange is None

    serialised = detail.model_dump(mode="json")
    assert "exchange" in serialised
    assert serialised["exchange"] is None


# ---------------------------------------------------------------------------
# StockDetail.country — happy path + backward-compat
# ---------------------------------------------------------------------------


def test_stock_detail_country_field_accepts_us_tag() -> None:
    """PR-A2 (0.10.12-phase4.6) — StockDetail.country accepts "US" and
    round-trips intact.

    For the S&P 500 universe every resolved exchange code is a US venue, so
    "US" is the expected value for all tickers whose exchange resolved.
    """
    payload = _base_stock_detail_payload()
    payload["country"] = "US"

    detail = StockDetail.model_validate(payload)
    assert detail.country == "US"

    serialised = detail.model_dump(mode="json")
    assert serialised["country"] == "US"

    restored = StockDetail.model_validate(serialised)
    assert restored.country == detail.country


def test_stock_detail_country_field_optional_default_none() -> None:
    """PR-A2 — StockDetail.country is optional with a ``= None`` default.

    None means exchange did not resolve (cold-cache miss / unknown code).
    """
    payload = _base_stock_detail_payload()
    assert "country" not in payload

    detail = StockDetail.model_validate(payload)
    assert detail.country is None

    serialised = detail.model_dump(mode="json")
    assert "country" in serialised
    assert serialised["country"] is None


# ---------------------------------------------------------------------------
# Both fields populated together — the common production case
# ---------------------------------------------------------------------------


def test_stock_detail_exchange_and_country_both_populated() -> None:
    """PR-A2 — exchange and country coexist on the same StockDetail object
    without interfering.

    Production happy-path: AAPL resolves NMS→exchange="NASDAQ",
    country_for_exchange("NMS")→country="US".
    """
    payload = _base_stock_detail_payload()
    payload["exchange"] = "NASDAQ"
    payload["country"] = "US"

    detail = StockDetail.model_validate(payload)
    assert detail.exchange == "NASDAQ"
    assert detail.country == "US"

    serialised = detail.model_dump(mode="json")
    assert serialised["exchange"] == "NASDAQ"
    assert serialised["country"] == "US"


def test_stock_detail_exchange_and_country_both_none() -> None:
    """PR-A2 — both fields None (cold-cache miss / unknown code).

    This is the simulate-mode result: QR_SKIP_CROSS_SOURCE=1 with no cache
    → fetch_yfinance_exchange returns None → both fields None.
    """
    payload = _base_stock_detail_payload()
    # Explicitly set both to None to mirror what the orchestrator writes
    payload["exchange"] = None
    payload["country"] = None

    detail = StockDetail.model_validate(payload)
    assert detail.exchange is None
    assert detail.country is None
