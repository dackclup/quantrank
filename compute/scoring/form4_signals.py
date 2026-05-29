"""Form 4 insider-transaction annotates (Phase 4.5e PR 3).

Two annotate-only flags emitted on the cache surface populated by
``compute/scoring/form4_insider.py`` (PR 1) and observability-validated
by ``Metadata.form4_*`` (PR 2). Per ``portable-annotate-before-veto``
and SKILL.md Rule 16: composite rank unchanged; flags surface in
``StockSummary.valuation_warnings`` only.

Flags
-----

**``insider_sell_cluster``** — multi-insider concentrated-sell signal.
Fires when:

- ``≥ 3 distinct insiders`` (by CIK, deduped)
- with ``transaction_code in {"S", "D"}`` (open-market or sale-back-to-issuer;
  Cohen-Malloy-Pomorski 2012 §III.A "opportunistic" set — explicitly excludes
  codes ``A`` (grant), ``M`` (derivative exercise), ``F`` (tax-via-shares),
  ``G`` (gift) as compensation-mechanical / non-information-bearing)
- within a ``30-day`` rolling window
- AND cohort-aggregate ``dollar_value`` summed across those insiders ≥
  ``$1,000,000``

**``c_suite_unusual_sell``** — CEO + CFO concentrated-sell sub-signal.
Fires when:

- ``≥ 2 distinct C-suite insiders`` where ``officer_title`` matches
  ``/\\b(CEO|CFO|Chief Executive|Chief Financial|President)\\b/i``
  (deliberately narrow per Jeng-Metrick-Zeckhauser 2003; excludes
  COO/CTO/CMO/CHRO which are operational not financial-information)
- with ``transaction_code in {"S", "D"}``
- within a ``30-day`` rolling window

Strict-superset relationship: when both flags fire, the C-suite flag's
weight is a DELTA on top of the cluster flag's weight (same semantic
as ``RESTATEMENT_HIGH_CONFIDENCE_WEIGHT`` vs
``RESTATEMENT_HISTORY_WEIGHT`` in PR #165). Combined contribution =
``INSIDER_SELL_CLUSTER_WEIGHT + C_SUITE_UNUSUAL_SELL_WEIGHT = 5 + 3 = 8``
pts ≈ ``REM_SUSPECT_WEIGHT``.

Threshold provenance (per Phase 2.5 tier convention)
----------------------------------------------------

- **Distinct-insider count ≥ 3**: LITERATURE-ANCHORED to
  Cohen-Malloy-Pomorski 2012 *J. Finance* §IV.A, "Decoding Inside
  Information," who define a cluster as ≥ 3 insiders trading in the
  same direction within a calendar quarter. Cluster trades carry ~6×
  the predictive content of single-insider trades.
- **30-day window**: GUT-FEEL ACCEPTABLE. CMP 2012 use ~90d
  (calendar-quarter); Jagolinzer 2009 *Mgmt Sci* §3.2 shows ~50%
  signal decay past 60d so tightening to 30d targets the
  high-information regime. Revisit at Q3 2026-08-19 quarterly audit
  if firing rate < 2% (CMP's quarterly base rate on cluster-sells is
  ~5-8%; 30d cohort is expected lower).
- **$1,000,000 cohort-aggregate floor**: GUT-FEEL. No paper anchors
  an absolute dollar floor — CMP 2012 §III, Cohen 2008 *J. Finance*
  §2, and Jagolinzer 2009 all use RELATIVE sizing (% of insider's
  existing holding sold). $1M is engineering choice for S&P 500
  scale; future PR may add a per-insider relative gate (drop
  insiders selling < 10% of ``shares_owned_following + shares``) to
  better match CMP's "opportunistic vs routine" classification.
- **Transaction codes {S, D}**: LITERATURE-ANCHORED to CMP 2012
  §III.A "opportunistic" definition. Code F (payment-via-shares) is
  compensation-mechanical and explicitly excluded by the literature.
- **10b5-1 filter (PR 4-eq, 2026-05-23)**: LITERATURE-ANCHORED to
  Cohen 2008 §III routine-vs-opportunistic partition (10b5-1 plans
  are pre-scheduled, hence ⊊ routine), Jagolinzer 2009 §3.1
  (10b5-1 trades exhibit ~75% lower forward-return predictability
  vs unscheduled), and the SEC's "Insider Trading Arrangements and
  Related Disclosures" final rule (Release 33-11138, effective
  2023-04-01) that mandated structured 10b5-1 disclosure.
  ``_is_opportunistic_sell`` requires NOT ``is_rule_10b5_one is True``
  in addition to the code ∈ {S, D} gate so 10b5-1 scheduled trades
  are excluded from BOTH cluster + C-suite cohort counts. None and
  False both pass (None = no footnote disclosure parsed — option
  (a) per methodology-scientist Mode B 2026-05-23, matches the
  CMP/Jagolinzer empirical regime used to calibrate the thresholds).
- **C-suite count ≥ 2 (CEO + CFO)**: LITERATURE-ANCHORED to
  Jeng-Metrick-Zeckhauser 2003 *RFS* §V; CFO + CEO co-sells precede
  ~5-7% 6-month negative abnormal returns. Title regex narrowed to
  CEO/CFO/President per Wachtell-Lipton 2018 governance-survey
  finding that 31% of S&P 500 companies use President as the
  operating-CEO title.
- **30-day window for C-suite**: LITERATURE-ANCHORED to Jagolinzer
  2009 §3.2 showing C-suite signal half-life ~45d (faster decay than
  the broader insider pool).

Weight provenance
-----------------

- ``INSIDER_SELL_CLUSTER_WEIGHT = 5.0`` (annotate-mid tier alongside
  ``restatement_history``, ``accruals_momentum_high``,
  ``loss_avoidance_pattern``). LITERATURE-ANCHORED on cite, GUT-FEEL
  on magnitude. Original reserved slot at 10.0 (PR 1 reservation)
  downgraded for PR 3 launch pending cohort-PPV acceptance check.
  Bushman-Smith 2003 *J. Acct. Econ.* review warns post-SOX
  insider-trade signal degraded 30-50%; conservative weight protects
  against false-positive penalties on contamination modes (10b5-1
  scheduled trades, vesting-driven liquidations). Promote to 10.0
  only after empirical PPV against forward 6-month returns matches
  CMP 2012's reported magnitude on the S&P 500 universe.
- ``C_SUITE_UNUSUAL_SELL_WEIGHT = 3.0`` (annotate-delta tier alongside
  ``beneish_high``, ``dechow_high``, ``restatement_high_confidence``).
  **Weight semantics: DELTA not total** — same pattern as PR #165's
  ``RESTATEMENT_HIGH_CONFIDENCE_WEIGHT``. When this flag fires the
  broader ``insider_sell_cluster`` ALSO fires (strict superset); both
  are summed → combined contribution = 5 + 3 = 8 pts ≈
  ``REM_SUSPECT_WEIGHT``. Provenance: LITERATURE-ANCHORED on the PPV
  ratio (JMZ 2003 C-suite signal ~2-3× broad cluster).

Footguns
--------

1. **10b5-1 contamination — MITIGATED in PR 4-eq (2026-05-23).**
   SEC Rule 10b5-1 allows insiders to set up pre-scheduled trading
   plans that carry near-zero information-asymmetry signal.
   Jagolinzer 2009 finds 10b5-1 trades are ~25-40% of S&P 500
   insider sales post-2003 (SEC's 2022 economic analysis updates the
   2018-2021 large-cap regime to ~50-60% by sale dollar-value).
   CMP 2012 §III.B opportunistic-only subset carries 4× the
   predictive content; without filtering, expected FP rate is
   40-60% per Jagolinzer 2009.

   **Mitigation in this PR**: ``_is_opportunistic_sell`` gates on
   NOT ``is_rule_10b5_one is True`` so 10b5-1 scheduled trades are
   excluded from both cluster + C-suite cohort counts. Source field
   resolved per-transaction by ``form4_insider._detect_10b5_1_on_transaction``
   via footnote-text pattern scan (edgartools 5.31.5 does NOT parse
   the SEC structured ``<aff10b5One>`` XML element added in the
   2023-04-01 mandate — see ``form4_insider.py`` module docstring
   §"Footnote resolution" for the access-path rationale).

   Expected firing-rate delta (methodology Mode B 2026-05-23):
   ``insider_sell_cluster`` -30% to -45% (absolute 4-10%),
   ``c_suite_unusual_sell`` -45% to -65% (absolute 1-4%). Q3
   2026-08-19 cohort audit gates whether to promote
   ``INSIDER_SELL_CLUSTER_WEIGHT`` 5.0 → 7.0 (mid-point — vesting-
   driven liquidations remain a separate ~15-25% contamination per
   Aboody et al. 2010 §3.2).

   **PR 6 (2026-05-28)** — residual negation-guard hardening landed.
   ``detect_10b5_1_plan`` is now wrapped by a post-detector regex
   guard that downgrades a True detection to False when the resolved
   footnote text contains a negation phrase (``terminated`` /
   ``cancelled`` / ``no`` / ``previously`` / ``former`` / etc.)
   within ±5 word tokens of the 10b5-1 mention. Pre-PR-6 the
   detector matched True on FP phrases like "10b5-1 plan terminated
   2022" or "no 10b5-1 plan in effect" — conservatively over-
   excluding legitimate opportunistic trades from the cluster
   cohort. PR 6 reverses this bias toward ground truth. Expected
   delta-firing-rate per Cohen 2008 §III + Jagolinzer 2009 §3.2:
   ``insider_sell_cluster`` +5% to +10% relative on a universe-
   baseline cron (absolute << 1%; most 10b5-1 disclosures are
   affirmative, not negated). Universe count surfaces as
   ``Metadata.form4_negation_guard_downgrade_count`` per Rule 18.

   Residual: ~10-15% routine-but-not-10b5-1 trades per Jagolinzer
   2009 §3.2 (insider whose Q1 sale 14d post-10-K is consistent
   across 5y but never filed a 10b5-1 plan). Full Cohen 2008
   routine-vs-opportunistic classifier requires a 5y per-insider
   lookback the current 180d cache cannot satisfy without a
   structural change — deferred to a future iteration.

2. **Post-earnings-window seasonal clustering**: Insiders are barred
   from trading during the 30-day pre-earnings blackout window and
   transact in a concentrated 2-3 week window starting ~3 business
   days after the 10-Q is filed. This creates artificial clustering
   that has nothing to do with insider information — it's a
   compliance artifact. The current implementation does NOT
   earnings-shift the window; expected over-firing in the 4-25-day
   post-earnings band. Mitigation: a future PR will compute the
   cluster window relative to the latest ``raw_metrics.fiscal_period_end``
   and reject clusters that fall entirely within the legal-trading
   band. Until then, the annotate-only contract + Q3 cohort audit
   will catch over-firing.

3. **Joint-filer + stale officer-title**: ``form4_insider.py`` takes
   ``owners[0]`` only on multi-owner filings; an officer + entity
   co-filing may suppress the C-suite flag if the entity is the [0]
   owner. ``officer_title`` is set at filing time and not retroactively
   updated when an executive changes roles — a former-CFO who is now
   a board member may still appear as ``officer_title="CFO"`` on
   filings older than the role change. Both noise floors documented
   here; the joint-filer fix is a scout-module change deferred to a
   follow-up; the stale-title fix (sort by ``filing_date`` desc within
   a CIK group, prefer the most recent title) is a future-iteration
   refinement.

References
----------

- **Cohen-Malloy-Pomorski 2012** *Journal of Finance* 67(3),
  1009-1043 — "Decoding Inside Information." Cluster ≥ 3 insiders /
  same-quarter rule; opportunistic-trade definition (excludes
  A/M/F/G codes); cluster sells precede ~1.2% monthly abnormal
  returns.
- **Jeng-Metrick-Zeckhauser 2003** *Review of Financial Studies*
  16(2), 453-484 — "Estimating the Returns to Insider Trading." CFO
  + CEO co-sell signature; CFO-specific PPV premium on accruals-
  related information; 30-90d signal-decay curve.
- **Jagolinzer 2009** *Management Science* 55(2), 224-239 —
  "SEC Rule 10b5-1 and Insiders' Strategic Trade." Documents the
  signal-decay half-life used for the 30d window choice; also the
  primary 10b5-1-contamination paper (footgun #1).
- **Lakonishok-Lee 2001** *Review of Financial Studies* 14(1),
  79-111 — "Are Insider Trades Informative?" Baseline noise floor
  and aggregate-insider-portfolio result.
- **Cohen 2008** *Journal of Finance* 63(4), 1593-1640 —
  "Opportunistic vs Routine Insiders." Routine-vs-opportunistic
  classification mechanic; basis for the relative-size gate proposed
  as a follow-up.
- **Bushman-Smith 2003** *Journal of Accounting & Economics* 32,
  237-333 — "Transparency, Financial Accounting Information, and
  Corporate Governance." Post-SOX insider-signal degradation; basis
  for the conservative-weight argument.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Final

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Thresholds — see module docstring §"Threshold provenance"
# ---------------------------------------------------------------------------

#: CMP 2012 §IV.A canonical cluster definition.
INSIDER_SELL_CLUSTER_MIN_DISTINCT_INSIDERS: Final[int] = 3

#: Jagolinzer 2009 §3.2 high-information regime (vs CMP's ~90d).
INSIDER_SELL_CLUSTER_LOOKBACK_DAYS: Final[int] = 30

#: Engineering floor for S&P 500 scale — see footgun #1 caveat re
#: relative-vs-absolute sizing.
INSIDER_SELL_CLUSTER_MIN_DOLLAR_VALUE: Final[float] = 1_000_000.0

#: JMZ 2003 §V CFO + CEO co-sell signature.
C_SUITE_UNUSUAL_SELL_MIN_DISTINCT_INSIDERS: Final[int] = 2

#: Jagolinzer 2009 §3.2 C-suite signal half-life ~45d.
C_SUITE_UNUSUAL_SELL_LOOKBACK_DAYS: Final[int] = 30

#: CMP 2012 §III.A "opportunistic" transaction-code set.
#: S = open-market or private sale, D = sale back to issuer.
#: F (payment-via-shares) is compensation-mechanical — excluded.
_OPPORTUNISTIC_SELL_CODES: Final[frozenset[str]] = frozenset({"S", "D"})

#: Narrow C-suite regex per JMZ 2003 + Wachtell-Lipton 2018.
#: Matches CEO, CFO, "Chief Executive [Officer]", "Chief Financial
#: [Officer]", or "President". Deliberately EXCLUDES COO/CTO/CMO/CHRO
#: which are operational not financial-information.
_C_SUITE_TITLE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(CEO|CFO|Chief\s+Executive|Chief\s+Financial|President)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_transaction_date(tx: dict) -> date | None:
    """Resolve the best-available date for a transaction row.

    Prefer ``transaction_date`` (the actual trade date in SEC's Table I),
    fall back to ``filing_date`` (the SEC-receipt date, typically 1-2
    business days after the transaction). Returns ``None`` when both are
    missing or malformed — caller should skip the row.
    """
    for key in ("transaction_date", "filing_date"):
        raw = tx.get(key)
        if not raw:
            continue
        try:
            return datetime.strptime(str(raw)[:10], "%Y-%m-%d").date()
        except (TypeError, ValueError):
            continue
    return None


def _is_opportunistic_sell(tx: dict) -> bool:
    """Per CMP 2012 §III.A: open-market sale (S) or sale-back-to-issuer (D),
    with the PR 4-eq 10b5-1 contamination filter applied.

    Returns True only when:

    - ``transaction_code ∈ {"S", "D"}`` (opportunistic-code partition;
      A/M/F/G are compensation-mechanical and excluded)
    - AND ``is_rule_10b5_one`` is NOT ``True`` (None and False both
      pass — see module docstring §"Footguns" #1 for the option (a)
      None-handling rationale per Cohen 2008 + Jagolinzer 2009)

    Pre-PR-4-eq cache rows lack the ``is_rule_10b5_one`` key entirely;
    ``dict.get`` returns None on those, which keeps the row in the
    opportunistic cohort. Forward-compatible: when the field is True,
    the row is dropped (10b5-1 scheduled trade excluded).
    """
    if str(tx.get("transaction_code", "")).upper() not in _OPPORTUNISTIC_SELL_CODES:
        return False
    return tx.get("is_rule_10b5_one") is not True


def _is_c_suite(tx: dict) -> bool:
    """Per JMZ 2003 §V: title matches CEO/CFO/President (narrow set)."""
    if not tx.get("is_officer"):
        return False
    title = tx.get("officer_title")
    if not title:
        return False
    return bool(_C_SUITE_TITLE_PATTERN.search(str(title)))


def _window_filter(
    transactions: list[dict],
    as_of: date,
    lookback_days: int,
) -> list[dict]:
    """Return only transactions whose effective date falls within
    ``[as_of - lookback_days, as_of]`` (inclusive)."""
    cutoff = as_of - timedelta(days=lookback_days)
    out: list[dict] = []
    for tx in transactions:
        tx_date = _parse_transaction_date(tx)
        if tx_date is None:
            continue
        if cutoff <= tx_date <= as_of:
            out.append(tx)
    return out


# ---------------------------------------------------------------------------
# Public predicates
# ---------------------------------------------------------------------------


def detect_insider_sell_cluster(
    transactions: list[dict] | None,
    as_of: date,
) -> bool:
    """Fire ``insider_sell_cluster`` when:

    - ≥ ``INSIDER_SELL_CLUSTER_MIN_DISTINCT_INSIDERS`` (3) distinct
      insiders (by ``insider_cik``)
    - with ``transaction_code`` in ``{"S", "D"}``
    - within a ``INSIDER_SELL_CLUSTER_LOOKBACK_DAYS`` (30) day window
      ending ``as_of``
    - AND cohort-aggregate ``dollar_value`` ≥
      ``INSIDER_SELL_CLUSTER_MIN_DOLLAR_VALUE`` ($1M)

    Returns ``False`` on None / empty / missing fields — safe default
    so the annotate doesn't fire on tickers with no Form-4 coverage.
    """
    if not transactions:
        return False
    windowed = _window_filter(transactions, as_of,
                              INSIDER_SELL_CLUSTER_LOOKBACK_DAYS)
    if not windowed:
        return False

    distinct_ciks: set[str] = set()
    total_dollar_value = 0.0
    for tx in windowed:
        if not _is_opportunistic_sell(tx):
            continue
        cik = tx.get("insider_cik")
        if not cik:
            continue
        distinct_ciks.add(str(cik))
        dollar_value = tx.get("dollar_value")
        if isinstance(dollar_value, (int, float)):
            total_dollar_value += float(dollar_value)

    return (
        len(distinct_ciks) >= INSIDER_SELL_CLUSTER_MIN_DISTINCT_INSIDERS
        and total_dollar_value >= INSIDER_SELL_CLUSTER_MIN_DOLLAR_VALUE
    )


def detect_c_suite_unusual_sell(
    transactions: list[dict] | None,
    as_of: date,
) -> bool:
    """Fire ``c_suite_unusual_sell`` when:

    - ≥ ``C_SUITE_UNUSUAL_SELL_MIN_DISTINCT_INSIDERS`` (2) distinct
      C-suite insiders (by ``insider_cik``; ``officer_title`` matches
      the narrow CEO/CFO/President regex)
    - with ``transaction_code`` in ``{"S", "D"}``
    - within a ``C_SUITE_UNUSUAL_SELL_LOOKBACK_DAYS`` (30) day window
      ending ``as_of``

    Returns ``False`` on None / empty / missing fields — safe default.
    """
    if not transactions:
        return False
    windowed = _window_filter(transactions, as_of,
                              C_SUITE_UNUSUAL_SELL_LOOKBACK_DAYS)
    if not windowed:
        return False

    distinct_ciks: set[str] = set()
    for tx in windowed:
        if not _is_opportunistic_sell(tx):
            continue
        if not _is_c_suite(tx):
            continue
        cik = tx.get("insider_cik")
        if not cik:
            continue
        distinct_ciks.add(str(cik))

    return len(distinct_ciks) >= C_SUITE_UNUSUAL_SELL_MIN_DISTINCT_INSIDERS


def count_10b5_1_filtered_transactions(
    transactions: list[dict] | None,
    as_of: date,
) -> int:
    """Count transactions excluded by the PR 4-eq 10b5-1 filter — i.e.,
    transactions that WOULD have been classified as opportunistic
    (``code ∈ {S, D}``) absent the filter, but were dropped because
    ``is_rule_10b5_one is True``.

    Counted only WITHIN the broader cluster lookback window so the
    metric directly tracks the contamination eliminated from the
    cluster-detection input, not 10b5-1 trades in general.

    Used by ``compute/main.py`` to populate
    ``Metadata.form4_rule10b5_one_excluded_count`` — the Rule 18
    diagnostic that gates the Q3 2026-08-19 cohort-acceptance check
    (issue #130). Expected universe-wide delta vs PR #222 baseline:
    -30% to -45% on ``insider_sell_cluster_firing_count`` per
    methodology-scientist Mode B 2026-05-23 (Jagolinzer 2009 §3.2 +
    SEC 2022 economic analysis).

    Returns 0 on None / empty / no windowed transactions — safe
    default for tickers with no Form-4 coverage.
    """
    if not transactions:
        return 0
    windowed = _window_filter(
        transactions, as_of, INSIDER_SELL_CLUSTER_LOOKBACK_DAYS
    )
    if not windowed:
        return 0
    count = 0
    for tx in windowed:
        if str(tx.get("transaction_code", "")).upper() not in _OPPORTUNISTIC_SELL_CODES:
            continue
        if tx.get("is_rule_10b5_one") is True:
            count += 1
    return count


__all__ = [
    "C_SUITE_UNUSUAL_SELL_LOOKBACK_DAYS",
    "C_SUITE_UNUSUAL_SELL_MIN_DISTINCT_INSIDERS",
    "INSIDER_SELL_CLUSTER_LOOKBACK_DAYS",
    "INSIDER_SELL_CLUSTER_MIN_DISTINCT_INSIDERS",
    "INSIDER_SELL_CLUSTER_MIN_DOLLAR_VALUE",
    "count_10b5_1_filtered_transactions",
    "detect_c_suite_unusual_sell",
    "detect_insider_sell_cluster",
]
