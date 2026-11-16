{#-
  grain: 1 row per customer per month with activity (PERIODIC SNAPSHOT).
  mrr_eur is SEMI-ADDITIVE: sum across customers, never across months (MetricFlow: non_additive_dimension, Phase 5).
  is_multi_product_active = used BOTH products in that month (time-aware), unlike dim_customer.is_multi_product
  (ever enrolled in both).
  Churn flags (Phase 5, decision 3C): two NAMED definitions, computed row-level here, aggregated by MetricFlow.
    * is_subscription_cancelled: a RutaPay cancel event happened this month (subscription churn).
    * is_customer_churned: this is a last-active month followed by ≥ 90 days without revenue or shipments in EITHER
      product (customer churn; only the UDL can see it). A customer who comes back later can churn again.
      Months too close to the data horizon can't be judged yet → false (right-censoring).
-#}
{{ config(materialized='table', cluster_by=['customer_key']) }}

with rev as (
    select
        customer_key,
        date_trunc(revenue_date, month)                                 as month,
        sum(amount_eur)                                                 as revenue_eur,
        sum(if(revenue_type = 'subscription', amount_eur, 0))           as mrr_eur,
        sum(if(source_system = 'ship', amount_eur, 0))                  as ship_revenue_eur,
        sum(if(source_system = 'pay', amount_eur, 0))                   as pay_revenue_eur
    from {{ ref('fct_revenue') }}
    group by 1, 2
),

shp as (
    select
        x.customer_key,
        date_trunc(s.booked_date, month)                                as month,
        count(*)                                                        as shipments,
        round(sum(s.gmv_amount / fx.rate_per_eur), 2)                   as gmv_eur
    from {{ ref('stg_ship__shipments') }} s
    join {{ ref('int_customer_xwalk') }} x on x.source_system = 'ship' and x.source_id = cast(s.shipper_id as string)
    left join {{ ref('seed_fx_rates_monthly') }} fx on fx.currency = s.currency and fx.month = date_trunc(s.booked_date, month)
    where s.status != 'cancelled'
    group by 1, 2
),

cxl as (
    select
        x.customer_key,
        date_trunc(date(s.valid_from), month)                           as month,
        true                                                            as is_subscription_cancelled
    from {{ ref('int_subscriptions_scd2') }} s
    join {{ ref('int_customer_xwalk') }} x on x.source_system = 'pay' and x.source_id = s.account_id
    where s.subscription_status = 'cancelled'
    group by 1, 2
),

monthly as (
    select
        customer_key,
        month,
        coalesce(rev.revenue_eur, 0)                    as revenue_eur,
        coalesce(rev.mrr_eur, 0)                        as mrr_eur,
        coalesce(rev.ship_revenue_eur, 0)               as ship_revenue_eur,
        coalesce(rev.pay_revenue_eur, 0)                as pay_revenue_eur,
        coalesce(shp.shipments, 0)                      as shipments,
        coalesce(shp.gmv_eur, 0)                        as gmv_eur,
        coalesce(cxl.is_subscription_cancelled, false)  as is_subscription_cancelled
    from rev
    full join shp using (customer_key, month)           -- FULL JOIN ... USING coalesces the key columns
    full join cxl using (customer_key, month)
),

activity as (
    select
        *,
        revenue_eur > 0 or shipments > 0                                                    as is_active,
        -- next ACTIVE month of the same customer (a cancel-only row isn't activity)
        min(if(revenue_eur > 0 or shipments > 0, month, null)) over (
            partition by customer_key order by month
            rows between 1 following and unbounded following)                               as next_active_month,
        max(month) over ()                                                                  as horizon_month
    from monthly
)

select
    customer_key,
    month,
    revenue_eur,
    mrr_eur,
    ship_revenue_eur,
    pay_revenue_eur,
    shipments,
    gmv_eur,
    ship_revenue_eur > 0 and pay_revenue_eur > 0                                as is_multi_product_active,
    is_active,
    mrr_eur > 0                                                                 as is_subscriber,
    is_subscription_cancelled,
    -- gap to the next active month ≥ 90 days after this month ends; or no next month and the horizon is ≥ 90 days away
    coalesce(is_active and date_diff(
        coalesce(next_active_month, if(date_diff(last_day(horizon_month), last_day(month), day) >= 90, date '9999-12-01', null)),
        last_day(month), day) > 90, false)                                      as is_customer_churned   -- null (censored) → false
from activity
