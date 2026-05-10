"""Unit tests for compute.output.schema_check (Phase 3c Step 9).

Locks the snapshot generator's contract + the diff-message format +
the round-trip semantics, so future schema additions can't silently
break the Python ↔ TypeScript parity guarantee.
"""

from __future__ import annotations

import json

import pytest

from compute.output import schema_check
from compute.output.schema_check import (
    TRACKED_MODELS,
    check_snapshot,
    generate_snapshot,
    main,
    update_snapshot,
)

# ---------------------------------------------------------------------------
# A. Snapshot generation
# ---------------------------------------------------------------------------

def test_A1_snapshot_has_expected_top_level_models():
    snap = generate_snapshot()
    expected = {"DataQuality", "Metadata", "PillarScores", "RawMetrics",
                "StockDetail", "StockSummary"}
    assert expected.issubset(set(snap.keys()))


def test_A2_fields_sorted_alphabetically():
    snap = generate_snapshot()
    for model_name, fields in snap.items():
        keys = list(fields.keys())
        assert keys == sorted(keys), (
            f"{model_name} fields not alphabetical: {keys}"
        )


def test_A3_field_entries_have_required_keys():
    snap = generate_snapshot()
    for model_name, fields in snap.items():
        for field_name, info in fields.items():
            assert set(info.keys()) == {"type", "required", "default"}, (
                f"{model_name}.{field_name} has unexpected keys: {info.keys()}"
            )
            assert isinstance(info["type"], str)
            assert isinstance(info["required"], bool)


def test_A4_top_level_models_sorted_alphabetically():
    """Module-level keys are alphabetized so the JSON output is stable
    across runs regardless of TRACKED_MODELS list order."""
    snap = generate_snapshot()
    keys = list(snap.keys())
    assert keys == sorted(keys)


def test_A5_tracked_models_count_matches_schemas_module():
    """If a new BaseModel is added to schemas.py, the test maintainer
    must remember to add it to TRACKED_MODELS. This canary catches
    the omission early."""
    from pydantic import BaseModel

    from compute.output import schemas as schemas_mod

    schema_classes = {
        cls
        for name in dir(schemas_mod)
        if isinstance(cls := getattr(schemas_mod, name), type)
        and issubclass(cls, BaseModel)
        and cls is not BaseModel
    }
    tracked = set(TRACKED_MODELS)
    missing = schema_classes - tracked
    assert not missing, (
        f"BaseModel subclasses in schemas.py not tracked: {missing}. "
        f"Add them to TRACKED_MODELS in schema_check.py."
    )


# ---------------------------------------------------------------------------
# B. Round-trip
# ---------------------------------------------------------------------------

def test_B1_round_trip_is_in_sync(tmp_path, monkeypatch):
    """After update_snapshot(), check_snapshot() must report in-sync."""
    fake_path = tmp_path / "schema-snapshot.json"
    monkeypatch.setattr(schema_check, "SNAPSHOT_PATH", fake_path)
    update_snapshot()
    assert fake_path.exists()
    ok, diff = check_snapshot()
    assert ok is True
    assert diff is None


def test_B2_mutated_file_triggers_drift(tmp_path, monkeypatch):
    """If the on-disk snapshot is mutated to add a synthetic field,
    check_snapshot() returns (False, <diff message>)."""
    fake_path = tmp_path / "schema-snapshot.json"
    monkeypatch.setattr(schema_check, "SNAPSHOT_PATH", fake_path)
    update_snapshot()

    stored = json.loads(fake_path.read_text())
    stored["StockDetail"]["__synthetic_field__"] = {
        "type": "str", "required": False, "default": None,
    }
    fake_path.write_text(json.dumps(stored, indent=2) + "\n")

    ok, diff = check_snapshot()
    assert ok is False
    assert diff is not None
    assert "__synthetic_field__" in diff


