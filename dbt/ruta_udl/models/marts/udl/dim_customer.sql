{#-
  grain: 1 row per CANONICAL CUSTOMER VERSION (SCD2). The conformed dimension of the UDL.

  TIMELINE MERGE: a customer's history lives in two SCD2s with unrelated change dates
  (Ship: tier/region from the snapshot; Pay: plan from the change log). The merged dimension needs a new version
  whenever EITHER side changes:
    1. collect every change point from both sides,   2. turn consecutive points into [valid_from, valid_to),
    3. as-of join each side's version that is valid at the start of each interval.
  SCD policy (Phase 1): plan, tier, region = SCD2; current_region = type-6 "current value on every row";
  name, tax id = SCD1 (profile CTE).
  SURVIVORSHIP (golden record): name = RutaShip's (clean operational master) else RutaPay's legal name;
  region = RutaShip's history else RutaPay's primary-address region. A business decision, written down.
-#}
{{ config(materialized='table', cluster_by=['customer_key']) }}

with x as (select * from {{ ref('int_customer_xwalk') }}),

ship_v as (
    select x.customer_key, v.tier, v.region, v.valid_from, v.valid_to
    from {{ ref('stg_ship__shipper_versions') }} v
    join x on x.source_system = 'ship' and x.source_id = cast(v.shipper_id as string)
),

pay_v as (
    select x.customer_key, s.plan_code, s.subscription_status, s.valid_from, s.valid_to
    from {{ ref('int_subscriptions_scd2') }} s
    join x on x.source_system = 'pay' and x.source_id = s.account_id
),

pay_acct as (
    select x.customer_key, a.created_at, r.region as pay_region
    from {{ ref('stg_pay__accounts') }} a
    join x on x.source_system = 'pay' and x.source_id = a.account_id
    left join {{ ref('seed_region_map') }} r on r.country_code = a.primary_country
),

profile as (   -- SCD1 attributes + product enrollment, one row per customer
    select
        x.customer_key,
        coalesce(max(if(c.source_system = 'ship', c.raw_name, null)),
                 initcap(max(if(c.source_system = 'pay', c.raw_name, null))))           as customer_name,
        coalesce(max(if(c.source_system = 'ship', c.tax_id_norm, null)),
                 max(if(c.source_system = 'pay', c.tax_id_norm, null)))                 as tax_id_normalized,
        coalesce(max(if(c.source_system = 'ship', c.country, null)),
                 max(if(c.source_system = 'pay', c.country, null)))                     as country,
        safe_cast(max(if(x.source_system = 'ship', x.source_id, null)) as int64)        as shipper_id,
        max(if(x.source_system = 'pay', x.source_id, null))                             as account_id,
        array_agg(distinct x.source_system order by x.source_system)                    as products,   -- ARRAY<STRING>
        max(x.match_rule)                                                               as match_rule,
        min(x.confidence)                                                               as match_confidence
    from x
    join {{ ref('int_customer_candidates') }} c using (source_system, source_id)
    group by 1
),

change_points as (
    select customer_key, valid_from as ts from ship_v
    union distinct select customer_key, valid_from from pay_v
    union distinct select customer_key, created_at from pay_acct
),

intervals as (
    select
        customer_key,
        ts                                                                              as valid_from,
        coalesce(lead(ts) over (partition by customer_key order by ts), timestamp '9999-12-31') as valid_to
    from change_points
),

versions as (
    select
        i.customer_key,
        i.valid_from,
        i.valid_to,
        sv.tier                                         as ship_tier,
        coalesce(sv.region, pa.pay_region)              as region,
        pv.plan_code,
        pv.subscription_status
    from intervals i
    left join ship_v sv on sv.customer_key = i.customer_key and i.valid_from >= sv.valid_from and i.valid_from < sv.valid_to
    left join pay_v pv  on pv.customer_key = i.customer_key and i.valid_from >= pv.valid_from and i.valid_from < pv.valid_to
    left join pay_acct pa on pa.customer_key = i.customer_key
)

select
    farm_fingerprint(concat(cast(v.customer_key as string), '|', cast(v.valid_from as string))) as customer_sk,
    v.customer_key,
    p.customer_name,
    p.tax_id_normalized,
    p.country,
    v.region,
    first_value(v.region) over (partition by v.customer_key order by v.valid_from desc)  as current_region,
    v.ship_tier,
    v.plan_code,
    v.subscription_status,
    p.shipper_id,
    p.account_id,
    p.products,
    array_length(p.products) > 1                                                        as is_multi_product,
    p.match_rule,
    p.match_confidence,
    v.valid_from,
    v.valid_to,
    v.valid_to = timestamp '9999-12-31'                                                 as is_current
from versions v
join profile p using (customer_key)
