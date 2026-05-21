# QuantRank Subagents

> `.claude/agents/` — project-specific Claude Code subagents tuned to
> QuantRank's invariants. Subagents are spawned via the `Agent` tool
> and run in their own context window — distinct from skills under
> `.claude/skills/` (which are prompt packs invoked by the main agent
> via the `Skill` tool).

## When to use a subagent vs a skill

| Pattern | Reach for |
|---|---|
| Context-isolated work (don't pollute main session) | Subagent |
| Parallel investigation (multiple files / multiple queries) | Subagent |
| Read-only review with focused tool allowlist | Subagent |
| Single in-session expansion of project knowledge | Skill |
| Workflow harness (PR iteration, phase bump) | Skill |
| One-shot lookup / search | Direct `Read` / `Grep` |

When a task fits both, prefer the **skill** if it already exists — 42
skills are loaded each session, so the main agent already has the
trigger map. Subagents add value where context isolation or parallelism
specifically helps.

## The current set (4)

| Subagent | Trigger | Model | Tools |
|---|---|---|---|
| [`quantrank-reviewer`](quantrank-reviewer.md) | After non-trivial edits in `compute/` / `frontend/` / `tests/`; before flipping a PR to Ready | opus | Read, Grep, Glob, Bash |
| [`schema-sentinel`](schema-sentinel.md) | When `schemas.py` / `types.ts` / `schema-snapshot.json` changes; CI schema-drift failures | haiku | Read, Bash, Grep |
| [`defense-layer-auditor`](defense-layer-auditor.md) | After scoring / valuation changes; after weekly cron lands; before PR Ready-flip on scoring touches | sonnet | Read, Bash, Grep, Glob |
| [`edgar-debugger`](edgar-debugger.md) | SEC EDGAR ingest test failures; live-run hangs; rate-limit / edgartools drift errors | sonnet | Read, Bash, Grep, Glob |

## How auto-invocation works

Claude Code reads the `description:` line of each agent file and routes
work that matches. The descriptions in this set use the **TRIGGER when /
Use PROACTIVELY** pattern (mirroring the project's vendored-skill
description sharpening from PR #157) so the main agent picks them up on
the relevant cues:

- `quantrank-reviewer` fires on diff cues (edit + push intent)
- `schema-sentinel` fires on schema-triple cues
- `defense-layer-auditor` fires on "verify the output" / scoring-edit cues
- `edgar-debugger` fires on EDGAR / ingest / throttling cues

The user can also invoke any subagent explicitly: "use the
defense-layer-auditor to check the latest run", and the main agent will
spawn it with that scope.

## Authoring conventions (when adding a new subagent)

1. **One job per agent.** A reviewer doesn't also write tests; a debugger
   doesn't also fix code. Read-only by default; promote to write only when
   the task inherently requires it.
2. **Sharp `description:`.** Match the vendored-skill TRIGGER discipline
   from `THIRD_PARTY_NOTICES.md` "Description divergence" — concrete
   keywords ("verify the output", "ตรวจ output", "check the latest run"),
   false-positive guardrails, and a fail-fast verdict format.
3. **Model selection:**
   - `haiku` — deterministic checks (schema drift, lint-style guards)
   - `sonnet` — multi-step audits with judgment (defense scorecard, debug)
   - `opus` — full code review where breadth + nuance matter
4. **Tool allowlist.** Restrict to what the agent actually needs. A code
   reviewer doesn't need `Edit` or `Write`; an auditor doesn't need
   `Edit` either. Explicit allowlists reduce blast radius.
5. **Project anchoring.** Every subagent references the relevant
   `CLAUDE.md` section + the corresponding skill so it stays aligned
   with the project's invariants as those evolve.
6. **Output format pinned.** Always specify the exact reply shape — the
   user is going to act on the agent's output, not read it as prose.

## Companion docs

- [`CLAUDE.md`](../../CLAUDE.md) §Conventions — project invariants
- [`AGENTS.md`](../../AGENTS.md) §Boundaries — what subagents may / must
  not do
- [`SKILL.md`](../../SKILL.md) — Rules 1-18 (the invariants every
  subagent enforces)
- [`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md) — vendor /
  license posture for any future vendored subagents (none today)
