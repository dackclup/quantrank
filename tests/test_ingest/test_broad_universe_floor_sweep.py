"""Tests for PR-1 — the ADV-floor-scoping shadow-observability slice.

Covers the two new pure functions in ``compute/ingest/broad_universe.py``:

  - ``_adv_survivors_at_floors``   — private helper computing the
                                      MONOTONE-NESTED survivor-set-per-floor
                                      mapping (generic floors).
  - ``sweep_broad_universe_floors`` — public Rule-18 diagnostic wrapping the
                                      helper into the 6 new ``Metadata``
                                      fields.

Also covers the PR-1 "latent coupling defect" fix:
  - ``select_broad_universe_survivors``'s ``adv_floor`` default now reads
    ``config.BROAD_UNIVERSE_ADV_FLOOR_USD`` (NOT ``config.ADV_FLOOR_USD``).
  - ``screen_broad_universe_investability``'s ``adv_floor`` default is
    UNCHANGED — still ``config.ADV_FLOOR_USD`` (probe-diagnostic continuity).
  - ``config.BROAD_UNIVERSE_ADV_FLOOR_USD == config.ADV_FLOOR_USD`` at launch
    (byte-identical decoupling — see also the dedicated
    ``tests/test_config.py`` pin).

And the byte-identical wiring guard:
  - the new sweep call in ``compute/main.py`` sits OUTSIDE every
    universe-selector branch (same unconditional post-Step-1 lifecycle as
    the existing Phase 9.1 probe) — the sp500/sp900/sp1500/broad_investable_us
    branches themselves are untouched (already locked byte-for-byte by
    ``tests/test_ingest/test_broad_universe_ranked.py``'s
    ``TestDefaultPathUnchangedRegressionGuard``; this file adds one
    positional guard specific to the new call site).

Test groups:
  FS1  ``_adv_survivors_at_floors`` MONOTONE-NESTED subset property — with
       CUSTOM (non-default) ascending floors, proving the property holds
       generically, not just for the literal 5m/10m/15m values.
  FS2  ``_adv_survivors_at_floors`` n_with_prices denominator semantics.
  FS3  ``sweep_broad_universe_floors`` default-floor counts against known
       synthetic data (exact numbers, non-increasing).
  FS4  Graceful-degradation / None-semantics: empty candidates, zero
       price data, missing optional signal dicts (adr_suspect /
       fundamentals_coverage stay None; floor counts + sector_unknown_pct
       still populate).
  FS5  ADR-suspect count — correct arithmetic once BOTH optional signals
       ARE supplied (proves the logic is correct even though production
       always passes None today).
  FS6  Sector-unknown-pct — both the "no sector column" (structural 100%)
       and "sector column present" (measured %) branches.
  FS7  Survivor-fundamentals-coverage-pct arithmetic.
  FS8  The "latent coupling defect" fix: ``select_broad_universe_survivors``
       decoupled to ``BROAD_UNIVERSE_ADV_FLOOR_USD``;
       ``screen_broad_universe_investability`` unchanged on ``ADV_FLOOR_USD``.
  FS9  ``compute/main.py`` wiring — the sweep call sits at the same
       unconditional level as the probe (byte-identical guard companion to
       ``TestDefaultPathUnchangedRegressionGuard``).
"""

from __future__ import annotations

import inspect

import pandas as pd

from compute import config
from compute.ingest.broad_universe import (
    _adv_survivors_at_floors,
    screen_broad_universe_investability,
    select_broad_universe_survivors,
    sweep_broad_universe_floors,
)

# ---------------------------------------------------------------------------
# Helpers — synthetic price DataFrames (mirrors test_broad_universe.py)
# ---------------------------------------------------------------------------


def _price_df(n_rows: int = 40, close: float = 50.0, volume: float = 200_000.0) -> pd.DataFrame:
    """Minimal OHLCV DataFrame — constant close/volume so
    ``compute_average_dollar_volume`` == close * volume exactly."""
    idx = pd.bdate_range("2025-01-02", periods=n_rows)
    return pd.DataFrame(
        {
            "Open": [close] * n_rows,
            "High": [close + 1.0] * n_rows,
            "Low": [close - 1.0] * n_rows,
            "Close": [close] * n_rows,
            "Volume": [volume] * n_rows,
        },
        index=idx,
    )


