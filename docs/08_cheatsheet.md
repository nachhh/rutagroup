# 08: Cheatsheet

One answer per core topic: what to say (2–3 sentences), where this repo implements it, and the trade-off to mention.
Spec: [phase-8](../specs/phase-8-wrap-up.md). Terms: [glossary](glossary.md).

**One-liner:** the UDL is the data, the semantic layer is the math, the ontology is the dictionary, the knowledge graph
is the map, and the context layer is the agent's briefing.

---

### 1. Semantic layer
**Say:** Metrics, dimensions, entities and join paths defined **once** in code, then compiled into SQL for every consumer
(BI, notebooks, APIs, agents). It removes whole bug classes (fan-out joins, averages of ratios, SCD2 as-of joins) and
makes every number traceable to one definition.
**Here:** [models/semantic/](../dbt/ruta_udl/models/semantic/) + semantic models in `_udl.yml`; ratio, cumulative,
conversion and derived metrics; SCD2 `dim_customer` with `validity_params`; saved queries. [docs/05](05_semantic_layer.md).
**Trade-off:** another layer to own and test; complex logic (entity resolution, survivorship) still belongs in dbt
models. Rule: *transformations in dbt, aggregations in the semantic layer*.

### 2. UDL / context layer
**Say:** The UDL integrates product-centric data into **entity-centric**, conformed, governed data products: one
customer across products, unified revenue in one currency. The context layer is what an agent needs on top of that to
act correctly: metric catalog, ontology synonyms, graph neighbourhoods, governance rules, served through tools.
**Here:** entity resolution → crosswalk → `dim_customer` (SCD2 timeline merge), `fct_revenue`, `fct_customer_monthly`;
persisted **key registry** + `customer_key_aliases` so keys survive re-matching. Context = MCP tool descriptions +
metric descriptions + ontology. [docs/04](04_udl_ontology.md).
**Trade-off:** entity resolution is never perfect (here precision 1.000, recall 0.974): stewardship (review queue,
decisions as reviewed PRs) is part of the product, not a one-off.

### 3. Ontology / knowledge graph
**Say:** The ontology declares classes, relations, synonyms and how each maps to a data product; the KG is the ontology
populated with instances (nodes and edges). Agents use it for questions that are paths ("customers sharing a carrier
with churned customers"), which are awkward as metrics.
**Here:** [ontology/ruta_ontology.yml](../ontology/ruta_ontology.yml) → generated `kg_nodes` / `kg_edges` in BigQuery
(`make ontology`); each class links to a semantic entity, checked in CI (rule R7).
**Trade-off:** YAML + property graph tables instead of RDF/OWL/SPARQL: simple and warehouse-native, but no formal
reasoning. A graph database is worth it only when traversals get deep or interactive.

### 4. dbt Semantic Layer / MetricFlow vs LookML / Cube
**Say:** MetricFlow is the open-source engine (YAML → SQL); the dbt Semantic Layer is the hosted service around it
(JDBC/GraphQL APIs, caching, BI integrations): headless BI. LookML ties the semantics to Looker; Cube is headless with
strong pre-aggregations for embedded analytics; Snowflake and Databricks now offer warehouse-native metric views.
**Here:** `mf query` locally, saved queries, the agent calls MetricFlow through MCP. OSI document written by dbt 1.12.
**Trade-off:** dbt SL keeps metrics next to the models and lineage, but its APIs need the hosted plan; Cube is better for
low-latency embedded use; warehouse-native views avoid a tool but lock definitions to one engine.

### 5. NL querying / agents
**Say:** Text-to-SQL gives plausible but inconsistent numbers on a multi-product model; **text-to-metric-query** lets the
LLM pick governed metrics and dimensions, and the semantic layer writes the SQL. Guardrails live in the server and the
warehouse, never only in the prompt.
**Here:** [agent/ask.py](../agent/ask.py) (Claude Haiku) → MCP → [mcp_server/metrics_server.py](../mcp_server/metrics_server.py):
metric allowlist, allowlisted KG predicates, parameterized SQL, row cap, 1 GB bytes cap, returns the exact `mf` command.
**Trade-off:** less flexible than free SQL (only modeled metrics); most failures are **context** failures (a missing
fact in a tool description), fixed by improving context, not the model.

### 6. BigQuery + Redshift
**Say:** The UDL lives where it's consumed: BigQuery (spiky agent workloads, native nested JSON, the Pay product already
there). What crosses clouds is **contracted public marts**, by **batch replication** (UNLOAD Parquet → S3 → GCS → BQ
load, `WRITE_TRUNCATE`, idempotent). PII is minimized before crossing; governance is reapplied on arrival.
**Here:** [replicate_ship_to_bq.py](../scripts/replicate_ship_to_bq.py) reads the `udl_replication` exposure;
`ship_replica` sources with freshness. Dialect map (DISTKEY → none, SORTKEY → partition + cluster). [docs/07](07_bq_redshift_airflow.md).
**Trade-off:** latency, egress and two governance planes. Change course for real-time (CDC from OLTP), egress at huge
volume (BigQuery Omni / federation), or residency rules.

