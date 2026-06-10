# CLAUDE.md

QuantRank is a static-site US-equity ranking tool. Python compute layer
generates JSON; a Next.js static site renders it. Currently ranks the
S&P 500 (universe = 502 after one delisting). See
[`README.md`](README.md) for the user-facing pitch,
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) for the academic
backing, and [`docs/design.md`](docs/design.md) for the visual /
design-system spec.

## Stack

- **Python 3.11+** — pandas 2.2 · edgartools 5.32 · pydantic 2.6 ·
  tenacity 8.2 · BeautifulSoup 4 · lxml 5 · pytest 8 · ruff 0.4
- **Next.js 14.2** (App Router, static export) — React 18.3 ·
  TypeScript 5.9 · Tailwind 3.4 · Recharts 2.15. Self-hosted fonts
  via @fontsource: **IBM Plex Sans** (body) · **JetBrains Mono**
  (tabular numerics) · **Roboto Slab** (headlines, LedgerCraft adoption Phase 1 PR #211 +
  Phase 2 PR #212 + Phase 3a PR #213 + Phase 3c PR #215 — `font-slab`
  + 4-tier shadow tokens + spreadsheet header treatment + `AppShell`
  + `TopNav` tab nav (the `Sidebar` left-rail was removed PR #414, with
  `TopNav` now the sole nav); Phase 3b (merged) — `next-themes`
  class-strategy dark mode, OKLCH dark band, paired `dark:` variants
  across every chip family + table + card surface, three-state theme
  toggle in the AppShell header.
  Phase 3d folded into the same PR: LedgerCraft canonical palette
  alignment — body bg `#FAFAFA`, brand primary `emerald-700`
  (`#047857`; the LedgerCraft spec named forest-green `#15803D` =
  green-700, but the impl ships Tailwind emerald-700) on wordmark Q
  logo + primary CTA surfaces, OKLCH
  hue 155 → 152 + chroma 0.09 → 0.13 closer to forest green,
  border-radius normalization `rounded-2xl/xl` → `rounded-lg`).
- **CI** — GitHub Actions; weekday `compute-rankings.yml` (cron Mon-Fri 22:00 UTC; weekends skipped — no new trading data; a `trading-day-gate` job further skips NYSE holidays; also folds a warm PIT-backtest refresh step so the AI-pick home page updates each cron)
- **Data** — SEC EDGAR via `edgartools` · yfinance for prices · S&P 500
  constituents scraped from Wikipedia

## Layout

