"""Research warehouse: per-run point-in-time Parquet snapshot.

Observability-first (Rule 18): this package WRITES the warehouse only.
Nothing reads it yet; the read/query layer ships in a later slice.
The warehouse NEVER blocks the cron — every write path is wrapped in a
try/except at the main.py call site.
"""
