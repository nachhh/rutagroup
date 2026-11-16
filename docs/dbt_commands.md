# Command cheat sheet: dbt, MetricFlow, make

These are the commands used in this repo, plus other useful ones. Run dbt from inside a project folder
(`dbt/ruta_ship` or `dbt/ruta_udl`) with `DBT_PROFILES_DIR` pointing at the repo root. The Makefile does this for you.

```bash
cd dbt/ruta_udl && export DBT_PROFILES_DIR=../..     # then: uv run dbt …  /  uv run mf …
```

## 1. Core dbt commands

| Command | What it does | Example |
|---|---|---|
| `dbt debug` | Checks the profile, the connection and the dependencies | `uv run dbt debug` |
| `dbt deps` | Installs packages from `packages.yml` (e.g. dbt_utils) | `uv run dbt deps` |
| `dbt parse` | Parses the project and writes `target/manifest.json` and `semantic_manifest.json`. **No warehouse queries.** Fast; the base for CI checks, `make govern` and `mf` | `uv run dbt parse -q` |
| `dbt compile` | Renders Jinja to plain SQL in `target/compiled/` (to see what will run) | `uv run dbt compile -s fct_revenue` |
| `dbt show` | Runs a model's (or inline) SQL and prints a preview. Nothing is materialized | `uv run dbt show -s dim_customer --limit 5` · `uv run dbt show --inline "select count(*) from {{ ref('fct_revenue') }}"` |
| `dbt run` | Materializes models (no tests) | `uv run dbt run -s fct_udl_shipments` |
| `dbt test` | Runs data tests and unit tests | `uv run dbt test -s fct_revenue` · `uv run dbt test -s test_type:unit` |
| `dbt seed` | Loads CSVs from `seeds/` into tables | `uv run dbt seed -s seed_fx_rates_monthly` |
| `dbt snapshot` | Captures SCD2 history (Phase 2, Postgres) | `uv run dbt snapshot` |
| `dbt build` | seed + run + snapshot + test **in DAG order**; a failing test skips everything downstream. The default for CI and Airflow | `uv run dbt build -s +fct_revenue` |
| `dbt source freshness` | Checks `loaded_at_field` against the warn/error thresholds | `uv run dbt source freshness -s source:ship_replica` |
| `dbt ls` | Lists the resources a selector matches (dry run of a selection) | `uv run dbt ls -s state:modified+ --state prod-artifacts/` |
| `dbt docs generate` / `serve` | Builds and serves the docs site with lineage (models, exposures, semantic models) | `uv run dbt docs generate && uv run dbt docs serve` |
| `dbt retry` | Re-runs only what failed or was skipped in the last invocation | `uv run dbt retry` |
| `dbt clone` | Zero-copy clones of prod objects into your schema (BQ table clones). Fast dev setup | `uv run dbt clone -s state:modified+ --state prod-artifacts/` |
| `dbt clean` | Deletes `target/` and `dbt_packages/` | `uv run dbt clean` |

## 2. Node selection (`-s` / `--select`, `--exclude`)

| Selector | Meaning | Example |
|---|---|---|
| `model` | Just that model | `-s dim_customer` |
| `+model` / `model+` | Plus all upstream / downstream | `-s +fct_revenue` · `-s seed_fx_rates_monthly+` (rate change → rebuild children) |
| `2+model` | Only 2 levels upstream | `-s 2+fct_revenue` |
| `@model` | The model, its descendants **and** their ancestors (safe CI rebuild) | `-s @int_customer_xwalk` |
| `path:` / `tag:` / `group:` | By folder, tag, or ownership group | `-s path:models/marts/udl` · `-s group:udl_core` |
| `exposure:` | Everything a consumer depends on | `-s +exposure:metrics_mcp_server` |
| `source:` | A source (freshness, or `source:x+` for its children) | `-s source:ship_replica+` |
| `test_type:` | `unit` or `data` tests | `-s test_type:unit` |
| `state:modified` | Changed versus a prod `manifest.json` (Slim CI) | `-s state:modified+ --state prod-artifacts/` |
| `result:error` | Failed in the previous run (needs `--state`) | `-s result:error+ --state target/` |
| `--exclude` | Remove from the selection | `-s +fct_revenue --exclude tag:slow` |

## 3. Useful flags

