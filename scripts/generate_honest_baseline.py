"""Generate the honest-baseline report for Phase 4.6.

CLI wrapper that wires the Phase 4.6 modules end-to-end into the
artifact published at ``docs/research/honest-baseline-2026-05-27.md``.

Currently produces a JSON payload (Section 2-5 cells) when run on a
warm-cache machine; the markdown skeleton in the docs file stays
fixed-form and a future PR may add a markdown writer that fills the
TBD cells in-place.

Usage:
    python -m scripts.generate_honest_baseline \\
        --start-date 2024-06-01 \\
        --end-date 2025-06-01 \\
        --horizon-months 6 \\
        --json > report.json

    python -m scripts.generate_honest_baseline \\
        --start-date 2024-06-01 \\
        --end-date 2025-06-01 \\
        --horizon-months 6 \\
        --text

Exit codes:
    0 — report produced (whether numeric cells are populated or not)
    1 — input validation failure (bad date string / non-positive horizon)
    2 — orchestrator returned an empty report (no commits in window OR
        no cached prices anywhere); honest-baseline cells stay TBD —
        useful signal for CI to know the warm-cache run was needed

Per the autonomous mission constraint:
    - No new dependencies (uses argparse + stdlib + the validation modules)
    - No live inference / no SEC fetch — purely a consumer of the
      committed rankings.json + the gitignored price cache
    - Honest disclaimer banner ALWAYS printed before any numbers
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date as _date
from datetime import datetime

from compute.validation.historical_ic import (
    compute_historical_ic_report,
    format_ic_report,
)
from compute.validation.manipulation_distribution import (
    compute_manipulation_distribution_shift,
    format_shift_report,
)

logger = logging.getLogger(__name__)


HONEST_DISCLAIMER_BANNER: str = """\
============================================================
HONEST-BASELINE REPORT — Phase 4.6 closing artifact
============================================================
  All IC / PBO / DSR figures below are NAIVE — no transaction
  costs, no slippage, no sector neutralization. Apply the
  Research Report v1.0 frictions ladder (~60bp round-trip)
  + McLean-Pontiff 2016 32% decay before interpreting any
  number as α-after-costs. Honest net α ceiling: 2-5% per year.
  Composite formula sacred (Rule 16) — never replayed.
  Universe = S&P 500 (502) only.