# ---------------------------------------------------------------------------
# FS1/FS2 — _adv_survivors_at_floors
# ---------------------------------------------------------------------------


class TestAdvSurvivorsAtFloorsMonotoneNesting:
    def test_monotone_nested_with_custom_ascending_floors(self) -> None:
        """Subset property holds for ARBITRARY ascending floors, not just the
        literal 5m/10m/15m default — proves it's a mathematical property of
        the threshold comparison, not special-cased bookkeeping.

        4 tickers with ADV = $1M / $3M / $6M / $12M (close=$100, volume
        chosen so close*volume lands exactly on each target).  Floors swept:
        $2M / $5M / $10M.
        """
        candidates = pd.DataFrame({"ticker": ["ADV1M", "ADV3M", "ADV6M", "ADV12M"]})
        prices_by_ticker = {
            "ADV1M": _price_df(close=100.0, volume=10_000.0),  # $1M
            "ADV3M": _price_df(close=100.0, volume=30_000.0),  # $3M
            "ADV6M": _price_df(close=100.0, volume=60_000.0),  # $6M
            "ADV12M": _price_df(close=100.0, volume=120_000.0),  # $12M
        }
        floors = (2_000_000.0, 5_000_000.0, 10_000_000.0)

        survivors_by_floor, n_with_prices = _adv_survivors_at_floors(
            candidates, prices_by_ticker, floors, price_floor=5.0, adv_lookback_days=30
        )

        assert n_with_prices == 4
        assert survivors_by_floor[2_000_000.0] == {"ADV3M", "ADV6M", "ADV12M"}
        assert survivors_by_floor[5_000_000.0] == {"ADV6M", "ADV12M"}
        assert survivors_by_floor[10_000_000.0] == {"ADV12M"}

        # The subset property, checked directly (not just eyeballed above).
        s_2m = survivors_by_floor[2_000_000.0]
        s_5m = survivors_by_floor[5_000_000.0]
        s_10m = survivors_by_floor[10_000_000.0]
        assert s_10m <= s_5m <= s_2m, (
            "MONOTONE-NESTED violated: survivors at a larger floor must "
            "always be a SUBSET of survivors at a smaller floor"
        )
        # Counts non-increasing too.
        assert len(s_10m) <= len(s_5m) <= len(s_2m)

    def test_monotone_nested_holds_regardless_of_floors_input_order(self) -> None:
        """Floors passed out of order (descending) must still produce a
        correctly-nested result — the helper sorts internally."""
        candidates = pd.DataFrame({"ticker": ["LOW", "HIGH"]})
        prices_by_ticker = {
            "LOW": _price_df(close=50.0, volume=40_000.0),  # $2M
            "HIGH": _price_df(close=50.0, volume=400_000.0),  # $20M
        }
        # Deliberately descending input order.
        floors = (15_000_000.0, 1_000_000.0, 8_000_000.0)

        survivors_by_floor, _ = _adv_survivors_at_floors(
            candidates, prices_by_ticker, floors, price_floor=5.0, adv_lookback_days=30
        )
        assert survivors_by_floor[1_000_000.0] == {"LOW", "HIGH"}
        assert survivors_by_floor[8_000_000.0] == {"HIGH"}
        assert survivors_by_floor[15_000_000.0] == {"HIGH"}
        assert (
            survivors_by_floor[15_000_000.0]
            <= survivors_by_floor[8_000_000.0]
            <= survivors_by_floor[1_000_000.0]
        )

    def test_n_with_prices_zero_when_no_ticker_has_price_data(self) -> None:
        candidates = pd.DataFrame({"ticker": ["GHOST1", "GHOST2"]})
        survivors_by_floor, n_with_prices = _adv_survivors_at_floors(
            candidates, {}, (5_000_000.0,), price_floor=5.0, adv_lookback_days=30
        )
        assert n_with_prices == 0
        assert survivors_by_floor[5_000_000.0] == set()

    def test_price_floor_fail_still_counts_toward_n_with_prices(self) -> None:
        """A ticker with price data that fails the PRICE floor still counts
        toward n_with_prices (it "had data") even though it survives no ADV
        floor — matches screen_broad_universe_investability's convention."""
        candidates = pd.DataFrame({"ticker": ["CHEAP"]})
        prices_by_ticker = {"CHEAP": _price_df(close=2.0, volume=10_000_000.0)}
        survivors_by_floor, n_with_prices = _adv_survivors_at_floors(
            candidates, prices_by_ticker, (5_000_000.0,), price_floor=5.0, adv_lookback_days=30
        )
        assert n_with_prices == 1
        assert survivors_by_floor[5_000_000.0] == set()

    def test_empty_candidates_returns_empty_sets(self) -> None:
        empty = pd.DataFrame(columns=["ticker"])
        survivors_by_floor, n_with_prices = _adv_survivors_at_floors(
            empty, {}, (5_000_000.0, 10_000_000.0), price_floor=5.0, adv_lookback_days=30
        )
        assert n_with_prices == 0
        assert survivors_by_floor[5_000_000.0] == set()
        assert survivors_by_floor[10_000_000.0] == set()


