# AGENTS.md

> Cross-tool agent instructions for QuantRank. Read by Claude Code,
> GitHub Copilot, Cursor, Devin, VS Code Agent Mode, and other tools
> that follow the [agents.md](https://agents.md/) open standard. Claude
> Code users: also see [`CLAUDE.md`](CLAUDE.md) for Anthropic-specific
> session context (auto-loaded each session). Both files coexist; they
> do not duplicate.

## Tech stack

- **Python 3.11+** — pandas 2.2 · edgartools 2.30 · pydantic 2.6 ·
  tenacity 8.2 · BeautifulSoup 4 · lxml 5 · pytest 8 · ruff 0.4 ·
  pyarrow 15 · yfinance 0.2
- **Next.js 14.2** (App Router, static export) · React 18.3 ·
  TypeScript 5.4 · Tailwind 3.4 · Recharts 2.12
- **GitHub Actions** for CI + weekly compute cron
- **SEC EDGAR** + **yfinance** + Wikipedia (S&P 500 constituents) for
  data ingestion

## Commands

| Action | Command |
|---|---|
| Install Python deps | `pip install -e .` (from repo root) |
| Install frontend deps | `cd frontend && npm install` |
| Lint Python | `ruff check .` |
| Auto-fix Python lint | `ruff check --fix .` |
| Test (offline, default) | `pytest tests/ -m "not network"` |
| Test (live SEC EDGAR) | `pytest --run-network` (requires `EDGAR_USER_AGENT` env var) |
| Test one module | `pytest tests/test_scoring/test_tier2.py -v` |
| Schema in-sync check | `python -m compute.output.schema_check` |
| Schema snapshot regen | `python -m compute.output.schema_check --update-snapshot` |
| Frontend type-check | `cd frontend && npx --no -- tsc --noEmit` |
| Frontend dev server | `cd frontend && npm run dev` (port 3000) |
| Frontend production build | `cd frontend && npx --no -- next build` |
| Frontend lint | `cd frontend && npm run lint` |
| Run weekly compute locally | `python -m compute.main` (writes `frontend/public/data/`) |
| Section A-H production scan | `python .claude/skills/verify-production-output/helper.py` |

## Testing

- **Framework**: pytest 8. Config in `pyproject.toml` under
  `[tool.pytest.ini_options]`. Tests live under `tests/<module>/`.
- **Network gating**: tests that hit live SEC EDGAR are marked
  `@pytest.mark.network` and skipped by default. Run with
  `--run-network` AND `EDGAR_USER_AGENT="Name email@domain"` set. CI
  does NOT run network tests (no env var) — they are pre-merge sanity
  for the author.
- **Coverage policy**: no enforced threshold. Add a test when a bug is
  found, when a new defense ships, or when a contract is added to the
  output schema.
- **Where to put new tests**:
  - Compute logic → `tests/test_scoring/` or `tests/test_valuation/`
  - Ingest / cache → `tests/test_ingest/` or `tests/test_features/`
  - Output writers / schemas → `tests/test_output/`
  - Orchestrator helpers → `tests/test_main.py`
- **Synthetic fixtures preferred** over live network calls. The
  `test_eight_k_events.py` `_filing()` builder is a good model.

## Project structure

```
compute/                          # Python compute pipeline
├── ingest/                       # SEC EDGAR + yfinance fetchers (read/write OK)
│   ├── fundamentals.py           # XBRL fact extraction; gotcha: shares_outstanding bug for ~12 tickers (issue #10)
│   ├── prices.py                 # yfinance wrapper
│   ├── filing_text.py            # 10-K narrative text fetcher
│   └── universe.py               # S&P 500 constituents
├── scoring/                      # 8-pillar composite + risk overlay (read/write OK)
│   ├── pillars.py
│   ├── composite.py              # Weighted aggregation + sector neutralization
│   ├── risk_overlay.py           # 3 active vetoes: altman / sloan / NSI
│   ├── tier2.py                  # Tier-2 events orchestrator; _EIGHT_K_DEFENSES_ENABLED = False until Phase 4
│   ├── eight_k_events.py
│   └── going_concern.py
├── valuation/                    # Fair-price ensemble (read/write OK)
│   ├── ensemble.py               # 6-method aggregation + outlier guard + $10K ceiling
│   ├── dcf.py · rim.py · graham.py · multiples.py · tangible_book.py
├── output/                       # JSON output + schema snapshot guard (⚠️ schemas)
│   ├── schemas.py                # Pydantic models — mirror frontend/lib/types.ts
│   ├── schema_check.py           # Drift guard against frontend/lib/schema-snapshot.json
│   └── writer.py                 # Atomic writes for rankings + per-stock detail JSON
├── config.py                     # Constants: thresholds, lookbacks, paths
├── main.py                       # Weekly compute orchestrator
└── cache/                        # 🚫 GITIGNORED — never commit cache contents

frontend/                         # Next.js static site
├── app/                          # App Router (read/write OK)
│   ├── page.tsx                  # Rankings page
│   └── stock/[ticker]/page.tsx   # Per-stock detail page (502 static routes)
├── components/                   # React UI (read/write OK)
│   ├── RankingTable.tsx · FairPriceBarChart.tsx · PillarRadarChart.tsx · Tier2EventCard.tsx · …
├── lib/                          # ⚠️ schemas live here
│   ├── types.ts                  # Mirrors compute/output/schemas.py
│   ├── schema-snapshot.json      # Canonical bridge — auto-generated, do not hand-edit
│   └── format.ts                 # Display formatters
├── public/data/                  # 🟡 generated by compute/main.py — gitignored except production snapshots
│   ├── metadata.json · rankings.json · stocks/<TICKER>.json
└── package.json

tests/                            # pytest suite (read/write OK)
docs/                             # Academic methodology + research findings (read/write OK)
.claude/skills/                   # 38 loaded skills + planning docs (read/write OK)
.github/workflows/                # CI definitions (⚠️ ask before editing)
pyproject.toml                    # Python project config + ruff + pytest (⚠️ ask before deps changes)

# 🚫 Never touch
compute/cache/                    # Local caches, gitignored
node_modules/                     # Frontend deps, gitignored
.next/ · dist/                    # Build output
.env · .env.local · *.secret.*    # Secrets
frontend/public/data/             # ⚠️ DO commit only via the CI compute job, NEVER hand-edit
```

## Code style

### Python

Ruff enforces formatting + import sort + lint rules (E / F / I / B / UP /
W; ignore `E501` since we cap at 100 chars). Run `ruff check --fix .`
to auto-fix. Do not hand-format what the linter handles.

**Type hints required** on all public functions. Modern union syntax
(`int | None`, not `Optional[int]`).

✅ Good:
```python
def compute_altman_z(snapshot: FundamentalsSnapshot) -> float | None:
    """Return Altman Z″ score; None if any required input is missing."""
    if snapshot.total_assets is None or snapshot.total_assets <= 0:
        return None
    return (
        3.25
        + 6.56 * (snapshot.working_capital / snapshot.total_assets)
        + 3.26 * (snapshot.retained_earnings / snapshot.total_assets)
        + 6.72 * (snapshot.ebit / snapshot.total_assets)
        + 1.05 * (snapshot.book_value_equity / snapshot.total_liabilities)
    )
```

❌ Avoid:
```python
def compute_altman_z(snapshot):  # missing types
    # crashes on zero or None total_assets
    return 3.25 + 6.56 * snapshot.working_capital / snapshot.total_assets + ...
```

**Pydantic v2** for all data classes that cross the JSON boundary.
Frozen dataclasses for internal compute-only structures.

**Tenacity retry** for any function that hits SEC EDGAR. Use
`stop_after_delay(30) | stop_after_attempt(2)` with `wait_exponential(min=2, max=8)`
— per PR-3d's amplification incident, more aggressive policies cause
60-90s/stuck-stock cascades.

### TypeScript

✅ Good:
```ts
import type { StockDetail } from '@/lib/types';

export function FairPriceCard({ detail }: { detail: StockDetail }) {
  const fp = detail.fair_price;
  if (fp === null || fp.median === null) {
    return <span className="text-slate-400">Fair ⚠ N/A</span>;
  }
  return <span className="text-slate-700 tabular-nums">${fp.median.toFixed(2)}</span>;
}
```

❌ Avoid:
```ts
export function FairPriceCard(props) {  // no types
  return <span>{props.detail.fair_price.median.toFixed(2)}</span>;
  // crashes if fair_price or median is null (which Step 7.5 sanity guard makes common)
}
```

- TypeScript strict mode is on; never silence with `any` or
  `@ts-ignore` without a comment explaining why
- Tailwind classes via the existing palette (slate / indigo / rose /
  amber). No raw hex.
- Loose-equal `null` checks (`== null` rather than `=== null`) when
  reading older schema JSONs — `tier2_events` may be `undefined` on
  pre-PR-3d snapshots
- `tabular-nums` Tailwind class for all numeric columns so digits
  right-align cleanly

## Git workflow

- **Branch naming**: `<type>/<scope-and-summary>`. Types we use:
  `feat`, `fix`, `chore`, `polish`, `perf`, `docs`, `refactor`.
  Examples: `feat/phase-3e-beneish`, `polish/phase-3d-ui-clipping`,
  `chore/refactor-quantrank-skills`.
- **Commit message format**: `<type>(scope): <one-line summary>`
  followed by a body explaining WHY. Example:
  `perf(phase-3d): skip 8-K parser via raw HTML + regex`.
- **All PRs open as Draft first.** Flip to Ready only after CI passes
  AND a user-driven spot-check (Vercel preview) AND explicit user
  authorization. See
  [`.claude/skills/pr-iteration-flow/SKILL.md`](.claude/skills/pr-iteration-flow/SKILL.md).
- **Never merge without explicit user authorization.** Agents propose;
  the user merges.
- **Never push to `main` directly.** Always via PR.
- **PR body template**: scope + verification table (ruff / pytest /
  tsc / next build / schema-check) + "what this PR does NOT touch" +
  reviewer checklist. See `pr-iteration-flow/SKILL.md` for the canonical
  template.
- **AGENTS.md + CLAUDE.md ship with every PR.** Every PR — current and
  future, regardless of type (feat / fix / ci / docs / chore) — must
  include an edit to both AGENTS.md (this file) and CLAUDE.md that
  records what is changing and why. At minimum, a paragraph under
  §"Phase + version state" (PR in flight) or in the appropriate section
  (new gotcha / convention / boundary / command / connector). The PR
  is incomplete until both agent docs reflect it. Non-Claude runtimes
  (Copilot / Cursor / Devin) read AGENTS.md; Claude reads CLAUDE.md.
  They must stay in lockstep so behavior is consistent across agents.

## Boundaries

### ✅ Always OK

- Read any file under `compute/`, `frontend/`, `tests/`, `docs/`,
  `.claude/`
- Write to `compute/`, `frontend/components/`, `frontend/app/`, `tests/`,
  `docs/`, `.claude/skills/` (own QuantRank skills only — not the
  vendored Anthropic ones)
- Run `ruff check .`, `pytest -m "not network"`, `schema_check`,
  `tsc --noEmit`, `next build`
- Open a draft PR
- Subscribe to PR activity via `mcp__github__subscribe_pr_activity`
- Add a test next to any new defense or contract
- Use `git mv` for renames so history is preserved

### ⚠️ Ask first

- Schema changes (`compute/output/schemas.py`,
  `frontend/lib/types.ts`, `frontend/lib/schema-snapshot.json`) — the
  triple must move together; ask before changing any one of them
- Dependency additions to `pyproject.toml` or `frontend/package.json`
- CI workflow file edits (`.github/workflows/*.yml`)
- New top-level files at repo root (we already have 8; adding more
  needs justification)
- Editing the 17 vendored Anthropic skills under `.claude/skills/`
  (treat as upstream-frozen; if upstream changes, re-vendor)
- Phase status updates (`PHASE_STATUS.md`, `SKILL.md`, `WORKFLOW.md`)
  — these three move in lockstep; use the
  `phase-status-bump` skill
- Force-pushing to any branch
- Removing the `@pytest.mark.network` skip on a test

### 🚫 Never

- Touch `.env`, `.env.local`, or any file matching `*.secret.*`
- Modify files under `node_modules/`, `.next/`, `dist/`,
  `compute/cache/`
- Commit API keys, EDGAR identity strings, GitHub tokens, or any
  secret (even temporarily)
- Push directly to `main`, force-push to `main`, or rewrite history
  on any branch that has been merged
- Run `rm -rf` on any tracked directory
- Skip pre-commit hooks (`--no-verify`, `--no-gpg-sign`)
- Flip a PR from Draft → Ready without explicit user authorization
- Merge a PR (any PR, ever)
- Delete a branch (local or remote) without explicit user authorization
- Trigger a `workflow_dispatch` on `compute-rankings.yml` — the user
  triggers production compute runs from GitHub mobile
- Modify `compute/output/schema-snapshot.json` by hand (always
  regenerate via `--update-snapshot`)

## Security considerations

- `EDGAR_USER_AGENT` is required for SEC EDGAR fetches. Set via env
  var. CI uses a GitHub Actions secret. Never commit.
- Pre-commit hooks run `ruff` + the schema-snapshot guard. Do not
  bypass.
- No telemetry / external network beacons in the frontend. The site is
  pure static HTML+JS; no analytics in v1.0.

## Phase + version state

- Current release tag: [`v1.2.0-phase4.5`](https://github.com/dackclup/quantrank/releases/tag/v1.2.0-phase4.5)
  (tagged 2026-05-17 on `main` at commit `6d414a9b`)
- Active defenses: **7 vetoes** + 10 annotates + 5 numerical guards +
  `manipulation_index` rollup = **17 total defense layer entries**
- Schema version: `0.9.2-phase4h.2` in `metadata.json` (see
  [`SKILL.md`](SKILL.md) §schema-version table for full history)
- Test suite: see CI build artifact for current count
- Production-verified run: #51 (`b1588b2a`, 5m14s warm-cache)
- Open Phase 4+ issues: **4** — #15 (SEC throttling) · #41 (Next 14→16
  CVE bump) · #67 (Damodaran sector-adjusted CoE, Phase 5+) · #75
  (PR 4b §3 IC-decay writer, Phase 5-blocked)
- Next deliverable tracks (parallelizable): 4.5e Form 4 insider
  (~3w → v1.3.0) · 4h/4i/4j/4k factor integrations OSAP/JKP/Qlib/IPCA
  (~6w → v1.1.0-phase4) · Phase 5 ML meta-learner (~10-12w)
- **Epic #125 Item 3** (pre-merge production simulation) — **PR 1 of
  2 shipped** via [PR #140](https://github.com/dackclup/quantrank/pull/140)
  on 2026-05-20 at commit `a52aa2de`. PR 1 landed the workflow
  harness (`.github/workflows/pre-merge-prod-sim.yml`): warm-cache
  restore via the cron's `cache-v4` key + `python -m compute.main`
  against the PR branch + sticky PR comment with duration / universe
  / schema / commit + PR-branch output uploaded as
  `pr-<n>-compute-output` artifact (14-day retention). Dogfoods on
  the next PR touching `compute/scoring/**` or `compute/features/**`.
  **PR 2 next** — per-ticker composite-score diff vs main + top-10
  movers table.
- **Karpathy LLM Wiki gist** vendored as a reference skill at
  `.claude/skills/karpathy-llm-wiki/SKILL.md` (same PR #140) —
  license-pending: gist has no declared LICENSE but explicit
  copy-paste-to-your-LLM-agent permission in the gist body; see
  `THIRD_PARTY_NOTICES.md` § karpathy-llm-wiki. Reference-only — does
  **not** instantiate a QuantRank wiki. Non-Claude runtimes
  (Copilot / Cursor / Devin) can read the file directly but it has no
  procedural triggers in their skill systems (it's a Claude Code
  `SKILL.md` with description-based dispatch).
- **`.md` optimization** in flight (Option D — multi-PR overhaul).
  PR A (drift fix + YAML frontmatter fix) shipped via
  [PR #141](https://github.com/dackclup/quantrank/pull/141). PR B
  (CLAUDE.md token diet, 236 → ~170 lines) ships next — moves the
  multi-session audit pattern detail to this file (AGENTS.md) and
  compresses the Phase status / Connector / Conventions sections.
  Subsequent PRs: C (AGENTS.md sync + dedup) · D (WORKFLOW.md archive
  Phase 0-3) · E (SKILL.md restructure) · F (skill description audit
  ×38) · G (PHASE_STATUS.md "Current State" summary).

## Claude-Code-specific tooling

Claude Code sessions for this project have 6 MCP connectors enabled
(GitHub · Gmail · Google Drive · Vercel · Supabase · Sentry-planned).
Other agent runtimes (GitHub Copilot, Cursor, Devin, VS Code Agent
Mode) do not have these connectors — when those tools work this repo,
they should:

- Use `gh` CLI for PRs / issues / CI status (instead of `mcp__github__*`)
- Inspect Vercel deploys via `vercel.com` dashboard or `vercel` CLI
  (instead of `mcp__vercel__*`)
- Skip Supabase entirely — current code does not depend on it
- Skip Sentry MCP — frontend SDK is not yet wired

If a task requires the connector surface (e.g., automated batch deploy
audit), prefer routing it through Claude Code rather than re-
implementing the integration in a different agent.

## Multi-session audit pattern

When an in-flight session (mid-audit, mid-PR-review) discovers it lacks
the connector needed for a verification step — typically because the
session started before the connector was registered — **do not restart
mid-task**. Restart loses audit context. Instead, delegate the
connector-bound step to a sibling session:

1. **Run what you CAN** with the tools you already have (Bash, file reads,
   GitHub MCP, Playwright via `executable_path` workaround, etc.)
2. **Identify the gap** — list the exact `mcp__<connector>__*` calls the
   in-flight session cannot make
3. **Write a short, focused prompt** for a new session: the specific calls,
   parameter values, and the report-back format you expect (markdown table
   / fixed sections / fail-fast verdict)
4. **Synthesize** — when the sibling session pastes its report back, merge
   it with your own findings into the single verdict

Example — Section I post-`workflow_dispatch` (`verify-production-output/SKILL.md`)
has three steps: Vercel MCP deploy-health (Step 1), Playwright 4-ticker
matrix (Step 2), Sentry recent issues (Step 3). A session without Vercel
MCP runs Step 2 itself, delegates Step 1 to a sibling session, and notes
Step 3 as deferred-until-SDK-wires.

The pattern preserves session continuity. Use it for: live-UI audits,
post-deploy log inspection, Supabase row inspection during 4.5e / Phase
5 work, or any case where a single session straddles connector-bound and
non-connector-bound work. CLAUDE.md keeps a 5-line reference to this
section; the full procedure lives here so cross-tool agents see the
same pattern.

## Companion files

- [`CLAUDE.md`](CLAUDE.md) — Claude Code-specific session context;
  auto-loaded each session
- [`SKILL.md`](SKILL.md) — long-form QuantRank rulebook (Rules 1-16)
- [`WORKFLOW.md`](WORKFLOW.md) — per-phase task lists
- [`PHASE_STATUS.md`](PHASE_STATUS.md) — chronological phase tracker
- [`.claude/skills/README.md`](.claude/skills/README.md) — index of
  loaded skills + planning docs
- [`.claude/skills/agent-Creator.md`](.claude/skills/agent-Creator.md)
  — the meta-guide that shaped this file
