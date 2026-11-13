{#-
  grain: 1 row per invoice that has payment activity (latest outcome). Rows CHANGE (failed → paid, refunds).

  INCREMENTAL / MERGE on invoice_id, same pattern as the accumulating snapshot (Quiz 1 Q5):
    1. find invoices touched by new events (watermark on received_at + 3-day lookback),
    2. RECOMPUTE their row from ALL their events (no partial counts from only the new events),
    3. MERGE.
-#}
{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    on_schema_change='append_new_columns',
    unique_key='invoice_id',
    cluster_by=['account_id'],
) }}

with events as (
    select * from {{ ref('stg_pay__payment_events') }}
),

{% if is_incremental() %}
touched as (
    select distinct invoice_id from events
    where received_at > (select max(last_event_at) from {{ this }}) - interval 3 day
),
{% endif %}

per_invoice as (
    select
        invoice_id,
        countif(event_type = 'payment.failed')                                  as failed_attempts,
        min(if(event_type = 'payment.succeeded', received_at, null))           as paid_at,
        max(if(event_type = 'payment.succeeded', amount, null))                as amount_paid,
        sum(amount_refunded)                                                   as amount_refunded,
        -- latest non-null payment method: ARRAY_AGG with IGNORE NULLS + ORDER BY + LIMIT 1
        array_agg(method_type ignore nulls order by received_at desc limit 1)[safe_offset(0)] as method_type,
        max(received_at)                                                       as last_event_at
    from events
    {% if is_incremental() %} where invoice_id in (select invoice_id from touched) {% endif %}
    group by invoice_id
)

select
    p.invoice_id,
    i.account_id,
    i.currency,
    i.due_date,
    p.paid_at,
    date(p.paid_at)                                    as paid_date,
    p.paid_at is not null                              as is_paid,
    date(p.paid_at) > i.due_date                       as is_late,
    p.failed_attempts,
    p.amount_paid,
    p.amount_refunded,
    p.method_type,
    p.last_event_at
from per_invoice p
join {{ ref('stg_pay__invoices') }} i using (invoice_id)
