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
| `tests/` | pytest suite (offline + `@network` gated; see CI for current count) |
| `.claude/skills/` | 42 invocation-triggerable skills + phase planning docs. See [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for vendoring / license posture per source. |
| `.claude/agents/` | 14 project-specific subagents in 4 tiers: **Tier 1 Core** (quantrank-reviewer · schema-sentinel · defense-layer-auditor · edgar-debugger), **Tier 2 Lifecycle** (security-reviewer · frontend-design-reviewer · release-captain · phase-coordinator), **Tier 3 Specialized** (test-engineer · methodology-scientist · performance-engineer · dependency-auditor), **Tier 4 Operations** (docs-reviewer · incident-commander). Spawned via the `Agent` tool with a separate context window; see [`.claude/agents/README.md`](.claude/agents/README.md) for the routing matrix + 6 coordination flows (pre-push gate / release ladder / new-defense flow / incident response / review escalation / quarterly audit). |
| `.claude/hooks/` | Bash hook scripts wired by `.claude/settings.json`. 2 PostToolUse hooks: `log-bash.sh` (append every Bash command to gitignored `.claude/session.log`) + `schema-reminder.sh` (inject reminder when any file in the Pydantic↔TS↔snapshot triple is touched via Write/Edit). Both fail-open (missing `jq` / unwritable FS / empty stdin → exit 0). 5-second timeout each. |

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

Subagents under [`.claude/agents/`](.claude/agents/) auto-spawn on the
cues below. The main agent MUST spawn them without asking for
confirmation first — they are all read-only and their cost is bounded.
Only destructive commands a subagent *proposes* require user
authorization.

| Cue / situation | Auto-spawn | Mode |
|---|---|---|
| Edit to `compute/output/schemas.py` / `frontend/lib/types.ts` / `frontend/lib/schema-snapshot.json` | `schema-sentinel` | Parallel with the edit; report PASS/FAIL before commit |
| Edit to anything under `compute/scoring/` or `compute/valuation/` | `quantrank-reviewer` after the edit set stabilizes; `defense-layer-auditor` if `frontend/public/data/` is committed in the same PR | Sequential — reviewer first, auditor on output |
| Edit to `frontend/components/` / `frontend/app/` | `frontend-design-reviewer` | Parallel; emits Playwright matrix for user spot-check |
| Test failure under `tests/test_ingest/` OR live-run hang OR `429`/`403` from SEC | `edgar-debugger` | On-demand, only when the failure signal appears |
| Edit to `.github/workflows/*.yml` OR new dep added to `pyproject.toml` / `frontend/package.json` OR new env-var read introduced | `security-reviewer` | Pre-push |
| User says "ก่อน push" / "ready to push" / "open PR" / "mark ready" / "ตรวจก่อน push" | `quantrank-reviewer` + `phase-coordinator` Mode B | Parallel pre-push gate |
| User says "tag release" / "cut a release" / "release vX.Y.Z" / "ตัด release" / phase-epic PR just merged | `release-captain` (acts as orchestrator and spawns the others as the ladder demands) | Owns the release ladder |
| User asks to create a new `claude/*` branch from a handoff prompt | `phase-coordinator` Mode A | Before first non-trivial edit |
| Phase / sub-PR marked complete on this branch | `phase-coordinator` Mode C | After merge / on close |
| `workflow_dispatch` on `compute-rankings.yml` lands green | `defense-layer-auditor` Section A-J + Section I (Playwright) | Automatic post-cron |
| New defense flag proposed (new risk_flag in `compute/scoring/`) | `methodology-scientist` (validate paper anchor) + `test-engineer` (positive + negative tests) | Sequential — methodology first |
| Threshold / weight constant changed in `compute/scoring/manipulation_index.py` or `earnings_quality.py` | `methodology-scientist` Mode B | On the edit |
| Production code added without a corresponding test in the same PR | `test-engineer` | Pre-push |
| Weekly cron warm-cache exceeds 10 min OR p95 latency > 20s | `performance-engineer` | On detection |
| Dependabot alert lands OR new dep added to `pyproject.toml` / `frontend/package.json` | `dependency-auditor` + `security-reviewer` | Parallel |
| Any of CLAUDE.md / AGENTS.md / SKILL.md / WORKFLOW.md / PHASE_STATUS.md / README.md / METHODOLOGY.md modified | `docs-reviewer` (substance check; complements `phase-coordinator` Mode B which checks file-touch) | Parallel with the edit |
| Production cron fails / hangs / produces corrupt output, OR Vercel deploy breaks, OR schema-snapshot CI fails, OR user says "production is broken" / "site is down" / "incident" | `incident-commander` (P1; orchestrator that fans out to relevant specialists) | Immediate |
| Quarterly cohort audit scheduled date reached (next 2026-08-19) | `methodology-scientist` Mode C + `defense-layer-auditor` | Sequential — scientist drives |

### Spawn discipline

- **Spawn without asking** for read-only subagents (all 8 are
  read-only). Do not pause the user's flow with "should I spawn X?"
  — just spawn and report back.
- **Ask before authorizing the destructive command** a subagent
  proposes (e.g., `release-captain` emits `git tag` + `git push
  origin <tag>` — that command needs explicit user authorization per
  §Executing actions with care).
- **Skip auto-spawn** if the user explicitly says "skip the X agent",
  "don't review this one", "I'll handle it manually" — note the skip
  in chat and proceed.
- **De-duplicate**: if a subagent ran on the same diff within the
  last ~10 minutes and the diff hasn't moved, don't re-spawn — point
  to the prior result instead.
- **Parallel by default**: when multiple cues fire on the same edit
  (e.g., `schemas.py` + `compute/scoring/*` together), spawn the
  agents in parallel — they each have their own context window.
- **Disable per-session**: user can `/agents` → toggle off any agent
  they don't want auto-routing this session.

## Gotchas

- **`compute/cache/` is gitignored.** Cold-cache compute runs hit SEC
  EDGAR live and can take 25-50 min depending on throttling. Warm-cache
  runs finish in under 5 min.
- **`shares_outstanding` is wrong for ~12 tickers** (issue #10) — Step
  7.5 sanity guard fires `data_quality_input_corruption` on the worst
  cases. Composite scoring doesn't yet respect this flag (issue #18).
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
  Annotate-only — composite rank unaffected. Follow-up: replace
  absolute-dollar with NI/TotalAssets (size-invariant) so the
  threshold doesn't drift with universe market-cap inflation.
- **Hypothesis property-based tests** are the new defense line for
  data-shape bugs (issue #126). Pair each new shape assumption (port
  cardinality, pillar count, manifest partition) with a `@given`
  property in `tests/**/test_*_properties.py`. Don't use
  `@settings(deadline=None)` — a slow example is itself a signal.

## Phase status

Current schema **`0.9.4-phase4h.4`** · defense layer **17 declared
veto+annotate flags** of [**27 boolean flags actually emitted**](https://github.com/dackclup/quantrank/issues/130#issuecomment-4496605644)
(7 active vetoes + 10 annotates + 5 method-applicability +
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

**Phase 1 ops hardening in flight (this PR)** — surfaced by the
14-subagent full self-audit (roll-call + deep-check pass on
`claude/enable-subagents-standby-7lMN4`, 2026-05-21). Three reconciles
in one focused diff: (a) `.github/workflows/compute-monthly.yml`
`permissions: contents: write` → `contents: read` per
`security-reviewer` Section C — the workflow's only step is the
Phase-0 stub `echo`, so write perm is dead weight until Phase 5 ML
retrain lands; (b) §Conventions EDGAR_MAX_WORKERS guideline 5 → 8 to
match the PR-3d empirical bump documented inline at
`compute/config.py:34-42` (this doc was stale, not the code — the
`edgar-debugger` + `performance-engineer` audits both confirmed the
code's ~1 req/s sustained load is comfortably under the 10/s SEC
ceiling and the inline rationale is self-documenting); (c) §Gotchas
`going_concern_disclosure` FP-rate stat 10.8% → 1.0% to match the
2026-05-20 production cron (now within the Mayew 2015 1-3% band
without a confirmed code mechanism — re-audit at Q3 2026-08-19).
Deferred from this PR to keep scope tight: form4 module-load
assertion (couples with Phase 4.5e PR 2 on the peer branch);
edgar_form4 CI cache restore path (same coupling); PHASE_STATUS /
SKILL.md schema table / METHODOLOGY.md vetoes-count drift (separate
doc-reconcile PR); frontend 6-FAIL palette+null+chip-family bundle
(separate UI PR); `loss_avoidance_pattern` size-invariant follow-up
(separate recalibration PR). No compute / schema / output change.

**Next deliverables** (pick by appetite):
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
