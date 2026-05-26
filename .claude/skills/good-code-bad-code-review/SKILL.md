---
name: good-code-bad-code-review
description: Reference catalog of paired good/bad code-review examples by Miler (milerdev) at <https://good-code-bad-code.pages.dev/> — 18 language/framework tracks × 10 examples each, side-by-side comparative review patterns. TRIGGER when reviewing non-trivial Python / TypeScript / React / Next.js / Tailwind / Git code (the QuantRank-relevant tracks) and wanting a generic-language idiom sanity-check, when the user says "is this idiomatic" / "is this Pythonic" / "is this good code" / "review this function" / "any code-smells" / "ดู code นี้ดีมั้ย", or as a complementary reference alongside `quantrank-reviewer` (which owns project-specific invariants — this skill covers generic-language idioms). SKIP for non-code-review tasks, for tracks not used by QuantRank (PHP / Java / Go / Express / Django / FastAPI / SQL / Docker / HTML / CSS-without-Tailwind / Node.js-server-side — QuantRank ships static-export only), and for trivial diffs (single-line / pure rename / typo fix).
license: REFERENCE LINK ONLY — no content vendored; see THIRD_PARTY_NOTICES.md § good-code-bad-code-review for attribution + posture
---

# Good Code / Bad Code review patterns

> **Source**: <https://good-code-bad-code.pages.dev/>
> **Author**: Miler (`milerdev`)
> **Methodology**: paired side-by-side examples ("bad" → "good") across 18 tracks of 10 examples each (~180 total reviews)
> **Tagline (verbatim from site)**: *"Study code review patterns through curated side-by-side examples"* · *"Side-by-side code review examples for developers who want sharper review instincts"*

## What this skill does

This is a **reference-catalog skill**, not a behavioral skill. It does NOT carry a procedural workflow to execute — it tells the agent **where to look** for a curated good/bad comparison when a code-review judgement call surfaces in a language the resource covers.

**The skill's job** when invoked:

1. Identify which of the 18 tracks matches the code under review
2. WebFetch the relevant track index (`/tracks/<track-name>`) OR a specific example URL (`/tracks/<track-name>/<example-slug>`) to pull the canonical paired example
3. Apply the pattern to the current review with project-specific judgement
4. Cite the example URL inline in the review report when it influences a verdict

**The skill's job** is NOT:

- Replace `quantrank-reviewer` (project-invariant owner) — they're complementary; `quantrank-reviewer` enforces Rules 1-18 + schema triple + tenacity policy + project-specific patterns; this skill provides a generic-language idiom reference
- Vendor or cache the 180 examples locally — content is web-only; lazy-fetch on demand
- Fire on every diff — only when an idiom judgement actually arises in a covered language

## QuantRank-relevant tracks (use these)

QuantRank's stack maps to these tracks specifically:

| Track | URL | When to consult |
|---|---|---|
| **Python** | `/tracks/python` | All `compute/**/*.py` review — fundamentals ingest, scoring, valuation, output writers, tests |
| **TypeScript** | `/tracks/typescript` | `frontend/lib/types.ts`, `frontend/lib/schema-snapshot.json` adjacent typing work |
| **React** | `/tracks/react` | `frontend/components/**/*.tsx` review — RankingTable, FairPriceCard, ScoreBadge, PillarRadarChart, etc. |
| **Next.js** | `/tracks/nextjs` | `frontend/app/**/*.tsx` review — App Router pages, static-export discipline, layout |
| **Tailwind CSS** | `/tracks/tailwindcss` | Token usage, utility composition, dark-mode variants, responsive layout review (LedgerCraft palette + chip family discipline) |
| **Git** | `/tracks/git` | Workflow review — commit hygiene, branch discipline, rebase-before-mark-ready (CLAUDE.md §Conventions) |

## Tracks to SKIP (not in QuantRank stack)

These tracks describe stacks QuantRank does NOT use; don't consult them:

`HTML` · `CSS` (raw, sans Tailwind) · `JavaScript` (project uses TS exclusively) · `Node.js` (no server-side runtime — static export only) · `Express` · `SQL` (no DB; static JSON) · `PHP` · `Java` · `FastAPI` · `Django` · `Go` · `Docker` (no Dockerfile in the project)

If a future PR adds any of these (e.g., a real backend), update this skip-list before consulting them.

## Per-track topic indexes (quick reference)

So the agent knows which slug to deep-link without re-fetching the whole site each time:

### Python (`/tracks/python/<slug>`)

