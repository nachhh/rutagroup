# 01: Data modeling for Ruta

How the marts are shaped and why. Spec: [phase-1](../specs/phase-1-data-modeling.md).
Diagram: [star schema](diagrams/star-schema.md).

## 1. Grain first

Every model declares its grain as "one row per ___" in its YAML description. Most modeling bugs,
such as double-counted revenue or join fan-out, come from mixing grains in one table or from
joining two facts directly at different grains.

## 2. Fact tables

| Model | Grain | Fact type | Load pattern | Measures (additivity) |
|---|---|---|---|---|
| `fct_shipments` | 1 row per shipment | Transaction (with current status) | Incremental `merge` on `shipment_id` (status changes late); re-reads shipments with a changed row **or** new events | `gmv`, `booking_fee` (additive); `is_on_time` (flag, feeds a ratio) |
| `fct_shipment_events` | 1 row per tracking event | Transaction, **append-only** | Incremental `append`: events are immutable and arrive unannounced | count of events |
| `fct_shipment_lifecycle` | 1 row per shipment, milestone columns filled in over time | **Accumulating snapshot** | Rebuilt (`table`) from events: `booked_at`, `picked_up_at`, `delivered_at`, lags in hours | lag hours (additive per row, usually averaged) |
| `fct_invoice_lines` | 1 row per invoice line | Transaction | Incremental `insert_overwrite` on `issued_date` partitions | `amount` (additive), `qty` |
| `fct_payments` | 1 row per invoice payment outcome | Transaction | Incremental `merge` on `invoice_id` | `amount_paid`, `amount_refunded` (additive) |
| `fct_customer_monthly` | 1 row per customer per month | **Periodic snapshot** | `table` | `mrr` (**semi-additive**: sums across customers, not across months), `shipments`, `gmv` |
| `fct_revenue` (Phase 4) | 1 row per revenue-bearing line, across both products | Transaction (unified) | `table` | `revenue_eur` (additive) |
| `fct_product_enrollment` | 1 row per customer × product | **Factless** (coverage) | `table` | none; count rows ("customers on both products") |

> **Note: `fct_shipments` vs `fct_shipment_lifecycle` is a teaching split.** Both are 1 row per
> shipment built from the same inputs; the second exists only to show an accumulating snapshot. In a
> real project they would be **one** model (`fct_shipments` carrying the milestone columns), because:
> - two models at the same grain duplicate columns (`delivered_at`, `is_on_time` vs `hours_late`);
> - `status` (source) and `current_milestone` (derived from events) are two definitions of the same
>   concept that can disagree, which is the drift a semantic layer is meant to prevent.
>
> Keep them separate only when the **grain** differs (per shipment leg/stop) or the **owner or
> contract/SLA** differs (ops milestones vs finance GMV).

**Change detection on every input.** `fct_shipments` reads two tables: shipments (status, GMV) and
events (`delivered_at`, `had_exception`). Its incremental filter re-reads a shipment if its own row
changed **or** it has new events, both against the same source-clock watermark (`max(updated_at)`).
We enforce this instead of assuming the source always bumps `shipments.updated_at` when an event
lands. That assumption breaks when the two tables replicate with different lag (the shipment row
arrives before its `delivered` event), when an event doesn't change the shipment row, or when a script
bypasses `updated_at`. The reconciliation test
(`assert_fct_shipments_reconciles_with_source`) also checks both inputs, so drift beyond the lookback
shows up as a warning until a `--full-refresh`.

**Additivity cheat sheet**
- **Additive:** can be summed across every dimension (`gmv`, `revenue`).
- **Semi-additive:** can be summed across some dimensions but not time (`mrr`, balances, headcount). Use the last/max value in the period. In MetricFlow this is `non_additive_dimension`.
- **Non-additive:** never summed (`take_rate`, `on_time_rate`). Compute them as `sum(num) / sum(den)`, which is a MetricFlow **ratio** metric. Averaging per-row ratios is a classic bug.

## 3. Dimensions

| Model | Grain | Notes |
|---|---|---|
| `dim_customer` | 1 row per customer **version** (SCD2) | Conformed across Ship + Pay. `customer_sk` (surrogate, per version), `customer_key` (canonical, durable, Phase 4) |
| `dim_date` | 1 row per day | **Role-playing**: booked / delivered / issued / due / month |
| `dim_carrier`, `dim_lane` | 1 row per carrier / lane | Ship-only dimensions |
| `dim_plan` | 1 row per plan (seed) | Price list, plan tier ordering |
| `dim_region` | 1 row per region (seed) | Conformed: both products and lanes use it |
| degenerate | n/a | `invoice_number` lives on `fct_invoice_lines`. No dimension needed |

