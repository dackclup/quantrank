# agent-Creator.md — a guide for writing a great `AGENTS.md`

> **Use this guide whenever you're about to author, edit, or audit
> an `AGENTS.md` for a project.** It compresses the consensus from
> the official open spec at [agents.md](https://agents.md/),
> GitHub's empirical write-up of 2,500+ repositories
> ([github.blog](https://github.blog/ai-and-ml/github-copilot/how-to-write-a-great-agents-md-lessons-from-over-2500-repositories/)),
> and the agentskills.io community resources into one actionable
> reference.

## 1. What AGENTS.md is (and why it's not CLAUDE.md)

`AGENTS.md` is the **cross-tool open standard** for agent
instructions. It is stewarded by the Agentic AI Foundation (a Linux
Foundation project) and read by 20+ coding agents at the time of
writing — Claude Code, GitHub Copilot, Cursor, Devin, VS Code Agent
Mode, OpenHands, Replit, and others.

`AGENTS.md` is to AI agents what `README.md` is to humans: the entry
point. If you're going to write one file that every coding agent
will reach for, write `AGENTS.md`.

| Compare with | Difference |
|---|---|
| `CLAUDE.md` | Anthropic-specific. Auto-loaded only by Claude Code. See `claude-Creator.md`. |
| `.cursorrules` | Cursor IDE only. |
| `.github/copilot-instructions.md` | GitHub Copilot only. |
| `README.md` | For humans. AGENTS.md is for agents. |

**You can keep both `CLAUDE.md` and `AGENTS.md`.** They have
distinct roles: `AGENTS.md` is the procedural / technical handshake
that every agent reads; `CLAUDE.md` is the project-bound persistent
memory specific to Claude Code sessions.

## 2. The six sections every great AGENTS.md has

GitHub's empirical study of 2,500+ repos found a consistent
six-section spine in the high-performing ones:

1. **Commands** — exact, executable commands with flags
2. **Testing** — framework + invocation + coverage policy
3. **Project structure** — where files live + read/write permissions
4. **Code style** — concrete examples (not prose)
5. **Git workflow** — commit / branch / PR conventions
6. **Boundaries** — ✅ Always / ⚠️ Ask first / 🚫 Never

If your `AGENTS.md` has all six, you're already ahead of most repos
in the dataset.

Optional add-ons used by mature projects:
- Security considerations (secrets handling, sandbox policy)
- Deployment steps
- Tech stack with versions (one block, top of file)
- Environment setup (one-time, e.g., env vars)

## 3. Writing style

- **Imperative form.** "Use TypeScript", "Run `npm test --coverage`",
  not "we recommend using TypeScript" or "tests are run via npm".
- **Specificity over abstraction.** Tech stack with versions
  (`React 18, TypeScript 5.4, Vite 5.2`) beats "a React project".
  Specific exact commands (`pytest -v -m "not network" --durations=20`)
  beat "run tests".
- **One code snippet > three paragraphs.** Show ✅ Good vs ❌ Bad code
  side-by-side rather than describing conventions in prose.

> **"One real code snippet showing your style beats three paragraphs
> describing it."** — GitHub blog (2,500-repo study)

- **YAML frontmatter (optional).** A minimal `--- name + description ---`
  block at the top helps some agent tools index the file. Not
  required by the spec.
- **Use ✅ ⚠️ 🚫 markers for boundaries.** Visual scanability matters
  for the most-read section.

## 4. The Commands section

This is the highest-leverage section. Every agent reading
`AGENTS.md` runs commands; vague commands waste agent time and
produce errors.

Format as a small table or list with exact strings:

```markdown
## Commands

| Action | Command |
|---|---|
| Install | `pnpm install` |
| Build | `pnpm build` |
| Dev server | `pnpm dev` |
| Test (unit) | `pnpm test` |
| Test (with coverage) | `pnpm test --coverage` |
| Test (e2e) | `pnpm test:e2e` |
| Lint | `pnpm lint` |
| Format | `pnpm format` |
| Type-check | `pnpm typecheck` |
```

Anti-patterns to avoid:

- "Use the test framework" — name it (Jest, PyTest, Vitest)
- "Run the tests" — give the exact command + relevant flags
- "Install dependencies" — name the tool (`pnpm install`, not "install")

## 5. The Boundaries section

The three-tier `✅ / ⚠️ / 🚫` system appears in every
high-performing `AGENTS.md` in the GitHub study. Without it, agents
make destructive mistakes (touching secrets, vendor directories,
production configs).

```markdown
## Boundaries

### ✅ Always OK

- Read any file under `src/`, `tests/`, `docs/`
- Write to `src/`, `tests/`, `docs/`
- Run linting, formatting, type-checking
- Commit code to a topic branch
- Open a draft PR

### ⚠️ Ask first

- Schema changes (`schemas.py`, `types.ts`)
- Dependency additions to `package.json` or `pyproject.toml`
- Database migrations
- CI/CD workflow file edits
- Force-pushing to any branch

### 🚫 Never

- Touch `.env`, `.env.local`, or any file matching `*.secret.*`
- Modify files under `node_modules/`, `vendor/`, `dist/`, `build/`
- Commit API keys, tokens, or passwords (even temporarily)
- Push directly to `main` or `release/*`
- Run `rm -rf` against any tracked directory
- Skip pre-commit hooks (`--no-verify`)
```

The list above is illustrative — adapt to your repo. The point is
the structure: explicit verbs, no ambiguity.

## 6. The Code style section (with examples)

```markdown
## Code style

### TypeScript

✅ Good:
\```ts
async function fetchUser(id: string): Promise<User | null> {
  const response = await fetch(`/api/users/${id}`);
  if (!response.ok) return null;
  return response.json();
}
\```

❌ Avoid:
\```ts
async function fetchUser(id) {
  const r = await fetch('/api/users/' + id);
  return r.json();  // crashes on 404
}
\```

Conventions:
- camelCase functions, PascalCase types, CONSTANT_CASE enums
- Return `T | null` over throwing on expected misses
- Use template literals for path interpolation
- Always check `response.ok` before `.json()`
```

Anti-pattern: a prose list of "we prefer camelCase, we use Promise
returns, we don't throw…". Skipped by agents; show the code.

## 7. The Project structure section

```markdown
## Project structure

\```
src/
├── components/        # React components (read/write OK)
├── lib/              # Pure utilities (read/write OK)
├── api/              # Server routes (read/write OK; ⚠️ schemas)
├── styles/           # Tailwind config (read OK; ⚠️ writes)
└── types/            # Shared TS types (⚠️ mirrors backend)

tests/                # All test files (write OK)
docs/                 # Documentation (write OK)
scripts/              # Build scripts (⚠️ ask before editing)
\```

Forbidden directories: `node_modules/`, `.next/`, `dist/`,
`coverage/`. Never edit, never commit.
```

Annotate read/write/⚠️ inline. Saves an agent the round-trip of
asking "is this file safe to edit?"

## 8. Length budget

| Range | Verdict |
|---|---|
| **< 100 lines** | Likely too sparse — add the six sections |
| **100-400 lines** | Sweet spot for most repos |
| **400-800 lines** | Healthy ceiling for mature projects |
| **> 800 lines** | Split. Link out to `docs/` for deep dives. |

GitHub's study explicitly recommends:

> **"Begin with single, constrained task (documentation writing,
> linting, test creation) rather than general-purpose assistants.
> Iterate based on agent mistakes rather than attempting
> comprehensive upfront documentation."** — GitHub blog

Start narrow. Watch where agents stumble. Add to `AGENTS.md` only
when a stumble happens twice.

## 9. Nested AGENTS.md in monorepos

Agents read the **nearest** `AGENTS.md` walking up from the file
they're editing. So a monorepo can have:

```
/AGENTS.md                  # Universals — git workflow, top-level boundaries
/frontend/AGENTS.md         # Frontend-specific commands + style
/backend/AGENTS.md          # Backend-specific commands + style
/infra/AGENTS.md            # Infra: ⚠️ + 🚫 are stricter
```

Each child overrides specific sections of the parent without
duplicating universals. Keep the root `AGENTS.md` thin and let
children be specific.

## 10. Anti-patterns (from the 2,500-repo dataset)

| Anti-pattern | Why it fails | Fix |
|---|---|---|
| Vague personas ("helpful coding assistant") | Adds no signal; agents ignore | Delete or replace with role-specific ("quality engineer writing unit tests") |
| Generic tool names ("use the testing framework") | Agent has to guess | Name it: Jest, PyTest, Vitest, with the exact flag set |
| Missing file structure | Agents create files in wrong locations | Add the structure section with read/write annotations |
| No code-style examples | Agents produce inconsistent style | Show ✅ vs ❌ code blocks |
| Undefined or absent boundaries | Agents touch secrets, vendor code, prod configs | Always include the three-tier `✅ / ⚠️ / 🚫` |
| Overly comprehensive upfront documentation | Pollutes context, never gets read end-to-end | Start narrow; iterate on observed mistakes |

## 11. Authoring workflow

1. **Start with a single constrained task.** Pick one thing your
   agent should do well (write a test, lint a module, generate
   docs). Draft `AGENTS.md` for that task only.
2. **Add the six-section skeleton.** Commands, Testing, Project
   structure, Code style, Git workflow, Boundaries. Fill what you
   know; mark unknowns "TBD".
3. **Run an agent against a real task.** Observe where it stumbles.
4. **Add to `AGENTS.md` only when a stumble repeats.** First
   mistake = noise. Second mistake = pattern. Add then.
5. **Iterate, don't pre-empt.** Most failed `AGENTS.md` files in
   the GitHub dataset failed by over-specifying upfront.

## 12. Coexistence with CLAUDE.md

| File | Loaded by | Role |
|---|---|---|
| `AGENTS.md` | 20+ agent tools (Claude, Copilot, Cursor, …) | Procedural — commands, structure, boundaries, code style. Cross-tool. |
| `CLAUDE.md` | Claude Code only (auto-loaded each session) | Project-bound persistent memory specific to Claude Code workflows |

**Recommendation:** keep both. Don't symlink. They have distinct
purposes. `AGENTS.md` is the broader, more shareable handshake;
`CLAUDE.md` is Claude-specific refinement.

Cross-reference from each:

```markdown
# AGENTS.md
> Claude Code users: see `CLAUDE.md` for Anthropic-specific session context.

# CLAUDE.md
> See `AGENTS.md` for cross-tool agent instructions (commands,
> boundaries, code style).
```

## 13. Minimum-viable template

```markdown
# AGENTS.md

<one-paragraph project summary + the agent's expected role>

## Tech stack

- <Lang + version>
- <Framework + version>
- <Key libs: 3-5 max>

## Commands

| Action | Command |
|---|---|
| Install | `<cmd>` |
| Build | `<cmd>` |
| Test | `<cmd + flags>` |
| Lint | `<cmd>` |

## Project structure

\```
<dir tree with read/write/⚠️ annotations>
\```

## Code style

✅ Good:
\```<lang>
<example snippet>
\```

❌ Avoid:
\```<lang>
<anti-example snippet>
\```

## Git workflow

- Branch from `main` with `<type>/<short-desc>` naming
- Commit format: `<type>(scope): <summary>`
- Open draft PRs first; ask before flipping Ready

## Boundaries

### ✅ Always OK
- <list>

### ⚠️ Ask first
- <list>

### 🚫 Never
- <list>
```

100-150 lines once filled. Grow from there.

## 14. Verification

After writing or editing `AGENTS.md`, ask:

- [ ] Do all six sections exist (Commands, Testing, Structure, Style, Git, Boundaries)?
- [ ] Are commands exact and runnable (no "the test framework")?
- [ ] Is the tech stack listed with **versions**?
- [ ] Does the Code style section show **example code** (not prose)?
- [ ] Does the Boundaries section have ✅ / ⚠️ / 🚫 tiers?
- [ ] Is the file under the length budget (under 800 for most repos)?
- [ ] Have I started narrow and let usage drive growth, or did I
      pre-emptively write everything?

## 15. Companion files in this repo

- `.claude/skills/claude-Creator.md` — counterpart guide for `CLAUDE.md`
- `.claude/skills/README.md` — index of loaded skills + planning docs
- `/WORKFLOW.md` — long-form per-phase task list
- `/SKILL.md` — high-level project rules + state
- `.claude/skills/<name>/SKILL.md` — Claude-specific invocation-triggerable skills

## Sources

- [agents.md — official open spec](https://agents.md/)
- [GitHub blog — How to write a great AGENTS.md (2,500 repos)](https://github.blog/ai-and-ml/github-copilot/how-to-write-a-great-agents-md-lessons-from-over-2500-repositories/)
- [agentskills.io](https://agentskills.io/home)
