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
    "additionalContext": "DELEGATE-FIRST: orchestrator, not laborer — default = spawn the matching .claude/agents/ sub-agent; inline only per the (a)-(e) exceptions. Routing table + exceptions: CLAUDE.md §Auto-routing. Team-fit task → PROPOSE the matching TEAMS.md §Auto-proposal recipe (propose-not-create; web/mobile → subagent fallback)."
  }
}
JSON

exit 0
