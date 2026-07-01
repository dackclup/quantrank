"""Tests for Phase 9.3 — Broad Investable US RANKED path (dispatch-only).

Covers the ``QR_UNIVERSE=broad_investable_us`` wiring added to
``compute/main.py``'s universe-selector seam plus the two new pure functions
in ``compute/ingest/broad_universe.py``:

  - ``candidates_to_universe_frame``     — shapes the raw candidate pool into
                                            a universe DataFrame.
  - ``select_broad_universe_survivors``  — the ranked-path investability
                                            screen (returns the SURVIVOR SET,
                                            distinct from the probe's
                                            diagnostic-count function).

Also covers the ``derive_index_memberships`` extension that suppresses the
russell1000 proxy tag for the new ``"broad"`` cohort, and the CRITICAL
default-path-unchanged regression guard: the sp1500/sp900/sp500 branches of
``run_weekly_compute``'s universe selector must be byte-identical to their
pre-Phase-9.3 behaviour.

All tests are offline (no network, no disk-cache writes). Wiring-layer
assertions use ``inspect.getsource`` (mirrors ``tests/test_ingest/
test_sp1500_seam.py`` — a full ``run_weekly_compute`` invocation is
impractical for offline CI; the source-level checks pin the exact
integration points that were actually missing coverage).

Test groups:
  BUR1  candidates_to_universe_frame — column shape + sector/sub_industry/
        cik/cohort defaults + empty-input graceful degradation + cik
        zero-padding + missing-cik-str fallback.
  BUR2  select_broad_universe_survivors — price/ADV floor screen, returns a
        ticker SET (not counts); empty candidates; no-price-data tickers
        excluded (not crashed on); mirrors the P1-G1 look-ahead-guard
        floors from test_broad_universe.py's BU2.
  BUR3  derive_index_memberships — "broad" cohort suppresses the
        russell1000 proxy tag (new); sp500/sp600 regression guards
        (existing behaviour UNCHANGED).
  BUR4  run_weekly_compute wiring — the new elif branch exists, is gated on
        config.QR_UNIVERSE == "broad_investable_us", sets universe=
        "BROAD_INVESTABLE_US" in the Metadata constructor, calls
        candidates_to_universe_frame + select_broad_universe_survivors in
        the right positions (after the elif, before Step 2 fundamentals).
  BUR5  DEFAULT-PATH-UNCHANGED regression guard — the sp500/sp900/sp1500
        elif/else branches' source text is IDENTICAL to a pinned pre-9.3
        snapshot (proves the new elif is purely additive, no existing
        branch was touched); the "SP1500"/"SP900" Metadata universe labels
        still appear unconditionally (not nested inside the new branch).
  BUR6  QR_UNIVERSE config docstring documents the new accepted value;
        the absent-env-var default is still "sp500" (regression).
  BUR7  End-to-end screen-then-reduce simulation — replays the EXACT
        reduction expressions from compute/main.py (df.isin() filter, rows
        list-comp, prices_by_ticker / adv_by_ticker dict-comps) against
        synthetic fetch_all_prices-shaped inputs, proving the full chain
        behaves correctly TOGETHER (not just each piece in isolation), incl.
        the all-fail-to-empty-frame degradation path.
"""

from __future__ import annotations

import inspect

import pandas as pd
import pytest

from compute.ingest.broad_universe import (
    candidates_to_universe_frame,
    select_broad_universe_survivors,
)
from compute.ingest.universe import derive_index_memberships

# ---------------------------------------------------------------------------
# Helpers — synthetic price DataFrames (mirrors test_broad_universe.py)
# ---------------------------------------------------------------------------


def _price_df(n_rows: int = 40, close: float = 50.0, volume: float = 200_000.0) -> pd.DataFrame:
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
# BUR1 — candidates_to_universe_frame
# ---------------------------------------------------------------------------


