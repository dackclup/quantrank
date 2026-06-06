"""Phase 4j.1 — Qlib Alpha158 feature → long-short return adapter.

Observability-only PR (SKILL.md Rule 18). This module converts the
Alpha158 *feature panel* (per-stock-per-date feature VALUES) into the
``(signalname, date, ls_return)`` long-short return contract that the
already-ratified PBO/DSR gate
(:func:`compute.validation.osap_validation.gate_osap_signals`) consumes
— so Alpha158 reuses the exact Phase-4h gate machinery without
reimplementing any PBO/DSR math. No blend, no score mutation, no
``StockDetail`` field is written this phase: every Alpha158 surface is
diagnostic ``Metadata`` only and ``composite_score`` is byte-identical
to pre-4j.1 (Δscore = 0 on every ticker). The actual blend that could
influence rank is deferred to 4j.2 (≥ 1 cron later, after the
accounting equation is verified on real data).

Why an adapter is needed (the structural difference from OSAP)
==============================================================

OSAP (Phase 4h) ships precomputed long-short portfolio RETURN series;
``compute/features/osap_replicate.py::compute_long_short_returns``
pivots them straight into the gate contract. Alpha158 is different —
``compute/ingest/qlib_features.py::fetch_alpha158_features`` returns a
``(date, ticker)``-indexed matrix of 158 per-stock feature *values*,
not portfolio returns. The PBO/DSR gate needs a ``(date × signal)``
return matrix, so this adapter inserts the missing conversion: per
feature, per month, cross-sectionally rank the universe and form a
top-decile-minus-bottom-decile long-short portfolio on the NEXT
month's forward return. This is the canonical Fundamental-Law decile-
spread construction (Grinold & Kahn 2000, *Active Portfolio
Management* 2nd ed. Ch. 6) — zero free parameters (the decile cut is
fixed; no in-sample optimization happens here), so it adds no
overfitting surface of its own; all multiple-testing defense stays
downstream in the gate.

Academic-prior discipline (methodology-scientist GO-WITH-CONDITIONS, 2026-06-06)
===============================================================================

**Yang, Liu, Zhou, Bian, Liu 2020 — "Qlib: An AI-oriented Quantitative
Investment Platform", arXiv:2009.11189 [q-fin.GN] — is an
IMPLEMENTATION reference for the Alpha158 expression set, NOT an
effect-size anchor.** The paper is an arXiv-only engineering/platform
preprint (not peer-reviewed); it reports no standalone per-feature
information coefficient (its IC figures, e.g. LightGBM IC≈0.045 on
CSI300, are *model* benchmarks on Chinese A-shares, not factor-level
effect sizes) and self-describes Alpha158 as "carefully designed by
human (feature engineering)" — i.e. a re-expression of classical
technical-analysis indicators, with no novelty claim. The real
per-family priors are the classical literature:

- **K-bar shape** (KMID/KLEN/KUP/KLOW/KSFT…) → candlestick / intrabar
  microstructure literature.
- **Rolling-price** (ROC/MA/STD/RANK/RSV/MAX/MIN/QTLU/QTLD) →
  Jegadeesh & Titman 1993 momentum (the family QuantRank's momentum
  pillar + the OSAP ``Momentum`` theme already encode — expect high
  φ-overlap, see §Orthogonality below).
- **CORR / BETA / RSQR / RESI** → market-beta / Frazzini & Pedersen
  2014 (Betting-Against-Beta) adjacency.
- **Volume-flow** (VMA/VSTD/WVMA/VSUMP/VSUMN/VSUMD) → volume /
  liquidity factor literature.

**Acceptance is decided by the Bailey-López de Prado PBO/DSR gate +
the Harvey-Liu-Zhu 2016 t ≥ 3.0 multiple-testing hurdle (n_trials =
158), NOT by any Alpha158 paper claim.** A surfaced rolling-12m
|IC| materially above the METHODOLOGY.md realistic band (0.02-0.05) is
an OVERFIT / look-ahead ALARM to audit, never a win.

Orthogonality (surfaced in 4j.1, gated in 4j.2)
===============================================

The rolling-price families overlap heavily (φ ≈ 0.5-0.7) with the
momentum pillar + OSAP ``Momentum`` theme; the genuinely additive
content is the K-bar (intrabar shape) + volume-flow families
(φ < 0.3 expected). 4j.1 only OBSERVES this — it blends nothing, so no
φ-gate is applied here. 4j.2 may blend a PBO/DSR survivor only if it
ALSO clears ``|φ| < 0.30`` (Cohen 1988 medium-effect / the
``docs/phase3-correlation/findings.md`` redundancy threshold) against
every accepted OSAP signal + the momentum/technical pillar exposures.

Survivorship honesty (methodology condition #2)
===============================================

The per-month ranking universe is built from the point-in-time
membership snapshot (``universe_provider``, wired to
``compute.ingest.historical_universe.members_at``), NOT the current
502-survivor universe — otherwise the decile-spread returns are
survivorship-inflated even when the diagnostic flag reads "corrected".
:meth:`Alpha158LongShort.survivorship_bias_corrected` is ``True`` only
when a ``universe_provider`` was supplied AND every consumed month was
complete; a single degraded (incomplete) month flips it to ``False``.

Look-ahead discipline (methodology condition #2)
================================================

The forward return is the NEXT month's realized return: the adapter
owns the lag (it shifts the trailing-return panel by one period
internally), so a feature value known as of month ``m`` is only ever
paired with the return realized over ``(m, m+1]``. A contemporaneous
join — feature@m against the return ending at ``m`` — would silently
inflate IC and is the look-ahead trap the lag-discipline test pins.

No network / no Qlib import here — the feature panel is handed in by
the ingest layer; this module is pure pandas and offline-testable.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date

import pandas as pd

logger = logging.getLogger(__name__)

# Minimum cross-section size before a decile spread is formable. With
# the 0.10 / 0.10 default deciles this guarantees ≥ 1 name per leg and
# disjoint long/short legs (2 ≤ 10). Below this floor the month forms
# no long-short row for the feature (it counts toward
# ``features_dropped_no_long_short`` only if the feature NEVER forms a
# row across the whole panel).
MIN_UNIVERSE_FOR_DECILE_SPREAD: int = 10

# The long-short contract columns — identical to
# ``osap_replicate.compute_long_short_returns`` so the existing
# ``osap_validation.gate_osap_signals`` consumes Alpha158 unchanged.
_LS_COLUMNS: tuple[str, ...] = ("signalname", "date", "ls_return")

# universe_provider(as_of) -> (members, is_complete). ``is_complete`` is
# False when the point-in-time membership reconstruction fell back /
# could not be certified for that month.
UniverseProvider = Callable[[date], "tuple[Iterable[str], bool]"]


@dataclass(frozen=True)
class Alpha158LongShort:
    """Adapter output: the gate-ready long-short matrix + survivorship verdict.

    ``long_short`` carries columns ``{signalname, date, ls_return}`` —
    one row per ``(feature, month)`` that formed a decile spread —
    ready to feed :func:`compute.validation.osap_validation.gate_osap_signals`
    with ``signalname`` = Alpha158 feature name.

    ``survivorship_bias_corrected`` is ``True`` only when a
    ``universe_provider`` was supplied AND every consumed month was
    complete (point-in-time honest). ``False`` when no provider was
    given (cannot certify membership) or any consumed month was
    degraded.
    """

    long_short: pd.DataFrame
    survivorship_bias_corrected: bool


def _empty_long_short() -> pd.DataFrame:
    return pd.DataFrame(columns=list(_LS_COLUMNS))


def _normalize_panel_index(panel: pd.DataFrame) -> pd.DataFrame:
    """Coerce a ``(date, ticker)`` MultiIndex to canonical level names.

    ``fetch_alpha158_features`` returns a ``(datetime, instrument)``
    MultiIndex; tests may hand a ``(date, ticker)`` one. We normalize by
    POSITION (level 0 = date, level 1 = ticker) so the adapter is
    agnostic to the upstream level naming.
    """
    out = panel.copy()
    out.index = out.index.set_names(["date", "ticker"])
    return out


def compute_alpha158_long_short_returns(
    features: pd.DataFrame,
    period_returns: pd.DataFrame | pd.Series,
    *,
    universe_provider: UniverseProvider | None = None,
    top_q: float = 0.10,
    bottom_q: float = 0.10,
) -> Alpha158LongShort:
    """Convert an Alpha158 feature panel into per-feature long-short returns.

    Algorithm (per feature, per month ``m``):

        1. Restrict the cross-section to the month's universe
           (``universe_provider(m)`` members when supplied, else every
           ticker present that month).
        2. Drop tickers with a NaN feature value or a NaN forward
           return.
        3. If fewer than :data:`MIN_UNIVERSE_FOR_DECILE_SPREAD` names
           remain, the feature forms no row this month.
        4. Rank descending by feature value; long leg = top ``top_q``
           fraction, short leg = bottom ``bottom_q`` fraction (≥ 1 name
           each, disjoint).
        5. ``ls_return = mean(fwd_ret[long]) − mean(fwd_ret[short])``.

    The forward return is owned by this adapter: ``period_returns`` is
    the TRAILING per-period return (the natural ``pct_change`` from the
    price cache), and the adapter shifts it one period forward
    internally so feature@m pairs with the return over ``(m, m+1]``. The
    last month in the panel therefore forms no rows (no forward return
    exists) — by construction, never a look-ahead leak.

    Args:
        features: ``(date, ticker)``-MultiIndexed DataFrame, one column
            per Alpha158 feature, values = the feature as of ``date``.
        period_returns: ``(date, ticker)``-indexed trailing per-period
            return (DataFrame with a single column or a Series).
        universe_provider: optional ``as_of -> (members, is_complete)``
            point-in-time membership provider. When ``None`` the month's
            cross-section is every ticker present and
            ``survivorship_bias_corrected`` is forced ``False``.
        top_q: long-leg fraction (default 0.10 = top decile).
        bottom_q: short-leg fraction (default 0.10 = bottom decile).

    Returns:
        :class:`Alpha158LongShort` — the gate-ready ``long_short`` frame
        + the ``survivorship_bias_corrected`` verdict.
    """
    if features.empty:
        return Alpha158LongShort(_empty_long_short(), survivorship_bias_corrected=False)

    feats = _normalize_panel_index(features)

    # Forward-return panel: pivot trailing returns to wide (date ×
    # ticker), then shift one period forward so ``fwd_wide.loc[m]`` holds
    # the return realized over ``(m, m+1]``. This is the single place the
    # lag lives — see the look-ahead note in the module docstring.
    if isinstance(period_returns, pd.Series):
        ret_series = period_returns.copy()
    else:
        ret_series = period_returns.iloc[:, 0].copy()
    ret_series.index = ret_series.index.set_names(["date", "ticker"])
    ret_wide = ret_series.unstack("ticker").sort_index()
    fwd_wide = ret_wide.shift(-1)

    dates = sorted(feats.index.get_level_values("date").unique())

    rows: list[dict[str, object]] = []
    months_complete: list[bool] = []

    for d in dates:
        if d not in fwd_wide.index:
            continue
        fwd_d = fwd_wide.loc[d].dropna()
        if fwd_d.empty:
            # No forward return exists for this month (the panel's last
            # month) — skip without consuming it.
            continue

        try:
            feat_d = feats.xs(d, level="date")
        except KeyError:
            continue

        if universe_provider is not None:
            members, is_complete = universe_provider(d)
            member_set = frozenset(members)
            feat_d = feat_d.loc[feat_d.index.intersection(member_set)]
            months_complete.append(bool(is_complete))

        if feat_d.empty:
            continue

        for feat_name in feat_d.columns:
            col = feat_d[feat_name].dropna()
            # Keep only tickers with both a feature value and a forward
            # return.
            aligned_fwd = fwd_d.reindex(col.index).dropna()
            col = col.reindex(aligned_fwd.index)
            n = len(col)
            if n < MIN_UNIVERSE_FOR_DECILE_SPREAD:
                continue

            k_long = max(1, int(n * top_q))
            k_short = max(1, int(n * bottom_q))
            if k_long + k_short > n:
                continue

            ordered = col.sort_values(ascending=False)
            long_idx = ordered.index[:k_long]
            short_idx = ordered.index[-k_short:]
            ls_return = (
                aligned_fwd.loc[long_idx].mean()
                - aligned_fwd.loc[short_idx].mean()
            )
            if pd.isna(ls_return):
                continue
            rows.append(
                {
                    "signalname": str(feat_name),
                    "date": d,
                    "ls_return": float(ls_return),
                }
            )

    long_short = (
        pd.DataFrame(rows, columns=list(_LS_COLUMNS))
        if rows
        else _empty_long_short()
    )

    survivorship_ok = (
        universe_provider is not None
        and len(months_complete) > 0
        and all(months_complete)
    )

    logger.info(
        "Alpha158 long-short: %d rows across %d features (%d months; "
        "survivorship_corrected=%s)",
        len(long_short),
        long_short["signalname"].nunique() if not long_short.empty else 0,
        len(dates),
        survivorship_ok,
    )
    return Alpha158LongShort(
        long_short=long_short, survivorship_bias_corrected=survivorship_ok
    )


def features_present(features: pd.DataFrame) -> frozenset[str]:
    """Alpha158 feature names present as columns in the computed panel.

    The analog of ``osap_replicate.signals_in_dataframe`` — feeds the
    manifest-vs-compute set diff in ``compute/main.py`` (the
    ``features_missing_from_compute`` accounting bucket). Empty frozenset
    when the panel is empty.
    """
    if features.empty:
        return frozenset()
    return frozenset(str(c) for c in features.columns)


def features_missing_from_compute(
    features: pd.DataFrame, requested: tuple[str, ...]
) -> list[str]:
    """Manifest features that never appeared as a computed panel column.

    The first accounting bucket: features the compute could not produce
    at all (e.g., a window needing more history than available, or an
    all-NaN feature stripped upstream). Sorted for deterministic JSON.
    """
    return sorted(set(requested) - features_present(features))


def features_dropped_no_long_short(
    long_short: pd.DataFrame,
    features: pd.DataFrame,
    requested: tuple[str, ...],
) -> list[str]:
    """Features present in the panel but that formed NO long-short row.

    The analog of ``osap_replicate.signals_dropped_no_long_short``: a
    feature is "dropped" when it is a real computed column
    (``features_present``) yet never formed a decile spread across the
    whole panel — every month had fewer than
    :data:`MIN_UNIVERSE_FOR_DECILE_SPREAD` valued names, or the feature
    is constant so no spread exists. Restricted to the requested
    manifest so the accounting equation closes against the 158-name
    manifest:

        len(ALPHA158_FEATURE_NAMES) == (
            len(features_missing_from_compute)      # never a panel column
          + len(features_dropped_no_long_short)     # column, but 0 LS rows
          + len(used)                               # passed PBO/DSR gate
          + len(excluded)                           # reached gate, failed
        )

    Sorted for deterministic JSON.
    """
    requested_set = set(requested)
    present = features_present(features) & requested_set
    with_rows = (
        frozenset(str(s) for s in long_short["signalname"].unique())
        if not long_short.empty
        else frozenset()
    )
    return sorted(present - with_rows)


def coverage_pct(features: pd.DataFrame, universe_size: int) -> float | None:
    """% of the universe with ≥ 1 non-null Alpha158 feature at the latest date.

    The ``dump_bin`` / feature-compute health canary — mirrors
    ``Metadata.tier2_coverage_pct``. Returns ``None`` when the panel is
    empty or the universe size is non-positive (nothing to divide by).
    """
    if features.empty or universe_size <= 0:
        return None
    feats = _normalize_panel_index(features)
    latest = max(feats.index.get_level_values("date").unique())
    cross = feats.xs(latest, level="date")
    covered = int(cross.notna().any(axis=1).sum())
    return round(100.0 * covered / universe_size, 2)


__all__ = [
    "MIN_UNIVERSE_FOR_DECILE_SPREAD",
    "Alpha158LongShort",
    "UniverseProvider",
    "compute_alpha158_long_short_returns",
    "coverage_pct",
    "features_dropped_no_long_short",
    "features_missing_from_compute",
    "features_present",
]
