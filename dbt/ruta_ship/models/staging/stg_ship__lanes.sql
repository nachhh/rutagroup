select lane_id, origin_region, dest_region, distance_km from {{ source('raw_ship', 'lanes') }}