### SCD policy for `dim_customer` (decided)

You decide the SCD type per attribute, based on (a) the analytical need for history and (b) the
governance cost of keeping it.

| Attribute | Type | Rationale |
|---|---|---|
| `plan_code` (Pay) | **SCD2** | Revenue by plan must be "as of" the invoice date |
| `ship_tier` (Ship) | **SCD2** | Tier drives take rate, and history matters for audits |
| `region` | **SCD2** + `current_region` (type 6 lite) | Territory reporting needs "as was". `current_region` answers "customers in X *today*" over all history |
| `legal_name` | SCD1 | Changes are mostly corrections. Audit copy: `billed_legal_name` stays on the invoice fact (the document of record) |
| `contact_email`, `contact_phone` | SCD1 | PII: history multiplies personal-data copies (GDPR erasure, data minimization) and has no analytical value |

**Joining facts to an SCD2 dimension.** There are two classic options:
1. **At load time (Kimball):** look up the `customer_sk` valid at the event time and store it on the fact. Queries are fast and simple, but late-arriving dimension changes force a fact rebuild.
2. **At query time:** store the durable `customer_key` + event timestamp on the fact, and join
   `on f.customer_key = d.customer_key and f.event_ts >= d.valid_from and f.event_ts < d.valid_to`.
   This is more flexible, and it's what **MetricFlow supports natively** through `validity_params` on an SCD2
   semantic model (Phase 5). **We use option 2**, with `customer_key` on all facts.

## 4. Keys

- **Natural key:** the ID in the source system: `shipper_id`, `account_id`.
- **Surrogate key:** generated in the warehouse, one per SCD2 version (`customer_sk` = hash of key + valid_from).
- **Canonical / golden key:** one per real-world entity across systems (`customer_key`). Entity
  resolution produces it in Phase 4. This is where dimensional modeling meets the **UDL** and the **ontology**.

## 5. Modeling styles: when to pick which

| Style | Use it for | In Ruta |
|---|---|---|
| **3NF / ER** | OLTP sources, integrity, few redundancies | RutaShip raw schema |
| **Dimensional (star)** | Analytics marts, BI, and the structure a semantic layer needs (entities, measures, dims) | Our marts ✅ |
| **One Big Table (OBT)** | Fast and simple consumption, ML features. Cheap on columnar engines, especially BQ nested | ❌ Not built: duplicated metric logic, fan-out risk. The semantic layer serves NL/agents instead |
| **Data Vault 2.0** | An integration layer for many sources with full auditability (hubs = business keys, links = relationships, satellites = history) | Not built. A valid choice for a large UDL's integration layer, with stars on top |
| **Nested / document (BQ)** | Keeping 1:N children with the parent (`ARRAY<STRUCT>`), avoiding joins | RutaPay raw (`invoices.lines`); flattened in staging |

## 6. Bus matrix

Rows are business processes, columns are conformed dimensions. A ✅ in a column shared by both
products is what makes cross-product questions answerable. That is the essence of a UDL.

| Process ↓ / Dimension → | Customer | Date | Region | Plan | Carrier | Lane | Product |
|---|---|---|---|---|---|---|---|
| Shipment booking (`fct_shipments`) | ✅ | ✅ booked, delivered | ✅ | | ✅ | ✅ | ✅ Ship |
| Shipment tracking (`fct_shipment_events`, `_lifecycle`) | ✅ | ✅ | ✅ | | ✅ | ✅ | ✅ Ship |
| Invoicing (`fct_invoice_lines`) | ✅ | ✅ issued, due | ✅ | ✅ | | | ✅ Pay |
| Payments (`fct_payments`) | ✅ | ✅ paid | ✅ | | | | ✅ Pay |
| Subscriptions (`dim_customer` SCD2) | ✅ | ✅ valid_from/to | | ✅ | | | ✅ Pay |
| Customer monthly (`fct_customer_monthly`) | ✅ | ✅ month | ✅ | ✅ | | | ✅ both |
| Unified revenue (`fct_revenue`) | ✅ | ✅ | ✅ | ✅ | | | ✅ both |

**Customer, Date and Region** span both products, so these three need to be conformed first.
