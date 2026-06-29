"""Multi-class aggregate-filer detector (Issue #261; post-#456 informational).

Detects tickers in the universe that share a CIK with at least one
other ticker — the signature of a multi-class issuer whose SEC
``companyfacts`` API reports the company-TOTAL share count across all
classes rather than a per-class breakdown.

**Post-#456 semantics (RATIFY-B, ASC 260).** The #456 dual-class fix
made ``raw_metrics.shares_outstanding`` the SEC company-total aggregate
on purpose, and the #261 CLOSE-AS-CORRECT verdict (methodology-scientist,
2026-06-15) confirmed that basis is *correct* under ASC 260: the
aggregate market_cap IS the issuer's real equity value (Alphabet's
~$4.34T is correct; the per-class listed count lives in display-only
``shares_outstanding_listed_class``). So this module is **not** a
corruption detector — it is an informational tag that surfaces the
multi-class-filer pattern at the per-ticker level for cohort visibility.
Using the per-class count instead would re-introduce the #456
PE-contamination bug.

Examples (steady state — six known S&P 500 multi-class lines):

- Alphabet: GOOG (Class C) + GOOGL (Class A), CIK ``0001652044`` —
  both report the company-total market_cap (correct, ASC 260).
- News Corp / Fox: NWS + NWSA and FOX + FOXA share CIKs and also
  fire this flag — they ALSO appear in the PR #257
  ``MULTI_CLASS_SHARE_ALLOWLIST`` (which handles a separate
  *companyfacts-undercount* pattern by per-filing XBRL dimensional
  SUM, distinct from this detector). The two are orthogonal: PR #257's
  dimensional override corrects undercounts via the ingest layer; this
  annotate surfaces the multi-class-filer structure at the per-ticker
  level for Q3 audit visibility.

Annotate-only per :mod:`portable-annotate-before-veto`. Composite
rank UNCHANGED — the flag surfaces in
``StockDetail.valuation_warnings`` for the detail-page UI and
``Metadata.multi_class_aggregate_shares_suspected_count`` for Q3
2026-08-19 quarterly-audit cohort visibility. The user-visible
annotate string still reads as a "suspected" tag; relabeling it to an
explicit "multi-class aggregate filer" informational tag is deferred to
the Q3 2026-08-19 cohort audit (Issue #484 Item 2) so the
output-semantics change moves with that review.

Anchor: methodology-scientist Mode B verdict on Issue #261
(2026-05-26) + CLOSE-AS-CORRECT verdict (2026-06-15). Damodaran 2019
*Investment Valuation* 3rd ed. Ch. 16 §"Multiple Classes of Shares".
The CIK-collision detector is the cleanest universe-level signature —
it catches Alphabet (CIK ``0001652044``), News Corp / Fox, and any
future S&P 500 multi-class addition without a hardcoded ticker list.
"""

from __future__ import annotations

from statistics import median
from typing import Final

#: Market-cap floor expressed as a fraction of the universe median
#: ``market_cap``. Methodology-scientist Mode B verdict 2026-05-26:
#: 10% of the universe median catches all six known S&P 500 multi-
#: class tickers (GOOG, GOOGL, NWS, NWSA, FOX, FOXA — each above the
#: floor on the 2026-05-23 cron) while excluding micro-class artifacts
#: (e.g., a tracking-stock subsidiary that files separately but is
#: < 1% of the parent's economic footprint). Threshold provenance:
#: **gut-feel calibration** — no paper anchors an absolute floor; the
#: 10% relative threshold is a Q3 2026-08-19 quarterly-audit
#: recalibration target after ≥ 1 cron's firing-rate data accumulates
#: in ``Metadata.multi_class_aggregate_shares_suspected_count``.
MARKET_CAP_FLOOR_RATIO: Final[float] = 0.10


def detect_multi_class_aggregate_shares_suspected(
    cik_by_ticker: dict[str, str | None],
    market_cap_by_ticker: dict[str, float | None],
) -> set[str]:
    """Return the set of tickers that should fire the annotate.

    Trigger (methodology-scientist Mode B 2026-05-26):

    1. Ticker's CIK appears on at least one OTHER ticker in the
       universe (CIK collision = multi-class filer signature).
    2. Ticker's ``market_cap`` exceeds
       ``MARKET_CAP_FLOOR_RATIO × universe-median(market_cap)``.

    Args:
        cik_by_ticker: mapping ticker -> CIK string. ``None`` allowed
            when no fundamentals snapshot was built (e.g., live SEC
            fetch failed) — tickers with ``None`` CIK are excluded
            from collision detection (cannot collide on missing data).
        market_cap_by_ticker: mapping ticker -> ``market_cap`` float
            (computed by the caller as ``current_price ×
            shares_outstanding``). ``None`` allowed when share count
            or price is missing — excluded from the median computation
            AND from the firing set (cannot exceed a floor when value
            is unknown).

    Returns:
        Set of ticker symbols that fire the annotate. Empty set when
        no CIK collisions exist OR when no tickers meet the
        market-cap floor.
    """
    cik_to_tickers: dict[str, list[str]] = {}
    for ticker, cik in cik_by_ticker.items():
        if cik is None:
            continue
        cik_to_tickers.setdefault(cik, []).append(ticker)

    market_caps = [
        mc for mc in market_cap_by_ticker.values() if mc is not None and mc > 0
    ]
    if not market_caps:
        return set()
    universe_median_mc = median(market_caps)
    floor = MARKET_CAP_FLOOR_RATIO * universe_median_mc

    flagged: set[str] = set()
    for tickers in cik_to_tickers.values():
        if len(tickers) < 2:
            continue
        for ticker in tickers:
            mc = market_cap_by_ticker.get(ticker)
            if mc is not None and mc > floor:
                flagged.add(ticker)
    return flagged
