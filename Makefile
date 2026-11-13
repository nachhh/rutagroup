# Ruta Group playground. Run `make help`.
SHELL := /bin/bash
include .env
export
export DBT_PROFILES_DIR := $(CURDIR)
DBT := uv run dbt

.PHONY: help up down data load load-pg load-bq deps ship udl debug clean day2 snapshot freshness govern pg-roles bq-governance

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
