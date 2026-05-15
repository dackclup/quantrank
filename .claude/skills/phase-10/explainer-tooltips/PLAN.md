# Explainer Tooltips + Glossary + "Why is X rated Y?" (Phase 10 planning stub)

**Status**: Planning. Three-in-one UX improvement: tooltips on every
metric + glossary modal + per-stock "why this rating?" explainer.

## Purpose

The single biggest beginner-UX gap. Beginners see "Beneish 1.8" or
"value_trap_risk" and have no idea what those mean. Compared to Jitta
/ Simply Wall St which have first-class explainer surfaces, QuantRank
currently puts the burden of understanding on the user.

Phase 10 §1: ship the explainer trio.

## Three deliverables

### (1) Tooltip on every metric

Hovering / tapping any metric in the UI shows a 1-2 sentence tooltip.
Coverage: every metric in the ranking-table cells, detail-page header,
fair-price card, defense flag, pillar score.

```tsx
// Example: hover on "MoS −12%"
<Tooltip text="Margin of Safety = (Fair price − Current price) / Current price. Negative means current price is above fair value.">
  <MoSCell mos={-12} />
</Tooltip>
```

### (2) Glossary modal

A single `<GlossaryModal>` opened by clicking "Glossary" link in footer
OR clicking the `?` icon in any chip. Searchable single-page reference
for every term: composite, MoS, Beneish, Dechow, Sloan, Altman, Sloan
accruals, NSI, Loss Chance, recommendation tiers, sector pills, ...

### (3) "Why is X rated Y?" explainer modal

Click the recommendation badge → modal opens showing the **rubric
walkthrough** for that specific stock:

```
NVDA — Recommendation: Sell

Why:
✗ MoS −271%  (below CAUTIOUS threshold of −180%)
   → forced to Sell tier regardless of composite

If MoS were not flagged:
- Composite 70.7 → would have qualified for Bullish (≥60)
- Sloan flag → blocks Bullish, falls to Lean Bullish
- Without Sloan: would be Bullish

Inputs used:
- composite_score: 70.7
- risk_flags: [sloan_accruals_top_decile]
- valuation_warnings: [extreme_graham_estimate, beneish_high]
- mos_pct: −271%

Methodology: recommendation-badge/PLAN.md
```

## Architecture

```
frontend/lib/glossary.ts           # term ↔ explanation lookup
frontend/components/Tooltip.tsx    # reusable tooltip wrapper
frontend/components/GlossaryModal.tsx
frontend/components/RecommendationExplainer.tsx
frontend/components/MoSCell.tsx    # add tooltip wrapper
frontend/components/RecommendationBadge.tsx  # add click-to-explain
... (16 other components touched for tooltip add)
```

## Effort

| Step | LOC | Days |
|---|---|---|
| `Tooltip` reusable component (Radix UI primitive) | ~80 | 0.5 |
| `glossary.ts` term ↔ explanation map (40 entries) | ~400 | 2 |
| `GlossaryModal.tsx` searchable modal | ~250 | 2 |
| `RecommendationExplainer.tsx` modal | ~300 | 2.5 |
| Tooltip wrappers on 20 components | ~150 | 2 |
| Footer "Glossary" link + `?` icons added to chips | ~80 | 1 |
| Tests + visual regression | ~150 | 1.5 |
| **Total** | **~1410 LOC** | **~11 days** |

## Decisions (locked)

1. ~~Native HTML `<title>` vs custom tooltip?~~ → **Custom Radix-based**
   (mobile-friendly tap; supports rich content; consistent styling)
2. ~~Glossary as inline page or modal?~~ → **Modal** (keeps user on
   current view; faster than full page navigation)
3. ~~Recommendation explainer vs "Hide this section"?~~ → **Modal on
   click** (no permanent UI clutter; opt-in deeper dive)
4. ~~Static glossary vs dynamic (i18n)?~~ → **i18n-ready from day 1**
   (Phase 10 §3 bilingual depends on this structure)

## Dependencies

- Phase 10 §3 `bilingual-i18n/PLAN.md` — same glossary structure
  needs to support TH + EN

## Out of scope

- Video tutorials (Phase 11)
- Interactive walkthroughs of the methodology (Phase 11)
- Comparison narrative ("NVDA vs AMD: NVDA is better at X but worse at Y")
  (Phase 10 §2 comparison-view + Phase 11)
