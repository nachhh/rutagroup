# Pipeline flow (Airflow DAGs, Phase 7)

Two DAGs in [airflow/dags/ruta_pipeline.py](../../airflow/dags/ruta_pipeline.py), linked by an Asset (data-aware
scheduling). Diamonds are quality gates (retries=0, fail before spending). Table-level lineage:
[end-to-end-lineage.md](end-to-end-lineage.md).

```mermaid
flowchart LR
  subgraph P[ruta_pipeline · @daily]
    subgraph EL[extract_load]
      LS[load_ship_source<br/>CSV → PG raw_ship]
      LP[load_pay_source<br/>JSONL → BQ raw_pay] --> BG[bq_governance<br/>re-apply policy tags]
    end
    subgraph RS[redshift]
      F{ship_freshness} --> SB[ship_build<br/>dbt build ruta_ship]
    end
    subgraph CC[cross_cloud]
      R[replicate_to_bq<br/>UNLOAD→S3→GCS→BQ sim]
    end
    subgraph U[udl]
      K[kg_codegen<br/>ontology → kg models] --> G{governance_gate<br/>R1–R7} --> UB[udl_build<br/>dbt build ruta_udl]
    end
    LS --> F
    SB -->|Asset ship_marts| R
    R -->|Asset ship_replica| K
    BG --> K
  end
  UB ==>|Asset udl_marts triggers| S
  subgraph S[ruta_semantic_checks · schedule=udl_marts]
    MV[mf_validate] --> SQ[saved_queries<br/>CSV exports] --> AG[agent_smoke_test<br/>opt-in param, else skipped]
  end
```
