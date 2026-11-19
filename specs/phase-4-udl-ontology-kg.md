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
   - Output: `customer_key` (`FARM_FINGERPRINT` of the winning cluster; persisted in a key registry since
     [Phase 7s2](phase-7s2-extras.md)), `source_system`, `source_id`,
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

## Status log
- ✅ Replication from the `udl_replication` exposure (public only): 5 marts → `ship_replica` (Parquet, WRITE_TRUNCATE).
- ✅ ER: precision 1.000, recall 0.974 vs truth (`make eval-er`); 0 decoys merged; 15 true pairs in the review queue;
  2 steward decisions seeded. Unit test on veto/score/routing.
- ✅ `dim_customer` (timeline merge, 1,904 customers, 554 multi-product), `fct_revenue` (107.5k rows, all FX resolved),
  `fct_customer_monthly`, `fct_product_enrollment`. Churn 11.0% multi vs 30.4% single.
- ✅ As-of at date grain: Phase 2 finding 20 → 8 → 0 (tie-break must prefer an active version on cancel days).
- ✅ Ontology YAML → generated KG (122k nodes, 270k edges, all 11 relations); churn-neighbourhood query; govern R6.
- ⚠️ Gotcha: enforced contract + `insert_overwrite` → `_dbt_max_partition` undeclared on incremental runs. Fixed with
  an explicit `max(issued_date)` watermark.
- Full `make udl`: 91 pass, 0 warn.
- ✅ Quiz 4 done (4 questions).

## 🧭 Decisions (settled)
1. **Matching (A):** rule cascade with a **veto evaluated first**. Veto: both normalized tax_ids present and different →
   never auto-merge (goes to review as `tax_conflict`). Rules: exact tax_id (1.0) → exact `email_sha256`, corporate
   domains only (0.95) → same corporate domain + name `EDIT_DISTANCE` ≤ 2 (0.8) → name-only, same country (0.5).
   Auto-merge ≥ 0.8; 0.5–0.8 → review; personal domains (gmail/hotmail/yahoo/outlook) are excluded from email rules.
2. **Ambiguous (A):** `int_customer_review_queue` + steward decisions as a seed (`seed_match_decisions.csv`:
   shipper_id, account_id, decision, reviewer, decided_at). Undecided pairs stay separate customers.
3. **FX (A, hybrid):** `seed_fx_rates_monthly` (monthly AVERAGE rate, EUR base). `fct_revenue` stores `amount_local`,
   `currency`, `fx_rate`, `amount_eur` (rate of the transaction month). It's a table rebuilt every run, so rate changes
   propagate; closed months are locked by finance anyway. MetricFlow measures can't multiply by a rate from another
   semantic model, so the converted column lives in the fact.
4. **As-of grain (A):** join plans at DATE grain (`issued_date between date(valid_from) and date(valid_to)`); when
   two versions overlap on the same day, QUALIFY prefers the *active* version (then the latest `valid_from`): a fee charged
   on the cancel day belongs to the cancelled plan. The SCD2 stays truthful.
- Revenue definition across products: Ship = `booking_fee`; Pay = subscription + txn_fee + freight_fee. The Pay
  `FREIGHT` line is pass-through GMV (already counted as Ship GMV) → excluded. Summing GMV across products would double-count.

## 🧭 Checkpoints (original)
1. Matching rules and confidence threshold for auto-merge
2. Ambiguous matches: drop, keep separate, or review queue?
3. Revenue currency normalization: where and when (FX at transaction date vs month-end)?
4. As-of join grain for billing (Phase 2 finding: 20 invoices issued hours before the subscription start on the same day):
   join at date grain, or normalize `valid_from` to the start of the day?

## 🧠 Quiz 4: 4 questions (ER precision vs recall, the five layers, FX in the fact + incremental backfill, property graph vs RDF)
