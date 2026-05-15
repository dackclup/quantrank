# Onboarding Tutorial (Phase 10 planning stub)

**Status**: Planning. First-visit walkthrough so beginners don't see
a wall of metrics with no idea where to start.

## Purpose

A first-time user landing on QuantRank sees:
- Disclaimer banner
- "S&P 500 ranking" header
- A list of stocks with composite scores, sector pills, recommendation
  badges, MoS bars, Loss Chance chips

Without onboarding, this looks overwhelming. With a 6-step tooltip
walkthrough, beginners learn the layout in 90 seconds.

## Sequence (6 steps, dismissable)

1. **Welcome card** — "QuantRank ranks 502 US stocks weekly using 8
   academic factor pillars. No login. Free forever." [Next →]

2. **Composite score** — point at the ScoreBadge column. "The headline
   number. Higher = better-ranked by our combined methodology."
   [Glossary →] [Next]

3. **Recommendation badge** — point at the Strong Buy / Buy / Hold /
   Sell pill. "Quick read: Strong Buy = top decile + clean. Sell =
   distressed / overvalued. Heuristic, not advice." [Glossary →] [Next]

4. **Loss Chance %** — point at the Loss Chance chip. "Heuristic chance
   that buying today results in loss over a year. NOT a backtested
   probability — explains in tooltip." [Next]

5. **Filters** — point at Filters button. "Narrow by sector, score,
   recommendation, or MoS. Filters persist when you navigate to a
   stock detail and back." [Next]

6. **Watchlist** — point at ⭐ icon. "Star stocks to save them. Lives
   in your browser; nothing sent to our server." [Done — get started!]

Optional **Skip tutorial** link at each step. Won't show again unless
user clicks "Replay tutorial" link in footer.

## Architecture

```
frontend/components/Onboarding.tsx        # main walkthrough
frontend/components/OnboardingStep.tsx    # individual step bubble
frontend/lib/onboarding-state.ts          # localStorage seen-flag
frontend/lib/onboarding-config.ts         # the 6 steps as data
```

### Persistence

```typescript
const KEY = 'quantrank.onboarding.v1';
type State = { completed: boolean; dismissed_at: string };
```

If `completed=true` OR `dismissed_at` set → don't show again. Replay
link in footer wipes the state.

## Visual spec

Step bubble = small floating card with arrow pointing at the target
component. Backdrop dimmed slightly. Bubble has:
- Step counter ("Step 3 of 6")
- Heading + body text (1-2 sentences)
- Glossary link (when relevant)
- "Skip tutorial" + "Next →" buttons

## Effort

| Step | LOC | Days |
|---|---|---|
| `Onboarding.tsx` + step bubble + backdrop | ~250 | 2 |
| `OnboardingStep.tsx` reusable individual step | ~150 | 1 |
| 6 step configs + i18n strings (EN + TH) | ~120 | 1 |
| Target-component pointing (data-attr based) | ~80 | 0.5 |
| Persistence + replay link in footer | ~80 | 0.5 |
| Tests (golden walkthrough + skip path) | ~150 | 1.5 |
| **Total** | **~830 LOC** | **~6.5 days** |

## Decisions (locked)

1. ~~Modal-blocking vs floating bubble?~~ → **Floating** (less
   intrusive; user can still scroll behind)
2. ~~Number of steps?~~ → **6** (sweet spot; 4 is too brief, 10 too
   tedious; based on Jitta / SWS onboarding lengths)
3. ~~Auto-trigger?~~ → **YES** on first visit (after small 2s delay so
   page renders fully first); plus footer replay link
4. ~~Show after returning user?~~ → **NO** — only first visit OR
   explicit replay; respect user's time

## Dependencies

- Phase 10 §1 explainer-tooltips — glossary links from onboarding
  steps reuse the Glossary modal
- Phase 10 §3 bilingual-i18n — step text comes from i18n JSON

## Out of scope

- Video tutorials (Phase 11)
- Per-feature walkthrough on later visits (e.g., comparison view
  walkthrough — Phase 11 if needed)
- Adaptive onboarding (different paths for beginner vs pro)
