# Phase 5 — Supabase Hybrid (PLAN)

> Outline draft 2026-05-27. Full PLAN body expands per sub-PR after user
> approval. Cross-refs: phase-coordinator Mode A verdict 2026-05-27 (agent
> id `a0578bd4794157369`) + AskUserQuestion lock 2026-05-27 (Option A
> renumber + 5.1-5.4 features + wait-for-merge handoff).

## Goal

Add user-state / interactive layer to QuantRank (auth · watchlist · alerts)
via Supabase (Postgres + Auth + RLS) + Next.js Route Handlers + Resend
email. **Ranking JSON pipeline UNTOUCHED** — `compute/` +
`frontend/public/data/` static-export contract preserved. Achieves slide
#4 "Backend: APIs + DBs + Auth + Business Logic" box without breaking
Option D static-site architecture.

## Scope locks (preserved hard rules)

- Composite formula UNCHANGED (Rule 16) · Pydantic↔TS schema triple
  UNCHANGED (Rule 9) · static-export `output: 'export'` PRESERVED ·
  mobile-only dev PRESERVED · free-tier first
- License: Supabase Apache-2.0 ✅ · Resend free tier OK
- Roadmap renumber: current Phase 5 ML → Phase 6 · Phase 6 Sentiment v2 →
  Phase 7 · Phase 7 Regime+Portfolio → Phase 8 · Phase 8 Universe
  expansion → Phase 9

## Sub-PR ladder

| # | Title | Scope | Effort |
|---|---|---|---|
| **5.0** | Roadmap renumber + this PLAN | 6 doc files lockstep + 8 stub renames + commit this PLAN.md | 1d |
| **5.1** | Supabase Foundation | `@supabase/supabase-js` npm dep + scout manifest + client/server init + env-var convention + Route Handler scaffold + first migration | 2-3d |
| **5.2** | Auth | OAuth Google + GitHub + magic-link + session middleware + sign-in/up/out UI shell + protected route guard + ToS/Privacy doc | 4-5d |
| **5.3** | Watchlist | `watchlists` table + RLS + CRUD Route Handlers + ⭐ icon on rankings + `/my/watchlist` page | 4-5d |
| **5.4** | Alerts | **Rule 18 `Metadata.alerts_*` diagnostic FIRST** + `alert_rules` schema + Vercel Cron + Supabase Edge Function + Resend HMAC + dedup + alert-prefs UI | 5-7d |

## Skill gaps to close (from phase-coordinator Mode A)

- **Gap 1** Postgres↔TS lockstep — `schema-check` covers only Pydantic↔TS.
  Propose SKILL.md **Rule 19 candidate** in 5.3: "Postgres migrations under
  `supabase/migrations/` + TS user-state types in `frontend/lib/types-user.ts`
  move together; new `schema_check_pg.py` asserts column types match TS"
- **Gap 2** Route Handler security cue — `security-reviewer` doesn't
  auto-fire on `frontend/app/api/**`. Add new auto-routing row in 5.1 PLAN
  + actual CLAUDE.md edit in 5.2
- **Gap 3** Alerts observability (Rule 18 forcing) — mirror Phase 4.5e
  PR 2 → PR 3 pattern: ship `Metadata.alerts_*` (queue depth, dispatch
  latency p95, bounce count 24h) BEFORE Resend wires real users

## Renumber tasks (in 5.0)

`git mv` operations:

| Current | New |
|---|---|
| `.claude/skills/phase-5/backtest-infrastructure/` | `phase-6/` |
| `.claude/skills/phase-5/conformal-predict/` | `phase-6/` |
| `.claude/skills/phase-5/meta-label/` | `phase-6/` |
| `.claude/skills/phase-5/shap-explain/` | `phase-6/` |
| `.claude/skills/phase-5/triple-barrier-label/` | `phase-6/` |
| `.claude/skills/phase-6/finbert-score/` | `phase-7/` |
| `.claude/skills/phase-6/lazy-prices-detect/` | `phase-7/` |
| `.claude/skills/phase-6/whisper-transcribe/` | `phase-7/` |

Text updates: `WORKFLOW.md:496-502` "Phase 5 foundational" → "Phase 6
foundational"; `SKILL.md` Supabase library-matrix row label `Phase 4.5e
+ Phase 5+` → `Phase 5 Supabase`; 6 doc files in lockstep.

## Acceptance criteria

Per sub-PR section — expanded after user approval of this outline.

## Methodology priors

None for Phase 5 Supabase hybrid (engineering work, not scoring
methodology). `methodology-scientist` NOT REQUIRED unless alert rules
later add score-prediction heuristics.

## Security & legal notes

- `security-reviewer` = most-fired subagent this Phase (every sub-PR)
- httpOnly cookie token storage via `@supabase/ssr` (NOT localStorage)
- RLS policies are the load-bearing security guard, NOT application-level filtering
- Resend HMAC webhook verification mandatory (prevents bounce-rate fraud)
- README disclaimer "Educational use only, ไม่ใช่ investment advice" extends to user features:
  - Watchlist UI must NOT show portfolio P&L
  - Alerts must NOT include "buy" / "sell" recommendations — only objective signal-state changes
- **ToS + Privacy Policy doc PR REQUIRED before 5.2 Auth** (land as 5.1.5 or alongside 5.2)

## Fallback triggers

- Supabase 500MB DB exceeded → reduce alert retention OR paid tier
- Resend 3k/mo exhausted → weekly digest OR paid tier OR drop alerts feature
- OAuth provider policy change → fallback to magic-link only
- Vercel Cron 2/day exhausted → migrate to Supabase Edge Function `pg_cron`
- RLS bypass discovered → P0 `incident-commander` spawn + rollback migration

## Cost model

$0/mo at launch (Supabase free + Resend free + Vercel hobby + Vercel Cron free) · estimated $25-50/mo at ~50k MAU scale (Supabase Pro $25 + Resend Pro $20)

## References

- Supabase Auth · Supabase RLS · Supabase Edge Functions
- Resend Webhooks (HMAC verification)
- Vercel Cron Jobs
- `portable-scout-then-integrate` skill (used in 5.1)
- `portable-observability-before-wiring` skill (used in 5.4)
- `portable-graceful-degradation-try-except` skill (used in 5.4 dispatch)
- `frontend-design-system` skill (used in 5.2 + 5.3 + 5.4 UI surfaces)

---

**Status**: OUTLINE — awaiting user approval to expand each sub-PR
acceptance-criteria section + commit + open Draft PR 5.0.
