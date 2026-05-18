"""Phase 4i scout — Jensen-Kelly-Pedersen factor library ingest skeleton.

Scout PR scope. Surfaces the API + license + access-path facts so the
follow-on full-integration PR (theme aggregation + pillar blending +
PBO/DSR gate + ``compute/main.py`` wiring) starts from solid ground.

Background — Jensen, Kelly, Pedersen 2023 *Journal of Finance* "Is
There a Replication Crisis in Finance?" The authors publish a 153-
signal × multi-region long-short portfolio dataset; Phase 4i collapses
those 153 signals into 13 quasi-orthogonal theme clusters
(``quality / value / investment / profitability / profit_growth /
momentum / leverage / trading_frictions / skewness / low_risk /
size / accruals / seasonality``) per ``.claude/skills/phase-4/
jkp-integration/PLAN.md:14``. The integration PR consumes the
theme-aggregated returns only; raw 153-signal access stays out of
scope per PLAN.md:171.

Access-path discovery (verified 2026-05-18 — pre-PR probes):

1. **NO PyPI package**. ``pip index versions`` 404 for all 11
   candidate names (``jkpfactors``, ``jkp-factors``, ``kellyjkp``,
   ``jkp-data``, etc.). Confirmed.
2. **`bkelly-lab/jkp-data` GitHub repo IS the official codebase**
   (MIT code license) BUT is WRDS-dependent — its `jkp` CLI
   orchestrates user-supplied WRDS downloads. Useless for an open-
   source CI environment without WRDS credentials.
3. **`jkpfactors.com/factors/` UI page returns HTTP 302 → /login**
   (gated UI). The PLAN.md "freely downloadable" claim refers to a
   *legacy* access path that has since been re-routed through auth.
4. **`https://jkpfactors.s3.amazonaws.com/` S3 bucket IS publicly
   readable** (no auth required, HTTP 200 on root + `?list-type=2`
   listing). Verified asset: ``other_data/market_returns.csv``
   (small, stable, dated 2025-02-21 last-modified per S3
   `LastModified` header). Per-factor returns live under
   ``public/[<country>]_[<factor>]_[<freq>]_[<weight>].zip`` (~1000+
   keys; integration PR maps these to the 13 themes).

**Scout strategy**: hit the public S3 bucket. Fetch a single small
verification asset (``JKP_SCOUT_ASSET``) to prove the path works
end-to-end through tenacity + cache + parquet writeback. The full
integration PR replaces this with a higher-level fetcher that walks
the ``public/`` prefix and aggregates per-factor ZIPs into the 13-
theme schema.

License (CC BY-NC 4.0 — DATA_LICENSE in bkelly-lab/jkp-data verified
verbatim 2026-05-18): "Creative Commons Attribution-NonCommercial 4.0
International License. Copyright (c) 2023 Theis Ingerslev Jensen,
Bryan T. Kelly, Lasse Heje Pedersen." QuantRank's current open-source
static-site educational deployment qualifies per PLAN.md:33. **Phase
6+ commercial roadmap would invalidate this** — the scout PR body
flags the explicit license-review checkpoint before integration.

No vendored data — cache only, gitignored (``compute/cache/jkp/``
inherits from the repo-level ``compute/cache/`` gitignore).
"""

from __future__ import annotations

import logging
import time
from datetime import date
from io import StringIO

import pandas as pd
import requests
from tenacity import retry, stop_after_attempt, stop_after_delay, wait_exponential

from compute import config

logger = logging.getLogger(__name__)

# Publicly-readable S3 bucket (no auth). Verified 2026-05-18 via
# `curl -sL https://jkpfactors.s3.amazonaws.com/?list-type=2` returning
# a valid ListBucketResult XML body.
JKP_BUCKET_ROOT: str = "https://jkpfactors.s3.amazonaws.com"

# Scout verification asset. Small (~kilobytes), stable, plain CSV with
# no bracket-encoded path components. Selected by `?list-type=2&prefix=
# other_data/&delimiter=/` listing (verified 2026-05-18). NOT the theme
# returns the integration PR will consume — the scout's job is to verify
# bucket read access, NOT to lock in the integration path.
JKP_SCOUT_ASSET_PATH: str = "other_data/market_returns.csv"

# 13-theme manifest from PLAN.md:14 (the "153 → 13 quasi-orthogonal
# axes" collapse). Locked at scout time; integration PR maps each
# theme to a `public/` prefix slice of the 153-factor universe.
JKP_THEMES: tuple[str, ...] = (
    "quality",
    "value",
    "investment",
    "profitability",
    "profit_growth",
    "momentum",
    "leverage",
    "trading_frictions",
    "skewness",
    "low_risk",
    "size",
    "accruals",
    "seasonality",
)

