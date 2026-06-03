---
target: compare view (/compare)
total_score: 33
p0_count: 0
p1_count: 0
timestamp: 2026-06-03T08-44-04Z
slug: frontend-app-compare-page-tsx
---
# Critique — Cross-stock Compare view (`/compare`)

Target: the compare surface — `CompareView.tsx` + `CompareMatrix.tsx` + `app/compare/page.tsx`, plus the `RankingTable` multi-select entry. Register: product (design serves the task).

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Compare bar shows N-selected + "Select 1 more"/"Compare N"; best-in-row ▲; skeleton pre-hydration; URL reflects selection. No confirm/toast on add (bar updates live, so minor). |
| 2 | Match System / Real World | 3 | Plain labels (Compare, Margin of safety, Loss chance, Flags). "Manipulation index" / Beneish-Dechow labels lean on prior methodology knowledge; right for the audience, but undefined inline on this triage surface. |
| 3 | User Control and Freedom | 4 | Remove column (×), Clear all, add via picker, editable/shareable URL, back-to-ranking. Full exits + free add/remove. |
| 4 | Consistency and Standards | 4 | Reuses the entire design system verbatim (Chip family, ScoreBadge/RecommendationBadge/SectorChip/LossChanceBadge, soft-OKLCH palette, tabular-nums, empty-state pattern). Detector: 0 findings. |
| 5 | Error Prevention | 3 | Checkbox disabled at cap 4; URL >4 capped; null cells → "—". The add-picker accepts free text → caught with a message (recovery) rather than hard-constrained (prevention). |
| 6 | Recognition Rather Than Recall | 3 | Datalist autocompletes tickers; the matrix shows everything side-by-side (no recall). Still requires knowing which tickers to compare unless arriving from the table. |
| 7 | Flexibility and Efficiency | 3 | Table multi-select = batch path; URL deep-link = power/share. But /compare-direct adds one ticker at a time (no paste-list / no keyboard shortcut / no Esc-to-remove). |
| 8 | Aesthetic and Minimalist Design | 4 | The focused decision-set IS the minimalist choice (calm-not-overload); grouped Overview/Pillars/Valuation/Risk; best-in-row guides the eye. Detector clean. |
| 9 | Error Recovery | 3 | Invalid ticker → "X isn't in the current universe" (plain, near input via aria-describedby); not-found + cap notes; empty state teaches. |
| 10 | Help and Documentation | 3 | Row sub-labels ("heuristic, lower is better"; "vs fair value, higher is better"); intro explains the ▲; disclaimer points at methodology. No inline glossary for the jargon terms. |
| **Total** | | **33/40** | **Good (28–35) — strong foundation; minor UX gaps** |

## Anti-Patterns Verdict

**LLM assessment**: Does not read as AI-generated. The surface is a restrained, ledger-style comparison matrix that inherits the app's deliberate "Bloomberg-minus-the-overload" register. No identical-card grid, no eyebrow-over-every-section, no gradient text, no hero-metric template, no glassmorphism. The best-in-row ▲ is a quiet sage mark, not a dopamine signal. Composition is purposeful: rows=metric × cols=stock, the exact topology a value-screener wants. The one place it could read generic — a comparison table — is saved by the metric-aware best-marking + the focused-set discipline + the soft semantic band.

**Deterministic scan**: `detect.mjs` over the 4 markup files returned `[]` (0 findings, exit 0). No flagged slop patterns (no side-stripe borders, over-rounding, ghost-card shadow pairing, stripe backgrounds, gradient text).

