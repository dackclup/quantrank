# CLAUDE.md

QuantRank is a static-site US-equity ranking tool. Python compute layer
generates JSON; a Next.js static site renders it. Currently ranks the
S&P 1500 (~1500 names: S&P 500 large-caps + S&P 400 mid-caps + S&P 600
small-caps; `sp900`-only or `sp500`-only via manual dispatch). See
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
  S&P 400 + S&P 600 constituents scraped from Wikipedia (`QR_UNIVERSE=sp1500`
  cron default since Slice 7 flip 2026-06-20; `sp900`/`sp500`-only via manual
  dispatch)

## Layout

| Path | Purpose |
|---|---|
| `compute/ingest/` | SEC EDGAR + yfinance fetchers with on-disk caches |
| `compute/scoring/` | 8-pillar composite + risk overlay (7 active vetoes after Phase 4.5a) |
| `compute/valuation/` | 6-method fair-price ensemble + Tier-1 defenses |
| `compute/output/` | Pydantic schemas + JSON writers + schema-snapshot guard |
| `compute/warehouse/` | Per-run PIT research warehouse: `flatten` (Pydantic→row) + `writer` (Parquet snapshot + run manifest + filing-index partition) + `flag_registry` + `warehouse_schema_check` drift guard + `filing_index` (SEC filing pointer index — Slice 1, issue #579; 10-K/10-Q/8-K accession rows; no cron wiring yet). Writes `data/warehouse/`; observability-first (write-only, no read path) |
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

## Architecture & data flow

QuantRank is **two layers joined by a JSON contract**. There is no
server, no database, and no API at runtime — the Python layer runs
once a weekday in CI, writes static JSON, and the Next.js layer is a
static export (`next build` → HTML/JS) that reads that JSON at build
time. Everything the user sees was computed hours earlier by the cron.

```
SEC EDGAR ─┐
yfinance  ─┤→ compute/  ──writes──>  frontend/public/data/*.json  ──read at build──>  Next.js static export  ──>  Vercel CDN
Wikipedia ─┘   (Python)              (the JSON contract)                              (HTML/JS, no runtime)
```

### The compute pipeline (`compute/main.py::run_weekly_compute`)

One orchestrator runs ~12 numbered steps (the main steps 1-9 plus
sub-steps 3b · 4b · 5b/5c · 6b) over the full universe (~900 tickers),
with a couple of unnumbered blocks interleaved (the Form-4 loop, the
sp900 cohort-size recompute). Steps that hit the network are
parallelized across `EDGAR_MAX_WORKERS`; every external call site
degrades gracefully (try/except → `None`, never blocks the cron — see
the `portable-graceful-degradation-try-except` skill).

| Step | What it does | Key modules |
|---|---|---|
| 1 | Prices (10y daily OHLCV) in parallel | `ingest/prices.py` (yfinance) |
| 2 | Fundamentals snapshot (XBRL facts) in parallel | `ingest/fundamentals.py` (edgartools) |
| 3 | Annual history in parallel (feeds growth CAGRs) | `ingest/fundamentals.py` |
| — | (unnumbered) Form-4 insider-transaction fetch loop | `scoring/form4_*.py` |
| 3b | **Post-split share-lag correction** (Tier-1 CORRECT or Tier-2 veto, #499) | `ingest/splits.py` · `scoring/risk_overlay.py` |
| 4 | Assemble `TickerInputs`, compute the 8 pillars | `scoring/pillars.py` |
| 4b | Tier-2 event defenses (8-K going-concern / non-reliance / auditor-change) fetched in parallel | `scoring/tier2.py` + siblings |
| 5 | Composite score + risk-overlay flags (Beneish / Dechow-F computed here) | `scoring/composite.py` · `scoring/risk_overlay.py` · `scoring/beneish.py` · `scoring/dechow_f.py` |
| 5b/5c | Cross-sectional inputs (`main.py` local helpers) + per-sector pillar medians for the ensemble & stock-detail baselines | `compute/main.py` · `scoring/composite.py` |
| 6 / 6b | Assemble + sort the ranking DataFrame (6); inject `stale_filing_hard` (6b) | `scoring/composite.py` · `valuation/applicability.py` |
| 7 | **Top-5 rotation** — flagged stocks keep their rank but lose `entered_top5`; next clean stock inherits it | `scoring/composite.py` (Rule 16) |
| 8 | Per-ticker loop: 6-method fair-price ensemble + price-history series + per-stock JSON write | `valuation/ensemble.py` · `output/writer.py` |
| 9 | Sanity smoke test (cross-sectional Spearman IC) | `scoring/sanity.py` |
| — | (unnumbered, `sp900` only) post-scoring cohort-size recompute | `compute/main.py` |

Interleaved are the **observability-first** factor-research surfaces
(OSAP Alpha replication + PBO/DSR gate, Qlib Alpha158, IPCA) — these
emit diagnostic `Metadata` fields but, per Rule 18, do **not** drive
production scoring until an accounting-equation verification clears on
≥ 1 real cron.

### Scoring model (the 8-pillar composite + defense layer)

- **8 pillars** (`scoring/pillars.py`): value · quality · profitability ·
  growth · health · momentum · technical (an honest 4-metric mean
  since #441) · risk. Each is normalized cross-sectionally to 0-100,
  then weighted into the **composite** (`scoring/composite.py`).
- **Defense layer** (`scoring/risk_overlay.py` + `manipulation_index.py`):
  **36 declared boolean flags** (9 active vetoes + 27 annotates/reserved
  incl. `low_liquidity` #527; ~28 emit) + 5 numerical guards. A **veto** marks a stock `cautious`
  and suppresses its Top-5 badge; an **annotate** is informational only
  and never changes rank. New flags ship `annotate`-first
  (`portable-annotate-before-veto`); vetoes are added only after a cron
  of calibration. Academic anchors per flag live in `docs/METHODOLOGY.md`.

### Valuation (`compute/valuation/`)

A **6-method fair-price ensemble** — the `METHOD_NAMES` tuple in
`ensemble.py`: `graham` · `multiples_pe` · `multiples_pb` ·
`multiples_ev_ebitda` · `rim` · `dcf` — reduced to a `median` +
margin-of-safety `mos_pct`. (The three `multiples_*` methods use
sector-peer medians for their comparable; `tangible_book` is NOT an
ensemble method — it's a Tier-1 defense input feeding the
`goodwill_heavy` annotate + the per-method `tangible_book_value_per_share`
parameter.) `applicability.py` excludes methods that don't fit a
sector; Tier-1 defenses null out fair-price on corrupt inputs rather
than print a garbage number.

### The output contract (`compute/output/`)

Three JSON shapes land in `frontend/public/data/`:
`metadata.json` (run-level: schema version, universe, coverage %,
latency, all the Rule-18 diagnostic counters) · `rankings.json` (the
full ordered table) · `stocks/<TICKER>.json` (per-stock detail). The
Pydantic models in `schemas.py` are the source of truth; `writer.py`
writes atomically and prunes orphan stock files for de-listed/renamed
tickers. **Schema triple lockstep:** `schemas.py` ↔
`frontend/lib/types.ts` ↔ `frontend/lib/schema-snapshot.json` move
together, enforced by a CI guard (`schema_check`).

### Frontend rendering (`frontend/`)

Next.js 14 App Router, **static export only**. `frontend/lib/data.ts`
resolves the JSON at **build time** — `rankings.json` + `metadata.json`
via static `import`, per-stock + backtest files via `fs` inside Server
Components — so there is no client-side fetch and no `fs` access from a
`'use client'` component. The **home page IS the AI-pick portfolio**
(`getAiPickData()` fs-read; the basket self-sizes when `nav.adaptive`
is present). Routes: `/` (home/AI-pick), `/stock/[ticker]` (one static
page per ranked stock). Design tokens + component family live in
`frontend/lib/visual.ts` + `docs/design.md` (LedgerCraft design
system); consult the `frontend-design-system` skill before adding any
new UI surface. The frontend carries TWO cookieless Vercel-edge beacons in
`app/layout.tsx` — **Web Analytics** (`<Analytics />`, PR #517, page views)
+ **Speed Insights** (`<SpeedInsights />`, Core Web Vitals); the former
"no analytics in v1.0" pledge was lifted by explicit owner decision.
Posture detail: [`AGENTS.md`](AGENTS.md) §Security considerations.

### CI cadence (`.github/workflows/`)

- **`compute-rankings.yml`** — weekday cron (Mon-Fri 22:00 UTC), the
  `trading-day-gate` skips weekends + NYSE holidays. Runs the full
  `compute.main`, folds a warm PIT-backtest refresh, commits the JSON.
  Universe defaults to `sp1500` (Slice 7 flip 2026-06-20; manual `sp900`/`sp500` via dispatch).
- **`precache-edgar.yml`** — Saturday 08:00 UTC off-cycle EDGAR cache
  warmer (outputs discarded, caches saved).
- **PR checks** — `Python (lint + test)` (`ruff` + offline pytest) +
  `Frontend (build)` (`tsc --noEmit` + `next build`) + Vercel preview.

The EDGAR cache (`compute/cache/`, **gitignored**) is split into two
`actions/cache` bundles — a fast quarter-keyed bundle and a slow-text
run-id-keyed bundle — and has several non-obvious freshness invariants
(frozen-fast-cache, last-bar-date price recency, jittered 8-K TTL).
These are exactly the kind of trap catalogued in §Gotchas /
`docs/GOTCHAS.md` — read the relevant entry before touching ingest.

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
| Warehouse backfill (manual, Slice 2) | `python -m scripts.backfill_warehouse` — or the `backfill-warehouse.yml` `workflow_dispatch` (writes PIT `row_provenance="pit_replay"` rows to the GITIGNORED `data/warehouse/backfill/`, uploaded as a CI artifact — NEVER committed; SP500-only history; forward-only flags NULL; `IN_START`/`IN_END` shell-safe proxies) |
| Filing-index backfill (manual, Slice 1) | `python -m scripts.backfill_filing_index` (`QR_SKIP_FILING_INDEX=1` opt-out; requires `EDGAR_USER_AGENT`; writes `data/warehouse/filing_index/year=/run_date=/part-0.parquet`, **committed** alongside snapshots — NOT a CI artifact; ~1500 submissions-JSON round-trips, measure cost before cron wiring; issue #579) |
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
| **Supabase** | ⏸ toggle OFF (user discretion) | reserved for Phase 5+ — re-enable with the Phase 5 client-wiring pre-PR |
| **Sentry** | ⏸ toggle OFF (user discretion) | planned post-deploy monitor; re-enable when the `@sentry/nextjs` wiring PR lands |
| Gmail · Google Drive | ⏸ toggle OFF (user discretion) | rarely used; re-enable per-task for cross-tool comms / doc backup |

If `ToolSearch query="<name>"` returns no matches, the session
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
- **Doc layout (token-budget control RETIRED 2026-06-19).** The former
  "CLAUDE.md is an INDEX, not an encyclopedia" discipline no longer
  binds — there is no length cap on CLAUDE.md and no requirement to
  keep §Gotchas a one-line index. The split files
  ([`docs/GOTCHAS.md`](docs/GOTCHAS.md) ·
  [`PHASE_STATUS.md`](PHASE_STATUS.md) ·
  [`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md) ·
  [`docs/PHASE_STATUS_ARCHIVE.md`](docs/PHASE_STATUS_ARCHIVE.md))
  remain as the canonical long-form trackers and stay useful for
  organization, but inlining fuller detail here is now allowed. The
  CLAUDE.md + AGENTS.md lockstep (ship both with every PR) is
  unaffected — that's correctness, not token budget.
- **Thai sessions: Thai for the human, English for the machine
  (language-split, token-cost rationale RETIRED 2026-06-19).** When the
  user works in Thai, reply in Thai but keep machine-facing artifacts in
  English (code · comments · commit messages · PR bodies · log lines ·
  sub-agent prompts) for tooling / review consistency. This is now a
  practical convention, not a token-saving mandate.

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
| "ก่อน push" / "ready to push" / "open PR" / "mark ready" / "ตรวจก่อน push" — OR explicit "full review" / "deep review" / diff > 200 lines on `compute/scoring/` | `quantrank-reviewer` (opus) + `phase-coordinator` Mode B, plus conditional sonnet re-batch (`schema-sentinel` / `defense-layer-auditor` / `frontend-design-reviewer` / `docs-reviewer` / `security-reviewer` / `test-engineer`, dedup-skipped). **The opus review fires at this gate only — NOT on every push / edit set** (narrowed 2026-06-11) |
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

Invariant index — **full detail in [`docs/GOTCHAS.md`](docs/GOTCHAS.md)**.
Open that file before touching the file/area a gotcha names. The one-line-per-entry
format is now a convenience, not a hard cap (token-budget control retired 2026-06-19) —
inline fuller detail here when it aids the reader.

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
- **`fair_price.median_trimmed` / `methods_excluded_from_median` are SHADOW diagnostics (#177 obs-first, 0.10.24) — live `median`/`mos_pct` STILL use the untrimmed median; behavioral flip DEFERRED to Q3 2026-08-19 (Path C #497) via a forward-OOS shadow record (V55.1 condition-2 substituted for a synthetic backfill holdout, +U9 charge `BASKET_RULE_N_TRIALS` 15→16) — NOT a silent relaxation**
- **`prices.py` cache freshness is LAST-BAR-DATE, not file-mtime (#498) — GHA `actions/cache` restore resets mtime every run so the old `age_hours < PRICES_CACHE_MAX_AGE_HOURS` TTL was DEAD (same class as #471 frozen-fast-cache); `PRICES_CACHE_MAX_STALE_DAYS=7` forces a refetch when the cached frame's last bar is > 7 calendar days old, regardless of mtime. (Distinct from post-split share lag — that's a FUNDAMENTALS `shares_outstanding` bug, not prices)**
- **`post_split_share_lag` defense (#499): EDGAR `shares_outstanding` lags a stock split until the next 10-Q/10-K → pre-split shares × post-split price corrupts P/E / market_cap (KLAC rank-2 P/E 6.68 vs real ~66.8). HYBRID: Tier-1 CORRECT (split ≤100d / ratio ≥2× / yf-ratio-match ±10% → `shares_outstanding × ratio` at `main.py` Step 3b, raw kept in `shares_outstanding_pre_split_raw`) else Tier-2 VETO `post_split_share_lag_unreconciled` (cautious + null fair-price). Runs BEFORE DQIC. New `compute/ingest/splits.py` yfinance `.splits` fetcher (`POST_SPLIT_WINDOW_DAYS=100`/`MIN_RATIO=2.0`/`RATIO_TOLERANCE=0.10`)**
- **`_yf_info_fetch` is a 4-TUPLE since #512** — `cross_source.py:_yf_info_fetch` returns `(market_cap, shares_outstanding, dividend_yield_pct, payout_ratio)`; callers that unpacked a 2-tuple before #512 must update to 4 (both existing callers `fetch_yfinance_market_cap` + `fetch_yfinance_shares_outstanding` updated). Extend the tuple + update callers when adding new `yf.info` fields — don't re-collapse to 2.
- **`dividend_yield_pct` is PERCENT, `payout_ratio` is a 0-1 fraction (#512; ×100 double-scaling fix #533)** — yfinance `.info["dividendYield"]` now returns PERCENT directly (e.g. `2.67` = 2.67%). It was a fraction pre-2025, so the original #512 code multiplied by 100 — after yfinance's format change that over-scaled the value 100× (KO showed `267.0`, AAPL `36.0`). #533 removes the `×100` in `_yf_info_fetch` (assigns `float(dy_val)` as-is) and adds a format-reversion guard: any `dividend_yield_pct > 100.0` is discarded to `None` (logs a warning) so a future yfinance revert-to-fraction surfaces as missing data, never a 100× inflated number. `pays_dividend = True iff dividend_yield_pct > 0` (tri-state, `None` when absent). `fetch_yfinance_dividend` is a pure cache-read off the warm `yfinance_info` cache (zero new round-trips). The `HeroAttributeTiles` "Dividend" tile reads the field LIVE since #549 (UI PR-2; tile shows `"2.67%"` payer / `"None"` non-payer / `"—"` unavailable via `formatDividendYield`) — wired after cron #121 confirmed `Metadata.dividend_coverage_pct` populates with CORRECTED values (observability-before-wiring, `exchange_coverage_pct` precedent).
- **`security_type` is a display-only label from yfinance `fast_info.quote_type` (#541 PR-1, obs-first)** — `StockDetail.security_type: str \| None` maps yfinance quote-type codes via `_QUOTE_TYPE_LABEL` in `cross_source.py` (`EQUITY`→`"Common stock"`, `ETF`→`"ETF"`, `MUTUALFUND`→`"Fund"`, …; unknown codes pass through verbatim, forward-safe like the exchange-code map). `fetch_yfinance_security_type` is a pure cache-read off the warm `yfinance_info` cache (zero new round-trips); `_yf_fast_exchange` widened to a 2-tuple `(exchange_code, quote_type)` — update the single caller `fetch_yfinance_exchange` if you touch it. Descriptive metadata, NOT a scoring/veto input. **ADR detection is a `TODO(#541 PR-1b)`** — yfinance returns `EQUITY` for most ADRs; the SEC override (`dei:DocumentType == "20-F"` OR EDGAR submissions-JSON `entityType` = foreign private issuer) is deferred because `sec_health.py` doesn't cache the submissions JSON (would need a new round-trip). The `HeroAttributeTiles` "Type" tile stays the "Coming soon" placeholder until a UI PR-2 — gated on ≥ 1 sp1500 cron confirming `Metadata.security_type_coverage_pct` populates (same Rule-18 gate the dividend tile cleared).
- **`low_liquidity` is an ANNOTATE, not a veto (#527, S&P 1500 Slice 4)** — fires when trailing-30d mean dollar volume (`StockDetail.average_dollar_volume`, from `compute_average_dollar_volume()` in `prices.py`) < `ADV_FLOOR_USD` ($5M, `ADV_LOOKBACK_DAYS=30`; Amihud 2002 illiquidity family). RANK-NEUTRAL: emitted into `valuation_warnings`, NOT `risk_flags` — no `cautious`, no Top-5 suppression, no fair-price null (`portable-annotate-before-veto` + Rule 18). `Metadata.low_liquidity_annotate_count` is the Rule-18 counter. **Dormant (~0 fires) on sp900** (every S&P 900 name clears $5M ADV); lights up only on sp600 small-caps. Veto promotion deferred pending ≥ 1 cron of firing-rate data + methodology ratification (RATIFY-SHADOW).
- **`smallcap_*` Metadata fields were a PROBE in Slice 2 (#519); sp600 is NOW RANKED since Slice 7 (#534, 2026-06-21)** — `_run_smallcap_coverage_probe` still runs and emits sp600 `smallcap_fundamentals_coverage_pct` / `smallcap_null_rate_pct` / `smallcap_cik_resolution_pct` for diagnostic coverage, but sp600 tickers are NO LONGER filtered from the scored frame: the cron ranks the full ~1504-name S&P 1500 and `Metadata.universe` emits `"SP1500"` (no longer `"SP1500-probe"`). `derive_index_memberships` russell1000-proxy sp600 guard retained. Cron default is now `sp1500` (since #534); `sp900`/`sp500` via manual dispatch.
- **`cache-v11-fast` is the current fast-bundle key (#520, S&P 1500 Slice 5)** — `cache-v10-fast`→`cache-v11-fast` cold-seed bump across 4 workflows (compute-rankings · precache-edgar · pre-merge-prod-sim · backfill-portfolio) so sp600/sp1500 fundamentals/prices warm correctly past the FROZEN-IMMUTABLE-within-a-quarter save-skip (same mechanism as the v9→v10 precache-900 Phase B bump #492). Adds sp600/sp1500 parquet cache paths + the `sp1500` `workflow_dispatch` option; cron default was UNCHANGED at sp900 at #520 time, then flipped to `sp1500` by #534 (Slice 7, 2026-06-21); slow-text bundle key unchanged.
- **`EntityFacts.get_fact(tag)` sort-key trap — 8-K / S-type event facts can beat 10-K consolidated balance values** — full detail in `docs/GOTCHAS.md`; do NOT revert `_try_balance_tags` to the bare `get_fact()` call
- **Research warehouse is WRITE-ONLY + cron-committed, NOT the schema triple (Slice 1 + 2)** — `compute/warehouse/` writes a per-run PIT Parquet snapshot (1 row/ticker, **128 cols** after the Slice-2 `replay_completeness` add) to `data/warehouse/snapshots/year=/run_date=/` + a `_manifest.parquet`; the cron's `git add data/warehouse/` commits forward snapshots (gitignore-whitelisted). It is an OFFLINE research store — the static site never reads it; `WAREHOUSE_DIR` is repo-root `data/warehouse/`, NEVER `frontend/public/data/` (must not ship in the Vercel bundle). Guarded by its OWN `compute/warehouse/warehouse_schema_check.py` (introspects models + `flag_registry.py`), NOT the Pydantic↔TS↔snapshot triple. `QR_SKIP_WAREHOUSE=1` skips the Step-13.5 write (mirrors `QR_SKIP_DECAY_MONITOR`); try/except makes it non-fatal regardless so it NEVER blocks the cron. Adding a new `risk_flags`/`valuation_warnings` literal? also add it to `flag_registry.py` + regen the manifest (`--update`) or there's no `flag_*`/`warn_*` column for it (raw value still survives in `*_json`). **Slice 2 backfill** (`scripts/backfill_warehouse.py` + `backfill-warehouse.yml`): replays ~2016→today weekly with `row_provenance="pit_replay"` to the GITIGNORED `data/warehouse/backfill/` (CI/release ARTIFACT, NEVER committed — blanket `*.parquet` ignores it, do NOT whitelist). HONEST LIMITS: SP500-only before sp900/sp1500 go-live (no historical mid/small-cap ledger); the 11 `FORWARD_ONLY_FLAGS` (8-K/Form-4/tier2/cross-source/post-split/low_liquidity/OSAP) are written **NULL not False** in replay rows so ML never reads an unconfirmed flag's absence as a confirmed False; `replay_completeness` ∈ [0,1] (None on live rows) is the diagnostic. `flatten_stock`'s live-path default is byte-identical — `null_flags`/`row_provenance` are keyword-only opt-ins the backfill uses. **Filing pointer index** (Slice 1, issue #579, `compute/warehouse/filing_index.py`): the `.gitignore` also whitelists `!data/warehouse/filing_index/**/*.parquet` (forward partitions committed alongside snapshots); it is guarded by `warehouse_schema_check.py`'s `check_filing_index_schema` against its OWN baseline `data/warehouse/filing_index_schema.json` (NOT the Pydantic↔TS↔snapshot triple). Write-only + NOT yet wired into the weekday cron — manual `scripts/backfill_filing_index.py` only (`QR_SKIP_FILING_INDEX=1` opt-out) until the ~1500-ticker EDGAR enumeration cost is measured.
- **`bonferroni_shadow_*` Metadata fields are SHADOW-only (#564, Slice 8)** — `compute/scoring/bonferroni_shadow.py` reads `beneish_m_scores` and emits 3 `int | None` counters: `bonferroni_shadow_live_fire_count` (M > −2.22, matches the `beneish_high` annotate count) · `bonferroni_shadow_provisional_fire_count` (M > −1.94, always ⊆ live) · `bonferroni_shadow_flip_count` (live-but-not-provisional — the false-positives a tighter threshold would suppress). `m = valid_count` (non-None M-scores; `α* = 0.05/valid_count`, ZeroDivisionError-guarded) — NOT hardcoded 1500. The provisional threshold −1.94 is an ARBITRARY PLACEHOLDER between live −2.22 and the soft-veto −1.78; real re-derivation is DEFERRED to the empirical sp1500 M-score SD after ≥1 real cron. NEVER feeds scoring, vetoes, or the composite — observability-only (Rule 18); defense layer UNCHANGED at 36.
- **`security_type` is display-only, NO UI wiring yet (#565, Slice 8)** — `StockDetail.security_type` (from yfinance `fast_info.quote_type`, `_QUOTE_TYPE_LABEL` map, unknown codes pass through verbatim) + `Metadata.security_type_coverage_pct` coverage canary. obs-first Rule 18: the `HeroAttributeTiles` "Type" tile stays 'Coming soon' until a UI PR-2 (issue #541 follow-up) gated on ≥1 sp1500 cron confirming the canary. `fetch_yfinance_security_type` is a pure cache-read off the warm `yfinance_info` cache; ADR detection is `TODO(#541 PR-1b)`.

## Phase status

Current schema **`0.10.31-phase8pilot`** on `main` (#565 squash `2c9dc1371`, merged 2026-06-22 — Security-type (Type) HeroAttributeTile signal ingest PR-1 (issue #541): 2 new schema fields (`StockDetail.security_type: str | None` from yfinance `fast_info.quote_type` + `Metadata.security_type_coverage_pct` coverage canary); obs-first Rule 18, NO UI wiring (the Type tile stays 'Coming soon' until a UI PR-2 gated on ≥1 sp1500 cron confirming the canary), display-only — rankings/scores/flags BYTE-IDENTICAL; defense UNCHANGED at 36; +17 tests). Prior **`0.10.30-phase8pilot`** on `main` (#564 squash `62dbf4f89`, merged 2026-06-22 — Bonferroni multi-test shadow counter (Slice 8, issue #542): 3 new `Metadata.bonferroni_shadow_*` fields (all `int | None`); new `compute/scoring/bonferroni_shadow.py`; SHADOW/OBSERVABILITY-ONLY — live scores/rankings/flags BYTE-IDENTICAL; `m = valid_count` data-driven (NOT hardcoded 1500), provisional threshold −1.94 placeholder (re-derivation deferred to empirical sp1500 M-score SD); defense UNCHANGED at 36; 20 tests). Prior **`0.10.29-phase8pilot`** on `main` (#527 squash `2e45a33bf`, merged 2026-06-20 — S&P 1500 cutover Slice 4: `low_liquidity` ANNOTATE flag (<$5M trailing-30d ADV, Amihud 2002 illiquidity family; rank-neutral — emitted into `valuation_warnings`, NOT `risk_flags`) + `compute_average_dollar_volume()` in `prices.py` + `StockDetail.average_dollar_volume` + `Metadata.low_liquidity_annotate_count`; defense layer 35→36 (new annotate); rankings/scores/flags BYTE-IDENTICAL; dormant (~0 fires) on sp900, lights up on sp600; methodology-scientist RATIFY-SHADOW, veto promotion deferred). Prior **`0.10.28-phase8pilot`** on `main` (#519 squash `5e49dca0a`, merged 2026-06-20 — S&P 1500 cutover Slice 2: `sp1500` universe seam in `compute/main.py` + `_run_smallcap_coverage_probe`; 3 additive `Metadata` fields (`smallcap_fundamentals_coverage_pct` / `smallcap_null_rate_pct` / `smallcap_cik_resolution_pct`); sp600 is PROBE-ONLY (filtered from the scored frame, universe label `SP1500-probe`, NOT ranked yet); `derive_index_memberships` guards sp600 from the russell1000 proxy; cron stays sp900; defense layer UNCHANGED at 35; observability-first Rule 18). Prior **`0.10.27-phase8pilot`** on `main` (#512 squash `78fd608423`, merged 2026-06-20 — Dividend signal PR-1: observability-first display metadata; 3 new `StockDetail` fields (`dividend_yield_pct` PERCENT / `pays_dividend` / `payout_ratio` 0-1) + `Metadata.dividend_coverage_pct` coverage canary; `_yf_info_fetch` 2-tuple → 4-tuple + pure cache-read `fetch_yfinance_dividend`; rankings/scores/flags BYTE-IDENTICAL; defense layer UNCHANGED at 35; +25 tests). Prior **`0.10.26-phase8pilot`** on `main` (#501 squash `72ee8667d`, merged 2026-06-19 — cross-source share-count-corruption SHADOW observability PR-1: 4 new `Metadata.cross_source_corruption_*` fields, `grade_cross_source_corruption` + dual-ratio corroboration, MUTATES NOTHING — rankings byte-identical; defense layer UNCHANGED at 35). Prior **`0.10.25-phase8pilot`** on `main` (#499 squash `816cda0ea`, merged 2026-06-18 — `post_split_share_lag` HYBRID defense: Tier-1 CORRECT annotate + Tier-2 veto `post_split_share_lag_unreconciled` + folded leg-3 override (direct yfinance `sharesOutstanding`); `RawMetrics.shares_outstanding_pre_split_raw` + 3 `Metadata.*` post-split counters; defense 34→35; KLAC/CVNA/COKE rank correction next cron). Prior **`0.10.24-phase8pilot`** on `main` (#496/PR-A merged 2026-06-18 — additive `Metadata.median_trim_delta_count: int | None` + shadow `FairPriceEnsemble.median_trimmed`/`methods_excluded_from_median` (#177 trimmed-median diagnostic, observability-first Rule 18; live `median`/`mos_pct` byte-identical; 33 tickers ~3.8% would flip MoS sign; behavioral flip gated on ≥1 cron + data-scientist V55.1-gauntlet). Prior #493/#494, 2026-06-16/17 — additive `index_memberships: list[str]` on `StockSummary`/`StockDetail` for Dow 30 / NDX 100 overlap tabs + Wikipedia sources + DJI/NDX frontend tabs; `index_membership` (singular) UNCHANGED; defense layer 34. Prior #487, 2026-06-15 —
OZK/PBF flip-blocker: `fundamentals_unavailable` direct veto (`snap is
None` → cautious + Top-5 suppress) + `Metadata.fundamentals_unavailable_count`
Rule-18 counter + PBF EDGAR-identity ingest fix; defense layer 33→34.
Prior #482 — S&P 900 pilot 3a: additive `index_membership: str = "sp500"` on
`StockSummary`/`StockDetail` + a `compute/main.py` universe-load seam
that ranks all ~903 names on `QR_UNIVERSE=sp900`. **The scheduled cron now defaults to `sp1500`** (Slice 7 cron flip, 2026-06-21, #534 squash `8301b82cb` — ranks the full ~1504 names: ~503 sp500 + ~399 sp400 + ~602 sp600; `Metadata.universe` = `"SP1500"`; cohort-size recompute gate widened to `in ("sp900","sp1500")`; NO schema bump (stays 0.10.29); defense UNCHANGED at 36; cold ~174 min / warm extrapolated ~45 min (< 90); smallcap coverage 99.67% / null 0.33% / cik 100%; opus cohort-gate + security workflow review PASSED; prior `sp900` default since precache-900 Phase B flip 2026-06-16 #492 — that flip's gates cleared: sp900 validation run #107 PASSED pre-registered defense bands, methodology RATIFIED PROCEED-WITH-DOC, FDXF empty-snap fix merged #491). Lineage: 0.10.18 #456 RATIFY-B dual-class → 0.10.19/0.10.21
#479/#482 phase-8 pilot → 0.10.20 #477 IC-decay; full table SKILL.md
§schema-version). The AI-pick home now sizes its own basket
(adaptive rule, composite ≥ 65 / floor 5 / no cap (uncapped 2026-06-11) — see §Gotchas; gates
A1/A2/A2-S/B/C tracked on issue #130). The technical
pillar is an honest 4-metric mean after the #441 MAD close-out
(`0.10.17`, RATIFY-REMOVE) — **no 5th technical input without a fresh
pre-registration**. Defense layer **36 declared boolean flags** (9
active vetoes incl. `fundamentals_unavailable` #487 + `post_split_share_lag_unreconciled` #499 + 27 annotates incl.
the paired `post_split_share_lag` #499 + `low_liquidity` #527 + reserved; ~28 emit; `USE_SECTOR_COE = True`) + 5 numerical guards + `manipulation_index` rollup. Gate (a)
verdict (#453): **the veto layer does NOT rescue returns**
(drawdown-year protection only; bite is 97% `sloan_accruals_top_decile`
on structural compounders — disposition routed to issue #454 for the Q3
2026-08-19 cohort audit). Latest release tag
[**`v2.0.0-phase8`**](https://github.com/dackclup/quantrank/releases/tag/v2.0.0-phase8)
(published 2026-06-23 at `8c89a5af0`, "Set as latest") — the S&P 1500 universe
cutover release (502 → ~1504 production expansion; release PR #577). Prior
[**`v1.4.0-phase4.6`**](https://github.com/dackclup/quantrank/releases/tag/v1.4.0-phase4.6)
(2026-05-27 at `a820caee`) — Phase 4.6 honest re-validation harness.

Full merged-PR log: [`PHASE_STATUS.md`](PHASE_STATUS.md) (canonical) · [`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md) (per-PR) · [`docs/PHASE_STATUS_ARCHIVE.md`](docs/PHASE_STATUS_ARCHIVE.md) (drained prose).

**In flight** (not yet merged on `main`): **v2.0 release PR** (`claude/release-v2.0.0-phase8` — `pyproject` 1.4.0→2.0.0 + `docs/release-notes/v2.0.0-phase8.md` + this Mode C doc reconciliation; all Phase 8 WORKFLOW.md acceptance gates met; `release-captain` owns the `v2.0.0-phase8` tag — DRAFT, HOLD the tag until ≥1 green scheduled sp1500 cron). `low_liquidity` veto promotion (#544, KEEP-ANNOTATE for v2.0) + Bonferroni provisional-threshold re-derivation deferred post-v2.0. Merged
since last Mode C (#538 reconciled to 0.10.29 / Slice 7, 2026-06-21): **#565** (feat(compute): Security-type (Type) HeroAttributeTile ingest PR-1, issue #541 — `StockDetail.security_type` + `Metadata.security_type_coverage_pct`; schema `0.10.30`→**`0.10.31-phase8pilot`**; obs-first, NO UI wiring; rankings byte-identical; +17 tests — squash `2c9dc1371`) · **#564** (feat(compute): Bonferroni multi-test shadow counter, issue #542, Slice 8 — 3 new `Metadata.bonferroni_shadow_*` fields; `compute/scoring/bonferroni_shadow.py`; schema `0.10.29`→**`0.10.30-phase8pilot`**; SHADOW/OBSERVABILITY-ONLY; defense UNCHANGED at 36; 20 tests — squash `62dbf4f89`) · **#548** (feat(frontend): infinite-scroll the ~1500-row ranking table, Slice 8 §8.3 gate — squash `e0ea07dc1`) · **#549** (feat(frontend): wire HeroAttributeTiles Dividend tile to real data PR-2 — squash `a7fd57b18`) · **#539/#547/#570** (research warehouse Slices 1/2 + per-method `fp_*` dtype fix — squashes `b2e899159`/`bca926d9d`/`0b11f6415`) · **#555** (fix(ingest): XBRL balance-sheet tag selection — instant + 10-K/Q form filter; fixes HASI/LGIH/GPK — squash `100f0f549`) · **#554** (fix(ingest): payout_ratio >20→None format-reversion guard — squash `c38829362`) · **#553** (ci(compute): timeout-minutes 240→270 for S&P 1500 scale — squash `dbf59ed26`) · **#552** (fix(compute): drop free-text post-split valuation_warning + DQIC docstrings — squash `70b5f60fd`) · **#537** (feat(frontend): Sold rows in Current-picks table — squash `a1a0bbc49`) · **#533** (fix(ingest): dividend `×100` double-scaling removal + `>100` reversion guard — squash `3df2ba5f8`) · **#546** (docs: groom Next deliverables + scaffold Slice 8 issues) · **#556/#557/#559/#560/#575** (dependabot + CI Node 20→22 bumps). Prior batch (#538 reconciled to 0.10.29 / Slice 7): **#534** (ci(compute): S&P 1500 cutover Slice 7 — cron-default flip `sp900`→`sp1500`; `compute/main.py` lifts the Slice-2 probe-only sp600 filter → full ~1504 names ranked; `Metadata.universe` = `"SP1500"`; cohort-size recompute gate widened to `in ("sp900","sp1500")`; NO schema bump (stays `0.10.29-phase8pilot`); defense UNCHANGED at 36 — squash `8301b82cb`, merged 2026-06-21) · **#531** (S&P 1500 cutover Slice 6 — `SmallcapChip` + SML tab activation; frontend-only, NO schema bump) · **#527** (S&P 1500 cutover Slice 4 — `low_liquidity` ANNOTATE flag (<$5M trailing-30d ADV, Amihud 2002; rank-neutral — `valuation_warnings`, not `risk_flags`) + `compute_average_dollar_volume()` + `StockDetail.average_dollar_volume` + `Metadata.low_liquidity_annotate_count`; schema `0.10.29-phase8pilot`; defense 35→36 (new annotate); rankings/scores byte-identical; dormant on sp900, lights up on sp600; methodology RATIFY-SHADOW, veto promotion deferred — squash `2e45a33bf`) · **#528** (test(ingest): offline coverage for `universe.py` scrape parsing 80→93%; NO schema bump — squash `8be261fd8`) · **#525** (test(ingest): offline coverage for PIT parquet readers; NO schema bump — squash `c51ddd55e`) · **#520** (ci(precache): S&P 1500 cutover Slice 5 — `cache-v10-fast`→`cache-v11-fast` cold-seed bump across 4 workflows + `sp1500` `workflow_dispatch` option + sp600/sp1500 parquet cache paths; cron default UNCHANGED (stays sp900); NO schema bump — squash `b2bffde3e`) · **#519** (feat(compute): S&P 1500 cutover Slice 2 — `sp1500` universe seam + `_run_smallcap_coverage_probe`; 3 additive `Metadata.smallcap_*` fields; sp600 PROBE-ONLY (`SP1500-probe` label, NOT ranked); folded a WORKFLOW.md §8.6 Beneish Bonferroni sign-fix (−2.22→−2.50) + Slice 3 (Bonferroni shadow) DEFERRED to Slice-8 calibration; schema `0.10.28-phase8pilot`; defense UNCHANGED at 35 — squash `5e49dca0a`) · **#512** (Dividend signal PR-1 — 3 new `StockDetail` fields `dividend_yield_pct`/`pays_dividend`/`payout_ratio` + `Metadata.dividend_coverage_pct` coverage canary; `_yf_info_fetch` 2→4-tuple + `fetch_yfinance_dividend` cache-read; schema `0.10.27-phase8pilot`; rankings/scores/flags byte-identical; defense UNCHANGED at 35; +25 tests — squash `78fd608423`) · **#522** (feat(frontend): Vercel Speed Insights — Core Web Vitals beacon; frontend-only, NO schema bump — squash `a653d6df1`) · **#517** (feat(frontend): Vercel Web Analytics — page-view beacon; frontend-only, NO schema bump — squash `f39390eb3`) · **#515** (fix(test): weekend-robust R6 prices-recency boundary — squash `a766bd1eb`) · **#514** (feat(ingest): S&P 1500 cutover Slice 1 — S&P 600 fetcher + S&P 1500 universe loader scout; NO schema bump, no `main.py` wiring yet — squash `08a74c099`) · **#521** (chore(ui): design-kit alignment polish pass — frontend-only, NO schema bump — squash `92c69ce51`) · **#518** (test+tooling: pytest-cov coverage baseline 85% + P-low coverage tests — squash `7952c1dd1`) · **#513** (test+ci: expand vitest coverage + hermetic CI exact-pin + `npm ci`) · **#511** (test+ci: vitest runner + flagLabel contract test + `fundamentals_unavailable` label fix) · **#510** (docs: S&P 900 pilot milestone reconciliation) · **#509** (docs: cron #115 cross-source shadow read-out — VETO deferred Q3) · **#501** (cross-source share-count-corruption SHADOW observability PR-1; `grade_cross_source_corruption` + dual-ratio corroboration; 4 new `Metadata.cross_source_corruption_*` fields; MUTATES NOTHING, rankings byte-identical; schema `0.10.26-phase8pilot`; defense layer UNCHANGED at 35; PR-2 veto/correction wiring gated on yfinance `.splits` corroboration + methodology re-anchor Q3 2026-08-19 — squash `72ee8667d`) · **#499** (`post_split_share_lag` HYBRID defense — Tier-1 CORRECT annotate + Tier-2 veto `post_split_share_lag_unreconciled` + folded leg-3 override; new `compute/ingest/splits.py`; schema `0.10.25-phase8pilot`; defense 34→35; fixes KLAC rank-2 P/E 6.68→~66.8 — squash `816cda0ea`) · **#498** (fix(ingest): prices.py last-bar-date recency guard — `PRICES_CACHE_MAX_STALE_DAYS=7`, mtime-TTL dead on GHA) · **#497** (docs(methodology) Path C amendment: #177 flip DEFERRED Q3 + `BASKET_RULE_N_TRIALS` 15→16) · **#496/PR-A** (trimmed-median diagnostic #177, `0.10.24-phase8pilot` — shadow `median_trimmed`/`methods_excluded_from_median` + `Metadata.median_trim_delta_count`) · **#485** (fix+test: APA `OilAndGasRevenue` #385 +
cache-v8→v9 + form4 retry #207 + 83 tests; closed #261 CLOSE-AS-CORRECT)
· **#486** (precache-900 Phase A — `edgar_form4` fast→slow-text +
`universe` dispatch input) · **#487** (`fundamentals_unavailable` veto,
schema `0.10.22`, defense 34) · **#488** (Mode C bump) · **#492** (precache-900 Phase B — cache-v10 fast-bundle + cron-default flip sp500→sp900) · **#493** (multi-index membership `0.10.23` — `index_memberships: list[str]`, Dow 30 / NDX 100 DJI/NDX tabs) · **#494** (Russell 1000 RUI overlap tab — market-cap proxy appends `"russell1000"`, NO schema bump). precache-900 Phase B (#492) + multi-index membership (#493) + Russell 1000 (#494) **MERGED 2026-06-16/17**; the gated sequence is COMPLETE — the weekday cron ranks S&P 900 by default and the first post-#494 cron tagged russell1000/dow30/ndx live (russell1000 900/902). **S&P 900 pilot milestone COMPLETE 2026-06-19**: both remaining acceptance gates cleared — frontend PR 4 (midcap badge) shipped earlier as #490 (`MidcapChip` + per-index SPX/MID/ALL tabs, wired into RankingTable + StockListCard + stock-detail) and ≥ 2 green sp900 crons confirmed (3 scheduled crons 6/16 · 6/17 · 6/18 all green). Next universe step = **S&P 1500 cutover** (S&P 600 small-cap ingest) — Slices 1 (scout #514) / 2 (seam + smallcap probe #519) / 4 (`low_liquidity` ADV annotate #527) / 5 (precache `cache-v11-fast` cold-seed #520) **MERGED**; Slice 3 (Bonferroni shadow) DEFERRED to the Slice-8 calibration; the first manual `QR_UNIVERSE=sp1500` Compute Rankings run committed a `chore: update rankings` (label `SP1500-probe`) populating the `smallcap_*` coverage Metadata. **Slices 6 (SML tab #531) + 7 (cron flip #534) MERGED 2026-06-21 — the weekday cron now ranks the full S&P 1500 (~1504 names) by default; next = Slice 8 (v2.0, gated on ≥ 1-2 green sp1500 crons).** Detail: PHASE_STATUS_INFLIGHT.md.

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
  **Dividend PR-1 MERGED 2026-06-20 (#512)** — observability-first display
  metadata (`dividend_yield_pct` / `pays_dividend` / `payout_ratio` + coverage
  canary `Metadata.dividend_coverage_pct`; schema `0.10.27-phase8pilot`).
  **#533 fixed the `×100` double-scaling** (yfinance now returns percent
  directly) + a `>100` reversion guard. **7a COMPLETE — Dividend UI tile
  MERGED (#549, 2026-06-22)** reads live `dividend_yield_pct` (gate cleared:
  cron #121 confirmed corrected values + `dividend_coverage_pct`).
  **7b Security-type obs-first ingest PR-1 MERGED (#565, schema
  `0.10.31-phase8pilot`)** — `StockDetail.security_type` +
  `Metadata.security_type_coverage_pct`; the Type tile stays 'Coming soon'
  until a UI PR-2 (issue **#541** follow-up) gated on ≥ 1 sp1500 cron
  confirming the canary.
- Phase 6 = TEXT-ONLY (→ 6.1) · Phase 7 remainder = **7.1** (gated on
  the 7.0c baseline + a longer fit window) · Phase 8 = staged S&P 900
  pilot — **3a integration slice merged 2026-06-15 (#482)** ·
  **precache-900 Phase A merged (#486)**; #249 pre-cache DONE (#468),
  #467 scout done; **precache-900 Phase B merged (#492, 2026-06-16 — cron now defaults `sp900`)**; **S&P 900 pilot milestone COMPLETE 2026-06-19** — frontend PR 4 (midcap badge) shipped #490 + ≥ 2 green sp900 crons confirmed (3 scheduled crons 6/16-6/18). **S&P 1500 cutover — Slices 1/2/4/5/6/7 MERGED (#514/#519/#527/#520/#531/#534); Slice 3 (Bonferroni shadow) DEFERRED to Slice-8 calibration. The weekday cron now ranks the full S&P 1500 (~1504 names) by default since Slice 7 (#534, 2026-06-21).** **Slice 8 ALL ACCEPTANCE GATES MET 2026-06-22** — Bonferroni shadow #564 (schema `0.10.30`) · infinite-scroll table #548 (epic #545 §8.3 frontend gate) · Dividend tile #549 · Security-type ingest #565 (schema `0.10.31`) · research warehouse Slices 1/2 (#539/#547/#570) · data-integrity hardening (#552/#553/#554/#555) all MERGED. **`v2.0.0-phase8` tag PUBLISHED 2026-06-23** at `8c89a5af0` ("Set as latest"; release PR #577 + the green scheduled sp1500 cron it gated on — Section A-L 12/12, Bonferroni shadow counters live=86/prov=47/flip=39, defense 36). The S&P 1500 cutover epic is COMPLETE. Open deferred (post-v2.0): `low_liquidity` annotate→veto promotion (#544, KEEP-ANNOTATE for v2.0) + Bonferroni provisional-threshold re-derivation (#542, needs empirical sp1500 M-score SD). Detail in WORKFLOW.md.

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
