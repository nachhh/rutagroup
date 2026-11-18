{#-
  grain: 1 row per shipment, current status. Transaction fact whose rows change (status updates).

  INCREMENTAL / MERGE (decision 1A):
    * unique_key + merge → upsert: changed shipments are updated, new ones inserted.
    * Lookback: re-read rows with updated_at > watermark - N days. N = worst expected INGESTION delay
      (late-arriving rows), NOT shipment duration. Rows arriving later than N days behind the watermark
      are missed → periodic `--full-refresh` + reconciliation tests (see tests/).
    * Best practice when available: filter on a load timestamp (_loaded_at) instead of a business one.
    * CHANGE DETECTION ON BOTH INPUTS: delivered_at / had_exception come from EVENTS, so a shipment is
      re-read if its own row changed OR it has new events. We don't assume the source bumps
      shipments.updated_at whenever an event lands: that breaks when the two tables replicate with
      different lag, when an event doesn't change the shipment row, or when a script bypasses updated_at.
      Both checks use the same SOURCE-clock watermark (max(updated_at)); comparing event_ts to
      _dbt_loaded_at (warehouse clock) would mix clocks.

  PHYSICAL DESIGN per engine:
    * Postgres (here): the contract's primary_key constraint on shipment_id creates the unique B-tree
      (the MERGE match) and is ENFORCED; BRIN on booked_date (tiny index for time-ordered data).
    * Redshift (real RutaShip): no indexes. Use  dist='shipper_id'  sort=['booked_date']
      (co-locate with shippers for joins; zone maps prune by date).
    * At scale, prune the MERGE target with incremental_predicates, e.g.
      incremental_predicates=["DBT_INTERNAL_DEST.booked_date >= current_date - 90"]
-#}
-- depends_on: {{ ref('stg_ship__shipment_events') }}
-- ↑ the events ref below lives only inside is_incremental(), so dbt can't see it at parse time; this hint
--   declares the edge (lineage + run order).
{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    unique_key='shipment_id',
    on_schema_change='append_new_columns',
    indexes=[{'columns': ['booked_date'], 'type': 'brin'}],
) }}

with shipments as (
    select * from {{ ref('stg_ship__shipments') }}
    {% if is_incremental() %}
    where updated_at > (select max(updated_at) from {{ this }}) - interval '{{ var("lookback_days", 3) }} days'
       or shipment_id in (                                   -- new events, even if the shipment row didn't change
            select shipment_id from {{ ref('stg_ship__shipment_events') }}
            where event_ts > (select max(updated_at) from {{ this }}) - interval '{{ var("lookback_days", 3) }} days')
    {% endif %}
)

select
    s.shipment_id,
    s.shipper_id,
    s.carrier_id,
    s.lane_id,
    s.status,
    s.gmv_amount,
    s.booking_fee,
    s.currency,
    s.booked_at,
    s.booked_date,
    s.promised_delivery_at,
    e.delivered_at,
    e.delivered_at::date                                     as delivered_date,
    coalesce(e.had_exception, false)                         as had_exception,
    case when e.delivered_at is not null
         then e.delivered_at <= s.promised_delivery_at end   as is_on_time,     -- null until delivered
    s.updated_at,
    current_timestamp                                        as _dbt_loaded_at  -- load timestamp for downstream incrementals
from shipments s
left join {{ ref('int_shipment_event_rollup') }} e using (shipment_id)
