#!/usr/bin/env bash
# delegate-first.sh — inject orchestrator-role reminder at every user turn
#
# Triggered by: UserPromptSubmit (every user message, before main agent reads it)
# Risk: zero — pure additionalContext injection, no side effects, fail-open
# Reads:  hook stdin JSON (user prompt available but we don't need it)
# Writes: stdout JSON  (hookSpecificOutput.additionalContext)
#
# Design notes:
#   - Always-fire: the reminder is short (~80 tokens, trimmed 2026-06-03
#     from the prior ~220-token verbatim copy — the full (a)-(d) rule
#     lives in CLAUDE.md §Auto-routing, which is always loaded, so this
#     injection only needs to be a pointer, not a restatement).
#     Filtering by prompt content would risk missing cases that need it.
#   - Fail-open: missing jq / unwritable stdin / etc. → exit 0 with
#     no output. The harness treats absent additionalContext as no-op.

set +e

cat <<'JSON'
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "DELEGATE-FIRST: you are the orchestrator. Default = spawn the matching .claude/agents/ sub-agent (drains the paid, idle Sonnet pool), not inline work. Inline ONLY if no agent matches / trivial 1-Read lookup / user said do-it-inline / it is agent-infra meta-work. Full (a)-(d) rule + delegation table: CLAUDE.md §Auto-routing policy."
  }
}
JSON

exit 0
