# Phase 1: Data modeling refresher (⏱ 40 min)

## Goal
Be able to explain *why* the marts look the way they do: grain, fact type, dimension design.

## Concepts (→ `docs/01_modeling.md`)
- **Grain first**: "one row per ___" before any column.
- Fact types:
  - **transaction**: `fct_shipments`, `fct_invoice_lines`
  - **periodic snapshot**: `fct_customer_monthly` (MRR, shipments, active flags per month)
  - **accumulating snapshot**: `fct_shipment_lifecycle` (booked → picked_up → delivered milestones)
  - **factless**: customer × product enrollment
- Additive, semi-additive (balances, MRR over time), and non-additive (ratios) measures. This
  connects directly to MetricFlow measure aggregation in Phase 5.
- Dimensions: **conformed** (`dim_customer`, `dim_date`, `dim_region` shared by both products),
  role-playing (`dim_date` as booked/delivered/issued/due), junk, degenerate (invoice number).
- **SCD 0/1/2/3/6**. In this project, `dim_customer` uses SCD2 on plan and region.
- Surrogate vs natural vs canonical keys (`customer_key` from Phase 4).
- ER/3NF vs dimensional vs One Big Table vs Data Vault: one line each on *when* you'd choose it.
- **Bus matrix**: business processes × conformed dimensions.

## Deliverables
- `docs/01_modeling.md`
- `docs/diagrams/star-schema.md` (Mermaid erDiagram of the target marts)
- The bus matrix table in the doc

## Draft target marts
| Model | Grain | Type | Key dims |
|---|---|---|---|
| `fct_shipments` | 1 row per shipment | transaction | customer, carrier, lane, date(booked), date(delivered) |
| `fct_shipment_lifecycle` | 1 row per shipment, updated as milestones arrive | accumulating snapshot | same |
| `fct_invoice_lines` | 1 row per invoice line | transaction | customer, plan, date(issued), date(due) |
| `fct_payments` | 1 row per successful payment | transaction | customer, invoice, method |
| `fct_customer_monthly` | 1 row per customer per month | periodic snapshot | customer, month |
| `dim_customer` | 1 row per customer version (SCD2) | dimension | canonical across products |

## 🧭 Checkpoints
1. Grain of the shipments fact: shipment vs shipment-event (or both)?
2. Is `dim_customer` SCD2, and on which attributes?
3. Should we add a wide OBT (`obt_customer_360`) for AI/NL consumers, or let the semantic layer handle the joins?

## 🧠 Quiz 1: 6 questions (grain, fact types, semi-additivity, SCD2, conformed dims, OBT trade-off)
