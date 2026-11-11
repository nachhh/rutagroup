# Phase 0: Setup (⏱ 45 min)

## Goal
Get both "warehouses" running with synthetic data loaded, and scaffold both dbt projects so that `dbt debug` passes.

## Files
| File | Purpose |
|---|---|
| `docker-compose.yml` | Postgres 16 (`ruta_pg`, port 5432, db `ruta`), volume-backed |
| `pyproject.toml` / `uv.lock` | Python 3.12. Deps: `dbt-core`, `dbt-postgres`, `dbt-bigquery`, `dbt-metricflow[postgres,bigquery]`, `google-cloud-bigquery`, `pyarrow`, `psycopg[binary]`, `faker` (versions pinned at install time) |
| `.env.example` | `PG_*`, `GCP_PROJECT`, `BQ_LOCATION=US`, `GEMINI_API_KEY=` / `ANTHROPIC_API_KEY=` |
| `profiles.example.yml` | Two profiles: `ruta_ship` (postgres) and `ruta_udl` (bigquery, `method: oauth`). The real `profiles.yml` is gitignored |
| `Makefile` | `up`, `down`, `data`, `load`, `ship`, `replicate`, `udl`, `mf`, `all` |
| `scripts/generate_data.py` | Deterministic generator (seed 42) that writes `data/*.jsonl` / `*.csv` |
| `scripts/load_postgres.py` | Loads RutaShip CSVs into schema `raw_ship` |
| `scripts/load_bigquery.py` | Loads RutaPay JSONL into dataset `raw_pay` with an explicit nested schema (load jobs are allowed in Sandbox) |
| `dbt/ruta_ship/`, `dbt/ruta_udl/` | `dbt init` skeletons + `packages.yml` (`dbt_utils`) |

## Data volumes
About 2,000 companies, ~1,300 RutaShip shippers and ~1,100 RutaPay accounts, with ~30% overlap
(~550 matched). There are ~50k shipments, ~200k shipment events, ~30k invoices, ~35k payment
events, and 18 months of history ending 2026-10-31.
Match keys are deliberately messy: `tax_id` formatting (`B-1234567-8` vs `B12345678`), name
variants ("Acme Logistics S.L." vs "ACME LOGISTICS"), and personal emails vs corporate domains.

## Manual steps for the user
1. Create a GCP project, then open the BigQuery console. The Sandbox banner should appear (no billing).
2. `gcloud auth application-default login`, then `gcloud config set project <id>`.
3. `cp .env.example .env`, `cp profiles.example.yml ~/.dbt/profiles.yml` (or project-local, gitignored).

## Acceptance criteria
- `make up && make data && make load` leaves the `raw_ship.*` tables populated in PG and the `raw_pay.*` tables in BQ.
- `dbt debug` passes in both projects.
- A sanity query runs on each side: row counts match the generator log.

## Notes and risks
- dbt + Python 3.14 is unsupported, so pin `python = "3.12"` in uv.
- The MetricFlow YAML spec changed in 2025 (metrics-first spec / Fusion). Pin versions at install
  time, use the spec that matches them, and record which spec in Phase 5.
- Verify the Sandbox DML limits empirically (one `MERGE` attempt) and record the result here.
