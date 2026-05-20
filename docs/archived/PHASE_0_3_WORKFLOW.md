# PHASE 0-3 (v1.0) — Archived Workflow

> **Archived 2026-05-20** as part of `.md` optimization PR D. v1.0
> shipped 2026-05-14 (tag [`v1.0.0-phase3e`](https://github.com/dackclup/quantrank/releases/tag/v1.0.0-phase3e)).
> All acceptance criteria below are ✅ MET. Content preserved verbatim
> from the original `WORKFLOW.md` L196-L474 as a historical record of
> what shipped in each sub-PR. Forward-looking work continues in
> [`WORKFLOW.md`](../../WORKFLOW.md) starting at Phase 4.

---

# PHASE 0 — Scaffolding + First Deploy

**Goal**: Empty `quantrank` repo on GitHub, deployed to Vercel, showing "Hello World" — proves the pipeline works before adding any analysis.

*(Same as before — see original WORKFLOW for full task breakdown 0.1-0.8)*

## Phase 0 Acceptance Criteria
- [ ] Repo exists at `github.com/<user>/quantrank` (public)
- [ ] CI workflow green on first push
- [ ] Site live at Vercel URL showing placeholder
- [ ] `compute-rankings.yml` succeeds when triggered manually (no-op stub)
- [ ] PHASE_STATUS.md committed

---

# PHASE 1 — Universe + Prices Ingestion

**Goal**: GitHub Actions fetches S&P 500 prices, computes a stub composite (just based on momentum), outputs valid `rankings.json`, and the frontend displays a real ranking table.

**Knowledge ref**: stock_ranking_knowledge.md Section 5 (Free Data Stack), Section 25 (Caching), Section 7.3 (momentum).

*(Tasks 1.1-1.10 same as before)*

## Phase 1 Acceptance Criteria
- [ ] `compute-rankings.yml` runs in <15 min on first try
- [ ] `public/data/rankings.json` exists with 500 stocks ranked by momentum
- [ ] `metadata.json` reflects accurate timestamp
- [ ] Vercel URL shows working table after auto-redeploy
- [ ] Mobile view of ranking table is readable

---

# PHASE 2 — Fundamentals via SEC EDGAR

**Goal**: Pull real annual + quarterly financials, point-in-time correct (`filing_date`).

**Knowledge ref**: stock_ranking_knowledge.md Section 5 (SEC EDGAR), Section 27 (schema), Rule 5 (point-in-time).

*(Tasks 2.1-2.8 same as before)*

## Phase 2 Acceptance Criteria
- [ ] All 500 tickers have ≥5 years annual fundamentals
- [ ] `filing_date` populated for every row
- [ ] Golden-value tests pass for 5 reference tickers
- [ ] Stock detail pages exist at `/stock/AAPL` etc.
- [ ] Cross-sectional null rate <5% on revenue, net income, total assets

---

# PHASE 3 — Classical Features + Composite + Defenses → v1.0

**Goal**: All 30+ classical metrics implemented, 8 pillar scores, full composite, fair price ensemble, **6 Tier-1 defenses, 3 Tier-2 defenses, 2 Tier-3 defenses**. **Tag v1.0.**

**Knowledge ref**: stock_ranking_knowledge.md Sections 6-11 (formulas), Section 21 (normalization), Section 10 (fair price ensemble).

**Defense ref**: `docs/RESEARCH_FINDINGS.md` §"Defense Playbook" — 11 research-validated defenses ship across PR 3c/3d/3e (6 + 3 + 2).

**Sub-PR Strategy** (locked, defense-augmented 2026-05-09):
- ✅ PR 3a — Pillar feature modules (foundation, no production output) — DONE
- ✅ PR 3b — Normalization, pillar aggregation, composite, risk overlay (Altman Z″ + Sloan accruals = 2 vetoes) — DONE
- 🟡 PR 3c — Fair price ensemble + price history + **Tier-1 defenses (6)** — NEXT (~960 LOC)
- ⚪ PR 3d — Charts (Pillar Radar + Fair Price Bar + Price History) + about page + **Tier-2 defenses (3)** (~520 LOC)
- ⚪ PR 3e — README polish + **Tier-3 defenses (2)** + Honest Limitations + tag **v1.0** (~370 LOC)

*(Tasks 3.1-3.10 same as before, broken across 5 sub-PRs)*

## PR 3c — Tier-1 Defense Layer (research-validated, ~260 LOC)

Per `docs/RESEARCH_FINDINGS.md` §"PR 3c-Specific Recommendations". 6
defenses operating in 3 modes (VETO / GUARD / ANNOTATE).

**(1) Net Stock Issuance veto** — extend `compute/scoring/risk_overlay.py`:
```python
# NSI per Pontiff-Woodgate (2008, JF)
nsi_t = ln(shares_outstanding_t / shares_outstanding_{t-12m})
# Top decile WITHIN sector (post-SBC era requires sector relativity)
if nsi_rank_within_sector >= 0.90:
    flag `net_issuance_top_decile`  # joins 2 existing vetoes → 3 total
```
EDGAR source: `dei:EntityCommonStockSharesOutstanding` (preferred) →
fallback `us-gaap:CommonStockSharesOutstanding`. Adjust for splits via
yfinance `Ticker.splits`.

**(2) Tangible BVPS with full intangibles netting** — new module
`compute/valuation/tangible_book.py`:
```python
def tangible_book_value_per_share(snap):
    equity = snap.stockholders_equity or 0
    goodwill = snap.goodwill or 0
    intangibles = snap.intangibles_net or 0  # fallback chain
    if snap.shares_outstanding in (None, 0):
        return None
    tbvps = (equity - goodwill - intangibles) / snap.shares_outstanding
    return tbvps if tbvps > 0 else None
```
EDGAR fallback chain for intangibles:
`us-gaap:IntangibleAssetsNetExcludingGoodwill` →
`us-gaap:OtherIntangibleAssetsNet` →
`us-gaap:FiniteLivedIntangibleAssetsNet`.
TBVPS used in Graham + RIM for fair price (NOT in Value pillar — pillar
keeps fast-TTM Graham; intentional dual implementation).
Flag `goodwill_heavy` if TBVPS / BVPS_reported < 0.5.

**(3) Stale filing guard (soft 120d / hard 180d)** —
`compute/valuation/applicability.py`:
```python
if filing_lag_days > 180:
    return None  # null all fair_price + risk_flag stale_filing_hard
elif filing_lag_days > 120:
    valuation_warnings.append("stale_filing_soft")
```
Justification: 10-Q deadline 45d (large accelerated); 120d = 75d past
deadline (unusual); 180d = missed filing entirely → restatement risk.

**(4) Multi-method outlier guard at 5×** — `compute/valuation/ensemble.py`:
```python
for method, value in method_estimates.items():
    if value > 5.0 * current_price or value < 0.2 * current_price:
        outlier_methods.add(method)  # exclude from max_fair_price
        valuation_warnings.append(f"extreme_{method}_estimate")
        # Still in median (median is robust to one outlier)
```
5× chosen empirically (RESEARCH_FINDINGS §IV-4). Even high-growth tech
rarely shows fair-value-to-price > 5× across all methods; 10× would let
model bugs slip through.

**(5) Terminal g constraint** — `compute/valuation/dcf.py`:
```python
TERMINAL_GROWTH_MAX = 0.03   # long-run nominal GDP cap (Damodaran)
g_constrained = min(TERMINAL_GROWTH_MAX, WACC - 0.01)  # 100bp buffer
if g >= WACC - 0.01:
    return None  # mathematical sanity
```

**(6) Quality pillar sector exclusions extended** —
`compute/scoring/sector_rules.py`:
```python
SECTOR_BLACKLIST = {
    # Existing
    "magic_formula": {"Financials", "Utilities", "Real Estate"},
    "asset_turnover": {"Financials"},
    # NEW (PR 3c)
    "ebit_based_roic": {"Financials", "Utilities"},
    "gross_profitability": {"Financials"},
    "ev_ebitda_multiple": {"Financials"},
}
```
Reasoning: Greenblatt's capital-structure-distortion argument applies to
ALL Quality metrics using EBIT, total debt, or invested capital.

## PR 3d — Tier-2 Defense Layer (~270 LOC)

**(7) Going-concern phrase scan** —
`compute/features/text/going_concern.py`:
```python
GOING_CONCERN_PHRASES = {
    "substantial doubt", "going concern",
    "ability to continue", "raise substantial doubt",
    "unable to continue as a going concern",
}
def scan_going_concern(filing_10k_text):
    matches = [p for p in GOING_CONCERN_PHRASES
               if p in filing_10k_text.lower()]
    return len(matches) > 0
```
ANNOTATE-only flag (`going_concern_warning`) but pair with Altman Z″
< 1.10 for hard veto.

**(8) 8-K Item 4.02 hard veto + Item 4.01 soft flag** —
`compute/ingest/eight_k_events.py`:
```python
def scan_8k_events(cik, lookback_months=12):
    filings = edgar.Company(cik).get_filings(
        form="8-K", date_after=lookback_months_ago)
    for f in filings:
        if "4.02" in f.items:  # Non-Reliance on Previously Issued
            return ("hard_veto", "restatement_4_02")
        if "4.01" in f.items:  # Changes in Certifying Accountant
            return ("soft_flag", "auditor_change_4_01")
    return None
```
Item 4.02 in trailing 12m → hard veto; Item 4.01 → annotate-only.

## PR 3e — Tier-3 Defense Layer + v1.0 polish (~370 LOC)

**(9) Beneish M-Score full 8-ratio** — `compute/features/text/beneish.py`:

Full formula per Beneish 1999 *FAJ*:
```
M = -4.84 + 0.92*DSRI + 0.528*GMI + 0.404*AQI + 0.892*SGI
    + 0.115*DEPI - 0.172*SGAI + 4.679*TATA - 0.327*LVGI
```
Threshold M > -2.22 → flag `beneish_high`.

⚠️ **CRITICAL**: ANNOTATE-only, NO scoring penalty. Reasons:
1. Sloan accruals already encodes much of TATA → double-jeopardy
2. Beneish FP rate ~30% in broad market (Beneish 2022 confirm)
3. Sector relativity matters: tech and biotech inflate DSRI/SGI

Implementation needs 2-year balance items. Use existing
`fetch_fundamentals_history` from PR 3a for prior fiscal year.

**(10) Dechow F-Score** — `compute/features/text/dechow_f.py`:

Dechow et al. 2011 F-Score is parallel to Beneish — different ratio
inputs (RSST accruals + non-financial proxies). Average sensitivity 73%,
type-II 27%; complementary to Beneish.

Both flags ANNOTATE-only. Display side-by-side in stock detail UI.

**(11) Honest Limitations section** in README v1.0:

Per `docs/RESEARCH_FINDINGS.md` §"Honest Limitations Section". User-facing
copy MUST include:
- Frauds we cannot catch: Madoff-style fabrication; off-shore related-
  party round-trips (Wirecard); audit-firm complicity; post-acquisition
  baseline reset
- Realistic FP/FN rates with academic citations
- Decay reality: 58% cumulative (McLean-Pontiff 2016)
- Free-data fragility caveat
- "QuantRank is a risk-stratifier and screener, not a fraud guarantor"
- Diminishing returns: defense set freezes at v1.0; rotate (don't stack)
  beyond 4 fraud signals

## Phase 3 / v1.0 Acceptance Criteria — ✅ ALL MET (2026-05-14)

### Core (existing)
- [x] All 30+ classical metrics implemented; golden value tests pass
- [x] StockRank computed for all S&P 500 weekly
- [x] Top-10 are sensible (high ROE, low D/E, decent momentum)
- [x] Bottom-10 are sensible (distressed, low quality)
- [x] Fair Price exists for all stocks with ≥3 applicable methods —
      **99.2% coverage (498/502)** at v1.0
- [x] Mobile site has table + detail page + radar + fair price
- [x] Lighthouse mobile score >85
- [x] README professional with disclaimer + Honest Limitations section

### Defenses (research-validated, NEW 2026-05-09)
- [x] **3 active vetoes**: Altman Z″ + Sloan accruals + Net Stock
      Issuance — confirmed live in production
- [x] **4 numerical guards**: stale_filing (120/180), outlier_5x,
      terminal_g (≤ WACC−100bp), sector_exclusion (Quality pillar) +
      `data_quality_input_corruption` (Defense #7, $10K TBVPS ceiling)
- [x] **5+ annotate-only flags**: goodwill_heavy, value_trap_risk,
      extreme_<method>_estimate (×6 method slots), stale_filing_soft,
      **going_concern_disclosure** (Mayew 2015 with Option B MD&A
      restriction — 1.0% FP rate), **beneish_high** (Beneish 1999
      8-ratio), **dechow_high** (Dechow 2011 Model 1)
- [x] **1 hard event veto**: 8-K Item 4.02 — implemented but
      **deferred** behind `_EIGHT_K_DEFENSES_ENABLED = False` per
      PR 3e final state; re-enable in Phase 4 (4f)
- [x] Tangible BVPS uses full intangibles netting (goodwill + identifiable)
- [x] **Honest Limitations** section in README (PR #46, 126 lines —
      frauds we cannot catch, realistic FP/FN rates, decay reality
      58% cumulative, free-data fragility, diminishing returns)
- [x] Defense badges display correctly on stock detail UI

### Audit-#6 deep-clean (added mid-3e, completes the v1.0 ingest layer)
- [x] 9 `_NORMALIZED_LATEST` flow items replaced with TTM-aware
      `_TTM_FLOW_TAGS` + `_try_ttm_max_fresh` helper
- [x] `pe_ratio` formula switched from single-period `eps_diluted` to
      `NI_TTM / shares` — universe median PE dropped **77.8 → 23.2**
- [x] Smart `shares_outstanding` fallback (DEI + weighted-avg with
      MAX-by-period_end) — fixes META / MA / ACN / 24 other tickers
      that shipped with shares=None pre-audit
- [x] Revenue / NI chains expanded for utilities (DUK), banks (WFC/GS),
      tech (CRWD), BKNG-class
- [x] `data_quality_input_corruption` patterns expanded: rev<$50M +
      |NI|>|rev| (catches HBAN-class residual cleanly)
- [x] Workflow cache key v2 bump forces fresh fetch through the
      schema-changed ingest layer
- [x] Workflow rebase-then-push hardens against "main moved during
      compute" race (PR #55)

### Ship
- [x] **v1.0.0 tag pushed + GitHub Release published** (2026-05-14)
- [x] Production verified: commit `b5bc65f3` / workflow run #32

---
