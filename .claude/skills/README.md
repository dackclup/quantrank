# QuantRank project skills

Project-specific [Claude Code skills](https://docs.claude.com/en/docs/claude-code/skills)
for QuantRank's compute → output → verify lifecycle. Skills here encode
the conventions, file paths, schema versions, and verification patterns
that emerged from PR-3a through PR-3d so each phase doesn't re-invent
them.

## Layout

```
.claude/skills/
├── README.md                                  # this file
│
├── verify-production-output/                  # cross-phase: 7 skills total
├── schema-check/                              # — used by every phase that
├── defense-scorecard/                         #   touches output JSON or
├── top5-rotation-audit/                       #   schema
├── network-test-runner/
├── phase-status-bump/
├── pr-iteration-flow/
│
├── phase-1/                                   # phase-specific: 36 stubs
│   ├── universe-refresh/                      #   organized per phase
│   └── yfinance-debug/                        #
├── phase-2/                                   # Phases 1 / 2 / 3a / 3b /
├── phase-3a/                                  # 3c / 3d / 3e / 4 / 5 /
├── phase-3b/                                  # 6 / 7 / 8
├── phase-3c/
├── phase-3d/
├── phase-3e/
├── phase-4/
├── phase-5/
├── phase-6/
├── phase-7/
└── phase-8/
```

Each skill directory contains a `SKILL.md` with YAML frontmatter
(`name`, `description`) plus markdown body that describes when to use
the skill, its inputs / outputs, and any helper script paths.

## Cross-phase skills (full)

| Skill | When to use |
|---|---|
| `verify-production-output` | After every workflow_dispatch or scheduled run, before authorizing Mark-Ready / merge / tag |
| `schema-check` | Anytime `compute/output/schemas.py` or `frontend/lib/types.ts` changes |
| `defense-scorecard` | After risk-overlay or new-defense work, to count vetoes / guards / annotate flags vs baseline |
| `top5-rotation-audit` | After scoring changes, to verify entered_top5 / exited_top5 semantics + composition churn |
| `network-test-runner` | When `@network`-marked tests need to run against real SEC EDGAR (sandbox skips them) |
| `phase-status-bump` | At the end of each phase, to update `PHASE_STATUS.md` + `SKILL.md` + `WORKFLOW.md` consistently |
| `pr-iteration-flow` | During UI polish iteration — manage Draft↔Ready flips + spot-check matrix authoring |

## Phase-specific skills (stubs)

Each `phase-N/` directory contains stubs (frontmatter + brief
description) for the skills that phase will need. Flesh out each
SKILL.md when starting that phase's work — the stub captures the
intent + acceptance criteria so the implementation has a clear target.

| Phase | Skills |
|---|---|
| Phase 1 — universe + prices | `universe-refresh`, `yfinance-debug` |
| Phase 2 — fundamentals (SEC EDGAR) | `fundamentals-cache-warm`, `xbrl-tag-debug`, `sec-api-health-check` |
| Phase 3a — pillars | `pillar-imputation-check`, `sector-neutralization-debug` |
| Phase 3b — risk overlay (3 vetoes) | `altman-debug`, `sloan-debug`, `nsi-debug` |
| Phase 3c — fair-price ensemble | `ensemble-method-debug`, `outlier-detection-debug`, `mos-display-clamp-check` |
| Phase 3d — Tier-2 events | `tier2-deferred-mode-check`, `going-concern-fp-audit`, `fundamentals-coverage-report` |
| Phase 3e — Tier-3 + v1.0 | `beneish-mscore-debug`, `dechow-fscore-debug`, `honest-limitations-section` |
| Phase 4 — factor consolidation + 3d follow-ups | `8k-events-pre-cache`, `going-concern-phrase-refine`, `ipca-factor-fit`, `alpha158-fit`, `chronic-slow-ticker-special-case` |
| Phase 5 — ML meta-learner | `triple-barrier-label`, `meta-label`, `conformal-predict`, `shap-explain` |
| Phase 6 — sentiment v2 | `whisper-transcribe`, `finbert-score`, `lazy-prices-detect` |
| Phase 7 — regime + portfolio | `student-t-hmm-fit`, `nco-portfolio-allocate`, `tda-risk-off` |
| Phase 8 — universe expansion | `universe-expand-sp1500`, `microcap-skip` |

## Authoring conventions

- **YAML frontmatter** — every `SKILL.md` starts with:
  ```yaml
  ---
  name: <skill-name>
  description: <full sentence describing when to invoke this skill>
  ---
  ```
- **Description length** — write the description like an instruction
  the model would read to decide whether to invoke. Specific verbs
  ("verify", "scan", "regenerate") + the trigger condition ("after
  workflow_dispatch completes", "when schemas.py changes").
- **No emojis in frontmatter or body** unless explicitly requested.
- **File paths** in skills always absolute from repo root (e.g.,
  `frontend/public/data/metadata.json`, not `metadata.json`) — the
  agent may not start in the directory you expect.
- **Helper scripts** — if a skill needs Python or shell helpers, put
  them next to the SKILL.md as `helper.py` / `helper.sh`. Reference
  them from the body with their relative path.

## Adding a new skill

1. Pick the right directory (`<skill-name>/` for cross-phase, `phase-N/<skill-name>/` for phase-specific).
2. Author `SKILL.md` with frontmatter + body.
3. Add helper scripts if needed (next to SKILL.md).
4. Update this README's table.
5. Commit on a topic branch; open a PR if the skill is non-trivial.

## Sister source: Anthropic skills marketplace

The official Anthropic skills marketplace
([`anthropics/skills`](https://github.com/anthropics/skills)) is
pre-registered in `.claude/settings.json` at the repo root, with all
17 marketplace skills listed in `enabledPlugins`. On a fresh clone,
Claude Code will prompt to trust the marketplace and auto-install
the listed plugins.

The 17 marketplace skills:

```
claude-api          webapp-testing      mcp-builder
docx                pdf                  xlsx
pptx                skill-creator        web-artifacts-builder
frontend-design     algorithmic-art      canvas-design
brand-guidelines    theme-factory        slack-gif-creator
doc-coauthoring     internal-comms
```

These complement (do not replace) the 43 QuantRank-specific skills
above. The marketplace skills are general-purpose (Claude API
helpers, web app testing, MCP server scaffolding, document
generation, design utilities); the QuantRank skills here cover
domain workflows (verify-production-output, defense-scorecard,
schema-check, per-phase debuggers).

**If a contributor's Claude Code doesn't auto-install on clone**,
the manual incantation is:

```
/plugin marketplace add anthropics/skills
/plugin install <name>@anthropics-skills    # per skill, no wildcard
```

Or use the `/plugin` UI's Discover tab to multi-select.

**Settings.json scope**: `.claude/settings.json` is committed to the
repo, so the marketplace registration + enabled-plugin list ships
with the repo. Per-user overrides go in `.claude/settings.local.json`
(gitignored).

Docs: <https://code.claude.com/docs/en/discover-plugins.md>

## What this is NOT

- **Not a substitute for project documentation** — `SKILL.md`,
  `WORKFLOW.md`, `PHASE_STATUS.md`, `docs/METHODOLOGY.md`, and
  `docs/RESEARCH_FINDINGS.md` remain the canonical reference. Skills
  point AT those docs; they don't replace them.
- **Not generic AI-agent skills** — for those, browse
  [skills.sh](https://skills.sh) and install with
  `npx skills add <owner/repo>`. The skills here are specific to
  QuantRank's compute pipeline and only useful in this repo.