**Visual overlays**: No parent-injected `[Human]` overlay (this session has no direct browser-inject). The live browser-evidence half is delegated to the concurrently-running `expert-user-explorer` (drives Playwright on a local serve, bypassing the preview's SSO wall) — its experiential verdict confirms/extends this critique.

## Overall Impression

A confident, on-brand surface that does exactly one job well: let a value-quality screener see which of 2–4 shortlist names leads on each signal. The strength is restraint — it ships the focused decision-set (composite + 8 pillars + MoS + flag load) and links out for depth rather than dumping the full detail page into a column. It was already through a design review (2 FAILs fixed: ×-button 44px touch target, dark sticky-rail opacity), a Vercel build/runtime GO, and a lockstep pass. The biggest remaining opportunity is the **first-timer / power-user split on the /compare-direct entry**: the jargon is undefined inline and the only efficient multi-add path is back on the ranking table.

## What's Working

- **The ledger topology + metric-aware best-marking.** Rows=metric, cols=stock, a sticky label rail, and a sage ▲ that marks the leader ONLY where "better" is honest (max for composite/pillars/MoS, min for loss/flags/manip-index, never on raw price). This is the single best decision: it answers "which leads here?" at a glance without ever nudging a trade.
- **Zero design-system drift.** Every chip, color, and numeric column routes through the existing primitives; `pillarColor`/`flagLabel` were centralized so the matrix can never diverge from the detail page. Detector clean, palette PASS.
- **Honest, calm state design.** Invalid-ticker skip-with-note, >4 cap, null → "—", disabled-at-cap checkbox, skeleton pre-hydration, the educational-only disclaimer — the surface degrades gracefully and never overclaims.

## Priority Issues

**[P2] Jargon on a triage surface has no inline definition.** "Manipulation index", the Beneish/Dechow flag labels, and the two margin-of-safety framings assume the reader already knows the app's methodology. On the detail page that's fine (methodology is one scroll away); on a fast side-by-side triage surface a first-timer reads "Manipulation index 12 ▲" with no in-context "what's this?". Mitigated for the core finance-literate audience, but it's the surface's main first-timer barrier.
- *Fix*: a `title`/tooltip or a small `?`-affordance on the group headers (Risk · Valuation) linking to the methodology anchor, or a one-line legend under the matrix. *Suggested command*: `$impeccable clarify` (labels/microcopy) or `$impeccable onboard` (first-run hints).

**[P2] The Risk "Flags" cell grows unboundedly → row-height asymmetry across columns.** A flag-laden stock renders a tall wrapped chip stack while a clean stock is one "Clean" chip; the Flags row then has very different heights per column and the matrix loses its tabular rhythm exactly where the comparison matters most (the stress-tester's clean-vs-dirty contrast).
- *Fix*: cap visible chips at ~3 + "and N more" (full list in `title` / on the detail page), keeping the count chip + ▲ as the comparable signal. *Suggested command*: `$impeccable layout` or `$impeccable distill`.

**[P2] /compare-direct entry is one-ticker-at-a-time.** The efficient bulk path (tick rows → "Compare N") lives only on the ranking table. A power user who lands on `/compare` via a shared URL can only add singly through the datalist — no comma-separated paste, no keyboard accelerator, no Esc-to-remove-column.
- *Fix*: accept a comma-separated paste in the add-input (parse → add many), and/or a "pick from ranking" link. *Suggested command*: `$impeccable clarify` / `$impeccable harden`.

**[P3] Micro-perf + scan-pop.** The 502-option `<datalist>` re-renders on every selection change (native-cheap, but the one O(n) render here), and the manipulation-index value is intentionally neutral slate (no color band, to avoid inventing thresholds) so a dirty column doesn't pop on a fast scan. Both are deliberate trade-offs; note for a future pass.
- *Suggested command*: `$impeccable optimize` (datalist) — or accept as-is.

## Persona Red Flags

**Alex (power user)** — Lands on `/compare?compare=…` from a shared link. Adds a 4th name: must type it into the datalist one at a time; no paste-a-list, no keyboard shortcut, no Esc to drop a column. The batch path (table checkboxes) requires navigating back to `/`. The efficient path exists, but not where a power user starts.

**Sam (accessibility)** — Mostly strong: semantic `<table>` with `th scope`, sr-only `<caption>` + "best of N", labeled checkboxes, `aria-describedby` on the add-error, visible focus rings, best-mark never color-only. One real flag: the column-header `×` button at rest is `text-slate-400` (~3.3:1, sub-4.5:1) until hover — fine on interaction, sub-threshold at rest. The mobile row checkbox is 20px (secondary affordance; the card body is the 44px target).

**Casey (distracted mobile)** — Compare bar is bottom-fixed (thumb zone ✓); state survives via the URL (✓ returns to the same comparison); ×-button and Clear are now 44px (✓). Flag: 4 columns on a 390px phone is a lot of horizontal swiping (3 would be the comfortable default, 4 a stretch); the iOS datalist opens a full-page picker sheet.

**"The diligence reader" (project persona — skeptical value-screener, from PRODUCT.md)** — Served well: the side-by-side pillars + flags + MoS with best-in-row directly answers "which has the best value pillar AND the cleanest flags?". Flag: a careless reader could read a sage ▲ on the MoS row as a buy signal; the calm tone + "not investment advice" disclaimer + no-best-on-price discipline mitigate, but the ▲ is the one element that flirts with a recommendation cue.

## Minor Observations

- The top-left corner cell reads "N stocks" — a data-as-of date or "Metric" label might earn that slot better.
- Datalist `<option value="TICKER">Company Name</option>`: some browsers surface only the value; acceptable, but the company-name label is invisible on those.
- Group headers are now `sticky left-0` (good) — confirm in the live pass that a full-width sticky colgroup cell renders cleanly under horizontal scroll in both themes.

## Questions to Consider

- Should `/compare` earn a persistent way in (a sidebar entry, or a "compare these" affordance), or stay selection/URL-only? (The IA call was deferred to "selection + shareable URL" in the shape brief.)
- Does a triage surface need the jargon defined inline, or is linking to methodology enough for this finance-literate audience?
- Is 4 the right column cap, or is 3 the comfortable mobile default with 4 as a stretch?
