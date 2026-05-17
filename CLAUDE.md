# CLAUDE.md

QuantRank is a static-site US-equity ranking tool. Python compute layer
generates JSON; a Next.js static site renders it. Currently ranks the
S&P 500 (universe = 502 after one delisting). See
[`README.md`](README.md) for the user-facing pitch and
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) for the academic
backing.

## Stack

- **Python 3.11+** — pandas 2.2 · edgartools 2.30 · pydantic 2.6 ·
  tenacity 8.2 · BeautifulSoup 4 · lxml 5 · pytest 8 · ruff 0.4
- **Next.js 14.2** (App Router, static export) — React 18.3 ·
  TypeScript 5.4 · Tailwind 3.4 · Recharts 2.12
- **CI** — GitHub Actions; weekly `compute-rankings.yml` (cron Sun 22:00 UTC)
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
| `tests/` | pytest suite (831 offline + 17 `@network` gated) |
| `.claude/skills/` | 24 invocation-triggerable skills (7 QuantRank + 17 Anthropic vendored) plus phase planning docs |

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
| Section A-H verification | `python .claude/skills/verify-production-output/helper.py` |

Verification ladder before any push: `ruff check .` → `pytest -m "not
network"` → (if schemas touched) `schema_check` → (if frontend touched)
`tsc --noEmit` + `next build` → (if compute output committed)
`verify-production-output/helper.py`.

**After every `workflow_dispatch` turns green** (REQUIRED 2026-05-17):
run the existing Section A-H scan **AND** a Playwright spot-check
against the live Vercel deployment for any PR that lands a new UI
surface or schema bump. See
`.claude/skills/verify-production-output/SKILL.md` §"Live UI visual
spot-check (Section I)" for the 4-ticker matrix + sandbox / browser-
version caveats.

**Connector-aware first-line check** (post-2026-05-17): when MCP
connectors are loaded (see §Connectors), use `mcp__vercel__list_
deployments` → confirm `READY` → `get_runtime_logs` as the cheap
pre-Playwright pass. The Playwright matrix is still required for any
new UI surface, but Vercel MCP catches deploy / runtime failures
before paying the browser-launch cost.

## Connectors

Claude Code sessions for this project have these MCP connectors
enabled (managed in Claude app Settings → Connectors):

| Connector | Status | Use |
|---|---|---|
| **GitHub** | ✅ active | PRs, issues, releases, CI runs, file ops |
| **Vercel** | ✅ active (since 2026-05-17) | first-line deploy + runtime log check before Section I Playwright; `list_deployments` / `get_deployment` / `get_deployment_build_logs` / `get_runtime_logs` |
| **Supabase** | ✅ active (since 2026-05-17) | **reserved for Phase 5+** (user accounts, ML experiment log, insider event time-series); **not used by current code** — do not add a Supabase client to compute/ or frontend/ without an explicit PR |
| **Sentry** | ⚪ planned | post-deploy error monitor for 502 static routes; `@sentry/nextjs` SDK wiring is a separate PR (not yet filed) — connector is registered but no events flow yet |
| Gmail · Google Drive | ✅ active | rarely used in this project; available for cross-tool comms / doc backup |

New sessions surface connector tools as `mcp__<name>__*` after a
fresh start — if `ToolSearch query="vercel"` returns no matches, the
session was started before the connector was added; restart resolves
it. Other agent runtimes (Copilot / Cursor / Devin) don't have these
connectors — see `AGENTS.md` § "Claude-Code-specific tooling" for the
graceful-degradation note.

## Conventions

- **Pydantic and TypeScript schemas move together.** `compute/output/schemas.py`
  + `frontend/lib/types.ts` + `frontend/lib/schema-snapshot.json` are a
  triple. The schema-snapshot CI guard fails the build on drift. See
  `.claude/skills/schema-check/SKILL.md`.
