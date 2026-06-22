# AGENTS.md

> Cross-tool agent instructions for QuantRank. Read by Claude Code,
> GitHub Copilot, Cursor, Devin, VS Code Agent Mode, and other tools
> that follow the [agents.md](https://agents.md/) open standard. Claude
> Code users: also see [`CLAUDE.md`](CLAUDE.md) for Anthropic-specific
> session context (auto-loaded each session). Both files coexist; they
> do not duplicate.

## Tech stack

See [`CLAUDE.md`](CLAUDE.md) §Stack for the canonical stack list
(Python 3.11+ · Next.js 14.2 · pytest 8 · ruff 0.4 · etc.). Extra
deps not auto-loaded into Claude context but relevant for build /
test work: `pyarrow 15` (parquet on-disk caches), `yfinance 0.2`
(price ingest). GitHub Actions runs CI + the weekly compute cron.

## Commands

[`CLAUDE.md`](CLAUDE.md) §Commands has the canonical verification
ladder. Setup + dev-loop commands that don't fit there:

| Action | Command |
|---|---|
| Install Python deps | `pip install -e .` (from repo root) |
| Install Python deps (with dev + factor extras) | `pip install -e ".[dev,factors]"` |
| Install frontend deps | `cd frontend && npm install` |
| Auto-fix Python lint | `ruff check --fix .` |
| Test one module | `pytest tests/test_scoring/test_tier2.py -v` |
| Frontend dev server | `cd frontend && npm run dev` (port 3000) |
| Frontend lint | `cd frontend && npm run lint` |

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

[`CLAUDE.md`](CLAUDE.md) §Layout has the top-level path table, and
[`CLAUDE.md`](CLAUDE.md) §Architecture & data flow explains how the
two layers join through the JSON contract + the ~9-step compute
pipeline (read it first for the end-to-end mental model).
Granular tree for cross-tool agents below — annotations are
file-purpose only. Known bugs / drift live in CLAUDE.md §Gotchas;
this section doesn't duplicate them.

```
compute/                          # Python compute pipeline (read/write OK)
├── ingest/                       # SEC EDGAR + yfinance fetchers
│   ├── fundamentals.py           # XBRL fact extraction
│   │                             #   (CIK discipline: never `Company("")` —
│   │                             #   resolves to an arbitrary company; see
│   │                             #   CLAUDE.md §Gotchas + docs/GOTCHAS.md;
│   │                             #   fast cache frozen-immutable per quarter →
│   │                             #   filing-date precheck the only safe skip
│   │                             #   path for stale-but-cached tickers, #471)
│   ├── prices.py                 # yfinance wrapper (daily OHLCV from the fixed
│   │                             #   floor 2015-11-29 — Design A 2026-06-11,
│   │                             #   covers the decade AI-pick backtest;
│   │                             #   per-stock history tail-capped to ~5y by
│   │                             #   HISTORY_TAIL_DAYS, so the stock chart's per-
│   │                             #   period resolution — 5Y monthly, shorter
│   │                             #   daily — is unchanged + frontend-
│   │                             #   side, see CLAUDE.md §Gotchas "Price-
│   │                             #   chart resolution"; 1D/5D intraday = v1.3)
│   ├── filing_text.py            # 10-K narrative text fetcher
│   ├── historical_8k.py          # PIT 8-K Item 4.02 reader (data/pit_item402_history.parquet;
│   │                             #   graceful-absent → []; see CLAUDE.md §Gotchas)
│   ├── historical_sector.py      # PIT GICS sector reader (data/historical_sector.parquet;
│   │                             #   graceful-absent → today's sector)
│   └── universe.py               # S&P 500 / 400 / 900 (combined) constituents (QR_UNIVERSE)
├── scoring/                      # 8-pillar composite + risk overlay
│   ├── pillars.py · composite.py · risk_overlay.py
│   ├── tier2.py                  # Tier-2 events orchestrator
│   └── eight_k_events.py · going_concern.py · beneish.py · dechow_f.py
│                                 #   (8-K cache TTL is per-ticker JITTERED
│                                 #   to de-sync the cohort cliff — see
│                                 #   CLAUDE.md §Gotchas + docs/GOTCHAS.md #469)
├── features/                     # Factor signals (OSAP / Qlib / IPCA …)
├── valuation/                    # 6-method fair-price ensemble + Tier-1 defenses
│   ├── ensemble.py · dcf.py · rim.py · graham.py · multiples.py · tangible_book.py
├── output/                       # ⚠️ schemas live here (triple lockstep)
│   ├── schemas.py                # Pydantic models — mirror frontend/lib/types.ts
│   ├── schema_check.py           # Drift guard against frontend/lib/schema-snapshot.json
│   └── writer.py                 # Atomic writes + prune_orphan_stock_files (drops de-listed/renamed tickers' stock JSON; see CLAUDE.md §Gotchas)
├── config.py · main.py
└── cache/                        # 🚫 GITIGNORED — never commit

frontend/                         # Next.js static site (read/write OK)
├── app/                          # App Router (page.tsx · stock/[ticker]/page.tsx)
├── components/                   # React UI (RankingTable / FairPriceBarChart / AnnualReturnsTable / NavCompareChart / …)
├── lib/                          # ⚠️ types.ts · schema-snapshot.json · format.ts
├── public/data/                  # 🟡 generated by compute/main.py
└── package.json

tests/                            # pytest suite
docs/                             # Academic methodology + research findings
.claude/skills/                   # first-party + vendored skills + phase-N/ planning docs (+ symlink to the vendored impeccable skill at .agents/skills/)
.claude/agents/                   # 25 subagents (5 opus / 20 sonnet; 23 at `effort: max`, 2 at `high`: schema-sentinel + vercel-preview-auditor) — Tier 1 Core 5 (incl. stock-detail-auditor for per-stock JSON correctness) + Tier 2 Lifecycle 6 (incl. vercel-preview-auditor + expert-user-explorer for interactive end-to-end app usage) + Tier 3 Specialized 9 (incl. literature-searcher + financial-engineer for generative quant design + data-pipeline-engineer + data-analyst + data-scientist for data-layer health + analytics + ML/statistical validation) + Tier 4 Operations 3 (incl. ci-triage-engineer) + Tier 5 Builders 2 (write-capable compute-builder + frontend-builder for agent-team Feature Squads, see TEAMS.md); Claude Code only — Copilot / Cursor / Devin do not auto-route to these
.claude/hooks/                    # PostToolUse Bash hooks (log-bash.sh, schema-reminder.sh) + UserPromptSubmit hook (delegate-first.sh — orchestrator reminder + agent-team auto-propose for team-fit tasks) wired by .claude/settings.json (Claude Code only — Copilot / Cursor / Devin ignore)
.claude/worktrees/                # Harness-managed isolation dirs for Agent-tool subagents (Claude Code on the web only; per-session transient; gitignored 2026-05-22)
.claude/settings.json             # Claude Code harness config (hooks, permissions). Per-user overrides go in .claude/settings.local.json (gitignored)
.agents/skills/                   # Vendored third-party skills (skills.sh layout) — currently impeccable (pbakaus/impeccable, Apache-2.0); symlinked into .claude/skills/, dev-session tooling only (never CI). See THIRD_PARTY_NOTICES.md
.github/workflows/                # ⚠️ ask before editing
pyproject.toml                    # ⚠️ ask before deps changes

# 🚫 Never touch
compute/cache/ · node_modules/ · .next/ · dist/ · .env* · *.secret.*
frontend/public/data/             # commit only via CI compute job
```

## Code style

### Python

Ruff enforces formatting + import sort + lint rules (E / F / I / B / UP /
W; ignore `E501` since we cap at 100 chars). Run `ruff check --fix .`
to auto-fix. Do not hand-format what the linter handles.

**Pre-push lint is whole-repo, never per-file.** CI runs `ruff check .`
(no path). Running `ruff check <one-file>` for a focused diff is fine for
inner-loop iteration but is NOT the pre-push gate — a later commit on the
same branch can add a file the per-file pass never saw and it sails
through locally while CI goes red (PR #310, 2026-05-29: a test file added
in a second commit carried two `UP037` redundant-quote annotations that a
per-file lint of the first commit's production files never checked). The
last step before every push is the full ladder verbatim: `ruff check .`
then `pytest -m "not network"` (whole suite, not just the file you
touched).

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
- **LedgerCraft adoption (2026-05-22)** — `font-slab` class for
  headlines + h1/h2 surfaces (slab-serif Roboto Slab, "editorial
  finance" register); `shadow-{subtle,medium,large,overlay}` formal
  elevation tokens (replace ad-hoc `shadow-sm` / `shadow` pairs);
  `odd:bg-white even:bg-slate-50 hover:bg-slate-100` alternating-row
  pattern on data tables (`#FFFFFF / #F1F5F9` per LedgerCraft spec).
  Existing palette + OKLCH semantic colors + Plex Sans body + JBM
  numerics retained — LedgerCraft is selectively adopted for slab
  headlines + table polish, not a wholesale visual rewrite. **Phase 2
  (2026-05-22)** propagated the tokens to per-stock detail-page
  surfaces: hero card → `shadow-large`; company-name `<p>` →
  `font-slab`; FairPriceBarChart headline → `shadow-medium`;
  FairPriceBarChart method-list → `shadow-subtle`; PillarRadarChart
  container → `shadow-medium`; RawMetricsTable → `shadow-medium` + alternating
  rows. Section labels (the small `text-sm font-medium uppercase
  tracking-wide` h2s) intentionally STAYED in IBM Plex Sans — slab
  at that small uppercase size reads wrong; slab is hero-scale only.
  **Phase 3a (PR #213)** spreadsheet-polished those same section h2s
  + every table thead to the ledger pattern: `font-medium` →
  `font-semibold`, `tracking-wide` (0.025em) → `tracking-[0.14em]`,
  `text-slate-500` → `text-slate-600` — darker + heavier + wider
  letter-spacing for Excel/Numbers column-header feel.
  **Phase 3c (PR #215)** landed the LedgerCraft layout shell (`AppShell.tsx`). NOTE: the `Sidebar.tsx` left rail added here was later REMOVED (PRs #413/#414); `TopNav` is now the sole nav.
  **Phase 3b (this PR)** lands class-strategy dark mode behind
  `next-themes`. `tailwind.config.ts` flips to `darkMode: 'class'`;
  `<ThemeProvider>` (uses `next-themes`, `attribute="class"`,
  `defaultTheme="system"`) wraps `<AppShell>` so the `dark` class
  toggles on `<html>`. `globals.css` gains a `.dark` block that
  swaps the OKLCH `--c-pos-*` / `--c-neg-*` band to a brighter-
  chroma / darker-bg variant + a `.dark body` rule that flips
  background to slate-950 territory + a `color-scheme: dark`
  metadata cue. The 4-family Tailwind ramp (slate / indigo / rose /
  amber + emerald exception) gets paired `dark:` variants on every
  surface: chip families in `frontend/lib/visual.ts` (TIERS /
  MOS_BUCKETS / SECTOR_COLORS / scoreColorClasses /
  filingLagBadgeClasses), badge components (Recommendation /
  Score / MoS / LossChance), table containers (Ranking /
  RawMetrics — the former `FairPriceCard` method sub-table was removed
  PR #339, per-method values live in `FairPriceBarChart` only), cards
  (FairPriceBarChart / FairPriceCard /
  PillarRadarChart / Tier2EventCard / RiskSummaryCard /
  Disclaimer), and the two app pages (home + stock
  detail). The stock-detail SECTION ORDER is deliberate (PR #340 — see
  CLAUDE.md §Gotchas "Stock-detail section order"): hero → price →
  PillarRadarChart → Tier2EventCard → RiskSummaryCard → fair-price pair →
  raw → data-quality. Don't reorder these without re-reading that gotcha.
  (A hero "N risk vetoes" chip was tried + reverted same PR per user call —
  keep the hero quiet.) The hero's Fair-value / Target / Loss-chance values
  count-up via the `HeroMetric` client leaf (PR #342; `useCountUp` ease-in-out, 300ms
  since the $impeccable quieter pass — within the ≤320ms micro budget so the 800ms
  score-gauge sweep stays the lone >320ms beat);
  the `RecommendationBadge` is now STATIC (its chip-pop entrance was removed
  same PR — see CLAUDE.md §Gotchas "Hero metric values count-up"). Under the
  hero (own section, above the price chart) sits `HeroAttributeTiles` — a 4-box
  icon-over-label grid (Size · Sector · 2 reserved "Coming soon" placeholders —
  Dividend + Type), the theme-reskinned answer to a reference app's category
  tiles (PR #344; uses `lucide-react` icons via NAMED imports only — see
  CLAUDE.md §Gotchas "lucide-react … named imports ONLY" + "Hero attribute
  tiles"). The two reserved tiles are a roadmap item (PHASE_STATUS.md §Next
  deliverables #7 — Dividend + Security-type ingest, display-only, behind a
  `*_coverage_pct` observability cron); they auto-promote out of "reserved"
  when their schema field lands. `PillarRadarChart` reflows on mobile (PR #345):
  the bar drops to its own full-width line under the label/value text (was a
  squeezed fixed 3-col grid); the axis-tick row mirrors the same breakpoint —
  see CLAUDE.md §Gotchas "PillarRadarChart row REFLOWS on mobile".
  New `<ThemeToggle layout="icon|row">` component renders
  a three-state cycle button (system → light → dark → system) with
  `useTheme()` + a `mounted` guard to suppress the SSR-fallback
  hydration mismatch. Lives in the AppShell sticky header (icon layout). `<html suppressHydrationWarning>` on
  layout.tsx silences the harmless attribute mismatch
  `next-themes` introduces when it sets the class before paint.
  **Phase 3d (folded into the same PR)** aligns to LedgerCraft's
  canonical palette: body bg `#FAFAFA` (was slate-50 `#F8FAFC`);
  brand primary `emerald-700` (`#047857`) on the wordmark Q logo — the LedgerCraft "Primary button" pattern; OKLCH positive band shifted hue 155 →
  152 + chroma 0.09 → 0.13 (light) / 0.13 → 0.16 (dark) so the
  strong swatch sits closer to forest-green #15803D (green-700) in
  perceptually-uniform space without flipping to solid emerald-700 (#047857);
  border-radius normalization across cards — `rounded-2xl` (hero
  card) + `rounded-xl` (PillarRadarChart + FairPriceBarChart) →
  `rounded-lg` per LedgerCraft "max 8px / typical 4-6px" radius
  scale; OKLCH negative kept on dusty-rose hue 18 (NOT shifted to
  red-600 `#DC2626`) per the prior 2026-05-14 design feedback that
  rejected alarm-red intensity. Canonical hex → Tailwind class
  mapping table now in `docs/design.md` §Colors.
- **Global `overflow-x: clip` on `html, body`** (`frontend/app/globals.css`,
  PR #322): the page never scrolls horizontally — wide content nests its own
  `overflow-x-auto` (e.g. `RankingTable`'s desktop table). Keep `clip`, never
  `hidden` (`hidden` creates a scroll container and breaks the sticky header). Full rationale in CLAUDE.md §Gotchas.
- **Fluid root font-size** (`frontend/app/globals.css` `html { font-size:
  clamp(1rem, 0.89rem + 0.45vw, 1.125rem) }`, 2026-05-29): the rem-based app
  scales everything with the viewport (~16px phone → ~18px tablet+). Use
  rem-based Tailwind text utilities (`text-sm`/`text-2xl`), not arbitrary
  `text-[Npx]` (fixed px won't scale); never add a second `font-size` on
  `html`/`:root`/`body` (compounds the scale). Full rationale in CLAUDE.md
  §Gotchas.
- **Stock-detail hero splits on a CSS container query, not a viewport
  breakpoint** (`frontend/app/stock/[ticker]/page.tsx` + `globals.css`
  `.hero-card` / `@container hero (min-width: 46rem)`, PR #332): the hero's two-column (name-left / stats-top-right) vs stacked decision keys off the hero's OWN inline-size, not `md:`/`lg:` viewport prefixes (robust to future layout-chrome changes). JSX default = the stacked `flex-col`; the `@container` rule only
  ADDS the row. Don't refactor back to viewport prefixes. Raw CSS, no
  container-query plugin/dep. Full rationale in CLAUDE.md §Gotchas.
- **MoS gauge arc is sign-aware** (`frontend/components/MoSBadge.tsx`, PR #332):
  MoS ≥ 0 sweeps clockwise (like the score gauge), MoS < 0 sweeps
  counter-clockwise via `-scale-x-100` on the gauge container, with the number
  span mirrored back to stay readable. Keep both `-scale-x-100` in lockstep.
  Full rationale in CLAUDE.md §Gotchas.
- **`globals.css` soft-color overrides are an ALLOWLIST** (`frontend/app/globals.css`,
  2026-06-01): the `--c-pos-*`/`--c-neg-*` cascade remaps only the ENUMERATED
  utility classes (`.text-emerald-700`, `.bg-emerald-50/600`, `.bg-rose-50/500`,
  `.ring-rose-200`, `.text-red-700`, …). An un-listed class (notably
  `.bg-rose-600`) renders RAW alarm-red, not muted terracotta — the gap that made
  the rankings daily-change DOWN pill loud while the UP pill softened (fixed via
  the `$impeccable polish` PR by moving the pill to the outlined-light chip
  family). For any positive/negative surface use a listed class or the chip
  family; inline `style`/svg `stroke` (gauge accents) are never reached and stay
  raw rgb by design. The one soft NEGATIVE dot is `bg-rose-500`; the "Sell" +
  high-loss-chance dots + `RiskSummaryCard` severity dots (was raw
  `bg-red-500/600` / `bg-rose-600`) now use it. `PillarRadarChart`
  bar fills are raw `scoreAccentColor` rgb BY DESIGN (chart ramp + amber gap) —
  not a soft-color miss. Full rationale in CLAUDE.md §Gotchas.
- **Build-time, server-component stats — never `import lib/data.ts` into a `'use client'`
  component** (`frontend/app/page.tsx` + `frontend/app/ranking/page.tsx`, 2026-06-04): the home
  dashboard + ranking page are plain Server Components deriving every value from the
  already-imported `rankings.json` / `metadata.json` at BUILD time — QuantRank is a weekly
  static export, so they are "as of" the last cron, NOT live (the `metadata.last_update_utc`
  stamp is the anchor). A genuinely live / intra-week feed (or net-new index/commodity data) is
  a separate observability-before-wiring PR, not a tweak. The data layer (`lib/data.ts`, fs +
  JSON) must never enter the client bundle — resolve on the server, pass the node in as a
  prop/child. (Removed 2026-06-04: the top `MarketStatsBar` strip + `lib/market-stats.ts` +
  `AppShell` `topBar` slot, and the standalone `/sectors` + `/movers` routes.) Full rationale
  in CLAUDE.md §Gotchas.
- **44px touch targets + modal focus-trap + severity-toned warning headings**
  (`frontend/components/*`, 2026-06-01): primary interactive controls carry
  `min-h-[44px]` (mobile-first per PRODUCT.md); any future slide-over/modal must trap + restore focus (WCAG 2.4.3), not just Esc + scroll-lock; the
  `Tier2EventCard` / `RiskSummaryCard` `<h2>` takes a rose/amber severity tone so
  warning cards outweigh the neutral data-section eyebrows. A new control / modal
  / warning card must follow suit. Full rationale in CLAUDE.md §Gotchas.
- **Secondary / muted text = `text-slate-500 dark:text-slate-400`, never the
  inverted `text-slate-400 dark:text-slate-500`** (2026-06-01): the inverted
  token fails WCAG AA in BOTH modes (~2.6:1 light / ~3.75:1 dark); the standard
  clears both (~4.8:1 / ~7:1). slate-* is OUTSIDE the globals.css soft-override
  allowlist → check contrast on the raw hex, not an OKLCH token. Normalized
  app-wide (16 components); disabled controls + decorative `aria-hidden` icons
  stay faint by design. Full rationale in CLAUDE.md §Gotchas.
- **Stock-detail page = DECISION zone + collapsed "Supporting data" reference
  zone** (`app/stock/[ticker]/page.tsx`, 2026-06-01): raw fundamentals +
  data-quality are grouped into one native `<details>` (Server-Component-safe,
  collapsed by default, recessed slate-50 surface, `font-slab` summary that's a
  different register from the decision eyebrows). A new provenance section goes
  INSIDE it; a new decision signal goes above the fair-price pair. Don't
  re-flatten into a 12th top-level section. Full rationale in CLAUDE.md §Gotchas.
- **The home page IS the AI-pick portfolio** (`app/page.tsx`, Phase 7.0 PR-4):
  reads `backtest_pit.json` via `getAiPickData()` (fs-read + trim+round to a small
  client view-model — NEVER a static `import`; the 1.3MB artifact never ships in
  the page payload; `null` → "backtest pending"). The Server-Component page
  resolves it; the `'use client'` `AiPickPortfolio` receives it as props
  (build-time-data rule — no client component imports `lib/data.ts`). The 1-20
  holdings slider (`MAX_PICKS` in `compute/portfolio/weights.py`; backtest-only,
  not imported by the live forward compute) switches `nav.by_count[N]` (one NAV
  line per count); the chart uses the pre-aligned `nav.benchmark`, so
  `benchmarks.json` is NOT read by the frontend.
  Full rationale in CLAUDE.md §Gotchas. The `/portfolio` nav tab is labelled
  **"Watchlist"** (the coming-soon personal watchlist) to disambiguate from the
  AI-pick portfolio on Home. Selection (`compute/portfolio/weights.py`
  `select_picks`) is **top-N eligible by composite, NO sector cap** (the
  2-per-sector cap was removed 2026-06-06) — the basket can concentrate in one
  sector, so the home surfaces a "Top sector: X — N of count" disclosure;
  inverse-vol + the 0.35 cap bound single-NAME risk only. It DOES dedup
  **dual-class issuers** (`_DUAL_CLASS_GROUP`: GOOG/GOOGL, FOX/FOXA, NWS/NWSA) —
  one slot per issuer, CANONICALIZED to a fixed Class-A ticker (GOOGL/FOXA/NWSA)
  so the basket shows the SAME ticker every quarter (else one company burns two
  slots, and the two classes' near-equal composites flip which ranks higher →
  spurious GOOG↔GOOGL churn). Falls back to the held class if the canonical is
  vetoed. The backtest NAV math is **audit-verified CORRECT** (methodology-scientist
  2026-06-08: Σwᵢ·rᵢ, rebalance-seam chaining, no look-ahead leak-probe,
  cost-on-turnover-at-rebalance, PIT survivorship, benchmark rebased same-base, and
  BOTH portfolio + SPY total-return via `Adj Close` — no dividend asymmetry); the
  count=5 −10%/yr index gap is concentration + raw signal (`veto_layer_replayed=False`)
  + annual-10K + 2021-26 mega-cap regime, **~96% pre-cost, NOT a bug** (net CAGR rises
  monotonically with N and beats SPY at N≈11). So `AiPickPortfolio.tsx` renders an
  inline **count-reactive concentration caveat** beside the headline "vs index"
  number (small-N → "concentrated N-stock book — slide right to diversify, read the
  full ladder") so the divergence is never read without context; `DISCLAIMER_BASE`
  likewise clarifies the net lines charge a modeled 10-25 bps spread cost (gross only
  of ADDITIONAL market-impact slippage). A **high-conviction selection gate** drives
  the AI-pick (`financial-engineer` design → `methodology-scientist`
  RATIFY-WITH-CONDITION 2026-06-08): the basket holds ONLY Strong Buy/Buy names
  (`recommendation∈{bullish,lean_bullish}`) that are undervalued (`MoS>0`), with
  `composite≥50` + `loss-chance≤45`, fail-closed (`is_high_conviction` in
  `weights.py`). Shipped in 2 stages: **PR-1 (#437, observability)** replayed the
  valuation+recommendation layer point-in-time + COUNTED eligibles per rebalance
  (`eligible_high_conviction_count` / `meta.high_conviction_eligible_median`),
  confirming condition C1 (median 52 ≫ `DEFAULT_COUNT`); **PR-2** then wired it —
  `select_picks(gate="high_conviction")` filters then takes top-N by composite
  (default `gate="veto_only"` unchanged), `meta.high_conviction_gate_active=True`,
  sell-eviction implicit (basket rebuilt each quarter). The backtest's annual-10K
  cadence relaxes Defense #3's hard-stale ceiling to 455d FOR THE PIT PATH ONLY
  (`BACKTEST_HARD_STALE_DAYS`; live keeps `config.FILING_STALE_HARD_DAYS`=180, never
  mutated). PR-3 (the wall-free LIVE forward pick) is the deferred follow-up. The home
  also renders a
  **"Rotation history"** timeline (`HoldingsTimeline.tsx`): every quarterly
  rebalance's holdings at the current basket size, newest-first, with
  entered/exited markers, reactive to the count slider — fed by
  `AiPickData.timeline` (trimmed ticker+sector per rebalance from
  `getAiPickData()`, display-only types, no schema change). It is the
  point-in-time rotation, NOT today's picks back-projected. The weekly cron
  (`compute-rankings.yml`) now folds a warm `backfill_portfolio_pit` step after
  the compute so `backtest_pit.json` (NAV + Current picks + Rotation history)
  auto-refreshes every run — it rides the cron's existing trusted
  `git add frontend/public/data/` commit (continue-on-error + 40m step cap so a
  backtest hiccup can't block the rankings commit); `backfill-portfolio.yml`
  stays the manual on-demand path, guarded off `main`. A `trading-day-gate` job
  skips the SCHEDULED run on NYSE holidays (stdlib-only, hardcoded holiday set,
  **default-run + fail-open** so it never skips a real trading day; manual
  `workflow_dispatch` bypasses it) — so the cron runs on trading days only and
  doesn't land timestamp-only no-op commits on weekday holidays.
- **Loss-chance band/tone derives from `Math.round(pct)`, not the raw float**
  (`LossChanceBadge` + `RankingTable` mobile card + detail-hero `lossBand`,
  2026-06-01 + P2 2026-06-02): the display rounds (`HeroMetric` prints
  `${Math.round(v)}%`), so banding off the raw value showed "60% · Neutral" for
  a 59.7. The 5-band rubric is duplicated across all three — keep them in
  lockstep. P2 promoted the hero from a 3-tone collapse to the full 5-band
  `{ tone, dot, label }` object so the hero now shows the band WORD ("Neutral",
  …) under the number, matching the mobile card. Full rationale in CLAUDE.md
  §Gotchas.
- **`PillarRadarChart` tier labels share the composite `TIERS` vocabulary**
  (`frontend/components/PillarRadarChart.tsx` + `lib/visual.ts`, P3 2026-06-02):
  the pillar bars previously used a separate 4-word scheme (Strong/Decent/Weak/
  Poor at 30/50/70) that collided with the composite score's 5-tier words
  (Exceptional/Strong/Average/Weak/Poor at 25/40/55/70) — "Strong" meant two
  different ranges. The pillar now derives its tier word + color ramp + gridlines
  + legend from the SAME `TIERS` boundaries, banded off `Math.round(value)`. Do
  NOT reintroduce a second band table in the pillar. Full rationale in CLAUDE.md
  §Gotchas.
- **Detail-page a11y/clarity minors** (`MoSBadge` + `PillarRadarChart` +
  `app/stock/[ticker]/page.tsx`, 2026-06-02): the MoS donut is a `role="img"`
  with a full `aria-label` + a visible `(vs fair value)` anchor (disambiguates
  the two MoS formulas in-page); each pillar row carries an `sr-only` sector-
  median (parity with the mouse `title` + notch); the hero shows "Data as of
  {date}". `MoSCell.tsx` is orphaned dead code. Full rationale in CLAUDE.md
  §Gotchas.
- **Chip/numeric/soft-shade consistency** (`$impeccable polish`, 2026-06-02):
  every chip carries `font-medium` (SectorChip + the RankingTable toolbar chips
  were holdouts); every large number carries `font-mono` (RiskSummaryCard manip
  index was the holdout); annotate-amber bodies use `bg-amber-50`; negative-
  strong rings use the soft `-200` shade (never raw `-300`); value sub-labels use
  `tracking-wider`; sections don't add own `mb-*` (the `<article>` `space-y-4`
  owns gaps). Full rationale in CLAUDE.md §Gotchas.
- **Price chart is lazy-loaded (`PriceHistoryChartLazy`)** (`$impeccable optimize`,
  2026-06-02): Recharts (the only Recharts consumer) code-splits out of the
  stock-detail First Load via `dynamic(ssr:false)`, dropping it 214 → 110 kB
  (−49%). The Server Component page imports the LAZY wrapper, never
  `PriceHistoryChart` directly (that would pull Recharts back). Zero-CLS — the
  chart already client-fetched + showed a skeleton. Full rationale in CLAUDE.md
  §Gotchas.
- **Score gauge/caption tier WORD = canonical `scoreTierLabel`** (`ScoreGauge` +
  `ScoreBadge` + `lib/visual.ts`, 2026-06-02): both carried local `tierLabel()`
  copies on the wrong `80/60/40/20` accent boundaries, so 81 tickers (incl. top-3)
  showed the wrong composite-score tier word vs the pillar bars. Now both call
  `scoreTierLabel(<displayed value>)` (TIERS), finishing the #363 P3 consolidation.
  `scoreAccentColor` (the COLOR) stays on its own heat-signal boundaries. A new
  score-tier-word surface must call `scoreTierLabel`, never a local copy. Full
  rationale in CLAUDE.md §Gotchas.
- **Press feedback = the global `.press` utility** (`globals.css` + 23 controls
  across 7 files, `$impeccable animate` 2026-06-02): the press/tap tier the
  motion system was missing (`active:` was 0 app-wide) — `transition: transform
  130ms + colors/opacity 150ms ease-in-out` + `:active { scale(0.97) }`,
  reduced-motion guarded beside `.hover-lift`. A global class (not Tailwind
  `active:scale`) so ONE reduced-motion guard covers every target + it cleanly
  replaces a host's `transition-colors`/`-opacity`. Scope = discrete controls
  (buttons · chips · toggles · nav/back-links · pagination · CTAs · mobile
  ranking card); NOT the desktop `<tr>` or sort headers. A new interactive
  control must add `press`. Full rationale in CLAUDE.md §Gotchas.
- **Home-page header = deliberate 4-tier hierarchy** (`app/page.tsx`,
  `$impeccable bolder` 2026-06-02): headline → weight-contrasted sub-headline
  (the universe COUNT is the one figure with presence, in brand `emerald-800` —
  the single front-door accent; `-700` would fail AA at 4.08:1, `-800` = 5.23:1) → muted provenance (universe · updated · schema;
  schema demoted by POSITION, not a fainter AA-failing color) → methodology fine
  print. Product-bolder = clarity / hierarchy / one accent, not drama. Don't
  re-flatten tiers 2+3 into one gray line. Full rationale in CLAUDE.md §Gotchas.
- **Ranking-table "no matches" empty-state = the app's warm delight moment**
  (`RankingTable.tsx`, `$impeccable delight` 2026-06-02): muted `SearchX` (lucide,
  aria-hidden) anchor glyph + human heading + actionable recovery nudge +
  `animate-fade-in`. Product-delight = a SPECIFIC reached moment, warm not wacky
  (finance reads the room). A new empty/error/pending state follows the same shape
  (glyph + heading + how-to-recover); don't scatter delight onto non-empty
  surfaces. Full rationale in CLAUDE.md §Gotchas.
- **Stock-detail `<article>` = two-level spacing rhythm** (`page.tsx`,
  `$impeccable layout` 2026-06-02): `space-y-4` default (16px) + two `!mt-8`
  zone-seams (32px) above the warnings + valuation groups (squint-test: the
  prior uniform 16px read as one undifferentiated stack, worst on mobile). Only
  those 2 pairs are wrapped (article stays `space-y-4` — no hero/`<details>`
  reindent); `!mt-8` important is REQUIRED (a plain `mt-*` is overridden by
  space-y's `> * ~ *`). The warnings wrapper is gated on `hasWarningZone` (the
  exact union of both cards' null-guards) so a clean stock doesn't strand a 32px
  void. Also: `HeroAttributeTiles` reserved tiles now share the FILLED surface
  (`bg-slate-50 dark:bg-slate-800/40`) — dashed border + dimmed content
  distinguish them — so the 4-tile row no longer floats/vanishes. Full rationale
  in CLAUDE.md §Gotchas.
- **Ranking-table FLIP reshuffle is SEARCH-SCOPED** (`lib/useFlip.ts` + `RankingTable.tsx`, `$impeccable overdrive` 2026-06-02): on a search change the surviving rows slide old→new via WAAPI `translateY` (300ms, app ease-in-out, reduced-motion guarded, transform-only). `useFlip(orderKey, filterKey)` re-measures on any order change but only PLAYS when `filterKey` (the current search string) changed — NOT on a column-sort, because the paginated 50-row page turns over on sort so a sort FLIP fires on <5% of rows and reads as broken (browser-verified: sort=0, search fired 36 then 7). Every reorderable child needs `data-flip-key`; the hook skips zero-height nodes (desktop `<tbody>` no-op on mobile + vice-versa). A new search/filter dimension must be added to the `filterKey` JSON. Full rationale in CLAUDE.md §Gotchas.
- **Outlined-light chip is a PRIMITIVE — `frontend/components/Chip.tsx`**
  (`$impeccable extract` 2026-06-02): the design system's one chip pattern was a
  copy-pasted className shell across 7+ components (+ a verbatim-duplicated
  `SIZE_CLASSES` map). Now `<Chip tone size dot leading>` owns the shell + dot +
  size scale; `CHIP_BASE` / `CHIP_DOT` / `CHIP_SIZES` exports cover bespoke
  surfaces (`ScoreBadge` semibold pill, `SectorChip` inline-rgb dot) that would
  emit a conflicting utility through the props. A NEW metadata chip uses `<Chip>`;
  tones pass through verbatim (globals.css allowlist). Follow-up `$impeccable
  polish` extended the shell into `FairPriceCard` `<li>` warnings (+`font-medium`)
  and `FairPriceBarChart` tally pills/verdict badges (via `CHIP_BASE`); only the `RankingTable` selection-state chips stay bespoke (interactive toggles — though a follow-up normalized their NEUTRAL ring to the
  canonical `ring-slate-200` too: bespoke structure, shared ring shade). Neutral
  chip ring is canonically `ring-slate-200` across EVERY neutral chip now (no
  `ring-slate-300` neutral outlier remains; the surviving `ring-slate-300` is
  `FairPriceBarChart`'s muted `outlier` verdict, not a neutral chip).
  `RECOMMENDATION_CHIP_*` exports unchanged. Full rationale in CLAUDE.md §Gotchas.
- **Whole-app polish pass** (`$impeccable polish "all app"`, 2026-06-03; audited
  by `frontend-design-reviewer` + `expert-user-explorer` which built + drove the
  real app): 4 reusable rules + a batch of one-off a11y/consistency fixes.
  Reusable: (1) empty-state primary CTA is `disabled` not just styled (any modal/drawer CTA with a zero result count); (2) a labeled chip inside an `aria-label`'d
  container is `aria-hidden` (detail `<h1>` badge — but stays announced in the
  ranking table); (3) `ring-rose-300` is never a negative chip ring (`-200` only;
  RiskSummaryCard + FairPriceBarChart headline were the holdouts); (4) detail
  valuation sections own no `mb-*` (FairPriceBarChart double-gap). One-offs: `FairPriceCard` `<div>`→`<dl>`, Tier2 drop `role="status"`, HeroAttributeTiles `aria-labelledby`, CurrentPriceLine `text-rose-600→700`, ScoreBadge md `font-bold→semibold`. Verified `next build` green locally. Full rationale in CLAUDE.md §Gotchas.

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
- **Every PR records itself in the agent-doc surface.** Every PR —
  regardless of type (feat / fix / ci / docs / chore) — must leave a
  written trace of what is changing and why. **At minimum, a
  substantive entry in [`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md)**
  (the append-only side-file adopted 2026-05-24) — OR a matching
  substance edit to CLAUDE.md + AGENTS.md in the appropriate section
  (new gotcha / convention / boundary / command / connector). **Do NOT
  add a per-PR phase/schema log entry under AGENTS.md §"Phase + version
  state"** — that section was collapsed to a pointer-only redirect on
  2026-06-03 (the ~1,068-line parallel mirror was retired); per-PR
  in-flight state now lives ONLY in PHASE_STATUS_INFLIGHT.md + CLAUDE.md
  §Phase status. A genuinely new convention / gotcha / boundary / command
  still lands directly in BOTH files (real-section substance, not a phase
  log). Non-Claude runtimes (Copilot / Cursor / Devin) read AGENTS.md;
  Claude reads CLAUDE.md — they must stay in lockstep so behavior is
  consistent across agents.

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
- Editing the 15 vendored Anthropic skills under `.claude/skills/`
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
- Set `shares_outstanding` to a per-class share count for a dual-class
  ticker (GOOG/GOOGL · FOX/FOXA · NWS/NWSA in
  `MULTI_CLASS_OVERCOUNT_ALLOWLIST`) — it MUST be the SEC companyfacts
  **company-total** across all classes (ASC 260 / RATIFY-B, #374), so it
  stays class-invariant and the CIK-keyed parquet cache can't corrupt it;
  the listed line's per-class count belongs in the additive
  `shares_outstanding_listed_class` (display/checksum only, no scoring
  consumer). Ratio-1 classes only — BRK-B (1500:1) stays deferred. See
  `docs/GOTCHAS.md`.
- Propose `git tag` / `git push origin <tag>` / `gh release create`
  shell commands for release ladder — the user is **mobile-only**
  (locked 2026-05-27); always emit a pre-filled
  `https://github.com/dackclup/quantrank/releases/new?tag=...&target=...&title=...&body=...`
  URL the user taps once on their phone. Sandbox itself blocks
  tag-ref pushes (HTTP 403) so the shell pattern wouldn't work
  even with authorization. See `.claude/skills/release-tag/SKILL.md`
  §"Mobile-operator release workflow".

## Security considerations

- `EDGAR_USER_AGENT` is required for SEC EDGAR fetches. Set via env
  var. CI uses a GitHub Actions secret. Never commit.
- **Subagent model-downgrade guard.** The 22 Claude Code subagents use
  floating `model: opus` / `model: sonnet` aliases (always resolve to the
  latest). Do NOT commit a `CLAUDE_CODE_SUBAGENT_MODEL` or
  `ANTHROPIC_DEFAULT_{OPUS,SONNET,HAIKU}_MODEL` override into
  `.claude/settings.json` — it pins every subagent to a fixed (possibly older)
  version invisibly. CI's "Subagent model-pin guard" step
  (`tools/check_model_pin.py`) fails the build if one is present (the only
  benign value is `CLAUDE_CODE_SUBAGENT_MODEL='inherit'`) or if an agent pins a
  dated model ID. Per-user `.claude/settings.local.json` is gitignored and out
  of scope — a local override can't reach `main`.
- **`impeccable` skill phone-home env-vars** (vendored third-party skill,
  2026-06-01). `.agents/skills/impeccable/scripts/context.mjs` makes a
  once-daily `GET https://impeccable.style/api/version` version check (no repo
  content / paths / credentials sent — `security-reviewer` verified).
  `IMPECCABLE_NO_UPDATE_CHECK=1` disables it; `IMPECCABLE_UPDATE_HOST` overrides
  the host. The skill's `scripts/` run ONLY in a local dev agent session (no
  `package.json` / install hooks) — never in CI or the static export. See
  CLAUDE.md §Gotchas + `THIRD_PARTY_NOTICES.md` §pbakaus/impeccable.
- **`backfill-portfolio.yml` workflow_dispatch (Phase 7.0 PR-2b)** — its
  `start` / `end` inputs reach the shell ONLY via the `IN_START` / `IN_END`
  env proxies (never `${{ inputs.* }}` interpolated into a `run:` line — the
  Actions script-injection vector) and are validated by `date.fromisoformat`
  in `scripts/backfill_portfolio_pit.py` before any syscall. The job carries
  `if: github.ref_name != 'main'` so a dispatch can never commit the artifact
  straight to the protected branch; the backfill lands its data via PR review,
  and the weekly cron stays the only writer to `main`.
- **The cron cache is split into TWO `actions/cache` steps — don't re-merge**
  (2026-06-06, edgar-debugger root-cause of tier2-cold-every-run): the old
  single 11-path bundle (~250-500 MB) was too big to save reliably post-job, so
  `edgar_10k_text`/`edgar_8k` never persisted → tier2 ran cold ~80m every run.
  Now: **fast** (fundamentals/prices, `cache-v11-fast-<quarter>-<os>`;
  family bumped v5→…→v11 — current pin lives in
  tests/test_workflow_cache_coverage.py) + **slow-text**
  (edgar_10k_text/edgar_8k/edgar_form4/osap, `cache-v5-text-<os>-<run_id>` +
  prefix restore-keys so each run persists fresh text + restores last-good;
  `edgar_form4` moved fast→slow in precache-900 Phase A so a sp900 precache
  can persist midcap Form-4 — the fast bundle's exact-key save-skip discards it).
  Saturday `precache-edgar.yml` (#249) is a SECOND writer on the SAME keys
  (shared `edgar-cache-writers` concurrency group, queue-not-cancel): warm
  Saturdays exact-hit and skip the save (~free); post-eviction Saturdays eat
  the cold rebuild and SAVE so Monday's cron restores warm.
  Plus a "Stage timing summary" step (per-stage wall-clock → `$GITHUB_STEP_SUMMARY`,
  `if: always()`). Full detail in CLAUDE.md §Gotchas / docs/GOTCHAS.md.
- **CI escape-hatch env-var combo for simulate** (5 vars, all set
  together in `.github/workflows/pre-merge-prod-sim.yml`; NONE set
  in weekly cron `compute-rankings.yml`). Each is optional, fails
  open on absence (= no skip), and falls through to live fetch if
  no cached parquet exists. Cron and local dev must leave them
  unset. (The 2026-05-25 emergency `FORM4_FETCH_SKIP=1` exception on the
  weekly cron — PR #245 — was reverted via Issue #287 PR B once the tier2
  cache split #427 made the cron warm again, restoring this "none in
  cron" invariant.) The combo is the durable structural fix for the
  recurring simulate 45-min cap breach pattern (PRs #230 / #238 / #241).
  - `FORM4_FETCH_SKIP=1` — skips Form-4 bulk fetch
    (`compute/main.py:959`)
  - `QR_SKIP_TIER2=1` — skips Tier-2 10-K text + 8-K fetch
    (`compute/scoring/tier2.py:162`)
  - `QR_SKIP_FUNDAMENTALS=1` — skips fundamentals freshness gate
    (`compute/ingest/fundamentals.py` in BOTH `fetch_fundamentals`
    + `fetch_fundamentals_history`; PR #257-fix also gates the
    `_fetch_shares_from_per_filing_xbrl` multi-class dimensional
    override path)
  - `QR_SKIP_OSAP=1` — skips OSAP openassetpricing.com bulk
    download (`compute/ingest/osap.py:fetch_osap_returns`)
  - `QR_SKIP_CROSS_SOURCE=1` — skips the 502-ticker yfinance.info
    cross-source validation loop
    (`compute/ingest/cross_source.py:fetch_yfinance_market_cap`)
  - `QR_SKIP_WAREHOUSE=1` — skips the research-warehouse per-run PIT
    snapshot write (`compute/main.py` Step 13.5;
    `compute/warehouse/writer.py`); try/except non-fatal regardless.
    The Slice-2 max-history BACKFILL (`scripts/backfill_warehouse.py` +
    `backfill-warehouse.yml`) writes `row_provenance="pit_replay"` rows to
    the gitignored `data/warehouse/backfill/` (CI artifact, never committed;
    SP500-only history; the 11 `FORWARD_ONLY_FLAGS` are NULL not False).
- Pre-commit hooks run `ruff` + the schema-snapshot guard. Do not
  bypass.
- Frontend telemetry: TWO cookieless Vercel-edge client-side beacons —
  **Vercel Web Analytics** (`@vercel/analytics`, PR #517 — page-view
  counts) and **Vercel Speed Insights** (`@vercel/speed-insights`, added
  alongside #517 — Core Web Vitals). Neither persists an IP or sets a
  user ID (the source IP is transiently visible at the Vercel edge for
  geo-country inference, then dropped — not stored in the aggregate data),
  and both are served from Vercel's own edge (`/_vercel/insights/` +
  `/_vercel/speed-insights/`, not third-party CDNs). The original
  "no analytics in v1.0" pledge was lifted by explicit owner decision
  (2026-06-20). No OTHER third-party telemetry / external network beacons
  in the frontend; the site otherwise stays pure static HTML+JS. (Each
  requires its feature enabled in the Vercel dashboard or the injected
  script 404s silently.)

## Phase + version state

Canonical phase / schema / defense-layer state lives in [`CLAUDE.md`](CLAUDE.md)
§Phase status (current-state + the one in-flight entry + Next deliverables) and
the chronological log in [`PHASE_STATUS.md`](PHASE_STATUS.md) +
[`PHASE_STATUS_INFLIGHT.md`](PHASE_STATUS_INFLIGHT.md) (per-PR) +
[`docs/PHASE_STATUS_ARCHIVE.md`](docs/PHASE_STATUS_ARCHIVE.md) (drained prose).
Cross-tool agents (Copilot / Cursor / Devin / Codex): READ those files; do NOT
maintain a parallel phase log here. The former ~1,068-line mirror was collapsed
2026-06-03 (token-economy drain — it duplicated CLAUDE.md verbatim; git history
preserves it).
Schema is currently **`0.10.30-phase8pilot`** on `main` (#564 squash `62dbf4f8`, merged 2026-06-22 — Bonferroni multi-test shadow counter (Slice 8, #542): 3 new `Metadata.bonferroni_shadow_*` fields, SHADOW/OBSERVABILITY-ONLY, defense UNCHANGED at 36, methodology RATIFY-SHADOW pending); prior **`0.10.29-phase8pilot`** (#527 squash `2e45a33bf`, merged 2026-06-20 — S&P 1500 cutover Slice 4: `low_liquidity` ANNOTATE flag (<$5M ADV, Amihud 2002; rank-neutral — `valuation_warnings`, not `risk_flags`) + `compute_average_dollar_volume()` + `StockDetail.average_dollar_volume` + `Metadata.low_liquidity_annotate_count`; defense 35→36 (new annotate); rankings/scores byte-identical; dormant on sp900, lights up on sp600; methodology RATIFY-SHADOW, veto promotion deferred); prior **`0.10.28-phase8pilot`** (#519 squash `5e49dca0a`, merged 2026-06-20 — S&P 1500 cutover Slice 2: `sp1500` universe seam + small-cap coverage probe; 3 new `Metadata.smallcap_*` fields; sp600 PROBE-ONLY (label `SP1500-probe`, NOT ranked); defense UNCHANGED at 35); prior **`0.10.27-phase8pilot`** (#512 squash `78fd608423`, merged 2026-06-20 — Dividend signal PR-1: 3 new `StockDetail` fields `dividend_yield_pct`/`pays_dividend`/`payout_ratio` + `Metadata.dividend_coverage_pct` coverage canary; `_yf_info_fetch` 2-tuple → 4-tuple; rankings/scores/flags byte-identical; defense UNCHANGED at 35; +25 tests); prior **`0.10.26-phase8pilot`** (#501 squash `72ee8667d`, merged 2026-06-19 — cross-source share-count-corruption SHADOW observability PR-1; 4 new `Metadata.cross_source_corruption_*` fields; MUTATES NOTHING, defense UNCHANGED at 35). Recent no-schema-bump parallel merges (tracker-only; schema stays `0.10.29`): #514 (S&P 1500 scout) · #515 (R6 weekend-test fix) · #517/#522 (Vercel analytics) · #518/#525/#528 (pytest-cov + ingest coverage tests) · #520 (S&P 1500 Slice 5 — `cache-v11-fast` precache bump + `sp1500` dispatch; cron default was unchanged at #520 time, later flipped to sp1500 by #534) · #521 (UI polish) · #524 (Mode C) · **#531** (S&P 1500 Slice 6 — `SmallcapChip` + SML tab activation; frontend-only, NO schema bump) · **#534** (S&P 1500 cutover **Slice 7** — cron-default flip `sp900`→`sp1500` across `compute-rankings.yml` + `precache-edgar.yml` defaults + `pre-merge-prod-sim.yml` pin; `compute/main.py` lifts the Slice-2 probe-only sp600 filter so the weekday cron RANKS the full ~1504 names (`Metadata.universe` `SP1500-probe`→`SP1500`); cohort-size recompute gate widened to `in ("sp900","sp1500")`; smallcap coverage probe + russell1000-proxy sp600 guard retained; NO schema bump (stays `0.10.29`); defense UNCHANGED at 36; validation 1504 names / cold ~174 min (< 240 ceiling) / warm ~45 min (< 90) / smallcap coverage 99.67% — squash `8301b82cb`, merged 2026-06-21; the 902→~1504 production cutover) · **#533** (fix(ingest): `dividend_yield_pct` ×100 double-scaling removal — yfinance `.info["dividendYield"]` already returns percent; the #512 `×100` over-scaled 100×; adds a `>100` format-reversion guard; NO schema bump, display-field-only, rankings byte-identical) · **#537** (feat(frontend): append rotated-out "Sold" rows to the Current-picks table; frontend-only, NO schema bump). **In flight:** **Security-type ingest PR-1** (branch `claude/work-preparation-0dygyk`, issue #541 — `StockDetail.security_type: str \| None` from yfinance `fast_info.quote_type` + `Metadata.security_type_coverage_pct` coverage canary; schema bump `0.10.30`→`0.10.31-phase8pilot`; obs-first Rule 18, NO UI wiring, ADR override `TODO(#541 PR-1b)`; display-only, rankings byte-identical; defense UNCHANGED at 36) · roadmap-prep docs PR (branch `claude/roadmap-preparation-ycaqf8`) · **XBRL balance-sheet context mis-pick fix** (branch `claude/sp1500-xbrl-balance-tag-fix` — `_try_balance_tags` three-tier selection replacing the bare `get_fact()` call; fixes HASI/LGIH/GPK corrupt equity/liabilities on first sp1500 cron; NO schema bump; offline + `@network` regression tests (see CI for the count); DRAFT PR pending `quantrank-reviewer` + `--run-network` confirmation). See CLAUDE.md §Phase status + PHASE_STATUS_INFLIGHT.md.

## Claude-Code-specific tooling

Claude Code sessions for this project keep 2 MCP connectors active
(GitHub · Vercel); Supabase / Sentry / Gmail / Google Drive are toggled
OFF at user discretion until their phase needs them (the token-economy
policy that previously governed this was retired 2026-06-19;
CLAUDE.md §Connectors is canonical).
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

Claude Code also reads `.claude/settings.json` for the harness's hook
configuration. Three hooks ship today (2 PostToolUse + 1
UserPromptSubmit):

- `.claude/hooks/log-bash.sh` (PostToolUse Bash) — appends every Bash
  invocation (one line per command: `[<ISO8601-UTC>] <command>`) to
  gitignored `.claude/session.log` for per-session audit trail. Pure
  side-effect, no stdout, fail-open. Includes a `sed` pre-filter
  that redacts the value half of known secret prefixes (`ghp_*`,
  `sk-ant-api*`, `AKIA*`, `Bearer <tok>`, etc.) before logging — PR
  #229 W4 hardening.
- `.claude/hooks/schema-reminder.sh` (PostToolUse Write/Edit) — when
  Write/Edit touches any file in the Pydantic↔TS↔snapshot triple
  (`compute/output/schemas.py`, `frontend/lib/types.ts`,
  `frontend/lib/schema-snapshot.json`), emits
  `hookSpecificOutput.additionalContext` reminding the agent to run
  `python -m compute.output.schema_check` (or spawn the
  `schema-sentinel` subagent) before commit. Closes the local
  pre-commit gap left by the schema-drift CI guard.
- `.claude/hooks/delegate-first.sh` (UserPromptSubmit) — injects the
  "DELEGATE-FIRST CHECK" reminder as `additionalContext` on every
  user turn so the main agent defaults to spawning the matching
  sub-agent in `.claude/agents/` instead of doing the work inline.
  Drains the under-utilized Max-plan "Weekly · Sonnet only" pool
  (PR #223 token-economy rebalance).

**Background-run hygiene** (2026-05-31): prefer SYNCHRONOUS sub-agent
spawns and foreground Bash. A `run_in_background:true` sub-agent is
tracked by an `agentId` that a `/compact` or context roll drops from
the live transcript — the post-compact session then can't stop it, so
it sits "Running" in the Background-tasks panel billing tokens, and it
is NOT an OS process (`ps`/`pgrep` can't see it — they only see Bash).
Only background a sub-agent for a long job whose result you'll collect
in the SAME session before any compact; if it must straddle a compact,
tell the user (only they can Stop it from the panel). Background Bash
must have a deterministic exit (an `until grep -q …; do sleep …; done`
that ends in seconds) — never park a `next dev` / `tail -f` /
`while true`; if you must serve for a Playwright pass, kill it the same
turn (`ps … | grep next | awk '{print $2}' | xargs kill` — NOT a broad
`pkill`, which can catch the harness's own shell, return exit 144, and
cancel the rest of the tool batch). Full rationale in CLAUDE.md
§Gotchas "Background runs default to SYNC".

The 25 subagents under `.claude/agents/` follow the **gate-moment
auto-routing policy** in [`CLAUDE.md`](CLAUDE.md) §Auto-routing
policy — most cues fire at "ready to push" / explicit ask / signal
event, not on every edit. This is the reduced-token policy
introduced after the original "spawn-on-every-diff" rule proved
too expensive. Notable Tier 1 addition: `stock-detail-auditor` for
data correctness of per-stock JSON the frontend renders (range /
consistency / Rule 16 / known-issue overlap; deterministic prefilter
walks the universe for outliers then thorough LLM verdict on every
flagged ticker — the original ≤ 20 hard cap was lifted in PR #219;
fires post-cron + pre-release + "ตรวจ data หุ้น").

Every subagent ends its report with a parseable `HANDOFF · status=… ·
next=<DONE | SPAWN <agent>:<scope> | ESCALATE <agent>:<why> | NEEDS-USER:…>`
line so the Opus 4.8 main session composes the next step *dynamically*
from it — the documented coordination flows are canonical examples, not
an exhaustive script. See [`.claude/agents/README.md`](.claude/agents/README.md)
§Dynamic workflow.

The 25 agent prompts are kept tight (total ~3.8k lines across the 25
agent files in `.claude/agents/`) so per-spawn context cost stays bounded —
trim target is the boilerplate ("read these first" + verbose intros
+ duplicated material from CLAUDE.md / SKILL.md / AGENTS.md), NOT
the work the agent does. Hard constraints on prompt size do not
imply hard caps on output size or investigation depth. Sub-agents
on the sonnet pool (20 of 25 agents) should walk every relevant
file, list every finding, and follow every escalation lead — the
Max-plan "Weekly · Sonnet only" budget is intended for thorough
audit work and is separate from the "Weekly · all models" pool the
main session consumes. Capping a sub-agent's report length or
fan-out wastes that budget without improving signal.

Spawn frequency follows the same dual-pool discipline: sonnet
agents fire on **non-trivial edit** to their domain (schema-
sentinel on the triple, defense-layer-auditor on `compute/
scoring/*` or `compute/valuation/*`, frontend-design-reviewer on
`frontend/components/*`, etc.) — see [`CLAUDE.md`](CLAUDE.md)
§Auto-routing policy for the routing table. Opus agents
(`incident-commander` · `release-captain` · `methodology-scientist`
· `quantrank-reviewer` · `financial-engineer`) stay rare-fire on gates /
signals so they don't drain the all-models pool. "Non-trivial" = > 5 added lines
OR touches non-comment code OR adds/removes a public symbol;
comment / whitespace / single-line fixes do not trigger. A 10-min
dedup window prevents the same sonnet agent from firing twice on
an unchanged diff.

**Main agent is the orchestrator, not the laborer.** The Claude
Code main session re-frames itself as the team's tech lead — its
DEFAULT action when given a task is to identify the matching
sub-agent in `.claude/agents/` and spawn it, NOT to do the work
inline. Inline work is the EXCEPTION, acceptable only for trivial
1-Read lookups, when no sub-agent matches the task, when the user
explicitly opts out ("ทำเอง" / "inline this"), when the work IS
building the agent / hook infrastructure itself, or when
synthesizing across multiple sub-agent reports. A
`UserPromptSubmit` hook (`.claude/hooks/delegate-first.sh`)
injects this rule as `additionalContext` on every user turn so
the main agent can't lose it mid-session. Cross-tool agents
(Copilot / Cursor / Devin) do not have access to the
sub-agent / hook layer and should fall back to running the
canonical skills (`schema-check`, `verify-production-output`,
`security-check`) inline.

The three hooks are bash + `jq` only, 5-second timeout, fail-open
on missing dependencies / unwritable filesystem / empty stdin.
Copilot / Cursor / Devin do NOT execute `.claude/hooks/` — those
tools should rely on git pre-commit hooks (run `ruff` + the
schema-snapshot guard, see §Security considerations) instead.

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
  auto-loaded each session; canonical for stack / commands / phase
  status / gotchas / conventions / connectors
- [`SKILL.md`](SKILL.md) — long-form QuantRank rulebook (Rules 1-18)
- [`WORKFLOW.md`](WORKFLOW.md) — per-phase task lists
- [`PHASE_STATUS.md`](PHASE_STATUS.md) — chronological phase tracker
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) — vendor /
  license posture per third-party source
- [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) — defense layer +
  scoring + valuation method anchors against academic literature
- [`docs/design.md`](docs/design.md) — visual / design-system
  specification (LedgerCraft adoption Phase 1/2/3a as of 2026-05-22)
- [`docs/LESSONS_LEARNED.md`](docs/LESSONS_LEARNED.md) — agent-process
  dos/don'ts + per-session mistakes log (workflow / git / review discipline;
  complements CLAUDE.md §Gotchas, which owns code/domain invariants)
- [`.claude/skills/README.md`](.claude/skills/README.md) — skill index
