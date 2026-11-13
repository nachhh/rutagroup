-- grain: 1 row per shipment (current status)
select
    shipment_id,
    shipper_id,
    carrier_id,
    lane_id,
    status,
    gmv_amount,
    booking_fee,
    currency,                 -- local currency; FX normalization happens in the UDL (Phase 4)
    booked_at,
    booked_at::date           as booked_date,
    promised_delivery_at,
    updated_at
from {{ source('raw_ship', 'shipments') }}
