# Bilingual Thai + English (Phase 10 planning stub)

**Status**: Planning. Adds Thai language as first-class language
alongside English. QuantRank originates from Thai dev community; Thai
content unlocks a much larger retail audience.

## Purpose

Most retail stock-analysis tools in Thai market are paid (Jitta, Settrade
membership). QuantRank already has English UX; adding Thai = 10× the
retail Thai-speaking addressable users without methodology changes.

## Architecture

Use [next-intl](https://next-intl-docs.vercel.app/) — Next.js 14 App
Router compatible, static-export friendly, lightweight.

```
frontend/
  i18n/
    en.json   # all English strings (already implicit in code)
    th.json   # Thai translations
    config.ts # locale registry
  middleware.ts  # locale routing (/en/, /th/, default /en/)
  app/
    [locale]/
      page.tsx       # ranking
      stock/[ticker]/page.tsx  # detail
      compare/[tickers]/page.tsx  # comparison
```

### Locale toggle

Top-right header next to "GitHub" link:
```
[ EN / TH ]
```
Click → switch locale + persist preference in localStorage. URL
updates to `/th/` or `/en/` prefix.

### Translation coverage

All user-facing strings:
- Headers (S&P 500 ranking → "อันดับ S&P 500")
- Disclaimer ("Educational use only" → "เพื่อการศึกษาเท่านั้น")
- Metric labels (Composite → "คะแนนรวม", MoS → "ส่วนต่างความปลอดภัย")
- Recommendation tier display (Strong Buy → "แนะนำซื้อ", Hold → "ถือ")
- Filter chip labels
- Tooltip + glossary content (Phase 10 §1)
- Error messages, empty states

### NOT translated

- Ticker symbols (NVDA stays NVDA)
- Sector names (Information Technology stays — GICS English convention)
- Internal schema IDs (`bullish`, `lean_bullish`, etc.)
- Numbers / dates (locale-aware formatting via `Intl.NumberFormat`)

## Effort

| Step | LOC | Days |
|---|---|---|
| `next-intl` setup + locale config | ~80 | 0.5 |
| `en.json` — extract all hardcoded strings (~200 entries) | ~600 | 3 |
| `th.json` — Thai translations (~200 entries) | ~600 | 4 (translation + native review) |
| Component refactor — replace literal strings with `t()` calls | ~300 | 2 |
| Locale toggle component | ~100 | 0.5 |
| Locale routing + middleware + static-export config | ~120 | 1 |
| Number / date formatting via `Intl.NumberFormat(locale)` | ~80 | 0.5 |
| Glossary modal (Phase 10 §1) — i18n-aware content | ~150 | 1 |
| Tests + visual regression both locales | ~200 | 1.5 |
| **Total** | **~2230 LOC** | **~14 days** |

## Decisions (locked)

1. ~~Which i18n library?~~ → **next-intl** (Next.js 14 App Router
   native; static-export compatible; popular)
2. ~~URL prefix shape?~~ → **`/en/`, `/th/`** (RFC-style standard;
   SEO-friendly; defaults to `/en/`)
3. ~~Default locale?~~ → **English** (codebase already English; Thai is
   opt-in via toggle)
4. ~~Translate sector names?~~ → **NO** (GICS keeps English to match
   how SEC filings classify; "Information Technology" is the formal
   name, "เทคโนโลยีสารสนเทศ" is informal)
5. ~~Ticker symbol localization?~~ → **NO** (NVDA stays NVDA everywhere)
6. ~~AI translation or native review?~~ → **AI-translate draft + native
   review pass** (free machine translation produces ~80% quality; the
   20% nuance that retail-finance contexts need requires native ear)

## Translation glossary (sample)

| English | Thai |
|---|---|
| Strong Buy | แนะนำซื้อ |
| Buy | ซื้อ |
| Hold | ถือ |
| Sell | ขาย |
| Composite Score | คะแนนรวม |
| Margin of Safety | ส่วนต่างความปลอดภัย |
| Loss Chance | โอกาสขาดทุน |
| Fair Price | ราคายุติธรรม |
| Bullish | ขาขึ้น |
| Cautious | ระวัง |
| Educational use only | เพื่อการศึกษาเท่านั้น |
| Not investment advice | ไม่ใช่คำแนะนำการลงทุน |

Full glossary in `frontend/i18n/glossary.csv` for native reviewer.

## Dependencies

- Phase 10 §1 explainer-tooltips — glossary lives in i18n JSON, so
  Thai glossary is part of this PR's deliverable
- Phase 0-8 stable schema — translation strings depend on which UI
  elements exist; bilingual launches AFTER Phase 8 stable

## Out of scope

- 3rd language (Japanese, Chinese, Vietnamese) — Phase 11+
- Right-to-left languages (Arabic, Hebrew) — Phase 11+
- Currency display switch (USD → THB) — Phase 11+ (price display
  stays USD since data is US equities)
- Locale-aware compute results — composite doesn't change with locale

## Marketing impact

Once Phase 10 bilingual ships, README + landing page can target Thai
retail community directly. Estimated traffic uplift: 3-5× based on
Jitta's Thai-language SEO position.
