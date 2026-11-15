{#-
  grain: 1 row per customer per month with activity (PERIODIC SNAPSHOT).
  mrr_eur is SEMI-ADDITIVE: sum across customers, never across months (MetricFlow: non_additive_dimension, Phase 5).
  is_multi_product_active = used BOTH products in that month (time-aware), unlike dim_customer.is_multi_product
  (ever enrolled in both).
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
)

select
    customer_key,
    month,                                              -- FULL JOIN ... USING coalesces the key columns
    coalesce(rev.revenue_eur, 0)                        as revenue_eur,
    coalesce(rev.mrr_eur, 0)                            as mrr_eur,
    coalesce(rev.ship_revenue_eur, 0)                   as ship_revenue_eur,
    coalesce(rev.pay_revenue_eur, 0)                    as pay_revenue_eur,
    coalesce(shp.shipments, 0)                          as shipments,
    coalesce(shp.gmv_eur, 0)                            as gmv_eur,
    coalesce(rev.ship_revenue_eur, 0) > 0 and coalesce(rev.pay_revenue_eur, 0) > 0 as is_multi_product_active
from rev
full join shp using (customer_key, month)
