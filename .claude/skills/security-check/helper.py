#!/usr/bin/env python3
"""Section A-G security audit for the QuantRank repo + current branch.

Invoked by the ``security-check`` skill. Pure stdlib — no third-party
imports — so it runs cleanly in CI before ``pip install`` does
anything. Optional ``pip-audit`` / ``npm`` subprocess probes degrade
to a soft-warning skip when the tool isn't installed.

Run from the repo root:

    python .claude/skills/security-check/helper.py

Optional flags:

    --strict        Soft warnings (⚠) become hard failures (exit 2)
    --only=<sec>    Run a single section: secrets|deps|edgar|output|ci|licenses|git
    --data-dir=<p>  Override output-JSON root (default frontend/public/data)
    --quiet         Suppress per-section detail lines on healthy checks

Exit codes:
    0 = all clean (or only ⚠ under default mode)
    1 = hard failure (✗) in Sections A / B / C / D
    2 = --strict mode and any ⚠ in any section
    3 = helper itself couldn't run (e.g., not in a git repo)
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
from collections.abc import Iterable

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
# Section A — secrets in tracked files
# ---------------------------------------------------------------------------

# Real-looking prefixes / patterns we never want committed. Each tuple is
# (label, compiled regex). Patterns target the *prefix* + entropy hint;
# they aim for "would a public-repo scanner flag this?" not "is this a
# valid credential right now?".
_SECRET_REGEXES: list[tuple[str, re.Pattern[str]]] = [
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Anthropic API key", re.compile(r"\bsk-ant-[a-zA-Z0-9_-]{20,}")),
    ("OpenAI project key", re.compile(r"\bsk-proj-[a-zA-Z0-9_-]{20,}")),
    ("GitHub personal token", re.compile(r"\bghp_[a-zA-Z0-9]{30,}")),
    ("GitHub server token", re.compile(r"\bghs_[a-zA-Z0-9]{30,}")),
    ("Slack bot token", re.compile(r"\bxoxb-[0-9a-zA-Z-]{20,}")),
    (
        "generic API-key assignment",
        re.compile(
            r"""(?ix)
            (?:api[_-]?key|secret|token|password)
            \s*[:=]\s*
            ['\"](?P<value>[\w\-]{16,})['\"]
            """
        ),
    ),
    (
        "EDGAR_USER_AGENT with literal value",
        # The legitimate pattern is `os.environ.get("EDGAR_USER_AGENT")` or
        # similar env-var indirection. A literal string assignment is the
        # red flag.
        re.compile(
            r"""(?ix)
            EDGAR_USER_AGENT
            \s*=\s*
            ['\"](?P<value>[^'\"\n]{4,}@[^'\"\n]{4,})['\"]
            """
        ),
    ),
    (
        ".env content pattern",
        # A standalone line like `FOO_TOKEN=abcd1234...` inside a tracked
        # file (not actual .env content, but copy-pasted into source).
        re.compile(
            r"""(?im)
            ^\s*[A-Z][A-Z0-9_]{4,}_(?:TOKEN|KEY|SECRET|PASSWORD)\s*=\s*(?P<value>[\w\-]{16,})\s*$
            """
        ),
    ),
]

# Substrings that mark a captured value as "obviously a placeholder",
# not a real credential. Hits whose `value` named group contains any of
# these are skipped. Tuned by inspection — vendored skill docs use
# "your_*", README templates use "example", scripts use "xxx" /
# "changeme" / "<replace>". Real keys never contain these.
_PLACEHOLDER_TOKENS: tuple[str, ...] = (
    "your_",
    "your-",
    "your.",
    "your ",
    "yourname",
    "your@",
    "@email",
    "@example",
    "example",
    "placeholder",
    "dummy",
    "changeme",
    "change_me",
    "todo",
    "xxxx",
    "<",
    "...",
    "abc123",
)


def _is_placeholder(value: str | None) -> bool:
    if not value:
        return False
    needle = value.lower()
    return any(token in needle for token in _PLACEHOLDER_TOKENS)

# Paths we DO want to scan. Anything outside these stays off the scan
# floor — the goal is "files Claude / humans might paste secrets into".
_SECRET_SCAN_DIRS = ("compute", "frontend", "tests", ".github", ".claude")

# Files we explicitly skip inside the scan dirs.
_SECRET_SKIP_SUFFIXES = (
    ".lock",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".pdf",
    ".parquet",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".zip",
)

# A few file paths we know contain example/dummy secret-like strings as
# DOCUMENTATION (not real keys). They live inside this skill itself.
_SECRET_SCAN_ALLOWLIST = {
    ".claude/skills/security-check/SKILL.md",
    ".claude/skills/security-check/helper.py",
}


def _iter_tracked_files() -> Iterable[pathlib.Path]:
    """All files tracked by git, scoped to the secret-scan dirs."""
    try:
        result = subprocess.run(
            ["git", "ls-files", *_SECRET_SCAN_DIRS],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [pathlib.Path(line) for line in result.stdout.splitlines() if line]


def section_a_secrets(*, strict: bool, quiet: bool) -> tuple[bool, bool]:
    """Returns (hard_failure, soft_warning)."""
    _section("A", "Secrets in tracked files")
    hard = False
    soft = False
    scanned = 0
    hits: list[str] = []

    for path in _iter_tracked_files():
        if path.suffix in _SECRET_SKIP_SUFFIXES:
            continue
        if str(path) in _SECRET_SCAN_ALLOWLIST:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        for label, regex in _SECRET_REGEXES:
            for match in regex.finditer(text):
                # Skip obvious placeholder values (your_*, example, ...).
                if "value" in (match.groupdict() or {}) and _is_placeholder(
                    match.group("value")
                ):
                    continue
                # 1-based line number for the start of the match.
                line = text.count("\n", 0, match.start()) + 1
                hits.append(f"{path}:{line} [{label}]")

    if hits:
        hard = True
        _emit(FAIL, f"{len(hits)} secret-pattern match(es) in {scanned} scanned files")
        for hit in hits[:20]:
            print(f"      {hit}")
        if len(hits) > 20:
            print(f"      ... +{len(hits) - 20} more")
    else:
        _emit(OK, f"no secret patterns in {scanned} scanned files")

    del strict, quiet
    return hard, soft


# ---------------------------------------------------------------------------
# Section B — dependency CVEs
# ---------------------------------------------------------------------------


def _which(cmd: str) -> str | None:
    """Return the resolved path of an executable, or None if absent."""
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        candidate = pathlib.Path(entry) / cmd
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def section_b_deps(*, strict: bool, quiet: bool) -> tuple[bool, bool]:
    _section("B", "Dependency CVEs")
    hard = False
    soft = False

    # --- Python (pip-audit) ---
    pip_audit = _which("pip-audit")
    if pip_audit is None:
        _emit(WARN, "pip-audit not installed; skipping Python CVE scan")
        soft = True
    else:
        try:
            result = subprocess.run(
                [pip_audit, "-r", "pyproject.toml", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            _emit(WARN, "pip-audit timed out after 120s")
            soft = True
        else:
            if result.returncode == 0:
                _emit(OK, "pip-audit clean (no advisories)")
            else:
                # pip-audit returns non-zero when advisories exist; parse
                # severity from JSON if possible.
                high_cves = _count_pip_audit_high(result.stdout)
                if high_cves > 0:
                    hard = True
                    _emit(FAIL, f"pip-audit reports {high_cves} high/critical advisory(ies)")
                else:
                    soft = True
                    _emit(WARN, "pip-audit reports low/medium advisories")
                if not quiet:
                    for line in result.stdout.splitlines()[:5]:
                        print(f"      {line}")

    # --- Node (npm audit) — frontend/ only ---
    npm = _which("npm")
    frontend_dir = pathlib.Path("frontend")
    if npm is None or not (frontend_dir / "package.json").exists():
        if npm is None:
            _emit(WARN, "npm not installed; skipping JS CVE scan")
        else:
            _emit(WARN, "frontend/package.json not found; skipping JS CVE scan")
        soft = True
    else:
        try:
            result = subprocess.run(
                [npm, "audit", "--omit=dev", "--audit-level=high", "--json"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(frontend_dir),
            )
        except subprocess.TimeoutExpired:
            _emit(WARN, "npm audit timed out after 120s")
            soft = True
        else:
            high = _count_npm_audit_high(result.stdout)
            if high == 0:
                _emit(OK, "npm audit clean at --audit-level=high")
            else:
                hard = True
                _emit(FAIL, f"npm audit reports {high} high/critical vulnerability(ies)")

    del strict
    return hard, soft


def _count_pip_audit_high(stdout: str) -> int:
    """Count high+critical advisories in pip-audit JSON output."""
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return 0
    # pip-audit JSON is { "dependencies": [ { "vulns": [ {...} ] } ] }
    high = 0
    for dep in payload.get("dependencies", []) or []:
        for vuln in dep.get("vulns", []) or []:
            sev = (vuln.get("severity") or "").lower()
            if sev in {"high", "critical"}:
                high += 1
    return high


def _count_npm_audit_high(stdout: str) -> int:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return 0
    meta = (payload.get("metadata") or {}).get("vulnerabilities") or {}
    return int(meta.get("high", 0)) + int(meta.get("critical", 0))


# ---------------------------------------------------------------------------
# Section C — EDGAR rate-limit hygiene
# ---------------------------------------------------------------------------


def section_c_edgar(*, strict: bool, quiet: bool) -> tuple[bool, bool]:
    _section("C", "EDGAR rate-limit hygiene")
    hard = False
    soft = False

    config_path = pathlib.Path("compute/config.py")
    if not config_path.exists():
        _emit(WARN, "compute/config.py not found; skipping")
        return hard, True

    config_text = config_path.read_text()
    match = re.search(r"EDGAR_MAX_WORKERS\s*:\s*int\s*=\s*(\d+)", config_text)
    if match is None:
        _emit(FAIL, "EDGAR_MAX_WORKERS not declared in compute/config.py")
        hard = True
    else:
        workers = int(match.group(1))
        if workers > 10:
            hard = True
            _emit(FAIL, f"EDGAR_MAX_WORKERS={workers} exceeds SEC 10 req/s ceiling")
        else:
            _emit(OK, f"EDGAR_MAX_WORKERS={workers} ≤ 10")

    fund_path = pathlib.Path("compute/ingest/fundamentals.py")
    if not fund_path.exists():
        _emit(WARN, "compute/ingest/fundamentals.py not found; skipping retry-policy probe")
        soft = True
    else:
        fund_text = fund_path.read_text()
        has_delay = "stop_after_delay" in fund_text
        has_attempt = "stop_after_attempt" in fund_text
        if has_delay and has_attempt:
            _emit(OK, "tenacity retry uses stop_after_delay | stop_after_attempt")
        else:
            hard = True
            missing = []
            if not has_delay:
                missing.append("stop_after_delay")
            if not has_attempt:
                missing.append("stop_after_attempt")
            _emit(FAIL, f"tenacity retry missing: {', '.join(missing)}")

    eight_k_path = pathlib.Path("compute/scoring/eight_k_events.py")
    if eight_k_path.exists():
        eight_k_text = eight_k_path.read_text()
        # The forbidden calls are EightK.items / EightK.sections — accessing
        # them triggers the hybrid_section_detector performance cliff. The
        # current code uses EightK.document (which is OK).
        forbidden_hits = []
        for forbidden in (".items", ".sections"):
            # Look for `EightK<anything>` followed by the forbidden attr.
            pattern = re.compile(r"\bEightK\b[^=\n]{0,40}\\" + forbidden + r"\b")
            # Use a simpler, more robust scan: tokenize lines and flag any
            # line containing both "EightK" and the forbidden suffix.
            for line_no, line in enumerate(eight_k_text.splitlines(), start=1):
                if "EightK" in line and forbidden in line:
                    # Skip comment-only mentions (the SKILL.md docs the rule).
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith("//"):
                        continue
                    forbidden_hits.append(f"line {line_no}: {stripped[:80]}")
            del pattern
        if forbidden_hits:
            hard = True
            _emit(FAIL, "compute/scoring/eight_k_events.py uses forbidden EightK attribute(s)")
            if not quiet:
                for hit in forbidden_hits[:5]:
                    print(f"      {hit}")
        else:
            _emit(OK, "compute/scoring/eight_k_events.py avoids EightK.items / .sections")
    else:
        _emit(WARN, "compute/scoring/eight_k_events.py not found; skipping forbidden-attr probe")
        soft = True

    del strict
    return hard, soft


# ---------------------------------------------------------------------------
# Section D — output JSON cleanliness
# ---------------------------------------------------------------------------

_PII_KEY_RE = re.compile(r"(?i)(email|password|secret|api[_-]?key|token)")
_PRIVATE_PATH_RE = re.compile(r"(/home/|/Users/|C:\\\\Users\\\\)[^\"\s]{2,}")


def _walk_json(value, *, key_path: str = "", key_hits: list, path_hits: list, secret_hits: list) -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            if _PII_KEY_RE.search(k):
                key_hits.append(f"{key_path}.{k}" if key_path else k)
            _walk_json(
                v,
                key_path=f"{key_path}.{k}" if key_path else k,
                key_hits=key_hits,
                path_hits=path_hits,
                secret_hits=secret_hits,
            )
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _walk_json(
                item,
                key_path=f"{key_path}[{i}]",
                key_hits=key_hits,
                path_hits=path_hits,
                secret_hits=secret_hits,
            )
    elif isinstance(value, str):
        if _PRIVATE_PATH_RE.search(value):
            path_hits.append(key_path)
        for label, regex in _SECRET_REGEXES:
            if regex.search(value):
                secret_hits.append(f"{key_path} [{label}]")


def section_d_output(*, strict: bool, quiet: bool, data_dir: pathlib.Path) -> tuple[bool, bool]:
    _section("D", "Output JSON cleanliness")
    hard = False
    soft = False

    if not data_dir.exists():
        _emit(WARN, f"data dir {data_dir} not found; skipping")
        return hard, True

    files: list[pathlib.Path] = []
    for candidate in (data_dir / "metadata.json", data_dir / "rankings.json"):
        if candidate.exists():
            files.append(candidate)
    stocks_dir = data_dir / "stocks"
    if stocks_dir.exists():
        files.extend(sorted(stocks_dir.glob("*.json")))

    if not files:
        _emit(WARN, "no JSON output files to scan; skipping")
        return hard, True

    key_hits: list[str] = []
    path_hits: list[str] = []
    secret_hits: list[str] = []
    for path in files:
        try:
            payload = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            soft = True
            _emit(WARN, f"could not parse {path}")
            continue
        _walk_json(payload, key_hits=key_hits, path_hits=path_hits, secret_hits=secret_hits)

    if secret_hits:
        hard = True
        _emit(FAIL, f"{len(secret_hits)} secret-pattern string(s) in output JSON")
        for hit in secret_hits[:10]:
            print(f"      {hit}")
    if path_hits:
        hard = True
        _emit(FAIL, f"{len(path_hits)} private-path string(s) in output JSON")
        for hit in path_hits[:10]:
            print(f"      {hit}")
    if key_hits:
        hard = True
        _emit(FAIL, f"{len(key_hits)} suspicious field-name(s) in output JSON")
        for hit in key_hits[:10]:
            print(f"      {hit}")
    if not (secret_hits or path_hits or key_hits):
        _emit(OK, f"{len(files)} output JSON files clean")

    del strict, quiet
    return hard, soft


# ---------------------------------------------------------------------------
# Section E — CI workflow permissions
# ---------------------------------------------------------------------------


def section_e_ci(*, strict: bool, quiet: bool) -> tuple[bool, bool]:
    _section("E", "CI workflow permissions")
    hard = False
    soft = False

    workflows_dir = pathlib.Path(".github/workflows")
    if not workflows_dir.exists():
        _emit(WARN, ".github/workflows not found; skipping")
        return hard, True

    workflow_files = sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml"))
    if not workflow_files:
        _emit(WARN, "no workflow files found; skipping")
        return hard, True

    write_all_hits: list[str] = []
    missing_perm_hits: list[str] = []
    compute_missing_timeout = False
    found_compute_workflow = False

    for path in workflow_files:
        text = path.read_text()
        if re.search(r"permissions:\s*write-all", text):
            write_all_hits.append(str(path))
        # Heuristic: every file should declare a top-level permissions:
        # block. We don't parse YAML (stdlib-only); we check the literal.
        if not re.search(r"(?m)^permissions:\s*$", text) and not re.search(
            r"(?m)^permissions:\s*\{[^}]*\}", text
        ):
            # Allow a permissions key under a job, but soft-warn the
            # missing top-level declaration.
            if "permissions:" not in text:
                missing_perm_hits.append(str(path))

        # Compute-workflow timeout check. The compute-rankings.yml file
        # is the relevant one — defends against runaway GH-Actions cost.
        if "compute-rankings" in path.name:
            found_compute_workflow = True
            if not re.search(r"timeout-minutes\s*:\s*\d+", text):
                compute_missing_timeout = True

    if write_all_hits:
        soft = True
        _emit(WARN, f"{len(write_all_hits)} workflow(s) use permissions: write-all")
        if not quiet:
            for hit in write_all_hits:
                print(f"      {hit}")
    if missing_perm_hits:
        soft = True
        _emit(WARN, f"{len(missing_perm_hits)} workflow(s) missing explicit permissions:")
        if not quiet:
            for hit in missing_perm_hits:
                print(f"      {hit}")

    if found_compute_workflow:
        if compute_missing_timeout:
            soft = True
            _emit(WARN, "compute-rankings workflow missing timeout-minutes")
        else:
            _emit(OK, "compute-rankings workflow declares timeout-minutes")

    if not (write_all_hits or missing_perm_hits or compute_missing_timeout):
        _emit(OK, f"{len(workflow_files)} workflow(s) follow least-privilege pattern")

    del strict
    return hard, soft


# ---------------------------------------------------------------------------
# Section F — third-party license attribution
# ---------------------------------------------------------------------------

# The cross-phase QuantRank-owned skills that don't need a LICENSE.txt
# (they fall under the repo-root MIT LICENSE).
_QUANTRANK_SKILLS = {
    "verify-production-output",
    "schema-check",
    "defense-scorecard",
    "top5-rotation-audit",
    "network-test-runner",
    "phase-status-bump",
    "pr-iteration-flow",
    "security-check",
}


def section_f_licenses(*, strict: bool, quiet: bool) -> tuple[bool, bool]:
    _section("F", "Third-party license attribution")
    hard = False
    soft = False

    notices = pathlib.Path(".claude/skills/THIRD_PARTY_NOTICES.md")
    if notices.exists():
        _emit(OK, "THIRD_PARTY_NOTICES.md present")
    else:
        soft = True
        _emit(WARN, "THIRD_PARTY_NOTICES.md missing under .claude/skills/")

    skills_root = pathlib.Path(".claude/skills")
    missing_license: list[str] = []
    if skills_root.exists():
        for child in sorted(skills_root.iterdir()):
            if not child.is_dir():
                continue
            if child.name.startswith("phase-"):
                continue
            if child.name in _QUANTRANK_SKILLS:
                continue
            if not (child / "LICENSE.txt").exists() and not (child / "LICENSE").exists():
                missing_license.append(child.name)

    if missing_license:
        soft = True
        _emit(WARN, f"{len(missing_license)} vendored skill(s) missing LICENSE")
        if not quiet:
            for name in missing_license[:10]:
                print(f"      {name}")
    else:
        _emit(OK, "all vendored skills carry per-skill LICENSE")

    # Repo-root license/pyproject consistency. We just check that both
    # exist + that pyproject's license string is non-empty when present.
    root_license = pathlib.Path("LICENSE")
    pyproject = pathlib.Path("pyproject.toml")
    if root_license.exists() and pyproject.exists():
        py_text = pyproject.read_text()
        if re.search(r'(?m)^\s*license\s*=', py_text):
            _emit(OK, "pyproject.toml declares license + LICENSE file present")
        else:
            soft = True
            _emit(WARN, "pyproject.toml missing license field")
    elif not root_license.exists():
        soft = True
        _emit(WARN, "repo-root LICENSE file missing")

    del strict
    return hard, soft


# ---------------------------------------------------------------------------
# Section G — git hygiene at branch boundary
# ---------------------------------------------------------------------------


def section_g_git(*, strict: bool, quiet: bool) -> tuple[bool, bool]:
    _section("G", "Git hygiene at branch boundary")
    hard = False
    soft = False

    try:
        log = subprocess.run(
            ["git", "log", "-n", "20", "--pretty=format:%H%x09%an%x09%s"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        _emit(WARN, "git log unavailable; skipping")
        return hard, True

    no_verify_hits: list[str] = []
    placeholder_hits: list[str] = []
    bot_scope_violations: list[str] = []
    merge_commits: list[str] = []

    for line in log.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        sha, author, subject = parts
        short = sha[:8]
        body = _git_show_body(sha)
        if "--no-verify" in body or "--no-gpg-sign" in body:
            no_verify_hits.append(f"{short}: {subject[:60]}")
        if subject.strip().lower() in {"wip", "fix", "test", "update", "todo"}:
            placeholder_hits.append(f"{short}: {subject[:60]}")
        if "github-actions[bot]" in author.lower():
            files = _git_show_files(sha)
            non_data = [
                f for f in files
                if not f.startswith("frontend/public/data/") and f
            ]
            if non_data:
                bot_scope_violations.append(
                    f"{short}: touches {len(non_data)} non-data file(s)"
                )
        if _is_merge_commit(sha):
            merge_commits.append(f"{short}: {subject[:60]}")

    findings = [
        (no_verify_hits, "commit messages reference --no-verify / --no-gpg-sign"),
        (placeholder_hits, "commits with placeholder message (wip/fix/test/...)"),
        (bot_scope_violations, "bot commits touch files outside frontend/public/data/"),
        (merge_commits, "merge commits on current branch (expected squash-merge)"),
    ]
    any_finding = False
    for hits, label in findings:
        if hits:
            soft = True
            any_finding = True
            _emit(WARN, f"{len(hits)} {label}")
            if not quiet:
                for hit in hits[:5]:
                    print(f"      {hit}")
    if not any_finding:
        _emit(OK, "last 20 commits clean (no bypassed hooks, no merge commits)")

    del strict
    return hard, soft


def _git_show_body(sha: str) -> str:
    try:
        result = subprocess.run(
            ["git", "show", "-s", "--format=%B", sha],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return ""
    return result.stdout


def _git_show_files(sha: str) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "show", "--name-only", "--pretty=format:", sha],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return []
    return [line for line in result.stdout.splitlines() if line]


def _is_merge_commit(sha: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-list", "--no-walk", "--count", "--merges", sha],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return False
    return result.stdout.strip() == "1"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


SECTIONS = {
    "secrets": ("A", section_a_secrets),
    "deps": ("B", section_b_deps),
    "edgar": ("C", section_c_edgar),
    "output": ("D", section_d_output),
    "ci": ("E", section_e_ci),
    "licenses": ("F", section_f_licenses),
    "git": ("G", section_g_git),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", maxsplit=1)[0])
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--only", choices=list(SECTIONS.keys()))
    parser.add_argument("--data-dir", default="frontend/public/data")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    # Sanity: must be in a git repo.
    try:
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("error: helper.py must be run inside a git repo", file=sys.stderr)
        return 3

    data_dir = pathlib.Path(args.data_dir)

    selected = [args.only] if args.only else list(SECTIONS.keys())
    any_hard = False
    any_soft = False

    for name in selected:
        _, fn = SECTIONS[name]
        if name == "output":
            hard, soft = fn(strict=args.strict, quiet=args.quiet, data_dir=data_dir)
        else:
            hard, soft = fn(strict=args.strict, quiet=args.quiet)
        any_hard = any_hard or hard
        any_soft = any_soft or soft

    print("\n=== Summary ===")
    if any_hard:
        _emit(FAIL, "hard failure(s) present — do not push / merge / tag")
        return 1
    if any_soft and args.strict:
        _emit(FAIL, "soft warning(s) present under --strict mode")
        return 2
    if any_soft:
        _emit(WARN, "soft warning(s) present — acceptable but track as Phase 4 issue")
        return 0
    _emit(OK, "all sections clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
