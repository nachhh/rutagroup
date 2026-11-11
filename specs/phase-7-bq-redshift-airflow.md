# Phase 7: BigQuery + Redshift patterns + Airflow DAG (⏱ 45 min)

## Goal
Be able to defend an architecture for a company with data in both Redshift and BigQuery, and show
end-to-end orchestration and lineage with Airflow.

## Concepts → `docs/07_bq_redshift.md`
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
| `airflow/dags/ruta_pipeline.py` | Airflow 3 DAG: `generate_data → load_pg → dbt_build_ship → replicate_to_bq → dbt_build_udl → governance_check → mf_saved_queries`. `BashOperator`, with comments on **Cosmos** (renders dbt models as tasks), Datasets/Assets for data-aware scheduling, retries/SLAs, and OpenLineage |
| `airflow/README` section in the spec | How to run: separate uv venv, `airflow standalone`, `AIRFLOW_HOME=./airflow_home` (gitignored) |

## Optional hands-on (if time allows)
Run `stg_pay` models against Postgres too, using `adapter.dispatch` macros. This shows how far "same SQL, two
engines" goes before nested types break it, which is a good argument for *where* to unify.

## Acceptance criteria
- The DAG parses (`airflow dags list`). One full run succeeds, or is skipped if we're cutting time
- You can whiteboard the pattern you'd choose for Ruta and justify it in 2 minutes

## 🧭 Checkpoint
Which pattern would you defend, and why? (Answer in your own words; we refine it together.)

## 🧠 Quiz 7: 4 questions
