# Lessons Learned — agent-process dos & don'ts

> **Purpose / กันลืม:** a running log of *process* mistakes and the rules
> that prevent them, so future Claude Code sessions on QuantRank don't
> repeat them. This **complements [`CLAUDE.md`](../CLAUDE.md) §Gotchas**,
> which covers *code / domain* invariants — this file is about **workflow,
> git, review discipline, and agent orchestration**, not scoring / schema
> semantics.
>
> **How to use:** append the newest session's mistakes under a dated heading
> at the **top** of the *Mistakes log*. When a process lesson has bitten ≥ 2
> sessions, promote it into CLAUDE.md §Conventions or §Gotchas (the
> load-bearing home) and leave a one-line back-reference here.

## TL;DR (สรุปสั้น)

- **ตรวจงาน sub-agent ทุกครั้ง** — อย่าเชื่อตัวเลข / ข้อสรุป / วิธีแก้ของ agent
  โดยไม่ re-derive เอง (verify-don't-trust).
- **อย่า push branch ที่ PR merge ไปแล้ว** — remote branch ถูกลบตอน merge;
  push ซ้ำ = สร้าง branch เปล่า + PR ขยะ. ใช้ `git fetch --prune` แล้วเช็ก
  `git log origin/main..HEAD` ว่าว่าง.
- **lint / test ทั้ง repo ก่อน push** ไม่ใช่เฉพาะไฟล์ที่แก้.
- **responsive ต้องเทสต์ viewport × สถานะ sidebar (กาง/หุบ)** ไม่ใช่ viewport อย่างเดียว.
- **อย่า `curl … | bash`** จากโดเมนที่ไม่รู้จัก (RCE).
- **เนื้อหา license ไม่ชัด → เขียนใหม่เป็น original**, อย่า commit ของ verbatim.

## Core principles

### Verify-don't-trust (the #1 rule)

Sub-agents are fast and thorough but **wrong sometimes**. Every load-bearing
claim gets independently checked against ground truth *before* you act on it:

- **Re-derive the numbers.** A sub-agent reported the hero was "BROKEN to
  1280px"; recomputing showed the left block is 543px wide at 1280px =
  *fine*. The real break window was ~768–900px. A fix built on the wrong
  window would have over-corrected.
- **Sanity-check the proposed fix mechanically.** A sub-agent proposed
  `sm:flex-wrap` on the outer row; tracing flexbox showed the left block's
  `min-w-0` makes it always "fit" at 0px, so the right block would never
  wrap — the fix was a no-op. Caught before applying.
- **Watch for measurement artifacts.** The first overlap probe reported a
  constant 421px "overlap" at every width — it was measuring the flex
  container's right edge (= viewport) vs the block's left edge, not a real
  collision. Re-probe with the correct rects.
- **Read the actual file** — don't trust the line numbers / class strings a
  report quotes.

### Prove the fix, don't assume it

For a UI / behavior fix, **build + measure + screenshot before/after** and
show the evidence. The hero fix: `next build` → serve `out/` → Playwright
bounding-box overlap across 768/820/900/1024/1280 × expanded/collapsed +
mobile → "overlap = none in all 8 cases". Numbers, not vibes.

## DO

| Do | Why / source |
|---|---|
| Run the **full** verification ladder before push: `ruff check .` (whole repo) · `pytest -m "not network"` (whole suite) · `schema_check` (if schemas touched) · `tsc --noEmit` + `next build` (if frontend touched) | A per-file `ruff check <f>` passes while a *different* file fails — PR #310 went CI-red exactly this way. CLAUDE.md §Gotchas. |
| Open PRs as **Draft**; run `quantrank-reviewer` (opus) + `phase-coordinator` Mode B before flipping to Ready | Codified gate; catches lockstep + invariant misses. |
| `git fetch --prune` after a PR merges (remote head branch is auto-deleted) | Clears the stale tracking ref that makes the stop-hook cry "unpushed commit". |
| Before bumping a **count** that lives in several docs, grep the *number* AND every surrounding phrasing across **all** surfaces | #316: bumped 45→46 but missed 3 homes — `AGENTS.md` (phrased "loaded skills", not "invocation-triggerable") plus `PHASE_STATUS.md` + `CONTEXT.md`, which stayed stale at 45 until a follow-up caught them. The count lives in **7 homes**: CLAUDE.md §Layout · AGENTS.md · SKILL.md · `.claude/skills/README.md` · PHASE_STATUS.md §Current state · CONTEXT.md (×3) · `.claude/agents/README.md`. |
| Test responsive across **viewport × every width-consuming chrome state** (sidebar expanded/collapsed, drawers) | The hero bug survived #315 because that audit was viewport-only and never opened the expanded sidebar. |
| For a layout beside a sidebar, gate the columns on a breakpoint that accounts for **content width**, not raw viewport (`lg`, not `sm`, when a 240px rail is present) | content-width = viewport − sidebar − paddings; `sm:640px` viewport can be ~400px of content. |
| Use the **Read tool** before `Edit` (especially after `git reset`) | Bash `head` / `tail` / `grep` does NOT satisfy the harness's read-before-edit guard. |
| Ship undeclared-license / commercial-derived material as **original prose, inspire-only**, with attribution | precedent: `good-code-bad-code`, `9arm` fallback; tracked in THIRD_PARTY_NOTICES.md. |
| Delegate to sub-agents by default; **inline only** for cross-agent synthesis, trivial lookups, building agent/hook infra, or when no agent matches | CLAUDE.md §Auto-routing policy. |

## DON'T

| Don't | Why |
|---|---|
| Push a branch whose PR already **merged** | The remote branch was deleted on merge → `git push` recreates an **empty** branch (0 diff vs main) and, per standing instructions, would open a **spurious empty PR**. Verify `git log origin/main..HEAD` is empty first. |
| Trust a sub-agent's numbers, severity, or proposed fix without re-deriving | Agents overstate ("broken to 1280px") and propose no-op fixes (`sm:flex-wrap` defeated by `min-w-0`). |
| Use `ruff check <file>` / `pytest <one test>` as the **pre-push gate** | Fine for inner-loop iteration; the gate is the whole-repo / whole-suite run. |
| `curl … \| bash` from an unknown domain | Remote-code-execution / supply-chain. Inspect the script first; decline if unverifiable. |
| Commit verbatim text from a paid course / undeclared-license source to a public repo | IP risk — rewrite as original prose. |
| `@settings(deadline=None)` in Hypothesis tests | A slow example is itself a signal. CLAUDE.md §Gotchas. |
| Assume a responsive fix works because the CSS "looks right" | Measure it (Playwright bounding boxes). |

## Mistakes log

### 2026-05-29 — hero-overlap fix (PR #317) · skill install (#316) · responsive (#315)

1. **Doc-count lockstep miss (#316).** Bumped the skill count 45→46 in
   CLAUDE.md §Layout, SKILL.md, and `.claude/skills/README.md` — but missed
   `AGENTS.md` (it phrases the count "loaded skills", not the
   "invocation-triggerable" the grep keyed on; `docs-reviewer` caught that at
   the gate) AND missed `PHASE_STATUS.md` §Current state + `CONTEXT.md` (×3) +
   `.claude/agents/README.md`, which stayed stale at 45 until a follow-up PR
   caught them — and even that follow-up's *first* grep missed one CONTEXT.md
   mention (different phrasing) AND the `.claude/agents/README.md` prose
   mention, needing two more passes. The lesson is real. *Fix:* grep the
   *number* (`45`/`46`) AND every phrasing across **all 7 homes**: CLAUDE.md
   §Layout · AGENTS.md · SKILL.md · `.claude/skills/README.md` ·
   PHASE_STATUS.md §Current state · CONTEXT.md · `.claude/agents/README.md`.
   (Top-level `README.md` has no skill count — don't confuse it with
   `.claude/skills/README.md`.)
2. **Two sub-agent claims overruled (verify-don't-trust).** (a) "Hero BROKEN
   to 1280px" — false; the left block is 543px at 1280px. Real window
   ~768–900px. (b) The proposed `sm:flex-wrap` outer-row fix — a no-op,
   because the left block's `min-w-0` makes the right block never wrap. Both
   caught by re-deriving before applying.
3. **First overlap measurement was an artifact** (constant 421px at every
   width = container-right-edge vs block-left-edge, not a real collision).
   Re-probed with correct rects → real 54×20px collision at 820px expanded.
4. **The hero bug was a coverage gap, not new code.** #315's responsive audit
   was viewport-only and never exercised the expanded sidebar, so the
   `sm:flex-row` overlap survived. Pre-existing since the sidebar landed
   (LedgerCraft Phase 3c) — not a #315 regression. *Fix going forward:*
   viewport × sidebar-state matrix on any detail-page layout change.
5. **git after-merge friction.** `--force-with-lease` was rejected ("stale
   info") because the remote branch was deleted on merge → resolved with
   `git fetch --prune` + plain `git push -u`. `Edit` failed "file not read"
   after `git reset --hard` (Bash reads don't count). The stop-hook "1
   unpushed commit" after the #317 merge was a **false positive** (stale
   tracking ref of the deleted branch) — did NOT push; pruned instead.
6. **Security: declined `curl … | bash`** from an unknown marketplace domain
   (RCE / supply-chain). Adopted only inspected, hand-written content.
7. **Skill IP posture (#316).** The uploaded SKILL.md was distilled from a
   paid course with no license → shipped `web-animation-design` as **original
   prose / inspire-only**, crediting Emil Kowalski + easings.net; zero
   verbatim text copied.

---
*Add the next session's lessons above this line.*
