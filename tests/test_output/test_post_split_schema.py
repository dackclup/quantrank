"""Schema contract + round-trip tests for the three post-split counters in Metadata
(PR-2, schema ``0.10.25-phase8pilot``):

    post_split_share_lag_count: int | None = None
    post_split_correction_applied_count: int | None = None
    post_split_veto_count: int | None = None

Coverage policy (AGENTS.md §Testing): "add a test when a new contract is added to the
output schema" — this file satisfies that policy.

Pin 6 from the PR-2 spec:
  ``Metadata(post_split_correction_applied_count=a, post_split_veto_count=b,
  post_split_share_lag_count=a+b)`` round-trips; count == applied + veto.

Style mirrors ``tests/test_output/test_fundamentals_unavailable_count_schema.py``
(the most recent ``*_count`` Metadata field test in this module).
"""

from __future__ import annotations

from compute.output.schemas import Metadata

# ---------------------------------------------------------------------------
# Canonical minimal payload — the 7 required Metadata fields only.
# ---------------------------------------------------------------------------

def _base_metadata_payload() -> dict:
    """Minimal Metadata payload (7 required fields).

    Version pinned to the schema that introduced these fields
    (0.10.25-phase8pilot) so the fixture is self-documenting.  The model
    accepts any string for ``version`` — this does not need updating on
    future bumps as long as the three fields remain in the model.
    """
    return {
        "version": "0.10.25-phase8pilot",
        "last_update_utc": "2026-06-18T22:00:00Z",
        "next_update_utc": "2026-06-25T22:00:00Z",
        "universe": "sp900",
        "universe_size": 903,
        "compute_run_id": "local-pr2-test",
        "git_commit": "abc00000" + "a" * 32,
    }


# ---------------------------------------------------------------------------
# PSL6a — happy path: all three counters round-trip with correct values.
# ---------------------------------------------------------------------------

def test_post_split_counters_round_trip_with_int_values():
    """post_split_share_lag_count = correction_applied + veto round-trips faithfully.

    KLAC scenario: 1 Tier-1 correction + 0 vetoes.
    """
    payload = _base_metadata_payload()
    payload["post_split_correction_applied_count"] = 1
    payload["post_split_veto_count"] = 0
    payload["post_split_share_lag_count"] = 1  # = 1 + 0

    meta = Metadata.model_validate(payload)

    assert meta.post_split_correction_applied_count == 1
    assert meta.post_split_veto_count == 0
    assert meta.post_split_share_lag_count == 1

    serialised = meta.model_dump(mode="json")
    assert serialised["post_split_correction_applied_count"] == 1
    assert serialised["post_split_veto_count"] == 0
    assert serialised["post_split_share_lag_count"] == 1

    restored = Metadata.model_validate(serialised)
    assert restored.post_split_correction_applied_count == 1
    assert restored.post_split_veto_count == 0
    assert restored.post_split_share_lag_count == 1


# ---------------------------------------------------------------------------
# PSL6b — additive-sum invariant: share_lag_count == applied + veto.
# ---------------------------------------------------------------------------

def test_post_split_share_lag_count_equals_applied_plus_veto():
    """Counter consistency invariant: share_lag_count == correction_applied + veto.

    Pydantic does NOT enforce this algebraic constraint — it is a data-pipeline
    invariant maintained in compute/main.py.  This test pins the invariant by
    checking that the combination validates cleanly and the arithmetic holds.
    """
    applied = 3
    veto = 2
    total = applied + veto  # 5

    payload = _base_metadata_payload()
    payload["post_split_correction_applied_count"] = applied
    payload["post_split_veto_count"] = veto
    payload["post_split_share_lag_count"] = total

    meta = Metadata.model_validate(payload)

    assert meta.post_split_share_lag_count == meta.post_split_correction_applied_count + meta.post_split_veto_count, (
        "post_split_share_lag_count must equal correction_applied + veto_count "
        f"({meta.post_split_correction_applied_count} + {meta.post_split_veto_count} "
        f"= {meta.post_split_correction_applied_count + meta.post_split_veto_count}, "
        f"stored={meta.post_split_share_lag_count})"
    )


# ---------------------------------------------------------------------------
# PSL6c — optional-field contract: omitting any counter → None (backward-compat).
# ---------------------------------------------------------------------------

def test_post_split_counters_optional_default_to_none():
    """Pre-0.10.25 metadata.json (no post_split_* fields) must deserialize cleanly.

    Each field defaults to None — the additive-optional PATCH-bump backward-compat
    guarantee shared by every prior Phase-4h+ Metadata field.
    """
    payload = _base_metadata_payload()
    # Deliberately omit all three fields.
    assert "post_split_share_lag_count" not in payload
    assert "post_split_correction_applied_count" not in payload
    assert "post_split_veto_count" not in payload

    meta = Metadata.model_validate(payload)

    assert meta.post_split_share_lag_count is None
    assert meta.post_split_correction_applied_count is None
    assert meta.post_split_veto_count is None

    # Serialisation must include all three as None (stable JSON contract).
    serialised = meta.model_dump(mode="json")
    assert "post_split_share_lag_count" in serialised
    assert "post_split_correction_applied_count" in serialised
    assert "post_split_veto_count" in serialised
    assert serialised["post_split_share_lag_count"] is None
    assert serialised["post_split_correction_applied_count"] is None
    assert serialised["post_split_veto_count"] is None


# ---------------------------------------------------------------------------
# PSL6d — zero is a valid value (healthy cron: no splits in window).
# ---------------------------------------------------------------------------

def test_post_split_counters_zero_is_valid():
    """All three counters accept 0 (healthy cron — no recent material splits)."""
    payload = _base_metadata_payload()
    payload["post_split_share_lag_count"] = 0
    payload["post_split_correction_applied_count"] = 0
    payload["post_split_veto_count"] = 0

    meta = Metadata.model_validate(payload)
    assert meta.post_split_share_lag_count == 0
    assert meta.post_split_correction_applied_count == 0
    assert meta.post_split_veto_count == 0

    # Arithmetic check: 0 == 0 + 0.
    assert meta.post_split_share_lag_count == (
        meta.post_split_correction_applied_count + meta.post_split_veto_count
    )


# ---------------------------------------------------------------------------
# PSL6e — all-veto scenario (no Tier-1 corrections, only vetoes).
# ---------------------------------------------------------------------------

def test_post_split_all_veto_scenario():
    """Scenario: 2 tickers hit Tier-2 (veto), 0 Tier-1 corrections.

    share_lag_count = 0 + 2 = 2.
    """
    payload = _base_metadata_payload()
    payload["post_split_correction_applied_count"] = 0
    payload["post_split_veto_count"] = 2
    payload["post_split_share_lag_count"] = 2

    meta = Metadata.model_validate(payload)

    assert meta.post_split_share_lag_count == 2
    assert meta.post_split_correction_applied_count == 0
    assert meta.post_split_veto_count == 2
    # Invariant holds.
    assert meta.post_split_share_lag_count == (
        meta.post_split_correction_applied_count + meta.post_split_veto_count
    )
