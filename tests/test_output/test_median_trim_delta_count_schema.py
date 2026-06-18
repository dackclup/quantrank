"""Schema contract + round-trip tests for ``Metadata.median_trim_delta_count``.

Issue #177 PR-A (schema ``0.10.24-phase8pilot``) adds a Rule-18 blast-radius
observability counter:

    median_trim_delta_count: int | None = None

It counts universe tickers whose MoS SIGN would flip under the shadow trimmed
median vs the live median (diagnostic only — live ``mos_pct`` is byte-identical).
The field is nullable on legacy snapshots (pre-0.10.24) so the
additive-optional PATCH-bump contract is preserved.

Coverage policy (AGENTS.md §Testing): "add a test when a new contract is added
to the output schema" — this file satisfies that policy.

Style mirrors ``tests/test_output/test_fundamentals_unavailable_count_schema.py``
(the most recent ``*_count`` Metadata field test in the same module).
"""

from __future__ import annotations

from compute.output.schemas import Metadata

# ---------------------------------------------------------------------------
# Canonical minimal payload (7 required Metadata fields only).
# No ``median_trim_delta_count`` present by default — tests layer it in
# explicitly so the backward-compat assertion is unambiguous.
# ---------------------------------------------------------------------------

def _base_metadata_payload() -> dict:
    """Minimal Metadata payload with only the 7 required fields set.

    Schema version is set to the version that introduced the field
    (0.10.24-phase8pilot) so the fixture is self-documenting.  The model
    accepts any string for ``version`` — no validation against the current
    ``SCHEMA_VERSION`` constant — so this does not need updating on future
    schema bumps as long as the field stays in the model.
    """
    return {
        "version": "0.10.24-phase8pilot",
        "last_update_utc": "2026-06-18T22:00:00Z",
        "next_update_utc": "2026-06-25T22:00:00Z",
        "universe": "sp500",
        "universe_size": 502,
        "compute_run_id": "local",
        "git_commit": "abc12345" + "a" * 32,
    }


# ---------------------------------------------------------------------------
# test_metadata_median_trim_delta_count_field (required by PR-A spec)
# ---------------------------------------------------------------------------

def test_metadata_median_trim_delta_count_field():
    """``Metadata`` accepts + round-trips ``median_trim_delta_count`` as int
    and as None (Issue #177 PR-A).

    The field must:
    - Accept a non-negative int and preserve the exact value through
      model_validate → model_dump → model_validate.
    - Default to None when absent from the payload (backward-compat with
      pre-0.10.24 snapshots).
    - Appear in model_dump even when None (stable JSON contract — reader
      must not KeyError on legacy artifacts).
    """
    # --- Case 1: int value round-trips faithfully ---
    payload_int = _base_metadata_payload()
    payload_int["median_trim_delta_count"] = 7  # 7 tickers would flip MoS sign

    meta_int = Metadata.model_validate(payload_int)
    assert meta_int.median_trim_delta_count == 7, (
        "median_trim_delta_count=7 must survive model_validate"
    )

    serialised_int = meta_int.model_dump(mode="json")
    assert serialised_int["median_trim_delta_count"] == 7, (
        "median_trim_delta_count must appear in model_dump with the exact int value"
    )

    restored_int = Metadata.model_validate(serialised_int)
    assert restored_int.median_trim_delta_count == 7, (
        "full round-trip (validate → dump → validate) must preserve int value"
    )

    # --- Case 2: zero is a valid value (no sign flips on this cron) ---
    payload_zero = _base_metadata_payload()
    payload_zero["median_trim_delta_count"] = 0

    meta_zero = Metadata.model_validate(payload_zero)
    assert meta_zero.median_trim_delta_count == 0, (
        "median_trim_delta_count=0 (healthy cron — no MoS sign flips) must be accepted"
    )
    dumped_zero = meta_zero.model_dump(mode="json")
    assert dumped_zero["median_trim_delta_count"] == 0

    # --- Case 3: None — legacy snapshot or computation failure ---
    payload_none = _base_metadata_payload()
    # Deliberately omit the field — simulates a pre-0.10.24 snapshot.
    assert "median_trim_delta_count" not in payload_none

    meta_none = Metadata.model_validate(payload_none)
    assert meta_none.median_trim_delta_count is None, (
        "Omitting median_trim_delta_count must yield None (backward-compat)"
    )

    serialised_none = meta_none.model_dump(mode="json")
    assert "median_trim_delta_count" in serialised_none, (
        "median_trim_delta_count must appear in model_dump even when None "
        "(stable JSON contract — reader must not KeyError)"
    )
    assert serialised_none["median_trim_delta_count"] is None
