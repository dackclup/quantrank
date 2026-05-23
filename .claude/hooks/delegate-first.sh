#!/usr/bin/env bash
# delegate-first.sh — inject orchestrator-role reminder at every user turn
#
# Triggered by: UserPromptSubmit (every user message, before main agent reads it)
# Risk: zero — pure additionalContext injection, no side effects, fail-open
# Reads:  hook stdin JSON (user prompt available but we don't need it)
# Writes: stdout JSON  (hookSpecificOutput.additionalContext)
#
# Design notes:
#   - Always-fire: the reminder is short (~120 tokens) and the cost is
#     worth keeping the rule loaded every turn. Filtering by prompt
#     content would risk missing the cases that need it most.
#   - Fail-open: missing jq / unwritable stdin / etc. → exit 0 with
#     no output. The harness treats absent additionalContext as no-op.

set +e

cat <<'JSON'
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "DELEGATE-FIRST CHECK (Main agent = orchestrator, not laborer): Before doing inline work for this turn, scan .claude/agents/ — is there a sub-agent whose description matches this request? If yes → spawn it (sonnet sub-agents drain the Max-plan 'Weekly · Sonnet only' pool which is a separate, paid-for budget that is currently under-utilized). Inline work is acceptable ONLY when: (a) no sub-agent matches the task, (b) the request is a trivial lookup answerable with ≤ 1 Read + a single sentence, (c) the user explicitly says 'ทำเอง' / 'inline this' / 'don't spawn agents', OR (d) the work IS the meta-task of building/editing the agent + hook infrastructure itself. See CLAUDE.md §Auto-routing policy §Main agent role for the role definition + concrete delegation-patterns table."
  }
}
JSON

exit 0
