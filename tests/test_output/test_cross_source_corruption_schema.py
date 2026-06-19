"""Schema contract test for the 4 new Metadata fields added in PR-1
(cross-source share-count-corruption shadow observability,
schema ``0.10.26-phase8pilot``):

    cross_source_corruption_correct_candidate_count: int | None = None
    cross_source_corruption_veto_candidate_count: int | None = None
    cross_source_corruption_ratio_disagreement_count: int | None = None
    cross_source_corruption_inferred_ratio_by_ticker: dict[str, float] | None = None

Coverage policy (AGENTS.md §Testing): "add a test when a new contract is
added to the output schema" — this file satisfies that policy.

Style mirrors ``tests/test_output/test_post_split_schema.py``
(the most recent ``*_count`` Metadata field test in this module).
"""

from __future__ import annotations

from compute.output.schemas import Metadata

# ---------------------------------------------------------------------------
# Canonical minimal payload (7 required Metadata fields only).
# ---------------------------------------------------------------------------

def _base_metadata_payload() -> dict:
    """Minimal Metadata payload (7 required fields).

    Version pinned to the schema that introduced the corruption fields
    (0.10.26-phase8pilot).  The model accepts any string for ``version``;
    this does not need updating on future schema bumps as long as the 4
    fields remain in the model.
    """
    return {
        "version": "0.10.26-phase8pilot",
        "last_update_utc": "2026-06-19T22:00:00Z",
        "next_update_utc": "2026-06-26T22:00:00Z",
        "universe": "sp900",
        "universe_size": 903,
        "compute_run_id": "local-pr1-shadow-test",
        "git_commit": "abc00000" + "a" * 32,
    }


# ---------------------------------------------------------------------------
# CSC10 — Schema nullability: all 4 new fields default to None
# ---------------------------------------------------------------------------

def test_CSC10_cross_source_corruption_fields_default_to_none():
    """Pre-0.10.26 metadata.json (no corruption fields) must deserialize cleanly.

    All 4 fields default to None — the additive-optional PATCH-bump
    backward-compatibility guarantee shared by every prior Phase-4h+
    Metadata field (e.g., post_split_share_lag_count, median_trim_delta_count).

    Verifies:
    - Metadata(**minimal_kwargs) does not raise on any of the 4 fields missing.
    - All 4 fields are None on the deserialized model.
    - Serialisation (model_dump) includes all 4 keys as None (stable JSON contract).
    - Re-deserialization from the serialised JSON round-trips cleanly.
    """
    payload = _base_metadata_payload()
    # Confirm the 4 fields are absent from the minimal payload.
    assert "cross_source_corruption_correct_candidate_count" not in payload
    assert "cross_source_corruption_veto_candidate_count" not in payload
    assert "cross_source_corruption_ratio_disagreement_count" not in payload
    assert "cross_source_corruption_inferred_ratio_by_ticker" not in payload

    meta = Metadata.model_validate(payload)

    # All 4 default to None (backward-compat).
    assert meta.cross_source_corruption_correct_candidate_count is None
    assert meta.cross_source_corruption_veto_candidate_count is None
    assert meta.cross_source_corruption_ratio_disagreement_count is None
    assert meta.cross_source_corruption_inferred_ratio_by_ticker is None

    # Serialisation must include all 4 as None (stable JSON contract — keys present).
    serialised = meta.model_dump(mode="json")
    assert "cross_source_corruption_correct_candidate_count" in serialised
    assert "cross_source_corruption_veto_candidate_count" in serialised
    assert "cross_source_corruption_ratio_disagreement_count" in serialised
    assert "cross_source_corruption_inferred_ratio_by_ticker" in serialised
    assert serialised["cross_source_corruption_correct_candidate_count"] is None
    assert serialised["cross_source_corruption_veto_candidate_count"] is None
    assert serialised["cross_source_corruption_ratio_disagreement_count"] is None
    assert serialised["cross_source_corruption_inferred_ratio_by_ticker"] is None

    # Round-trip: re-deserialise from the serialised JSON must succeed.
    restored = Metadata.model_validate(serialised)
    assert restored.cross_source_corruption_correct_candidate_count is None
    assert restored.cross_source_corruption_veto_candidate_count is None
    assert restored.cross_source_corruption_ratio_disagreement_count is None
    assert restored.cross_source_corruption_inferred_ratio_by_ticker is None


# ---------------------------------------------------------------------------
# CSC10b — Round-trip with populated values (CVNA scenario)
# ---------------------------------------------------------------------------

def test_CSC10b_cross_source_corruption_fields_round_trip_with_values():
    """Populated scenario: 1 CORRECT_CANDIDATE (CVNA), 1 VETO (COKE), 1 ratio_disagree.

    Verifies that populated int / dict[str,float] values survive the
    Pydantic model_validate → model_dump → model_validate cycle.
    """
    payload = _base_metadata_payload()
    payload["cross_source_corruption_correct_candidate_count"] = 1
    payload["cross_source_corruption_veto_candidate_count"] = 1
    payload["cross_source_corruption_ratio_disagreement_count"] = 1
    payload["cross_source_corruption_inferred_ratio_by_ticker"] = {"CVNA": 5.0}

    meta = Metadata.model_validate(payload)

    assert meta.cross_source_corruption_correct_candidate_count == 1
    assert meta.cross_source_corruption_veto_candidate_count == 1
    assert meta.cross_source_corruption_ratio_disagreement_count == 1
    assert meta.cross_source_corruption_inferred_ratio_by_ticker == {"CVNA": 5.0}

    serialised = meta.model_dump(mode="json")
    assert serialised["cross_source_corruption_correct_candidate_count"] == 1
    assert serialised["cross_source_corruption_veto_candidate_count"] == 1
    assert serialised["cross_source_corruption_ratio_disagreement_count"] == 1
    assert serialised["cross_source_corruption_inferred_ratio_by_ticker"] == {"CVNA": 5.0}

    restored = Metadata.model_validate(serialised)
    assert restored.cross_source_corruption_correct_candidate_count == 1
    assert restored.cross_source_corruption_veto_candidate_count == 1
    assert restored.cross_source_corruption_ratio_disagreement_count == 1
    assert restored.cross_source_corruption_inferred_ratio_by_ticker == {"CVNA": 5.0}
