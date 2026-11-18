-- Reconciliation test: the safety net for the incremental lookback (decision 1A).
-- Checks BOTH inputs of fct_shipments: a shipment whose source row is newer than the fact's copy, or
-- whose event-derived columns differ from the events now, was missed by the incremental filter
-- (a late arrival older than watermark - lookback). Fix: `dbt build --full-refresh -s fct_shipments`.
{{ config(severity='warn', store_failures=true) }}

select s.shipment_id, s.updated_at as source_updated_at, f.updated_at as fact_updated_at,
       e.delivered_at as events_delivered_at, f.delivered_at as fact_delivered_at
from {{ ref('stg_ship__shipments') }} s
left join {{ ref('fct_shipments') }} f using (shipment_id)
left join {{ ref('int_shipment_event_rollup') }} e using (shipment_id)
where f.shipment_id is null
   or s.updated_at > f.updated_at
   or f.delivered_at is distinct from e.delivered_at
   or f.had_exception is distinct from coalesce(e.had_exception, false)