### 7. Governance as code
**Say:** Every policy becomes an artifact a machine checks: owners (groups), interfaces (access + contracts + versions),
classification (column meta), masking, and a CI gate over `manifest.json` that blocks the PR.
**Here:** [check_governance.py](../scripts/check_governance.py) rules R1–R7 (`make govern`); PII: hash at source
(`email_sha256`), BQ policy tags + dynamic masking, PG/Redshift RLS and owner-rights views; model versions with
deprecation dates. [docs/03](03_governance.md).
**Trade-off:** gates slow teams if rules are noisy; start with few, high-value rules (public = owned + contracted +
no raw PII) and grow. Contracts in BQ/Redshift are informational: tests are the real enforcement.

### 8. Data modeling
**Say:** Grain first ("one row per ___"). Facts: transaction, periodic snapshot (semi-additive MRR), accumulating
snapshot, factless. Dimensions: conformed, role-playing dates, SCD type chosen **per attribute** (history need vs
governance cost).
**Here:** [docs/01](01_modeling.md); SCD2 via dbt snapshot (polling) and via change log + `LEAD()` (log-based);
`fct_shipments` incremental merge watching **both** inputs (shipments + events).
**Trade-off:** SCD2 everywhere is expensive and complicates GDPR erasure; keep PII SCD1. Incremental models need
change detection on every input plus reconciliation tests.

### 9. Airflow
**Say:** Airflow orchestrates; dbt transforms. Tasks are idempotent, quality gates fail fast before spending money,
and cross-DAG dependencies use **Assets** (data-aware scheduling) instead of cron offsets or sensors.
**Here:** [ruta_pipeline.py](../airflow/dags/ruta_pipeline.py): freshness gate → Redshift build → replicate → governance
gate → UDL build → Asset → semantic checks. `max_active_runs=1`, `catchup=False`. Generated end-to-end lineage.
**Trade-off:** one task per dbt project (simple, dbt orders and skips) vs Cosmos (per-model tasks, retries per model,
heavier DAGs). Production lineage = OpenLineage (observed, column-level, with history).

### 10. Cost / performance optimization
**Say:** In BigQuery you pay for **bytes of referenced columns** after pruning: partition by time, cluster by filter and
join keys, never `SELECT *`, cap queries. Isolate unpredictable workloads (agents) with separate projects, quotas or
reservations. Model to reduce work: incrementals, pre-aggregated marts, semantic-layer caching.
**Here:** `maximum_bytes_billed: 1 GB` in the profile; `fct_invoice_lines` daily partitions + cluster with
`insert_overwrite`; `fct_udl_shipments` monthly partitions; modeled Parquet to keep egress small.
**Trade-off:** on-demand is cheap at low, spiky volume but unbounded; editions/reservations give predictable cost but
idle capacity. Over-partitioning (tiny partitions) hurts.

### 11. Tech leadership
**Say:** Ship a **thin vertical slice** first (one source → UDL → one governed metric → one consumer), then widen.
Make the standard path the easiest (paved road: templates, CI gates, `make` targets). Domains own their data products;
the UDL team owns integration, shared entities and the platform; governance is federated but checked centrally.
**Here:** specs written before code (design docs), 🧭 decisions recorded with options and consequences (ADRs), CI gate,
public contracts as the team boundary (dbt Mesh).
**Trade-off:** central team = consistency but a bottleneck; full mesh = autonomy but drift. Mix: platform + standards
centrally, ownership in domains. First 90 days: map consumers and pain, pick one high-value use case, deliver it end to
end, then publish the paved road.

---

## 2-minute walkthrough

> "Ruta is a playground for a unified data layer across two products. RutaShip, a shipping product, runs on Postgres
> playing Redshift; RutaPay, a billing product, is native BigQuery with nested webhook JSON.
>
> Each product has its own dbt project with public, contracted marts: that's the team boundary. RutaShip's marts are
> replicated to BigQuery in batch, driven by an exposure, so what's copied is exactly what's declared.
>
> In BigQuery, entity resolution matches shippers to billing accounts with blocking, a tax-id veto and a stewardship
> queue, then a persisted key registry gives each real customer a stable key. On top sit conformed marts: an SCD2
> customer that merges both products' histories, unified revenue in euros, and monthly customer snapshots.
>
> MetricFlow defines the metrics once: revenue, churn, take rate, ship-to-pay conversion. An ontology describes what
> things mean and generates a knowledge graph. An AI agent answers questions through an MCP server that exposes only
> governed metrics and graph paths, with guardrails in the server.
>
> Governance is code: owners, contracts, PII classification and masking, checked by a CI gate. Airflow runs it end to
> end with quality gates and asset-triggered checks, and lineage is generated across both clouds.
>
> The main trade-offs I'd discuss: batch copy vs federation, metrics in a semantic layer vs in BI, and how much
> history to keep versus what governance costs."
