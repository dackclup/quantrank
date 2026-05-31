# CONTEXT.md

Single-file orientation for QuantRank. **This file is a pointer + live
snapshot, not the source of truth.** The canonical project rules,
methodology, and workflow live in the four-file analog documented in
[`docs/agents/domain.md`](docs/agents/domain.md). Read this file first
for orientation, then dive into the relevant deep file from the
mapping table below.

> **Design note.** QuantRank's domain language pre-dates the upstream
> single-`CONTEXT.md` convention; it is distributed across CLAUDE.md +
> SKILL.md + WORKFLOW.md + docs/METHODOLOGY.md. The ADR analog is
> [`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md) (append-only
> side-file). This `CONTEXT.md` exists so external tools / fresh
> agents / vendored skills that expect a single `CONTEXT.md` at the
> repo root have one entry point — it bridges to the four-file
> analog, it does not replace it.

---

## What is QuantRank?

QuantRank is a static-site US-equity ranking tool. A Python compute
layer ingests SEC EDGAR + yfinance data, scores each ticker through
an 8-pillar composite + risk-overlay defense system, and writes JSON
artifacts. A Next.js static site renders the JSON.

- **Universe**: S&P 500 (502 tickers, historical-membership aware after
  the Hou-Xue-Zhang 2020 survivorship-bias fix in PR #274)
- **Output**: `metadata.json` + `rankings.json` + per-ticker
  `stocks/<TICKER>.json` under `frontend/public/data/`
- **Cadence**: weekday compute cron (Mon-Fri 22:00 UTC; weekends
  skipped — no new trading data)
- **Hosting**: static-export Next.js on Vercel CDN

See [`README.md`](README.md) for the user-facing pitch +
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) for the academic backing.

---

## Live snapshot (2026-05-29)

| Field | Value |
|---|---|
| Schema version | **`0.10.11-phase4.6`** on `main` (PR #303 merged 2026-05-29; verify: `python -m compute.output.schema_check`) |
| Active phase | **Phase 4.6** — Honest re-validation harness (Hou-Xue-Zhang 2020 + McLean-Pontiff 2016 32% decay banner). Phase 4.5e ladder closed (PR #303 = PR 6, final residual footgun) |
| Defense layer | **33 declared boolean flags** (7 active vetoes + 26 annotates + reserved; ~27 currently emit) + 5 numerical guards + `manipulation_index` rollup |
| Latest release | [**`v1.4.0-phase4.6`**](https://github.com/dackclup/quantrank/releases/tag/v1.4.0-phase4.6) (2026-05-27, `bbca9cac`) — Phase 4.6 honest re-validation harness |
| Post-tag patches | PR #292 GOOG/GOOGL XBRL · #293 NVR DQIC retire · #294 sector-CoE flip · #295 housekeeping · #296 CONTEXT.md · #297 Issue #287 PR A wall-clocks · #298 cache-v5 · #299 housekeeping · #300 per-sector delta · #301 .md sweep · #302 Site-2 dead-code removal (2026-05-28); PR #303 `847c21b` Form-4 negation guard (schema `0.10.11-phase4.6`) · #304 `e070db6` expert-user-explorer (19th agent) · #306 `6ce7c1b` RiskFlagsCard · #307 `bb1d7fd` Phase B orchestrator tuning · #308 `e77efbf` RiskFlagsCard footer fix · #310 `a941e2e` stale_filing_hard Rule-16 fix (2026-05-29) |
| Universe provider | historical S&P 500 membership (PR #274 Hou-Xue-Zhang 2020) |
| Sector-CoE | `USE_SECTOR_COE = True` (PR #294 flip; Damodaran 2019 Ch. 8.4 11-sector Ke; cron Run #71 confirmed `value_trap_risk` 132 → 109) |
| Sub-agent roster | 20 agents in 4 tiers (5 opus + 15 sonnet) |
| Skill inventory | 46 (vendored + project-internal) |
| Cron status | weekday cron Run #71 green (2026-05-28 08:44 UTC, `368dccd9`, 14m 32s warm cache; empirically validated PR #297 wall-clock fields) |

For chronological detail: [`PHASE_STATUS.md`](PHASE_STATUS.md) +
append-only side-file [`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md).

---

## Multi-file mapping — where to find what

