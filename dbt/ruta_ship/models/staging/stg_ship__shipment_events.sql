-- grain: 1 row per tracking event (immutable)
select event_id, shipment_id, event_type, event_ts
from {{ source('raw_ship', 'shipment_events') }}
