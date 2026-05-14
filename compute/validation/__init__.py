"""Defense infrastructure for Phase 4+ factor integration.

Per `.claude/skills/phase-4/defense-infrastructure/PLAN.md`. Three
modules, each guarding a different failure surface:

- :mod:`compute.validation.pbo_dsr` — PBO (Bailey 2014) + Deflated
  Sharpe Ratio (Bailey-López de Prado 2014). Pre-integration gate for
  Phase 4 OSAP / JKP / Qlib factor candidates.
- :mod:`compute.validation.ic_decay` — Rolling IC decay monitor
  (McLean-Pontiff 2016). Post-integration alert when a pillar's IC
  degrades below 50% of historical mean for 6+ consecutive months.

The cross-source validator (Phase 4b §1) lives in
:mod:`compute.ingest.cross_source` because it operates on raw ingest
inputs rather than on factor returns — it's an ingest-quality guard,
not a factor-validation gate.
"""
