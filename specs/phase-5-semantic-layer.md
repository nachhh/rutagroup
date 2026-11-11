# Phase 5: dbt Semantic Layer / MetricFlow (⏱ 1.25 h), *the centerpiece*

## Goal
Answer the business question with **one governed metric query**, and understand what MetricFlow does that a view can't.

## Files (in `dbt/ruta_udl/models/semantic/`)
| File | Content |
|---|---|
| `metricflow_time_spine.sql` + yml | Daily spine (`GENERATE_DATE_ARRAY`), required by MetricFlow |
| `sem_customers.yml` | Semantic model on `dim_customer`. Entity `customer` (primary). Dims: `region`, `plan`, `is_multi_product`, `first_seen_at` (time) |
| `sem_shipments.yml` | On `fct_shipments`. Entities: `shipment` (primary), `customer` (foreign), `carrier`. Measures: `gmv` (sum), `booking_fee` (sum), `shipments` (count), `on_time_shipments` (sum of a boolean→int expr). Time dim `booked_at` |
| `sem_revenue.yml` | On `fct_revenue`. Measure `revenue` (sum), dim `revenue_type`, `product` |
| `sem_customer_monthly.yml` | Semi-additive measure `mrr` (`non_additive_dimension: month, window_choice: max`) |
| `metrics.yml` | Metric definitions (below) |
| `saved_queries.yml` | `multi_product_revenue_by_region`, `churn_by_segment` |

## Metrics, one per type
| Metric | Type | Definition |
|---|---|---|
| `gmv`, `revenue`, `shipments` | simple | |
| `take_rate` | ratio | booking_fee / gmv |
| `on_time_delivery_rate` | ratio | on_time_shipments / delivered_shipments |
| `total_revenue` | derived | ship booking fees + pay revenue, the **unified metric** |
| `revenue_per_customer` | derived | total_revenue / active_customers |
| `trailing_90d_revenue` | cumulative | window 90 days |
| `mrr` | simple over a semi-additive measure | |
| `ship_to_pay_conversion` | conversion | shipper books → becomes a Pay customer within 90 days |
| `churned_customers` / `churn_rate` | simple + ratio, with metric-level `filter` | |

## Commands to run and inspect
```bash
mf validate-configs
mf list metrics
mf query --metrics total_revenue,churn_rate --group-by customer__is_multi_product,customer__region,metric_time__quarter --order -total_revenue
mf query ... --explain        # read the generated SQL: entity join paths, fan-out protection, time spine joins
```

## Concepts → `docs/05_semantic_layer.md`
- Semantic model = entities (join keys) + dimensions + measures. **Entities are the join graph**
  (that's where the overlap with ontologies sits).
- Why not just views: one definition reused across grains/dims, correct joins without fan-out,
  time-grain handling, semi-additive logic, and a metadata API for tools/agents.
- **MetricFlow (open-source engine) vs dbt Semantic Layer (hosted dbt Cloud: JDBC/ADBC + GraphQL
  APIs, caching, BI integrations, exports)**. We run the engine locally.
- Comparison: **LookML** (Looker, explores/views, tied to the BI tool), **Cube** (headless,
  pre-aggregations, SQL/REST/GraphQL APIs), **AtScale**, **Snowflake/Databricks native metric views**,
  and the **Open Semantic Interchange (OSI)** effort to standardize specs.
- Headless BI and "metrics as an API".

## Acceptance criteria
- The §1 business question is answered by a single `mf query` / saved query
- All metric types work. `--explain` SQL is reviewed together

## 🧭 Checkpoints
1. Where the "revenue" definition lives (fact vs metric layer), and the currency handling
2. Churn definition (no activity in either product for N days? subscription cancel?)

## 🧠 Quiz 5: 8 questions