# ---------------------------------------------------------------------------
# FS3/FS4 — sweep_broad_universe_floors: default floors + degradation
# ---------------------------------------------------------------------------


class TestSweepBroadUniverseFloorsDefaultBehavior:
    def test_default_floor_keys_present_and_non_increasing(self) -> None:
        """5 tickers spanning below-$5M through above-$15M — exercises all 4
        bands against the DEFAULT (5m/10m/15m) floors."""
        candidates = pd.DataFrame(
            {"ticker": ["BELOW5M", "AT7M", "AT12M", "AT20M", "PRICEFAIL"]}
        )
        prices_by_ticker = {
            "BELOW5M": _price_df(close=100.0, volume=30_000.0),  # $3M
            "AT7M": _price_df(close=100.0, volume=70_000.0),  # $7M
            "AT12M": _price_df(close=100.0, volume=120_000.0),  # $12M
            "AT20M": _price_df(close=100.0, volume=200_000.0),  # $20M
            "PRICEFAIL": _price_df(close=2.0, volume=50_000_000.0),  # price < $5
        }
        result = sweep_broad_universe_floors(candidates, prices_by_ticker)

        assert result["broad_universe_survivors_at_5m_count"] == 3  # AT7M/AT12M/AT20M
        assert result["broad_universe_survivors_at_10m_count"] == 2  # AT12M/AT20M
        assert result["broad_universe_survivors_at_15m_count"] == 1  # AT20M

        at5 = result["broad_universe_survivors_at_5m_count"]
        at10 = result["broad_universe_survivors_at_10m_count"]
        at15 = result["broad_universe_survivors_at_15m_count"]
        assert at15 <= at10 <= at5, "counts must be non-increasing as the floor rises"

    def test_result_keys_match_exact_schema_contract(self) -> None:
        candidates = pd.DataFrame({"ticker": ["ONE"]})
        prices_by_ticker = {"ONE": _price_df(close=100.0, volume=100_000.0)}
        result = sweep_broad_universe_floors(candidates, prices_by_ticker)
        assert set(result.keys()) == {
            "broad_universe_survivors_at_5m_count",
            "broad_universe_survivors_at_10m_count",
            "broad_universe_survivors_at_15m_count",
            "broad_universe_adr_suspect_count",
            "broad_universe_survivor_fundamentals_coverage_pct",
            "broad_universe_sector_unknown_pct",
        }

    def test_default_first_floor_equals_broad_universe_adv_floor_usd(self) -> None:
        """The DEFAULT floors tuple's first (smallest) entry is bound to the
        live production constant, not a hardcoded literal — so the sweep
        always includes 'today's floor' as a data point."""
        sig = inspect.signature(sweep_broad_universe_floors)
        default_floors = sig.parameters["floors"].default
        assert default_floors[0] == config.BROAD_UNIVERSE_ADV_FLOOR_USD
        assert sorted(default_floors) == list(default_floors), (
            "default floors must already be ascending"
        )


