"""Error-reduction Layer 2 — one-command verification-ladder runner.

Runs the CLAUDE.md "Verification ladder before any push" as a single
deterministic command so a rung can't be silently skipped:

    ruff → doc-count guard → model-pin guard → agent/hook consistency guard
    → (schemas touched?) schema_check → (compute/tests touched?) pytest
    → (frontend touched?) tsc --noEmit

Cheap deterministic rungs ALWAYS run; the expensive rungs (pytest, tsc) run
only when the diff touches their surface — mirroring the CI paths-filter in
.github/workflows/ci.yml so local preflight ≈ what CI will check. Each rung
reports PASS / FAIL / SKIP; the command exits non-zero if any rung FAILs.

Why this exists: "forgot to run schema_check / ruff before pushing" is a
process-skip error class. A single entrypoint that runs the right rungs for
the current diff removes the human/agent step of remembering the ladder.
This is the LOCAL complement to CI (CI re-runs everything regardless) — it
catches the failure on the laptop, before the push, before review.

Usage:
    python tools/preflight.py            # auto-detect changed surface vs main
    python tools/preflight.py --all      # force every rung (incl. pytest/tsc)
    python tools/preflight.py --base X    # diff against ref X (default: origin/main || main)

NOTE on "enforcement": the harness has no pre-push hook, so this tool is
opt-in (run it / wire it into your own git pre-push). CI is the hard gate;
preflight is the fast local mirror. The pre-push gate agents
(quantrank-reviewer / phase-coordinator) reference it.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Rung:
    name: str
    cmd: list[str]
    needed: bool = True
    cwd: Path = field(default=REPO_ROOT)


def _changed_files(base: str) -> list[str] | None:
    """Files changed vs ``base``…HEAD plus uncommitted + untracked edits.

    Returns ``None`` (NOT ``[]``) when git is unavailable or a ref can't be
    resolved — the caller treats ``None`` as "couldn't determine → run every
    conditional rung, fail-safe". An empty list means a genuine no-op diff.
    """
    files: set[str] = set()
    for args in (
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "diff", "--name-only", "--cached"],
        # untracked new files (not in any diff) — a new tool/test must still
        # trigger its rung.
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        try:
            out = subprocess.run(
                args, cwd=REPO_ROOT, capture_output=True, text=True, check=True
            )
            files.update(line for line in out.stdout.splitlines() if line)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None  # can't determine diff → fail-safe: run everything
    return sorted(files)


def _resolve_base(requested: str | None) -> str:
    if requested:
        return requested
    for ref in ("origin/main", "main"):
        try:
            subprocess.run(
                ["git", "rev-parse", "--verify", ref],
                cwd=REPO_ROOT, capture_output=True, check=True,
            )
            return ref
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return "HEAD"


def build_ladder(changed: list[str] | None, force_all: bool) -> list[Rung]:
    # changed is None → couldn't detect → run conditional rungs to be safe.
    unknown = changed is None
    chg = changed or []

    def touches(*prefixes: str) -> bool:
        return force_all or unknown or any(
            f.startswith(p) for f in chg for p in prefixes
        )

    schemas_touched = force_all or unknown or any(
        f in (
            "compute/output/schemas.py",
            "frontend/lib/types.ts",
            "frontend/lib/schema-snapshot.json",
        )
        for f in chg
    )

    return [
        # --- always-on cheap deterministic rungs ---
        Rung("ruff", ["ruff", "check", "."]),
        Rung("doc-count guard", [sys.executable, "tools/check_doc_test_counts.py"]),
        Rung("model-pin guard", [sys.executable, "tools/check_model_pin.py"]),
        Rung("agent/hook consistency", [sys.executable, "tools/check_agent_hook_consistency.py"]),
        Rung("defense-layer counts", [sys.executable, "tools/check_defense_layer_counts.py"]),
        # --- conditional rungs ---
        Rung(
            "schema_check",
            [sys.executable, "-m", "compute.output.schema_check"],
            needed=schemas_touched,
        ),
        Rung(
            "pytest (offline)",
            [sys.executable, "-m", "pytest", "-q", "-m", "not network"],
            needed=touches("compute/", "tests/", "tools/", "pyproject.toml"),
        ),
        Rung(
            "tsc --noEmit",
            ["npx", "--no", "--", "tsc", "--noEmit"],
            needed=touches("frontend/"),
            cwd=REPO_ROOT / "frontend",
        ),
    ]


def run_rung(rung: Rung) -> tuple[str, str]:
    """Return (status, detail). status ∈ {PASS, FAIL, SKIP, MISSING}."""
    if not rung.needed:
        return "SKIP", "not touched by this diff"
    try:
        proc = subprocess.run(rung.cmd, cwd=rung.cwd, capture_output=True, text=True)
    except FileNotFoundError as exc:
        return "MISSING", f"tool not installed ({exc.filename})"
    if proc.returncode == 0:
        return "PASS", ""
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-6:]
    return "FAIL", "\n      ".join(tail)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the QuantRank verification ladder.")
    parser.add_argument("--all", action="store_true", help="force every rung")
    parser.add_argument("--base", default=None, help="diff base ref (default origin/main || main)")
    args = parser.parse_args(argv)

    base = _resolve_base(args.base)
    # None → couldn't determine the diff → run every conditional rung
    # (fail-safe); [] → genuine no-op diff; list → the changed surface.
    changed = _changed_files(base)

    ladder = build_ladder(changed, args.all)

    print(f"Preflight ladder (base={base}, {len(changed or [])} changed files):\n")
    any_fail = False
    for rung in ladder:
        status, detail = run_rung(rung)
        mark = {"PASS": "✓", "FAIL": "✗", "SKIP": "·", "MISSING": "?"}[status]
        line = f"  {mark} {rung.name:<26} {status}"
        if detail and status in ("FAIL", "MISSING"):
            line += f"\n      {detail}"
        print(line)
        if status == "FAIL":
            any_fail = True

    print()
    if any_fail:
        print("PREFLIGHT FAILED — fix the ✗ rung(s) before pushing.")
        return 1
    print("PREFLIGHT GREEN — ladder clean for the current diff.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
