"""Schema + round-trip tests for the Issue #67 follow-up
``Metadata.value_trap_risk_delta_by_sector`` field (schema 0.10.10-phase4.6).

One new optional field lands on ``Metadata`` at this PATCH bump:

- ``value_trap_risk_delta_by_sector: dict[str, int] | None = None``

Keys are GICS sector names; values are
``value_trap_risk_count_without_sector_coe[sector]
- value_trap_risk_count_with_sector_coe[sector]`` so a POSITIVE value
means that sector *dropped* flags after the USE_SECTOR_COE flip (Ke <
flat 10% → ROE ≥ Ke threshold relaxed → fewer false positives; expected
for Utilities / Real Estate / Consumer Staples per Damodaran 2019
Ch. 8.4 §"Industry Beta").  A NEGATIVE value means the sector *gained*
flags (Ke > flat 10% → stricter; expected for Information Technology /
Energy).

The field follows the PATCH-bump "add optional field, default None"
contract (SKILL.md Rule: additive optional → PATCH) so legacy
metadata.json files (pre-0.10.10) deserialize cleanly.

Coverage policy (AGENTS.md §Testing): "add a test when a new contract
is added to the output schema" — this file satisfies that policy for
the ``value_trap_risk_delta_by_sector`` field.
"""

from __future__ import annotations

from compute.output.schemas import Metadata

# ---------------------------------------------------------------------------
# Canonical minimal payload for the 7 required Metadata fields.
# Mirrors the pattern from tests/test_output/test_wall_clock_schema.py
# (_base_metadata_payload) — keeps the fixture minimal and
# self-documenting.  The version string is bumped to 0.10.10-phase4.6 to
# match the PATCH that introduced this field (test_config.py pins this).
# ---------------------------------------------------------------------------

def _base_metadata_payload() -> dict:
    """A minimal Metadata payload with only the 7 required fields set.

    No ``value_trap_risk_delta_by_sector`` field included — lets each
    test layer in exactly what it needs to verify, following the
    synthetic-fixture pattern used throughout tests/test_output/.
    """
    return {
        "version": "0.10.10-phase4.6",
        "last_update_utc": "2026-05-28T22:00:00Z",
        "next_update_utc": "2026-06-04T22:00:00Z",
        "universe": "sp500",
        "universe_size": 502,
        "compute_run_id": "local",
        "git_commit": "a" * 40,
    }


# ---------------------------------------------------------------------------
# Test 1 — happy path: dict value populated, round-trip intact
# ---------------------------------------------------------------------------

def test_delta_by_sector_field_exists_on_metadata_with_dict():
    """Issue #67 follow-up (0.10.10-phase4.6) — ``value_trap_risk_delta_by_sector``
    accepts a concrete ``dict[str, int]`` and survives a
    ``model_dump(mode='json')`` round-trip with exact key and value
    preservation.

    Invariant: no JSON key reordering or integer coercion — the exact
    dict written to disk is what the operator and quarterly-cohort-audit
    helper (Q3 2026-08-19) read back from metadata.json.

    Expected per Damodaran 2019 Ch. 8.4 §"Industry Beta":
    - Positive delta (dropped flags after flip): Utilities, Real Estate
    - Negative delta (gained flags after flip): Information Technology,
      Energy
    """
    payload = _base_metadata_payload()
    sector_delta = {
        "Utilities": 12,
        "Information Technology": -5,
        "Real Estate": 8,
        "Energy": -3,
    }
    payload["value_trap_risk_delta_by_sector"] = sector_delta

    meta = Metadata.model_validate(payload)

    assert meta.value_trap_risk_delta_by_sector == sector_delta

    # Round-trip through JSON serialisation — what gets written to
    # frontend/public/data/metadata.json must be identical.
    serialised = meta.model_dump(mode="json")
    assert serialised["value_trap_risk_delta_by_sector"] == sector_delta

    # Verify each sector key + sign individually so a future per-sector
    # coercion regression surfaces with a precise failure message.
    delta = serialised["value_trap_risk_delta_by_sector"]
    assert delta["Utilities"] == 12
    assert delta["Information Technology"] == -5
    assert delta["Real Estate"] == 8
    assert delta["Energy"] == -3

    # Restore via model_validate and verify structural equality.
    restored = Metadata.model_validate(serialised)
    assert restored.value_trap_risk_delta_by_sector == sector_delta


# ---------------------------------------------------------------------------
# Test 2 — optional-field contract: omitting the field → None
# ---------------------------------------------------------------------------

def test_delta_by_sector_field_optional_default_none():
    """Issue #67 follow-up (0.10.10-phase4.6) — ``value_trap_risk_delta_by_sector``
    is optional with a ``= None`` default.  A Metadata constructed without
    supplying it raises no ValidationError and serialises as ``null``.

    This is the PATCH-bump backward-compat guarantee: a legacy
    metadata.json (pre-0.10.10) deserialises cleanly with the new field
    silently defaulting to None — identical semantics to every prior
    Phase-4h additive-optional field (tier2_wall_clock_seconds,
    form4_wall_clock_seconds, value_trap_risk_count_with_sector_coe, etc.).
    """
    payload = _base_metadata_payload()
    # Deliberately omit the new field — simulates a legacy snapshot or any
    # cron run where the field was not yet written.
    assert "value_trap_risk_delta_by_sector" not in payload

    # Must not raise ValidationError.
    meta = Metadata.model_validate(payload)

    assert meta.value_trap_risk_delta_by_sector is None

    # Serialisation must carry None explicitly (not omit the key) so the
    # JSON contract is stable regardless of whether the field was populated.
    serialised = meta.model_dump(mode="json")
    assert "value_trap_risk_delta_by_sector" in serialised
    assert serialised["value_trap_risk_delta_by_sector"] is None
