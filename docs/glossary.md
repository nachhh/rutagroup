# Glossary (EN ↔ ES)

Grows phase by phase. Format: **English** · *Español*: one-line definition.

| English | Español | Definition |
|---|---|---|
| Grain | Granularidad | What exactly one row of a table represents |
| Fact table | Tabla de hechos | Measurable events/processes at a declared grain |
| Dimension | Dimensión | Descriptive context used to filter and group facts |
| Conformed dimension | Dimensión conformada | A dimension shared with identical meaning across facts/processes |
| Slowly Changing Dimension (SCD) | Dimensión de cambio lento | A strategy for handling attribute changes over time (type 2 = keep history) |
| Semantic layer | Capa semántica | Governed definitions of metrics, dimensions and entities, compiled to SQL |
| Unified Data Layer (UDL) | Capa de datos unificada | An entity-centric integration layer across products/sources |
| Context layer | Capa de contexto | Metadata and meaning supplied to humans/agents to ground answers |
| Ontology | Ontología | A formal model of concepts, their relationships and their constraints |
| Knowledge graph | Grafo de conocimiento | Instance data organized as nodes and edges following an ontology |
| Entity resolution | Resolución de entidades | Determining which records refer to the same real-world entity |
| Data contract | Contrato de datos | An enforced schema/semantics promise of a data product to its consumers |
| Lineage | Linaje | The traceable path of data from source to consumption |
| Application Default Credentials (ADC) | Credenciales predeterminadas de aplicación | Google auth that picks up your gcloud user token, so no key files are needed |
| dbt profile / target | Perfil / destino de dbt | Connection config outside the repo; the target selects the environment (dev/prod) |
| DISTKEY / SORTKEY (Redshift) | Clave de distribución / de ordenamiento | How rows are spread across nodes / ordered on disk for pruning |
| Sandbox (BigQuery) | Sandbox / entorno de pruebas | Free BQ without billing: no DML, no streaming, 60-day table expiry |
| maximum_bytes_billed | Máximo de bytes facturados | Per-query cap: a BQ query that would scan more fails instead of billing |
| insert_overwrite (dbt/BQ) | Sobrescritura de particiones | Incremental strategy that replaces whole partitions instead of merging rows |
| Fusion engine (dbt v2) | Motor Fusion | dbt's Rust rewrite: faster parsing, static analysis, ADBC adapters |
| Transaction fact | Hecho transaccional | One row per business event; insert-only |
| Periodic snapshot | Instantánea periódica | One row per entity per period (e.g. customer × month) |
| Accumulating snapshot | Instantánea acumulativa | One row per process instance; milestone columns filled as they happen |
| Factless fact | Hecho sin medidas | Records an event/coverage with no numeric measure; you count rows |
| Additive / semi-additive / non-additive | Aditiva / semiaditiva / no aditiva | Summable across all dims / all but time / never (ratios) |
| Role-playing dimension | Dimensión de rol múltiple | Same dimension used in several roles (booked date, due date) |
| Degenerate dimension | Dimensión degenerada | An identifier stored on the fact with no dimension table (invoice number) |
| Junk dimension | Dimensión basura | Bundles low-cardinality flags into one small dimension |
| Surrogate key | Clave subrogada | Warehouse-generated key, one per SCD2 version |
| Natural key | Clave natural | The identifier from the source system |
| Canonical / golden key | Clave canónica / maestra | One ID per real-world entity across systems |
| Bus matrix | Matriz de bus | Business processes × conformed dimensions grid used to plan integration |
| One Big Table (OBT) | Tabla única desnormalizada | One wide pre-joined table for easy consumption |
| Data Vault | Data Vault | Hubs (keys), links (relations), satellites (history) for auditable integration |
| Right to erasure (GDPR) | Derecho de supresión | Obligation to delete personal data on request; history multiplies copies |
| Fan-out | Multiplicación de filas (fan-out) | Row duplication when joining at mismatched grains, inflating sums |
| Semi-join / anti-join | Semi-join / anti-join | Filter rows by existence (EXISTS) / non-existence (NOT EXISTS) in another table, without duplicating rows |
| incremental_predicates (dbt) | Predicados incrementales | Extra filters on the MERGE target so only recent partitions are scanned |
| BRIN index (Postgres) | Índice BRIN | Tiny block-range index, ideal for naturally ordered columns like timestamps |
| Zone maps (Redshift) | Mapas de zona | Per-block min/max metadata that lets Redshift skip blocks; driven by the SORTKEY |
| Hot / cold data | Datos calientes / fríos | Rows that still change (open processes) vs. frozen rows (closed) |
| Materialization (dbt) | Materialización | How dbt persists a model: view, table, incremental, ephemeral, materialized_view |
| Ephemeral model | Modelo efímero | Not created in the DB; inlined as a CTE into downstream models |
| Incremental model | Modelo incremental | Processes only new/changed rows after the first build |
| Watermark | Marca de agua | The max value (timestamp/id) already loaded; the next run reads above it |
| Lookback window | Ventana de reprocesamiento | Re-read rows N days behind the watermark to catch late arrivals |
| Late-arriving data | Datos que llegan tarde | Rows that land after newer rows were already processed |
| Idempotent | Idempotente | Running it twice gives the same result (merge on a key is; append is not) |
| delete+insert | Borrar e insertar | Incremental strategy: delete matching keys, then insert (classic on Redshift) |
| Microbatch (dbt) | Microlotes | Incremental strategy that processes time batches with built-in backfills/retries |
| Snapshot (dbt) | Snapshot / instantánea | Polling-based SCD2 capture of a mutable source table |
| Change log | Registro de cambios | App-written table with one row per business change (log-based history) |
| CDC (Change Data Capture) | Captura de cambios de datos | Streaming row changes from a DB transaction log (Debezium, DMS, Datastream) |
| Data test (generic / singular) | Test de datos (genérico / singular) | Query that returns failing rows; YAML-declared reusable vs one-off SQL file |
| Unit test (dbt) | Test unitario | Mocked inputs → expected outputs to test model logic without real data |
| Source freshness | Frescura de fuentes | SLA check on how recent a source's data is (loaded_at_field or table metadata) |
| store_failures | Guardar fallos | Persist a test's failing rows in a table for debugging |
| Reconciliation test | Test de conciliación | Compares source vs target to detect rows an incremental missed |
| adapter.dispatch | adapter.dispatch | dbt mechanism to pick a macro implementation per database |
| UNNEST | UNNEST / desanidar | Turns an ARRAY into rows (BigQuery) |
| QUALIFY | QUALIFY | Filters on a window function result without a subquery |
| HyperLogLog++ (APPROX_COUNT_DISTINCT) | HyperLogLog++ | Approximate distinct count: tiny memory, ~1% error |
| Document of record | Documento fehaciente | The legally issued artifact (invoice) whose values must be kept as issued |
| On-demand minimum billing (BQ) | Facturación mínima on-demand | BigQuery bills at least 10 MB per table referenced in a query |
