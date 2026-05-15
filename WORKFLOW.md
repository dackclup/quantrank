# WORKFLOW — QuantRank Build Plan
**Phase-by-phase guide for building QuantRank from scratch via Claude Code on mobile**

> Companion to `SKILL.md`, `stock_ranking_knowledge.md`, and `RESEARCH_FINDINGS.md`. Each phase produces a **working, testable deliverable visible at the public Vercel URL**. Designed for mobile-only development (Claude Code app + GitHub mobile + Vercel mobile).

> **Roadmap Strategy**: Option B (Research-Backed) with Option A (Original) as per-phase fallback. v1.0 (Phases 0-3) ships first regardless. Phases 4-8 may revert to Option A if blockers hit.

---

## How This Workflow Adapts to Mobile-Only Dev

You cannot run Python or Node locally. All execution happens in **GitHub Actions** (compute) and **Vercel** (frontend deploy). **Phase 5+** adds **Kaggle Notebooks** (heavy ML training) and **Modal** ($30/mo credits for LLM inference). This means:

1. **No "run it locally" steps** — every test runs in CI on push.
2. **`workflow_dispatch` everywhere** — manual trigger from GitHub mobile app for debugging.
3. **Smaller commits, more pushes** — iterate via CI logs.
4. **Visual verification = Vercel preview URL** on every PR.
5. **`PHASE_STATUS.md`** in repo tracks where you are. Update after every phase.
6. **Phase 5+: Kaggle/Modal triggered from GitHub Actions** via API tokens in secrets.

---

## Tools You'll Use Daily

| Tool | What for | Phase |
|---|---|---|
| **Claude Code (mobile app)** | Edit code, commit, push to GitHub | All |
| **GitHub mobile app** | View Actions logs, trigger workflow_dispatch, review PRs | All |
| **Vercel mobile app** | View deployment status + preview URL | All |
| **Mobile browser** | Open Vercel preview URL to see live site | All |
| **Kaggle (web/mobile)** | Monitor heavy training jobs | 5+ |
| **Modal dashboard** | Monitor LLM/Whisper inference jobs | 6+ |

---

## Phase Overview (9 Phases — Option B Research-Backed)

| Phase | Goal | Deliverable | Est. effort | Roadmap |
|---|---|---|---|---|
| 0 | Project scaffolding + first deploy | Empty site live on Vercel | 1 day | Both |
| 1 | Universe + prices ingestion | rankings.json with stub scores | 2 days | Both |
| 2 | Fundamentals from SEC EDGAR | Real data flowing into JSON | 3 days | Both |
| 3 | Classical features + composite | Working v1.0 with 30+ metrics | 5 days | Both |
| **v1.0 SHIPS** | | **Tag v1.0** | | |
| 4 | **Factor Consolidation** ⭐ | OSAP + JKP + Qlib + IPCA | 1-2 weeks | **B (NEW)** |
| 5 | ML meta-learner + SHAP | LightGBM + Triple-Barrier + Conformal | 1-1.5 weeks | B (enhanced) |
| 6 | Sentiment v2 | Whisper + 8-K + Lazy Prices | 1-1.5 weeks | B (enhanced) |
| 7 | Regime + Portfolio v2 | Student-t HMM + TDA + NCO | 1 week | B (enhanced) |
| 8 | Universe expansion | S&P 1500 → v2.0 | 3-5 days | Both |

**To v1.0**: ~11 working days. Calendar (full-time): 2-3 weeks.
**To v2.0 (Option B)**: ~32-37 working days. Calendar: 7-8 weeks.
**To v2.0 (Option A fallback)**: ~25-28 working days. Calendar: 5-6 weeks.

---

## SEC Filing Roadmap (Forms used per phase)

QuantRank pulls data from SEC EDGAR via `edgartools`. Each phase
gradually expands which SEC filing types feed the ranking. Phase 3 /
v1.0 ships with the minimum viable set; Phase 5-8 layer in additional
forms as new signals come online. This table is the canonical reference
for "what filings does the system read?" — keep it in sync when a phase
acceptance criterion changes.

| Form | What it is | Phase introduced | Used for | Status |
|---|---|---|---|---|
| **10-K** | Annual report (audited financials) | Phase 2 | Annual history (CAGR, RIM 3y-avg ROE, Beneish prior-year inputs, Dechow Δroa, Piotroski F-score, going-concern MD&A text scan) | ✅ active |
| **10-Q** | Quarterly report (unaudited) | Phase 2 | TTM aggregation (Q1+Q2+Q3 of fiscal year; Q4 from the 10-K), latest balance sheet items, EPS | ✅ active |
| **8-K Item 4.01** | Auditor change | Phase 3d → 4 | Tier-2 `auditor_change` annotate flag (Cohen-Malloy-Nguyen 2020 type) | 🟡 deferred (`_EIGHT_K_DEFENSES_ENABLED = False`) — re-enable in Phase 4 |
| **8-K Item 4.02** | Non-reliance on prior financials | Phase 3d → 4 | Tier-2 `non_reliance_filing` hard veto | 🟡 deferred — re-enable in Phase 4 |
| **8-K (other items)** | Material events (M&A, CEO change, guidance, restatements, NT-filings, …) | Phase 5+ | Sentiment v2 — event-driven re-rate signals (Lazy Prices pattern, Cohen-Malloy-Pomorski 2012) | ❌ not used (Phase 5 / 6 work) |
| **Form 4** | Insider transactions (officers, directors, 10%+ holders) | Phase 5 | Insider-signal pillar (cluster buys vs. routine sells; Cohen-Malloy-Pomorski 2012 *Decoding Inside Information* — cited in bibliography but not implemented) | ❌ not used |
| **DEF 14A** | Proxy statement (exec comp, board composition, voting) | Phase 5 | Governance pillar (currently inactive in PillarScores schema) — CEO/CFO comp, board independence, dual-class structure penalties | ❌ not used |
| **13F-HR** | Institutional holdings ($100M+ AUM funds) | Phase 5 / 6 | Smart-money / sentiment pillar — Bayesian update of holdings changes, hedge-fund-vs-mutual-fund divergence | ❌ not used |
| **20-F** | Annual report (foreign private issuers — ADRs like ASML, TSM, NVS) | Phase 8 | Replaces 10-K when the universe expands beyond domestic S&P 500. Same intent (annual fundamentals + MD&A text) but different XBRL taxonomy. Phase 8 universe expansion will hit this. | ❌ not used |
| **6-K** | Quarterly equivalent for foreign issuers | Phase 8 | Replaces 10-Q for foreign issuers. | ❌ not used |
| **N-CSR / N-Q** | Mutual fund + ETF reports | n/a | Out of scope — QuantRank ranks individual equities, not funds. | ❌ never |
| **S-1, S-3** | IPO + shelf registration | n/a | Out of scope for v1.0 — newly-public tickers have insufficient annual history for our defenses anyway. Possible Phase 6 "recent IPO" warning flag using filing date. | ❌ never |

### Per-phase summary

- **Phase 2 (v1.0 prep)**: 10-K + 10-Q. ~ALL TTM + balance + annual data flows through these two.
- **Phase 3 (v1.0)**: same — 10-K + 10-Q + (deferred) 8-K Items 4.01/4.02.
- **Phase 4 (factor consolidation + defense re-enable)**: same forms; the 8-K Tier-2 defenses re-enable. No new SEC forms.
- **Phase 5 (ML + Sentiment)**: **first phase that adds new SEC forms** — Form 4 (insider) + 13F-HR (smart-money) + 8-K-other (event-driven sentiment) + DEF 14A (governance pillar).
- **Phase 6 (Sentiment v2)**: 8-K event timeline + earnings call transcripts (separate API, not SEC).
- **Phase 7 (Regime + Portfolio v2)**: no new SEC forms — pure portfolio-construction layer.
- **Phase 8 (Universe expansion S&P 1500 + ADRs)**: **first phase that adds 20-F + 6-K** for foreign private issuers in the expanded universe.

### Why this matters

