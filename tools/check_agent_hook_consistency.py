"""Error-reduction Layer 1 — deterministic agent/hook/flow consistency guard.

Asserts that the *hardcoded structural counts* scattered across the
contributor-facing docs (CLAUDE.md · AGENTS.md · .claude/agents/README.md ·
CONTEXT.md · PHASE_STATUS.md) match the **actual filesystem + frontmatter
ground truth**. Exits non-zero with the offending file + line + claimed-vs-
actual so the drift surfaces in CI before review.

Why this exists: doc count-drift is a recurring, fully-mechanical error
class. In the agent-output-verifier work (PRs #621/#622) an LLM reviewer
(`docs-reviewer`) caught the SAME class of stale count three separate times
(25→26 subagents, 5→6 opus, 3→4 hooks, 8→9 flows). An LLM catching a
mechanical fact is probabilistic — it can miss. A script catches it every
time, for free, forever. This guard converts that probabilistic check into a
deterministic one (the project's "determinize the determinizable" principle —
see docs/LESSONS_LEARNED.md "count-drift").

Distinct from ``check_doc_test_counts.py`` (which BANS hardcoded *test*
counts because they move every PR): agent/hook/flow counts are slow-moving
*structural* facts that the docs intentionally state, so the right guard is
"the stated number must equal reality", not "don't state a number".

Two layers of checking:
  1. INTERNAL CONSISTENCY (filesystem only, no docs) — every agent has a
     valid model+effort; opus+sonnet == agents; effort max+high == agents;
     the README tier-count headers sum to the agent count; every hook wired
     in settings.json exists on disk.
  2. DOC ANCHORS — each canonical "N <thing>" phrase in the guarded docs
     must carry the ground-truth number. Anchors use precise regexes so
     chronological-log prose (historical "25 agents" snapshots) does NOT
     false-positive.

Scope notes:
  - PHASE_STATUS.md is a chronological log; only its single current-state
    "**N** in 6 tiers" table row is anchored (precise regex), not its prose.
  - Adding a new agent / hook / flow? Update the docs and this guard PASSES
    automatically (it reads reality) — no number lives in this file.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / ".claude" / "agents"
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"
SETTINGS = REPO_ROOT / ".claude" / "settings.json"
README = AGENTS_DIR / "README.md"

# Agent-catalog files that are NOT themselves subagents.
NON_AGENT_FILES = {"README.md", "TEAMS.md"}

VALID_MODELS = {"opus", "sonnet", "fable"}
# `ultracode` is the top effort tier (above `max`); `max`/`high` remain valid
# for any deliberate lower-effort carve-out.
VALID_EFFORTS = {"ultracode", "max", "high"}


@dataclass
class GroundTruth:
    n_agents: int
    n_opus: int
    n_sonnet: int
    n_fable: int
    n_effort_ultracode: int
    n_effort_max: int
    n_effort_high: int
    n_hooks: int
    n_flows: int
    tier_sum: int


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract the simple ``key: value`` YAML frontmatter as a flat dict.

    Only the leading ``---`` … ``---`` block is read; values are taken
    verbatim (single-line scalars — all this guard needs are ``model`` /
    ``effort`` / ``name``).
    """
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    fm: dict[str, str] = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return fm


def _agent_files() -> list[Path]:
    return sorted(
        p
        for p in AGENTS_DIR.glob("*.md")
        if p.name not in NON_AGENT_FILES
    )


