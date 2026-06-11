---
name: pr-iteration-flow
description: PR-review workflow harness while any PR is open: Draft↔Ready flips, CI-event subscription, spot-check matrix generation, the fix-commit-spot-check rhythm, and the final user-authorized Mark-Ready. TRIGGER: opening a PR (open as Draft), a preview spot-check fix request, a stop-the-line issue after Mark-Ready, CI failure on the branch, or "open a PR" / "mark this ready" / "flip to draft" / "watch this PR" / "เช็ค CI" / "ดู PR".
---

# pr-iteration-flow

The QuantRank PR workflow has converged on a specific iteration pattern
through PR-3c (initial polish), PR-3d (5+ iterations on UI), and PR-20
(restructure with retries). This skill codifies that pattern so each
PR doesn't reinvent it.

## The core loop

```
[author writes code]
        ↓
[ruff + pytest + tsc + next build locally]
        ↓
[open PR as Draft] ← always Draft first
        ↓
[subscribe_pr_activity]
        ↓
[CI runs] → green
        ↓
[Vercel preview rebuilds] → user spot-checks
        ↓
   ┌──[anomaly found]──┐
   ↓                    │
[user specs fix]      [no anomaly]
   ↓                    │
[apply fix → push] ────┘
        ↓
[user authorizes Mark-Ready]
        ↓
[update_pull_request draft=false]
        ↓
[user merges (on their timeline)]
```

The contract: **the agent never flips Draft→Ready without explicit user
authorization**, and **the agent never merges, period**.

## Three sub-flows

### 1. Initial Draft setup (open the PR)

When opening a new PR:

- Use `mcp__github__create_pull_request` with `draft=true`
- Title format: `<type>(scope): <one-line summary>`
  - Types: `feat`, `fix`, `chore`, `polish`, `perf`, `docs`, `refactor`
  - Scope examples: `phase-3d`, `skills`, `phase-3e`
