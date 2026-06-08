#!/usr/bin/env bash
# delegate-first.sh — inject orchestrator-role + agent-team auto-propose reminder at every user turn
#
# Triggered by: UserPromptSubmit (every user message, before main agent reads it)
# Risk: zero — pure additionalContext injection, no side effects, fail-open
# Reads:  hook stdin JSON (user prompt available but we don't need it)
# Writes: stdout JSON  (hookSpecificOutput.additionalContext)
#
# Design notes:
#   - Always-fire: the reminder is short (~140 tokens — the delegate-first
#     pointer + an agent-team auto-propose pointer; the full (a)-(d) rule
#     + the cue→recipe table live in CLAUDE.md §Auto-routing + TEAMS.md
#     §Auto-proposal, always loaded, so this injection is a pointer not a
#     restatement). Content-agnostic + always-on by design: filtering by
#     prompt text would risk missing cases (incl. team-fit ones) that need it.
#   - Fail-open: missing jq / unwritable stdin / etc. → exit 0 with
#     no output. The harness treats absent additionalContext as no-op.

set +e

cat <<'JSON'
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "DELEGATE-FIRST: you are the orchestrator. Default = spawn the matching .claude/agents/ sub-agent (drains the paid, idle Sonnet pool), not inline work. Inline ONLY if no agent matches / trivial 1-Read lookup / user said do-it-inline / it is agent-infra meta-work. AGENT-TEAM AUTO-PROPOSE: do NOT wait to be asked — when the task is team-fit (cross-layer build · new-flag/threshold/factor debate · root-cause-unclear incident · big multi-lens PR review) proactively PROPOSE the matching recipe before going inline; it is propose-not-create (the feature needs the user confirm) and on web/mobile propose the subagent fallback (same flow, runs there). Cues+recipes: .claude/agents/TEAMS.md §Auto-proposal. Full (a)-(d) rule + delegation table: CLAUDE.md §Auto-routing policy."
  }
}
JSON

exit 0
