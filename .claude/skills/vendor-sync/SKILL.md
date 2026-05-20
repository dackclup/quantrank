---
name: vendor-sync
description: Pull updates from each vendored upstream source (mattpocock/skills, multica-ai/andrej-karpathy-skills, karpathy gist, 9arm-skills) and reconcile with QuantRank's local copies — including the post-PR-#157 description-divergence resolution policy. TRIGGER when the user explicitly says "vendor sync", "sync upstream skills", "update vendored skills", "pull mattpocock updates", "refresh vendored sources", or names a specific upstream source plus "sync". ALSO trigger on quarterly cadence (≥ 6 months since the last `Vendored date` in `THIRD_PARTY_NOTICES.md`), when a security advisory affects an upstream source, or when CLAUDE.md / SKILL.md cite an upstream-fixed bug. SKIP for one-off edits to a single vendored file (use Edit directly) and for non-vendored project skills (`schema-check`, `pr-iteration-flow`, etc. — those are first-party and have no upstream).
---

# Vendor Sync

QuantRank vendors third-party Claude Code skills from 4 upstream
sources. Bodies are kept upstream-verbatim plus a 10-line
`## License + Attribution` block; the YAML frontmatter `description:`
line for 5 mattpocock-* skills diverges from upstream per PR #157
("Description divergence" section in `THIRD_PARTY_NOTICES.md`). This
skill is the disciplined sync workflow that keeps the vendored copies
fresh without losing the local divergence work.

## Vendored sources (4)

