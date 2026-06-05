"""Phase 7.0 — portfolio construction (AI-pick selection + auto-weighting).

Pure, deterministic, I/O-free so the "fair pick" is reproducible and
unit-testable offline. The forward pick runs every cron; the point-in-time
backfill reuses the SAME functions per historical rebalance date.
"""
