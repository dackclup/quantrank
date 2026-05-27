# Phase 4.6 — JKP-Aligned 8-Pillar Refactor (PLAN)

> **Status**: PLAN — large schema-breaking refactor; execution gated on
> explicit user authorization per feature (separate session recommended)

## Goal

Refactor the 8 QuantRank pillars to align with Jensen-Kelly-Pedersen
2023 JF 78(5):2465-2518 ("Is There a Replication Crisis in Finance?")
13-theme taxonomy. The JKP paper's tangency-portfolio evidence
**subsumes `profitability` into `quality`** (one of the 3 displaced
themes), so the 8 pillars can be re-mapped:

| Current | New | Action |
|---|---|---|
| quality | quality (QMJ + profitability merged) | KEEP + extend |
| value | value | KEEP |
| growth | profit_growth | RENAME |
| momentum | momentum | KEEP (12-1 standard) |
| health | low_leverage + accruals | SPLIT |
| profitability | (merged into quality) | DELETE |
| technical | short_term_reversal | RENAME (sign-flip aware!) |
| risk | low_risk | KEEP |
| (new) | debt_issuance | ADD (currently veto-only) |
| (new) | investment | ADD (asset growth, Cooper-Gulen-Schill 2008) |

Net: 8 → 9 pillars (`profitability` removed, `debt_issuance` +
`investment` added, `health` split into 2).

## Files changed

- `compute/scoring/pillars.py` — REWRITE pillar-name constants + computation map
- `compute/scoring/composite.py` — preserve formula semantics (Rule 16), only remap inputs
- `compute/scoring/normalize.py` — pillar normalization updates
- `compute/scoring/risk_overlay.py` — `net_issuance_top_decile` veto now also feeds positive `debt_issuance` pillar (2-sided signal)
- `compute/output/schemas.py` — `PillarScores` model rename + field bumps; `StockSummary.pillar_scores` updated; major breaking change
- `compute/output/writer.py` — preserve old field names for ≥ 1 cycle (back-compat) then drop
- `frontend/lib/types.ts` — major breaking type update
- `frontend/lib/schema-snapshot.json` — regen
- `frontend/components/PillarRadarChart.tsx` — relabel axes; ensure 9-pillar layout still readable (current is 8-axis radar)
- `frontend/components/RankingTable.tsx` — column-header strings
- `tests/test_scoring/test_pillars.py` — REWRITE
- `tests/test_scoring/test_composite.py` — assertion updates
- `tests/test_output/test_schemas.py` — field name updates
- `docs/METHODOLOGY.md` — pillar table update
- `docs/factor_taxonomy.md` (NEW) — JKP 13-theme → QuantRank 9-pillar mapping table with citation

## Schema delta

**MAJOR bump** (breaking): `0.10.6-phase4.6` → `1.0.0-phase4.6` OR
`0.11.0-phase4.6` (semver MAJOR-or-MINOR depending on
back-compat policy). Recommend `1.0.0-phase4.6` to signal stable
foundation post-JKP alignment.

## Defense mode

N/A — restructuring positive ranking signals, not defenses.

## Tests

- Pillar-level: 9 × 5+ tests per pillar = ≥ 45 new tests
- Composite invariant: top-N rotation unchanged within ±2 stocks vs pre-refactor baseline (Rule 16 sacred)
- Golden values: NVDA / AAPL / SMCI / CF composite scores preserved within ±1 point of pre-refactor
- Hypothesis: pillar score ∈ [0, 100]; composite ∈ [0, 100]; sum-to-1 weight invariant
- @network: 1 smoke test per new pillar (`debt_issuance`, `investment`) hitting yfinance

## Production verification

- `Metadata.composite_score` distribution mean/std within 1σ of pre-refactor cron
- Top-5 churn ≤ 2 stocks vs pre-refactor (Rule 16 invariant)
- All 33 defense flags fire-rates within ±2pp of pre-refactor (defenses untouched)

## Fallback triggers

- Top-5 churn > 2 stocks → fall back: rename pillars only, keep computation identical (cosmetic-only refactor)
- PBO > 0.5 on new pillar combo → reject new `debt_issuance` and/or `investment`, ship JKP rename only

## Acceptance checklist

- [ ] All 9 pillars match JKP taxonomy + cited in module docstrings
- [ ] Schema MAJOR bump atomic (Pydantic + TS + snapshot)
- [ ] Frontend radar chart adapted to 9 axes
- [ ] `docs/factor_taxonomy.md` committed with JKP citation
- [ ] ≥ 45 new pillar tests + composite invariant
- [ ] Composite golden values preserved within ±1 pt for NVDA/AAPL/SMCI/CF
- [ ] PBO ≤ 0.5 + DSR > 0 + BH-FDR < 0.05 for `debt_issuance` and `investment` pillars
- [ ] Methodology-scientist subagent verdict: LITERATURE-ANCHORED per JKP 2023 + Cooper-Gulen-Schill 2008 + Daniel-Titman 2006

## License posture

- JKP TAXONOMY (concept) — uncopyrightable; OK to use
- JKP DATA (jkpfactors.com CSV) — CC BY-NC 4.0; **do NOT use data**; replicate from Compustat/yfinance
- Citations: Jensen-Kelly-Pedersen 2023 JF; Asness-Frazzini-Pedersen 2019 RAS (quality QMJ); Cooper-Gulen-Schill 2008 JF (investment); Daniel-Titman 2006 (issuance); Pontiff-Woodgate 2008 JF

## Estimated effort

**1-2 weeks focused dev**. Largest scope of the 5 features. Test suite
will require ~hundreds of updates due to MAJOR schema break. **Defer to
dedicated session with explicit user authorization.**