Without this map, it's easy to write a Phase 5 PR that pulls Form 4 data
on day one without realizing the ingest layer needs significant work
(Form 4 has a different XBRL taxonomy + different filing cadence). The
roadmap also clarifies what's intentionally NOT in scope (S-1, N-CSR
etc.) so spec drift doesn't accidentally drag them in.

---

## Defense Roadmap (Research-Validated, 2026-05-09)

QuantRank operates in **3 defense modes** against analysis errors at all
three layers (data integrity, computation, methodology):

1. **VETO** — exclude flagged stock from Top-5 badge (composite score
   unchanged). 3 active by v1.0.
2. **GUARD** — return null + flag (e.g., null fair_price for stale
   filings). 4 numerical guards by v1.0.
3. **ANNOTATE** — warning only, no score change. 5+ flags by v1.0.

**Architectural principle (locked):** Risk overlays are
**annotate-and-veto-Top-N**, never scoring inputs. Empirical evidence
(Beneish-Vorst 2021; Bao-Ke 2020; McLean-Pontiff 2016) shows fraud-
detection FP rates ≥30% in broad market and anomaly returns decay 58%
cumulative — penalizing every name introduces more error than it removes.

Defense additions per phase (full bibliography in
[`docs/RESEARCH_FINDINGS.md`](docs/RESEARCH_FINDINGS.md) §"Defense Playbook"):

| Phase | Defense | Mode | Cost | Source |
|---|---|---|---|---|
| 3c | Net Stock Issuance | VETO | 80 LOC | Pontiff-Woodgate 2008 *JF* |
| 3c | Tangible BVPS (full intangibles netting) | GUARD | 50 LOC | Penman 2013; Damodaran |
| 3c | Stale filing 120/180d | GUARD | 40 LOC | (10-Q practitioner rule) |
| 3c | Multi-method outlier 5× | GUARD | 30 LOC | (DCF terminal sanity) |
| 3c | Terminal g ≤ WACC − 100bp | GUARD | 20 LOC | Damodaran |
| 3c | Quality sector exclusions extended | (logic) | 40 LOC | Greenblatt 2005 |
| 3d | Going-concern phrase scan | ANNOTATE | 120 LOC | Mayew-Sethuraman-Venkatachalam 2015 |
| 3d | 8-K Item 4.02 hard veto | VETO (event) | 100 LOC | Schroeder 2024 SSRN |
| 3d | 8-K Item 4.01 auditor change | ANNOTATE | 50 LOC | (Reg S-K Item 304) |
| 3e | Beneish M-Score full 8-ratio | ANNOTATE | 150 LOC | Beneish 1999 *FAJ* |
| 3e | Dechow F-Score | ANNOTATE | 100 LOC | Dechow et al. 2011 *CAR* |
| 4 | PBO + Deflated Sharpe gating | (infra) | 200 LOC | Bailey-de Prado 2014 |
| 4 | IC decay monitor | (infra) | 150 LOC | McLean-Pontiff 2016 |
| 4 | Cross-source validator | GUARD | 150 LOC | (data-fragility defense) |
| 5 | Bao-Ke ML fraud (RUSBoost) | ANNOTATE | 300 LOC | Bao et al. 2020 *JAR* |
| 5 | MAPIE conformal wrappers | (arch) | 150 LOC | Angelopoulos-Bates 2021 |
| 5 | Purged + Embargoed CV (skfolio) | (arch) | 100 LOC | López de Prado 2018 |
| 6 | Lazy Prices 10-K diff | ANNOTATE | 250 LOC | Cohen-Malloy-Nguyen 2020 *JF* |
| 6 | FinBERT MD&A classifier | ANNOTATE | 400 LOC | Loughran-McDonald + FinBERT |
| 6 | Whisper Vocal Delivery Quality | ANNOTATE | 600 LOC | Baik-Kim-Kim-Yoon 2025 *JAE* |
| 6 | Insider routine vs opportunistic | ANNOTATE | 200 LOC | Cohen-Malloy-Pomorski 2012 |
| 7 | HMM 3-state regime gating | (arch) | 250 LOC | Wang et al. 2020 *JRFM* |
| 7 | Persistent-homology TDA crash detector | (arch) | 300 LOC | Gidea-Katz 2018 |
| 8 | Bonferroni multi-test thresholds | (infra) | 100 LOC | Harvey-Liu-Zhu 2016 |
| 8 | Liquidity backstop ($5M ADV) | GUARD | 50 LOC | (microstructure defense) |

**Honest limits** (research-validated, post-v2.0 freeze):

- Marginal AAER capture < 5% beyond 4 fraud signals (Beneish + Dechow +
  Bao-ML + textual). After that: rotate signals, don't stack.
- Madoff-style fabrication (revenue/cash/customers all fictitious): **no
  quantitative system** based on filed financials can detect.
- Decay reality: 26% out-of-sample + 32% post-publication = 58% cumulative
  per McLean-Pontiff 2016. Plan for it via IC decay monitor (Phase 4+).
- Beneish FP/FN frontier not broken by ML (Beneish 2022 confirm). Expect
  ~30% type-I FP at −2.22 cutoff in broad market, ~15-20% in S&P 500.
- All defense flags are **risk stratifiers**, not fraud verdicts.

⚠️ **Critical license alert** (verified 2026-05-09):
- **mlfinlab is all-rights-reserved** (Hudson & Thames commercial license
  required). DO NOT depend on it. Reimplement Triple-Barrier +
  Meta-Labeling + Purged CV from primary papers (López de Prado 2018)
  under MIT. Algorithms are not patented.
- **JKP data is CC BY-NC 4.0** (non-commercial). Educational static-site
  use OK; if commercializing later, build factors from raw OSAP data.
- **Loughran-McDonald dictionary** is free for academic research;
  commercial license required. State explicitly in README for
  static-site use.

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

# PHASE 4 — Factor Consolidation ⭐ NEW (Option B)

**Goal**: Replace DIY factor work with peer-reviewed library factors. Highest single-phase ROI (+0.5-1% alpha lift).

**Research ref**: RESEARCH_FINDINGS.md Sections 1, 2.1-2.3, 2.4.

⚠️ **License caveats** — verify before each integration:
- **OSAP** (Chen-Zimmermann openassetpricing.com): Stock-level signals require WRDS for recompute; portfolio returns CSV freely downloadable. Use returns CSV directly.
- **JKP** (jkpfactors.com): CC BY-NC 4.0. Factor returns CSV free. Stock-level needs WRDS.
- **pyqlib** (Microsoft): MIT, fully free.
- **ipca** (Kelly-Pruitt-Su): MIT.

## Tasks

### 4.1 Add deps
```toml
[project.optional-dependencies]
factors = [
  "openassetpricing>=0.1",  # Chen-Zimmermann signals (Phase 4)
  "ipca>=0.2",              # Instrumented PCA (Kelly-Pruitt-Su 2019)
  "pyqlib>=0.9",            # Microsoft Qlib Alpha158 features
  "scikit-learn>=1.4",
]
```

### 4.2 OSAP Integration
`compute/ingest/osap.py`:
- Download Chen-Zimmermann portfolio returns CSV
- Cache to `compute/cache/osap/{signal_name}.parquet`
- Map signals to QuantRank pillars (Quality/Value/Growth/etc.)
- Add cross-sectional ranks as features

**Re-verify**: Check openassetpricing.com October 2025 release for current 319 signals list.

### 4.3 JKP Factor Integration
`compute/ingest/jkp.py`:
- Download JKP 153-factor monthly returns CSV
- Use 13 theme clusters to reduce dimension
- Avoid LightGBM double-counting collinear signals

**Re-verify**: jkpfactors.com terms — confirm CC BY-NC 4.0 still applies for non-commercial open-source use.

### 4.4 Microsoft Qlib Alpha158
`compute/features/alpha158.py`:
- Wrap Qlib Alpha158 feature generation
- Generate 158 hand-crafted technical features
- Benchmark: LightGBM Rank IC ≈ 0.0482, IR ≈ 1.57 on Qlib's CSI300

