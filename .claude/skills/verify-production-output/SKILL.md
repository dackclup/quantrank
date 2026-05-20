---
name: verify-production-output
description: >
  Run a Section A-H verification on the most recent QuantRank compute
  output (frontend/public/data/metadata.json + stocks/*.json +
  rankings.json). Surfaces metadata fields, Tier-2 fired-flag
  inventory, fair-price coverage, data-quality guard counts, Top-5
  rotation invariants, risk-flag deltas vs baseline, fundamentals
  latency p50/p95, and universe-size consistency. TRIGGER whenever a
  weekly compute run lands on main, after any workflow_dispatch
  completes, before authorizing a PR from Draft to Mark-Ready, before
  tagging a release, after any change to scoring / risk-overlay /
  fair-price layers, or when the user just says "verify the output" /
  "looks good?" / "check the latest run" / "ตรวจ output" / "เช็ค
  production" — invoke even without naming a section. SKIP if the
  user is asking about Python test execution against live SEC EDGAR
  (use network-test-runner) or schema drift only (use schema-check).
---

# verify-production-output

A read-only scan of the most recent compute output. Produces an A-H report
mirroring the verification template used in PR-3c run #11 and PR-3d run #15.

## When to use

Invoke whenever fresh JSON output from a compute run lands. The skill never
edits any output — it only inspects and reports — so it is safe to run
liberally during release gates.

Practical triggers:

- A weekly cron compute job auto-commits new JSON on main
- A manual `workflow_dispatch` finishes and the chore commit auto-lands
- A scoring / risk / fair-price PR is about to flip Draft → Ready
- A release tag is about to be cut (`v0.X.Y-phaseN`)
- The user is about to file post-merge follow-up issues and wants a final
  health snapshot

## What it produces

An A-H section report. Each section answers a specific health question:

| Section | Question | Hard failure trigger |
|---|---|---|
| A | Schema bumped? Coverage / latency healthy? | schema version doesn't match in-flight phase |
| B | Tier-2 fired-flag counts within expectations? | `non_reliance_filing` or `auditor_change` > 0 while feature flag is False |
| C | Fair-price + data-quality coverage | fair-price coverage < 95% |
| D | Top-5 composition (raw + effective + entered/exited) | rotation invariant violated |
| E | Risk-flag totals vs baseline | unexpected delta beyond drift |
| F | Tier-2 dict-shape spot-check (5 random tickers) | dict missing any of 5 required keys |
| G | Fundamentals resilience (p50/p95/coverage) | coverage < 80% (ship anyway, file Phase 4 priority) |
| H | Universe-size consistency across 3 files | mismatch beyond expected delisting delta |
| I | **Live UI visual spot-check via Playwright** (REQUIRED 2026-05-17) | new UI surface fails to render against live production data |

## Running

```bash
python .claude/skills/verify-production-output/helper.py
```

Optional flags:

```bash
# Compare against a prior run's metadata
python .claude/skills/verify-production-output/helper.py --baseline-commit=8a9d35f

# Strict mode — exit 1 on any soft warning
python .claude/skills/verify-production-output/helper.py --strict

# Pick a different random seed for Section F (default: 42, reproducible)
python .claude/skills/verify-production-output/helper.py --seed=7
```

The helper is pure stdlib + the repo's already-imported `json` / `glob` —
no extra installs needed.

## Reading the output

The report uses three severity markers so a glance tells you whether to
proceed:

- `✓` healthy
- `⚠` soft warning (ship but log)
- `✗` hard failure (do not ship; investigate)

### Hard contract checks (Section B + Section H)

These must pass for the deferred-mode contract to hold and for the
universe to be consistent:

- **Section B**: `non_reliance_filing` count = 0, `auditor_change` count = 0
  while `_EIGHT_K_DEFENSES_ENABLED = False` (current Phase 3d state).
  If either fires non-zero the feature flag is broken — halt and
  investigate `compute/scoring/tier2.py`.
- **Section H**: `metadata.universe_size` == `len(rankings.json.stocks)`
  == `len(glob frontend/public/data/stocks/*.json)`. Mismatch ≥ 2 means
  a writer regression.

### Soft warnings (Section A, C, G)

These signal degraded quality but do not block release. They feed Phase 4
priorities:

- A: `fundamentals_latency_p95_seconds > 15s` → SEC API throttled
- C: `fair_price` coverage 80-95% → some method outputs nulled out
- G: `fundamentals_coverage_pct < 80%` → file Phase 4 SEC-resilience issue

### Top-5 churn (Section D)

The raw top-5 (by composite score) may differ from the effective top-5
(after veto suppression). Both are reported. Comparison against the
`--baseline-commit` reveals composition churn.

### Live UI visual spot-check (Section I — REQUIRED 2026-05-17)

The static A-H scan reads JSON only. Whenever a workflow run lands a
schema bump or a new UI surface (e.g., PR 4.5f
`ManipulationRiskCard`, PR 3d `Tier2EventCard`), the JSON contract can
still pass A-H while the live page fails to render — wrong type
binding, missed `== null` vs `=== null` guard for legacy fields, CSS
class typo. Section I closes that gap with a one-shot Playwright pass
against the live Vercel deployment.

**Mandatory after every `workflow_dispatch` that lands a schema bump
or new component on main.** Optional but recommended after pure
data-refresh runs (no schema or UI change) — useful for catching
upstream data drift that propagates into the rendered page.

#### Step 1 — Vercel MCP deploy health (added 2026-05-17)

Before launching Playwright, do the cheap MCP pass:

1. `mcp__vercel__list_deployments` (project=quantrank, limit=3) →
   confirm the most recent deploy is `state=READY` and matches the
   `git_commit` you expect to verify
2. `mcp__vercel__get_deployment` on the matching deployment ID →
   confirm no build error, build duration is in the normal band
   (~30-60 s for a typical compute-output chore commit)
3. `mcp__vercel__get_deployment_build_logs` → grep for `error` /
   `failed` / `module not found` / `Type error` — Phase 4.5f's
   `toFixed()` regression on undefined would surface here as a
   TypeScript build error
4. `mcp__vercel__get_runtime_logs` (if any 4xx/5xx) → catch
   server-side rendering hiccups even though we ship static export

This 4-call MCP pass takes ~10 seconds and rules out 90% of the
"deploy is broken" cases before paying the ~30-60s Playwright
browser-launch cost. **If any step in this MCP pass shows a hard
failure, fix the deploy first; do not proceed to Step 2.**

#### Step 2 — Playwright 4-ticker visual matrix

If Step 1 is clean, run the live Playwright spot-check below. This
is the part Vercel MCP cannot replace — actual rendered chip colors,
card heights, MoS/CAG/recommendation badge visibility against the
forced-light background.

Minimum spot-check matrix — pick 4 representative tickers per the
PR's UI change:

1. **Worst-case stack** (e.g., SMCI for the manipulation cluster) —
   the new surface should render its loudest state
2. **Mid-band stock** (e.g., NVDA) — mid-severity render
3. **Boundary stock** (e.g., index = 3, just above the "render-if > 0"
   threshold) — confirm the guard doesn't false-negative
4. **Top-of-leaderboard clean stock** (e.g., CF rank #1) — confirm
   the surface either renders quietly or hides cleanly

For each ticker, capture: card-present boolean, the headline number,
the band-label chip, the per-flag / per-component drill-down count
+ first three labels, the penalty / qualifier text, and a
full-page screenshot to `/tmp/preview_<ticker>.png`.

Send all 4 screenshots to the user (status="normal") and read the
worst-case one back inline to confirm the design-system colors
(rose for HIGH, amber for MODERATE, emerald for LOW) actually
render against the live light-mode background — the PR #70
regression class (invisible `dark:text-*` on forced-light background)
is the failure mode this catches.

**Sandbox / browser-version caveat**: the system Playwright pkg often
ships ahead of the bundled Chromium revision under
`/opt/pw-browsers/`. If `playwright install chromium` is a no-op
(silent failure on outbound download), launch with an explicit
`executable_path` pointing at the existing
`/opt/pw-browsers/chromium-<rev>/chrome-linux/chrome` binary +
`args=["--no-sandbox"]`. Use `ignore_https_errors=True` on
`new_context()` because the sandbox typically doesn't trust public
CAs.

#### Step 3 — Sentry error surface (forward-looking, not yet wired)

Once the `@sentry/nextjs` SDK is wired in a follow-up PR, the final
Section I step will be: `mcp__sentry__list_recent_issues` (filtered
to the last 30 minutes since the workflow_dispatch) → confirm no new
issue groups appeared after the deploy. **Until that PR lands,
Step 3 is skipped — Section I is Steps 1 + 2 only.** Track Sentry SDK
wiring as part of Phase 5+ onboarding.

## Why this skill exists

QuantRank ships JSON output that the UI consumes directly. A buggy compute
run that lands on main flows immediately into production UI within minutes
of the chore-commit push. The cost of catching anomalies pre-release is
near-zero (this scan runs in under 2 seconds); the cost of shipping a
ranking with SPG at $1.62M market cap (PR-3d run #15 finding, issue #18)
is real reputational damage to the rankings layer. This skill is the
safety net.

## What this skill does not do

- It does not run pytest, ruff, or any other code-quality tool. Use
  `network-test-runner` for live SEC EDGAR tests.
- It does not regenerate the schema snapshot. Use `schema-check`.
- It does not tally the defense layer in isolation. Use
  `defense-scorecard` for a focused vetoes / guards / annotates report.
- It does not modify any output JSON, ever.

## Related skills

- `schema-check` — Pydantic ↔ TypeScript drift gate
- `defense-scorecard` — vetoes / guards / annotates tally
- `top5-rotation-audit` — deep dive on entered_top5 / exited_top5 invariants
- `pr-iteration-flow` — codifies the broader Draft↔Ready review pattern
  this skill plugs into
