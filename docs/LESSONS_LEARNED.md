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
- **สี: ห้ามตั้ง fg = สี token ของพื้นที่มันวางอยู่** (เช่น knob ขาวบนพื้นขาว → กลืนหาย).
  เช็ก contrast กับพื้น *จริง* ทั้ง **light + dark** และ **ทุก state** (selected /
  disabled / interior) — รวม **non-text 1.4.11** (ring / border / thumb ≥ 3:1) ไม่ใช่
  แค่ text. งาน "polish ทั้งหน้า" = browser audit ทั้ง surface × 2 ธีม × ทุก state
  **ก่อน** push (per-commit review จับ camouflage ไม่เจอ).
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
| For a "polish page X" task, run a **comprehensive browser contrast audit (both themes × every state: selected/disabled/interior/edge), computing real ratios for close calls, BEFORE push** | Per-commit/static review missed all 5 dark-mode camouflage bugs in #408/#409; the comprehensive whole-surface pass + the user caught them. One pass beats N round-trips. |
| Verify pseudo-element styles (`::thumb`, `::placeholder`) via **screenshot + known token values**, not `getComputedStyle` | Headless `getComputedStyle` returns defaults/`none`/transparent for pseudo-elements. |

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
| Set an element's color = the **same token as the surface it sits on** (a `bg-white` knob on a white panel; a `dark:bg-slate-900` thumb on the slate-900 panel) | It camouflages — visible only via its border. Use the CONTRASTING value (dark-on-light / light-on-dark). |
| Review contrast only in **light mode / the default state / from static code** | Camouflage hides in dark + selected/disabled/interior. WCAG **1.4.11** (non-text: rings/borders/thumbs ≥ 3:1) is the repeatedly-missed standard, not just 1.4.3 text. |

## Mistakes log

### 2026-06-26 — doc count-drift caught by an LLM 3× → determinized into a guard (`agent-output-verifier` work, #621/#622)

**What happened:** across the two PRs that added `agent-output-verifier`,
the *only* real defects were **hardcoded structural counts going stale** —
"25 subagents" not bumped to 26, "5 opus"→6, "3 hooks"→4, "8 flows"→9,
plus AGENTS.md "three hooks" prose. The `docs-reviewer` sub-agent (an LLM)
caught these — but it took **three separate review rounds** to catch them
all, and an LLM catching a purely mechanical fact is probabilistic: the
next session it could miss one.

**Root cause:** a deterministic fact (count of files / frontmatter values)
was being checked by probabilistic judgment. Wrong tool for the job.

**The ratchet (the fix that makes it never recur):** `tools/check_agent_hook_consistency.py`
derives every structural count from the filesystem + frontmatter and asserts
the doc anchors match — wired into CI (`ci.yml`) + `tools/preflight.py`. The
count-drift class is now caught **deterministically, every time, for free**.
No number lives in the guard; adding an agent/hook/flow and updating the docs
makes it pass automatically.

**The rule — Error→regression ratchet:** when an error is caught (by a
reviewer, an agent, CI, or production), and the error class is *mechanical*
(a count, a format, a sync, an invariant), **convert it into a deterministic
guard — a test or a `tools/` check — in the SAME fixing PR**, so the
probabilistic catch becomes a deterministic one. LLM review is the safety
net for the *novel* error; it must not be the standing defense for a
*mechanical* one. This is the path that ratchets the systematic error classes
toward ~0. (Promoted to CLAUDE.md §Conventions "Error→regression ratchet".)

### 2026-06-04 — filter-page color/UX polish (`$impeccable`, #408 + #409)

A multi-round `$impeccable polish` of the filter page surfaced ONE recurring
bug class — **a foreground element whose color ≈ its background, so it
camouflaged** — *five* times, every one in **dark mode** and/or a
**non-default state**, all missed by static + per-commit review, three of
them found by the **user** one at a time. This is a code/domain (design-system)
lesson as much as a process one; the actionable rule is mirrored in
`.claude/skills/frontend-design-system/SKILL.md` §"Anti-patterns checklist".

1. **Never set an element's color to the SAME token as the surface it sits
   on.** The composite-score slider thumbs were `bg-white dark:bg-slate-900`
   — the *exact* color of the panel they sit on (`bg-white dark:bg-slate-900`)
   — so the handles were invisible (only the 2px border hinted at them).
   *Fix:* the knob FILL must CONTRAST the panel (dark knob on a light surface /
   light knob on a dark surface), with the border as the INVERSE so it still
   separates from the same-colored active-fill bar.