class TestSweepBroadUniverseFloorsGracefulDegradation:
    def test_empty_candidates_returns_all_none(self) -> None:
        empty = pd.DataFrame(columns=["ticker"])
        result = sweep_broad_universe_floors(empty, {})
        assert all(v is None for v in result.values())

    def test_zero_price_data_returns_all_none(self) -> None:
        candidates = pd.DataFrame({"ticker": ["GHOST1", "GHOST2"]})
        result = sweep_broad_universe_floors(candidates, {})
        assert all(v is None for v in result.values())

    def test_adr_suspect_none_when_security_types_missing(self) -> None:
        candidates = pd.DataFrame({"ticker": ["AAPL"]})
        prices_by_ticker = {"AAPL": _price_df(close=100.0, volume=100_000.0)}
        result = sweep_broad_universe_floors(
            candidates,
            prices_by_ticker,
            security_types_by_ticker=None,
            foreign_filer_by_ticker={"AAPL": True},
        )
        assert result["broad_universe_adr_suspect_count"] is None

    def test_adr_suspect_none_when_foreign_filer_missing(self) -> None:
        candidates = pd.DataFrame({"ticker": ["AAPL"]})
        prices_by_ticker = {"AAPL": _price_df(close=100.0, volume=100_000.0)}
        result = sweep_broad_universe_floors(
            candidates,
            prices_by_ticker,
            security_types_by_ticker={"AAPL": "Common stock"},
            foreign_filer_by_ticker=None,
        )
        assert result["broad_universe_adr_suspect_count"] is None

    def test_fundamentals_coverage_none_when_signal_missing(self) -> None:
        candidates = pd.DataFrame({"ticker": ["AAPL"]})
        prices_by_ticker = {"AAPL": _price_df(close=100.0, volume=100_000.0)}
        result = sweep_broad_universe_floors(
            candidates, prices_by_ticker, fundamentals_ok_by_ticker=None
        )
        assert result["broad_universe_survivor_fundamentals_coverage_pct"] is None

    def test_production_callsite_shape_all_three_optional_signals_none(self) -> None:
        """Mirrors the EXACT kwargs compute/main.py's wiring block passes
        today — floor counts + sector_unknown_pct still populate; the two
        signal-gated fields are None."""
        candidates = pd.DataFrame({"ticker": ["AAPL", "MSFT"]})
        prices_by_ticker = {
            "AAPL": _price_df(close=100.0, volume=200_000.0),  # $20M
            "MSFT": _price_df(close=100.0, volume=200_000.0),  # $20M
        }
        result = sweep_broad_universe_floors(
            candidates,
            prices_by_ticker,
            security_types_by_ticker=None,
            foreign_filer_by_ticker=None,
            fundamentals_ok_by_ticker=None,
        )
        assert result["broad_universe_survivors_at_5m_count"] == 2
        assert result["broad_universe_survivors_at_10m_count"] == 2
        assert result["broad_universe_survivors_at_15m_count"] == 2
        assert result["broad_universe_adr_suspect_count"] is None
        assert result["broad_universe_survivor_fundamentals_coverage_pct"] is None
        assert result["broad_universe_sector_unknown_pct"] == 100.0


# ---------------------------------------------------------------------------
# FS5 — ADR-suspect arithmetic (both signals supplied)
# ---------------------------------------------------------------------------


