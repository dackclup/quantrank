"""Pre-merge production simulation — diff PR-branch compute output vs main.

Epic #125 Item 3 PR 2. PR 1 (#140) shipped the workflow skeleton that
runs ``python -m compute.main`` on a PR branch and posts a summary
sticky comment. This tool produces the diff section appended to that
comment:

- Summary deltas: universe size, schema version, baseline freshness
- Top-10 movers by ``|Δcomposite_score|`` desc
- Tickers added (in PR, not main) + tickers removed (in main, not PR)

Baseline = main's committed ``frontend/public/data/`` (not a re-run on
main). The diff answers "did this PR change composite scores relative
to what production currently shows users?" — that question's anchor is
the last-committed main output, not a counterfactual fresh main run.

USAGE
=====

    python tools/pre_merge_diff.py \\
      --pr-rankings frontend/public/data/rankings.json \\
      --pr-metadata frontend/public/data/metadata.json \\
      --main-rankings /tmp/main-data/rankings.json \\
      --main-metadata /tmp/main-data/metadata.json \\
      --output diff_output.md

Always exits 0 — the diff is best-effort observability, not a gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

TOP_N: int = 10
STALE_THRESHOLD_DAYS: int = 7
UNIVERSE_PREVIEW_MAX: int = 10

# Standing reviewer caveat appended under the movers table (issue #669).
# The baseline is the COMMITTED main output (cron warm-cache), while the PR
# branch is a COLD full re-fetch — so the two sides resolve slightly different
# EDGAR/yfinance fundamentals (XBRL/TTM resolution, share counts). On a
# rank-neutral PR the movers are therefore data-PROVENANCE artifacts, NOT a
# code effect. The #631 + #652 pre-merge-prod-sim diffs were both adjudicated
# DATA-DRIFT/provenance on exactly this basis. A mover is only a genuine
# code-induced regression if the PR diff touches the scoring inputs:
# compute/scoring/** · compute/valuation/** · compute/ingest/**. (OSAP does
# NOT feed composite_score — it is observability-only, Rule 18 — so QR_SKIP_OSAP
# in the sim cannot explain composite_score movers.)
PROVENANCE_CAVEAT_LINES: list[str] = [
    "> **Movers are cold-fetch (PR) vs warm-cache (committed main) "
    "fundamentals provenance, not necessarily a code effect.** The baseline is "
    "the cron's last-committed output (warm cache); the PR branch is a cold "
    "full re-fetch, so EDGAR/yfinance resolve slightly different fundamentals "
    "for some tickers — reordering ranks in dense bands. On a rank-neutral PR "
    "this is expected (cf. #631, #652). Treat a mover as a real regression "
    "ONLY if this PR's diff touches `compute/scoring/**`, `compute/valuation/**`, "
    "or `compute/ingest/**` — otherwise cross-check the diff before flagging it. "
    "See #669.",
    "",
]


def load_rankings(path: Path) -> dict[str, dict[str, Any]]:
    """Load rankings.json → ``{ticker: {rank, composite_score}}``."""
    rows = json.loads(path.read_text())
    return {
        row["ticker"]: {
            "rank": row["rank"],
            "composite_score": row["composite_score"],
        }
        for row in rows
    }


def load_metadata(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def baseline_age_days(
    main_metadata: dict[str, Any],
    now: datetime | None = None,
) -> float | None:
    """Days between ``last_update_utc`` and ``now`` (default: current UTC).

    Returns None on missing / unparseable timestamp — caller renders a
    degraded freshness line in that case.
    """
    raw = main_metadata.get("last_update_utc")
    if not raw:
        return None
    try:
        baseline = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if baseline.tzinfo is None:
        baseline = baseline.replace(tzinfo=UTC)
    now = now or datetime.now(UTC)
    return (now - baseline).total_seconds() / 86400.0


def compute_movers(
    pr: dict[str, dict[str, Any]],
    main: dict[str, dict[str, Any]],
    *,
    top_n: int = TOP_N,
) -> list[dict[str, Any]]:
    """Per-ticker score+rank deltas for tickers in BOTH sides.

    Sort by ``|Δcomposite_score|`` desc, then ticker asc as tiebreaker.
    Tickers in only one side are excluded (no baseline to diff against);
    they surface separately as added / removed counts.
    """
    shared = sorted(set(pr) & set(main))
    movers = [
        {
            "ticker": t,
            "pr_rank": pr[t]["rank"],
            "main_rank": main[t]["rank"],
            "delta_rank": main[t]["rank"] - pr[t]["rank"],
            "pr_score": pr[t]["composite_score"],
            "main_score": main[t]["composite_score"],
            "delta_score": pr[t]["composite_score"] - main[t]["composite_score"],
        }
        for t in shared
    ]
    movers.sort(key=lambda m: (-abs(m["delta_score"]), m["ticker"]))
    return movers[:top_n]


def _safe_int_delta(pr: Any, main: Any) -> str:
    if not isinstance(pr, int) or not isinstance(main, int):
        return "?"
    delta = pr - main
    return f"+{delta}" if delta >= 0 else str(delta)


def _signed(value: float, *, decimals: int = 2) -> str:
    return f"+{value:.{decimals}f}" if value >= 0 else f"{value:.{decimals}f}"


def _signed_int(value: int) -> str:
    return f"+{value}" if value >= 0 else str(value)


def render_markdown(
    pr_meta: dict[str, Any],
    main_meta: dict[str, Any],
    movers: list[dict[str, Any]],
    tickers_added: list[str],
    tickers_removed: list[str],
    age_days: float | None,
) -> str:
    lines: list[str] = ["", "## Diff vs main", ""]

    lines.append("| Field | Main | PR | Δ |")
    lines.append("|---|---|---|---|")
    lines.append(
        f"| Universe size | {main_meta.get('universe_size', '?')} | "
        f"{pr_meta.get('universe_size', '?')} | "
        f"{_safe_int_delta(pr_meta.get('universe_size'), main_meta.get('universe_size'))} |"
    )
    same_schema = pr_meta.get("version") == main_meta.get("version")
    lines.append(
        f"| Schema version | `{main_meta.get('version', '?')}` | "
        f"`{pr_meta.get('version', '?')}` | "
        f"{'✓' if same_schema else '⚠️ bumped'} |"
    )
    lines.append("")

    last_update = main_meta.get("last_update_utc", "?")
    if age_days is None:
        freshness = f"`{last_update}` (age unknown)"
    elif age_days > STALE_THRESHOLD_DAYS:
        freshness = (
            f"`{last_update}` ⚠️ **{age_days:.1f} days stale** — "
            "movers may include market drift, not just PR-induced churn"
        )
    else:
        freshness = f"`{last_update}` ({age_days:.1f} days old)"
    lines.append(f"**Main baseline**: {freshness}")
    lines.append("")

    if movers:
        lines.append(
            f"### Top-{len(movers)} movers (sorted by |Δcomposite_score|)"
        )
        lines.append("")
        lines.append(
            "| Ticker | PR rank | main rank | Δrank | "
            "PR score | main score | Δscore |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for m in movers:
            lines.append(
                f"| {m['ticker']} | {m['pr_rank']} | {m['main_rank']} | "
                f"{_signed_int(m['delta_rank'])} | "
                f"{m['pr_score']:.2f} | {m['main_score']:.2f} | "
                f"{_signed(m['delta_score'])} |"
            )
        lines.append("")
        lines.extend(PROVENANCE_CAVEAT_LINES)
    else:
        lines.append(
            "_No shared tickers between PR and main — universe shifted entirely._"
        )
        lines.append("")

    if tickers_added:
        preview = ", ".join(f"`{t}`" for t in tickers_added[:UNIVERSE_PREVIEW_MAX])
        more = (
            ""
            if len(tickers_added) <= UNIVERSE_PREVIEW_MAX
            else f" (+{len(tickers_added) - UNIVERSE_PREVIEW_MAX} more)"
        )
        lines.append(f"**Tickers in PR only ({len(tickers_added)})**: {preview}{more}")
    if tickers_removed:
        preview = ", ".join(f"`{t}`" for t in tickers_removed[:UNIVERSE_PREVIEW_MAX])
        more = (
            ""
            if len(tickers_removed) <= UNIVERSE_PREVIEW_MAX
            else f" (+{len(tickers_removed) - UNIVERSE_PREVIEW_MAX} more)"
        )
        lines.append(f"**Tickers in main only ({len(tickers_removed)})**: {preview}{more}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr-rankings", type=Path, required=True)
    parser.add_argument("--pr-metadata", type=Path, required=True)
    parser.add_argument("--main-rankings", type=Path, required=True)
    parser.add_argument("--main-metadata", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        help="Write markdown to file (default: stdout)",
    )
    args = parser.parse_args(argv)

    pr_ranks = load_rankings(args.pr_rankings)
    pr_meta = load_metadata(args.pr_metadata)
    main_ranks = load_rankings(args.main_rankings)
    main_meta = load_metadata(args.main_metadata)

    tickers_added = sorted(set(pr_ranks) - set(main_ranks))
    tickers_removed = sorted(set(main_ranks) - set(pr_ranks))
    movers = compute_movers(pr_ranks, main_ranks)
    age = baseline_age_days(main_meta)

    markdown = render_markdown(
        pr_meta, main_meta, movers, tickers_added, tickers_removed, age
    )

    if args.output:
        args.output.write_text(markdown)
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
