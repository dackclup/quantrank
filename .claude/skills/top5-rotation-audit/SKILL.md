---
name: top5-rotation-audit
description: Audit Top-5 rotation invariants in the latest output — flagged top-rank stocks lose `entered_top5`, the next-in-line clean stock inherits it; compares raw vs effective top-5 and reports churn vs baseline. TRIGGER: after changes to `composite.py` / `risk_overlay.py` / `writer.py`, a veto threshold tweak, a new veto, "did Top-5 rotate this week?" / "is the badge suppression working?", or as the focused dive when verify-production-output Section D flags a rotation anomaly.
---

# top5-rotation-audit

## The rotation contract

> Flagged stocks (any active veto) keep their composite rank but cannot
> earn the `entered_top5` badge. The next-in-line stock by composite
> (rank 6, 7, 8, …) inherits the badge instead. This is the
> annotate-and-veto-Top-N pattern (SKILL.md Rule 16) — the composite
> score is preserved (no retroactive adjustment); only the user-visible
> "new in Top-5" signal is suppressed.

Implications:

- A stock at rank 1 with `altman_distress` still appears at rank 1 in
  the rankings table — but with no `entered_top5` badge.
- A stock at rank 6 (clean) inherits the badge as the "5th effective
  entrant" with `entered_top5=true`.
- `exited_top5` fires only for the **suppressed** top-rankers, not for
  stocks that genuinely dropped due to score changes (those are
  tracked by a separate composite-rank diff vs baseline).

## What the audit checks

For the most recent compute output:

1. The **raw top-5** by composite score (rank 1-5)
2. The **effective top-5** — stocks with `entered_top5=true` anywhere
3. The **exited set** — stocks with `exited_top5=true`
4. Three rotation invariants:
   - Every raw-top-5 stock with an active veto has `entered_top5=false`
     AND `exited_top5=true`
   - Every `entered_top5=true` stock at rank > 5 corresponds to a
     suppressed top-rank slot
   - The effective top-5 has exactly 5 entries
5. Composition delta vs a baseline run (when provided)

## Running

```python
import json, glob

stocks = [json.load(open(f)) for f in sorted(glob.glob("frontend/public/data/stocks/*.json"))]

VETO_FLAGS = {"altman_distress", "sloan_accruals_top_decile",
              "net_issuance_top_decile", "non_reliance_filing"}

by_rank = sorted([s for s in stocks if isinstance(s.get("rank"), int)],
                 key=lambda s: s["rank"])

raw_top5 = by_rank[:5]
entered = [s for s in stocks if s.get("entered_top5")]
exited = [s for s in stocks if s.get("exited_top5")]

# Invariants
assert len(entered) == 5, f"entered count = {len(entered)} (expected 5)"

for s in raw_top5:
    has_veto = bool(set(s.get("risk_flags") or []) & VETO_FLAGS)
    if has_veto:
        assert not s["entered_top5"], f"{s['ticker']} flagged but still entered"
        assert s["exited_top5"], f"{s['ticker']} flagged but not in exited set"
```

## Output format

```
Raw top-5 (by composite, no suppression):
  #1 SPG    composite 74.81  | risk=[sloan_accruals_top_decile]    ← will be suppressed
  #2 NVDA   composite 73.07  | risk=[sloan_accruals_top_decile]    ← will be suppressed
  #3 SNDK   composite 72.50  | risk=[]
  #4 EOG    composite 71.02  | risk=[]
  #5 CF     composite 70.17  | risk=[]

Effective top-5 (entered_top5=true):
  #3 SNDK    (rank 3, clean)
  #4 EOG     (rank 4, clean)
  #5 CF      (rank 5, clean)
  #6 BKR     (rank 6, inherited from SPG)
  #7 HST     (rank 7, inherited from NVDA)

Suppressed (raw-top-5 with veto, exited_top5=true):
  SPG  ← sloan_accruals_top_decile
  NVDA ← sloan_accruals_top_decile

Invariants: ✓ all 3 pass

Churn vs baseline: effective top-5 unchanged
```

## Hard checks

- `len(entered_top5) == len(exited_top5)` — one stock promoted in per
  one suppressed at the top. Typical: 0-2 each on a healthy run. (The
  effective top-5 is the union of: unflagged rank ≤ 5 stocks +
  promoted-in stocks at rank > 5 with `entered_top5=true`.)
- `len(exited_top5)` equals the number of raw-top-5 stocks with active
  vetoes.
- For every `entered_top5=true` stock at rank > 5, there must exist a
  rank ≤ 5 stock with at least one active veto.

When any of these fails, do not write off as flake. The rotation logic
in `compute/output/writer.py::write_rankings_json` is doing something
unexpected — investigate that code path.

## Edge cases

| Scenario | Expected behavior |
|---|---|
| More than 5 raw-top-5 have vetoes | Rotation cascades to ranks 6, 7, 8, … until 5 clean stocks found. Flag if this happens — suggests too-aggressive veto layer |
| First-ever run, no baseline | Churn diff N/A; only the contract checks fire |
| Baseline missing newer fields | Graceful degrade — skip churn diff, run contract checks only |

## Anti-patterns

- Treating `exited_top5` as "lost its rank". It fires only for
  suppressed-from-top-5 stocks. Use a separate composite-rank diff for
  generic score-drop tracking.
- Auditing `valuation_warnings[]` as a veto. Warnings annotate; only
  `risk_flags[]` entries with active veto names suppress
  `entered_top5`.
- Counting a stock in both entered and suppressed sets. They are
  disjoint by construction.

## Why this skill exists

The Top-5 is the most visible signal in the QuantRank UI. A silent
break in the rotation logic — say, a refactor that lets flagged stocks
keep the `entered_top5` badge — directly degrades user trust. This
skill is the focused contract check that runs faster than the full
A-H scan when only the rotation matters.

## Related skills

- `verify-production-output` — Section D is a smaller version of this
  audit inside the full A-H scan
- `defense-scorecard` — the veto layer this skill depends on
- `compute/output/writer.py::write_rankings_json` — the production code
  that implements the rotation

## Long-form description (moved out of frontmatter 2026-06-11 token drain)

Audit QuantRank's Top-5 rotation invariants in the most recent
compute output — verify that flagged top-rank stocks correctly lose their
`entered_top5` badge and that the next-in-line stock fills the slot.
Compares the raw top-5 (by composite score) against the effective top-5
(after veto suppression) and reports composition churn vs a baseline run.
TRIGGER after any change to `compute/scoring/composite.py`,
`compute/scoring/risk_overlay.py`, or `compute/output/writer.py`, after
a veto threshold tweak, after a new veto lands, or when the user asks
"did Top-5 rotate this week?" / "why is X at rank 1 but not entered?"
/ "is the badge suppression working?". ALSO use as the focused dive
when verify-production-output Section D flags a rotation anomaly.
SKIP for the full Section A-H production scan (use verify-production-
output) or a defense-layer count comparison (use defense-scorecard).
