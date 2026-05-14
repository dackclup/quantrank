# Issue Remapping (Phase 4 planning stub)

**Status**: Planning. Closes P0 audit gap (2026-05-14): CLAUDE.md lists 8 open Phase 4 issues but never specified which Phase 4 PR each maps to. This PLAN resolves the mapping and triages each issue.

## Purpose

Map every open GitHub issue (10 total as of 2026-05-14) to one of:
1. **Close immediately** — work done; issue stale
2. **Phase 4 PR mapping** — pin to a specific Phase 4 PR
3. **Deferred** — explicit punt to Phase 5+ with rationale
4. **Out of scope** — chore work; separate non-Phase-4 PR

This removes the ambiguity of "8 open Phase 4 issues queued" → makes each one trackable.

## Audit (2026-05-14)

Open issues by ID at v1.0.0 close:

| # | Title | Map | Phase 4 PR | Rationale |
|---|---|---|---|---|
| #7 | NVDA Sloan accruals investigation | Phase 4 | PR 4l (final defense tuning) | Sector-relative threshold or sector exclusion for Financials; depends on Defense Acceptance Matrix (§`phase-4-kickoff-checklist/PLAN.md` §8) |
| #10 | `shares_outstanding` wrong for ~12 tickers | **CLOSE** (fixed in PR #49) | n/a | Audit #6 fix expanded `_BALANCE_TAGS["shares_outstanding"]` with multi-class shares + stale DEI tag workaround. Universe-wide verification post-PR-#49: WMT / MA / META all correct |
| #11 | `_avg_3y_roe` per-year equity denominator | Phase 4 | **PR 4c** (already planned per `v1-to-v1-1-migration/PLAN.md`) | Add `stockholders_equity` to `_ANNUAL_TAGS`; rewrite `_avg_3y_roe`. ~120 LOC; tag `v1.0.3-fix` |
| #14 | Re-enable 8-K Tier-2 defenses (`_EIGHT_K_DEFENSES_ENABLED = True`) | Phase 4 | **PR 4g** (gate: going-concern FP ≤5%) | Gate met at v1.0 close (1.0% FP rate per workflow #32). PR 4g flips the flag |
| #15 | Fundamentals SEC throttling resilience | Phase 4 | **PR 4a** (partial — cache improvements reduce hit rate) + Phase 5 (defer full retry hardening) | Cache hygiene reduces EDGAR pressure ~80%; remaining throttling cases need tenacity tuning that overlaps with `chronic-slow-ticker-special-case/PLAN.md` |
| #16 | Going-concern phrase scan 10.8% FP rate | **CLOSE** (resolved at v1.0) | n/a | Audit #6 + universe-wide cache refresh brought FP rate to 1.0% (well under Mayew 2015 1-3% target). Issue body reflected pre-audit-#6 state |
| #17 | Tier-2 log message cosmetic | Phase 4 | **PR 4f** (alongside 8-K re-enable, since both touch defense logging) | Trivial fix; piggyback on adjacent PR |
| #18 | Composite scoring doesn't respect `data_quality_input_corruption` | Phase 4 | **PR 4c** (composite uses risk_flags directly) | After audit #6, composite already skips the input — the flag triggers veto pre-composite. Verify; if confirmed → close |
| #31 | Next.js 14 → 16 bump (security advisory) | **Chore PR** (NOT Phase 4) | n/a | Separate workstream; doesn't belong in Phase 4 features. Open as `chore/nextjs-14-to-16` |
| #41 | Duplicate of #31 (Next.js bump) | **Close as dup** | n/a | Closes when #31 ships |

## Closures executed in this PR (4)

1. **Close #10** with reference: "Resolved in PR #49 (audit #6 — `_BALANCE_TAGS["shares_outstanding"]` expanded for multi-class shares + stale DEI tag workaround). Verified universe-wide post-workflow-run-#32: 0 of 502 tickers had `shares_outstanding=None` (down from ~12 pre-PR-#49)."

2. **Close #16** with reference: "Resolved at v1.0 close. Going-concern FP rate dropped to 1.0% (Mayew 2015 target: 1-3%) after the audit-#6 deep-clean cycle + universe-wide cache refresh. See `PHASE_STATUS.md` Phase 3e production stats."

3. **Close #41** with reference: "Duplicate of #31. Tracking single Next.js 14→16 bump issue there."

#7 / #11 / #14 / #15 / #17 / #18 / #31 stay open — pinned to the PRs above.

## Phase 4 PR + issue cross-reference

When each PR opens, its description must include:

| PR | Closes issues | Touches but doesn't close |
|---|---|---|
| 4a (cache improvements) | n/a | #15 (partial) |
| 4b (defense infra) | n/a | (sets up gates for 4g–4k) |
| 4c (`_avg_3y_roe` fix) | #11 | #18 (verify; close if confirmed) |
| 4d (recommendation-badge) | n/a | n/a |
| 4e (loss-chance) | n/a | n/a |
| 4f (price-chart) | #17 (cosmetic logs co-shipped) | n/a |
| 4g (8-K re-enable) | #14 | n/a |
| 4h (OSAP) | n/a | (uses 4b defenses) |
| 4i (JKP) | n/a | (uses 4b defenses) |
| 4j (Qlib Alpha158) | n/a | (uses 4b defenses) |
| 4k (IPCA) | n/a | (uses 4b defenses) |
| 4l (final defense tuning) | #7 | n/a |
| `chore/nextjs-14-to-16` (separate, not Phase 4) | #31, #41 | n/a |

## Auto-closing protocol

Each PR's description includes a `Closes #N` line for the issue(s) it resolves. GitHub auto-closes on merge. If a PR is reverted (rollback per `v1-to-v1-1-migration/PLAN.md`), the issue auto-reopens.

For PRs that touch but don't fully resolve an issue: include `Relates to #N` or `Partial fix for #N` instead.

## Phase 5+ deferrals

No Phase 4 issues defer to Phase 5+ at this audit (none above need backtest infrastructure or ML work to resolve).

Phase 5 expects new issues to file when ML work begins:
- ML training data backfill cost
- LightGBM hyperparameter tuning
- Conformal prediction calibration set sizing

Track those when they appear.

## Effort

This PLAN is purely documentation + GitHub-issue closures. Time: ~1 hour. LOC: ~250 (docs).

The actual fixes (PR 4c onward) are tracked in their own PLAN entries.

## Implementer notes

When opening each Phase 4 PR:
1. Reference this PLAN section in the PR description
2. Include `Closes #N` for whichever issues from the table above
3. Update `PHASE_STATUS.md` if a closure resolves an audit-tracked gap

When this PLAN graduates from planning to executed (all 10 issues mapped + closed/pinned):
- Update `CLAUDE.md` "Phase status" section to remove the "8 open Phase 4 issues queued" line
- Replace with: "Phase 4 in progress; issue mapping in `.claude/skills/phase-4/issue-remapping/PLAN.md`"

## Open questions (none)

All mappings locked per the table above.
