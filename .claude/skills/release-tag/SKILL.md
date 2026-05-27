---
name: release-tag
description: Cut a versioned release for a QuantRank phase-completion PR — bump `pyproject.toml` version, write release notes from the merged-PR log, tag `vX.Y.Z-phase<N>`, push the tag, and create the GitHub release. Codifies the project's release convention so the next release doesn't have to re-derive it. TRIGGER when the user explicitly says "tag release", "cut a release", "release v1.X.Y", "release notes for phase X", "ship the release", "make a tag", or "bump version", and after merging any PR that closes a phase (epic #150 Phase 1 complete, Phase 4.5e ships, etc.). ALSO trigger when the user names a specific version string (e.g., "v1.3.0-phase4.5e") in a context that suggests cutting a release. SKIP for in-flight PRs that haven't merged yet (release tags lag the merge by at least the time it takes to verify the post-merge compute output), for hotfix / patch releases that don't close a phase boundary (those can ship under the existing tag), and for re-running a release that already exists (use `git tag --list` to check first).
---

# Release Tag Workflow

QuantRank releases at phase boundaries. The most recent tag is
`v1.4.0-phase4.6` (2026-05-27, `a820caee`). Tag cadence is roughly
1-3 weeks, matching the phase-completion rhythm. This skill is the
end-to-end release workflow so the next release doesn't have to
re-derive the convention from looking at the last tag.

## OPERATOR CONSTRAINT — mobile-only (locked 2026-05-27)

**The user operates the GitHub UI from a mobile phone only — no
desktop, no `gh` CLI, no terminal beyond reading.** All release
steps that require pushing tags or creating Releases MUST be
delivered as **pre-filled GitHub URLs the user taps once** — never
as `git tag` / `git push origin <tag>` / `gh release create` shell
commands the user would have to execute.

This constraint is structural (not optional) because:

1. The sandbox itself **cannot push tag-refs** (HTTP 403 from the
   git proxy — branch pushes work, tag pushes do not). Confirmed
   2026-05-27 when v1.3.0 + v1.4.0 tags were cut.
2. The user has no terminal access — even `gh release create` is
   not an option.
3. GitHub's web UI accepts a single URL that pre-fills tag name,
   target commit SHA, release title, AND release body via query
   string parameters. The user only needs to **tap the link, verify
   the pre-filled fields, and tap Publish**.

The pattern is codified in §"Mobile-operator release workflow"
below — that section REPLACES the historical "Step 5 (Tag + push)"
and "Step 6 (Create GitHub release)" workflow. The old `git tag`
shell pattern is kept in §"Reference: shell pattern (NOT for
sandbox)" purely for documentation; do NOT propose it as a workflow
for this user.

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

### 5+6. Mobile-operator release workflow (REPLACES historical tag-push + release-create)

**Generate ONE pre-filled GitHub Release URL per release.** GitHub's
`/releases/new` endpoint accepts these query parameters:

| Param | Value |
|---|---|
| `tag` | tag name (e.g. `v1.4.0-phase4.6`) — auto-created on publish if it doesn't exist yet |
| `target` | full 40-char commit SHA the tag points at |
| `title` | release title (URL-encoded) |
| `body` | release body markdown (URL-encoded) |

URL pattern:

```
https://github.com/<owner>/<repo>/releases/new?tag=<TAG>&target=<SHA>&title=<URL-ENCODED-TITLE>&body=<URL-ENCODED-BODY>
```

**URL size budget**: stay under 8 KB (GitHub server-side HTTP request
limit; mobile browser URL bar caps too). A typical full release-notes
body is 8-12 KB raw → 12-18 KB URL-encoded → **TOO LARGE**. Use the
**short-body pattern** below:

#### Short-body template (keeps URL under 2 KB)

The full release notes file already lives on `main` at
`docs/release-notes/v<VERSION>-<PHASE>.md`. The short body in the URL
just links to it:

```markdown
Closes the **<headline phase or epic>** (PRs #<list>) since
<prior-tag> (<prior-SHA-short>, <prior-date>).

**Schema bump**: `<old>` → `<new>` (PATCH/MINOR/MAJOR; <one-line rationale>)
**Defense layer**: <old-count> → <new-count> declared boolean flags
**CVE baseline**: <CVE summary if changed>

**Full release notes**: [`docs/release-notes/v<VERSION>-<PHASE>.md`](https://github.com/<owner>/<repo>/blob/main/docs/release-notes/v<VERSION>-<PHASE>.md)

Compare: [<prior-tag>...v<VERSION>-<PHASE>](https://github.com/<owner>/<repo>/compare/<prior-tag>...v<VERSION>-<PHASE>)
```

This format keeps URL well under 2 KB AND the full notes stay
readable on the release page (just one tap into the linked file).

#### Generator helper (Python one-liner)

When proposing the URL to the user, generate it programmatically:

```python
import urllib.parse
base = "https://github.com/<owner>/<repo>/releases/new"
qs = urllib.parse.urlencode({
    "tag": "v<VERSION>-<PHASE>",
    "target": "<40-char-SHA>",
    "title": "v<VERSION>-<PHASE> — <headline>",
    "body": short_body_text,
})
url = f"{base}?{qs}"
assert len(url) < 8192, "URL too large — shorten body further"
print(url)
```

Then present it as **one tappable markdown link** in chat — the user
just taps it on their phone.

#### What the user does

After tapping the URL on their phone:

1. ✅ verify pre-filled fields look correct (tag, target, title, body)
2. **Set as the latest release** — ☑️ tick (for the newest release;
   uncheck for retroactive/historical tags)
3. **Pre-release** — ❌ uncheck
4. Tap green **Publish release** button

That's it. GitHub creates the tag + the release in one step. No
shell, no `git`, no CLI needed.

#### Multi-release ladder ordering

When cutting **multiple releases in one session** (e.g., retroactive
v1.3.0 + new v1.4.0):

1. Publish the **newest version FIRST** with "Set as latest" ✅
2. Publish older/retroactive versions AFTER with "Set as latest" ❌

This ordering avoids the recurring footgun where GitHub auto-flags
the most-recently-published release as Latest — caught on
2026-05-27 when v1.3.0 retroactive ended up as Latest until manually
re-promoted. Order matters; latest-flag matters more.

#### Verify after publish

Use `mcp__github__get_latest_release` to confirm Latest = the
newest tag. If wrong, propose the **edit URL** to the user:

```
https://github.com/<owner>/<repo>/releases/edit/<TAG>
```

User taps → toggles "Set as latest" → Update.

### Reference: shell pattern (NOT for this user)

For posterity / contributors with desktop access:

```bash
# Annotated tag with the release notes file as body
git tag -a "$NEW_TAG" -F docs/release-notes/$NEW_TAG.md
git push origin "$NEW_TAG"
gh release create "$NEW_TAG" "$TARGET_SHA" \
  --title "$TITLE" --notes-file docs/release-notes/$NEW_TAG.md --latest
```

But **do not propose this to the current user** — they have no
desktop. Always use the mobile-operator workflow above.

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
