-- grain: 1 row per invoice (header). Lines are exploded in stg_pay__invoice_lines.
select
    invoice_id,
    account_id,
    invoice_number,                                       -- degenerate dimension
    upper(currency)                                       as currency,
    status,
    issued_at,
    date(issued_at)                                       as issued_date,
    due_date,
    subtotal,
    total,
    bill_to.legal_name                                    as billed_legal_name,   -- document of record (audit), SCD discussion
    bill_to.tax_id                                        as billed_tax_id,

    -- JSON column (schemaless): JSON_VALUE extracts a scalar as STRING via a JSONPath.
    json_value(metadata, '$.source')                      as invoice_source,
    json_value(metadata, '$.shipment_ref')                as shipment_ref,        -- cross-product link to RutaShip!
    safe_cast(regexp_extract(json_value(metadata, '$.shipment_ref'), r'^SHP-(\d+)$') as int64) as shipment_id,
    json_value(metadata, '$.discount.code')               as discount_code,       -- nested JSON path
    safe_cast(json_value(metadata, '$.discount.pct') as numeric) as discount_pct, -- SAFE_CAST: bad data → null, not a failed job
    array_length(lines)                                   as line_count
from {{ source('raw_pay', 'invoices') }}
