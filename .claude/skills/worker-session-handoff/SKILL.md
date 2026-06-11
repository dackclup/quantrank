---
name: worker-session-handoff
description: Generate a paste-ready handoff prompt for a parallel worker session (branch → scoped implementation → Draft PR → report-back), pre-populating the constraint locks (Rule 16 / Rule 18 / schema triple / no-merge), the verification ladder, and the report structure. TRIGGER: "prompt คำสั่ง" / "ส่ง session ใหม่" / "เขียน handoff" / "เขียน prompt ให้ session ใหม่" / "spawn a worker session", or a multi-file task earmarked "for the worker" / "in parallel".
---

# worker-session-handoff

A QuantRank-specific skill that produces the standard handoff prompt
this session uses every time the user wants parallel implementation
work. Codifies the constraint locks + verification ladder + report-
back structure that appeared verbatim across PRs #123, #124, #127,
#128, #129, #131 — so the user copies ONE block instead of editing
five template snippets.

## When to use

Inline implementation is the default. Spawn a worker session via this
skill only when:

- The task spans ≥ 2 files AND ≥ 50 LOC of code logic (not just docs)
- OR the task introduces a new external dep / data integration
- OR the work needs verification on a clean branch off `main` (audit
  PRs, schema bumps, observability surfaces)
- OR the user explicitly asked for a parallel session

Stay inline when:

- The change is ≤ 50 LOC across a single file
- The change is a typo / single-comment edit / README polish
- The user is still iterating on requirements (handoff lock-in too
  early wastes scope back-and-forth)

## Constraint lock library

These constraints appear in EVERY handoff prompt unless the user
explicitly authorizes a deviation. The skill pre-populates them so
the worker session can't accidentally skip one.