- Body uses the canonical PR-description template (see "PR body
  template" section below)
- Immediately call `mcp__github__subscribe_pr_activity` for that PR
  number so webhook events arrive without polling

### 2. Iteration cycle (user spot-checked, found something)

The user has reviewed the Vercel preview and noticed an issue. They
specify a fix. The agent:

1. **Applies the fix** — code change, CSS tweak, content edit
2. **Runs local verification** — typically:
   - `ruff check .`
   - `python -m pytest tests/ -m "not network"` (or relevant subset)
   - `python -m compute.output.schema_check` (if schemas touched)
   - `cd frontend && npx --no -- tsc --noEmit` (if frontend touched)
   - `cd frontend && npx --no -- next build` (if route shape may have
     changed — typically only on structural frontend changes)
3. **Commits with a precise message** — keep messages short, name the
   fix, explain WHY in one line max. Format:
   `<type>(scope): <one-line summary>`
4. **Pushes to the PR branch** (no force-push unless the user
   explicitly asked)
5. **Stops and reports**: commit SHA, diff stat, what was fixed, what
   CI is doing — then waits for the next user spot-check

Don't queue multiple fixes locally before pushing. The user expects
the rhythm: spot-check → spec a fix → agent commits + pushes →
user spot-check. Each iteration is one commit.

### 3. Final Mark-Ready

When the user authorizes Mark-Ready:

1. Verify CI is green on the latest commit
2. Verify `mergeable_state: "clean"`
3. Update PR body if scope or verification snapshot changed during
   iteration
4. Flip Draft→Ready via
   `mcp__github__update_pull_request` with `draft=false`
5. Report: PR URL, final state, reviewer checklist completion

## Spot-check matrix template

When opening a PR or pushing an iteration, include a matrix the user
can quickly scan against the Vercel preview:

```markdown
| Issue # | Where to verify              | What to look for                            |
|---------|------------------------------|---------------------------------------------|
| 1       | NVDA detail FairPriceBarChart | "Current $X" label at top, no clipping      |
| 2       | NVDA detail x-axis            | Rightmost tick ($1238) renders fully        |
| 3       | Any detail PillarRadarChart   | "Technical" label fully visible             |
| ...     | ...                          | ...                                         |
| Regression | All previous fixes        | Still working as in <prior commit SHA>      |
```

## PR body template

```markdown
# <type>(scope): <one-line summary>

<2-3 sentence summary of what this PR does + why>

## Scope

<bullet list of changes, organized by component>

## Verification

| Check | Result |
|---|---|
| `ruff check .` | ✓ clean |
| `pytest -m "not network"` | ✓ N passed |
| `npx tsc --noEmit` | ✓ clean (if frontend touched) |
| `next build` | ✓ 506/506 routes (if frontend touched) |
| Schema snapshot | ✓ in sync (if schemas touched) |
| Production output | ✓ Section A-H clean (if compute touched) |

## What this PR does NOT touch

<explicit list of out-of-scope areas — reduces reviewer confusion>

## Reviewer checklist

- [ ] CI green
- [ ] Vercel preview spot-checked (if UI changed)
- [ ] <scope-specific items>

---
Generated with Claude Code · Tested with Anthropic API
```

## Hard rules

These exist because violating them has been expensive in this repo:

- **Never flip Draft→Ready without explicit user authorization.** Even
  if CI is green and the diff looks clean, wait for the "authorize
  Mark Ready" message.
- **Never merge without explicit user authorization.** Same rule, one
  step further.
- **Never delete the branch without explicit user authorization.** The
  user controls timing for tag → cleanup → next-PR-start.
- **Always commit the fix in the same iteration cycle.** Don't queue
  multiple fixes locally and ask before committing — that breaks the
  rhythm.
  - Exception: the FIRST iteration of a structurally significant
    change (e.g., schema refactor with non-obvious tradeoffs) —
    propose the diff and ask before committing. After approval,
    subsequent iterations follow the auto-commit rhythm.

## Stop-hook compatibility

The repo's `~/.claude/stop-hook-git-check.sh` fires on uncommitted
changes. The iteration pattern is compatible because each fix is
committed before the iteration ends. If a turn would end with
uncommitted changes:

1. Commit + push (default — matches user expectation)
2. Or explicitly tell the user "holding the diff for your review;
   don't commit per your instruction" — overrides the hook for that
   turn

## Subscribe to PR activity

After every push that needs CI to run:

```python
mcp__github__subscribe_pr_activity(
    owner="dackclup",
    repo="quantrank",
    pullNumber=<N>,
)
```

This delivers `<github-webhook-activity>` messages for CI failures
and review comments without polling.

**Never `sleep` to wait for CI.** The subscription delivers events
when they happen.

## Handling Vercel-bot comments

Vercel's preview-deployment bot posts an automated comment on every
PR with a "Building" / "Ready" status link. These are **informational
only** — no action needed. The skill skips them in the iteration
report.

## Anti-patterns

- Polling CI status in a loop. Use the subscription + webhook events.
- Running the full `next build` for every iteration if the change is
  a pure prop tweak with no new imports. `tsc --noEmit` + `ruff
  check .` is enough for fast feedback. Reserve `next build` for
  structural changes that could affect route count.
- Pasting the full PR description into chat after every iteration.
  Reference it via PR URL or `mcp__github__pull_request_read` if
  needed. Keep iteration reports tight: commit SHA, diff stat, fix
  summary.
- Referring to the user as "the user" in commit messages. Use neutral
  phrasing — "production spot-check found …" beats "user spot-check
  found …".

## Why this skill exists

Without a codified flow, every PR iteration starts from "what's our
PR workflow again?" The agent and the user re-negotiate the rhythm
each time. This skill is the single source of truth so every PR
follows the same predictable rhythm and the user knows exactly what
to expect at each step.

It also encodes the **hard rules** that violating has been expensive
(forgetting to Draft-first, premature Mark-Ready before spot-check,
auto-merging without authorization). Each rule reflects a specific
near-miss that surfaced earlier in the project.

## Related skills

- `verify-production-output` — used inside the iteration cycle when
  compute output is part of the diff
- `schema-check` — used inside the iteration cycle when schemas
  touched
- `defense-scorecard` — used inside iteration cycle when scoring
  touched
- `phase-status-bump` — runs AFTER merge as part of the broader phase
  lifecycle; not inside the PR-iteration loop itself

## Long-form description (moved out of frontmatter 2026-06-11 token drain)

Manage QuantRank's PR-review workflow — the Draft↔Ready flip cycle,
CI-event subscription, spot-check matrix generation, and the rhythm
of fix-commit-spot-check iterations before final user-authorized
Mark-Ready (5+ polish iterations per PR is common). The default
workflow harness while any PR is open. TRIGGER when opening a new
PR (open as Draft), when the user spot-checks a Vercel preview and
requests a fix, when a stop-the-line issue surfaces after Mark-Ready
(flip back to Draft), when CI fails on a PR branch (subscribe +
investigate), when authorizing the final Mark-Ready after spot-check
approval, or when the user says "open a PR for this" / "mark this
ready" / "flip to draft" / "watch this PR for me" / "เช็ค CI" / "ดู
PR". SKIP post-merge cleanup steps (branch deletion / tag / file
follow-up issues — those are different workflows).
