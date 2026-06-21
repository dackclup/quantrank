"""Flatten a StockDetail + optional StockSummary into one dict row.

Pure function — no I/O, no side effects.  ``flatten_stock`` is the only
public symbol.  The resulting dict is the row schema for the warehouse
snapshot Parquet; column names are derived deterministically from the
Pydantic model introspection so they stay in sync as the schema evolves.

Column naming conventions
-------------------------
- StockDetail scalar fields      → field name verbatim (e.g. ``composite_score``)
- StockSummary-only scalar fields → field name verbatim (deduped against
  StockDetail; Detail wins on collision because it is more detailed)
- pillar_scores (PillarScores)   → ``pillar_<name>`` (e.g. ``pillar_quality``)
- raw_metrics (RawMetrics)       → ``raw_<name>`` (e.g. ``raw_revenue``)
- data_quality (DataQuality)     → ``dq_<name>`` (e.g. ``dq_filing_lag_days``)
- fair_price dict                → ``fp_<key>`` for known scalar keys; full
                                    dict json-encoded as ``fair_price_json``
- risk_flags list                → ``flag_<name>: bool`` per KNOWN_RISK_FLAGS
                                    + ``risk_flags_json`` (raw list)
- valuation_warnings list        → ``warn_<name>: bool`` per KNOWN_VALUATION_WARNINGS
                                    + ``valuation_warnings_json`` (raw list)
- All other nested / list / dict fields → json-encoded string columns
- ``row_provenance: str``        = "live" for live compute runs;
                                    backfill slice will set "pit_replay"

NULL discipline for flag_<x> / warn_<x>
-----------------------------------------
Live rows compute all flags, so every flag column is ``True`` or ``False``
(never None).  The ``None`` case is reserved for a future backfill slice
that may replay only a subset of defenses (hence "not evaluated").  In this
module, live rows always produce True/False.
"""

from __future__ import annotations

import json
from typing import Any

from compute.output.schemas import DataQuality, PillarScores, RawMetrics, StockDetail, StockSummary
from compute.warehouse.flag_registry import (
    KNOWN_RISK_FLAGS,
    KNOWN_VALUATION_WARNINGS,
)

# Known scalar keys in the fair_price dict (order is stable for column naming).
# These are the keys emitted by compute.valuation.ensemble.ensemble_result_to_dict.
# Unknown keys land only in fair_price_json, not as fp_<key> columns.
_FP_SCALAR_KEYS: tuple[str, ...] = (
    "median",
    "max",
    "low",
    "high",
    "mos_pct",
    "median_trimmed",
    "methods_applicable",
    # Per-method estimate columns (METHOD_NAMES tuple from ensemble.py):
    "graham",
    "multiples_pe",
    "multiples_pb",
    "multiples_ev_ebitda",
    "rim",
    "dcf",
    "methods_excluded_from_median",
)

# StockDetail fields that should be skipped in the flat scalar pass because
# they are handled separately (nested models or complex types).
_DETAIL_SKIP_FIELDS: frozenset[str] = frozenset(
    {
        "pillar_scores",  # → pillar_* columns
        "raw_metrics",    # → raw_* columns
        "data_quality",   # → dq_* columns
        "fair_price",     # → fp_* + fair_price_json
        "risk_flags",     # → flag_* bools + risk_flags_json
        "valuation_warnings",  # → warn_* bools + valuation_warnings_json
        # Complex / variable nested fields → json-encoded string columns:
        "tier2_events",
        "manipulation_components",
        "osap_signals",
        "form4_diagnostics",
        "index_memberships",
        "top5_factors",
        "score_history",
        "pillar_baseline",
    }
)

# StockSummary fields that are also present in StockDetail (StockDetail wins).
# Computed lazily from the model at module load to stay in sync with schema.
def _build_summary_skip_fields() -> frozenset[str]:
    detail_fields = set(StockDetail.model_fields.keys())
    # Always skip these even if not in StockDetail:
    extra = {"pillar_scores", "risk_flags", "valuation_warnings", "index_memberships"}
    return detail_fields | extra

_SUMMARY_SKIP_FIELDS: frozenset[str] = _build_summary_skip_fields()


