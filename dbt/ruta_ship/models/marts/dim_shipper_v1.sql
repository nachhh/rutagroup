-- grain: 1 row per shipper VERSION (SCD2), built from the dbt snapshot.
-- v1 = DEPRECATED (see deprecation_date in _marts.yml): exposes raw contact_email. Consumers migrate to v2.
-- valid_to uses a far-future sentinel instead of NULL so as-of joins are a simple half-open range:
--   event_ts >= valid_from and event_ts < valid_to
{{ config(materialized='table') }}

select
    dbt_scd_id                                          as shipper_sk,      -- surrogate key, 1 per version
    shipper_id,                                                           -- natural key
    company_name,
    {{ normalize_tax_id('tax_id') }}                    as tax_id_normalized,
    lower(contact_email)                                as contact_email,  -- PII (governed in Phase 3)
    split_part(lower(contact_email), '@', 2)            as email_domain,
    country,
    region,
    tier,
    created_at,
    dbt_valid_from                                      as valid_from,
    coalesce(dbt_valid_to, '9999-12-31'::timestamp)     as valid_to,
    dbt_valid_to is null                                as is_current
from {{ ref('snap_shippers') }}