class TestAdrSuspectCountArithmetic:
    def test_counts_only_equity_and_foreign_intersection(self) -> None:
        candidates = pd.DataFrame(
            {"ticker": ["EQ_FOREIGN", "EQ_DOMESTIC", "ETF_FOREIGN", "EQ_UNKNOWN_FOREIGN"]}
        )
        prices_by_ticker = {
            t: _price_df(close=100.0, volume=100_000.0) for t in candidates["ticker"]
        }
        security_types_by_ticker = {
            "EQ_FOREIGN": "Common stock",
            "EQ_DOMESTIC": "Common stock",
            "ETF_FOREIGN": "ETF",
            # EQ_UNKNOWN_FOREIGN intentionally absent from this mapping.
        }
        foreign_filer_by_ticker = {
            "EQ_FOREIGN": True,
            "EQ_DOMESTIC": False,
            "ETF_FOREIGN": True,
            "EQ_UNKNOWN_FOREIGN": True,
        }
        result = sweep_broad_universe_floors(
            candidates,
            prices_by_ticker,
            security_types_by_ticker=security_types_by_ticker,
            foreign_filer_by_ticker=foreign_filer_by_ticker,
        )
        # Only EQ_FOREIGN is both equity-typed AND foreign-filer-flagged.
        # EQ_DOMESTIC: equity but not foreign. ETF_FOREIGN: foreign but not
        # equity. EQ_UNKNOWN_FOREIGN: missing security_type -> not counted
        # (conservative — never guesses at an incomplete mapping).
        assert result["broad_universe_adr_suspect_count"] == 1

    def test_raw_equity_quote_type_code_also_matches(self) -> None:
        """Defensive: accepts the RAW yfinance quote-type code 'EQUITY' too,
        not just the mapped display label 'Common stock'."""
        candidates = pd.DataFrame({"ticker": ["RAWCODE"]})
        prices_by_ticker = {"RAWCODE": _price_df(close=100.0, volume=100_000.0)}
        result = sweep_broad_universe_floors(
            candidates,
            prices_by_ticker,
            security_types_by_ticker={"RAWCODE": "EQUITY"},
            foreign_filer_by_ticker={"RAWCODE": True},
        )
        assert result["broad_universe_adr_suspect_count"] == 1

    def test_zero_when_no_ticker_matches(self) -> None:
        candidates = pd.DataFrame({"ticker": ["DOMESTIC"]})
        prices_by_ticker = {"DOMESTIC": _price_df(close=100.0, volume=100_000.0)}
        result = sweep_broad_universe_floors(
            candidates,
            prices_by_ticker,
            security_types_by_ticker={"DOMESTIC": "Common stock"},
            foreign_filer_by_ticker={"DOMESTIC": False},
        )
        assert result["broad_universe_adr_suspect_count"] == 0


# ---------------------------------------------------------------------------
# FS6 — sector-unknown-pct
# ---------------------------------------------------------------------------


class TestSectorUnknownPct:
    def test_no_sector_column_is_structurally_100_pct(self) -> None:
        """The Phase 9.1 probe callsite's raw candidate pool has NO 'sector'
        column at all — every survivor is counted unknown-sector."""
        candidates = pd.DataFrame({"ticker": ["AAPL", "MSFT"]})
        prices_by_ticker = {
            "AAPL": _price_df(close=100.0, volume=100_000.0),
            "MSFT": _price_df(close=100.0, volume=100_000.0),
        }
        result = sweep_broad_universe_floors(candidates, prices_by_ticker)
        assert result["broad_universe_sector_unknown_pct"] == 100.0

    def test_sector_column_present_computes_real_percentage(self) -> None:
        """The Phase 9.3 ranked-path callsite's shaped frame HAS a 'sector'
        column (always 'Unknown' per candidates_to_universe_frame — but this
        test uses a synthetic mix to prove the arithmetic itself, not just
        the structural-100% shortcut)."""
        candidates = pd.DataFrame(
            {
                "ticker": ["KNOWN1", "KNOWN2", "UNKNOWN1", "UNKNOWN2"],
                "sector": ["Technology", "Healthcare", "Unknown", "Unknown"],
            }
        )
        prices_by_ticker = {
            t: _price_df(close=100.0, volume=100_000.0) for t in candidates["ticker"]
        }
        result = sweep_broad_universe_floors(candidates, prices_by_ticker)
        assert result["broad_universe_sector_unknown_pct"] == 50.0

    def test_sector_column_all_unknown_matches_structural_case(self) -> None:
        candidates = pd.DataFrame(
            {"ticker": ["A", "B"], "sector": ["Unknown", "Unknown"]}
        )
        prices_by_ticker = {
            t: _price_df(close=100.0, volume=100_000.0) for t in candidates["ticker"]
        }
        result = sweep_broad_universe_floors(candidates, prices_by_ticker)
        assert result["broad_universe_sector_unknown_pct"] == 100.0

    def test_none_when_chosen_floor_survivor_set_empty(self) -> None:
        """Candidates exist and have price data, but none clear the $5M
        floor -> chosen-floor survivor set is empty -> None (not 0.0 or
        100.0 — an empty-denominator percentage is undefined)."""
        candidates = pd.DataFrame({"ticker": ["THIN"]})
        prices_by_ticker = {"THIN": _price_df(close=100.0, volume=1_000.0)}  # $100K ADV
        result = sweep_broad_universe_floors(candidates, prices_by_ticker)
        assert result["broad_universe_survivors_at_5m_count"] == 0
        assert result["broad_universe_sector_unknown_pct"] is None


