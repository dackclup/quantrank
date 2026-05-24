# PHASE_STATUS_INFLIGHT.md — append-only side-file for in-flight PRs

This file exists to solve the **parallel-PR §Phase status collision
pattern** documented in [`CLAUDE.md`](CLAUDE.md) §Gotchas. Every PR
that needs to satisfy the §Conventions "ship with every PR" lockstep
rule was previously inserting a `**X in flight (this PR)**` bullet
at the same anchor line in CLAUDE.md §Phase status + AGENTS.md
§Phase + version state. Two PRs opened in parallel both target that
single line → `mergeable_state: dirty` → recurring `git merge`
conflicts → user frustration.

Surfaced 2026-05-24 by PR #230 (`docs(form4)+ci(simulate)`) which
hit the collision pattern **3 times in one session** while iterating
on the simulate-cap fix:
- vs PR #229 (security WARN cleanup) mid-iteration
- vs PR #232 + PR #233 (LedgerCraft A1 + A2) before Mark-Ready
- vs PR #234 + PR #235 + PR #236 (LedgerCraft A3 + B1 + B2+B3+B4)
  during the simulate-fix re-push loop

Each conflict was BENIGN (both PRs added distinct entries at the
same insertion line; resolution was always "keep both in
chronological order"). But `git merge` cannot auto-detect that.

## The new convention

**Open PRs MUST add their in-flight entry HERE**, not directly to
CLAUDE.md §Phase status or AGENTS.md §Phase + version state. New
entries go at the END of this file (append-only). Parallel PRs both
append to disjoint last-lines and `git merge` resolves trivially —
no conflict.

**Format** — one fenced block per in-flight PR, dated header,
trailing horizontal rule for visual separation:

```
## PR #NNN — <one-line summary> (in flight, 2026-MM-DD)

<2-15 line paragraph describing the change, the rationale, and any
follow-up items. Mirrors the format used by historical entries in
CLAUDE.md §Phase status — keep it readable for the next reviewer.>

---
```

**On merge** — the entry STAYS HERE (do NOT move on merge). This
file is append-only by design; the cost of in-place moves at merge
time would re-introduce the collision pattern. The historical
record gets aggregated periodically (weekly / per-release) by a
**housekeeping commit** that:

1. Moves entries from this file's "Merged" section (auto-marked by
   the housekeeping script — see `tools/housekeep_phase_status.py`
   when implemented) into CLAUDE.md §Phase status with their
   `merged via PR #N (commit-SHA)` headers
2. Leaves the still-in-flight section untouched

The housekeeping commit is one-touch (single file modified, all PR
authors disjoint by then) so it doesn't re-trigger the parallel-PR
collision.

## File structure

```
# PHASE_STATUS_INFLIGHT.md
## In flight (current)
  ## PR #NNN — ... (in flight, YYYY-MM-DD)
  ## PR #MMM — ... (in flight, YYYY-MM-DD)
## Merged (awaiting housekeeping move to CLAUDE.md)
  ## PR #LLL — ... (merged YYYY-MM-DD, SHA)
```

After housekeeping runs, the "Merged" sub-section drains to empty
(entries land in CLAUDE.md §Phase status proper); "In flight"
keeps growing/draining as PRs cycle.

## Cross-references

- [`CLAUDE.md`](CLAUDE.md) §Conventions — the lockstep rule that
  this file satisfies
- [`CLAUDE.md`](CLAUDE.md) §Gotchas "Parallel-PR §Phase status
  collision pattern" — the recurring symptom this file fixes
- [`AGENTS.md`](AGENTS.md) §Phase + version state — cross-tool
  mirror of CLAUDE.md §Phase status; same housekeeping pattern
  applies

## SKIP this file when

- The PR is a doc-only edit to this file itself (the lockstep is
  trivially satisfied)
- The PR is updating CLAUDE.md / AGENTS.md ONLY (no code change) —
  in that case, edit CLAUDE.md / AGENTS.md directly; the parallel
  collision risk is low for doc-only PRs since they're less common
- Housekeeping commits that move entries from here to CLAUDE.md —
  those touch CLAUDE.md + this file but the rationale is in the
  commit message, not a duplicated in-flight entry

---

## In flight (current)

## PR (this PR) — Form-4 `<aff10b5One>` direct-XML parse closes the architectural gap (in flight, 2026-05-24)

Closes the architectural-gap surfaced by PR #230's edgar-debugger
audit + Part 1 §"Footnote resolution" docstring. Pre-fix: filers
who checked `<aff10b5One>true` at the document level but omitted
the per-transaction footnote text slipped past the footnote-text
regex path and INCORRECTLY entered the opportunistic-trades cohort
that drives `insider_sell_cluster` + `c_suite_unusual_sell`.

