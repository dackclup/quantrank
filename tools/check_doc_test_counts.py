"""Process Hygiene Item #2 — CI drift guard for hardcoded test counts.

Scans the canonical contributor-facing docs (``CLAUDE.md``,
``AGENTS.md``) for hardcoded test-count claims like ``"831 offline +
17 @network"``. Exits non-zero with the offending file + line + text
so PR authors see the violation in CI before pytest even runs.

Why this exists: doc drift after the 2026-05-19 PR wave found 3 stale
hardcoded counts (831, 906, 856) all wrong against the real ~959
offline. Manual maintenance of derived data isn't scalable — test
count moves every PR. Refer to "CI build artifact for current count"
instead, and let this guard keep new hardcoded counts out.

Scope notes:

- ``PHASE_STATUS.md`` / ``SKILL.md`` / ``WORKFLOW.md`` are
  chronological logs. Historical entries like
  ``"Phase 4i shipped 936 offline + 18 @network"`` are legitimate
  snapshots-in-time and intentionally NOT scanned by this guard.
- The regex matches both spelled-out (``offline``) and backtick-
  wrapped (``` `@network` ```) variants. Future drift patterns can be
  added without changing the call site.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Matches the canonical "N offline + M @network" drift pattern.
# Case-insensitive; tolerates flexible whitespace + optional backticks
# around ``@network``. Examples that fire:
#   "831 offline + 17 @network"
#   "Test suite: 906 offline + 19 `@network`"
#   "856 offline + 17 `@network` gated"
PATTERN = re.compile(
    r"\d+\s+offline\s*\+\s*\d+\s+`?@network`?",
    re.IGNORECASE,
)

# Canonical contributor-facing docs that should NEVER carry hardcoded
# test counts. Chronological logs (PHASE_STATUS, SKILL, WORKFLOW) are
# deliberately excluded — their historical entries are point-in-time
# snapshots, not derived data.
GUARDED_FILES: tuple[str, ...] = (
    "CLAUDE.md",
    "AGENTS.md",
)


def find_violations() -> list[str]:
    """Return a list of ``"<file>:<line>: <text>"`` violation strings.

    Empty list when all guarded files are clean. Missing files are
    silently skipped — a contributor running this in a partial checkout
    shouldn't be blocked.
    """
    violations: list[str] = []
    for fname in GUARDED_FILES:
        path = REPO_ROOT / fname
        if not path.exists():
            continue
        for i, line in enumerate(path.read_text().splitlines(), start=1):
            if PATTERN.search(line):
                violations.append(f"{fname}:{i}: {line.strip()}")
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print("Hardcoded test counts found in canonical docs:")
        for v in violations:
            print(f"  {v}")
        print(
            "\nReplace with a reference to the CI build artifact "
            "(e.g., 'see CI for current count').\n"
            "Test counts drift every PR — see Process Hygiene Item #2 "
            "(epic #125)."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
