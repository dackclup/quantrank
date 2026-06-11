---
name: security-check
description: Audit repo + branch for the security pitfalls of a public static-site finance project: committed secrets, dependency CVEs, EDGAR rate-limit violations, output-JSON PII, CI workflow over-permissions, license drift, dangerous git ops. TRIGGER: before every release tag, any `.github/` CI-workflow PR, any new pip/npm dep or env-var requirement, after a near-miss, "is this safe to push?" / "security review" / "check for secrets", or as a 4-6-weekly baseline scan.
---

# security-check

A focused security audit for QuantRank's surface area. The Anthropic
`security-review` skill (vendored at `.claude/skills/security-review/`)
gives a general-purpose review of pending diff lines — this skill
complements it by checking the **project-specific** pitfalls that
ship cheap-to-detect, expensive-to-fix:

- Secrets accidentally committed
- Dependencies with known CVEs
- EDGAR rate-limit ceiling violations (regression risk after the
  PR-3d retry tightening)
- Output-JSON shipping data it shouldn't (PII / API keys / internal
  fields)
- CI workflows with excessive permissions
- Third-party license drift in vendored skills

## When to invoke

| Trigger | Why |
|---|---|
| Before tagging a release (`v0.X.Y-phaseN`) | The tagged commit ships to public Vercel; everything in `frontend/public/data/` is permanently downloadable |
| Before merging anything that adds a pip / npm dependency | New dep = new CVE surface area + new license to track |
| Before merging CI workflow edits (`.github/workflows/*.yml`) | Workflow regressions can leak secrets to public logs |
| Before merging a PR that adds a new env-var requirement | New env vars often map to API keys; gating with `_ensure_*` patterns matters |
| After a near-miss (e.g., almost-pushed-a-token) | Forensic check that nothing slipped through |
| Periodic baseline (every 4-6 weeks) | New CVEs land in shipped deps over time |

Skip this skill for routine UI tweaks, docs edits, skill rewrites,
or any change that doesn't touch the surface above. The standard
`pr-iteration-flow` verification (ruff + pytest + tsc + next build +
schema-snapshot) already covers those.

## Running

```bash
python .claude/skills/security-check/helper.py
```

Optional flags:

```bash
# Strict mode: any soft warning becomes a hard failure (CI gate use).
python .claude/skills/security-check/helper.py --strict

# Restrict to one category (faster iteration):
python .claude/skills/security-check/helper.py --only=secrets
python .claude/skills/security-check/helper.py --only=deps
python .claude/skills/security-check/helper.py --only=ci
```

The helper is pure stdlib + `subprocess` (for `pip audit` / `npm
audit` if installed). No extra installs required.

## What it checks — 7 sections

The helper emits a Section A-G report. Each section maps to a
specific QuantRank risk surface; per-section markers are
`✓` healthy / `⚠` soft warning / `✗` hard failure.

### A. Secrets in tracked files

Greps `compute/`, `frontend/`, `tests/`, `.github/`, `.claude/` for
patterns:

- Real-looking AWS / Anthropic / OpenAI / GitHub PAT prefixes
  (`AKIA*`, `sk-ant-*`, `sk-proj-*`, `ghp_*`, `ghs_*`)
- `EDGAR_USER_AGENT=` with anything other than env-var indirection
- `.env` content patterns inside any tracked file
- Anything matching `(?i)(api_key|secret|token|password)\s*=\s*['"][\w-]{16,}['"]`

Healthy = zero matches. Any match is a hard failure — the secret
must be revoked and the commit rewritten before push.

### B. Dependency CVEs

Runs:
- `pip audit -r pyproject.toml` (Python deps) — if `pip-audit` is
  installed locally; otherwise emit a `⚠` skip note
- `npm audit --omit=dev --audit-level=high` in `frontend/` — same
  graceful-skip pattern

Healthy = no high / critical CVEs. Medium / low warnings are `⚠`
soft warnings — they don't block release but should land in a
Phase 4 issue.

### C. EDGAR rate-limit hygiene

Critical for the SEC EDGAR fair-access policy (10 req/s ceiling).
Checks:

- `compute/config.py::EDGAR_MAX_WORKERS` is ≤ 10
- `compute/ingest/fundamentals.py`'s tenacity retry has both
  `stop_after_delay` and `stop_after_attempt` in the stop policy
  (PR-3d's tightening — without these, retry amplification can
  trigger SEC throttling at scale)
- `compute/scoring/eight_k_events.py` does not call
  `EightK.items` or `EightK.sections` (those trigger the
  `hybrid_section_detector` performance cliff fixed in PR-3d
  commit `12ad7ff`)

Healthy = all four invariants hold. Any violation is a hard
failure — the SEC may rate-limit the entire IP, breaking weekly
compute for everyone using the same egress.

### D. Output JSON cleanliness

Scans `frontend/public/data/` (the public output) for fields that
shouldn't be there:

- Any field whose name matches `(?i)(email|password|secret|key|token)`
- Any string value matching a secret pattern from Section A
- Any value that looks like a private file path (`/home/`,
  `/Users/`)

Healthy = none of the above. Hard failure — the output is publicly
fetched by the frontend at runtime.

