{#-
  grain: 1 row per RutaShip shipment, re-keyed to the canonical customer (UDL conformed fact).
  Why a new model instead of reusing ship_replica.fct_shipments? MetricFlow joins on ENTITIES; the replica only
  knows shipper_id. Here every shipment carries customer_key (crosswalk), so `gmv by customer__region` or
  `ship_to_pay_conversion` can join to the rest of the UDL. Money in EUR at the month-average rate (as fct_revenue).
  booked_at is a UTC DATETIME (not TIMESTAMP): metricflow 0.213's BigQuery conversion-window SQL mixes TIMESTAMP and
  CAST(... AS DATETIME), so both event times of a conversion metric must be DATETIME.
-#}
{{ config(
    materialized='table',
    partition_by={'field': 'booked_date', 'data_type': 'date', 'granularity': 'month'},
    cluster_by=['customer_key', 'carrier_id'],
) }}

select
    s.shipment_id,
    x.customer_key,
    s.carrier_id,
    s.lane_id,
    s.status,
    datetime(s.booked_at)                                       as booked_at,   -- UTC DATETIME: see note below
    s.booked_date,
    s.currency,
    round(s.gmv_amount / fx.rate_per_eur, 2)                    as gmv_eur,
    round(s.booking_fee / fx.rate_per_eur, 2)                   as booking_fee_eur,
    s.delivered_at is not null                                  as is_delivered,
    coalesce(s.is_on_time, false)                               as is_on_time,
    -- Event time of the customer's FIRST booking (null otherwise): base event of ship_to_pay_conversion.
    -- QUALIFY-free: a window MIN compared row by row keeps the 1-row-per-shipment grain.
    if(s.booked_at = min(s.booked_at) over (partition by x.customer_key), datetime(s.booked_at), null) as first_booked_at
from {{ ref('stg_ship__shipments') }} s
join {{ ref('int_customer_xwalk') }} x
  on x.source_system = 'ship' and x.source_id = cast(s.shipper_id as string)
left join {{ ref('seed_fx_rates_monthly') }} fx
  on fx.currency = s.currency and fx.month = date_trunc(s.booked_date, month)
where s.status != 'cancelled'      -- same scope as fct_revenue's booking fees: take_rate compares like with like
