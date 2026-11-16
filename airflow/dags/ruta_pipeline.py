"""Ruta Group end-to-end pipeline: "Redshift" (Postgres) → BigQuery UDL → semantic layer → agent.

Two DAGs, linked by an ASSET (Airflow 3's data-aware scheduling, called "Datasets" in Airflow 2):

  ruta_pipeline (daily)                                               ruta_semantic_checks (runs when the UDL lands)
  ┌──────────────────────────────────────────────────────────────┐   ┌──────────────────────────────────────────┐
  │ extract_load: load_ship_source ─┐   load_pay_source → bq_gov  │   │ mf_validate → saved_queries               │
  │ redshift:     ship_freshness → ship_build ─► [ship_marts]     │   │            → agent_smoke_test (opt-in $)  │
  │ cross_cloud:  replicate_to_bq ─► [ship_replica]              │   └──────────────────────────────────────────┘
  │ udl:          kg_codegen → governance_gate → udl_build ─► [udl_marts] ═══ Asset triggers ═══►               │
  └──────────────────────────────────────────────────────────────┘

DESIGN DECISIONS (each one with its trade-off)
1. Airflow ORCHESTRATES, it doesn't compute. Every task shells out to the same commands we run by hand
   (`uv run dbt build`, `uv run python scripts/...`), executed in the PROJECT's venv. Airflow lives in its own
   venv (airflow/.venv): Airflow and dbt pin conflicting deps, so never install them together.
   We call the underlying commands, not `make`: one task = one command = one retry unit, and logs map 1:1.
2. Task granularity = one task per dbt PROJECT (`dbt build` runs models+tests in DAG order and skips downstream
   of a failed test). Alternative: **Astronomer Cosmos** renders every dbt model/test as its own Airflow task
   (DbtTaskGroup). Pros: per-model retries and visibility. Cons: hundreds of tasks, scheduler load, slower.
   Rule of thumb: Cosmos when teams need per-model ownership/alerts in Airflow; one-task-per-project otherwise.
3. Quality gates FAIL FAST before spending money: source freshness before the Redshift build, the governance
   check (contracts/PII/ontology/semantic links, rules R1–R7) before the BigQuery build. Gates have retries=0
   (deterministic failures don't heal). A run can downgrade freshness via the `enforce_freshness` param.
4. ASSETS make cross-DAG dependencies explicit: `outlets=[UDL_MARTS]` on udl_build triggers ruta_semantic_checks
   whenever the UDL is rebuilt, instead of guessing a cron time ("run at 7:00 and hope the UDL finished").
   The Airflow UI's Assets view shows producer → asset → consumer: that's the cross-DAG lineage graph.
5. LINEAGE end to end: dbt gives model-level lineage inside each project (manifest.json + exposures); the
   cross-cloud hop (replicate script) is invisible to dbt, so we declare it with inlets/outlets here. In
   production: apache-airflow-providers-openlineage + `dbt-ol` (openlineage-dbt) emit OpenLineage events to
   Marquez / DataHub / Dataplex, stitching Postgres tables → BQ tables → metrics → MCP exposure in one graph.
6. Idempotent tasks: every load truncates-and-reloads, dbt builds are rerunnable, bq_governance re-applies policy
   tags that a raw reload drops. Safe to retry and to backfill.
7. Retries with backoff, execution_timeout per task, max_active_runs=1 (two runs writing the same tables = races),
   catchup=False (this pipeline rebuilds state; it isn't a per-day partition backfill).
"""

from datetime import datetime, timedelta
from pathlib import Path

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG, Asset, Param, TaskGroup

ROOT = Path(__file__).resolve().parents[2]  # repo root (airflow/dags/ → ../../)

# Every task: load .env (GCP project, PG creds; gitignored), point dbt at the repo's profiles.yml, and drop the
# Airflow venv so `uv run` uses the project's .venv.
PRELUDE = "set -euo pipefail; set -a; source .env; set +a; export DBT_PROFILES_DIR=$PWD; unset VIRTUAL_ENV; "


def sh(task_id: str, cmd: str, **kw) -> BashOperator:
    return BashOperator(task_id=task_id, bash_command=PRELUDE + cmd, cwd=str(ROOT), **kw)


# Assets = logical data products, named by URI. Names are identifiers: Airflow doesn't connect to them.
SHIP_RAW = Asset("postgres://localhost:5432/ruta/raw_ship")
PAY_RAW = Asset("bigquery://rutagroup/raw_pay")
SHIP_MARTS = Asset("postgres://localhost:5432/ruta/marts")            # RutaShip public marts ("Redshift")
SHIP_REPLICA = Asset("bigquery://rutagroup/ship_replica")              # the cross-cloud copy
UDL_MARTS = Asset("bigquery://rutagroup/udl_marts")                    # conformed UDL + semantic models
UDL_KG = Asset("bigquery://rutagroup/udl_kg")                          # knowledge graph

default_args = {
    "owner": "data-platform",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "execution_timeout": timedelta(minutes=30),
}

