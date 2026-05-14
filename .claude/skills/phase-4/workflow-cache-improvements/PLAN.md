# Workflow Cache Improvements (Phase 4 planning stub — PR 4a)

**Status**: ✅ Implemented in PR (this branch). Audit found that 5 of 6 declared cache directories were not being restored across CI runs — the perf gap was in the workflow YAML, not in the ingest code itself. Implementation scope reduced accordingly (no new cache modules needed — the caches already exist in code; the workflow just wasn't preserving them).

## Purpose

Reduce weekly compute time from 25-50 min (cold-cache worst case) to <10 min steady-state by caching:
- 10-K text (chronic-slow tickers hit SEC EDGAR 5-10× per run for the same filing)
- Price history (yfinance 1Y daily — currently re-fetched every run)
- Universe constituents (Wikipedia S&P 500 scrape — rarely changes)

Fundamentals already cached (`fundamentals-v2-{quarter}-{os}` key, PR #49). This PLAN extends the discipline to the other ingest steps.

## Why now (PR 4a, leadoff Phase 4)

1. **Workflow #30 failure pattern**: 52m 59s compute time → push race vs newer main commits (PRs #52/#54). Even with PR #55's rebase-then-push retry, faster compute = smaller race window.
2. **Issue #15** (Fundamentals SEC throttling resilience): partial-fix relevance — fewer EDGAR hits when cache is warm.
3. **GitHub Actions free tier**: 2000 min/month. Current 30 min × 4 runs/month = 120 min. Headroom to add Phase 4 OSAP/JKP/Qlib without breaking quota.
4. **Subsequent Phase 4 PRs depend on caching discipline**: OSAP/JKP each add ~5 min if their parquet caches work. Without this PLAN landing first, Phase 4 cumulative compute could exceed 60-min budget.

## What's cached today (post-PR-4a)

The pre-flight audit (this PR) revealed that 5 of the 6 declared caches were *already implemented in code* but *not being restored across CI runs* — the workflow YAML only restored `compute/cache/fundamentals`. PR 4a expands the workflow's `path:` block.

| Ingest step | Cache module | In code? | Restored by workflow? |
|---|---|---|---|
| Fundamentals (EDGAR XBRL TTM) | `compute/ingest/fundamentals.py` + `FUNDAMENTALS_CACHE_DIR` | ✅ parquet, 45d freshness | ✅ pre-PR-4a |
| Fundamentals history (annual) | `compute/ingest/fundamentals.py` + `FUNDAMENTALS_HISTORY_CACHE_DIR` | ✅ parquet | ✅ PR 4a (new) |
| Price history (yfinance 5Y) | `compute/ingest/prices.py` + `PRICES_CACHE_DIR` | ✅ parquet, 24h freshness | ✅ PR 4a (new) |
| Universe constituents (Wikipedia) | `compute/ingest/universe.py` + `UNIVERSE_CACHE` | ✅ parquet, 7d freshness | ✅ PR 4a (new) |
| 10-K filing text (going-concern) | `compute/ingest/filing_text.py` + `EDGAR_10K_TEXT_CACHE_DIR` | ✅ JSON, 90d TTL | ✅ PR 4a (new) |
| 8-K Items 4.02 / 4.01 | `compute/scoring/eight_k_events.py` + `EDGAR_8K_CACHE_DIR` | ✅ JSON, 7d TTL | ✅ PR 4a (new) |
| OSAP returns (Phase 4 future) | (planned) `compute/cache/osap/` | ❌ not yet | n/a — add to workflow in PR 4h |
| JKP returns (Phase 4 future) | (planned) `compute/cache/jkp/` | ❌ not yet | n/a — add to workflow in PR 4i |

PR 4a's net impact: 5 cache layers now persist across CI runs. Each one's `_is_fresh()` check still applies (so stale data is auto-refetched).

CI guard: `tests/test_workflow_cache_coverage.py` parametrizes over every `config.*_CACHE_*` entry and asserts the workflow YAML includes it. Future cache additions (OSAP / JKP) must update **both** `config.py` *and* the workflow `path:` block to pass the test.

## Architecture

Same parquet + freshness-marker pattern as `compute/ingest/fundamentals.py`:

```
compute/cache/
  fundamentals/{ticker}.parquet      # existing
  filings/{cik}-{filing-id}.txt      # NEW — 10-K text by accession #
  filings_index/{cik}.parquet        # NEW — filing dates index per CIK
  prices/{ticker}-1y.parquet         # NEW — 1Y daily price history
  universe/sp500-{year-month}.parquet # NEW — universe snapshot
```

### Step 1: 10-K text cache (`compute/ingest/filings.py`)

```python
FILINGS_TEXT_CACHE = Path("compute/cache/filings")
FILINGS_TEXT_CACHE.mkdir(parents=True, exist_ok=True)

def fetch_10k_text(cik: str, accession_no: str) -> str:
    """Cache 10-K filing text by accession number (immutable — never re-fetch
    once cached)."""
    cache_path = FILINGS_TEXT_CACHE / f"{cik}-{accession_no.replace('-', '')}.txt"
    if cache_path.exists():
        return cache_path.read_text()
    text = _fetch_from_edgar_live(cik, accession_no)
    cache_path.write_text(text)
    return text
```

10-K accession numbers are **immutable** once published (SEC promise). Cache hit rate after first run = 100% until next 10-K filed.

Phase 1 hit-pattern: chronic-slow tickers (CRWD, SHOP, BKNG) fetch 10-K text 5-10× per run for different defense layers (going-concern, Beneish, Dechow, Sloan, etc.). PR 4a deduplicates this.

### Step 2: Filings index cache (`compute/ingest/filings.py`)

```python
FILINGS_INDEX_FRESHNESS_DAYS = 7  # weekly compute → 7-day staleness OK

def fetch_filings_index(cik: str) -> pd.DataFrame:
    """List of (form_type, accession_no, filing_date, period_end) for a CIK."""
    cache_path = Path(f"compute/cache/filings_index/{cik}.parquet")
    if _is_fresh(cache_path, FILINGS_INDEX_FRESHNESS_DAYS):
        return pd.read_parquet(cache_path)
    df = _fetch_index_from_edgar(cik)
    df.to_parquet(cache_path, index=False)
    return df
```

7-day freshness chosen because:
- 10-K filings are quarterly events; missing a fresh 10-K by ≤7 days is acceptable
- Weekly compute runs naturally invalidate this
- The CI cache restore step fills it cold-start

### Step 3: Price history cache (`compute/ingest/prices.py`)

```python
PRICE_FRESHNESS_DAYS = 3   # weekly compute Sun 22:00 UTC → 3-day staleness OK

def fetch_prices_1y(ticker: str) -> pd.DataFrame:
    """yfinance 1Y daily price history. Refresh every 3 days max."""
    cache_path = Path(f"compute/cache/prices/{ticker}-1y.parquet")
    if _is_fresh(cache_path, PRICE_FRESHNESS_DAYS):
        return pd.read_parquet(cache_path)
    df = yfinance.Ticker(ticker).history(period="1y")
    df.to_parquet(cache_path)
    return df
```

3-day freshness because daily price changes are the input to momentum / technical pillars; can't be stale by more than a week without alpha drift.

### Step 4: Universe snapshot (`compute/ingest/universe.py`)

```python
def fetch_sp500_universe() -> pd.DataFrame:
    """Wikipedia S&P 500 constituents. Refresh monthly (constituents change
    rarely)."""
    today_month = date.today().strftime("%Y-%m")
    cache_path = Path(f"compute/cache/universe/sp500-{today_month}.parquet")
    if cache_path.exists():
        return pd.read_parquet(cache_path)
    df = _scrape_sp500_from_wikipedia()
    df.to_parquet(cache_path, index=False)
    return df
```

Month-granular cache key auto-invalidates on the 1st of every month.

## GitHub Actions cache step

`.github/workflows/compute-rankings.yml` cache-restore step grows from a single fundamentals entry to a multi-path block:

```yaml
- name: Restore cache (Phase 4 multi-path)
  uses: actions/cache@v5
  with:
    path: |
      compute/cache/fundamentals
      compute/cache/filings
      compute/cache/filings_index
      compute/cache/prices
      compute/cache/universe
    key: cache-v3-${{ runner.os }}-${{ steps.quarter.outputs.q }}
    restore-keys: |
      cache-v3-${{ runner.os }}-
```

Key bump `fundamentals-v2-*` → `cache-v3-*` invalidates once on first PR 4a run, then all 5 caches build together.

## Expected compute time

| Scenario | Before PR 4a | After PR 4a |
|---|---|---|
| Fully cold cache (CI key miss + 90d freshness expiry) | 50 min | 35-40 min |
| Warm fundamentals cold extras (typical week post-PR-4a-cache-bump) | 25-30 min | 10-15 min |
| Fully warm steady state | 5 min | <5 min |

The cold scenario is rare (once per quarter when freshness expires). Steady state ≈ weekly runs after cache primes.

## Validation

- [ ] First PR 4a run after merge: takes longer (cache cold) — expected
- [ ] Second weekly run: comes in under 15 min (cache warm)
- [ ] `compute/cache/` total size stays under 1 GB (GitHub Actions cache limit is 10 GB per repo; we're well under)
- [ ] Cache restore step in workflow logs shows hit on all 5 paths after first warm run
- [ ] No regressions in production output (same `data_quality_input_corruption` count, same composite distribution within ±2%)

## Test plan

- [ ] Unit test `_is_fresh()` boundary conditions (existing — reuse)
- [ ] Unit test filings text cache returns from disk on second call (mock EDGAR)
- [ ] Unit test universe month-key invalidation (mock `date.today()`)
- [ ] Integration test: run `python -m compute.main` twice locally; second run < 50% of first run wall time
- [ ] Workflow dry-run: trigger `workflow_dispatch` on `docs/phase-4-cache-improvements` branch, confirm cache-restore step logs

## Effort estimate

| Step | LOC | Hours |
|---|---|---|
| 10-K text cache (`filings.py`) | ~80 | 3 |
| Filings index cache | ~50 | 2 |
| Price history cache (`prices.py`) | ~50 | 2 |
| Universe snapshot cache (`universe.py`) | ~40 | 1.5 |
| Workflow YAML update | ~20 | 1 |
| Tests | ~120 | 3 |
| Local verification + workflow dispatch dry-run | n/a | 2 |
| **Total** | **~360 LOC** | **~1.5 days** |

Smaller than the rough estimate in `docs/PHASE_4_8_EFFORT_BACKFILL.md` (which lumped it into "perf"). Worth its own PR.

## Tag + release

- Tag `v1.0.1-perf` (per `schema-versioning/PLAN.md` patch-bump rule — no schema change, just compute layer)
- Release notes: "Phase 4a: caches 10-K text + filings index + prices + universe. Reduces weekly compute from ~30 min to ~10 min steady-state."

## Risk mitigations

| Risk | Mitigation |
|---|---|
| Cache restore fails or restore-keys partial-match → some caches missing | Each `_is_fresh()` call independently re-fetches if cache missing; no cascading failure |
| GitHub Actions cache limit (10 GB) | Monitor cache size in workflow logs; if > 5 GB, prune oldest filings via `find -mtime +90 -delete` step |
| 10-K accession numbers change (shouldn't — SEC promise) | If detected, bump cache key v4 |
| yfinance API change | Existing PR #44 lock at `yfinance==0.2.55` already protects |

## Open questions (closed by decisions above)

1. ~~How long to cache 10-K text?~~ → **Indefinite** (immutable; cleanup script optional)
2. ~~Universe cache cadence?~~ → **Monthly** (auto-invalidating key)
3. ~~Single cache key or per-path?~~ → **Single key, 5 paths** (atomic restore, simpler)

## Dependencies

None — this is the leadoff PR. Everything else builds on it.

## What this PLAN doesn't cover

- **Distributed caching across CI workflows** (not needed — single weekly workflow)
- **Cache compression** (parquet already compressed)
- **External cache services** (S3, GCS) — defer until GitHub Actions cache becomes a bottleneck
