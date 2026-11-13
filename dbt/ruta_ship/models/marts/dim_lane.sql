{{ config(materialized='table') }}
select lane_id, origin_region, dest_region, distance_km from {{ ref('stg_ship__lanes') }}
