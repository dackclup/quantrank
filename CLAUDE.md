# CLAUDE.md

QuantRank is a static-site US-equity ranking tool. Python compute layer
generates JSON; a Next.js static site renders it. Currently ranks the
S&P 500 (universe = 502 after one delisting). See
[`README.md`](README.md) for the user-facing pitch and
[`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) for the academic
backing.

## Stack

- **Python 3.11+** — pandas 2.2 · edgartools 5.31 · pydantic 2.6 ·
  tenacity 8.2 · BeautifulSoup 4 · lxml 5 · pytest 8 · ruff 0.4
- **Next.js 14.2** (App Router, static export) — React 18.3 ·
  TypeScript 5.4 · Tailwind 3.4 · Recharts 2.12. Self-hosted fonts
  via @fontsource: **IBM Plex Sans** (body) · **JetBrains Mono**
  (tabular numerics) · **Instrument Serif** (display marquee) ·
  **Roboto Slab** (headlines, LedgerCraft adoption Phase 1 PR #211
  2026-05-22; Phase 2 propagated tokens to per-stock detail-page
  surfaces same day).
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
| `tests/` | pytest suite (offline + `@network` gated; see CI for current count) |
| `.claude/skills/` | 43 invocation-triggerable skills + phase planning docs. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for vendoring / license posture per source. |
| `.claude/agents/` | 15 project-specific subagents in 4 tiers + 1 data-correctness reviewer: **Tier 1 Core** (quantrank-reviewer · schema-sentinel · defense-layer-auditor · edgar-debugger · **stock-detail-auditor**), **Tier 2 Lifecycle** (security-reviewer · frontend-design-reviewer · release-captain · phase-coordinator), **Tier 3 Specialized** (test-engineer · methodology-scientist · performance-engineer · dependency-auditor), **Tier 4 Operations** (docs-reviewer · incident-commander). Spawned via the `Agent` tool with a separate context window; see [`.claude/agents/README.md`](.claude/agents/README.md) for the routing matrix + 6 coordination flows (pre-push gate / release ladder / new-defense flow / incident response / review escalation / quarterly audit). |
| `.claude/hooks/` | Bash hook scripts wired by `.claude/settings.json`. 2 PostToolUse hooks: `log-bash.sh` (append every Bash command to gitignored `.claude/session.log`) + `schema-reminder.sh` (inject reminder when any file in the Pydantic↔TS↔snapshot triple is touched via Write/Edit). Both fail-open (missing `jq` / unwritable FS / empty stdin → exit 0). 5-second timeout each. |
| `.claude/worktrees/` | Harness-managed isolation dirs for subagents spawned via the `Agent` tool with `isolation: "worktree"`. Per-session, transient, **gitignored** (added 2026-05-22 post the 3-PR fan-out so they don't show up as untracked on the main worktree's `git status`). Never commit them. |

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

**After every `workflow_dispatch` green** (REQUIRED 2026-05-17): run
Section A-H scan + Section I Playwright spot-check for any PR landing
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
  chore). At minimum a §Phase status note (PR in flight) or a
  section update (new gotcha / convention / connector / layout /
  command). Reject PRs that touch code / workflows / schemas without
  the matching CLAUDE.md + AGENTS.md diff.

## Auto-routing policy

Subagents under [`.claude/agents/`](.claude/agents/) auto-spawn on
the cues below — **lean-by-design**. Most cues fire at GATE moments
(`ready to push` / explicit ask / signal event), **not on every
edit**. Each spawn costs a separate context window; the policy keeps
that cost bounded while preserving the safety net at decision
points. The hook layer covers per-edit reminders that don't need
LLM judgment.

The main agent MUST spawn without asking for confirmation — all
subagents are read-only. Only destructive commands a subagent
*proposes* require user authorization.

**Edits alone do NOT auto-spawn.** Editing `schemas.py` /
`compute/scoring/` / `frontend/components/` / docs no longer fires
an agent on the edit. The schema-triple hook covers Pydantic ↔ TS
reminders; everything else batches into one parallel review at
"ready to push". This is the change vs the original wide policy
that fired per-diff.

| When | Auto-spawn | Notes |
|---|---|---|
| Test failure under `tests/test_ingest/` OR live-run hang OR `429`/`403` from SEC | `edgar-debugger` | Signal-driven, on-demand |
| Weekly cron warm-cache > 10 min OR p95 latency > 20s | `performance-engineer` | Signal-driven, on detection |
| Dependabot alert lands OR new dep added to `pyproject.toml` / `frontend/package.json` | `dependency-auditor` + `security-reviewer` | Signal-driven, parallel |
| Production cron fails / hangs / produces corrupt output, OR Vercel deploy breaks, OR schema-snapshot CI fails, OR user says "production is broken" / "site is down" / "incident" | `incident-commander` (P1; orchestrator that fans out to relevant specialists) | Immediate |
| `workflow_dispatch` on `compute-rankings.yml` lands green | `defense-layer-auditor` Section A-J + Section I (Playwright) + `stock-detail-auditor` (per-stock data audit) | Auto post-cron, parallel |
| Quarterly cohort audit scheduled date reached (next 2026-08-19) | `methodology-scientist` Mode C + `defense-layer-auditor` | Scheduled, sequential |
| New defense flag proposed (new risk_flag in `compute/scoring/`) | `methodology-scientist` (validate paper anchor) + `test-engineer` (positive + negative tests) | Rare; sequential — methodology first |
| Threshold / weight constant changed in `compute/scoring/manipulation_index.py` or `earnings_quality.py` | `methodology-scientist` Mode B | Rare; on the edit |
| User says "ก่อน push" / "ready to push" / "open PR" / "mark ready" / "ตรวจก่อน push" | `quantrank-reviewer` + `phase-coordinator` Mode B. Conditional batch-mates on the same gate: `schema-sentinel` if schema triple touched · `defense-layer-auditor` if `compute/scoring/` or `compute/valuation/` touched · `frontend-design-reviewer` if `frontend/components/` or `frontend/app/` touched · `docs-reviewer` if any of the 7 docs modified · `security-reviewer` if `.github/workflows/` or new env-var or new dep touched · `test-engineer` if production code added without a test | Parallel pre-push gate; one report cycle |
| User says "ตรวจ data หุ้น" / "check stock data correctness" / "audit the output" / "verify the output" / "ตรวจ output" / pre-release | `stock-detail-auditor` (deterministic prefilter caps LLM-judgment at ≤ 20 tickers) | One sonnet spawn, bounded |
| User says "tag release" / "cut a release" / "release vX.Y.Z" / "ตัด release" / phase-epic PR just merged | `release-captain` (orchestrator; spawns ladder agents as needed) | Owns release ladder |
| User asks to create a new `claude/*` branch from a handoff prompt | `phase-coordinator` Mode A | Before first non-trivial edit |
| Phase / sub-PR marked complete on this branch | `phase-coordinator` Mode C | After merge / on close |
| Diff > 200 lines on `compute/scoring/` OR user says "full review" / "deep review" | `quantrank-reviewer` with `model: opus` override | Rare; user authorization required |

### Spawn discipline

- **Default model = sonnet.** Opus only for cross-domain
  orchestration (`incident-commander`, `release-captain`),
  literature-heavy validation (`methodology-scientist` on new flag
  / threshold), or large-diff reviews (`quantrank-reviewer` with
  explicit user authorization for the opus override). 5 agents
  currently default to opus by design; the rest are sonnet.
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
  recovery path now via `_fetch_shares_from_per_filing_xbrl` shipped
  in this PR. Root cause: SEC's `companyfacts` aggregate API filters
  out dimensional facts; STZ files share counts only with
  Class A / Class B dimensions. The fallback pulls per-filing XBRL
  (`Filing.xbrl().facts.get_facts_by_concept`) for the most recent
  10-K / 10-Q and sums the dimensional `dei:EntityCommonStockSharesOutstanding`
  contexts. Triggered ONLY when the primary extraction returns
  ``None`` AND `revenue > 0` AND `total_assets > 0` (PR-#181
  signature); blast radius on the 2026-05-14 cron is 1 ticker, so the
  extra HTTP cost is bounded.
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

## Phase status

Current schema **`0.10.0-phase4.5e`** · defense layer **20 declared
veto+annotate flags** of [**30 boolean flags actually emitted**](https://github.com/dackclup/quantrank/issues/130#issuecomment-4496605644)
(7 active vetoes + 13 annotates + 5 method-applicability +
5 informational; epic [#150](https://github.com/dackclup/quantrank/issues/150)
Phase 2 splits the method-applicability flags out of `manipulation_index`).
Plus 5 numerical guards + `manipulation_index` rollup. Latest release
tag [**`v1.2.0-phase4.5`**](https://github.com/dackclup/quantrank/releases/tag/v1.2.0-phase4.5)
(2026-05-17, `6d414a9b`).

**Recently merged**:
- [PR #154](https://github.com/dackclup/quantrank/pull/154) —
  Epic #150 Phase 1.2: defense layer headline count reconcile 17 → 27
  (declared veto+annotate flags PLUS method-applicability + informational
  flags from the [2026-05-20 quarterly audit](https://github.com/dackclup/quantrank/issues/130#issuecomment-4496605644))
- [PR #153](https://github.com/dackclup/quantrank/pull/153) —
  Epic #150 Phase 1.3: pre-merge-prod-sim workflow dogfood (composite.py
  docstring cross-ref; sticky comment + diff table verified end-to-end)
- [PR #151](https://github.com/dackclup/quantrank/pull/151) —
  Phase 0 of epic #150: Known Limitations + pillar label clarification
- [PR #149](https://github.com/dackclup/quantrank/pull/149) —
  verify-helper Section B post-PR-#79 stale expectations (closes #117)
- [PR #148](https://github.com/dackclup/quantrank/pull/148) —
  Pre-merge production simulation PR 2 (composite diff + top-10 movers,
  closes Epic #125 Item 3)
- [PR #147](https://github.com/dackclup/quantrank/pull/147) —
  PHASE_STATUS.md "Current state" summary block hoist (Optimization PR G)

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
(Bartov-Lai-Yeung 2002 — surfaced as a CORRECTION during the
methodology-scientist audit; the hand-off had labeled it
Cohen-Malloy-Pomorski 2012 but the actual anchor is BLY 2002).
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

**Next deliverables** (pick by appetite):
- **Issue #67 flip PR** — `USE_SECTOR_COE = True` after ≥ 1 cron confirms
  delta-flag-count (target: `value_trap_risk` drops from ~176 toward ~80-110)
- **Phase 4.5e PR 3** — `insider_sell_cluster` + `c_suite_unusual_sell`
  annotate emit + threshold calibration against PR-2 cron data
- **Phase 4.5e** — Form 4 insider clustering (~3w → v1.3.0; weight
  slots already declared in `FLAG_WEIGHTS`)
- **Phase 4i.1 / 4j.1 / 4k.1** — JKP / Qlib / IPCA integration PRs
  (~1-2w each → v1.1.0-phase4)
- **Phase 5** — ML meta-learner (~10-12w, unblocks PR 4b §3
  IC-decay writer #75)

See [`PHASE_STATUS.md`](PHASE_STATUS.md) for the canonical
chronological tracker.

## Companion files

- [`AGENTS.md`](AGENTS.md) — cross-tool agent instructions (Copilot /
  Cursor / Devin) + multi-session audit pattern detail
- [`SKILL.md`](SKILL.md) — long-form QuantRank rulebook (Rules 1-18 +
  schema-version table + library matrix)
- [`WORKFLOW.md`](WORKFLOW.md) — per-phase task lists, decision points
- [`PHASE_STATUS.md`](PHASE_STATUS.md) — chronological phase tracker
- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) — vendor / license
  posture per third-party source
- [`.claude/skills/README.md`](.claude/skills/README.md) — skill index
