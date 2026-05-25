# Third-Party Notices

QuantRank vendors third-party code under permissive open-source
licenses. Each entry below cites the source, license, and the path
where the vendored copy lives in this repo.

---

## karpathy-guidelines (Claude Code skill)

- **Source**: <https://github.com/multica-ai/andrej-karpathy-skills>
- **License**: MIT (declared in upstream `README.md` § License + each
  skill's YAML frontmatter `license: MIT`; upstream has no standalone
  `LICENSE` file at the time of vendoring, 2026-05-20)
- **Vendored at**: `.claude/skills/portable-karpathy-guidelines/SKILL.md`
- **Vendored date**: 2026-05-20
- **Upstream commit SHA**: `2c606141936f1eeef17fa3043a72095b4765b9c2`
- **Upstream first commit**: 2026-01-27

### MIT License (full text)

The standard MIT License text, applied per upstream's `license: MIT`
declaration. Copyright attributed to the upstream repository owner
(multica-ai contributors) absent a more specific copyright line.

```
MIT License

Copyright (c) 2026 multica-ai contributors
(per https://github.com/multica-ai/andrej-karpathy-skills)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### Attribution note

The Karpathy guidelines themselves are derived from
[Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876)
on LLM coding pitfalls; the upstream `multica-ai/andrej-karpathy-skills`
repo is the codification of those observations into a Claude Code skill.

---

## karpathy-llm-wiki (Claude Code reference doc)

- **Source**: <https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f>
- **Author**: Andrej Karpathy
- **License**: NONE DECLARED on the gist. Vendored under the gist's
  explicit usage permission embedded in the gist text itself:
  > "This is an idea file, it is designed to be copy pasted to your own
  > LLM Agent (e.g. OpenAI Codex, Claude Code, OpenCode / Pi, or etc.).
  > Its goal is to communicate the high level idea, but your agent will
  > build out the specifics in collaboration with you."
  This is an explicit invitation to copy and use; treat as the
  vendoring basis until/unless Karpathy declares a formal license on
  the gist.
- **Vendored at**: `.claude/skills/karpathy-llm-wiki/SKILL.md`
- **Vendored date**: 2026-05-20
- **Vendored revision**: gist content as displayed on 2026-05-20 (gists
  do not expose stable commit SHAs in the way repos do — record the
  date and quote the in-text permission as the audit trail)

### Why no MIT block

Unlike `karpathy-guidelines` (vendored from `multica-ai/andrej-karpathy-skills`
which declares MIT), this gist has no declared license. The vendoring
basis is the in-text copy-paste permission, not a standard OSS license.
If Karpathy later adds a `LICENSE` block to the gist or repos this
content elsewhere with a formal license, update this section and the
`SKILL.md` frontmatter to reflect the declared terms.

### Attribution note

The LLM Wiki pattern is Karpathy's design idea, communicated as an
abstract pattern rather than a specific implementation. The gist
explicitly says *"share it with your LLM agent and work together to
instantiate a version that fits your needs"* — vendoring this here
makes the pattern available to QuantRank's Claude Code sessions as a
reference, not as a triggered behavioral skill in the usual sense.

---

## mattpocock-skills (Claude Code skills)

- **Source**: <https://github.com/mattpocock/skills>
- **License**: MIT (declared in upstream `LICENSE` at repo root)
- **Upstream commit SHA**: `d54c497aa94400a496d3f2c38be10fa5f284c5a9`
  (base sync 2026-05-20; `grill-with-docs` added 2026-05-25 from the
  same upstream snapshot)
- **Vendored date**: 2026-05-20 (base); 2026-05-25 (grill-with-docs add)
- **Vendored skills** (9 of 18 upstream skills selected):
  - `.claude/skills/mattpocock-diagnose/` (engineering/diagnose + `scripts/hitl-loop.template.sh`)
  - `.claude/skills/mattpocock-tdd/` (engineering/tdd + 5 sidecar `.md` files: deep-modules, interface-design, mocking, refactoring, tests)
  - `.claude/skills/mattpocock-to-issues/` (engineering/to-issues)
  - `.claude/skills/mattpocock-to-prd/` (engineering/to-prd)
  - `.claude/skills/mattpocock-setup-harness/` (engineering/setup-matt-pocock-skills + 5 sidecar `.md` files: domain, issue-tracker-{github,gitlab,local}, triage-labels)
  - `.claude/skills/mattpocock-handoff/` (productivity/handoff)
  - `.claude/skills/mattpocock-write-a-skill/` (productivity/write-a-skill)
  - `.claude/skills/mattpocock-grill-me/` (productivity/grill-me)
  - `.claude/skills/mattpocock-grill-with-docs/` (engineering/grill-with-docs + 2 sidecar `.md` files: CONTEXT-FORMAT, ADR-FORMAT)

### Vendoring rationale

Skills selected as the "engineering core" most applicable to QuantRank's
Python + TypeScript stack and PR-iteration workflow. Skipped: 9 upstream
skills (caveman, scaffold-exercises, setup-pre-commit, migrate-to-shoehorn,
git-guardrails-claude-code, improve-codebase-architecture, triage,
prototype, zoom-out) plus all `in-progress/`, `deprecated/`, and
`personal/` directories. Selection criteria: language-agnostic +
project-applicable. The 9 skipped are either TypeScript-specific
(shoehorn), redundant with QuantRank's existing skills (setup-pre-commit
overlaps with project's CI guardrails), or in-flux upstream.
**`grill-with-docs` was initially skipped at the 2026-05-20 base sync
as "in-flux upstream" — added 2026-05-25 after the skill stabilized
upstream and proved useful in PR2a scope-design (the user-shared
[AIHero post](https://www.aihero.dev/grill-with-docs) catalogued the
mature form).** QuantRank adapts the skill's single-`CONTEXT.md`
assumption to its multi-file equivalent (CLAUDE.md + METHODOLOGY.md +
SKILL.md + WORKFLOW.md); ADRs land in `PHASE_STATUS_INFLIGHT.md`
rather than `docs/adr/`. See the skill's `SKILL.md` "QuantRank
adaptation notes" section for the divergence rationale.

### Verbatim-preservation check

Each vendored `SKILL.md` carries upstream content byte-for-byte plus a
10-line appended `## License + Attribution` block, **except** for the
5 skills listed under "Description divergence" below. Sidecars (`.md`
references via `./domain.md` style links) are vendored without
modification. The Bash template script (`scripts/hitl-loop.template.sh`
under `mattpocock-diagnose/`) is also verbatim.

