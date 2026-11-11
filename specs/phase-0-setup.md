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
| `scripts/load_bigquery.py` | Loads RutaPay JSONL into dataset `raw_pay` with an explicit nested schema (load jobs are free) |
| `dbt/ruta_ship/`, `dbt/ruta_udl/` | `dbt init` skeletons + `packages.yml` (`dbt_utils`) |

## Data volumes
About 2,000 companies, ~1,300 RutaShip shippers and ~1,100 RutaPay accounts, with ~30% overlap
(~550 matched). There are ~50k shipments, ~200k shipment events, ~30k invoices, ~35k payment
events, and 18 months of history ending 2026-10-31.
Match keys are deliberately messy: `tax_id` formatting (`B-1234567-8` vs `B12345678`), name
variants ("Acme Logistics S.L." vs "ACME LOGISTICS"), and personal emails vs corporate domains.

## Manual steps for the user
1. Create a GCP project and open the BigQuery console (Sandbox or free tier both work).
2. `gcloud auth application-default login`, then `gcloud config set project <id>`.
3. `cp .env.example .env`, `cp profiles.example.yml ~/.dbt/profiles.yml` (or project-local, gitignored).

## Acceptance criteria
- `make up && make data && make load` leaves the `raw_ship.*` tables populated in PG and the `raw_pay.*` tables in BQ.
- `dbt debug` passes in both projects.
- A sanity query runs on each side: row counts match the generator log.

## Status log
- ✅ Postgres 16 up, `raw_ship` loaded (carriers 60, lanes 36, shippers 1,326, shipments 69,092, events 270,962).
- ✅ Generator: 1,890 companies (incl. 40 decoys), 1,132 Pay accounts, **569 true multi-product** companies
  (ground truth in `data/truth/company_xref.csv`, used later to score entity resolution).
  RutaPay: 25,778 invoices, 27,492 payment events (incl. ~3% redelivered dupes), 2,577 subscription changes.
- ✅ `ruta_ship`: `dbt debug` OK. `dbt_utils` 1.4.1 installed in both projects.
- ✅ BigQuery: `raw_pay` loaded (accounts 1,132 · invoices 25,778 · payment_events 27,492 incl. dupes · subscription_changes 2,577). `dbt debug` OK on `ruta_udl`.
- ⚠️ **Probe result:** project `rutagroup` has **billing enabled**, so it is on the free tier, not the Sandbox. `MERGE` and `INSERT` work and tables have no 60-day expiry.
  Guardrail added: `maximum_bytes_billed: 1 GB` in the dbt profile. **Decision (option A):** use BQ DML where it teaches something (incremental `insert_overwrite`/`merge` on BQ). Stay in the free tier. Set a $5 budget alert (user).

## Versions pinned (2026-11)
dbt-core 1.12.6 · dbt-postgres 1.11.0 · dbt-bigquery 1.12.3 · dbt-metricflow 0.15.0 (metricflow 0.213) · Python 3.12.

**dbt v2 (the Fusion engine), worth knowing for the interview:** installers now default to dbt v2,
a Rust rewrite. It connects through ADBC drivers (single binary, no Python), validates YAML and configs
more strictly, adds static analysis and column-level lineage, and ships under its own license
(`dbt-oss` is the Apache-2.0 runtime). Its adapters are BigQuery, Snowflake, Databricks and Redshift.
**Postgres is not listed**, so this repo stays on **dbt Core v1.12**, which is still fully supported.
In production, Redshift + BigQuery would both be eligible for v2.

## Notes and risks
- dbt + Python 3.14 is unsupported, so pin `python = "3.12"` in uv.
- The MetricFlow YAML spec changed in 2025 (metrics-first spec / Fusion). Pin versions at install
  time, use the spec that matches them, and record which spec in Phase 5.
- DML probe done: see the status log above.