def compute_ground_truth() -> tuple[GroundTruth, list[str]]:
    """Read the filesystem + frontmatter; return (truth, internal_errors)."""
    errors: list[str] = []

    agents = _agent_files()
    n_opus = n_sonnet = n_fable = n_ultracode = n_max = n_high = 0
    for path in agents:
        fm = _parse_frontmatter(path.read_text())
        model = fm.get("model", "")
        effort = fm.get("effort", "")
        if model == "opus":
            n_opus += 1
        elif model == "sonnet":
            n_sonnet += 1
        elif model == "fable":
            n_fable += 1
        else:
            errors.append(
                f".claude/agents/{path.name}: model '{model}' not in "
                f"{sorted(VALID_MODELS)} (frontmatter malformed?)"
            )
        if effort == "ultracode":
            n_ultracode += 1
        elif effort == "max":
            n_max += 1
        elif effort == "high":
            n_high += 1
        else:
            errors.append(
                f".claude/agents/{path.name}: effort '{effort}' not in "
                f"{sorted(VALID_EFFORTS)} (frontmatter malformed?)"
            )

    n_agents = len(agents)
    n_hooks = len(list(HOOKS_DIR.glob("*.sh")))
    readme = README.read_text()
    n_flows = len(re.findall(r"^### Flow \d+", readme, re.MULTILINE))

    # Tier headers: "### Tier 1 — Core (5)" → sum the parenthesized counts.
    tier_counts = [int(m) for m in re.findall(r"^### Tier \d+ —[^\n(]*\((\d+)\)", readme, re.MULTILINE)]
    tier_sum = sum(tier_counts)

    # --- Internal consistency (filesystem only) ---
    if n_opus + n_sonnet + n_fable != n_agents:
        errors.append(
            f"model split inconsistent: {n_opus} opus + {n_sonnet} sonnet "
            f"+ {n_fable} fable != {n_agents} agents"
        )
    if n_ultracode + n_max + n_high != n_agents:
        errors.append(
            f"effort split inconsistent: {n_ultracode} ultracode + {n_max} max "
            f"+ {n_high} high != {n_agents} agents"
        )
    if tier_sum != n_agents:
        errors.append(
            f"README tier headers sum to {tier_sum} (counts {tier_counts}) "
            f"!= {n_agents} agent files"
        )

    # --- settings.json hook wiring: every wired script must exist ---
    if SETTINGS.exists():
        try:
            settings = json.loads(SETTINGS.read_text())
            for event, groups in settings.get("hooks", {}).items():
                for group in groups:
                    for hook in group.get("hooks", []):
                        cmd = hook.get("command", "")
                        m = re.search(r"\.claude/hooks/([\w.-]+\.sh)", cmd)
                        if m and not (HOOKS_DIR / m.group(1)).exists():
                            errors.append(
                                f".claude/settings.json [{event}]: wires "
                                f"{m.group(1)} which does not exist in "
                                f".claude/hooks/"
                            )
        except json.JSONDecodeError as exc:
            errors.append(f".claude/settings.json: invalid JSON ({exc})")
    else:
        errors.append(".claude/settings.json: missing")

    truth = GroundTruth(
        n_agents=n_agents,
        n_opus=n_opus,
        n_sonnet=n_sonnet,
        n_fable=n_fable,
        n_effort_ultracode=n_ultracode,
        n_effort_max=n_max,
        n_effort_high=n_high,
        n_hooks=n_hooks,
        n_flows=n_flows,
        tier_sum=tier_sum,
    )
    return truth, errors


@dataclass
class Anchor:
    """A canonical doc phrase whose embedded number must equal ground truth."""
    file: str
    pattern: str          # one capture group = the claimed integer
    truth_key: str        # attribute on GroundTruth
    label: str


