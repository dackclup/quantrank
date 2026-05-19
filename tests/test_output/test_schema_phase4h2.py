"""Pydantic round-trip + legacy backward-compat tests for the
Phase 4h.2 Part 1 schema additions (issue #116).

Two new optional fields land on ``Metadata``:

- ``osap_signals_missing_from_dataset: list[str] | None = None``
- ``osap_gate_diagnostics: dict[str, OsapGateDiagnostic] | None = None``

Plus a new nested model ``OsapGateDiagnostic`` with 4 nullable fields.
All defaults are ``None`` so a legacy 0.9.0-phase4h ``metadata.json``
deserializes cleanly with the new fields set to ``None`` — the
canonical "additive optional field → PATCH bump" pattern from
SKILL.md L305 ("Add a new optional field (default = None) → patch").
"""

from __future__ import annotations

from compute.output.schemas import Metadata, OsapGateDiagnostic


def _legacy_0_9_0_metadata_payload() -> dict:
    """A canonical 0.9.0-phase4h metadata.json payload — the production
    shape *before* this PR's additions. Used to assert backward-compat.
    """
    return {
        "version": "0.9.0-phase4h",
        "last_update_utc": "2026-05-18T22:00:00Z",
        "next_update_utc": "2026-05-25T22:00:00Z",
        "universe": "sp500",
        "universe_size": 502,
        "compute_run_id": "local",
        "git_commit": "fbd1acf461847d835967bd701a098af93c9d2bd7",
        "mos_trailing_ic_smoke": 0.05,
        "tier2_coverage_pct": 0.97,
        "fundamentals_coverage_pct": 0.99,
        "fundamentals_latency_p50_seconds": 1.2,
        "fundamentals_latency_p95_seconds": 5.4,
        "osap_signals_used": None,
        "osap_excluded_signals": [
            "AbnormalAccruals", "AssetGrowth", "BM", "BetaFP", "CF",
        ],
        "osap_signals_ic_12m": None,
        "osap_signals_coverage_pct": None,
    }


def test_osap_gate_diagnostic_round_trip_with_all_fields():
    """Happy path — populate every field, round-trip through JSON."""
    diag = OsapGateDiagnostic(
        pbo=0.45,
        dsr=0.12,
        sharpe=0.34,
        rejection_reason=None,
    )
    payload = diag.model_dump()
    restored = OsapGateDiagnostic.model_validate(payload)
    assert restored == diag


def test_osap_gate_diagnostic_all_fields_default_to_none():
    """Empty construction (zero args) — every field is None.
    Per refinement #3: all 4 fields explicit ``= None`` defaults."""
    diag = OsapGateDiagnostic()
    assert diag.pbo is None
    assert diag.dsr is None
    assert diag.sharpe is None
    assert diag.rejection_reason is None


def test_osap_gate_diagnostic_rejection_reason_taxonomy():
    """Mirrors ``compute/validation/osap_validation.py::GateResult``
    rejection_reason values. The model accepts any str (no Literal
    constraint), but the canonical taxonomy should round-trip cleanly.
    """
    for reason in ("high_pbo", "low_dsr", "insufficient_data", "gate_failed"):
        diag = OsapGateDiagnostic(rejection_reason=reason)
        restored = OsapGateDiagnostic.model_validate(diag.model_dump())
        assert restored.rejection_reason == reason


def test_metadata_round_trip_with_new_fields_populated():
    """End-to-end: Metadata with both new fields populated."""
    payload = _legacy_0_9_0_metadata_payload()
    payload["osap_signals_missing_from_dataset"] = ["AOP", "AccrualsBM", "ChEQ"]
    payload["osap_gate_diagnostics"] = {
        "BM": {"pbo": 0.6, "dsr": -0.1, "sharpe": 0.05, "rejection_reason": "high_pbo"},
        "Mom12m": {"pbo": 0.4, "dsr": -0.3, "sharpe": 0.2, "rejection_reason": "low_dsr"},
    }
    meta = Metadata.model_validate(payload)
    assert meta.osap_signals_missing_from_dataset == ["AOP", "AccrualsBM", "ChEQ"]
    assert isinstance(meta.osap_gate_diagnostics, dict)
    assert meta.osap_gate_diagnostics["BM"].pbo == 0.6
    assert meta.osap_gate_diagnostics["BM"].rejection_reason == "high_pbo"
    assert meta.osap_gate_diagnostics["Mom12m"].dsr == -0.3

    restored = Metadata.model_validate(meta.model_dump())
    assert restored == meta


def test_metadata_backward_compat_with_0_9_0_payload():
    """Legacy 0.9.0-phase4h JSON (no new fields) deserializes cleanly
    — the backward-compat guarantee that justifies a PATCH bump per
    SKILL.md L305 ('Add a new optional field (default = None) →
    patch').
    """
    legacy_payload = _legacy_0_9_0_metadata_payload()
    assert "osap_signals_missing_from_dataset" not in legacy_payload
    assert "osap_gate_diagnostics" not in legacy_payload

    meta = Metadata.model_validate(legacy_payload)
    assert meta.version == "0.9.0-phase4h"
    assert meta.osap_signals_missing_from_dataset is None
    assert meta.osap_gate_diagnostics is None
    # Existing Phase 4h fields still populated.
    assert meta.osap_excluded_signals == [
        "AbnormalAccruals", "AssetGrowth", "BM", "BetaFP", "CF",
    ]


def test_metadata_new_fields_default_to_none():
    """Constructing a Metadata without supplying the new fields leaves
    them at None — same semantics as every other Phase-4h OSAP field."""
    payload = _legacy_0_9_0_metadata_payload()
    meta = Metadata.model_validate(payload)
    assert meta.osap_signals_missing_from_dataset is None
    assert meta.osap_gate_diagnostics is None


def test_metadata_extra_forbid_rejects_unknown_fields():
    """``model_config = ConfigDict(extra='forbid')`` catches typo'd
    field names. Locks the schema surface so future refactors that
    rename ``osap_signals_missing_from_dataset`` (e.g., to
    ``osap_manifest_missing``) raise instead of silently producing
    a no-op field."""
    import pytest as _pytest
    from pydantic import ValidationError

    payload = _legacy_0_9_0_metadata_payload()
    payload["osap_signals_missing"] = ["typo_field_name"]  # not the real field
    with _pytest.raises(ValidationError):
        Metadata.model_validate(payload)
