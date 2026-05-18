"""OpenAssetPricing (OSAP) long-short portfolio returns ingest.

Phase 4h **scout module**. Fetches Chen-Zimmermann OSAP portfolio returns
via the ``openassetpricing`` package (MIT-licensed) and caches to
parquet. The scout PR does NOT wire this into composite scoring —
Phase 4h will consume it in ``compute/features/osap_replicate.py`` +
``compute/scoring/osap_blend.py``.

Cached to ``compute/cache/osap/returns.parquet`` (gitignored). Re-
fetched after ``config.OSAP_RETURNS_MAX_AGE_DAYS`` (31 days; OSAP
releases monthly) unless ``force_refresh=True``.

The public signature is **provisional** — Phase 4h will add keyword-
only ``signals: list[str] | None`` / ``as_of: date | None`` params
(non-breaking additions).

Observed schema (verified 2026-05-18 against ``OpenAP().dl_port("op",
"pandas")``): ``signalname, port, date, ret, signallag, Nlong, Nshort``
— 1,188 signals × ~10 portfolio buckets × ~75 years monthly = ~1.2M
rows total. This differs from the hypothetical schema in
``.claude/skills/phase-4/osap-integration/PLAN.md`` (which assumed
``signal_name, year_month, ls_return, n_stocks``); Phase 4h must
derive long-short returns from ``port=01`` vs ``port=10`` differences.
"""

from __future__ import annotations

import logging
import time
from datetime import date

import openassetpricing
import pandas as pd
from tenacity import retry, stop_after_attempt, stop_after_delay, wait_exponential

from compute import config

logger = logging.getLogger(__name__)

# Load-bearing schema contract for Phase 4h consumption. Asserted on
# fetched DataFrames so a silent upstream schema change surfaces here
# rather than in the consumer.
REQUIRED_COLUMNS: frozenset[str] = frozenset({"signalname", "port", "date", "ret"})

# Default portfolio dataset name. "op" = PredictorPortsFull.csv (the
# canonical long format with all signals × all portfolio buckets).
# Phase 4h may switch to "deciles_vw" etc. once the blend logic
# locks down which bucket cardinality to use.
DEFAULT_PORTFOLIO: str = "op"


@retry(
    stop=(stop_after_delay(30) | stop_after_attempt(2)),
    wait=wait_exponential(min=2, max=8),
    reraise=True,
)
def _fetch_osap_returns_uncached(data_name: str = DEFAULT_PORTFOLIO) -> pd.DataFrame:
    """Direct OSAP fetch via ``openassetpricing.OpenAP().dl_port``.

    Tightened tenacity policy matches the post-PR-3d pattern in
    ``compute/ingest/fundamentals.py``. OSAP is a single bulk fetch
    (not per-stock like fundamentals), but a uniform retry policy
    across ingest modules avoids the two-style drift PR-3d
    explicitly resolved. 30-second hard ceiling + 2 attempts: if
    a CSV download can't complete in that window, the upstream is
    broken and we want a fast signal.
    """
    # TODO(phase-4h): the OpenAP() default release may shift; pin
    # ``release_year`` once 4h locks down which release the blend
    # logic was validated against.
    oa = openassetpricing.OpenAP()
    return oa.dl_port(data_name, "pandas")


def _is_fresh(cache_path, max_age_days: int) -> bool:
    if not cache_path.exists():
        return False
    age_days = (time.time() - cache_path.stat().st_mtime) / 86400
    return age_days < max_age_days


def fetch_osap_returns(
    force_refresh: bool = False,
    *,
    signals: list[str] | None = None,
    as_of: date | None = None,
) -> pd.DataFrame:
    """Return OSAP long-short portfolio returns, hitting the cache when fresh.

    Returns a DataFrame whose columns include at minimum
    ``REQUIRED_COLUMNS``. When ``signals`` is provided, the returned
    frame is filtered to rows whose ``signalname`` is in the list (the
    cache always stores the full bulk parquet — filtering happens
    post-load so a callsite that asks for 20 signals doesn't invalidate
    a callsite that asks for all 1,188). When ``as_of`` is provided,
    rows whose ``date`` is after ``as_of`` are dropped — Phase 4h's
    replication callers use this to keep the cross-section honest
    against the as-of point-in-time.
    """
    cache = config.OSAP_RETURNS_CACHE
    if not force_refresh and _is_fresh(cache, config.OSAP_RETURNS_MAX_AGE_DAYS):
        age_days = (time.time() - cache.stat().st_mtime) / 86400
        logger.info("OSAP cache hit (age=%.1f days)", age_days)
        df = pd.read_parquet(cache)
    else:
        logger.info("Fetching OSAP returns via openassetpricing.OpenAP().dl_port")
        df = _fetch_osap_returns_uncached()
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache, index=False)
        logger.info("Cached %d rows × %d cols to %s", len(df), len(df.columns), cache)

    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"OSAP returns missing required columns {sorted(missing)}; "
            f"got {sorted(df.columns)}. Upstream API may have changed."
        )

    if signals is not None:
        df = df[df["signalname"].isin(signals)]
    if as_of is not None:
        df = df[pd.to_datetime(df["date"]) <= pd.Timestamp(as_of)]
    return df