| If you need... | Read this |
|---|---|
| Project rules, conventions, gotchas, auto-routing policy | [`CLAUDE.md`](CLAUDE.md) |
| Long-form rulebook (Rules 1-18) + schema-version table + library matrix | [`SKILL.md`](SKILL.md) |
| Per-phase task lists, Defense Acceptance Matrix, decision points | [`WORKFLOW.md`](WORKFLOW.md) |
| Academic methodology + literature anchors + active-veto rationale | [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) |
| Chronological phase tracker + PR history | [`PHASE_STATUS.md`](PHASE_STATUS.md) |
| In-flight PRs (append-only, parallel-PR safe) | [`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md) |
| Cross-tool agent rules (Copilot / Cursor / Devin) | [`AGENTS.md`](AGENTS.md) |
| Visual / design-system spec (LedgerCraft) | [`docs/design.md`](docs/design.md) |
| Vendor + license posture per third-party source | [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) |
| Sub-agent catalog (20 agents, 4 tiers, 8 coordination flows) | [`.claude/agents/README.md`](.claude/agents/README.md) |
| Skill index (46 vendored + project-internal) | [`.claude/skills/README.md`](.claude/skills/README.md) |
| mattpocock harness consumer rules (issue-tracker, domain) | [`docs/agents/`](docs/agents/) |
| User-facing pitch + Honest Limitations | [`README.md`](README.md) |

**Topic-driven lookup** (mirrors `docs/agents/domain.md`):

| Topic | Read |
|---|---|
| Naming a new defense flag / risk_flag | METHODOLOGY.md (academic prior), SKILL.md (Rule 16) |
| Touching scoring or valuation math | METHODOLOGY.md, SKILL.md, WORKFLOW.md |
| Touching schema fields | SKILL.md (schema-version table), CLAUDE.md (§Conventions schema triple) |
| Touching frontend / UI | CLAUDE.md (§Stack), docs/design.md (LedgerCraft) |
| Cron / observability / Rule 18 | SKILL.md (Rule 18), CLAUDE.md (§Gotchas) |
| Anything cross-cutting | Start with CLAUDE.md as the index; it points at the deep file |

---

## Key invariants (do not violate)

1. **Annotate-and-veto-Top-N** (SKILL.md Rule 16). Flagged stocks
   keep their composite rank but lose the `entered_top5` badge; the
   next-in-line clean stock inherits it. Never modify the composite
   score retroactively.

2. **Schema triple lockstep** (§Conventions). `compute/output/schemas.py`
   (Pydantic) + `frontend/lib/types.ts` (TypeScript) +
   `frontend/lib/schema-snapshot.json` (snapshot) move together. CI
   guard fails the build on drift.

3. **Observability-before-wiring** (SKILL.md Rule 18). New external-
   data integrations ship the diagnostic `Metadata` surface first;
   production wiring follows >= 1 cron after the accounting equation
   is verified on real data.

4. **CLAUDE.md + AGENTS.md ship with every PR** (§Conventions). At
   minimum the PR's in-flight entry lands in
   [`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md); substance
   updates to CLAUDE.md / AGENTS.md (gotchas / conventions / commands)
   still land directly in those files.

5. **Rebase onto `origin/main` before flipping any PR Draft -> Ready**
   (§Conventions). `git fetch origin main && git rebase origin/main`
   resolves benign shared-code conflicts.

6. **Mobile-only releases** (§Gotchas). Tag-refs cannot be pushed from
   this sandbox (HTTP 403); deliver release-tag + GitHub-Release-
   creation steps as pre-filled GitHub URLs the user taps once on
   mobile. See
   [`.claude/skills/release-tag/SKILL.md`](.claude/skills/release-tag/SKILL.md)
   "Mobile-operator release workflow".

7. **Composite formula is sacred** (Rule 16). No retroactive rank
   modification. Vetoes act on UI badges, not score.

8. **Main agent is orchestrator, not laborer** (§Auto-routing policy).
   Default action when given a task is to spawn the matching sub-agent
   in `.claude/agents/`, not to do the work inline. Sonnet sub-agents
   drain the Max-plan "Weekly · Sonnet only" pool which is a separate
   paid-for budget. See CLAUDE.md §Auto-routing policy for delegation
   patterns + cue table.

---

## Stack

- **Python 3.11+** — pandas 2.2 / edgartools 5.31 / pydantic 2.6 /
  tenacity 8.2 / BeautifulSoup 4 / lxml 5 / pytest 8 / ruff 0.4
- **Next.js 14.2** App Router (static export) — React 18.3 /
  TypeScript 5.9 / Tailwind 3.4 / Recharts 2.15. Self-hosted fonts
  (IBM Plex Sans body / JetBrains Mono tabular numerics /
  Instrument Serif display / Roboto Slab headlines)
- **CI** — GitHub Actions; weekday `compute-rankings.yml`
- **Data** — SEC EDGAR via `edgartools` / yfinance for prices /
  S&P 500 constituents scraped from Wikipedia
- **MCP connectors** — GitHub (active) / Vercel (active) /
  Supabase (active, reserved for Phase 5+) / Sentry (planned)

---

## Layout (one-line tour)

