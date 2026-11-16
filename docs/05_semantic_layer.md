# 05: Semantic layer with dbt and MetricFlow

Define each metric **once**, as a recipe (what to aggregate, how it joins, which time axis), and let an engine write
the SQL for whatever slice is asked. Spec: [phase-5](../specs/phase-5-semantic-layer.md).
Diagram: [semantic layer](diagrams/semantic-layer.md).

## 1. The business question, one query

```bash
make semantic        # = mf query --saved-query multi_product_revenue_by_region (+ churn_by_segment)
```

| Finding (2026-Q2) | Multi-product | Single-product |
|---|---|---|
| Revenue per active customer (EUR), by region | ≈ 2,900–3,800 | ≈ 1,550–1,800 |
| `customer_churn_rate` (gone ≥ 90 days from both products), by region | ≈ 0–2.5% | ≈ 6–11% |
| `subscription_churn_rate` (RutaPay cancels) | 2.7% | 6.4% |

One governed definition per number. BI, the API and the agent (Phase 6) all get the same answer.

## 2. Building blocks

| Concept | Meaning | Here |
|---|---|---|
| Semantic model | Metadata on one dbt model: entities, dimensions, metrics | 5 models in `marts/udl/_udl.yml` |
| Entity | Join key with a role: primary, foreign, natural (SCD2) | `customer` everywhere; `shipment`, `revenue_item` |
| Dimension | Categorical or time (with native `granularity`) | `region`, `revenue_type`, `revenue_date` |
| `agg_time_dimension` → `metric_time` | Each metric's own date, mapped to one shared time axis | revenue on `revenue_date`, shipments on `booked_at` |
| Time spine | One row per day; needed for cumulative windows, offsets, filling gaps | `metricflow_time_spine` |
| Simple metric (ex-"measure") | `agg` + `expr` over one model's columns | `total_revenue = sum(amount_eur)` |
| Saved query | A named, versioned metric request (exports can materialize it) | `_saved_queries.yml` |

**Entities are the join graph.** That's the overlap with the ontology (Phase 4): `customer` ≈ the class Customer,
and foreign → primary/natural entity links ≈ relations. The ontology says what things *mean*; entities say how
to *join* them for aggregation.

## 3. One metric per type

| Type | Metric | What MetricFlow does for you |
|---|---|---|
| simple | `total_revenue`, `gmv`, `active_customers` | Aggregates at any grain/dimension |
| simple, **semi-additive** | `mrr` (`non_additive_dimension: activity_month, window_agg: max`) | For a quarter it takes the **last month**, not the sum of three |
| ratio | `take_rate`, `on_time_delivery_rate`, both churn rates | Sums numerator and denominator **separately**, then divides (never avg of ratios) |
| derived | `revenue_per_customer` | Expression over metrics from **different** semantic models |
| derived + offset | `revenue_qoq_growth` | The same metric shifted one quarter (time spine join) |
| cumulative | `trailing_90d_revenue` | Rolling window over the spine |
| conversion | `ship_to_pay_conversion` | Per customer: first booking → RutaPay enrollment within 90 days (a **funnel**, not FX!) |

## 4. Why not just views?

1. **One definition, any grain:** a view freezes one grain and one set of joins; `total_revenue` works by month,
   region, plan, customer, carrier…
2. **No fan-out:** `--explain` shows each metric aggregated in its own subquery, then FULL OUTER JOINed on the
   group-by keys. Hand-written joins of revenue lines to monthly rows double-count.
3. **Time handling:** grains, offsets, cumulative windows, semi-additive logic, and SCD2 as-of joins are generated.
4. **A metadata API:** metrics, dimensions and descriptions are discoverable (`mf list metrics`, the dbt SL APIs),
   which is what an agent needs (Phase 6).

## 5. Decisions

- **1A, latest YAML spec** (dbt Core 1.12): semantics inline on the model. Legacy ↔ latest mapping:

