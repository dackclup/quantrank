"""Error-reduction Layer 1 — deterministic defense-layer flag-count guard.

Asserts that the **declared defense-layer counts** stated in the
contributor-facing docs (CLAUDE.md · docs/METHODOLOGY.md) match the
**actual registry ground truth** in ``compute/warehouse/flag_registry.py``.
Exits non-zero with the offending file + line + claimed-vs-actual so the
drift surfaces in CI before review.

Why this exists: the defense-layer count is a recurring, fully-mechanical
drift class. An LLM review caught the same stale count three separate ways
across one PR (#641): §Layout said "7 active vetoes", §Scoring said "9",
METHODOLOGY said "7" — while the registry carried 10 active vetoes
(``KNOWN_RISK_FLAGS``) + 28 annotates (``KNOWN_VALUATION_WARNINGS``) = 38
declared flags. Root cause: three *different* gates with three different
membership sets are easy to conflate —
  - ``KNOWN_RISK_FLAGS`` (10)        → the Top-5 veto gate (main.py:1998);
                                        THIS is the canonical "active veto".
  - ``ACTIVE_VETO_FLAGS`` (weights)  → the backtest AI-pick basket gate only.
  - ``_CAUTIOUS_FORCING_RISK`` (rec) → the ``recommendation="cautious"`` label only.
The headline count is defined by the Top-5 gate, so the active-veto count
== ``len(KNOWN_RISK_FLAGS)``. An LLM catching a mechanical fact is
probabilistic — it can miss; a script catches it every time, for free,
forever (the project's "determinize the determinizable" principle — see
docs/LESSONS_LEARNED.md "count-drift").

Sibling of ``check_agent_hook_consistency.py`` (agent/hook/flow counts) and
``check_doc_test_counts.py`` (bans hardcoded *test* counts). This guard reads
the registry — NO count literal lives in this file, so adding a flag and
updating the doc PASSES automatically.

Scope notes:
  - Ground truth = the two registry frozensets. Active vetoes ==
    ``len(KNOWN_RISK_FLAGS)``; annotates == ``len(KNOWN_VALUATION_WARNINGS)``;
    declared total == their sum.
  - Only CURRENT-STATE headline phrases are anchored (precise regexes), so
    chronological-log prose ("defense UNCHANGED at 36" snapshots in
    PHASE_STATUS / code comments) does NOT false-positive.
  - The parenthetical "~28 emit" is a RUNTIME firing fact, not a
    registry-derivable count, so it is intentionally left as prose.
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from compute.warehouse.flag_registry import (  # noqa: E402
    KNOWN_RISK_FLAGS,
    KNOWN_VALUATION_WARNINGS,
)


@dataclass
class GroundTruth:
    n_vetoes: int
    n_annotates: int
    n_declared: int


def compute_ground_truth() -> GroundTruth:
    n_vetoes = len(KNOWN_RISK_FLAGS)
    n_annotates = len(KNOWN_VALUATION_WARNINGS)
    return GroundTruth(
        n_vetoes=n_vetoes,
        n_annotates=n_annotates,
        n_declared=n_vetoes + n_annotates,
    )


@dataclass
class Anchor:
    """A canonical doc phrase whose embedded number must equal ground truth."""
    file: str
    pattern: str          # one capture group = the claimed integer
    truth_key: str        # attribute on GroundTruth
    label: str


# Precise anchors — each regex is specific enough that chronological-log
# prose does not false-positive. Capture group 1 is always the integer.
ANCHORS: tuple[Anchor, ...] = (
    # --- declared total ---
    Anchor("CLAUDE.md", r"\*\*(\d+) declared boolean flags\*\*", "n_declared", "CLAUDE declared total"),
    Anchor("docs/METHODOLOGY.md", r"\*\*(\d+) declared boolean flags\*\*", "n_declared", "METHODOLOGY declared total"),
    # --- active vetoes ---
    Anchor("CLAUDE.md", r"risk overlay \((\d+) active vetoes", "n_vetoes", "CLAUDE §Layout veto count"),
    Anchor("CLAUDE.md", r"\((\d+) active vetoes \+ \d+ annotates", "n_vetoes", "CLAUDE §Scoring veto count"),
    Anchor("docs/METHODOLOGY.md", r"flags\*\* — (\d+) active vetoes", "n_vetoes", "METHODOLOGY veto count"),
    # --- annotates ---
    Anchor("CLAUDE.md", r"\(\d+ active vetoes \+ (\d+) annotates", "n_annotates", "CLAUDE §Scoring annotate count"),
    Anchor("docs/METHODOLOGY.md", r"active vetoes \+ (\d+) annotate", "n_annotates", "METHODOLOGY annotate count"),
)


def check_anchors(truth: GroundTruth) -> list[str]:
    violations: list[str] = []
    for anchor in ANCHORS:
        path = REPO_ROOT / anchor.file
        if not path.exists():
            continue
        expected = getattr(truth, anchor.truth_key)
        rx = re.compile(anchor.pattern)
        for i, line in enumerate(path.read_text().splitlines(), start=1):
            for m in rx.finditer(line):
                claimed = int(m.group(1))
                if claimed != expected:
                    violations.append(
                        f"{anchor.file}:{i}: {anchor.label} says {claimed}, "
                        f"actual is {expected} — {line.strip()[:90]}"
                    )
    return violations


def run() -> tuple[GroundTruth, list[str]]:
    truth = compute_ground_truth()
    return truth, check_anchors(truth)


def main() -> int:
    truth, problems = run()
    if problems:
        print("Defense-layer count consistency violations:")
        for p in problems:
            print(f"  {p}")
        print(
            f"\nGround truth (from flag_registry.py): {truth.n_vetoes} active "
            f"vetoes (KNOWN_RISK_FLAGS) + {truth.n_annotates} annotates "
            f"(KNOWN_VALUATION_WARNINGS) = {truth.n_declared} declared boolean "
            "flags.\nUpdate the stale doc number(s) above to match reality, or "
            "fix the registry if the code is wrong.\n(This guard derives every "
            "number from the registry — see tools/check_defense_layer_counts.py.)"
        )
        return 1
    print(
        f"Defense-layer counts OK — {truth.n_vetoes} active vetoes + "
        f"{truth.n_annotates} annotates = {truth.n_declared} declared boolean flags."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