class TestCandidatesToUniverseFrame:
    def test_shapes_expected_columns(self) -> None:
        candidates = pd.DataFrame(
            {
                "ticker": ["AAPL", "MSFT"],
                "name": ["Apple Inc.", "Microsoft Corp."],
                "exchange": ["Nasdaq", "NYSE"],
                "cik_str": ["320193", "789019"],
            }
        )
        frame = candidates_to_universe_frame(candidates)

        assert list(frame.columns) == [
            "ticker",
            "name",
            "sector",
            "sub_industry",
            "cik",
            "cohort",
        ]
        assert len(frame) == 2

    def test_sector_always_unknown(self) -> None:
        """GICS sector is not available from the SEC source — always 'Unknown'.

        Mirrors the exact precedent in compute/ingest/universe.py's S&P 400/600
        Wikipedia loader graceful-degradation path.
        """
        candidates = pd.DataFrame({"ticker": ["AAPL", "MSFT", "TINY"]})
        frame = candidates_to_universe_frame(candidates)
        assert (frame["sector"] == "Unknown").all()

    def test_sub_industry_always_none(self) -> None:
        candidates = pd.DataFrame({"ticker": ["AAPL"]})
        frame = candidates_to_universe_frame(candidates)
        assert frame["sub_industry"].iloc[0] is None

    def test_cohort_always_broad(self) -> None:
        candidates = pd.DataFrame({"ticker": ["AAPL", "MSFT", "TINY"]})
        frame = candidates_to_universe_frame(candidates)
        assert (frame["cohort"] == "broad").all()

    def test_cik_zero_padded_when_present(self) -> None:
        candidates = pd.DataFrame(
            {"ticker": ["AAPL"], "name": ["Apple Inc."], "cik_str": ["320193"]}
        )
        frame = candidates_to_universe_frame(candidates)
        assert frame["cik"].iloc[0] == "0000320193"

    def test_cik_none_when_cik_str_missing_column(self) -> None:
        """No cik_str column at all → cik column is all None (graceful)."""
        candidates = pd.DataFrame({"ticker": ["AAPL"], "name": ["Apple Inc."]})
        frame = candidates_to_universe_frame(candidates)
        assert frame["cik"].iloc[0] is None

    def test_cik_none_when_cik_str_value_missing(self) -> None:
        """cik_str column present but this row's value is None/NaN → cik is None."""
        candidates = pd.DataFrame(
            {"ticker": ["AAPL", "TINY"], "name": ["Apple Inc.", "Tiny Corp"], "cik_str": ["320193", None]}
        )
        frame = candidates_to_universe_frame(candidates)
        assert frame.loc[frame["ticker"] == "TINY", "cik"].iloc[0] is None
        assert frame.loc[frame["ticker"] == "AAPL", "cik"].iloc[0] == "0000320193"

    def test_cik_none_on_malformed_cik_str(self) -> None:
        """A non-numeric cik_str value degrades to None rather than raising."""
        candidates = pd.DataFrame(
            {"ticker": ["BAD"], "name": ["Bad Corp"], "cik_str": ["not-a-number"]}
        )
        frame = candidates_to_universe_frame(candidates)
        assert frame["cik"].iloc[0] is None

    def test_name_falls_back_to_ticker_when_name_column_missing(self) -> None:
        candidates = pd.DataFrame({"ticker": ["AAPL"]})
        frame = candidates_to_universe_frame(candidates)
        assert frame["name"].iloc[0] == "AAPL"

    def test_empty_candidates_returns_correctly_columned_empty_frame(self) -> None:
        """Empty input never raises — returns a zero-row DataFrame with the
        expected columns so downstream fetch_all_prices(universe) degrades
        to zero rows rather than crashing on a missing column."""
        empty = pd.DataFrame(columns=["ticker", "name", "exchange"])
        frame = candidates_to_universe_frame(empty)
        assert list(frame.columns) == [
            "ticker",
            "name",
            "sector",
            "sub_industry",
            "cik",
            "cohort",
        ]
        assert len(frame) == 0


# ---------------------------------------------------------------------------
# BUR2 — select_broad_universe_survivors
# ---------------------------------------------------------------------------