1. `naming-and-readability` — clarity of identifiers + reading order
2. `truthy-falsy-and-none-checks` — `is None` vs `== None` vs falsy
3. `mutable-default-arguments` — `def f(x=[]):` footgun
4. `list-and-dict-comprehensions` — vs `for`-loop with `.append()`
5. `exception-boundaries` — catch where you can act, not where it's tempting
6. `context-managers-for-files` — `with open(...)` discipline
7. `dataclasses-for-data-shapes` — Pydantic / `@dataclass` vs raw tuples
8. `type-hints-at-boundaries` — annotate public functions + module surfaces
9. `dependency-injection-for-testability` — pass dependencies in, not import-bind
10. `async-and-await-boundaries` — sync inside async, async leaking up

### TypeScript (`/tracks/typescript/<slug>`)

Topics: Type narrowing · API boundaries · Discriminated unions · Safer function shapes · (full slug list to populate on first WebFetch — exact slugs are upstream-controlled and may evolve)

### React (`/tracks/react/<slug>`)

Topics: Component boundaries · State · Effects · Rendering decisions

### Next.js (`/tracks/nextjs/<slug>`)

Topics: App Router structure · Server boundaries · Data fetching · Route APIs

### Tailwind CSS (`/tracks/tailwindcss/<slug>`)

Topics: Utility composition · Responsive variants · States · Theme tokens · Dark mode · Reuse boundaries · Accessibility · Class conflicts

### Git (`/tracks/git/<slug>`)

Topics: Status checks · Staging · Commits · Branches · Sync workflows · Diffs · Conflicts · History safety · Ignores · Release tags

## Invocation pattern

When a code-review judgement arises in a covered language:

```text
1. Match the language → pick the track slug from the table above
2. WebFetch <https://good-code-bad-code.pages.dev/tracks/<track>>
   prompt: "list the 10 example slugs + a one-line summary of each"
3. Identify the example most relevant to the current judgement
4. WebFetch <https://good-code-bad-code.pages.dev/tracks/<track>/<slug>>
   prompt: "show the bad version, good version, and the commentary explaining
            why the change matters"
5. Apply the pattern to the current code under review
6. Cite the example URL in the review write-up (e.g., "per Miler's
   `tracks/python/exception-boundaries`, narrow except to the caller").
```

## Hard constraints

- **DO NOT vendor the content** — the site has no declared license; quoting verbatim from individual examples is acceptable for citation + critique under fair use, but **wholesale copying of multiple examples into project files is not authorized** by the upstream
- **DO NOT block on this skill if WebFetch fails** — the patterns described are well-known idioms across the language community; if the live site is unreachable, fall back to `portable-karpathy-guidelines` (general code quality) + project-internal SKILL.md rules + the agent's own training
- **DO NOT override `quantrank-reviewer` findings** with generic-language idioms — when the project-specific Rule 16 / schema triple / tenacity policy / annotate-before-veto discipline conflicts with a generic idiom, the project rule wins
- **DO NOT fire on trivial diffs** — single-line fixes, pure renames, typo corrections don't need a curated-example reference; cite only when an idiom judgement materially affects the review verdict
- **DO NOT mistake this skill for a behavioral workflow** — it's a reference catalog; no procedural steps to follow other than the lookup pattern above

## Companion skills (when to prefer which)

- **`code-review`** (built-in) — when the user wants the standard diff-correctness scan with effort levels (low/medium/high/max). This skill **complements** that — once the diff is identified as touching a covered language, this skill provides the idiom-reference layer
- **`quantrank-reviewer` (agent)** — when the review must enforce the project's specific invariants (Rules 1-18, schema triple, annotate-before-veto, tenacity policy, design-token palette). Spawn the agent for full project-context review; consult this skill for orthogonal generic-language sanity-checks the agent's invariants don't cover
- **`portable-karpathy-guidelines`** (vendored) — generic behavioral guidelines for the agent's own code-writing. Use that one to AVOID writing bad code in the first place; use THIS one to CATCH bad code during review

## Attribution

This skill links to a third-party resource. See
[`THIRD_PARTY_NOTICES.md` § good-code-bad-code-review](../../../THIRD_PARTY_NOTICES.md)
for the license posture (no declared license; reference-link only;
no content vendored).

## Maintenance

- **Resource health check** — re-confirm the home page resolves
  (`<https://good-code-bad-code.pages.dev/>`) at quarterly cohort
  audits (next 2026-08-19). If the resource is gone, mark the skill
  STALE or remove it.
- **Track list drift** — Miler may add / rename tracks. If a track on
  the table above 404s during a review, WebFetch the home page first
  to refresh the catalog before deep-linking.
- **License declaration** — if Miler later adds a LICENSE to the
  resource, update `THIRD_PARTY_NOTICES.md` § good-code-bad-code-review
  to reflect the formal terms. The reference-link posture changes
  little either way (no content is currently vendored), but full
  example quoting may become permissible under an explicit MIT / CC
  declaration.
