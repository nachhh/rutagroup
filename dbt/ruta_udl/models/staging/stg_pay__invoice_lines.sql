-- grain: 1 row per invoice line.
-- CROSS JOIN UNNEST explodes the ARRAY<STRUCT> `lines`: one output row per array element, parent columns repeated.
--   ⚠️ CROSS JOIN drops invoices whose array is empty; use LEFT JOIN UNNEST(...) to keep them.
--   WITH OFFSET gives the 0-based position inside the array.
select
    i.invoice_id,
    l.line_no,
    line_idx,
    i.account_id,
    i.invoice_number,
    upper(i.currency)                                     as currency,
    i.status                                              as invoice_status,
    i.issued_at,
    date(i.issued_at)                                     as issued_date,
    i.bill_to.legal_name                                  as billed_legal_name,
    l.sku,
    l.description,
    l.qty,
    l.unit_amount,
    l.tax_rate,
    round(l.qty * l.unit_amount, 2)                       as net_amount,
    -- revenue classification: the FREIGHT line is money collected for the carrier → NOT RutaPay revenue
    case
        when starts_with(l.sku, 'SUB-') then 'subscription'
        when l.sku = 'FEE-TXN'          then 'txn_fee'
        when l.sku = 'FEE-PROC'         then 'freight_fee'
        when l.sku = 'FREIGHT'          then 'pass_through'
        else 'other'
    end                                                   as revenue_type,
    lower(regexp_extract(l.sku, r'^SUB-(.+)$'))           as sku_plan_code
from {{ source('raw_pay', 'invoices') }} as i
cross join unnest(i.lines) as l with offset as line_idx
