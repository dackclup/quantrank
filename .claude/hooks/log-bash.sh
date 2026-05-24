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
#   - Inline-credential scrub (added 2026-05-24 PR #229) redacts the
#     value half of common token formats before writing, so an
#     accidental `cat .claude/session.log` during a screen-share or
#     `gist` paste doesn't leak. File is gitignored so this is
#     defense-in-depth not the primary guard.

set +e

input=$(cat 2>/dev/null || echo "{}")
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty' 2>/dev/null || true)

if [ -n "$cmd" ]; then
  # Redact known secret-prefix tokens before logging. Patterns match the
  # value half only; the prefix stays so the log is still readable for
  # "which integration was being called" debugging.
  scrubbed=$(printf '%s' "$cmd" | sed -E \
    -e 's/(ghp_|gho_|ghu_|ghs_|ghr_)[A-Za-z0-9]{30,}/\1[REDACTED]/g' \
    -e 's/github_pat_[A-Za-z0-9_]{70,}/github_pat_[REDACTED]/g' \
    -e 's/sk-ant-api[0-9]{2}-[A-Za-z0-9_-]{40,}/sk-ant-api[REDACTED]/g' \
    -e 's/sk-[A-Za-z0-9_-]{40,}/sk-[REDACTED]/g' \
    -e 's/(AKIA|ASIA)[A-Z0-9]{16}/\1[REDACTED]/g' \
    -e 's/AIza[A-Za-z0-9_-]{35}/AIza[REDACTED]/g' \
    -e 's/xox[abprs]-[A-Za-z0-9-]{10,}/xox[REDACTED]/g' \
    -e 's/(Bearer |Authorization: Bearer )[A-Za-z0-9._-]{20,}/\1[REDACTED]/g' \
    2>/dev/null || printf '%s' "$cmd")
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date 2>/dev/null || echo "?")
  mkdir -p .claude 2>/dev/null || true
  printf '[%s] %s\n' "$ts" "$scrubbed" >> .claude/session.log 2>/dev/null || true
fi

exit 0
