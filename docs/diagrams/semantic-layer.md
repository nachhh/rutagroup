# Semantic layer (Phase 5)

Entities are the join graph. Facts point to `customer`; `dim_customer` is an SCD2 semantic model (natural entity +
validity window), so MetricFlow joins each fact row to the customer version valid at `metric_time`.

```mermaid
flowchart LR
  subgraph facts[Fact semantic models]
    rev[fct_revenue<br/>total_revenue]
    shp[fct_udl_shipments<br/>gmv · booking_fees · shipments<br/>delivered · on_time · first_bookings]
    mon[fct_customer_monthly<br/>active_customers · mrr semi-additive<br/>subscribers · cancellations · churned]
    enr[fct_product_enrollment<br/>pay_enrollments]
  end
  cust{{customer<br/>dim_customer SCD2<br/>region · plan · tier · is_multi_product}}
  rev -- customer --> cust
  shp -- customer --> cust
  mon -- customer --> cust
  enr -- customer --> cust
  spine[(metricflow_time_spine)] -. metric_time .- rev
  spine -. metric_time .- shp
  spine -. metric_time .- mon

  subgraph metrics[Cross-model metrics]
    tr[take_rate · on_time_delivery_rate<br/>ratio]
    ch[subscription_churn_rate · customer_churn_rate<br/>ratio]
    rpc[revenue_per_customer · revenue_qoq_growth<br/>derived / offset]
    t90[trailing_90d_revenue<br/>cumulative]
    cv[ship_to_pay_conversion<br/>conversion]
  end
  shp --> tr
  mon --> ch
  rev --> rpc
  mon --> rpc
  rev --> t90
  shp --> cv
  enr --> cv

  metrics --> sq[saved queries<br/>multi_product_revenue_by_region<br/>churn_by_segment]
  sq --> consumers([BI · API · MCP agent Phase 6])
```

How a cross-model query compiles (`--explain`): each metric is aggregated **in its own subquery** at the requested
grain (with the SCD2 as-of join), then the subqueries are FULL OUTER JOINed on the group-by keys. No fan-out.
