# .claude/agents/ — project subagents

Project-specific Claude Code subagents. Spawned via the `Agent` tool
with a separate context window. Read-only by default.

## Roster (lean baseline + 1 data-correctness reviewer)

| Agent | Model | When it fires | Cost class |
|---|---|---|---|
| `schema-sentinel` | sonnet | Schema-triple edit + "ready to push" | low (1 Bash + 1 Read) |
| `quantrank-reviewer` | sonnet | "ready to push" / Draft → Ready / explicit ask | medium (full diff walk) |
| `stock-detail-auditor` | sonnet | Post-cron / pre-release / "ตรวจ data หุ้น" / "check stock data correctness" | bounded (Step 2 prefilter caps Step 3 at ≤ 20 tickers) |

Three-agent baseline. `stock-detail-auditor` covers what
`quantrank-reviewer` deliberately won't: data correctness of the
per-stock JSON the frontend renders (range / consistency / Rule 16
invariants / known-issue overlap). Add more agents only when a real,
repeated pain point justifies the per-spawn token cost. See
[`CLAUDE.md`](../../CLAUDE.md) §Auto-routing policy for the firing
cues and the gate-moment discipline that keeps spawn count low.

## Author conventions

- **YAML frontmatter required**: `name`, `description`, `model`, `tools`.
- **`model: sonnet` by default.** Opus only for cross-domain
  orchestration or release-time work, and only after a sonnet pass has
  proven insufficient on real diffs.
- **Read-only**: no `Write` / `Edit` / `NotebookEdit` in `tools`.
- **Slim prompts**: tell the agent to Read `CLAUDE.md` / `SKILL.md`
  on demand. Do NOT duplicate project rules into the agent file —
  that bloats the per-spawn system prompt.
- **Hard constraints section**: every agent ends with "Hard
  constraints" enumerating what it must NOT do (edit files, run
  destructive commands, cover other agents' domains).
- **Output discipline**: cap the report length in the agent file
  ("under 250 words", "one-line PASS or 5-bullet FAIL"). Bounded
  output keeps the spawn-and-synthesize cost predictable.

## Future slots (not built)

The lean baseline deliberately skips these. Add only when usage shows
the cost is justified:

- `methodology-scientist` — academic-prior validation (opus; fires
  on threshold / weight edits in `compute/scoring/risk_overlay.py` /
  `compute/scoring/manipulation_index.py`); covers FORMULA
  correctness, which `stock-detail-auditor` deliberately does not
- `edgar-debugger` — SEC throttling / retry policy debug
- `defense-layer-auditor` — risk-overlay output diff vs baseline
- `security-reviewer` — pre-release CVE + secret scan
- `release-captain` — version bump + tag + GitHub release ladder

If a class of work keeps needing the main agent to re-derive the
same checks, that's the signal to promote it from "manual" to a new
agent here.
