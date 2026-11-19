{#-
  grain: 1 row per RETIRED customer_key → the key that replaced it TODAY.
  For consumers that stored a key before a merge (BI filters, KG node ids, agent context, reverse-ETL):
    coalesce((select surviving_key from customer_key_aliases where retired_key = :k), :k)

  A key is retired when its records left it in a MERGE and nobody holds it anymore. surviving_key is the CURRENT
  key of those records, so chains (K1 → K2 → K3) resolve in one lookup: no recursion needed.
-#}
with registry as (
    select * from {{ ref('int_customer_key_registry') }}
),

current_key as (
    select source_system, source_id, customer_key
    from registry
    qualify row_number() over (partition by source_system, source_id order by assigned_at desc) = 1
)

select
    m.previous_key   as retired_key,
    c.customer_key   as surviving_key,
    m.assigned_at    as retired_at
from registry m
join current_key c using (source_system, source_id)
where m.reason = 'merge'
  and m.previous_key not in (select customer_key from current_key)   -- still held by someone → not retired
qualify row_number() over (partition by m.previous_key order by m.assigned_at desc) = 1
