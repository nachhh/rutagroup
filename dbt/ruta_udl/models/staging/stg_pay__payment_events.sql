-- grain: 1 row per DISTINCT webhook event (source has ~3% redelivered duplicates).
select
    event_id,
    received_at,
    json_value(payload, '$.type')                                   as event_type,
    json_value(payload, '$.data.invoice_id')                        as invoice_id,
    safe_cast(json_value(payload, '$.data.amount') as numeric)      as amount,
    json_value(payload, '$.data.currency')                          as currency,
    json_value(payload, '$.data.method.type')                       as method_type,
    json_value(payload, '$.data.method.brand')                      as card_brand,
    json_value(payload, '$.data.failure.code')                      as failure_code,
    -- JSON array → SQL array: JSON_QUERY_ARRAY returns ARRAY<JSON>; UNNEST it in a scalar subquery to aggregate
    (select coalesce(sum(safe_cast(json_value(r, '$.amount') as numeric)), 0)
       from unnest(json_query_array(payload, '$.data.refunds')) as r) as amount_refunded,
    array_length(json_query_array(payload, '$.data.refunds'))       as refund_count
from {{ source('raw_pay', 'payment_events') }}
-- QUALIFY filters on a window function without a wrapping subquery. Keep the FIRST delivery of each event_id
-- (its received_at is the true event time; redeliveries carry the same payload later).
qualify row_number() over (partition by event_id order by received_at) = 1
