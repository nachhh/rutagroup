# 04: Unified Data Layer, entity resolution, ontology, knowledge graph

From two product-centric warehouses to one entity-centric layer, with its meaning written down (ontology) and made
traversable (knowledge graph). Spec: [phase-4](../specs/phase-4-udl-ontology-kg.md).
Diagrams: [entity resolution](diagrams/entity-resolution.md) · [ontology](diagrams/ontology.md) · [dbt lineage](diagrams/dbt-lineage.md).

## 1. Five terms people blur

| Term | Answers | Here |
|---|---|---|
| **UDL** (Unified Data Layer) | *What is the integrated data?* Product silos joined on canonical entities, conformed, governed | `dim_customer`, `fct_revenue`, `fct_customer_monthly`, `fct_product_enrollment` |
| **Semantic layer** | *How is each metric computed?* Measures, dimensions, joins, time grains defined once, served to BI/APIs/agents | MetricFlow (Phase 5) |
| **Ontology** | *What do things mean and how do they relate?* Classes, relations, synonyms, mapping to data products | [`ontology/ruta_ontology.yml`](../ontology/ruta_ontology.yml) |
| **Knowledge graph** | *Which instances are connected?* The ontology populated with nodes and edges | `udl_kg.kg_nodes`, `udl_kg.kg_edges` |
| **Context layer** | *What does an AI agent need to act correctly?* Ontology + metric catalog + graph neighbourhoods + governance rules | Phase 6 (MCP) |

**UDL = the data · semantic layer = the math · ontology = the dictionary · KG = the map · context layer = the agent's briefing.**
Entity-centric beats product-centric for agents: "how is ACME doing?" needs ACME's shipments, invoices, payments and
plan as *one* entity. Without a crosswalk and an ontology, the agent has to guess joins across systems.

## 2. Pipeline

```
Postgres (≈ Redshift)             BigQuery
ruta_ship public marts ──replicate──▶ ship_replica ──▶ stg_ship__*  ─┐
  (only what the udl_replication       (Parquet load,                 ├─▶ entity resolution ─▶ int_customer_xwalk
   exposure lists, all public)          WRITE_TRUNCATE)  raw_pay ─▶ stg_pay__* ─┘                    │
                                                                       dim_customer · fct_revenue · fct_customer_monthly
                                                     ontology YAML ──generate──▶ kg_nodes · kg_edges
```

- **Replication** ([`replicate_ship_to_bq.py`](../scripts/replicate_ship_to_bq.py)): reads the list of models from
  the `udl_replication` exposure and refuses non-public models. Real path: `UNLOAD … FORMAT PARQUET` → S3 → Storage
  Transfer Service → GCS → BQ load job (free). Alternative: BigLake/Omni external tables over S3 (no copy, slower).
- **Mesh boundary:** `ship_replica` is a dbt *source* with freshness on `_replicated_at`. With dbt Cloud Mesh it
  would be `ref('ruta_ship', 'fct_shipments')`, allowed only because the model is `public`.

## 3. Entity resolution (decisions 1A, 2A)

| Step | Model | What |
|---|---|---|
| Normalize | `int_customer_candidates` | One shape for both systems: `name_norm` (accents, punctuation, legal suffixes removed), `tax_id_norm`, `email_sha256` (same SHA-256 macro on both engines), personal-domain flag |
| Block | `int_customer_pairs` | UNION of equi-joins on tax id, email hash, corporate domain, name prefix + country. Never an OR-join (= cross join) |
| Veto → score → route | `int_customer_pairs` | **Veto first:** two present, different tax ids → `review_conflict`. Then the best rule: tax id 1.0 · email 0.95 · domain+name 0.8 · name only 0.5. ≥ 0.8 auto-merge |
| Decide | `int_customer_matches` | Auto-merges + steward `match`, minus steward `no_match`; mutual-best 1:1 |
| Steward | `int_customer_review_queue` + `seed_match_decisions.csv` | Stewardship as code: decisions are reviewed PRs with reviewer and date |
| Cluster | `int_customer_clusters` | Every source record → today's match cluster (`cluster_id` = anchor). Stateless |
| Key registry | `int_customer_key_registry` | Append-only log of key assignments (`full_refresh: false`): the only state. Phase 7s2 |
| Crosswalk | `int_customer_xwalk` | Every source record → `customer_key` (current key from the registry) |
| Aliases | `customer_key_aliases` | Public: retired key → today's key, for consumers that stored a key before a merge |

**Results vs ground truth** (`make eval-er`): precision **1.000**, recall **0.974** (F1 0.987). No decoy merged.
All 15 missed pairs sit in the review queue (a tax id missing on one side, so only name rules fire). In production,
precision is estimated by steward sampling per rule, and recall from known links (invoices with a `shipment_ref`).

Lessons:
- **Negative evidence matters as much as positive.** The queue contains identical names on the same domain with different
  tax ids: distinct companies whose names collided. Without the veto they'd be auto-merged at 0.8.
