"""Multi-class shares aggregate-overcount annotate (Issue #261).

Detects tickers in the universe that share a CIK with at least one
other ticker — the signature of a multi-class issuer whose SEC
``companyfacts`` API returns the AGGREGATE share count across all
classes rather than the per-class breakdown. When such tickers
appear at S&P 500 scale (market_cap > 10% of universe median),
each per-class ticker's reported ``market_cap`` is the aggregate
(~2× the real per-class value), producing a user-visible $4-5T
market cap display for what is actually a ~$1T company per class.

Examples on the 2026-05-23 cron #3:

- Alphabet: GOOG (Class C) + GOOGL (Class A), CIK ``0001652044``,
  both reporting market_cap $4.6T vs real ~$1.05T per class.
- News Corp / Fox: NWS + NWSA and FOX + FOXA share CIKs and also
  fire this flag — they ALSO appear in the PR #257
  ``MULTI_CLASS_SHARE_ALLOWLIST`` (which handles the
  *companyfacts-undercount* pattern by per-filing XBRL dimensional
  SUM, distinct from this overcount pattern). The two flags are
  orthogonal: PR #257's dimensional override corrects undercounts
  via the ingest layer; this annotate surfaces the structural
  pattern at the per-ticker level for Q3 audit visibility.

Annotate-only per :mod:`portable-annotate-before-veto`. Composite
rank UNCHANGED — the flag surfaces in
``StockDetail.valuation_warnings`` for the detail-page UI and
``Metadata.multi_class_aggregate_shares_suspected_count`` for Q3
2026-08-19 quarterly-audit cohort visibility. A structural fix for
the GOOG/GOOGL overcount path (reverse-allowlist per-class XBRL
extraction) lands in a follow-up PR after ``edgar-debugger``
verifies Alphabet's dimensional context shape.

Anchor: methodology-scientist Mode B verdict on Issue #261
(2026-05-26). Damodaran 2019 *Investment Valuation* 3rd ed.
Ch. 16 §"Multiple Classes of Shares" — by accounting identity
``Σ per-class market_cap = aggregate market_cap``; a per-class
ticker that reports the aggregate violates the identity. The CIK-
collision detector is the cleanest universe-level signature — it
catches Alphabet (CIK ``0001652044``), News Corp / Fox, and any
future S&P 500 multi-class addition without a hardcoded ticker
list.
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
