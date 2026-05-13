---
name: phase-status-bump
description: Update PHASE_STATUS.md, SKILL.md, and WORKFLOW.md in lockstep when
  a QuantRank phase or sub-PR completes. These three docs cross-reference each
  other (current phase, schema version, active veto count, deferred items)
  and tend to drift if updated piecemeal — this skill is the single update
  flow that keeps them aligned. TRIGGER after merging a phase-completion PR
  (e.g., PR 3d → tag v0.6.0-phase3d), after tagging a release version, when
  a sub-PR within a phase finishes and the next sub-PR begins (e.g.,
  3a→3b, 3c→3d), when the schema version moves, or when the user asks
  "mark phase X complete" / "bump the status docs" / "update the phase
  tracker". SKIP for compute / frontend code changes (no docs to bump),
  for README or docs/ARCHITECTURE.md updates (different lifecycle), or
  when only one of the three triple-docs needs editing (the value is in
  doing all three together; if only one needs an edit, just edit it).
---

# phase-status-bump

Three top-level docs form a triangle that contributors and Claude alike
read to ground their context:

- `PHASE_STATUS.md` — the chronological phase tracker (table + per-phase
  summary block)
- `SKILL.md` — high-level project rules + current state constants
- `WORKFLOW.md` — long-form per-phase task lists

When one moves and the others don't, future sessions get confused about
what version we're on, which vetoes are active, which sub-PR ships
next. This skill enforces a single update flow.

## When to run

Run as the **last step** after a phase-completion PR merges. The PR
itself may have docs changes; this skill catches the ones the PR didn't
update.

Concrete triggers:

| Event | Lockstep changes |
|---|---|
| PR for sub-PR X merges, sub-PR Y begins | mark X done, set Y as current focus |
| Phase boundary (e.g., Phase 3e completes, Phase 4 starts) | mark Phase 3e done, flip status to ⚪→🟡 on Phase 4 |
| Release tag cut (e.g., `v0.6.0-phase3d`) | record the tag + production-verified commit SHA |
| New SKILL.md rule introduced | append the rule + note in the prior sub-PR's summary |

## Update flow

### Step 1 — Gather inputs before touching any file

These come from the merged PR + the production-verified run:

- Phase number being completed (e.g., `3d`)
- Schema version delta (e.g., `0.5.0-phase3c → 0.6.0-phase3d`)
- One-sentence summary of what shipped
- Bullet list of what's deferred (with `/tmp/issue_drafts/` filenames if applicable)
- Defense-scorecard delta (vetoes / guards / annotate counts)
- Production-verified commit SHA + run number + test count

### Step 2 — `PHASE_STATUS.md`

Find the phase row. Update the **Status** column from "🟡 in progress"
or "⚪ not started" to "✅ DONE — YYYY-MM-DD".

If the row has a sub-PR breakdown (like Phase 3 has `3a/3b/3c/3d/3e`),
update the relevant sub-PR bullet:

- Mark the completed sub-PR ✅ DONE
- Add a 4-8 line summary mirroring the format of the prior sub-PR's
  block — same headings, same level of detail
- Include: schema version, commit count, test delta, production
  verification snapshot, key deferred items

### Step 3 — `SKILL.md`

Top-of-file constants:

- `Current schema version` — update if changed
- `Active vetoes count` — update if the defense layer changed
- `Last verified` — date + run number

Rules section:

- If a new rule was introduced this phase, append at the end
  (e.g., PR 3d added Rule 16 — annotate-and-veto-Top-N pattern)
- Number monotonically. Do not renumber existing rules.

End-of-file outlook:

- If the completed phase deferred items to Phase 4, append them to the
  deferred list with a one-line rationale + link to the
  `/tmp/issue_drafts/` issue draft

### Step 4 — `WORKFLOW.md`

Find the phase's task list. Mark each completed task `[x]`, leave `[ ]`
for deferred. For deferred tasks, append "(Phase 4)" or "(Phase N)" to
the task title so the deferral is visible in the checklist scan.

If the phase had per-step checkpoints documented inline, mark them all
`[x]` if the phase is fully done.

### Step 5 — Commit all three together

Single commit, all three staged. Suggested message format:

```
docs(phaseN): mark phase N complete + bump schema 0.X.Y → 0.X.Y+1

PHASE_STATUS.md: phase N row → ✅ DONE
SKILL.md: schema constant + active veto count + Rule N if added
WORKFLOW.md: phase N task list → all [x]

Production verified: commit <sha> / run #N / N stocks / N tests.
Deferred to Phase N+1: <list>.
```

## Do NOT touch (different lifecycles)

| File | Why not |
|---|---|
| `docs/METHODOLOGY.md` | Academic methodology reference. Updates via separate research-doc PRs. |
| `docs/RESEARCH_FINDINGS.md` | Same. |
| `docs/ARCHITECTURE.md` | System architecture. Updates only on layer-1 changes (new top-level module). |
| `README.md` | Reader-facing intro. Updates only on milestone tags (v1.0, v1.5). |
| `LICENSE`, `pyproject.toml`, CI workflows | Not docs. |
| `compute/**`, `frontend/**`, `tests/**` | Code, not docs. |

## Consistency invariants (verify before commit)

These must all hold simultaneously across the three files:

- Phase number matches in all three
- Schema version matches the `frontend/public/data/metadata.json` from
  the latest workflow run
- Production-verified commit SHA in `PHASE_STATUS.md` matches
  `metadata.json::git_commit`
- Active veto count in `SKILL.md` matches the defense-scorecard
- No deferred item mentioned in `PHASE_STATUS.md` lacks a matching
  `/tmp/issue_drafts/issue_*.md` draft (file the issue if needed)

If any invariant fails, the docs are still drifting — fix before
shipping the commit.

## Anti-patterns

- Updating only one or two of the three. The whole point is the triple
  — partial updates re-introduce the drift this skill exists to fix.
- Bumping the schema version in `pyproject.toml` or `schemas.py` here.
  Version bumps belong with the actual scoring / shape change PR; this
  skill only updates the docs that *reference* the bump.
- Preview-bumping (claiming a phase done before it's actually done).
  The phase is done when: CI is green on `main`, the workflow run
  succeeded, and the production JSON reflects the new schema. Until
  then, leave the row as 🟡.
- Archiving completed phases out of `PHASE_STATUS.md`. The whole point
  is the chronological record.

## Why this skill exists

The triple-doc drift problem comes up every phase. Without a single
flow, contributors update PHASE_STATUS.md and forget SKILL.md, or
update SKILL.md and forget WORKFLOW.md. Future sessions then read a
mix of stale and current state and make bad decisions (claiming the
wrong schema version is current, or that a deferred item is shipped).
This skill is the cheap insurance against that drift.

## Related skills

- `verify-production-output` — generates the snapshot to cite (commit
  SHA, run number, test count, coverage)
- `defense-scorecard` — generates the active veto count for SKILL.md
- `pr-iteration-flow` — the PR-side workflow this skill plugs into at
  the end (PR merge → status bump)