| Source | Local prefix | License | Upstream type |
|---|---|---|---|
| [`mattpocock/skills`](https://github.com/mattpocock/skills) | `mattpocock-*` (8 skills) | MIT | GitHub repo, commit-SHA pinnable |
| [`multica-ai/andrej-karpathy-skills`](https://github.com/multica-ai/andrej-karpathy-skills) | `portable-karpathy-guidelines` (1 skill) | MIT | GitHub repo, commit-SHA pinnable |
| [Karpathy LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) | `karpathy-llm-wiki` (1 skill) | NONE DECLARED (in-text copy permission) | gist, date-pinnable only |
| `9arm-skills` (LICENSE PENDING upstream) | `9arm-*` (4 skills) | PENDING | gist or repo, license-blocked |

Authoritative metadata for each source (commit SHA, vendored date,
in-scope files) lives in
[`THIRD_PARTY_NOTICES.md`](../../THIRD_PARTY_NOTICES.md). Always
re-read that file at the start of a sync — it's the source of truth
for what was last pulled.

## Process

### 1. Pick the scope

A sync should land as ONE PR per upstream source — don't bundle
mattpocock + karpathy in the same PR. Reasons: easier merge-conflict
resolution, cleaner attribution in the commit log, and each upstream
has its own license-block change risk.

Ask the user which source to sync first if they haven't named one.

### 2. Diff the upstream against the last vendored SHA

For repo-based sources (`mattpocock/skills`, `multica-ai/andrej-karpathy-skills`):

```bash
git clone --depth=100 <upstream_url> /tmp/<source>-upstream
cd /tmp/<source>-upstream
git log --oneline <vendored_SHA>..HEAD
git diff <vendored_SHA>..HEAD -- <in_scope_paths>
```

The vendored SHA + in-scope paths are listed in
`THIRD_PARTY_NOTICES.md` under each source's "Upstream commit SHA"
and "Vendored skills" rows.

For gist-based sources (Karpathy LLM Wiki): no SHA — diff against the
last-vendored date by fetching the gist via `WebFetch` and comparing
prose blocks. Smaller surface area, often unchanged.

### 3. Classify each upstream change

For each diff hunk:

| Change kind | Action |
|---|---|
| New behavior in skill body | Apply verbatim — bodies stay upstream-verbatim |
| Bug fix in skill body | Apply verbatim |
| Upstream changes the `description:` line of a skill we have NOT diverged | Apply verbatim |
| Upstream changes the `description:` line of a skill we HAVE diverged (the 5 mattpocock-* listed in `THIRD_PARTY_NOTICES.md` "Description divergence") | **See "Description divergence resolution policy" below** |
| Upstream adds a NEW skill | Check selection criteria (language-agnostic, project-applicable) — if accepted, vendor it; if rejected, note in PR description |
| Upstream removes a skill we vendor | Remove the local copy; note removal in PR description and update `Vendored skills` row |
| Upstream changes license | **STOP** — license change requires a separate license-review PR; do not bundle into a sync |

### 4. Description divergence resolution policy (5 mattpocock-* skills)

These 5 local descriptions are sharper than upstream after PR #157:

- `mattpocock-grill-me`
- `mattpocock-tdd`
- `mattpocock-to-prd`
- `mattpocock-to-issues`
- `mattpocock-write-a-skill`

When upstream changes the `description:` line of any of these:

1. **If upstream ALSO adopted explicit `TRIGGER when ...` syntax** — take upstream's wording as the new baseline, then re-evaluate sharp-keyword coverage against the project's false-positive history. Re-apply local sharpening if upstream's keywords are too broad.
2. **If upstream still uses `Use when user wants ...` pattern** — keep the local sharpened description; record the upstream wording in the PR description's "Divergence preserved" section so the next sync can see what was rejected.
3. **If upstream changes the underlying behavior** — apply the body change verbatim, then audit whether the local description still matches the new behavior. If behavior changed (e.g., new sub-workflow added), the trigger keywords may need to expand.

The principle: **local sharpness wins on description; upstream wins on body**.

### 5. Update THIRD_PARTY_NOTICES.md

After applying changes, update for the synced source:

- `Upstream commit SHA` → new SHA (or new gist date for Karpathy)
- `Vendored date` → today's date
- If skills were added/removed: update the `Vendored skills` enumeration + the "X of Y upstream skills selected" count
- If new divergences appeared (e.g., a body customization the team agreed to keep): add a row to the "Description divergence" or new "Body divergence" subsection

Run a final sanity-check:

```bash
grep -c "^- \`.claude/skills/" THIRD_PARTY_NOTICES.md
ls -1 .claude/skills/mattpocock-* | wc -l
```

The counts should agree with the "Vendored skills" enumeration.

### 6. Verification ladder

Vendor syncs touch markdown only — the standard CI ladder applies:

```
ruff check .                              # no-op, no Python touched
pytest tests/ -m "not network"            # no-op, no Python touched
cd frontend && npx --no -- tsc --noEmit   # no-op, no TS touched
cd frontend && npx --no -- next build     # no-op, no TS touched
```

CI is a smoke-test for any accidental non-markdown change. The
qualitative check is reading the diff: every change should be either
in `.claude/skills/<vendored>/SKILL.md`, a sidecar `.md`, or
`THIRD_PARTY_NOTICES.md`.

### 7. CLAUDE.md + AGENTS.md lockstep

Per the "ship with every PR" rule, vendor-sync PRs need a small
lockstep note even though they don't touch compute or schemas. Add a
single line to each:

- `CLAUDE.md` §Phase status — "Vendor sync `<source>` (`<old_sha>` → `<new_sha>`) in flight"
- `AGENTS.md` §Phase + version state — same one-line note

After merge, the lockstep entry can be removed in the next routine
CLAUDE.md update.

### 8. Open the PR

Open as Draft with title format:
`chore(skills): vendor-sync <source> (<old_sha[:7]> → <new_sha[:7]>)`

PR body sections:
- **Summary** — source synced, commit range, file count
- **Changes applied** — per skill, classify each change kind from step 3
- **Divergence preserved** — for any mattpocock-* description-divergence preservation per step 4.2
- **Skills added / removed** — if applicable
- **Test plan** — checkboxes for CI passes + the qualitative diff scan

## Source-specific notes

### `mattpocock/skills`

- Upstream's `LICENSE` file at repo root governs all vendored skills
- Verbatim policy enforced via a CI-time grep (planned): comparing
  body byte-count vs upstream
- 5 sharp-trigger descriptions per PR #157 — see step 4

### `multica-ai/andrej-karpathy-skills`

- Smaller surface (1 skill); syncs are usually trivial
- Watch for license declaration changes — upstream had no standalone
  `LICENSE` file at 2026-05-20 vendoring; if upstream adds one,
  reproduce the new text in `THIRD_PARTY_NOTICES.md`

### Karpathy LLM Wiki (gist)

- No upstream SHA — date-pin only via `Vendored date` + `Vendored revision`
- If Karpathy adds a formal LICENSE block to the gist (or repos the
  content elsewhere with a license), update `THIRD_PARTY_NOTICES.md`
  attribution block + the SKILL.md frontmatter
- Pattern doc, not a triggered behavioral skill — sync cadence can be
  much lower (yearly OK)

### `9arm-skills` (LICENSE PENDING)

- Currently blocked on upstream license declaration
- Sync = re-check upstream for a `LICENSE` file. If present, replace
  the "LICENSE PENDING" block in `THIRD_PARTY_NOTICES.md` with the
  proper provenance block (model on the karpathy / mattpocock entries)
- Do NOT add new 9arm-* skills until license is declared

## Verification + post-merge

Per `pr-iteration-flow`: open as Draft, subscribe to CI, run the
verification ladder, then flip to Ready after the user approves the
divergence-preservation calls. After merge, the next vendor sync of
the same source uses today's new SHA as the baseline — that's the
audit trail working as designed.

## Why not auto-PR upstream syncs?

A daily/weekly bot could open auto-syncs, but the description-
divergence resolution (step 4) needs human judgment — keep this as
an on-demand workflow until the divergence policy stabilizes (after
≥ 2 manual sync cycles validate the policy works in practice).
