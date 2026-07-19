# RevLens — Claude Code Project Instructions

## What this project is
End-to-end revenue intelligence platform for a fictional PLG SaaS ("NotionClone").
Unifies product telemetry + CRM (HubSpot-shaped) + billing (Stripe-shaped) into
dbt-modeled marts enabling closed-loop revenue attribution, with identity
resolution, event contracts, data quality, and (Phases 4-5) AI features.

## Architecture principles — do not violate
1. **Contract-first telemetry**: every event validates against `contracts/*.schema.json`.
   Invalid events go to a dead-letter table with the validation error. Never drop silently.
2. **Identity resolution lives in dbt**, not ingestion. Raw events keep anonymous_id/user_id
   as-is; stitching happens in `models/staging/identity/`.
3. **Medallion layering**: `raw` (as-landed, append-only) → `staging` (typed, deduped, 1:1 with
   sources) → `marts` (business logic). No mart reads raw directly.
4. **Idempotent loads**: everything keyed on natural ids (event_id, stripe object ids, hubspot ids).
   Re-running a load must never duplicate rows.
5. **Warehouse-agnostic**: dbt project must run on both Snowflake and DuckDB profiles.
   No warehouse-specific SQL outside `macros/` with dispatch.
6. **Docs are load-bearing**: every model and column gets a description — Phase 4's AI copilot
   consumes dbt docs as its semantic context. Undocumented model = broken AI feature later.

## Repo layout
- `data_simulator/` — generates the world. Deterministic via --seed. Don't "fix" the chaos
  (late events, dupes, malformed, CRM domain typos) — it's intentional DQ test material.
- `contracts/` — JSON Schema event contracts. Versioned. Breaking change = new major version file.
- `ingestion/` — loaders: NDJSON → warehouse raw tables + contract validation + dead-letter.
- `dbt/revlens/` — the dbt project.
- `sample_data/` — generated output (gitignored; regenerate with `make data`).

## Conventions
- Python 3.11+, type hints, no pandas in ingestion hot paths (use warehouse COPY/INSERT).
- dbt: staging models `stg_<source>__<object>`, marts `fct_`/`dim_`, tests on every PK.
- Every PR-sized change: run `make data && make validate` before considering it done.
- Secrets via env vars only (`SNOWFLAKE_*`), never committed.

## Current phase status
- [x] Phase 1: scaffold + simulator (this)
- [ ] Phase 2: dbt staging + identity resolution + core marts
- [ ] Phase 3: Dagster orchestration + Redpanda streaming path
- [ ] Phase 4: AI copilot ("Chat with RevLens") — semantic layer + evals
- [ ] Phase 5: AI DQ triage agent + governance + polish
