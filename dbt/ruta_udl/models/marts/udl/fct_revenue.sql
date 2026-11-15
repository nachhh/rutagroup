{#-
  grain: 1 row per REVENUE-BEARING ITEM across both products (unified transaction fact).
    * Pay:  invoice lines of type subscription / txn_fee / freight_fee (void invoices excluded).
    * Ship: booking_fee per non-cancelled shipment, recognized at booking (accrual purists would use delivery).
  ⚠️ The Pay FREIGHT line is pass-through GMV collected for the carrier (already Ship GMV) → NOT revenue.
     Summing GMV across both products would double-count it.
  FX (decision 3A): amount_local + currency kept; amount_eur at the transaction month's AVERAGE rate.
  Rebuilt every run → seed rate changes propagate; `dbt build -s seed_fx_rates_monthly+` rebuilds exactly this.
-#}
{{ config(
    materialized='table',
    partition_by={'field': 'revenue_date', 'data_type': 'date', 'granularity': 'month'},
    cluster_by=['customer_key', 'revenue_type'],
) }}

with x as (select * from {{ ref('int_customer_xwalk') }}),

pay as (
    select
        concat('pay:', l.invoice_id, ':', cast(l.line_no as string))    as revenue_id,
        'pay'                                                           as source_system,
        x.customer_key,
        l.revenue_type,
        l.issued_date                                                   as revenue_date,
        l.currency,
        l.net_amount                                                    as amount_local,
        l.plan_code,
        cast(null as int64)                                             as shipment_id,
        l.invoice_id
    from {{ ref('fct_invoice_lines') }} l
    join x on x.source_system = 'pay' and x.source_id = l.account_id
    where l.revenue_type in ('subscription', 'txn_fee', 'freight_fee')
      and l.invoice_status != 'void'
),

ship as (
    select
        concat('ship:', cast(s.shipment_id as string)),
        'ship',
        x.customer_key,
        'booking_fee',
        s.booked_date,
        s.currency,
        s.booking_fee,
        cast(null as string),
        s.shipment_id,
        cast(null as string)
    from {{ ref('stg_ship__shipments') }} s
    join x on x.source_system = 'ship' and x.source_id = cast(s.shipper_id as string)
    where s.status != 'cancelled'
)

select
    u.*,
    fx.rate_per_eur                                 as fx_rate,
    round(u.amount_local / fx.rate_per_eur, 2)      as amount_eur
from (select * from pay union all select * from ship) u
left join {{ ref('seed_fx_rates_monthly') }} fx
  on fx.currency = u.currency and fx.month = date_trunc(u.revenue_date, month)
