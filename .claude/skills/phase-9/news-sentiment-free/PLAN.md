# News Sentiment from Free Sources (Phase 9 planning stub)

**Status**: Planning. Adds news / social sentiment from purely-free
sources to complement Phase 6's FinBERT (which scans 10-K text).

## Purpose

Phase 6 `finbert-score` scans annual filing text — slow-moving, deep
signal. Phase 9 §5 adds **fast-moving daily / weekly** sentiment from
free news + social channels: headline scoring, Reddit r/stocks
mention volume, etc. Different time horizon, complementary signal.

## Free data sources (no paid API)

| Source | Cost | Coverage |
|---|---|---|
| **NewsAPI free tier** | $0 (100 requests/day) | English news headlines, last 30 days |
| **Reddit JSON API** | $0 (no auth needed for public subs) | r/stocks + r/wallstreetbets + r/investing |
| **Hacker News Algolia API** | $0 | YC tech / business headlines |
| **AP / Reuters RSS** | $0 | Wire-service headlines |
| **Wikipedia revision rate** | $0 | Editing activity on company page (proxy for attention) |

Each source emits ~daily; cache for 24h freshness.

## Signal features

Per stock per week:

| Feature | Source | Logic |
|---|---|---|
| `news_mention_count_7d` | NewsAPI + AP RSS | Count of headlines mentioning ticker |
| `news_sentiment_avg_7d` | NewsAPI titles → FinBERT scorer | Mean compound score [-1, +1] |
| `reddit_mention_count_7d` | Reddit r/stocks + r/wsb | Count of posts/comments |
| `reddit_velocity_change` | week-over-week | Change vs prior week |
| `wikipedia_edits_30d` | Wikipedia API | Edits per month (proxy for attention) |

Combined "sentiment heat" = weighted blend (news 0.5, reddit 0.3,
wikipedia 0.2). Re-scale to 0-100.

## UI display (beginner-friendly)

Per-stock chip:

| Pattern | Pill | Tooltip |
|---|---|---|
| Sentiment heat ≥ 75 (top decile) | 🟢 "Buzz: high positive" emerald-50 | "Strong positive coverage in news + social last 7 days" |
| Sentiment heat ≤ 25 (bottom decile) | 🔴 "Buzz: negative" red-50 | "Negative coverage spike last 7 days" |
| `reddit_velocity_change ≥ 3x` | 🟡 "Reddit spike" amber-50 | "WSB / r/stocks mentions tripled this week" |
| 25 < heat < 75 | — no chip (most stocks) | |

The 🟡 reddit spike chip is **separate** from sentiment because
retail-driven meme volume isn't always positive (e.g., GME 2021).

## Effort

| Step | LOC | Days |
|---|---|---|
| NewsAPI ingest + cache | ~100 | 1 |
| Reddit JSON ingest (no auth) | ~120 | 1 |
| Wikipedia revision count | ~50 | 0.5 |
| FinBERT scoring of headlines (reuse Phase 6 model) | ~80 | 0.5 |
| Aggregate sentiment-heat score + smoothing | ~100 | 1 |
| Schema additions | ~40 | 0.25 |
| 2 frontend chips (sentiment + reddit-spike) | ~120 | 1 |
| Detail-page expandable news headlines panel | ~200 | 2 |
| Tests + golden fixtures | ~180 | 1.5 |
| **Total** | **~990 LOC** | **~9 days** |

## Dependencies

- Phase 6 `finbert-score` PLAN — scorer reused for headlines (faster
  than annual filings; needs streaming-batch logic)
- Phase 4a workflow cache — caches NewsAPI + Reddit JSON responses

## Decisions (locked)

1. ~~NewsAPI paid tier?~~ → **NO — free tier only** (100/day enough for
   weekly batch)
2. ~~Twitter API?~~ → **NO** (paid since 2023; not in free-tier scope)
3. ~~Reddit auth?~~ → **NO — public JSON only** (no OAuth needed)
4. ~~Show raw headlines?~~ → **Yes on detail page** (transparency; user
   reads source for themselves) — link out to news source

## Cost considerations

NewsAPI free tier = 100 requests/day. For 502 stocks weekly + 7-day
window, we batch by sector (11 sectors × 7 days = 77 requests/week
well under 100/day). Cache aggressively.

Reddit JSON has no published rate limit but reasonable etiquette =
2-second delay between requests. Weekly compute can run 30-min Reddit
batch.

## Out of scope

- Twitter / X data (paid only)
- StockTwits (different free API; defer to 9.x)
- Bloomberg / FT premium content (paid)
- Earnings call live transcripts (Phase 6 `whisper-transcribe`)