`edgar-debugger` session 5 design report confirmed the cleanest
access path is `filing.xml()` — already `@lru_cache(maxsize=4)` so
calling it AFTER `filing.obj()` is a free cache hit (zero extra
HTTP per filing; universe-wide added cost ~1.5s for lxml find).
The XML element lives at `ownershipDocument/aff10b5One` per SEC
schema X0609 (Release 33-11138, effective 2023-04-01). Edgartools
5.31.5's `Ownership.parse_xml` walks a fixed set of child tags and
never reads it — the element is PRESENT in the BS4 tree but
discarded after parse.

Implementation in `compute/scoring/form4_insider.py`:
- New `_AFF10B5_REQUIRED_ATTRS = ("aff10b5One",)` manifest tuple
  (drift-detector documenting the canonical SEC element name)
- New `_extract_aff10b5_one(xml_str)` helper — lxml-based, handles
  `1`/`true`/`0`/`false` variants, returns None on absent / parse
  fail (graceful-degradation per existing pattern + methodology-
  scientist Mode B option (a) from PR #224)
- New `_combine_10b5_one_signals(doc_level, footnote_result)` helper
  — OR-of-True truth table: `True if either signal is True; None
  only when both are None; False otherwise`
- `_form4_to_transactions` modified to call `filing.xml()` +
  `_extract_aff10b5_one()` ONCE per filing, then propagate via
  `_combine_10b5_one_signals()` to every transaction in that
  filing's rows
- `Form4Transaction` dataclass gains `aff10b5_one_doc_level: bool
  | None = None` field with backward-compat default; `from_dict`
  reads it via `.get(...)` with None fallback

Tests in `tests/test_scoring/test_form4_insider.py` — `test-engineer`
spawn added 10 H-prefixed cases (9 offline + 1 @network-gated):
- H1-H4: `_extract_aff10b5_one` truth + variants + malformed + absent
- H5: doc-level propagation to all transactions in a filing
- H6-H8: `_combine_10b5_one_signals` truth-table coverage
- H9: `_AFF10B5_REQUIRED_ATTRS` manifest drift-detector
- H10 (@network): live AAPL Form 4 extraction verifies access path

Verification: `pytest tests/test_scoring/test_form4_insider.py -v -m
"not network"` → **32 passed, 2 deselected** (1 @network H10 + 1
@network D4). Smoke-test of helpers via direct `python3 -c` ✓ 14
assertions. `ruff check` clean.

Scope estimate from edgar-debugger held: ~30 LOC prod + ~80 LOC tests
+ 0 new deps + 0 schema changes (the new field lives in Form-4
cache rows only; doesn't surface in `StockDetail` / `Metadata` in
this PR). Defense layer flag count unchanged at 32. Downstream
consumer `_is_opportunistic_sell` in `form4_signals.py` reads the
existing combined `is_rule_10b5_one` field (now produced by
`_combine_10b5_one_signals` instead of just the footnote-text scan)
— no consumer changes needed.

This PR ALSO dogfoods the new `PHASE_STATUS_INFLIGHT.md` convention
adopted in PR #237 (`1ff6c11`) — this entry is the FIRST PR to
test-drive the side-file pattern. CLAUDE.md + AGENTS.md §Phase
status sections UNCHANGED in this PR (the in-flight entry is right
here in the side file). Lockstep rule satisfied per the new
§Conventions wording.

---

## Merged (awaiting housekeeping move to CLAUDE.md)

## PR #237 — adopt PHASE_STATUS_INFLIGHT.md side-file (merged 2026-05-24, 1ff6c11)

Closes the structural follow-up tracked in PR #230's §Gotcha
"Parallel-PR §Phase status collision pattern". PR #230 itself hit
the collision **3 times in one session** while iterating on the
simulate-cap fix — empirical proof that the doc-discipline §Convention
landed in PR #230 (rebase-before-Mark-Ready) is necessary but NOT
sufficient when 5+ PRs land on main in a single hour.

This PR creates `PHASE_STATUS_INFLIGHT.md` at the repo root with the
append-only convention documented above. Future PRs MUST add their
in-flight entry HERE instead of CLAUDE.md §Phase status / AGENTS.md
§Phase + version state. Parallel PRs both append at disjoint
last-lines → `git merge` auto-resolves → no more `mergeable_state:
dirty` from this pattern. CLAUDE.md §Conventions + §Gotchas updated
to point at this file as the canonical destination for in-flight
notes; AGENTS.md mirrored for cross-tool agents (Copilot / Cursor /
Devin).

Housekeeping workflow (`tools/housekeep_phase_status.py`) deferred —
manual housekeeping is fine for the first few weeks while the pattern
proves itself; a script can land later once we know the volume +
shape of entries this file accumulates.

No compute / schema / scoring / valuation / frontend / Python /
TS code change. Doc-only PR. CLAUDE.md + AGENTS.md lockstep
satisfied via §Conventions + §Gotchas substantive updates (the
"ship with every PR" rule now points at this file as the canonical
destination).
