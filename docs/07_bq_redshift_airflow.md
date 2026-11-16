# 07: BigQuery + Redshift patterns, Airflow orchestration, end-to-end lineage

Spec: [phase-7](../specs/phase-7-bq-redshift-airflow.md). DAG: [airflow/dags/ruta_pipeline.py](../airflow/dags/ruta_pipeline.py).
Diagrams: [pipeline flow](diagrams/pipeline-flow.md) · [end-to-end lineage](diagrams/end-to-end-lineage.md).

## 1. Six ways to combine Redshift and BigQuery

| # | Pattern | How | Pros | Cons |
|---|---|---|---|---|
| 1 | **Batch replicate RS → BQ** (what we simulate) | `UNLOAD` to Parquet → S3 → **Storage Transfer Service** → GCS → BQ load, or BigLake external tables | Simple, cheap at batch cadence, BigQuery becomes the UDL hub | AWS egress cost, hours of latency, two copies |
| 2 | **BigQuery Data Transfer Service for Redshift** | Managed connector: schema + data | Managed, good for a **migration** | Migration-oriented, not ongoing CDC |
| 3 | **BigQuery Omni** | BigQuery queries S3 in place (BigLake on AWS regions) | No copy, one SQL surface | Region limits; cross-cloud joins still move results; its own cost model |
| 4 | **CDC / streaming** | Debezium or AWS DMS → Kafka / Pub/Sub → BQ (Datastream doesn't read Redshift: capture from the source OLTP DB instead) | Minutes-fresh data | Operational complexity, schema evolution |
| 5 | **Federation / virtualization** | Trino / Starburst over both | No copies | Performance, governance spread across engines |
| 6 | **Unify only at the semantic layer** | Each warehouse stays; the metrics layer queries each | Least data movement | Cross-warehouse joins (the whole point of a UDL) are hard |

**How to choose (2-minute whiteboard).** Ask four questions:
1. Freshness: daily is enough → batch (1). Minutes → CDC (4).
2. Long-term direction: consolidating onto GCP → DTS migration (2), then batch for what remains.
3. Volume × egress cost: huge, rarely joined data → leave it in place (Omni 3 / federation 5).
4. Joins: a UDL **joins customers across products**, so the data needs one home → replicate into the hub.

**For Ruta:** batch replication of the *public marts only* (not raw), driven by a contract (the `udl_replication`
exposure), into BigQuery as the UDL hub. CDC is added later only for the tables that need freshness.
Replicating marts instead of raw means less egress, and governance (contracts, PII masking) is applied **before**
data crosses clouds.

## 2. Dialect and physical-design translation

| Redshift | BigQuery | Note |
|---|---|---|
| `DISTKEY` / `DISTSTYLE` | (none, storage is managed) | Redshift co-locates rows on nodes for joins; BQ shuffles |
| `SORTKEY` | `PARTITION BY` + `CLUSTER BY` | Both prune scanned data |
| `SUPER` + PartiQL | `JSON` / `STRUCT` / `ARRAY` + `UNNEST` | Nested data: BQ is far richer |
| `VARCHAR(n)` | `STRING` | Length limits disappear (and so do truncation bugs) |
| `IDENTITY` | none (use `GENERATE_UUID()` or a hash key) | That's why our keys are `FARM_FINGERPRINT` hashes |
| `GETDATE()` | `CURRENT_TIMESTAMP()` | Same with date functions: dbt cross-db macros hide it |
| `UNLOAD ... FORMAT PARQUET` | `EXPORT DATA ... FORMAT='PARQUET'` / `bq load` | The replication primitives |
| RA3 nodes / Serverless RPUs | On-demand (per TB scanned) / Editions (slots) | Pricing models differ: compare per workload |

**Same models on two adapters:** dbt makes `select ... from {{ ref() }}` portable, and `adapter.dispatch` macros
cover dialect gaps. Nested JSON (RutaPay webhooks) is where portability ends. That's an argument for *where* to
unify: in the warehouse with the strongest nested-data support.

## 3. Airflow: how the DAG is built (and why)

```
ruta_pipeline (@daily)
  extract_load:  load_ship_source           load_pay_source → bq_governance
  redshift:      ship_freshness → ship_build ──► Asset postgres://…/marts
  cross_cloud:   replicate_to_bq ──────────► Asset bigquery://rutagroup/ship_replica
  udl:           kg_codegen → governance_gate → udl_build ──► Asset bigquery://rutagroup/udl_marts
                                                                  ║ (data-aware trigger)
ruta_semantic_checks (schedule=[udl_marts])                       ▼
  mf_validate → saved_queries (CSV exports) → agent_smoke_test (opt-in, skipped by default)
```

| Decision | Choice | Alternative and when to use it |
|---|---|---|
| Who computes? | Airflow **orchestrates**; dbt/BigQuery/Postgres compute. `BashOperator` calls `uv run dbt build` in the project venv | `KubernetesPodOperator` / `DockerOperator` (one image per task, best isolation in production) |
| Task granularity | One task per dbt **project** (`dbt build` = models + tests in order, skips downstream of a failure) | **Astronomer Cosmos** `DbtTaskGroup`: one Airflow task per model/test; per-model retries and alerts, but hundreds of tasks |
| Dependencies | Separate venv for Airflow (`airflow/.venv`) | Never install Airflow and dbt together: conflicting pins |
| `make` or commands? | The underlying commands: one command = one retry unit, clean logs | `make` hides failures and retries the whole recipe |
| Quality gates | `source freshness` before the Redshift build; governance check R1–R7 before the BigQuery build | Fail fast before spending |
| Cross-DAG dependency | **Assets** (`outlets` → `schedule=[asset]`) | Cron offsets ("run at 07:00 and hope") or `ExternalTaskSensor` (couples DAG internals) |
| Reruns | Idempotent tasks (truncate-reload, rerunnable builds), `max_active_runs=1`, `catchup=False` | `catchup=True` with `{{ ds }}`-partitioned incrementals for true per-day backfills |
| Failures | `retries=2`, exponential backoff, `execution_timeout=30m` | Add `on_failure_callback` → Slack/PagerDuty; SLAs via deadline alerts |
| Cost-gated step | `agent_smoke_test` behind a `Param`, exit code 99 → **skipped** | |

Airflow 2 → 3 renames worth knowing: Datasets → **Assets**; `from airflow.sdk import DAG, Asset`; core operators moved
to `apache-airflow-providers-standard`; the webserver is now an API server; `airflow dags test` runs a DAG in-process.

## 4. End-to-end lineage

| Layer | Lineage source | What it sees |
|---|---|---|
| Inside each dbt project | `manifest.json` (refs, sources), exposures | source → staging → marts → exposure |
| Across clouds (the replication script) | **Nothing automatic**: dbt never sees it | Declared twice: `udl_replication` exposure (Ship side) ↔ `ship_replica` sources (UDL side); Airflow `inlets/outlets` |
| Semantic layer | `semantic_manifest.json` | public model → semantic model → metrics |
| Consumers | Exposures (`metrics_mcp_server`, `exec_dashboard`) | which products each consumer depends on |
| Across DAGs | Airflow **Assets** view | producer task → asset → consumer DAG |

`make lineage` stitches all of these into one generated graph:
[end-to-end-lineage.md](diagrams/end-to-end-lineage.md). It's built from metadata, not drawn by hand.

**In production:** use the **OpenLineage** standard.
- `apache-airflow-providers-openlineage` emits a run event per task with its inputs and outputs.
- `dbt-ol` (openlineage-dbt) wraps `dbt build` and emits one event per model, with column-level lineage.
- A custom script (our replication) emits its own event with the OpenLineage client.
- Events go to **Marquez** (the reference server), **DataHub**, or Google **Dataplex**.

The key point: **lineage breaks at every hand-written hop unless it's declared**. That's why the replication
is contract-driven (exposure) and the DAG declares inlets/outlets.

## 5. Run it

```bash
make airflow-install                    # separate venv: airflow/.venv (Airflow 3.1, constraints file)
make airflow-test                       # airflow dags test ruta_pipeline: one full run, in-process, no scheduler
make airflow-up                         # airflow standalone → http://localhost:8080 (UI: Graph, Assets, logs)
make lineage                            # regenerate docs/diagrams/end-to-end-lineage.md
```