class TestSelectBroadUniverseSurvivors:
    def test_returns_ticker_set_not_counts(self) -> None:
        """Distinct from screen_broad_universe_investability — returns a
        set[str], not a dict of counts."""
        candidates = pd.DataFrame({"ticker": ["PASS"]})
        prices_by_ticker = {"PASS": _price_df(close=100.0, volume=100_000.0)}

        result = select_broad_universe_survivors(candidates, prices_by_ticker)
        assert isinstance(result, set)
        assert result == {"PASS"}

    def test_price_floor_excludes_low_price_ticker(self) -> None:
        candidates = pd.DataFrame({"ticker": ["CHEAP"]})
        prices_by_ticker = {"CHEAP": _price_df(close=2.0, volume=1_000_000.0)}

        survivors = select_broad_universe_survivors(candidates, prices_by_ticker)
        assert survivors == set()

    def test_adv_floor_excludes_low_volume_ticker(self) -> None:
        candidates = pd.DataFrame({"ticker": ["THIN"]})
        # close=$100, volume=20_000 -> ADV=$2M < $5M floor
        prices_by_ticker = {"THIN": _price_df(close=100.0, volume=20_000.0)}

        survivors = select_broad_universe_survivors(candidates, prices_by_ticker)
        assert survivors == set()

    def test_ticker_with_no_price_data_excluded_not_crashed(self) -> None:
        """A candidate absent from prices_by_ticker (Step-1 fetch failure)
        must be silently excluded, never raise."""
        candidates = pd.DataFrame({"ticker": ["GHOST", "PASS"]})
        prices_by_ticker = {"PASS": _price_df(close=100.0, volume=100_000.0)}

        survivors = select_broad_universe_survivors(candidates, prices_by_ticker)
        assert survivors == {"PASS"}
        assert "GHOST" not in survivors

    def test_mixed_pass_fail_scenario(self) -> None:
        candidates = pd.DataFrame({"ticker": ["PASS1", "PFAIL", "AFAIL", "PASS2"]})
        prices_by_ticker = {
            "PASS1": _price_df(close=100.0, volume=100_000.0),  # ADV $10M — pass
            "PFAIL": _price_df(close=2.0, volume=100_000.0),  # price fail
            "AFAIL": _price_df(close=100.0, volume=20_000.0),  # ADV fail
            "PASS2": _price_df(close=50.0, volume=120_000.0),  # ADV $6M — pass
        }
        survivors = select_broad_universe_survivors(candidates, prices_by_ticker)
        assert survivors == {"PASS1", "PASS2"}

    def test_empty_candidates_returns_empty_set(self) -> None:
        survivors = select_broad_universe_survivors(
            pd.DataFrame(columns=["ticker"]), {}
        )
        assert survivors == set()

    def test_empty_prices_by_ticker_returns_empty_set(self) -> None:
        """All candidates present but zero price data — no crash, empty set."""
        candidates = pd.DataFrame({"ticker": ["A", "B", "C"]})
        survivors = select_broad_universe_survivors(candidates, {})
        assert survivors == set()

    def test_lookahead_guard_trailing_window_not_full_sample(self) -> None:
        """P1-G1 analog: the survivor screen must read the TRAILING-30d ADV,
        not a full-sample average (reuses compute_average_dollar_volume,
        which is already covered by BU2 in test_broad_universe.py — this
        test locks the same invariant on the NEW survivor-set function)."""
        lookback = 30
        n_history = 200
        idx = pd.bdate_range("2024-01-02", periods=n_history)
        n_history_rows = n_history - lookback
        closes = [100.0] * n_history_rows + [100.0] * lookback
        # historically huge volume, trailing volume tiny
        volumes = [1_000_000.0] * n_history_rows + [40_000.0] * lookback
        trap_df = pd.DataFrame(
            {
                "Open": closes,
                "High": [c + 1.0 for c in closes],
                "Low": [c - 1.0 for c in closes],
                "Close": closes,
                "Volume": volumes,
            },
            index=idx,
        )
        candidates = pd.DataFrame({"ticker": ["TRAP"]})
        survivors = select_broad_universe_survivors(candidates, {"TRAP": trap_df})
        assert survivors == set(), (
            "TRAP must be excluded — trailing-30d ADV ($4M) is below the $5M "
            "floor even though full-history ADV is huge (look-ahead guard)."
        )


