"""Schema + round-trip tests for the Issue #287 PR A wall-clock Metadata fields.

Four new optional fields land on ``Metadata`` at schema ``0.10.9-phase4.6``:

- ``tier2_wall_clock_seconds: float | None = None``
- ``form4_wall_clock_seconds: float | None = None``
- ``osap_wall_clock_seconds: float | None = None``
- ``cross_source_wall_clock_seconds: float | None = None``

All four follow the PATCH-bump "add optional field, default None" contract
(SKILL.md Rule: additive optional → PATCH) so legacy metadata.json files
(pre-0.10.9) deserialize cleanly.

Coverage policy (AGENTS.md §Testing): "add a test when a new contract is
added to the output schema" — this file satisfies that policy for the four
wall-clock fields.

Tests 3/4/5 (behavior wiring inside ``run_weekly_compute``) require the
full orchestrator harness (2000-line function, SEC EDGAR fetchers, yfinance,
ThreadPoolExecutor) and there is no existing unit-level pattern for it in
the test suite (see test_main.py docstring: "smoke / integration tests with
real data" cover the orchestrator). Those tests are deferred to a future PR
that adds a minimal orchestrator test harness.

TODO (future PR): add test_form4_wall_clock_none_when_skipped, using
    monkeypatch on ``os.environ["FORM4_FETCH_SKIP"] = "1"`` and a
    lightweight ``run_weekly_compute`` harness that stubs all SEC EDGAR
    fetchers. Invariant: form4_wall_clock_seconds is None in the
    Metadata written to disk when FORM4_FETCH_SKIP=1.

TODO (future PR): add test_osap_wall_clock_none_on_pipeline_failure, using
    monkeypatch to make ``fetch_osap_returns`` raise RuntimeError and
    assert that osap_wall_clock_seconds is None in the resulting Metadata.

TODO (future PR): add test_tier2_wall_clock_populated_on_success, using
    a monkeypatched ``fetch_tier2_for_ticker`` (return a minimal Tier2Result)
    and asserting that tier2_wall_clock_seconds is not None and isinstance
    of float after the loop completes.
"""

from __future__ import annotations

import pytest

from compute.output.schemas import Metadata

# ---------------------------------------------------------------------------
# Canonical minimal payload for the 7 required Metadata fields.
# Adapted from the existing test_schema_phase4h2._legacy_0_9_0_metadata_payload
# pattern — keeps the fixture minimal and self-documenting.
# ---------------------------------------------------------------------------

def _base_metadata_payload() -> dict:
    """A minimal Metadata payload with only the 7 required fields set.

    No wall-clock fields included — lets each test layer in exactly what
    it needs to verify, following the synthetic-fixture pattern used
    throughout tests/test_output/.
    """
    return {
        "version": "0.10.9-phase4.6",
        "last_update_utc": "2026-05-28T22:00:00Z",
        "next_update_utc": "2026-06-04T22:00:00Z",
        "universe": "sp500",
        "universe_size": 502,
        "compute_run_id": "local",
        "git_commit": "a" * 40,
    }


# ---------------------------------------------------------------------------
# Test 1 — happy path: all four wall-clock fields populated, round-trip intact
# ---------------------------------------------------------------------------

def test_wall_clock_fields_exist_on_metadata_with_floats():
    """Issue #287 PR A — all four wall-clock fields accept floats and
    survive a model_dump(mode='json') round-trip with exact value
    preservation.

    Invariant: the fields are plain ``float | None`` with no coercion or
    truncation — the exact float written to disk is what the operator
    sees in metadata.json.
    """
    payload = _base_metadata_payload()
    payload["tier2_wall_clock_seconds"] = 123.4
    payload["form4_wall_clock_seconds"] = 45.6
    payload["osap_wall_clock_seconds"] = 7.8
    payload["cross_source_wall_clock_seconds"] = 901.2

    meta = Metadata.model_validate(payload)

    assert meta.tier2_wall_clock_seconds == 123.4
    assert meta.form4_wall_clock_seconds == 45.6
    assert meta.osap_wall_clock_seconds == 7.8
    assert meta.cross_source_wall_clock_seconds == 901.2

    # Round-trip through JSON serialisation — what gets written to
    # frontend/public/data/metadata.json must be identical.
    serialised = meta.model_dump(mode="json")
    assert serialised["tier2_wall_clock_seconds"] == 123.4
    assert serialised["form4_wall_clock_seconds"] == 45.6
    assert serialised["osap_wall_clock_seconds"] == 7.8
    assert serialised["cross_source_wall_clock_seconds"] == 901.2

    # Restore via model_validate and verify structural equality.
    restored = Metadata.model_validate(serialised)
    assert restored.tier2_wall_clock_seconds == meta.tier2_wall_clock_seconds
    assert restored.form4_wall_clock_seconds == meta.form4_wall_clock_seconds
    assert restored.osap_wall_clock_seconds == meta.osap_wall_clock_seconds
    assert restored.cross_source_wall_clock_seconds == meta.cross_source_wall_clock_seconds


