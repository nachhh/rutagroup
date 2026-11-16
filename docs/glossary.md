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
| Data product | Producto de datos | A dataset run like an API: owner, documented interface, guarantees, consumers. In dbt: a public, contracted model |
| Model contract (dbt) | Contrato de modelo | `contract: {enforced: true}`: dbt checks column names/types *before* building (shape, not values) |
| Constraint (enforced / informational) | Restricción (aplicada / informativa) | PK/FK/not null in DDL. Postgres enforces; BigQuery and Redshift only record them for the optimizer |
| Access level (dbt) | Nivel de acceso | `private` (own group) · `protected` (own project, default) · `public` (other projects, semantic layer, agents) |
| Group (dbt) | Grupo | A named owning team for a set of models; `private` models are only ref-able inside it |
| Model version (dbt) | Versión de modelo | v1 and v2 of a model side by side so a breaking change doesn't break consumers; v1 gets a `deprecation_date` |
| Deprecation date | Fecha de deprecación | When an old model version stops being supported; dbt warns consumers that still ref it |
| Data classification | Clasificación de datos | Labels like public / internal / confidential and `pii`, stored as column metadata |
| PII (Personally Identifiable Information) | Datos personales identificables | Data that identifies a person (email, phone). GDPR: "personal data" |
| Pseudonymization | Seudonimización | Replacing an identifier with a token (e.g. SHA-256). Joinable but still personal data under GDPR |
| Masking (static / dynamic) | Enmascaramiento (estático / dinámico) | Hiding values: in SQL when building (static) or by the engine per reader at query time (dynamic) |
| Least privilege | Mínimo privilegio | Each role gets only the access it needs |
| Grants (dbt) | Permisos | `grants:` config: dbt applies GRANT/REVOKE after every build, so permissions are versioned with models |
| Row-level security (RLS) | Seguridad a nivel de fila | The engine filters rows per user/role (PG/Redshift `CREATE POLICY`, BQ row access policies) |
| Column-level security | Seguridad a nivel de columna | Per-column access control. BigQuery: policy tags + Fine-Grained Reader |
| Policy tag (BigQuery) | Etiqueta de política | A taxonomy node attached to columns; only Fine-Grained Readers see raw values, Masked Readers see masked ones |
| Data policy (BigQuery) | Política de datos | A masking rule (SHA256, nullify, default value, …) bound to a policy tag |
| Authorized view | Vista autorizada | A view allowed to read a dataset its own readers can't access: share a curated slice |
| Security definer view | Vista con derechos del propietario | A view that runs with its owner's privileges (Postgres default); the PG analogue of an authorized view |
| Policy as code | Políticas como código | Governance rules written as code and run in CI (here: checks over manifest.json) |
| manifest.json (dbt) | manifest.json | dbt's compiled project graph with all configs and metadata; the input for CI checks, `--defer`, docs |
| Exposure (dbt) | Exposición | A declared downstream consumer (dashboard, app) that closes the lineage graph |
| Data steward / owner | Responsable de datos | The accountable person/team for a dataset's quality, access and definitions |
| Crosswalk (xref) | Tabla de correspondencias | Maps each source-system id to the canonical entity key |
| Blocking | Bloqueo (blocking) | Only comparing record pairs that share a cheap key, to avoid comparing everything with everything |
| Matching rule | Regla de coincidencia | Deterministic or fuzzy condition that suggests two records are the same entity |
| Fellegi–Sunter | Fellegi–Sunter | Probabilistic record linkage: weights agreement per field into a match score (Splink implements it) |
| Veto (negative evidence) | Veto (evidencia negativa) | A conflicting strong key that blocks a merge regardless of other similarity |
| Edit distance (Levenshtein) | Distancia de edición | Minimum single-character edits between two strings (BigQuery `EDIT_DISTANCE`) |
| Survivorship | Supervivencia (de atributos) | Rules for which source's value wins in the golden record |
| Golden record | Registro maestro | The single best version of an entity assembled from all sources |
| MDM (Master Data Management) | Gestión de datos maestros | Discipline and tooling to maintain golden records operationally |
| Data stewardship | Custodia de datos | Humans accountable for resolving ambiguous data (e.g. the match review queue) |
| Key registry | Registro de claves | Persisted table that assigns canonical keys once and never reissues them |
| Precision / recall | Precisión / exhaustividad | Correct merges / all merges · correct merges / all true pairs |
| Timeline merge (SCD2) | Fusión de líneas de tiempo | Combining several SCD2 histories by unioning their change points into new intervals |
| Pass-through revenue | Ingreso de paso | Money collected on behalf of a third party (freight for carriers): not revenue |
| Average vs closing FX rate | Tipo de cambio medio vs de cierre | Income converted at the period average; balances at the period-end rate |
| Class / instance | Clase / instancia | Concept (Customer) vs a concrete member (customer 123) |
| Predicate / relation | Predicado / relación | The named link between two classes (Customer *books* Shipment) |
| RDF triple | Tripleta RDF | Subject–predicate–object: the atomic fact in RDF knowledge graphs |
| OWL | OWL | Web Ontology Language: formal ontologies with inference |
| SPARQL | SPARQL | Query language for RDF graphs |
| Property graph | Grafo de propiedades | Nodes and edges carrying key-value properties (Neo4j, GQL, Spanner Graph) |
| GQL | GQL | ISO standard graph query language (`MATCH (a)-[:rel]->(b)`) |
| Replication (UNLOAD → S3 → GCS) | Replicación | Redshift exports Parquet to S3, transfer to GCS, BigQuery loads it |
| Semantic model | Modelo semántico | Metadata on one dbt model: entities, dimensions, metrics (MetricFlow) |
| Entity (primary / foreign / natural) | Entidad | A semantic model's join key; natural = non-unique key of an SCD2 model |
| `metric_time` | Tiempo de la métrica | MetricFlow's shared time axis; each metric maps its own date to it |
| `agg_time_dimension` | Dimensión temporal de agregación | The date a metric is aggregated on by default |
| Time spine | Calendario base (time spine) | One row per day; used for cumulative windows, offsets and gap filling |
| Simple / ratio / derived / cumulative / conversion metric | Tipos de métrica | The five MetricFlow metric types (conversion = funnel within a window) |
| Semi-additive measure | Medida semiaditiva | Sums across some dimensions but not time (MRR, balances): take the last snapshot |
| Fan-out | Multiplicación de filas (fan-out) | A one-to-many join that duplicates rows and inflates sums |
| Saved query / export | Consulta guardada / exportación | A named metric request; an export materializes it as a table |
| Headless BI | BI sin interfaz (headless) | Metrics served as an API, independent of any front end |
| Open Semantic Interchange (OSI) | OSI | Industry effort for one portable semantic-layer spec |
| Right-censoring | Censura por la derecha | Recent periods can't be judged yet (e.g. churn needs 90 days of future) |
| Left-censoring | Censura por la izquierda | History starts mid-stream: the first observed event isn't the true first |
| Text-to-SQL | Texto a SQL | The LLM writes raw SQL against tables: flexible, but ungoverned and inconsistent |
| Text-to-metric-query | Texto a consulta de métricas | The LLM only picks metrics/dimensions/filters; the semantic layer writes the SQL |
| MCP (Model Context Protocol) | Protocolo de contexto de modelos | Open standard for exposing tools/resources/prompts to agents (client ↔ server, stdio or HTTP) |
| MCP host / client / server | Host / cliente / servidor MCP | The app running the agent / its protocol connection / the process exposing tools |
| Tool calling (function calling) | Llamada a herramientas | The LLM returns a structured call; the app executes it and feeds the result back |
| Guardrail | Barandilla / salvaguarda | A server-enforced limit on what an agent can do (allowlist, read-only, row cap) |
| Golden question set (eval) | Conjunto de preguntas de referencia | Questions with the expected metric query, used to test an agent |
| DAG (Airflow) | DAG / grafo acíclico dirigido | A workflow: tasks plus their dependencies, with a schedule |
| Operator / task | Operador / tarea | A task template (BashOperator…) / one node of the DAG run |
| TaskGroup | Grupo de tareas | Visual and logical grouping of tasks inside a DAG |
| Asset (ex-Dataset) | Activo de datos | Airflow 3 logical data product; `outlets` update it, `schedule=[asset]` reacts to it |
| Data-aware scheduling | Planificación por datos | Run a DAG when its input data is updated, not at a clock time |
| Idempotent task | Tarea idempotente | Running it twice gives the same result: safe retries and backfills |
| Backfill / catchup | Reproceso histórico | Running past intervals of a schedule |
| Astronomer Cosmos | Cosmos | Library that renders each dbt model/test as an Airflow task |
| OpenLineage | OpenLineage | Open standard for lineage events (job run + input/output datasets) |
| Marquez | Marquez | Reference OpenLineage server and lineage UI |
| UNLOAD (Redshift) | UNLOAD | Export a query result from Redshift to S3 (e.g. Parquet) |
| Storage Transfer Service | Servicio de transferencia de almacenamiento | GCP managed copy from S3 (and others) to GCS |
| BigQuery Data Transfer Service | Servicio de transferencia de datos de BQ | Managed connectors into BQ, incl. a Redshift migration connector |
| BigQuery Omni / BigLake | BigQuery Omni / BigLake | Query data in AWS/Azure object storage in place / governed external tables |
| DISTKEY / SORTKEY | Clave de distribución / de orden | Redshift physical design: node co-location and block pruning |
| SUPER (Redshift) | SUPER | Redshift semi-structured type, queried with PartiQL |
| RPU | Unidad de procesamiento de Redshift | Redshift Serverless compute/billing unit |
