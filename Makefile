# Ruta Group playground. Run `make help`.
SHELL := /bin/bash
include .env
export
export DBT_PROFILES_DIR := $(CURDIR)
DBT := uv run dbt

.PHONY: help up down data load load-pg load-bq deps ship udl debug clean

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
udl:             ## dbt build UDL (BigQuery)
	cd dbt/ruta_udl && $(DBT) build

clean:
	cd dbt/ruta_ship && $(DBT) clean
	cd dbt/ruta_udl && $(DBT) clean
