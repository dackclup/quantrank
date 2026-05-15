# Stock Story (Phase 11 planning stub)

**Status**: Planning. P0 differentiator surfaced in 2026-05-15 audit.
Simply Wall St's killer feature = LLM-generated 2-3 sentence "story"
per stock. Beginners read narrative > numbers. QuantRank can match +
exceed via Claude API + open prompt engineering.

## Purpose

Beginners stare at "Composite 72 · Buy · Loss Chance 35%" and don't
know how to **interpret** it. A 2-3 sentence summary in plain language
turns numbers into actionable insight:

> "NVDA is rated **Strong Buy** on a composite of 70.7, leading in
> momentum and growth pillars. The biggest concern is its Margin of
> Safety: at current $230, the price is 271% above our fair-value
> estimate of $62. The Sloan accruals flag also raises an
> annotate-level warning. Despite the strong composite, the deep
> overvaluation pushes the recommendation to **Sell**."

Plain-language summary + transparent reasoning trail. **Differentiates
QuantRank from Bloomberg/Refinitiv** (which use raw numbers only) AND
from SimplyWallSt (whose stories are opaque LLM black box without
source attribution).

## Architecture

```
compute/scoring/stock_story.py        # Claude API client; build prompt; parse response
compute/output/schemas.py             # StockDetail.story: string | None
frontend/components/StockStoryCard.tsx
```

### Prompt construction (deterministic input → variable LLM output)

```python
prompt = f"""
Write a 2-3 sentence summary of {ticker} ({company_name}) for a
beginner retail investor. Use neutral, fact-based language. NO
investment advice phrasing.

Inputs:
- Composite score: {composite_score}
- Recommendation: {recommendation_label}  ({recommendation_internal_id})
- Loss Chance: {loss_chance_pct}%
- MoS: {mos_pct}%
- Sector: {sector}
- Active risk flags: {risk_flags}
- Active valuation warnings: {valuation_warnings}
- Best pillar: {best_pillar} ({best_pillar_score})
- Worst pillar: {worst_pillar} ({worst_pillar_score})

Output a single paragraph (2-3 sentences). Mention:
1. What our methodology says (composite + recommendation)
2. The dominant reason (biggest pillar or biggest concern)
3. NO predictions, NO "should buy/sell" advice

Style: matter-of-fact, like a journalist not a salesperson.
"""
```

The prompt is **deterministic** (function of compute output). The LLM
output is variable but the prompt enforces structure. Cache per-stock
output; refresh weekly with new data.

### Anthropic Claude API usage

Use `claude-haiku-4-5` for cost-efficient narrative generation (~$0.001
per stock × 502 stocks = ~$0.50/week). User provides API key via
GitHub Secret; not required for ranking-table to render.

**Cost discipline**: if API key not set → `StockStoryCard` hidden;
graceful degradation. The site stays $0 for end users (only the
maintainer's $0.50/week if they choose to enable it).

### Optional: User-side LLM

Power users can paste their own Anthropic API key in browser
localStorage → frontend calls Claude directly. Server-side never
touches the key. Privacy-preserving + decentralized.

## UI display

### StockStoryCard on detail page
Between header card and price chart:
```
┌─────────────────────────────────────────────────────────────┐
│ 📖 Summary                                       Generated 5d ago │
│                                                                  │
│ NVDA is rated Strong Buy on a composite of 70.7, leading in     │
│ momentum and growth pillars. The biggest concern is its Margin  │
│ of Safety: at current $230, the price is 271% above our fair-   │
│ value estimate of $62...                                         │
│                                                                  │
│ [👁 See methodology trail]  [🔄 Regenerate]                       │
└─────────────────────────────────────────────────────────────┘
```

### Transparency button
"See methodology trail" → opens modal showing:
- The exact prompt used
- The inputs (with links to source: composite, MoS, etc.)
- The LLM response (verbatim)
- Generated-on timestamp

This is **what Simply Wall St doesn't do** — full attribution.

## Effort

| Step | LOC | Days |
|---|---|---|
| `stock_story.py` + Claude API client (reuse `claude-api` vendored skill) | ~250 | 2 |
| Prompt engineering + golden-output regression tests | ~200 | 2 |
| Schema additions (`StockDetail.story` + `story_generated_at`) | ~50 | 0.5 |
| `StockStoryCard.tsx` + transparency modal | ~300 | 2.5 |
| Detail-page integration | ~50 | 0.5 |
| Bilingual prompt (TH + EN) | ~100 | 1 |
| Caching (per-stock, 7-day TTL) | ~80 | 0.5 |
| Cost-discipline guard (no-API-key → hidden) | ~60 | 0.5 |
| Tests (mock API + golden fixtures) | ~180 | 1.5 |
| **Total** | **~1270 LOC** | **~11 days** |

## Decisions (locked 2026-05-15)

1. ~~Which LLM?~~ → **Claude Haiku 4.5** (cost-efficient, ~$0.001/call,
   matches `claude-api` vendored skill's recommendation)
2. ~~Server-side vs client-side LLM call?~~ → **Both supported** — server
   when maintainer's API key set; client when user's API key set in
   localStorage
3. ~~Always-on or opt-in?~~ → **Opt-in via env var** — no API key set =
   feature hidden gracefully
4. ~~Generate at compute time or render time?~~ → **Compute time +
   cache 7 days** — predictable cost, no per-render overhead
5. ~~Transparency level?~~ → **FULL prompt + response visible** — sets
   QuantRank apart from black-box competitors

## Free-tier discipline

Maintainer cost ceiling: $1/week = $52/year. Way below other
infrastructure costs (which are $0). Acceptable for v3.0 launch tier.

If usage hits cost ceiling, fallback to:
1. Self-host smaller LLM (Llama 3.2 on Modal free tier)
2. Use Claude API free tier (rate-limited but $0)
3. Disable feature, keep rest of site working

## Dependencies

- Anthropic `claude-api` skill (vendored ใน `.claude/skills/claude-api/`)
- Phase 10 §3 `bilingual-i18n/PLAN.md` — Thai version of prompt
- Phase 4d recommendation + Phase 4e loss-chance (both done) — input
  variables for the prompt

## Out of scope

- Streaming LLM responses (not needed for static-export site)
- Multi-LLM ensemble (GPT-4 + Claude + Gemini consensus) — over-
  engineering
- Auto-generation of investment thesis from earnings calls (Phase 6+)
- User-customized prompt templates — Phase 11+
