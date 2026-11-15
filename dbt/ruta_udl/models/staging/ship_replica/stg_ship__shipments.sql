-- grain: 1 row per shipment, from the replicated fct_shipments (already modeled upstream → thin staging).
select * except (_dbt_loaded_at, _replicated_at)
from {{ source('ship_replica', 'fct_shipments') }}
