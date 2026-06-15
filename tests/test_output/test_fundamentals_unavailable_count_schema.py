"""Schema contract + round-trip tests for ``Metadata.fundamentals_unavailable_count``.

The OZK/PBF flip-blocker (commit 31e95b6f, schema ``0.10.22-phase8pilot``)
adds a Rule-18 observability counter:

    fundamentals_unavailable_count: int | None = None

It counts tickers whose ``FundamentalsSnapshot`` was ``None`` (complete EDGAR
ingest failure) on the cron run.  Unlike ``share_count_extraction_missing_count``
(annotate-only), the underlying flag ships as a direct veto —
``fundamentals_unavailable`` in ``_CAUTIOUS_FORCING_RISK``.  The counter is
nullable on legacy snapshots (pre-0.10.22) so the additive-optional PATCH-bump
contract is preserved.

Coverage policy (AGENTS.md §Testing): "add a test when a new contract is added
to the output schema" — this file satisfies that policy.

Style mirrors ``tests/test_output/test_wall_clock_schema.py`` (the most recent
``*_count / *_seconds`` Metadata field test in the same module).
"""

from __future__ import annotations

from compute.output.schemas import Metadata


# ---------------------------------------------------------------------------
# Canonical minimal payload (7 required Metadata fields only).
# No ``fundamentals_unavailable_count`` present by default — tests layer
# it in explicitly so the backward-compat assertion is unambiguous.
# ---------------------------------------------------------------------------

def _base_metadata_payload() -> dict:
    """Minimal Metadata payload with only the 7 required fields set.

    Schema version is set to the version that introduced the field
    (0.10.22-phase8pilot) so the fixture is self-documenting.  The
    model accepts any string for ``version`` — no validation against the
    current ``SCHEMA_VERSION`` constant — so this does not need updating
    on future schema bumps as long as the field stays in the model.
    """
    return {
        "version": "0.10.22-phase8pilot",
        "last_update_utc": "2026-06-15T22:00:00Z",
        "next_update_utc": "2026-06-22T22:00:00Z",
        "universe": "sp500",
        "universe_size": 502,
        "compute_run_id": "local",
        "git_commit": "31e95b6f" + "a" * 32,
    }


# ---------------------------------------------------------------------------
# Test 1 — happy path: field accepts int, survives model_dump/model_validate
# ---------------------------------------------------------------------------

def test_fundamentals_unavailable_count_round_trips_with_int():
    """OZK/PBF flip-blocker — ``fundamentals_unavailable_count=2`` (the
    minimal scenario: OZK + PBF both returned None snapshots) serialises
    and round-trips through JSON with the exact value preserved.

    Invariant: the field is ``int | None`` with no coercion; the value
    written to ``metadata.json`` is the exact integer emitted by
    ``compute_risk_flags``.
    """
    payload = _base_metadata_payload()
    payload["fundamentals_unavailable_count"] = 2  # OZK + PBF scenario

    meta = Metadata.model_validate(payload)
    assert meta.fundamentals_unavailable_count == 2

    # Round-trip through JSON serialisation — what gets written to disk.
    serialised = meta.model_dump(mode="json")
    assert serialised["fundamentals_unavailable_count"] == 2

    # Restore via model_validate and verify structural equality.
    restored = Metadata.model_validate(serialised)
    assert restored.fundamentals_unavailable_count == 2


# ---------------------------------------------------------------------------
# Test 2 — optional-field contract: omitting the field → None (legacy compat)
# ---------------------------------------------------------------------------

def test_fundamentals_unavailable_count_optional_defaults_to_none():
    """Pre-0.10.22 metadata.json snapshots (no ``fundamentals_unavailable_count``
    key) must deserialise cleanly — the field defaults to ``None``.

    This is the PATCH-bump backward-compat guarantee: the same contract as
    every prior Phase-4h+ additive-optional field (wall-clock seconds, OSAP
    diagnostics, etc.).  A non-zero production value is a data-pipeline health
    signal; ``None`` means the counter was not populated on that cron (pre-fix
    run or cron where the step was skipped).
    """
    payload = _base_metadata_payload()
    # Deliberately omit the new field — simulates a legacy snapshot.
    assert "fundamentals_unavailable_count" not in payload

    meta = Metadata.model_validate(payload)

    assert meta.fundamentals_unavailable_count is None

    # Serialisation must carry None explicitly (not omit the key) so the
    # JSON contract is stable and the verify-helper can read the field.
    serialised = meta.model_dump(mode="json")
    assert "fundamentals_unavailable_count" in serialised
    assert serialised["fundamentals_unavailable_count"] is None


# ---------------------------------------------------------------------------
# Test 3 — zero is a valid value (healthy cron: all snaps returned non-None)
# ---------------------------------------------------------------------------

def test_fundamentals_unavailable_count_zero_is_valid():
    """On a healthy sp500 cron every ticker returns a non-None
    ``FundamentalsSnapshot``; the counter should be 0, not None.

    A value of 0 is semantically distinct from None: it means the feature
    ran and found no unavailable snapshots (all-clear), whereas None means
    the counter was never populated (pre-fix run).  The Pydantic model must
    accept 0 and round-trip it faithfully.
    """
    payload = _base_metadata_payload()
    payload["fundamentals_unavailable_count"] = 0

    meta = Metadata.model_validate(payload)
    assert meta.fundamentals_unavailable_count == 0

    serialised = meta.model_dump(mode="json")
    assert serialised["fundamentals_unavailable_count"] == 0

    restored = Metadata.model_validate(serialised)
    assert restored.fundamentals_unavailable_count == 0