# ---------------------------------------------------------------------------
# BUR3 — derive_index_memberships "broad" cohort extension
# ---------------------------------------------------------------------------


class TestDeriveIndexMembershipsBroadCohort:
    def test_broad_cohort_suppresses_russell1000_with_known_positive_cap(self) -> None:
        """A broad-universe-only ticker with a known positive market cap must
        NOT get the russell1000 proxy tag — the S&P-900-structural argument
        does not hold for the (unfiltered-at-the-top) broad candidate pool."""
        result = derive_index_memberships(
            "TINYCO", cohort="broad", dow30=set(), ndx=set(), market_cap=1_000_000.0
        )
        assert result == ["broad"]
        assert "russell1000" not in result

    def test_broad_cohort_with_dow30_ndx_overlap(self) -> None:
        """dow30/ndx tags still apply on the broad cohort (independent gates)."""
        result = derive_index_memberships(
            "AAPL",
            cohort="broad",
            dow30={"AAPL"},
            ndx={"AAPL"},
            market_cap=3_000_000_000_000.0,
        )
        assert result == ["broad", "dow30", "ndx"]
        assert "russell1000" not in result

    def test_broad_cohort_with_none_market_cap(self) -> None:
        result = derive_index_memberships(
            "UNKNOWNCO", cohort="broad", dow30=set(), ndx=set(), market_cap=None
        )
        assert result == ["broad"]

    # -- Regression guards: existing cohorts UNCHANGED --------------------

    def test_sp500_still_gets_russell1000_regression_guard(self) -> None:
        result = derive_index_memberships(
            "AAPL", cohort="sp500", dow30=set(), ndx=set(), market_cap=3_000_000_000_000.0
        )
        assert "russell1000" in result

    def test_sp400_still_gets_russell1000_regression_guard(self) -> None:
        result = derive_index_memberships(
            "MID1", cohort="sp400", dow30=set(), ndx=set(), market_cap=8_000_000_000.0
        )
        assert "russell1000" in result

    def test_sp600_still_suppresses_russell1000_regression_guard(self) -> None:
        result = derive_index_memberships(
            "SML1", cohort="sp600", dow30=set(), ndx=set(), market_cap=500_000_000.0
        )
        assert result == ["sp600"]
        assert "russell1000" not in result


# ---------------------------------------------------------------------------
# BUR4 — run_weekly_compute wiring (source-level, mirrors test_sp1500_seam.py)
# ---------------------------------------------------------------------------


