"""Schema + round-trip tests for the issue #441 PR-1 MAD diagnostics fields.

Three new optional fields land on ``Metadata`` at schema ``0.10.16-phase4.6``:

- ``mad_coverage_pct: float | None = None``
- ``mad_mom12_corr: float | None = None``
- ``mad_mom3_corr: float | None = None``

All three follow the PATCH-bump "add optional field, default None" contract
(SKILL.md Rule: additive optional -> PATCH) so legacy metadata.json files
(pre-0.10.16) deserialise cleanly.

Coverage policy (AGENTS.md §Testing): "add a test when a new contract is
added to the output schema" — this file satisfies that policy for the three
MAD diagnostics fields.
"""

from __future__ import annotations

import math

from compute.output.schemas import Metadata

# ---------------------------------------------------------------------------
# Minimal payload fixture — same pattern as test_wall_clock_schema.py.
# Only the 7 required Metadata fields; each test layers in exactly what it
# needs to verify.
# ---------------------------------------------------------------------------


def _base_payload() -> dict:
    """Minimal Metadata payload with the 7 required fields only.

    No MAD fields included — lets each test verify the default-None
    contract and the populated path independently.
    """
    return {
        "version": "0.10.16-phase4.6",
        "last_update_utc": "2026-06-10T22:00:00Z",
        "next_update_utc": "2026-06-17T22:00:00Z",
        "universe": "sp500",
        "universe_size": 502,
        "compute_run_id": "local",
        "git_commit": "a" * 40,
    }


# ---------------------------------------------------------------------------
# Test 1 — happy path: all three MAD fields populated; round-trip exact
# ---------------------------------------------------------------------------


def test_mad_diagnostics_fields_accept_floats_and_round_trip():
    """Issue #441 PR-1 — all three MAD fields accept floats and survive a
    model_dump(mode='json') round-trip with exact value preservation.

    Invariant: the fields are plain ``float | None`` with no coercion or
    truncation — the exact float written to disk is what appears in
    metadata.json.
    """
    payload = _base_payload()
    payload["mad_coverage_pct"] = 94.5
    payload["mad_mom12_corr"] = 0.18
    payload["mad_mom3_corr"] = -0.07

    meta = Metadata.model_validate(payload)

    assert meta.mad_coverage_pct == 94.5
    assert meta.mad_mom12_corr == 0.18
    assert meta.mad_mom3_corr == -0.07

    # Round-trip through JSON serialisation.
    serialised = meta.model_dump(mode="json")
    assert serialised["mad_coverage_pct"] == 94.5
    assert serialised["mad_mom12_corr"] == 0.18
    assert serialised["mad_mom3_corr"] == -0.07

    # Restore and verify structural equality.
    restored = Metadata.model_validate(serialised)
    assert restored.mad_coverage_pct == meta.mad_coverage_pct
    assert restored.mad_mom12_corr == meta.mad_mom12_corr
    assert restored.mad_mom3_corr == meta.mad_mom3_corr


# ---------------------------------------------------------------------------
# Test 2 — optional-field contract: omitting all three -> all None
# ---------------------------------------------------------------------------


def test_mad_diagnostics_fields_optional_default_none():
    """Issue #441 PR-1 — the three MAD fields are optional with ``= None``
    defaults. A Metadata constructed without supplying them raises no
    ValidationError and serialises all three as ``None``.

    This is the PATCH-bump backward-compat guarantee: a legacy
    metadata.json (pre-0.10.16) deserialises cleanly with the new fields
    silently defaulting to None.
    """
    payload = _base_payload()
    assert "mad_coverage_pct" not in payload
    assert "mad_mom12_corr" not in payload
    assert "mad_mom3_corr" not in payload

    meta = Metadata.model_validate(payload)

    assert meta.mad_coverage_pct is None
    assert meta.mad_mom12_corr is None
    assert meta.mad_mom3_corr is None

    # Serialisation must carry None explicitly (not omit the keys) so the
    # JSON contract is stable regardless of whether the field was populated.
    serialised = meta.model_dump(mode="json")
    assert "mad_coverage_pct" in serialised
    assert serialised["mad_coverage_pct"] is None
    assert "mad_mom12_corr" in serialised
    assert serialised["mad_mom12_corr"] is None
    assert "mad_mom3_corr" in serialised
    assert serialised["mad_mom3_corr"] is None


# ---------------------------------------------------------------------------
# Test 3 — JSON carries no NaN: None survives mode='json' round-trip cleanly
# ---------------------------------------------------------------------------


def test_mad_diagnostics_none_fields_carry_no_nan_in_json():
    """None values serialise as JSON null (not NaN).

    Pydantic's model_dump(mode='json') must never emit float('nan') for
    the MAD fields when the values are None — NaN is not valid JSON and
    would break downstream consumers (the Next.js frontend would fail to
    JSON.parse). The ``mode='json'`` round-trip is the write-path that
    produces ``frontend/public/data/metadata.json``.
    """
    payload = _base_payload()
    meta = Metadata.model_validate(payload)
    serialised = meta.model_dump(mode="json")

    for field in ("mad_coverage_pct", "mad_mom12_corr", "mad_mom3_corr"):
        val = serialised[field]
        assert val is None, f"{field} should be None in JSON, got {val!r}"
        # Explicit NaN-safety guard: None != float('nan'), and isinstance
        # check rules out any accidental float sentinel.
        assert not isinstance(val, float), (
            f"{field} must not be a float in JSON serialisation; got {val!r}"
        )


# ---------------------------------------------------------------------------
# Test 4 — known-float round-trip: values survive full Metadata round-trip
# ---------------------------------------------------------------------------


def test_mad_diagnostics_known_floats_survive_metadata_round_trip():
    """Populate all three MAD fields with production-representative values
    (coverage near 95%, correlations < 0.30 as required by the PR-2 gate),
    validate through Metadata, serialise, and restore — verifying the full
    write-path contract.

    Representative values: coverage 95.2% (> 90% gate passes), mom12_corr
    0.15 (|rho| < 0.30 gate passes), mom3_corr -0.04 (|rho| < 0.30 gate
    passes).
    """
    payload = _base_payload()
    payload["mad_coverage_pct"] = 95.2
    payload["mad_mom12_corr"] = 0.15
    payload["mad_mom3_corr"] = -0.04

    meta = Metadata.model_validate(payload)
    serialised = meta.model_dump(mode="json")
    restored = Metadata.model_validate(serialised)

    assert restored.mad_coverage_pct == 95.2
    assert restored.mad_mom12_corr == 0.15
    assert restored.mad_mom3_corr == -0.04
    # Confirm the gate conditions as documented in schemas.py comments.
    assert restored.mad_coverage_pct >= 90.0, "coverage below PR-2 gate"
    assert math.isfinite(restored.mad_mom12_corr)
    assert abs(restored.mad_mom12_corr) < 0.30, "|rho12| exceeds PR-2 gate"
    assert math.isfinite(restored.mad_mom3_corr)
    assert abs(restored.mad_mom3_corr) < 0.30, "|rho3| exceeds PR-2 gate"
