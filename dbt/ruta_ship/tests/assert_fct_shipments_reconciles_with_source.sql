-- Reconciliation test: the safety net for the incremental lookback (decision 1A).
-- Any shipment whose source state is newer than the fact's copy was missed by the incremental filter
-- (a late arrival older than watermark - lookback). Fix: `dbt build --full-refresh -s fct_shipments`.
{{ config(severity='warn', store_failures=true) }}

select s.shipment_id, s.updated_at as source_updated_at, f.updated_at as fact_updated_at
from {{ ref('stg_ship__shipments') }} s
left join {{ ref('fct_shipments') }} f using (shipment_id)
where f.shipment_id is null or s.updated_at > f.updated_at
