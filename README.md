# Ruta Group: Unified Data Layer + Semantic Layer playground

A hands-on playground for **semantic layers (dbt Semantic Layer / MetricFlow), Unified Data
Layers, ontologies and knowledge graphs, governance-as-code, natural-language querying, and
combining BigQuery with Redshift**, built on a small made-up multi-product company.

How the project is run:
- **Spec-driven.** Each phase has a spec in [specs/](specs/).
- **Checkpoints and quizzes.** Phases include 🧭 decision checkpoints and 🧠 quizzes.
- **Docs.** Concept notes are in [docs/](docs/), diagrams in [docs/diagrams/](docs/diagrams/), and a bilingual
  [glossary](docs/glossary.md).
- **Time budget.** Two sessions of 3–4 h each.

---

## 1. The business

**Ruta Group** is a logistics-tech holding that grew by acquisition. It builds connected workflows
that make shipping, carrier handoffs and payments a single customer experience. Its two products
run on **different clouds**:

| Product | What it does | Warehouse | Here |
|---|---|---|---|
| **RutaShip** | B2B freight marketplace: shippers book shipments, carriers move them, tracking events flow back | **Amazon Redshift** (legacy AWS stack) | **Postgres 16** in Docker (Redshift is a Postgres 8 fork, so the dialect feels similar) |
| **RutaPay** | Invoicing, subscriptions and payments for the same SMB customers | **BigQuery** (acquired GCP startup) | **BigQuery Sandbox** (real BQ, free, no card) |

The **Unified Data Layer (UDL)** lives in **BigQuery**. RutaShip data is replicated from
"Redshift" into BQ. This simulates `UNLOAD → S3 → GCS → BQ`.

**The question nobody can answer consistently:**
> "How much revenue do we make from customers who use **both** products, by region and plan, and
> do they churn less than single-product customers?"

Why it's hard, and what each difficulty teaches:

| Difficulty | Concept practiced |
|---|---|
| The same company has different IDs (`shipper_id` vs `account_id`), and match keys are messy | Entity resolution, canonical **Customer** entity, **ontology** |
| "Revenue" means booking fees in Ship and MRR + fees in Pay | One governed metric definition in the **semantic layer** |
| Different grains, late payments, plan changes over time | **Fact/dim** modeling, **SCD2**, incremental models |
| RutaPay raw data is nested JSON (webhooks, line-item arrays) | **BigQuery** STRUCT/ARRAY/UNNEST/JSON functions |
| PII (emails, tax IDs) | **Governance as code**: contracts, access, meta tags, masking, CI checks |
| Execs and agents ask in plain language | **NL → metric query** through the semantic layer, exposed via **MCP** |
| Two clouds, two warehouses | **BigQuery + Redshift** integration patterns, orchestrated by **Airflow** |

---

## 2. Architecture (summary)

```
Postgres ("Redshift")                         BigQuery Sandbox
┌───────────────────────────┐   replicate    ┌──────────────────────────────────────────────┐
│ raw_ship.*                │   (Parquet,    │ raw_pay.*  (nested JSON, ARRAY<STRUCT>)      │
│ dbt project: ruta_ship    │──"UNLOAD"────▶ │ ship_replica.*                               │
│  staging → marts          │   sim)         │ dbt project: ruta_udl                        │
│  incremental, snapshot,   │                │  stg_pay (UNNEST/JSON) → int_customer_xwalk  │
│  contracts, grants        │                │  → conformed dims + facts → semantic models  │
└───────────────────────────┘                │  → metrics (MetricFlow) → kg_nodes/kg_edges  │
                                             └───────────────┬──────────────────────────────┘
         Airflow DAG orchestrates all of it                  │ MCP server (metrics tools)
                                                             ▼
                                                   tiny NL agent (Gemini / Haiku)
```

