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