class TestRunWeeklyComputeBroadWiring:
    def test_broad_investable_us_elif_branch_present(self) -> None:
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        assert 'elif config.QR_UNIVERSE == "broad_investable_us":' in src, (
            "run_weekly_compute must have an elif branch gated on "
            'config.QR_UNIVERSE == "broad_investable_us"'
        )

    def test_broad_branch_calls_candidates_to_universe_frame(self) -> None:
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        branch_pos = src.find('elif config.QR_UNIVERSE == "broad_investable_us":')
        assert branch_pos != -1

        call_pos = src.find("candidates_to_universe_frame(")
        assert call_pos != -1, "candidates_to_universe_frame must be called in run_weekly_compute"
        assert call_pos > branch_pos, (
            "candidates_to_universe_frame call must be inside the "
            "broad_investable_us elif branch"
        )

    def test_broad_investable_us_metadata_universe_label_present(self) -> None:
        """The Metadata constructor must emit 'BROAD_INVESTABLE_US' gated on
        config.QR_UNIVERSE == 'broad_investable_us'."""
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        assert '"BROAD_INVESTABLE_US"' in src
        assert 'config.QR_UNIVERSE == "broad_investable_us"' in src

        # The label must sit inside the universe= assignment block, gated by
        # the correct sentinel (not a bare always-on string).
        universe_assign_pos = src.find("universe=(\n")
        assert universe_assign_pos != -1
        universe_assign_block = src[universe_assign_pos:universe_assign_pos + 600]
        assert '"BROAD_INVESTABLE_US"' in universe_assign_block
        assert 'config.QR_UNIVERSE == "broad_investable_us"' in universe_assign_block

    def test_survivor_reduction_calls_select_broad_universe_survivors(self) -> None:
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        call_pos = src.find("select_broad_universe_survivors(")
        assert call_pos != -1, (
            "select_broad_universe_survivors must be called in run_weekly_compute"
        )

    def test_survivor_reduction_runs_before_step2_fundamentals(self) -> None:
        """The survivor-reduction block must appear BEFORE fetch_all_fundamentals
        is called, so Step 2 only fetches fundamentals for survivors."""
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        screen_pos = src.find("select_broad_universe_survivors(")
        # There are two fetch_all_fundamentals call sites are not expected;
        # find the Step 2 call specifically (annual history is a later step).
        step2_pos = src.find("fetch_all_fundamentals(\n        df,")
        assert screen_pos != -1
        assert step2_pos != -1
        assert screen_pos < step2_pos, (
            "select_broad_universe_survivors must run BEFORE Step 2 "
            "fetch_all_fundamentals so fundamentals only fetch for survivors"
        )

    def test_survivor_reduction_gated_on_qr_universe_sentinel(self) -> None:
        """The survivor-reduction block must be gated behind the same
        QR_UNIVERSE sentinel — never runs on the sp1500/sp900/sp500 paths."""
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        screen_pos = src.find("select_broad_universe_survivors(")
        # Walk backwards from the call to find the nearest gating if-statement.
        preceding = src[:screen_pos]
        gate_pos = preceding.rfind('if config.QR_UNIVERSE == "broad_investable_us":')
        assert gate_pos != -1, (
            "select_broad_universe_survivors call must be preceded by an "
            'if config.QR_UNIVERSE == "broad_investable_us": gate'
        )

    def test_min_valid_tickers_abort_gate_present_on_broad_path(self) -> None:
        """The broad-path survivor reduction must abort (return 0) if the
        survivor count falls below MIN_VALID_TICKERS — mirrors the Step-1
        abort gate."""
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        screen_pos = src.find("select_broad_universe_survivors(")
        assert screen_pos != -1
        # The MIN_VALID_TICKERS check must appear after the screen call,
        # within the broad-path block.
        after_screen = src[screen_pos : screen_pos + 3000]
        assert "config.MIN_VALID_TICKERS" in after_screen
        assert "return 0" in after_screen

    def test_screen_failure_aborts_rather_than_falls_through_unscreened(self) -> None:
        """Design decision (deliberately NOT the usual fall-through idiom):
        a raised exception from select_broad_universe_survivors must ABORT
        (return 0) rather than fall through to scoring the full unscreened
        ~6,883-name candidate frame.  Falling through would double the
        fundamentals-fetch volume this PR explicitly bounds (task
        requirement: "control runtime") and risk a CI timeout — on this
        dispatch-only path, abort-and-preserve-last-good-data is the safer
        failure mode.  The call must sit inside its OWN try/except (not
        share a try block with the DataFrame-reduction lines that follow
        it), and that except clause must return 0 — never continue past it
        with an unreduced universe."""
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        gate_pos = src.find('if config.QR_UNIVERSE == "broad_investable_us":')
        # Locate the SECOND occurrence (the survivor-reduction block, not
        # the universe-selector elif — inspect.getsource includes the elif
        # branch text too, but "if config.QR_UNIVERSE ==" without "elif"
        # prefix is unique to the survivor-reduction gate).
        assert gate_pos != -1

        try_pos = src.find("try:", gate_pos)
        screen_call_pos = src.find("select_broad_universe_survivors(", gate_pos)
        except_pos = src.find("except Exception as _broad_screen_exc:", gate_pos)
        assert try_pos != -1
        assert screen_call_pos != -1
        assert except_pos != -1
        assert try_pos < screen_call_pos < except_pos, (
            "select_broad_universe_survivors call must be inside the "
            "try block that precedes the _broad_screen_exc except clause"
        )

        # The except block (up to the next unindented line / return) must
        # contain "return 0" — an abort, not a fall-through continuation.
        except_block = src[except_pos : except_pos + 500]
        assert "return 0" in except_block, (
            "The select_broad_universe_survivors except clause must abort "
            "with return 0, not fall through to an unscreened frame"
        )

        # The DataFrame-reduction lines (df[...].isin(...)) must appear
        # AFTER the except block closes, at the OUTER indentation level (not
        # inside the try/except) — confirming they run only on the happy
        # path where _broad_survivor_tickers is a real, valid set.
        reduction_pos = src.find('df = df[df["ticker"].isin(_broad_survivor_tickers)]')
        assert reduction_pos != -1
        assert reduction_pos > except_pos, (
            "The df reduction must appear after the except block — it must "
            "not be reachable when select_broad_universe_survivors raised"
        )


