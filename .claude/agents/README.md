# QuantRank Subagents

> `.claude/agents/` — project-specific Claude Code subagents tuned to
> QuantRank's invariants. Subagents are spawned via the `Agent` tool
> and run in their own context window — distinct from skills under
> `.claude/skills/` (which are prompt packs invoked by the main agent
> via the `Skill` tool).

## When to use a subagent vs a skill

| Pattern | Reach for |
|---|---|
| Context-isolated work (don't pollute main session) | Subagent |
| Parallel investigation (multiple files / multiple queries) | Subagent |
| Read-only review with focused tool allowlist | Subagent |
| Single in-session expansion of project knowledge | Skill |
| Workflow harness (PR iteration, phase bump) | Skill |
| One-shot lookup / search | Direct `Read` / `Grep` |

When a task fits both, prefer the **skill** if it already exists — 47
skills are loaded each session, so the main agent already has the
trigger map. Subagents add value where context isolation or parallelism
specifically helps.

## The current set (27)

Organized into five tiers — **core** (narrow project invariants),
**lifecycle** (engineering-org roles for PR / release / phase
boundaries), **specialized expertise** (domain specialists with deep
project knowledge), **operations** (orchestrators + ops roles), and
**builders** (write-capable implementers for agent-team parallel
builds — see [`TEAMS.md`](TEAMS.md)). This is the "full enterprise dev
team" topology — every tier maps to roles a 25-person engineering org
would have:

### Tier 1 — Core (5)

| Subagent | Enterprise role analogue | Trigger | Model | Tools |
|---|---|---|---|---|
| [`quantrank-reviewer`](quantrank-reviewer.md) | Senior eng / Tech lead | Gate-only (narrowed 2026-06-11): before flipping a PR Draft → Ready, on "ready to push" / "open PR", or explicit "full review" (e.g. diff > 200 lines on `compute/scoring/`) — NOT on every edit | opus | Read, Grep, Glob, Bash |
| [`schema-sentinel`](schema-sentinel.md) | API / contract governance | When `schemas.py` / `types.ts` / `schema-snapshot.json` changes; CI schema-drift failures | sonnet | Read, Bash, Grep |
| [`defense-layer-auditor`](defense-layer-auditor.md) | QA / data observability | After scoring / valuation changes; after weekly cron lands; before PR Ready-flip on scoring touches | sonnet | Read, Bash, Grep, Glob |
| [`edgar-debugger`](edgar-debugger.md) | On-call for downstream dep | SEC EDGAR ingest test failures; live-run hangs; rate-limit / edgartools drift errors | sonnet | Read, Bash, Grep, Glob |
| [`stock-detail-auditor`](stock-detail-auditor.md) | Data-correctness reviewer | Post-cron; pre-release; "ตรวจ data หุ้น" / "check stock data correctness" / "audit the output". Deterministic prefilter surfaces outliers; LLM-judgment then walks every flagged ticker without truncation (sonnet pool intended for thorough audit work). | sonnet | Read, Bash, Grep, Glob |

### Tier 2 — Lifecycle (6)

| Subagent | Enterprise role analogue | Trigger | Model | Tools |
|---|---|---|---|---|
| [`security-reviewer`](security-reviewer.md) | AppSec engineer | Before release tags; CI workflow edits; new deps; "scan for CVE" / "ตรวจ security" | sonnet | Read, Bash, Grep, Glob |
| [`frontend-design-reviewer`](frontend-design-reviewer.md) | Design system / UI lead | Edits under `frontend/components/` / `frontend/app/`; new badge / chip / color; "doesn't match the rest" | sonnet | Read, Grep, Glob, Bash |
| [`vercel-preview-auditor`](vercel-preview-auditor.md) | Release / preview-env QA | Before Mark-Ready on UI-touching PR; after `frontend/` / `compute/output/` edit; "ดู preview" / "is deploy green?". Wraps Vercel MCP (`list_deployments` → `get_deployment_build_logs` → `get_runtime_logs` → `web_fetch_vercel_url` 3-route UA probe). Codifies CLAUDE.md §Commands "Section I forcing example" pre-Playwright pass. | sonnet | Read, Bash, Grep, Glob |
| [`expert-user-explorer`](expert-user-explorer.md) | Power user / beta tester / UX researcher | Post-cron green; pre-release; after `vercel-preview-auditor` GO on a UI PR; "ลองใช้ app" / "expert user feedback" / "UX จริง" / "is the app usable?". BUILDS + SERVES the static export locally and DRIVES headless Playwright through persona missions (value-quality screener primary; risk-checker / quant-comparer / skeptic panel). The only agent that interactively *uses* the app. Read-only — proposes issues, never files/fixes. | sonnet | Read, Bash, Grep, Glob |
| [`release-captain`](release-captain.md) | Release manager | "tag release" / "cut a release" / "release vX.Y.Z" / after phase epic merge | opus | Read, Bash, Grep, Glob |
| [`phase-coordinator`](phase-coordinator.md) | Eng-program manager / docs PM | Before branch creation; before PR open / Ready-flip; after phase / sub-PR completes | sonnet | Read, Bash, Grep, Glob |

### Tier 3 — Specialized expertise (9)

| Subagent | Enterprise role analogue | Trigger | Model | Tools |
|---|---|---|---|---|
| [`test-engineer`](test-engineer.md) | SDET / test architect | Missing test coverage; new defense / schema field without test; "add tests" / "TDD this" / "เพิ่ม test" | sonnet | Read, Bash, Grep, Glob, Edit, Write |
| [`methodology-scientist`](methodology-scientist.md) | Research scientist / domain expert | New defense flag proposed; threshold recalibration; quarterly cohort audit; "validate against literature" / "ตรวจ academic prior" | opus | Read, Bash, Grep, Glob |
| [`financial-engineer`](financial-engineer.md) | Quant strategist / financial engineer | DESIGN a new valuation method / factor / scoring pillar / defense flag; scope a roadmap phase (Phase 4-7 — factors / ML / sentiment / regime + portfolio); "ออกแบบ factor / โมเดล quant" / "should we add signal X" / "scope Phase 5". Generative-design seat — proposes the construct + academic anchor, then hands to `methodology-scientist` to ratify. Read-only; never implements code, never ships the final verdict. | opus | Read, Bash, Grep, Glob |
| [`literature-searcher`](literature-searcher.md) | Research librarian / domain-knowledge retrieval | methodology-scientist verdict cites paper outside CLAUDE.md anchor list; new defense-flag academic prior proposed; "find me the paper that says X" / "หาเปเปอร์เรื่อง Y"; SEC rule release / EDGAR filing precise citation needed. Offloads retrieval from `methodology-scientist` (opus) → judgment stays on opus, fetch stays on sonnet. | sonnet | Read, Bash, Grep, Glob, WebSearch, WebFetch |
| [`performance-engineer`](performance-engineer.md) | Performance engineer / SRE | Cron > 15 min warm-cache; per-ticker hang > 30s; p95 latency over budget; "why is the cron slow?" | sonnet | Read, Bash, Grep, Glob |
| [`dependency-auditor`](dependency-auditor.md) | Supply-chain / FOSS-license engineer | Dependabot alert; `pyproject.toml` / `package.json` change; "should I bump X?" / "CVE check" | sonnet | Read, Bash, Grep, Glob |
| [`data-pipeline-engineer`](data-pipeline-engineer.md) | Data engineer | Post-cron; pre-release; edits under `compute/ingest/**`; membership-ledger edit; a `*_coverage_pct` drop; "is the data pipeline healthy?" / "ตรวจ data pipeline". Audits ALL sources + caches + survivorship ledger + freshness + coverage + backtest artifacts holistically. DISTINCT from edgar-debugger (EDGAR-only) / performance-engineer (latency) / stock-detail-auditor (per-stock output). Read-only. | sonnet | Read, Bash, Grep, Glob |
| [`data-analyst`](data-analyst.md) | Data analyst / BI | "analyze the rankings" / "วิเคราะห์ data" / "score distribution" / "sector breakdown" / "what changed this week"; post-cron descriptive pass. Aggregate / distributional analytics over rankings.json + metadata.json (score tiers, sector breakdown, rec mix, MoS / factor distributions, Top-N composition, WoW drift). DISTINCT from stock-detail-auditor (per-ticker correctness) / methodology-scientist (academic). Read-only. | sonnet | Read, Bash, Grep, Glob |
| [`data-scientist`](data-scientist.md) | Data scientist / ML engineer | Signal predictive-power evaluation (Spearman IC · IC decay · forward returns); backtest statistical scrutiny (PBO/DSR · deflated Sharpe · leakage/look-ahead probes); `compute/validation/**` + `compute/features/**` (OSAP / Qlib / IPCA) interpretation; Phase-5 ML meta-learner scoping (purged time-series CV, baseline-first); "is this signal real?" / "overfit ไหม" / "วิเคราะห์เชิงสถิติ". The EMPIRICAL seat — financial-engineer designs → data-scientist evaluates → methodology-scientist ratifies. Read-only. | sonnet | Read, Bash, Grep, Glob |

### Tier 4 — Operations (5)

| Subagent | Enterprise role analogue | Trigger | Model | Tools |
|---|---|---|---|---|
| [`docs-reviewer`](docs-reviewer.md) | Tech writer / docs PM | CLAUDE.md / AGENTS.md / SKILL.md / WORKFLOW.md / PHASE_STATUS.md / README.md / METHODOLOGY.md touched; section header added/renamed; "review the docs" | sonnet | Read, Bash, Grep, Glob |
| [`loop-engineer`](loop-engineer.md) | Workflow / automation architect | "ออกแบบ loop / workflow ให้งานนี้" / "design a loop for X" / "set up the work-loop" / "how do we iterate to done on X" / "make this self-verifying" / "loop engineering" — when a task needs a planned plan→act→check→fix→repeat cycle, not a one-shot pass. DESIGNS the Goal → Context → Action → Check/Fix → Repeat/Review loop: a verifiable definition-of-done, each iteration's exact CHECK command from the verification ladder + FIX-routing to the owning agent, a convergence guard, and — AUTONOMOUS up to the publish boundary — a single publish gate: the act→check→fix→repeat iteration self-drives with no human between rounds, and the only human authorization is the final irreversible/outward action (push to main · merge · release tag · destructive command). Read-only — COMPOSES the loop and hands it to the orchestrator to run; never executes or spawns peers itself. | sonnet | Read, Bash, Grep, Glob |
| [`ci-triage-engineer`](ci-triage-engineer.md) | CI / build engineer on-call | GitHub Actions check fails on any open PR (webhook event); "CI failed" / "Python test red" / "build แตก" / "เช็คทำไม CI fail". Knows the CI matrix (Python lint+test · Frontend build · simulate · Vercel preview) + 10-class failure taxonomy (schema-pin-drift / ruff-I001 / F401 / F841 / dep-missing-ci-only / real-bug / simulate-45min-cap / flaky-transient / vercel-build-skew / schema-drift-CI). Read-only; proposes the one-line fix the user authorizes. | sonnet | Read, Bash, Grep, Glob |
| [`incident-commander`](incident-commander.md) | Incident commander / SRE on-call | Cron fails / hangs / produces corrupt output; Vercel deploy breaks; schema-snapshot CI guard fails; "production is broken" / "site is wrong" / "incident" | opus | Read, Bash, Grep, Glob |
| [`agent-output-verifier`](agent-output-verifier.md) | QA / verification engineer (the "จับผิด" seat) | Before the orchestrator ACTS on a high-stakes agent claim (release GO / destructive command / Mark-Ready / "Top-5 rotated correctly" / "coverage is 99%"); when two agent reports disagree; "จับผิด" / "fact-check this report" / "verify the agent's claims" / "ข้อมูลที่ ai พ่นมาถูกไหม". The cross-cutting backstop on every agent's shared failure mode — a confident, fluent, WRONG sentence. Re-derives each checkable claim from ground truth (code · output JSON · git · the academic-anchor list); per-claim CONFIRMED / REFUTED / STALE / UNSUPPORTED / UNVERIFIABLE verdict. Read-only; does NOT redo the source analysis and does NOT fix. | opus | Read, Bash, Grep, Glob |

### Tier 5 — Builders (2)

Write-capable implementers — the project's first non-test agents that
write production code. They are **team-oriented** (the `compute/**` and
`frontend/**` owners in a cross-layer Feature Squad — see
[`TEAMS.md`](TEAMS.md)) but also work as scoped write-subagents. NOT
on-edit auto-spawns: code review stays with `quantrank-reviewer` /
`defense-layer-auditor` / `frontend-design-reviewer`; these BUILD, the
others audit.

| Subagent | Enterprise role analogue | Trigger | Model | Tools |
|---|---|---|---|---|
| [`compute-builder`](compute-builder.md) | Backend SWE (Python) | Explicit "implement X in compute/"; `compute/**` owner in a Feature Squad | sonnet | Read, Bash, Grep, Glob, Edit, Write |
| [`frontend-builder`](frontend-builder.md) | Frontend SWE (TS/React) | Explicit "build the X component/route"; `frontend/**` owner in a Feature Squad | sonnet | Read, Bash, Grep, Glob, Edit, Write |

### Tier rationale

The four tiers reflect QuantRank's actual workload distribution + the
"big-org dev team" mapping:

- **Tier 1 (Core)** fires on most PRs — compute / schema / scoring
  touches happen weekly. These are the "engineers always at their
  desk" of the team.
- **Tier 2 (Lifecycle)** fires at specific lifecycle moments — release
  cuts ~monthly, security baseline scans before release, frontend
  reviews when UI is touched. These are the "function leads" who get
  pulled in at gating moments.
- **Tier 3 (Specialized)** fires at specific knowledge moments — a new
  defense flag needs a research scientist's academic-prior check; a
  cron-slowdown needs a perf engineer; a new dep needs a supply-chain
  audit; designing a brand-new quant construct (valuation method /
  factor / pillar) or scoping a roadmap phase needs the financial
  engineer. Data-layer health (ingest / cache / ledger / freshness) needs the data engineer, aggregate output analytics need the data analyst, and empirical signal/ML validation needs the data scientist. These are the "deep specialists" called in for domain depth.
- **Tier 4 (Operations)** is the orchestrator / coordinator layer —
  `docs-reviewer` keeps the project's institutional memory clean;
  `loop-engineer` is the work-loop architect — given a task it designs
  the plan→act→check→fix→repeat cycle (the Loop Engineering discipline)
  the orchestrator then runs, so iterative work converges on a
  machine-checked done-state instead of a one-shot answer;
  `ci-triage-engineer` is the reactive triager for GitHub Actions
  failures (signal-driven via the PR-activity webhook);
  `incident-commander` is the P1 conductor when production breaks; and
  `agent-output-verifier` is the cross-cutting QA backstop that
  fact-checks what the *other agents themselves* emit before the
  orchestrator acts on it (the "จับผิด" seat — every other agent can
  produce a confident-but-wrong sentence; this one re-derives the claims
  from ground truth). These map to "staff+ engineers / SRE on-call / QA"
  in a big org.
- **Tier 5 (Builders)** is the write-capable implementer layer —
  `compute-builder` + `frontend-builder` own one code layer each in an
  agent-team Feature Squad (or run as scoped write-subagents). They map
  to the "feature engineers" who build; the other four tiers review what
  they ship. See [`TEAMS.md`](TEAMS.md).

## Coordination patterns — how the team works together

The team isn't a flat list of independent agents — it's a coordinated
system where specialists escalate to each other and orchestrators
spawn parallel workers. Nine canonical flows codify the integration:

### Flow 1 — Pre-push gate (every PR before Mark-Ready)

```
User: "ready to push" / "open PR" / "mark ready" / "ตรวจก่อน push"
  │
  ▼
[main agent] spawns in parallel:
  ├─ quantrank-reviewer (MUST)         ──► Rules 1-18 + schema triple
  ├─ phase-coordinator Mode B (MUST)   ──► CLAUDE.md + AGENTS.md lockstep
  ├─ schema-sentinel (if schema touched) ──► triple drift guard
  ├─ test-engineer (if prod code added without test) ──► coverage gap
  └─ security-reviewer (if CI / deps / env-var touched) ──► secrets + CVE

If ALL PASS  → propose Mark-Ready flip; user authorizes
If ANY FAIL  → reviewer routes to the specialist who owns the fix
```

### Flow 2 — Release ladder (release-captain as orchestrator)

```
User: "tag release v1.3.0" / "ตัด release"
  │
  ▼
[release-captain] (opus) drives the ladder; spawns in parallel:
  ├─ schema-sentinel         ──► no schema drift on release commit
  ├─ defense-layer-auditor   ──► Section A-J PASS on latest output
  ├─ stock-detail-auditor    ──► per-stock data correctness (prefilter + thorough LLM verdicts for every flagged ticker)
  ├─ security-reviewer       ──► CVE + secrets baseline
  ├─ performance-engineer    ──► cron latency within budget
  ├─ dependency-auditor      ──► no new CVEs since last tag
  ├─ docs-reviewer           ──► CLAUDE.md / SKILL.md / PHASE_STATUS.md aligned
  └─ phase-coordinator Mode C ──► PHASE_STATUS + SKILL + WORKFLOW lockstep

release-captain collects all PASS → drafts release notes → emits
exact tag + GitHub-release commands → USER AUTHORIZES the push
```

### Flow 3 — New-defense flow (annotate-before-veto in motion)

```
User: "add a new flag for X"
  │
  ▼
[main agent] sequences:
  1. methodology-scientist  ──► validate paper anchor + threshold +
                                predicted firing rate + φ-correlation
  2. quantrank-reviewer     ──► review the Rule 16 implementation
                                (annotate-only on first ship)
  3. test-engineer          ──► add positive + negative case tests +
                                Hypothesis property if shape-invariant
  4. schema-sentinel        ──► if a new schema field carries the flag
  5. defense-layer-auditor  ──► after 1+ production cron, verify
                                firing-rate matches prediction
  6. methodology-scientist  ──► Mode B threshold-recalibration if
                                actual ≠ predicted
```

### Flow 4 — Incident response (incident-commander as conductor)

```
User: "production is broken" / "cron stuck" / Vercel deploy fails
  │
  ▼
[incident-commander] (opus) triages via the symptom matrix; spawns
parallel specialists:
  ├─ edgar-debugger          (if ingest hang / 429 / 403)
  ├─ defense-layer-auditor   (if output corrupt / Top-5 wrong)
  ├─ performance-engineer    (if latency over budget)
  ├─ schema-sentinel         (if schema_check fails in CI)
  ├─ dependency-auditor      (if recent dep bump suspected)
  ├─ frontend-design-reviewer (if Vercel build / render broken)
  └─ security-reviewer       (if injection / committed-secret suspected)

incident-commander synthesizes findings → mitigation plan (stop-bleed
+ root-cause-fix + recurrence-prevention) → post-mortem skeleton →
spawns 9arm-post-mortem skill for the full writeup
```

### Flow 5 — Code-review escalation chain

```
quantrank-reviewer finds an issue → escalates to specialist:

  • Schema-shape concern      ──► schema-sentinel
  • Missing test coverage     ──► test-engineer
  • Academic-prior weakness   ──► methodology-scientist
  • Latency regression        ──► performance-engineer
  • New dep concern           ──► dependency-auditor
  • Doc drift                 ──► docs-reviewer
  • Security smell            ──► security-reviewer
  • Frontend pattern break    ──► frontend-design-reviewer
  • EDGAR ingest concern      ──► edgar-debugger
```

### Flow 6 — Quarterly cohort audit (scheduled, 2026-08-19 next)

```
[methodology-scientist] Mode C (scheduled) drives:
  1. Read .claude/skills/quarterly-cohort-audit/SKILL.md expected-band table
  2. Spawn defense-layer-auditor to count current firing rates
  3. Cross-reference: within-band / over-firing / under-firing per flag
  4. Spawn performance-engineer if any firing-rate jump correlates with
     a latency change (i.e., a cron-time data shift, not a code change)
  5. Output: comment on issue #130 (rolling cohort thread)
  6. Stage follow-up PRs: threshold recalibration / dead-flag removal
     proposals → spawn quantrank-reviewer for each draft
```

### Flow 7 — Experiential UX pass (does the app actually work for a user?)

```
User: "ลองใช้ app" / post-cron green / pre-release / vercel-preview-auditor GO on a UI PR
  │
  ▼
[expert-user-explorer] (sonnet) adopts an investor persona and:
  1. Builds + serves the Next.js static export locally
     (npm ci → next build → python http.server out/)
  2. Drives headless Playwright through the persona's end-to-end mission
     (navigate → paginate → filter → sort → drill into /stock/<T> → read charts)
  3. Cross-checks each rendered value against the committed JSON
  4. Reports severity-ranked friction + a did-they-accomplish-the-goal verdict
```

Runs AFTER `vercel-preview-auditor` (the deploy is green) and completes the
correctness triad — `stock-detail-auditor` (data correct) +
`frontend-design-reviewer` (design on-pattern) + `expert-user-explorer`
(actually usable). It escalates a display-bug-given-correct-data →
`frontend-design-reviewer`, a wrong-JSON-value → `stock-detail-auditor`.
It is the only agent that *interacts* with the running app.

### Flow 8 — Quant-design flow (financial-engineer originates, validators gate)

```
User: "design a new factor / valuation method / scoring pillar" / "scope Phase 5"
  │
  ▼
[financial-engineer] (opus) produces the design proposal (problem →
academic anchor → math spec → architecture fit → annotate-before-veto
rollout → observability fields → test plan → orthogonality → footguns);
the orchestrator then sequences the gate:
  1. methodology-scientist  ──► ratify the proposed academic prior +
                                threshold (can REJECT the design)
  2. literature-searcher    ──► (if the anchor is outside the CLAUDE.md
                                list) retrieve the paper for the verdict
  3. test-engineer          ──► positive + negative + Hypothesis tests
                                once the design is ratified
  4. quantrank-reviewer     ──► review the implementation the main agent
                                + user write from the ratified design
```

This is the GENERATIVE complement to Flow 3 (new-defense flow): Flow 3
starts at validation ("add a flag for X" → methodology-scientist);
Flow 8 starts one step earlier, at design ("how should we model X" →
financial-engineer), when the construct doesn't exist yet. The designer
proposes; the validator gates; they are deliberately separate seats so
no single agent both invents and ratifies its own prior.

### Flow 9 — Output verification (don't act on a wrong claim)

```
[any agent] returns a report whose claims gate a high-stakes action
  (release GO · destructive command · Mark-Ready · "Top-5 rotated" ·
   "coverage 99%" · "threshold matches Beneish 1999")
  │           — OR two agent reports disagree
  │           — OR user: "จับผิด" / "fact-check that report" / "is that true?"
  ▼
[agent-output-verifier] (opus) re-derives EVERY checkable claim from
ground truth (code · output JSON · metadata · git · academic-anchor list):
  1. Extract atomic claims from the report
  2. Per claim → CONFIRMED / REFUTED / STALE / UNSUPPORTED / UNVERIFIABLE
  3. Quote claimed-vs-actual with the exact source for every REFUTED/STALE
  4. Verdict: TRUSTWORTHY | TRUSTWORTHY-WITH-CORRECTIONS | DO-NOT-ACT
  │
  ▼
orchestrator proceeds with the gated action ONLY on TRUSTWORTHY(-WITH-
CORRECTIONS); on DO-NOT-ACT it routes each refuted claim back to the
owning agent (a wrong number → that agent; a mis-citation → ESCALATE
methodology-scientist) and re-verifies after the fix.
```

This is the cross-cutting backstop: every other flow above produces
*claims*, and any claim can be confidently wrong. Flow 9 is the optional
"trust but verify" gate the orchestrator inserts before *acting* on a
report whose error would be expensive to undo. It is NOT run on every
agent report (that would double the team's cost) — it fires when the
stakes of acting on a false claim are high, or when reports conflict.
The verifier never fixes; it routes the fix back to the claim's owner.

### Spawn discipline (cross-cutting)

When a flow says "spawn in parallel", the main agent uses ONE Agent
tool call message with multiple Agent blocks — so the agents fire
concurrently rather than serializing. Each subagent has its own
context window, so parallel fan-out costs nothing extra in the main
session's budget.

When a flow says "sequences", each step's output feeds the next —
e.g., methodology-scientist's predicted firing rate becomes
defense-layer-auditor's verification target.

## Dynamic workflow & the Opus 4.8 orchestrator

The main Claude Code session runs on **Opus 4.8** and is the orchestrator.
The eight flows above are **canonical examples, not an exhaustive
script** — Opus 4.8 composes the next step *dynamically* from what each
agent reports, so an unexpected finding routes to the right specialist
even when no canned flow covers it. The live example from this team's
own history: `expert-user-explorer` surfaced an unrendered-`risk_flags`
bug → the orchestrator filed the issue → spawned `frontend-design-reviewer`
to scope the fix → re-spawned `expert-user-explorer` to re-validate. That
loop is not in the flow list above — it was composed on the fly.

For dynamic composition to be reliable, **every agent ends its report
with one parseable handoff line** the orchestrator routes on without
re-reading the whole report:

```
HANDOFF · status=<agent's verdict vocab> · next=<DONE | SPAWN <agent>:<scope> | ESCALATE <agent>:<why> | NEEDS-USER:<decision>>
```

- `status` uses the agent's own verdict vocabulary (PASS/FAIL/WARN ·
  GO/WAIT/NO-GO · P1/P2 severity · …).
- `next` names a **concrete sibling agent + one-line scope** when more
  work is warranted; `DONE` otherwise. Agents **propose**; they never
  spawn peers themselves — the orchestrator dispatches. Agents never
  invent follow-up to look busy.
- `NEEDS-USER` flags a decision only the user can make (a destructive
  command, an ambiguous requirement) — the orchestrator surfaces it via
  `AskUserQuestion` rather than guessing.

**Model split (why 6 opus / 21 sonnet under an Opus 4.8 main):** the
orchestrator carries cross-agent synthesis, so most agents are **sonnet**
— focused, well-scoped work handing a crisp verdict back up. The six
**opus** agents (`quantrank-reviewer` · `methodology-scientist` ·
`release-captain` · `incident-commander` · `financial-engineer` ·
`agent-output-verifier`) run on opus because their job IS
breadth-of-judgment (full-diff review · academic-prior weighing ·
release-ladder orchestration · P1 incident triage · generative quant
design · adversarial cross-checking of another model's output) that
doesn't compress to a sonnet pass. `agent-output-verifier` is opus on
purpose: catching a fluent, confident, wrong sentence that a capable
model produced needs at least as much reasoning headroom as producing
it did. Sonnet agents also drain the separate Max-plan
"Weekly · Sonnet only" pool (see [`CLAUDE.md`](../../CLAUDE.md)
§Spawn discipline).

**Effort: 25 of 27 agents run at `effort: max`** (frontmatter; set 2026-05-31,
carve-out 2026-06-03). The `effort` field is orthogonal to `model` — `model`
picks WHICH model (opus / sonnet), `effort` sets how hard it reasons. `max` is
the top of the `low / medium / high / xhigh / max` ladder and overrides the
session's inherited effort while the subagent is active. Rationale: most agents
are open-ended correctness / judgment gates (review · audit · academic
validation · design), so the extra reasoning headroom pays back — and
sonnet-at-max still drains the separate Sonnet-only pool rather than the
all-models pool. **The two carve-outs at `effort: high` are the deterministic
script-runners — `schema-sentinel` (runs `schema_check`, reports the diff) and
`vercel-preview-auditor` (runs a fixed Vercel MCP chain, reports GO/WAIT):**
they follow a fixed procedure, so max reasoning is wasted; `high` saves
thinking tokens per spawn at no capability cost (token-economy drain,
2026-06-03). A NEW agent should carry `effort: max` too (authoring convention #3
below). If an agent is a pure mechanical lookup where max is wasteful, drop it
to `high` deliberately
and note why.

## How auto-invocation works

Claude Code reads the `description:` line of each agent file AND
[`CLAUDE.md` §Auto-routing policy](../../CLAUDE.md#auto-routing-policy)
on every session start. The combination gives the main agent two
levels of routing strength:

- **MUST-invoke agents** — `schema-sentinel`, `quantrank-reviewer`,
  `phase-coordinator`, `release-captain`, `ci-triage-engineer`,
  `incident-commander`, `methodology-scientist`, and
  `agent-output-verifier` (the last gates ACTING on a high-stakes agent
  claim / a release GO / a Mark-Ready / merge flip / two reports
  disagreeing — reinforced every turn by the `verify-claims.sh`
  UserPromptSubmit hook). The description uses "MUST be invoked (no
  confirmation)" language; the main agent spawns them automatically
  without pausing the user's flow.
- **PROACTIVELY-invoke agents** — `defense-layer-auditor`,
  `edgar-debugger`, `security-reviewer`, `frontend-design-reviewer`.
  The description uses "Use PROACTIVELY when..." language; the main
  agent spawns them when the trigger keywords match, but they're not
  hard-gating.

The descriptions in this set use the **TRIGGER when / Use PROACTIVELY
/ MUST be invoked** pattern (mirroring the project's vendored-skill
description sharpening from PR #157) so the main agent picks them up
on the relevant cues:

Core tier:
- `quantrank-reviewer` fires at gate cues only (push intent / Mark-Ready / explicit "full review" — not on edits)
- `schema-sentinel` fires on schema-triple cues
- `defense-layer-auditor` fires on "verify the output" / scoring-edit cues
- `edgar-debugger` fires on EDGAR / ingest / throttling cues

Enterprise tier:
- `security-reviewer` fires on release-tag / CI-workflow-edit / new-dep cues
- `frontend-design-reviewer` fires on `frontend/components/` diff cues
- `release-captain` fires on "tag release" / "cut release" cues
- `phase-coordinator` fires on branch / PR-open / phase-completion cues

Operations tier:
- `agent-output-verifier` fires (MUST-invoke) before ACTING on a high-stakes
  agent claim — release GO / Mark-Ready / merge / destructive command / two
  reports disagreeing — and on "จับผิด" / "fact-check this report"; the
  `verify-claims.sh` UserPromptSubmit hook keeps the verify-before-acting
  reflex top-of-mind every turn. NOT per-report (cost).

The user can also invoke any subagent explicitly: "use the
defense-layer-auditor to check the latest run", and the main agent will
spawn it with that scope.

### Wrap-don't-duplicate pattern

Enterprise-tier agents do NOT re-implement the project's existing
skills — they **wrap** them as auto-routing surfaces. Each enterprise
agent's first action is to read the corresponding skill's `SKILL.md`:

| Enterprise agent | Wrapped skill(s) |
|---|---|
| `security-reviewer` | `.claude/skills/security-check/` |
| `frontend-design-reviewer` | `.claude/skills/frontend-design-system/` |
| `release-captain` | `.claude/skills/release-tag/` (delegates to `phase-coordinator` for doc bumps) |
| `phase-coordinator` | `.claude/skills/branch-collision-check/`, `claude-md-lockstep-check/`, `phase-status-bump/` |

This keeps the skills as the source-of-truth playbooks. When the skill
updates, the subagent benefits automatically because it reads the skill
each invocation.

## Authoring conventions (when adding a new subagent)

1. **One job per agent.** A reviewer doesn't also write tests; a debugger
   doesn't also fix code. Read-only by default; promote to write only when
   the task inherently requires it.
2. **Sharp `description:`.** Match the vendored-skill TRIGGER discipline
   from `THIRD_PARTY_NOTICES.md` "Description divergence" — concrete
   keywords ("verify the output", "ตรวจ output", "check the latest run"),
   false-positive guardrails, and a fail-fast verdict format.
3. **Model selection (this project uses `opus` + `sonnet` only — no `haiku`):**
   - `sonnet` — default for deterministic checks (schema drift) AND
     multi-step audits with judgment (defense scorecard, debug).
   - `opus` — full code review where breadth + nuance matter (one or
     two passes over a multi-file diff, weighing project-specific
     conventions against the change).
   - **`effort: max` on judgment-gate agents** (the `effort` frontmatter
     field, orthogonal to `model`). 25 of 27 agents run at the top
     reasoning level; the 2 deterministic script-runners (`schema-sentinel`
     + `vercel-preview-auditor`) sit at `effort: high` — see §Effort above.
     A new agent gets `effort: max` too unless it's a pure mechanical
     lookup (then `high`, with a note). See §Model split above.
4. **Tool allowlist.** Restrict to what the agent actually needs. A code
   reviewer doesn't need `Edit` or `Write`; an auditor doesn't need
   `Edit` either. Explicit allowlists reduce blast radius.
5. **Project anchoring.** Every subagent references the relevant
   `CLAUDE.md` section + the corresponding skill so it stays aligned
   with the project's invariants as those evolve.
6. **Output format pinned.** Always specify the exact reply shape — the
   user is going to act on the agent's output, not read it as prose.

## Companion docs

- [`TEAMS.md`](TEAMS.md) — agent-team recipes (the collaborative,
  multi-session complement to these report-back subagents) + the two
  write-capable builders' team protocol
- [`CLAUDE.md`](../../CLAUDE.md) §Conventions — project invariants
- [`AGENTS.md`](../../AGENTS.md) §Boundaries — what subagents may / must
  not do
- [`SKILL.md`](../../SKILL.md) — Rules 1-18 (the invariants every
  subagent enforces)
- [`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md) — vendor /
  license posture for any future vendored subagents (none today)