### Description divergence (2026-05-20)

To enable auto-trigger on sharp keyword phrases (and to reduce false-
positive auto-fires that the original "Use when user wants..." pattern
would have caused), the YAML frontmatter `description:` field was
rewritten for 5 vendored skills. **The body of every SKILL.md remains
upstream-verbatim.** Diverging files:

- `.claude/skills/mattpocock-grill-me/SKILL.md`
- `.claude/skills/mattpocock-tdd/SKILL.md`
- `.claude/skills/mattpocock-to-prd/SKILL.md`
- `.claude/skills/mattpocock-to-issues/SKILL.md`
- `.claude/skills/mattpocock-write-a-skill/SKILL.md`

Pattern of change: original "Use when user wants X" → "TRIGGER when
user explicitly says 'X' / 'Y' / 'Z'" with 4-6 sharp keyword phrases
plus a `do NOT auto-fire on generic ...` guardrail.

**Next vendor sync (from upstream `mattpocock/skills@HEAD`)**: expect
merge conflicts on these 5 `description:` lines. Resolution policy:
keep the local TRIGGER-style descriptions unless upstream has likewise
adopted explicit TRIGGER syntax — in that case, take upstream's wording
and re-evaluate sharp-keyword coverage. Body content of each SKILL.md
should still pull upstream verbatim.

### MIT License (full text)

The upstream `LICENSE` file at repo root:

```
MIT License

Copyright (c) 2026 Matt Pocock

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 9arm-skills (Claude Code skills) — LICENSE PENDING

> **⚠️ License status**: At the time of vendoring (2026-05-20), the
> upstream `thananon/9arm-skills` repository ships **no `LICENSE`
> file** at the root, declares **no `license:` field** in any
> `SKILL.md` YAML frontmatter, and has **no license section** in
> `README.md` or `CLAUDE.md`. Per default copyright law (US / TH /
> EU), the copyright holder retains all rights absent an explicit
> license grant, and public visibility on GitHub is **not** a
> redistribution license.
>
> This vendoring proceeded against the auditor session's
> recommendation, on the maintainer's explicit instruction. Tracker
> issue **[dackclup/quantrank#137](https://github.com/dackclup/quantrank/issues/137)**
> is the record of the license-clarification follow-up with the
> upstream author. If `thananon` declines redistribution permission
> (or doesn't respond within a reasonable window), the 4 vendored
> skills below **must be removed** from this repo and replaced with
> the "inspire-only" pattern (original prose covering the same
> patterns, attributing thananon as inspiration without copying the
> upstream text).

- **Source**: <https://github.com/thananon/9arm-skills>
- **License**: NOT DECLARED upstream at vendoring time (see warning
  above)
- **Original author**: thananon ("9arm")
- **Upstream commit SHA**: `d714cb84f35e0c42b2ca29bca505e564ab9f2bcd`
- **Vendored date**: 2026-05-20
- **Vendored skills** (all 4 upstream skills):
  - `.claude/skills/9arm-debug-mantra/SKILL.md` (upstream `engineering/debug-mantra/`)
  - `.claude/skills/9arm-post-mortem/SKILL.md` (upstream `engineering/post-mortem/`)
  - `.claude/skills/9arm-scrutinize/SKILL.md` (upstream `engineering/scrutinize/`)
  - `.claude/skills/9arm-management-talk/SKILL.md` (upstream `productivity/management-talk/`)

### Verbatim-preservation check

Each vendored `SKILL.md` carries upstream content byte-for-byte plus
an 18-line appended `## Provenance + Attribution` block (referencing
the upstream SHA, the no-license disclosure, and tracker issue
#137). The upstream skills do not ship sidecar `.md` files or
bundled scripts, so the directory contents are 1-file each.

### Action items on upstream license outcome

| Upstream response | Action |
|---|---|
| Adds permissive `LICENSE` (MIT / Apache 2.0 / BSD) | Replace this section with the proper provenance block (modeled on karpathy / mattpocock entries above); update the attribution block in each `9arm-*/SKILL.md` to reference the now-declared license. |
| Adds copyleft `LICENSE` (GPL / AGPL) | Either accept the copyleft (requires re-licensing QuantRank or making `.claude/skills/9arm-*/` a separate concern) or remove all 4 vendored skills. |
| Adds non-OSI license forbidding redistribution | Remove all 4 vendored skills; close issue #137 with "vendor not permitted"; optionally pursue the "inspire-only" path. |
| Doesn't respond | Re-evaluate at 4 weeks post-filing — either remove the skills or proceed with the explicit understanding that takedown may follow. |
