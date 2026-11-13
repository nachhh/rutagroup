# Phase 4: UDL, entity resolution, ontology, knowledge graph (⏱ 1 h)

## Goal
Turn two product-centric models into one entity-centric layer, and make its meaning explicit
(ontology) and traversable (knowledge graph).

## Steps
1. **Replicate** (`scripts/replicate_ship_to_bq.py`, `make replicate`): read the public marts of `ruta_ship`
   from PG → write Parquet → load into BQ dataset `ship_replica` (`WRITE_TRUNCATE`). The
   comments map each step to the real path: `UNLOAD ... FORMAT PARQUET` → S3 → Storage Transfer Service → GCS → BQ load.
2. **Sources**: `ruta_udl` declares `ship_replica.*` as sources with freshness. This is the dbt Mesh
   contract boundary.
3. **Entity resolution**: `int_customer_candidates` → `int_customer_xwalk`
   - Blocking key: normalized tax_id prefix / email domain
   - Rules, in priority order: exact normalized `tax_id` (conf 1.0) → corporate email domain + name
     similarity (`EDIT_DISTANCE` on normalized names, conf 0.8) → name-only (conf 0.5, review queue)
   - Output: `customer_key` (`FARM_FINGERPRINT` of the winning cluster), `source_system`, `source_id`,
     `match_rule`, `confidence`
   - `int_customer_review_queue` holds ambiguous matches (a stewardship workflow, which is also a governance point)
4. **Conformed marts**: `dim_customer` (SCD2, `is_multi_product`, `products ARRAY<STRING>`),
   `fct_revenue` (unified revenue facts from both products, same grain/currency, with `revenue_type`),
   `fct_customer_monthly`.
5. **Ontology** (`ontology/ruta_ontology.yml`): a lightweight, YAML-based model (not OWL):
   ```yaml
   classes:
     Customer: {description, identifiers: [customer_key], synonyms: [client, account, shipper, cliente], maps_to: dim_customer}
     Shipment: {...}  Invoice: {...}  Payment: {...}  Plan: {...}  Carrier: {...}  Region: {...}
   relations:
     - {subject: Customer, predicate: books, object: Shipment, cardinality: 1..*, via: fct_shipments.customer_key}
     - {subject: Invoice, predicate: bills_for, object: Shipment, via: stg_pay__invoices.shipment_ref}
     - {subject: Customer, predicate: subscribes_to, object: Plan, temporal: true}
   ```
   Uses: documentation, NL synonyms (Phase 6), KG generation (step 6), and a test (every class maps to a public model).
6. **Knowledge graph**: `kg_nodes(node_id, node_type, properties JSON)` and
   `kg_edges(src_id, predicate, dst_id, valid_from, valid_to, properties JSON)` are generated from the
   ontology + marts (a dbt macro loops over the ontology `relations`). Demo query:
   2-hop "customers who share a carrier with churned customers" using recursive CTE / self-joins.
7. `docs/04_udl_ontology.md`: definitions and differences between **semantic layer vs UDL vs
   context layer vs ontology vs knowledge graph**; RDF/OWL/SPARQL vs property graph (Neo4j,
   Spanner Graph / BQ graph queries) in one paragraph; why entity-centric beats product-centric for agents.

## Diagrams
Update `docs/diagrams/ontology.md` (final) and add `docs/diagrams/entity-resolution.md` (flowchart).

## Acceptance criteria
- ~550 customers resolved as multi-product (± the noise rate). Unit test on the matching rules.
- `kg_edges` has every relation type from the ontology. The 2-hop query returns rows.

## 🧭 Checkpoints
1. Matching rules and confidence threshold for auto-merge
2. Ambiguous matches: drop, keep separate, or review queue?
3. Revenue currency normalization: where and when (FX at transaction date vs month-end)?
4. As-of join grain for billing (Phase 2 finding: 20 invoices issued hours before the subscription start on the same day):
   join at date grain, or normalize `valid_from` to the start of the day?

## 🧠 Quiz 4: 4 questions