2. **Check WCAG 1.4.11 (non-text contrast, ≥ 3:1) on borders / rings / thumbs /
   icons — not just 1.4.3 (text, ≥ 4.5:1).** Almost every miss was *non-text*:
   the dark unselected-chip ring `slate-700`-on-`slate-800` = **1.41:1**
   (invisible boundary); the dark disabled "Clear all" `slate-600`-on-`slate-900`
   = **2.36:1**. *Fix:* `slate-500` is the floor for a neutral ring/text on a
   `slate-800/900` dark surface (≈ 3.0–3.8:1).
3. **Dark mode is where camouflage hides.** All five read OK (or less-bad) in
   light and failed in dark — the dark surface sits close in luminance to the
   muted slate tokens. *Always do a dark-mode pass.*
4. **Test the NON-DEFAULT states.** The bugs lived in SELECTED (not unselected),
   DISABLED (not enabled), INTERIOR slider positions (not the 0/100 default), and
   the SLATE-TONED options (Near fair / Hold) — never the default. A selected
   toggle was indistinguishable from unselected in dark because the pale tint ≈
   the unselected slate AND the slate-toned tones ARE slate. *Fix:* drive every
   state (selected / disabled / interior / edge) × theme in a real browser.
5. **A "selected / active" signal must be EXCLUSIVE to that state.** The chip dot
   rendered on BOTH selected and unselected, so it carried zero state info; the
   differentiator (a 2px ring + `font-semibold`) had to be added as a
   selected-only signal — and `aria-pressed` to carry it to screen readers.
6. **Raising an adjacent element's contrast can erode a pair's gap.** Making the
   unselected ring visible (1.41 → 3.07:1) narrowed its distance from the
   *selected* 2px ring of the same color — had to re-verify the slate-toned
   selected still reads (bold + 2px carries it). When you bump one element,
   re-check the pairs that relied on the old gap.
7. **Process: per-commit / static review missed all five; only a COMPREHENSIVE
   whole-surface browser pass (both themes × every state) caught the rest — and
   the user caught 3 first.** *Fix:* for a "polish page X" task, run the holistic
   multi-theme / multi-state browser contrast audit UP FRONT (computing actual
   ratios for close calls), not per-commit. It would have surfaced all five at
   once instead of across five round-trips.
8. **`getComputedStyle` can't read pseudo-element styles** (`::-webkit-slider-thumb`,
   `::placeholder`, `:focus-visible::thumb`) in headless — it returns
   defaults / `none` / transparent. *Fix:* verify those via screenshot + the
   known token values, not the pseudo's computed style.
9. **Tracked debt:** the same `dark:ring-slate-700`-on-`slate-800` = 1.41:1 ring
   is the *app-wide* neutral-chip default (`NEUTRAL_CHIP_RG` /
   `ACTIVE_FILTER_CHIP_TONE` → sector chips + active-filter chips everywhere).
   Only the scoped `UNSELECTED_CHIP` (filter toggles) was fixed; the app-wide bump
   is DEFERRED (ScoreBadge / table / detail blast radius — the #401-class trap,
   its own pass). Also deferred: the 4 chip-group heading `<label>`s are
   semantically inert (need `<span>` + `role=group`).

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

## 2026-06-10 — bare `pytest` resolves to the SYSTEM python in the remote sandbox

In the Claude Code remote execution environment, `which pytest` → `/root/.local/bin/pytest`
(system python 3.11, NO project deps — `ModuleNotFoundError: pandas` across ~63 collection
errors) while `which python` → `/usr/local/bin/python` (full project env). A sub-agent
(test-engineer, issue #441 PR-1) ran bare `pytest`, hit the wall of import errors, and
mislabeled them "missing optional dependencies / pre-existing" — the second mislabel of this
shape (first: #438). Rule: in this environment ALWAYS run `python -m pytest tests/ -m "not
network"`, and treat any "broad pre-existing failure" claim from a sub-agent as unverified
until the orchestrator reproduces it with `python -m pytest`. (The only GENUINE pre-existing
sandbox gap is the 2 `openassetpricing` osap test modules — the `[factors]` extra isn't
installed here; CI installs it.)

---
*Add the next session's lessons above this line.*
