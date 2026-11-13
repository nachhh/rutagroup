{{ config(materialized='table') }}
select carrier_id, carrier_name, mode from {{ ref('stg_ship__carriers') }}
