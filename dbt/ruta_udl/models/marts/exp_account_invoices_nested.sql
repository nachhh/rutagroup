-- grain: 1 row per account. The REVERSE of UNNEST: re-nest children into ARRAY<STRUCT> for an API/export
-- consumer (one document per account, no joins needed client-side).
select
    account_id,
    count(*)                                                           as invoice_count,
    approx_count_distinct(shipment_ref)                                as shipments_billed_approx,  -- HyperLogLog++: cheap at scale, ~1% error
    array_agg(struct(invoice_id, invoice_number, issued_date, total, status)
              order by issued_at desc limit 12)                        as last_12_invoices
from {{ ref('stg_pay__invoices') }}
group by account_id