**Re-verify**: Qlib's data loader status on free-tier GitHub Actions runners. May need pre-compute on Kaggle if heavy.

### 4.5 IPCA Latent Factors
`compute/features/ipca_factors.py`:
- Fit Kelly-Pruitt-Su IPCA with 5 latent factors
- Use OSAP signals as instruments for time-varying loadings
- Output: 5 latent factor exposures per stock per month

```python
from ipca import InstrumentedPCA
ipca = InstrumentedPCA(n_factors=5, intercept=True)
ipca.fit(X=characteristics, y=returns, indices=panel_index)
factor_exposures = ipca.predict_panel(...)
```

### 4.6 Update Pillar Aggregation
- Quality pillar: blend DIY + OSAP quality signals + JKP Quality theme
- Value pillar: blend DIY + OSAP value + JKP Value theme
- (etc. for all pillars)

### 4.7 Validation
- Replication QC: verify OSAP signal returns match published t-stats within 5%
- IC test: each library factor must show |IC| > 0.01 on walk-forward
- If validation fails for a library → fallback to Option A for that signal

### 4.8 Schema Bump
`metadata.json` version → `1.1.0-phase4`

### 4.9 Defense additions (research-validated, 2026-05-09)

Per `docs/RESEARCH_FINDINGS.md` §"Phase 4 Defense Layer".

**Cross-source validator** — `compute/ingest/cross_source.py`:
- For each stock, compute SEC-derived market cap (shares × close) and
  yfinance-reported market cap.
- If |delta| / sec_mc > 5% → flag `cross_source_disagreement`.
- Catches ~80% of yfinance scraper drift (a common Phase 1 fragility).
- Mode: GUARD. ~150 LOC.

**PBO + Deflated Sharpe gating** — `compute/validation/pbo_dsr.py`:
- Bailey-Borwein-Lopez de Prado-Zhu (2014) Combinatorially Symmetric CV.
- Use S=8 or 16 partitions.
- **Hard-veto threshold**: PBO > 0.5 → reject factor for production use.
- **Deflated Sharpe Ratio** (Bailey-Lopez de Prado 2014) > 0 required.
- Library: `pypbo` (esvhd/pypbo, MIT) + custom DSR (~30 LOC pandas).
- Mode: infrastructure. ~200 LOC.

**IC decay monitor** — `compute/validation/ic_decay.py`:
- Rolling 12-month and 36-month IC per pillar.
- Alert if IC < 50% of historical mean for 6+ consecutive months.
- McLean-Pontiff anchor: 26% out-of-sample, 32% post-publication decay.
- Surface to `frontend/public/data/decay_report.json` for transparency.
- Mode: infrastructure. ~150 LOC.

⚠️ **License re-verification at Phase 4 entry:**
- `openassetpricing` (OSAP): MIT-style, ✅ free
- `bkelly-lab/jkp-data` code: MIT, ✅ free
- JKP factor returns CSV: CC BY-NC 4.0, ✅ educational static-site OK
- `bkelly-lab/ipca`: MIT, ✅ free
- `pyqlib`: MIT, ✅ free

## Phase 4 Fallback Triggers (Option A revert)
Revert to Option A if:
- ❌ OSAP CSV download fails or signals materially differ from published
- ❌ JKP license terms changed to commercial-only
- ❌ Qlib Alpha158 cannot run on GitHub Actions free tier within 6hr
- ❌ IPCA fitting requires WRDS data not available free
- ❌ Replication QC shows <50% of signals match published values

If fallback triggered → log in PHASE_STATUS.md, continue Phase 5 on Option B.

## Phase 4 Acceptance Criteria
- [ ] OSAP signals integrated for ≥100 of 319 signals
- [ ] JKP factor returns merged into pillar aggregation
- [ ] Qlib Alpha158 features generated for all 500 stocks
- [ ] IPCA 5 latent factors fit and exposure outputs verified
- [ ] **Each library factor passes IC > 0.01 on walk-forward rolling 12-month evaluation** (locked 2026-05-14 — replaces "composite alpha lift ≥ 0.3%" criterion which is unreachable in Phase 4; full composite-alpha-lift gate moves to Phase 5 when backtest infrastructure lands. Per `phase-4-kickoff-checklist/PLAN.md` §7)
- [ ] Compute time stays <60 min weekly
- [ ] **Cross-source validator running weekly; <5% of universe flagged** (per `defense-infrastructure/PLAN.md` §1)
- [ ] **PBO + DSR computed for every Phase 4 factor before integration; PBO ≤ 0.5 AND DSR > 0 required to accept** (per `defense-infrastructure/PLAN.md` §2)
- [ ] **IC decay report published; baseline IC documented per pillar** (per `defense-infrastructure/PLAN.md` §3)
- [ ] **Going-concern FP rate ≤ 5% at PR 4g (8-K Tier-2 re-enable gate)** (formal blocker; was informal target. Per `phase-4-kickoff-checklist/PLAN.md` §6)
- [ ] Tag `v1.1.0-phase4` (per `v1-to-v1-1-migration/PLAN.md` sequencing — `v1.0.1-perf` → `v1.0.2-defense` → `v1.0.3-fix` → `v1.1.0-rc1..8` → `v1.1.0-phase4`)

### Defense Acceptance Matrix (locked 2026-05-14)

Per `phase-4-kickoff-checklist/PLAN.md` §8 — consolidates defense gates scattered across this WORKFLOW.md, `SKILL.md` Rule 13, and individual feature PLANs.

| Defense | Mode | Activation gate | Veto status |
|---|---|---|---|
| Altman Z″ < 1.1 | Active veto | Standard Phase 0 spec | ✅ blocks Top-N badge |
| Sloan accruals top decile | Active veto | Standard Phase 0 spec | ✅ blocks Top-N badge |
| Net issuance top decile | Active veto | Standard Phase 0 spec | ✅ blocks Top-N badge |
| Going-concern (10-K phrase) | Active veto | Mayew 2015 reimplementation | ✅ blocks Top-N badge |
| `data_quality_input_corruption` | Active veto | Audit #6 (PR #48 expansion) | ✅ blocks Top-N badge |
| Beneish M-score (Phase 3e) | Annotate-only | `beneish_high` valuation_warning | ⚠️ warns, no veto |
| Dechow F-score (Phase 3e) | Annotate-only | `dechow_high` valuation_warning | ⚠️ warns, no veto |
| Cross-source disagreement (PR 4b) | Annotate-only | 5% market-cap delta | ⚠️ warns, no veto |
| IC-decay alert (PR 4b) | Monitor + manual review | 6-month threshold breach | ❌ no production veto; surface in `decay_report.json` |
| PBO + DSR (PR 4b) | Pre-integration gate | PBO ≤ 0.5 AND DSR > 0 per factor | ✅ veto factor from being added to composite |

Promotion path (Annotate → Active Veto): FP rate ≤ 5% + academic citation + sector-specific exclusions documented + schema minor bump.

### Phase 4 P0 audit close PLANs (added 2026-05-14)

These 6 PLANs close the P0 gaps surfaced by the comprehensive Phase 4 planning audit:

