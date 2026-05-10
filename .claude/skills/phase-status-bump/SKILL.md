---
name: phase-status-bump
description: Update PHASE_STATUS.md, SKILL.md, and WORKFLOW.md consistently when a
  phase or sub-PR completes. Use after merging a phase-completion PR — the
  three docs reference each other and tend to drift. This skill keeps them
  aligned with one update flow.
---

# phase-status-bump

## When to use

- After merging a phase-completion PR (e.g., PR 3d → tag v0.6.0-phase3d)
- After tagging a release version
- When a sub-PR within a phase finishes and the next sub-PR begins
  (e.g., 3a→3b, 3c→3d, 3d→3e)

## What it does

Updates three top-level docs in lockstep:

1. **`PHASE_STATUS.md`** — the canonical phase tracker
2. **`SKILL.md`** — the project's high-level rules + current state
3. **`WORKFLOW.md`** — the longer-form per-phase task lists

The three docs cross-reference each other and tend to drift if
updated piecemeal. This skill enforces a single update flow with
a consistent format.

## Inputs (gather before invoking)

- Phase number being completed (e.g., "3d")
- Schema version delta (e.g., `0.5.0-phase3c` → `0.6.0-phase3d`)
- One-sentence summary of what shipped
- Bullet list of what's deferred (e.g., "Defenses #9 + #10 → Phase 4")
- Defense scorecard delta (vetoes / guards / annotate flags counts)
- Production verification snapshot (commit SHA, run #, test count)

## Update flow

### Step 1 — `PHASE_STATUS.md`

Find the phase row. Update the **Status** column from "🟡 in progress"
or "⚪ not started" to "✅ DONE — YYYY-MM-DD".

If the row has a sub-PR breakdown (like Phase 3 has `3a/3b/3c/3d/3e`),
update the relevant sub-PR's bullet:

- ✅ Mark the completed sub-PR ✅ DONE
- Add a 4-8 line summary of what shipped, mirroring the format of
  earlier sub-PR entries (don't reinvent — copy the structure of the
  immediately prior sub-PR)
- Include: schema version, commit count, test delta, production
  verification snapshot, key deferred items

### Step 2 — `SKILL.md`

Top-of-file:
- Update `Current schema version` constant if changed
- Update `Active vetoes count` if defense layer changed
- Update `Last verified` line with date + run #

Mid-file (Rules section):
- If a new rule was introduced this phase, append at the end
  (e.g., PR 3d added Rule 16 — annotate-and-veto-Top-N pattern).
  Number monotonically. Do not renumber existing rules.

End-of-file (`## Phase 4+` outlook):
- If the completed phase deferred items to Phase 4, append them
  to the deferred list with a one-line rationale + link to the
  `/tmp/issue_drafts/` issue draft.

### Step 3 — `WORKFLOW.md`

Find the phase's task list. Mark each task `[x]` if completed,
leave `[ ]` if deferred. For deferred tasks, append "(Phase 4)" or
"(Phase N)" to the task title.

If the phase had per-step checkpoints documented inline, mark them
all `[x]` if the phase is fully done.

## Do NOT touch

- `docs/METHODOLOGY.md` — academic methodology reference. Updates
  via separate research doc PRs, not phase status bumps.
- `docs/RESEARCH_FINDINGS.md` — same.
- `docs/ARCHITECTURE.md` — system architecture. Updates only on
  architectural changes (new module added at the layer-1 level),
  not phase completion.
- `README.md` — reader-facing intro. Updates only on milestone tags
  (v1.0, v1.5).
- `LICENSE`, `pyproject.toml`, `.github/workflows/*.yml`,
  `compute/**`, `frontend/**`, `tests/**` — not docs.

## Consistency invariants (verify before commit)

- Phase number cited in all three files matches.
- Schema version cited in all three files matches the
  `frontend/public/data/metadata.json` from the latest workflow run.
- Production-verified commit SHA in `PHASE_STATUS.md` matches the
  `git_commit` field in `metadata.json`.
- Active veto count in `SKILL.md` matches the defense scorecard.
- No mention of a deferred item appears in PHASE_STATUS without a
  matching `/tmp/issue_drafts/issue_*.md` file.

## Output

Single commit with all three files staged together. Suggested
commit message format:

```
docs(phaseN): mark phase N complete + bump schema 0.X.Y → 0.X.Y+1

PHASE_STATUS.md: phase N row → ✅ DONE
SKILL.md: schema constant + active veto count + Rule N if added
WORKFLOW.md: phase N task list → all [x]

Production verified: commit <sha> / run #N / N stocks / N tests.
Deferred to Phase N+1: <list>.
```

## Anti-patterns (do not do)

- Don't update only one of the three files. They're a triple — if
  they drift, the next phase's planning gets confused about state.
- Don't bump the schema version in code (pyproject / schemas.py)
  via this skill. Schema bumps belong with the phase's actual code
  changes; this skill only updates the docs that *reference* the
  bump.
- Don't preview-bump (claim a phase is done before it actually is).
  The phase is done when CI is green on `main`, the workflow run is
  successful, and the production output JSON reflects the new
  schema. Until then, leave the row as 🟡.
- Don't archive completed phases out of `PHASE_STATUS.md`. The
  whole point is the chronological record.

## Related

- `verify-production-output` — generates the snapshot to cite in
  `PHASE_STATUS.md`
- `defense-scorecard` — generates the active veto count for `SKILL.md`
- `pr-iteration-flow` — the PR-side workflow this skill follows
