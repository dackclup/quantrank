"""Process Hygiene Item #6 — preflight check for cross-session branch collisions.

Lists active ``claude/*`` branches and recent commits merged into
``origin/main`` so a worker session can spot scope overlap BEFORE
opening a duplicate PR. Motivated by PR #123 (closed 2026-05-19): a
worker session opened a Phase 4j+4k duplicate of the already-merged
PRs #119+#121 and got closed without merging after 100% wasted effort.

USAGE
=====
    python tools/check_branch_collisions.py [KEYWORD ...]

When KEYWORDs are passed, the script flags any branch / recent
commit whose name or message contains a keyword (case-insensitive
substring). Without KEYWORDs the script lists data only.

Always returns exit 0 — informational only. The calling Claude Code
session (or contributor) decides whether to proceed based on the
warnings printed.

DESIGN NOTES
============
- Git-only data sources (``git ls-remote`` + ``git log``). No
  ``gh`` CLI dependency — works in the QuantRank Claude Code Web
  environment where ``gh`` is unavailable, and on any contributor
  machine with bare git.
- 48-hour window for recent commits — matches the typical worker-
  session ↔ main-session handoff cadence; long enough to catch
  duplicate work, short enough not to bury the output in noise.
- No network access beyond the existing ``origin`` remote.
"""
from __future__ import annotations

import subprocess
import sys

WINDOW_HOURS: int = 48
GIT_TIMEOUT_SECONDS: int = 30


def _git(args: list[str]) -> str:
    """Run a git command, return stdout. Returns "" on any failure so
    the script never crashes on a partial checkout / missing remote."""
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def active_claude_branches() -> list[str]:
    """Return sorted ``claude/<name>`` branch names from ``origin``.

    Queries the remote via ``git ls-remote`` (no fetch needed). Empty
    list when the remote has no ``claude/*`` branches OR when ``git``
    isn't available.
    """
    out = _git(["ls-remote", "origin", "refs/heads/claude/*"])
    branches: list[str] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        ref = parts[1].strip()
        prefix = "refs/heads/"
        if ref.startswith(prefix):
            branches.append(ref[len(prefix):])
    return sorted(branches)


def recent_main_commits(window_hours: int = WINDOW_HOURS) -> list[str]:
    """Return one-line summaries of commits merged into ``origin/main``
    within the last ``window_hours``. Squash-merged PRs surface here
    with the PR number embedded in the message (``"feat(x): blah (#NNN)"``).
    """
    out = _git(
        [
            "log",
            f"--since={window_hours} hours ago",
            "--oneline",
            "--no-merges",
            "origin/main",
        ]
    )
    return [line for line in out.splitlines() if line.strip()]


def keyword_matches(text: str, keywords: list[str]) -> list[str]:
    """Return the keywords (preserving caller's case) that occur as
    case-insensitive substrings of ``text``. Empty list when no match."""
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


def _format_with_warning(text: str, matches: list[str]) -> str:
    """Render a line + optional warning suffix listing matched keywords."""
    if matches:
        return f"  {text}  ⚠️  match: {', '.join(matches)}"
    return f"  {text}"


def main(argv: list[str]) -> int:
    keywords = argv[1:]

    branches = active_claude_branches()
    print(f"Active claude/* branches ({len(branches)}):")
    if not branches:
        print("  (none)")
    for branch in branches:
        print(_format_with_warning(branch, keyword_matches(branch, keywords)))

    recent = recent_main_commits()
    print(
        f"\nRecently merged commits on origin/main "
        f"(last {WINDOW_HOURS}h, {len(recent)}):"
    )
    if not recent:
        print("  (none)")
    for line in recent:
        print(_format_with_warning(line, keyword_matches(line, keywords)))

    if keywords:
        warn_count = sum(1 for b in branches if keyword_matches(b, keywords))
        warn_count += sum(1 for line in recent if keyword_matches(line, keywords))
        print()
        if warn_count:
            print(
                f"⚠️  {warn_count} potential scope collision(s) found for "
                f"keyword(s): {keywords}. Review before opening a new PR."
            )
            print(
                "    Reference precedent: PR #123 (closed as duplicate of "
                "#119+#121) wasted 100% effort because the worker session "
                "skipped this check."
            )
        else:
            print(f"No scope collisions detected for keyword(s): {keywords}.")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
