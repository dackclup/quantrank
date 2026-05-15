# Methodology FAQ Page (Phase 11 planning stub)

**Status**: Planning. Dedicated `/methodology` page answering "how does
QuantRank compute X?" so beginners + skeptics can verify the math.

## Purpose

Phase 0-8 have built rigorous methodology — backtest-validated,
academically-grounded. Phase 10 made it accessible via tooltips +
glossary. Phase 11 §1 = a dedicated **deep-dive FAQ page** that
documents the methodology end-to-end for users who want more than
tooltips.

Compares to:
- Jitta's "How is the Score calculated?" page
- Simply Wall St's "Snowflake explained"
- Morningstar's "Star ratings methodology"

QuantRank's edge = **open-source, reproducible, peer-reviewed-paper-backed**.
FAQ page makes that visible.

## Architecture

```
frontend/app/methodology/page.tsx       # main FAQ landing
frontend/app/methodology/[section]/page.tsx  # per-section deep dive
  - composite
  - pillars
  - fair-price
  - defense-layer
  - recommendation
  - loss-chance
  - macro-regime (Phase 9)
  - insider-trading (Phase 9)
  - backtest-validation (Phase 5)
frontend/components/MethodologySection.tsx
```

## Content structure (per section)

Each `/methodology/<section>` page has:

1. **TL;DR** — 1-2 sentence summary
2. **What it answers** — user question this addresses ("Should I buy
   X?" / "Is this stock cheap?" / etc.)
3. **Formula** — academic notation + Python code (collapsible)
4. **Inputs** — table of source data + provenance (SEC EDGAR /
   yfinance / OSAP / etc.)
5. **References** — peer-reviewed papers (with DOI)
6. **Limitations** — honest caveats
7. **Code** — link to GitHub source file
8. **Backtest** — Phase 5 IC + DSR + PBO numbers for this signal

## Example section: Recommendation tiers

```markdown
# Recommendation: Strong Buy / Buy / Hold / Sell

## TL;DR

Combines composite score + risk flags + valuation warnings + Margin
of Safety into a 4-tier rating. Internal IDs are neutral; display
labels are sell-side conventional for retail familiarity.

## Rubric

(formula here — same as recommendation-badge/PLAN.md but
beginner-friendly explained)

## Inputs

| Input | Source | Update cadence |
|---|---|---|
| composite_score | 8-pillar weighted | Weekly |
| risk_flags | Altman + Sloan + NSI + Beneish + Dechow + data-quality | Weekly |
| valuation_warnings | 6-method fair-price ensemble | Weekly |
| mos_pct | (fair_price.median − current_price) / current_price | Weekly |

## References

- Bullish tier criterion: composite ≥ 60 + clean + MoS ≥ 0%
- Cautious force: data_quality_input_corruption (Section X.Y of...)
- ...

## Limitations

- Calibrated against current S&P 500 distribution; would need re-tune
  for non-US universe
- Not backtested — heuristic combiner (Phase 5+ adds calibration)
- ...

## Code

`compute/scoring/recommendation.py` (link to GitHub)
```

## Effort

| Step | LOC | Days |
|---|---|---|
| Page route + layout shell | ~150 | 1 |
| 9 section deep-dive pages | ~1500 | 9 (~1 day each) |
| `MethodologySection.tsx` reusable component | ~200 | 1 |
| Cross-linking from glossary + tooltips | ~80 | 0.5 |
| i18n (TH + EN) — 9 sections × 2 langs | ~3000 | 6 |
| **Total** | **~4930 LOC** | **~17.5 days** |

Note: Much of the content is **prose markdown**, not code. The
effort here is writing quality educational content, not building UI.

## Decisions (locked)

1. ~~Static markdown vs CMS?~~ → **Static markdown in repo** (version-
   controlled, no CMS dependency, no $ per month)
2. ~~Math notation?~~ → **KaTeX** (Next.js MDX-compatible)
3. ~~Code samples?~~ → **Show in collapsed `<details>`** by default
   (less intimidating for beginners)
4. ~~Include backtest numbers?~~ → **YES — after Phase 5 produces
   them** (defer this PR until Phase 5 backtest infra has shipped at
   least one factor's PBO/DSR/IC numbers)

## Dependencies

- Phase 5 backtest infrastructure — for the "Backtest" section per
  signal
- Phase 10 §1 explainer-tooltips — glossary cross-links INTO this page
- Phase 10 §3 bilingual-i18n — content needs both Thai + English

## Out of scope

- Interactive playground (try different thresholds) — Phase 11+
- User-submitted research notes / forum — Phase 11+
- Per-stock methodology trace ("for NVDA specifically, here's why...")
  — that's the Phase 10 §1 RecommendationExplainer modal, not this
- API documentation — Phase 11 separate stub (`public-api-docs/`)
