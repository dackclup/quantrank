#!/usr/bin/env python3
"""Section A-G pre-merge quality gate for a QuantRank PR.

Invoked by the ``pr-quality-gate`` skill. Walks the diff between the
current branch and ``origin/main`` and answers the senior-reviewer
checklist: scope vs description, skill triggers met, doc drift, test
coverage delta, local verification ladder, commit hygiene, final
polish.

Run from the repo root, on the PR's branch (not on main):

    python .claude/skills/pr-quality-gate/helper.py

Optional flags:

    --strict             Soft warnings (⚠) become hard failures (exit 2)
    --only=<sec>         Run a single section: scope|triggers|docs|tests|
                         ladder|commits|polish
    --base=<ref>         Base ref to diff against (default origin/main)
    --skip-ladder        Skip Section E entirely (CI already covers it)
    --skip-pytest        Skip pytest in Section E
    --skip-next-build    Skip the 60s next build step in Section E
    --pr-title=<title>   PR title (for Section A scope correlation)
    --pr-body=<body>     PR body text (for Section A + G checks)
    --quiet              Suppress per-check detail lines on healthy checks

Exit codes:
    0 = all clean (or only ⚠ under default mode)
    1 = hard failure (✗) in Sections C / E / G
    2 = --strict mode and any ⚠ in any section
    3 = helper couldn't run (on main, no upstream, detached HEAD, ...)
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys

OK = "\033[32m✓\033[0m"
WARN = "\033[33m⚠\033[0m"
FAIL = "\033[31m✗\033[0m"


def _emit(marker: str, label: str, detail: str = "") -> None:
    if detail:
        print(f"  {marker} {label}: {detail}")
    else:
        print(f"  {marker} {label}")


def _section(letter: str, title: str) -> None:
    print(f"\n=== Section {letter} — {title} ===")


# ---------------------------------------------------------------------------
# Git helpers — pure subprocess + stdlib
# ---------------------------------------------------------------------------


def _run_git(*args: str) -> str:
    """Run `git <args>` and return stdout. Empty string on failure."""
    try:
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return result.stdout


def _current_branch() -> str:
    return _run_git("rev-parse", "--abbrev-ref", "HEAD").strip()


def _merge_base(base: str) -> str:
    return _run_git("merge-base", base, "HEAD").strip()


def _diff_files(base: str) -> list[str]:
    out = _run_git("diff", "--name-only", f"{base}...HEAD")
    return [line for line in out.splitlines() if line]


def _diff_numstat(base: str) -> list[tuple[int, int, str]]:
    """Return (added, removed, path) tuples for each changed file."""
    out = _run_git("diff", "--numstat", f"{base}...HEAD")
    rows: list[tuple[int, int, str]] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added = 0 if parts[0] == "-" else int(parts[0])
        removed = 0 if parts[1] == "-" else int(parts[1])
        rows.append((added, removed, parts[2]))
    return rows


def _diff_body(base: str) -> str:
    return _run_git("diff", f"{base}...HEAD")


def _commits_on_branch(base: str) -> list[tuple[str, str, str, str]]:
    """(sha, author, subject, body) tuples for commits not on base."""
    log = _run_git(
        "log",
        f"{base}..HEAD",
        "--pretty=format:%H%x1f%an%x1f%s%x1f%b%x1e",
    )
    commits: list[tuple[str, str, str, str]] = []
    for chunk in log.split("\x1e"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split("\x1f")
        if len(parts) < 4:
            parts += [""] * (4 - len(parts))
        commits.append((parts[0], parts[1], parts[2], parts[3]))
    return commits


# ---------------------------------------------------------------------------
# Section A — Diff scope vs PR description
# ---------------------------------------------------------------------------

_SCOPE_KEYWORDS = {
    "frontend": {"frontend/", "tailwind", "next", "tsx", "css"},
    "compute": {"compute/", "scoring", "ingest", "valuation", "fundamentals"},
    "schema": {"schemas.py", "types.ts", "schema-snapshot"},
    "ci": {".github/", "workflow", "ci.yml"},
    "docs": {".md", "readme", "docs/", "claude.md", "agents.md"},
    "skills": {".claude/skills/"},
    "tests": {"tests/", "test_"},
    "security": {"security", "audit"},
    "compute-output": {"frontend/public/data/"},
}


def section_a_scope(
    *,
    strict: bool,
    quiet: bool,
    files: list[str],
    numstat: list[tuple[int, int, str]],
    pr_title: str,
    pr_body: str,
) -> tuple[bool, bool]:
    _section("A", "Diff scope vs PR description")
    hard = False
    soft = False

    total_lines = sum(a + r for a, r, _ in numstat)
    if len(files) > 50:
        soft = True
        _emit(WARN, f"{len(files)} files changed (>50) — consider splitting the PR")
    if total_lines > 2000:
        soft = True
        _emit(WARN, f"{total_lines} lines changed (>2000) — review-expensive")
    if len(files) <= 50 and total_lines <= 2000:
        _emit(OK, f"{len(files)} file(s) / {total_lines} line(s) — review-sized")

    blob = (pr_title + " " + pr_body).lower()
    if not blob.strip():
        soft = True
        _emit(WARN, "no PR title/body provided; skipping scope correlation")
        return hard, soft

    inferred_scopes = {
        scope for scope, kws in _SCOPE_KEYWORDS.items() if any(kw in blob for kw in kws)
    }
    if not inferred_scopes:
        soft = True
        _emit(WARN, "could not infer scope from PR title/body")
        return hard, soft

    out_of_scope: list[str] = []
    for path in files:
        path_l = path.lower()
        matched = False
        for scope in inferred_scopes:
            if any(kw in path_l for kw in _SCOPE_KEYWORDS[scope]):
                matched = True
                break
        if not matched:
            out_of_scope.append(path)

    if out_of_scope:
        soft = True
        _emit(
            WARN,
            f"{len(out_of_scope)} file(s) outside inferred scope "
            f"{sorted(inferred_scopes)}",
        )
        if not quiet:
            for path in out_of_scope[:10]:
                print(f"      {path}")
    else:
        _emit(OK, f"all files match inferred scope {sorted(inferred_scopes)}")

    del strict
    return hard, soft


# ---------------------------------------------------------------------------
# Section B — Skill triggers met
# ---------------------------------------------------------------------------

# (diff-path-predicate, required-skill, signal-predicate, why)
_SKILL_TRIGGERS: list[tuple[str, str, str, str]] = [
    (
        "compute/output/schemas.py",
        "schema-check",
        "frontend/lib/schema-snapshot.json",
        "Pydantic schema changed → snapshot must move",
    ),
    (
        "frontend/lib/types.ts",
        "schema-check",
        "frontend/lib/schema-snapshot.json",
        "TS types changed → snapshot must move",
    ),
    (
        "compute/scoring/risk_overlay.py",
        "defense-scorecard",
        "",
        "Risk-overlay changed → run defense-scorecard for veto delta",
    ),
    (
        "compute/scoring/composite.py",
        "top5-rotation-audit",
        "",
        "Composite scoring changed → run top5-rotation-audit",
    ),
    (
        "compute/valuation/ensemble.py",
        "verify-production-output",
        "",
        "Fair-price ensemble changed → run Section C of verify-production-output",
    ),
    (
        "compute/ingest/",
        "network-test-runner",
        "",
        "Ingest layer changed → run @network tests against real SEC",
    ),
    (
        "compute/main.py",
        "verify-production-output",
        "",
        "Orchestrator changed → workflow_dispatch + verify the output",
    ),
    (
        ".github/workflows/",
        "security-check",
        "",
        "CI workflow changed → run security-check Section E",
    ),
    (
        "pyproject.toml",
        "security-check",
        "",
        "Python deps may have changed → run security-check Section B",
    ),
    (
        "frontend/package.json",
        "security-check",
        "",
        "JS deps may have changed → run security-check Section B",
    ),
]


def section_b_triggers(
    *, strict: bool, quiet: bool, files: list[str]
) -> tuple[bool, bool]:
    _section("B", "Skill triggers met")
    hard = False
    soft = False

    files_set = set(files)
    fired_triggers: list[tuple[str, str, str, str]] = []
    for predicate, skill, signal, why in _SKILL_TRIGGERS:
        if predicate.endswith("/"):
            triggered = any(f.startswith(predicate) for f in files_set)
        else:
            triggered = predicate in files_set
        if triggered:
            fired_triggers.append((predicate, skill, signal, why))

    if not fired_triggers:
        _emit(OK, "no skill-trigger files touched — clean")
        return hard, soft

    for predicate, skill, signal, why in fired_triggers:
        if signal and signal in files_set:
            _emit(OK, f"{predicate} → {skill} (signal: {signal} also changed)")
        elif signal:
            soft = True
            _emit(
                WARN,
                f"{predicate} → {skill}: expected {signal} change not in diff",
            )
            if not quiet:
                print(f"      ({why})")
        else:
            # No structural signal — skill needs to be run + result noted.
            soft = True
            _emit(WARN, f"{predicate} → run {skill}: {why}")

    del strict
    return hard, soft


# ---------------------------------------------------------------------------
# Section C — Documentation drift
# ---------------------------------------------------------------------------


def section_c_docs(
    *, strict: bool, quiet: bool, files: list[str], diff_body: str
) -> tuple[bool, bool]:
    _section("C", "Documentation drift")
    hard = False
    soft = False

    files_set = set(files)

    # 1) Pydantic schema field add/remove → snapshot must move.
    if "compute/output/schemas.py" in files_set:
        snap = "frontend/lib/schema-snapshot.json"
        if snap not in files_set:
            # Heuristic: only fail if the diff actually added/removed a field.
            field_change = re.search(
                r"(?m)^[+-]\s+\w+\s*:\s*[A-Z]\w*", diff_body
            )
            if field_change:
                hard = True
                _emit(
                    FAIL,
                    "compute/output/schemas.py changed but schema-snapshot.json didn't",
                )
            else:
                _emit(OK, "schemas.py change appears non-structural; snapshot OK")
        else:
            _emit(OK, "schemas.py + schema-snapshot.json both changed")

    # 2) SCHEMA_VERSION bumped → PHASE_STATUS must move.
    if "compute/config.py" in files_set:
        config_diff = _file_diff_in_body(diff_body, "compute/config.py")
        if re.search(r"(?m)^\+.*SCHEMA_VERSION\s*:", config_diff):
            if "PHASE_STATUS.md" not in files_set:
                hard = True
                _emit(FAIL, "SCHEMA_VERSION bumped but PHASE_STATUS.md not updated")
            else:
                _emit(OK, "SCHEMA_VERSION bump matched in PHASE_STATUS.md")

    # 3) Triple-doc lockstep: editing 1 of {PHASE_STATUS, SKILL, WORKFLOW}.
    triple = {"PHASE_STATUS.md", "SKILL.md", "WORKFLOW.md"}
    touched = triple & files_set
    if 0 < len(touched) < 3:
        # Allow single-doc edits for non-phase content (e.g., README pointer).
        # Soft warn only — the phase-status-bump skill is the canonical fix.
        soft = True
        _emit(
            WARN,
            f"{sorted(touched)} touched in isolation — phase-status-bump exists for lockstep",
        )
    elif len(touched) == 3:
        _emit(OK, "PHASE_STATUS + SKILL + WORKFLOW moved together")

    # 4) New env-var reads in code → mention in CLAUDE.md / AGENTS.md / README.
    new_env_pattern = re.compile(r"(?m)^\+.*os\.environ(?:\.get)?\(\s*['\"]([A-Z][A-Z0-9_]+)['\"]")
    new_envs: set[str] = set()
    for match in new_env_pattern.finditer(diff_body):
        new_envs.add(match.group(1))
    # Ignore standard ones that are already documented.
    new_envs -= {"EDGAR_USER_AGENT", "PATH", "HOME", "USER", "CI", "GITHUB_TOKEN"}
    if new_envs:
        docs_touched = any(
            f in files_set for f in ("CLAUDE.md", "AGENTS.md", "README.md")
        )
        if not docs_touched:
            soft = True
            _emit(
                WARN,
                f"new env vars {sorted(new_envs)} read in code; no docs updated",
            )
        else:
            _emit(OK, f"new env vars {sorted(new_envs)} read; docs touched")

    # 5) New dependency rows in pyproject.toml without LICENSE/notice mention.
    if "pyproject.toml" in files_set:
        pyproj_diff = _file_diff_in_body(diff_body, "pyproject.toml")
        new_deps = re.findall(r"(?m)^\+\s+\"([a-zA-Z][\w-]+)\s*[<>=~]", pyproj_diff)
        new_deps = [d for d in new_deps if d not in {"python"}]
        if new_deps:
            soft = True
            _emit(
                WARN,
                f"new Python dep(s) {new_deps}; verify license + CLAUDE.md dep table",
            )

    if not (
        "compute/output/schemas.py" in files_set
        or "compute/config.py" in files_set
        or touched
        or new_envs
        or "pyproject.toml" in files_set
    ):
        _emit(OK, "no doc-drift-prone surfaces touched")

    del strict, quiet
    return hard, soft


def _file_diff_in_body(diff_body: str, path: str) -> str:
    """Extract the diff hunk for a specific file from a full git-diff body."""
    marker = f"diff --git a/{path} b/{path}"
    start = diff_body.find(marker)
    if start == -1:
        return ""
    rest = diff_body[start:]
    nxt = rest.find("\ndiff --git ", 1)
    return rest[:nxt] if nxt != -1 else rest


# ---------------------------------------------------------------------------
# Section D — Test coverage delta
# ---------------------------------------------------------------------------


def section_d_tests(
    *,
    strict: bool,
    quiet: bool,
    files: list[str],
    numstat: list[tuple[int, int, str]],
    diff_body: str,
) -> tuple[bool, bool]:
    _section("D", "Test coverage delta")
    hard = False
    soft = False

    files_set = set(files)
    added_by_path = {p: a for a, _, p in numstat}

    # 1) Substantial compute/ change without matching test_<name>.py.
    missing_tests: list[str] = []
    for path in files:
        if not path.startswith("compute/") or not path.endswith(".py"):
            continue
        if path.endswith("__init__.py") or "/cache/" in path:
            continue
        if added_by_path.get(path, 0) < 20:
            continue
        # Look for any tests/ file that imports or names this module.
        module_name = pathlib.Path(path).stem
        test_files = [
            f for f in files if f.startswith("tests/") and module_name in f
        ]
        if not test_files:
            # Also check if any tests/ file is changed AT ALL that references
            # the module name in its diff.
            if not re.search(rf"\b{re.escape(module_name)}\b", diff_body):
                missing_tests.append(path)
    if missing_tests:
        soft = True
        _emit(
            WARN,
            f"{len(missing_tests)} compute/*.py file(s) with substantial change but no test reference",
        )
        if not quiet:
            for path in missing_tests[:10]:
                print(f"      {path}")
    else:
        _emit(OK, "substantial compute/ changes have matching test refs")

    # 2) New scoring defense without dedicated test file.
    new_scoring_files = [
        f for f in files if f.startswith("compute/scoring/") and f.endswith(".py")
        and not f.endswith("__init__.py")
    ]
    for path in new_scoring_files:
        # Did the file exist on base? If unchanged or modified-only, skip.
        if added_by_path.get(path, 0) < 50:
            continue
        # Expect tests/test_scoring/test_<name>.py.
        stem = pathlib.Path(path).stem
        expected = f"tests/test_scoring/test_{stem}.py"
        if expected not in files_set:
            hard = True
            _emit(FAIL, f"new defense {path} missing required test file {expected}")

    # 3) fix: PR should have regression test.
    # (Heuristic — only fires if the user passed a fix-style PR title via env.)
    pr_title = os.environ.get("_PR_TITLE", "")
    if pr_title.lower().startswith("fix"):
        has_regression_test = any(
            "regression" in f or "_does_not_" in f or "_bug" in f
            for f in files if f.startswith("tests/")
        )
        if not has_regression_test:
            soft = True
            _emit(WARN, "fix: PR without regression-style test name")

    # 4) Pytest collection sanity.
    if pathlib.Path("tests").exists():
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "--collect-only", "-q"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                hard = True
                _emit(FAIL, "pytest --collect-only failed (broken test collection)")
                if not quiet:
                    for line in (result.stdout + result.stderr).splitlines()[-5:]:
                        print(f"      {line}")
            else:
                _emit(OK, "pytest --collect-only clean")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            soft = True
            _emit(WARN, "pytest collection probe failed to run")

    del strict
    return hard, soft


# ---------------------------------------------------------------------------
# Section E — Local verification ladder
# ---------------------------------------------------------------------------


def section_e_ladder(
    *,
    strict: bool,
    quiet: bool,
    files: list[str],
    skip_pytest: bool,
    skip_next_build: bool,
) -> tuple[bool, bool]:
    _section("E", "Local verification ladder")
    hard = False
    soft = False

    files_set = set(files)
    frontend_touched = any(f.startswith("frontend/") for f in files)
    schema_touched = (
        "compute/output/schemas.py" in files_set
        or "frontend/lib/types.ts" in files_set
    )

    # 1) ruff check .
    try:
        result = subprocess.run(
            ["ruff", "check", "."], capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            _emit(OK, "ruff check . — clean")
        else:
            hard = True
            _emit(FAIL, "ruff check . — failures present")
            if not quiet:
                for line in result.stdout.splitlines()[:10]:
                    print(f"      {line}")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        soft = True
        _emit(WARN, "ruff not runnable; skipping")

    # 2) pytest -m "not network"
    if skip_pytest:
        _emit(WARN, "pytest skipped via --skip-pytest")
        soft = True
    else:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "-m", "not network", "-q"],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode == 0:
                _emit(OK, "pytest -m 'not network' — passed")
            else:
                hard = True
                _emit(FAIL, "pytest -m 'not network' — failures")
                if not quiet:
                    for line in (result.stdout + result.stderr).splitlines()[-15:]:
                        print(f"      {line}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            soft = True
            _emit(WARN, "pytest not runnable; skipping")

    # 3) schema-check if relevant.
    if schema_touched:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "compute.output.schema_check"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                _emit(OK, "schema_check — in sync")
            else:
                hard = True
                _emit(FAIL, "schema_check — drift detected")
                if not quiet:
                    for line in (result.stdout + result.stderr).splitlines()[-10:]:
                        print(f"      {line}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            soft = True
            _emit(WARN, "schema_check not runnable")

    # 4) tsc / next build if frontend touched.
    if frontend_touched:
        try:
            result = subprocess.run(
                ["npx", "--no", "--", "tsc", "--noEmit"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd="frontend",
            )
            if result.returncode == 0:
                _emit(OK, "frontend tsc --noEmit — clean")
            else:
                hard = True
                _emit(FAIL, "frontend tsc --noEmit — errors")
                if not quiet:
                    for line in (result.stdout + result.stderr).splitlines()[-10:]:
                        print(f"      {line}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            soft = True
            _emit(WARN, "tsc not runnable; skipping")

        if skip_next_build:
            _emit(WARN, "next build skipped via --skip-next-build")
            soft = True
        else:
            try:
                result = subprocess.run(
                    ["npx", "--no", "--", "next", "build"],
                    capture_output=True,
                    text=True,
                    timeout=180,
                    cwd="frontend",
                )
                if result.returncode == 0:
                    _emit(OK, "frontend next build — clean")
                else:
                    hard = True
                    _emit(FAIL, "frontend next build — errors")
                    if not quiet:
                        for line in (result.stdout + result.stderr).splitlines()[-15:]:
                            print(f"      {line}")
            except (subprocess.TimeoutExpired, FileNotFoundError):
                soft = True
                _emit(WARN, "next build not runnable; skipping")

    del strict
    return hard, soft


# ---------------------------------------------------------------------------
# Section F — Commit hygiene
# ---------------------------------------------------------------------------

_PLACEHOLDER_SUBJECTS = {"wip", "fix", "update", "todo", "test", "tmp", "tmp commit"}
_TYPE_PREFIX_RE = re.compile(
    r"^(feat|fix|chore|docs|refactor|test|perf|build|ci|style|revert)(\([^)]+\))?:\s+"
)
_DEBUG_PATTERNS = [
    ("console.log call", re.compile(r"(?m)^\+[^-+].*\bconsole\.log\(")),
    ("bare print()", re.compile(r"(?m)^\+[^-+].*\bprint\(")),
    ("breakpoint()", re.compile(r"(?m)^\+[^-+].*\bbreakpoint\(\)")),
    ("pdb.set_trace", re.compile(r"(?m)^\+[^-+].*pdb\.set_trace")),
]


def section_f_commits(
    *,
    strict: bool,
    quiet: bool,
    base: str,
    diff_body: str,
) -> tuple[bool, bool]:
    _section("F", "Commit hygiene")
    hard = False
    soft = False

    commits = _commits_on_branch(base)
    if not commits:
        _emit(WARN, "no commits ahead of base; nothing to check")
        return hard, True

    no_verify_hits: list[str] = []
    placeholder_hits: list[str] = []
    bot_scope_violations: list[str] = []
    no_type_prefix: list[str] = []

    for sha, author, subject, body in commits:
        short = sha[:8]
        subj_l = subject.strip().lower()
        if "--no-verify" in body or "--no-gpg-sign" in body:
            no_verify_hits.append(f"{short}: {subject[:60]}")
        if subj_l in _PLACEHOLDER_SUBJECTS or len(subj_l.split()) <= 1:
            placeholder_hits.append(f"{short}: {subject[:60]}")
        if not _TYPE_PREFIX_RE.match(subject):
            no_type_prefix.append(f"{short}: {subject[:60]}")
        if "github-actions[bot]" in author.lower():
            files = _run_git("show", "--name-only", "--pretty=format:", sha).splitlines()
            non_data = [f for f in files if f and not f.startswith("frontend/public/data/")]
            if non_data:
                bot_scope_violations.append(
                    f"{short}: touches {len(non_data)} non-data file(s)"
                )

    if no_verify_hits:
        hard = True
        _emit(FAIL, f"{len(no_verify_hits)} commit(s) reference --no-verify / --no-gpg-sign")
        if not quiet:
            for hit in no_verify_hits[:5]:
                print(f"      {hit}")
    if placeholder_hits:
        soft = True
        _emit(WARN, f"{len(placeholder_hits)} commit(s) have placeholder subjects")
        if not quiet:
            for hit in placeholder_hits[:5]:
                print(f"      {hit}")
    if no_type_prefix:
        soft = True
        _emit(
            WARN,
            f"{len(no_type_prefix)} commit(s) miss <type>(scope): subject format",
        )
        if not quiet:
            for hit in no_type_prefix[:5]:
                print(f"      {hit}")
    if bot_scope_violations:
        soft = True
        _emit(WARN, f"{len(bot_scope_violations)} bot commit(s) touch non-data files")
        if not quiet:
            for hit in bot_scope_violations[:3]:
                print(f"      {hit}")

    # Debug artifacts in the diff.
    debug_hits: list[str] = []
    for label, pattern in _DEBUG_PATTERNS:
        # Bare print() is OK inside tests/ + helper.py / *.md files; filter
        # the simple cases.
        for match in pattern.finditer(diff_body):
            line = match.group(0)
            if label == "bare print()":
                # Skip if the surrounding diff path is tests/ / helper.py.
                if _diff_line_path(diff_body, match.start()).startswith(("tests/", ".claude/")):
                    continue
            debug_hits.append(f"{label}: {line.strip()[:80]}")

    if debug_hits:
        soft = True
        _emit(WARN, f"{len(debug_hits)} debug-artifact line(s) in diff")
        if not quiet:
            for hit in debug_hits[:5]:
                print(f"      {hit}")

    if not (
        no_verify_hits or placeholder_hits or bot_scope_violations or no_type_prefix or debug_hits
    ):
        _emit(OK, f"{len(commits)} commit(s) clean")

    del strict
    return hard, soft


def _diff_line_path(diff_body: str, offset: int) -> str:
    """Return the file path the diff hunk at the given offset belongs to."""
    head = diff_body[:offset]
    last_marker = head.rfind("diff --git a/")
    if last_marker == -1:
        return ""
    rest = diff_body[last_marker:]
    match = re.match(r"diff --git a/(\S+) b/\S+", rest)
    return match.group(1) if match else ""


# ---------------------------------------------------------------------------
# Section G — Final polish (PR-level)
# ---------------------------------------------------------------------------

_WIP_MARKERS = ("wip", "do not merge", "[wip]", "draft only", "[draft]")


def section_g_polish(
    *,
    strict: bool,
    quiet: bool,
    pr_title: str,
    pr_body: str,
    diff_body: str,
    base: str,
) -> tuple[bool, bool]:
    _section("G", "Final polish")
    hard = False
    soft = False

    branch = _current_branch()
    if branch in {"main", "master", "HEAD"}:
        hard = True
        _emit(FAIL, f"on branch '{branch}' — must run from a feature branch")

    # WIP markers in title.
    if pr_title:
        title_l = pr_title.lower()
        if any(marker in title_l for marker in _WIP_MARKERS):
            hard = True
            _emit(FAIL, f"PR title contains WIP / DO NOT MERGE marker: {pr_title[:60]}")
        else:
            _emit(OK, "PR title has no WIP marker")
    else:
        soft = True
        _emit(WARN, "no PR title provided; skipping WIP-marker check")

    # PR body conventions.
    if pr_body:
        has_summary = bool(re.search(r"(?im)^##\s*summary\b", pr_body))
        has_test_plan = bool(re.search(r"(?im)^##\s*test plan\b", pr_body))
        if has_summary and has_test_plan:
            _emit(OK, "PR body has ## Summary + ## Test plan")
        else:
            soft = True
            missing = []
            if not has_summary:
                missing.append("## Summary")
            if not has_test_plan:
                missing.append("## Test plan")
            _emit(WARN, f"PR body missing: {', '.join(missing)}")
    else:
        soft = True
        _emit(WARN, "no PR body provided; skipping section check")

    # Conflict markers in diff.
    conflict_re = re.compile(r"(?m)^[+].*(<{7} |={7}$|>{7} )")
    if conflict_re.search(diff_body):
        hard = True
        _emit(FAIL, "conflict markers (<<<<<<<, =======, >>>>>>>) present in diff")
    else:
        _emit(OK, "no conflict markers in diff")

    # Base branch sanity.
    base_short = base.replace("origin/", "")
    if base_short in {"main", "master"}:
        _emit(OK, f"diff base = {base}")
    else:
        soft = True
        _emit(WARN, f"diff base = {base} (expected main)")

    # PR-level checklist for the agent to verify via GitHub MCP.
    if not quiet:
        print("\n  ── Agent: verify via GitHub MCP before authorizing Mark-Ready ──")
        print("      • mcp__github__pull_request_read get_check_runs — all green?")
        print("      • mcp__github__pull_request_read get — base = main? draft state?")
        print("      • Vercel preview built? (if frontend changed) — spot-check it")

    del strict
    return hard, soft


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


SECTIONS = {
    "scope": ("A", "scope"),
    "triggers": ("B", "triggers"),
    "docs": ("C", "docs"),
    "tests": ("D", "tests"),
    "ladder": ("E", "ladder"),
    "commits": ("F", "commits"),
    "polish": ("G", "polish"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--only", choices=list(SECTIONS.keys()))
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--skip-ladder", action="store_true")
    parser.add_argument("--skip-pytest", action="store_true")
    parser.add_argument("--skip-next-build", action="store_true")
    parser.add_argument("--pr-title", default="")
    parser.add_argument("--pr-body", default="")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    # Sanity: in a git repo + on a feature branch + base resolves.
    if not _run_git("rev-parse", "--show-toplevel"):
        print("error: must run inside a git repo", file=sys.stderr)
        return 3
    branch = _current_branch()
    if branch in {"main", "master", "HEAD"}:
        print(
            f"error: must run from a feature branch, not '{branch}'",
            file=sys.stderr,
        )
        return 3
    base = _merge_base(args.base)
    if not base:
        print(f"error: could not resolve base ref '{args.base}'", file=sys.stderr)
        return 3

    files = _diff_files(base)
    numstat = _diff_numstat(base)
    diff_body = _diff_body(base)
    if args.pr_title:
        os.environ["_PR_TITLE"] = args.pr_title

    print(f"branch: {branch}   base: {args.base} ({base[:8]})   files: {len(files)}")

    selected = [args.only] if args.only else list(SECTIONS.keys())
    any_hard = False
    any_soft = False

    for name in selected:
        if name == "ladder" and args.skip_ladder:
            _section(SECTIONS[name][0], "Local verification ladder")
            _emit(WARN, "section skipped via --skip-ladder")
            any_soft = True
            continue
        if name == "scope":
            hard, soft = section_a_scope(
                strict=args.strict,
                quiet=args.quiet,
                files=files,
                numstat=numstat,
                pr_title=args.pr_title,
                pr_body=args.pr_body,
            )
        elif name == "triggers":
            hard, soft = section_b_triggers(
                strict=args.strict, quiet=args.quiet, files=files
            )
        elif name == "docs":
            hard, soft = section_c_docs(
                strict=args.strict,
                quiet=args.quiet,
                files=files,
                diff_body=diff_body,
            )
        elif name == "tests":
            hard, soft = section_d_tests(
                strict=args.strict,
                quiet=args.quiet,
                files=files,
                numstat=numstat,
                diff_body=diff_body,
            )
        elif name == "ladder":
            hard, soft = section_e_ladder(
                strict=args.strict,
                quiet=args.quiet,
                files=files,
                skip_pytest=args.skip_pytest,
                skip_next_build=args.skip_next_build,
            )
        elif name == "commits":
            hard, soft = section_f_commits(
                strict=args.strict,
                quiet=args.quiet,
                base=base,
                diff_body=diff_body,
            )
        elif name == "polish":
            hard, soft = section_g_polish(
                strict=args.strict,
                quiet=args.quiet,
                pr_title=args.pr_title,
                pr_body=args.pr_body,
                diff_body=diff_body,
                base=args.base,
            )
        else:
            continue
        any_hard = any_hard or hard
        any_soft = any_soft or soft

    print("\n=== Summary ===")
    if any_hard:
        _emit(FAIL, "hard failure(s) present — do not authorize Mark-Ready / merge")
        return 1
    if any_soft and args.strict:
        _emit(FAIL, "soft warning(s) present under --strict mode")
        return 2
    if any_soft:
        _emit(WARN, "soft warning(s) present — review before authorizing Mark-Ready")
        return 0
    _emit(OK, "all sections clean — PR is ready for Mark-Ready authorization")
    return 0


if __name__ == "__main__":
    sys.exit(main())
