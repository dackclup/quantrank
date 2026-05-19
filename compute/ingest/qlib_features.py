"""Phase 4j scout — Microsoft Qlib (Alpha158) integration skeleton.

Scout PR scope: install pyqlib + verify Alpha158 API surface + lock
the 158-feature manifest. Full Alpha158 feature compute on the
502-ticker S&P 500 universe is deferred to the follow-on integration
PR.

**Phase 4j is STRUCTURALLY DIFFERENT** from Phase 4h (OSAP) + Phase
4i (JKP). Both 4h/4i fetch precomputed factor RETURN time series from
a remote endpoint (OSAP package, JKP S3 bucket). Qlib's Alpha158
computes per-stock-per-date FEATURES *locally* from OHLCV bars via a
Python library. There is **no remote endpoint to hit**; no
`@network` test makes architectural sense for this scout. The scout's
verification surface is install + API + manifest drift detection.

**Module-name choice**: this module is ``compute/ingest/qlib_features.py``,
NOT ``compute/ingest/qlib.py``. Python's import resolution would
treat the latter as the ``qlib`` package and shadow the actual
installed PyPI package, breaking the entire factor-library integration.
The distinct module name avoids the namespace collision.

**License**: ``pyqlib`` is MIT-licensed (verified 2026-05-19 via wheel
METADATA inspection — ``Classifier: License :: OSI Approved :: MIT
License``). No CC BY-NC complication like JKP. Safe for Phase 6+
commercial roadmap.

**NO public US data bundle**: Qlib's default ``provider_uri``
(``~/.qlib/qlib_data/cn_data``) covers the Chinese A-share market
only. The ``REG_US`` region constant exists but **no bundled US data
cache is distributed by upstream Qlib** — users supply their own
OHLCV via Qlib's local ``.bin`` format. The yfinance-to-Qlib BYO
adapter is integration-PR scope.

**Tenacity policy NOT applicable**: Qlib's data flow is local
filesystem I/O (``.bin`` files under ``provider_uri``). No network
retry semantics needed. This is the first ingest module in QuantRank
that does NOT use the canonical
``compute/ingest/osap.py:52-56`` retry decorator.

**Heavy transitive deps**: ``pip install pyqlib`` pulls ~22 deps
including ``mlflow``, ``lightgbm``, ``cvxpy``, ``pymongo``, ``redis``
(client), ``gym``, ``jupyter``, ``nbconvert``. Net CI install
footprint bump: ~150-180 MB. Disclosed in the scout PR body so
reviewers can audit CI cold-start cost.

The :data:`ALPHA158_FEATURE_NAMES` tuple below is hardcoded for
stability + the offline test
``test_alpha158_feature_manifest_matches_runtime_introspection``
asserts the hardcoded list matches the runtime introspection result
from ``Alpha158DL.get_feature_config()[1]``. If pyqlib upstream
drifts the feature set in a future release, that test fails and we
deliberately re-hardcode the manifest. The ``pyqlib>=0.9.7,<0.10``
pin in ``pyproject.toml`` keeps any drift to a manual upgrade.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from compute import config

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)

# Custom instruments universe identifier. Integration PR will register
# this against Qlib's instruments API after the yfinance-to-Qlib BYO
# adapter converts the 502-ticker OHLCV cache into Qlib's ``.bin``
# format. Scout-mode default = string only (no Qlib registration).
QLIB_INSTRUMENTS_UNIVERSE: str = "sp500"

# 158-feature manifest from
# ``qlib.contrib.data.loader.Alpha158DL.get_feature_config()[1]``
# (the human-readable column names; corresponding field expressions
# live in ``get_feature_config()[0]``). Captured at scout-implementation
# time 2026-05-19 against pyqlib 0.9.7. The offline test
# ``test_alpha158_feature_manifest_matches_runtime_introspection``
# locks this tuple against upstream drift on every ``pip install``.
#
# Feature families (5-window rolling: 5/10/20/30/60-day):
#   K-bar shape (9):     KMID/KLEN/KMID2/KUP/KUP2/KLOW/KLOW2/KSFT/KSFT2
#   Price level (4):     OPEN0/HIGH0/LOW0/VWAP0
#   ROC (5):             ROC{5,10,20,30,60}
#   MA (5):              MA{5,10,20,30,60}
#   STD (5):             STD{5,10,20,30,60}
#   BETA / RSQR (10):    BETA + RSQR per window
#   RESI (5):            RESI{5,10,20,30,60}
#   MAX / MIN (10):      MAX + MIN per window
#   QTLU / QTLD (10):    upper + lower quantile per window
#   RANK / RSV (10):     RANK + RSV per window
#   IMAX / IMIN / IMXD (15): argmax / argmin / their diff per window
#   CORR / CORD (10):    correlation + correlation-of-diffs per window
#   CNTP / CNTN / CNTD (15): up-day count / down-day count / diff
#   SUMP / SUMN / SUMD (15): pos-sum / neg-sum / diff per window
#   VMA / VSTD (10):     volume MA + volume STD per window
#   WVMA (5):            volume-weighted vol per window
#   VSUMP / VSUMN / VSUMD (15): volume pos/neg/diff sums per window
# Total: 158 features.
ALPHA158_FEATURE_NAMES: tuple[str, ...] = (
    "KMID", "KLEN", "KMID2", "KUP", "KUP2", "KLOW", "KLOW2", "KSFT", "KSFT2",
    "OPEN0", "HIGH0", "LOW0", "VWAP0",
    "ROC5", "ROC10", "ROC20", "ROC30", "ROC60",
    "MA5", "MA10", "MA20", "MA30", "MA60",
    "STD5", "STD10", "STD20", "STD30", "STD60",
    "BETA5", "BETA10", "BETA20", "BETA30", "BETA60",
    "RSQR5", "RSQR10", "RSQR20", "RSQR30", "RSQR60",
    "RESI5", "RESI10", "RESI20", "RESI30", "RESI60",
    "MAX5", "MAX10", "MAX20", "MAX30", "MAX60",
    "MIN5", "MIN10", "MIN20", "MIN30", "MIN60",
    "QTLU5", "QTLU10", "QTLU20", "QTLU30", "QTLU60",
    "QTLD5", "QTLD10", "QTLD20", "QTLD30", "QTLD60",
    "RANK5", "RANK10", "RANK20", "RANK30", "RANK60",
    "RSV5", "RSV10", "RSV20", "RSV30", "RSV60",
    "IMAX5", "IMAX10", "IMAX20", "IMAX30", "IMAX60",
    "IMIN5", "IMIN10", "IMIN20", "IMIN30", "IMIN60",
    "IMXD5", "IMXD10", "IMXD20", "IMXD30", "IMXD60",
    "CORR5", "CORR10", "CORR20", "CORR30", "CORR60",
    "CORD5", "CORD10", "CORD20", "CORD30", "CORD60",
    "CNTP5", "CNTP10", "CNTP20", "CNTP30", "CNTP60",
    "CNTN5", "CNTN10", "CNTN20", "CNTN30", "CNTN60",
    "CNTD5", "CNTD10", "CNTD20", "CNTD30", "CNTD60",
    "SUMP5", "SUMP10", "SUMP20", "SUMP30", "SUMP60",
    "SUMN5", "SUMN10", "SUMN20", "SUMN30", "SUMN60",
    "SUMD5", "SUMD10", "SUMD20", "SUMD30", "SUMD60",
    "VMA5", "VMA10", "VMA20", "VMA30", "VMA60",
    "VSTD5", "VSTD10", "VSTD20", "VSTD30", "VSTD60",
    "WVMA5", "WVMA10", "WVMA20", "WVMA30", "WVMA60",
    "VSUMP5", "VSUMP10", "VSUMP20", "VSUMP30", "VSUMP60",
    "VSUMN5", "VSUMN10", "VSUMN20", "VSUMN30", "VSUMN60",
    "VSUMD5", "VSUMD10", "VSUMD20", "VSUMD30", "VSUMD60",
)
assert len(ALPHA158_FEATURE_NAMES) == config.ALPHA158_FEATURE_COUNT, (
    f"ALPHA158_FEATURE_NAMES has {len(ALPHA158_FEATURE_NAMES)} entries, "
    f"expected {config.ALPHA158_FEATURE_COUNT}"
)


def init_qlib(provider_uri: Path | str | None = None) -> None:
    """Idempotent thin wrapper around ``qlib.init(provider_uri=...,
    region="us")``.

    Scout-mode default ``provider_uri`` = :data:`config.QLIB_DATA_CACHE`
    (gitignored under ``compute/cache/qlib/``). Integration PR will
    populate the cache via the yfinance-to-Qlib BYO adapter before
    this is called from ``compute/main.py``.

    Wrapped in a function rather than executed at module import so
    tests can hand ``init_qlib`` a synthetic ``tmp_path`` without
    affecting the real cache. The actual ``qlib.init`` IS itself
    idempotent (logs a warning on re-init but does not raise).

    Args:
        provider_uri: Optional path to a Qlib ``.bin`` data cache. If
            omitted, defaults to :data:`config.QLIB_DATA_CACHE`.
    """
    import qlib  # local import — pyqlib is in the [factors] extra
    from qlib.config import REG_US

    uri = str(provider_uri if provider_uri is not None else config.QLIB_DATA_CACHE)
    logger.info("Initializing Qlib (provider_uri=%s, region=%s)", uri, REG_US)
    qlib.init(provider_uri=uri, region=REG_US)


def fetch_alpha158_features(
    *,
    instruments: str = QLIB_INSTRUMENTS_UNIVERSE,
    start_time: str,
    end_time: str,
) -> pd.DataFrame:
    """Forward-compat wrapper around
    ``Alpha158(...).fetch(col_set="feature")``.

    **Scout does NOT exercise this end-to-end.** ``pyqlib``'s PyPI
    wheel does not bundle the ``scripts/dump_bin.py`` utility needed
    to convert raw OHLCV CSV into Qlib's ``.bin`` format. Integration
    PR will either vendor a minimal bin-writer OR clone the upstream
    ``microsoft/qlib`` ``scripts/`` directory at install time.

    Caller MUST call :func:`init_qlib` first against a ``provider_uri``
    that contains a valid Qlib bin cache for the requested
    ``instruments`` universe.

    Args:
        instruments: Qlib instruments universe identifier. Default
            ``"sp500"`` (custom universe registered by the
            integration PR's BYO adapter).
        start_time: ISO date string (YYYY-MM-DD).
        end_time: ISO date string (YYYY-MM-DD).

    Returns:
        DataFrame with a ``(datetime, instrument)`` MultiIndex and
        158 feature columns (matching :data:`ALPHA158_FEATURE_NAMES`).
    """
    from qlib.contrib.data.handler import Alpha158

    handler = Alpha158(
        instruments=instruments,
        start_time=start_time,
        end_time=end_time,
    )
    return handler.fetch(col_set="feature")
