# QuantRank Agent Teams

> Recipes for the experimental **agent teams** feature (Claude Code
> ≥ v2.1.32) — coordinating multiple full Claude Code sessions (one
> **lead** + **teammates**) that share a task list and message each
> other directly. This is the COLLABORATIVE complement to the 25
> read-/write-subagents in this directory, which only report back to
> the main agent. Official docs:
> [agent-teams](https://code.claude.com/docs/en/agent-teams) ·
> [settings](https://code.claude.com/docs/en/settings).

## Teams vs subagents (read this first)

The two are **different mechanisms**, and a team **reuses subagent
definitions as teammate roles** — it does not replace them.

| | **Subagent** (the 26 files here) | **Agent team** (this doc) |
|---|---|---|
| Communication | reports back to main only; peers never talk | teammates message each other directly (mailbox) |
| Coordination | main spawns + manages everything | shared task list; teammates self-claim |
| Cost | lower (result summarized back) | higher (each teammate is a full Claude) |
| Runs on | everywhere incl. **Claude Code on the web / mobile** | desktop terminal (in-process / tmux / iTerm2) |
| Best for | focused gate checks where only the result matters | parallel work needing **debate / cross-layer ownership** |

**Rule of thumb:** subagent is the default (cheaper, runs anywhere,
drains the paid Sonnet pool). Convene a TEAM only for the handful of
scenarios below where teammates genuinely need to challenge each other
or own separate files in parallel.

## ⚠️ Mobile / web caveat

Agent teams are an **interactive desktop-terminal** feature (cycle
teammates with Shift+Down, or split panes via tmux/iTerm2). On Claude
Code on the **web / mobile** you cannot drive a live team interactively.
Therefore **every recipe below carries a "subagent fallback"** that runs
the same flow as report-back subagents — which works on web/mobile today
and drains the Sonnet pool. Use the team form when you're at a desktop;
use the fallback everywhere else. The recipes themselves are durable
repo artifacts either way.

## Enablement

Enabled project-wide via [`.claude/settings.json`](../settings.json):

```json
{ "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
```

The flag is inert unless you actually create a team, so it is safe to
leave on for web/mobile sessions. To opt out for a single session, run
`claude` with the flag unset, or remove the `env` line. Optional:
`teammateMode` (`auto` / `in-process` / `tmux`) and **Default teammate
model** in `/config` (set to *leader's model*, or pick Sonnet to drain
the Sonnet pool).

## Auto-proposal (Claude offers the team — you confirm)

You don't have to remember to ask. The `delegate-first.sh` UserPromptSubmit hook
fires every turn and reminds the orchestrator to **proactively propose** the
matching recipe when a task is team-fit. Creation still needs your one-tap
confirm (Claude never creates a team without approval), and on web/mobile the
orchestrator proposes the **subagent fallback** instead (live teams need a
desktop terminal).

| If the task looks like… | Claude auto-proposes |
|---|---|
| cross-layer build (schema + compute + UI + tests) | **Feature Squad** (or the builders as subagents on web/mobile) |
| new defense flag / threshold recalibration / new factor / scoring pillar | **Methodology Debate** (or the Flow 8 subagent sequence) |
| production broken / cron stuck / corrupt output, root cause unclear | **Incident War Room** (or the Flow 4 subagent fan-out) |
| big / risky multi-lens PR review | **PR Review Crew** (or the Flow 1 subagent gate) |
| about to act on an irreversible / expensive-to-undo claim (release GO · destructive command · cron-gating accounting-equation) | **Verification Panel** (or 3 sequential `agent-output-verifier` lens passes — majority rule) |

Decline any time ("just do it inline" / "no team") and the orchestrator drops
back to the normal subagent path.

## The 6 recipes

Teammate roles reference existing subagent definitions by name (Claude
Code honors their `tools` + `model`; the body is appended to the
teammate's system prompt). Keep teams **3-5 teammates** (docs' best
practice — beyond that, coordination overhead + diminishing returns).

> **Note on `red-team-skeptic`:** recipes mark it as an *optional
> adversary teammate*. That role is a documented FUTURE addition — it is
> **not yet created** in this directory. Until it exists, get the same
> effect by giving an existing teammate an adversarial spawn prompt
> ("your job is to disprove the others' findings").

### 1 — Methodology Debate  *(strongest team fit)*

A new defense flag / threshold recalibration / new factor, argued as a
scientific debate — proposer vs skeptic vs evidence. Matches the docs'
flagship "adversarial debate" use case and the project's
annotate-before-veto rigor.

- **Lead:** main session
- **Teammates:** `financial-engineer` (proposes the construct) ·
  `methodology-scientist` (challenges the academic prior, can REJECT) ·
  `literature-searcher` (retrieves papers to settle disputes) ·
  *(optional)* `red-team-skeptic` (tries to falsify every claim)
- **Task split:** each owns a thesis; they message each other to
  disprove, converging on a ratified prior or a rejection.
- **Subagent fallback (web/mobile):** sequence Flow 8 — spawn
  `financial-engineer`, feed its design to `methodology-scientist`, pull
  papers via `literature-searcher`. No cross-talk, but same gate.

### 2 — Incident War Room  *(competing hypotheses)*

Production cron broke / output corrupt / deploy down and root cause is
unclear. Teammates each pursue a hypothesis and actively try to disprove
the others — kills anchoring on the first plausible theory.

- **Lead:** `incident-commander` adopted by the main session
- **Teammates:** `edgar-debugger` (ingest hang / 429) ·
  `performance-engineer` (latency) · `dependency-auditor` (recent bump) ·
  `schema-sentinel` (contract drift) · *(optional)* `red-team-skeptic`
- **Task split:** one hypothesis per teammate; debate to consensus;
  lead synthesizes the timeline + mitigation.
- **Subagent fallback (web/mobile):** Flow 4 — `incident-commander`
  fans the same specialists out as report-back subagents and synthesizes.

### 3 — Feature Squad  *(cross-layer parallel build — needs the new builders)*

A feature that spans schema + compute + UI + tests, with each teammate
**owning a different layer** so they never edit the same file. This is
the one scenario the read-only roster cannot do — it needs the
write-capable builders.

- **Lead:** main session
- **Teammates:** `compute-builder` (owns `compute/**`) ·
  `frontend-builder` (owns `frontend/**`) · `test-engineer` (owns
  `tests/**`) · *(optional)* `schema-sentinel` to guard the triple
- **Task split:** by FILE OWNERSHIP (the hard boundary in each builder's
  prompt). compute-builder messages frontend-builder the instant a
  schema field changes so the Pydantic↔TS↔snapshot triple stays locked.
- **Subagent fallback (web/mobile):** the main session + user implement
  with `compute-builder` / `frontend-builder` spawned as scoped
  write-subagents one layer at a time, then `quantrank-reviewer`.

### 4 — PR Review Crew  *(multi-lens, big PRs only)*

A large PR reviewed through independent lenses simultaneously, with the
lenses challenging each other.

- **Lead:** main session
- **Teammates:** `quantrank-reviewer` (invariants) · `security-reviewer`
  (secrets/CVE) · `test-engineer` (coverage) · `defense-layer-auditor`
  (scoring impact) · *(optional)* `red-team-skeptic`
- **When:** big / risky PRs only — for a normal PR the subagent gate
  (Flow 1) is cheaper and sufficient.
- **Subagent fallback (web/mobile):** Flow 1 pre-push gate (parallel
  report-back subagents). **Default for most PRs.**

### 5 — Release Readiness Board  *(parallel checks, no debate needed)*

Pre-tag readiness across many independent checks. Listed for
completeness — these checks DON'T need to talk to each other, so the
subagent form is usually the right call.

- **Lead:** `release-captain`
- **Teammates:** `defense-layer-auditor` · `stock-detail-auditor` ·
  `security-reviewer` · `dependency-auditor` · `docs-reviewer`
- **Recommendation:** prefer the **subagent fallback** (Flow 2 ladder).
  Convene as a team only if a finding needs cross-discussion.

### 6 — Verification Panel  *(irreversible claims only)*

A 3-lens adversarial panel over a single high-stakes, expensive-to-undo
claim (a release GO, an irreversible destructive command, a production-
cron-gating "the accounting equation holds"). Kills the single-point-of-
failure of one verifier being confidently wrong. NOT for routine
verification — that's a single `agent-output-verifier` pass (cost).

- **Lead:** main session
- **Teammates:** three `agent-output-verifier` instances, each a distinct
  lens — **re-derivation** (recompute from ground truth) · **refutation**
  (assume every claim is wrong, hunt the breaker) · **completeness** (find
  the claim nobody stated). See `agent-output-verifier.md` §Panel mode.
- **Decision rule:** proceed only if ≥ 2 of 3 return TRUSTWORTHY with no
  shared CRITICAL refutation; any CRITICAL REFUTED → DO-NOT-ACT.
- **Subagent fallback (web/mobile):** the orchestrator spawns the three
  `agent-output-verifier` passes sequentially (different lens prompt each)
  and takes the majority — no cross-talk, same gate.

## Teammate protocol (shared rules)

1. **File ownership is law.** Two teammates editing one file = overwrite.
   The builders enforce `compute/**` vs `frontend/**` vs `tests/**`; in
   any team, assign disjoint file sets.
2. **Schema triple stays locked.** Whoever edits `schemas.py` messages
   whoever owns `types.ts` immediately; `schema_check` must pass before
   the task is marked complete.
3. **Message peers, not the void.** Use direct messages to challenge a
   finding or hand off a dependency; surface user-only decisions to the
   lead, who raises them via `AskUserQuestion`.
4. **Plan approval for risky tasks.** For schema bumps / scoring changes,
   require teammates to plan in read-only mode first (lead approves).
5. **Lead cleans up.** Shut down teammates, then `Clean up the team` from
   the lead only.

## Limitations (from the docs)

- Experimental; off by default. **No nested teams** (teammates can't
  spawn teams). **One team at a time** per lead. **Lead is fixed** for
  the team's life. **`/resume` / `/rewind` don't restore in-process
  teammates.** Task status can lag (mark-complete sometimes missed).
  Split panes need tmux/iTerm2 (not VS Code terminal / Windows Terminal
  / Ghostty). Teammates do NOT apply a subagent definition's `skills` /
  `mcpServers` frontmatter — they load skills + MCP from project/user
  settings like a normal session (none of our 25 defs set those, so no
  impact).

## How to start one (desktop)

Natural language to the lead, naming the recipe's roles:

```
Create an agent team for a Methodology Debate on the proposed
<flag/threshold>. Spawn financial-engineer to propose, methodology-scientist
to challenge the prior, and literature-searcher to pull papers. Have them
debate and converge on ratify-or-reject.
```

```
Create a Feature Squad to build <feature>. Spawn compute-builder for the
compute/ layer, frontend-builder for frontend/, and test-engineer for tests.
Each owns its layer; require plan approval before schema changes.
```

## Companion docs

- [`README.md`](README.md) — the 26-subagent catalog + 9 subagent flows
- [`CLAUDE.md`](../../CLAUDE.md) §Auto-routing policy — subagent routing
- the two builders: [`compute-builder.md`](compute-builder.md) ·
  [`frontend-builder.md`](frontend-builder.md)
