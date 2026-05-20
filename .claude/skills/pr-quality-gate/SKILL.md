---
name: pr-quality-gate
description: >
  Final pre-merge completeness audit for a QuantRank PR. Runs the
  Section A-G checklist a senior reviewer would walk before approving
  a Mark-Ready flip: diff scope vs PR description, skill triggers met
  (schema-check / security-check / verify-production-output /...),
  documentation drift (Pydantic↔TS, PHASE_STATUS, README), test
  coverage delta, local verification ladder pass, commit hygiene, and
  CI/preview status. TRIGGER before authorizing the Draft→Ready flip,
  before authorizing a merge, before tagging a release, or when the
  user asks "is this PR ready?" / "final check on PR #X" / "anything
  else before we merge?" / "did I miss anything?" / "review the whole
  PR" — invoke even when the user names a single concern, since this
  skill verifies all surfaces in one pass. SKIP for doc-only PRs
  (README typos / SKILL.md wording) that have no code surface, and
  for in-progress iteration commits (use `pr-iteration-flow` for that
  rhythm); this skill is the final gate, not the per-iteration nudge.
---

# pr-quality-gate

The final completeness check before authorizing a Mark-Ready flip /
merge / tag. Sister skills `pr-iteration-flow` (manages the flow),
`security-check` (security audit), and `verify-production-output`
(compute output audit) each cover one slice; this skill is the
**checklist that catches what each slice misses**: did the right
slices run at all?

A senior reviewer's mental model when approving a merge is:

> "I have the diff in front of me. Does the diff match the claim?
> Were the right verifications run? Did the docs follow the code?
> Were tests added? Is the commit history clean? Is CI green?
> Is the preview good?"

This skill answers each of those questions explicitly.

## When to invoke

| Trigger | Why |
|---|---|
| Before flipping Draft → Ready | Mark-Ready signals "human review please" — make sure the PR is actually ready |
| Before authorizing a merge | The user's final go/no-go decision deserves a real checklist |
| Before tagging a release | Tags ship to production Vercel + lock the commit |
| User asks "is this ready?" / "did I miss anything?" | Direct invocation |
| After a stop-the-line issue → before flipping back to Ready | The fix may have introduced new gaps |

Skip for:

- Doc-only PRs (README / SKILL.md wording / typo fixes) — no code surface
- In-progress iteration commits — use `pr-iteration-flow` for that rhythm
- Hotfix PRs where the urgency outweighs the audit cost (record the
  skip in the PR body as `quality-gate: skipped — hotfix`)

## Running

```bash
# Run from repo root, on the PR's branch (not main).
python .claude/skills/pr-quality-gate/helper.py
```

Optional flags:

```bash
# Strict mode: any soft warning becomes a hard failure (exit 2). Use
# this when you want a CI-gate-strength run.
python .claude/skills/pr-quality-gate/helper.py --strict

# Restrict to one section (faster iteration during fix cycles):
python .claude/skills/pr-quality-gate/helper.py --only=scope
python .claude/skills/pr-quality-gate/helper.py --only=triggers
python .claude/skills/pr-quality-gate/helper.py --only=docs
python .claude/skills/pr-quality-gate/helper.py --only=tests
python .claude/skills/pr-quality-gate/helper.py --only=ladder
python .claude/skills/pr-quality-gate/helper.py --only=commits
python .claude/skills/pr-quality-gate/helper.py --only=polish

# Skip the heavy local-verification subprocess calls (Section E).
# Use when CI has already run them on the branch and you trust those.
python .claude/skills/pr-quality-gate/helper.py --skip-ladder

# Compare against a different base (default origin/main).
python .claude/skills/pr-quality-gate/helper.py --base=origin/develop
```

The helper is pure stdlib + a few subprocess shells (`git`, `ruff`,
`pytest`, `npx tsc`, `npx next`). No extra installs required beyond
what the project already depends on.

## What it checks — 7 sections

Each section emits per-check `✓` healthy / `⚠` soft warning / `✗`
hard failure markers. Hard failures in any section block merge;
soft warnings are acceptable but logged.

### A. Diff scope vs PR description

Goal: catch scope creep + accidental edits.

- Files changed are correlated to the keywords in the PR title /
  description (passed via `--pr-title` / `--pr-body` or read from
  `.git/PULL_REQUEST_BODY` if present)
- Files outside the inferred scope = `⚠` (e.g., a PR titled
  "frontend redesign" that also edits `compute/main.py`)
- Diff size sanity — > 2,000 lines changed or > 50 files touched in
  one PR = `⚠` (large PRs are review-expensive; consider splitting)

This section is heuristic and conservative — false positives are
expected. The point is to surface "did you mean to change this?"

### B. Skill triggers met

Goal: catch "should have run skill X but didn't."

