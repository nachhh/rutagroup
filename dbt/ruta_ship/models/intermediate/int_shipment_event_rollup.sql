-- materialized: ephemeral (project default for intermediate/) → no object is created; dbt inlines
-- this as a CTE wherever it's ref'd. Good for reusable logic that isn't worth a table.
-- grain: 1 row per shipment that has events
select
    shipment_id,
    min(event_ts) filter (where event_type = 'booked')     as booked_event_at,
    min(event_ts) filter (where event_type = 'picked_up')  as picked_up_at,
    max(event_ts) filter (where event_type = 'delivered')  as delivered_at,
    max(event_ts) filter (where event_type = 'cancelled')  as cancelled_at,
    bool_or(event_type = 'exception')                      as had_exception,   -- Quiz 1 Q2: flag at the fact's grain
    count(*)                                               as event_count,
    max(event_ts)                                          as last_event_at
from {{ ref('stg_ship__shipment_events') }}
group by shipment_id