def _json_encode(obj: Any) -> str | None:
    """JSON-encode obj; return None if obj is None."""
    if obj is None:
        return None
    try:
        return json.dumps(obj, default=str)
    except Exception:  # noqa: BLE001
        return json.dumps(str(obj))


def flatten_stock(
    detail: StockDetail,
    summary: StockSummary | None,
) -> dict[str, Any]:
    """Produce one flat dict row from a StockDetail + optional StockSummary.

    Parameters
    ----------
    detail:
        Full per-stock StockDetail (from the Step-8 per-ticker loop).
    summary:
        Matching StockSummary (from the ``summaries`` list in main.py).
        When None the summary-only fields are omitted.

    Returns
    -------
    dict
        Flat dict suitable for a Parquet row. All keys are stable strings;
        values are Python scalars (int, float, bool, str, None).
    """
    row: dict[str, Any] = {}

    # --- 1. StockSummary scalar fields (summary-only; StockDetail wins on dupe) ---
    if summary is not None:
        for field_name in StockSummary.model_fields:
            if field_name in _SUMMARY_SKIP_FIELDS:
                continue
            row[field_name] = getattr(summary, field_name, None)

    # --- 2. StockDetail scalar fields ---
    for field_name in StockDetail.model_fields:
        if field_name in _DETAIL_SKIP_FIELDS:
            continue
        row[field_name] = getattr(detail, field_name, None)

    # --- 3. Nested PillarScores → pillar_<name> ---
    ps: PillarScores = detail.pillar_scores
    for field_name in PillarScores.model_fields:
        row[f"pillar_{field_name}"] = getattr(ps, field_name, None)

    # --- 4. Nested RawMetrics → raw_<name> ---
    rm: RawMetrics = detail.raw_metrics
    for field_name in RawMetrics.model_fields:
        row[f"raw_{field_name}"] = getattr(rm, field_name, None)

    # --- 5. Nested DataQuality → dq_<name> ---
    dq: DataQuality = detail.data_quality
    for field_name in DataQuality.model_fields:
        val = getattr(dq, field_name, None)
        # list fields (missing_metrics, imputed_metrics) → json string
        if isinstance(val, list):
            val = _json_encode(val)
        row[f"dq_{field_name}"] = val

    # --- 6. fair_price dict ---
    fp: dict | None = detail.fair_price
    # Keep full json for unrestricted downstream access.
    row["fair_price_json"] = _json_encode(fp)
    # Known scalar keys → fp_<key> columns.
    for key in _FP_SCALAR_KEYS:
        if fp is not None and key in fp:
            val = fp[key]
            # methods_excluded_from_median is a list → json-encode it.
            if isinstance(val, (list, dict)):
                val = _json_encode(val)
            row[f"fp_{key}"] = val
        else:
            row[f"fp_{key}"] = None

    # --- 7. risk_flags: dual bool columns + raw json ---
    rf_set: set[str] = set(detail.risk_flags)
    row["risk_flags_json"] = _json_encode(detail.risk_flags)
    for flag in sorted(KNOWN_RISK_FLAGS):
        row[f"flag_{flag}"] = flag in rf_set

    # --- 8. valuation_warnings: dual bool columns + raw json ---
    vw_set: set[str] = set(detail.valuation_warnings)
    row["valuation_warnings_json"] = _json_encode(detail.valuation_warnings)
    for warn in sorted(KNOWN_VALUATION_WARNINGS):
        row[f"warn_{warn}"] = warn in vw_set

    # --- 9. Complex / variable nested fields → json-encoded strings ---
    row["tier2_events_json"] = _json_encode(detail.tier2_events)
    row["manipulation_components_json"] = _json_encode(detail.manipulation_components)
    row["osap_signals_json"] = _json_encode(detail.osap_signals)
    row["form4_diagnostics_json"] = _json_encode(detail.form4_diagnostics)
    row["index_memberships_json"] = _json_encode(detail.index_memberships)
    row["top5_factors_json"] = _json_encode(detail.top5_factors)
    row["score_history_json"] = _json_encode(detail.score_history)
    row["pillar_baseline_json"] = _json_encode(
        detail.pillar_baseline.model_dump(mode="json") if detail.pillar_baseline is not None else None
    )

    # --- 10. Provenance sentinel ---
    row["row_provenance"] = "live"

    return row
