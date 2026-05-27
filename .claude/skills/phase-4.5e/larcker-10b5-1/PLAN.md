# Phase 4.5e Follow-on — Larcker 10b5-1 Three-Red-Flags (PLAN)

> **Status**: PLAN — small additive extension of existing
> `compute/scoring/form4_signals.py` 10b5-1 contamination filter
> (PR #224). Suitable for execution in a follow-up session.

## Goal

Per Research Report v1.0 §6 + Larcker-Lynch-Quinn-Tayan-Taylor 2021
Stanford CGRI Closer Look 88, add three sub-checks on existing 10b5-1
plan signals to identify the **gaming the system** pattern. Current
PR #224 filter EXCLUDES 10b5-1 trades from the opportunistic cluster
(treating them as routine). Larcker shows the OPPOSITE for a subset
with these red flags — those should re-enter as a NEW veto-class flag.

### The 3 red flags

1. **Short cooling-off** — first planned trade within < 30 days of plan
   adoption. Stanford CGRI 2021: "associated with a subsequent
   industry-adjusted return of -2.5 percent"
2. **Single-trade plan** — entire plan is just 1 trade (vs multi-trade
   scheduled). Stanford CGRI 2021: highest loss-avoidance among
   sub-patterns at -4% industry-adjusted
3. **Pre-earnings trade** — trade scheduled within 10 trading days
   prior to next earnings announcement. (Larcker subset evidence)

A 10b5-1 plan exhibiting ≥ 2 of 3 flags → fire
`insider_10b5_1_red_flags` annotate (Phase 1) then promote to veto
after ≥ 1 cron's firing-rate observation (per
`portable-annotate-before-veto`).

## Files changed

- `compute/scoring/form4_signals.py` — extend `_is_opportunistic_sell` with `_check_larcker_red_flags(plan)` returning `Counter[str]` of which flags fire; add module-level constants:
  - `LARCKER_COOLING_OFF_DAYS = 30`
  - `LARCKER_PRE_EARNINGS_WINDOW_DAYS = 10`
- `compute/scoring/form4_insider.py` — extend cache schema to include `plan_adoption_date` (if available via `<aff10b5One>` element) and `next_earnings_date_estimate`
- `compute/output/schemas.py` — `Metadata.insider_10b5_1_red_flag_count: int | None` + `StockDetail.insider_10b5_1_red_flag_breakdown: dict[str, int] | None`
- `frontend/lib/types.ts` + snapshot — triple lockstep
- `tests/test_scoring/test_form4_signals.py` — 12+ new tests covering each red flag separately + combinations

## Schema delta

PATCH bump: `0.10.5-phase4.5e` → `0.10.6-phase4.5e` (additive Metadata
+ StockDetail fields). If conflicts with survivorship-bias PR's
0.10.6, bump to 0.10.7.

## Defense mode

- **Phase 1 (this PR)**: ANNOTATE only — observability surface fires +
  Rule 18 diagnostics, no rank change
- **Phase 2 (follow-up PR after ≥ 1 cron)**: promote to VETO if cohort
  acceptance check passes (PPV ≥ 0.6, ≤ 3% universe fire rate)

## Tests

- 12+ unit tests in `test_form4_signals.py`:
  - Each red flag fires independently
  - 0/3, 1/3, 2/3, 3/3 red-flag combinations
  - Edge: plan with `aff10b5One = False` doesn't trip any flag
  - Edge: pre-earnings window calculation across earnings re-schedules
- Hypothesis property: red-flag count ∈ [0, 3]; flag is idempotent (same plan → same flags)
- Golden value: 2-3 known historical cases per CGRI 2021 Appendix A (if data accessible from existing Form-4 cache)

## Production verification

- `Metadata.insider_10b5_1_red_flag_count` fires on ≤ 5% of universe per Larcker 2021 base-rate
- Section L (verify-helper) Form-4 proxy invariant unchanged
- `manipulation_index` rollup gains optional `larcker_10b5_1_red_flags` component (reserved weight 5.0 if promoted to veto, 2.0 as annotate per phase-1)

## Fallback triggers

- If `<aff10b5One>` plan_adoption_date NOT exposed by edgartools 5.31 (likely — per CLAUDE.md §Gotcha "edgartools 5.31.5 does NOT parse structured `<aff10b5One>`"): the cooling-off-day check requires DIRECT XML parsing of Form 4 to find the plan_adoption_date element. Defer until edgartools adds API OR implement minimal lxml parser for this one element.
- If pre-earnings window calculation fails (no earnings calendar in cache): annotate with `LARCKER_PRE_EARNINGS_UNKNOWN` instead of firing, mark as data-quality-degraded rather than false-positive.

## Acceptance checklist

- [ ] 3 red-flag predicates implemented as pure functions
- [ ] Combined `_check_larcker_red_flags` returns dict + count
- [ ] Annotate-only mode (Phase 1) — composite rank UNCHANGED
- [ ] `Metadata.insider_10b5_1_red_flag_count` Rule 18 diagnostic ships in same PR
- [ ] 12+ unit tests + 1 Hypothesis property + golden values
- [ ] `methodology-scientist` verdict: LITERATURE-ANCHORED per CGRI 2021
- [ ] Module docstring cites: Larcker-Lynch-Quinn-Tayan-Taylor 2021 CGRI Closer Look 88 (vegaeconomics.com mirror); Cohen 2008 JF (routine vs opportunistic; 10b5-1 ⊊ routine)
- [ ] `dependency-auditor` not needed (no new deps)

## License posture

- Stanford CGRI Closer Look 88: public access via vegaeconomics.com mirror; methodology + threshold values are factual + citation-only
- No new dependencies

## Estimated effort

**2-3 days focused dev**. Smallest of the 5 features (extension of
existing module). The blocker is the `<aff10b5One>` plan_adoption_date
extraction; if edgartools 5.31 doesn't expose it, the cooling-off
check ships disabled until a minimal lxml parser lands.
