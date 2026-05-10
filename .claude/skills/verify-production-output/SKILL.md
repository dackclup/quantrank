---
name: verify-production-output
description: Run a Section A-H production verification on the most recent compute
  output (frontend/public/data/metadata.json + stocks/*.json + rankings.json).
  Use after every workflow_dispatch or scheduled compute run, before authorizing
  PR Mark-Ready, tagging a release, or filing post-merge issues. Mirrors the
  verification template established in PR-3c run #11 + PR-3d run #15.
---

# verify-production-output

## When to use

After a `workflow_dispatch` (or scheduled) compute run completes and
the chore commit lands on the branch. Specifically before any of:

- Authorizing PR Mark-Ready (Draft → Ready for Review)
- Tagging a release version (`v0.X.Y-phaseN`)
- Filing post-merge follow-up issues

The skill is **read-only** — it never edits compute output. It just
inspects and reports.

## What it does

Runs a Python scan against `frontend/public/data/` and emits an A-H
report. Each section maps to a verification dimension that's been
useful in practice:

| Section | Question answered |
|---|---|
| A | Did the schema bump land? Coverage / latency healthy? |
| B | Did Tier-2 fired-flag counts match expectations (deferred-mode contract still in force)? |
| C | Fair-price coverage + data-quality sanity guard counts |
| D | Top-5 composition — same as baseline? Effective vs raw rank breakdown |
| E | Risk-flag totals — vetoes match prior-run baseline? |
| F | Tier-2 events spot-check (5 random tickers, dict shape contract) |
| G | Fundamentals resilience — histogram, p50/p95, slow tickers |
| H | Universe size consistency (metadata vs rankings vs file count) |

## Inputs

Required:
- `frontend/public/data/metadata.json`
- `frontend/public/data/rankings.json`
- `frontend/public/data/stocks/<TICKER>.json` × N

Optional flags (if running the helper script):
- `--baseline-commit=<sha>` — compare against an earlier run's metadata
- `--top-n=5` — number of top-rank stocks to spotlight (default 5)
- `--random-sample=5` — number of tickers for Section F dict-shape check
- `--strict` — exit code 1 on any section anomaly (default: warn-only)

## Helper script

`helper.py` (next to this SKILL.md) — single-file Python scan, no deps
beyond stdlib. Invoke from repo root:

```bash
python .claude/skills/verify-production-output/helper.py
```

Or with explicit baseline:

```bash
python .claude/skills/verify-production-output/helper.py --baseline-commit=8a9d35f
```

## Output sections

### Section A — Schema + metadata

Reports:
- `version` (e.g., `0.6.0-phase3d`) — should match the in-flight phase
- `git_commit` — hex prefix; should match the workflow run's commit
- `universe_size` — typically 502 (S&P 500 minus 1 delisted)
- `mos_trailing_ic_smoke` — informational (negative is normal in
  certain regimes; not a backtest)
- `tier2_coverage_pct` — target ≥ 95% in 10-K-only mode (Phase 3d
  default), ≥ 99% when 8-K is re-enabled (Phase 4)
- `fundamentals_coverage_pct` — target ≥ 95%; <80% indicates SEC
  throttling, ship anyway but file Phase 4 priority
- `fundamentals_latency_p50_seconds` — target <5s in healthy SEC,
  10-15s in throttled
- `fundamentals_latency_p95_seconds` — target <15s

### Section B — Tier-2 fired-flag inventory

For each of `going_concern_disclosure` / `non_reliance_filing` /
`auditor_change`, report count + ticker list.

Hard contract checks (current Phase 3d):
- `non_reliance_filing` MUST be 0 (deferred via `_EIGHT_K_DEFENSES_ENABLED=False`)
- `auditor_change` MUST be 0 (same)
- `going_concern_disclosure` typical range: 1-10% of universe
  (Mayew 2015 expects 1-3% in healthy population; PR-3d run #15
  observed 10.8% pending phrase-regex refinement in Phase 4)

If B2 or B3 fire above 0 → HALT, feature flag broken.

### Section C — Coverage + sanity guard

- Fair-price coverage: count of stock JSONs where `fair_price.median !== null`
  (target: ≥95% of universe)
- `data_quality_input_corruption` count + ticker list (typically 8 in
  the S&P 500: AMCR/BKR/CHTR/ERIE/PSKY/RTX/SPG/VTRS — see Phase 3c
  Step 7.5 for the $10K/share sanity ceiling)
- Spot-check one corrupted ticker (e.g., BKR): all 6 methods
  `applicable=false`, `fair_price.median=null`, `tier2_events` dict
  populated with deferred-mode defaults

### Section D — Top-5 composition

| Rank | Ticker | Sector | Composite | fair_price.median | warnings | risk_flags |
|---|---|---|---|---|---|---|

Effective top-5 = top-5 by composite *after* veto suppression. Cards
flagged by altman / sloan / NSI / non_reliance keep their composite
rank but lose the `entered_top5` badge; the next-in-line cards earn
the badge instead.

Compare to baseline run's effective top-5. Document any churn.

### Section E — Risk-flag totals

| Flag | Count |
|---|---|
| altman_distress | (typically 54 in S&P 500) |
| sloan_accruals_top_decile | (typically 50) |
| net_issuance_top_decile | (typically 37) |
| non_reliance_filing | (currently 0 — deferred) |

Exact parity with prior run = scoring layer didn't regress.

### Section F — Tier-2 events spot-check

For 5 random tickers, verify `tier2_events` dict has all 5 expected
keys (`going_concern_disclosure`, `non_reliance_filing`,
`auditor_change`, `latest_8k_filing_date`, `latest_8k_filing_url`)
with deferred-mode defaults (last 4 should be `false`/`null`).

### Section G — Fundamentals resilience

From metadata: report p50, p95, coverage_pct.
From workflow logs (if accessible): histogram bucket distribution,
top-20 slow tickers.

Coverage interpretation:
- ≥95%: SEC API healthy
- 80-95%: throttled but graceful degrade working
- <80%: heavily throttled (concerning but ship anyway, file Phase 4
  priority on `issue_fundamentals_resilience_phase4.md`)

### Section H — Universe size

Three numbers must match (or differ by 1 due to delisting):
- `metadata.universe_size`
- `len(rankings.json.stocks)` (or array length)
- `len(glob frontend/public/data/stocks/*.json)`

If Wikipedia returned N constituents but we wrote N-1 stock files,
the delta should equal `len(yfinance_failures)` — typically 0 or 1.

## Exit codes

- 0: all sections healthy (or only soft warnings under non-strict mode)
- 1: hard criteria failure (in `--strict` mode):
  - feature flag broken (B2/B3 > 0 in Phase 3d)
  - coverage <80% in any layer
  - schema version mismatch with branch
- 2: soft warning (e.g., going-concern FP rate >5%) — caller logs + continues

## Anti-patterns (do not do)

- Don't modify any output JSON during verification.
- Don't trigger workflow_dispatch from this skill — verification reads
  what already exists.
- Don't compare against an arbitrary git ref unless the user explicitly
  passes `--baseline-commit=`. Default behavior is single-run inspection.

## Related

- `schema-check` — for the schema-side contract (Pydantic ↔ TypeScript)
- `defense-scorecard` — focused dive on the veto/guard/annotate layer
- `top5-rotation-audit` — focused dive on entered/exited semantics
- `fundamentals-coverage-report` (phase-3d) — Section G deep-dive
