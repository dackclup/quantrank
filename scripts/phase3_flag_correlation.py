"""Epic #150 Phase 3 — pairwise flag correlation on production output.

Reads `frontend/public/data/stocks/*.json` and emits:

- Per-flag firing rate (sorted descending)
- Top-N correlated pairs (φ > 0.3) — redundancy candidates
- Top-N orthogonal pairs (|φ| < 0.05 with both base-rates > 5%) —
  diversity-confirmed pairs
- Dead flags (firing-rate = 0) — prune-or-recal candidates
- Heatmap PNG of pairwise φ across the firing-rate ≥ 1% flag subset

The φ-coefficient (a.k.a. Matthews correlation coefficient for the
2×2 case) is the boolean analog of Pearson correlation; it's defined
on {0, 1} variables as the same formula and reads the same way (-1 to
+1, with 0 = independent).

One-shot analysis — not part of the weekly cron. Re-run after the
quarterly cohort audit (next: 2026-08-19) or whenever the defense
layer changes materially.

Usage:

    python scripts/phase3_flag_correlation.py \\
        --data-dir frontend/public/data/stocks \\
        --output-dir docs/phase3-correlation

Outputs `correlation_matrix.csv`, `firing_rates.csv`, `summary.md`,
and `heatmap.png` under ``--output-dir``.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

# Minimum firing rate to include a flag in the pairwise correlation
# heatmap. Sub-1% flags carry too little variance to produce a stable
# φ — show them in the dead-or-rare table instead.
HEATMAP_MIN_FIRING_RATE: float = 0.01

# Redundancy threshold — pairs with |φ| above this are flagged for
# Phase 2.2 / 2.5 weight-recalibration review. 0.3 captures "moderate"
# correlation per Cohen 1988 §"Statistical Power Analysis" small-
# medium-large rules of thumb, adapted to boolean variables.
REDUNDANCY_PHI_THRESHOLD: float = 0.30

# Diversity-confirmed threshold — pairs with |φ| below this AND both
# base-rates above 5% are the orthogonal-by-design pairs that justify
# additive weighting in `manipulation_index.py`.
ORTHOGONALITY_PHI_THRESHOLD: float = 0.05
ORTHOGONALITY_MIN_BASE_RATE: float = 0.05


def load_flag_matrix(data_dir: Path) -> pd.DataFrame:
    """Read every per-stock JSON and return a (ticker × flag) boolean
    DataFrame. Each column is True if the flag fired for that ticker.

    Sources merged (de-duped on flag name):
    - ``risk_flags`` list (active vetoes + numerical guards)
    - ``valuation_warnings`` list (annotates + method-applicability + informational)
    - ``tier2_events`` dict (boolean keys only)
    """
    rows: list[tuple[str, set[str]]] = []
    for path in sorted(glob.glob(str(data_dir / "*.json"))):
        with open(path) as fh:
            d = json.load(fh)
        ticker = d["ticker"]
        flags: set[str] = set()
        flags.update(d.get("risk_flags") or [])
        flags.update(d.get("valuation_warnings") or [])
        tier2 = d.get("tier2_events") or {}
        for k, v in tier2.items():
            if isinstance(v, bool) and v:
                flags.add(k)
        rows.append((ticker, flags))

    all_flags = sorted({f for _, flags in rows for f in flags})
    matrix = pd.DataFrame(
        {
            "ticker": [t for t, _ in rows],
            **{f: [f in flags for _, flags in rows] for f in all_flags},
        }
    ).set_index("ticker")
    return matrix


def firing_rates(matrix: pd.DataFrame) -> pd.Series:
    return matrix.mean().sort_values(ascending=False)


def phi_coefficient(x: pd.Series, y: pd.Series) -> float:
    """φ-coefficient for two boolean Series of equal length.

    φ = (n11·n00 − n10·n01) / sqrt((n11+n10)(n01+n00)(n11+n01)(n10+n00))

    Returns 0.0 when any marginal is zero (one variable is constant).
    """
    n11 = int(((x) & (y)).sum())
    n10 = int(((x) & (~y)).sum())
    n01 = int(((~x) & (y)).sum())
    n00 = int(((~x) & (~y)).sum())
    num = n11 * n00 - n10 * n01
    denom_sq = (n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00)
    if denom_sq <= 0:
        return 0.0
    return num / math.sqrt(denom_sq)


def correlation_matrix(matrix: pd.DataFrame) -> pd.DataFrame:
    cols = list(matrix.columns)
    out = np.zeros((len(cols), len(cols)), dtype=float)
    for i, a in enumerate(cols):
        for j, b in enumerate(cols):
            if i == j:
                out[i, j] = 1.0
            elif i < j:
                v = phi_coefficient(matrix[a], matrix[b])
                out[i, j] = v
                out[j, i] = v
    return pd.DataFrame(out, index=cols, columns=cols)


def top_correlated_pairs(
    corr: pd.DataFrame,
    rates: pd.Series,
    threshold: float = REDUNDANCY_PHI_THRESHOLD,
) -> pd.DataFrame:
    cols = list(corr.columns)
    rows = []
    for i, a in enumerate(cols):
        for j, b in enumerate(cols):
            if i >= j:
                continue
            phi = corr.iat[i, j]
            if abs(phi) >= threshold:
                rows.append((a, b, phi, rates[a], rates[b]))
    df = pd.DataFrame(rows, columns=["flag_a", "flag_b", "phi", "rate_a", "rate_b"])
    return df.sort_values("phi", key=lambda s: s.abs(), ascending=False).reset_index(drop=True)


def orthogonal_pairs(
    corr: pd.DataFrame,
    rates: pd.Series,
    phi_threshold: float = ORTHOGONALITY_PHI_THRESHOLD,
    min_rate: float = ORTHOGONALITY_MIN_BASE_RATE,
) -> pd.DataFrame:
    cols = list(corr.columns)
    rows = []
    for i, a in enumerate(cols):
        for j, b in enumerate(cols):
            if i >= j:
                continue
            phi = corr.iat[i, j]
            if abs(phi) <= phi_threshold and rates[a] >= min_rate and rates[b] >= min_rate:
                rows.append((a, b, phi, rates[a], rates[b]))
    df = pd.DataFrame(rows, columns=["flag_a", "flag_b", "phi", "rate_a", "rate_b"])
    return df.sort_values("phi", key=lambda s: s.abs()).reset_index(drop=True)


def render_heatmap(corr: pd.DataFrame, rates: pd.Series, out_path: Path) -> bool:
    """Render the heatmap PNG. Returns False (and skips) if matplotlib
    isn't installed — this script is one-shot analysis, not a compute
    dependency, so matplotlib stays out of ``pyproject.toml``.
    """
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print(f"matplotlib not installed; skipping heatmap → {out_path}")
        return False

    active = sorted(rates[rates >= HEATMAP_MIN_FIRING_RATE].index)
    sub = corr.loc[active, active]
    fig, ax = plt.subplots(figsize=(max(8, len(active) * 0.5), max(8, len(active) * 0.5)))
    im = ax.imshow(sub.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(range(len(active)))
    ax.set_yticks(range(len(active)))
    ax.set_xticklabels(active, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels(active, fontsize=8)
    for i in range(len(active)):
        for j in range(len(active)):
            v = sub.values[i, j]
            if abs(v) >= 0.2 and i != j:
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=6, color="black")
    ax.set_title(f"Phase 3 flag-correlation φ-matrix ({len(active)} flags, firing-rate ≥ 1%)")
    fig.colorbar(im, ax=ax, shrink=0.6, label="φ-coefficient")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return True


def write_summary(
    out_path: Path,
    matrix: pd.DataFrame,
    rates: pd.Series,
    correlated: pd.DataFrame,
    orthogonal: pd.DataFrame,
) -> None:
    n_universe = len(matrix)
    n_flags = len(rates)
    dead = rates[rates == 0.0]
    rare = rates[(rates > 0.0) & (rates < HEATMAP_MIN_FIRING_RATE)]

    lines: list[str] = []
    lines.append("# Phase 3 flag-correlation analysis")
    lines.append("")
    lines.append(f"- Universe: **{n_universe} stocks**")
    lines.append(f"- Active flags observed: **{n_flags}**")
    lines.append(
        f"- Dead flags (firing-rate = 0): **{len(dead)}** "
        f"— prune-or-recal candidates"
    )
    lines.append(
        f"- Rare flags (0 < firing-rate < 1%): **{len(rare)}** "
        f"— excluded from heatmap (low variance)"
    )
    lines.append("")
    lines.append("## Firing rates")
    lines.append("")
    lines.append("| Flag | Fired | Base rate |")
    lines.append("|---|---:|---:|")
    for flag, rate in rates.items():
        lines.append(f"| `{flag}` | {int(rate * n_universe)} | {rate * 100:.1f}% |")
    lines.append("")
    if len(dead) > 0:
        lines.append("### Dead flags")
        lines.append("")
        for flag in dead.index:
            lines.append(f"- `{flag}`")
        lines.append("")
    lines.append(
        f"## Redundancy candidates (|φ| ≥ {REDUNDANCY_PHI_THRESHOLD})"
    )
    lines.append("")
    if len(correlated) == 0:
        lines.append("_No pairs above threshold._")
    else:
        lines.append("| Flag A | Flag B | φ | Rate A | Rate B |")
        lines.append("|---|---|---:|---:|---:|")
        for _, row in correlated.iterrows():
            lines.append(
                f"| `{row.flag_a}` | `{row.flag_b}` | {row.phi:+.3f} "
                f"| {row.rate_a * 100:.1f}% | {row.rate_b * 100:.1f}% |"
            )
    lines.append("")
    lines.append(
        f"## Diversity-confirmed pairs (|φ| ≤ {ORTHOGONALITY_PHI_THRESHOLD}, "
        f"both rates ≥ {ORTHOGONALITY_MIN_BASE_RATE * 100:.0f}%)"
    )
    lines.append("")
    if len(orthogonal) == 0:
        lines.append("_No pairs meet both thresholds._")
    else:
        lines.append("| Flag A | Flag B | φ | Rate A | Rate B |")
        lines.append("|---|---|---:|---:|---:|")
        for _, row in orthogonal.iterrows():
            lines.append(
                f"| `{row.flag_a}` | `{row.flag_b}` | {row.phi:+.3f} "
                f"| {row.rate_a * 100:.1f}% | {row.rate_b * 100:.1f}% |"
            )
    lines.append("")
    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "- φ-coefficient (Matthews correlation coefficient for the 2×2 case) "
        "is the boolean analog of Pearson; defined on {0,1} variables, "
        "reads -1 to +1, 0 = independent."
    )
    lines.append(
        "- Sources merged into the flag matrix: `risk_flags` (active vetoes "
        "+ numerical guards), `valuation_warnings` (annotates + method-"
        "applicability + informational), `tier2_events` (boolean keys)."
    )
    lines.append(
        f"- Heatmap subset: flags with firing-rate ≥ {HEATMAP_MIN_FIRING_RATE * 100:.0f}% "
        "(sub-1% flags carry too little variance for stable φ)."
    )
    lines.append(
        "- Reproduce: `python scripts/phase3_flag_correlation.py "
        "--data-dir frontend/public/data/stocks --output-dir <dest>`."
    )

    out_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("frontend/public/data/stocks"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/phase3-correlation"),
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    matrix = load_flag_matrix(args.data_dir)
    rates = firing_rates(matrix)
    corr = correlation_matrix(matrix)
    correlated = top_correlated_pairs(corr, rates)
    orthogonal = orthogonal_pairs(corr, rates)

    matrix.to_csv(args.output_dir / "flag_matrix.csv")
    rates.to_csv(args.output_dir / "firing_rates.csv", header=["firing_rate"])
    corr.to_csv(args.output_dir / "correlation_matrix.csv")
    correlated.to_csv(args.output_dir / "redundancy_candidates.csv", index=False)
    orthogonal.to_csv(args.output_dir / "orthogonal_pairs.csv", index=False)
    render_heatmap(corr, rates, args.output_dir / "heatmap.png")
    write_summary(
        args.output_dir / "summary.md",
        matrix,
        rates,
        correlated,
        orthogonal,
    )
    print(f"Wrote {args.output_dir}/ outputs across {len(matrix)} stocks × {len(rates)} flags.")


if __name__ == "__main__":
    main()
