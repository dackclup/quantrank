---
name: release-tag
description: Cut a versioned release for a QuantRank phase-completion PR — bump `pyproject.toml` version, write release notes from the merged-PR log, tag `vX.Y.Z-phase<N>`, push the tag, and create the GitHub release. Codifies the project's release convention so the next release doesn't have to re-derive it. TRIGGER when the user explicitly says "tag release", "cut a release", "release v1.X.Y", "release notes for phase X", "ship the release", "make a tag", or "bump version", and after merging any PR that closes a phase (epic #150 Phase 1 complete, Phase 4.5e ships, etc.). ALSO trigger when the user names a specific version string (e.g., "v1.3.0-phase4.5e") in a context that suggests cutting a release. SKIP for in-flight PRs that haven't merged yet (release tags lag the merge by at least the time it takes to verify the post-merge compute output), for hotfix / patch releases that don't close a phase boundary (those can ship under the existing tag), and for re-running a release that already exists (use `git tag --list` to check first).
---

# Release Tag Workflow

QuantRank releases at phase boundaries. The most recent tag is
`v1.2.0-phase4.5` (2026-05-17, `6d414a9b`). Tag cadence is roughly
1-3 weeks, matching the phase-completion rhythm. This skill is the
end-to-end release workflow so the next release doesn't have to
re-derive the convention from looking at the last tag.

## Versioning convention

Format: `v<major>.<minor>.<patch>-phase<N>[<suffix>]`

- **major** — bumps on breaking schema changes that aren't behind a
  migration (rare; currently `1` since v1.0.0-phase3e)
- **minor** — bumps on substantial new features (new defense layer,
  new pillar, new fair-price method)
- **patch** — bumps on bug fixes + non-breaking refinements
- **phase** suffix — the QuantRank phase that closed with this
  release. Pulled from `CLAUDE.md` §Phase status + epic issue numbers

Examples in the wild:
- `v1.0.0-phase3e` — initial release after Phase 3 closed
- `v1.2.0-phase4.5` — Phase 4.5 closed; minor bump for the 5 new
  active vetoes
- `v1.3.0-phase4.5e` (hypothetical next) — Phase 4.5e Form 4
  insider clustering ships

`pyproject.toml` `version` field uses the bare semver (e.g., `1.2.0`)
without the `v` prefix or phase suffix — those go in the git tag only.

## Process

### 1. Pre-flight checks

Before cutting the tag:

```bash
# On main, fully up to date
git checkout main && git fetch origin && git pull origin main

# No uncommitted changes
git status   # should report "nothing to commit, working tree clean"

# CI green on main HEAD
# (use mcp__github__list_commits or the GitHub UI to verify)

# Production output is current (the release will be tied to this output)
python .claude/skills/verify-production-output/helper.py
# expect: 0 failures, 0 warnings (or known-acceptable warnings only)
```

Don't proceed if any pre-flight fails — investigate first.

### 2. Determine the version

Look at the previous tag + the merged PRs since:

```bash
LAST_TAG=$(git describe --tags --abbrev=0)
git log --oneline "$LAST_TAG"..HEAD | head -30
```

Classify the cumulative delta:

- **Patch (X.Y.Z+1)** — only bug fixes + docs + small polish
- **Minor (X.Y+1.0)** — at least one new feature (new defense /
  pillar / method / large feature flag flip)
- **Major (X+1.0.0)** — breaking change in the public JSON schema or
  the static-site URL contract (NEVER cut without explicit user OK —
  document the break + migration in the release notes)

Phase suffix: pull the closing phase identifier from `CLAUDE.md`
§Phase status `Latest release tag` line + the most recent merged
PRs' commit messages.

If unclear, ASK the user before tagging — version names are durable
and a wrong call requires a force-tag (destructive).

### 3. Bump `pyproject.toml`

```bash
# Open pyproject.toml and bump the [project] version field.
# Example: "0.3.0" → "1.3.0" (don't include the phase suffix here)
```

Lockstep edit: `CLAUDE.md` §Phase status `Latest release tag` line.
Update to the new tag + date + commit SHA placeholder
(`<SHA-after-tag>` — fill in after step 5 once the tag commit exists).

### 4. Write release notes

Template:

```markdown
## What's new in v<VERSION>-<PHASE>

<1-2 sentence headline describing the most user-visible change>

### Highlights

- **<Feature 1>** (PR #<N>) — <one-line summary, link to docs/issue>
- **<Feature 2>** (PR #<N>) — <one-line>
- **<Defense layer change>** — defense layer counts moved from X to Y

### Defense layer changes (if applicable)

| Flag | Status | Source |
|---|---|---|
| `<new flag>` | ✅ added (annotate) | PR #<N> |
| `<recalibrated flag>` | 🔄 threshold tightened | PR #<N> |

### Breaking changes

(None — or list each with migration guide)

### Internal / no user impact

- Skill additions / refactors
- Test coverage bumps
- CI workflow polish

### Schema version

- `<old>` → `<new>` (typical patch: same; minor / major: bumped)

### Verification

- Section A-H scan: ✅ (link to most recent helper.py output)
- Defense scorecard delta: ✅ vs `<LAST_TAG>`
- Top-5 rotation invariant: ✅

### Contributors

<list PR authors from `git log <LAST_TAG>..HEAD --format='%an'` | sort -u>

---

Full changelog: <LAST_TAG>...<NEW_TAG>
```

### 5. Tag + push

```bash
# Annotated tag with the release notes in the message body
NEW_TAG="v<VERSION>-<PHASE>"
git tag -a "$NEW_TAG" -m "$(cat release_notes_<VERSION>.md)"
git push origin "$NEW_TAG"
```

Annotated tags (`-a`) are the QuantRank convention — they store the
message + tagger + timestamp, which is what GitHub Releases consumes
from. Don't use lightweight tags.

### 6. Create the GitHub release

Via the MCP `mcp__github__*` tool surface (this skill prefers the API
over the `gh` CLI since CLI may be unavailable in the sandbox):

- Title: `v<VERSION>-<PHASE>`
- Tag: the tag just pushed
- Body: the release notes from step 4
- Pre-release: false (unless the phase is in flight — rare)
- Generate auto changelog: false (we wrote curated notes; auto would
  duplicate)

### 7. Backfill the CLAUDE.md commit SHA

After the tag exists on remote, `git rev-parse <NEW_TAG>^{commit}`
returns the tagged commit SHA. Edit `CLAUDE.md` §Phase status
`Latest release tag` line to replace the `<SHA-after-tag>` placeholder
with the real `[:7]` SHA. This is a small follow-up PR, NOT amended
into the tagged commit (we never amend a published tag).

### 8. Post-release hygiene

After the release lands:

- `defense-scorecard` baseline updated to the new tag (next compute
  run's "vs baseline" diff measures against the release)
- `phase-status-bump` skill invocation to update `PHASE_STATUS.md` +
  `SKILL.md` + `WORKFLOW.md` triple
- If a major release: announce in any relevant Slack / email channel
- Close any GitHub milestone tied to this phase

## Gotchas

- **Don't tag from a branch** — always tag from `main` after merge.
  Tags from a feature branch produce confusing tag→commit links.
- **Pre-release suffix** — phase-N in our convention is NOT a SemVer
  pre-release indicator. `v1.2.0-phase4.5` IS a stable release. If a
  true pre-release is needed (rare), use a suffix like
  `-rc1` BEFORE the phase suffix: `v1.3.0-rc1-phase4.5e`.
- **Schema bump synchronization** — if the release bumps the schema
  (e.g., 0.9.2 → 0.10.0 from epic #150 Phase 2.1), the schema bump
  PR should be the LAST merge before the tag. Don't tag mid-schema-
  migration.
- **Verify-production-output is part of the release** — the most
  recent compute output committed to `frontend/public/data/` defines
  what the release ranks. Don't cut a release on a stale compute
  output — re-run if needed.

## What this skill is NOT

- Not a hotfix workflow — those are handled per-PR without a new tag
- Not a rollback — rollback is a separate (destructive) workflow that
  requires explicit user authorization
- Not for `frontend/public/data/` weekly compute updates — those are
  not tagged; only phase-completion releases are