| Path | Purpose |
|---|---|
| `compute/ingest/` | SEC EDGAR + yfinance fetchers with on-disk caches |
| `compute/scoring/` | 8-pillar composite + risk overlay (7 active vetoes) |
| `compute/valuation/` | 6-method fair-price ensemble + Tier-1 defenses |
| `compute/output/` | Pydantic schemas + JSON writers + schema-snapshot guard |
| `compute/main.py` | Weekly compute orchestrator |
| `frontend/app/` | Next.js routes (one per stock at `/stock/[ticker]`) |
| `frontend/components/` | React UI (RankingTable, FairPriceBarChart, ...) |
| `frontend/public/data/` | Compute output: `metadata.json` + `rankings.json` + `stocks/<TICKER>.json` |
| `tests/` | pytest suite (offline + `@network` gated) |
| `.claude/skills/` | 46 invocation-triggerable skills + phase planning docs |
| `.claude/agents/` | 20 project-specific sub-agents in 4 tiers |
| `.claude/hooks/` | 3 hook scripts (`log-bash.sh` + `schema-reminder.sh` + `delegate-first.sh`) |
| `docs/` | METHODOLOGY.md, design.md, agents/ |

---

## Quick-start commands

**Verification ladder before any push:**

```sh
ruff check .
pytest tests/ -m "not network"
# if schemas touched:
python -m compute.output.schema_check
# if frontend touched:
cd frontend && npx --no -- tsc --noEmit && npx --no -- next build
# if compute output committed:
python .claude/skills/verify-production-output/helper.py
```

**Local weekly compute:**

```sh
python -m compute.main   # writes frontend/public/data/
```

**Live SEC tests (network):**

```sh
EDGAR_USER_AGENT="Your Name your@email" pytest --run-network
```

---

## Standing constraints (license + scope)

- **NO `mlfinlab`** (AGPL/commercial) — reimplement Triple-Barrier /
  Meta-Labeling / Purged CV from primary papers under MIT
- **NO JKP DATA** without license review (CC BY-NC 4.0, issue #115)
- **NO `gudhi`** (GPL-3) — use `ripser-py` for TDA instead
- **Loughran-McDonald** dictionary academic-only — README disclaimer
  required when Phase 6 ships
- **Honest alpha 2-5% net** post-McLean-Pontiff 2016 32% decay floor
- **S&P 500 only** until Phase 8 (universe = 502)
- **No specific ticker trade recommendations** (research output only)
- **Sub-agents are read-only** — user authorizes any destructive
  command they propose
- **Do not push to `main` directly** — PR-based workflow with rebase

---

## Vocabulary discipline

When naming a domain concept (issue title, refactor proposal, test
name), use the canonical project term:

- **annotate-only** (not "advisory flag") — Rule 16
- **veto** (not "rejection" / "exclusion") — Rule 16
- **Tier-2 defense** (not "secondary scoring layer") — METHODOLOGY.md
- **schema triple** (not "type contract") — §Conventions
- **Rule 18** (not "observability discipline") — SKILL.md
- **dimensional override** (PR #257) — for multi-class XBRL recovery
- **S&P 500 universe** (502 tickers, not 500) — §Phase status

See [`docs/agents/domain.md`](docs/agents/domain.md) §"Use the project
vocabulary" for the full list.

---

## Roadmap pointer

For the high-level roadmap from current state to project end (v2.0
S&P 1500 universe expansion), see
[`PHASE_STATUS.md`](PHASE_STATUS.md) §"Next deliverables" +
[`WORKFLOW.md`](WORKFLOW.md) per-phase task lists. Headline phases:

- **Stage 0** (immediate): Issue #287 PR B FORM4 revert (single-line, gated on ≥ 1 cron < 195m green with `form4_wall_clock_seconds` populated; PR #297 ceiling bump active so headroom confirmed by cron Run #71 14m 32s)
- **Stage 1**: Phase 4.5e PR 5 cluster-weight promotion 5.0 -> 7.0
- **Stage 2**: Phase 4 factor integrations (4h.2 / 4j.1 / 4k.1) -> `v1.5.0-phase4`
- **Stage 3**: Phase 5 ML meta-learner (LightGBM + Triple-Barrier + Conformal + SHAP) -> `v1.6.0-phase5`
- **Stage 4**: Phase 6 Sentiment v2 (FinBERT + Whisper + 8-K Lazy Prices) -> `v1.7.0-phase6`
- **Stage 5**: Phase 7 Regime + Portfolio v2 (Student-t HMM + TDA + NCO) -> `v1.8.0-phase7`
- **Stage 6**: Phase 8 universe expansion (S&P 1500 + 20-F + 6-K ADRs) -> `v2.0.0-phase8`

---

## Companion files

- [`CLAUDE.md`](CLAUDE.md) — primary project instructions
- [`AGENTS.md`](AGENTS.md) — cross-tool agent rules
- [`SKILL.md`](SKILL.md) — long-form QuantRank rulebook
- [`WORKFLOW.md`](WORKFLOW.md) — per-phase task lists
- [`PHASE_STATUS.md`](PHASE_STATUS.md) — chronological tracker
- [`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md) — append-only side-file
- [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) — academic backing
- [`docs/design.md`](docs/design.md) — design system (LedgerCraft)
- [`docs/agents/domain.md`](docs/agents/domain.md) — multi-file CONTEXT mapping
- [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md) — GitHub MCP rules
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) — vendor + license posture
- [`README.md`](README.md) — user-facing pitch
