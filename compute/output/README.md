# compute/output

Atomic JSON writers and Pydantic schemas. Treat the JSON contract as sacred —
the frontend depends on it (Rule 9 in SKILL.md).

| Module | Role | Phase |
|---|---|---|
| `writer.py` | Atomic write to `frontend/public/data/` (tmp + rename) | 1 |
| `schemas.py` | Pydantic models that mirror `frontend/lib/types.ts` | 1+ |
