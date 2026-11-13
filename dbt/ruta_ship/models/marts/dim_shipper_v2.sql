-- grain: 1 row per shipper VERSION (SCD2). v2 = the PUBLIC data product.
-- Breaking change vs v1: raw `contact_email` is gone; `email_sha256` (pseudonymized, joinable) replaces it.
-- Raw contacts live in the protected dim_shipper_contacts (pii_reader only).
{{ config(materialized='table') }}

select
    dbt_scd_id                                          as shipper_sk,
    shipper_id,
    company_name,
    {{ normalize_tax_id('tax_id') }}                    as tax_id_normalized,
    {{ hash_email('contact_email') }}                   as email_sha256,
    split_part(lower(contact_email), '@', 2)            as email_domain,
    country,
    region,
    tier,
    created_at,
    dbt_valid_from                                      as valid_from,
    coalesce(dbt_valid_to, '9999-12-31'::timestamp)     as valid_to,
    dbt_valid_to is null                                as is_current
from {{ ref('snap_shippers') }}
