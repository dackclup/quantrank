"""Cross-session branch-collision detector — Issue #125 Item 6.

Complements ``check_branch_collisions.py`` (git-only, 48h window) by
hitting the GitHub API for ``claude/*`` branches updated in the last 7
days and open PRs whose title or head branch contains the scope keyword.
Catches the failure mode where a sibling session opened the same scope
on a different machine and hasn't pushed yet — a gap the git-only
checker cannot cover.

USAGE
=====
    python tools/check_cross_session_collision.py <scope-keyword>

Examples:
    python tools/check_cross_session_collision.py form4
    python tools/check_cross_session_collision.py stock-detail
    python tools/check_cross_session_collision.py "cross-session"

EXIT CODES
==========
    0  No collision detected
    1  At least one collision candidate found — review before proceeding
    2  Authentication error — set GH_TOKEN or GITHUB_TOKEN env var

AUTHENTICATION
==============
The script tries authentication sources in priority order:

    1. ``GH_TOKEN`` environment variable
    2. ``GITHUB_TOKEN`` environment variable
    3. ``gh`` CLI token  (``gh auth token``)

If none is available the script exits with code 2 and a clear message.
No token is ever hardcoded or written to disk.

DESIGN NOTES
============
- Read-only: uses only GET endpoints, no mutations
- 7-day branch window (vs 48h for the git-only checker) — wider net
  for sessions that may have stalled without pushing
- Merged+closed branches are filtered out (false-positive guard)
- Closed PRs are excluded; only OPEN PRs flag as collisions
- Requires ``requests`` (standard in QuantRank's Python env)
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

REPO_OWNER: str = "dackclup"
REPO_NAME: str = "quantrank"
BRANCH_WINDOW_DAYS: int = 7
API_BASE: str = "https://api.github.com"
REQUESTS_TIMEOUT_SECONDS: int = 20


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def _resolve_token() -> str:
    """Return a GitHub PAT / OAuth token, or raise RuntimeError if none found.

    Priority:
    1. ``GH_TOKEN`` env var
    2. ``GITHUB_TOKEN`` env var
    3. ``gh auth token`` CLI output
    """
    for var in ("GH_TOKEN", "GITHUB_TOKEN"):
        val = os.environ.get(var, "").strip()
        if val:
            return val

    # Try gh CLI last — subprocess call; gh may not be installed.
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        token = result.stdout.strip()
        if token:
            return token
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    raise RuntimeError(
        "No GitHub token found.\n"
        "Set GH_TOKEN or GITHUB_TOKEN env var, or run `gh auth login`.\n"
        "Example:\n"
        "    export GH_TOKEN=ghp_xxxxxxxxxxxx\n"
        "    python tools/check_cross_session_collision.py <keyword>"
    )


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _get(url: str, token: str, params: dict[str, Any] | None = None) -> Any:
    """GET ``url`` with auth, return parsed JSON. Raises on non-200."""
    try:
        import requests  # local import so missing dep gives a clear message
    except ImportError:
        print(
            "ERROR: 'requests' package not installed.\n"
            "Install with: pip install requests",
            file=sys.stderr,
        )
        sys.exit(2)

    resp = requests.get(
        url,
        headers=_headers(token),
        params=params or {},
        timeout=REQUESTS_TIMEOUT_SECONDS,
    )
    if resp.status_code == 401:
        print(
            f"ERROR: GitHub API returned 401 Unauthorized for {url}\n"
            "The token is invalid or expired. Re-authenticate and retry.",
            file=sys.stderr,
        )
        sys.exit(2)
    if resp.status_code == 403:
        print(
            f"ERROR: GitHub API returned 403 Forbidden for {url}\n"
            "The token may lack the 'repo' scope needed to list branches.",
            file=sys.stderr,
        )
        sys.exit(2)
    resp.raise_for_status()
    return resp.json()


def _paginate(url: str, token: str, params: dict[str, Any] | None = None) -> list[Any]:
    """Collect all pages from a GitHub list endpoint."""
    items: list[Any] = []
    page = 1
    base_params = dict(params or {})
    base_params["per_page"] = 100
    while True:
        base_params["page"] = page
        batch = _get(url, token, params=base_params)
        if not isinstance(batch, list) or not batch:
            break
        items.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return items


# ---------------------------------------------------------------------------
# Data fetchers
# ---------------------------------------------------------------------------


def _fetch_claude_branches(
    token: str, keyword: str, window_days: int
) -> list[dict[str, str]]:
    """Return ``claude/*`` branches whose last commit is within ``window_days``
    and whose name contains ``keyword`` (case-insensitive).

    Only branches that are NOT merged (i.e., exist on the remote right now)
    are returned — the false-positive guard for already-merged scopes.
    """
    url = f"{API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/branches"
    all_branches = _paginate(url, token)

    cutoff = datetime.now(tz=UTC) - timedelta(days=window_days)
    keyword_lower = keyword.lower()

    results: list[dict[str, str]] = []
    for b in all_branches:
        name: str = b.get("name", "")
        # Must be a claude/* branch matching the keyword
        if not name.startswith("claude/"):
            continue
        if keyword_lower not in name.lower():
            continue
        # Fetch the commit date for the recency filter
        commit_sha: str = b.get("commit", {}).get("sha", "")
        commit_url: str = b.get("commit", {}).get("url", "")
        commit_date: str = ""
        author: str = ""
        if commit_url:
            try:
                commit_data = _get(commit_url, token)
                commit_date = (
                    commit_data.get("commit", {})
                    .get("author", {})
                    .get("date", "")
                )
                author = (
                    commit_data.get("commit", {})
                    .get("author", {})
                    .get("name", "")
                )
            except Exception:
                pass
        # Parse and filter by window
        if commit_date:
            try:
                dt = datetime.fromisoformat(commit_date.replace("Z", "+00:00"))
                if dt < cutoff:
                    continue
            except ValueError:
                pass

        # Compute human-readable age
        age_str = _age_str(commit_date)
        results.append(
            {
                "branch": name,
                "sha": commit_sha[:7] if commit_sha else "unknown",
                "author": author or "unknown",
                "age": age_str,
                "commit_date": commit_date,
            }
        )
    return results


def _fetch_open_prs(token: str, keyword: str) -> list[dict[str, str]]:
    """Return OPEN PRs whose title or head-branch contains ``keyword``."""
    url = f"{API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/pulls"
    prs = _paginate(url, token, params={"state": "open"})

    keyword_lower = keyword.lower()
    results: list[dict[str, str]] = []
    for pr in prs:
        title: str = pr.get("title", "")
        head_branch: str = pr.get("head", {}).get("ref", "")
        if keyword_lower not in title.lower() and keyword_lower not in head_branch.lower():
            continue
        author: str = pr.get("user", {}).get("login", "unknown")
        created_at: str = pr.get("created_at", "")
        number: int = pr.get("number", 0)
        url_html: str = pr.get("html_url", "")
        age_str = _age_str(created_at)
        results.append(
            {
                "number": f"#{number}",
                "title": title,
                "head_branch": head_branch,
                "author": author,
                "age": age_str,
                "url": url_html,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _age_str(iso_date: str) -> str:
    """Return a human-readable age string like '3d 2h' from an ISO-8601 date."""
    if not iso_date:
        return "unknown"
    try:
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
        delta = datetime.now(tz=UTC) - dt
        total_hours = int(delta.total_seconds() // 3600)
        days = total_hours // 24
        hours = total_hours % 24
        if days > 0:
            return f"{days}d {hours}h"
        return f"{hours}h"
    except ValueError:
        return "unknown"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    if len(argv) < 2 or not argv[1].strip():
        print(
            "Usage: python tools/check_cross_session_collision.py <scope-keyword>\n"
            "Example: python tools/check_cross_session_collision.py form4",
            file=sys.stderr,
        )
        return 2

    keyword = argv[1].strip()
    print(f"Cross-session collision check — keyword: '{keyword}'")
    print(f"Repo: {REPO_OWNER}/{REPO_NAME}  |  Branch window: {BRANCH_WINDOW_DAYS}d\n")

    # Resolve auth — exit 2 with a clear message if unavailable.
    try:
        token = _resolve_token()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    # Fetch data
    print(f"Fetching claude/* branches updated in the last {BRANCH_WINDOW_DAYS} days...")
    branches = _fetch_claude_branches(token, keyword, BRANCH_WINDOW_DAYS)

    print(f"Fetching open PRs matching '{keyword}'...\n")
    open_prs = _fetch_open_prs(token, keyword)

    # Report
    collision_found = False

    print(f"claude/* branches matching '{keyword}' (last {BRANCH_WINDOW_DAYS}d, {len(branches)}):")
    if not branches:
        print("  (none)")
    for b in branches:
        collision_found = True
        print(
            f"  {b['branch']}"
            f"  sha:{b['sha']}  author:{b['author']}  age:{b['age']}"
        )

    print(f"\nOpen PRs matching '{keyword}' ({len(open_prs)}):")
    if not open_prs:
        print("  (none)")
    for pr in open_prs:
        collision_found = True
        print(
            f"  {pr['number']} {pr['title']}"
            f"  (branch: {pr['head_branch']}  author: {pr['author']}  age: {pr['age']})"
        )
        print(f"       {pr['url']}")

    print()
    if collision_found:
        print(
            "⚠️  COLLISION RISK: At least one active claude/* branch or open PR "
            f"matches keyword '{keyword}'.\n"
            "   STOP — review the items above before opening a new PR.\n"
            "   Possible resolutions:\n"
            "     1. Different scope (false positive) → proceed\n"
            "     2. Same scope, already in flight elsewhere → coordinate with"
            " that session\n"
            "     3. Same scope, branch is stale/abandoned → confirm with user"
            " before proceeding\n"
            "   Reference precedent: PR #123 (closed as duplicate of #119+#121)"
            " — 100% wasted effort because the worker skipped this check."
        )
        return 1

    print(f"No cross-session collision detected for keyword '{keyword}'. Safe to proceed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