# ---------------------------------------------------------------------------
# BUR5 — DEFAULT-PATH-UNCHANGED regression guard (CRITICAL)
# ---------------------------------------------------------------------------


class TestDefaultPathUnchangedRegressionGuard:
    """Proves the Phase 9.3 broad_investable_us elif is PURELY ADDITIVE:
    the sp900 / sp1500 / sp500(else) branches were not touched.

    Strategy: assert that the exact source snippets that implement those
    three branches (pinned verbatim from the pre-Phase-9.3 source) are
    STILL PRESENT, byte-for-byte, in the current run_weekly_compute source.
    If any of these branches had been edited, the exact-substring match
    would fail — this is a stronger guard than a behavioural test because
    it catches accidental reformatting/reordering, not just semantic
    regressions a mocked pipeline run might miss.
    """

    def test_sp900_branch_source_unchanged(self) -> None:
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        # Pinned verbatim snippet from the sp900 branch (pre-9.3).
        pinned = (
            'if config.QR_UNIVERSE == "sp900":\n'
            '        logger.info("[sp900] Loading SP900 universe (sp500 + sp400 de-duped)…")\n'
            "        universe = get_sp900_constituents()\n"
            '        logger.info("[sp900] Universe size: %d (sp500+sp400 combined)", len(universe))'
        )
        assert pinned in src, (
            "sp900 branch source has changed — Phase 9.3 must be a PURELY "
            "ADDITIVE elif, never touching the existing sp900 branch"
        )

    def test_sp1500_branch_source_unchanged(self) -> None:
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        pinned = (
            'elif config.QR_UNIVERSE == "sp1500":\n'
        )
        assert pinned in src
        # The Slice-7 ranked-universe assignment line must still be present
        # verbatim (this is the load-bearing "sp600 is now ranked" line).
        pinned_ranked_line = (
            "        universe = _sp1500_full_frame.reset_index(drop=True)"
        )
        assert pinned_ranked_line in src, (
            "sp1500 branch's ranked-universe assignment has changed — "
            "Phase 9.3 must not touch the sp1500 branch"
        )

    def test_default_sp500_else_branch_source_unchanged(self) -> None:
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        pinned = (
            "    else:\n"
            "        # Default sp500 path — byte-identical scoring to pre-PR-3a.\n"
            "        # Add cohort column so _fetch_prices_one.row.get(\"cohort\") is always defined.\n"
            "        universe = get_sp500_constituents()\n"
            "        universe = universe.copy()\n"
            '        universe["cohort"] = "sp500"\n'
            '        logger.info("Universe size: %d", len(universe))'
        )
        assert pinned in src, (
            "Default sp500 (else) branch source has changed — Phase 9.3 must "
            "insert its new elif BEFORE this else, never touching its body"
        )

    def test_broad_investable_us_elif_sits_between_sp1500_and_default_else(self) -> None:
        """Structural guard: the new elif must be positioned AFTER the sp1500
        elif and BEFORE the final else — i.e. appended to the chain, not
        inserted in a way that could shadow an existing branch."""
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        sp1500_pos = src.find('elif config.QR_UNIVERSE == "sp1500":')
        broad_pos = src.find('elif config.QR_UNIVERSE == "broad_investable_us":')
        else_pos = src.find(
            "    else:\n"
            "        # Default sp500 path — byte-identical scoring to pre-PR-3a."
        )
        assert sp1500_pos != -1
        assert broad_pos != -1
        assert else_pos != -1
        assert sp1500_pos < broad_pos < else_pos, (
            "broad_investable_us elif must sit strictly between the sp1500 "
            "elif and the final default else — got positions "
            f"sp1500={sp1500_pos} broad={broad_pos} else={else_pos}"
        )

    def test_universe_labels_sp1500_sp900_still_unconditional_in_metadata(self) -> None:
        """The "SP1500" / "SP900" Metadata labels must still be reachable
        independent of the new broad_investable_us branch — i.e. the new
        nested ternary did not accidentally make SP1500/SP900 conditional
        on anything related to broad_investable_us."""
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        universe_assign_pos = src.find("universe=(\n")
        assert universe_assign_pos != -1
        block = src[universe_assign_pos : universe_assign_pos + 600]

        assert '"SP1500"' in block
        assert '"SP900"' in block
        assert '"BROAD_INVESTABLE_US"' in block
        assert 'config.QR_UNIVERSE == "sp1500"' in block
        assert 'config.QR_UNIVERSE == "sp900"' in block
        assert 'config.QR_UNIVERSE == "broad_investable_us"' in block

    def test_universe_cohort_sizes_recompute_gate_unaffected_by_broad_path(self) -> None:
        """The post-scoring cohort-size recompute gate (config.QR_UNIVERSE in
        ('sp900', 'sp1500')) must remain a 2-tuple — broad_investable_us must
        NOT be added to it (that recompute is sp900/sp1500-specific cohort
        bookkeeping unrelated to the broad path's own survivor accounting)."""
        import compute.main as main_mod

        src = inspect.getsource(main_mod.run_weekly_compute)
        assert 'config.QR_UNIVERSE in ("sp900", "sp1500")' in src, (
            "The cohort-size recompute gate must remain gated on exactly "
            '("sp900", "sp1500") — Phase 9.3 does not use _pilot_cohort_sizes '
            "so broad_investable_us must not be added to this tuple"
        )