Full Mermaid diagrams are in [docs/diagrams/](docs/diagrams/):
[architecture](docs/diagrams/architecture.md) ·
[source ERD](docs/diagrams/source-erd.md) ·
[pipeline flow](docs/diagrams/pipeline-flow.md) ·
[ontology (draft)](docs/diagrams/ontology.md) ·
[NL agent sequence](docs/diagrams/nl-agent-sequence.md)

**Why two dbt projects?** A dbt invocation targets one adapter. RutaShip on Postgres
(Redshift) and the UDL on BigQuery are two projects: the upstream project's public models
become the downstream project's sources. This is a hand-rolled version of the **dbt Mesh**
pattern. In dbt Cloud, cross-project `ref` handles this.

**Why split work between engines?** The BQ Sandbox has no DML, so incremental `MERGE` and
dbt snapshots go on the Postgres side. On the BQ side we build SCD2 from a change log with window
functions. That gives us two ways to do SCD2, which is a good interview talking point.

---

## 3. Roadmap

Weak-point focus: **Phases 4–6 are protected**. Phases 1–3 are tight refreshers.

| # | Phase | ⏱ | Spec |
|---|---|---|---|
| **Session 1** ||||
| 0 | Setup: Docker PG, uv, BQ Sandbox auth, data generator, both dbt projects | 45 m | [phase-0](specs/phase-0-setup.md) |
| 1 | Data modeling refresher: grain, fact types, conformed dims, SCD, bus matrix | 40 m | [phase-1](specs/phase-1-data-modeling.md) |
| 2 | dbt refresher on both engines: materializations, incremental, snapshots, tests, BQ nested SQL | 1.5 h | [phase-2](specs/phase-2-dbt.md) |
| 3 | Governance → code: contracts, access, groups, PII meta, masking, grants, CI check | 45 m | [phase-3](specs/phase-3-governance.md) |
| **Session 2** ||||
| 4 | UDL: replication, entity resolution, ontology, knowledge graph | 1 h | [phase-4](specs/phase-4-udl-ontology-kg.md) |
| 5 | **dbt Semantic Layer / MetricFlow** (centerpiece) | 1.25 h | [phase-5](specs/phase-5-semantic-layer.md) |
| 6 | NL querying + MCP server + tiny agent | 45 m | [phase-6](specs/phase-6-nl-mcp-agent.md) |
| 7 | BigQuery + Redshift patterns + Airflow DAG (end-to-end lineage) | 45 m | [phase-7](specs/phase-7-bq-redshift-airflow.md) |
| 8 | Wrap-up: cheat sheet, glossary pass, mock Q&A | 30 m | [phase-8](specs/phase-8-wrap-up.md) |

Total ≈ 7.75 h. That is the top of the budget. If we run behind, cut in this order: Phase 7 Airflow
(keep the DAG file, skip running it locally) → Phase 1 depth → Phase 2 extras (microbatch, `dbt_expectations`).

## 4. Progress

- [ ] Phase 0: Setup
- [ ] Phase 1: Data modeling
- [ ] Phase 2: dbt refresher
- [ ] Phase 3: Governance → code
- [ ] Phase 4: UDL / ontology / KG
- [ ] Phase 5: Semantic Layer / MetricFlow
- [ ] Phase 6: NL + MCP agent
- [ ] Phase 7: BigQuery + Redshift + Airflow
- [ ] Phase 8: Wrap-up

## 5. Repo layout (target)

```
docker-compose.yml  Makefile  pyproject.toml  .env.example  profiles.example.yml
scripts/            generate_data.py, load_postgres.py, load_bigquery.py, replicate_ship_to_bq.py
dbt/ruta_ship/      dbt project on Postgres ("Redshift")
dbt/ruta_udl/       dbt project on BigQuery (UDL + semantic layer + KG)
ontology/           ruta_ontology.yml
mcp/                metrics MCP server (wraps MetricFlow)
agent/              tiny NL agent (MCP client + LLM)
airflow/dags/       ruta_pipeline.py
specs/              one spec per phase
docs/               concept notes, glossary.md, diagrams/
```
