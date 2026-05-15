# Case Studies Archive (Phase 11 planning stub)

**Status**: Planning. Curated walkthroughs of how QuantRank's
methodology evolved on specific famous stocks. Builds trust by showing
the methodology in action on cases everyone knows.

## Purpose

Static methodology FAQ (Phase 11 §1) explains how things work in
theory. Case studies show how they work in practice. Each case study
walks through a famous stock and shows:

- How the composite score evolved month-over-month
- What flags fired and when
- How fair price tracked the share price
- Whether the recommendation was "right" in retrospect

Builds trust (transparency) + serves as worked-example for new users.

## Initial case study slate (5 cases)

| Case | Why notable | Timeframe |
|---|---|---|
| **NVDA — the AI bubble** | Composite kept rising while MoS deteriorated; Sloan + Beneish fired; recommendation went Buy → Hold → Sell | 2023-2026 |
| **SPG — the data-quality incident** | Phase 1 yfinance scraper shipped SPG as Top-1 with $1.62M market cap (real $76B); data_quality veto promoted from annotate → veto in Audit #6 | PR-3d / Audit #6 |
| **CRWD — chronic-slow EDGAR fetcher** | 8-min ingest time blew up workflow; documented in Audit #6 + PR 4a cache improvements | Phase 3-4 |
| **WBD / SBUX / SJM — the Loss Chance >80% cluster** | Cautious tier with deep overvaluation but no distress flag (LC = 80+); how the heuristic distinguishes "expensive" from "distressed" | PR 4e verification |
| **The 2024 Fed pivot** (Phase 9 case) | macro_regime flipped late_cycle → expansion → recovery; how the regime chip changed for the same stocks | Phase 9 (after macro-regime ships) |

Each case study = ~1500-2500 word markdown article.

## Architecture

```
frontend/app/case-study/[slug]/page.tsx
content/case-studies/
  nvda-ai-bubble.mdx
  spg-data-quality.mdx
  crwd-slow-edgar.mdx
  cautious-cluster.mdx
  2024-fed-pivot.mdx
frontend/components/CaseStudyLayout.tsx
frontend/components/EmbeddedPriceChart.tsx  # historical chart with annotations
frontend/components/EmbeddedScoreTimeline.tsx  # composite over time
```

## Content structure

Each case study has:

1. **Hook** — 2-sentence summary (why you should care)
2. **Timeline** — events + composite/recommendation snapshots
3. **Embedded chart(s)** — price + score over time, with annotations
4. **Lessons** — what we learned + which Phase change reflected it
5. **References** — PR numbers, audit notes, source filings
6. **What the system would say today** — current recommendation
7. **Critique** — what the case study shows the methodology MISSED

The **Critique** section is critical — case studies that only
self-promote = corporate marketing. Honest critique = academic
transparency.

## Effort

| Step | LOC | Days |
|---|---|---|
| Page route + MDX support | ~150 | 1 |
| `CaseStudyLayout.tsx` + embedded components | ~300 | 2 |
| 5 case studies — research + write | ~4000 | 12 (~2.5/each) |
| Historical chart annotations (require backfill from PHASE_STATUS history) | ~200 | 2 |
| i18n (TH + EN) for case studies | ~4000 | 8 |
| Index landing page + tags | ~150 | 1 |
| **Total** | **~8800 LOC** | **~26 days** |

Note: bulk of effort = writing high-quality 5-page articles. Code
infra is small. Translation doubles the writing cost.

## Decisions (locked)

1. ~~MDX vs plain Markdown?~~ → **MDX** (Next.js native; allows
   embedded React components for charts)
2. ~~How many initial?~~ → **5** (cover diverse failure modes; not
   too many to maintain)
3. ~~Update cadence?~~ → **Quarterly** when a new Phase ships + 1
   case study per release tag
4. ~~Include "what would have been recommended" hindsight?~~ → **YES**
   — but flagged as "post-hoc, not predictive" for honesty
5. ~~Critique vs marketing tone?~~ → **Critique always present**
   — honesty over marketing

## Dependencies

- Phase 5 backtest infra — for "would have been" hindsight numbers
- Phase 10 §3 bilingual-i18n — case studies need both Thai + English
- Phase 11 §1 methodology-faq — cross-link cases to methodology
  sections
- PHASE_STATUS.md archive — primary source for what changed when

## Out of scope

- User-submitted case studies (community moderation overhead) —
  Phase 11+
- Live "case study in progress" tracking specific stocks now —
  Phase 11+
- Video / podcast format — text-only initially
