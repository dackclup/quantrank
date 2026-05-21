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

## The current set (8)

Organized into two tiers — **core** (always loaded, narrow project
invariants) and **enterprise** (broader engineering-org roles that
wrap the project's existing skills into auto-routable surfaces):

### Core tier (4)

| Subagent | Trigger | Model | Tools |
|---|---|---|---|
| [`quantrank-reviewer`](quantrank-reviewer.md) | After non-trivial edits in `compute/` / `frontend/` / `tests/`; before flipping a PR to Ready | opus | Read, Grep, Glob, Bash |
| [`schema-sentinel`](schema-sentinel.md) | When `schemas.py` / `types.ts` / `schema-snapshot.json` changes; CI schema-drift failures | sonnet | Read, Bash, Grep |
| [`defense-layer-auditor`](defense-layer-auditor.md) | After scoring / valuation changes; after weekly cron lands; before PR Ready-flip on scoring touches | sonnet | Read, Bash, Grep, Glob |
| [`edgar-debugger`](edgar-debugger.md) | SEC EDGAR ingest test failures; live-run hangs; rate-limit / edgartools drift errors | sonnet | Read, Bash, Grep, Glob |

### Enterprise tier (4)

| Subagent | Enterprise role analogue | Trigger | Model | Tools |
|---|---|---|---|---|
| [`security-reviewer`](security-reviewer.md) | AppSec / Security engineer | Before release tags; CI workflow edits; new deps; "scan for CVE" / "ตรวจ security" | sonnet | Read, Bash, Grep, Glob |
| [`frontend-design-reviewer`](frontend-design-reviewer.md) | Design system / UI lead | Edits under `frontend/components/` / `frontend/app/`; new badge / chip / color; "doesn't match the rest" | sonnet | Read, Grep, Glob, Bash |
| [`release-captain`](release-captain.md) | Release manager | "tag release" / "cut a release" / "release vX.Y.Z" / after phase epic merge | opus | Read, Bash, Grep, Glob |
| [`phase-coordinator`](phase-coordinator.md) | Eng-program manager / docs PM | Before branch creation; before PR open / Ready-flip; after phase / sub-PR completes | sonnet | Read, Bash, Grep, Glob |

The two tiers reflect QuantRank's actual workload distribution: core
agents fire on most PRs (compute / schema / scoring touches happen
weekly); enterprise agents fire at specific lifecycle moments (release
cuts ~monthly, security baseline scans before release, frontend reviews
when UI is touched).

## How auto-invocation works

Claude Code reads the `description:` line of each agent file and routes
work that matches. The descriptions in this set use the **TRIGGER when /
Use PROACTIVELY** pattern (mirroring the project's vendored-skill
description sharpening from PR #157) so the main agent picks them up on
the relevant cues:

Core tier:
- `quantrank-reviewer` fires on diff cues (edit + push intent)
- `schema-sentinel` fires on schema-triple cues
- `defense-layer-auditor` fires on "verify the output" / scoring-edit cues
- `edgar-debugger` fires on EDGAR / ingest / throttling cues

Enterprise tier:
- `security-reviewer` fires on release-tag / CI-workflow-edit / new-dep cues
- `frontend-design-reviewer` fires on `frontend/components/` diff cues
- `release-captain` fires on "tag release" / "cut release" cues
- `phase-coordinator` fires on branch / PR-open / phase-completion cues

The user can also invoke any subagent explicitly: "use the
defense-layer-auditor to check the latest run", and the main agent will
spawn it with that scope.

### Wrap-don't-duplicate pattern

Enterprise-tier agents do NOT re-implement the project's existing
skills — they **wrap** them as auto-routing surfaces. Each enterprise
agent's first action is to read the corresponding skill's `SKILL.md`:

| Enterprise agent | Wrapped skill(s) |
|---|---|
| `security-reviewer` | `.claude/skills/security-check/` |
| `frontend-design-reviewer` | `.claude/skills/frontend-design-system/` |
| `release-captain` | `.claude/skills/release-tag/` (delegates to `phase-coordinator` for doc bumps) |
| `phase-coordinator` | `.claude/skills/branch-collision-check/`, `claude-md-lockstep-check/`, `phase-status-bump/` |

This keeps the skills as the source-of-truth playbooks. When the skill
updates, the subagent benefits automatically because it reads the skill
each invocation.

## Authoring conventions (when adding a new subagent)

1. **One job per agent.** A reviewer doesn't also write tests; a debugger
   doesn't also fix code. Read-only by default; promote to write only when
   the task inherently requires it.
2. **Sharp `description:`.** Match the vendored-skill TRIGGER discipline
   from `THIRD_PARTY_NOTICES.md` "Description divergence" — concrete
   keywords ("verify the output", "ตรวจ output", "check the latest run"),
   false-positive guardrails, and a fail-fast verdict format.
3. **Model selection (this project uses `opus` + `sonnet` only — no `haiku`):**
   - `sonnet` — default for deterministic checks (schema drift) AND
     multi-step audits with judgment (defense scorecard, debug).
   - `opus` — full code review where breadth + nuance matter (one or
     two passes over a multi-file diff, weighing project-specific
     conventions against the change).
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
