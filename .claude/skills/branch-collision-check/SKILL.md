---
name: branch-collision-check
description: Preflight for worker sessions handed off via prompt: list active claude/* branches + last-48h merged PRs and flag scope-keyword collisions before a duplicate PR reaches Draft. Pure read-only (git ls-remote + git log; no GitHub API). TRIGGER: before creating a claude/* branch from a handoff, before the first non-trivial edit in a fresh worker session, or when a Phase / issue / Item number hasn't been cross-checked against open PRs.
---

# branch-collision-check

Read-only preflight check that surfaces in-flight scope on QuantRank
before a worker session writes any code. Designed to catch the PR #123
failure mode: a worker session worked Phase 4j + Phase 4k on the
`claude/resume-quantrank-phase-4.5-Zh0pO` branch in parallel with the
main session that shipped the same work directly via PRs #119 + #121,
producing a duplicate Draft that closed with 100% wasted effort.

## Trigger conditions

Run **before** any of the following:

- Creating a new `claude/*` branch from a handoff prompt
- The first non-trivial file edit on a fresh worker session
- Acting on a user message mentioning a Phase number (e.g.,
  "Phase 4j", "Phase 4h.2 Part 2"), an issue number (e.g., "#116",
  "#126"), or an epic Item identifier ("Process Hygiene Item #N")
  that hasn't been cross-checked against open PRs
- A handoff prompt containing "spawn a worker session", "open this
  from the worker side", "in parallel with X", or equivalent

## Skip conditions

- Doc-only chores whose substance can't collide (single-comment
  edits, typo fixes, README polish)
- Iteration #2+ within the same worker session — the first check
  already covered the relevant scope
- User has explicitly authorized parallel work on overlapping scope
  ("yes I know #119 shipped — also open this from the worker side")

## Invocation

```bash
# Bare invocation — list state, no warning logic.
python tools/check_branch_collisions.py

# With scope keywords — flag any branch/commit whose name/message
# matches case-insensitively. Pass each keyword as a separate arg.
python tools/check_branch_collisions.py "Phase 4j" "Alpha158" "issue 116"
```

## Sample output

Clean run with no keyword collision:

```
Active claude/* branches (1):
  claude/resume-quantrank-phase-4.5-Zh0pO

Recently merged commits on origin/main (last 48h, 7):
  dcc853ac docs(workflow): Codify observability-before-wiring pattern (#129)
  0209e4c3 chore(docs): Strip hardcoded test counts + CI drift guard (#128)
  780650f8 test(features): Add Hypothesis property-based tests for data-shape invariants (#127)
  ...
```

Warning run — caller passed `"Alpha158"` knowing they're about to
spawn a Qlib feature-set scout, script flags the prior PR #119:

```
Recently merged commits on origin/main (last 48h, 7):
  dcc853ac docs(workflow): Codify observability-before-wiring pattern (#129)
  ...
  f0ade65b feat(ingest): Qlib scout — pyqlib MIT install + Alpha158 158-feature manifest + 6 offline tests (#119)  ⚠️  match: Alpha158

⚠️  1 potential scope collision(s) found for keyword(s): ['Alpha158'].
    Review before opening a new PR.
    Reference precedent: PR #123 (closed as duplicate of #119+#121)
    wasted 100% effort because the worker session skipped this check.
```

## Output interpretation

- **No `⚠️` lines** → proceed with the worker task as normal.
- **One or more `⚠️` lines** → STOP. Ask the user whether the
  matched PR / branch represents the same scope. Possible
  resolutions:
  1. Different scope (false positive) → proceed
  2. Same scope, already shipped → abort; tell the user the work
     is already merged in PR #NNN
  3. Same scope, in-flight elsewhere → ask the user how to
     coordinate (rebase onto the in-flight branch, wait, or scope
     this PR to a follow-up)

## Constraints + design notes

- Pure read-only — no destructive git ops, no branch creation, no
  push, no GitHub API mutation
- Always returns exit 0 — informational only; the caller decides
- Git-only data sources (`git ls-remote` + `git log`); works in
  the Claude Code Web sandbox where `gh` CLI is unavailable
- 48-hour window for "recent commits" — matches typical
  worker ↔ main session handoff cadence

## Reference precedent

PR #123 (2026-05-19, closed without merging): worker session on
`claude/resume-quantrank-phase-4.5-Zh0pO` opened a Phase 4j + 4k
scout duplicate while the main session shipped the same work
directly via PRs #119 (Qlib) + #121 (IPCA). Root cause: the worker
session never inspected the `claude/*` branch list + recent PRs
before writing code. This skill exists to make that check
mandatory before the first edit on a worker session.

## Long-form description (moved out of frontmatter 2026-06-11 token drain)

Preflight check for QuantRank worker sessions handed off via a
prompt. Lists active claude/* branches + recent merged PRs (last 48h) and
flags scope-keyword collisions so a duplicate PR (like #123, closed as a
duplicate of #119+#121 after 100% wasted effort) doesn't reach Draft. Pure
read-only — uses git ls-remote + git log only, no `gh` CLI / GitHub API
needed. TRIGGER before creating a new claude/* branch from a handoff prompt,
before the first non-trivial file edit on a fresh worker session, when the
user mentions a Phase number / issue number / "Item #N" that hasn't been
cross-checked against open PRs, or when "do this on a new branch" / "spawn
a worker session" appears in the handoff. SKIP for doc-only chores that
can't collide on substance (e.g., editing a single comment, fixing a typo),
for the second-and-later iterations within the same already-checked
session, or when the user has explicitly authorized parallel work on the
same scope ("yes I know #119 shipped, also open this from the worker side").
