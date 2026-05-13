---
name: network-test-runner
description: Run pytest with the `@pytest.mark.network` opt-in marker enabled
  to exercise live SEC EDGAR fetches against the real API. Required when
  modifying any module under `compute/ingest/` (fundamentals, prices,
  universe), `compute/ingest/filing_text.py`, or `compute/scoring/
  eight_k_events.py`. Sets up the `EDGAR_USER_AGENT` env var requirement,
  surfaces SEC throttling state via per-test duration, and distinguishes
  rate-limit failures from genuine regressions. TRIGGER any time the
  ingest layer or any EDGAR-bound module changes, when offline /
  synthetic-fixture tests pass but the user wants live-data confidence,
  when CI doesn't run network tests (sandboxed) and the change needs
  pre-merge live verification, or when the user asks "did the live
  fetch still work?" / "run the @network tests" / "test against real
  EDGAR". SKIP for any change that doesn't touch the ingest or 10-K /
  8-K parser layers — the @network tests skip cleanly without
  `EDGAR_USER_AGENT` so accidental invocation is harmless.
---

# network-test-runner

## Why @network is opt-in

The `@pytest.mark.network` tests hit the real SEC EDGAR API. They live
behind an opt-in flag because:

1. **SEC EDGAR rate limit is 10 req/s**. Multiple developers running
   the full network suite concurrently can exhaust this limit and
   trigger SEC's automated throttling response.
2. **Network flake risk**. Transient SEC throttling produces false
   test failures; CI shouldn't treat those as red builds.
3. **CI sandbox has no `EDGAR_USER_AGENT`**. All `@network` tests skip
   cleanly when the env var is absent, so the default `pytest`
   invocation in CI works without surprise.

The flag flips the test from "skipped" to "live" — useful in local dev
when ingest changes need real-data confidence.

## Required environment

```bash
export EDGAR_USER_AGENT="Your Name your@email.com"
```

SEC EDGAR rejects requests without a real contact string (HTTP 403).
The string should be a real email — the SEC may contact you about
anomalous traffic patterns, and a fake address risks IP-level
deny-listing.

## Invocation

### Run all `@network` tests

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

### Verbose with per-test timing (useful for throttling detection)

```bash
pytest --run-network -v --durations=20
```

### Run network + non-network in one shot

```bash
pytest --run-network -m "network or not network"
```

## Expected runtime

| Scope | Expected duration |
|---|---|
| Single-ticker test | 2-10 seconds (one EDGAR round-trip) |
| Full module | 30 seconds - 2 minutes |
| Full `@network` suite (~3 tests in PR-3d) | < 30 seconds (cache warms after first test) |

If a single-ticker test takes > 30 seconds, SEC EDGAR is throttled.
Re-run after a few minutes — or accept the elevated p95 if the test
still passes.

## Test markers used in this repo

| Marker | Purpose | Skip condition |
|---|---|---|
| `@pytest.mark.network` | Hits real SEC EDGAR | `--run-network` flag absent |
| `@_NETWORK_PRE` | Composite of `network` + `EDGAR_USER_AGENT` env check | Either condition fails |

The composite skip avoids confusing failures when running locally
without the env var. Tests SKIP rather than fail with `auth required`.

## Output interpretation

### All passed

```
========== 5 passed, 17 deselected, 3 warnings in 19.81s ==========
```

The "deselected" count = non-network tests not run because of
`--run-network`. To run both kinds, use the `-m "network or not network"`
form above.

### Some skipped

```
SKIPPED [1] tests/test_scoring/test_eight_k_events.py:378: EDGAR_USER_AGENT not set
```

Set the env var and re-run.

### Live failure

```
FAILED test_C1_known_clean_tickers_mostly_no_fired_flags - AssertionError
```

Common causes (in order of frequency):

1. **SEC throttling** — re-run after a few minutes. A second failure
   in a row probably isn't throttling.
2. **edgartools API drift** — check `pip show edgartools` version. May
   need pin / unpin in `pyproject.toml`.
3. **Real data change** — e.g., a known-clean ticker filed an Item 4.02.
   Legitimate test failure; update the test universe to a different
   known-clean ticker.

## Anti-patterns

- Running `--run-network` in CI's main pytest job. The sandbox has no
  `EDGAR_USER_AGENT`; tests would skip OR (worse) auth successfully
  and burn through the SEC rate-limit budget. The CI workflow
  `compute-rankings.yml` runs the actual weekly compute, not the
  network test suite.
- Committing `EDGAR_USER_AGENT` to settings or hardcoding it. Always
  via env var. CI uses a GitHub Actions secret.
- Looping network tests in `while true` to find intermittent flakes.
  That hammers the SEC rate limit. If a test is flaky, inspect logs +
  add retries via tenacity in the production code, not the test loop.

## Why this skill exists

EDGAR fetches are the slowest, flakiest part of QuantRank. Offline
tests use synthetic fixtures that don't catch protocol-level drift —
XBRL tag rename, edgartools API change, HTML/SGML structure shift.
The `@network` tests are the safety net that fires when the upstream
contract breaks. This skill makes that safety net easy to run before
merging an ingest change.

## Related skills

- `verify-production-output` — the production-side end of this same
  contract. A green network suite means the production compute should
  work; a Section A scan confirms it actually does.
- The PR 3d run-#14 incident (SEC throttling at scale) was triaged
  using this skill against the affected ingest modules.
