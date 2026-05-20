---
name: portable-graceful-degradation-try-except
description: Wrap every external-data integration call site in a try /
  except that sets ALL related output fields to None on failure.
  Production cron / job MUST NEVER block on a single external
  dependency failure (network outage, API rate limit, schema drift,
  package install failure). The try/except is paired with a structured
  log line and a per-integration `Metadata.<source>_status` field so
  the failure is observable downstream. Generic — drop-in for any
  project with a multi-source production pipeline. TRIGGER when adding
  a new external-data integration (API client, dataset fetch, optional
  dependency), when the user says "this shouldn't break the cron", or
  when CR feedback flags "what happens if this fails?". SKIP for core
  compute paths with no upstream dependency (pure math, in-memory
  transforms) and for early-development scout PRs where loud failure
  is the desired feedback signal.
---

# portable-graceful-degradation-try-except

A production-hygiene pattern: external-data integrations fail
non-deterministically. A weekly cron that aborts on a single fetch
failure produces stale or empty output, which is worse than partial
fresh output. Portable — applies to any project with a multi-source
production pipeline.

## Pattern

```python
try:
    result = fetch_external_data(...)
    output.source_a_value = result.value
    output.source_a_status = "ok"
except Exception as exc:  # broad on purpose
    logger.warning("source_a integration failed", exc_info=exc)
    output.source_a_value = None
    output.source_a_status = "failed"
    output.source_a_error = str(exc)[:200]
```

### Three-rule contract

1. **No partial state**: every field downstream of the failed fetch
   gets set to `None` (or the project's equivalent missing-value
   sentinel). Never leave a half-populated struct.
2. **No log-swallowing**: the exception is logged (with `exc_info`
   so the traceback is preserved) AND surfaced in the output
   metadata. Downstream consumers should be able to query
   `source_a_status == "failed"` without reading logs.
3. **Downstream-aware**: every consumer of `source_a_value` checks
   for `None` and handles it explicitly. Don't pass `None` into a
   formula that silently produces `NaN`.

## Anti-pattern

```python
# DON'T:
result = fetch_external_data(...)  # raises on failure
output.source_a_value = result.value  # cron aborts before reaching here
```

The cron now produces no output, and the operator gets a stack
trace at 22:00 Sunday with no fresh data for the rest of the week.

```python
# Also DON'T:
try:
    result = fetch_external_data(...)
    output.source_a_value = result.value
except Exception:
    pass  # ⚠️ silent failure, no observability
```

Silent failure is worse than loud failure. Downstream consumers see
a missing field and have no way to tell whether the source legitimately
returned nothing or whether the integration is broken.

## Trigger conditions

- Adding a new external-data integration (API client, dataset
  fetch, optional dependency)
- The integration consumes a network resource (HTTP, S3, database)
- The dependency is loaded via `pip install` of an optional extra
  (could be missing on contributor installs)
- CR feedback flags "what happens if this fails?"
- The integration sits inside a cron / batch job that is expected
  to produce SOME output even on partial failure

## Skip conditions

- Core compute paths with no upstream dependency (pure math,
  in-memory transforms, deterministic feature derivations from
  already-fetched data)
- Early-development scout PRs where loud failure is desirable
  (you WANT the test to abort if the dep doesn't install — that's
  the test)
- Single-shot manual scripts where the operator is watching the
  exit code

## Observability pairing

This pattern composes with `portable-observability-before-wiring`.
The `Metadata.<source>_status` field is the diagnostic surface;
the try/except is the implementation that populates it.

## QuantRank precedent

`compute/main.py` wraps every external integration in the OSAP /
JKP / Qlib / IPCA cluster in try/except. The OSAP integration
specifically (added in PR #112, hardened in PR #118) demonstrates
the pattern end-to-end:

```python
try:
    osap_signals, osap_diagnostics = fetch_osap_signals(...)
    detail.osap_signals = osap_signals
    metadata.osap_signals_used = osap_diagnostics.used
    metadata.osap_signals_missing_from_dataset = osap_diagnostics.missing
    metadata.osap_gate_diagnostics = osap_diagnostics.gate_results
except Exception as exc:
    logger.warning("OSAP integration failed", exc_info=exc)
    detail.osap_signals = None
    detail.osap_blended_score = None
    metadata.osap_signals_used = None
    metadata.osap_excluded_signals = None
    metadata.osap_signals_ic_12m = None
    metadata.osap_signals_coverage_pct = None
    metadata.osap_signals_missing_from_dataset = None
    metadata.osap_gate_diagnostics = None
    metadata.osap_signals_dropped_no_long_short = None
```

Every OSAP-derived field defaults to `None` on failure (rule 1, no
partial state). The exception is logged with traceback (rule 2, no
swallowing). Downstream `compute_composite()` and the UI both
check for `None` and skip OSAP-related rendering (rule 3,
downstream-aware).

See QuantRank's `SKILL.md` Rule 17 (production cron never blocks on
external dep) and `WORKFLOW.md` § "Graceful degradation contract"
for the project-specific lock.
