{#-
  grain: 1 row per SOURCE RECORD (shipper or account) → its match cluster. Stateless: recomputed every run.

  cluster_id = a deterministic anchor: the Pay account if matched/any, else the shipper. It identifies TODAY's
  cluster only; it is NOT the customer key (it changes when a ship-only customer later matches an account).
  Stable keys are assigned once in int_customer_key_registry: "recompute identity, persist keys".
-#}
with m as (select * from {{ ref('int_customer_matches') }}),
c as (select * from {{ ref('int_customer_candidates') }}),

ship as (
    select c.source_system, c.source_id, coalesce(concat('pay:', m.account_id), concat('ship:', c.source_id)) as cluster_id,
           coalesce(m.match_rule, 'unmatched') as match_rule, coalesce(m.confidence, 1.0) as confidence, m.decided_by
    from c left join m on m.shipper_id = c.source_id
    where c.source_system = 'ship'
),

pay as (
    select c.source_system, c.source_id, concat('pay:', c.source_id) as cluster_id,
           coalesce(m.match_rule, 'unmatched'), coalesce(m.confidence, 1.0), m.decided_by
    from c left join m on m.account_id = c.source_id
    where c.source_system = 'pay'
)

select * from ship
union all
select * from pay