- **`workflow-cache-improvements/PLAN.md`** — PR 4a leadoff. Caches 10-K text + filings index + prices + universe. Reduces weekly compute from ~30 min to ~10 min steady-state. ~360 LOC, ~1.5 days
- **`defense-infrastructure/PLAN.md`** — PR 4b. Three sections (cross-source validator + PBO+DSR gate + IC-decay monitor). Hard gates for Phase 4 factor work. ~820 LOC, ~5.5 days
- **`osap-integration/PLAN.md`** — PR 4h. Chen-Zimmermann OSAP returns CSV + 100-signal subset replication + 50/50 DIY blending. ~1,160 LOC, ~9 days
- **`jkp-integration/PLAN.md`** — PR 4i. Jensen-Kelly-Pedersen 13 theme cluster returns + exposure regression + pillar blending. CC BY-NC 4.0 license (educational static-site OK). ~610 LOC, ~6 days
- **`phase-4-kickoff-checklist/PLAN.md`** — Pre-flight decision registry. Locks UX terminology (Option B / D / fair_price.max), library version pins, license re-verification, sequencing, acceptance metric, Defense Matrix
- **`issue-remapping/PLAN.md`** — Maps every open issue to a Phase 4 PR. Closes #10 + #16 immediately; pins #7 / #11 / #14 / #15 / #17 / #18 to specific PRs; defers #31 / #41 to a separate Next.js chore PR
- **`changelog-scaffolding/PLAN.md`** *(audit add 2026-05-15)* — Public `CHANGELOG.md` following Keep a Changelog 1.1.0 convention. Auto-generated from PR titles + tag boundaries; CI gates ensure `[Unreleased]` section non-empty before tag push. Referenced by Phase 4 `schema-versioning` + Phase 11 `case-studies` + `public-api-docs`. ~1,070 LOC + markdown, ~5.5 days

### UI / UX features queued for Phase 4 (post-v1.0)

These are planning stubs at `.claude/skills/phase-4/<name>/PLAN.md`.
Trio shipping order locked 2026-05-14: recommendation-badge → loss-chance
→ price-chart (chart hard-depends on badge for the conditional target line).

- ✅ **recommendation-badge** *(PR 4d, merged 2026-05-14 — PRs #68 / #69
  / #70)* — 4-tier indicator (**Bullish / Lean Bullish / Neutral /
  Cautious** internal IDs, **Strong Buy / Buy / Hold / Sell** display
  labels) next to every ticker on overview + detail pages, plus filter
  control. Derived from composite + risk overlay + fair-price MoS via
  pure-function `derive_recommendation` in
  `compute/scoring/recommendation.py`. Calibration thresholds tuned
  against the actual S&P 500 distribution after simulation showed the
  original spec produced 0% Strong Buy (composite ≥70 + MoS ≥20%). Final
  constants: `BULLISH_COMPOSITE_MIN=60` + `BULLISH_MOS_MIN_PCT=-10`,
  `LEAN_BULLISH_COMPOSITE_MIN=50` + `LEAN_BULLISH_MOS_MIN_PCT=-80` +
  `LEAN_BULLISH_MAX_RISK_FLAGS=2`, `CAUTIOUS_COMPOSITE_MAX=25` /
  `CAUTIOUS_MOS_MAX_PCT=-180`. Production: 26 Strong Buy / 147 Buy /
  216 Hold / 113 Sell. SKILL Rule 17 (frontend-design-system +
  threshold-symbolic tests) drafted from this PR's audit findings.
