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

## mattpocock-skills (Claude Code skills)

- **Source**: <https://github.com/mattpocock/skills>
- **License**: MIT (declared in upstream `LICENSE` at repo root)
- **Upstream commit SHA**: `d54c497aa94400a496d3f2c38be10fa5f284c5a9`
- **Vendored date**: 2026-05-20
- **Vendored skills** (8 of 18 upstream skills selected):
  - `.claude/skills/mattpocock-diagnose/` (engineering/diagnose + `scripts/hitl-loop.template.sh`)
  - `.claude/skills/mattpocock-tdd/` (engineering/tdd + 5 sidecar `.md` files: deep-modules, interface-design, mocking, refactoring, tests)
  - `.claude/skills/mattpocock-to-issues/` (engineering/to-issues)
  - `.claude/skills/mattpocock-to-prd/` (engineering/to-prd)
  - `.claude/skills/mattpocock-setup-harness/` (engineering/setup-matt-pocock-skills + 5 sidecar `.md` files: domain, issue-tracker-{github,gitlab,local}, triage-labels)
  - `.claude/skills/mattpocock-handoff/` (productivity/handoff)
  - `.claude/skills/mattpocock-write-a-skill/` (productivity/write-a-skill)
  - `.claude/skills/mattpocock-grill-me/` (productivity/grill-me)

### Vendoring rationale

Skills selected as the "engineering core" most applicable to QuantRank's
Python + TypeScript stack and PR-iteration workflow. Skipped: 10 upstream
skills (caveman, scaffold-exercises, setup-pre-commit, migrate-to-shoehorn,
git-guardrails-claude-code, grill-with-docs, improve-codebase-architecture,
triage, prototype, zoom-out) plus all `in-progress/`, `deprecated/`, and
`personal/` directories. Selection criteria: language-agnostic +
project-applicable. The 10 skipped are either TypeScript-specific
(shoehorn), redundant with QuantRank's existing skills (setup-pre-commit
overlaps with project's CI guardrails), or in-flux upstream.

### Verbatim-preservation check

Each vendored `SKILL.md` carries upstream content byte-for-byte plus a
10-line appended `## License + Attribution` block. Sidecars (`.md`
references via `./domain.md` style links) are vendored without
modification. The Bash template script (`scripts/hitl-loop.template.sh`
under `mattpocock-diagnose/`) is also verbatim.

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
