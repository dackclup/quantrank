---
target: frontend/app (all pages)
total_score: 26
p0_count: 0
p1_count: 3
timestamp: 2026-06-01T15-05-48Z
slug: frontend-app-all-pages
---
# QuantRank — Re-critique #2 (all pages, post P1–P3)

Combined `$impeccable critique` re-run after the P1–P3 shipping spree (#357 detail-page IA · #358 URL filter state · #359 loss-chance band + empty-state + nits, on top of #352/#355/#356 polish). Two independent, unanchored assessments — **A** (design-director, source review) + **B** (real-browser persona pass) — plus the bundled detector. Baseline to delta against: prior **27/40 Nielsen + 16/20 audit** (2026-06-01T13-08-11Z).

## Headline delta

**27 → 26 Nielsen — essentially flat, and that's the honest result.** The P1–P3 work *did* lift the dimensions it targeted (A scores **H5 error-prevention 2→3** from the empty-state recovery, **H9 error-recovery 2→3**), and B confirms the substance is solid: **data cross-check 100% correct** (incl. the loss-chance values that no longer mis-band — the "60% · Neutral" bug is gone), **0 console errors**, focus-trap works, URL filter state works, risk cards trustworthy. But the re-critique is unanchored, and a *harsher, different* reviewer pass docked three other dimensions for a **new tier of issues the first critique never surfaced** — mostly **palette coherence**: H4 4→3, H6 3→2, H8 3→2. Net −1 (within noise). The real signal isn't the number: the **original structural/a11y backlog is cleared**, and what's left is finer — palette-token coherence on the charts + a couple of detail-page display gaps.

## Design Health Score (Nielsen, /40)

| # | Heuristic | Score | Δ | Key issue |
|---|-----------|-------|---|-----------|
| 1 | Visibility of system status | 3 | = | No "data as-of" date in the detail decision-zone; it's buried in the collapsed Supporting-data drawer |
| 2 | Match real world | 3 | = | "Composite / pillar / MoS" finance terms need prior knowledge; sub-captions help |
| 3 | User control & freedom | 3 | = | Can't remove an active-filter chip from *inside* the open drawer (close → click chip → reopen) |
| 4 | Consistency & standards | 3 | ▼1 | `bg-red-600` "Sell" dot + "High" loss-chance dots render RAW alarm-red (not in the soft-color allowlist) vs soft terracotta everywhere else |
| 5 | Error prevention | 3 | ▲1 | Empty-state "Clear filters" recovery landed (#359); 0–0 score range still possible but recoverable |
| 6 | Recognition vs recall | 2 | ▼1 | Pillar bars use raw `rgb()` → "Strong" bar green ≠ "Strong" chip green; ScoreBadge vs Pillar tier-words conflict |
| 7 | Flexibility & efficiency | 2 | = | URL filters shipped (good) but still no FilterDrawer keyboard shortcut, no export, no per-page URL |
| 8 | Aesthetic & minimalist | 2 | ▼1 | Detail page = 9 same-elevation cards; #357 demoted raw-metrics but `FairPriceCard` (reference) still sits at decision-elevation |
| 9 | Error recovery | 3 | ▲1 | FairPrice outlier verdicts + flag explanations are strong; a few raw `extreme_*_estimate` keys still leak |
| 10 | Help & documentation | 2 | = | Still no inline "what is this?" on Score / MoS / Loss / pillars |
| **Total** | | **26/40** | **▼1** | Acceptable — original backlog cleared; next tier is palette coherence + display gaps |

## Technical / audit delta (/20, from B's real-browser evidence)

| # | Dimension | Score | Note |
|---|-----------|-------|------|
| 1 | Accessibility | 3 | Focus-trap ✓ (re-confirmed), most targets 44px ✓; residual: the Disclaimer "more" 24px (intentional/documented) + FilterDrawer chips 27px on DESKTOP (intentional `lg:min-h-0`) |
| 2 | Performance | 4 | 0 console errors across 8 sessions, no overflow 320→1280 |
| 3 | Responsive | 4 | Clean at 320 / 390 / 1280; mobile cards + daily-change pill render correctly |
| 4 | Theming | 3 | Dark mode correct; the new palette-coherence gap (raw `rgb()` pillar bars + `red-600` dots) is the holdout |
| 5 | Anti-Patterns | 3 | Detector 5/5 false positives; residual fingerprints: pillar raw-rgb, Coming-soon tiles, eyebrow-on-every-section |
| **Total** | | **~17/20** | ▲1 — the #355/#356 a11y + contrast work shows; palette coherence is the remaining ding |

## Anti-Patterns Verdict

**Largely not AI-made** (A: "genuine visual reasoning" — OKLCH token system, container-query hero, disciplined motion). Residual fingerprints: the **inline `rgb()` color explosions** in `PillarRadarChart` (8 bare values duplicated rather than calling the canonical `scoreAccentColor`), the **eyebrow-on-every-section** terminology fatigue, and the **two "Coming soon" tiles** (intentional per PR #344, but they read as unfinished). **Detector:** 5 findings, all false positives (em-dashes in CSS/TSX comments, `.stagger-N` markers, `RecommendationBadge` size-props).

## What's Working

- **OKLCH soft-color token architecture** (A: "unusually careful for a solo project") + **FilterDrawer** (A: "best-designed component" — focus-trap, live count, restore) + **the motion vocabulary** (one curve, reduced-motion guards, the keyframe gauge-sweep).
- **B's substance confirmations**: 100% data-vs-JSON cross-check (AAPL/AEP/NVDA score·MoS·loss-chance·fair-price·flags all correct, `Math.round` banding confirmed — the loss-chance boundary fix works), 0 console errors, focus-trap WCAG 2.4.3, URL filter round-trip clean, risk cards name+explain+cite every flag.

## Priority Issues (the new tier)

**[P1] Palette coherence — charts + dots escape the OKLCH soft-color system.** Two parts, same root cause: (a) `PillarRadarChart` bar fills use raw `rgb(5 150 105)` etc. (bypass the `!important` remap) → the "Strong" *bar* is a different, more-saturated green than the "Strong" *chip* on the same card; (b) `bg-red-600` on the "Sell" recommendation dot + the "High" loss-chance dots (RecommendationBadge / LossChanceBadge / RankingTable) isn't in the `globals.css` allowlist → raw alarm-red vs the soft terracotta everywhere else. **Fix:** pillar bars → Tailwind classes or `var(--c-pos-*)`; `bg-red-600 → bg-rose-500` (which IS allowlisted). → `$impeccable colorize`

**[P1] Detail-page hierarchy — finish the demotion** (`FairPriceCard`). #357 recessed raw-metrics + data-quality into the collapsed zone, but the *reference* `FairPriceCard` still renders at the same white `bg-white` elevation as the *decision* `FairPriceBarChart`. One-class fix: `bg-slate-50` recessed surface (matching the Supporting-data treatment). → `$impeccable polish`

**[P1] Daily change missing from the detail hero** (B MAJOR, real display gap). `price_change_1d_pct` is populated in the JSON and shown on the mobile rankings card, but the detail hero shows only the 52-week return ("+54% past year"), never the 1-day move — a user who drilled in after seeing a big daily move loses it. **Fix:** add a daily-change pill to the hero metric row. → `$impeccable harden`

**[P2] Loss-chance band word missing on the detail hero** (B MINOR). Mobile cards show "Neutral" / "Moderate-low" next to the %, the detail hero shows only "56%". Add the band word for consistency. → `$impeccable clarify`

**[P3] Tier-label vocabulary conflict.** `ScoreBadge` says "Exceptional / Strong / Average / Weak / Poor"; `PillarRadarChart` says "Strong / Decent / Weak / Poor" — a 72 is "Exceptional" on the donut but "Strong" on the bar. Consolidate to one label set. → `$impeccable clarify`

**[Verify-before-fix — declined / non-issues]** B flagged three that don't hold: the "Supporting data toggle 42×24px" is the **Disclaimer "more" button** (deliberate WCAG-2.5.8 24px, documented #355) — mis-attributed; the **FilterDrawer chips at 27px on desktop** are intentional (`lg:min-h-0` — 44px on touch, compact on mouse); the "loss-chance % missing" was a **text-extraction artifact** (it renders fine). The **Coming-soon tiles** remain a deliberate user decision (#344).

## Persona Red Flags

- **Alex (power user):** the alarm-red "Sell" dot + the pillar bars not matching the chip ramp read as incoherent; can't remove a filter chip from inside the drawer; the two MoS formulas (vs-fair-value hero vs vs-market-price FairPriceBarChart) still lack in-page disambiguation.
- **Sam (keyboard/SR):** the MoS donut + pillar-bar `title` tooltips sit on non-interactive `<div>`s (invisible to keyboard/SR); otherwise focus-trap + summary aria-label are correct.
- **Casey (mobile):** two "Coming soon" tiles tax vertical space; otherwise clean (no overflow, 44px targets, daily-change pills render).

## Questions to Consider

- Should the detail hero surface a compact **"Data as of {date}"** line? (The filing date is currently only inside the collapsed Supporting-data drawer.)
- The pillar chart shows **8 bars** but 2 (Sentiment/ML) are Phase-5 reserved — does showing all 8 misrepresent the methodology to someone who counts them?
- Is the static **→ chevron** in the FairPrice "Today's price → Median fair price" headline adding info, or implying a directional "go from here to there"?
