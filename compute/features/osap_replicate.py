"""OpenAssetPricing (OSAP) per-stock signal replication.

Phase 4h commit 2. Builds a per-ticker signal map from OSAP's
long-short portfolio returns (Chen-Zimmermann 2022 *Critical Finance
Review*, github.com/OpenSourceAP/CrossSection). The fetcher in
``compute/ingest/osap.py`` returns the bulk parquet of
``signalname × port × date`` rows; this module aligns ``port=01``
(long bucket) against ``port=10`` (short bucket) per
``(signalname, date)``, picks the most-recent cross-section at or
before ``as_of``, ranks signals cross-sectionally by their long-short
return, and surfaces the per-signal rank as the ticker's OSAP
exposure proxy.

**Scope note** (locked 2026-05-18 plan audit). This is the
*factor-exposure proxy* version: every ticker receives the same
signal map, derived from the market-wide OSAP long-short return at
``as_of``. True per-stock signal replication — porting the ~100
signal formulas from OSAP's SAS / Stata source into pandas, fed by
our existing ``compute/features/`` pillar inputs — is the deferred
heavy lift. The proxy version is sufficient for Phase 4h's blend
target because:

1. ``osap_blended_score`` is *observability-only* in this phase
   (Top-5 ranking still uses ``composite_score``; SKILL.md Rule 16).
2. PR 4b §2 PBO/DSR gate
   (``compute/validation/pbo_dsr.py::factor_passes_gates``) runs on
   the long-short returns themselves, not the per-stock projection
   — so signal acceptance is identical to the full version.
3. Per-stock replication of all 100 signals slips Phase 4h by weeks
   without unblocking 4i/4j/4k.

If this module needs to graduate to true per-stock replication
later, the contract (``compute_osap_signals(returns, tickers, as_of)
-> dict[str, dict[str, float] | None]``) stays stable — only the
inner ``signal -> rank`` derivation changes per ticker.

Universe-gap policy: tickers receive ``None`` (NOT zero, NOT an
imputed neutral) when the as-of cross-section is empty (e.g.,
``as_of`` precedes OSAP coverage). Pillar
``compute_composite(neutralize_missing=True)`` imputes 50.0 for
missing pillars; OSAP intentionally does not — the blend layer
(commit 3, ``compute/scoring/osap_blend.py``) treats ``None`` as
"no OSAP adjustment" and passes ``composite_score`` through
unchanged.

No tenacity / network access in this module — all I/O is delegated
to the ingest layer.
"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from compute import config

logger = logging.getLogger(__name__)

# OSAP port-label convention (Chen-Zimmermann 2022, PredictorPortsFull.csv
# from the openassetpricing "op" dataset). port=01 is consistently the
# LONG bucket (highest-signal-rank portfolio) across signal cardinalities;
# the SHORT bucket varies with the signal's bucket count:
#   - decile signals:   ports 01..10 → SHORT = 10
#   - quintile signals: ports 01..05 → SHORT = 05
#   - tercile signals:  ports 01..03 → SHORT = 03
# Phase 4h.2 Part 2 (issue #116) replaced the hardcoded port=10 SHORT
# label with per-signal `min(port)` / `max(port)` inference, recovering
# the ~56 quintile / tercile signals that 0.9.0-0.9.1 silently dropped
# at the LS-derivation step.

# Columns the inbound DataFrame must carry. This is a *load-bearing*
# contract — the ingest layer already enforces
# ``REQUIRED_COLUMNS`` (``signalname, port, date, ret``); this module
# tightens the requirement only on the same four columns.
_REQUIRED_INPUT_COLUMNS: frozenset[str] = frozenset(
    {"signalname", "port", "date", "ret"}
)


def _normalize_port_label(port_series: pd.Series) -> pd.Series:
    """Coerce ``port`` to the canonical zero-padded string ('01', '02',
    ..., '10').

    OSAP's parquet may store ``port`` as int (1..10), int64, or
    zero-padded string depending on the release. The pivot step below
    is column-name sensitive, so we normalize once at the entry point
    rather than scatter ``astype(str).str.zfill(2)`` across helpers.
    """
    # Cast through str first to absorb any int / int64 / numpy.int64 /
    # categorical input. zfill ensures '1' → '01' and '10' stays '10'.
    return port_series.astype(str).str.zfill(2)


def compute_long_short_returns(returns: pd.DataFrame) -> pd.DataFrame:
    """Compute long-short return per ``(signalname, date)`` with per-signal
    port-pair inference.

    Phase 4h.2 Part 2 (issue #116) replaces the hardcoded ``port=01`` /
    ``port=10`` corner-bucket assumption with per-signal
    ``min(port)`` / ``max(port)`` inference, so quintile (01..05) and
    tercile (01..03) signals form long-short pairs instead of silently
    disappearing. Decile signals (01..10) degenerate to the same
    ("01", "10") corners — backward-compatible.

    Algorithm:
        1. Normalize ``port`` to zero-padded string.
        2. Per signal, derive ``(long_port, short_port) = (min(ports),
           max(ports))``. Drop signals with fewer than 2 distinct ports
           (no LS pair possible — surfaced via the sibling helper
           :func:`signals_dropped_no_long_short`).
        3. For each signal, keep only the rows whose port equals the
           long or short bucket (intermediate quintile / tercile / decile
           buckets are discarded).
        4. Pivot per ``(signalname, date)`` with the bucket role
           ("long" / "short") as the column axis, then compute
           ``ls_return = ret[long] - ret[short]`` and drop rows where
           either side is missing.

    Returns a DataFrame with columns: ``signalname``, ``date``,
    ``ls_return``. Empty DataFrame (same columns) when the input has
    no valid long-short pairs.
    """
    missing = _REQUIRED_INPUT_COLUMNS - set(returns.columns)
    if missing:
        raise ValueError(
            f"compute_long_short_returns missing columns {sorted(missing)}; "
            f"got {sorted(returns.columns)}. Check compute/ingest/osap.py "
            f"REQUIRED_COLUMNS contract."
        )

    if returns.empty:
        return pd.DataFrame(columns=["signalname", "date", "ls_return"])

    df = returns.copy()
    df["port"] = _normalize_port_label(df["port"])

    # Per-signal port-pair inference (Phase 4h.2 Part 2). Zero-padded
    # string min/max is lexicographic and matches numeric order for the
    # 2-char OSAP labels ('01' < '02' < ... < '10') because both
    # operands share the same width after _normalize_port_label.
    port_extents = df.groupby("signalname")["port"].agg(["min", "max"])
    port_extents.columns = ["long_port", "short_port"]
    port_extents = port_extents[
        port_extents["long_port"] != port_extents["short_port"]
    ]
    if port_extents.empty:
        return pd.DataFrame(columns=["signalname", "date", "ls_return"])

    df = df.merge(port_extents, left_on="signalname", right_index=True)
    keep = (df["port"] == df["long_port"]) | (df["port"] == df["short_port"])
    df = df[keep].copy()
    if df.empty:
        return pd.DataFrame(columns=["signalname", "date", "ls_return"])

    # Encode the role ("long" / "short") so the pivot column axis is
    # stable across signals with heterogeneous port labels (a decile
    # signal's "10" and a quintile signal's "05" both become "short").
    df["side"] = "long"
    df.loc[df["port"] == df["short_port"], "side"] = "short"

    pivot = df.pivot_table(
        index=["signalname", "date"],
        columns="side",
        values="ret",
        aggfunc="first",
    )

    if "long" not in pivot.columns or "short" not in pivot.columns:
        return pd.DataFrame(columns=["signalname", "date", "ls_return"])

    pivot["ls_return"] = pivot["long"] - pivot["short"]
    pivot = pivot.dropna(subset=["ls_return"])
    return pivot[["ls_return"]].reset_index()


def select_as_of_cross_section(
    ls_returns: pd.DataFrame, as_of: date
) -> pd.DataFrame:
    """For each signal, pick the most recent ``ls_return`` at or before
    ``as_of``.

    OSAP releases monthly — ``as_of`` is typically the most recent
    month-end. Signals whose latest available observation precedes
    ``as_of`` by more than one release cycle still surface (the staleness
    is intentional — Phase 4h's universe coverage is a separate metric).
    Signals with no observation at or before ``as_of`` are dropped.

    Returns a DataFrame with columns: ``signalname``, ``date``,
    ``ls_return``. Empty DataFrame when the entire window is empty.
    """
    if ls_returns.empty:
        return pd.DataFrame(columns=["signalname", "date", "ls_return"])

    as_of_ts = pd.Timestamp(as_of)
    df = ls_returns.copy()
    df["_date_ts"] = pd.to_datetime(df["date"])
    df = df[df["_date_ts"] <= as_of_ts]
    if df.empty:
        return pd.DataFrame(columns=["signalname", "date", "ls_return"])

    # For each signal, idxmax over the timestamp picks the most recent
    # observation at or before as_of. Behaviour on tie (same signal
    # observed twice on the same date) is to keep the first row —
    # acceptable because OSAP releases are monthly and per-signal
    # uniqueness on (signalname, date) is contractually enforced upstream.
    idx = df.groupby("signalname")["_date_ts"].idxmax()
    cross_section = (
        df.loc[idx, ["signalname", "date", "ls_return"]]
        .sort_values("signalname")
        .reset_index(drop=True)
    )
    return cross_section


def rank_signals_cross_sectional(cross_section: pd.DataFrame) -> pd.Series:
    """Rank signals by ``ls_return`` cross-sectionally, normalised to
    ``[0, 1]``.

    Uses ``pandas.Series.rank(method='average', pct=True)`` —
    average-rank for ties, percentile-normalised. No scipy dependency.

    Returns a Series indexed by ``signalname`` whose values are in
    ``(0, 1]``. Empty Series (dtype float, name 'rank') when the input
    cross-section is empty.
    """
    if cross_section.empty:
        return pd.Series(dtype=float, name="rank")

    ranks = cross_section.set_index("signalname")["ls_return"].rank(
        method="average", pct=True
    )
    ranks.name = "rank"
    return ranks


def compute_osap_signals(
    returns: pd.DataFrame,
    tickers: list[str],
    as_of: date,
    requested_signals: tuple[str, ...] | None = None,
) -> dict[str, dict[str, float] | None]:
    """Build the per-ticker OSAP signal map for ``as_of``.

    Args:
        returns: DataFrame from
            ``compute/ingest/osap.py::fetch_osap_returns``. Must include
            columns: ``signalname``, ``port``, ``date``, ``ret``.
        tickers: ticker symbols to populate the map for. Tickers are
            **not** filtered or validated — Phase 4h's universe set is
            assumed to be passed in.
        as_of: cross-section date. The most recent observation at or
            before this date is used per signal.
        requested_signals: optional restriction to a subset of signals.
            Defaults to ``config.OSAP_SIGNALS_100`` (the 100-signal
            manifest).

    Returns:
        ``{ticker: {signalname: rank} | None}``.

        - Inner-dict values are floats in ``(0, 1]`` (cross-sectional
          rank of the long-short return at ``as_of``).
        - Outer values are ``None`` when the as-of cross-section is
          empty (e.g., ``as_of`` precedes OSAP coverage, or no requested
          signal has any data). Distinct from pillar
          ``neutralize_missing`` — the blend layer treats ``None`` as
          "no OSAP adjustment" and passes ``composite_score`` through.

    Phase 4h commit 2 implements the *factor-exposure proxy*: every
    ticker receives the same signal map, derived from the market-wide
    OSAP long-short return cross-section. See the module docstring for
    why this is sufficient for the Phase 4h blend target.
    """
    if requested_signals is None:
        requested_signals = config.OSAP_SIGNALS_100

    requested_set = set(requested_signals)
    none_map: dict[str, dict[str, float] | None] = {t: None for t in tickers}

    if returns.empty:
        logger.info("OSAP returns DataFrame empty; returning None for all tickers")
        return none_map

    df = returns[returns["signalname"].isin(requested_set)]
    if df.empty:
        logger.info(
            "No requested signals found in OSAP returns (manifest=%d, "
            "available=%d); returning None for all tickers",
            len(requested_set),
            returns["signalname"].nunique(),
        )
        return none_map

    ls = compute_long_short_returns(df)
    if ls.empty:
        logger.info(
            "compute_long_short_returns produced empty cross-section for as_of=%s",
            as_of,
        )
        return none_map

    cs = select_as_of_cross_section(ls, as_of)
    if cs.empty:
        logger.info(
            "Cross-section at as_of=%s is empty (likely as_of precedes coverage)",
            as_of,
        )
        return none_map

    ranks = rank_signals_cross_sectional(cs)
    if ranks.empty:
        return none_map

    # Factor-exposure proxy: every ticker gets the same signal map.
    # Phase 4h commit 2 design — see module docstring for rationale.
    signal_map: dict[str, float] = {
        str(sig): float(rank) for sig, rank in ranks.items()
    }
    logger.info(
        "OSAP signals populated: %d signals × %d tickers (proxy mode)",
        len(signal_map),
        len(tickers),
    )
    # Use a fresh dict per ticker so downstream mutation doesn't leak
    # across rows (defensive — Pydantic deepcopies on validate, but the
    # writer path may not).
    return {t: dict(signal_map) for t in tickers}


def coverage_by_signal(
    signal_map: dict[str, dict[str, float] | None],
) -> dict[str, float]:
    """Report per-signal coverage % across the populated ticker set.

    In the Phase 4h commit 2 *proxy* mode every ticker gets the same
    signal map, so per-signal coverage is binary: either 100.0 (signal
    present in the cross-section) or 0.0 (signal absent or all-None
    tickers). Surfaced into
    ``metadata.json::osap_signals_coverage_pct`` by commit 5's
    ``compute/main.py`` wiring.

    Returns ``{signalname: coverage_pct}`` covering only signals that
    appeared in at least one ticker's map. Empty dict when all tickers
    are ``None``.
    """
    total = len(signal_map)
    if total == 0:
        return {}

    counts: dict[str, int] = {}
    for sig_dict in signal_map.values():
        if sig_dict is None:
            continue
        for sig in sig_dict:
            counts[sig] = counts.get(sig, 0) + 1

    return {sig: 100.0 * count / total for sig, count in counts.items()}


def signals_in_dataframe(df: pd.DataFrame) -> frozenset[str]:
    """Return unique ``signalname`` values present in an OSAP returns
    DataFrame.

    Phase 4h.2 Part 1 helper (issue #116). Used by
    ``compute/main.py`` to compute the manifest-vs-dataset set diff
    (``OSAP_SIGNALS_100 - signals_in_dataframe(returns)``) — the silent-
    drop surface that was invisible in Phase 4h's first production
    run.

    Single-purpose pure helper, unit-testable without main.py
    orchestration. Mirrors the shape of :func:`coverage_by_signal`
    above (no I/O, no logging, no side effects).

    Args:
        df: OSAP returns DataFrame. Expected to satisfy the
            ``signalname`` contract from
            ``compute/ingest/osap.py::REQUIRED_COLUMNS`` but defensive
            against absent column or empty input.

    Returns:
        ``frozenset[str]`` of unique signalname values. Empty
        frozenset when input is empty OR ``signalname`` column is
        absent (treat both as "no signals present" — caller's set
        diff then reports the full manifest as missing).
    """
    if df.empty or "signalname" not in df.columns:
        return frozenset()
    return frozenset(df["signalname"].unique().tolist())


def signals_dropped_no_long_short(returns: pd.DataFrame) -> list[str]:
    """Signals present in the OSAP fetch but with fewer than 2 distinct
    port buckets — the accounting-balance complement to
    :func:`signals_in_dataframe`.

    Phase 4h.2 Part 2 helper (issue #116). Before Part 2,
    :func:`compute_long_short_returns` silently dropped signals whose
    SHORT bucket label differed from the hardcoded ``"10"`` (i.e., every
    quintile / tercile / binary signal in the OSAP universe). Part 2's
    multi-port adapter brings them back, but signals with a single port
    bucket genuinely have no long-short pair — this helper surfaces
    them into ``Metadata.osap_signals_dropped_no_long_short`` so the
    100-signal manifest accounting balances.

    The Phase 4h.2 Part 2 accounting invariant:

        len(OSAP_SIGNALS_100) == (
            len(osap_signals_missing_from_dataset)    # 0 rows in dataset
            + len(osap_signals_dropped_no_long_short) # <2 distinct ports
            + len(osap_signals_used)                  # passed PBO/DSR gate
            + len(osap_excluded_signals)              # reached gate, failed
        )

    Args:
        returns: OSAP returns DataFrame from
            :func:`compute.ingest.osap.fetch_osap_returns`. Defensive
            against an empty input or a DataFrame missing ``signalname``
            or ``port`` (returns ``[]`` in either case — caller's
            accounting then treats this as "no diagnostic to surface").

    Returns:
        Sorted ``list[str]`` of signal names present in the dataset but
        with fewer than 2 distinct ``port`` values. Empty list when the
        input is empty / missing required columns / every signal has
        ≥ 2 ports.
    """
    if (
        returns.empty
        or "signalname" not in returns.columns
        or "port" not in returns.columns
    ):
        return []

    normalized = _normalize_port_label(returns["port"])
    per_signal_port_count = (
        returns.assign(_port_norm=normalized)
        .groupby("signalname")["_port_norm"]
        .nunique()
    )
    dropped = per_signal_port_count[per_signal_port_count < 2].index.tolist()
    return sorted(str(s) for s in dropped)
