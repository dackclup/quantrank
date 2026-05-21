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
.claude/skills/                   # 24 loaded skills + planning docs (read/write OK)
.claude/agents/                   # 2 project subagents — sonnet, Claude Code only (Copilot / Cursor / Devin ignore)
.claude/hooks/                    # PostToolUse Bash hooks (schema-reminder.sh) wired by .claude/settings.json (Claude Code only)
.claude/settings.json             # Claude Code harness config — hooks. Per-user overrides go in .claude/settings.local.json (gitignored)
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

## Claude-Code-specific tooling

Claude Code reads `.claude/settings.json` for hooks and uses
`.claude/agents/` for project subagents. Both surfaces are
Claude-Code-only — other agent runtimes (GitHub Copilot, Cursor,
Devin, VS Code Agent Mode) should ignore them and rely on git
pre-commit hooks + manual review instead.

**Hook (PostToolUse)**:

- `.claude/hooks/schema-reminder.sh` — emits an
  `additionalContext` reminder when Write/Edit touches any file
  in the Pydantic↔TS↔snapshot triple (`compute/output/schemas.py`,
  `frontend/lib/types.ts`, `frontend/lib/schema-snapshot.json`).
  Bash + `jq`, 5-second timeout, fail-open on missing deps /
  empty stdin.

**Subagents (lean baseline + 1 data-correctness reviewer, all sonnet)**:

- `schema-sentinel` — deterministic schema-triple drift check.
  Reads the three schema files and runs
  `python -m compute.output.schema_check`. Never runs
  `--update-snapshot` itself.
- `quantrank-reviewer` — full diff review against project
  invariants (Rule 16 annotate-and-veto, schema triple, tenacity
  retry policy, EDGAR rate-limit, `frontend/public/data/`
  read-only).
- `stock-detail-auditor` — data correctness of the per-stock
  JSON the frontend renders. Pre-filters the ~502-ticker
  universe deterministically (range / consistency / Rule 16
  invariant / known-issue overlap with #7 / #10 / #11), then
  does LLM-judgment review on ≤ 20 flagged tickers. Read-only;
  never modifies `frontend/public/data/`. Fires at hand-off
  moments (post-cron, pre-release, "ตรวจ data หุ้น"), not on
  every code edit. Covers OUTPUT correctness; formula
  correctness (Altman Z weights, Beneish M coefficients, etc.)
  is a separate concern handled outside the agent layer today.

All fire at gate moments only (`ready to push` / `Draft → Ready` /
post-cron / explicit ask) — not on every edit. See
[`CLAUDE.md`](CLAUDE.md) §Auto-routing policy for the firing cues
and the "lean by design" token-economy reasoning.

## Phase + version state

- Current version: `v0.6.0-phase3d` (tagged on `main`)
- Active defenses: **3 vetoes** (altman / sloan / NSI), 5 numerical
  guards, 6 annotate flags
- Schema version: `0.6.0-phase3d` in `metadata.json`
- Open Phase 4 issues: 8 (#7 / #10 / #11 / #14 / #15 / #16 / #17 /
  #18) — see GitHub issues for triage order

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