# ---------------------------------------------------------------------------
# Test 2 — optional-field contract: omitting all four fields → all None
# ---------------------------------------------------------------------------

def test_wall_clock_fields_optional_default_none():
    """Issue #287 PR A — the four wall-clock fields are optional with
    ``= None`` defaults.  A Metadata constructed without supplying them
    raises no ValidationError and serialises all four as ``None``.

    This is the PATCH-bump backward-compat guarantee: a legacy
    metadata.json (pre-0.10.9) deserialises cleanly with the new fields
    silently defaulting to None — identical semantics to every prior
    Phase-4h additive-optional field (osap_signals_missing_from_dataset,
    loss_avoidance_size_invariant_firing_count, etc.).
    """
    payload = _base_metadata_payload()
    # Deliberately omit all four wall-clock fields — simulates a legacy
    # snapshot or any cron run where the fields were not yet written.
    assert "tier2_wall_clock_seconds" not in payload
    assert "form4_wall_clock_seconds" not in payload
    assert "osap_wall_clock_seconds" not in payload
    assert "cross_source_wall_clock_seconds" not in payload

    # Must not raise ValidationError.
    meta = Metadata.model_validate(payload)

    assert meta.tier2_wall_clock_seconds is None
    assert meta.form4_wall_clock_seconds is None
    assert meta.osap_wall_clock_seconds is None
    assert meta.cross_source_wall_clock_seconds is None

    # Serialisation must carry None explicitly (not omit the keys) so the
    # JSON contract is stable regardless of whether the field was populated.
    serialised = meta.model_dump(mode="json")
    assert "tier2_wall_clock_seconds" in serialised
    assert serialised["tier2_wall_clock_seconds"] is None
    assert "form4_wall_clock_seconds" in serialised
    assert serialised["form4_wall_clock_seconds"] is None
    assert "osap_wall_clock_seconds" in serialised
    assert serialised["osap_wall_clock_seconds"] is None
    assert "cross_source_wall_clock_seconds" in serialised
    assert serialised["cross_source_wall_clock_seconds"] is None


# ---------------------------------------------------------------------------
# Tests 3/4/5 — deferred (orchestrator harness not available as unit tests)
# ---------------------------------------------------------------------------

@pytest.mark.skip(
    reason=(
        "TODO (future PR): test_form4_wall_clock_none_when_skipped requires a "
        "lightweight run_weekly_compute harness that stubs all SEC EDGAR "
        "fetchers. No such harness exists in the test suite today (test_main.py "
        "covers only helper functions, not the orchestrator). Invariant to pin: "
        "monkeypatch os.environ['FORM4_FETCH_SKIP']='1' → form4_wall_clock_seconds "
        "is None in the written Metadata."
    )
)
def test_form4_wall_clock_none_when_skipped():
    """Deferred — see module docstring TODO block."""


@pytest.mark.skip(
    reason=(
        "TODO (future PR): test_osap_wall_clock_none_on_pipeline_failure requires "
        "a lightweight run_weekly_compute harness. Invariant to pin: monkeypatch "
        "fetch_osap_returns to raise RuntimeError → osap_wall_clock_seconds is "
        "None in the resulting Metadata (the outer except in main.py:1331 leaves "
        "osap_wall_clock_seconds = None per Issue #287 PR A semantics)."
    )
)
def test_osap_wall_clock_none_on_pipeline_failure():
    """Deferred — see module docstring TODO block."""


@pytest.mark.skip(
    reason=(
        "TODO (future PR): test_tier2_wall_clock_populated_on_success requires a "
        "lightweight run_weekly_compute harness. Invariant to pin: monkeypatch "
        "fetch_tier2_for_ticker to return a minimal Tier2Result → "
        "tier2_wall_clock_seconds is not None and isinstance(float) in the "
        "resulting Metadata (happy-path wiring: main.py:1023 assigns the end "
        "marker inside the try block after the ThreadPoolExecutor completes)."
    )
)
def test_tier2_wall_clock_populated_on_success():
    """Deferred — see module docstring TODO block."""
