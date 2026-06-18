# CLAUDE.md

QuantRank is a static-site US-equity ranking tool. Python compute layer
generates JSON; a Next.js static site renders it. Currently ranks the
S&P 900 (~903 names: S&P 500 large-caps + S&P 400 mid-caps; `sp500`-only
via manual dispatch). See
[`README.md`](README.md) for the user-facing pitch,
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) for the academic
backing, and [`docs/design.md`](docs/design.md) for the visual /
design-system spec.

## Stack

- **Python 3.11+** — pandas 2.2 · edgartools 5.32 · pydantic 2.6 ·
  tenacity 8.2 · BeautifulSoup 4 · lxml 5 · pytest 8 · ruff 0.4
- **Next.js 14.2** (App Router, static export) — React 18.3 ·
  TypeScript 5.9 · Tailwind 3.4 · Recharts 2.15. Fonts via @fontsource:
  **IBM Plex Sans** (body) · **JetBrains Mono** (tabular numerics) ·
  **Roboto Slab** (headlines). LedgerCraft design system: `AppShell` +
  `TopNav` (sole nav since PR #414), brand primary `emerald-700`
  (`#047857`), `next-themes` class-strategy dark mode with paired
  `dark:` variants on every surface. Visual spec + adoption history:
  [`docs/design.md`](docs/design.md).
- **CI** — GitHub Actions; weekday `compute-rankings.yml` (cron Mon-Fri
  22:00 UTC; `trading-day-gate` skips weekends + NYSE holidays; folds a
  warm PIT-backtest refresh so the AI-pick home updates each cron) +
  Saturday `precache-edgar.yml` (08:00 UTC off-cycle EDGAR cache warmer,
  #249 — full 5-loop `compute.main`, outputs discarded, caches saved)
- **Data** — SEC EDGAR via `edgartools` · yfinance for prices · S&P 500 +
  S&P 400 constituents scraped from Wikipedia (`QR_UNIVERSE=sp900` cron
  default since Phase B flip 2026-06-16; `sp500`-only via manual dispatch)

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
| `.claude/skills/` | Invocation-triggerable skills (first-party + vendored — license posture per source in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)) + `phase-N/` planning stubs. Index: [`.claude/skills/README.md`](.claude/skills/README.md). |
| `.agents/skills/` | Vendored third-party skills in the cross-tool [skills.sh](https://skills.sh) layout (currently 1: `impeccable`, Apache-2.0, symlinked into `.claude/skills/`, pinned by `skills-lock.json`). Dev-session tooling only — never runs in CI / the export / the cron. |
| `.claude/agents/` | 25 project subagents in 5 tiers (Core · Lifecycle · Specialized · Operations · write-capable Builders: `compute-builder` owns `compute/**`, `frontend-builder` owns `frontend/**`). Routing matrix + 8 coordination flows: [`.claude/agents/README.md`](.claude/agents/README.md); agent-team recipes: [`.claude/agents/TEAMS.md`](.claude/agents/TEAMS.md). |
| `.claude/hooks/` | 3 bash hooks wired by `.claude/settings.json`: `log-bash.sh` (Bash audit log → `.claude/session.log`) · `schema-reminder.sh` (schema-triple edit reminder) · `delegate-first.sh` (orchestrator-role + team auto-proposal nudge every turn). All fail-open, 5s timeout. |
| `.claude/worktrees/` | Harness-managed isolation dirs for `isolation: "worktree"` subagent spawns. Transient, gitignored — never commit. |
| `docs/agents/` | Config consumed by the vendored mattpocock skills: `issue-tracker.md` + `domain.md`. See §Agent skills. |

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

MCP connectors, managed in Claude app Settings → Connectors (repo files
cannot toggle them — the user flips the switch there):

| Connector | Status | Use |
|---|---|---|
| **GitHub** | ✅ active | PRs, issues, releases, CI runs, file ops |
| **Vercel** | ✅ active | pre-Playwright deploy + runtime log check: `list_deployments` / `get_deployment_build_logs` / `get_runtime_logs` |
| **Supabase** | ⏸ toggle OFF (token-economy policy 2026-06-11) | reserved for Phase 5+ — re-enable with the Phase 5 client-wiring pre-PR |
| **Sentry** | ⏸ toggle OFF (same policy) | planned post-deploy monitor; re-enable when the `@sentry/nextjs` wiring PR lands |
| Gmail · Google Drive | ⏸ toggle OFF (same policy) | rarely used; re-enable per-task for cross-tool comms / doc backup |

Unused connectors cost schema/name tokens on surfaces that load tools
eagerly. If `ToolSearch query="<name>"` returns no matches, the session
predates the connector — don't restart mid-task (loses audit context);
delegate the connector-bound step to a sibling session
([`AGENTS.md`](AGENTS.md) §"Multi-session audit pattern").

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
  [`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md) (PR #230) made
  phase-status entries parallel-safe, so the rebase is the backstop for
  the OTHER conflict surfaces (shared code edits, workflow YAML, schema
  bumps): run `git fetch origin main && git rebase origin/main` and
  resolve benign doc conflicts "keep both in chronological order".
- **Session-start phase identification.** First action on any new
  session: read [`PHASE_STATUS.md`](PHASE_STATUS.md) §"Current state"
  for active schema + phase + defense-layer count + in-flight PRs, then
  route through [`WORKFLOW.md`](WORKFLOW.md) §"Agentic 6-Phase Cadence"
  (Planning → Code Gen → Integration → Test → Deploy → Monitor) using
  the standing 25 subagents — don't spawn ad-hoc workflow agents on top.
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

The main session is the **orchestrator / tech lead** of the 25-agent
team, not the laborer. Default on any task: **spawn the matching
sub-agent from `.claude/agents/`**, not inline work (the
`UserPromptSubmit` hook re-injects this rule every turn). Main-session
tokens land on the "Weekly · all models" pool; sonnet sub-agents drain
the separate, paid-but-under-utilized "Weekly · Sonnet only" pool.

**Inline work is the EXCEPTION**, acceptable only when: (a) no agent's
`description:` matches; (b) trivial lookup — ≤ 1 Read + a one-sentence
answer; (c) the user says "ทำเอง" / "inline this" / "don't spawn
agents"; (d) the work IS the agent / hook / settings
meta-infrastructure itself; (e) cross-agent synthesis after sub-agents
report. Otherwise STOP and spawn first.

### Routing table — trigger → spawn

One row per fire-pattern; user-ask cues and event cues share a row.
Sonnet agents (the unmarked default) fire on edits / signals in their
domain; the five **opus** agents (`quantrank-reviewer` ·
`methodology-scientist` · `release-captain` · `incident-commander` ·
`financial-engineer`) are gate / signal-only. **Non-trivial edit** =
> 5 added lines OR non-comment code OR a public-symbol change (pure
comment / whitespace / single-line fixes don't trigger). Spawn
read-only agents **without asking** — only a proposed destructive
command needs user authorization. Pattern not in the table → walk the
`description:` fields of all 25 agents before defaulting to inline.

| Trigger (user ask OR event) | Spawn |
|---|---|
| "ก่อน push" / "ready to push" / "open PR" / "mark ready" / "ตรวจก่อน push" — OR explicit "full review" / "deep review" / diff > 200 lines on `compute/scoring/` | `quantrank-reviewer` (opus) + `phase-coordinator` Mode B, plus conditional sonnet re-batch (`schema-sentinel` / `defense-layer-auditor` / `frontend-design-reviewer` / `docs-reviewer` / `security-reviewer` / `test-engineer`, dedup-skipped). **The opus review fires at this gate only — NOT on every push / edit set** (narrowed 2026-06-11, token economy) |
| "ตรวจ data หุ้น" / "check ticker X" / "verify the output" / "ตรวจ output" / pre-release | `stock-detail-auditor` — deterministic prefilter, then thorough verdict per flagged ticker |
| Non-trivial edit to `schemas.py` / `types.ts` / `schema-snapshot.json` OR "schema in sync?" OR CI schema-drift | `schema-sentinel` |
| Non-trivial edit to `compute/scoring/*` / `compute/valuation/*` OR "audit defenses" / defense count diff | `defense-layer-auditor` |
| Non-trivial edit to `frontend/components/*` / `frontend/app/*` OR "design X" / new UI component / "doesn't match the rest" | `frontend-design-reviewer` — emits Playwright spot-check matrix |
| Non-trivial edit to `.github/workflows/*` OR new env-var read OR "scan for secrets" / pre-release | `security-reviewer` |
| Dependabot alert OR new dep in `pyproject.toml` / `frontend/package.json` OR "ตรวจ CVE" | `dependency-auditor` + `security-reviewer` (parallel) |
| Prod code without a test in the same diff OR "write tests for X" / "TDD this" | `test-engineer` |
| Non-trivial edit to CLAUDE.md / AGENTS.md / SKILL.md / WORKFLOW.md / PHASE_STATUS.md / README.md / METHODOLOGY.md OR "ตรวจ doc" | `docs-reviewer` — substance check (file-touch lockstep = `phase-coordinator` Mode B at the gate) |
| `tests/test_ingest/` failure OR live-run hang OR SEC 429/403 OR edgartools drift | `edgar-debugger` |
| "ทำไม cron ช้า" OR warm-cache > 10 min OR p95 > 20s | `performance-engineer` |
| Cron fails / hangs / corrupt output OR Vercel deploy breaks OR schema CI fails OR "production is broken" / "site is down" / "incident" | `incident-commander` (opus, P1) — immediate |
| CI check fails on an open PR (webhook) OR "CI fail" / "Python test red" / "build แตก" / "เช็คทำไม CI fail" | `ci-triage-engineer` — proposes the one-line fix |
| Pre-Mark-Ready on a UI-touching PR OR Vercel preview URL posted OR "ดู preview" / "is deploy green?" | `vercel-preview-auditor` — Vercel MCP chain before Playwright |
| Post-cron green OR pre-release OR vercel GO on a UI PR OR "ลองใช้ app (จริง)" / "expert user feedback" / "UX จริง" / "is the app actually usable?" | `expert-user-explorer` — serves the export, drives Playwright persona missions; NOT per-edit |
| Methodology cite outside the CLAUDE.md anchor list (paper text matters) OR "find me the paper that says X" / "หาเปเปอร์เรื่อง Y" OR new defense-flag prior | `literature-searcher` — keeps opus tokens on judgment |
| `workflow_dispatch` on `compute-rankings.yml` lands green | Post-cron parallel batch: `defense-layer-auditor` (Section A-L + I) + `stock-detail-auditor` + `data-pipeline-engineer` + `data-analyst` + `expert-user-explorer` |
| Edit under `compute/ingest/**` OR `data/sp500_membership_historical.csv` edit OR `Metadata.*_coverage_pct` drop OR "ตรวจ data pipeline" / "is the data pipeline healthy?" | `data-pipeline-engineer` |
| "วิเคราะห์ data" / "analyze the rankings" / "score / sector distribution" / "what changed this week" | `data-analyst` |
| "is this signal real?" / "IC เท่าไหร่" / "overfit ไหม" / "วิเคราะห์เชิงสถิติ" OR PBO-DSR / leakage probe OR Phase-5 ML scoping | `data-scientist` — empirical seat (financial-engineer designs → data-scientist evaluates → methodology-scientist ratifies) |
| New defense flag proposed OR threshold / weight change in `manipulation_index.py` / `earnings_quality.py` OR "validate against literature" OR quarterly cohort audit (next 2026-08-19) | `methodology-scientist` (opus) — new flags also get `test-engineer`; the quarterly audit pairs `defense-layer-auditor` |
| "design a new valuation method / factor / scoring pillar / defense flag" / "ออกแบบ factor / โมเดล quant" / "scope Phase 5/6/7" (construct doesn't exist yet) | `financial-engineer` (opus) → `methodology-scientist` ratifies the prior |
| "tag release" / "cut a release" / "ตัด release" OR phase-epic PR merged | `release-captain` (opus) — owns the release ladder |
| New `claude/*` branch from a handoff · phase / sub-PR complete | `phase-coordinator` Mode A · Mode C (Mode B rides the push gate) |
| "implement X in compute/" / "build the Y component / route" / cross-layer feature build | `compute-builder` / `frontend-builder` (**write**, disjoint layers) — or propose a **Feature Squad** team ([`.claude/agents/TEAMS.md`](.claude/agents/TEAMS.md)) |

### Spawn discipline

- **Route on the handoff line.** Every agent report ends with
  `HANDOFF · status=… · next=<DONE | SPAWN <agent>:<scope> | ESCALATE
  <agent>:<why> | NEEDS-USER:<decision>>` — compose next steps
  dynamically; the 8 flows in
  [`.claude/agents/README.md`](.claude/agents/README.md) are canonical
  examples, not an exhaustive script.
- **Don't gatekeep sub-agent effort** — no word caps / "≤ N items";
  sonnet tokens drain the under-utilized Sonnet-only pool. Keep the
  5-opus / 20-sonnet model split and the effort policy (23 of 25 at
  `effort: max`; the two deterministic script-runners `schema-sentinel`
  + `vercel-preview-auditor` at `high`; a new agent gets `max` unless
  it's a pure mechanical lookup). Rationale + authoring conventions:
  README §Model split + §Authoring #3.
- **Ask before authorizing a destructive command** an agent proposes
  (e.g. `release-captain`'s `git tag` + push); honor "skip the X
  agent" / "I'll handle it manually" — note the skip and proceed.
- **Parallel at gate moments, not per edit** — batch-mates at the push
  gate spawn in one message. **De-duplicate**: same agent + same
  unchanged diff within ~10 min → point at the prior result.
- **Disable per-session**: `/agents` toggle, or "spawn only on
  explicit ask this session".

### Agent-team auto-proposal (Claude proposes, you confirm)

When the task is team-fit, **proactively propose** the recipe (the
hook nudges this every turn): cross-layer build → **Feature Squad** ·
new flag/threshold/factor → **Methodology Debate** · root-cause-unclear
incident → **Incident War Room** · big multi-lens PR → **PR Review
Crew**. Propose-not-create — the user confirms; on web/mobile propose
the subagent fallback (same flow). Cue→recipe table:
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
- **pre-merge-prod-sim must mirror the cron's TWO cache bundles AND its `timeout-minutes` — the 5 QR_SKIP_* skips only help on a cache HIT**
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
- **Whole-app polish conventions (`$impeccable polish`, 2026-06-03)** — empty-state CTA `disabled` · labeled chip in `aria-label`'d container is `aria-hidden` · negative chip ring is `-200` only · no `mb-*` on valuation sections
- **Footer build-version chip = build-time `NEXT_PUBLIC_APP_VERSION`, never hardcoded**
- **`pillarColor`→`lib/visual` + `flagLabel`→`lib/flag-labels` are SHARED tokens — don't re-inline**
- **`globals.css` soft-color `!important` override is LITERAL-class-keyed — never reaches `dark:` solid-fills (theme audit #401)**
- **Home + ranking pages derive stats at BUILD TIME (Server Components) — never `fs`-import into a `'use client'` component**
- **`data/sp500_membership_historical.csv` must stay ADD/REMOVE-balanced — run `scripts/verify_membership_ledger.py` after ANY edit; Track B covers 2016→present, rename-aware**
- **The home page IS the AI-pick portfolio — `getAiPickData()` fs-read; NEVER static-`import` the 1.3MB `backtest_pit.json`. The AI sizes its own basket when `nav.adaptive` is present (composite ≥ 65 / floor 5 / no cap (uncapped 2026-06-11)); the 1-20 slider + `nav.by_count[N]` are the legacy fallback for pre-adaptive artifacts**
- **Per-stock JSON for dropped tickers auto-pruned by `prune_orphan_stock_files()` — don't glob `stocks/` for param-gen**
- **`AnnualReturnsTable` + `NavCompareChart` money mode derive in-browser from NAV; the CAGR caveat is DATA-DRIVEN on `meta.veto_layer_replayed` — never hardcode it, and backtest ≠ live track record**
- **Agent teams (experimental, ≠ subagents) — desktop-terminal only; builders own disjoint layers; recipes in [`.claude/agents/TEAMS.md`](.claude/agents/TEAMS.md)**
- **Dual-class `shares_outstanding` = SEC company-TOTAL across classes (ASC 260 / RATIFY-B #374); the per-class count lives in `shares_outstanding_listed_class` (display-only)**
- **edgartools `Company("")` resolves to an ARBITRARY company (no raise) — resolve a real CIK (`snap.cik` → `Company(ticker).cik`) before any history fetch; empty-CIK `fetch_fundamentals` calls also bypass the snapshot parquet cache BOTH ways**
- **8-K event cache TTL is JITTERED per-ticker (`EDGAR_8K_CACHE_TTL_SECONDS + _ttl_jitter_seconds(ticker)`, 0-72h SHA-256-stable) — do NOT flatten back to a bare TTL; the jitter de-syncs the 502-cohort cold-burst expiry that caused the ~80-min tier2 spike every ~6 days (#469)**
- **Fast-cache is FROZEN-IMMUTABLE within a quarter — parquet mtimes / fetch-recency signals are NO-OPs; the only safe skip path for stale-but-cached tickers is a filing-date precheck against SEC each run (`_latest_filing_date` in `compute/ingest/fundamentals.py`, #471)**
- **Backtest PIT data is parquet-gated + graceful — `data/{historical_sector,pit_item402_history}.parquet` (whitelisted past `*.parquet`; regen via `scripts/backfill_{historical_sector,item402_history}.py`) drive `meta.sector_from_today` + `vetoes_replayed`/`not_replayed` DYNAMICALLY; both absent → byte-identical backtest. `meta.validation` = DSR (primary, `n_trials=15`, Φ≥0.95) + PBO (CSCV) + purged-embargo holdout (the ONE `in_sample=false` block). EFTS `_source` keys = `ciks`/`adsh`/`items`, NOT `entity_id`/`file_num`**
- **The IC-decay monitor (`decay_report.json`, #75 §3) is a MONITOR — NEVER vetoes / changes scores; `alert` stays suppressed until ≥12 monthly IC points/pillar (`preliminary`); the JSON is dataclass-emitted, NOT in the schema triple (only `Metadata.decay_report_url` is); cron-wired in `compute/main.py` under `QR_SKIP_DECAY_MONITOR`**
- **`edgar_form4` cache is in the SLOW-TEXT bundle (run-id key, always saves), NOT the fast bundle — precache-900 Phase A move (both workflows, lockstep) so midcap Form-4 persists; the fast bundle's exact quarter-key skips the save on a warm hit (Phase B v9→v10 bump at the flip — #485 took v9 — handles sp400 fundamentals/prices)**
- **`fundamentals_unavailable` is a DIRECT veto (#487, widened 2026-06-16) — fires on NO-USABLE-FUNDAMENTALS: `snap is None` (complete EDGAR ingest failure, OZK/PBF) OR a non-None snap with ALL 34 metrics null (`_snapshot_has_no_usable_fundamentals`, FDXF empty-snap case) → cautious + Top-5 suppress; FP rate structurally zero (input-absence) so annotate-before-veto does NOT bind (DQIC issue #18 governing precedent); defense layer stays 34 (domain widening, no new flag). Distinct from `data_quality_input_corruption` (requires a PRESENT field internally inconsistent — never fires when all null) — partition is no-usable-fundamentals vs present-but-corrupt, `test_D3` locks it**
- **`index_membership` (singular, sp500/sp400 partition — MidcapChip + survivorship-ledger verifier depend on it) vs `index_memberships` (plural list — all indices incl. dow30/ndx/russell1000) — never consolidate the two; the ledger verifier reads the SINGULAR field**
- **`russell1000` in `index_memberships` is a market-cap PROXY, NOT a fetched FTSE list — every S&P 900 constituent qualifies (sp400 floor > Russell cutoff), so the RUI tab ≈ All-stocks by design; RUT/RUA stay SOON (need small-cap ingest)**

## Phase status

Current schema **`0.10.23-phase8pilot`** on `main` (#493, 2026-06-16 — additive `index_memberships: list[str]` on `StockSummary`/`StockDetail` for Dow 30 / NDX 100 overlap tabs + Wikipedia sources + DJI/NDX frontend tabs; `index_membership` (singular) UNCHANGED; defense layer 34. Prior #487, 2026-06-15 —
OZK/PBF flip-blocker: `fundamentals_unavailable` direct veto (`snap is
None` → cautious + Top-5 suppress) + `Metadata.fundamentals_unavailable_count`
Rule-18 counter + PBF EDGAR-identity ingest fix; defense layer 33→34.
Prior #482 — S&P 900 pilot 3a: additive `index_membership: str = "sp500"` on
`StockSummary`/`StockDetail` + a `compute/main.py` universe-load seam
that ranks all ~903 names on `QR_UNIVERSE=sp900`. **The scheduled cron now defaults to `sp900`** (precache-900 Phase B flip, 2026-06-16 — all gates cleared: sp900 validation run #107 PASSED pre-registered defense bands, methodology RATIFIED PROCEED-WITH-DOC, FDXF empty-snap fix merged #491). Lineage: 0.10.18 #456 RATIFY-B dual-class → 0.10.19/0.10.21
#479/#482 phase-8 pilot → 0.10.20 #477 IC-decay; full table SKILL.md
§schema-version). The AI-pick home now sizes its own basket
(adaptive rule, composite ≥ 65 / floor 5 / no cap (uncapped 2026-06-11) — see §Gotchas; gates
A1/A2/A2-S/B/C tracked on issue #130). The technical
pillar is an honest 4-metric mean after the #441 MAD close-out
(`0.10.17`, RATIFY-REMOVE) — **no 5th technical input without a fresh
pre-registration**. Defense layer **34 declared boolean flags** (8
active vetoes incl. `fundamentals_unavailable` #487 + 26 annotates +
reserved; ~27 emit; `USE_SECTOR_COE = True`) + 5 numerical guards + `manipulation_index` rollup. Gate (a)
verdict (#453): **the veto layer does NOT rescue returns**
(drawdown-year protection only; bite is 97% `sloan_accruals_top_decile`
on structural compounders — disposition routed to issue #454 for the Q3
2026-08-19 cohort audit). Latest release tag
[**`v1.4.0-phase4.6`**](https://github.com/dackclup/quantrank/releases/tag/v1.4.0-phase4.6)
(2026-05-27) — Phase 4.6 honest re-validation harness.

Full merged-PR log: [`PHASE_STATUS.md`](PHASE_STATUS.md) (canonical) · [`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md) (per-PR) · [`docs/PHASE_STATUS_ARCHIVE.md`](docs/PHASE_STATUS_ARCHIVE.md) (drained prose).

**In flight** (not yet merged on `main`): _Nothing currently in flight._ Merged
since last Mode C: **#485** (fix+test: APA `OilAndGasRevenue` #385 +
cache-v8→v9 + form4 retry #207 + 83 tests; closed #261 CLOSE-AS-CORRECT)
· **#486** (precache-900 Phase A — `edgar_form4` fast→slow-text +
`universe` dispatch input) · **#487** (`fundamentals_unavailable` veto,
schema `0.10.22`, defense 34) · **#488** (Mode C bump) · **#492** (precache-900 Phase B — cache-v10 fast-bundle + cron-default flip sp500→sp900) · **#493** (multi-index membership `0.10.23` — `index_memberships: list[str]`, Dow 30 / NDX 100 DJI/NDX tabs) · **#494** (Russell 1000 RUI overlap tab — market-cap proxy appends `"russell1000"`, NO schema bump). precache-900 Phase B (#492) + multi-index membership (#493) + Russell 1000 (#494) **MERGED 2026-06-16/17**; the gated sequence is COMPLETE — the weekday cron ranks S&P 900 by default and the first post-#494 cron tagged russell1000/dow30/ndx live (russell1000 900/902). Next: ≥ 2 green sp900 crons confirm the firing-rates hold, then frontend PR 4 (midcap badge). Detail: PHASE_STATUS_INFLIGHT.md.

**Next deliverables** (re-scoped 2026-06-11, ordered by decision-value;
prior items 1-2 — 7.0c gate (a) + issue #441 — are DONE, see
PHASE_STATUS.md):
- **1 · Data-integrity hardening sprint** (~1-2w) — the share-count /
  extraction corruption cluster (#248 V ~4× no-veto · #374 warm-cache
  bypass · #376 · #379 · #375 · #247/#289 NVR) — **Phase 5 entry gate
  (b)**. Closed by #485: #385 · #261 (CLOSE-AS-CORRECT via #456).
- **2 · Phase 4.5e PR 5 — cluster weight promotion 5.0 → 7.0** —
  UNBLOCKED (#287 PR B merged as #431); needs ≥ 1 cron's
  `form4_rule10b5_one_excluded_count` confirming the Aboody et al. 2010
  §3.2 −30..−45% band ahead of the Q3 2026-08-19 cohort audit.
- **3 · v1.1.0-phase4 tag — RE-GATED** — gate = OSAP 4h.1 (#113) + the
  4j.2 Qlib blend decision on ≥ 1 real cron of `Metadata.alpha158_*` IC
  evidence (PBO ≤ 0.5 + DSR > 0); 4k.1 IPCA (#122) additive,
  non-blocking; JKP 4i.1 dropped from the hard gate (license #115).
- **4 · Phase 5 — ML meta-learner** (~10-12w; the #75 IC-decay writer
  now ships observability-first (this PR) — Phase 5's walk-forward
  monthly-IC panel is what makes its `alert` meaningful) — gated on item
  1 + the 7.0c composite-signal follow-through + a Supabase
  client-wiring pre-PR (§Connectors). Entry gates: WORKFLOW.md §Phase 5.
- **5 · Stock-attribute tiles (Dividend + Security-type)** —
  display-only, parallel-safe; full spec: PHASE_STATUS.md §Next item 5.
- Phase 6 = TEXT-ONLY (→ 6.1) · Phase 7 remainder = **7.1** (gated on
  the 7.0c baseline + a longer fit window) · Phase 8 = staged S&P 900
  pilot — **3a integration slice merged 2026-06-15 (#482)** ·
  **precache-900 Phase A merged (#486)**; #249 pre-cache DONE (#468),
  #467 scout done; **precache-900 Phase B merged (#492, 2026-06-16 — cron now defaults `sp900`)**; next = ≥ 2 green sp900 crons → frontend PR 4 (midcap badge). Detail in WORKFLOW.md.

See [`PHASE_STATUS.md`](PHASE_STATUS.md) for the canonical
chronological tracker.

## Agent skills

Per-repo config for the vendored mattpocock skills (`to-issues`,
`to-prd`): **issue tracker** = GitHub Issues via the GitHub MCP server
(`gh` CLI absent in the remote env) —
[`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md);
**domain docs** = QuantRank's CONTEXT.md analog is multi-file
(CLAUDE.md + docs/METHODOLOGY.md + SKILL.md + WORKFLOW.md) with
`PHASE_STATUS_INFLIGHT.md` as the ADR analog —
[`docs/agents/domain.md`](docs/agents/domain.md). **Triage labels**
intentionally NOT scaffolded (upstream `triage` skill not vendored;
re-run `/mattpocock-setup-harness` if a future sync adds it).

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
