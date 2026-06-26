"""Offline tests for tools/check_agent_hook_consistency.py (error-reduction Layer 1).

Pure-Python, no network. Locks the deterministic agent/hook/flow consistency
guard: the live repo must be internally consistent AND every doc anchor must
match ground truth, the anchor-comparison must actually fire on a mismatch,
and every agent file must carry valid model+effort frontmatter.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from tools.check_agent_hook_consistency import (
    ANCHORS,
    REPO_ROOT,
    GroundTruth,
    _parse_frontmatter,
    check_anchors,
    compute_ground_truth,
    run,
)


def test_live_repo_is_consistent() -> None:
    """The committed repo must pass the guard (no internal errors, no drift)."""
    truth, problems = run()
    assert problems == [], f"consistency drift in committed repo: {problems}"
    assert truth.n_agents > 0


def test_ground_truth_internal_invariants() -> None:
    truth, errors = compute_ground_truth()
    assert errors == [], errors
    assert truth.n_opus + truth.n_sonnet == truth.n_agents
    assert truth.n_effort_max + truth.n_effort_high == truth.n_agents
    assert truth.tier_sum == truth.n_agents
    assert truth.n_hooks >= 1
    assert truth.n_flows >= 1


def test_anchors_fire_on_mismatch() -> None:
    """A wrong ground-truth value MUST produce anchor violations.

    Proves the comparison logic actually fires (guards against a guard that
    silently passes everything).
    """
    truth, _ = compute_ground_truth()
    bogus = replace(
        truth,
        n_agents=truth.n_agents + 100,
        n_opus=truth.n_opus + 100,
        n_hooks=truth.n_hooks + 100,
        n_flows=truth.n_flows + 100,
        n_effort_max=truth.n_effort_max + 100,
    )
    violations = check_anchors(bogus)
    assert violations, "anchors did not fire on an obviously-wrong ground truth"


def test_anchors_match_real_ground_truth() -> None:
    """Against the REAL ground truth, every anchor must agree (no violations)."""
    truth, _ = compute_ground_truth()
    assert check_anchors(truth) == []


def test_every_agent_has_valid_frontmatter() -> None:
    """Each agent file declares model ∈ {opus,sonnet} and effort ∈ {max,high}.

    This is the regression guard for the malformed-frontmatter error class —
    compute_ground_truth() records such files as internal errors.
    """
    _, errors = compute_ground_truth()
    frontmatter_errors = [e for e in errors if "frontmatter malformed" in e]
    assert frontmatter_errors == [], frontmatter_errors


def test_parse_frontmatter_basic() -> None:
    fm = _parse_frontmatter(
        "---\nname: foo\nmodel: opus\neffort: max\n---\nbody\n"
    )
    assert fm["name"] == "foo"
    assert fm["model"] == "opus"
    assert fm["effort"] == "max"


def test_parse_frontmatter_no_block() -> None:
    assert _parse_frontmatter("no frontmatter here") == {}


def test_anchors_reference_valid_truth_keys() -> None:
    """Every anchor's truth_key must be a real GroundTruth field."""
    valid = set(GroundTruth.__dataclass_fields__)
    for anchor in ANCHORS:
        assert anchor.truth_key in valid, anchor


def test_no_dead_anchors() -> None:
    """Every anchor regex must match ≥1 line in its target file.

    A dead anchor (one whose pattern never matches — e.g. broken by a `**`
    bold marker, or aimed at a spelled-out number) silently guards nothing.
    This is the regression guard for the two dead anchors quantrank-reviewer
    caught in PR #625 (Error→regression ratchet).
    """
    dead: list[str] = []
    for anchor in ANCHORS:
        path = Path(REPO_ROOT) / anchor.file
        if not path.exists():
            continue
        rx = re.compile(anchor.pattern)
        if not any(rx.search(line) for line in path.read_text().splitlines()):
            dead.append(f"{anchor.label} ({anchor.file}): pattern {anchor.pattern!r} matched nothing")
    assert not dead, "dead anchors (guard nothing):\n" + "\n".join(dead)
