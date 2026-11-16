# Ruta Group playground. Run `make help`.
SHELL := /bin/bash
include .env
export
export DBT_PROFILES_DIR := $(CURDIR)
DBT := uv run dbt

.PHONY: help up down data load load-pg load-bq deps ship udl debug clean day2 snapshot freshness govern pg-roles bq-governance replicate ontology eval-er semantic mf ask lineage airflow-install airflow-test airflow-up

help:            ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

up:              ## start Postgres ("Redshift")
	docker compose up -d --wait
down:            ## stop Postgres
	docker compose down

data:            ## generate synthetic data into ./data
	uv run python scripts/generate_data.py
load: load-pg load-bq  ## load both warehouses
load-pg:         ## RutaShip CSV → Postgres raw_ship
	uv run python scripts/load_postgres.py
load-bq:         ## RutaPay JSONL → BigQuery raw_pay
	uv run python scripts/load_bigquery.py

deps:            ## install dbt packages in both projects
	cd dbt/ruta_ship && $(DBT) deps
	cd dbt/ruta_udl && $(DBT) deps
debug:           ## dbt debug in both projects
	cd dbt/ruta_ship && $(DBT) debug
	cd dbt/ruta_udl && $(DBT) debug

ship:            ## dbt build RutaShip (Postgres)
	cd dbt/ruta_ship && $(DBT) build
snapshot:        ## dbt snapshot RutaShip (SCD2 capture)
	cd dbt/ruta_ship && $(DBT) snapshot
freshness:       ## source freshness checks, both projects
	cd dbt/ruta_ship && $(DBT) source freshness || true
	cd dbt/ruta_udl && $(DBT) source freshness || true
day2:            ## simulate day-2 changes in RutaShip source (incrementals, snapshot, late data)
	uv run python scripts/day2_ship.py
udl:             ## dbt build UDL (BigQuery)
	cd dbt/ruta_udl && $(DBT) build

replicate:       ## RutaShip PUBLIC marts (Postgres) → BigQuery ship_replica (simulated UNLOAD → S3 → GCS → BQ)
	cd dbt/ruta_ship && $(DBT) parse --quiet
	uv run python scripts/replicate_ship_to_bq.py
ontology:        ## generate KG dbt models (kg_nodes, kg_edges) from ontology/ruta_ontology.yml
	uv run python scripts/generate_kg_models.py
semantic:        ## parse + validate the semantic layer (MetricFlow) and run the two saved queries
	cd dbt/ruta_udl && $(DBT) parse -q && uv run mf validate-configs
	cd dbt/ruta_udl && uv run mf query --saved-query multi_product_revenue_by_region --order metric_time__quarter
	cd dbt/ruta_udl && uv run mf query --saved-query churn_by_segment --order metric_time__quarter
mf:              ## ad-hoc MetricFlow query, e.g. make mf Q="--metrics total_revenue --group-by customer__region"
	cd dbt/ruta_udl && $(DBT) parse -q && uv run mf query $(Q)
ask:             ## NL question -> agent -> MCP server -> semantic layer / KG, e.g. make ask Q="Do multi-product customers churn less?"
	cd dbt/ruta_udl && $(DBT) parse -q
	uv run python agent/ask.py "$(Q)"
eval-er:         ## score entity resolution against the generator's ground truth (precision / recall)
	uv run python scripts/eval_entity_resolution.py
pg-roles:        ## create least-privilege roles in Postgres (analyst, pii_reader, pii_reader_iberia)
	docker exec -i ruta_pg psql -U $(PG_USER) -d $(PG_DB) -q < scripts/setup_pg_roles.sql
govern:          ## governance CI gate: dbt parse both projects, then policy checks on manifest.json
	cd dbt/ruta_ship && $(DBT) parse --quiet
	cd dbt/ruta_udl && $(DBT) parse --quiet
	uv run python scripts/check_governance.py
bq-governance:   ## BigQuery: policy tag + data masking + row access policy + authorized view (free tier)
	uv run python scripts/setup_bq_governance.py apply

clean:
	cd dbt/ruta_ship && $(DBT) clean
	cd dbt/ruta_udl && $(DBT) clean

# --- Phase 7: Airflow (own venv: Airflow and dbt pin conflicting deps) + end-to-end lineage ---
AIRFLOW_ENV := AIRFLOW_HOME=$(CURDIR)/airflow_home AIRFLOW__CORE__DAGS_FOLDER=$(CURDIR)/airflow/dags AIRFLOW__CORE__LOAD_EXAMPLES=False
AIRFLOW := $(AIRFLOW_ENV) airflow/.venv/bin/airflow
lineage:         ## generate docs/diagrams/end-to-end-lineage.md from both manifests + semantic manifest + exposures
	cd dbt/ruta_ship && $(DBT) parse -q
	cd dbt/ruta_udl && $(DBT) parse -q
	uv run python scripts/lineage_e2e.py
airflow-install: ## Airflow 3.1 in airflow/.venv (pinned with the official constraints file)
	uv venv -q airflow/.venv --python 3.12
	VIRTUAL_ENV=airflow/.venv uv pip install -q "apache-airflow==3.1.0" --constraint https://raw.githubusercontent.com/apache/airflow/constraints-3.1.0/constraints-3.12.txt
	$(AIRFLOW) db migrate
airflow-test:    ## one full in-process run of ruta_pipeline (no scheduler); demo data is old → freshness downgraded
	$(AIRFLOW) dags reserialize
	$(AIRFLOW) dags test ruta_pipeline -c '{"enforce_freshness": false}'
	$(AIRFLOW) dags test ruta_semantic_checks
airflow-up:      ## Airflow UI + scheduler at http://localhost:8080 (credentials printed on first start)
	$(AIRFLOW) standalone