- **Annotate-and-veto-Top-N** (SKILL.md Rule 16). Flagged stocks keep
  their composite rank but lose the `entered_top5` badge; the
  next-in-line clean stock inherits it. Never modify the composite
  score retroactively. See `.claude/skills/top5-rotation-audit/SKILL.md`.
- **EDGAR is rate-limited (10 req/s).** Use `EDGAR_MAX_WORKERS=5` and
  the tightened tenacity retry policy in `compute/ingest/fundamentals.py`.
  Off-cycle pre-cache jobs (Phase 4) for batch warming.
- **Phase-N stubs are planning docs, not loaded skills.** Anything under
  `.claude/skills/phase-N/<name>/PLAN.md` is roadmap material — Claude
  Code doesn't recurse into nested directories. Promote a PLAN.md to a
  top-level `<name>/SKILL.md` when that phase begins.

## Gotchas

- **`compute/cache/` is gitignored.** Cold-cache compute runs hit SEC
  EDGAR live and can take 25-50 min depending on throttling. Warm-cache
  runs finish in under 5 min.
- **`shares_outstanding` is wrong for ~12 tickers** (issue #10) — Step
  7.5 sanity guard fires `data_quality_input_corruption` on the worst
  cases. Composite scoring doesn't yet respect this flag (issue #18).
- **`_avg_3y_roe` uses single-period equity as denominator** (issue #11)
  → inflated `value_trap_risk` flag on 44% of S&P 500. Phase 4 fix.
- **Going-concern phrase scan has 10.8% FP rate** vs Mayew 2015 expected
  1-3% (issue #16) — negation lookbehind needed.
- **`loss_avoidance_pattern` fires 0% on S&P 500** (Phase 4.5d) —
  Burgstahler-Dichev 1997 cohort thresholds (NI ≤ $5M / EPS ≤ $0.05)
  are too tight for large-cap universe. Annotate-only so it's a
  safe no-op; consider S&P-500-scaled thresholds in Phase 4.5
  follow-up.

## Phase status

Current schema: **`0.8.0-phase4.5f`** · Defense layer: **17**
(7 active vetoes + 10 annotates + 5 numerical guards +
`manipulation_index` rollup). Latest release tag:
[**`v1.2.0-phase4.5`**](https://github.com/dackclup/quantrank/releases/tag/v1.2.0-phase4.5)
**SHIPPED 2026-05-17** at commit `6d414a9b` — **Phase 4.5 cluster
✅ complete** (6 sub-PRs). Production verified run #51
(`b1588b2a`, 5m14s warm-cache). Test suite: 856 offline + 17
`@network`.

**Next deliverable** (pick by appetite — three tracks parallelize):
**4.5e** (Form 4 insider, ~3w → v1.3.0) · **4h/4i/4j/4k** factor
integrations (OSAP / JKP / Qlib / IPCA, ~6w total → v1.1.0-phase4) ·
**Phase 5** ML meta-learner (~10-12w, unblocks PR 4b §3 IC-decay
writer). 4.5e weight slots already declared in
`FLAG_WEIGHTS` so integration is a one-line uncomment.

See [`PHASE_STATUS.md`](PHASE_STATUS.md) for the canonical
chronological tracker — keep this section under 15 lines and let
PHASE_STATUS.md own the per-sub-PR detail.

## Companion files

- [`AGENTS.md`](AGENTS.md) — cross-tool agent instructions (read by
  Copilot / Cursor / Devin / …); procedural detail belongs there
- [`SKILL.md`](SKILL.md) — the long-form QuantRank rulebook (Rules 1-16
  + schema-version table + library matrix)
- [`WORKFLOW.md`](WORKFLOW.md) — per-phase task lists, decision points
- [`PHASE_STATUS.md`](PHASE_STATUS.md) — chronological phase tracker
- [`.claude/skills/README.md`](.claude/skills/README.md) — index of
  loaded skills + planning docs
- [`.claude/skills/claude-Creator.md`](.claude/skills/claude-Creator.md)
  — the meta-guide that shaped this file