# ---------------------------------------------------------------------------
# FS7 — survivor-fundamentals-coverage-pct arithmetic
# ---------------------------------------------------------------------------


class TestSurvivorFundamentalsCoveragePct:
    def test_coverage_computed_over_chosen_floor_survivors_only(self) -> None:
        candidates = pd.DataFrame({"ticker": ["OK1", "OK2", "BAD1", "BELOWFLOOR"]})
        prices_by_ticker = {
            "OK1": _price_df(close=100.0, volume=100_000.0),  # $10M
            "OK2": _price_df(close=100.0, volume=100_000.0),  # $10M
            "BAD1": _price_df(close=100.0, volume=100_000.0),  # $10M
            "BELOWFLOOR": _price_df(close=100.0, volume=1_000.0),  # $100K — excluded
        }
        fundamentals_ok_by_ticker = {
            "OK1": True,
            "OK2": True,
            "BAD1": False,
            "BELOWFLOOR": True,  # must NOT count — not a $5M-floor survivor
        }
        result = sweep_broad_universe_floors(
            candidates,
            prices_by_ticker,
            fundamentals_ok_by_ticker=fundamentals_ok_by_ticker,
        )
        assert result["broad_universe_survivors_at_5m_count"] == 3
        # 2 of 3 chosen-floor survivors have usable fundamentals.
        # round(100.0 * 2 / 3, 2) == 66.67 (matches the implementation's
        # own round(..., 2) — asserted directly, no approx needed).
        assert result["broad_universe_survivor_fundamentals_coverage_pct"] == 66.67

    def test_missing_ticker_in_mapping_treated_as_not_ok(self) -> None:
        candidates = pd.DataFrame({"ticker": ["OK", "MISSING"]})
        prices_by_ticker = {
            "OK": _price_df(close=100.0, volume=100_000.0),
            "MISSING": _price_df(close=100.0, volume=100_000.0),
        }
        result = sweep_broad_universe_floors(
            candidates,
            prices_by_ticker,
            fundamentals_ok_by_ticker={"OK": True},  # MISSING absent
        )
        assert result["broad_universe_survivor_fundamentals_coverage_pct"] == 50.0


# ---------------------------------------------------------------------------
# FS8 — the "latent coupling defect" fix
# ---------------------------------------------------------------------------


class TestAdvFloorDecoupling:
    def test_broad_universe_adv_floor_usd_equals_adv_floor_usd_at_launch(self) -> None:
        """Byte-identical decoupling: the new constant's INITIAL value is
        identical to the constant it decouples from."""
        assert config.BROAD_UNIVERSE_ADV_FLOOR_USD == config.ADV_FLOOR_USD
        assert config.BROAD_UNIVERSE_ADV_FLOOR_USD == 5_000_000.0

    def test_select_broad_universe_survivors_default_uses_new_constant(self) -> None:
        """The RANKED-path screen's adv_floor default reads the NEW,
        decoupled constant — not the shared ADV_FLOOR_USD anymore."""
        sig = inspect.signature(select_broad_universe_survivors)
        assert sig.parameters["adv_floor"].default == config.BROAD_UNIVERSE_ADV_FLOOR_USD

    def test_screen_broad_universe_investability_default_unchanged(self) -> None:
        """The Phase 9.1 probe diagnostic's adv_floor default is UNCHANGED —
        still config.ADV_FLOOR_USD, for probe-continuity (task requirement:
        do NOT change screen_broad_universe_investability's default)."""
        sig = inspect.signature(screen_broad_universe_investability)
        assert sig.parameters["adv_floor"].default == config.ADV_FLOOR_USD

    def test_survivor_set_unaffected_by_the_decoupling(self) -> None:
        """End-to-end proof: since the two constants hold the same value,
        select_broad_universe_survivors' output is unaffected by which
        constant its default resolves to."""
        candidates = pd.DataFrame({"ticker": ["AT_FLOOR", "BELOW_FLOOR"]})
        prices_by_ticker = {
            "AT_FLOOR": _price_df(close=100.0, volume=51_000.0),  # $5.1M > $5M
            "BELOW_FLOOR": _price_df(close=100.0, volume=49_000.0),  # $4.9M < $5M
        }
        survivors = select_broad_universe_survivors(candidates, prices_by_ticker)
        assert survivors == {"AT_FLOOR"}


