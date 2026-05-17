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

Current schema: `0.7.1-phase4g` (no shape delta across the 4.5a-d
wave — new flag identifiers are strings on existing
`risk_flags: list[str]` + `valuation_warnings: list[str]` arrays).
Defense layer: **16** (7 active vetoes + 10 annotates + 5 numerical
guards). Latest release tag: `v1.0.0` (2026-05-14). Phase **4.5d
merged 2026-05-17** (PR #97). Production verified run #50 (commit
`c3b29af4`, warm-cache 6m24s). Test suite: 831 offline + 17
`@network`.

**Next deliverable**: choose between **4.5e** (Form 4 insider
clustering — `insider_sell_cluster` + `c_suite_unusual_sell`, ~420
LOC, new SEC parser, ~3 weeks) and **4.5f** (`manipulation_index`
0-100 composite + composite-score penalty + UI Manipulation pillar
card + schema bump → tag `v1.2.0-phase4.5`, ~250 LOC, ~1 week).
Factor integrations **4h/4i/4j/4k** (OSAP / JKP / Qlib / IPCA) run
in parallel — disjoint code paths, share the PR 4b §2 PBO/DSR gate.
Tag `v1.1.0-phase4` after 4h-4k land.

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
