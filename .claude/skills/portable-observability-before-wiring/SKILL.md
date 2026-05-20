---
name: portable-observability-before-wiring
description: For every integration PR that consumes a NEW external data
  source, ship the diagnostic surface BEFORE the production logic uses the
  data. The diagnostic exposes WHICH inputs were dropped at each filter /
  gate / NaN-strip and WHY, making silent-drop failure modes visible from
  the first cron / job run instead of after a multi-PR debugging cycle.
  Generic — drop-in for any data pipeline with filters or gates. TRIGGER
  when adding a new external-data integration (API, dataset, library),
  when adding a gate / filter / rejection step to an existing pipeline,
  or when the user says "ship the metric first, the logic later". SKIP
  for changes that don't drop / filter / reject any input (pure
  transformations, identity-preserving passes).
---

# portable-observability-before-wiring

The headline failure mode this skill prevents: shipping production
logic that silently filters or rejects inputs, then waiting through
N debugging cycles to learn WHY the output is empty / wrong / 0%.
Portable — applies to any data pipeline.

## Pattern

For every integration PR that consumes a NEW external data source
or adds a NEW filter / gate / rejection step:

1. **Identify the decision points** where data is dropped, filtered,
   or rejected (missing-column, gate-fail, NaN-strip, type-coerce
   fallback, etc.)
2. **For each decision point**, add a diagnostic field on the
   pipeline's output `Metadata` (or equivalent observability
   surface) of shape `dict[str, FailureReason] | None` or
   `list[str] | None` that surfaces WHICH inputs were dropped and
   WHY
3. **Ensure the accounting equation balances**:
   `len(input_universe) == sum(len(diagnostic_buckets))` — every
   input lands in exactly one bucket (passed, filtered, gated, etc.);
   no input disappears silently
4. **Schema PATCH bump** (additive optional fields only)
5. **Schema triple lockstep** if applicable (see
   `portable-schema-triple-lockstep`)
6. **Production wiring lands ≥ 1 cron / job run after** the
   diagnostic surface — verify the accounting equation balances on
   real data before the consuming logic ships

## Anti-pattern (what NOT to do)

Do not ship production wiring + gate logic without a diagnostic
surface "to keep the PR small." The diagnostic surface IS the unit
test for the gate logic — without it, you're flying blind on
production data.

## Trigger conditions

- Adding a new external-data integration (API, dataset, library)
- Adding a gate / filter / rejection step to an existing pipeline
- The user says "ship the metric first, the logic later"
- A previous integration's silent-drop required a multi-PR
  retrofit (you don't want a second retrofit)

## Skip conditions

- Changes that don't drop / filter / reject any input (pure
  transformations, identity-preserving passes)
- The output universe is already self-describing (e.g., the
  pipeline produces a `(input, output)` tuple per row, so drops
  are visible without diagnostic surface)
- Internal-only intermediate stages whose output isn't consumed
  by users / downstream PRs

## Accounting-equation invariant

```
len(input_universe) == (
    len(filtered_at_step_1)
    + len(filtered_at_step_2)
    + ...
    + len(passed_through_all_filters)
)
```

Test this as a property — if a filter is added and the equation
breaks, CI fails fast.

## QuantRank precedent

The Phase 4h timeline (PR #112 → #118 → #124) is the forcing
precedent:

- **PR #112 (2026-05-18)**: OSAP signal replication + PBO/DSR gate
  + Path-b blend, NO diagnostic surface. First production cron: 0%
  acceptance, no observability into WHY.
- **PR #118 (2026-05-19)**: Retrofit `osap_signals_missing_from_dataset`
  + `osap_gate_diagnostics`. Next cron: 78/100 missing + 22/22
  `low_dsr` — both invisible before.
- **PR #124 (2026-05-19)**: Multi-port adapter + new
  `osap_signals_dropped_no_long_short` field. Accounting now
  balances 100/100.

Combined cost of PRs #118 + #124: ~10 hours across 2 PRs. The
diagnostic surface in PR #112 would have been ~30 minutes of
additional scope.

See QuantRank's `WORKFLOW.md` §Observability-Before-Wiring Pattern
+ `SKILL.md` Rule 18 for the project-specific lock.
