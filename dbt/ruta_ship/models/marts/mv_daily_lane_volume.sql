-- MATERIALIZED VIEW: the database stores the result and refreshes it (Postgres: REFRESH MATERIALIZED
-- VIEW, which dbt issues on each run). Trade-offs vs a dbt table: engine-managed, but limited SQL support
-- and refresh semantics differ by engine (Redshift supports AUTO REFRESH; BigQuery MVs refresh
-- incrementally with strict SQL restrictions).
{{ config(materialized='materialized_view') }}

select
    s.booked_date,
    l.origin_region,
    l.dest_region,
    count(*)            as shipments,
    sum(s.gmv_amount)   as gmv_local     -- mixed currencies! fine for volume, NOT for money: see Phase 4 FX
from {{ ref('stg_ship__shipments') }} s
join {{ ref('stg_ship__lanes') }} l using (lane_id)
group by 1, 2, 3
