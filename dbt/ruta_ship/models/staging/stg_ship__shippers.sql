-- grain: 1 row per shipper (current state)
select
    shipper_id,
    trim(company_name)                         as company_name,
    tax_id                                     as tax_id_raw,
    {{ normalize_tax_id('tax_id') }}           as tax_id_normalized,
    lower(trim(contact_email))                 as contact_email,
    split_part(lower(trim(contact_email)), '@', 2) as email_domain,
    contact_phone,
    country,
    region,
    tier,
    created_at,
    updated_at
from {{ source('raw_ship', 'shippers') }}
