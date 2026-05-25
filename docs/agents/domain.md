# Domain Docs — QuantRank adaptation

How the engineering skills should consume QuantRank's domain
documentation when exploring the codebase.

## QuantRank has NO `CONTEXT.md`

Upstream mattpocock skills assume a single `CONTEXT.md` at the repo root
that serves as both glossary and decision-log entry point. QuantRank's
domain language is instead distributed across **four canonical doc
files** that pre-date this skill scaffold:

| File | Owns |
|---|---|
| [`CLAUDE.md`](../../CLAUDE.md) | Stack, layout, conventions, commands, gotchas, phase status |
| [`docs/METHODOLOGY.md`](../METHODOLOGY.md) | Academic priors per defense flag, citation anchors, threshold provenance tiers (literature-anchored / gut-feel / reserved) |
| [`SKILL.md`](../../SKILL.md) | Rules 1-18, schema-version table, library matrix, long-form rulebook |
| [`WORKFLOW.md`](../../WORKFLOW.md) | Per-phase task lists, decision points |

When a skill instruction says **"read `CONTEXT.md` before exploring"**,
interpret it as **"read whichever of the four files above is relevant to
the topic"**. Rough mapping:

| Topic | Read |
|---|---|
| Naming a new defense flag / risk_flag | METHODOLOGY.md (academic prior), SKILL.md (Rule 16 annotate-before-veto) |
| Touching scoring or valuation math | METHODOLOGY.md (anchor paper), SKILL.md (Rules), WORKFLOW.md (phase the change belongs to) |
| Touching schema fields | SKILL.md (schema-version table), CLAUDE.md (§Conventions schema triple) |
| Touching frontend / UI | CLAUDE.md (§Stack + design system), `docs/design.md` (visual spec) |
| Cron / observability / Rule 18 | SKILL.md (Rule 18), CLAUDE.md (§Gotchas) |
| Anything cross-cutting | Start with CLAUDE.md as the index; it points at the deep file |

If a skill instruction says **"update `CONTEXT.md` inline when a term
resolves"**, interpret it as **"update the most appropriate of the four
files above based on the term's nature"**:

- **Gotcha / project-specific bug pattern** → CLAUDE.md §Gotchas
- **Academic methodology term** → METHODOLOGY.md (with citation)
- **Project invariant / rule** → SKILL.md Rules 1-18
- **Phase / sub-PR scope** → WORKFLOW.md

The four files are NOT a glossary in the strict mattpocock sense (no
canonical "term → one sentence definition + avoid: X" structure). They
are a layered set of long-form docs. If a skill complains, the
adaptation note in `.claude/skills/mattpocock-grill-with-docs/SKILL.md`
trailer explains the divergence.

## QuantRank has NO `docs/adr/0001-*.md` files

Upstream mattpocock skills create sequentially-numbered ADRs under
`docs/adr/`. QuantRank's ADR analog is
[`PHASE_STATUS_INFLIGHT.md`](../../PHASE_STATUS_INFLIGHT.md) — an
**append-only side-file** documenting in-flight + recently-merged PR
decisions, including the architectural trade-offs typically captured by
ADRs.

**Why the divergence**: parallel PRs both inserting a "**X in flight
(this PR)**" bullet at the same anchor line in CLAUDE.md §Phase status
caused recurring `mergeable_state: dirty` collisions (PR #230 hit the
pattern 3 times in one session). Adopting `PHASE_STATUS_INFLIGHT.md` in
PR #237 closed the structural conflict at the file boundary. See
`CLAUDE.md` §Gotchas "Parallel-PR §Phase status collision pattern" for
the full incident chain.

When a skill instruction says **"create an ADR"**, interpret it as
**"append an in-flight PR entry to `PHASE_STATUS_INFLIGHT.md`"**.
Decision content follows the same shape as a Michael Nygard ADR (status,
context, decision, consequences) but lives inline with the PR scope.

When a skill instruction says **"read existing ADRs in `docs/adr/`"**,
interpret it as **"read the relevant sections of
`PHASE_STATUS_INFLIGHT.md` + CLAUDE.md §Phase status (the merged
historical record)"**.

## Layout marker

QuantRank declares as **single-context** for the upstream skill's
binary single-vs-multi-context check (no `CONTEXT-MAP.md`); the
"single context" is the entire 502-ticker S&P 500 ranking pipeline.
There is no monorepo subdivision.

The single context is just multi-FILE rather than single-FILE — the
distinction is internal to the docs surface, not external to the
skill's choice axis.

## Use the project vocabulary

When skill output names a domain concept (in an issue title, a refactor
proposal, a hypothesis, a test name), use the term as canonicalized in
the four-file CONTEXT analog. Examples:

- Use "**annotate-only**" (not "advisory flag") — Rule 16
- Use "**veto**" (not "rejection" / "exclusion") — Rule 16
- Use "**Tier-2 defense**" (not "secondary scoring layer") — METHODOLOGY.md
- Use "**schema triple**" (not "type contract") — §Conventions
- Use "**Rule 18**" (not "observability discipline") — SKILL.md
- Use "**dimensional override**" (PR #257) — for multi-class XBRL recovery
- Use "**S&P 500 universe**" (502 tickers, not 500) — §Phase status

## Flag conflicts with the project's existing decisions

If skill output contradicts an existing decision in the four-file
CONTEXT analog or in PHASE_STATUS_INFLIGHT.md, surface the conflict
explicitly:

> _Contradicts CLAUDE.md §Conventions schema triple — but worth
> reopening because…_

Same for methodology priors in METHODOLOGY.md (the canonical
paper-anchor list is non-trivially expensive to revisit) and the
schema-version chain in SKILL.md.
