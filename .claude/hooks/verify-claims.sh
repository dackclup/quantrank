#!/usr/bin/env bash
# verify-claims.sh — inject a "verify high-stakes agent claims" reminder at every user turn
#
# Triggered by: UserPromptSubmit (every user message, before main agent reads it)
# Risk: zero — pure additionalContext injection, no side effects, fail-open
# Reads:  hook stdin JSON (user prompt available but we don't need it)
# Writes: stdout JSON  (hookSpecificOutput.additionalContext)
#
# Design notes:
#   - Always-fire pointer (~70 tokens), NOT a restatement: the full
#     agent-output-verifier remit + its MUST-invoke gates live in
#     CLAUDE.md §Auto-routing + .claude/agents/agent-output-verifier.md
#     (always loaded). This injection only keeps the verify-before-acting
#     reflex top-of-mind so a high-stakes agent claim never gets acted on
#     unchecked — the orchestrator still decides WHETHER a given turn hits
#     a gate (the agent is MUST-invoke at the gates, NOT per-report by
#     design — cost). Content-agnostic + always-on: filtering by prompt
#     text would risk missing the exact turns that need it.
#   - Fail-open: missing jq / unwritable stdin / etc. → exit 0 with no
#     output. The harness treats absent additionalContext as a no-op.
#   - Sibling of delegate-first.sh (the second UserPromptSubmit injector);
#     kept as a SEPARATE hook so each reminder can be tuned / disabled
#     independently via .claude/settings.json.

set +e

cat <<'JSON'
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "VERIFY-BEFORE-ACTING: before acting on a HIGH-STAKES claim emitted by any sub-agent or by yourself (a release GO, a destructive command, a Mark-Ready / merge flip, a 'Top-5 rotated' / 'coverage N%' / 'threshold matches <paper>' assertion), OR when two agent reports disagree, you MUST spawn agent-output-verifier first to re-derive the claim from ground truth. It is MUST-invoke at those gates, NOT per-report (cost). Routing: CLAUDE.md §Auto-routing."
  }
}
JSON

exit 0