Cross-references the diff against each skill's `TRIGGER` clause:

| Touched | Required skill | Why |
|---|---|---|
| `compute/output/schemas.py` | `schema-check` | Pydantic↔TS bridge |
| `frontend/lib/types.ts` | `schema-check` | Same bridge, other side |
| `compute/scoring/risk_overlay.py` | `defense-scorecard` | Vetoes/guards count |
| `compute/scoring/composite.py` | `top5-rotation-audit` | Top-5 invariants |
| `compute/scoring/<new>.py` | `defense-scorecard` | New defense layer |
| `compute/valuation/ensemble.py` | `verify-production-output` Section C | Fair-price coverage |
| `compute/ingest/<any>.py` | `network-test-runner` | Live SEC fetch |
| `compute/main.py` | `verify-production-output` (after workflow_dispatch) | Orchestrator changes |
| `.github/workflows/*.yml` | `security-check` Section E | CI permissions |
| `pyproject.toml` deps | `security-check` Section B | New CVE surface |
| `frontend/package.json` deps | `security-check` Section B | Same |
| New env-var read in code | `security-check` Section A | New secret surface |
| `frontend/public/data/*.json` | `verify-production-output` | Output JSON contract |
| End of phase | `phase-status-bump` | 3-doc lockstep |

For each triggered skill, the helper looks for the corresponding
**signal** that it was run:

- `schema-check` → `frontend/lib/schema-snapshot.json` modified in
  the same PR (or no schema fields changed — both are valid)
- `security-check` → grep PR body for `security-check: ran` line, or
  presence of `.security-check.json` artifact (not enforced if user
  ran it locally)
- `verify-production-output` → metadata.json in the PR or chore
  commit reference in body

Healthy = either the skill's signal is present, or the file change
was a no-op for the skill's invariants. Missing signal + relevant
diff = `⚠` (the skill MAY have been run mentally without artifact;
the warning is a reminder).

### C. Documentation drift

Goal: catch "code changed but docs didn't follow."

- Pydantic schema field added/removed → `schema-snapshot.json` must
  move. Drift = `✗` (the schema-snapshot CI guard catches this too;
  belt-and-suspenders)
- New `_ensure_*` env-var pattern in code → `CLAUDE.md` / `AGENTS.md`
  / `README.md` must mention it. Drift = `⚠`
- New dep in `pyproject.toml` or `frontend/package.json` →
  `THIRD_PARTY_NOTICES.md` if vendored, or the dep table in
  `CLAUDE.md` if pinned. Drift = `⚠`
- New `compute/scoring/<defense>.py` → `SKILL.md` Rule 16 +
  `WORKFLOW.md` defense-layer table + `docs/RESEARCH_FINDINGS.md`
  citation. Drift = `⚠`
- `SCHEMA_VERSION` bumped → `PHASE_STATUS.md` must move too. Drift
  = `✗`
- PHASE_STATUS / SKILL / WORKFLOW edited in isolation (only 1 of 3)
  → `⚠` (the `phase-status-bump` skill exists precisely so all 3
  move together)

### D. Test coverage delta

Goal: catch "new feature, no test" / "bug fix, no regression test."

- For each `compute/**/*.py` added or substantially modified
  (≥ 20 added lines), check `tests/**/test_<name>.py` is also
  touched in the diff. Miss = `⚠`
- For each new public function `def foo(`, check `tests/` for any
  reference to `foo`. Miss = `⚠`
- New `compute/scoring/<defense>.py` MUST have
  `tests/test_scoring/test_<defense>.py` with ≥ 5 tests. Miss = `✗`
- Bug-fix PR (title starts with `fix:`) MUST add a regression test
  named `test_*_regression` / `test_*_does_not_*`. Miss = `⚠`
- Pytest collection passes — `pytest --collect-only -q` exits 0.
  Failure = `✗`

### E. Local verification ladder

Goal: catch what CI catches, before CI catches it.

Subprocess-shells the standard ladder (skip individual steps with
`--skip-<step>`):

- `ruff check .` — must exit 0 (`✗` on failure)
- `pytest -m "not network"` — must exit 0 (`✗` on failure; can be
  slow, skip with `--skip-pytest` if CI just ran it)
- If `frontend/**` changed → `cd frontend && npx tsc --noEmit` (`✗`)
- If `frontend/**` changed → `cd frontend && npx next build` (`✗`)
  → Skip with `--skip-next-build` for the 60-second cost
- If `compute/output/schemas.py` or `frontend/lib/types.ts` changed
  → `python -m compute.output.schema_check` (`✗`)

This section duplicates CI on purpose — running locally before
push catches the embarrassing "CI red on the obvious thing" cycle.

### F. Commit hygiene

Goal: catch sloppy commit history before squash-merge.

Walks the commits between `merge-base(origin/main, HEAD)` and `HEAD`:

