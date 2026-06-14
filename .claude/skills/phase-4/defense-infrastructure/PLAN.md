# Defense Infrastructure (Phase 4 planning stub)

**Status**: ✅ Implemented in PR 4b (`feat/phase-4b-defense-infrastructure`). All 3 sections ship in one PR per the locked single-PR decision.

- §1 Cross-source validator: production-wired in `compute/main.py` (annotate-only via `valuation_warnings`)
- §2 PBO + DSR: library at `compute/validation/pbo_dsr.py`; ready to be called by PR 4h (OSAP) / 4i (JKP) / 4j (Qlib) / 4k (IPCA) when their factor returns are available
- §3 IC-decay monitor: **production-wired 2026-06-13** (issue #75 §3) — `compute/main.py` runs `ic_decay.build_decay_report` each cron → `frontend/public/data/decay_report.json`, surfaced on `/analysis` via `Metadata.decay_report_url`. Monitor-only (never vetoes); `alert` suppressed until ≥12 monthly IC points/pillar; stays `insufficient_history` until the cron checkout is deepened (currently shallow `fetch-depth: 1` — follow-up #478; Phase 5's walk-forward panel is the longer-term densification source)

No new third-party deps (pure numpy implementation of CSCV + DSR replaces `scipy` + `pypbo`).

## Purpose

Phase 4 introduces academic-library factor blending (OSAP + JKP + Qlib Alpha158 + IPCA). Without infrastructure to validate them — pre-integration AND post-integration — we'd be flying blind. This PLAN specifies the three guardrails that gate every Phase 4+ factor addition.

| Section | Purpose | Mode | Hard veto? |
|---|---|---|---|
| §1 Cross-source validator | Catches yfinance scraper drift via SEC cross-check | GUARD | ✅ veto on >5% delta |
| §2 PBO + DSR gate | Validates each new factor isn't backtest-overfit | INFRA | ✅ veto factor at PBO>0.5 or DSR<0 |
| §3 IC-decay monitor | Catches signal degradation post-publication | MONITOR (live 2026-06-13) | ❌ no veto — alert only (manual review); `alert` suppressed until ≥12 monthly IC pts/pillar |

## §1: Cross-source validator (`compute/ingest/cross_source.py`)

### Spec

For each stock, compare two independent estimates of market cap:
1. **SEC-derived**: `shares_outstanding (from XBRL) × close_price (from yfinance)`
2. **yfinance-reported**: `Ticker.info["marketCap"]`

If `|delta| / sec_mc > 5%` → flag `cross_source_disagreement`.

Catches ~80% of yfinance scraper drift, which is one of Phase 1's documented fragilities (per `README.md` Honest Limitations).

### Architecture

```python
# compute/ingest/cross_source.py

CROSS_SOURCE_TOLERANCE = 0.05  # 5% delta threshold (locked)

def validate_market_cap(ticker: str, snap: FundamentalsSnapshot, current_price: float) -> set[str]:
    """Returns set of risk_flags. Empty if no disagreement."""
    if snap.shares_outstanding is None or current_price is None:
        return set()
    sec_mc = float(snap.shares_outstanding) * float(current_price)

    try:
        yf_info = yfinance.Ticker(ticker).info
        yf_mc = yf_info.get("marketCap")
        if yf_mc is None or yf_mc <= 0:
            return set()
    except Exception:
        return set()  # yfinance flake — don't add false flag

    delta = abs(sec_mc - yf_mc) / sec_mc
    if delta > CROSS_SOURCE_TOLERANCE:
        return {"cross_source_disagreement"}
    return set()
```

### Mode

**GUARD** (annotate-only). Joins the existing 5 Tier-2 annotate flags. Does NOT veto Top-N badge — that's reserved for `data_quality_input_corruption` + `altman_distress` + new active vetoes only.

Schema additive: `RiskFlag` literal-union extends with `"cross_source_disagreement"`.

### Effort

| Step | LOC | Hours |
|---|---|---|
| Validator function | ~50 | 2 |
| Schema additive (RiskFlag) | ~10 | 0.5 |
| Wire-up in `main.py` | ~20 | 1 |
| Tests (4-6 unit tests covering large delta / NaN / yf flake) | ~60 | 2 |
| Distribution validation against latest `rankings.json` | n/a | 1 |
| **§1 total** | **~140 LOC** | **~7 hr (~1 day)** |

Acceptance gate: **<5% of universe flagged** in steady-state (else tolerance too tight).

## §2: PBO + DSR gate (`compute/validation/pbo_dsr.py`)

### Spec

Bailey-Borwein-López de Prado-Zhu (2014) **Combinatorially Symmetric Cross-Validation** computes the **Probability of Backtest Overfitting** (PBO). PBO > 0.5 = factor likely overfit to in-sample noise.

Bailey-López de Prado (2014) **Deflated Sharpe Ratio** corrects for multiple-testing inflation. DSR > 0 = post-deflation Sharpe still positive.

Combined gate: **any new Phase 4+ factor must pass both PBO ≤ 0.5 AND DSR > 0** before integration.

### Architecture

```python
# compute/validation/pbo_dsr.py

PBO_VETO_THRESHOLD = 0.5
DSR_VETO_THRESHOLD = 0.0

def compute_pbo(returns_matrix: pd.DataFrame, n_partitions: int = 16) -> float:
    """Combinatorially Symmetric CV per Bailey 2014. Returns PBO in [0, 1]."""
    # Use pypbo (esvhd/pypbo, MIT) — vetted reimplementation of CSCV
    from pypbo.pbo import compute_pbo as _csv_pbo
    return _csv_pbo(returns_matrix, n_partitions=n_partitions)

def deflated_sharpe(returns: pd.Series, n_trials: int) -> float:
    """Bailey-López de Prado 2014 DSR. Returns DSR (deflated Sharpe ratio).

    n_trials = number of factor variants tested (for multiple-testing correction).
    For Phase 4: n_trials = number of OSAP/JKP signals examined for the
    same target pillar.
    """
    sharpe = returns.mean() / returns.std() * np.sqrt(12)  # monthly → annual
    skew, kurt = scipy.stats.skew(returns), scipy.stats.kurtosis(returns)
    var_sharpe = (1 - skew * sharpe + (kurt - 1) / 4 * sharpe**2) / (len(returns) - 1)
    expected_max = (
        (1 - np.euler_gamma) * scipy.stats.norm.ppf(1 - 1 / n_trials)
        + np.euler_gamma * scipy.stats.norm.ppf(1 - 1 / (n_trials * np.e))
    )
    return (sharpe - expected_max) / np.sqrt(var_sharpe)

def factor_passes_gates(factor_returns: pd.Series, returns_matrix: pd.DataFrame, n_trials: int) -> tuple[bool, dict]:
    """Return (pass: bool, metrics: dict). Used by OSAP/JKP integration."""
    pbo = compute_pbo(returns_matrix)
    dsr = deflated_sharpe(factor_returns, n_trials)
    passes = pbo <= PBO_VETO_THRESHOLD and dsr > DSR_VETO_THRESHOLD
    return passes, {"pbo": pbo, "dsr": dsr}
```

### Dependencies

```toml
factors = [
    "pypbo>=0.2",          # esvhd/pypbo, MIT — CSCV reference impl
    "scipy>=1.13",         # already pinned via pandas dep
    ...
]
```

License re-verification: `pypbo` is MIT, no commercial restriction. ✅

### Effort

| Step | LOC | Hours |
|---|---|---|
| `pypbo` wrapper + DSR computation | ~100 | 3 |
| Tests: synthetic random returns → PBO ~0.5; published Bailey 2014 example → DSR matches paper | ~80 | 3 |
| Integration with OSAP / JKP signal-acceptance gate | ~30 | 1 |
| Report writer — `backtest_report_<feature>.json` schema | ~50 | 2 |
| **§2 total** | **~260 LOC** | **~9 hr (~1.5 days)** |

Acceptance gate: synthetic random returns must yield PBO 0.45-0.55 (within tolerance of 0.5 nominal); Bailey 2014 example DSR must match paper within ±0.05.

## §3: IC-decay monitor (`compute/validation/ic_decay.py`)

### Spec

McLean-Pontiff (2016) "Does Academic Research Destroy Stock Return Predictability?" finds **26% out-of-sample IC decay** and **32% post-publication decay** on average across 97 anomalies.

For each QuantRank pillar (DIY + OSAP-blended + JKP-blended), maintain a rolling-IC time series. Alert when IC drops below 50% of historical mean for **6+ consecutive months** — that's the McLean-Pontiff signature of a decayed anomaly.

### Architecture

```python
# compute/validation/ic_decay.py

IC_DECAY_THRESHOLD = 0.5      # 50% of historical mean
IC_DECAY_DURATION_MONTHS = 6

@dataclass
class ICDecayReport:
    pillar: str
    rolling_12m_ic: float
    rolling_36m_ic: float
    historical_mean_ic: float
    decay_ratio: float          # rolling_12m_ic / historical_mean_ic
    months_below_threshold: int
    alert: bool

def check_pillar_decay(pillar_history: pd.DataFrame) -> ICDecayReport:
    """pillar_history: DataFrame with columns (year_month, monthly_ic, n_stocks)."""
    historical_mean = pillar_history["monthly_ic"].mean()
    rolling_12m = pillar_history.tail(12)["monthly_ic"].mean()
    rolling_36m = pillar_history.tail(36)["monthly_ic"].mean()
    decay_ratio = rolling_12m / historical_mean if historical_mean > 0 else 0.0

    threshold = IC_DECAY_THRESHOLD * historical_mean
    consecutive_below = 0
    for ic in pillar_history.tail(12)["monthly_ic"][::-1]:
        if ic < threshold:
            consecutive_below += 1
        else:
            break

    return ICDecayReport(
        pillar=pillar_history["pillar"].iloc[0],
        rolling_12m_ic=rolling_12m,
        rolling_36m_ic=rolling_36m,
        historical_mean_ic=historical_mean,
        decay_ratio=decay_ratio,
        months_below_threshold=consecutive_below,
        alert=consecutive_below >= IC_DECAY_DURATION_MONTHS,
    )

def emit_decay_report(pillars: list[ICDecayReport], out_path: Path) -> None:
    """Write `frontend/public/data/decay_report.json` for transparency."""
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "pillars": [asdict(p) for p in pillars],
        "anomalies_alerted": [p.pillar for p in pillars if p.alert],
    }
    out_path.write_text(json.dumps(payload, indent=2))
```

### Decay → action

When `alert=True` for a pillar:

1. **First detection** (month 6): log to `PHASE_STATUS.md`; do not auto-exclude
2. **Sustained alert** (month 9): consider re-tuning that pillar's blend weight (e.g., 50/50 OSAP/DIY → 30/70)
3. **Sustained alert** (month 12): exclude the pillar from composite (zero its weight) and redistribute to other pillars

This is **monitoring + recommendation**, not auto-veto. Manual review per `WORKFLOW.md` Phase 6 "When to Add a Defense" gate (recursive: same gate applies to removing a decayed factor).

### Schema additive

```python
class Metadata(BaseModel):
    ...
    decay_report_url: str | None = None   # e.g., "/data/decay_report.json"
```

Frontend may surface "X pillars decaying" badge on `/about` or methodology page.

### Effort

| Step | LOC | Hours |
|---|---|---|
| ICDecayReport dataclass + check function | ~100 | 3 |
| Report writer (`decay_report.json`) | ~50 | 2 |
| Tests: synthetic decay pattern → alert fires after 6m; synthetic stable IC → alert doesn't fire | ~80 | 2 |
| Wire-up in `compute/main.py` (post-scoring) | ~30 | 1 |
| Frontend stub (optional v1.1; can defer to v1.2) | ~50 | 2 |
| **§3 total** | **~310 LOC** | **~10 hr (~1.5 days)** |

Acceptance gate: synthetic test where pillar IC drops to 30% of mean for 7 months → `alert=True`; synthetic stable pillar → `alert=False`.

## Combined effort

| Section | LOC | Days |
|---|---|---|
| §1 Cross-source validator | ~140 | 1 |
| §2 PBO + DSR gate | ~260 | 1.5 |
| §3 IC-decay monitor | ~310 | 1.5 |
| Integration test (all three working together on Phase 4 OSAP factor) | ~80 | 1 |
| Documentation (WORKFLOW.md cross-ref + README sub-section) | ~30 | 0.5 |
| **Grand total** | **~820 LOC** | **~5.5 days** |

Larger than the sum in `docs/PHASE_4_8_EFFORT_BACKFILL.md` (~500 LOC) because that doc undercounted integration tests. Worth its own PR.

## Phase 4 ship order

Per `v1-to-v1-1-migration/PLAN.md` PR sequencing:

- **PR 4b** ← inserted after 4a cache improvements (this PLAN, before any factor work) — defense infrastructure landing first means OSAP/JKP PRs can use the gates from day 1
- **OR** split: PR 4b = §1 cross-source (small + immediate value), PR 4c = §2+§3 PBO/DSR/IC-decay (larger; lands just before OSAP)

Locked decision: **single PR for all 3 sections** (PR 4b), per the user's "comprehensive audit close" framing.

## Dependencies

- `workflow-cache-improvements/PLAN.md` (PR 4a) lands first
- `backtest-infrastructure/PLAN.md` (Phase 5 foundational) is a **stronger** version of §2 — Phase 5 walk-forward + purged + embargoed CV. Phase 4 §2 is a simpler rolling-IC + Bailey 2014 DSR check; Phase 5 backtest-infra subsumes it.

## What this PLAN doesn't cover

- **Full walk-forward backtest** — that's `backtest-infrastructure/PLAN.md` (Phase 5)
- **Per-stock anomaly detection** — that's existing `compute/scoring/risk_overlay.py`
- **Composite stability monitoring** — could be added later; not a Phase 4 P0

## Open questions (closed by decisions above)

1. ~~PBO threshold?~~ → **0.5 locked** (Bailey-Borwein-López de Prado-Zhu 2014 standard)
2. ~~Cross-source delta tolerance?~~ → **5% locked** (RESEARCH_FINDINGS §"Phase 4 Defense Layer")
3. ~~IC-decay action policy?~~ → **6m alert + 12m auto-exclude** (graduated, not abrupt)
4. ~~`pypbo` vs custom?~~ → **`pypbo`** (MIT, vetted) + custom DSR (~30 LOC pandas)

## References

- Bailey, Borwein, López de Prado, Zhu (2014). "The Probability of Backtest Overfitting." *J. Computational Finance*.
- Bailey, López de Prado (2014). "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting, and Non-Normality." *J. Portfolio Management*.
- McLean, Pontiff (2016). "Does Academic Research Destroy Stock Return Predictability?" *Journal of Finance*.
- `pypbo` library: github.com/esvhd/pypbo (MIT)