# ---------------------------------------------------------------------------
# C. Diff message quality
# ---------------------------------------------------------------------------

def test_C1_added_field_in_fresh_diff_format(tmp_path, monkeypatch):
    """If a field is in fresh but not stored, diff says 'ADDED' + name."""
    fake_path = tmp_path / "schema-snapshot.json"
    monkeypatch.setattr(schema_check, "SNAPSHOT_PATH", fake_path)
    update_snapshot()

    stored = json.loads(fake_path.read_text())
    # Remove a field from stored to simulate "fresh has it, stored doesn't".
    removed_key = "fair_price"
    assert removed_key in stored["StockSummary"]
    del stored["StockSummary"][removed_key]
    fake_path.write_text(json.dumps(stored, indent=2) + "\n")

    ok, diff = check_snapshot()
    assert ok is False
    assert "ADDED" in diff
    assert removed_key in diff
    assert "[StockSummary]" in diff


def test_C2_removed_field_in_fresh_diff_format(tmp_path, monkeypatch):
    """If a field is in stored but not fresh, diff says 'REMOVED' + name."""
    fake_path = tmp_path / "schema-snapshot.json"
    monkeypatch.setattr(schema_check, "SNAPSHOT_PATH", fake_path)
    update_snapshot()

    stored = json.loads(fake_path.read_text())
    stored["StockSummary"]["__phantom__"] = {
        "type": "str", "required": False, "default": None,
    }
    fake_path.write_text(json.dumps(stored, indent=2) + "\n")

    ok, diff = check_snapshot()
    assert ok is False
    assert "REMOVED" in diff
    assert "__phantom__" in diff


def test_C3_type_change_diff_shows_old_and_new(tmp_path, monkeypatch):
    """If a field's type changes, diff shows both stored and fresh values."""
    fake_path = tmp_path / "schema-snapshot.json"
    monkeypatch.setattr(schema_check, "SNAPSHOT_PATH", fake_path)
    update_snapshot()

    stored = json.loads(fake_path.read_text())
    stored["StockSummary"]["fair_price"] = {
        "type": "int | None",  # the live schema has float | None
        "required": False,
        "default": None,
    }
    fake_path.write_text(json.dumps(stored, indent=2) + "\n")

    ok, diff = check_snapshot()
    assert ok is False
    assert "CHANGED" in diff
    assert "fair_price" in diff
    assert "stored" in diff
    assert "fresh" in diff
    # Both type strings should appear in the diff so the reader sees what
    # changed.
    assert "int | None" in diff
    assert "float | None" in diff


# ---------------------------------------------------------------------------
# D. CLI integration
# ---------------------------------------------------------------------------

def test_D1_update_snapshot_cli_writes_file(tmp_path, monkeypatch, capsys):
    fake_path = tmp_path / "schema-snapshot.json"
    monkeypatch.setattr(schema_check, "SNAPSHOT_PATH", fake_path)

    rc = main(["--update-snapshot"])
    assert rc == 0
    assert fake_path.exists()
    out = capsys.readouterr().out
    assert "Snapshot updated" in out


def test_D2_check_cli_in_sync_returns_zero(tmp_path, monkeypatch, capsys):
    fake_path = tmp_path / "schema-snapshot.json"
    monkeypatch.setattr(schema_check, "SNAPSHOT_PATH", fake_path)
    update_snapshot()

    rc = main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "in sync" in out


def test_D3_check_cli_drift_returns_one_with_resolution_text(
    tmp_path, monkeypatch, capsys,
):
    fake_path = tmp_path / "schema-snapshot.json"
    monkeypatch.setattr(schema_check, "SNAPSHOT_PATH", fake_path)
    update_snapshot()
    stored = json.loads(fake_path.read_text())
    del stored["StockSummary"]["fair_price"]
    fake_path.write_text(json.dumps(stored, indent=2) + "\n")

    rc = main([])
    assert rc == 1
    out = capsys.readouterr().out
    assert "drift detected" in out
    assert "Resolution" in out
    assert "--update-snapshot" in out


