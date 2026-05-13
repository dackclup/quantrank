# QuantRank project skills

Skills for QuantRank's compute → output → verify lifecycle, plus
vendored third-party skills from
[`anthropics/skills`](https://github.com/anthropics/skills).

## Layout

```
.claude/skills/
├── README.md                                  # this file
├── THIRD_PARTY_NOTICES.md                     # license attribution for vendored skills
│
├── verify-production-output/                  # cross-phase: 7 QuantRank skills
├── schema-check/                              # — used by every phase that
├── defense-scorecard/                         #   touches output JSON or
├── top5-rotation-audit/                       #   schema
├── network-test-runner/
├── phase-status-bump/
├── pr-iteration-flow/
│
├── phase-1/ ... phase-8/                      # phase-specific stubs (12 dirs)
│
├── algorithmic-art/                           # vendored from anthropics/skills (17 dirs)
├── brand-guidelines/
├── canvas-design/
├── claude-api/
├── doc-coauthoring/
├── docx/
├── frontend-design/
├── internal-comms/
├── mcp-builder/
├── pdf/
├── pptx/
├── skill-creator/
├── slack-gif-creator/
├── theme-factory/
├── web-artifacts-builder/
├── webapp-testing/
└── xlsx/
```

Each skill directory contains a `SKILL.md` with YAML frontmatter
(`name`, `description`) plus markdown body. The vendored skills
additionally include `LICENSE.txt` (Apache 2.0 or source-available
per skill) and per-skill helper scripts / templates / fonts.

## QuantRank cross-phase skills (7)

| Skill | When to use |
|---|---|
| `verify-production-output` | After every workflow_dispatch or scheduled run, before authorizing Mark-Ready / merge / tag |
| `schema-check` | Anytime `compute/output/schemas.py` or `frontend/lib/types.ts` changes |
| `defense-scorecard` | After risk-overlay or new-defense work, to count vetoes / guards / annotate flags vs baseline |
| `top5-rotation-audit` | After scoring changes, to verify entered_top5 / exited_top5 semantics + composition churn |
| `network-test-runner` | When `@network`-marked tests need to run against real SEC EDGAR (sandbox skips them) |
| `phase-status-bump` | At the end of each phase, to update `PHASE_STATUS.md` + `SKILL.md` + `WORKFLOW.md` consistently |
| `pr-iteration-flow` | During UI polish iteration — manage Draft↔Ready flips + spot-check matrix authoring |

## QuantRank phase-specific stubs (36)

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

## Vendored third-party skills (17, from `anthropics/skills`)

Full snapshot of [`anthropics/skills`](https://github.com/anthropics/skills)
@ main (2026-05-09). Placed flat alongside the QuantRank skills so
Claude Code auto-loads them at session start — no plugin
marketplace mechanism, no runtime fetch from GitHub.

| Vendored skill | Description |
|---|---|
| `algorithmic-art` | Generative art with p5.js (seeded randomness, parametric exploration) |
| `brand-guidelines` | Apply Anthropic corporate colors / typography to artifacts |
| `canvas-design` | Static visual design (posters, graphics) as PNG/PDF — includes ~5 MB of font files |
| `claude-api` | Build/debug Claude API + Anthropic SDK apps; prompt caching; model versioning |
| `doc-coauthoring` | Structured workflow for collaborative docs / proposals / decision docs |
| `docx` | Create/edit Word documents (.docx); formatting, tables, tracked changes |
| `frontend-design` | Production-grade UI; distinctive visual design; avoid AI clichés |
| `internal-comms` | Template-based internal communications (updates, FAQs, status reports) |
| `mcp-builder` | Create Model Context Protocol servers in Python (FastMCP) or TypeScript |
| `pdf` | Read/extract/merge/split PDFs; OCR; encryption; watermarking |
| `pptx` | Create/edit PowerPoint presentations; templates; layouts; speaker notes |
| `skill-creator` | Develop, test, iterate, and package Claude skills; eval framework |
| `slack-gif-creator` | Animated GIFs optimized for Slack (128×128 emoji, 480×480 message) |
| `theme-factory` | Pre-configured themes (10 themes) for styling artifacts |
| `web-artifacts-builder` | Complex React/TypeScript/Tailwind/shadcn artifacts; Vite bundling |
| `webapp-testing` | Playwright-based web app testing; browser automation; UI verification |
| `xlsx` | Spreadsheet operations (.xlsx, .csv, .tsv); formulas; financial models |

**License**: most are Apache 2.0; `docx`/`pdf`/`pptx`/`xlsx` are
source-available per upstream. See
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) at the directory
root for full attribution, and each skill's `LICENSE.txt` for
per-skill terms.

**Updates**: vendored skills do NOT auto-update. To pull a newer
snapshot, re-download the ZIP from upstream and re-vendor:

```bash
unzip -q skills-main.zip -d /tmp/skills-extract
for skill in /tmp/skills-extract/skills-main/skills/*/; do
  rm -rf ".claude/skills/$(basename "$skill")"
  cp -r "$skill" ".claude/skills/$(basename "$skill")/"
done
cp /tmp/skills-extract/skills-main/THIRD_PARTY_NOTICES.md .claude/skills/
```

## Authoring conventions (for new QuantRank skills)

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

## Adding a new QuantRank skill

1. Pick the right directory (`<skill-name>/` for cross-phase, `phase-N/<skill-name>/` for phase-specific).
2. Author `SKILL.md` with frontmatter + body.
3. Add helper scripts if needed (next to SKILL.md).
4. Update this README's tables.
5. Commit on a topic branch; open a PR if the skill is non-trivial.

## What this is NOT

- **Not a substitute for project documentation** — `SKILL.md`,
  `WORKFLOW.md`, `PHASE_STATUS.md`, `docs/METHODOLOGY.md`, and
  `docs/RESEARCH_FINDINGS.md` remain the canonical reference. Skills
  point AT those docs; they don't replace them.
- **Not a marketplace mirror** — the vendored skills are a frozen
  snapshot, not a live mirror of `anthropics/skills`. For the latest
  upstream content, see <https://github.com/anthropics/skills>.
