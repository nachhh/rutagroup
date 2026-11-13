select carrier_id, carrier_name, mode from {{ source('raw_ship', 'carriers') }}