with DAG(
    dag_id="ruta_pipeline",
    description="Redshift(PG) → BigQuery UDL: load, build, replicate, govern, build UDL",
    schedule="@daily",
    start_date=datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["ruta", "udl", "dbt"],
    doc_md=__doc__,
    # Run-level switch: a demo/backfill run on old data can downgrade the freshness gate to a warning, explicitly
    # and visibly in the run's conf (never by editing the DAG). Default = enforce.
    params={"enforce_freshness": Param(True, type="boolean", description="Fail the run on stale sources")},
) as pipeline:

    with TaskGroup("extract_load", tooltip="Sources → raw layers of each warehouse"):
        # In production these are the apps' replicas/CDC (DMS, Fivetran, Datastream...). Here: deterministic files.
        load_ship = sh("load_ship_source", "uv run python scripts/load_postgres.py", outlets=[SHIP_RAW])
        load_pay = sh("load_pay_source", "uv run python scripts/load_bigquery.py", outlets=[PAY_RAW])
        # A raw reload recreates tables and drops column policy tags / row policies → re-apply (idempotent).
        bq_gov = sh("bq_governance", "uv run python scripts/setup_bq_governance.py apply")
        load_pay >> bq_gov

    with TaskGroup("redshift", tooltip="RutaShip dbt project on Postgres (playing Redshift)"):
        # Gates get retries=0: a stale source or a policy violation won't fix itself in 2 minutes.
        ship_fresh = sh(
            "ship_freshness",
            'cd dbt/ruta_ship && { uv run dbt source freshness || [ "{{ params.enforce_freshness }}" = "False" ]; }',
            inlets=[SHIP_RAW], retries=0,
        )
        ship_build = sh("ship_build", "cd dbt/ruta_ship && uv run dbt build", outlets=[SHIP_MARTS])
        ship_fresh >> ship_build

    with TaskGroup("cross_cloud", tooltip="UNLOAD → S3 → GCS → BQ, simulated"):
        # dbt can't see this hop: inlets/outlets declare it so lineage stays connected across clouds.
        replicate = sh(
            "replicate_to_bq",
            "cd dbt/ruta_ship && uv run dbt parse -q && cd ../.. && uv run python scripts/replicate_ship_to_bq.py",
            inlets=[SHIP_MARTS], outlets=[SHIP_REPLICA],
        )

    with TaskGroup("udl", tooltip="BigQuery UDL: codegen, governance gate, dbt build"):
        kg_codegen = sh("kg_codegen", "uv run python scripts/generate_kg_models.py")  # ontology → kg_* models
        gate = sh(
            "governance_gate",  # R1–R7 over both manifests; fails the run BEFORE any BigQuery spend
            "(cd dbt/ruta_ship && uv run dbt parse -q) && (cd dbt/ruta_udl && uv run dbt parse -q) "
            "&& uv run python scripts/check_governance.py",
            retries=0,
        )
        udl_build = sh(
            "udl_build", "cd dbt/ruta_udl && uv run dbt build",
            inlets=[SHIP_REPLICA, PAY_RAW], outlets=[UDL_MARTS, UDL_KG],
        )
        kg_codegen >> gate >> udl_build

    load_ship >> ship_fresh
    ship_build >> replicate
    [replicate, bq_gov] >> kg_codegen


with DAG(
    dag_id="ruta_semantic_checks",
    description="Runs whenever the UDL is rebuilt: validate the semantic layer, refresh saved queries, agent smoke test",
    schedule=[UDL_MARTS],  # data-aware: triggered by the Asset, not by the clock
    start_date=datetime(2026, 11, 1),
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    params={"run_agent": Param(False, type="boolean", description="Run the LLM smoke test (costs ~$0.003)")},
    tags=["ruta", "semantic-layer", "agent"],
) as semantic_checks:

    mf_validate = sh("mf_validate", "cd dbt/ruta_udl && uv run dbt parse -q && uv run mf validate-configs",
                     inlets=[UDL_MARTS])
    # Saved queries = the governed answers to the business question. Here they're printed + exported to CSV;
    # with dbt Platform, saved-query EXPORTS would materialize them as tables for BI.
    saved_queries = sh(
        "saved_queries",
        "mkdir -p airflow_home/exports && cd dbt/ruta_udl && "
        "uv run mf query --saved-query multi_product_revenue_by_region --csv ../../airflow_home/exports/revenue.csv && "
        "uv run mf query --saved-query churn_by_segment --csv ../../airflow_home/exports/churn.csv",
    )
    # Opt-in: exit code 99 marks the task SKIPPED (not failed) when run_agent is false.
    agent_smoke = sh(
        "agent_smoke_test",
        '[ "{{ params.run_agent }}" = "True" ] || exit 99; '
        'uv run python agent/ask.py "Do customers using both products churn less? Answer in 2 lines."',
        skip_on_exit_code=99,
    )
    mf_validate >> saved_queries >> agent_smoke