- Empty / placeholder message (`wip`, `fix`, `update`, `todo`,
  single-word subjects) = `⚠`
- Commit body references `--no-verify` / `--no-gpg-sign` in a `git ...`
  command context = `⚠` (prose mentions in code-listing form are
  filtered out)
- Merge commit on the branch (squash-merge expected) = `⚠`
- Commit author is `github-actions[bot]` but touches files outside
  `frontend/public/data/` = `⚠`
- Commits not following the project's `<type>(scope): subject`
  pattern (feat / fix / chore / docs / refactor / test) = `⚠`
- Debug-artifact patterns in the cumulative diff: `console.log(`,
  bare `print(` (excluding `tests/`), `breakpoint(`, `pdb.set_trace`,
  `// FIXME` without an issue reference, large commented-out code
  blocks (≥ 5 lines starting with `# ` or `// `) = `⚠`

### G. Final polish (PR-level)

Goal: catch the metadata issues that block a clean merge.

- PR body has both `## Summary` and `## Test plan` sections (the
  project convention). Missing = `⚠`
- PR title doesn't contain `WIP` / `DO NOT MERGE` / `[wip]`. Match
  = `✗` (you're not ready)
- PR base = `main`. Mismatch = `✗` (forgot to retarget)
- No conflict markers in the diff (`<<<<<<<`, `=======`, `>>>>>>>`)
  = `✗`
- For PR-level checks (CI status, Vercel preview, body content),
  the helper emits a checklist to verify via GitHub MCP — it can't
  call `gh` directly. The agent uses `mcp__github__pull_request_read`
  for those.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | All sections healthy (or only `⚠` warnings under default mode) |
| 1 | Any hard failure (`✗`) in Sections C / E / G (drift + ladder + polish) |
| 2 | `--strict` mode and any soft warning in any section |
| 3 | Helper itself couldn't run (e.g., on `main`, no upstream, detached HEAD) |

**Production-use rule**: exit code > 0 means do NOT authorize
Mark-Ready / merge / tag without remediation.

## Workflow integration

```
... iterate (pr-iteration-flow rhythm) ...
       ↓
[pr-quality-gate run]   ← THIS skill (the final gate)
       ↓
   exit 0?  ────  yes  ──→  Authorize Mark-Ready
       ↓
       no
       ↓
   Fix the findings → commit → re-run gate → loop
```

The gate is the bridge between iteration (managed by
`pr-iteration-flow`) and merge-authorization (the user's decision).
The agent never decides "Mark Ready" on its own — but it should
never recommend Mark-Ready without running this gate first.

## Anti-patterns

- Running the gate on EVERY commit. Section E takes 30-90 seconds;
  reserve for the final check, not per-iteration.
- Treating `⚠` as merge-blocking. Soft warnings are signals, not
  vetoes. The user decides whether to address or accept-and-log.
- Skipping Section E to "save time" before a release tag. The
  60-second cost prevents the much-larger cost of a red CI on main.
- Using this skill INSTEAD of `pr-iteration-flow`. They compose;
  iteration manages the flow, this gates the final state.
- Adding more sections ad-hoc. New checks should map to a clearly
  named risk surface that another skill doesn't already cover.

## Why this skill exists

QuantRank PRs touch a fan-out of surfaces: Pydantic schemas,
TypeScript types, schema snapshot, compute scoring, fair-price
ensemble, risk overlay, frontend rendering, CI workflows, doc
triple-files. Forgetting ANY one creates drift that ships to public
Vercel.

The verification ladder (ruff / pytest / tsc / next build /
schema-check / verify-production-output / security-check) exists to
catch each individual surface. But there's no skill that asks the
meta-question:

> "Of the things this PR touched, did we run the checks that each
> touched surface requires?"

That's this skill. It's the orchestration layer above the individual
verification skills — a checklist that turns "did I remember everything?"
into a single command.

## Related skills

- `pr-iteration-flow` — manages the Draft↔Ready flow, CI events,
  spot-check matrix. This skill is the **final gate** within that
  flow, not a replacement for it.
- `verify-production-output` — Section A-H scan of compute output
  JSON. This skill checks whether `verify-production-output` was
  RUN; it doesn't re-run it.
- `security-check` — Section A-G security audit. Same composition:
  this skill checks whether `security-check` was triggered + run
  for the relevant diff.
- `schema-check` — Pydantic↔TS bridge guard. This skill verifies
  the snapshot moved if schemas did, but defers actual validation
  to `schema-check`.
- `phase-status-bump` — 3-doc lockstep. This skill flags isolated
  edits to one of the three; defers actual update to
  `phase-status-bump`.
- `top5-rotation-audit` / `defense-scorecard` — invoked-skill checks
  that this gate's Section B looks for signals of.
