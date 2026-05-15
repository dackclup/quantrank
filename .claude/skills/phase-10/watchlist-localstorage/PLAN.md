# Watchlist via localStorage (Phase 10 planning stub)

**Status**: Planning. "Killer retail feature" that every comparable
tool has (Jitta, SWS, Yahoo Finance, Robinhood). Persistent across
sessions, no login required.

## Purpose

User wants to track 5-20 specific stocks across visits without
manually searching each time. Current UX requires searching every
visit. Watchlist solves it without requiring login/auth.

## Approach: localStorage (no auth)

| Constraint | Approach |
|---|---|
| No backend / no auth required | `localStorage` keyed by ticker |
| Persist across browser sessions | Persists by default (not sessionStorage) |
| Cross-device sync | Out of scope (would need auth — Phase 11+) |
| Privacy | Lives entirely in user's browser; nothing sent to server |

## Architecture

```
frontend/lib/watchlist-storage.ts   # load / save / add / remove / clear
frontend/components/WatchlistStar.tsx  # ⭐ toggle button on each row + detail
frontend/components/WatchlistDrawer.tsx  # slide-in panel showing all saved
frontend/components/RankingTable.tsx  # add WatchlistStar column
frontend/app/stock/[ticker]/page.tsx  # add WatchlistStar to header
```

### Storage shape (versioned, like filter-storage)

```typescript
const STORAGE_KEY = 'quantrank.watchlist.v1';

type WatchlistEntry = {
  ticker: string;
  added_at: string;  // ISO timestamp
};

type WatchlistSnapshot = {
  entries: WatchlistEntry[];  // ordered by `added_at`
  max_size: 100;  // cap to prevent abuse / unreasonable sizes
};
```

## UI

### Star toggle on each row

```
#  Ticker     Name             Sector       Score  ...   ⭐
#1 CF  ⭐     CF Industries    Materials    75.2         (filled)
#2 HST       Host Hotels      Real Estate  72.1         (outline)
```

Clicking ⭐ adds/removes from watchlist; persists in localStorage.

### Watchlist drawer

Click "Watchlist" button in header toolbar (next to Filters) → slide-
in panel from right showing all saved stocks with mini-rows
(ticker + sector + composite + recommendation badge). Click any row
to navigate to detail page.

Empty state: "Star a stock from the ranking to add it here."

### Filter integration

Add `Only show my watchlist` toggle in `FilterDrawer.tsx` — useful for
focused browsing.

## Effort

| Step | LOC | Days |
|---|---|---|
| `watchlist-storage.ts` (load/save/add/remove + shape validation) | ~150 | 1 |
| `WatchlistStar.tsx` component | ~80 | 0.5 |
| `WatchlistDrawer.tsx` slide-in panel | ~250 | 2 |
| RankingTable + detail page wire-up | ~80 | 0.5 |
| FilterDrawer "Only my watchlist" toggle | ~50 | 0.5 |
| Tests (golden path + storage failures) | ~150 | 1 |
| Tutorial tooltip on first visit ("Star to save") | ~50 | 0.5 |
| **Total** | **~810 LOC** | **~6 days** |

## Decisions (locked)

1. ~~Auth-based watchlist?~~ → **NO** — adds backend complexity; static-
   site model rules. Cross-device sync deferred to Phase 11+
2. ~~Cookie vs localStorage?~~ → **localStorage** (no expiry, larger
   capacity, no server visibility, privacy-friendly)
3. ~~Cloud backup?~~ → **NO** — keeps privacy + free + simple
4. ~~Max size cap?~~ → **100 entries** (prevent abuse; user unlikely
   to need more than that)

## Privacy + transparency

- Watchlist NEVER leaves user's browser
- No analytics tracks which stocks are starred
- Clear UI affordance: "Watchlist lives on this device only"

## Dependencies

- Phase 4 filter-storage (PR #65) — same versioned-key pattern
- Phase 10 §1 explainer-tooltips — onboarding tooltip explaining the
  ⭐ star UX

## Out of scope

- Multi-watchlist (folders / lists) — Phase 10.x or Phase 11
- Sharing watchlist via URL — Phase 11
- Watchlist notifications (price alerts) — Phase 11+
- Public watchlist of influencer / curator — Phase 11+
