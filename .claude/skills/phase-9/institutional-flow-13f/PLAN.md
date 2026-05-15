# Institutional Flow via SEC 13F (Phase 9 planning stub)

**Status**: Planning. Quarterly 13F filings let retail track what
Berkshire/Bridgewater/Pershing Square are buying. Free, public,
already in EDGAR.

## Purpose

SEC Form 13F = quarterly filing by institutional managers with >$100M
AUM. Lists all US-listed long positions as of quarter-end. 45-day lag.
A stock that 5+ top funds initiated last quarter has different return
expectations than one being exited.

Phase 9 §3: aggregate 13F filings from ~50 top-tier institutional
managers, surface per-stock chip showing institutional flow direction.

## Free data source

SEC EDGAR Form 13F-HR (Holdings Report) — fully free. ~5000 funds file
per quarter; we curate a tracking list of ~50.

## Curated tracker fund list (~50 funds)

| Tier | Funds | Why |
|---|---|---|
| Value | Berkshire Hathaway, Tweedy Browne, Greenlight Capital | Long-term value investors |
| Growth | Tiger Global, Coatue, ARK Invest, Whale Rock | Tech growth |
| Quant | Renaissance, Two Sigma, AQR, DE Shaw | Algorithm-driven |
| Macro | Bridgewater, Pershing Square (Ackman), Soros Fund | Big picture |
| Activist | Pershing Square, Elliott, ValueAct | Concentrated activist plays |

List in `compute/ingest/trackers.py` — re-verify yearly.

## Signal features

Per stock per quarter:

| Feature | Logic |
|---|---|
| `n_trackers_holding` | Count of tracked funds holding > 0 shares |
| `n_trackers_added` | Count that increased position vs prior quarter |
| `n_trackers_exited` | Count that exited fully vs prior quarter |
| `top_holder_concentration` | Largest single position size (% of fund's portfolio) |
| `aggregate_flow_pct` | (current $ in stock - prior $) / market cap |

## UI display

Beginner-friendly chip with hover tooltip:

| Signal | Pill | Tooltip |
|---|---|---|
| 3+ trackers added (and 0 exited) | 🟢 "Smart money adding" | "3 of 50 tracked funds increased position last quarter" |
| 5+ trackers holding | 🟢 "Widely held" | "5 funds in our tracker list have positions" |
| 2+ trackers exited | 🔴 "Smart money exiting" | "2 funds exited fully last quarter" |
| (none) | — no badge | |

Per-stock detail page can list **which funds** for transparency
("Berkshire Hathaway added 200K shares — see source filing →").

## Effort

| Step | LOC | Days |
|---|---|---|
| 13F XML parser (edgartools facade) | ~150 | 2 |
| Aggregate across ~50 tracked funds | ~100 | 1 |
| Quarterly cache (90-day TTL, manual bump on quarterly filing date) | ~50 | 0.5 |
| Schema additions (`institutional_flow_signal`) | ~30 | 0.25 |
| InstitutionalFlowBadge component | ~80 | 0.5 |
| Detail-page table "Tracked fund holdings" | ~120 | 1 |
| Tests (mock 13F XML) | ~150 | 1.5 |
| **Total** | **~680 LOC** | **~7 days** |

## Decisions (locked)

1. ~~Universe of trackers?~~ → **~50 curated** (not all 5000 13F filers — too noisy)
2. ~~Update cadence?~~ → **Quarterly** (45-day post-quarter-end SEC deadline)
3. ~~Show fund names on detail page?~~ → **Yes** for transparency (links to source filing)
4. ~~Include hedge fund shorts?~~ → **No** (13F doesn't disclose shorts; only longs)

## Dependencies

- Phase 4a workflow cache — caches 13F XML
- 90-day cache key (quarterly cadence)

## Out of scope

- 13D/G activist filings (more frequent, different signal)
- Mutual fund N-PORT (monthly but private until 60d delay)
- ETF holdings (different filing structure)
- Family Office trackers (don't file 13F if AUM < $100M)