| Lock | Source | Why |
|---|---|---|
| `compute_composite()` / `PHASE3_WEIGHTS` sum=1.0 | composite.py:43-45 | Pillar-weight invariant — any drift breaks composite-score domain |
| Rule 16: Top-5 rank by raw `composite_score` | SKILL.md L428 | Annotate-only defense layer; never modify rank source |
| Rule 18: Observability-before-wiring | SKILL.md L491 (new in PR #129) | Diagnostic surface ships ≥ 1 cron before production wiring |
| No push / force-push to main | CLAUDE.md, branch protection | Standard branch hygiene |
| No PR self-merge | pr-iteration-flow precedent | Draft → CI green → Mark-Ready → user authorize → merge |
| No `--no-verify` (skip pre-commit) | CLAUDE.md | Fix the root cause; don't suppress the signal |
| No `workflow_dispatch` on `compute-rankings.yml` | User runs from mobile | Production cron is user-triggered only |
| Schema triple lockstep | `compute/output/schemas.py` + `frontend/lib/types.ts` + `frontend/lib/schema-snapshot.json` | CI guard fails build on drift |

Task-specific locks (added per prompt): "don't touch `PHASE_STATUS.md`",
"defer DSR investigation to Part 3", etc.

## Anti-pattern: paste-loop avoidance

The user copies the handoff into a new chat. If the handoff is split
across multiple code blocks, the user has to copy 4-5 times. **Always
emit the entire handoff as ONE outer code block** using a triple-
backtick fence with a language tag of ` text` (or no tag) so the
inner triple-backticks pass through verbatim.

A handoff prompt that worked once must work the second time without
re-pasting context. PR #123 (closed as duplicate) is a related — but
distinct — paste-loop failure mode where a worker session re-pasted
the original plan instead of opening a Draft. The constraint lock
"no PR self-merge + no force-push to main" guards against that
specific failure.

## Template (paste-ready, single outer code block)

````
═══ MOTIVATION ═══

[Why this work? What bug / PR / incident / production-cron diagnostic
motivates the task. Cite specific commit SHAs, PR numbers, file paths.]

═══ SCOPE — N sub-tasks ═══

### 1. [Sub-task title]
[Detail. Include file paths, function names, code examples for
non-trivial steps.]

### 2. [Next sub-task...]
[...]

═══ CONSTRAINTS — ห้ามทำ ═══

- ห้ามแตะ compute_composite() / PHASE3_WEIGHTS (sum=1.0 lock at
  composite.py:43-45) — [or note if THIS PR's scope authorizes touch]
- Rule 16: Top-5 rank ด้วย raw composite_score
- Rule 18 (observability-before-wiring): ถ้า PR เพิ่ม external-data
  consumption → diagnostic Metadata field ต้องชิป ≥ 1 cron ก่อน
  production wiring
- ห้าม push ตรงไป main / force-push main
- ห้าม merge PR เอง — pattern: draft → CI green → flip ready → รอ
  user authorize → merge
- ห้าม skip pre-commit hooks (--no-verify)
- ห้าม trigger workflow_dispatch compute-rankings.yml
- Schema triple lockstep — ถ้าแตะ schemas.py / types.ts → ทั้งสาม
  ต้องขยับพร้อมกัน (Pydantic + types.ts + snapshot.json)
- [Task-specific locks]

═══ BRANCH + PR ═══

Branch: <descriptive-kebab-case> (base: main)

PR title: <conventional-commit-prefix>: <summary> (#<issue>)

PR body ต้องมี:
- "Closes #<issue>" หรือ "Part of #<epic>"
- [Task-specific sections]

═══ VERIFICATION LADDER ═══

1. ruff check . → green
2. pytest tests/ -m "not network" → no regress (959 baseline at
   commit b16fc5b8 — update as test count moves)
3. python -m compute.output.schema_check → in sync
4. python tools/check_doc_test_counts.py → exit 0
5. python tools/check_branch_collisions.py "<scope keyword>" → check
   for parallel work
6. [Task-specific verification]

═══ REPORT BACK ═══

หลัง PR open + CI green ส่งกลับมา N อย่าง:
1. PR number + URL
2. [Task-specific data]
3. [Task-specific verdict]

จบงาน = PR Draft + CI green + รายงานกลับ. อย่า merge เอง.

เริ่มได้เลย.
````

## Reference invocations

- "ขอ prompt คำสั่ง สำหรับ <task>" → emit a fresh handoff
- "เขียน handoff ให้ session ใหม่ ทำ <task>" → emit
- "ส่ง session ใหม่ แก้ <bug>" → emit
- "in parallel — open <task> from a worker" → emit

## QuantRank precedents

- PR #124 (Phase 4h.2 Part 2, multi-port OSAP adapter) — handoff
  produced a 10-file PR with diagnostic surface + accounting
  invariant test, reported back accounting equation pre/post
- PR #127 (Hypothesis property tests) — handoff included sanity-
  break verification ("temporarily revert X, confirm property test
  catches, then revert") that surfaced as the most rigorous CI
  signal in the epic-#125 series
- PR #131 (this skill's neighbor: branch-collision check) — handoff
  pre-empted PR #123-style duplicate work via a preflight script

## Long-form description (moved out of frontmatter 2026-06-11 token drain)

Generate a paste-ready handoff prompt for a parallel Claude Code
worker session that will create a branch, implement scoped work, open a
Draft PR, and report back. Pre-populates constraint locks (Rule 16, Rule 18,
schema triple, no-merge), the standard verification ladder, and a
report-back structure so the user copies one block instead of editing five
template snippets. TRIGGER when the user asks "prompt คำสั่ง" / "ส่ง
session ใหม่" / "เขียน handoff" / "เขียน prompt ให้ session ใหม่" /
"spawn a worker session" / "open this from a worker" after a plan has
been approved. ALSO trigger when the user describes a multi-file
implementation task and says "for the worker" / "in parallel". SKIP for
trivial edits doable inline in ≤5 minutes (single-line fixes, typo
changes, comment polish) — handoff overhead dominates.
