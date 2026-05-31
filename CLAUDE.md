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
  (tabular numerics) · **Instrument Serif** (display marquee) ·
  **Roboto Slab** (headlines, LedgerCraft adoption Phase 1 PR #211 +
  Phase 2 PR #212 + Phase 3a PR #213 + Phase 3c PR #215 — `font-slab`
  + 4-tier shadow tokens + spreadsheet header treatment + `AppShell`
  / `Sidebar` left-rail nav; Phase 3b (merged) — `next-themes`
  class-strategy dark mode, OKLCH dark band, paired `dark:` variants
  across every chip family + table + card + drawer surface, three-
  state theme toggle in sidebar footer + AppShell header.
  Phase 3d folded into the same PR: LedgerCraft canonical palette
  alignment — body bg `#FAFAFA`, brand primary `emerald-700`
  (`#15803D`) on wordmark Q logo + FilterDrawer submit CTA, OKLCH
  hue 155 → 152 + chroma 0.09 → 0.13 closer to forest green,
  border-radius normalization `rounded-2xl/xl` → `rounded-lg`).
- **CI** — GitHub Actions; weekday `compute-rankings.yml` (cron Mon-Fri 22:00 UTC; weekends skipped — no new trading data)
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
| `.claude/skills/` | 46 invocation-triggerable skills + phase planning docs. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for vendoring / license posture per source. |
| `.claude/agents/` | 20 project-specific subagents in 4 tiers + 1 data-correctness reviewer: **Tier 1 Core** (quantrank-reviewer · schema-sentinel · defense-layer-auditor · edgar-debugger · **stock-detail-auditor**), **Tier 2 Lifecycle** (security-reviewer · frontend-design-reviewer · **vercel-preview-auditor** · **expert-user-explorer** · release-captain · phase-coordinator), **Tier 3 Specialized** (test-engineer · methodology-scientist · **literature-searcher** · performance-engineer · dependency-auditor · **financial-engineer**), **Tier 4 Operations** (docs-reviewer · **ci-triage-engineer** · incident-commander). Spawned via the `Agent` tool with a separate context window; see [`.claude/agents/README.md`](.claude/agents/README.md) for the routing matrix + 8 coordination flows (pre-push gate / release ladder / new-defense flow / incident response / review escalation / quarterly audit / experiential UX pass / quant design). |
| `.claude/hooks/` | Bash hook scripts wired by `.claude/settings.json`. 3 hooks total: `log-bash.sh` (PostToolUse Bash → append every command to gitignored `.claude/session.log`) + `schema-reminder.sh` (PostToolUse Write/Edit → inject reminder when any file in the Pydantic↔TS↔snapshot triple is touched) + `delegate-first.sh` (UserPromptSubmit → inject orchestrator-role reminder every user turn so the main agent defaults to spawning sub-agents instead of doing work inline). All fail-open (missing `jq` / unwritable FS / empty stdin → exit 0). 5-second timeout each. |
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
  the standing 20 subagents — don't spawn ad-hoc workflow agents on top.

## Auto-routing policy

### Main agent role — orchestrator, not laborer

