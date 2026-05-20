#!/usr/bin/env python3
"""Section A-J production verification scan for QuantRank compute output.

Invoked by the `verify-production-output` skill. Reads
`frontend/public/data/{metadata.json, rankings.json, stocks/*.json}` and
emits a structured report covering schema, Tier-2 contract, fair-price
coverage, Top-5 rotation, risk-flag totals, Tier-2 dict shape,
fundamentals resilience, universe-size consistency, and the annotate-
flag inventory used by quarterly audit automation.

Section I is reserved for the Playwright UI spot-check (CLAUDE.md
post-`workflow_dispatch` requirement); it lives outside this script
because it drives a browser, not stdout.

Pure stdlib. Run from the repo root:

    python .claude/skills/verify-production-output/helper.py

Optional flags:
    --baseline-commit=<sha>   Compare against a prior run's metadata
                              (reads via `git show <sha>:path` — must be
                              a sha reachable in the local repo)
    --strict                  Exit 1 on any soft warning
    --seed=<int>              Section F random seed (default 42)
    --data-dir=<path>         Override the data root (default
                              frontend/public/data)
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import random
import subprocess
import sys

TIER2_REQUIRED_KEYS = {
    "going_concern_disclosure",
    "non_reliance_filing",
    "auditor_change",
    "latest_8k_filing_date",
    "latest_8k_filing_url",
}


# ---------------------------------------------------------------------------
# Severity markers
# ---------------------------------------------------------------------------

OK = "\033[32m✓\033[0m"
WARN = "\033[33m⚠\033[0m"
FAIL = "\033[31m✗\033[0m"


def _emit(marker: str, label: str, detail: str = "") -> None:
    if detail:
        print(f"  {marker} {label}: {detail}")
    else:
        print(f"  {marker} {label}")


def _section(letter: str, title: str) -> None:
    print(f"\n=== Section {letter} — {title} ===")


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def _load_metadata(data_dir: pathlib.Path) -> dict:
    return json.loads((data_dir / "metadata.json").read_text())


def _load_rankings(data_dir: pathlib.Path) -> list:
    payload = json.loads((data_dir / "rankings.json").read_text())
    if isinstance(payload, list):
        return payload
    # Some schemas wrap the list in {"stocks": [...]}.
    return payload.get("stocks") or []


def _load_stocks(data_dir: pathlib.Path) -> list[dict]:
    out = []
    for path in sorted((data_dir / "stocks").glob("*.json")):
        out.append(json.loads(path.read_text()))
    return out


def _load_baseline_metadata(sha: str, data_dir: pathlib.Path) -> dict | None:
    rel = data_dir.relative_to(pathlib.Path.cwd()) / "metadata.json"
    try:
        result = subprocess.run(
            ["git", "show", f"{sha}:{rel.as_posix()}"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# Section reporters — each returns (warnings, failures) counts
# ---------------------------------------------------------------------------


def section_a_schema(metadata: dict, baseline: dict | None) -> tuple[int, int]:
    _section("A", "Schema + metadata")
    warnings = failures = 0

    version = metadata.get("version")
    commit = (metadata.get("git_commit") or "")[:7]
    universe_size = metadata.get("universe_size")
    _emit(OK, "version", version or "(missing)")
    _emit(OK, "git_commit", commit or "(missing)")
    _emit(OK, "universe_size", str(universe_size))

    # Tier-2 coverage
    t2_cov = metadata.get("tier2_coverage_pct")
    if t2_cov is None:
        _emit(WARN, "tier2_coverage_pct", "missing")
        warnings += 1
    elif t2_cov < 95:
        _emit(WARN, "tier2_coverage_pct", f"{t2_cov}% (target ≥95)")
        warnings += 1
    else:
        _emit(OK, "tier2_coverage_pct", f"{t2_cov}%")

    # Fundamentals coverage + latency
    f_cov = metadata.get("fundamentals_coverage_pct")
    f_p50 = metadata.get("fundamentals_latency_p50_seconds")
    f_p95 = metadata.get("fundamentals_latency_p95_seconds")
    if f_cov is not None:
        if f_cov < 80:
            _emit(FAIL, "fundamentals_coverage_pct", f"{f_cov}% — heavily throttled")
            failures += 1
        elif f_cov < 95:
            _emit(WARN, "fundamentals_coverage_pct", f"{f_cov}% (target ≥95)")
            warnings += 1
        else:
            _emit(OK, "fundamentals_coverage_pct", f"{f_cov}%")
    if f_p95 is not None and f_p95 > 15:
        _emit(WARN, "fundamentals_latency_p95_seconds", f"{f_p95}s (target <15)")
        warnings += 1
    elif f_p95 is not None:
        _emit(OK, "fundamentals_latency_p95_seconds", f"{f_p95}s")
    if f_p50 is not None:
        _emit(OK, "fundamentals_latency_p50_seconds", f"{f_p50}s")

    if baseline:
        b_version = baseline.get("version")
        if b_version and b_version != version:
            _emit(OK, "vs baseline", f"schema bumped {b_version} → {version}")

    return warnings, failures


def section_b_tier2(stocks: list[dict], metadata: dict) -> tuple[int, int]:
    """Tier-2 fired-flag inventory — post-PR-#79 (Phase 4g, 2026-05-15).

    `non_reliance_filing` (Schroeder 2024) and `auditor_change`
    (Cohen-Malloy-Nguyen 2020) are now ACTIVE — non-zero fires in the
    normal cohort band are EXPECTED, not bugs. The regression guard
    inverts: if the Tier-2 feature flag is OFF at compute time (proxied
    by `metadata.tier2_coverage_pct` ≤ 5%), then any fire is the bug.

    Soft bands per academic priors:
      going_concern_disclosure  — Mayew 2015: 1-3% expected; warn > 5%
      non_reliance_filing        — Schroeder 2024: rare Item 4.02s; warn > 2%
      auditor_change             — Cohen-Malloy-Nguyen 2020: 1-5%; warn > 5%
    """
    _section("B", "Tier-2 fired-flag inventory")
    warnings = failures = 0

    gc, nr, ac = [], [], []
    for s in stocks:
        t2 = s.get("tier2_events")
        if not isinstance(t2, dict):
            continue
        if t2.get("going_concern_disclosure"):
            gc.append(s.get("ticker"))
        if t2.get("non_reliance_filing"):
            nr.append(s.get("ticker"))
        if t2.get("auditor_change"):
            ac.append(s.get("ticker"))

    n = max(len(stocks), 1)
    pct_gc = 100 * len(gc) / n
    pct_nr = 100 * len(nr) / n
    pct_ac = 100 * len(ac) / n

    # Read the explicit compute-time flag emitted since 0.9.3-phase4h.3
    # (epic #150 Phase 1.6, issue #155). On legacy snapshots written before
    # that schema bump the key is absent — fall back to the prior coverage-
    # based heuristic (`tier2_coverage_pct > 5%`) so the verifier can still
    # run against an older `metadata.json`.
    t2_cov = metadata.get("tier2_coverage_pct") or 0
    if "tier2_enabled" in metadata:
        tier2_enabled = bool(metadata["tier2_enabled"])
        disabled_reason = "tier2_enabled=False"
    else:
        tier2_enabled = t2_cov > 5
        disabled_reason = f"tier2_coverage_pct={t2_cov}%"

    # going_concern: Mayew 2015 expects 1-3% FP rate
    if pct_gc > 5:
        _emit(WARN, "going_concern_disclosure",
              f"{len(gc)} ({pct_gc:.1f}%) — over 5% FP-rate target, see issue #16")
        warnings += 1
    else:
        _emit(OK, "going_concern_disclosure", f"{len(gc)} ({pct_gc:.1f}%)")

    # non_reliance_filing — Schroeder 2024 (Item 4.02, 365d lookback).
    # Item 4.02 filings are rare; expect 0-2% of universe.
    if not tier2_enabled:
        if nr:
            _emit(FAIL, "non_reliance_filing",
                  f"{len(nr)} fired but Tier-2 appears disabled ({disabled_reason}) — flag broken?")
            failures += 1
        else:
            _emit(OK, "non_reliance_filing", "0 (Tier-2 disabled — contract holds)")
    elif pct_nr > 2:
        _emit(WARN, "non_reliance_filing",
              f"{len(nr)} ({pct_nr:.1f}%) — over 2% expected band (Schroeder 2024)")
        warnings += 1
    else:
        _emit(OK, "non_reliance_filing", f"{len(nr)} ({pct_nr:.1f}%)")

    # auditor_change — Cohen-Malloy-Nguyen 2020 (Item 4.01, 730d lookback).
    # Annotate-only; expected 1-5% of universe in the lookback window.
    if not tier2_enabled:
        if ac:
            _emit(FAIL, "auditor_change",
                  f"{len(ac)} fired but Tier-2 appears disabled ({disabled_reason}) — flag broken?")
            failures += 1
        else:
            _emit(OK, "auditor_change", "0 (Tier-2 disabled — contract holds)")
    elif pct_ac > 5:
        _emit(WARN, "auditor_change",
              f"{len(ac)} ({pct_ac:.1f}%) — over 5% expected band (Cohen-Malloy-Nguyen 2020)")
        warnings += 1
    else:
        _emit(OK, "auditor_change", f"{len(ac)} ({pct_ac:.1f}%)")

    return warnings, failures


def section_c_coverage(stocks: list[dict]) -> tuple[int, int]:
    _section("C", "Fair-price coverage + sanity guard")
    warnings = failures = 0

    fp_count = 0
    dq_tickers = []
    for s in stocks:
        fp = s.get("fair_price")
        if isinstance(fp, dict) and fp.get("median") is not None:
            fp_count += 1
        if "data_quality_input_corruption" in (s.get("valuation_warnings") or []):
            dq_tickers.append(s.get("ticker"))

    pct_fp = 100 * fp_count / max(len(stocks), 1)
    if pct_fp < 80:
        _emit(FAIL, "fair_price coverage", f"{fp_count}/{len(stocks)} ({pct_fp:.1f}%)")
        failures += 1
    elif pct_fp < 95:
        _emit(WARN, "fair_price coverage", f"{fp_count}/{len(stocks)} ({pct_fp:.1f}%)")
        warnings += 1
    else:
        _emit(OK, "fair_price coverage", f"{fp_count}/{len(stocks)} ({pct_fp:.1f}%)")

    _emit(OK, "data_quality_input_corruption",
          f"{len(dq_tickers)} tickers: {sorted(dq_tickers)}")
    return warnings, failures


def section_d_top5(stocks: list[dict]) -> tuple[int, int]:
    _section("D", "Top-5 composition + rotation invariants")
    warnings = failures = 0

    by_rank = sorted([s for s in stocks if isinstance(s.get("rank"), int)],
                     key=lambda s: s["rank"])

    raw_top5 = by_rank[:5]
    entered = [s for s in stocks if s.get("entered_top5")]
    exited = [s for s in stocks if s.get("exited_top5")]

    print("  Raw top-5 (by composite):")
    for s in raw_top5:
        rf = s.get("risk_flags") or []
        vw = s.get("valuation_warnings") or []
        _emit(OK, f"#{s.get('rank')} {s.get('ticker'):6s}",
              f"composite={s.get('composite_score'):.2f} | risk={rf} | warn={vw}")

    print(f"  entered_top5: {sorted((s['rank'], s['ticker']) for s in entered)}")
    print(f"  exited_top5: {sorted(s['ticker'] for s in exited)}")

    # Rotation invariant: entered count == exited count (one promoted per
    # suppressed top-ranker). Typical: 0-2 each on a healthy run.
    if len(entered) != len(exited):
        _emit(FAIL, "rotation invariant",
              f"entered={len(entered)} != exited={len(exited)}")
        failures += 1
    else:
        _emit(OK, "rotation invariant",
              f"entered={len(entered)} == exited={len(exited)}")
    return warnings, failures


def section_e_risk_flags(stocks: list[dict]) -> tuple[int, int]:
    _section("E", "Risk-flag totals")
    counter: collections.Counter = collections.Counter()
    for s in stocks:
        for flag in s.get("risk_flags") or []:
            counter[flag] += 1
    for flag, n in sorted(counter.items(), key=lambda kv: -kv[1]):
        _emit(OK, flag, str(n))
    return 0, 0


def section_f_tier2_spotcheck(stocks: list[dict], seed: int) -> tuple[int, int]:
    _section("F", "Tier-2 events spot-check (5 random)")
    rnd = random.Random(seed)
    sample = rnd.sample(stocks, min(5, len(stocks)))
    failures = 0
    for s in sample:
        t2 = s.get("tier2_events")
        if not isinstance(t2, dict):
            _emit(FAIL, s.get("ticker", "?"), "tier2_events missing or non-dict")
            failures += 1
            continue
        missing = TIER2_REQUIRED_KEYS - set(t2.keys())
        if missing:
            _emit(FAIL, s.get("ticker", "?"), f"missing keys: {sorted(missing)}")
            failures += 1
        else:
            _emit(OK, s.get("ticker", "?"), "5-key dict shape ✓")
    return 0, failures


def section_g_fundamentals(metadata: dict) -> tuple[int, int]:
    _section("G", "Fundamentals resilience")
    warnings = 0
    cov = metadata.get("fundamentals_coverage_pct")
    if cov is None:
        _emit(WARN, "coverage", "missing from metadata")
        return 1, 0
    if cov >= 95:
        _emit(OK, "interpretation", f"healthy ({cov}%)")
    elif cov >= 80:
        _emit(WARN, "interpretation", f"throttled but graceful ({cov}%)")
        warnings += 1
    else:
        _emit(FAIL, "interpretation", f"heavily throttled ({cov}%)")
    return warnings, 0


def section_h_universe_consistency(
    metadata: dict, rankings: list, stocks: list[dict]
) -> tuple[int, int]:
    _section("H", "Universe-size consistency")
    meta_n = metadata.get("universe_size")
    rk_n = len(rankings)
    files_n = len(stocks)
    if meta_n == rk_n == files_n:
        _emit(OK, "consistent", f"all three = {meta_n}")
        return 0, 0
    _emit(FAIL, "mismatch",
          f"metadata={meta_n} rankings={rk_n} stock_files={files_n}")
    return 0, 1


def section_j_annotate_audit(stocks: list[dict]) -> tuple[int, int]:
    """Auto-tabulate the annotate-flag surface for quarterly audit automation.

    The Q2 2026-05 quarterly audit (issue #130 comment) discovered 10
    undocumented flags by manual inventory walk. This section automates
    that walk: it counts every entry in `valuation_warnings` (list[str])
    plus every boolean-True key in `tier2_events` across the universe,
    so the next quarterly review reads the table off the helper instead
    of grepping source.

    Complements Section E (risk_flags counter on the veto surface) by
    covering the annotate surface. Flags with dual nature (e.g.,
    `non_reliance_filing` is both an active veto AND a tier2 boolean)
    appear in both Section E and Section J — that is intentional, the
    annotate surface is the full set, not the veto-complement.
    """
    _section("J", "Annotate-flag inventory (quarterly audit auto-tabulator)")
    vw_counter: collections.Counter = collections.Counter()
    t2_counter: collections.Counter = collections.Counter()
    n = max(len(stocks), 1)

    for s in stocks:
        for flag in (s.get("valuation_warnings") or []):
            vw_counter[flag] += 1
        t2 = s.get("tier2_events")
        if isinstance(t2, dict):
            for key, val in t2.items():
                # Only boolean-True entries count as fires. The 5-key
                # tier2 contract also stores `latest_8k_filing_date` +
                # `_url` metadata, which aren't fire-state.
                if isinstance(val, bool) and val:
                    t2_counter[key] += 1

    print("  valuation_warnings (annotate surface):")
    if not vw_counter:
        _emit(OK, "(none)", "no annotates fired on the universe")
    else:
        for flag, count in sorted(vw_counter.items(), key=lambda kv: -kv[1]):
            pct = 100 * count / n
            _emit(OK, flag, f"{count} ({pct:.1f}%)")

    print("  tier2_events (8-K Tier-2 annotate surface):")
    if not t2_counter:
        _emit(OK, "(none)", "no Tier-2 8-K flags fired")
    else:
        for flag, count in sorted(t2_counter.items(), key=lambda kv: -kv[1]):
            pct = 100 * count / n
            _emit(OK, flag, f"{count} ({pct:.1f}%)")

    return 0, 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="QuantRank Section A-H verification")
    p.add_argument("--data-dir", default="frontend/public/data",
                   help="Path to compute output root")
    p.add_argument("--baseline-commit", default=None,
                   help="git sha of a prior metadata.json to diff against")
    p.add_argument("--strict", action="store_true",
                   help="Exit 1 on any soft warning")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args(argv)

    data_dir = pathlib.Path(args.data_dir).resolve()
    if not data_dir.exists():
        print(f"data dir not found: {data_dir}", file=sys.stderr)
        return 2

    metadata = _load_metadata(data_dir)
    rankings = _load_rankings(data_dir)
    stocks = _load_stocks(data_dir)
    baseline = (_load_baseline_metadata(args.baseline_commit, data_dir)
                if args.baseline_commit else None)

    total_warnings = total_failures = 0
    for fn in (
        lambda: section_a_schema(metadata, baseline),
        lambda: section_b_tier2(stocks, metadata),
        lambda: section_c_coverage(stocks),
        lambda: section_d_top5(stocks),
        lambda: section_e_risk_flags(stocks),
        lambda: section_f_tier2_spotcheck(stocks, args.seed),
        lambda: section_g_fundamentals(metadata),
        lambda: section_h_universe_consistency(metadata, rankings, stocks),
        lambda: section_j_annotate_audit(stocks),
    ):
        w, f = fn()
        total_warnings += w
        total_failures += f

    print(f"\n=== Summary: {total_failures} failures, {total_warnings} warnings ===")
    if total_failures:
        return 1
    if args.strict and total_warnings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
