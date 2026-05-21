#!/usr/bin/env bash
# log-bash.sh — append every Bash command to .claude/session.log
#
# Triggered by: PostToolUse with matcher "Bash"
# Risk: ZERO — pure side-effect, cannot block tool, fails open.
# Reads:  hook stdin JSON  (tool_input.command)
# Writes: .claude/session.log  (gitignored)
#
# Design notes:
#   - Every step `|| true` so a missing jq / unwritable filesystem
#     never causes the hook to fail and disrupt Claude's flow.
#   - No stdout output → no context injection, no UI message.
#   - The log lives under .claude/ so it stays scoped to the project.

set +e

input=$(cat 2>/dev/null || echo "{}")
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null || true)

if [ -n "$cmd" ]; then
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date 2>/dev/null || echo "?")
  mkdir -p .claude 2>/dev/null || true
  printf '[%s] %s\n' "$ts" "$cmd" >> .claude/session.log 2>/dev/null || true
fi

exit 0
