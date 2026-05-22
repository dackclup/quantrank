---
name: cross-session-collision-check
description: >
  GitHub API preflight that detects claude/* branches opened by a sibling
  session on a different machine within the last 7 days. TRIGGER before
  opening any new claude/* branch from a handoff prompt, or when a handoff
  prompt references a scope keyword (issue #N, feature name, phase label)
  that hasn't been cross-checked against GitHub-hosted branches. SKIP for
  doc-only chores that can't collide on substance, for second-and-later
  iterations within the same already-checked session, or when the user has
  explicitly authorized parallel work on overlapping scope.
---

# cross-session-collision-check

Companion to [`branch-collision-check`](../branch-collision-check/SKILL.md).
That skill uses git-only data sources (48h window, local remote cache) and
works without any GitHub token. This skill hits the GitHub API directly
(7-day window) to surface branches opened by sibling sessions on OTHER
machines that haven't pushed recently — the gap the git-only checker cannot
cover. The two skills complement each other and both run in Mode A of
`phase-coordinator`.

## Motivation

PR #123 (2026-05-19, closed without merging): a worker session opened a
Phase 4j + 4k duplicate of already-merged PRs #119 + #121 because it
never checked GitHub for in-flight `claude/*` branches. 100% wasted effort.
Issue #125 Item 6 tracked the structural fix.

## Trigger conditions

Run **before** any of the following:

- Creating a new `claude/*` branch from a handoff prompt
- The first non-trivial file edit on a fresh worker session whose scope
  has not been cross-checked against GitHub-hosted branches
- A handoff prompt containing a scope keyword (issue number, feature name,
  phase label) that could overlap with an in-flight sibling session

## Skip conditions

- Doc-only chores whose substance can't collide (single-comment edits, typo
  fixes, README polish)
- Iteration #2+ within the same worker session — the first check already
  covered the relevant scope
- User has explicitly authorized parallel work on overlapping scope ("yes I
  know branch X is open — also start this from the worker side")
- `GH_TOKEN` / `GITHUB_TOKEN` / `gh` CLI unavailable AND the user confirms
  they accept the risk of skipping the GitHub-API check

## Invocation

```bash
# <scope-keyword> is a case-insensitive substring matched against
# claude/* branch names AND open PR titles / head-branches.
python tools/check_cross_session_collision.py <scope-keyword>

# Examples:
python tools/check_cross_session_collision.py form4
python tools/check_cross_session_collision.py "cross-session"
python tools/check_cross_session_collision.py sector
```

## Authentication

The script tries these sources in order:

1. `GH_TOKEN` environment variable
2. `GITHUB_TOKEN` environment variable
3. `gh auth token` (gh CLI)

If none is available, the script exits with code 2 and prints a clear
message. **Do not hardcode any token.** If neither source is available in
the current session, inform the user and ask them to set `GH_TOKEN` or run
`gh auth login`, or confirm they want to proceed without the GitHub-API
check (accepting the PR #123 risk).

## False-positive guard

The script **only** reports:

- `claude/*` branches that currently exist on GitHub (i.e., not yet
  deleted / merged) AND were updated within the last 7 days AND whose name
  contains the keyword
- Open PRs (state: `open`) whose title or head-branch contains the keyword

Branches that were merged and deleted, or PRs that are closed, are
automatically excluded. A branch like `claude/stock-detail-auditor-agent-*`
that was merged via PR #175 and then deleted will NOT appear as a
false-positive collision even if the keyword "stock-detail" is used.

## Sample output — clean run

```
Cross-session collision check — keyword: 'form4'
Repo: dackclup/quantrank  |  Branch window: 7d

Fetching claude/* branches updated in the last 7 days...
Fetching open PRs matching 'form4'...

claude/* branches matching 'form4' (last 7d, 0):
  (none)

Open PRs matching 'form4' (0):
  (none)

No cross-session collision detected for keyword 'form4'. Safe to proceed.
```

## Sample output — collision detected

```
Cross-session collision check — keyword: 'sector'
Repo: dackclup/quantrank  |  Branch window: 7d

Fetching claude/* branches updated in the last 7 days...
Fetching open PRs matching 'sector'...

claude/* branches matching 'sector' (last 7d, 1):
  claude/sector-exposure-flag-i201-Abc12  sha:a1b2c3d  author:Claude  age:5h

Open PRs matching 'sector' (0):
  (none)

⚠️  COLLISION RISK: At least one active claude/* branch or open PR matches keyword 'sector'.
   STOP — review the items above before opening a new PR.
   Possible resolutions:
     1. Different scope (false positive) → proceed
     2. Same scope, already in flight elsewhere → coordinate with that session
     3. Same scope, branch is stale/abandoned → confirm with user before proceeding
   Reference precedent: PR #123 (closed as duplicate of #119+#121) — 100% wasted effort
   because the worker skipped this check.
```

## Output interpretation

- **Exit 0, no `⚠️` lines** → proceed with the worker task as normal.
- **Exit 1, `⚠️` line** → STOP. Ask the user whether the matched branch /
  PR represents the same scope. Possible resolutions:
  1. Different scope (false positive) → proceed
  2. Same scope, already in flight elsewhere → coordinate (rebase, wait, or
     scope this PR as a follow-up)
  3. Same scope, branch stale/abandoned → get user confirmation before
     proceeding
- **Exit 2** → authentication error. Set `GH_TOKEN` or run `gh auth login`.

## Relationship to `branch-collision-check`

| | `branch-collision-check` | `cross-session-collision-check` |
|---|---|---|
| Data source | git ls-remote + git log | GitHub REST API |
| Window | 48h | 7 days |
| Auth required | No | Yes (GH_TOKEN / gh CLI) |
| Catches local-only branches | Yes (via origin remote) | Only pushed branches |
| Catches sibling machines | No | Yes (any pushed branch) |
| Exit code on collision | Always 0 (informational) | 1 (actionable signal) |

Both skills run in `phase-coordinator` Mode A — they cover complementary
failure modes and neither replaces the other.

## Constraints + design notes

- Pure read-only — uses only GitHub GET endpoints, no mutations
- `requests` library required (already a transitive dep in QuantRank's env)
- Closed / merged PRs are excluded; only open PRs flag as collisions
- Merged-and-deleted branches are excluded from the GitHub branch list
  automatically (GitHub API returns only existing branches)
