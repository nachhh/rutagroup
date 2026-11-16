# Phase 5: dbt Semantic Layer / MetricFlow (⏱ 1.25 h), *the centerpiece*

## Goal
Answer the business question with **one governed metric query**, and understand what MetricFlow does that a view can't.

## 🧭 Decisions (settled)
1. **YAML spec (A): the latest spec** (dbt Core 1.12, verified with local `mf`): semantic metadata lives in the model's
   YAML (`semantic_model: {enabled: true}`, `agg_time_dimension`, `entity:` / `dimension:` / `granularity` on columns,
   `metrics:` of `type: simple` with `agg`/`expr` instead of measures). Cross-model metrics go under top-level `metrics:`.
   `docs/05_semantic_layer.md` keeps a legacy ↔ latest mapping table (most production projects still use legacy).
2. **Revenue rules (A):** row-level rules stay in `fct_revenue` (void + pass-through excluded, EUR at month-average rate);
   the semantic layer only aggregates: `total_revenue = sum(amount_eur)` is therefore a **simple** metric. Derived
   examples become `revenue_per_customer` and `revenue_qoq_growth` (offset window).
3. **Churn (C): two named metrics, never a bare "churn".**
   - `subscription_churn_rate` = subscription cancellations in the period / customers subscribed in the period (RutaPay view).
   - `customer_churn_rate` = customers whose last activity (revenue or shipment, either product) falls in the period and
     who then stay inactive ≥ 90 days / customers active in the period (UDL-only view).
   Flags are computed row-level in `fct_customer_monthly`; MetricFlow aggregates them.

## Files
Semantic metadata sits next to each model (latest spec). New files:

| File | Content |
|---|---|
| `models/semantic/metricflow_time_spine.sql` + `_time_spine.yml` | Daily spine (`GENERATE_DATE_ARRAY`), `time_spine: standard_granularity_column` |
| `models/marts/udl/fct_udl_shipments.sql` | NEW public mart, grain shipment: `customer_key` (crosswalk), carrier, lane, status, `gmv_eur`, `booking_fee_eur`, `is_delivered`, `is_on_time` (MetricFlow needs a model with `customer_key`; the replica only has `shipper_id`) |
| `models/semantic/_metrics.yml` | Cross-model metrics (ratio / derived / cumulative / conversion) |
| `models/semantic/_saved_queries.yml` | `multi_product_revenue_by_region`, `churn_by_segment` |

Semantic models (in `marts/udl/_udl.yml`):

| Model | Entities | Dimensions | Simple metrics |
|---|---|---|---|
| `dim_customer` (SCD2) | `customer` (**natural**, validity window `valid_from`/`valid_to`) | `region`, `plan_code`, `ship_tier`, `subscription_status`, `is_multi_product` | none (dimension-only) |
| `fct_revenue` | `revenue_item` (primary), `customer` (foreign) | `revenue_type`, `source_system`, `revenue_date` (time) | `total_revenue` |
| `fct_udl_shipments` | `shipment` (primary), `customer`, `carrier`, `lane` (foreign) | `status`, `booked_at` (time) | `gmv`, `booking_fees`, `shipments`, `delivered_shipments`, `on_time_shipments` |
| `fct_customer_monthly` | `customer_month` (primary_entity), `customer` (foreign) | `month` (time) | `active_customers` (count_distinct), `mrr` (semi-additive: `non_additive_dimension: month, window_agg: max`), `subscribers`, `subscription_cancellations`, `churned_customers` |
| `fct_product_enrollment` | `customer` (foreign) | `product`, `enrolled_at` (time) | `pay_enrollments` (filtered) |

## Metrics, one per type
| Metric | Type | Definition |
|---|---|---|
| `total_revenue`, `gmv`, `shipments`, `active_customers` | simple | |
| `mrr` | simple, semi-additive | last month of the period, summed across customers |
| `take_rate` | ratio | booking_fees / gmv |
| `on_time_delivery_rate` | ratio | on_time_shipments / delivered_shipments |
| `subscription_churn_rate`, `customer_churn_rate` | ratio | see decision 3 |
| `revenue_per_customer` | derived | total_revenue / active_customers |
| `revenue_qoq_growth` | derived + offset | (revenue − revenue 1 quarter ago) / revenue 1 quarter ago |
| `trailing_90d_revenue` | cumulative | window 90 days |
| `ship_to_pay_conversion` | conversion | customer books a shipment → enrolls in RutaPay within 90 days |

## Commands to run and inspect
```bash
mf validate-configs
mf list metrics
mf query --metrics total_revenue,customer_churn_rate --group-by customer__is_multi_product,customer__region,metric_time__quarter
mf query ... --explain        # read the generated SQL: entity join paths, fan-out protection, time spine joins
```

## Status log
- ✅ Latest YAML spec verified on dbt Core 1.12.6 + metricflow 0.213 (`mf validate-configs` all green, every metric executed).
- ✅ New public mart `fct_udl_shipments`; `fct_customer_monthly` gains churn/subscription flags; `fct_product_enrollment`
  gains `pay_enrolled_at`; `dim_customer` is an SCD2 semantic model (natural entity + validity_params).
- ✅ Business question answered by one saved query (`multi_product_revenue_by_region`): multi-product ≈ 2× revenue per
  customer, customer churn ≈ 0–2.5% vs 6–11% single-product.
- ⚠️ Gotchas (see docs §6): SCD2 first version must open at 1900-01-01; BigQuery TIMESTAMP vs DATETIME in MetricFlow SQL
  (convention: semantic time columns DATE or UTC DATETIME); metric filters don't resolve inside conversion metrics;
  conversion inputs must be COUNT(1)/COUNT_DISTINCT; `month` is a reserved name; dbt 1.12 also emits an OSI document.

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

## 🧭 Checkpoints (original)
1. Where the "revenue" definition lives (fact vs metric layer), and the currency handling → decision 2
2. Churn definition (no activity in either product for N days? subscription cancel?) → decision 3
3. (added) Latest vs legacy YAML spec → decision 1

## 🧠 Quiz 5: 4 questions, done (2026-11-15)
Topics: why not a view (fan-out), semi-additive MRR, ratio vs average of ratios, the two churn metrics + censoring.
Results in `quizzes/` (gitignored).
