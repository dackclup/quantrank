---
name: verify-production-output
description: Run a Section A-H verification on the most recent QuantRank compute
  output (frontend/public/data/metadata.json + stocks/*.json + rankings.json).
  Surfaces schema version + git_commit + universe_size, Tier-2 fired-flag
  inventory (deferred-mode contract checks), fair-price coverage, data-quality
  guard counts, Top-5 rotation invariants, risk-flag totals vs baseline,
  Tier-2 dict-shape spot-check, fundamentals latency p50/p95/coverage, and
  universe-size consistency. TRIGGER whenever a weekly compute run lands on
  main, after any workflow_dispatch completes, before authorizing a PR from
  Draft to Mark-Ready, before tagging a release version, or before filing
  post-merge issues — invoke even when the user just says "verify the
  output" / "looks good?" / "check the latest run" without naming a section.
  ALSO use after any change to scoring, risk-overlay, or fair-price layers
  to confirm no regression. SKIP if the user is asking about Python test
  execution against live SEC EDGAR (use network-test-runner instead) or
  about Pydantic↔TypeScript schema drift only (use schema-check instead).
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