- **Key stability → key registry (Phase 7s2).** A key hashed from an anchor changes when a ship-only customer later
  matches an account. Fix: **recompute identity, persist keys.** Matching stays stateless; `int_customer_key_registry`
  assigns keys once and records every change as an appended row with a reason:

  | Event | Registry | Key |
  |---|---|---|
  | Churn, inactivity, source deletion | nothing (a deleted record's last row = tombstone) | unchanged: not identity events |
  | New record joins a keyed customer | `inherit` | the customer's key |
  | Two keyed customers become one | `merge` | **oldest key wins**; the loser → `customer_key_aliases` |
  | A match is undone (steward `no_match`) | `split` | the side that held it longest keeps it; the other gets its own or a new key |
  | Brand-new customer | `new` | minted once (`FARM_FINGERPRINT(cluster_id ‖ invocation_id)`), never recomputed |

  Adoption was a **migration**, not a reissue: an empty registry uses the old formula, so no existing key changed
  (verified by checksum on the crosswalk, `dim_customer` and `fct_revenue`). A retired key is never handed out again
  (singular test), so an alias lookup can't land on the wrong customer. The registry is state like a snapshot:
  `full_refresh: false`, cloned/deferred in CI. Simulated with steward decisions: merge → alias; reverting it gave the
  split-off side a **new** key and the old alias followed it (`retired → current`, resolved in one lookup).
  Known simplification: migrated keys share one birth time, so a merge between two of them falls back to the
  smallest key; a production version would use the records' `created_at` as the age.
- **Dynamic masking vs matching.** A masked email (Phase 3) can't be matched after `lower()`. ER needs Fine-Grained
  Reader, or matching on hashes computed at the source (what RutaShip does with `email_sha256`).

## 4. Conformed marts

- **`dim_customer`: timeline merge.** Ship tier/region history (snapshot) and Pay plan history (change log) change on
  unrelated dates. Collect every change point → intervals `[valid_from, valid_to)` → as-of join each side. Survivorship:
  name from RutaShip else RutaPay; region from Ship history else Pay's primary address. `current_region` = type 6.
  Snapshot history starts at the first `dbt snapshot` run, so the first ship version is back-dated to `created_at`
  (a documented assumption).
- **`fct_revenue`:** Ship `booking_fee` + Pay subscription / txn_fee / freight_fee, void invoices excluded. The Pay
  `FREIGHT` line is **pass-through GMV** (already Ship GMV): summing GMV across products would double-count it.
  FX (3A): `amount_local`, `currency`, `fx_rate`, `amount_eur` at the month's **average** rate (income at period-average,
  balances at closing rate). A table rebuilt every run → rate updates propagate; MetricFlow measures can't multiply by
  a rate from another semantic model, so the EUR column lives in the fact.
- **`fct_customer_monthly`:** periodic snapshot; `mrr_eur` is semi-additive.
- **`fct_product_enrollment`:** factless coverage fact.
- **Validation that the UDL works:** current-plan churn is **11.0%** for multi-product customers vs **30.4%** for
  single-product ones, a signal that only exists after entity resolution.
- **As-of grain (4A):** plans joined to invoice lines at date grain; the tie-break prefers an *active* version (a fee
  charged on the cancel day belongs to the cancelled plan). The Phase 2 finding (20 lines without plan) → 0.

## 5. Ontology and knowledge graph

[`ontology/ruta_ontology.yml`](../ontology/ruta_ontology.yml): 9 classes (Customer, Shipment, Carrier, Lane, Region,
Invoice, Payment, Plan, Product), 11 relations (books, carries, follows, originates_in, ends_in, located_in,
subscribes_to *(temporal)*, uses, billed_to, bills_for, settles). Each class has a description, synonyms (for the NL
agent), `maps_to` (a public data product; `make govern` rule **R6**) and how to materialize its instances.

`make ontology` **generates** the dbt models `kg_nodes` (≈ 122k) and `kg_edges` (≈ 270k) from the YAML. Change
meaning in one place and the graph follows. Edges reference nodes (`relationships` tests); node ids are typed
(`customer:…`, `shipment:…`).

Demo ([`analyses/kg_churn_neighbourhood.sql`](../dbt/ruta_udl/analyses/kg_churn_neighbourhood.sql)): carriers ranked
by how many churned customers they serve, and how many active customers share them. That's a 4-edge path
(Customer→Shipment←Carrier→Shipment←Customer) written as self-joins, with the GQL equivalent in the comments.

## 6. RDF/OWL vs property graphs (one paragraph)

**RDF** stores facts as subject–predicate–object *triples* with global IRIs. **OWL** adds formal semantics (class
hierarchies, constraints, inference: "every Shipper is a Customer"). **SPARQL** queries it. It's strong for
standards-based data integration across organizations and reasoning, but heavy for analytics teams. **Property graphs** (Neo4j/Cypher,
ISO **GQL**, Spanner Graph, BigQuery graph queries via `CREATE PROPERTY GRAPH`) put key-value properties directly on
nodes and edges and are what most data platforms use. Ours is a property graph stored as two tables, with a YAML
ontology instead of OWL: enough meaning for documentation, code generation, governance checks and an LLM agent,
without a reasoner.