- ✅ **loss-chance** *(PR 4e, merged 2026-05-15 — PRs #71 / #72)* —
  `Loss Chance %` chip directly after the Margin of Safety display on
  rankings table + detail page in a 5-band gradient outlined-light
  chip. Pure-function `derive_loss_chance` in
  `compute/scoring/loss_chance.py` with asymmetric MoS contribution
  (baseline 40, MoS scale 0.35, `cap_neg=35` / `cap_pos=20`, composite
  scale 2.0). 5-95% clipped range. **Heuristic** framing explicit —
  small italic "heuristic" qualifier + tooltip — pending Phase 5
  Triple-Barrier + Conformal Prediction work for a true calibrated
  probability. Independent of badge/chart so it shipped second.
- ✅ **price-chart-enhancements** *(PR 4f, merged 2026-05-15 — PR
  #76, commit `17323346`)* — Phase 4.1 + 4.2 shipped; 4.3 (intraday
  `1D / 5D`) deferred to Phase 5+ per locked PLAN §3.
  - **Phase 4.1**: 7-button time-period selector (1M / 6M / YTD / 1Y
    enabled; 1D / 5D / 5Y disabled with tooltip in the initial scope);
    `fair_price.median` dashed line + `fair_price.max` solid target
    line for **every recommendation tier** (relaxed from the original
    bullish-only PLAN after user spot-check — Hold / Sell tickers
    benefit from the upper-bound reference, with chip color cueing
    direction); off-chart annotation chips color-coded by direction
    (green when reference > current price, red when reference <
    current); current-price + USD + period-change indicator following
    the Google Finance pattern; dynamic trend color (line + area fill
    green on positive period, rose on negative); gradient area fill;
    Y-axis hidden; X-axis format MM-YY / YYYY; inline legend; hero
    card 3-column row refactor with `flex justify-evenly` + centered
    content (closes #77).
  - **Phase 4.2 (inlined)**: `HISTORY_TAIL_DAYS` 252 → 1260 (5Y
    daily data persisted per stock); `compute/ingest/prices.py`
    `PRICES_PERIOD = "5y"` already in place from PR 3c; total
    `stocks/history/` grew 16 MB → 74 MB; per-file 31 KB → 155 KB.
    `5Y` button now enabled.
  - **Cron schedule change** (`compute-rankings.yml`): weekly Sunday
    22:00 UTC → **Mon-Fri 22:00 UTC daily** (after US market close).
    `_next_business_day_offset()` helper computes the correct
    `next_update_utc` (Fri → Mon +3d, Sat → Mon +2d, Sun → Mon +1d,
    Mon-Thu → next day +1d). Price staleness ≤ 24 h on trading days
    (was ≤ 7 days).
  - **SPY benchmark overlay** *(PLAN §4)* — initially scoped, reverted
    on user request "vs SPY เอาออกยังไม่ต้องมีตอนนี้" before
    Mark-Ready. Frontend toggle + backend SPY writer dropped. Deferred
    to a future PR with no specific timeline.
  - 14 commits, +527 / -85 LOC, 10 files. Schema unchanged
    (additive-only-within-major rule per `v1-to-v1-1-migration/PLAN.md`).
  - See
    [`price-chart-enhancements/PLAN.md`](.claude/skills/phase-4/price-chart-enhancements/PLAN.md).
- **exchange-pill** — adds an exchange-of-listing pill
  (`NASDAQ` / `NYSE` / `NYSE Arca` / `NYSE American` / `Cboe`)
  immediately before the existing Sector pill on both overview and
  detail pages, plus an exchange filter chip in the filter bar.
  Data source: SEC EDGAR submissions JSON `.exchanges[0]` (primary) +
  yfinance `.info["exchange"]` (fallback) — both already in the cache
  surface, no new dependencies. Schema additive
  (`StockSummary.exchange` + `StockDetail.exchange`). ~290 LOC, ~1.5 days.
  Independent of the UX trio. See
  [`exchange-pill/PLAN.md`](.claude/skills/phase-4/exchange-pill/PLAN.md).

### Foundational PLANs added 2026-05-14 (P1 audit backfill)

These close gaps surfaced by the comprehensive planning audit on
2026-05-14. They're foundational for everything after v1.0:

- **v1-to-v1-1-migration** — defines what v1.0 promises (schema
  contract, frozen formulas, defense thresholds), what v1.1 may /
  may not change, the suggested PR sequencing for Phase 4 work
  (4a-4f), deprecation policy (additive-only within a major), and
  rollback procedure. ~100 LOC scaffolding (field-deletion CI guard +
  changelog + release notes template). See
  [`v1-to-v1-1-migration/PLAN.md`](.claude/skills/phase-4/v1-to-v1-1-migration/PLAN.md).
- **schema-versioning** — semver applied to the JSON output schema.
  Table of when a change is patch / minor / major. Extends
  `schema_check` to detect field deletions / type narrowing against
  the most recent `v*.0.0` tag. ~130 LOC. See
  [`schema-versioning/PLAN.md`](.claude/skills/phase-4/schema-versioning/PLAN.md).
- **backtest-infrastructure** (Phase 5 foundational) — the shared
  rolling-window + purged + embargoed CV harness that ALL Phase 5
  ML stubs depend on. Metrics: rank IC + Sharpe + Deflated Sharpe
  (Bailey 2014) + PBO (Bailey 2016). Hard gate: any ML feature with
  DSR < 0 OR PBO > 0.5 is excluded from the composite. ~900 LOC,
  ~8-9 days. **Must land before any other Phase 5 stub.** See
  [`backtest-infrastructure/PLAN.md`](.claude/skills/phase-5/backtest-infrastructure/PLAN.md).
- **Effort estimates backfill** — `docs/PHASE_4_8_EFFORT_BACKFILL.md`
  has rough LOC + calendar estimates for all 28 Phase 4-8 stubs.
  Grand total: ~6,000 LOC, ~11-13 weeks full-time
  (3-4 months mobile-only). Aligns with this doc's "Phase Overview"
  headline + adds the UX trio + scaffolding overhead.

---

# PHASE 5 — ML Meta-Learner Enhanced (Option B)

**Goal**: LightGBM ranker + research-backed wrapping (Triple-Barrier + Meta-Labeling + Conformal Prediction).

**Knowledge ref**: stock_ranking_knowledge.md Section 13.
**Research ref**: RESEARCH_FINDINGS.md Section 2.4 (López de Prado), 2.7 (Conformal Prediction).

⚠️ **CRITICAL LICENSE ALERT** (re-verified 2026-05-09):
- **mlfinlab is all-rights-reserved** (Hudson & Thames commercial license
  required). DO NOT depend on it. Reimplement Triple-Barrier +
  Meta-Labeling + Purged CV from primary papers (López de Prado 2018
  *Advances in Financial Machine Learning*) under MIT. Algorithms are
  not patented; papers are publicly available.
- **mapie** (Conformal): BSD-3-Clause, ✅ fully compatible.
- **skfolio**: BSD-3-Clause, ✅ use for `CombinatorialPurgedCV`
  (replacement for mlfinlab's PurgedKFold).

## Tasks

### 5.1 Add deps
```toml
ml = [
  "lightgbm>=4.3",
  "scikit-learn>=1.4",
  "shap>=0.45",
  "skfolio>=0.2",   # Purged + Embargoed CV (BSD-3) — replaces mlfinlab
  "mapie>=0.8",     # Conformal Prediction (BSD)
]
# ⚠️ Do NOT add mlfinlab — all-rights-reserved (commercial license).
# Reimplement Triple-Barrier + Meta-Labeling under MIT.
```

### 5.2 Historical Training Data Backfill
*(Same as original Phase 5 task)*

### 5.3 LightGBM LambdaRank Training
*(Same as original Phase 5)*

### 5.4 Triple-Barrier Method ⭐ NEW (reimplemented under MIT)
`compute/ml/triple_barrier.py` — pure-pandas implementation per
López de Prado 2018 Ch. 3 (~150 LOC). Algorithm not patented:
```python
def cusum_filter(close, threshold):
    """López de Prado Ch. 3.6 — symmetric CUSUM filter."""
    s_pos, s_neg = 0, 0
    events = []
    diff = close.diff()
    for i, d in diff.items():
        s_pos = max(0, s_pos + d)
        s_neg = min(0, s_neg + d)
        if s_neg < -threshold:
            s_neg = 0; events.append(i)
        elif s_pos > threshold:
            s_pos = 0; events.append(i)
    return pd.DatetimeIndex(events)

def add_vertical_barrier(events, close, num_days):
    """Time barrier — return Series of t1 (vertical) timestamps."""
    t1 = close.index.searchsorted(events + pd.Timedelta(days=num_days))
    t1 = t1[t1 < close.shape[0]]
    return pd.Series(close.index[t1], index=events[:len(t1)])

def triple_barrier_labels(close, events, pt_sl, target, t1):
    """Take-profit / stop-loss / time barriers per López de Prado Ch. 3.4."""
    # ~80 LOC — see RESEARCH_FINDINGS.md §"Phase 5 Defense Layer" for full impl
    ...
```

Replaces fixed-horizon labels with vol-scaled take-profit / stop-loss /
time barriers. **Does NOT depend on mlfinlab.**

### 5.5 Meta-Labeling ⭐ NEW (reimplemented under MIT)
`compute/ml/meta_labeling.py` — López de Prado 2018 Ch. 3.7 (~80 LOC):
- Primary model: LightGBM produces BUY/HOLD signal per stock
- Secondary model: classifier predicts probability primary signal correct
- Use secondary probability for position sizing

### 5.6 Conformal Prediction ⭐ NEW
`compute/ml/conformal.py`:
```python
from mapie.regression import MapieRegressor
mapie = MapieRegressor(estimator=lgbm, method="cv_plus", cv=5)
mapie.fit(X_train, y_train)
y_pred, y_pis = mapie.predict(X_test, alpha=0.1)  # 90% prediction intervals
```

Use prediction interval width for confidence-weighted ranking.

### 5.7 Validation
*(Same as original Phase 5)*
- Mean IC ≥ 0.02 hard requirement
- PBO < 50%
- Hard fail: don't deploy if degrades

### 5.8 Optional: Conditional Autoencoder
If Kaggle GPU setup smooth + time permits:
- Implement Gu-Kelly-Xiu 2021 conditional autoencoder
- Repo: github.com/rongwang0824/Autoencoder-Asset-Pricing-Models
- Trains in <1hr on Colab T4

### 5.9 Monthly Retrain Workflow
*(Same as original)*

### 5.10 Schema Bump
`metadata.json` version → `1.2.0-phase5`

### 5.11 Defense additions (research-validated, 2026-05-09)

Per `docs/RESEARCH_FINDINGS.md` §"Phase 5 Defense Layer".

**Bao-Ke ML fraud overlay** — `compute/ml/fraud_overlay.py`:
- Bao, Ke, Li, Yu, Zhang 2020 *J. Accounting Research*: RUSBoost on 28
  raw accounting numbers (not ratios).
- NDCG ~50% better than Dechow logit.
- Replication code at `JarFraud/FraudDetection` (MIT-style).
- ANNOTATE-only flag `bao_ml_fraud_high` (top decile cross-section).
- ⚠️ Do NOT subtract from composite — already covered by 4 other fraud
  signals (Beneish + Dechow + Sloan + going-concern). This is the 5th
  diversifier, not the 5th penalty.
- Mode: ANNOTATE. ~300 LOC.

**MAPIE conformal prediction wrappers** — `compute/ml/conformal.py`:
- Wrap LightGBM with `mapie.regression.MapieRegressor` (BSD-3-Clause).
- Output: 90% prediction intervals around ML pillar score.
- Propagate intervals via Monte-Carlo to composite (1000 samples).
- Display ranks as `(rank, ci_low, ci_high)` in UI.
- Distribution-free finite-sample coverage guarantee (Vovk-Gammerman-
  Shafer framework; Angelopoulos-Bates 2021 introduction).
- Mode: architecture. ~150 LOC.

**Purged + Embargoed CV** — `compute/ml/cv.py`:
- López de Prado 2018, Ch. 7. Mandatory for ALL Phase 5+ ML training.
- Library: `skfolio.model_selection.CombinatorialPurgedCV` (BSD-3).
- Embargo = 5% of sample.
- Mode: architecture. ~100 LOC.

## Phase 5 Fallback Triggers
Revert to Option A (original Phase 5) if:
- ❌ Triple-Barrier reimplementation complexity > expected, blocks shipping
- ❌ Conformal Prediction shows no Sharpe lift
- ❌ Conditional Autoencoder fails to train on Kaggle in 6hr
- ❌ Bao-Ke replication QC fails on golden tickers

## Phase 5 Acceptance Criteria
- [ ] LightGBM walk-forward shipped (Option A baseline)
- [ ] Triple-Barrier labels in production (Option B addition, MIT-reimplemented)
- [ ] Meta-labeling secondary model deployed (Option B, MIT-reimplemented)
- [ ] **MAPIE conformal intervals reported on every ML score**
- [ ] **Purged + Embargoed CV (5% embargo) used for all training**
- [ ] **Bao-Ke ML fraud annotation visible per stock**
- [ ] Mean IC ≥ 0.02 OOS
- [ ] PBO < 50%
- [ ] **No mlfinlab dependency anywhere in `pyproject.toml`**
- [ ] Tag `v1.2.0-phase5`

---

# PHASE 6 — Sentiment v2 Enhanced (Option B)

**Goal**: Multi-signal sentiment beyond original Reddit/StockTwits plan. Whisper + 8-K + Lazy Prices.

**Research ref**: RESEARCH_FINDINGS.md Section 2.5 (Whisper VDQ), 2.6 (Lazy Prices), 2.9 (8-K events).

⚠️ **Compute requirement**: This phase needs **Modal ($30/mo credits)** for Whisper transcription. Estimate: ~50 GPU-hrs T4 monthly.

## Tasks

### 6.0 Defense-priority ordering (research-validated, 2026-05-09)

Implement Phase 6 defenses in this order (highest ROI first per
`docs/RESEARCH_FINDINGS.md` §"Phase 6 Defense Layer"):

1. **Lazy Prices first** (Cohen-Malloy-Nguyen 2020 *JF*) — 22% reported
   annual alpha, simplest to implement (cosine similarity on 10-K text
   YoY changes). Caveat: published 2020 → expect McLean-Pontiff decay
   (~30% by 2026). Validate on recent OOS data.
2. **8-K Item 4.02 / 4.01 already shipped in PR 3d** (Tier-2 defenses).
   Phase 6 extends with full event-window CAR computation `(-1, +1)`,
   expected −5 to −15% on Item 4.02.
3. **FinBERT MD&A classifier** — Apache 2.0. Forward-looking vs
   negative tone in 10-K Item 7. Modal $30/mo sufficient for monthly
   batch (502 stocks × ~30s/stock).
4. **Whisper Vocal Delivery Quality** — Baik-Kim-Kim-Yoon 2025 *JAE*.
   Most expensive (Modal GPU time). Defer if budget tight.
5. **Insider routine vs opportunistic classifier** — Cohen-Malloy-
   Pomorski 2012 *JF*. Reclassify Form 4 trades; only opportunistic
   predict returns.

⚠️ **Diminishing returns warning** (Beneish-Vorst 2021): marginal
AAER capture < 5% beyond 4 fraud signals. By Phase 6, QuantRank has
Beneish + Dechow + Sloan + going-concern + Bao-ML = 5 signals. Lazy
Prices is the 6th — track its incremental information ratio carefully
and FREEZE the defense set if marginal IR < 0.05.

### 6.1 Add deps
```toml
sentiment_v2 = [
  "transformers>=4.40",
  "torch>=2.2",
  "openai-whisper>=20240930",   # Whisper transcription
  "sentence-transformers>=3.0", # For Lazy Prices
  "praw>=7.7",                  # Skip for megacap, use for small-cap
  "finnhub-python>=2.4",
]
```

### 6.2 FinBERT News Sentiment (original Phase 4 plan)
*(Same as original)*

### 6.3 Insider Form 4 (original Phase 4 plan)
*(Same as original)*

### 6.4 Whisper Earnings Call Audio ⭐ NEW
`compute/ingest/earnings_audio.py`:
- Scrape audio URLs from IR websites + Seeking Alpha public archive
- Quarterly cron triggers Modal job to transcribe
- Output: text transcripts + Wav2Vec2 vocal features

`compute/features/vdq.py`:
- Vocal Delivery Quality features (Sang et al. 2024 JAR)
- Independent of textual sentiment
- Documented alpha contribution: +0.2-0.4%

**Re-verify**: Modal pricing 2026 — may differ from $30/mo credit estimate.

### 6.5 8-K Item-Level Events ⭐ NEW
`compute/ingest/eight_k.py`:
- Parse all 8-K filings via edgartools
- Item 1.01 (M&A): event window CAR feature
- Item 4.02 (restatement): -2.6% to -5.4% CAR (Schroeder 2024)
- Item 5.02 (mgmt change): mixed signal
- Item 1.05 (cyber): negative
- Aggregate per stock per 90-day window

### 6.6 Lazy Prices (MD&A YoY Similarity) ⭐ NEW
`compute/features/lazy_prices.py`:
- Cohen-Malloy-Nguyen 2020 (JoF)
- Compute year-over-year cosine similarity of 10-K MD&A sections
- Use sentence-transformers `all-MiniLM-L6-v2` (free)
- Stocks with major language change underperform by 30-60 bps/month

```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('all-MiniLM-L6-v2')
embeddings_y1 = model.encode(mda_text_y1)
embeddings_y2 = model.encode(mda_text_y2)
similarity = cosine_similarity(embeddings_y1, embeddings_y2)
# Lower similarity = larger language change = lower expected return
```

### 6.7 SKIP Reddit/StockTwits for Megacap
Research finding: no documented alpha at S&P 500 scale. Skip these for the main pipeline. **Phase 8** can re-evaluate for small-caps.

### 6.8 Update Sentiment Pillar Weight
*(Same as original Phase 4)*

### 6.9 Schema Bump
`metadata.json` version → `1.3.0-phase6`

## Phase 6 Fallback Triggers
Revert to Option A (original Phase 4 sentiment) if:
- ❌ Modal credits insufficient for Whisper at universe scale
- ❌ IR website scraping legally blocked (ToS issues)
- ❌ 8-K parsing complexity blocks shipping
- ❌ Lazy Prices shows no IC improvement

## Phase 6 Acceptance Criteria
- [ ] FinBERT news sentiment in production
- [ ] Insider Form 4 cluster signals visible
- [ ] **Routine vs opportunistic classifier (Cohen-Malloy-Pomorski 2012)
      separates the two; only opportunistic counted as signal**
- [ ] Whisper transcription job runs quarterly on Modal
- [ ] 8-K event features in JSON output (extends Tier-2 defenses from PR 3d)
- [ ] Lazy Prices similarity computed monthly
- [ ] **Lazy Prices replicated within 5% of published alpha (or
      documented decay if not)**
- [ ] **All Phase 6 defenses ANNOTATE-only — no scoring penalties**
- [ ] Sentiment pillar shows IC > 0.02
- [ ] Tag `v1.3.0-phase6`

---

# PHASE 7 — Regime + Portfolio v2 (Option B)

**Goal**: Better regime detection + portfolio construction. Student-t HMM + TDA + NCO.

**Research ref**: RESEARCH_FINDINGS.md Section 2.10 (NCO), 2.15 (TDA).

⚠️ **License re-verification at Phase 7 entry (2026-05-09):**
- `skfolio` (NCO): BSD-3-Clause, ✅ free
- `giotto-tda` (TDA, package name `gtda`): Apache 2.0, ✅ free
  *(Original WORKFLOW.md said AGPL — corrected after re-check.)*
- `hmmlearn`: BSD-3-Clause, ✅ free

## Tasks

### 7.1 Add deps
```toml
quant_v2 = [
  "fredapi>=0.5",
  "hmmlearn>=0.3",
  "arch>=7.0",
  "alphalens-reloaded>=0.4",
  "skfolio>=0.2",         # NCO portfolio (BSD)
  "gtda>=0.6",            # TDA (AGPL — verify)
]
```

### 7.2 Macro Ingestion (original Phase 6)
*(Same as original)*

### 7.3 HMM Regime — Student-t Distribution ⭐ NEW
Original was Gaussian HMM. Student-t is more robust per Lee 2026 (KAIST):
```python
from hmmlearn.hmm import GaussianHMM
# Or implement Student-t HMM via custom emission distribution
# Fat-tailed emission better captures crisis periods
```

### 7.4 Topological Data Analysis ⭐ NEW
`compute/features/tda_regime.py`:
- Persistent homology on rolling correlation matrices (Gidea-Katz 2018)
- Use `gtda` library
- Detect topological "phase transitions" before crashes
- Use as **risk-off gate**, not return signal

### 7.5 Regime-Conditional Weights (original Phase 6)
*(Same as original)*

### 7.6 Nested Clustered Optimization ⭐ NEW
`compute/portfolio/nco.py`:
- López de Prado 2019 — improves over HRP under noisy correlations
```python
from skfolio.optimization import NestedClustersOptimization
nco = NestedClustersOptimization(
    inner_estimator=...,
    outer_estimator=...,
)
nco.fit(returns)
weights = nco.weights_
```

### 7.7 Backtest Harness (original Phase 6)
- Add Hansen SPA test
- Add Romano-Wolf StepM
- Add Deflated Sharpe (Bailey-LdP 2014)

### 7.8 PBO via CSCV (original Phase 6)
*(Same as original)*

### 7.9 Backtest Report Page
*(Same as original)*

### 7.10 Schema Bump
`metadata.json` version → `1.4.0-phase7`

### 7.11 Defense additions (research-validated, 2026-05-09)

Per `docs/RESEARCH_FINDINGS.md` §"Phase 7 Defense Layer".

**HMM 3-state regime gating** — `compute/regime/hmm.py`:
- Inputs: monthly S&P 500 returns + VIX + credit spreads (HYG/LQD) +
  200-DMA breadth.
- Library: `hmmlearn` (BSD-3-Clause).
- Output: 3-state classifier {calm, transition, stress}.
- In `stress` regime: down-weight momentum 50%, up-weight quality+low-
  vol by equivalent.
- Source: Wang et al. 2020 *J. Risk and Financial Management*.
- Mode: architecture. ~250 LOC.

**Persistent-homology TDA crash detector** —
`compute/regime/tda_crash.py`:
- Compute persistence landscape L¹ and L² norms on rolling 60-day
  return windows.
- Source: Gidea-Katz 2018; recent extension MDPI 2025 confirms
  predictive power on COVID + 2022 selloffs.
- Library: `giotto-tda` (Apache 2.0).
- Alert when norms exceed 2σ above trailing 12-month baseline.
- ⚠️ Compute-intensive: schedule monthly on Kaggle, not weekly GH Actions.
- Mode: architecture. ~300 LOC.

## Phase 7 Fallback Triggers
Revert to Option A (original Phase 6) if:
- ❌ Student-t HMM convergence issues
- ❌ TDA computation > acceptable time budget
- ❌ NCO shows no Sharpe lift over HRP
- ❌ skfolio/gtda license issues

## Phase 7 Acceptance Criteria
- [ ] HMM regime updates weekly (Gaussian or Student-t)
- [ ] **HMM regime classifier published to `metadata.json.regime_state`**
- [ ] TDA risk-off gate visible in metadata
- [ ] **TDA L¹/L² norms tracked monthly; alerts logged**
- [ ] **Regime-conditional pillar weights documented and A/B tested**
- [ ] NCO replaces HRP (or HRP retained per fallback)
- [ ] Backtest report shows IC, IR, PBO < 50%, DSR > 0
- [ ] Net-of-cost top-decile alpha reported honestly
- [ ] Tag `v1.4.0-phase7`

---

# PHASE 8 — Universe Expansion → v2.0

**Goal**: Expand from S&P 500 → S&P 1500. **Stop here. Do NOT push to Russell 2000** — free data quality collapses.

## Tasks

*(Same as original Phase 7)*

### 8.1 Source larger universe
- S&P 1500 = SP500 + S&P 400 (mid-cap) + S&P 600 (small-cap)
- Wikipedia has constituents

### 8.2 Performance considerations
- 1500 stocks × all features = approaching GH Actions time limit
- Parallelize ticker processing
- Add `--universe` CLI flag

### 8.3 Frontend pagination
- Use `@tanstack/react-virtual` for 1500-row table

### 8.4 Data quality monitoring
- Track null rates per universe segment
- Display in `data_quality` per stock

### 8.5 v2.0 Tag
```bash
git tag v2.0
git push origin v2.0
```

### 8.6 Scale-aware defense additions (research-validated, 2026-05-09)

Per `docs/RESEARCH_FINDINGS.md` §"Phase 8 Defense Layer".

**Bonferroni-adjusted multi-test thresholds** — when expanding to 1500
stocks (3× more multiple-comparison burden):
- Beneish M-Score cutoff: bump from −2.22 to −2.50 to maintain 5% FDR
- IC significance: t-hurdle bumps from 1.96 → 2.78 (Hou-Xue-Zhang 2020)
- Document each adjustment in `docs/METHODOLOGY.md`.
- Mode: infrastructure. ~100 LOC.

**Liquidity backstop** — exclude any stock with average daily volume
< $5M (microstructure noise dominates at smaller caps; market-impact
modeling needed for any actionable signal).
- Mode: GUARD. ~50 LOC.

### 8.7 DEFENSE FREEZE policy (post-v2.0)

⚠️ **Do NOT add new defenses post-v2.0** unless ALL of:
1. Existing defense IC has decayed > 50% for 6+ months (per Phase 4 IC
   monitor), AND
2. New addition has academic evidence of incremental IC > 0.01 OOS, AND
3. Free data exists, AND
4. License is MIT/BSD/Apache compatible.

**Rotate, don't stack** (Beneish-Vorst 2021): marginal AAER capture
< 5% beyond 4 fraud signals. Adding more defenses = more false
positives without proportional true positives.

## Phase 8 Acceptance Criteria
- [ ] S&P 1500 ranked weekly
- [ ] Compute time <90 min
- [ ] Frontend handles 1500-row table smoothly on mobile
- [ ] Null rate <10% mid-cap, <20% small-cap
- [ ] **All defenses verified on S&P 1500 universe (no scaling failures)**
- [ ] **Bonferroni adjustments documented and applied**
- [ ] **Liquidity backstop excludes <$5M ADV stocks**
- [ ] **Defense set FROZEN — no new flags added unless rotation criteria met**
- [ ] **v2.0 tag pushed**

---

# PHASE 9 — Free Alt-Data Expansion (toward v2.5)

**Goal**: Match institutional-tool data breadth using only **free public
sources**. Adds 5 new signal surfaces (insider, institutional flow,
macro regime, news sentiment, earnings surprise) without touching the
$0 budget.

**Mandate (user, 2026-05-15)**: scope = "ใกล้เคียงหรือดีกว่าเครื่องมือ
ของบริษัท / องค์กรชั้นนำของโลก ภายใต้ฟรี + เป็นมิตรกับมือใหม่"

## Stubs

| Stub | LOC | Days | Signal type |
|---|---|---|---|
| `macro-regime-fred/` | ~390 | ~3 | Macro context (FRED yield curve, unemployment, CPI, VIX) |
| `insider-trading-form-4/` | ~510 | ~5 | SEC Form 4 — CEO/CFO buys (Cohen-Malloy-Pomorski 2012) |
| `institutional-flow-13f/` | ~680 | ~7 | SEC 13F — ~50 tracker funds (Berkshire/Bridgewater/Tiger) |
| `earnings-surprise-history/` | ~590 | ~5.5 | 8-quarter beats/misses (PEAD signal) |
| `news-sentiment-free/` | ~990 | ~9 | NewsAPI free + Reddit + Wikipedia + HN |
| `dividend-history/` *(audit add)* | ~980 | ~8 | Yield + growth + payout + aristocrat status |
| `earnings-calendar/` *(audit add)* | ~720 | ~6 | Next earnings date + estimate + countdown |
| **Phase 9 subtotal** | **~4860 LOC** | **~43.5 days (~9 wks mobile)** | |

Cumulative compute time after Phase 9: stays under 60 min/week (each
signal cached aggressively per `workflow-cache-improvements/PLAN.md`).

## Phase 9 Acceptance Criteria

- [ ] All 5 signals integrated; each passes PBO ≤ 0.5 + DSR > 0 + IC > 0.01
- [ ] Per-stock detail page shows new chips/badges (insider buy,
      institutional flow, earnings surprise, macro context)
- [ ] News sentiment chip surfaces top decile / bottom decile only
      (no chip when middle-of-pack)
- [ ] **Cost stays $0** — all data sources free-tier or free-public
- [ ] Tag `v2.5.0-phase9`

---

# PHASE 10 — Beginner UX Layer (toward v2.8)

**Goal**: Make the rigor of Phase 4-9 **accessible to beginners**. Adds
glossary + tooltips + recommendation explainer + watchlist + comparison
view + onboarding + bilingual (TH/EN).

**Mandate**: matches Jitta / Simply Wall St / Morningstar in UX
accessibility while keeping methodology rigor at hedge-fund grade.

## Stubs

| Stub | LOC | Days | Feature |
|---|---|---|---|
| `explainer-tooltips/` | ~1410 | ~11 | Tooltips + Glossary modal + "Why X rated Y?" explainer |
| `watchlist-localstorage/` | ~810 | ~6 | ⭐ Star to save stocks (no login) |
| `comparison-view/` | ~1490 | ~12 | `/compare/NVDA-AMD-INTC/` 2-3 stock side-by-side |
| `bilingual-i18n/` | ~2230 | ~14 | next-intl + Thai translations (TH + EN) |
| `onboarding-tutorial/` | ~830 | ~6.5 | First-visit 6-step walkthrough |
| **Phase 10 subtotal** | **~6770 LOC** | **~49.5 days (~10 wks mobile)** | |

## Phase 10 Acceptance Criteria

- [ ] Every metric in the UI has hover/tap tooltip
- [ ] Glossary modal covers 40+ terms
- [ ] "Why X rated Y?" explainer walks through rubric per stock
- [ ] Watchlist persists across sessions in browser
- [ ] Comparison view supports 2-3 stocks side-by-side with overlaid
      pillar radar + normalized price chart
- [ ] Bilingual: both `/en/` and `/th/` URL routes work
- [ ] First-visit tutorial walks new users through the layout in 6 steps
- [ ] Tag `v2.8.0-phase10`

---

# PHASE 11 — Community + Transparency (toward v3.0)

**Goal**: Cement the open-source educational positioning with public
methodology + case-studies + API documentation. Trust-building +
academic-grade transparency.

## Stubs

| Stub | LOC | Days | Deliverable |
|---|---|---|---|
| `methodology-faq/` | ~4930 | ~17.5 | `/methodology/<section>` deep-dive pages (9 sections × bilingual) |
| `case-studies/` | ~8800 | ~26 | 5 worked-example case studies (NVDA / SPG / CRWD / cautious-cluster / 2024 Fed pivot) |
| `public-api-docs/` | ~2520 | ~14.5 | `/api-docs` for 3rd-party consumers of the JSON output |
| `stock-story-llm/` *(audit add)* | ~1270 | ~11 | LLM-generated 2-3 sentence narrative per stock (Claude Haiku 4.5 via vendored `claude-api` skill); opt-in; transparency modal shows full prompt + response |
| **Phase 11 subtotal** | **~17,520 LOC** | **~69 days (~14 wks mobile)** | |

Note: bulk of Phase 11 LOC = **written prose**, not code. Effort dominated
by writing quality educational content and Thai translation.

## Phase 11 Acceptance Criteria

- [ ] `/methodology` page with 9 deep-dive sections (TH + EN)
- [ ] 5 case studies published; each includes honest critique
- [ ] Public API doc page with quickstart + schema + examples in
      curl / Python / JS / MCP server stub
- [ ] CHANGELOG.md auto-generated from PR + tag history
- [ ] Tag `v3.0.0-phase11` — flagship release for retail community

---

# v3.0 Vision (Phase 11 close)

By Phase 11 close, QuantRank will be:

- **Methodology rigor**: matches or exceeds Jitta / Simply Wall St /
  Morningstar; matches academic SOTA (López de Prado, Bailey,
  Kelly-Pruitt-Su, Angelopoulos-Bates, Cohen-Malloy)
- **Data breadth**: 5+ free alt-data sources beyond fundamentals + prices
  (insider, institutional flow, macro, news, earnings surprise)
- **Beginner accessibility**: tooltips on every metric, glossary, "Why
  rated X?" explainer, watchlist, comparison view, onboarding, Thai +
  English
- **Transparency**: methodology page, case studies (honest critique
  included), public API docs, open-source MIT throughout
- **Cost to user**: **$0** forever
- **Cost to maintainer**: $0 hosting (Vercel free tier) + 1-3 hrs/day
  mobile dev throughout

Estimated calendar: **Phase 9 → 11 = ~28 weeks mobile-only**
(~6-7 months from Phase 8 close).

---

# Decision Points Table (Option B Discipline)

Hard veto criteria during any phase shipping:

| Metric | Threshold | Action if violated |
|---|---|---|
| Mean IC OOS | < 0.02 | Don't deploy phase changes |
| PBO | > 0.5 | Hard veto on shipping |
| Deflated Sharpe | < 0 | Hard veto |
| Compute time | > 6 hrs | Move to Kaggle/Modal |
| Net alpha vs SPY | < 0% post-cost | Investigate before next phase |
| Library license | Conflict with MIT | Exclude or fallback |
| Replication QC | < 50% match published | Use library output, not reconstruct |

---

# Maintenance Cycle (Post-v2.0)

| Task | Cadence | Notes |
|---|---|---|
| Pillar weight retune | Quarterly | Use last 12 months IR |
| ML hyperparameter retune | Quarterly | Optuna on training fold only |
| OSAP/JKP update check | Quarterly | New October release each year |
| Free data source rotation | As needed | Watch yfinance breaks |
| License re-verification | Annually | Especially mlfinlab, JKP, gtda |
| Disclaimers + methodology | Quarterly | Keep accurate |
| GitHub Actions minutes | Monthly | Public repo unlimited but be efficient |
| Decay monitoring | Monthly | Per Rule 14 in SKILL.md |

## When to STOP adding features
After v2.0, **resist scope creep** unless:
1. Mean IC has plateaued/declined for 2+ quarters AND
2. New addition has academic evidence of incremental IC > 0.01 AND
3. Free data exists AND
4. License is compatible.

Most "improvements" past v2.0 are noise + maintenance burden.

---

# Mobile Workflow Cheat Sheet

| Situation | Do this on mobile |
|---|---|
| Starting work session | Open Claude Code → "What phase are we in? Read PHASE_STATUS.md" |
| After Claude Code commit | GitHub mobile app → check Actions tab → wait for green |
| Failed Actions run | GitHub mobile → Actions → tap failed run → read logs → tell Claude Code error |
| Want to manually trigger compute | GitHub mobile → Actions → "Compute Rankings" → "Run workflow" |
| Want to see live site | Vercel mobile app → tap latest deploy → "Visit" |
| Backtest looks "too good" | "Run PBO and deflated Sharpe before trusting any number >5%" |
| Adding a metric | Tell Claude Code section number from knowledge doc |
| Stuck on yfinance error | Tell Claude Code: "yfinance broke again, check field names" |
| Phase 4+: monitor Kaggle | Open Kaggle web → check Notebooks → watch logs |
| Phase 6+: monitor Modal | Open Modal dashboard → check usage → ensure within $30 credit |

---

# Initial Prompts to Give Claude Code

## Session 1: Phase 0 kickoff
> Read SKILL.md, WORKFLOW.md, RESEARCH_FINDINGS.md, and stock_ranking_knowledge.md. We're starting Phase 0 of QuantRank. Execute Phase 0 tasks. Push to main when CI is green. List anything I need to do manually (Vercel hookup, secrets, etc.).

## Subsequent sessions
> Read PHASE_STATUS.md. We're in Phase X. Continue from task X.Y.

## Phase 4+ kickoff
> Read PHASE_STATUS.md and RESEARCH_FINDINGS.md. We just shipped v1.0. Now starting Phase 4 (Factor Consolidation, Option B). First task: re-verify current OSAP/JKP/Qlib data availability and licenses before integration.

---

**End of WORKFLOW.md** — combined with `SKILL.md`, `stock_ranking_knowledge.md`, and `RESEARCH_FINDINGS.md`, this is everything Claude Code needs to build QuantRank from your phone via the Option B research-backed roadmap with Option A fallback.