# ---------------------------------------------------------------------------
# FS9 — compute/main.py wiring: byte-identical guard companion
# ---------------------------------------------------------------------------


class TestMainPySweepWiringPosition:
    def test_sweep_call_present_in_run_weekly_compute(self) -> None:
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        assert "sweep_broad_universe_floors(" in src

    def test_sweep_call_sits_after_probe_call_and_before_survivor_reduction(self) -> None:
        """The sweep call must sit in the SAME unconditional post-Step-1
        block as the existing Phase 9.1 probe — after the probe call,
        before the (dispatch-only-gated) survivor-reduction block that
        calls select_broad_universe_survivors."""
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        probe_call_pos = src.find("_run_broad_universe_probe(\n")
        sweep_call_pos = src.find("sweep_broad_universe_floors(")
        survivor_call_pos = src.find("select_broad_universe_survivors(")

        assert probe_call_pos != -1
        assert sweep_call_pos != -1
        assert survivor_call_pos != -1
        assert probe_call_pos < sweep_call_pos < survivor_call_pos, (
            "sweep_broad_universe_floors must run AFTER the Phase 9.1 probe "
            "and BEFORE the dispatch-only survivor-reduction block — the "
            "'same place' the task brief specifies"
        )

    def test_sweep_call_sits_outside_every_universe_selector_branch(self) -> None:
        """Structural guard: the sweep call must be positioned strictly
        AFTER the entire if/elif/elif/else universe-selector chain closes
        (mirrors TestDefaultPathUnchangedRegressionGuard's else-branch
        anchor in test_broad_universe_ranked.py) — every universe path
        (sp500/sp900/sp1500/broad_investable_us) reaches it identically."""
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        else_pos = src.find(
            "    else:\n"
            "        # Default sp500 path — byte-identical scoring to pre-PR-3a."
        )
        sweep_call_pos = src.find("sweep_broad_universe_floors(")
        assert else_pos != -1
        assert sweep_call_pos != -1
        assert else_pos < sweep_call_pos

    def test_sweep_gated_on_same_skip_env_var_as_probe(self) -> None:
        """The sweep block must be gated on the SAME
        config.BROAD_UNIVERSE_SKIP_ENV_VAR escape hatch the probe uses —
        prevents an unconditional network/disk-cache attempt in the
        pre-merge sim (which sets QR_SKIP_BROAD_UNIVERSE=1)."""
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        sweep_call_pos = src.find("sweep_broad_universe_floors(")
        assert sweep_call_pos != -1
        preceding = src[:sweep_call_pos]
        gate_pos = preceding.rfind("config.BROAD_UNIVERSE_SKIP_ENV_VAR")
        assert gate_pos != -1, (
            "sweep_broad_universe_floors call must be preceded by a "
            "config.BROAD_UNIVERSE_SKIP_ENV_VAR gate check"
        )

    def test_sweep_call_wrapped_in_its_own_try_except(self) -> None:
        """Graceful degradation: a failure inside the sweep block must not
        propagate — it must be caught by a dedicated except clause (never
        blocks the cron, mirrors every other Rule-18 diagnostic block)."""
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        sweep_call_pos = src.find("sweep_broad_universe_floors(")
        assert sweep_call_pos != -1
        except_pos = src.find("except Exception as _broad_sweep_exc:", sweep_call_pos)
        assert except_pos != -1, (
            "sweep_broad_universe_floors call must be inside a try block "
            "with a dedicated except Exception as _broad_sweep_exc: clause"
        )

    def test_metadata_constructor_receives_all_six_new_kwargs(self) -> None:
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        for kwarg in (
            "broad_universe_survivors_at_5m_count=",
            "broad_universe_survivors_at_10m_count=",
            "broad_universe_survivors_at_15m_count=",
            "broad_universe_adr_suspect_count=",
            "broad_universe_survivor_fundamentals_coverage_pct=",
            "broad_universe_sector_unknown_pct=",
        ):
            assert kwarg in src, f"Metadata(...) constructor must pass {kwarg}"
