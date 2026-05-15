# Public API Documentation (Phase 11 planning stub)

**Status**: Planning. Documents the JSON output as a stable public
API so 3rd parties (researchers, hobbyists, MCP server builders) can
consume QuantRank's rankings reliably.

## Purpose

QuantRank already serves rankings.json + metadata.json + per-stock
JSONs from `frontend/public/data/` — these are effectively a public
API but no consumer docs exist. Phase 11 §3 formalizes the API
contract so 3rd parties can build on top with confidence.

Use cases for 3rd-party consumers:
- Academic researchers ingesting our factor library
- MCP server exposing rankings to LLM apps
- Mobile apps / browser extensions / Discord bots
- Algo-trading hobbyist signals (free home use only — per Disclaimer)
- Educators using QuantRank as a teaching dataset

## Architecture

```
frontend/app/api-docs/page.tsx        # main doc landing
content/api/
  contract.md                          # versioning + stability rules
  schemas.md                           # auto-gen from Pydantic schemas
  examples.md                          # curl / Python / JS samples
  changelog.md                         # version-by-version changes
frontend/components/SchemaTable.tsx    # render field table
```

## Public API surface

### Endpoints (static-served JSON, no auth, free forever)

| Path | Schema | Update cadence |
|---|---|---|
| `/data/metadata.json` | `Metadata` (Pydantic) | Weekly |
| `/data/rankings.json` | `StockSummary[]` | Weekly |
| `/data/stocks/<TICKER>.json` | `StockDetail` | Weekly |
| `/data/stocks/history/<TICKER>.json` | `StockHistory` | Weekly |
| `/data/decay_report.json` *(Phase 5)* | `ICDecayReport[]` | Monthly |

### Versioning contract

Per `schema-versioning/PLAN.md` (Phase 4 work):
- `metadata.version` follows semver: `1.0.0` / `1.1.0` / `2.0.0`
- Same major version: **additive only** (existing fields keep type +
  meaning)
- Minor version: new optional fields may appear
- Major version: breaking changes; consumers should pin to a major

API doc page formalizes this for 3rd-party readers.

## Doc page sections

1. **Quickstart** — fetch + render rankings.json in 5 lines of Python
2. **Authentication** — none (free, public)
3. **Rate limits** — none (Vercel CDN; cache and respect)
4. **Schema reference** — auto-generated from `schemas.py` snapshot
5. **Versioning** — semver rules, deprecation policy
6. **Examples**:
   - curl GET
   - Python with `pandas.read_json`
   - JavaScript with `fetch`
   - MCP server stub (reuses `mcp-builder` skill)
7. **Changelog** — version-by-version diff (from CHANGELOG.md)
8. **License** — MIT; commercial use prohibited per Disclaimer

## Effort

| Step | LOC | Days |
|---|---|---|
| Page route + layout | ~120 | 1 |
| Schema table auto-render from `schema-snapshot.json` | ~250 | 2 |
| Quickstart + 4 example languages | ~300 | 2 |
| Versioning + changelog page | ~200 | 1.5 |
| MCP server stub example (links to vendored `mcp-builder` skill) | ~300 | 2 |
| i18n (TH + EN) | ~800 | 3 |
| OpenAPI / Swagger generation (optional Phase 11+) | ~400 | 2 |
| Tests | ~150 | 1 |
| **Total** | **~2520 LOC** | **~14.5 days** |

## Decisions (locked)

1. ~~Free vs paid tier?~~ → **Free forever** (matches Disclaimer
   educational-use posture; commercial use restricted by license, not
   by tech gate)
2. ~~Rate limit?~~ → **None at our layer** (Vercel CDN handles; CDN
   provider rate-limits abusive consumers automatically)
3. ~~Auth?~~ → **None** (would need backend; static-site model wins)
4. ~~OpenAPI / Swagger spec?~~ → **Optional — only if 3rd-party
   demand surfaces** (initial scope is docs + examples)

## Dependencies

- Phase 4 `schema-versioning/PLAN.md` — formalize semver before docs
- Phase 4 `v1-to-v1-1-migration/PLAN.md` — define what v1.0 promises
- Phase 5 `decay_report.json` — new endpoint surfaces here
- Phase 10 §3 bilingual-i18n — TH + EN versions

## Out of scope

- API key issuance / per-user quotas — paid tier territory
- WebSocket / streaming feed — static export model excludes
- Historical archive endpoint (rankings.json snapshots over time) —
  separate stub if 3rd-party requests it
- Backend mutation endpoints (POST / PUT) — explicitly NEVER (this
  is a read-only public dataset)