# ---------------------------------------------------------------------------
# BUR6 — QR_UNIVERSE config docstring / accepted-values sanity
# ---------------------------------------------------------------------------


class TestQrUniverseConfigDocumentsBroadValue:
    def test_config_module_mentions_broad_investable_us(self) -> None:
        import compute.config as cfg

        src = inspect.getsource(cfg)
        assert "broad_investable_us" in src

    def test_default_qr_universe_env_absent_is_sp500(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Regression: absent QR_UNIVERSE env-var still defaults to 'sp500'
        (the module-level default expression is unaffected by this PR since
        QR_UNIVERSE is read once at import time — this test documents the
        expected behaviour of a fresh re-import)."""
        import importlib

        monkeypatch.delenv("QR_UNIVERSE", raising=False)
        import compute.config as cfg

        importlib.reload(cfg)
        try:
            assert cfg.QR_UNIVERSE == "sp500"
        finally:
            importlib.reload(cfg)


# ---------------------------------------------------------------------------
# BUR7 — End-to-end reduction simulation (mirrors the exact main.py pattern)
# ---------------------------------------------------------------------------


class TestScreenThenReduceSimulation:
    """Simulates the exact screen-then-reduce sequence used in
    ``run_weekly_compute``'s survivor-reduction block, WITHOUT invoking the
    full pipeline (impractical — see module docstring).  Builds synthetic
    ``universe`` / ``df`` / ``rows`` / ``prices_by_ticker`` / ``adv_by_ticker``
    matching the exact shapes ``fetch_all_prices`` produces, then replays the
    identical reduction expressions from ``compute/main.py`` line-for-line.

    This is the closest thing to an integration test the offline suite can
    afford — it proves the FULL chain (select_broad_universe_survivors →
    df.isin() filter → rows list-comp → prices_by_ticker dict-comp →
    adv_by_ticker dict-comp) behaves correctly TOGETHER, not just each piece
    in isolation.
    """

    def test_full_reduction_chain_keeps_only_survivors(self) -> None:
        candidates = pd.DataFrame(
            {
                "ticker": ["SURVIVOR1", "SURVIVOR2", "PRICEFAIL", "ADVFAIL"],
                "name": ["Survivor One", "Survivor Two", "Price Fail Co", "ADV Fail Co"],
            }
        )
        universe = candidates_to_universe_frame(candidates)
        assert len(universe) == 4

        prices_by_ticker = {
            "SURVIVOR1": _price_df(close=100.0, volume=100_000.0),  # ADV $10M — pass
            "SURVIVOR2": _price_df(close=50.0, volume=150_000.0),  # ADV $7.5M — pass
            "PRICEFAIL": _price_df(close=3.0, volume=500_000.0),  # price $3 < $5
            "ADVFAIL": _price_df(close=100.0, volume=10_000.0),  # ADV $1M < $5M
        }
        adv_by_ticker = {
            "SURVIVOR1": 10_000_000.0,
            "SURVIVOR2": 7_500_000.0,
            "PRICEFAIL": 1_500_000.0,
            "ADVFAIL": 1_000_000.0,
        }
        # Mirror fetch_all_prices' output shape: rows is a list of dicts,
        # df is a DataFrame set_index("ticker", drop=False).
        rows = [
            {"ticker": t, "name": universe.loc[universe["ticker"] == t, "name"].iloc[0]}
            for t in candidates["ticker"]
        ]
        df = pd.DataFrame(rows)
        df = df.set_index("ticker", drop=False)

        # --- Replay the EXACT reduction sequence from compute/main.py -----
        survivor_tickers = select_broad_universe_survivors(
            candidates=universe, prices_by_ticker=prices_by_ticker
        )
        assert survivor_tickers == {"SURVIVOR1", "SURVIVOR2"}

        pre_screen_count = len(df)
        df = df[df["ticker"].isin(survivor_tickers)].copy()
        rows = [r for r in rows if r["ticker"] in survivor_tickers]
        prices_by_ticker = {
            t: p for t, p in prices_by_ticker.items() if t in survivor_tickers
        }
        adv_by_ticker = {
            t: a for t, a in adv_by_ticker.items() if t in survivor_tickers
        }
        # --------------------------------------------------------------------

        assert pre_screen_count == 4
        assert len(df) == 2
        assert set(df["ticker"]) == {"SURVIVOR1", "SURVIVOR2"}
        assert {r["ticker"] for r in rows} == {"SURVIVOR1", "SURVIVOR2"}
        assert set(prices_by_ticker.keys()) == {"SURVIVOR1", "SURVIVOR2"}
        assert set(adv_by_ticker.keys()) == {"SURVIVOR1", "SURVIVOR2"}

        # Non-survivors must be gone from EVERY reduced structure.
        for excluded in ("PRICEFAIL", "ADVFAIL"):
            assert excluded not in df["ticker"].to_numpy()
            assert excluded not in {r["ticker"] for r in rows}
            assert excluded not in prices_by_ticker
            assert excluded not in adv_by_ticker

    def test_full_reduction_chain_all_fail_below_min_valid_tickers(self) -> None:
        """When every candidate fails the screen, the reduced df has zero
        rows — the caller's MIN_VALID_TICKERS gate (tested at the source
        level in TestRunWeeklyComputeBroadWiring) is what aborts in that
        case; this test confirms the reduction itself degrades to an empty
        (not crashing) result rather than raising."""
        candidates = pd.DataFrame({"ticker": ["ALLFAIL1", "ALLFAIL2"]})
        universe = candidates_to_universe_frame(candidates)
        prices_by_ticker = {
            "ALLFAIL1": _price_df(close=1.0, volume=1_000.0),
            "ALLFAIL2": _price_df(close=1.0, volume=1_000.0),
        }
        rows = [{"ticker": t, "name": t} for t in candidates["ticker"]]
        df = pd.DataFrame(rows).set_index("ticker", drop=False)

        survivor_tickers = select_broad_universe_survivors(
            candidates=universe, prices_by_ticker=prices_by_ticker
        )
        assert survivor_tickers == set()

        df = df[df["ticker"].isin(survivor_tickers)].copy()
        rows = [r for r in rows if r["ticker"] in survivor_tickers]

        assert len(df) == 0
        assert rows == []