The main Claude Code session is the **orchestrator / tech lead** of
the 20-agent team, not the laborer. Default action when given a
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
| "review code" / "ก่อน push" / "ready to push" / "open PR" | `quantrank-reviewer` (opus) |
| "schema in sync?" / edit to `schemas.py`/`types.ts`/snapshot | `schema-sentinel` (sonnet) |
| "ทำไม cron ช้า" / p95 > 20s / cron > 10 min warm-cache | `performance-engineer` (sonnet) |
| "design X" / new UI component / "doesn't match the rest" | `frontend-design-reviewer` (sonnet) |
| "ตรวจ doc" / md edit / section header added | `docs-reviewer` (sonnet) |
| "audit defenses" / new flag / defense count diff | `defense-layer-auditor` (sonnet) |
| 429/403 from SEC / EDGAR hangs / edgartools drift | `edgar-debugger` (sonnet) |
| "tag release" / "ตัด release" / phase-epic PR merged | `release-captain` (opus) |
| "production is broken" / "site is down" / cron failure | `incident-commander` (opus, P1) |
| "validate against literature" / threshold change / new flag academic prior | `methodology-scientist` (opus) |
| Dependabot alert / new dep / "ตรวจ CVE" | `dependency-auditor` (sonnet) + `security-reviewer` (sonnet) parallel |
| New prod code without test / "TDD this" / "write tests for X" | `test-engineer` (sonnet) |
| "scan for secrets" / pre-release / new env-var / `.github/workflows/` edit | `security-reviewer` (sonnet) |
| New `claude/*` branch from handoff / phase complete / PR open | `phase-coordinator` (sonnet) |
| CI check failed (webhook event) / "CI fail" / "Python test red" / "build แตก" / "เช็คทำไม CI fail" | `ci-triage-engineer` (sonnet) |
| "ดู preview" / "is deploy green?" / pre-Mark-Ready on UI-touching PR / Vercel preview URL just posted | `vercel-preview-auditor` (sonnet) |
| "ลองใช้ app (จริง)" / "expert user feedback" / "ใช้งานจริงดูหน่อย" / "UX จริง" / "is the app actually usable?" / post-cron experiential pass | `expert-user-explorer` (sonnet) |
| "find me the paper that says X" / "หาเปเปอร์เรื่อง Y" / methodology cite outside CLAUDE.md anchor list / new defense-flag prior | `literature-searcher` (sonnet) |
| "design a new valuation method / factor / scoring pillar / defense flag" / "ออกแบบ factor / โมเดล quant" / "scope Phase 5/6/7" / "should we add signal X" (construct doesn't exist yet) | `financial-engineer` (opus; generative design) → then `methodology-scientist` to ratify |

Pattern not in the table → walk the description fields of all 20
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

**Sonnet sub-agents fire on edit; opus agents wait for gate.** This
is the split discipline that drains the Max-plan "Weekly · Sonnet
only" pool without burning the "Weekly · all models" pool. Each
sonnet agent has a non-trivial-edit cue in its domain (rows
below). The five opus agents (`quantrank-reviewer` ·
`methodology-scientist` · `release-captain` · `incident-commander` ·
`financial-engineer`) stay rare-fire on gates or signals. Dedup window ~10 min — if the
same sonnet agent ran on the same diff and it hasn't moved, point
at the prior result instead of re-spawning. The "ready to push"
gate still fires as a safety net (opus reviewer + a re-batch of
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
| Production cron fails / hangs / produces corrupt output, OR Vercel deploy breaks, OR schema-snapshot CI fails, OR user says "production is broken" / "site is down" / "incident" | `incident-commander` (opus; P1 orchestrator) | Immediate |
| GitHub Actions check fails on any open PR (webhook PR-activity event) OR user says "CI fail" / "Python test red" / "build แตก" / "เช็คทำไม CI fail" | `ci-triage-engineer` (sonnet) | Signal-driven, on webhook; reactive — proposes one-line fix |
| Pre-Mark-Ready on a UI-touching PR OR new Vercel preview URL posted OR user says "ดู preview" / "is deploy green?" / "spot-check the preview" | `vercel-preview-auditor` (sonnet) | Gated; runs Vercel MCP build+runtime+UA-probe before Playwright is scheduled |
| Post-cron green OR pre-release OR after `vercel-preview-auditor` GO on a UI PR OR user says "ลองใช้ app" / "expert user feedback" / "UX จริง" / "is the app usable?" | `expert-user-explorer` (sonnet) | Gated; builds+serves the static export locally, drives headless Playwright through a persona mission; read-only, proposes issues. NOT per-edit (that's `frontend-design-reviewer`) |
| methodology-scientist verdict cites a paper outside CLAUDE.md anchor list AND the actual paper text matters, OR user says "find me the paper that says X" / "หาเปเปอร์เรื่อง Y" / new defense-flag academic prior is proposed | `literature-searcher` (sonnet) | On-demand; offloads retrieval so methodology-scientist (opus) stays on judgment |
| `workflow_dispatch` on `compute-rankings.yml` lands green | `defense-layer-auditor` Section A-L + Section I (Playwright) + `stock-detail-auditor` (per-stock data audit) + `expert-user-explorer` (experiential P1 mission on the fresh data) | Auto post-cron, parallel; all sonnet |
| Quarterly cohort audit scheduled date reached (next 2026-08-19) | `methodology-scientist` (opus) Mode C + `defense-layer-auditor` (sonnet) | Scheduled, sequential |
| User says "design a new valuation method / factor / scoring pillar / defense flag" / "ออกแบบ factor / โมเดล quant" / "scope Phase 5/6/7" / "should we add signal X" (the construct doesn't exist yet) | `financial-engineer` (opus; generative design) → then `methodology-scientist` to ratify the prior | Rare; design precedes validation (Flow 8) |
| New defense flag proposed (new risk_flag in `compute/scoring/`) | `methodology-scientist` (opus; validate paper anchor) + `test-engineer` (sonnet; positive + negative tests) | Rare; sequential — methodology first |
| Threshold / weight constant changed in `compute/scoring/manipulation_index.py` or `earnings_quality.py` | `methodology-scientist` (opus) Mode B | Rare; on the edit |
| User says "ก่อน push" / "ready to push" / "open PR" / "mark ready" / "ตรวจก่อน push" | `quantrank-reviewer` (opus) + `phase-coordinator` (sonnet) Mode B. Conditional sonnet re-batch on the same gate: `schema-sentinel` / `defense-layer-auditor` / `frontend-design-reviewer` / `docs-reviewer` / `security-reviewer` / `test-engineer` (skipped per-agent if the dedup window confirms it already ran on this diff) | Parallel pre-push safety-net gate |
| User says "ตรวจ data หุ้น" / "check stock data correctness" / "audit the output" / "verify the output" / "ตรวจ output" / pre-release | `stock-detail-auditor` (sonnet; deterministic prefilter then thorough LLM verdict for every flagged ticker) | One sonnet spawn, thorough |
| User says "tag release" / "cut a release" / "release vX.Y.Z" / "ตัด release" / phase-epic PR just merged | `release-captain` (orchestrator; spawns ladder agents as needed) | Owns release ladder |
| User asks to create a new `claude/*` branch from a handoff prompt | `phase-coordinator` Mode A | Before first non-trivial edit |
| Phase / sub-PR marked complete on this branch | `phase-coordinator` Mode C | After merge / on close |
| Diff > 200 lines on `compute/scoring/` OR user says "full review" / "deep review" | `quantrank-reviewer` with `model: opus` override | Rare; user authorization required |

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
  reviewer` + `financial-engineer` all opus by design; the other 15
  sonnet) as they are — opus agents land on the "Weekly · all models"
  pool; sonnet agents drain the underutilized sonnet pool. Tune the
  5-vs-15 split only when usage data justifies it. **All 20 agents also
  carry `effort: max`** (frontmatter, 2026-05-31) — orthogonal to
  `model`: `model` picks opus-vs-sonnet, `effort` (low/medium/high/
  xhigh/max) sets reasoning depth and overrides the session's inherited
  level. Every agent is a correctness / judgment gate, so max pays back;
  sonnet-at-max still drains the Sonnet-only pool. A new agent gets
  `effort: max` too (README §Authoring conventions #3).
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

## Gotchas

- **`compute/cache/` is gitignored.** Cold-cache compute runs hit SEC
  EDGAR live and can take 25-50 min depending on throttling. Warm-cache
  runs finish in under 5 min.
- **`shares_outstanding` is wrong for ~12 tickers** (issue #10) — Step
  7.5 sanity guard fires `data_quality_input_corruption` on the worst
  cases (issue #18 closed: this flag is a veto now). A separate
  **partial-extraction** failure mode — `shares_outstanding=None`
  despite company-level revenue + balance sheet being present (STZ
  2026-05-14 pattern, issue #176) — surfaces via the
  `share_count_extraction_missing` annotate (PR #181) AND has a live
  recovery path via `_fetch_shares_from_per_filing_xbrl` (PR #182).
  Root cause: SEC's `companyfacts` aggregate API filters out
  dimensional facts; STZ files share counts only with Class A /
  Class B dimensions. The fallback pulls per-filing XBRL
  (`Filing.xbrl().facts.get_facts_by_concept`) for the most recent
  10-K / 10-Q and sums the dimensional `dei:EntityCommonStockSharesOutstanding`
  contexts. Triggered ONLY when the primary extraction returns
  ``None`` AND `revenue > 0` AND `total_assets > 0` (PR-#181
  signature). **Cron-#3 silent-failure gap closed on this PR**:
  PR #182's outer `except: return None` was bare — when the fallback
  failed under cron load (2026-05-23 STZ regression: worked in
  2026-05-21 live probe, returned None two days later under SEC 429),
  the operator had no log line distinguishing transient 429 from
  structural XBRL drift. This PR threads `ticker` into
  `_fetch_shares_from_per_filing_xbrl` and emits `logger.warning(...
  shares_outstanding fallback FAILED ...)` on the outer except;
  inner exceptions log at `DEBUG`. Annotate
  `share_count_extraction_missing` keeps firing as the safety net.
- **`eps_basic` / `eps_diluted` display fields now derive from
  `NI_TTM / shares_outstanding`** (DD cron-#3 fix) — `compute/main.py`
  `_build_raw_metrics` previously passed `snapshot.eps_diluted`
  (XBRL `EarningsPerShareDiluted` concept) raw to `RawMetrics`. That
  concept returns the **latest single-period value** per
  `fundamentals.py:114-117` — for a quarterly filer that's one
  quarter's EPS, NOT TTM. DD on the 2026-05-23 cron showed
  `eps_diluted=0.39` against `net_income=$7M / shares=410M = $0.017`
  (~23× off). The valuation chain (`pe_ratio_ttm`) was already on
  the NI/shares path since audit #6 / PR #49, so internal consistency
  held — but `/stock/DD` rendered the wrong EPS to users. This PR
  computes `ttm_eps = NI / shares` once and uses it for BOTH
  `eps_basic` and `eps_diluted` display fields (basic-vs-diluted
  spread on the S&P 500 is typically < 1-3%, within display
  precision). `pe_ratio_ttm` formula unchanged.
- **`_avg_3y_roe` fallback removed** (issue #11, 2026-05-21) — PR 4c
  earlier added the per-year stockholders_equity denominator path but
  kept a fallback to single-period equity when history was incomplete,
  preserving the original bug for ~30% of the universe. This PR drops
  the fallback (returns `None` instead) AND introduces a distinct
  `insufficient_history_for_roe` skip reason so the ensemble doesn't
  emit a spurious `value_trap_risk` warning when RIM is skipped for
  missing data. Tickers with < 3y of equity history lose RIM as an
  applicable method; the 5 other valuation methods still cover them.
- **Going-concern phrase scan FP rate dropped to 1.0%** on the
  2026-05-20 cron (within Mayew 2015 expected 1-3% band, down from
  10.8% pre-Phase-4h). Mechanism not yet code-confirmed — issue #16
  negation lookbehind may have been side-effect-fixed by the Tier-2
  8-K scan integration. Verify root cause + decide whether to close
  issue #16 at the Q3 cohort audit (2026-08-19).
- **`loss_avoidance_pattern` thresholds rescaled** (Phase 2.4,
  2026-05-21) — Burgstahler-Dichev 1997 cohort thresholds were
  rescaled 10× to S&P 500 scale (NI ≤ $50M / EPS ≤ $0.50) after
  Phase 4.5d's original $5M / $0.05 fired 0% on the universe.
  Annotate-only — composite rank unaffected. Phase 4b
  (2026-05-21) closed the size-invariance follow-up by adding the
  sibling annotate `loss_avoidance_pattern_size_invariant`
  (Roychowdhury 2006 *JAE* §5.2 suspect-firm:
  ``NI / TotalAssets ∈ [0, 0.005]`` for 3+ consecutive years).
  Both flags ship side-by-side annotate-only pending the Q3
  2026-08-19 quarterly-audit decision (retire one, keep both,
  or split weights vs `rem_suspect` which shares the Roychowdhury
  paper anchor but a different sub-trigger).
- **Hypothesis property-based tests** are the new defense line for
  data-shape bugs (issue #126). Pair each new shape assumption (port
  cardinality, pillar count, manifest partition) with a `@given`
  property in `tests/**/test_*_properties.py`. Don't use
  `@settings(deadline=None)` — a slow example is itself a signal.
- **CI escape-hatch env-var combo for simulate** (5 vars, all set
  together in `.github/workflows/pre-merge-prod-sim.yml`; NONE set in
  weekly cron `compute-rankings.yml`): `FORM4_FETCH_SKIP=1` (skip Form-4
  bulk fetch — read at `compute/main.py:879`; safe empty default),
  `QR_SKIP_TIER2=1` (skip Tier-2 10-K text + 8-K fetch — read at
  `compute/scoring/tier2.py:162`), `QR_SKIP_FUNDAMENTALS=1` (skip
  fundamentals freshness gate — read at `compute/ingest/fundamentals.py`
  in BOTH `fetch_fundamentals` + `fetch_fundamentals_history` BEFORE
  `_require_identity()`), `QR_SKIP_OSAP=1` (skip OSAP openassetpricing.com
  bulk download — read at `compute/ingest/osap.py:fetch_osap_returns`
  BEFORE the `_is_fresh` check), and `QR_SKIP_CROSS_SOURCE=1` (skip
  the 502-ticker yfinance.info cross-source validation loop — read at
  `compute/ingest/cross_source.py:fetch_yfinance_market_cap` at the
  TOP of the function; bypasses 24h cache TTL on stale-but-present
  entries; returns None on cache-miss). Each falls through to live
  fetch if no cached parquet exists, or to "no validation possible"
  in the cross-source case. Together they cover the FIVE independent
  external-data loops in `compute/main.py` — the four discovered by
  PR #230's iteration plus the 5th (cross_source yfinance.info)
  identified by PR #241's ci-triage-engineer session-6 root-cause.
  CI-only — never set in cron / local dev. Simulate workflow
  expected steady-state with all five skips active on a warm-cache
  restore: 8-15 min (vs the pre-fix 45-min cap breach across PRs
  #230 / #238 / #241).
- **GitHub-Actions-injected env-vars `GITHUB_RUN_ID` + `GITHUB_SHA`**
  — auto-provided by the GitHub Actions runner; read at
  `compute/main.py:2084-2085` via `os.environ.get(...)` with safe
  empty defaults; surface into `Metadata.compute_run_id` +
  `Metadata.git_commit` for downstream audit trail (verify-helper
  Section A reads both). Not operator-managed — no value to redact.
  Listed here so the env-var inventory of CLAUDE.md §Gotchas stays
  exhaustive (security-reviewer 2026-05-28 baseline flagged the doc
  gap as W1).
- **`Metadata.*_wall_clock_seconds` ≠ `fundamentals_latency_p95_seconds`**
  (Issue #287 PR A, 0.10.9-phase4.6) — they look like sibling latency
  metrics but measure ORTHOGONAL things and BOTH are needed for cron
  diagnostics. `fundamentals_latency_p95_seconds` = p95 of per-ticker
  fetch times collected in the `fundamentals_latency` dict (tenacity-
  cascade detector — useful for spotting per-ticker slowness or SEC
  CIK-specific weirdness even when the loop wall-clock looks fine).
  `tier2_wall_clock_seconds` / `form4_wall_clock_seconds` /
  `osap_wall_clock_seconds` / `cross_source_wall_clock_seconds` = total
  elapsed wall-clock for the entire loop start-to-end via
  `time.monotonic()` (budget-overrun + cache-eviction detector). On a
  warm cache the wall-clock may be 5-10s while p95 is 15s+ (most
  tickers return instantly; a handful spike). On cold + throttled the
  wall-clock can be 30+ min while p95 only reaches 30s (slow tickers
  serialize through the thread pool). **None semantic varies per loop**:
  `FORM4_FETCH_SKIP=1` → `form4_wall_clock_seconds = None` (start marker
  is INSIDE the `else:` branch). `QR_SKIP_OSAP=1` → `osap_wall_clock_seconds`
  populates a SMALL FLOAT (~0.5-2s; only the freshness gate is bypassed,
  not the try block). `QR_SKIP_TIER2=1` → `tier2_wall_clock_seconds`
  populates a small float (each worker returns ~0ms). Outer-try failure
  on any loop → `None`. `cross_source_wall_clock_seconds` measures the
  ENTIRE Step 8 per-ticker loop (fair-price + manipulation + StockDetail
  write), not just the cross-source sub-calls — documented limitation;
  on cold the cross-source dominates, on warm the rest does.
- **Sub-agent `tools:` frontmatter does NOT auto-inherit MCP tools**
  — surfaced 2026-05-23 by the post-PR-#225 live-fire of
  `vercel-preview-auditor`. The Claude Code sub-agent runtime restricts
  each sub-agent's tool surface to what's listed explicitly in the
  agent file's `tools:` field; MCP tools must be enumerated by their
  full name (`mcp__<server>__<tool>`). The GitHub MCP server uses a
  stable `mcp__github__*` namespace, but OAuth connectors like Vercel /
  Supabase / Sentry register under an OAuth-connection UUID
  (`mcp__0addee55-...__list_deployments`) that is **install-specific**
  — a fresh clone by a different user would have a different UUID and
  the agent's pinned tool list would silently fail to match. Both
  affected agents (`vercel-preview-auditor` + `ci-triage-engineer`)
  now carry a hard-constraint bullet that requires explicit gap
  surfacing + main-agent escalation when the listed MCP tools aren't
  reachable in the sub-agent's context. The main agent retains full
  MCP access and can run the check inline OR re-spawn the sub-agent
  with the correct tool surface.
- **Release tags are mobile-only (locked 2026-05-27)** — the user
  operates GitHub from a phone only; no desktop, no `gh` CLI, no
  terminal. The sandbox itself **cannot push tag-refs** either
  (HTTP 403 from the git proxy — confirmed during the v1.3.0 +
  v1.4.0 cut on 2026-05-27). All release-tag + GitHub-Release-
  creation steps MUST be delivered as **pre-filled GitHub URLs the
  user taps once**, never as `git tag` / `git push origin <tag>` /
  `gh release create` shell commands. Pattern: build a single URL of
  the shape `https://github.com/dackclup/quantrank/releases/new?tag=<TAG>&target=<40-char-SHA>&title=<URL-ENC>&body=<URL-ENC>`
  with a **short body** (≤ 2 KB encoded) that links to the full
  release notes file already on `main` — the URL must stay under
  GitHub's 8 KB server-side limit. Multi-release ladder ordering:
  **publish newest FIRST with "Set as latest" ✅, retroactive/older
  LAST with "Set as latest" ❌** — avoids the auto-flag-latest
  footgun caught on 2026-05-27 (v1.3.0 retroactive accidentally
  became Latest until manually re-promoted via the edit URL).
  Codified in [`.claude/skills/release-tag/SKILL.md`](.claude/skills/release-tag/SKILL.md)
  §"Mobile-operator release workflow" + [`.claude/agents/release-captain.md`](.claude/agents/release-captain.md)
  Step 5.
- **Parallel-PR §Phase status collision pattern** (RESOLVED
  2026-05-24 via [`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md)
  side-file adoption) — historical record: every PR was required to
  add a §Phase status entry to CLAUDE.md + AGENTS.md per the
  §Conventions "ship with every PR" rule. The pre-2026-05-24
  structure inserted every "in flight" bullet at the SAME line
  (just before "**Next deliverables**"). Two PRs opened in parallel
  both targeted that line → second-to-rebase hit
  `mergeable_state: dirty` → the recurring
  "merge ไม่ได้ หลังแก้แล้วกลับมาเป็นอีก" pattern. PR #230
  (`docs(form4)+ci(simulate)`) hit this **3 times in one session**
  while iterating on the simulate-cap fix (vs PR #229, then PR
  #232 + #233, then PR #234 + #235 + #236). Structural fix landed
  in this PR: new in-flight entries go in `PHASE_STATUS_INFLIGHT.md`
  (append-only-per-PR; parallel PRs touch disjoint last-lines and
  `git merge` auto-resolves). CLAUDE.md §Conventions updated to
  point at the side-file as the canonical destination. The
  rebase-before-Mark-Ready discipline still applies for OTHER
  conflict surfaces (shared code edits, workflow YAML, schema
  bumps) but is no longer the recurring drag it used to be.
  Housekeeping workflow to drain merged entries from
  `PHASE_STATUS_INFLIGHT.md` into CLAUDE.md §Phase status proper
  deferred (manual cleanup is fine for the first few weeks while
  the pattern proves itself; `tools/housekeep_phase_status.py`
  may land later once volume + shape are known).
- **Lint the WHOLE repo before push, never per-file** (recorded
  2026-05-29 after PR #310 went CI-red on a self-inflicted lint
  miss). The §Commands verification ladder already says
  `ruff check .` — the trap is running `ruff check <changed-file>`
  instead, to "save time" on a focused diff. It silently passes
  while a DIFFERENT file fails. The PR #310 failure mode: commit 1
  changed two `compute/` files (I linted just those two — clean);
  commit 2 added a test file with two `UP037` redundant-quote
  annotations (`df: "pd.DataFrame"` under `from __future__ import
  annotations`) — never linted locally because it wasn't in my
  per-file list. CI runs `ruff check .` and caught it instantly.
  **Correct procedure**: run `ruff check .` (no path argument) as
  the LAST step before every `git push`, especially on a multi-
  commit branch where a later commit adds files the earlier
  per-file pass never saw. Per-file `ruff check <f>` is fine for
  fast inner-loop iteration, but it is NOT the pre-push gate — the
  pre-push gate is the full ladder verbatim. Same discipline for
  `pytest -m "not network"` (whole suite, not just the one test
  file you touched) — a verbatim-copy test helper or a cross-module
  import can fail elsewhere.
- **`html, body` are globally `overflow-x: clip`** (`frontend/app/globals.css`,
  PR #322). Keep `clip` — NOT `hidden`: both stop the page from widening, but
  `clip` creates NO scroll container, so the `position: sticky` sidebar +
  header keep working (`overflow: hidden` would break them). Consequence:
  page-level horizontal scroll is intentionally impossible — a genuinely wide
  surface must nest its OWN scroll container (`overflow-x-auto` on the inner
  element, as `RankingTable`'s desktop table does), never rely on the page
  scrolling. Why it exists: the price-chart `AreaChart` remount (crosshair
  re-park on release) transiently overflowed, and the `fixed inset-0` sidebar
  backdrop then sized itself to the widened layout viewport and SUSTAINED it
  as phantom right-side scroll (only reproducible under mobile emulation — a
  plain desktop viewport hid it). `overflow: clip` is Safari 16+ / Chrome 90+;
  pre-Safari-16 silently degrades to the prior behavior (not a regression,
  just unfixed on that old sliver).
- **Root font-size is FLUID** (`frontend/app/globals.css` `html { font-size:
  clamp(1rem, 0.89rem + 0.45vw, 1.125rem) }`, 2026-05-29). The whole app is
  rem-based (Tailwind `text-*` / spacing / gaps / chart `h-64` all in rem), so
  the root font-size scaling with the viewport scales EVERYTHING proportionally
  — ~16px on phones (≤~390px, the clamp floor) → ~18px on tablet+ (the ceiling
  engages ~835px; lowered from 20px per the 2026-05-29 layout-density audit). Consequences for future code: (a) use rem-based Tailwind text
  utilities (`text-sm`, `text-2xl`, …) so new text scales with the system —
  an arbitrary `text-[14px]` is a FIXED px that will NOT scale and will drift
  out of proportion on desktop; (b) do NOT add a second `font-size` on `html`
  / `:root` / `body` (a `font-size` on `body` would re-resolve `rem` against
  the already-fluid `html` and compound the scale); (c) the `rem` terms in the
  `clamp` (not pure `vw`) are intentional — they keep browser zoom / user
  font-size prefs working (pure-vw font-size breaks WCAG 1.4.4 resize). A few
  chart-internal SVG labels sized in raw px (Recharts `tick fontSize`) are a
  known minor holdout — they don't follow the rem scale.

- **Sidebar `data-rail` attrs ↔ `globals.css` pre-paint rules move in
  lockstep** (`frontend/components/Sidebar.tsx` + `frontend/app/globals.css`,
  PR #326). The collapsed sidebar is rendered BEFORE React hydrates: a
  pre-paint inline script in `frontend/app/layout.tsx` adds `.sidebar-collapsed`
  to `<html>` from `localStorage['quantrank.sidebar.collapsed']`, and
  `html.sidebar-collapsed [data-rail="…"]` rules in `globals.css` mirror the
  `collapsed ? 'md:…'` Tailwind classes `Sidebar.tsx` applies at runtime. Five
  `data-rail` values are in use: `hide` · `show` · `header` · `navlink` ·
  `chevron`. Add a new collapsible Sidebar element WITHOUT a matching
  `html.sidebar-collapsed [data-rail="<new>"]` rule and the "sidebar opens then
  shrinks back / text flashes for a frame on refresh + rotation" regression
  returns for that element. `AppShell` keeps the `<html>` class synced to the
  live collapsed state (`classList.toggle`) so the CSS never fights React
  post-hydration. The aside transition is also gated behind an `animate` flag
  (true only ~250ms around an explicit toggle) + `motion-reduce:transition-none`
  so refresh / rotation switch width INSTANTLY (no animated shrink). The
  animated transition list MUST include `max-width` alongside `width` (PR #330):
  the collapsed rail toggles `md:max-w-[64px]` AND the pre-paint rule sets
  `max-width:4rem`, so an un-transitioned `max-width` snaps to the collapsed cap
  the instant `collapsed` flips and CLAMPS the rendered width to 64px — the
  `width` animation is nullified, so collapse "snaps" while expand (a GROWING
  max-width never clamps) stays smooth = asymmetric jank. `max-width` is
  load-bearing (not removable): it caps the fluid-rem `md:w-60` — which is
  ~270px at the font-size ceiling — down to a stable 240px.
- **Re-parking the price-chart crosshair MUST debounce the `<AreaChart>`
  remount ≥ ~300ms** (`frontend/components/PriceHistoryChart.tsx`, PR #326).
  Recharts 2.15 applies `defaultIndex` (latest-point park) only on MOUNT. A
  WIDTH change — window resize, device rotation, OR the sidebar expand/collapse
  reflowing the content width — makes `ResponsiveContainer` re-measure over
  ~100-200ms. Bumping the `<AreaChart key>` remount key immediately re-parks
  against the OLD width → the crosshair lands at index 0 (far LEFT). A
  width-delta `ResizeObserver` debounced ~300ms lands the remount AFTER the
  re-measure so it re-parks at the latest point. Shorten / remove the debounce
  → the "crosshair jumps left on sidebar toggle" regression returns. This
  ResizeObserver subsumes the old orientation-only `matchMedia` re-park
  (rotation changes width too).
- **App-wide motion uses ONE `ease-in-out` timing curve** (2026-05-30,
  PR #330). Every discrete move / entrance / slide / sweep accelerates out
  of the start and decelerates into the end — one calm, symmetric feel across
  the whole app. Concretely: `tailwind.config.ts` `animation` (`fade-in` /
  `rise-in` / `chip-pop` / `flag-pulse`), `globals.css` `.gauge-sweep` +
  `.hover-lift`, the `Sidebar` collapse/expand + `FilterDrawer` slide-over
  transitions, and the JS rAF easings in `PriceHistoryChart.tsx` (intro sweep)
  + `useMotion.ts` (`useCountUp`) all use `ease-in-out` — the CSS keyword /
  Tailwind `ease-in-out` class / `easeInOutCubic = t<0.5 ? 4t³ :
  1−(−2t+2)³/2` in JS. A NEW animated component MUST follow suit — do not
  introduce a one-off `ease-out` / `ease-in` / `cubic-bezier`. TWO deliberate
  carve-outs: (1) `shimmer` stays `linear infinite` — ease-in-out on a
  seamless background-position loop stutters at the wrap boundary (slow-end
  meets slow-start = a visible stall); (2) a bare Tailwind `transition-*`
  with no explicit `ease-*` already compiles to `cubic-bezier(0.4,0,0.2,1)`
  ≈ ease-in-out, so it needs no change. `chip-pop`'s overshoot (70% → 1.04)
  and `flag-pulse`'s settle (55% → 1.012) now live entirely in the keyframe
  %-stops, not the timing curve — the curve just eases into them. The
  `@media (prefers-reduced-motion: reduce)` guard in `globals.css` still
  neutralizes every one of these.

- **The stock-detail hero splits on a CSS CONTAINER QUERY, not a viewport
  breakpoint** (`frontend/app/stock/[ticker]/page.tsx` + `frontend/app/globals.css`
  `.hero-card` / `@container hero (min-width: 46rem)`, PR #332). The hero lays
  out name-block-left / stats-block-top-right when there's room and falls back
  to the vertical mobile-portrait stack when squeezed — but the decision is
  driven by the hero's OWN inline-size (`container: hero / inline-size` on the
  `<header>`), NOT `md:`/`lg:` viewport prefixes. **Why it must stay a container
  query**: the left `Sidebar` eats a viewport-VARIABLE slice (expanded 240px /
  collapsed 64px / mobile-drawer 0px), so at one fixed viewport the hero's real
  width differs by ~180px depending on sidebar state. A viewport `md:`/`lg:`
  gate therefore left a DEAD BAND (768–1023px) where the sidebar was already a
  desktop rail but the hero still stacked — the bug the user hit 2026-05-31.
  The container query measures the space the hero actually has AFTER the sidebar
  takes its cut, so the row engages exactly when both columns fit. Consequences
  for future edits: (a) the JSX default classes are the STACKED `flex flex-col`
  (`hero-split` / `hero-left` / `hero-right`); the `@container` rule only ADDS
  the row behavior, so pre-2023 browsers without `@container` degrade to the
  safe stack — do NOT "simplify" the hooks back to `md:flex-row`; (b) the 46rem
  threshold ≈ left name block + the ~18rem stats block + gap headroom — retune
  it against BOTH sidebar states, not just one viewport; (c) `@container` is
  raw CSS in `globals.css` (no `@tailwindcss/container-queries` plugin / no new
  dep — Tailwind compiles the raw rule through fine, verified in the built CSS).
- **MoS gauge arc direction is SIGN-AWARE** (`frontend/components/MoSBadge.tsx`,
  PR #332). The Margin-of-Safety donut shares `ScoreGauge`'s sweep + count-up
  motion, but unlike the score (0–100, always clockwise) MoS is signed:
  **MoS ≥ 0 sweeps clockwise** (same as the score gauge — upside reads like a
  high score); **MoS < 0 sweeps counter-clockwise** (overvalued visibly "runs
  the other way"). The reversal is a `-scale-x-100` on the gauge CONTAINER when
  `mos < 0` — it mirrors the rendered ring CW→CCW robustly, with no fragile
  `rotate ∘ scale` composition against the SVG's internal `-rotate-90`; the
  centered number `<span>` carries its OWN `-scale-x-100` so it un-mirrors back
  to readable (scaleX(-1)×scaleX(-1)=identity). 329/502 of the current universe
  is negative MoS, so the CCW path is the COMMON case, not an edge — keep both
  mirrors in lockstep if you touch either (drop the span's mirror and every
  negative-MoS number renders backwards). Accent stays emerald (≥0) / rose (<0).

- **Subagent model aliases float forward to the LATEST — guard the downgrade
  vector, not the agent files** (`.claude/agents/*.md` + `tools/check_model_pin.py`,
  2026-05-31). All 20 agents use bare `model: opus` / `model: sonnet` aliases.
  Per the Claude Code docs an alias resolves to the newest Opus/Sonnet at
  runtime and floats forward automatically on a CLI update — so the project is
  "always latest" by design; **never pin a dated/numbered model ID** (e.g.
  `model: claude-opus-4-8`) in an agent, that's a future-dated downgrade the day
  a newer model ships. The real downgrade risk is NOT in the agent files — it's
  an **environment override**: a `CLAUDE_CODE_SUBAGENT_MODEL` or
  `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL` committed into
  `.claude/settings.json` pins every subagent to a specific (possibly older)
  version WITHOUT touching a single agent file — an invisible downgrade. CI
  enforces both halves: `tools/check_model_pin.py` (wired into `ci.yml` as the
  "Subagent model-pin guard" step) fails the build if committed settings carry
  any of those override vars (the one benign value is
  `CLAUDE_CODE_SUBAGENT_MODEL='inherit'`) OR if an agent frontmatter pins a
  non-alias model ID. `effort: max` is orthogonal and unaffected (it tunes
  reasoning depth, not which model). Per-user `.claude/settings.local.json` is
  gitignored so it's out of scope for the committed guard — a local operator
  can still self-downgrade their own machine, but it can't land on `main`.
  **Second out-of-scope vector** (security-reviewer 2026-05-31): the guard
  inspects committed files only, so a `CLAUDE_CODE_SUBAGENT_MODEL` /
  `ANTHROPIC_DEFAULT_*_MODEL` set as a **GitHub Actions repository secret** or
  in a workflow-level `env:` block in another `.github/workflows/` file would
  reach the runner without touching `settings.json` and bypass this check —
  don't add one (there's no legitimate reason to pin the subagent model in CI).

- **`RiskSummaryCard` merges rank-gates + manipulation-index into ONE card
  but the two sub-sections are SEMANTICALLY DISTINCT — never flatten them
  into a single list** (`frontend/components/RiskSummaryCard.tsx`, PR #337;
  replaced the former `RiskFlagsCard` + `ManipulationRiskCard`). The card
  renders TWO sub-sections: **RANK GATES** (`risk_flags[]` — Rule-16 Top-5
  disqualifiers; `altman_distress` + `data_quality_input_corruption` also
  force a cautious recommendation) and **MANIPULATION INDEX** (the 0-100
  rollup — INFORMATIONAL soft penalty, rank uses raw composite). They share
  some flag NAMES but the overlap is asymmetric BOTH directions:
  `altman_distress` / `data_quality_input_corruption` /
  `net_issuance_top_decile` / `stale_filing_hard` are rank gates NOT in the
  manipulation index; the annotate-only flags (`accruals_momentum_high`,
  `beneish_high`, `restatement_history`, `rem_suspect`, …) are in the index
  but NEVER in `risk_flags`. A flat merge under one "Manipulation Risk"
  header would mislabel `altman_distress` (financial distress, not earnings
  manipulation) — that is the footgun. **De-dup contract** (load-bearing):
  a flag that is BOTH a rank gate AND a fired manipulation component shows
  ONLY in RANK GATES; the manipulation sub-section lists only the
  annotate-only SURPLUS via `alsoFired = firedComponents − gateSet` under
  the "Also fired — not rank-gating" label. Drop the set-difference and the
  shared flags (sloan / beneish_veto / …) render TWICE again — the exact
  on-screen duplication this card was built to fix (82/502 of the current
  universe carry both a gate and a manipulation component). Outer ring =
  worst-case (rose if any rank gate, else the manipulation band tone); the
  band chip (Low/Moderate/High) moves into the manipulation sub-header when
  gates own the outer-header count chip so it's never lost. Returns `null`
  only when BOTH halves are empty (no rank gates AND `manipulation_index`
  is `null` / `undefined` / `0` — `hasIndex` suppresses on a zero index,
  not just null). The two flag-label maps stay separate on
  purpose: `RANK_GATE_META` carries the academic-anchor detail line,
  `MANIPULATION_FLAG_LABELS` is label-only.

- **Background runs (`Agent run_in_background:true` / `Bash run_in_background:true`)
  default to SYNC — and if you go background, you OWN the teardown in the
  SAME session** (process hygiene, 2026-05-31, after a "chevron review"
  agent + an `npm install` bash showed as perpetually-"Running" in the
  Background-tasks panel across a `/compact`). Two distinct zombie classes,
  two distinct fixes:
  - **Background AGENT orphaned by `/compact`** — an async sub-agent spawned
    with `run_in_background:true` is tracked by an `agentId` the harness
    returns at spawn time. A `/compact` (or a context-window roll) drops that
    `agentId` from the live transcript, so the post-compact main agent has NO
    handle to `SendMessage`/stop it — it runs (or sits "Running") forever,
    still billing tokens, and `ps aux` CANNOT see it (it lives in the harness,
    not as an OS process in the container — do NOT "confirm it's dead" with
    `ps`/`pgrep`, that only sees Bash). **Prevention**: default to SYNCHRONOUS
    `Agent` calls (await the result in the one tool block) — that is the
    normal mode and it self-cleans. Reserve `run_in_background:true` for a
    genuinely long job whose completion you will collect in the SAME session,
    BEFORE any compact. If a long run must straddle a compact, tell the user
    so they can Stop it from the panel — the orphaned `agentId` is
    unrecoverable from the agent side.
  - **Background BASH left "Running"** — a `run_in_background:true` Bash with
    no natural exit (`next dev`, `tail -f`, `while true`, an `npm install`
    whose panel entry lingers) shows "Running" until killed. **Prevention**:
    background Bash must have a DETERMINISTIC exit (an `until grep -q …; do
    sleep 0.5; done` that ends in seconds, per the Monitor/Bash guidance) —
    never a server/`-f`/`while true` parked in the background. If you must
    serve (e.g. `next dev` for a Playwright pass), KILL it in the same turn
    you finish with it (`ps … | grep next | awk '{print $2}' | xargs kill`,
    NOT a broad `pkill` — a `pkill` that catches the harness's own shell
    returns a non-zero/144 and CANCELS the rest of your tool batch, which is
    how the parallel-batch nuke on 2026-05-31 happened). A finished
    background Bash that still shows in the panel is harmless (no tokens) —
    the user can Stop it; only flag it if `ps` shows a real live PID.

- **The fair-price detail pair is split INTERPRETATION vs REFERENCE on
  purpose — `FairPriceCard` does NOT repeat the per-method dollar values**
  (`frontend/components/FairPriceBarChart.tsx` + `FairPriceCard.tsx`, PR #339).
  Two adjacent cards both read the SAME `detail.fair_price` object but answer
  DIFFERENT questions, so they were de-duplicated rather than merged (unlike
  the RiskFlags+Manipulation merge — those asked the SAME question). **Card A
  `FairPriceBarChart` ("Fair price check", renders first)** owns the
  INTERPRETATION layer: every applicable method's dollar estimate + a
  cheap/fair/pricey/outlier verdict badge + plain-English narrative + the
  tally ("Of N methods: X cheap …"). **Card B `FairPriceCard` ("Fair price
  ensemble", renders second)** owns the REFERENCE/metadata layer: Median /
  MoS / Max-ex-outliers / Tangible-BVPS stat grid + the defense-flag warning
  chips + the methodology footnote. The former METHOD→VALUE table in Card B
  was REMOVED (PR #339) — it restated the exact dollar values Card A already
  shows per method, so it was pure on-screen duplication. **Do NOT re-add a
  per-method value table to Card B** — per-method dollars live in Card A only;
  Card B's footnote cross-references "the Fair price check above". **The two
  cards also carry DIFFERENT MoS formulas by design and the card boundary is
  what keeps them from looking contradictory**: Card B "Margin of safety" =
  schema `mos_pct = (median − price) / median` (vs FAIR VALUE — the
  Damodaran/Graham definition, the official scoring field, `ensemble.py`);
  Card A "−X% vs today" = `(median − price) / price` (vs MARKET PRICE,
  recomputed inline in `FairPriceBarChart.tsx`). For NVDA that's −175% (Card B,
  clamped "< −99%") vs −64% (Card A) — both correct for their own anchor. A
  future "merge these two cards" idea must FIRST resolve that two-formula
  clash (the reason they stay separate cards, not one).

- **Stock-detail section order is deliberate — score-explanation rides high,
  the warning group frames valuation, raw data sinks** (`frontend/app/stock/[ticker]/page.tsx`,
  PR #340; two-agent reading-order audit `frontend-design-reviewer` +
  `expert-user-explorer`). Top-to-bottom: back-link → hero (identity + Score
  donut + MoS donut + Fair-value/Target/Loss-chance) → Price chart →
  **`PillarRadarChart`** → `Tier2EventCard` → `RiskSummaryCard` →
  `FairPriceBarChart` ("Fair price check") → `FairPriceCard` ("Fair price
  ensemble") → `RawMetricsTable` → Data quality → methodology footnote.
  Load-bearing ordering rules: (1) **`PillarRadarChart` sits right after the
  price chart, NOT below the fair-price pair** — it answers "why is the
  composite score what it is?" (NVDA value-pillar 35 vs quality 91) while the
  hero's score donut is still fresh; moving it back down re-strands the score
  explanation ~1000px from the score. (2) **The warning group
  (`Tier2EventCard` + `RiskSummaryCard`) stays ABOVE the fair-price pair** so
  red flags frame the valuation read (a Beneish veto makes a $36 fair-value
  estimate suspect); both `null`-collapse on clean stocks so the clean-stock
  order is hero → price → pillars → fair-price → raw. The two-agent audit
  deliberately did NOT move the warning group above the price chart (the
  `frontend-design-reviewer` IA suggestion) — `expert-user-explorer` showed
  the current spot optimizes the risk-checker persona correctly; the real gap
  was the **hero being silent about flags**, fixed by (3) the hero **"N risk
  vetoes" rose chip** (renders only when `risk_flags.length > 0`, anchors to
  `#risk-summary` — a `scroll-mt-20` wrapper div around `RiskSummaryCard` so
  the jump clears the sticky header). The chip is keyed on `risk_flags`
  (rank gates — the entered_top5 suppressors), NOT `manipulation_index`
  (informational). Singular/plural via `=== 1 ? 'veto' : 'vetoes'`.

## Phase status

Current schema **`0.10.11-phase4.6`** on `main` (PR #303 merged
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

**Recently merged** (PR #303 → PR #330, 2026-05-29 → 2026-05-31):
- PR #330 `ba218ff` — feat(frontend): motion + price-chart polish — app-wide ONE `ease-in-out` timing-curve unification + `max-width` transition fix for symmetric sidebar collapse/expand (§Gotchas "ONE ease-in-out curve" + sidebar `max-width` load-bearing notes)
- PR #329 `9ee1b32` — feat(frontend): price-chart intro sweep (line + crosshair draw left→right) + remove tooltip price box
- PR #328 `c80b5e8` — fix(frontend): move brand to top header when sidebar collapsed; chevron-only rail (`data-rail="header"` family)
- PR #327 `0303e9f` — docs: CLAUDE.md §Phase status drain (#311–#326) + Section A-L label fix + 2 PR #326 §Gotchas (`data-rail` lockstep · crosshair debounce)
- PR #326 `b82b845` — fix(frontend): sidebar refresh/rotate flash + chart crosshair re-park (width-delta ResizeObserver debounced remount) + no-text-flash pre-paint (`html.sidebar-collapsed` + `data-rail` CSS) + 2 flaky-test guards (`test_ranking_history` shallow-clone skip · `test_osap` class-level API check)
- PR #325 `732853c` — feat(frontend): app-wide fluid responsive scaling (clamp root font-size) + layout-density audit + sidebar collapsed-state polish
- PR #324 `6ca174f` — fix(frontend): tap (no drag) moves the price-chart crosshair to the tap point
- PR #323 `4f7edf1` — fix(frontend): chart reference-line + chip polish (post-#322) + `overflow-x: clip` §Gotcha
- PR #322 `fd04527` — fix(frontend): price-chart crosshair — park-at-latest · touch scrub · tap/scroll re-park · flush right edge + no page-widen
- PR #321 `3640a8e` — fix(frontend): bump stale sidebar footer version chip v1.2 → v1.4.0
- PR #320 `22cd579` — fix(frontend): keep mobile sidebar drawer full when desktop collapsed pref is set
- PR #319 `a49f21c` — docs: fix stale skill-count (45 → 46) across 4 doc homes + correct LESSONS_LEARNED
- PR #318 `79c0aac` — docs: add `docs/LESSONS_LEARNED.md` — agent-process dos & don'ts
- PR #317 `fc886de` — fix(frontend): stack detail hero below `lg` to fix sidebar-expanded gauge/chip overlap
- PR #316 `89c5ee0` — docs(skill): add `web-animation-design` skill (original-prose, inspire-only; skill count 45 → 46)
- PR #315 `aeca318` — fix(frontend): responsive + a11y audit fixes — 320px hero overflow · focus rings · touch targets
- PR #314 `a5e756b` — docs(frontend): fix stale `.gauge-arc` comment ref in ScoreGauge header
- PR #313 `c5251f7` — fix(frontend): animation audit fixes + play-every-visit + gauge keyframe sweep
- PR #312 `e602485` — feat(frontend): app-wide tasteful motion — gauge sweep · row stagger · veto pulse
- PR #311 `10c6221` — docs: reconcile cross-doc drift after the 6-PR session (#303–#310)
- PR #310 `a941e2e` — fix(scoring): inject `stale_filing_hard` before Top-5 rotation (latent Rule-16 fix, closes #309; Step-6b pre-scan + `asof_date` hoist + `ensemble.py` docstring; +5 tests; zero scoring impact, fires 0× on current universe)
- PR #308 `e77efbf` — fix(frontend): correct RiskFlagsCard footer over-claim (only `altman_distress` + `data_quality_input_corruption` force cautious; 27/56 sloan-flagged are lean_bullish) + add latent `stale_filing_hard` key + header "Risk Vetoes" → "Risk Flags"
- PR #307 `bb1d7fd` — feat(agents): Phase B — opus-4.8 orchestrator + dynamic-workflow tuning (uniform `## Handoff` contract on all 19 agents + README §"Dynamic workflow" + Flow 7)
- PR #306 `6ce7c1b` — fix(frontend): render `risk_flags[]` vetoes on stock detail (`RiskFlagsCard`; closes #305 — 137/502 tickers carried an invisible flag)
- PR #304 `e070db6` — feat(agents): add `expert-user-explorer` (19th subagent, Tier 2 Lifecycle; first agent that interactively uses the app)
- PR #303 `847c21b` — feat(scoring): Phase 4.5e PR 6 — Form-4 10b5-1 negation guard (residual footgun #1; schema `0.10.10 → 0.10.11-phase4.6`, new `Metadata.form4_negation_guard_downgrade_count`)

**Earlier** (PR #286 → PR #302, 2026-05-28 — **14 PRs same day post-v1.4.0**):
- PR #302 `c956f06a` — chore(valuation): PR #293 follow-up — Site-2 dead-code removal (`_has_corrupt_input` + `_data_quality_corrupt_result`; cron Run #71 retention-gate confirmed clean; NET −56 prod lines / −84 test lines)
- PR #301 `978cab65` — chore(docs): end-of-day 2026-05-28 .md sweep — fix 8 MUST-FIX + 6 SHOULD-FIX cross-doc drifts (PHASE_STATUS.md schema row + SKILL.md table + WORKFLOW.md tag)
- PR #300 `5fa9a443` — feat(scoring): Issue #67 follow-up — per-sector `value_trap_risk` delta instrumentation (schema `0.10.9 → 0.10.10-phase4.6`; methodology-scientist Mode B Q2 verdict)
- PR #299 `3ec4b29e` — chore(docs): end-of-day housekeeping — drain 3 INFLIGHT (#295/#297/#298) + pointer bumps
- PR #298 `030675e9` — fix(ci): Issue #288 follow-up — bump workflow cache key `cache-v4 → cache-v5` (forces fresh fetch on Run #72 so PR #292 GOOG/GOOGL Branch 3 actually fires; closes silent-failure gap surfaced by PR #297 Rule 18 disambiguator)
- PR #297 `ecb60e64` — feat(perf): Issue #287 PR A — durable timeout + per-loop wall-clocks (schema `0.10.8 → 0.10.9-phase4.6`; `timeout-minutes: 150 → 195` + cache-restore canary + 4 `Metadata.*_wall_clock_seconds` fields; empirically validated cron Run #71)
- PR #296 `e85dfbcf` — docs(context): add root `CONTEXT.md` pointer + reconcile `docs/agents/domain.md` (single-file orientation bridge for upstream tools)
- PR #295 `2d2ec83e` — chore(docs): post-session housekeeping — drain 6 INFLIGHT + bump pointers
- PR #294 `0ddb6b81` — feat(valuation): Issue #67 — flip `USE_SECTOR_COE = True` (Damodaran 11-sector Ke; `value_trap_risk` 132 → 109 cohort drop)
- PR #293 `95e638bf` — fix(valuation): Issue #289 — retire Site-2 DQIC ceiling (NVR FP, methodology Option C)
- PR #292 `e9aaab31` — fix(ingest): Issue #288 — GOOG/GOOGL XBRL concept-name omission (schema `0.10.7 → 0.10.8-phase4.6`)
- PR #291 `cb9114bb` — docs(agents): AGENTS.md substance refresh (cron #51 → #69 pointer; 11 open-issues list)
- PR #290 `dea8e3ad` — chore(cleanup): post-cron-#69 — BK orphan removal + 3 doc drifts
- PR #286 `27361047` — chore(docs): housekeeping PR-B — drain INFLIGHT + bump pointers post-v1.4.0
- (3 issues filed + ALL closed same day: #287 PR A merged via #297 [PR B FORM4 revert remaining] · #288 closed via #292 + #298 · #289 closed via #293 + #302)

**In flight** (not yet merged on `main`):
- **20th subagent `financial-engineer` + doc-drain housekeeping (this PR)** —
  adds the generative quant-design seat (Tier 3 Specialized · opus ·
  read-only; the design counterpart to `methodology-scientist`'s
  validation seat — it PROPOSES a new valuation method / factor / pillar /
  defense flag + academic anchor, then hands off to `methodology-scientist`
  to ratify). Roster 19 → 20 (5 opus / 15 sonnet); coordination flows
  7 → 8 (new Flow 8 quant-design in README). Also drains the #311–#330 doc
  drift surfaced at session start: PRs #327–#330 into this **Recently
  merged** block + #311–#330 into PHASE_STATUS.md §Recently merged +
  subagent-count lockstep across CLAUDE.md / AGENTS.md / CONTEXT.md /
  WORKFLOW.md / PHASE_STATUS.md / README.md. Full entry in
  [`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md) (PR #237 convention).
  Doc + agent-infra only — no compute / schema / scoring / valuation /
  frontend code change.

**Earlier** (PR #264 → PR #285, 2026-05-26 → 2026-05-27):
- PR #285 `8f373758` — docs(release): codify mobile-only operator convention for tag releases
- PR #284 `a820caee` — fix(test): manipulation_distribution smoke resilient to shallow clones (CI `actions/checkout@v6` fetch-depth=1)
- PR #283 `bbca9cac` — chore(release): **v1.4.0-phase4.6** — Honest re-validation harness
- PR #282 `c7cdd881` — feat(validation): Phase 4.6 task #2f — honest-baseline skeleton + CLI (closing the chain)
- PR #281 `858e8666` — feat(validation): Phase 4.6 task #2c — per-pillar Spearman IC at historical dates
- PR #280 `1ef962cd` — feat(validation): Phase 4.6 task #2b — forward-return loader from gitignored price cache
- PR #279 `6a712e82` — feat(validation): Phase 4.6 task #2e — manipulation_index distribution shift report
- PR #278 `e169aba6` — feat(validation): Phase 4.6 task #2a — rankings.json time-series loader (via git-archive)
- PR #277 `b70ea971` — feat(validation): Phase 4.6 task #2 — universe-drift harness
- PR #276 `7480734b` — feat(main): Phase 4.6 writer wiring — universe-provenance Metadata in forward cron
- PR #275 `78ab1d7d` — feat(validation): Phase 4.6 — wire `universe_provider` into pbo_dsr gates
- PR #274 `f2888844` — feat(universe): Phase 4.6 — survivorship-bias fix (historical S&P 500 membership)
- PR #273 `cfa1f709` — docs(research): calibration + 5 PLAN drafts from Research Report v1.0
- PR #272 `65649993` — docs(phase-5): outline PLAN.md for Supabase hybrid (sub-PR 5.0 first commit)
- PR #271 `75b6c682` — docs(workflow): distill Agentic 6-Phase Cadence into WORKFLOW.md + CLAUDE.md
- PR #270 `1bf5bb81` — chore(gitignore): ignore `graphify-out/` build artifacts
- PR #269 `5bf38c12` — feat(ingest): Issue #261 PR-B — per-class XBRL extraction (structural fix for GOOG/GOOGL `$4.6T` overcount; schema `0.10.5 → 0.10.6-phase4.5e`)
- PR #268 `f79548f0` — docs(skill): `good-code-bad-code-review` reference catalog (Miler/milerdev paired good/bad examples; skill count 44 → 45)
- PR #267 `a70978af` — docs: Phase B post-v1.3.0 housekeeping (pointer backfill + drain 11 stale INFLIGHT markers)
- PR #266 `5db3b978` — chore(release): **v1.3.0-phase4.5e** — Form-4 insider clustering + LedgerCraft frontend
- PR #265 `e6013bae` — fix(scoring): Issue #262 — rename DQIC site-2 emission to `valuation_output_anomalous` + writer-parity for veto cohort UI
- PR #264 `d9c62292` — feat(scoring): Issue #261 PR-A — `multi_class_aggregate_shares_suspected` annotate (CIK-collision detector; schema `0.10.4 → 0.10.5-phase4.5e`; flags 32 → 33 declared)

**Epic #150 Phase 1.4 + 1.5 merged via PR #156** (2026-05-20) —
`section_j_annotate_audit()` added to `verify-production-output/helper.py`
so the next quarterly cohort audit (2026-08-19) reads the full
annotate-flag table off the helper instead of grepping source; paired
with `tests/test_verify_helper.py` covering Section A schema reporter +
Section B 4-branch Tier-2 matrix + the new Section J. Phase 1 of
epic #150 (1.1-1.5) closed by PR #156; Phase 1.6 tracked separately
under issue [#155](https://github.com/dackclup/quantrank/issues/155).
Phases 2-3 remaining (threshold recalibration + correlation analysis +
structural). See epic [#150](https://github.com/dackclup/quantrank/issues/150).

**Skill-trigger-flip merged via PR #157** (2026-05-20) — 5 vendored
`mattpocock-*` skill description lines rewritten from `Use when user
wants ...` → explicit `TRIGGER when user explicitly says ...` with
sharp keyword phrases + false-positive guardrails. Body of every
SKILL.md remains upstream-verbatim; divergence catalogued in
`THIRD_PARTY_NOTICES.md` "Description divergence" section. Goal:
reduce false-positive auto-fires of interactive workflows (grill-me,
tdd, to-prd, to-issues, write-a-skill).

**Vendor-sync skill merged via PR #158** (2026-05-20) — new
`.claude/skills/vendor-sync/SKILL.md` codifies the disciplined
upstream-sync workflow for the 4 vendored sources (mattpocock,
multica-ai/karpathy-guidelines, karpathy LLM Wiki gist, 9arm-skills),
including the description-divergence resolution policy carried forward
from PR #157 ("local sharpness wins on description; upstream wins on
body"). Doc-only, no compute / schema change. Use this skill before
pulling new commits from any vendored upstream.

**3 workflow skills bundle merged via PR #159** (2026-05-20) — three
new project-internal workflow skills:
- `claude-md-lockstep-check` — preflight that CLAUDE.md + AGENTS.md
  were both touched on the current branch (enforces the §Conventions
  "ship with every PR" rule that has no CI guard today)
- `release-tag` — end-to-end release workflow: `pyproject.toml`
  version bump + release notes from merged-PR log + annotated tag +
  GitHub Release. Codifies the `vX.Y.Z-phaseN` convention from the
  last 3 releases (v1.0.0-phase3e → v1.2.0-phase4.5)
- `quarterly-cohort-audit` — scheduled walk of defense layer vs
  academic priors with per-flag expected-band table; output lands as
  comment on issue #130 (rolling cohort thread). Next scheduled
  2026-08-19 (Q3)

Doc-only, no compute / schema change. Skill count 39 → 42.

**Epic #150 Phase 1.6 merged via PR #160** (2026-05-20) — explicit
`tier2_enabled: bool` field added to `Metadata` (sourced from
`compute/scoring/tier2._EIGHT_K_DEFENSES_ENABLED` at writer time);
verify-helper Section B now branches on the explicit flag instead of
inferring from `tier2_coverage_pct > 5%`, with legacy-snapshot
fallback. Schema bump `0.9.2-phase4h.2` → `0.9.3-phase4h.3`. Closed
the last open AC item carried forward from issue #117 (PR #149
deferred) and issue #155.

**Epic #150 Phase 2.1 merged via PR #161** (2026-05-20) — explicit
`valuation_methods_applicable: int` field added to `StockDetail` (and
nested in `fair_price` dict), counted as the positive-framed inverse
of `extreme_*_estimate` warnings emitted in `compute/valuation/ensemble.py`.
Surfaces the method-applicability signal explicitly at the schema-
snapshot level so downstream filtering / audits can use it without
deriving from the warning list. Additive only — no consumer migration
in this PR; `loss_chance.py` and `FairPriceBarChart.tsx` keep reading
`extreme_*_estimate` for back-compat. Schema bump `0.9.3-phase4h.3`
→ `0.9.4-phase4h.4`. Defense surface unchanged.

**Epic #150 Phase 2.5 merged via PR #162** (2026-05-20) —
`compute/scoring/manipulation_index.py` weight constants
(`SLOAN_WEIGHT` through `C_SUITE_UNUSUAL_SELL_WEIGHT_RESERVED`)
now carry per-flag provenance docstrings citing the academic source
+ effect-size figure where one exists, OR labeling the weight as
**gut-feel calibration** where the magnitude is engineering choice
rather than literature-derived. Three provenance tiers introduced
in the module docstring: literature-anchored / gut-feel / reserved.
Doc-only — no compute / schema change. Future weight-recalibration
PRs (Phase 2.2 / 2.4) now have a documented baseline to delta from.

**Epic #150 Phase 2.4 merged via PR #163** (2026-05-20) —
`compute/scoring/earnings_quality.py` `LOSS_AVOID_NI_CEILING` rescaled
`$5M → $50M` and `LOSS_AVOID_EPS_CEILING` rescaled `$0.05 → $0.50`
(10× the original Burgstahler-Dichev 1997 Compustat-cohort thresholds)
so the `loss_avoidance_pattern` flag actually fires on the S&P 500
universe instead of the documented 0% pre-rescale. Annotate-only flag
— composite rank unaffected. Module docstring + `manipulation_index.py`
Phase-2.5 provenance comment updated to match. New test
`test_loss_avoidance_ni_just_above_new_ceiling_breaks_streak` pins the
new upper bound. Tests: 945 → 946. No schema / output-JSON change.

**Epic #150 Phase 3 merged via PR #164** (2026-05-20) —
`scripts/phase3_flag_correlation.py` + `docs/phase3-correlation/`
produce a baseline pairwise-φ analysis of the 25 active flags on
production output (502 stocks × 25 flags). Headline findings: defense
layer is mostly orthogonal (35 diversity-confirmed pairs vs 15
redundancy candidates); `restatement_history` is independent of the
Sloan/Beneish manipulation cluster (φ ≈ 0) → Phase 2.2 safe to
proceed; `TRIPLE_FLAG_WEIGHT` may be redundant with Dechow at current
sample size (watch in Q3 audit). Doc + script only — no compute /
schema / output change. Reproducible via the one-shot script;
re-run after every quarterly cohort audit + after each Phase 2.x
recalibration PR lands.

**Epic #150 Phase 2.2 merged via PR #165** (2026-05-21) — new
annotate `restatement_high_confidence` fires when a 10-K/A or 10-Q/A
amendment co-occurs with an 8-K Item 4.02 (non-reliance) filing
within 90 days. Hennes-Leone-Miller 2008 *TAR* "irregularity"
signature — PPV ~70% vs bare `restatement_history`'s ~30%. Three
follow-up fix commits during PR review: (a) capped non-reliance
lookback to 1y instead of 5y (avoided 8-K cache 5y-refetch that
cancelled the simulate workflow at 43m); (b) corrected the weight
from 8.0 (total mis-spec, would have double-counted) to 3.0 (delta);
(c) added 4 missing tests for `get_non_reliance_filing_dates`. Bare
`restatement_history` semantics + weight unchanged; the next-PR
decision (retire bare flag or split weights) waits on a cohort
acceptance check after ≥ 1 production cron. No schema / output-JSON
shape change. Tests: 946 → 962 (+16).

**Issue #11 fix merged via PR #166** (2026-05-21) — `_avg_3y_roe`
removes the legacy single-period-equity fallback that kept the
original Issue #11 bug alive for ~30% of the universe even after
PR 4c added the per-year denominator path. New
`insufficient_history_for_roe` skip reason in
`compute/valuation/applicability.py` distinguishes "missing input
data" from "real value trap signal" — the ensemble no longer appends
a spurious `value_trap_risk` warning when RIM is skipped for missing
data. SKIP_REASONS taxonomy 24 → 25. Side-effect: tickers with < 3y
of stockholders_equity history lose RIM as an applicable method;
the 5 remaining valuation methods cover them.

**Phase 4.5e PR 1 (Scout) in flight (this PR)** — new
`compute/scoring/form4_insider.py` lands the SEC Form 4 fetcher +
cache layer + parser, per the `portable-scout-then-integrate`
pattern. NO production wiring yet — the dep is exercised, the
edgartools Form-4 API surface is locked via `_FORM4_REQUIRED_ATTRS`
manifest tuple + drift-detector test, and the cache shape (one row
per insider transaction, mirrors edgar_amendments/8K siblings) is
validated against synthetic fixtures. PRs 2 + 3 follow:
PR 2 = `Metadata.form4_*` observability surface (no scoring impact);
PR 3 = annotate-only `insider_sell_cluster` + `c_suite_unusual_sell`
emit + threshold calibration against PR-2 cron data + uncomment the
already-reserved `INSIDER_SELL_CLUSTER_WEIGHT` / `C_SUITE_UNUSUAL_SELL_WEIGHT`
constants in `manipulation_index.py`. Tests: 1009 → 1024 (+15).

**Subagent integration in flight (this PR)** — first set of project-
specific Claude Code subagents under `.claude/agents/`. Four agents
land, all on `opus` or `sonnet` (no `haiku` per user direction):
`quantrank-reviewer` (opus; full code review against Rules 1-18 +
schema triple + tenacity policy), `schema-sentinel` (sonnet;
deterministic Pydantic↔TS↔snapshot drift guard pinned to
`compute.config.SCHEMA_VERSION` as the bump point; output JSON key
is `metadata.version`), `defense-layer-auditor` (sonnet; verify-
production-output Section A-J + 27-flag scorecard + Top-5 rotation
Rule 16 check, with accurate section labels A=schema+meta / F=tier2
spotcheck / G=fundamentals resilience / H=universe consistency /
J=annotate inventory), and `edgar-debugger` (sonnet; SEC EDGAR
ingest debug specialist that knows the PR-3d amplification incident,
the strict tenacity policy scoped to SEC-bound modules in
`compute/ingest/fundamentals.py` / `jkp.py` / `osap.py` only — NOT
the lenient policies in `universe.py` / `prices.py` /
`cross_source.py` — plus the `_FORM4_REQUIRED_ATTRS` family of
drift-detector manifests in `compute/scoring/form4_insider.py`).
Subagents are spawned via the `Agent` tool and run in a separate
context window — distinct from `.claude/skills/` (prompt packs the
main agent invokes via the `Skill` tool). Routing matrix + author
conventions in [`.claude/agents/README.md`](.claude/agents/README.md).
Doc-only — no compute / schema / output change.

**Specialized + Operations tiers added (same PR; 8 → 14)** — 6 more
subagents complete the "full enterprise dev team" topology with
specialized-expertise and operations layers, plus 6 codified
coordination flows in `.claude/agents/README.md` that show how the
team integrates: pre-push gate, release ladder, new-defense flow,
incident response, code-review escalation chain, and quarterly cohort
audit. **Tier 3 Specialized**: `test-engineer` (sonnet; TDD + pytest
discipline + Hypothesis property tests; writes test files only —
never modifies production code), `methodology-scientist` (opus;
academic-prior validation against the canonical literature map —
Altman 1968 / Sloan 1996 / Beneish 1999 / Dechow 2011 / Mayew 2015 /
Burgstahler-Dichev 1997 / Hennes-Leone-Miller 2008 / Daniel-Titman
2006 / Damodaran 2019; drives the next quarterly cohort audit
2026-08-19), `performance-engineer` (sonnet; cron latency + cache
health; knows the warm < 5 min / cold 25-50 min / p95 < 15s budgets),
`dependency-auditor` (sonnet; supply-chain + CVE deep triage; owns
the 25-active-CVE baseline + issue #41 Next 14 → 16 tracker). **Tier
4 Operations**: `docs-reviewer` (sonnet; substance-check across the
six top-level docs + METHODOLOGY.md; complements `phase-coordinator`
Mode B which only checks file-touch), `incident-commander` (opus;
P1 production-failure orchestrator that triages symptoms via a
matrix and spawns relevant specialists in parallel — edgar-debugger
/ defense-layer-auditor / performance-engineer / schema-sentinel /
dependency-auditor / frontend-design-reviewer / security-reviewer —
then synthesizes findings into a mitigation plan + post-mortem
skeleton). Subagent count 8 → 14; auto-routing policy table extended
with 9 new cue rows. Doc-only — no compute / schema / output change.

**Enterprise tier added (same PR)** — 4 more subagents wrap the
project's existing lifecycle-event skills into auto-routable surfaces:
`security-reviewer` (sonnet; wraps `security-check`, fires before
release tags / CI workflow edits / new deps — Dependabot CVE triage,
secret scan, EDGAR identity handling), `frontend-design-reviewer`
(sonnet; wraps `frontend-design-system`, fires on `frontend/components/`
diffs — palette discipline, tabular-nums, chip family consistency,
emits Playwright spot-check matrix), `release-captain` (opus; wraps
`release-tag`, fires on "tag release" cues — runs the full pre-flight
ladder, drafts notes from merged-PR log, proposes the exact tag /
release commands for user authorization), and `phase-coordinator`
(sonnet; wraps `branch-collision-check` + `claude-md-lockstep-check`
+ `phase-status-bump` into 3 modes — branch preflight before edits,
agent-doc lockstep before PR open, triple-doc lockstep after phase
completion). Subagent count 4 → 8. Wrap-don't-duplicate pattern: each
enterprise agent reads its wrapped skill on every invocation, so
skill updates propagate automatically.

**Safe settings + hooks in flight (this PR)** — `.claude/settings.json`
+ `.claude/hooks/` land 2 PostToolUse Bash hooks: `log-bash.sh`
(append every Bash command to gitignored `.claude/session.log` for
session audit trail; ~zero risk — pure side-effect, fail-open) and
`schema-reminder.sh` (inject `additionalContext` reminder + the
exact `python -m compute.output.schema_check` command when any file
in the Pydantic↔TS↔snapshot triple — `compute/output/schemas.py`,
`frontend/lib/types.ts`, `frontend/lib/schema-snapshot.json` — is
touched via Write/Edit; closes the local-pre-commit gap left by the
schema-drift CI guard). Both hooks fail-open on missing `jq` /
unwritable FS / empty stdin; 5-second timeout. `.gitignore` appends
`.claude/session.log` + `.claude/settings.local.json`. Doc-only
otherwise — no compute / schema / output change.

**Phase 1 ops hardening shipped via PR #170** (2026-05-21) — surfaced
by the 14-subagent full self-audit (roll-call + deep-check pass on
`claude/enable-subagents-standby-7lMN4`). Three reconciles in one
focused diff: (a) `.github/workflows/compute-monthly.yml`
`permissions: contents: write` → `contents: read` per
`security-reviewer` Section C — the workflow's only step is the
Phase-0 stub `echo`, so write perm is dead weight until Phase 5 ML
retrain lands; (b) §Conventions EDGAR_MAX_WORKERS guideline 5 → 8 to
match the PR-3d empirical bump documented inline at
`compute/config.py:34-42` (the doc was stale, not the code — the
`edgar-debugger` + `performance-engineer` audits both confirmed the
code's ~1 req/s sustained load is comfortably under the 10/s SEC
ceiling and the inline rationale is self-documenting); (c) §Gotchas
`going_concern_disclosure` FP-rate stat 10.8% → 1.0% to match the
2026-05-20 production cron (now within the Mayew 2015 1-3% band
without a confirmed code mechanism — re-audit at Q3 2026-08-19).
Deferred from PR #170 to keep scope tight: form4 module-load
assertion (couples with Phase 4.5e PR 2 on the peer branch);
edgar_form4 CI cache restore path (same coupling); PHASE_STATUS /
SKILL.md schema table / METHODOLOGY.md vetoes-count drift (this PR);
frontend 6-FAIL palette+null+chip-family bundle (separate UI PR);
`loss_avoidance_pattern` size-invariant follow-up (separate
recalibration PR). No compute / schema / output change.

**Phase 2 doc-drift reconcile in flight (this PR)** — second deliverable
from the 14-subagent self-audit (2026-05-21). Doc drift surfaced by
`docs-reviewer` + `methodology-scientist` against the current
implementation state, fixed in lockstep across 5 documents — no
compute / schema / output / dep change. (a) `PHASE_STATUS.md`
§Current state block — schema `0.9.2-phase4h.2` → `0.9.4-phase4h.4`,
defense layer headline 17 → 27 emitted flags (PR #154 reconcile), skill
inventory 38 → 42, subagent inventory added (14 in 4 tiers), recently-
merged block refreshed from PR #146-back to PRs #148-#169, next-
deliverables list updated to drop PR #148-closed Epic-#125-Item-3
entry and add the `loss_avoidance_pattern` size-invariant follow-up.
(b) `SKILL.md` schema-version table — 2 missing rows added
(`0.9.3-phase4h.3` PR #160 `tier2_enabled` field + `0.9.4-phase4h.4`
PR #161 `valuation_methods_applicable` field). (c) `WORKFLOW.md`
Phase 4.5d `loss_avoidance_pattern` task — threshold description
`$5M / $0.05` → `$50M / $0.50` (PR-#163 Phase 2.4 rescale) + Phase 4
size-invariant follow-up note. (d) `docs/METHODOLOGY.md` Active vetoes
section — 4 → 7 rows (adds `beneish_manipulation_veto`,
`dechow_manipulation_veto`, `data_quality_input_corruption`), and the
Known-calibration-drift block refreshed to reflect Issue #11 closure
(PR #166), Phase 2.4 rescale (PR #163), Phase 2.2 high-confidence
irregularity (PR #165), and the going-concern FP-rate drop to 1.0%.
(e) `README.md` §Honest Limitations — adds Phase 2.2
`restatement_high_confidence` and Issue #11 closure entries; mentions
PR #163's 10× rescale on the `loss_avoidance_pattern` line. Deferred
to a follow-up Phase 2.x PR (too large for this scope): METHODOLOGY.md
annotate-only section full refresh (7 → 14+ flags) + missing citation
blocks (full Hennes-Leone-Miller 2008 *TAR*, Cohen-Malloy-Pomorski
2012, etc.) — needs `methodology-scientist` sign-off per the
new-defense-flow rule.

**Phase 3 frontend rule fixes in flight (this PR)** — third deliverable
from the 14-subagent self-audit (2026-05-21). Six `frontend-design-reviewer`
FAILs fixed in lockstep across 6 components — UI-only, no schema /
compute / output / dep change. (a) `StockLogo.tsx` `LOGO_PALETTE` —
12-color avatar fallback palette remapped to the four-family design
system (slate / indigo / rose / amber in 500/600/700 shade triplets),
replacing the 8 out-of-family entries (violet / pink / teal / orange /
sky / lime / red) that violated SKILL.md Rule 0; inline `'#fff'`
literals at the fallback letter-avatar + image-background style props
swapped for the `'white'` CSS keyword. (b)-(e) Loose-null discipline
fixed in `MoSCell` · `MoSBadge` · `LossChanceBadge` · `RankingTable`
— `=== null || === undefined` → `== null` (catches both via JS coercion;
preserves the existing `Number.isNaN()` follow-on check where present)
on legacy-snapshot nullable fields (`margin_of_safety_pct`,
`loss_chance_pct`, `composite_score`). (f) `FilterDrawer.tsx` chip
pattern consolidation — local solid-fill overrides
(`bg-emerald-600 text-white` for bullish + `bg-red-500 text-white` for
cautious; pattern A retired by Rule 2 since PR #68) removed and
replaced with the canonical `RECOMMENDATION_CHIP_TONES` +
`RECOMMENDATION_CHIP_DOTS` imports from `RecommendationBadge.tsx` —
one outlined-light pattern shared across the badge surface and the
drawer-selection surface. Verified via `tsc --noEmit` filtered to
edited files (no new TS errors introduced; pre-existing env-noise
errors from missing `@types/node` / `react` types are untouched
since they would also appear on `main`). Deferred from this PR (still
WARNs from the audit, not FAILs): `FairPriceBarChart.tsx` tabular-nums
+ verdict-badge shape; `RawMetricsTable` + `PillarRadarChart`
loose-null 5 instances; `RankingTable` toolbar-search aria-label.

**Lean auto-routing + stock-detail-auditor in flight (this PR)** —
two coupled changes to the agent layer. **(a) Auto-routing policy
rewrite**: 17-row table collapsed and reshaped so most cues fire at
GATE moments (`ready to push` / explicit ask / signal event) instead
of on every edit. The schema-triple hook covers per-edit reminders
that don't need LLM judgment; everything else batches into one
parallel pre-push review. Edits to `compute/scoring/` /
`compute/valuation/` / `frontend/components/` / docs no longer
spawn an agent — they now ride the next "ready to push" gate as
conditional batch-mates. Spawn discipline updated: default model
sonnet (opus only for cross-domain orchestration / methodology /
large-diff with user authorization). Token economy paragraph added
to the §Auto-routing intro. **(b) New 15th agent**: Tier 1
`stock-detail-auditor` (sonnet, read-only) audits per-stock JSON
the frontend renders. Step 2 deterministic prefilter walks the
~502-ticker universe for range / consistency (issue #10
`shares_outstanding` gap > 5%, |eps_diluted| > 500 XBRL parse
errors, |mos_pct| > 500%) / Rule 16 invariant (entered_top5 +
risk_flags) / known-issue overlap (#7 Sloan-Financials, #11
value_trap noise). Step 3 LLM-judgment review capped at ≤ 20
tickers (real_outlier vs broken_data + upstream cause). Fires
post-cron, pre-release, "ตรวจ data หุ้น"; folded into release
ladder Flow 2 alongside `defense-layer-auditor`. Covers OUTPUT
correctness; FORMULA correctness remains methodology-scientist's
slot. No compute / schema / scoring / valuation / frontend code
change. Closes the gap left when the previous "wide" policy spawn
cost compounded across multi-file edits.

**Trim agent prompts in flight (this PR)** — second-order
token-economy optimization on top of the gate-moment policy rewrite.
Six largest subagent prompts under `.claude/agents/` rewritten leaner
without changing behavior: `incident-commander` 218 → 126 (−42%),
`test-engineer` 189 → 113 (−40%), `stock-detail-auditor` 177 → 120
(−32%), `docs-reviewer` 180 → 125 (−31%), `release-captain` 211 →
145 (−31%), `security-reviewer` 185 → 131 (−29%). Total across the
15-agent set: 2925 → 2525 lines (−400, −13.7%). Cuts target the
genuine bloat — long "Read these first" prose enumerating files
anyone knows, post-mortem template duplicated from
`9arm-post-mortem` skill, "Project test conventions (memorize)"
duplicate of `AGENTS.md` §Testing, Section-A-H verbose intros where
a compressed table suffices. Hard constraints + workflow steps +
output discipline + escalation tables all preserved. Each spawn of
the 6 trimmed agents loads ~25-90 fewer prompt lines (~500-1500
fewer tokens). Companion to #175 (which reduced spawn FREQUENCY);
this PR reduces per-spawn SIZE. Also files 2 GitHub issues from the
auditor dry-run: **#176** (STZ `market_cap: null` — XBRL fact
extraction missing `shares_outstanding`) and **#177** (15 tickers
`|mos_pct| > 500%` — fair-price ensemble extreme estimates on
growth/goodwill-heavy stocks). No compute / schema / scoring /
valuation / frontend change.

**Phase 4b loss_avoidance_pattern_size_invariant merged via PR #180**
(2026-05-21, `a24a57d4`) — closed the long-running follow-up from
CLAUDE.md §Gotchas (`loss_avoidance_pattern` threshold-drift) and
Phase 2.4 (PR #163 absolute-$ rescale to S&P 500 scale). New annotate
`loss_avoidance_pattern_size_invariant` fires when
``NI / TotalAssets ∈ [0, 0.005]`` for 3+ consecutive fiscal years —
the size-invariant Roychowdhury 2006 *JAE* Table 1 + §5.2 suspect-firm
signature. **methodology-scientist Mode B verdict on the 0.005
threshold: LITERATURE-ANCHORED** (Roychowdhury's exact suspect-firm
cutoff, with Donelson-McInnis-Mergenthaler 2013 *TAR* reaffirming it
as canonical). Schema bumped `0.9.4-phase4h.4` → `0.9.5-phase4h.5`
for the new `Metadata.loss_avoidance_size_invariant_firing_count:
int | None` observability field (Rule 18 — diagnostic shipped in the
SAME PR as the flag emission). `LOSS_AVOIDANCE_SIZE_INVARIANT_WEIGHT
= 5` in `manipulation_index.py` (parity with the absolute-$ sibling;
revisit at Q3 audit + a φ-correlation check vs `REM_SUSPECT_WEIGHT`
which shares the Roychowdhury anchor but fires on abnormal
CFO/Production/DiscExp WITHIN the suspect cohort rather than cohort
membership itself). Defense layer headline count 27 → 28 emitted
boolean flags. Tests: 1024 → 1031 (+7: 5 unit + 1 Hypothesis property
+ 1 constants pin). Companion frontend WARN polish in the same PR —
`FairPriceBarChart.tsx` headline %-delta gained `tabular-nums`,
verdict badge moved to canonical `rounded-full` + `font-medium` chip
family; 6 loose-null sites in `RawMetricsTable` + `PillarRadarChart`
tightened to `== null`; `RankingTable.tsx:268` toolbar search gained
`aria-label="Search by ticker or company name"` for screen-reader
affordance.

**Issue #176 share_count_extraction_missing annotate merged via PR #181**
(2026-05-21, `998cd530`) — landed the visibility-gap annotate. STZ on
the 2026-05-14 cron shipped with `market_cap: null` + `risk_flags: []`
because `shares_outstanding` failed to extract. The flag
`share_count_extraction_missing` fires when
``shares_outstanding is None AND revenue > 0 AND total_assets > 0``.
Annotate-only per `portable-annotate-before-veto`. Schema bumped
`0.9.5-phase4h.5` → `0.9.6-phase4h.6` for the
`Metadata.share_count_extraction_missing_count: int | None` Rule 18
diagnostic. Defense layer 28 → 29 emitted flags. Tests 1031 → 1040.

**Issue #176 root-cause fallback merged via PR #182** (2026-05-21,
`a6129011`) — actually
RECOVERS the missing share count via per-filing XBRL dimensional-fact
aggregation, removing the dependency on a follow-up after PR #181
shipped only the visibility surface. Live SEC probe on STZ
(2026-05-21) confirmed the SEC `companyfacts` aggregate API filters
out *dimensional* facts (companyconcept API returns HTTP 404 for both
`dei:EntityCommonStockSharesOutstanding` and
`us-gaap:CommonStockSharesOutstanding` on STZ) while the per-filing
XBRL DOES expose them with `is_dimensioned=True` and a
`period_instant` "as-of" date (share-count facts are instant-type,
not flow-type). New `_fetch_shares_from_per_filing_xbrl(company)` in
`compute/ingest/fundamentals.py` pulls the most recent 10-K (falls
back to 10-Q if none on file), aggregates
`dei:EntityCommonStockSharesOutstanding` across all dimensional
contexts at the most-recent `period_instant`, and returns the sum;
falls back to `us-gaap:CommonStockSharesIssued` if the dei concept
is empty. Wrapped in graceful-degradation try/except — any failure
returns `None`, keeping the upstream `share_count_extraction_missing`
annotate (PR #181) firing as the safety net. Triggered ONLY when the
primary extraction returns `None` AND `revenue > 0` AND
`total_assets > 0` (the exact PR-#181 signature), so universe-wide
HTTP cost is bounded to ~1-3 tickers per cron (blast radius = 1 on
2026-05-14). Live verification (this session): STZ 172.20M shares
(Class A 172.17M + Class B 26K), AAPL 14.78B, WMT 7.97B — all match
ground truth. Tests: 1040 → 1049 (+9 offline mock tests + 1
`@network` STZ live drift-detector). No schema change (operates at
the snapshot-construction layer, doesn't add any field). The
`share_count_extraction_missing` annotate keeps the same emission
semantic — when the fallback succeeds, `shares_outstanding` is no
longer `None` so the annotate doesn't fire; when the fallback also
fails (e.g., the filer has no 10-K or 10-Q with XBRL), the annotate
fires and surfaces the gap.

**Issue #177 extreme_estimate_majority annotate merged via PR #183**
(2026-05-21, `b881d544`) —
the `stock-detail-auditor` dry-run on the 2026-05-14 cron flagged 15
tickers with `|fair_price.mos_pct| > 500%` (APP -1255% / DDOG -1354%
/ AXON -1113% / TSLA -1280% / …). Per-method universe-wide audit
showed Defense #4 outlier guard (`extreme_*_estimate`, the 5×/0.2×
band) over-fires on RIM (36.1%) and Graham (24.0%) for high-growth /
goodwill-heavy stocks. With 4-5 of 6 methods routinely extreme on
the affected cohort, the ensemble's median (a 50% trimmed estimator
over 6 samples) is past its Huber 1981 §1.4 breakdown point
(⌊5/2⌋ = 2 outliers) and collapses to the low-cluster — APP shows
`fair_price.median = $36` against `current_price = $482` (4 methods
extreme, 2 surviving in the low cluster). New annotate
`extreme_estimate_majority` fires when ≥
`EXTREME_MAJORITY_THRESHOLD = 3` of the 6 methods emit
`extreme_*_estimate`. **Annotate-only** per Rule 16 +
`portable-annotate-before-veto` — the actual median-exclusion logic +
a `fair_price.methods_excluded_from_median: list[str]` field lands in
a follow-up PR after ≥ 1 cron's firing-rate observation (per
methodology-scientist Mode B verdict 2026-05-21). Methodology
verdict: median-exclusion is **literature-anchored** (Damodaran 2019
*Investment Valuation* 3rd ed. Ch. 18 + Penman 2013 *FSA/SV* §7.4 +
Huber 1981 *Robust Statistics* §1.4); threshold = 3 is **gut-feel
with Huber breakdown-point rationale**; the 5×/0.2× per-method bands
are **gut-feel only** and need a separate recalibration PR (RIM-
specific or per-cohort) — NOT bundled here. Schema bumped
`0.9.6-phase4h.6` → `0.9.7-phase4h.7` for the
`Metadata.extreme_estimate_majority_count: int | None` Rule 18
diagnostic (gates the follow-up median-exclusion PR — the next cron's
universe-wide firing rate is what tells us whether to promote).
Defense layer 29 → 30 emitted flags. Tests 1049 → 1059 (+10: 6
threshold-branch unit tests + 3 full-ensemble integration tests + 1
config-constant pin).

**Phase 5 dependabot tailwindcss-ignore follow-up in flight (this PR)**
— small backstop after Dependabot's second wave (2026-05-22) filed
PR #200 (`tailwindcss 3.4.4 → 4.3.0`), a complete-engine-rewrite
major bump that the original PR #195 ignore list missed. Tailwind 4
replaces `tailwind.config.js` with a CSS-based `@theme` directive +
new `@tailwindcss/postcss` plugin chain — frontend build FAILED.
This PR adds `tailwindcss` to the `.github/dependabot.yml` npm
`ignore:` block (10 → 11 npm entries total). Closes the gap so a
future Dependabot run doesn't re-file the same major bump. Minor +
patch within `3.x` still flow automatically. Doc-only otherwise.

**Phase 5 dependabot ignore-list extension merged via PR #195**
(2026-05-22, `8c22cee9`) —
durable backstop after Dependabot's first wave (2026-05-22) filed 8
PRs from the config that landed in PR #185. Outcomes:

- PR #186 `actions/github-script v7 → v9` — major (GitHub Actions),
  merged 2026-05-22 (v9 breaking patterns `require('@actions/github')`
  + getOctokit redeclaration NOT used by our pre-merge-prod-sim
  script; only `github.rest.*` calls which are unchanged)
- PR #187 `actions/upload-artifact v4 → v7` — major, merged
  2026-05-22 (only breaking change is Node 24 runner requirement;
  `ubuntu-latest` runners already on v2.327.1+)
- PR #188 `pandas` constraint `<3 → <4` — CLOSED + `ignore this
  major version`; pandas 3.0 has untested breaking changes (copy-on-
  write default, removed deprecated APIs)
- PR #189 npm-minor-patch group (next/autoprefixer/postcss) —
  auto-closed by Dependabot (PR #194 already bumped the same `next`
  14.2.15 → 14.2.35)
- PR #190 `eslint 8.57.0 → 10.4.0` — frontend build FAILED, closed
  (eslint 9+ flat-config breaks `eslint-config-next 14.2.x`)
- PR #191 `typescript 5.4.5 → 6.0.3` — frontend build FAILED,
  closed (TS6 strict-mode + lib.dom typing changes)
- PR #192 `@types/node 20.12.7 → 25.9.1` — merged 2026-05-22
  (type-only metadata)
- PR #193 `recharts 2.12.7 → 3.8.1` — frontend build FAILED,
  closed (recharts 3 restructured chart-component API)

PR #188, #190, #191, #193 closed via `@dependabot ignore this major
version` comment commands. This PR adds the same 4 deps (`pandas`
on the pip side; `eslint` / `typescript` / `recharts` PLUS
`eslint-config-next` on the npm side) to the
`.github/dependabot.yml` `ignore:` blocks — durable YAML-level
backstop that survives Dependabot server resets and per-PR comment-
ignore-history garbage collection. Total ignore entries: 10 (1 pip
+ 9 npm + 0 github-actions; #186 + #187 confirmed SAFE-TO-MERGE so
no actions block needed). Minor + patch + security updates on ALL
ignored packages STILL file automatically — the ignore only blocks
`version-update:semver-major` transitions. Issue #41 still owns the
scoped React-stack breaking-change migration; `recharts 3` and
`pandas 3` are separate scoped migration work items if/when
priority. No compute / schema / scoring / valuation / Python /
TypeScript code change — `.github/`-only addition.

**Phase 5 Next.js 14.2 patch bump merged via PR #194** (2026-05-22,
`72f8a33c`) — partial
progress on issue #41 (`next 14.2 → 16` CVE refresh) via a
within-branch patch bump that closes the 8 advisories #41 originally
itemized at filing time, without breaking-change migration.
`frontend/package.json`: `"next": "14.2.15" → "14.2.35"` +
`"eslint-config-next": "14.2.15" → "14.2.35"` (lockstep with `next`
minor) + `"postcss": "8.4.38" → "8.5.15"` + new `"overrides": {
"postcss": "8.5.15" }` block (forces next's nested
`postcss@8.4.31` exact-pin to lift to 8.5.15 transitively, closing
the postcss XSS advisory `GHSA-qx2v-qp2m-jg93`). `package-lock.json`
regenerated; `npm install` clean; `next build` produces all 506
static routes; `tsc --noEmit` clean. Issue #41 STAYS OPEN — 14 new
`next` advisories surfaced on the npm advisory database between
2026-05-13 (issue filed) and 2026-05-22 (PR #194), ALL requiring
`<15.5.16` to fix, none with a 14.2.x backport. All 14 target
SSR / Server-Components / middleware / runtime features QuantRank
doesn't use (we ship static export only — `next build` → static
HTML, no SSR runtime, no middleware, no rewrites). Real
exploitability for the static-export site remains zero per #41's
own original risk rating, but `npm audit` cannot infer the
static-export posture so the advisories still surface in CI. The
remaining 14→16 migration (App Router async APIs + React 18→19
typing + Node 20+ requirement + eslint-config-next 16.x) is
release-tag-cleanliness, not security-critical; tracked under #41.
Dependency-auditor verdict (2026-05-22): SAFE-TO-MERGE as a focused
patch PR. No compute / schema / scoring / valuation / Python code
change — frontend dep-bump only.

**Phase 5 dependabot housekeeping merged via PR #185** (2026-05-22) — closes
another deferred parking-lot item from the 14-subagent self-audit
(2026-05-21). New `.github/dependabot.yml` configures automated
weekly dependency-update PRs across QuantRank's three ecosystems:
**pip** (`pyproject.toml` at repo root), **npm** (`frontend/package.json`),
**github-actions** (`.github/workflows/`). Schedule: Monday 08:00
Asia/Bangkok, weekly. Minor + patch updates grouped into one PR per
ecosystem (reduces PR count when a multi-package sweep lands upstream);
security updates always file separately at top priority. `next` /
`react` / `react-dom` / `@types/react*` **major** bumps explicitly
ignored — tracked under issue #41 (Next 14 → 16 needs scoped
breaking-change migration with `dependency-auditor` triage; routine
Dependabot PR would footgun the App Router async-API migration).
Minor + patch + security updates on those packages still file
automatically. Commit-prefix scheme: `chore(deps-py)` / `chore(deps-npm)` /
`chore(deps-ci)` matching the project's `chore(X):` convention.
`open-pull-requests-limit` capped at 5/5/3 per ecosystem. No
compute / schema / scoring / valuation / frontend change — `.github/`
addition only. The next Dependabot run lands Monday after merge.

**Phase 2.x METHODOLOGY annotate refresh merged via PR #184**
deferred parking-lot item from the 14-subagent self-audit (2026-05-21).
`docs/METHODOLOGY.md` §"Annotate-only flags" section refreshed from 10
documented bullets to 18, closing the doc-drift surfaced by the
methodology-scientist Mode C audit. Eight previously-emitted-but-
undocumented annotates now carry full literature-anchored bullets:
`accruals_momentum_high` (Sloan 1996 + Beneish 1999 + Xie 2001),
`loss_avoidance_pattern` (Burgstahler-Dichev 1997 with PR #163 10×
rescale note), `beneish_high` (Beneish 1999 + Beneish-Lee-Nichols
2013 warning-band PPV), `dechow_high` (Dechow-Ge-Larson-Sloan 2011
Table 9), `manipulation_triple_flag` (PR 4.5a.3 joint-gate + PR #164
correlation watch), `restatement_history` (Hennes-Leone-Miller 2008
bare-flag PPV), `restatement_high_confidence` (HLM 2008 irregularity
signature + Schroeder 2024 90d window), and `late_filing_notification`
(Bartov & Konchitchki 2017 *Accounting Horizons* — citation
corrected 2026-05-26 after literature-searcher verified the prior
"Bartov-Lai-Yeung 2002 *JAR*" attribution was hallucinated; the
hand-off originally labeled it Cohen-Malloy-Pomorski 2012, which
also turned out to be wrong, and the late-filing 5-day abnormal-
return finding is anchored in Bartov-Konchitchki 2017 §III).
Each bullet carries the Phase 2.5 provenance tier (LITERATURE-ANCHORED
/ GUT-FEEL with rationale) cross-checked against
`compute/scoring/manipulation_index.py` weight docstrings — zero
drift verified. Stale footnote "Phase 3e adds `beneish_high` and
`dechow_f_high`" removed (those flags are now full bullets; the
footnote also misspelled `dechow_f_high` as `dechow_high` is the
actual emit name). No compute / schema / code change. Defense layer
emit count unchanged at 30 (the 8 new bullets document flags that
were already in the headline math — this PR closes the doc gap, not
the emit gap). Cohen-Malloy-Pomorski 2012 confirmed NOT-NEEDED
(provenances reserved-not-emitted Form-4 weight slots that wire in
Phase 4.5e PR 3; not a live annotate today). Doc-only PR — `ruff` /
`schema_check` / `pytest` / `tsc` trivially pass.

**Phase 4a osap-import guard merged via PR #179** (2026-05-21) —
surfaced by the 14-subagent self-audit on 2026-05-21 (`test-engineer` follow-up).
`compute/main.py` carried top-level imports of four OSAP modules
(`compute.features.osap_replicate`, `compute.ingest.osap`,
`compute.scoring.osap_blend`, `compute.validation.osap_validation`).
Only one of them (`compute.ingest.osap`) directly `import
openassetpricing` at module load — but that single transitive edge
blocked `tests/test_main.py` collection in any environment without
the `.[factors]` optional extra installed, since the 11 OSAP function
references in `run_weekly_compute()` pulled the failing import chain
in eagerly. The fix moves all four OSAP imports into the existing
`try:` block at `compute/main.py:975` (which already wraps every
OSAP function call in a graceful-degradation path per Rule 18 — every
`StockDetail.osap_*` + `Metadata.osap_*` field is `| None = None` in
the schema). The existing `except Exception` at the call site catches
`ImportError` (subclass) cleanly; the failure path was already
implemented and is now reachable for the "openassetpricing not
installed" case it was designed for. Verification: `python -m pytest
tests/test_main.py --collect-only -q` reports 39 tests collected, 0
errors in a base-install env (was: ModuleNotFoundError on collection);
the full offline suite still reports `1024 passed` in CI-mode (with
`openassetpricing==0.0.2` installed via `.[factors]`). No compute
logic / schema / scoring / valuation / frontend change — pure import
topology refactor.

**Issue #125 Item 6 cross-session collision detector merged via PR #203**
(2026-05-22) — new `tools/check_cross_session_collision.py` hits the
GitHub API for `claude/*` branches updated in the last 7 days + open PRs
matching a scope keyword, exits 1 on collision and 0 when clean.
Companion to the existing git-only `branch-collision-check` skill (which
covers local origin state in a 48h window); this skill covers sibling
sessions on OTHER machines that haven't pushed recently — the gap the
git-only checker cannot cover. New
`.claude/skills/cross-session-collision-check/SKILL.md` wraps the script
with trigger/skip conditions, auth instructions (GH_TOKEN / GITHUB_TOKEN
/ gh CLI), false-positive guard (merged+closed branches excluded by
design), and a comparison table vs `branch-collision-check`.
`phase-coordinator` Mode A wired to run BOTH skills in sequence: Step 1
git-only (no auth), Step 2 GitHub API (7-day window). Skill count
42 → 43. No compute / schema / scoring / valuation / frontend change.
Closes issue #125 Item 6.

**Issue #67 sector-adjusted CoE data-collection merged via PR #204**
(2026-05-22) — `compute/scoring/cost_of_equity.py` adds the GICS-keyed
Damodaran 2019 Table 8.4 + NYU January 2025 dataset sector-CoE dict
(11 sectors, Ke range 6%-12%). `config.USE_SECTOR_COE = False` (default
OFF per Rule 18 — data-collection only). `compute/valuation/ensemble.py`
reads the flag and passes the sector-adjusted Ke to `rim_fair_price`
when enabled. `Metadata` gains 3 Rule 18 diagnostics:
`sector_coe_enabled` + `value_trap_risk_count_without_sector_coe`
(flat-10% baseline) + `value_trap_risk_count_with_sector_coe`
(per-sector Ke). Both counts computed every cron so the delta is
visible before the flag is flipped. Schema bumped `0.9.7-phase4h.7`
→ `0.9.8-phase4h.8`. Tests +35 (11-sector dict pin + Hypothesis band
test + sector-CoE RIM gate sanity tests). Pre-merge sim (PR #204):
Δscore max ±0.17 / Δrank max ±3 — confirms data-collection only.
Methodology-scientist Mode B (agent layer): LITERATURE-ANCHORED across
all 11 sectors. Closes issue #67 prep; flip follows after ≥ 1 cron
delta-count.

**Phase 4.5e PR 2 — Form-4 observability surface in flight (this PR)**
(2026-05-22) — wires the Form-4 fetch loop from PR 1 (Scout,
`compute/scoring/form4_insider.py`) into `compute/main.py` as an
observe-only loop (`form4_enabled=False`). 7 new `Metadata` fields:
`form4_enabled` · `form4_coverage_pct` · `form4_fetch_latency_p50_seconds`
· `form4_fetch_latency_p95_seconds` · `form4_universe_insider_count_median`
· `form4_tickers_with_recent_activity` · `form4_fetch_failures`. 1 new
`StockDetail` field: `form4_diagnostics` (per-ticker `{insider_count,
latest_filing_date, fetch_status}`). New helper Section K: Form-4
universe accounting equation (`universe_size == ok_active + ok_zero +
failed + missing`). Schema bump `0.9.8-phase4h.8` → `0.10.0-phase4.5e`
(MINOR — additive fields, no consumer migration; supersedes the PR-#204
PATCH bump after rebase). ZERO scoring impact;
`_FORM4_FLAGS_ENABLED` stays False. PR 3 wires the
`insider_sell_cluster` + `c_suite_unusual_sell` annotates after ≥ 1
cron's firing-rate data lands in the new `form4_*` Metadata fields.

**Sonnet sub-agent thoroughness + frequency reset in flight (this PR)** —
two-part reversal of the over-restriction introduced during PR
#175 (spawn frequency) + PR #178 (per-spawn work caps). User
observation: "Weekly · Sonnet only" pool on the Max plan sits at
~2% utilization while "Weekly · all models" pool moves normally —
meaning sonnet sub-agents are being under-used across both axes
(spawned too rarely AND capped too tightly per-spawn). Combined
fix in this PR.

**(a) Per-spawn caps lifted** (PR #178 over-correction):

- `stock-detail-auditor.md` Step 3 — removed the 20-ticker hard cap;
  agent now walks every prefilter-flagged ticker with a verdict,
  fetches 1-2 adjacent peers when a multi-ticker pattern is
  suspected, and adds a "DO NOT skip flagged tickers to keep the
  report short" hard constraint that codifies the new principle.
  Frontmatter `description:` rewritten to remove the "≤ 20" phrase.
- `quantrank-reviewer.md` Output format — removed "terse"
  instruction; agent now lists every PASS / FAIL / WARN finding it
  encountered while walking Sections A-H.
- `.claude/agents/README.md` Flow 2 (release ladder) — release-
  captain's `stock-detail-auditor` lane no longer says "≤ 20 LLM
  verdicts"; says "thorough LLM verdicts for every flagged ticker".
  Roster row description updated to match.
- `CLAUDE.md` §Auto-routing policy §Spawn discipline — added two
  new principles: (a) "Don't gatekeep sub-agent effort" explaining
  the Max-plan dual-pool topology (sonnet sub-agents drain the
  Sonnet-only pool which is a separate, paid-for budget) and why
  bounding sub-agent output wastes it; (b) "Prefer delegation to
  sub-agents over inline main-session work" so the main agent
  routes work proactively to sonnet sub-agents instead of doing it
  inline (which lands on the all-models pool).

**(b) Spawn frequency lifted for sonnet agents** (PR #175 over-
correction):

The §Auto-routing policy cue table now fires sonnet agents on
**non-trivial edit** to their domain, not only at "ready to push"
gates. Six new edit-trigger rows:

- Schema triple edit → `schema-sentinel` (sonnet)
- `compute/scoring/*` / `compute/valuation/*` edit → `defense-layer-auditor` (sonnet)
- `frontend/components/*` / `frontend/app/*` edit → `frontend-design-reviewer` (sonnet)
- `.github/workflows/*` / new dep / new env-var → `security-reviewer` (sonnet)
- Production code added without test → `test-engineer` (sonnet)
- Any of 7 docs edited → `docs-reviewer` (sonnet)

"Non-trivial" = > 5 added lines OR touches non-comment code OR
adds/removes a public symbol. Comment / whitespace / single-line
fixes do not trigger. The four **opus** agents (`incident-commander`
· `release-captain` · `methodology-scientist` · `quantrank-reviewer`)
keep the rare-fire policy — they land on the all-models pool, so
firing them more often does not help drain the sonnet pool.

The "ready to push" gate still fires as a **safety net** — opus
reviewer + sonnet re-batch, with the 10-min dedup window skipping
sonnet agents that already ran on the same diff during the
edit-trigger pass. So a typical PR cycle is: edit X → sonnet agent
fires immediately → user iterates → at "ready to push", opus
reviewer + phase-coordinator fire fresh, sonnet agents skip via
dedup. Worst case spawn count per PR rises ~2-3× vs PR #175
baseline, but every extra spawn drains the Sonnet-only pool which
is paid-for and currently idle.

Model assignments unchanged: 4 opus by design (`incident-commander`
· `release-captain` · `methodology-scientist` · `quantrank-reviewer`)
+ 11 sonnet. The 4-vs-11 split was investigated — temporary swap of
`quantrank-reviewer` + `methodology-scientist` to sonnet was tested
and reverted in the same PR after re-reading the user intent. Opus
on the most-fired reviewer remains correct because the project's
defense-layer invariants are dense enough that opus headroom pays
back on real diffs. The fix is to stop capping work, not to demote
models.

Companion artifact deferred to a follow-up: a per-session usage
report (post-merge spot-check) that confirms the Sonnet-only pool
actually moves more after this lands. Not in this PR's diff.

No compute / schema / scoring / valuation / frontend code change.

**Issues #217 + #218 OSAP proxy contract codification merged via PR #221**
(2026-05-23, `eba0fde`) —
the 2026-05-23 cron #3 surfaced a false-positive escalation chain: the
`stock-detail-auditor` interpreted the universe-wide identical
`osap_signals` dict (502 tickers × same dict) as cron-wide data
corruption and escalated to `incident-commander`, which then had to
walk the schema + frontend + blending pipeline before downgrading the
P1 to P3. Root cause: the documented Phase 4h factor-exposure proxy
contract (`compute/features/osap_replicate.py:14-35`, locked
2026-05-18) was nowhere in the agent prompts or the verify-helper —
both directions of drift (regression OR Phase 4i+ graduation) were
silent. This PR closes the loop on both sides. **(a)
`.claude/agents/stock-detail-auditor.md`** gains a "Documented
patterns — NOT broken_data" callout at the top of Step 3 with the
3-row recognition table (proxy_active+blended_varies →
documented_proxy / proxy_active+uniform_blended → broken_data /
graduated → escalate to methodology-scientist), a third verdict
type `documented_proxy`, and a new escalation row routing universe-
wide proxy-shaped findings to `methodology-scientist` (NOT
`incident-commander`). **(b)
`.claude/skills/verify-production-output/helper.py`** gains
`section_l_osap_proxy_invariant()` (issue #218's proposed code,
cleaned up): walks `osap_signals` + `osap_blended_score` across the
universe, classifies into `phase4h_proxy` / `blending_regression` /
`graduated` / `schema_drift` / `unknown`, returns
`(warnings, failures)` matching the existing Section A-K reporter
shape. Section L passes on the 2026-05-23 cron #3 output with
`mode=phase4h_proxy (1 signal set × 428 blended scores)` — confirming
the contract holds. The blending-regression failure mode is the
defensive guard: if a future code change accidentally drops the
per-ticker scalar multiplication in `compute/scoring/osap_blend.py`,
the helper FAILS instead of passing silently. The graduated WARN
mode forces an intentional scope-note bump when Phase 4i+ true
per-stock replication lands. **(c) `tests/test_verify_helper.py`**
gains 6 Section L tests (empty/skip + populated-but-no-OSAP/skip +
phase4h_proxy/pass + blending_regression/fail + graduated/warn +
schema_drift/fail + None-coverage-gap exclusion), 12 → 18 tests in
this file, 1056 → 1062 in the suite. **(d) Helper module docstring**
header text updated from "Section A-J" to "Section A-L"; the
`main()` argparse description and runner tuple both bumped to wire
the new section. No compute / schema / scoring / valuation /
frontend code change — agent prompt + helper script + tests only.
Closes issues #217 + #218.

**Delegate-first orchestrator role merged via PR #223** (2026-05-23) —
behavioral fix for the under-delegation problem surfaced after PR
#219. Even after PR #219 lifted spawn caps + frequency, the
"Weekly · Sonnet only" pool remained under-utilized because the
main Claude Code session (opus) was doing checks / reviews /
investigations **inline** instead of delegating to sub-agents.
Root cause: the "Prefer delegation" rule in §Spawn discipline was
worded too softly; the main agent kept defaulting to inline work
because it never hit a hard "delegate-first" reminder. Three-layer
fix:

- **Layer 1 — Identity statement in `CLAUDE.md` §Auto-routing
  policy**: new `### Main agent role — orchestrator, not laborer`
  sub-section at the top of the section reframes the main agent as
  the team's tech lead whose DEFAULT action is to identify the
  matching sub-agent + spawn it. Inline work is the EXCEPTION,
  acceptable only under five enumerated conditions
  ((a) no agent matches · (b) trivial 1-Read lookup · (c) user
  explicitly says "ทำเอง" / "inline this" · (d) the work is
  building agent/hook infrastructure itself · (e) cross-agent
  synthesis after multi-agent reports).
- **Layer 2 — Delegation patterns table in `CLAUDE.md`**: 15-row
  mapping `user request pattern → which agent to spawn` so the
  delegate-first check doesn't degrade into guesswork. Covers the
  common phrases ("ตรวจ data หุ้น" / "ก่อน push" / "schema in
  sync" / etc.) and which sub-agent owns each.
- **Layer 3 — `UserPromptSubmit` hook
  `.claude/hooks/delegate-first.sh`**: injects the "DELEGATE-FIRST
  CHECK" reminder as `additionalContext` on every user turn so the
  rule stays loaded — main agent can't lose it mid-session. ~120
  tokens per turn cost; pays back the first time it prevents
  main-session inline work that should have gone to sonnet pool.
  Fail-open on missing jq / unwritable stdin per the existing hook
  convention; 5-second timeout. Wired in `.claude/settings.json`
  alongside the existing 2 PostToolUse hooks.

`CLAUDE.md` §Layout `.claude/hooks/` row updated 2 hooks → 3.
`AGENTS.md` §Claude-Code-specific tooling adds a paragraph on the
delegate-first discipline so cross-tool readers (Copilot / Cursor /
Devin) understand why the main session defaults to spawning rather
than doing.

Companion follow-up (not in this PR): per-session usage spot-check
3-5 days post-merge to confirm Sonnet-only pool moves more (vs
PR #219's flat 2% baseline). If still flat, re-investigate whether
sub-agents themselves are the bottleneck (e.g., descriptions don't
match common request phrasings) — separate PR.

No compute / schema / scoring / valuation / frontend code change.

**Phase 4.5e PR 3 — insider-cluster annotates in flight (this PR)** —
closes the Phase 4.5e ladder (PR 1 Scout + PR 2 Observability already
merged). Two new annotate-only flags emit from a new
`compute/scoring/form4_signals.py` module on the Form-4 cache surface
populated by PR 2 (which now has 502/502 = 100% coverage on the
2026-05-23 cron #3 with insider_count p50=14 / p95≈23). **(a)
`insider_sell_cluster`** fires when ≥ 3 distinct insiders sold ≥ $1M
cohort-aggregate in opportunistic transactions (codes `{S, D}` per
Cohen-Malloy-Pomorski 2012 §III.A "opportunistic" partition — codes
A/M/F/G are compensation-mechanical and explicitly excluded) within
a rolling 30-day window. **(b) `c_suite_unusual_sell`** fires when
≥ 2 distinct CEO + CFO + President insiders sold in the same window
(narrow regex per Jeng-Metrick-Zeckhauser 2003 §V; deliberately
EXCLUDES COO/CTO/CMO/CHRO which are operational not
financial-information). **Methodology-scientist Mode B verdict
(2026-05-23)**: distinct-insider thresholds and transaction-code
partition are LITERATURE-ANCHORED (CMP 2012 + JMZ 2003 + Jagolinzer
2009); 30-day window is GUT-FEEL-acceptable (compresses CMP's ~90d
calendar-quarter into Jagolinzer 2009 §3.2 high-information regime);
$1M cohort floor is GUT-FEEL (no paper anchors an absolute dollar
floor — relative-sizing follow-up tracked for a future iteration).
**Reserved weights downgraded per verdict**:
`INSIDER_SELL_CLUSTER_WEIGHT_RESERVED = 10.0` → `INSIDER_SELL_CLUSTER_WEIGHT = 5.0`
(annotate-mid peer group; Bushman-Smith 2003 post-SOX 30-50% signal
degradation + unfiltered 10b5-1 contamination risk argue for
conservative weight pending cohort-PPV acceptance check);
`C_SUITE_UNUSUAL_SELL_WEIGHT_RESERVED = 5.0` → `C_SUITE_UNUSUAL_SELL_WEIGHT = 3.0`
with **DELTA-not-total semantics** mirroring PR #165's
`RESTATEMENT_HIGH_CONFIDENCE_WEIGHT` (strict superset of the cluster
flag when the $1M floor is met → combined = 5 + 3 = 8 pts ≈
`REM_SUSPECT_WEIGHT`). Both `FLAG_WEIGHTS` entries uncommented in
`compute/scoring/manipulation_index.py`. **Rule 18 observability**:
2 new `Metadata` fields `insider_sell_cluster_firing_count` +
`c_suite_unusual_sell_firing_count` ship in the same PR; gate the
Q3 2026-08-19 quarterly-audit cohort-acceptance check that may
promote the cluster weight to 10.0. Annotate-only per Rule 16 +
`portable-annotate-before-veto` — composite rank unchanged; only
`manipulation_index` + `composite_score_adjusted` soft-penalty is
affected. **Scout-module docstring fixes (same PR)**:
`compute/scoring/form4_insider.py:62-89` corrected to (i) document
the `{S, D}` opportunistic filter (was wrongly `{S, F}`) and (ii)
remove the Cohen-Malloy-Nguyen 2020 "Lazy Prices" misattribution
(Lazy Prices is about 10-K/10-Q disclosure-language changes, NOT
insider trades), replaced with canonical CMP 2012 + JMZ 2003 +
Jagolinzer 2009 anchor set. **Footguns acknowledged in module
docstring** (per methodology-scientist verdict): (1) 10b5-1
pre-scheduled-trade contamination — expected FP rate 40-60% per
Jagolinzer 2009 absent filtering; (2) post-earnings-window quarterly
clustering — compliance-window artifact unrelated to information
asymmetry; (3) joint-filer attribution + stale officer-title noise.
All three deferred to follow-up PRs with explicit Q3 cohort-audit
gate before any weight promotion. Schema bump
`0.10.0-phase4.5e` → `0.10.1-phase4.5e` (PATCH — additive Metadata
fields only). Tests **1115 → 1144 (+29)** in this PR: 22 unit cases
across both predicates + 2 Hypothesis monotonicity / lookback-window
properties + 1 threshold-constants pin + 2 strict-superset
invariants + 1 schema-version bump on `tests/test_config.py`.
Defense layer emitted-flag count 30 → 32. Closes Phase 4.5e ladder
(PRs 1-3).

**Phase 4.5e PR 4-eq merged via PR #224** (2026-05-23, `98e761e`) —
Form-4 10b5-1 contamination filter. First follow-up after the
Phase 4.5e ladder closed (PRs 1+2+3 = #210 + #205 + #222). Closes footgun #1 from
`compute/scoring/form4_signals.py` module docstring (10b5-1
contamination, Jagolinzer 2009 §3.2 expected FP rate 40-60% on
`insider_sell_cluster`). `_is_opportunistic_sell` now requires NOT
`is_rule_10b5_one is True` in addition to the `transaction_code ∈
{S, D}` gate — 10b5-1 scheduled trades excluded from both cluster +
C-suite cohort counts; None and False both pass (option (a)
None-handling per methodology-scientist Mode B verdict 2026-05-23,
matches CMP 2012 + Jagolinzer 2009 empirical regime used to
calibrate the existing thresholds).

**Access-path caveat — edgartools 5.31.5 does NOT parse the SEC
structured `<aff10b5One>` XML element** added by SEC Release 33-11138
(effective 2023-04-01, EDGAR schema X0609). Verified by
`edgar-debugger` 2026-05-23 + 2026-05-24 via exhaustive grep of
`/usr/local/lib/python3.11/dist-packages/edgar/` (no `aff10b5One`,
`rule10b5`, `tradingPlan`, `tradingArrangement` hits in any parse
path) AND live-XML fetch from 3 AAPL Form 4 filings confirming the
element lives at `ownershipDocument/aff10b5One` as a DOCUMENT-LEVEL
boolean (one per filing, covering all transactions). The
`equity_swap: str` field on `NonDerivativeTransaction` carries
`<equitySwapInvolved>` — unrelated SEC concept, red herring. Only access surface is footnote-
text pattern scan via `edgar.ownership.core.detect_10b5_1_plan`
(regex on `["10b5-1", "10b-5-1", "rule 10b5", "rule 10b-5", "10b5
plan", "10b-5 plan"]`). `NonDerivativeTransaction.footnotes`
carries newline-joined footnote IDs only — the parsed `Ownership`
object exposes a `footnotes: Footnotes` dict that resolves IDs to
text via public `.get(id, default)` accessor (avoids edgartools'
underscore-prefixed `_resolve_footnotes` private method). PR adds
`footnotes` to `_NON_DERIVATIVE_TX_REQUIRED_ATTRS` + `_OWNERSHIP_REQUIRED_ATTRS`
manifests, plus new `_FOOTNOTES_REQUIRED_ATTRS = ("get",)` manifest.
FP risk: terminated-plan disclosures ("10b5-1 plan terminated 2022")
match True — bias is conservative (over-excludes from opportunistic
cohort, never under-excludes); Q3 2026-08-19 audit gates negation
guard.

**Methodology verdict highlights** (Mode B 2026-05-23):
- Q1 Filter semantic: LITERATURE-ANCHORED (Cohen 2008 §III + Jagolinzer
  2009 §3.1 — 10b5-1 ⊊ routine; 75% lower predictability on NEO
  scheduled trades)
- Q2 None-handling: option (a) — None → not-10b5-1 (let cluster fire);
  matches CMP/Jagolinzer empirical regime
- Q3 Expected delta: cluster `-30% to -45%` (absolute 4-10%), C-suite
  `-45% to -65%` (absolute 1-4%) per Jagolinzer 2009 §3.2 + SEC 2022
  economic analysis
- Q4 C-suite inherits filter: YES, with STRONGER lit support than
  cluster (Jagolinzer 2009 §5.2 NEO subsample 80% predictability drop;
  CMP 2012 §V.A CFO 9× ratio)
- Q5 Weight: HOLD at 5.0 / 3.0 for this PR. Promotion 5.0 → 7.0
  (Aboody et al. 2010 §3.2 vesting-residual mid-point) is a separate
  follow-up PR after ≥ 1 cron's firing-rate data lands in
  `Metadata.form4_rule10b5_one_excluded_count`

**Rule 18 observability shipped in same PR**: new
`Metadata.form4_rule10b5_one_excluded_count: int | None` counts the
universe-wide total of transactions excluded by the filter (within
the 30d cluster window — directly tracks contamination eliminated
from cluster-detection input, not 10b5-1 trades in general). Gates
the Q3 2026-08-19 cohort-acceptance check (issue #130). Schema bump
`0.10.1-phase4.5e` → `0.10.2-phase4.5e` (PATCH — additive Metadata
field only). Defense layer emitted-flag count UNCHANGED at 32
(filter is signal-quality, not new flag). Tests 1144 → 1160+ (16
new cases per methodology pre-condition table, written by
`test-engineer` parallel-spawn).

**Three new subagents in flight (this PR)** — bumps roster 15 → 18
to drain the underutilized "Weekly · Sonnet only" pool on Max plans
while keeping the 4-opus roster fixed. All three identified as
session-observed gaps where main-agent inline work was draining the
"Weekly · all models" pool:

- **`ci-triage-engineer`** (Tier 4 Operations, sonnet) — reactive to
  GitHub Actions check failures via the PR-activity webhook. Knows
  the CI matrix (Python lint+test · Frontend build · simulate ·
  Vercel preview) + 10-class failure taxonomy (schema-pin-drift /
  ruff-I001 / F401 / F841 / dep-missing-ci-only / real-bug /
  simulate-45min-cap / flaky-transient / vercel-build-skew /
  schema-drift-CI). Proposes one-line fix the user authorizes;
  refuses to auto-flip test assertions or classify as flaky without
  re-run evidence. Closes the gap from this session where PR #224
  Python check failed and main-agent (opus) had to diagnose inline.
- **`vercel-preview-auditor`** (Tier 2 Lifecycle, sonnet) — wraps
  the Vercel MCP server (`list_deployments` → `get_deployment_build_logs`
  → `get_runtime_logs` → `web_fetch_vercel_url` 3-route UA probe).
  Codifies CLAUDE.md §Commands "When Vercel MCP is loaded, list_deployments
  → get_runtime_logs is the cheap pre-Playwright pass" — which today
  depends on main-agent memory. Fires before Mark-Ready on any UI-
  touching PR; refuses to invoke `deploy_to_vercel` or promote
  preview to production.
- **`literature-searcher`** (Tier 3 Specialized, sonnet) — WebSearch +
  WebFetch wrapper for academic papers + SEC rule releases + EDGAR
  filings. Carries the canonical CLAUDE.md anchor list of 17 papers
  in its prompt (Altman / Sloan / Beneish / Dechow / Mayew / BD /
  HLM / DT / Damodaran / Roychowdhury / Cohen / CMP / JMZ /
  Jagolinzer / Bushman-Smith / Aboody / Huber) and refuses to re-
  fetch those. For new papers: WebSearch → preferred author/SSRN/NBER
  free PDF → WebFetch → locate the section → return citation-ready
  excerpt + suggested docstring format. Offloads retrieval from
  `methodology-scientist` (opus) — judgment stays on opus, fetch
  stays on sonnet. Refuses to make a methodology verdict (that's
  methodology-scientist's slot exclusively) or paraphrase a paper
  without direct quotes.

Tier counts updated: Tier 1 Core 5 (unchanged) · Tier 2 Lifecycle
4 → 5 · Tier 3 Specialized 4 → 5 · Tier 4 Operations 2 → 3 — total
15 → 18. The 4-opus / 14-sonnet split is preserved (was 4 / 11);
all three new agents are sonnet to drain the sonnet pool per the
PR #219 + PR #223 token-economy rebalance.

Auto-routing policy table extended with 3 new cue rows + 3
delegation-pattern rows. README.md tier tables updated to match.
Doc-only otherwise — no compute / schema / scoring / valuation /
frontend code change.

**Dependabot 15-vuln triage + 2-WARN doc fix merged via PR #226**
(2026-05-23, `d67e105`) —
output from the post-PR-#225 parallel `dependency-auditor` +
`security-reviewer` spawn (2026-05-23, session 3). Dependabot wave
of 15 new vulnerabilities (6H / 7M / 2L) flagged on `main` —
**zero actionable on QuantRank's static-export deployment**. All 15
are `next@14.2.35` SSR / middleware / Server-Actions / Image-
optimization / API-route advisories requiring `next≥15.5.16`; none
have a 14.2.x backport; **all route to issue #41** (Next 14→16
migration tracker). Exploitability on the static-export site is
effectively zero per #41's own original risk rating (no SSR runtime,
no middleware, no Server Actions, no Image endpoint, no API routes —
Vercel CDN serves pre-built static HTML). 14 GHSA IDs confirmed; 1
(the 7th MODERATE) — Dependabot-alerts-API confirmation pending
(token access unavailable as of 2026-05-23). CVE baseline updates from `25 open
(1C/8H/12M/4L)` → **`15 open (0C/6H/7M/2L)`** after PR #194's
14.2.15→14.2.35 + postcss-override closed 10. Python side clean
(`requests 2.33.1` past 2.32.0 fix · `pyarrow ≥15.0` past 14.0.1
critical · `lxml ≥5.0` past 5.2 fix). GitHub Actions all current
major (`checkout@v6` / `setup-node@v6` / `setup-python@v6` /
`cache@v5` / `github-script@v9` / `upload-artifact@v7`).

The companion `security-reviewer` scan turned up 0 CRITICAL + 4 WARN
across Sections A-G + 8 spot-checks. Two land as doc fixes in THIS
PR; two deferred:

- **W1 (this PR)** — `FORM4_FETCH_SKIP=1` operational escape hatch
  was undocumented. Added §Gotchas entry in CLAUDE.md + §Security
  considerations entry in AGENTS.md describing the env-var, where
  it's set (`pre-merge-prod-sim.yml`), and the safe default behavior.
- **W3 (this PR)** — `.claude/agents/literature-searcher.md` Hard
  Constraints lacked an explicit untrusted-content guard against
  prompt injection in fetched papers / SEC HTML. Added a constraint
  bullet that treats every `WebFetch` result as data to QUOTE and
  CITE, never to execute — handles the "ignore previous
  instructions" / "fetch this other URL" / "modify your output"
  injection vectors that academic-PDF + arbitrary-URL retrieval
  surfaces.
- **W2 deferred** — `compute-rankings.yml` workflow-level
  `contents: write` is pre-existing + justified (the commit-JSON
  step is the only writer); narrowing to job-scope is a future
  optimization, not a regression.
- **W4 deferred** — `.claude/hooks/log-bash.sh` logs raw bash
  command (including inline env-var values) to gitignored
  `.claude/session.log`; severity low because file is gitignored
  and local-only; optional `sed`-scrub follow-up if desired.

`dependency-auditor` baseline-tracker update + 14 GHSA IDs to be
appended on issue #41 separately (issue-comment, not in this PR).
Doc-only PR — `ruff` / `schema_check` / `pytest` trivially pass; no
compute / schema / scoring / valuation / frontend / Python / TS
change.

**Sub-agent MCP-tools inheritance fix in flight (this PR)** —
post-PR-#225 live-fire of the three new sub-agents on 2026-05-23
surfaced a real infrastructure gap: `vercel-preview-auditor` could
not reach the Vercel MCP tools because the Claude Code sub-agent
runtime does NOT auto-inherit MCP tools — the agent file's `tools:`
frontmatter restricts the sub-agent's tool surface to what's listed
explicitly. `ci-triage-engineer` worked around the same gap by
falling back to git history, but hit GitHub API rate-limits during
the audit-fallback. Two-part fix:

- **`tools:` frontmatter extended** on both agents to list the
  specific MCP tools their workflow requires:
  `vercel-preview-auditor` gains 7 `mcp__0addee55-...__*` Vercel
  tools (`list_deployments` · `get_deployment` ·
  `get_deployment_build_logs` · `get_runtime_logs` ·
  `web_fetch_vercel_url` · `get_project` · `list_projects`);
  `ci-triage-engineer` gains 6 `mcp__github__*` GitHub tools
  (`pull_request_read` · `list_pull_requests` · `list_commits` ·
  `get_commit` · `search_pull_requests` · `search_code`).
- **Hard-constraint bullets added** to both agents covering the
  MCP-access-gap failure mode: `vercel-preview-auditor` surfaces
  `WAIT (MCP access gap)` + escalates to main (the Vercel MCP UUID
  is install-specific so a fresh clone by a different user would
  silently fail to match); `ci-triage-engineer` may fall back to
  local git primary evidence (squash-merge commit body, refs) but
  must explicitly cite the access gap in the report — never
  fabricate check-run IDs or log URLs.

Companion §Gotcha entry documents the inheritance limitation so
future agent authors don't repeat the gap. Doc-only PR otherwise —
no compute / schema / scoring / valuation / frontend / Python / TS
production-code change.

**PR-#224 review-nit polish merged via PR #227** (2026-05-23, `105d79e`) —
two of the three `quantrank-reviewer` WARN-tier punch-list items
from PR #224 landed. (a) `tests/test_scoring/test_form4_signals.py`
— two PR-#222 Hypothesis property tests
(`test_cluster_monotonic_under_added_compensation_txns` +
`test_cluster_fires_only_within_lookback`) drop `@settings(deadline=None)`
per CLAUDE.md §Gotchas "Don't use `@settings(deadline=None)` — a slow
example is itself a signal." Both tests verified to run sub-millisecond
under default 200ms Hypothesis deadline; `HealthCheck.too_slow` +
`HealthCheck.filter_too_much` suppression retained (separate concern).
(b) `test_strict_superset_invariant_holds_under_10b5_1_filter` docstring
+ inline contrapositive comment rewritten to remove the confusing `⊆`
+ "strict-superset" mixed set/boolean notation; replaced with the
unambiguous implication form "c_suite firing implies cluster firing
(PR #222 strict-superset, when the $1M floor is met)" + the
contrapositive `¬cluster ⟹ ¬c_suite` framing. (c) `_FOOTNOTES_REQUIRED_ATTRS`
manifest extension `("get",) → ("get", "__contains__")` **DEFERRED** —
sandbox environment doesn't have edgartools installed so the
`@network`-gated `test_D4_edgar_footnotes_api_surface_locked` cannot
verify that `Footnotes.__contains__` actually exists on the live class;
adding the attr blindly risks a silent break under `pytest --run-network`
on a future CI cron run. Schedule the strengthening for a follow-up
PR that can run network tests first. Tests 1168 → 1168 (no test added /
removed; 3 edits in-place). No compute / schema / scoring / valuation /
frontend / Python production-code change.

**Security WARN cleanup (W2 + W4) merged via PR #229**
(2026-05-24, `dacf293`) — closed the
two remaining security-reviewer WARNs deferred from PR #226 (W1 + W3
already shipped there). Both are operational hygiene with no
compute / schema / production-code surface; bundled in a single
focused PR.

- **W2 — `compute-rankings.yml` workflow-perm narrowing**: the
  workflow-level `permissions: contents: write` declaration was
  flagged as wider-than-needed by `security-reviewer` Section C on
  2026-05-23. The only writer in the workflow is the final `Commit
  JSON outputs` step inside the `compute:` job. Fix: workflow-level
  default narrowed to `contents: read`; the `compute:` job
  explicitly opts up to `contents: write` per least-privilege. Any
  future job added to this file now inherits `read` by default
  unless it explicitly opts up. Behavior unchanged (the compute job
  still has write); only the default surface shrinks. YAML
  parse-verified.
- **W4 — `.claude/hooks/log-bash.sh` inline-credential scrub**: the
  hook previously appended the raw Bash command (including any
  inline env-var dereference like `EDGAR_USER_AGENT=foo python ...`
  or an `Authorization: Bearer <tok>` header) to gitignored
  `.claude/session.log`. Severity was LOW because the file is
  gitignored + local-only, but an accidental `cat .claude/session.log`
  during a screen-share / pasted into a gist could leak the
  credential. Fix: `sed` pre-filter redacts the value half of known
  secret prefixes before logging, preserving prefix + structure for
  readability. Covered prefixes: GitHub tokens
  (`ghp_/gho_/ghu_/ghs_/ghr_/github_pat_`), Anthropic + OpenAI
  (`sk-ant-api*` + generic `sk-*`), AWS (`AKIA*` / `ASIA*`), Google
  (`AIza*`), Slack (`xox*-`), and bare `Bearer <tok>` /
  `Authorization: Bearer <tok>` headers. Manual scrub test:
  `Bearer ghp_abc...456` → `Bearer ghp_[REDACTED]`. Fail-open
  preserved (sed errors return original command via the existing
  `|| true` discipline).

Both fixes shipped under one PR per security-hardening bundle. CLAUDE.md
+ AGENTS.md lockstep satisfied via §Phase status in-flight notes (no
new §Gotchas — these are not invariants future code authors need to
remember; they're hardening of existing surfaces).

**Phase 4 LedgerCraft reskin · PR-A1 merged via PR #232** (2026-05-24,
`5517b98`) — first of three sub-PRs taking LedgerCraft from the
Phase 3d adopted baseline (canonical palette + `font-slab` + 4-tier
shadow tokens + AppShell/Sidebar + dark mode + `rounded-lg`
normalization) to full spec alignment (restrained palette on sector
chips + sharp ≤4px radius family + borders-as-depth). Direction
approval gate landed via the now-closed PR #231 HTML mockups under
`design-mockups/` (3 files: `current-app-snapshot.html`,
`ledgercraft-redesign.html` w/ responsive treatment for every
breakpoint + orientation). User-locked defaults on 2026-05-24:
sector palette → mute to single neutral tone (steel #475569 fg /
slate-100 bg / slate-200 ring per LedgerCraft Filter Chip spec) with
sector dots kept distinct for glance-affordance; pill shape → all
`rounded-full` → `rounded-sm` (A2); colour intensity → keep soft
sage/terracotta OKLCH tokens (no canonical alarm-red revert per
feedback 2026-05-14); output → actual `frontend/` PR series. **A1
scope**: `frontend/lib/visual.ts` — `SECTOR_COLORS` 11-entry literal
re-keyed to `NEUTRAL_CHIP_BG / FG / RG` constants (Tailwind
`slate-100 / slate-600 / slate-200` mapped to spec `#F1F5F9 /
#475569 / #E2E8F0`). Dot rgb() values kept verbatim from the prior
palette so returning users still associate sectors with their
familiar dot cue. `sectorStyle()` fallback also collapses to the
same neutral chip with a slate-400 dot for unknown-sector entries.

**Phase 4 LedgerCraft reskin · PR-A2 merged via PR #233** (2026-05-24,
`dc615ae`) — second of three sub-PRs. **Chip-family squaring** — every chip body
across the six chip surfaces flips `rounded-full` (Tailwind 9999px,
violates LedgerCraft Rule 8 "no border-radius > 4px on data
surfaces") → `rounded-sm` (Tailwind 2px, exactly LedgerCraft Chip
spec line 95 "2px radius"). Touches: `SectorChip.tsx` ·
`ScoreBadge.tsx` (sm pill only — lg radial donut + md vertical
stack keep their respective shapes) · `RecommendationBadge.tsx` ·
`LossChanceBadge.tsx` · `FilterDrawer.tsx` (4 chip groups — score
tier · recommendation · valuation · sector) · `RankingTable.tsx`
(5 active-filter chip variants at the top of the page + the
notification count badge on the Filters button). The inactive
filter chip surface in `FilterDrawer.tsx` also shifts `bg-white →
bg-slate-100` + `ring-slate-300 → ring-slate-200` to match the
LedgerCraft Filter Chip default-state spec (`#F1F5F9` bg / `#E2E8F0`
border). Status dots (`h-1.5 w-1.5 rounded-full ${...dot}`) keep
their `rounded-full` per LedgerCraft Border-Radius spec line 51
("Full (9999px): Status dots, toggle switches" — explicit
exception). `MoSBadge.tsx` is a radial SVG donut (no chip body)
and `MoSCell.tsx` already uses `rounded-sm` (the micro diverging
bar at the MoS column) — both untouched. **Out of scope this PR**:
table card border treatment + alternating-row bg shift to
`slate-100` (A3); sidebar nav-item radius normalization (A3); 
FilterDrawer "View N stocks" footer button + search-input radius
(A3 button + input pass). No schema / Python / scoring / valuation
change — JSX className-only diff. Live `npm install` + `tsc
--noEmit` + `next build` run by CI (sandbox has no `node_modules`;
visible TS errors are pre-existing env noise).

**Phase 4 LedgerCraft reskin · PR-A3 merged via PR #234** (2026-05-24,
`1a9501c`) — third and final of three sub-PRs. **Table + frame polish** — sharpens
the remaining frame-level radii and drops the soft shadow tokens from
the data grid per LedgerCraft Elevation philosophy ("flat design with
borders as the primary depth indicator. Shadows are used sparingly —
only for overlays and dropdowns that must appear above the data grid").
Touched five files:

- `RankingTable.tsx` — desktop table card `rounded-lg shadow-medium`
  → `rounded` (4px, border-only) per Cards spec line 79 + Elevation
  line 55 · alternating row `even:bg-slate-50` → `even:bg-slate-100`
  + hover `hover:bg-slate-100` → `hover:bg-slate-200` to match the
  LedgerCraft Rule 5 alternating-row palette (`#FFFFFF / #F1F5F9` =
  white / slate-100) · Filters button `rounded-md shadow-sm` →
  `rounded-sm` (no shadow) per Button spec line 70 (Secondary button
  size Medium = 32px / 8px 16px / 13px / **2px radius**) · search
  input `rounded-md shadow-sm` → `rounded-sm` (no shadow) per Text
  Input spec line 91 · mobile cards `rounded-lg shadow-sm` →
  `rounded` (4px, no shadow) + hover bg align to slate-100 · mobile
  rank label + delta pill `rounded-md` → `rounded-sm` · empty-state
  card `rounded-lg` → `rounded` · pagination Prev/Next buttons
  `rounded-md shadow-sm` → `rounded-sm`.
- `Sidebar.tsx` — brand mark `Q` `rounded-md` → `rounded-sm` (matches
  LedgerCraft Filter Chip / Button radii at 2px) · collapse + mobile
  close buttons `rounded-md` → `rounded-sm` · nav-item `rounded-md`
  → `rounded-sm` (per LedgerCraft Lists "Default Item" spec line 101
  which uses no radius itself; 2px matches the ambient button family).
- `FilterDrawer.tsx` — close button + Clear-all button + footer "View
  N stocks" primary CTA + search input all `rounded-md` → `rounded-sm`;
  search input loses `shadow-sm` per Text Input spec.
- `AppShell.tsx` — mobile hamburger `rounded-md` → `rounded-sm`.
- `app/page.tsx` — "Compute pending" empty-state banner
  `rounded-lg` → `rounded` (4px per Cards spec).

Preserved (out of scope this PR, deferred to later polish or
no-change-needed)
- Status dots (`rounded-full` inside chips) — LedgerCraft Border-
  Radius spec line 51 explicit exception ("Full (9999px): Status
  dots, toggle switches").
- `app/stock/[ticker]/page.tsx` — per-stock detail page chrome
  not in scope; will inherit the new chip + table conventions
  automatically through shared component imports
  (`SectorChip` / `ScoreBadge` / `RecommendationBadge` /
  `LossChanceBadge` already squared via A2).
- `StockLogo.tsx` `rounded-md` — logo container, not a chip;
  6px is acceptable per LedgerCraft Cards Medium radius
  (4-6px band) and the larger size warrants a softer corner.
- OKLCH soft sage/terracotta tokens.
- Layout / column order / spacing / typography — UNCHANGED.

The three-PR Phase 4 LedgerCraft reskin series (A1 + A2 + A3) lands
the project on full spec alignment: restrained palette (sector chip
body neutralized to steel, semantic colors stay OKLCH-soft for
positive/negative pairs), sharp ≤4px radius family across every
chip / button / input / card surface, and borders-as-depth with
shadows only on overlays (FilterDrawer keeps `shadow-overlay`
from its slide-over `<aside>` since it IS an overlay). No schema /
Python / scoring / valuation / output JSON change across the
entire 3-PR series — all token-and-className diffs under
`frontend/`.

**Phase 4 LedgerCraft alignment · PR-B1 merged via PR #235** (2026-05-24,
`2b588c8`) —
follow-up surfaced by the post-A3 `frontend-design-reviewer` audit
(28 MUST-FIX + 5 SHOULD-FIX violations across 16 untouched
components). **B1 = score-tier token fix** — `frontend/lib/visual.ts`
removes teal + orange (two color families outside the LedgerCraft
restrained palette of forest / amber / steel / red) from the
score-tier ramp. (a) `TIERS[1]` "Strong" (scores 55-70) shifts from
`teal-50/700/200` + `teal-500` dot to `emerald-50/600/200` +
`emerald-400` dot — emerald step-down from "Exceptional" (70+
emerald-700/500) preserving the 5-step ramp via lighter shade rather
than a new hue. (b) `TIERS[3]` "Weak" (scores 25-40) shifts from
`orange-50/700/200` + `orange-500` dot to `amber-50/800/300` +
`amber-600` dot — amber step-down from "Average" (40-55
amber-50/700/200 + amber-500 dot) preserving the ramp via darker
shade. (c) `scoreColorClasses` 20-40 band mirrors the same orange →
amber shift. (d) `scoreAccentColor` 20-40 band shifts from
`rgb(249 115 22)` (orange-500) to `rgb(180 83 9)` (amber-700) so the
ScoreBadge `size='lg'` radial-gauge stroke + tier-label color stays
consistent with the chip body. **Cascade** — `ScoreBadge.tsx`
(sm pill + lg radial), `FilterDrawer.tsx` score-tier filter chips,
and `RankingTable.tsx` Score column inherit the fix automatically
since they all import from these tokens; no component code changes.
**B2 + B3 + B4 deferred** to follow-up PRs (card surface
normalization · chip shape squaring round 2 · stripe + hover polish —
~50-70 lines across 8 more components). No schema / Python /
scoring / valuation / output JSON change — token-only diff.

**Phase 4 LedgerCraft alignment · PR-B2+B3+B4 combined merged via PR #236** (2026-05-24, `08d7563`) —
final follow-up of the post-A3 design-reviewer audit. Combined B2
(card surface normalization) + B3 (chip shape squaring round 2) +
B4 (stripe + hover polish) into one PR because the three scopes
share five files (FairPriceBarChart · FairPriceCard ·
ManipulationRiskCard · Tier2EventCard · `app/stock/[ticker]/page.tsx`)
and splitting them would force the second/third PR to rebase on
each merge. **Scope (10 files, ~30 className edits)**:

- `app/stock/[ticker]/page.tsx` — detail-data-pending banner +
  hero header + empty-state placeholder + data-quality section
  `rounded-lg shadow-large/medium` → `rounded` (4px, no shadow) ·
  rank badge `rounded-md` → `rounded-sm` · filing-lag badge
  `rounded-full` → `rounded-sm`
- `FairPriceBarChart.tsx` — outer section `rounded-lg` → `rounded` ·
  headline card `rounded-lg shadow-medium` → `rounded` · per-method
  list `rounded-lg shadow-subtle` → `rounded` · 3 tally pills +
  per-method verdict badge `rounded-full` → `rounded-sm`
- `FairPriceCard.tsx` — 2 section cards `rounded-lg` → `rounded` ·
  inner table `rounded-md` → `rounded` · warning chip `rounded-full`
  → `rounded-sm` · MethodRow hover `hover:bg-slate-50` →
  `hover:bg-slate-100`
- `ManipulationRiskCard.tsx` — section card `rounded-lg` →
  `rounded` · severity chip `rounded-full` → `rounded-sm`
- `PillarRadarChart.tsx` — section card `rounded-lg shadow-medium`
  → `rounded` · pillar bar track `rounded-md` → `rounded-sm`
- `RawMetricsTable.tsx` — outer container `rounded-lg shadow-medium`
  → `rounded` · alt-row `even:bg-slate-50 hover:bg-slate-100` →
  `even:bg-slate-100 hover:bg-slate-200` (per Rule 5 #FFFFFF /
  #F1F5F9)
- `Tier2EventCard.tsx` — section card `rounded-lg` → `rounded` ·
  severity badge `rounded-full` → `rounded-sm`
- `PriceHistoryChart.tsx` — 2 off-chart Fair/Target reference chips
  `rounded-full` → `rounded-sm` (chart legend swatches kept
  `rounded-full` per "decorative visual flourish" — fine since they're
  not data chips)
- `PriceTimePeriodSelector.tsx` — period button base `rounded-full`
  → `rounded-sm` · unselected hover `hover:bg-slate-50` →
  `hover:bg-slate-100`
- `ThemeToggle.tsx` — both layouts (row + icon) `rounded-md` →
  `rounded-sm`

Status dots (`h-1.5 w-1.5 rounded-full`) preserved per Border-
Radius spec line 51 exception. DualRange thumb pseudo-elements,
MoSBadge SVG donut, MoSCell inline RGB, StockLogo `borderRadius:
'50%'`, and Recharts adapter hex values all OK-TO-KEEP per
spec / Rule 0 carve-outs. After this PR the project is at full
LedgerCraft palette + theme alignment across every component —
restrained 4-family palette, sharp ≤4px radii, borders-as-depth
on every data surface (overlays and slide-overs keep their
elevation shadows). No schema / Python / scoring / valuation /
output JSON change.

**Form-4 10b5-1 docstring precision fix in flight (this PR)** —
`edgar-debugger` follow-up to PR #224 (F2 deferred from session 4
post-live-fire). The `literature-searcher` proof-of-life on
2026-05-23 flagged a precision gap: the form4 module docstring
referenced the colloquial `<rule10b5_1>` XML tag name (a label, not
the actual SEC EDGAR Ownership XML element). `edgar-debugger`
re-audit on 2026-05-24 fetched 3 live AAPL Form 4 XMLs from SEC
EDGAR and confirmed the actual element is **`<aff10b5One>`** at
`ownershipDocument/aff10b5One` — a **document-level boolean** (one
per filing, covering ALL transactions in that Form 4), NOT a
per-transaction attribute. Updated 7 references across 5 code files
(`compute/scoring/form4_insider.py` ×3 + `compute/scoring/form4_signals.py`
×1 + `compute/output/schemas.py` ×1) + 2 docs (CLAUDE.md +
AGENTS.md) to use the canonical name. Added a §"Footnote resolution"
architectural-gap note in `form4_insider.py` docstring: a filer who
checks `<aff10b5One>true` at the document level but does NOT include
the footnote text on a specific transaction (valid — the checkbox IS
the formal affirmative defense, footnotes are supplemental) will
slip past the current footnote-text path and enter the opportunistic
cohort incorrectly. Deferred to a follow-up PR that parses the raw
Form 4 XML directly for `<aff10b5One>` at the filing level (a
non-trivial change requiring direct XML parse since edgartools 5.31.5
still doesn't expose the element). PyPI confirmed 5.31.5 is the
current edgartools release; no newer version adds a parse path.
`detect_10b5_1_plan` regex set (6 patterns) is complete vs real-world
footnote text — no additions needed (pattern `"10b5-1"` alone covers
every common variant including `Rule 10b5-1(c)` subsection cites).
Docstring-only PR — no compute / scoring / valuation / behavior
change. `schema_check` clean, ruff clean, tests unchanged at 1168+.

**Simulate 45-min recurrence root-cause fix bundled with this PR** —
the docstring-only commit above triggered the `simulate` workflow
(path filter matched `compute/scoring/**`) which then **cancelled
at 45m02s** on the timeout cap. `ci-triage-engineer` deep-dive
(2026-05-24 session 5) identified the recurring pattern: the
`QR_SKIP_TIER2` kill-switch is fully wired in
`compute/scoring/tier2.py:158` but **was never set in
`pre-merge-prod-sim.yml`**. Past mitigations (PR #165's 1y
non-reliance lookback, PR-form4-2's `FORM4_FETCH_SKIP=1`) addressed
adjacent budget items but left the Tier-2 loop (502 tickers × 10-K
text fetch + 8-K fetch, 20-35m cold-cache) running unconditionally
on every simulate. Recurrence tally on the last 5 simulate runs:
PR #165 ✅ 19m01s warm · PR #204 ✅ 19m37s warm · PR #222 ✅ 16m56s
warm · PR #224 ✅ 17m08s warm · PR #230 ❌ 45m15s cold cancelled.
Pattern is structural — when GitHub evicts the warm cache after a
7-day gap without a simulate-triggering PR, the next compute/scoring
PR hits full cold. Four-part permanent fix lands in this PR:
(a) `QR_SKIP_TIER2: "1"` added to `pre-merge-prod-sim.yml` env
block (PRIMARY — eliminates the 20-35m cold-cache cost);
(b) `compute/cache/edgar_form4` added to both workflows' cache
restore paths (future-proof for the Phase 4.5e PR 5 form4 weight
promotion); (c) path-filter widened to include
`compute/ingest/**` + `compute/valuation/**` + `compute/output/schemas.py`
+ `compute/main.py` + `pyproject.toml` (was: scoring + features
only — a fundamentals fetcher regression would silently miss
simulate); (d) `compute/scoring/tier2.py:154-155` docstring updated
— old comment said `_EIGHT_K_DEFENSES_ENABLED=False` (stale since
PR 4g 2026-05-17 re-enabled it); new comment correctly notes the
non_reliance veto IS suppressed in simulate (acceptable — simulate
is informational-only; veto correctness is offline pytest's slot).
Expected: docstring/comment PRs that touch compute/ → simulate
completes in 12-15m warm OR 17-20m partial-cold; real scoring PRs
get the same budget with composite-score diff unchanged. Companion
benefit: this PR doubles as the **live validation** of the fix
(re-pushing the docstring change with the simulate-fix appended
should produce the first sub-45m simulate run on this branch).

**Simulate Part 4 — fundamentals freshness-gate skip (in flight, this PR)** —
Parts 2 + 3 alone did NOT close the recurrence. Re-pushing the
QR_SKIP_TIER2 fix (commit `ae1c2f2`) on 2026-05-24 07:06 UTC still
hit simulate cancellation at 45m15s. `ci-triage-engineer` deep-dive
#2 identified the gap: my session-5 root-cause analysis was
INCOMPLETE — `compute/main.py` has THREE independent SEC EDGAR
ThreadPoolExecutor loops:
- Step 2 (`compute/main.py:728`) — fundamentals snapshot (502
  tickers × `companyfacts` XBRL)
- Step 3 (`compute/main.py:805`) — annual fundamentals history
  (502 tickers × `_ANNUAL_TAGS` per-year XBRL)
- Step 4b (`compute/main.py:1025`) — Tier-2 / 8-K orchestrator
QR_SKIP_TIER2 killed Step 4b (20-35m) but Steps 2 + 3 still ran
unconditionally. Cold-cache cost of fundamentals alone is 25-50m
per CLAUDE.md §Gotchas — enough to fill the entire 45m budget.
`_is_fresh()` in `compute/ingest/fundamentals.py:917` gates the
disk cache by `filed_date` inside the parquet (not by file mtime)
with `FUNDAMENTALS_REFETCH_DAYS=45` — so even on a partial cache
hit, any ticker with a > 45d-old most-recent filing forces a live
EDGAR round-trip.

**Part 4 fix**: `QR_SKIP_FUNDAMENTALS=1` escape hatch wired in
TWO places — (a) `compute/ingest/fundamentals.py:fetch_fundamentals`
at the top, BEFORE `_require_identity()`, returns cached snapshot
unconditionally (no freshness check) when the env var is set;
falls through to live fetch if no cache exists. (b)
`compute/ingest/fundamentals.py:fetch_fundamentals_history`
mirror — returns the cached annual parquet without the 180d age
check when env var set. The env var is wired in
`.github/workflows/pre-merge-prod-sim.yml` env block alongside
`QR_SKIP_TIER2` + `FORM4_FETCH_SKIP`. SAFE for simulate because:
the workflow's purpose is composite-score-diff vs main's COMMITTED
`rankings.json`; both sides were produced from the same upstream
fundamentals input (the cache the weekly cron wrote), so using
that cache without re-fetch is the CORRECT input for the diff,
not a quality compromise. Weekly cron (`compute-rankings.yml`)
does NOT set `QR_SKIP_FUNDAMENTALS` — full live fetch still runs
there and populates the warm cache for future simulate restores.
Expected post-fix: simulate completes in 8-12m on a cache-hit
restore (no live SEC fetch in Steps 2 + 3 + 4b). Live validation
this PR: re-push after Part 4 → simulate green under 25m.

**Rebase-discipline § + parallel-PR §Phase status §Gotcha bundled with this PR** —
on top of Parts 1 + 2, this PR also closes a recurring CI-merge
issue surfaced 2026-05-24: PR #230 hit `mergeable_state: dirty`
twice in a single session — first when PR #229 (security) landed
on main mid-iteration, then again when PR #232 + PR #233
(LedgerCraft A1 + A2) landed before Mark-Ready. Each parallel PR
adds a "**X in flight (this PR)**" bullet in CLAUDE.md §Phase
status + AGENTS.md §Phase + version state at the SAME insertion
line, and `git merge` cannot auto-resolve two adds at the same
line. Three companion edits documenting + mitigating:
- **§Conventions**: new bullet "Rebase onto `origin/main` before
  flipping any PR Draft → Ready" with the operational `git fetch
  origin main && git rebase origin/main` recipe + the "keep both
  entries in chronological order" resolution discipline
- **§Gotchas**: new "Parallel-PR §Phase status collision pattern"
  entry recording the recurring symptom + the local-mitigation
  workflow + a forward-looking structural follow-up note (move
  in-flight entries to a side file like `PHASE_STATUS_INFLIGHT.md`
  that's append-only-per-PR; not yet adopted)
- **AGENTS.md mirror** of both notes for cross-tool agents
No infrastructure / CI / behavior change — pure doc discipline.
Future contributors who hit the same conflict find the §Gotchas
entry + the §Conventions recipe and resolve in seconds, instead
of re-discovering the pattern.

**Next deliverables** (pick by appetite):
- **Phase 4.5e PR 5 — cluster weight promotion 5.0 → 7.0** — after ≥ 1
  cron's `form4_rule10b5_one_excluded_count` lands and firing-rate
  delta confirms the -30% to -45% predicted band (Aboody et al. 2010
  §3.2 mid-point; vesting-driven liquidation residual still argues
  against full 10.0 restoration)
- **Issue #67 — DONE** (PR #294, 2026-05-28): `USE_SECTOR_COE = True` flipped
  (`value_trap_risk` 132 → 109); now tracking per-sector delta via
  `Metadata.value_trap_risk_delta_by_sector` (PR #300)
- **Phase 4i.1 / 4j.1 / 4k.1** — JKP / Qlib / IPCA integration PRs
  (~1-2w each → v1.1.0-phase4)
- **Phase 5** — ML meta-learner (~10-12w, unblocks PR 4b §3
  IC-decay writer #75)

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
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) — vendor / license
  posture per third-party source
- [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md) — mattpocock
  skill consumer rules for GitHub Issues access via the GitHub MCP server
- [`docs/agents/domain.md`](docs/agents/domain.md) — mattpocock skill
  consumer rules for QuantRank's multi-file CONTEXT analog +
  PHASE_STATUS_INFLIGHT.md as ADR analog
- [`.claude/skills/README.md`](.claude/skills/README.md) — skill index
- [`docs/LESSONS_LEARNED.md`](docs/LESSONS_LEARNED.md) — running log of
  agent-process dos/don'ts + per-session mistakes (workflow / git / review
  discipline; complements §Gotchas, which owns code/domain invariants)
