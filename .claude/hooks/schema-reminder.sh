#!/usr/bin/env bash
# schema-reminder.sh — inject reminder when the schema-triple files are edited
#
# Triggered by: PostToolUse with matcher "Write|Edit"
# Risk: low — only emits JSON on a triple-path match. Fail-open.

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
    "additionalContext": "Schema-triple file touched. Per CLAUDE.md §Conventions, compute/output/schemas.py ↔ frontend/lib/types.ts ↔ frontend/lib/schema-snapshot.json move together. Before commit: run `python -m compute.output.schema_check` (regenerate with `--update-snapshot` if intentional)."
  }
}
JSON
    ;;
esac

exit 0
