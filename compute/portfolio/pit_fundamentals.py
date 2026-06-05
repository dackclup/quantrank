"""Point-in-time fundamentals selection for the Phase 7.0 backtest backfill.

This module is the **anti-look-ahead guardrail** the methodology-scientist
flagged as the single most important correctness point in PR-2b: when
re-scoring the composite at a historical rebalance date ``T``, the fundamentals
fed to the pillars MUST be only what was publicly filed on or before ``T``.

It is deliberately **pure + pandas-free + fundamentals-free** (it imports no
``FundamentalsSnapshot``): it operates on plain annual-history rows (the
backfill converts the cached ``_build_annual_history`` DataFrame into these
dicts once), so the filed-``<=``-T / 10-K-only / most-recent-fiscal-year
selection logic is unit-testable offline without any market data, pandas, or
EDGAR. The thin glue that builds the actual ``FundamentalsSnapshot`` +
filtered history DataFrame from these outputs lives in the backfill script.

Methodology basis (ratified 2026-06-04, Option A): annual (10-K) figures in
place of the live TTM basis; ``filing_date <= T`` AND ``form_type == "10-K"``
(amendments excluded) so the as-of-T view sees the originally-filed number,
not a later restatement. See ``docs/GOTCHAS.md`` (membership ledger entry's
sibling — the backtest point-in-time discipline).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

# Only an originally-filed annual report counts as point-in-time fundamentals.
# A 10-K/A (amendment) filed later to RESTATE a prior year is excluded by both
# the filing_date <= T gate and this form_type gate, so the as-of-T view keeps
# the number that was actually public at T.
_PIT_FORM_TYPES: frozenset[str] = frozenset({"10-K"})

AnnualRow = Mapping[str, object]
"""One annual fact: keys ``metric`` (str), ``fiscal_year`` (int), ``value``
(float), ``filing_date`` (ISO ``YYYY-MM-DD`` str), ``form_type`` (str)."""


def _eligible(row: AnnualRow, as_of: str) -> bool:
    """True iff the row was an originally-filed 10-K public on or before ``as_of``."""
    fd = row.get("filing_date")
    ft = row.get("form_type")
    val = row.get("value")
    if not isinstance(fd, str) or not fd:
        return False
    if ft not in _PIT_FORM_TYPES:
        return False
    if val is None or (isinstance(val, float) and val != val):  # None / NaN
        return False
    # ISO YYYY-MM-DD compares lexically == chronologically.
    return fd <= as_of


def select_pit_annual_values(
    rows: Iterable[AnnualRow], as_of: str
) -> dict[str, float]:
    """Most-recent annual value per metric known on or before ``as_of``.

    For each ``metric``, keep the eligible row (10-K, ``filing_date <= as_of``)
    with the LARGEST ``fiscal_year``; ties broken by the later ``filing_date``.
    Returns ``{metric: value}``. A metric with no eligible row is omitted (the
    downstream pillar treats a missing field as NaN -> neutral per Rule 7).
    """
    best: dict[str, tuple[int, str, float]] = {}  # metric -> (fy, filing_date, value)
    for row in rows:
        if not _eligible(row, as_of):
            continue
        metric = row.get("metric")
        if not isinstance(metric, str):
            continue
        try:
            fy = int(row["fiscal_year"])  # type: ignore[arg-type]
            value = float(row["value"])  # type: ignore[arg-type]
        except (KeyError, TypeError, ValueError):
            continue
        fd = str(row["filing_date"])
        cur = best.get(metric)
        if cur is None or (fy, fd) > (cur[0], cur[1]):
            best[metric] = (fy, fd, value)
    return {metric: v for metric, (_, _, v) in best.items()}


def pit_snapshot_fields(rows: Iterable[AnnualRow], as_of: str) -> dict[str, float]:
    """Point-in-time annual values + the two derived fields the snapshot needs.

    Wraps ``select_pit_annual_values`` and adds ``free_cash_flow`` (= OCF -
    capex) and ``ebitda`` (= operating_income + D&A) when their components are
    present and not already supplied. The backfill filters the returned dict to
    valid ``FundamentalsSnapshot`` field names before constructing the dataclass
    (this module stays decoupled from that schema).
    """
    vals = select_pit_annual_values(rows, as_of)

    if "free_cash_flow" not in vals:
        ocf = vals.get("operating_cash_flow")
        capex = vals.get("capex")
        if ocf is not None and capex is not None:
            # capex is reported as a (usually negative) outflow OR a positive
            # magnitude depending on the tag; the snapshot path treats capex as a
            # magnitude subtracted from OCF — mirror the live derivation by using
            # the absolute capex so a sign convention can't flip FCF.
            vals["free_cash_flow"] = ocf - abs(capex)

    if "ebitda" not in vals:
        oi = vals.get("operating_income")
        da = vals.get("depreciation_and_amortization")
        if oi is not None and da is not None:
            vals["ebitda"] = oi + abs(da)

    return vals


def pit_history_rows(rows: Sequence[AnnualRow], as_of: str) -> list[dict]:
    """The eligible (10-K, filing_date <= as_of) annual rows, all fiscal years.

    The growth pillar's CAGRs + the quality pillar's Piotroski F-score need
    MULTIPLE fiscal years, not just the latest — so the backfill rebuilds a
    history DataFrame from THIS filtered subset (not the raw frame) before it
    reaches ``_growth_metrics`` / ``_quality_metrics``. Without this filter
    those functions would read a fiscal year filed AFTER ``as_of`` and silently
    look ahead (the 0.40-weight leak the methodology-scientist warned about).
    """
    return [dict(r) for r in rows if _eligible(r, as_of)]
