{#-
  grain: 1 row per SOURCE RECORD (shipper or account) → its canonical customer_key. The CROSSWALK of the UDL:
  facts keep their source ids and get customer_key from here.

  customer_key comes from the persisted KEY REGISTRY (int_customer_key_registry), not from a hash computed on the
  fly: matching (int_customer_clusters) is recomputed every run, keys are assigned once and survive re-matching.
  Merges retire keys into customer_key_aliases so consumers holding an old key can resolve it.
-#}
with registry_current as (
    select source_system, source_id, customer_key
    from {{ ref('int_customer_key_registry') }}
    qualify row_number() over (partition by source_system, source_id order by assigned_at desc) = 1
)

select
    r.customer_key,
    c.source_system,
    c.source_id,
    c.match_rule,
    c.confidence,
    c.decided_by
from {{ ref('int_customer_clusters') }} c
join registry_current r using (source_system, source_id)   -- the registry ran first, so every present record has a key
