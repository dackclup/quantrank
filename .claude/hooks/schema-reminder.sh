#!/usr/bin/env bash
# schema-reminder.sh — inject reminder when the schema-triple files are edited
#
# Triggered by: PostToolUse with matcher "Write|Edit"
# Risk: low — only emits JSON when a schema-triple file path matches.
#       Cannot block (PostToolUse doesn't honor decision:"block" for
#       schema enforcement); only injects model-side context.
# Reads:  hook stdin JSON  (tool_input.file_path / tool_response.filePath)
# Writes: stdout JSON  (hookSpecificOutput.additionalContext) on match
#
# Design notes:
#   - Pure path-suffix match — no regex on file contents (cheap, fast).
#   - Three exact file matches; nothing fuzzy. Prevents false fires on
#     unrelated edits.
#   - Fails open: no jq / no stdin / no match → exit 0 with no output.

set +e

input=$(cat 2>/dev/null || echo "{}")
path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_response.filePath // empty' 2>/dev/null || true)

[ -z "$path" ] && exit 0

case "$path" in
  */compute/output/schemas.py | */frontend/lib/types.ts | */frontend/lib/schema-snapshot.json | \
  compute/output/schemas.py   | frontend/lib/types.ts   | frontend/lib/schema-snapshot.json)
    cat <<'JSON'
{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "Schema-triple file touched (compute/output/schemas.py or frontend/lib/types.ts or frontend/lib/schema-snapshot.json). Per CLAUDE.md §Conventions, the Pydantic ↔ TS ↔ snapshot triple MUST move together. Before commit: run `python -m compute.output.schema_check` (regenerate snapshot with `--update-snapshot` if intentional), or spawn the schema-sentinel subagent."
  }
}
JSON
    ;;
esac

exit 0