### E. CI workflow permissions

Reads `.github/workflows/*.yml` and checks:

- Every job has an explicit `permissions:` block (no implicit
  full-access fallback)
- `permissions: write-all` is not used anywhere
- No workflow checks out `secrets.*` into `env:` that artifacts can
  see (i.e., `env: { TOKEN: ${{ secrets.X }} }` at the step level
  is fine; setting it as a job-level env that gets included in
  `actions/upload-artifact` outputs is not)
- The compute workflow's `timeout-minutes` exists (defends against
  runaway compute eating GH Actions budget — PR-3d set this to 90)

Healthy = all explicit + minimal. Implicit defaults or `write-all`
are `⚠` soft warnings (acceptable but should be tightened next
edit).

### F. Third-party license attribution

The 17 vendored Anthropic skills include Apache 2.0 + source-
available licenses. Checks:

- `.claude/skills/THIRD_PARTY_NOTICES.md` exists
- Every directory under `.claude/skills/<name>/` has either a
  `LICENSE.txt` or is one of the 7 QuantRank-owned cross-phase
  skills (verify-production-output / schema-check / etc.)
- `pyproject.toml` license field matches `LICENSE` file at repo
  root

Healthy = all present + consistent. Missing notices are `⚠` —
attribution debt to fix but not release-blocking.

### G. Git hygiene at branch boundary

Surface dangerous git state on the current branch:

- No `--no-verify` or `--no-gpg-sign` in the last 20 commit
  message bodies (signal that someone bypassed pre-commit hooks)
- No commits with empty / placeholder messages (`wip`, `fix`,
  `test` alone)
- No commits authored by `github-actions[bot]` that touch
  anything outside `frontend/public/data/` (chore commits must
  stay scoped to the data dir)
- No merge commits on the current branch (the project's pattern
  is squash-merge; merge commits indicate a workflow break)

Healthy = clean. Findings are `⚠` soft warnings — they signal a
process drift, not a security hole.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | All sections healthy (or only `⚠` warnings under default mode) |
| 1 | Any hard failure (`✗`) in Sections A / B / C / D |
| 2 | `--strict` mode and any soft warning in any section |
| 3 | Helper itself couldn't run (e.g., not in a git repo) |

Production-use rule: **anything > 0 means do not push / merge / tag
without remediation**. Soft warnings stay open as Phase 4 issues.

## Anti-patterns

- Running this on every minor commit. The helper takes ~30-60
  seconds (heavy on Section D for the 502 stock JSON files);
  reserve for the trigger events listed above.
- Treating a `⚠` in Section B as release-blocking. Medium-CVE deps
  often have no upstream fix yet; document + ship + revisit.
- Adding secret patterns ad-hoc inline. New patterns go in
  `helper.py::_SECRET_REGEXES` so the regression coverage
  accumulates.
- Disabling the `pre-commit` ruff hook with `--no-verify` and then
  running this skill as compensation. The hook + this skill are
  layered; bypassing the hook defeats the purpose.

## Why this skill exists

QuantRank ships output JSON to a public Vercel preview at every PR
and to production at every Sunday cron. The data flow is:

```
SEC EDGAR (read-only) → compute layer → frontend/public/data/*.json
                                                   ↓
                                         public Vercel static site
```

There are no user accounts, no API keys at runtime, no PII in the
output by design. But the **build-time** surface has multiple risk
points: `EDGAR_USER_AGENT` env var, GitHub Actions secrets, third-
party vendored skills, dependency CVE drift, retry-policy regression
risk. Each is cheap to detect with a focused check + expensive to
recover from after the fact (SEC IP-level throttle, leaked
credentials, public data leak via output JSON regression).

This skill is the gate that catches each of those before they ship.

## Related skills

- `security-review` (global, vendored from `anthropics/skills`) —
  general-purpose review of pending diff lines; complements this
  skill (which is project-specific surface checks)
- `verify-production-output` — Section A scans the metadata; this
  skill's Section D scans the actual stock JSONs for leakage
- `schema-check` — drift in the Pydantic ↔ TypeScript bridge can
  inadvertently expose new fields; this skill's Section D catches
  the public-side leak even if schema-check missed it
- `pr-iteration-flow` — the broader review workflow; this skill is
  a specific gate within it for high-risk PRs

## Long-form description (moved out of frontmatter 2026-06-11 token drain)

Audit QuantRank's repo + branch for the security pitfalls specific to
a public static-site finance project — committed secrets, dependency CVEs,
EDGAR rate-limit violations, output-JSON PII, CI workflow over-permissions,
third-party license drift, and dangerous git operations. TRIGGER before
every release tag, before any PR that touches CI workflows (`.github/`),
before pushing a branch that adds new pip / npm dependencies, before
merging anything that adds a new env-var requirement, after a contributor
reports a near-miss (e.g., almost-committed-a-token), or when the user
asks "is this safe to push?" / "security review" / "check for secrets" /
"audit before release". ALSO use periodically (every 4-6 weeks) as a
baseline scan. SKIP for routine UI / docs / skills-folder changes that
don't touch deps, CI, secrets handling, or compute output schemas — those
are sufficiently covered by `pr-iteration-flow`'s standard verification.
