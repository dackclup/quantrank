# Issue tracker: GitHub

Issues and PRDs for QuantRank live as GitHub issues at
`https://github.com/dackclup/quantrank/issues`.

## Access surface

QuantRank's primary access surface to GitHub is the **GitHub MCP server**
(prefixed `mcp__github__*`), not the `gh` CLI. The `gh` CLI is NOT
installed in the Claude Code on the Web execution environment used for
weekly compute / iteration sessions. See `CLAUDE.md` §Connectors for the
canonical list of MCP connectors and `AGENTS.md` for cross-tool agent
instructions.

The MCP tools cover every operation `gh` would: read / write issues,
PRs, comments, releases, CI runs, file ops. Operations are restricted to
the `dackclup/quantrank` repository.

## Conventions

- **Create an issue**: `mcp__github__issue_write` with `method: "create"`,
  pass title + body + labels. Use multi-line body strings.
- **Read an issue**: `mcp__github__issue_read` with `method: "get"` /
  `"get_comments"`. Returns body + labels + state + comments.
- **List issues**: `mcp__github__list_issues` with state + label filters.
- **Comment on an issue**: `mcp__github__issue_write` with
  `method: "add_comment"`.
- **Apply / remove labels**: `mcp__github__issue_write` with
  `method: "update"` and the `labels` array (set, not delta).
- **Close**: `mcp__github__issue_write` with `method: "close"`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue via `mcp__github__issue_write` with
`method: "create"`. Tag with relevant area labels if the repo's label
taxonomy applies; otherwise leave unlabeled.

## When a skill says "fetch the relevant ticket"

Run `mcp__github__issue_read` with `method: "get"` then with
`method: "get_comments"`.

## Frugality note

Per `CLAUDE.md`: "Be frugal about posting replies on GitHub. Use your
best judgement and only comment when a reply is genuinely necessary."
The mattpocock skills sometimes want to drop a draft comment as a
side-effect; in QuantRank's flow prefer chat-side discussion + a single
final issue update rather than running commentary.

## Skipped surfaces

QuantRank does NOT use:

- `gh` CLI (not installed in remote execution environment)
- GitLab (the `glab` equivalent surface)
- Local-markdown `.scratch/` directory (not adopted; PHASE_STATUS_INFLIGHT.md
  serves the equivalent "in-flight decision log" role)

The `glab` and `.scratch/` template files vendored under
`.claude/skills/mattpocock-setup-harness/` are kept for cross-project
portability but inapplicable here.
