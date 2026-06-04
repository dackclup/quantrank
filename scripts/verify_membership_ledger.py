"""Integrity verifier for ``data/sp500_membership_historical.csv``.

Reverse-walks ``members_at()`` from the CURRENT universe (the frontend
``rankings.json`` snapshot) across every month of the 5-year backtest window
and checks two invariants:

1. **Consistency** — every ticker the ledger REMOVES in-window (and never
   re-adds) must be ABSENT from the current universe; every ticker the ledger
   ADDS in-window (and never removes) must be PRESENT. A violation means a
   stale/wrong event or a cron-lagged universe.
2. **Size band** — the reconstructed S&P 500 size must stay within the index
   band (~500 companies / ~502-503 stocks with multi-class) at every month. A
   drift localizes a missing or extra event to the month it appears.

This is the Phase 7.0 PR-0 survivorship gate (methodology-scientist: the ledger
must be verified before any backtest leg is trusted). Re-run after any edit to
the CSV.

    python scripts/verify_membership_ledger.py

Exit 0 = clean; 1 = drift / inconsistency found.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from compute.ingest.historical_universe import (  # noqa: E402
    list_known_events,
    members_at,
)

RANKINGS = ROOT / "frontend" / "public" / "data" / "rankings.json"
ANCHOR = date(2026, 6, 3)        # metadata.json last_update_utc date
WINDOW_START = date(2021, 6, 1)  # 5-year backtest window start
BAND = (498, 506)                # S&P 500: ~500 companies, ~502-503 stocks


def current_universe() -> frozenset[str]:
    data = json.loads(RANKINGS.read_text())
    return frozenset(r["ticker"] for r in data)


def month_starts(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield date(y, m, 1)
        m += 1
        if m > 12:
            m, y = 1, y + 1


def main() -> int:
    uni = current_universe()
    events = list_known_events()
    adds = {e.ticker for e in events if e.action == "ADD"}
    rms = {e.ticker for e in events if e.action == "REMOVE"}

    print(f"current universe : {len(uni)} tickers (anchor {ANCHOR})")
    print(f"ledger           : {len(events)} events "
          f"({events[0].effective_date} .. {events[-1].effective_date})")

    ok = True

    # Invariant 1 — consistency vs the anchor universe
    bad_rm = sorted(t for t in (rms - adds) if t in uni)
    bad_add = sorted(t for t in (adds - rms) if t not in uni)
    if bad_rm:
        ok = False
        print(f"\n[FAIL] {len(bad_rm)} REMOVED-in-window but STILL in universe "
              f"(stale/wrong remove): {bad_rm}")
    if bad_add:
        ok = False
        print(f"\n[FAIL] {len(bad_add)} ADDED-in-window; never removed; NOT in "
              f"universe (cron-lag / wrong ticker): {bad_add}")

    # Invariant 2 — size band across the backtest window
    print(f"\nmonthly reconstructed size (band {BAND[0]}-{BAND[1]}):")
    worst = (ANCHOR, len(uni))
    out_of_band = 0
    for d in month_starts(WINDOW_START, ANCHOR):
        n = len(members_at(d, uni, anchor_date=ANCHOR).tickers)
        if not (BAND[0] <= n <= BAND[1]):
            ok = False
            out_of_band += 1
            print(f"  {d}  size={n}  <-- OUT OF BAND")
        if abs(n - 502) > abs(worst[1] - 502):
            worst = (d, n)
    print(f"  worst deviation: {worst[0]} size={worst[1]} "
          f"({out_of_band} month(s) out of band)")

    print("\nRESULT:", "CLEAN" if ok else "ISSUES FOUND")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
