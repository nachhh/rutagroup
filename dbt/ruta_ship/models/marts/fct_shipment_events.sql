{#-
  grain: 1 row per tracking event. Immutable → INCREMENTAL APPEND (insert-only, no unique_key).

  ⚠️ Append + a time-based lookback would DUPLICATE rows (re-inserting events already loaded).
  So the watermark here is the monotonically increasing event_id, not event_ts. Late events still get
  a new, higher event_id when they land, so they're picked up even if their event_ts is old.

  Alternative (dbt ≥ 1.9): incremental_strategy='microbatch' with event_time='event_ts', batch_size='day':
  dbt processes one day per batch, retries failed batches, and backfills with --event-time-start/end.
-#}
{{ config(
    materialized='incremental',
    incremental_strategy='append',
    indexes=[{'columns': ['event_id'], 'unique': True}, {'columns': ['event_ts'], 'type': 'brin'}],
) }}

select
    event_id,
    shipment_id,
    event_type,
    event_ts,
    current_timestamp as _dbt_loaded_at
from {{ ref('stg_ship__shipment_events') }}
{% if is_incremental() %}
where event_id > (select coalesce(max(event_id), 0) from {{ this }})
{% endif %}
