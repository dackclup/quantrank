---
name: network-test-runner
description: Run pytest with the @network mark enabled to exercise live SEC EDGAR
  fetches against the real API. Use when modifying ingest layer (fundamentals,
  filing_text, eight_k_events) and the offline / synthetic-fixture tests aren't
  enough to prove correctness against live data. Skipped by default in CI sandbox.
---

# network-test-runner

## When to use

- After modifying any module under `compute/ingest/` or
  `compute/scoring/eight_k_events.py` / `compute/ingest/filing_text.py`
  (anything that hits SEC EDGAR live)
- When the offline test surface is exercised but you suspect a
  protocol-level regression (XBRL tag rename, edgartools API drift,
  HTML/SGML structure change)
- During PR pre-merge if `@network` tests flagged as required

## What it does

Runs pytest with the `--run-network` flag (custom marker config in
`pyproject.toml`). The marker is opt-in because:

1. SEC EDGAR rate limit (10 req/s) — full network suite hits the
   limit if multiple developers run concurrently
2. Network flake risk — transient SEC throttling causes false test
   failures
3. CI sandbox has no `EDGAR_USER_AGENT` env var, so all `@network`
   tests skip cleanly there

## Required environment

```bash
export EDGAR_USER_AGENT="Your Name your@email.com"
```

SEC EDGAR rejects requests without a real contact string (returns
403). Use a real email — the SEC may contact you about anomalous
traffic patterns.

## Invocation

### Run all @network tests

```bash
pytest --run-network
```

### Run a specific module

```bash
pytest tests/test_features/test_fundamentals.py --run-network
pytest tests/test_scoring/test_eight_k_events.py --run-network
pytest tests/test_ingest/test_filing_text.py --run-network
```

### Run a single test

```bash
pytest tests/test_scoring/test_eight_k_events.py::test_C1_known_clean_tickers_mostly_no_fired_flags --run-network
```

### Verbose with timing

```bash
pytest --run-network -v --durations=20
```

## Expected runtime

- Single ticker test: 2-10 seconds (one EDGAR round-trip)
- Full module: 30 seconds - 2 minutes
- Full `--run-network` suite (current ~3 tests in PR-3d): under 30s
  (cache warms after the first test)

If a test takes >30s for a single-ticker check, the SEC API is
throttled. Re-run after a few minutes or accept the elevated p95.

## Test markers in this repo

| Marker | Purpose | Skip when |
|---|---|---|
| `@pytest.mark.network` | Hits real SEC EDGAR | `--run-network` flag absent |
| `@_NETWORK_PRE` | Composite of `network` + `EDGAR_USER_AGENT` env check | Either condition fails |

The composite skip avoids confusing failures when running locally
without the env var (you'd see `auth required` rather than `skipped`).

## Output interpretation

### All passed

```
========== 5 passed, 17 deselected, 3 warnings in 19.81s ==========
```

The "deselected" count = non-network tests not run because we used
`--run-network`. To run the full suite (network + non-network), use:

```bash
pytest --run-network -m "network or not network"
```

### Some skipped

```
SKIPPED [1] tests/test_scoring/test_eight_k_events.py:378: EDGAR_USER_AGENT not set
```

Set `EDGAR_USER_AGENT` and re-run.

### Live failure

```
FAILED test_C1_known_clean_tickers_mostly_no_fired_flags - AssertionError
```

Read the assertion. Common causes:
- SEC throttling: re-run after a few minutes
- edgartools API drift: check `pip show edgartools` version, may need
  pin / unpin in `pyproject.toml`
- Real data change: e.g., a known-clean ticker filed an Item 4.02 —
  legitimate test failure, update the test universe

## Anti-patterns (do not do)

- Don't run `--run-network` in CI's main pytest job. The CI sandbox
  has no `EDGAR_USER_AGENT`; tests would skip OR (worse) auth
  successfully and burn through SEC rate limit. The job
  `compute-rankings.yml` is for running the actual compute, not
  the network test suite.
- Don't commit `EDGAR_USER_AGENT` to settings or hardcode it. Always
  via env var. CI uses a GitHub Actions secret.
- Don't loop network tests in a `while true` to detect intermittent
  flakes — that hammers the SEC rate limit. If a test is flaky,
  inspect logs + add retries via tenacity in the production code,
  not the test loop.

## Related

- `compute/ingest/fundamentals.py` (Phase 2 ingest tests)
- `compute/ingest/filing_text.py` (Phase 3d Defense #8 — 10-K text)
- `compute/scoring/eight_k_events.py` (Phase 3d Defenses #9/#10 —
  currently deferred; tests still fixture-driven)
- `pytest.ini` / `pyproject.toml` `[tool.pytest.ini_options]` for
  the marker config
