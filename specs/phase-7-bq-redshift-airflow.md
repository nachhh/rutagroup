# Phase 7: BigQuery + Redshift patterns + Airflow DAG (⏱ 45 min)

## Goal
Be able to defend an architecture for a company with data in both Redshift and BigQuery, and show
end-to-end orchestration and lineage with Airflow.

## Concepts → `docs/07_bq_redshift_airflow.md`
| Pattern | How | Pros | Cons |
|---|---|---|---|
| 1. Batch replicate RS → BQ | `UNLOAD` (Parquet) → S3 → **Storage Transfer Service** → GCS → BQ load / BigLake external tables | Simple, cheap at batch cadence, BQ becomes the UDL hub | Egress cost (AWS → GCP), latency, two copies |
| 2. **BigQuery Data Transfer Service for Redshift** | Managed migration connector (schema + data) | Managed, good for migration | Migration-oriented, not ongoing CDC |
| 3. **BigQuery Omni** | BQ queries S3 data in place (BigLake on AWS) | No copy, single SQL surface | Region limits, cross-cloud joins need results moved, cost model |
| 4. CDC / streaming | Debezium/DMS → Kafka/Pub/Sub → BQ (Datastream doesn't read Redshift; source the OLTP instead) | Fresh data | Operational complexity |
| 5. Federation / virtualization | Trino/Starburst, or unify only at the semantic layer | No copies | Performance, governance spread |
| 6. Semantic-layer-only unification | Each warehouse stays; the metrics layer federates | Least movement | Cross-warehouse joins are hard |

Also covered: dialect and physical-design translation (DISTKEY/SORTKEY ↔ partition/cluster;
`SUPER`/PartiQL ↔ `JSON`/`STRUCT`; `VARCHAR(n)` ↔ `STRING`; `IDENTITY` ↔ none; `GETDATE()` ↔
`CURRENT_TIMESTAMP()`), metadata/lineage carried over via dbt (same models, two adapters,
cross-db macros), cost (egress, slots vs on-demand, RA3/Serverless RPUs), and governance
consistency across clouds.

## Files
| File | Content |
|---|---|
| `airflow/dags/ruta_pipeline.py` | Airflow 3.1. **Two DAGs linked by an Asset.** `ruta_pipeline` (@daily): task groups `extract_load` (load_ship_source, load_pay_source → bq_governance), `redshift` (ship_freshness gate → ship_build), `cross_cloud` (replicate_to_bq), `udl` (kg_codegen → governance_gate → udl_build). `ruta_semantic_checks` (schedule=[udl_marts Asset]): mf_validate → saved_queries (CSV) → agent_smoke_test (opt-in Param; exit 99 = skipped). `BashOperator` calling the underlying commands in the project venv (not `make`); Cosmos, OpenLineage, retries/timeouts explained in the module docstring. Data generation is NOT a task (sources are apps in production) |
| `scripts/lineage_e2e.py` → `docs/diagrams/end-to-end-lineage.md` | (added) End-to-end lineage generated from both manifests + semantic manifest + exposures; the cross-cloud edge from the `udl_replication` exposure ↔ `ship_replica` sources. `make lineage` |
| `docs/07_bq_redshift_airflow.md`, `docs/diagrams/pipeline-flow.md` | Patterns, dialect translation, DAG decisions table, lineage layers |
| Makefile | `airflow-install` (airflow/.venv + constraints), `airflow-test` (`airflow dags test`), `airflow-up` (standalone UI), `lineage`. `AIRFLOW_HOME=./airflow_home` (gitignored) |

## Optional hands-on (if time allows)
Run `stg_pay` models against Postgres too, using `adapter.dispatch` macros. This shows how far "same SQL, two
engines" goes before nested types break it, which is a good argument for *where* to unify.

## Acceptance criteria
- The DAG parses (`airflow dags list`). One full run succeeds, or is skipped if we're cutting time
- You can whiteboard the pattern you'd choose for Ruta and justify it in 2 minutes

## Implementation decisions (made while the user was away; to review)
1. One task per dbt project, not Cosmos (per-model tasks): simpler, `dbt build` already orders and skips on test failure.
2. Quality gates (`ship_freshness`, `governance_gate`) have `retries=0`. Freshness is enforced by default; the
   `enforce_freshness` run param downgrades it for demo runs (the synthetic data ends 2026-10-31, so it is stale).
3. Assets connect the DAGs (data-aware scheduling) instead of cron offsets or ExternalTaskSensor.
4. End-to-end lineage generated from metadata (`make lineage`) instead of installing Marquez/OpenLineage; the
   OpenLineage path is documented as the production answer.

## 🧭 Checkpoint
Which pattern would you defend, and why? (Answer in your own words; we refine it together.)

## 🧠 Quiz 7: 4 questions