# Schema contract for the scout-mode CSV. Asserted on fetched
# DataFrames so a silent upstream schema change surfaces here rather
# than in the consumer. Verified 2026-05-18 against actual CSV header:
# ``excntry, eom, stocks, me_lag1, dolvol_lag1, mkt_vw_lcl, mkt_ew_lcl,
# mkt_vw, mkt_ew, mkt_vw_exc, mkt_ew_exc``. Distinct from the eventual
# theme-returns schema (``{theme, year_month, ls_return, region}``) the
# integration PR will commit to.
JKP_SCOUT_REQUIRED_COLUMNS: frozenset[str] = frozenset(
    {"excntry", "eom", "mkt_vw"}
)


@retry(
    stop=(stop_after_delay(30) | stop_after_attempt(2)),
    wait=wait_exponential(min=2, max=8),
    reraise=True,
)
def _fetch_jkp_csv_uncached(url: str) -> pd.DataFrame:
    """HTTP GET a CSV from the JKP S3 bucket.

    Tightened tenacity policy matches the post-PR-3d pattern in
    ``compute/ingest/fundamentals.py:551-554`` + ``:788-791`` and
    ``compute/ingest/osap.py:52-56``. 30-second hard ceiling + 2
    attempts: if the bucket can't complete in that window, the
    upstream is broken and we want a fast signal.
    """
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    return pd.read_csv(StringIO(resp.text))


def _is_fresh(cache_path, max_age_days: int) -> bool:
    """Cache freshness check. Mirrors ``compute/ingest/osap.py:75``."""
    if not cache_path.exists():
        return False
    age_days = (time.time() - cache_path.stat().st_mtime) / 86400
    return age_days < max_age_days


def fetch_jkp_returns(
    force_refresh: bool = False,
    *,
    asset_path: str | None = None,
    region: str | None = None,
    as_of: date | None = None,
) -> pd.DataFrame:
    """Scout-mode JKP fetch — downloads a single CSV from the JKP S3
    bucket, verifying the access path the integration PR will build on.

    Args:
        force_refresh: ignore cache freshness; re-fetch.
        asset_path: bucket-relative path (default
            :data:`JKP_SCOUT_ASSET_PATH`). Integration PR will walk the
            ``public/`` prefix; scout fetches one stable file.
        region: forward-compat kwarg. NO-OP in scout mode — the scout
            asset is single-region market returns. Integration PR will
            filter per the 4-region split (us / dev / em / global) per
            PLAN.md:68.
        as_of: forward-compat kwarg. NO-OP in scout mode. Integration
            PR will apply ``eom <= as_of`` filtering.

    Returns:
        DataFrame whose columns include ``JKP_SCOUT_REQUIRED_COLUMNS``.
        Schema is whatever ``other_data/market_returns.csv`` exposes;
        integration PR commits to the theme-aggregated 4-column schema.

    Raises:
        ValueError: if the fetched CSV is missing the required columns
            (upstream schema-drift detector).
    """
    path = asset_path if asset_path is not None else JKP_SCOUT_ASSET_PATH
    url = f"{JKP_BUCKET_ROOT}/{path}"
    cache = config.JKP_RETURNS_CACHE

    if not force_refresh and _is_fresh(cache, config.JKP_RETURNS_MAX_AGE_DAYS):
        age_days = (time.time() - cache.stat().st_mtime) / 86400
        logger.info("JKP cache hit (age=%.1f days, path=%s)", age_days, cache)
        df = pd.read_parquet(cache)
    else:
        logger.info("Fetching JKP CSV from %s", url)
        df = _fetch_jkp_csv_uncached(url)
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(cache, index=False)
        logger.info(
            "Cached %d rows × %d cols to %s", len(df), len(df.columns), cache
        )

    missing = JKP_SCOUT_REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            f"JKP scout CSV missing required columns {sorted(missing)}; "
            f"got {sorted(df.columns)}. Upstream S3 asset may have changed."
        )

    # `region` and `as_of` are forward-compat no-ops in scout mode.
    # Logged so calls that pass them surface in test/debug output.
    if region is not None:
        logger.debug("region=%s passed but ignored in scout mode", region)
    if as_of is not None:
        logger.debug("as_of=%s passed but ignored in scout mode", as_of)

    return df
