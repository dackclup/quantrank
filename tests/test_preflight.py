"""Offline tests for tools/preflight.py rung-selection logic (error-reduction Layer 2).

Pure-Python; exercises build_ladder()'s diff-aware rung gating without
shelling out to ruff/pytest/tsc.
"""

from __future__ import annotations

from tools.preflight import build_ladder


def _rung(ladder, name):
    return next(r for r in ladder if r.name == name)


def test_always_on_rungs_are_needed_regardless() -> None:
    ladder = build_ladder([], force_all=False)  # empty diff
    for name in ("ruff", "doc-count guard", "model-pin guard", "agent/hook consistency"):
        assert _rung(ladder, name).needed, name


def test_frontend_change_triggers_tsc_not_pytest() -> None:
    ladder = build_ladder(["frontend/components/X.tsx"], force_all=False)
    assert _rung(ladder, "tsc --noEmit").needed
    assert not _rung(ladder, "pytest (offline)").needed
    assert not _rung(ladder, "schema_check").needed


def test_compute_change_triggers_pytest_not_tsc() -> None:
    ladder = build_ladder(["compute/scoring/pillars.py"], force_all=False)
    assert _rung(ladder, "pytest (offline)").needed
    assert not _rung(ladder, "tsc --noEmit").needed


def test_schema_file_triggers_schema_check() -> None:
    for f in (
        "compute/output/schemas.py",
        "frontend/lib/types.ts",
        "frontend/lib/schema-snapshot.json",
    ):
        ladder = build_ladder([f], force_all=False)
        assert _rung(ladder, "schema_check").needed, f


def test_docs_only_change_skips_heavy_rungs() -> None:
    ladder = build_ladder(["CLAUDE.md"], force_all=False)
    assert not _rung(ladder, "pytest (offline)").needed
    assert not _rung(ladder, "tsc --noEmit").needed
    assert not _rung(ladder, "schema_check").needed
    # but the cheap guards still run
    assert _rung(ladder, "agent/hook consistency").needed


def test_unknown_diff_runs_all_conditional_rungs_failsafe() -> None:
    ladder = build_ladder(None, force_all=False)
    for name in ("schema_check", "pytest (offline)", "tsc --noEmit"):
        assert _rung(ladder, name).needed, name


def test_force_all_runs_everything() -> None:
    ladder = build_ladder(["CLAUDE.md"], force_all=True)
    for r in ladder:
        assert r.needed, r.name
