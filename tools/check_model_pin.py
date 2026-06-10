#!/usr/bin/env python3
"""Guard against a silent subagent model downgrade.

The 24 subagents in ``.claude/agents/*.md`` use bare model aliases
(``model: fable`` / ``model: sonnet``). Per the Claude Code docs an alias
resolves to the LATEST model in that family at runtime and floats forward on a
CLI update — which is exactly what we want (no self-inflicted downgrade, always
newest). The risk is NOT in the agent files: it's the *environment*. A
``CLAUDE_CODE_SUBAGENT_MODEL`` or ``ANTHROPIC_DEFAULT_{FABLE,OPUS,SONNET,HAIKU}_MODEL``
override committed into ``.claude/settings.json`` would pin every subagent to a
specific (possibly older) version WITHOUT changing a single agent file — an
invisible downgrade. This guard fails CI if either appears in the committed
settings, or if an agent frontmatter pins a dated/numbered model ID instead of
the floating alias.

Exit 0 = clean. Exit 1 = a downgrade vector found (prints what + how to fix).

Run locally: ``python tools/check_model_pin.py``
Wired into ``.github/workflows/ci.yml`` (Python job).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO / ".claude" / "agents"
SETTINGS = REPO / ".claude" / "settings.json"

# Env vars that, if set in committed settings, silently override the alias for
# ALL subagents (CLAUDE_CODE_SUBAGENT_MODEL) or remap the alias on third-party
# providers (ANTHROPIC_DEFAULT_*_MODEL). `inherit` is the one safe value for
# CLAUDE_CODE_SUBAGENT_MODEL (it means "use the main session's model").
_OVERRIDE_VARS = (
    "CLAUDE_CODE_SUBAGENT_MODEL",
    "ANTHROPIC_DEFAULT_FABLE_MODEL",
    "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_SMALL_FAST_MODEL",
)

# The only model: values we allow in agent frontmatter — the floating aliases
# (+ `inherit`, which follows the main session). A dated / numbered ID like
# `claude-opus-4-8` or `claude-sonnet-4-6-20260101` is a PIN that will NOT float
# forward → a future-dated downgrade the day a newer model ships. Reject those.
_ALLOWED_MODEL_VALUES = {"fable", "opus", "sonnet", "haiku", "inherit"}

_MODEL_LINE = re.compile(r"^model:\s*(.+?)\s*$", re.MULTILINE)


def _settings_overrides() -> list[str]:
    """Return human-readable problems found in committed settings.json."""
    if not SETTINGS.exists():
        return []
    try:
        data = json.loads(SETTINGS.read_text())
    except json.JSONDecodeError as exc:
        return [f"{SETTINGS.relative_to(REPO)} is not valid JSON: {exc}"]

    problems: list[str] = []
    env = data.get("env", {})
    if not isinstance(env, dict):
        return problems
    for var in _OVERRIDE_VARS:
        if var not in env:
            continue
        value = env[var]
        # CLAUDE_CODE_SUBAGENT_MODEL=inherit is benign (follows main session).
        if var == "CLAUDE_CODE_SUBAGENT_MODEL" and str(value).strip() == "inherit":
            continue
        problems.append(
            f"{SETTINGS.relative_to(REPO)} env.{var} = {value!r} — this pins / "
            f"overrides the subagent model and can silently downgrade all 24 "
            f"agents below the latest. Remove it (or set "
            f"CLAUDE_CODE_SUBAGENT_MODEL='inherit') unless the pin is "
            f"deliberate + documented."
        )
    return problems


def _agent_pins() -> list[str]:
    """Return problems for any agent frontmatter that PINS a model version."""
    problems: list[str] = []
    if not AGENTS_DIR.is_dir():
        return problems
    for path in sorted(AGENTS_DIR.glob("*.md")):
        if path.name in {"README.md", "TEAMS.md"}:  # non-agent docs
            continue
        text = path.read_text()
        # Only inspect the YAML frontmatter (between the first two --- fences).
        if text.startswith("---"):
            end = text.find("\n---", 3)
            front = text[: end if end != -1 else len(text)]
        else:
            front = text
        m = _MODEL_LINE.search(front)
        if not m:
            problems.append(
                f"{path.relative_to(REPO)} has no `model:` line in its "
                f"frontmatter (would inherit the session model)."
            )
            continue
        value = m.group(1).strip().strip("\"'")
        if value not in _ALLOWED_MODEL_VALUES:
            problems.append(
                f"{path.relative_to(REPO)} model: {value!r} pins a specific "
                f"version — use a floating alias ({', '.join(sorted(_ALLOWED_MODEL_VALUES))}) "
                f"so it always resolves to the latest and never self-downgrades."
            )
    return problems


def main() -> int:
    problems = _settings_overrides() + _agent_pins()
    if problems:
        print("Model-pin guard FAILED — subagent-downgrade vector(s) found:\n")
        for p in problems:
            print(f"  ✗ {p}")
        print(
            "\nWhy this matters: bare `model: fable` / `model: sonnet` aliases "
            "float forward to the newest model automatically. A committed env "
            "override or a pinned model ID defeats that and can silently run an "
            "OLDER model. See CLAUDE.md §Gotchas 'subagent model aliases float "
            "forward'."
        )
        return 1
    print(
        "Model-pin guard OK — all agent frontmatter uses floating aliases and "
        "committed settings carry no model-override env var (subagents always "
        "resolve to the latest model for their alias — Fable/Opus/Sonnet)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
