# claude-Creator.md — a guide for writing a great `CLAUDE.md`

> **Use this guide whenever you're about to author, edit, or audit a
> `CLAUDE.md` for a project.** It compresses the consensus from
> Anthropic's official Claude Code docs, the Claude API platform
> docs, and Humanlayer's empirical write-up
> ([humanlayer.dev](https://www.humanlayer.dev/blog/writing-a-good-claude-md))
> into one actionable reference. It does NOT replace those sources —
> read them when you need depth.

## 1. What CLAUDE.md is (and isn't)

`CLAUDE.md` is the **project-bound persistent memory** for Claude
Code. It is auto-loaded into context at the start of every session,
so it is the **only** file guaranteed to ground every conversation
about this repo.

| Compare with | Difference |
|---|---|
| `AGENTS.md` | Cross-tool open standard. Procedural / technical. Read by 20+ agent tools (Copilot, Cursor, Devin, …). See `agent-Creator.md`. |
| `.cursorrules` | Cursor-only. Same niche as CLAUDE.md but bound to one IDE. |
| `.github/copilot-instructions.md` | GitHub Copilot only. |
| The Anthropic system prompt | Global across all Anthropic conversations. You don't author it. |

`CLAUDE.md` complements `AGENTS.md`; it does not replace it. If both
exist, Claude Code prioritises `CLAUDE.md`; other tools read
`AGENTS.md`.

## 2. Length budget

| Range | Verdict |
|---|---|
| **< 60 lines** | Ideal — sharp, every line earns its place |
| **60-200 lines** | Healthy — most repos land here |
| **200-300 lines** | Ceiling — split into linked sub-docs before this |
| **> 300 lines** | Too long. The model treats peripheral content as low-priority |

Background: frontier LLMs follow ~150-200 instructions with
reasonable consistency before drift sets in, and Claude Code's
built-in system prompt already burns ~50 instructions. Every line
in `CLAUDE.md` competes with the model's task context for
attention.

> **"Frontier thinking LLMs can follow ~ 150-200 instructions with
> reasonable consistency."** — Humanlayer

## 3. The WHAT / WHY / HOW backbone

Organize content around three questions:

- **WHAT** — Stack, project structure, where things live
- **WHY** — Purpose of the project, role of major components
- **HOW** — Build commands, test commands, verification workflow

Subsections under these umbrellas may include:

| Subsection | Belongs to | Notes |
|---|---|---|
| Tech stack with **versions** | WHAT | `React 18 + TypeScript 5 + Vite` beats "a React project" |
| Directory map | WHAT | One-line description per top-level dir |
| Domain ownership | WHAT | Which dir owns auth / scoring / output / etc. |
| Build / test / lint commands | HOW | Exact commands and flags. `pytest -m "not network"` not "run tests" |
| Verification ladder | HOW | What "done" means: lint + tests + schema-check + smoke run |
| Conventions / patterns | WHY → HOW | E.g. "Pydantic + TS snapshot must move together" |
| Gotchas | HOW | Known fragile spots. One line each. |

## 4. Writing style

- **Imperative form.** "Run `npm test`", not "tests are run by npm".
- **Explain the WHY.** Modern models follow rules better when they
  understand the rationale than when ordered with bare ALL-CAPS
  MUSTs.
- **Link out, don't inline.** Code snippets and schemas embedded in
  `CLAUDE.md` rot faster than the code they describe. Link to the
  canonical file (`docs/ARCHITECTURE.md`, `pyproject.toml`).
- **Concrete > abstract.** "Auth lives in `services/auth/`" beats
  "authentication is in its own module".
- **One sentence per gotcha.** Gotchas get long quickly. Cap each at
  a single line; link out for depth.
- **No emojis in body unless the project itself uses them.** They
  cost tokens and add no signal for the model.

## 5. Anti-patterns (things that DEGRADE CLAUDE.md)

| Pattern | Why it hurts | What to do instead |
|---|---|---|
| Style-guide rules (line length, brace style) | Models ignore formatting instructions; linters / formatters do this job deterministically | Add a pre-commit hook with `ruff`, `prettier`, `biome` |
| Auto-generated from `/init` | Generic noise pushes signal out of the budget | Hand-author. Treat every line as load-bearing. |
| Stale code snippets | Rot fast; mislead the model | Link the file path; the model can `Read` it |
| Long do-not-do lists | Reads as paranoid; signals to model that disobedience is expected | Explain WHY a thing matters; trust the model |
| Task-specific instructions ("when fixing issue #42, do X") | Pollute the budget for unrelated sessions | Put in the issue itself, not CLAUDE.md |
| Personas / tone ("you are a senior engineer who...") | No measured effect on output quality at the project level | Drop |

> **"Never send an LLM to do a linter's job."** — Humanlayer

> **"Manually craft every line — this is the highest leverage point
> of the harness."** — Humanlayer

## 6. Authoring workflow

1. **Skim the repo** before writing a single line. Run the build,
   the tests, open the entry-point modules. The goal is to write
   from understanding, not from a template.
2. **Draft the WHAT / WHY / HOW backbone** with just the headings
   filled in.
3. **Fill HOW first.** Build + test + lint + verification commands
   are the highest-leverage content. They're what every session
   needs.
4. **Fill WHAT second.** Stack + structure + domain ownership.
5. **Fill WHY last and lightly.** A paragraph at top suffices unless
   the project's purpose is genuinely non-obvious.
6. **Add 1-3 gotchas** discovered during step 1, one line each.
7. **Re-read with fresh eyes.** Cut anything that wouldn't change
   how Claude acts on a real task.
8. **Commit it.** Treat `CLAUDE.md` changes as substantive — they
   affect every future session.

## 7. Sub-CLAUDE.md (per-directory)

Use a per-directory `CLAUDE.md` only when a subdirectory has:

- A genuinely different stack (e.g., `frontend/` vs `compute/`)
- A different test command
- A different deployment lifecycle
- Distinct conventions that don't apply repo-wide

Otherwise: keep one root `CLAUDE.md`. Per-directory copies multiply
the maintenance burden and frequently drift.

The root `CLAUDE.md` is always the **index**. Per-directory files
override or extend, not replace, the root.

## 8. Maintenance

| Event | Action on CLAUDE.md |
|---|---|
| New tool added (e.g., `tenacity` retry) | Add it to "Tech stack". Maybe a gotcha. |
| Major refactor lands | Update directory map + ownership table |
| Build command changes | Update HOW immediately. Stale commands waste agent time. |
| A gotcha is fixed / no longer relevant | Remove it |
| A new convention emerges (e.g., schema snapshot guard) | Add one line + link to the doc that explains it |

Treat `CLAUDE.md` as living code. Diff it in PRs. Don't archive old
versions (Git history is the archive).

## 9. Minimum-viable template

For a fresh project, this skeleton is enough to start:

```markdown
# CLAUDE.md

<one-paragraph statement of what the project does>

## Stack

- <Lang/runtime + version>
- <Framework + version>
- <Key libs: 3-5 max>

## Layout

- `src/` — <one line>
- `tests/` — <one line>
- `docs/` — <one line>

## Commands

- Build: `<exact command>`
- Test: `<exact command + flags>`
- Lint: `<exact command>`
- Verify before push: `<the full ladder>`

## Conventions

- <One line each, 3-5 max>

## Gotchas

- <One line each, only the ones you'd want a new contributor warned about>
```

That's 30 lines. You can grow it from here. Don't pre-fill it.

## 10. Verification

After writing or editing `CLAUDE.md`, ask:

- [ ] Could a competent contributor pick up a real task with only
      this file as context, without asking questions?
- [ ] Is every line load-bearing — would removing it cost the agent
      time on a real task?
- [ ] Is the file under the length budget (under 300, ideally under 200)?
- [ ] Are all commands exact and runnable?
- [ ] Are all file paths absolute from repo root?
- [ ] Does it link to deeper docs rather than embedding them?
- [ ] Did I auto-generate any part of it? (If yes — rewrite by hand.)
- [ ] Did I put a code-style rule in it? (If yes — move to the linter.)

If every box is ticked, the file is doing its job.

## 11. Companion files in this repo

- `agent-Creator.md` — counterpart for `AGENTS.md` (cross-tool standard)
- `WORKFLOW.md` — the long-form per-phase task list this project follows
- `SKILL.md` — high-level project rules + current state (separate from
  CLAUDE.md; QuantRank-specific historical doc)
- `.claude/skills/` — invocation-triggerable skills loaded at session start

## Sources

- [Anthropic Claude Code docs](https://code.claude.com/docs/en/overview)
- [Anthropic Claude API docs](https://platform.claude.com/docs/en/home)
- [Humanlayer — Writing a good CLAUDE.md](https://www.humanlayer.dev/blog/writing-a-good-claude-md)
