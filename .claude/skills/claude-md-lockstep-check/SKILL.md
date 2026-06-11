---
name: claude-md-lockstep-check
description: Verify CLAUDE.md + AGENTS.md both moved on the current branch per the "ship with every PR" rule — catches one-side-only drift and code/workflow/schema PRs missing both. TRIGGER: before opening any PR, after staging commits that touch compute/ / frontend/ / workflows / schemas, before Draft→Ready, or "lockstep check" / "did I update both docs?" / "ลืม update CLAUDE.md หรือเปล่า".
---

# CLAUDE.md + AGENTS.md Lockstep Check

QuantRank's `CLAUDE.md` §Conventions rule ("CLAUDE.md + AGENTS.md ship
with every PR") fails silently — there's no CI guard, so it relies on
PR-time discipline. This skill is the discipline: a quick read-only
diff check that catches missing lockstep updates before they reach the
reviewer.

## Why this matters

Drift between the two agent docs has happened in real PRs:

- **PR #154** (Phase 1.2) updated CLAUDE.md but the AGENTS.md row for
  Phase 1.2 lagged
- The cross-tool agents (Copilot, Cursor, Devin) read AGENTS.md but
  NOT CLAUDE.md — so the lag silently broke their context

This skill is the disciplined preflight that catches that drift.

## Process

### 1. Inspect the current diff

Identify what changed vs the merge base:

```bash
BASE=$(git merge-base HEAD origin/main)
git diff --name-only "$BASE"..HEAD
```

Extract three boolean signals:

- `CLAUDE_TOUCHED` — is `CLAUDE.md` in the diff?
- `AGENTS_TOUCHED` — is `AGENTS.md` in the diff?
- `CODE_TOUCHED` — does the diff include any of:
  - `compute/**/*.py`
  - `frontend/**/*.{ts,tsx,js,jsx,css}`
  - `.github/workflows/**`
  - `pyproject.toml`
  - `compute/output/schemas.py`
  - `frontend/lib/types.ts`
  - `compute/main.py`
  - schema-snapshot.json

### 2. Decision matrix

| `CODE_TOUCHED` | `CLAUDE_TOUCHED` | `AGENTS_TOUCHED` | Verdict |
|:---:|:---:|:---:|---|
| ✅ | ✅ | ✅ | ✅ pass — lockstep satisfied |
| ✅ | ✅ | ❌ | 🟡 warn — AGENTS.md missing (cross-tool agents will go stale) |
| ✅ | ❌ | ✅ | 🟡 warn — CLAUDE.md missing (Claude Code sessions will go stale) |
| ✅ | ❌ | ❌ | 🔴 fail — code changed, neither agent doc updated (Convention violation) |
| ❌ | ✅ | ✅ | ✅ pass — coordinated docs update |
| ❌ | ✅ | ❌ | 🟡 warn — diverging agent docs (likely typo / oversight) |
| ❌ | ❌ | ✅ | 🟡 warn — same as above, reversed |
| ❌ | ❌ | ❌ | ✅ pass (or "no diff" — irrelevant) |

### 3. If warn / fail, suggest the minimum edit

Pick the smallest valid lockstep entry per `CLAUDE.md`'s rule text:

> At minimum a §Phase status note (PR in flight) or a section update
> (new gotcha / convention / connector / layout / command).

Suggest one of these patterns depending on the change kind:

| Change kind | Where to add the lockstep entry |
|---|---|
| New phase work in flight | `CLAUDE.md` §Phase status "in flight" block + `AGENTS.md` §Phase + version state matching line |
| New skill | Layout table count bump in both, plus a short §Phase status / §version-state entry |
| New convention / rule | `CLAUDE.md` §Conventions bullet + `AGENTS.md` matching cross-tool note |
| New gotcha | `CLAUDE.md` §Gotchas bullet + `AGENTS.md` if cross-tool-visible, else skip AGENTS side |
| New MCP connector | `CLAUDE.md` §Connectors table row + `AGENTS.md` cross-tool note |
| Schema bump | Both docs need a phase-status note + the schema-version line in CLAUDE.md |

### 4. Show the user the verdict + suggested edits

Don't auto-edit — print the verdict and the suggested edit location.
The user decides whether the lockstep entry needs more substance.

If `CODE_TOUCHED` is true but the change is tiny (e.g., a typo in a
docstring), the user may legitimately judge "no real lockstep needed"
and accept the warn without action. That's their call; this skill's
job is to surface the question.

## Output format

```
=== CLAUDE.md + AGENTS.md lockstep check ===
Branch: claude/<branch-name>
Merge base: <SHA[:7]>

Diff signals:
  ✓ CLAUDE.md touched
  ✗ AGENTS.md NOT touched
  ✓ Code touched (compute/scoring/composite.py + tests/test_scoring/test_composite.py)

Verdict: 🟡 WARN — AGENTS.md missing

Suggested minimum edit:
  AGENTS.md §Phase + version state — add a 1-line "in flight" entry
  matching the CLAUDE.md update on line N.

Example:
  - **<Change name> in flight via PR #<N>** — <one-line summary>.
    Cross-tool agents: <impact, e.g., schema version moved 0.9.2 →
    0.9.3, see CLAUDE.md §Phase status>.
```

## Quick check (one-liner)

For experienced users who just want a fast yes/no:

```bash
BASE=$(git merge-base HEAD origin/main); \
git diff --name-only "$BASE"..HEAD | \
grep -E '^(CLAUDE|AGENTS)\.md$' | sort -u
```

If the output shows **both** `CLAUDE.md` and `AGENTS.md`, the lockstep
is satisfied at minimum. The skill body is the disciplined version
that catches the "code changed but neither doc updated" failure mode.

## What this skill is NOT

- Not a CI guard (yet — could be promoted to a GitHub Actions check
  in a future PR; the helper logic in step 2 is the implementation)
- Not a content review — only checks that the docs were touched, not
  that the touch was substantive. A whitespace-only edit to CLAUDE.md
  would satisfy this skill but probably fail PR review
- Not coupled to `phase-status-bump` — that skill aligns the
  PHASE_STATUS / SKILL / WORKFLOW triple; this skill is the CLAUDE +
  AGENTS pair, which is a different invariant

## Long-form description (moved out of frontmatter 2026-06-11 token drain)

Verify CLAUDE.md + AGENTS.md were both modified on the current branch, per QuantRank's "ship with every PR" rule (CLAUDE.md §Conventions). Catches the common drift pattern where only one of the two agent docs is updated, or neither when code / workflows / schemas changed. TRIGGER before opening any PR, after staging a commit that touches `compute/`, `frontend/`, `.github/workflows/`, `pyproject.toml`, `compute/output/schemas.py`, or `frontend/lib/types.ts`, when the user says "lockstep check", "did I update both docs?", "CLAUDE.md drift", "ลืม update CLAUDE.md หรือเปล่า", or before flipping a PR from Draft to Ready. SKIP for PRs that touch ONLY `CLAUDE.md` / `AGENTS.md` themselves (the lockstep is trivially satisfied), for `.claude/skills/<vendored>/` body-only changes (vendor-sync skill handles those), and for branch-local exploration commits that won't ship as a PR.