| Legacy | Latest |
|---|---|
| top-level `semantic_models:` with `model: ref(...)` | `semantic_model: {enabled: true}` under the model |
| `entities:` / `dimensions:` lists | `entity:` / `dimension:` on each column |
| `type_params: {time_granularity: day}` | `granularity: day` on the column |
| `defaults: {agg_time_dimension}` | `agg_time_dimension` on the model |
| `measures:` + `type: simple, type_params: {measure}` | `metrics: - type: simple, agg, expr` (measures gone) |
| `type_params: {numerator, denominator}` | `numerator`, `denominator` |
| derived `type_params.metrics` | `input_metrics` |
| cumulative `type_params.measure` + `cumulative_type_params` | `input_metric`, `window`, `grain_to_date`, `period_agg` |
| conversion `base_measure` / `conversion_measure` | `base_metric` / `conversion_metric` |

  Limitation: cross-project refs (dbt Mesh) are legacy-only for now.
- **2A, revenue rules in the fact:** `fct_revenue` excludes void and pass-through lines and converts to EUR row by row;
  the semantic layer only aggregates. **Measures can only reference their own model's columns:** a joined FX rate
  can feed a dimension, never a row-level calculation inside a measure.
- **3C, two churn metrics, never a bare "churn":** `subscription_churn_rate` (RutaPay view) and `customer_churn_rate`
  (gone from both products ≥ 90 days; only the UDL can compute it). Right-censored months (too close to today to
  judge) count as not churned.

## 6. Gotchas found

| Symptom | Cause | Fix |
|---|---|---|
| Null `customer__region` row | SCD2 as-of join at day/month grain: activity dated before the first version (e.g. 1st of month vs a mid-month start) | First version opens at `1900-01-01` |
| `TIMESTAMP` vs `DATETIME` errors on BigQuery | MetricFlow truncates `DATE` metric_time to `DATETIME` and casts conversion windows to `DATETIME` | Convention: semantic time columns are `DATE` or UTC `DATETIME` |
| Conversion metric filter not resolved | metricflow 0.213 can't resolve a metric `filter:` inside a conversion | Model the event: a time column that is null for non-events |
| Conversion rate 0.03% | Base event = every shipment (repeat shippers) | Base event = customer's **first** booking (`first_booked_at`) |
| `mrr` = 0 in the latest quarter | Semi-additive takes the last month, which is incomplete | Query closed periods only |
| `revenue_qoq_growth` −66% | Partial current quarter | Same: closed periods |
| `trailing_90d_revenue` row in 2027 | Cumulative windows keep rolling over the spine | Bound the query with `--end-time` |
| `mf` shows stale errors | `mf` reads `target/semantic_manifest.json` | `dbt parse` before `mf` (`make mf` does) |
| `month` rejected as a name | Time grain names are reserved | Dimension renamed `activity_month` |

## 7. MetricFlow vs the dbt Semantic Layer, and the landscape

- **MetricFlow** = the open-source engine (YAML → SQL). We run it locally with `mf`.
- **dbt Semantic Layer** = the hosted dbt platform service around it: JDBC/ADBC and GraphQL APIs, caching, BI
  integrations (Tableau, Sheets, Hex…), exports, and a metadata API. "Headless BI": metrics as an API, any front end.
- **LookML** (Looker): views and explores, strong but tied to the BI tool.
- **Cube**: headless, pre-aggregations, SQL/REST/GraphQL APIs; popular for embedded analytics.
- **AtScale**: an enterprise semantic layer, OLAP-style.
- **Warehouse-native**: Snowflake semantic views, Databricks metric views. The definitions live in the warehouse.
- **Open Semantic Interchange (OSI)**: an industry effort (Snowflake, dbt Labs, Salesforce and others) to make one
  semantic spec portable across tools. dbt 1.12 already writes `target/osi_document.json` and warns about what OSI
  can't express yet (natural/SCD entities, cumulative windows, conversion metrics).
