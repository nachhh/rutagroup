{#-
  grain: 1 row per SOURCE RECORD (shipper or account) → its canonical customer_key. The CROSSWALK of the UDL:
  facts keep their source ids and get customer_key from here.

  customer_key = FARM_FINGERPRINT of a deterministic anchor: the Pay account if any, else the shipper.
  ⚠️ Key stability: if a ship-only customer later matches an account, its anchor (and key) changes. Production fix:
     a persisted KEY REGISTRY (incremental table that assigns a key once and never reissues it; merges keep the
     surviving key and record the retired one).
-#}
with m as (select * from {{ ref('int_customer_matches') }}),
c as (select * from {{ ref('int_customer_candidates') }}),

ship as (
    select c.source_system, c.source_id, coalesce(concat('pay:', m.account_id), concat('ship:', c.source_id)) as anchor,
           coalesce(m.match_rule, 'unmatched') as match_rule, coalesce(m.confidence, 1.0) as confidence, m.decided_by
    from c left join m on m.shipper_id = c.source_id
    where c.source_system = 'ship'
),

pay as (
    select c.source_system, c.source_id, concat('pay:', c.source_id) as anchor,
           coalesce(m.match_rule, 'unmatched'), coalesce(m.confidence, 1.0), m.decided_by
    from c left join m on m.account_id = c.source_id
    where c.source_system = 'pay'
)

select
    farm_fingerprint(anchor)  as customer_key,
    source_system,
    source_id,
    match_rule,
    confidence,
    decided_by
from (select * from ship union all select * from pay)