| Flag | What it does | Example |
|---|---|---|
| `--full-refresh` | Rebuild incrementals (and seeds) from scratch | `dbt build -s fct_invoice_lines --full-refresh` |
| `--vars` | Pass project variables | `dbt run -s fct_invoice_lines --vars '{overwrite_lookback_days: 35}'` |
| `--target` / `-t` | Pick a profile output (dev / prod / ci) | `dbt build -t prod` |
| `--defer --state <dir>` | Unbuilt upstream refs resolve to **prod** objects (Slim CI / dev without building everything) | `dbt build -s state:modified+ --defer --state prod-artifacts/` |
| `--favor-state` | With `--defer`: prefer prod even if a dev object exists | `… --defer --favor-state --state prod-artifacts/` |
| `--empty` | Build with zero rows (schema and contract check only, almost free) | `dbt build --empty -s marts` |
| `--fail-fast` / `-x` | Stop at the first failure | `dbt build -x` |
| `--threads` | Parallelism | `dbt build --threads 8` |
| `-q` / `--quiet` | Errors only | `dbt parse -q` |
| `--warn-error` | Treat warnings as errors (strict CI) | `dbt parse --warn-error` |

## 4. MetricFlow (`mf`, local engine for the semantic layer)

`mf` reads `target/semantic_manifest.json`, so run **`dbt parse` first** after any YAML change (`make mf` does it).

| Command | What it does | Example |
|---|---|---|
| `mf validate-configs` | Validates semantics, then runs every model, dimension and metric against the warehouse | `uv run mf validate-configs` |
| `mf list metrics` | Metric catalog (what an agent would discover) | `uv run mf list metrics` |
| `mf list dimensions` | Dimensions available for given metrics | `uv run mf list dimensions --metrics total_revenue` |
| `mf list entities` | Join keys | `uv run mf list entities --metrics take_rate` |
| `mf query --metrics … --group-by …` | Compile and run a metric query | `uv run mf query --metrics total_revenue,active_customers --group-by customer__region,metric_time__quarter` |
| `--where` | Filter with Jinja dimension references | `--where "{{ Dimension('customer__region') }} = 'iberia'"` |
| `--start-time` / `--end-time` | Bound `metric_time` (avoid partial periods and spine overrun) | `--start-time 2025-07-01 --end-time 2026-09-30` |
| `--order` / `--limit` | Sort (prefix `-` for descending) and cap rows | `--order -total_revenue --limit 10` |
| `--explain` | Print the generated SQL instead of running it | `uv run mf query --metrics revenue_per_customer --group-by customer__is_multi_product --explain` |
| `--show-dataflow-plan` | Print the internal plan (joins, aggregations) | `… --explain --show-dataflow-plan` |
| `--saved-query` | Run a saved query | `uv run mf query --saved-query churn_by_segment` |
| `--csv` | Write the results to a file | `… --csv /tmp/revenue.csv` |

In dbt Cloud the equivalents are `dbt sl list metrics`, `dbt sl query …` and `dbt sl validate`, served by the
hosted Semantic Layer API.

Migrating legacy semantic YAML to the latest spec: `dbt-autofix deprecations --semantic-layer`.

## 5. Make targets (this repo)

| Target | What it does |
|---|---|
| `make up` / `make down` | Start / stop Postgres ("Redshift") in Docker |
| `make data` | Generate the synthetic data into `./data` |
| `make load` (`load-pg`, `load-bq`) | Load RutaShip CSV → Postgres, RutaPay JSONL → BigQuery |
| `make deps` / `make debug` | dbt deps / debug in both projects |
| `make ship` / `make udl` | `dbt build` RutaShip (Postgres) / the UDL (BigQuery) |
| `make snapshot` / `make day2` | SCD2 snapshot; simulate day-2 source changes |
| `make freshness` | Source freshness, both projects |
| `make pg-roles` / `make bq-governance` | Least-privilege roles in PG; BQ policy tag, masking, row policy, authorized view |
| `make govern` | Governance CI gate over both `manifest.json` files (rules R1–R6) |
| `make replicate` | RutaShip public marts → BigQuery `ship_replica` |
| `make ontology` | Regenerate `kg_nodes` / `kg_edges` from `ontology/ruta_ontology.yml` |
| `make eval-er` | Entity-resolution precision / recall vs ground truth |
| `make semantic` | Validate the semantic layer + run both saved queries |
| `make mf Q="…"` | Ad-hoc MetricFlow query, e.g. `make mf Q="--metrics take_rate --group-by metric_time__year"` |

## 6. A few `bq` CLI commands used along the way

| Command | What it does |
|---|---|
| `bq ls --project_id=rutagroup` | List datasets |
| `bq ls --project_id=rutagroup udl_marts` | List tables in a dataset |
| `bq query --use_legacy_sql=false 'select …'` | Run standard SQL |
| `bq query --dry_run --use_legacy_sql=false 'select …'` | Bytes that would be scanned (cost check, free) |
| `bq show --schema --format=prettyjson rutagroup:udl_marts.fct_revenue` | Table schema |
| `bq rm -f -t rutagroup:dataset.table` | Delete a table |
