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
| `compute/scoring/` | 8-pillar composite + risk overlay (5 active vetoes) |
| `compute/valuation/` | 6-method fair-price ensemble + Tier-1 defenses |
| `compute/output/` | Pydantic schemas + JSON writers + schema-snapshot guard |
| `compute/main.py` | Weekly compute orchestrator |
| `frontend/app/` | Next.js routes (one per stock at `/stock/[ticker]`) |
| `frontend/components/` | React UI (RankingTable, FairPriceBarChart, …) |
| `frontend/public/data/` | Compute output: `metadata.json` + `rankings.json` + `stocks/<TICKER>.json` |
| `tests/` | pytest suite (526 tests, 3 `@network` gated) |
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
- **`sloan_accruals_top_decile` over-fires on Financials** (issue #7)
  → sector-relative threshold or sector exclusion needed.
- **Going-concern phrase scan has 10.8% FP rate** vs Mayew 2015 expected
  1-3% (issue #16) — negation lookbehind needed.

## Phase status

**v1.0.0 shipped 2026-05-14** — Phase 3 + 3e complete (Beneish +
Dechow Tier-3 + Honest Limitations all merged). **Phase 4 in
flight**: 4a / 4b (`_avg_3y_roe` fix) / 4c+4c.1/4c.2/4c.3 / 4d / 4e
/ 4f / 4g all merged (cache + ROE + UX trio + price chart + 8-K
Tier-2 re-enable). Production schema `0.7.0-phase4g`;
`SCHEMA_VERSION` constant currently `0.7.1-phase4g` (additive
`price_change_1d_pct` field — flips on next weekly compute).
**Next deliverable**: **Phase 4.5a.1 — sector-relative Sloan**
(folds in [issue #7](https://github.com/dackclup/quantrank/issues/7)).
Replaces the cross-sectional top-decile Sloan veto with a
within-GICS-sector top-decile gate. Removes the known over-fire
on Financials + REITs whose non-cash earnings are structural, not
manipulative. ~80 LOC + AAER backtest, ~3 days. **PR 4b §3
(IC-decay writer + UI surface) is deferred to Phase 5** —
`compute/validation/ic_decay.py` needs a per-pillar monthly IC
time series that only the Phase 5 walk-forward backtest harness
will accumulate. PR #60 + ic_decay.py:51 always intended this
sequencing ("until then, this module ships as a callable
library"); issue #75's last 2 acceptance criteria are Phase-5-
blocked, not next-deliverable work. **PR 4b §1 cross-source
validator and §2 PBO/DSR library already shipped in PR #60
(2026-05-14, pre-v1.0)** — production run #45 confirms 23 stocks
flagging `cross_source_disagreement` (4.6%, within the < 5%
sanity bound) and `pbo_dsr.factor_passes_gates()` is callable for
4h/4i/4j/4k.

After 4.5a.1 → 4.5a.2 (Beneish soft-veto) + 4.5a.3 (Dechow soft-
veto + `manipulation_triple_flag`) in parallel → 4.5b through
4.5f. Factor integrations 4h/4i/4j/4k can run in parallel with
4.5 (disjoint code paths, same PR 4b §2 PBO/DSR gate). Tag
`v1.1.0-phase4` after 4h-4k land; tag `v1.2.0-phase4.5` after
4.5a-4.5f. **Phase 4.5 (earnings-manipulation defense cluster)**:
6 sub-PRs (4.5a-4.5f) covering sector-relative Sloan + Beneish/
Dechow soft-veto + restatement history + Form 12b-25 late
filings + Roychowdhury REM + earnings-quality time-series +
Burgstahler-Dichev kink + Form 4 insider clustering +
manipulation-composite penalty. Defense layer grows **9 → 18
layers** (5 → 7 active vetoes; 4 → 11 annotates). See
[`PHASE_STATUS.md`](PHASE_STATUS.md) §"Phase 4.5 plan" for the
full sub-PR breakdown + AAER backtest cohort. **5 open Phase 4+
issues**: #7 (Sloan sector-relative — addressed by 4.5a.1) / #15
(fundamentals throttling) / #41 (Next.js 14 → 16 CVEs) / #67
(Damodaran CoE Phase 5+) / #75 (PR 4b §3 — Phase-5-blocked).

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