# Precise anchors — each regex is specific enough that chronological-log
# prose does not false-positive. Capture group 1 is always the integer.
ANCHORS: tuple[Anchor, ...] = (
    # --- agent count ---
    Anchor("CLAUDE.md", r"(\d+) project subagents in 6 tiers", "n_agents", "subagent count"),
    Anchor("CLAUDE.md", r"orchestrator / tech lead\*\* of the (\d+)-agent", "n_agents", "orchestrator N-agent team"),
    Anchor("CLAUDE.md", r"`description:` fields of all (\d+) agents", "n_agents", "walk-all-N-agents"),
    Anchor("AGENTS.md", r"The (\d+) subagents under", "n_agents", "AGENTS subagent count"),
    Anchor("AGENTS.md", r"(\d+) agent prompts are kept tight", "n_agents", "AGENTS prompt-count"),
    Anchor(".claude/agents/README.md", r"## The current set \((\d+)\)", "n_agents", "README current set"),
    Anchor("CONTEXT.md", r"(\d+) agents in 6 tiers", "n_agents", "CONTEXT roster"),
    Anchor("CONTEXT.md", r"(\d+) project-specific sub-agents in 6 tiers", "n_agents", "CONTEXT layout"),
    Anchor("PHASE_STATUS.md", r"\*\*(\d+)\*\* in 6 tiers", "n_agents", "PHASE_STATUS current-state"),
    # --- opus split ---
    Anchor("AGENTS.md", r"(\d+) opus / 21 sonnet", "n_opus", "AGENTS opus split"),
    Anchor("CONTEXT.md", r"(\d+) opus \+ 21 sonnet", "n_opus", "CONTEXT opus split"),
    Anchor("PHASE_STATUS.md", r"(\d+) opus \+ 21 sonnet", "n_opus", "PHASE_STATUS opus split"),
    Anchor(".claude/agents/README.md", r"why (\d+) opus / 21 sonnet", "n_opus", "README model-split heading"),
    # --- fable split (the Fable 5 creative seat, Tier 6) ---
    Anchor("AGENTS.md", r"21 sonnet / (\d+) fable", "n_fable", "AGENTS fable split"),
    Anchor("CONTEXT.md", r"21 sonnet \+ (\d+) fable", "n_fable", "CONTEXT fable split"),
    Anchor("PHASE_STATUS.md", r"21 sonnet \+ (\d+) fable", "n_fable", "PHASE_STATUS fable split"),
    Anchor(".claude/agents/README.md", r"21 sonnet / (\d+) fable", "n_fable", "README fable split"),
    # --- effort ultracode (top tier) ---
    Anchor(".claude/agents/README.md", r"Effort: (\d+) of \d+ agents run at", "n_effort_ultracode", "README effort heading"),
    Anchor(".claude/agents/README.md", r"(\d+) of \d+ agents run at the top", "n_effort_ultracode", "README authoring effort"),
    # --- hook count ---
    Anchor("CLAUDE.md", r"(\d+) bash hooks wired by", "n_hooks", "CLAUDE hook count"),
    Anchor("CONTEXT.md", r"(\d+) hook scripts", "n_hooks", "CONTEXT hook count"),
    # --- coordination flows ---
    # NOTE: the README intro phrases the flow count spelled-out ("Nine
    # canonical flows"), so it is intentionally NOT anchored here (a \d+
    # pattern can't match a word). The count is guarded numerically below
    # AND is itself the ground-truth source (n_flows counts the "### Flow N"
    # headers in README), so README is self-consistent by construction.
    Anchor("CLAUDE.md", r"(\d+) coordination flows", "n_flows", "CLAUDE flow count"),
    Anchor("CONTEXT.md", r"(\d+) coordination flows", "n_flows", "CONTEXT flow count"),
)


def check_anchors(truth: GroundTruth) -> list[str]:
    violations: list[str] = []
    for anchor in ANCHORS:
        path = REPO_ROOT / anchor.file
        if not path.exists():
            continue
        expected = getattr(truth, anchor.truth_key)
        rx = re.compile(anchor.pattern)
        for i, line in enumerate(path.read_text().splitlines(), start=1):
            for m in rx.finditer(line):
                claimed = int(m.group(1))
                if claimed != expected:
                    violations.append(
                        f"{anchor.file}:{i}: {anchor.label} says {claimed}, "
                        f"actual is {expected} — {line.strip()[:90]}"
                    )
    return violations


def run() -> tuple[GroundTruth, list[str]]:
    truth, internal_errors = compute_ground_truth()
    anchor_violations = check_anchors(truth)
    return truth, internal_errors + anchor_violations


def main() -> int:
    truth, problems = run()
    if problems:
        print("Agent/hook/flow consistency violations:")
        for p in problems:
            print(f"  {p}")
        print(
            f"\nGround truth: {truth.n_agents} agents "
            f"({truth.n_opus} opus / {truth.n_sonnet} sonnet / "
            f"{truth.n_fable} fable; "
            f"{truth.n_effort_ultracode} ultracode / {truth.n_effort_max} max "
            f"/ {truth.n_effort_high} high) · "
            f"{truth.n_hooks} hooks · {truth.n_flows} flows · "
            f"tier sum {truth.tier_sum}.\n"
            "Update the stale doc number(s) above to match reality, or fix "
            "the frontmatter/settings if the filesystem is wrong.\n"
            "(This guard derives every number from the filesystem — see "
            "tools/check_agent_hook_consistency.py.)"
        )
        return 1
    print(
        f"Agent/hook consistency OK — {truth.n_agents} agents "
        f"({truth.n_opus} opus / {truth.n_sonnet} sonnet / "
        f"{truth.n_fable} fable; "
        f"{truth.n_effort_ultracode} ultracode / {truth.n_effort_max} max "
        f"/ {truth.n_effort_high} high) · "
        f"{truth.n_hooks} hooks · {truth.n_flows} flows."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