| Path | Purpose |
|---|---|
| `compute/ingest/` | SEC EDGAR + yfinance fetchers with on-disk caches |
| `compute/scoring/` | 8-pillar composite + risk overlay (7 active vetoes after Phase 4.5a) |
| `compute/valuation/` | 6-method fair-price ensemble + Tier-1 defenses |
| `compute/output/` | Pydantic schemas + JSON writers + schema-snapshot guard |
| `compute/main.py` | Weekly compute orchestrator |
| `frontend/app/` | Next.js routes (one per stock at `/stock/[ticker]`) |
| `frontend/components/` | React UI (RankingTable, FairPriceBarChart, …) |
| `frontend/public/data/` | Compute output: `metadata.json` + `rankings.json` + `stocks/<TICKER>.json` |
| `tests/` | pytest suite (offline + `@network` gated; see CI for current count) |
| `.claude/skills/` | 47 first-party invocation-triggerable skills + phase planning docs, plus a symlink to the 1 vendored third-party skill (`impeccable`, row below). See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for vendoring / license posture per source. |
| `.agents/skills/` | Vendored third-party agent skills in the cross-tool [skills.sh](https://skills.sh) layout. Currently 1: **`impeccable`** ([pbakaus/impeccable](https://github.com/pbakaus/impeccable), **Apache-2.0**) — a frontend-design skill (design review / live browser iteration / critique / typography / color / motion), symlinked into `.claude/skills/impeccable`; installed via `npx skills add`, pinned by root `skills-lock.json`, bundled `scripts/` marked `linguist-vendored`. Dev-session tooling only — never runs in CI / the static export / the compute cron. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). |
| `.claude/agents/` | 22 project-specific subagents in 5 tiers: **Tier 1 Core** (quantrank-reviewer · schema-sentinel · defense-layer-auditor · edgar-debugger · **stock-detail-auditor**), **Tier 2 Lifecycle** (security-reviewer · frontend-design-reviewer · **vercel-preview-auditor** · **expert-user-explorer** · release-captain · phase-coordinator), **Tier 3 Specialized** (test-engineer · methodology-scientist · **literature-searcher** · performance-engineer · dependency-auditor · **financial-engineer**), **Tier 4 Operations** (docs-reviewer · **ci-triage-engineer** · incident-commander), **Tier 5 Builders** (write-capable: **compute-builder** owns `compute/**` · **frontend-builder** owns `frontend/**`). Spawned via the `Agent` tool with a separate context window; see [`.claude/agents/README.md`](.claude/agents/README.md) for the routing matrix + 8 coordination flows. The collaborative multi-session **agent-teams** feature reuses these defs as teammate roles — [`.claude/agents/TEAMS.md`](.claude/agents/TEAMS.md) has the 5 team recipes + the builders' file-ownership protocol + a mobile/web subagent fallback. |
| `.claude/hooks/` | Bash hook scripts wired by `.claude/settings.json`. 3 hooks total: `log-bash.sh` (PostToolUse Bash → append every command to gitignored `.claude/session.log`) + `schema-reminder.sh` (PostToolUse Write/Edit → inject reminder when any file in the Pydantic↔TS↔snapshot triple is touched) + `delegate-first.sh` (UserPromptSubmit → inject orchestrator-role reminder every user turn so the main agent defaults to spawning sub-agents instead of doing work inline, AND auto-proposes the matching agent-team recipe when the task is team-fit — see [`.claude/agents/TEAMS.md`](.claude/agents/TEAMS.md) §Auto-proposal). All fail-open (missing `jq` / unwritable FS / empty stdin → exit 0). 5-second timeout each. |
| `.claude/worktrees/` | Harness-managed isolation dirs for subagents spawned via the `Agent` tool with `isolation: "worktree"`. Per-session, transient, **gitignored** (added 2026-05-22 post the 3-PR fan-out so they don't show up as untracked on the main worktree's `git status`). Never commit them. |
| `docs/agents/` | Per-repo configuration consumed by the vendored mattpocock engineering skills (`to-issues`, `to-prd`). Scaffolded 2026-05-25 via `mattpocock-setup-harness`. 2 files: `issue-tracker.md` (GitHub MCP conventions) + `domain.md` (the upstream-instruction → QuantRank-multi-file-CONTEXT-analog mapping). See §Agent skills below for the index. |

## Commands

| Action | Command |
|---|---|
| Lint | `ruff check .` |
| Test (offline) | `pytest tests/ -m "not network"` |
| Test (live SEC) | `pytest --run-network` (requires `EDGAR_USER_AGENT`) |
| Schema in-sync check | `python -m compute.output.schema_check` |
| Regenerate schema snapshot | `python -m compute.output.schema_check --update-snapshot` |
| Frontend build | `cd frontend && npx --no -- next build` |
| Frontend type-check | `cd frontend && npx --no -- tsc --noEmit` |
| Local weekly compute | `python -m compute.main` (writes `frontend/public/data/`) |
| Backtest backfill (manual) | `python -m scripts.backfill_portfolio_pit` — or the `backfill-portfolio.yml` `workflow_dispatch` (Phase 7.0; writes `frontend/public/data/portfolio/backtest_pit.json`; `IN_START`/`IN_END` are the shell-safe proxies for its `start`/`end` inputs) |
| Section A-L verification | `python .claude/skills/verify-production-output/helper.py` |

Verification ladder before any push: `ruff check .` → `pytest -m "not
network"` → (if schemas touched) `schema_check` → (if frontend touched)
`tsc --noEmit` + `next build` → (if compute output committed)
`verify-production-output/helper.py`.

**After every `workflow_dispatch` green** (REQUIRED 2026-05-17): run
Section A-L scan + Section I Playwright spot-check for any PR landing
a new UI surface or schema bump. See
`.claude/skills/verify-production-output/SKILL.md`. When Vercel MCP is
loaded, `list_deployments` → `get_runtime_logs` is the cheap pre-
Playwright pass.

## Connectors

Claude Code sessions for this project have these MCP connectors
enabled (managed in Claude app Settings → Connectors):

| Connector | Status | Use |
|---|---|---|
| **GitHub** | ✅ active | PRs, issues, releases, CI runs, file ops |
| **Vercel** | ✅ active (since 2026-05-17) | pre-Playwright deploy + runtime log check: `list_deployments` / `get_deployment_build_logs` / `get_runtime_logs` |
| **Supabase** | ✅ active (since 2026-05-17) | **reserved for Phase 5+** — not used by current code; do not add a client without an explicit PR |
| **Sentry** | ⚪ planned | post-deploy error monitor; `@sentry/nextjs` SDK wiring is a separate PR (not yet filed) |
| Gmail · Google Drive | ✅ active | rarely used; cross-tool comms / doc backup |

If `ToolSearch query="<name>"` returns no matches, this session
started before that connector was registered. Don't restart mid-task
(loses audit context) — delegate the connector-bound step to a sibling
session. See [`AGENTS.md`](AGENTS.md) §"Multi-session audit pattern"
for the full 4-step pattern + Section I forcing example.

## Conventions

- **Pydantic and TypeScript schemas move together.** `compute/output/schemas.py`
  + `frontend/lib/types.ts` + `frontend/lib/schema-snapshot.json` are a
  triple. The schema-snapshot CI guard fails the build on drift. See
  `.claude/skills/schema-check/SKILL.md`.
- **Annotate-and-veto-Top-N** (SKILL.md Rule 16). Flagged stocks keep
  their composite rank but lose the `entered_top5` badge; the
  next-in-line clean stock inherits it. Never modify the composite
  score retroactively. See `.claude/skills/top5-rotation-audit/SKILL.md`.
- **EDGAR is rate-limited (10 req/s).** Use `EDGAR_MAX_WORKERS=8`
  (PR-3d empirical bump from 5; ~1 req/s sustained vs 10/s ceiling
  per `compute/config.py:34-42`) and the tightened tenacity retry
  policy in `compute/ingest/fundamentals.py`. If
  `Metadata.fundamentals_latency_p95_seconds` sustains > 15s on a
  healthy SEC run, drop back to 5 or 6. Off-cycle pre-cache jobs
  (Phase 4) for batch warming.
- **Phase-N stubs are planning docs, not loaded skills.** Anything under
  `.claude/skills/phase-N/<name>/PLAN.md` is roadmap material — Claude
  Code doesn't recurse into nested directories. Promote a PLAN.md to a
  top-level `<name>/SKILL.md` when that phase begins.
- **Observability-before-wiring** (SKILL.md Rule 18, Process Hygiene
  Item #4). New external-data integrations ship the diagnostic
  `Metadata` surface first; production wiring follows ≥ 1 cron after
  the accounting equation is verified on real data. The Phase 4h →
  4h.2 retrofit (PRs #112 → #118 → #124) is the forcing precedent.
  See `WORKFLOW.md` §Observability-Before-Wiring Pattern.
- **CLAUDE.md + AGENTS.md ship with every PR.** Both agent docs must
  move in lockstep on every PR (any type — feat / fix / ci / docs /
  chore). At minimum the PR's **in-flight entry lands in
  [`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md)** (the
  append-only side-file adopted 2026-05-24 — see §Gotchas
  "Parallel-PR §Phase status collision pattern" for why). Substance
  updates to CLAUDE.md / AGENTS.md sections (new gotcha / convention
  / connector / layout / command) still land directly in those
  files. Reject PRs that touch code / workflows / schemas without
  EITHER a `PHASE_STATUS_INFLIGHT.md` entry OR a matching CLAUDE.md +
  AGENTS.md substance diff.
- **Rebase onto `origin/main` before flipping any PR Draft → Ready.**
  The §Phase status block in CLAUDE.md + the §Phase + version state
  block in AGENTS.md were append-shaped (pre-2026-05-24) — every PR
  inserted a new "**X in flight (this PR)**" bullet at the SAME
  insertion point, and parallel PRs hit `mergeable_state: dirty`.
  PR #230's adoption of [`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md)
  closes that pattern at the structural level: new PRs append their
  in-flight entry to the side-file (parallel-safe), so the rebase
  discipline is now a backstop for OTHER conflict surfaces (shared
  code edits, workflow YAML changes, schema bumps) — not the
  recurring §Phase status drag it used to be. **The mitigation
  remains local**: before authorizing Mark-Ready, run
  `git fetch origin main && git rebase origin/main` and resolve any
  remaining benign conflicts ("keep both in chronological order" if
  somebody added a CLAUDE.md substance change in the same area).
- **Session-start phase identification.** First action on any new
  session: read [`PHASE_STATUS.md`](PHASE_STATUS.md) §"Current state"
  for active schema + phase + defense-layer count + in-flight PRs, then
  route through [`WORKFLOW.md`](WORKFLOW.md) §"Agentic 6-Phase Cadence"
  (Planning → Code Gen → Integration → Test → Deploy → Monitor) using
  the standing 22 subagents — don't spawn ad-hoc workflow agents on top.
- **CLAUDE.md is an INDEX, not an encyclopedia (token-budget
  discipline, adopted 2026-06-03).** CLAUDE.md loads into EVERY session
  AND every sub-agent spawn, so it is the project's most token-expensive
  file. Keep it lean: §Gotchas is a **one-line index** whose detail
  lives in [`docs/GOTCHAS.md`](docs/GOTCHAS.md); §Phase status keeps only
  current-state + the one in-flight entry + Next deliverables, with the
  merged-PR log in [`PHASE_STATUS.md`](PHASE_STATUS.md) /
  [`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md) /
  [`docs/PHASE_STATUS_ARCHIVE.md`](docs/PHASE_STATUS_ARCHIVE.md). When
  adding a new gotcha: append the **one-line title** here AND the **full
  detail** to `docs/GOTCHAS.md` (both required) — never paste a
  multi-paragraph gotcha back into CLAUDE.md, and never inline a
  merged-PR note here (it goes in PHASE_STATUS_INFLIGHT.md). This is the
  rule that keeps the ~46K-token P0 drain (2026-06-03) from re-bloating.
- **Thai sessions: Thai for the human, English for the machine
  (token economy, 2026-06-03).** When the user works in Thai, reply in
  concise Thai but keep ALL machine-facing artifacts + your own
  reasoning in English (code · comments · commit messages · PR bodies ·
  log lines · sub-agent prompts · scratch reasoning) — Thai costs ~2-4x
  tokens/char at the tokenizer, so this layer-split closes most of the
  gap at zero capability cost. Never let concision drop a real finding /
  warning / caveat. Full discipline in the `thai-token-economy` skill
  ([`.claude/skills/thai-token-economy/SKILL.md`](.claude/skills/thai-token-economy/SKILL.md)).

## Auto-routing policy

### Main agent role — orchestrator, not laborer

The main Claude Code session is the **orchestrator / tech lead** of
the 22-agent team, not the laborer. Default action when given a
task is to **identify the matching sub-agent in `.claude/agents/`
and spawn it** — not to do the work inline. The
`UserPromptSubmit` hook injects this reminder every turn so the
rule stays loaded.

**Inline work is the EXCEPTION**, acceptable only when:

- (a) No sub-agent's `description:` matches the task.
- (b) The request is a trivial lookup — answerable with ≤ 1 Read +
  a single-sentence answer (e.g. "what's the current schema
  version?").
- (c) The user explicitly says "ทำเอง" / "inline this" / "don't
  spawn agents" / "do it yourself".
- (d) The work IS the meta-task of building or editing the agent /
  hook / settings infrastructure itself (you can't delegate
  building the delegation system).
- (e) Cross-agent synthesis after multiple sub-agents have
  reported — that's orchestrator work by definition.

If none of (a)-(e) applies and you find yourself reading / grepping /
investigating production code without having spawned an agent, STOP
and spawn the relevant sub-agent first. Main-session tokens land on
the "Weekly · all models" pool; sonnet sub-agents land on the
separate "Weekly · Sonnet only" pool which on Max plans is paid-for
and currently under-utilized.

### Delegation patterns — common requests → which agent to spawn

Concrete mapping so the delegate-first check doesn't become
guesswork:

| User pattern / task | Spawn (don't do inline) |
|---|---|
| "ตรวจ data หุ้น" / "check ticker X" / audit per-stock JSON correctness | `stock-detail-auditor` (sonnet) |
| "review code" / "ก่อน push" / "ready to push" / "open PR" | `quantrank-reviewer` (fable) |
| "schema in sync?" / edit to `schemas.py`/`types.ts`/snapshot | `schema-sentinel` (sonnet) |
| "ทำไม cron ช้า" / p95 > 20s / cron > 10 min warm-cache | `performance-engineer` (sonnet) |
| "design X" / new UI component / "doesn't match the rest" | `frontend-design-reviewer` (sonnet) |
| "ตรวจ doc" / md edit / section header added | `docs-reviewer` (sonnet) |
| "audit defenses" / new flag / defense count diff | `defense-layer-auditor` (sonnet) |
| 429/403 from SEC / EDGAR hangs / edgartools drift | `edgar-debugger` (sonnet) |
| "tag release" / "ตัด release" / phase-epic PR merged | `release-captain` (fable) |
| "production is broken" / "site is down" / cron failure | `incident-commander` (fable, P1) |
| "validate against literature" / threshold change / new flag academic prior | `methodology-scientist` (fable) |
| Dependabot alert / new dep / "ตรวจ CVE" | `dependency-auditor` (sonnet) + `security-reviewer` (sonnet) parallel |
| New prod code without test / "TDD this" / "write tests for X" | `test-engineer` (sonnet) |
| "scan for secrets" / pre-release / new env-var / `.github/workflows/` edit | `security-reviewer` (sonnet) |
| New `claude/*` branch from handoff / phase complete / PR open | `phase-coordinator` (sonnet) |
| CI check failed (webhook event) / "CI fail" / "Python test red" / "build แตก" / "เช็คทำไม CI fail" | `ci-triage-engineer` (sonnet) |
| "ดู preview" / "is deploy green?" / pre-Mark-Ready on UI-touching PR / Vercel preview URL just posted | `vercel-preview-auditor` (sonnet) |
| "ลองใช้ app (จริง)" / "expert user feedback" / "ใช้งานจริงดูหน่อย" / "UX จริง" / "is the app actually usable?" / post-cron experiential pass | `expert-user-explorer` (sonnet) |
| "find me the paper that says X" / "หาเปเปอร์เรื่อง Y" / methodology cite outside CLAUDE.md anchor list / new defense-flag prior | `literature-searcher` (sonnet) |
| "design a new valuation method / factor / scoring pillar / defense flag" / "ออกแบบ factor / โมเดล quant" / "scope Phase 5/6/7" / "should we add signal X" (construct doesn't exist yet) | `financial-engineer` (fable; generative design) → then `methodology-scientist` to ratify |
| "implement X in compute/" / "build the Y component / route" / cross-layer feature build (schema + compute + UI + test) | `compute-builder` / `frontend-builder` (sonnet, **write** — owns `compute/**` / `frontend/**`) — or a **Feature Squad** agent team ([`.claude/agents/TEAMS.md`](.claude/agents/TEAMS.md)) |

Pattern not in the table → walk the description fields of all 22
agents in `.claude/agents/` before defaulting to inline work.

### Cue table — when each agent fires

Subagents under [`.claude/agents/`](.claude/agents/) auto-spawn on
the cues below — **lean-by-design**. Most
cues fire at GATE moments (`ready to push` / explicit ask / signal
event), **not on every edit**. Each spawn costs a separate context
window; the policy keeps that cost bounded while preserving the
safety net at decision points. The hook layer covers per-edit
reminders that don't need LLM judgment.

The main agent MUST spawn without asking for confirmation — all
subagents are read-only. Only destructive commands a subagent
*proposes* require user authorization.

**Sonnet sub-agents fire on edit; fable agents wait for gate.** This
is the split discipline that drains the Max-plan "Weekly · Sonnet
only" pool without burning the "Weekly · all models" pool. Each
sonnet agent has a non-trivial-edit cue in its domain (rows
below). The five fable agents (`quantrank-reviewer` ·
`methodology-scientist` · `release-captain` · `incident-commander` ·
`financial-engineer`) stay rare-fire on gates or signals. Dedup window ~10 min — if the
same sonnet agent ran on the same diff and it hasn't moved, point
at the prior result instead of re-spawning. The "ready to push"
gate still fires as a safety net (fable reviewer + a re-batch of
sonnet agents in case earlier edit-triggered runs missed
something).

**What "non-trivial edit" means**: > 5 added lines OR touches
non-comment code OR adds/removes a public symbol. Pure comment /
whitespace / single-line fixes do not trigger.

| When | Auto-spawn | Notes |
|---|---|---|
| **Non-trivial edit** to `compute/output/schemas.py` / `frontend/lib/types.ts` / `frontend/lib/schema-snapshot.json` | `schema-sentinel` (sonnet) | On-edit; sonnet pool; hook still fires its reminder regardless |
| **Non-trivial edit** to `compute/scoring/*` or `compute/valuation/*` | `defense-layer-auditor` (sonnet) | On-edit; sonnet pool |
| **Non-trivial edit** to `frontend/components/*` or `frontend/app/*` | `frontend-design-reviewer` (sonnet) | On-edit; sonnet pool; emits Playwright spot-check matrix |
| **Non-trivial edit** to `.github/workflows/*` OR new dep in `pyproject.toml` / `frontend/package.json` OR new env-var read | `security-reviewer` (sonnet) | On-edit; sonnet pool |
| Production code added without a corresponding test in the same diff | `test-engineer` (sonnet) | On-edit; sonnet pool; covers `compute/**/*.py` not under `tests/` |
| **Non-trivial edit** to any of CLAUDE.md / AGENTS.md / SKILL.md / WORKFLOW.md / PHASE_STATUS.md / README.md / METHODOLOGY.md | `docs-reviewer` (sonnet) | On-edit; sonnet pool; substance check (file-touch lockstep handled separately by `phase-coordinator` Mode B at the push gate) |
| Test failure under `tests/test_ingest/` OR live-run hang OR `429`/`403` from SEC | `edgar-debugger` (sonnet) | Signal-driven, on-demand |
| Weekly cron warm-cache > 10 min OR p95 latency > 20s | `performance-engineer` (sonnet) | Signal-driven, on detection |
| Dependabot alert lands OR new dep added to `pyproject.toml` / `frontend/package.json` | `dependency-auditor` (sonnet) + `security-reviewer` (sonnet) | Signal-driven, parallel |
| Production cron fails / hangs / produces corrupt output, OR Vercel deploy breaks, OR schema-snapshot CI fails, OR user says "production is broken" / "site is down" / "incident" | `incident-commander` (fable; P1 orchestrator) | Immediate |
| GitHub Actions check fails on any open PR (webhook PR-activity event) OR user says "CI fail" / "Python test red" / "build แตก" / "เช็คทำไม CI fail" | `ci-triage-engineer` (sonnet) | Signal-driven, on webhook; reactive — proposes one-line fix |
| Pre-Mark-Ready on a UI-touching PR OR new Vercel preview URL posted OR user says "ดู preview" / "is deploy green?" / "spot-check the preview" | `vercel-preview-auditor` (sonnet) | Gated; runs Vercel MCP build+runtime+UA-probe before Playwright is scheduled |
| Post-cron green OR pre-release OR after `vercel-preview-auditor` GO on a UI PR OR user says "ลองใช้ app" / "expert user feedback" / "UX จริง" / "is the app usable?" | `expert-user-explorer` (sonnet) | Gated; builds+serves the static export locally, drives headless Playwright through a persona mission; read-only, proposes issues. NOT per-edit (that's `frontend-design-reviewer`) |
| methodology-scientist verdict cites a paper outside CLAUDE.md anchor list AND the actual paper text matters, OR user says "find me the paper that says X" / "หาเปเปอร์เรื่อง Y" / new defense-flag academic prior is proposed | `literature-searcher` (sonnet) | On-demand; offloads retrieval so methodology-scientist (fable) stays on judgment |
| `workflow_dispatch` on `compute-rankings.yml` lands green | `defense-layer-auditor` Section A-L + Section I (Playwright) + `stock-detail-auditor` (per-stock data audit) + `expert-user-explorer` (experiential P1 mission on the fresh data) | Auto post-cron, parallel; all sonnet |
| Quarterly cohort audit scheduled date reached (next 2026-08-19) | `methodology-scientist` (fable) Mode C + `defense-layer-auditor` (sonnet) | Scheduled, sequential |
| User says "design a new valuation method / factor / scoring pillar / defense flag" / "ออกแบบ factor / โมเดล quant" / "scope Phase 5/6/7" / "should we add signal X" (the construct doesn't exist yet) | `financial-engineer` (fable; generative design) → then `methodology-scientist` to ratify the prior | Rare; design precedes validation (Flow 8) |
| New defense flag proposed (new risk_flag in `compute/scoring/`) | `methodology-scientist` (fable; validate paper anchor) + `test-engineer` (sonnet; positive + negative tests) | Rare; sequential — methodology first |
| Threshold / weight constant changed in `compute/scoring/manipulation_index.py` or `earnings_quality.py` | `methodology-scientist` (fable) Mode B | Rare; on the edit |
| User says "ก่อน push" / "ready to push" / "open PR" / "mark ready" / "ตรวจก่อน push" | `quantrank-reviewer` (fable) + `phase-coordinator` (sonnet) Mode B. Conditional sonnet re-batch on the same gate: `schema-sentinel` / `defense-layer-auditor` / `frontend-design-reviewer` / `docs-reviewer` / `security-reviewer` / `test-engineer` (skipped per-agent if the dedup window confirms it already ran on this diff) | Parallel pre-push safety-net gate |
| User says "ตรวจ data หุ้น" / "check stock data correctness" / "audit the output" / "verify the output" / "ตรวจ output" / pre-release | `stock-detail-auditor` (sonnet; deterministic prefilter then thorough LLM verdict for every flagged ticker) | One sonnet spawn, thorough |
| User says "tag release" / "cut a release" / "release vX.Y.Z" / "ตัด release" / phase-epic PR just merged | `release-captain` (orchestrator; spawns ladder agents as needed) | Owns release ladder |
| User asks to create a new `claude/*` branch from a handoff prompt | `phase-coordinator` Mode A | Before first non-trivial edit |
| Phase / sub-PR marked complete on this branch | `phase-coordinator` Mode C | After merge / on close |
| Diff > 200 lines on `compute/scoring/` OR user says "full review" / "deep review" | `quantrank-reviewer` with `model: fable` override | Rare; user authorization required |

### Spawn discipline

- **Route on the handoff line.** Every sub-agent ends its report
  with a parseable `HANDOFF · status=… · next=<DONE | SPAWN
  <agent>:<scope> | ESCALATE <agent>:<why> | NEEDS-USER:<decision>>` line
  (convention in [`.claude/agents/README.md`](.claude/agents/README.md)
  §Dynamic workflow). Compose the next step from it **dynamically** —
  the 8 coordination flows are canonical examples, not an exhaustive
  script; an unexpected finding still routes to the right specialist
  (this session's `expert-user-explorer` → bug → `frontend-design-reviewer`
  → re-validate loop was composed on the fly, not from a listed flow).
- **Don't gatekeep sub-agent effort.** When a sub-agent is
  spawned, let it do the full thorough job — read every relevant
  file, walk every section, follow every escalation lead.
  Sonnet sub-agent tokens come out of the "Weekly · Sonnet only"
  pool on Max plans, which is a separate budget that empties
  slowly and often goes unused. Bounding sub-agent output with
  hard word caps or "≤ N items" limits wastes that pool without
  improving signal. Keep model assignments (`incident-commander`
  + `release-captain` + `methodology-scientist` + `quantrank-
  reviewer` + `financial-engineer` all fable by design; the other 17
  sonnet) as they are — fable agents land on the "Weekly · all models"
  pool; sonnet agents drain the underutilized sonnet pool. Tune the
  5-vs-17 split only when usage data justifies it. **20 of 22 agents
  carry `effort: max`** (frontmatter) — orthogonal to `model`: `model`
  picks fable-vs-sonnet, `effort` (low/medium/high/xhigh/max) sets
  reasoning depth and overrides the session's inherited level. Most
  agents are open-ended correctness / judgment gates, so max pays back;
  sonnet-at-max still drains the Sonnet-only pool. **Carve-out (2026-06-03):
  the two deterministic script-runners — `schema-sentinel` (runs
  `schema_check`, reports the diff) and `vercel-preview-auditor` (runs a
  fixed Vercel MCP chain, reports GO/WAIT) — run at `effort: high`, not
  max** (max reasoning is wasted on a fixed procedure; saves thinking
  tokens per spawn at no capability cost). A new agent gets `effort: max`
  unless it's a pure mechanical lookup (then `high`, with a note) —
  README §Authoring conventions #3.
- **Prefer delegation to sub-agents** over inline main-session
  work when both options exist. Main-session tokens land on the
  "Weekly · all models" pool; sonnet sub-agents land on the
  separate, often-under-utilized "Weekly · Sonnet only" pool.
  Route work through sonnet sub-agents proactively to balance
  pool usage — e.g., when the user edits a scoring file, spawn
  `defense-layer-auditor` (sonnet) early to walk the diff before
  the main agent (which costs all-models tokens) synthesizes.
- **Spawn without asking** for read-only subagents — just spawn
  and report back. Do not pause the user's flow with "should I
  spawn X?".
- **Ask before authorizing the destructive command** a subagent
  proposes (e.g., `release-captain` emits `git tag` + `git push
  origin <tag>` — that command needs explicit user authorization
  per §Executing actions with care).
- **Skip auto-spawn** if the user explicitly says "skip the X
  agent", "don't review this one", "I'll handle it manually" —
  note the skip in chat and proceed.
- **De-duplicate**: if a subagent ran on the same diff within the
  last ~10 minutes and the diff hasn't moved, don't re-spawn —
  point to the prior result instead.
- **Parallel at gate moments, not on every edit**: when multiple
  conditional batch-mates fire at the "ready to push" gate, spawn
  them in parallel — they each have their own context window, and
  the user gets one consolidated report cycle.
- **Disable per-session**: user can `/agents` → toggle off any
  agent they don't want auto-routing this session, or say "spawn
  only on explicit ask this session" to force the strictest mode.

### Agent-team auto-proposal (Claude proposes, you confirm)

The `delegate-first.sh` hook nudges the orchestrator every turn to
**proactively propose** an agent-team recipe (don't wait to be asked) when the
task is team-fit — cross-layer build → **Feature Squad** · new
flag/threshold/factor → **Methodology Debate** · root-cause-unclear incident →
**Incident War Room** · big multi-lens PR → **PR Review Crew**. This is
**propose-not-create**: the feature never spawns a team without the user's
confirm. On web/mobile (no desktop terminal) propose the **subagent fallback**
instead — same flow, runs there. Cue→recipe table + fallbacks:
[`.claude/agents/TEAMS.md`](.claude/agents/TEAMS.md) §Auto-proposal.

## Gotchas

One-line invariant index — **full detail in [`docs/GOTCHAS.md`](docs/GOTCHAS.md)**.
Open that file before touching the file/area a gotcha names; the index keeps the
always-loaded context small while preserving discoverability of every invariant.

- **`compute/cache/` is gitignored.**
- **`shares_outstanding` is wrong for ~12 tickers**
- **`eps_basic` / `eps_diluted` display fields now derive from
- **`_avg_3y_roe` fallback removed**
- **Going-concern phrase scan FP rate dropped to 1.0%**
- **`loss_avoidance_pattern` thresholds rescaled**
- **Hypothesis property-based tests**
- **CI escape-hatch env-var combo for simulate**
- **The cron cache is split into TWO `actions/cache` steps (don't re-merge): fast (quarter-key) + slow-text (run-id key)**
- **GitHub-Actions-injected env-vars `GITHUB_RUN_ID` + `GITHUB_SHA`**
- **`IMPECCABLE_NO_UPDATE_CHECK` + `IMPECCABLE_UPDATE_HOST`**
- **`Metadata.*_wall_clock_seconds` ≠ `fundamentals_latency_p95_seconds`**
- **Sub-agent `tools:` frontmatter does NOT auto-inherit MCP tools**
- **Release tags are mobile-only (locked 2026-05-27)**
- **Parallel-PR §Phase status collision pattern**
- **Lint the WHOLE repo before push, never per-file**
- **`html, body` are globally `overflow-x: clip`**
- **Root font-size is FLUID**
- **Re-parking the price-chart crosshair MUST debounce the `<AreaChart>`
- **App-wide motion uses ONE `ease-in-out` timing curve**
- **The stock-detail hero splits on a CSS CONTAINER QUERY, not a viewport
- **MoS gauge arc direction is SIGN-AWARE**
- **Subagent model aliases float forward to the LATEST — guard the downgrade
- **`RiskSummaryCard` merges rank-gates + manipulation-index into ONE card
- **Background runs (`Agent run_in_background:true` / `Bash run_in_background:true`)
- **The fair-price detail pair is split INTERPRETATION vs REFERENCE on
- **Stock-detail section order is deliberate — score-explanation rides high,
- **Price-chart resolution is PER-PERIOD — 5Y aggregates to monthly, the
- **Hero metric values count-up; the recommendation badge is STATIC**
- **`lucide-react` is the project's FIRST icon library — named imports ONLY**
- **`country-flag-icons` flag SVGs — per-country STATIC imports ONLY**
- **Hero attribute tiles = the 4-box category grid, theme-reskinned, 2 data +
- **`PillarRadarChart` row REFLOWS on mobile — bar drops to its own full-width
- **`globals.css` soft-color overrides are an ALLOWLIST — `bg-rose-600` /
- **Interactive controls carry a `min-h-[44px]` touch target; modals trap +
- **Secondary / muted text uses `text-slate-500 dark:text-slate-400` — NOT the
- **The stock-detail page splits into a DECISION zone and a collapsed
- **Loss-chance (and any rounded-display band/tone) must derive from the
- **`PillarRadarChart` shares the composite `TIERS` vocabulary + boundaries —
- **MoS donut + pillar rows expose their data to SR (not just a mouse `title`);
- **The outlined-light chip is a PRIMITIVE now — `frontend/components/Chip.tsx`,
- **Chip family carries `font-medium`; every large numeric display carries
- **The price chart is lazy-loaded via `PriceHistoryChartLazy` so Recharts
- **The composite-score gauge + mobile caption tier WORD comes from the canonical
- **Press feedback is the global `.press` utility — the PRESS tier of the
- **The home-page header is a deliberate 4-TIER hierarchy — don't re-flatten it
- **The ranking-table "no matches" empty-state is the app's ONE warm delight
- **The stock-detail `<article>` uses a TWO-LEVEL spacing rhythm — `space-y-4`
- **`HeroAttributeTiles` reserved tiles share the FILLED tile SURFACE**
- **The ranking-table FLIP reshuffle is SEARCH-SCOPED — never make it fire on a
- **`exchange_coverage_pct` and `country_coverage_pct` look like siblings but
- **Whole-app polish conventions (`$impeccable polish "all app"`, 2026-06-03) — empty-state CTA is `disabled` not just styled · a labeled chip inside an `aria-label`'d container is `aria-hidden` · `ring-rose-300` is never a negative chip ring (`-200` only) · detail-page valuation sections own no `mb-*`**
- **Footer build-version chip = build-time `NEXT_PUBLIC_APP_VERSION` (`next.config.js` git-describe→SHA), never a hardcoded version (in the `AppShell` footer since 2026-06-04; was the removed Sidebar footer before)**
- **`pillarColor`→`lib/visual` + `flagLabel`→`lib/flag-labels` are SHARED tokens (don't re-inline) — introduced by the now-removed compare/filter, still used by `PillarRadarChart` / `RiskSummaryCard` / `FairPriceCard`**
- **`globals.css` soft-color `!important` override is LITERAL-class-keyed → it NEVER reaches `dark:bg-emerald-*` / `dark:bg-rose-*` solid-fills (they render RAW Tailwind in dark → white label ~3.8:1, under AA). A dark CTA / brand mark = `dark:bg-emerald-700` (emerald-700 = `#047857`, white 5.5:1) or a `--c-*` token directly, never `dark:bg-emerald-600` expecting the soft remap (theme audit #401)**
- **The home + ranking pages derive stats from `rankings.json`/`metadata.json` at BUILD TIME (Server Components) — weekly static export, so values are "as of" the last cron, NOT live; never `import lib/data.ts` (or any `fs` module) into a `'use client'` component (resolve on the server, pass the node in as a prop/child). Removed 2026-06-04: the top `MarketStatsBar` strip + `lib/market-stats.ts` + `AppShell` `topBar` slot, AND the standalone `/sectors` + `/movers` routes — the build-time server-component rule lives on via the home + ranking pages**
- **`data/sp500_membership_historical.csv` (the survivorship ledger behind `members_at()`) must stay ADD/REMOVE-balanced — the reverse-walk reconstructs ~500-503 constituents at EVERY backtest month; run `scripts/verify_membership_ledger.py` after ANY edit (checks the size band 498-506 + that every removed ticker is gone / every added ticker present vs the live universe). Use effective (not announcement) dates + real tickers (SIVB not "SVB"; BX=Blackstone≠BLK=BlackRock); cite the Wikipedia change-history URL (the `press.spglobal.com/<date>-<title>` shape 404s). **Track B 10Y rebuild**: now covers **2016-01-04 .. present** (485 events; `EARLIEST_EVENT_DATE` + the verify `WINDOW_START` both moved 2020→2016). The 2016-01..2026-01-14 portion is snapshot-diff-DERIVED from the fja05680 historical-components dataset and is **RENAME-AWARE** (a symbol change = REMOVE old + ADD new, so `members_at` returns the correct historical ticker — a convention shift vs the prior "renames out of scope" 2020-2026 hand-built rows, which fja05680 cross-validated at the boundary). Tickers normalized to the yfinance dash form (BRK-B/BF-B). The 10Y `backtest_pit.json` reflects this after the DATA-layer extension (`PRICES_PERIOD`/`ANNUAL_HISTORY_YEARS`→10y + the load-bearing `cache-v6-fast` bump for the period-blind caches + `write_benchmarks_json` full-series) AND a cold `backfill_portfolio_pit` dispatch from 2016 (manual — the cold ~60-85m run exceeds the cron 40m folded-step cap; warm fits). ~15-20 pre-2021-renamed tickers' 2016-2020 legs drop (yfinance can't resolve the historical alias)**
- **The home page IS the AI-pick portfolio (Phase 7.0 PR-4)** — reads `backtest_pit.json` via `getAiPickData()` (fs-read + trim+round to a small client view-model, NEVER a static `import`; the 1.3MB artifact never ships in the page payload; `null` → "backtest pending"). Server resolves → the `'use client'` `AiPickPortfolio` gets it as props (the build-time-data rule). The 1-10 slider switches `nav.by_count[N]` (one NAV line per count); the chart uses the pre-aligned `nav.benchmark`, so `benchmarks.json` is NOT read by the frontend
- **Per-stock JSON for a dropped ticker (de-listed / renamed, e.g. EPAM / BK→BNY) is auto-pruned by `prune_orphan_stock_files()` (defined in `compute/output/writer.py`, called from `compute/main.py` after `write_rankings_json`; safety floor `_PRUNE_SAFETY_FLOOR=50`; cron `git add` stages the deletes). Don't glob `stocks/` for param-gen — it reads `rankings.json` by design. Full detail: `docs/GOTCHAS.md`**
- **The home's `AnnualReturnsTable` (calendar-year rows + CAGR footer) + the `NavCompareChart` `money` mode ($10k→$X growth + end-of-line $ labels) are DERIVED in-browser from the NAV series — no schema / compute / `backtest_pit.json` change. The CAGR is the **raw top-composite signal's** record, NOT the live veto-filtered Top-5 (`veto_layer_replayed=False`) — it underperforms the S&P 500 at every count (honest by design; disclosed in `meta.disclaimer` + a caveat beside the CAGR row). Don't describe the backtest CAGR as the live product's track record. Full detail: `docs/GOTCHAS.md`**
- **Agent teams (experimental, ≠ subagents) — flag `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` enables multi-session teams whose teammates MESSAGE each other + reuse subagent defs as roles; the 2 write-capable Tier-5 builders own DISJOINT layers (`compute-builder`=`compute/**`, `frontend-builder`=`frontend/**`) in a Feature Squad; live teams are desktop-terminal only (every recipe ships a mobile/web subagent fallback); teammates DON'T apply a def's `skills`/`mcpServers` frontmatter (load from settings). Recipes: [`.claude/agents/TEAMS.md`](.claude/agents/TEAMS.md)**

## Phase status

Current schema **`0.10.16-phase4.6`** on `main` (issue #441 PR-1 — additive
3 `Metadata.mad_*` MAD-factor diagnostics: coverage + cross-sectional Spearman
ρ vs `mom_12_1`/`mom_3_1`; pillar untouched, observability-only, Δscore = 0;
feeds the PR-2 wiring gate |ρ| < 0.30 + coverage ≥ 90%). Prior
**`0.10.15-phase4.6`** (#426 Phase 4j.1 — additive
9 `Metadata.alpha158_*` Qlib observability fields, `OsapGateDiagnostic` reused,
no new model; observability-only, Δscore = 0). Prior **`0.10.14-phase4.6`**:
**Phase 7.0 — the
AI-pick portfolio home + 5-year point-in-time backtest — shipped**
(#416 → #420: survivorship membership ledger + benchmark export +
inverse-vol weighting → PIT NAV engine + anti-look-ahead orchestrator →
NAV-per-holding-count N=1-10 → re-sourced restatement canary +
result-dependent disclaimer + the real 5y `backtest_pit.json` → the
AI-pick home page that renders it). The backtest artifact self-carries
its `meta`, so it required **no `schemas.py` model**; the only Phase 7
schema change was the additive `Metadata.benchmark_coverage_pct`
(`0.10.14`, #416 PR-1, atop the prior `0.10.13` `country_coverage_pct`
strict-resolution canary — see §Gotchas). Prior schema
**`0.10.12-phase4.6`** on `main` (PR #303 merged
2026-05-29 `847c21b` — Phase 4.5e PR 6 Form-4 10b5-1 negation guard,
residual footgun #1 from PR 4-eq; new
`Metadata.form4_negation_guard_downgrade_count: int | None` counts
True → False downgrades from the 11-token bidirectional ±5-word-token
regex wrapping `edgar.ownership.core.detect_10b5_1_plan`. Prior: PR #300
PATCH bump — new `Metadata.value_trap_risk_delta_by_sector: dict[str,
int] | None` per methodology-scientist Q2 verdict deferred from PR #294;
positive value = sector dropped flags after flip per lower sector Ke vs
flat 10% baseline; populates from cron Run #72+ as Step 8 per-ticker
loop accumulation). Schema cluster history: PR #297
Issue #287 PR A `0.10.7 → 0.10.9-phase4.6` (4 new `Metadata.*_wall_clock_seconds`
fields for Tier-2 / Form-4 / OSAP / Step-8 cross_source loops; paired
with `compute-rankings.yml` `timeout-minutes: 150 → 195` + cache-
restore canary; empirically validated on cron Run #71 / `368dccd9` at
2026-05-28 08:44 UTC). PR #298 cache-v5 bump landed (workflow cache
key flipped v4 → v5 to force live EDGAR re-fetch on cron Run #72 so
PR #292 GOOG/GOOGL per-class XBRL override actually fires; Run #71
confirmed silent-failure pattern via `multi_class_per_class_attempt_count = 0`). Defense layer **33 declared boolean flags** (7 active
vetoes + 26 annotates + reserved slots; ~27 currently emit;
`USE_SECTOR_COE = True` post-PR #294 flip). Plus 5 numerical guards
+ `manipulation_index` rollup. Latest release tag
[**`v1.4.0-phase4.6`**](https://github.com/dackclup/quantrank/releases/tag/v1.4.0-phase4.6)
(2026-05-27, `bbca9cac`) — Phase 4.6 honest re-validation harness
(universe survivorship-bias fix per Hou-Xue-Zhang 2020 + rankings.json
time-series loader + forward-return loader + per-pillar Spearman IC
+ manipulation-index distribution shift + honest-baseline CLI with
McLean-Pontiff 2016 32% post-publication decay banner). Post-tag
production patches: PR #292 schema PATCH `0.10.7 → 0.10.8-phase4.6`
(Rule 18 disambiguator `multi_class_per_class_attempt_count` for
the GOOG/GOOGL XBRL concept-name omission fix); PR #293 Site-2 DQIC
ceiling retirement (NVR FP, methodology-scientist Option C); PR #294
sector-CoE flip (Issue #67 `USE_SECTOR_COE = True`, Damodaran 2019
Ch. 8.4 11-sector Ke, `value_trap_risk` 132 → 109 cohort drop).
Prior tag [**`v1.3.0-phase4.5e`**](https://github.com/dackclup/quantrank/releases/tag/v1.3.0-phase4.5e)
(2026-05-26, `5db3b978`) — Phase 4.5e Form-4 insider-clustering
ladder closure + LedgerCraft frontend reskin (defense layer 32 → 33;
PR #264 `multi_class_aggregate_shares_suspected` + PR #265 DQIC
site-2 rename `valuation_output_anomalous`).

Full merged-PR log: [`PHASE_STATUS.md`](PHASE_STATUS.md) (canonical) · [`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md) (per-PR) · [`docs/PHASE_STATUS_ARCHIVE.md`](docs/PHASE_STATUS_ARCHIVE.md) (drained prose).

**In flight** (not yet merged on `main`):
- **docs(roadmap) — roadmap-fit re-scope, user-confirmed (this PR, 2026-06-10)** —
  a `financial-engineer` roadmap-fit assessment (verified against the repo)
  found 8 plan-vs-reality divergences; the user confirmed all adjustments.
  (1) **Phase 7.0c PIT veto-replay PROMOTED** to next-up — it gates Phase 5 ML
  (the 10Y backtest's raw composite underperforms SPX at every N with
  `veto_layer_replayed=False`; the veto-rescue question precedes the ~10-12w ML
  spend). (2) **#441 `macd_hist` fix ordered BEFORE the MAD PR-2 WIRING**
  (`pillars.py` dict-check vs float return → always-NaN; technical pillar runs
  4-of-5 inputs; the #447 diagnostics PR-1 deliberately left it — the fix gates
  the wiring step, not the observability). (3) NEW **data-integrity hardening
  sprint** (share-count corruption cluster
  #248/#374/#376/#379/#375/#385/#261/#247+#289) as a Phase 5 entry gate.
  (4) **v1.1 tag RE-GATED** — JKP 4i.1 dropped from the hard gate (license #115
  stale since 2026-05-14; WORKFLOW fallback invoked); new gate = OSAP 4h.1
  (#113) + 4j.2 blend decision on cron IC evidence; IPCA non-blocking.
  (5) Phase 6 re-scoped TEXT-ONLY (Whisper → 6.1). (6) Phase 7 remainder renamed
  7.1 with baseline + fit-window gates. (7) Phase 8 staged (S&P 900 pilot; #249
  pre-cache prerequisite). (8) Phase 4.5e PR 5 marked UNBLOCKED (#287 PR B
  merged as #431). Doc-drift sweep folded in (PHASE_STATUS.md Phase-7 row ·
  subagent count 20→22 · stale in-flight/open-issues blocks · WORKFLOW.md
  schema pointer 0.10.13→0.10.16 · `gtda` license inconsistency · "Opus agents"
  → fable). Docs-only — no production code / schema change.


**Next deliverables** (re-scoped 2026-06-10, ordered by decision-value):
- **1 · Phase 7.0c — PIT veto-layer replay** (PROMOTED) — replay the 7 active
  vetoes in `scripts/backfill_portfolio_pit.py` (flip `veto_layer_replayed`
  False → True) + one backfill dispatch. Answers "does the defense layer rescue
  the composite?" — the **Phase 5 entry gate (a)**.
- **2 · Issue #441 — fix the dead `macd_hist` input** (always-NaN dict-vs-float
  type mismatch) **BEFORE the MAD PR-2 wiring** (diagnostics PR-1 merged as
  #447, pillar untouched), so the IC comparison runs against a clean 5-input
  technical-pillar baseline.
- **3 · Data-integrity hardening sprint** (~1-2w, NEW) — the share-count /
  extraction corruption cluster (#248 V ~4× no-veto · #374 warm-cache per-class
  bypass · #376 · #379 · #375 · #385 · #261 · #247/#289 NVR) — **Phase 5 entry
  gate (b)**.
- **4 · Phase 4.5e PR 5 — cluster weight promotion 5.0 → 7.0** — **UNBLOCKED**
  (#287 PR B merged as #431); needs ≥ 1 cron's
  `form4_rule10b5_one_excluded_count` confirming the -30% to -45% Aboody et
  al. 2010 §3.2 band, accumulating ahead of the Q3 2026-08-19 cohort audit.
- **5 · v1.1.0-phase4 tag — RE-GATED** — JKP 4i.1 **dropped** from the hard
  gate (license #115; WORKFLOW fallback clause); new gate = OSAP 4h.1 (#113) +
  the 4j.2 Qlib blend decision on ≥ 1 real cron of `Metadata.alpha158_*` IC
  evidence (PBO ≤ 0.5 + DSR > 0); 4k.1 IPCA (#122) additive, non-blocking.
- **6 · Phase 5 — ML meta-learner** (~10-12w; unblocks PR 4b §3 IC-decay
  writer #75) — gated on items 1 + 3 + a Supabase client-wiring pre-PR
  (§Connectors). Entry gates spelled out in WORKFLOW.md §Phase 5.
- **7 · Stock-attribute data — Dividend + Security-type tiles** — unchanged,
  display-only, parallel-safe; full spec in PHASE_STATUS.md §Next deliverables
  item 7 (yfinance `Ticker.info` / `fast_info.quote_type` + schema triple +
  `*_coverage_pct` observability-first; tiles auto-promote when non-null).
- Phase 6 = TEXT-ONLY, Whisper → 6.1 · Phase 7 remainder = **7.1** (gated on
  the 7.0c baseline + a longer fit window) · Phase 8 = staged S&P 900 pilot
  with the #249 off-cycle pre-cache as prerequisite — detail in WORKFLOW.md.

See [`PHASE_STATUS.md`](PHASE_STATUS.md) for the canonical
chronological tracker.

## Agent skills

Per-repo configuration consumed by the vendored mattpocock engineering
skills (`to-issues`, `to-prd`, et al.). Scaffolded 2026-05-25 via
`mattpocock-setup-harness`.

### Issue tracker

GitHub Issues at `dackclup/quantrank` via the GitHub MCP server
(`mcp__github__*` tools — `gh` CLI is not installed in the remote
execution environment). See [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md).

### Domain docs

Single-context. QuantRank's `CONTEXT.md` analog is **multi-file** —
distributed across CLAUDE.md + docs/METHODOLOGY.md + SKILL.md +
WORKFLOW.md; the ADR analog is `PHASE_STATUS_INFLIGHT.md` (append-only
side-file). See [`docs/agents/domain.md`](docs/agents/domain.md) for the
upstream-instruction-to-QuantRank-file mapping.

### Triage labels

Intentionally NOT scaffolded — the upstream `triage` skill is not
vendored in QuantRank (skipped at 2026-05-20 base sync), so a triage
label vocabulary would be dead config. If `triage` is vendored in a
future sync, re-run `/mattpocock-setup-harness` to add this section.

## Companion files

- [`AGENTS.md`](AGENTS.md) — cross-tool agent instructions (Copilot /
  Cursor / Devin) + multi-session audit pattern detail
- [`SKILL.md`](SKILL.md) — long-form QuantRank rulebook (Rules 1-18 +
  schema-version table + library matrix)
- [`WORKFLOW.md`](WORKFLOW.md) — per-phase task lists, decision points
- [`PHASE_STATUS.md`](PHASE_STATUS.md) — chronological phase tracker
- [`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md) — append-only
  per-PR in-flight side-file (ADR analog)
- [`docs/GOTCHAS.md`](docs/GOTCHAS.md) — full detail for every invariant
  indexed in CLAUDE.md §Gotchas (load on demand, before touching the
  file/area a gotcha names)
- [`docs/PHASE_STATUS_ARCHIVE.md`](docs/PHASE_STATUS_ARCHIVE.md) —
  merged-PR prose drained from CLAUDE.md §Phase status (reference only)
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) — vendor / license
  posture per third-party source
- [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md) — mattpocock
  skill consumer rules for GitHub Issues access via the GitHub MCP server
- [`docs/agents/domain.md`](docs/agents/domain.md) — mattpocock skill
  consumer rules for QuantRank's multi-file CONTEXT analog +
  PHASE_STATUS_INFLIGHT.md as ADR analog
- [`.claude/agents/TEAMS.md`](.claude/agents/TEAMS.md) — agent-team
  recipes + the 2 write-capable builders (collaborative multi-session
  complement to the report-back subagents)
- [`.claude/skills/README.md`](.claude/skills/README.md) — skill index
- [`docs/LESSONS_LEARNED.md`](docs/LESSONS_LEARNED.md) — running log of
  agent-process dos/don'ts + per-session mistakes (workflow / git / review
  discipline; complements §Gotchas, which owns code/domain invariants)