def test_D4_missing_snapshot_file_returns_one(tmp_path, monkeypatch):
    """When the snapshot file doesn't exist, check_snapshot() returns
    (False, helpful message) and the CLI exits 1."""
    fake_path = tmp_path / "does_not_exist.json"
    monkeypatch.setattr(schema_check, "SNAPSHOT_PATH", fake_path)
    ok, diff = check_snapshot()
    assert ok is False
    assert "does not exist" in diff
    assert "--update-snapshot" in diff


# ---------------------------------------------------------------------------
# E. Critical fields present (regression guard)
# ---------------------------------------------------------------------------

def test_E1_stock_summary_has_fair_price_field():
    snap = generate_snapshot()
    assert "fair_price" in snap["StockSummary"]
    assert snap["StockSummary"]["fair_price"]["type"] == "float | None"


def test_E2_stock_detail_has_phase3c_fields():
    snap = generate_snapshot()
    sd = snap["StockDetail"]
    for field in (
        "fair_price",
        "valuation_warnings",
        "has_history",
        "tangible_book_value",
    ):
        assert field in sd, f"StockDetail missing {field}"

    # Sanity-check the type strings for each.
    assert sd["fair_price"]["type"] == "dict | None"
    assert sd["valuation_warnings"]["type"] == "list[str]"
    assert sd["has_history"]["type"] == "bool"
    assert sd["tangible_book_value"]["type"] == "float | None"


def test_E3_metadata_has_mos_trailing_ic_smoke():
    snap = generate_snapshot()
    assert "mos_trailing_ic_smoke" in snap["Metadata"]
    assert snap["Metadata"]["mos_trailing_ic_smoke"]["type"] == "float | None"


# ---------------------------------------------------------------------------
# F. Production snapshot is in sync (canary against committed file)
# ---------------------------------------------------------------------------

def test_F1_committed_snapshot_matches_live_schemas():
    """The committed schema-snapshot.json must match the live Pydantic
    schemas. This is the same check CI runs, but inside pytest so a
    test-only invocation also catches drift early."""
    ok, diff = check_snapshot()
    assert ok, f"Committed snapshot is out of sync. Diff:\n{diff}"


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

def test_default_factory_normalization_is_factory_prefixed():
    """Field with default_factory=list serializes as '<factory:list>'."""
    snap = generate_snapshot()
    assert snap["StockSummary"]["risk_flags"]["default"] == "<factory:list>"


def test_required_field_serializes_as_sentinel():
    snap = generate_snapshot()
    assert snap["StockSummary"]["ticker"]["default"] == "<required>"
    assert snap["StockSummary"]["ticker"]["required"] is True


def test_invalid_json_in_snapshot_returns_drift_with_message(
    tmp_path, monkeypatch,
):
    """If the snapshot file exists but is corrupt JSON, check_snapshot
    returns (False, <message>) rather than raising."""
    fake_path = tmp_path / "schema-snapshot.json"
    fake_path.write_text("{ this is not json")
    monkeypatch.setattr(schema_check, "SNAPSHOT_PATH", fake_path)
    ok, diff = check_snapshot()
    assert ok is False
    assert "not valid JSON" in diff


@pytest.mark.parametrize("flag", ["", "--update-snapshot"])
def test_main_does_not_crash(flag, tmp_path, monkeypatch):
    """Smoke: both CLI modes return an int exit code (0/1/2)."""
    fake_path = tmp_path / "schema-snapshot.json"
    monkeypatch.setattr(schema_check, "SNAPSHOT_PATH", fake_path)
    if flag == "--update-snapshot":
        rc = main([flag])
    else:
        # Pre-create a snapshot so the no-arg branch has something to read.
        update_snapshot()
        rc = main([])
    assert rc in (0, 1, 2)