============================================================
"""


def _parse_date(text: str) -> _date:
    """Parse YYYY-MM-DD; raise argparse-friendly error on bad input."""
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid date {text!r} (expected YYYY-MM-DD): {exc}"
        ) from exc


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate the Phase 4.6 honest-baseline report.",
    )
    parser.add_argument(
        "--start-date",
        type=_parse_date,
        required=True,
        help="ISO date — start of the as-of window (inclusive).",
    )
    parser.add_argument(
        "--end-date",
        type=_parse_date,
        required=True,
        help="ISO date — end of the as-of window (inclusive).",
    )
    parser.add_argument(
        "--horizon-months",
        type=int,
        default=6,
        help="Forward-return horizon in months (default 6).",
    )
    parser.add_argument(
        "--min-tickers",
        type=int,
        default=30,
        help=(
            "Minimum cross-section per anchor for IC (default 30, "
            "matches Grinold-Kahn 2000 §4.2). Lower for sandbox / "
            "synthetic-fixture testing."
        ),
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON payload to stdout (for downstream tooling).",
    )
    output_group.add_argument(
        "--text",
        action="store_true",
        help="Emit human-readable text rendering to stdout (default).",
    )
    parser.add_argument(
        "--no-banner",
        action="store_true",
        help=(
            "Suppress the honest-baseline disclaimer banner (used by "
            "downstream pipelines that aggregate JSON; the banner is "
            "still printed in text mode by default)."
        ),
    )
    return parser


def _report_to_payload(
    start_date: _date,
    end_date: _date,
    horizon_months: int,
    ic_report,
    manip_report,
) -> dict:
    """Build a JSON-serializable payload from the orchestrator outputs.

    Mirrors the cells in docs/research/honest-baseline-2026-05-27.md
    Section 2 (per-pillar IC) + Section 4 (manipulation distribution).
    PBO/DSR Section 3 is left as None — that's an orthogonal call
    that requires factor-return time series, separate from the per-
    pillar IC orchestrator.
    """
    pillar_rows = []
    for pillar, summary in ic_report.summary_by_pillar.items():
        pillar_rows.append({
            "pillar": pillar,
            "n_dates": summary.n_dates,
            "mean_ic": summary.mean,
            "std_ic": summary.std,
            "median_ic": summary.median,
            "min_ic": summary.min_value,
            "max_ic": summary.max_value,
            "ic_ir": summary.ic_ir,
            "hit_rate": summary.hit_rate,
        })

    manip_summary = None
    if manip_report.per_date_summary:
        manip_summary = {
            "first_date_mean": (
                manip_report.per_date_summary[
                    min(manip_report.per_date_summary.keys())
                ].mean
            ),
            "last_date_mean": (
                manip_report.per_date_summary[
                    max(manip_report.per_date_summary.keys())
                ].mean
            ),
            "mean_delta": manip_report.mean_delta,
            "std_delta": manip_report.std_delta,
            "high_count_first": manip_report.high_count_first,
            "high_count_last": manip_report.high_count_last,
            "high_count_delta": manip_report.high_count_delta,
            "n_dates": manip_report.n_dates,
        }

    return {
        "report_version": "0.1.0-skeleton",
        "honest_baseline_disclaimer": (
            "All figures are NAIVE — apply frictions ladder + "
            "McLean-Pontiff 2016 32% decay before interpreting as net α."
        ),
        "window": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "horizon_months": horizon_months,
        },
        "honest_alpha_ceiling": {
            "lower_pct": 2.0,
            "upper_pct": 5.0,
            "source": "Research Report v1.0",
        },
        "pillar_ic": {
            "n_dates_walked": ic_report.n_dates_walked,
            "n_dates_with_ic": ic_report.n_dates_with_ic,
            "rows": pillar_rows,
            "note": ic_report.note,
        },
        "manipulation_distribution": manip_summary,
        "pbo_dsr": {
            "note": (
                "Run separately via factor_passes_gates("
                "universe_provider=members_at, ...) — orthogonal call "
                "with factor-return inputs"
            ),
            "pbo": None,
            "dsr": None,
        },
    }


def _format_text_report(
    start_date: _date,
    end_date: _date,
    horizon_months: int,
    ic_report,
    manip_report,
) -> str:
    """Build the text rendering — honest-baseline header + per-section blocks."""
    blocks = [
        f"Honest baseline window: [{start_date}, {end_date}]",
        f"Forward horizon       : {horizon_months} months",
        "",
        "Section 2 — Per-pillar IC",
        "─" * 60,
        format_ic_report(ic_report),
        "",
        "Section 4 — Manipulation-index distribution shift",
        "─" * 60,
        format_shift_report(manip_report),
        "",
        "Section 3 — PBO / DSR (run separately; not included in this CLI):",
        (
            "  Run compute.validation.pbo_dsr.factor_passes_gates("
            "universe_provider=members_at, ...) with factor returns; "
            "this CLI only covers per-pillar IC + manipulation shift."
        ),
        "",
    ]
    return "\n".join(blocks)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.horizon_months <= 0:
        print(
            f"error: --horizon-months must be positive, got {args.horizon_months}",
            file=sys.stderr,
        )
        return 1
    if args.start_date > args.end_date:
        print(
            f"error: --start-date {args.start_date} must be <= "
            f"--end-date {args.end_date}",
            file=sys.stderr,
        )
        return 1

    if not args.no_banner and not args.json:
        # In text mode, always print the disclaimer banner first.
        print(HONEST_DISCLAIMER_BANNER, file=sys.stderr)

    ic_report = compute_historical_ic_report(
        args.start_date,
        args.end_date,
        horizon_months=args.horizon_months,
        min_tickers=args.min_tickers,
    )
    manip_report = compute_manipulation_distribution_shift(
        start_date=args.start_date,
        end_date=args.end_date,
    )

    if args.json:
        payload = _report_to_payload(
            args.start_date,
            args.end_date,
            args.horizon_months,
            ic_report,
            manip_report,
        )
        if not args.no_banner:
            # Embed the disclaimer inside the JSON for downstream
            # tooling that doesn't read stderr.
            payload["__banner__"] = HONEST_DISCLAIMER_BANNER.strip()
        json.dump(payload, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        print(_format_text_report(
            args.start_date,
            args.end_date,
            args.horizon_months,
            ic_report,
            manip_report,
        ))

    # Exit code 2 → empty report (no warm cache / no commits in window)
    if ic_report.n_dates_with_ic == 0 and not manip_report.per_date_summary:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
