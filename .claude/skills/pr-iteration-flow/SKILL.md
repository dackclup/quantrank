---
name: pr-iteration-flow
description: Manage the Draft↔Ready flip cycle during PR review iterations and
  generate spot-check matrices for user review. Use during UI polish or post-merge
  preparation when the PR may need multiple iterations of fix-commit-spot-check
  before final Mark-Ready authorization. Codifies the pattern used in PR-3d.
---

# pr-iteration-flow

## When to use

- During UI polish iterations where the user spot-checks Vercel
  preview after each fix and may flag more issues
- During post-production-verification iterations where Section A-H
  results may surface anomalies needing fixes before Mark-Ready
- When a PR has been pushed Ready but a stop-the-line issue
  surfaced and we need to flip back to Draft for fix-iterations

This skill **codifies the iteration pattern** that emerged in PR-3d
(5+ polish iterations from initial Mark-Ready through final spot-check
approval). The pattern is:

```
[push fix] → [CI green] → [Vercel preview rebuild] → [user spot-check]
                                                            ↓
                                          ┌────[anomaly found]────┐
                                          ↓                        │
                                    [next iteration spec]        [continue]
                                          ↓                        │
                                    [push fix] ←──────────────────┘
                                          ↓
                              [user authorizes Mark-Ready]
                                          ↓
                                    [flip Draft → Ready]
```

## What it does

Provides three sub-flows:

### 1. Initial Draft setup

When opening a new PR:
- Open as Draft (`gh pr create --draft` or MCP equivalent)
- Body uses the standard PR template structure (see
  `pr-iteration-flow/template.md` for canonical layout)
- Title format: `<type>(phaseN): <one-line summary>`

### 2. Iteration cycle

When user requests a fix during review:
- Apply the fix (CSS/code change)
- Run local verification: `ruff check .`, `pytest -m "not network"`,
  `python -m compute.output.schema_check`, frontend `tsc + next build`
- Commit with message format:
  `polish(phaseN): <one-line summary>` (or `fix`, `feat`, etc.)
- Push to the PR branch
- Subscribe to PR activity for CI events
- Stop and report: commit SHA, diff stat, what was fixed
- Wait for user spot-check before next action

### 3. Final Mark-Ready

When user authorizes Mark-Ready:
- Confirm CI is green on the latest commit
- Confirm `mergeable_state: clean`
- Update PR body if scope or verification snapshot changed
- Flip Draft → Ready (`gh pr ready` or MCP `update_pull_request draft=false`)
- Report: PR URL, final state, reviewer checklist

## Spot-check matrix template

Generate a matrix the user can scan against the Vercel preview:

```
| Issue # | Where to verify              | What to look for                                   |
|---------|------------------------------|----------------------------------------------------|
| 1       | NVDA detail FairPriceBarChart | "Current $X" label visible at top, no clipping     |
| 2       | NVDA detail x-axis            | Rightmost tick ($1238) renders fully               |
| 3       | Any detail PillarRadarChart   | "Technical" / "Profitability" labels render fully  |
| 4a      | Rankings mobile               | SPG #1 height = NVDA #2 (uniform)                  |
| 4b      | Rankings mobile null fp       | SPG/BKR show "Fair ⚠ N/A"                          |
| 5       | NVDA detail BarChart          | Graham + Residual Income bars ≥5px                 |
| ...     | ...                          | ...                                                |
| Regression | All previous fixes        | Still working as in <prior commit SHA>             |
```

## Hard rules

- **Never flip Draft → Ready without explicit user authorization.**
  Even if CI is green and the diff looks clean, wait for the
  "authorize Mark Ready" message.
- **Never merge without explicit user authorization.** Same rule,
  one step further.
- **Never delete the branch without explicit user authorization.**
  The user controls timing for tagging + cleanup.
- **Always commit the fix in the same iteration cycle.** Don't queue
  multiple fixes locally and ask before committing — that breaks
  the rhythm. The user expects: spot-check → spec a fix → I commit
  + push → user spot-check next iteration.
  - Exception: the FIRST iteration of a brand-new pattern (e.g., a
    structural refactor with non-obvious tradeoffs) — propose
    diff + ask before committing. After approval, subsequent
    iterations follow the auto-commit rhythm.

## Stop hook compatibility

The repo's stop hook (`~/.claude/stop-hook-git-check.sh`) fires on
uncommitted changes. The iteration cycle pattern is compatible with
the hook because each fix is committed before the iteration ends. If
you find yourself about to end a turn with uncommitted changes,
either:
1. Commit + push (default — matches user expectation)
2. Or explicitly tell the user "I'm holding the diff for your review;
   don't commit per your instruction" — overrides the hook for that
   turn

## Subscribe to PR activity

After every push that needs CI to run:

```python
# via MCP github tool
mcp__github__subscribe_pr_activity(
    owner="dackclup",
    repo="quantrank",
    pullNumber=12,
)
```

This delivers `<github-webhook-activity>` messages for CI failures
and review comments without polling. **Never `sleep` to wait for CI.**

## Anti-patterns (do not do)

- Don't poll CI status in a loop. Use `subscribe_pr_activity` and
  let webhooks wake the session.
- Don't run the full `next build` for every iteration if the change
  is purely a tsx prop tweak with no new imports — rely on `tsc
  --noEmit` + `ruff check .` for fast feedback. Reserve `next build`
  for verifying route count after structural changes.
- Don't paste the entire PR description into chat after every
  iteration. Reference it via `gh pr view 12` or the MCP equivalent
  if needed; otherwise keep iteration reports tight (commit SHA,
  diff stat, fix summary).
- Don't call the user "the user" in commit messages. Use neutral
  phrasing: "user spot-check" → "production spot-check" if you must
  reference the trigger.

## Related

- `verify-production-output` — Section A-H runs typically conclude
  with a spot-check matrix
- `phase-status-bump` — runs after the final Mark-Ready + merge
- The PR template lives at `.github/PULL_REQUEST_TEMPLATE.md` (if
  exists) — should be loaded here as a default body when opening
  new PRs
