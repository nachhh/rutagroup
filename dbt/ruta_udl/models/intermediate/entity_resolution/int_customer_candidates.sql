-- grain: 1 row per source record that could be a customer (current shipper versions + Pay accounts).
-- Puts both systems into ONE comparable shape: same normalization for name, tax id and email.
with ship as (
    select
        'ship'                                  as source_system,
        cast(shipper_id as string)              as source_id,
        company_name                            as raw_name,
        tax_id_normalized                       as tax_id_norm,
        email_sha256,                           -- hashed upstream in Postgres (dim_shipper v2): raw email never left RutaShip
        email_domain,
        country,
        created_at
    from {{ ref('stg_ship__shipper_versions') }}
    where is_current
),

pay as (
    select
        'pay'                                   as source_system,
        account_id                              as source_id,
        legal_name                              as raw_name,
        tax_id_normalized                       as tax_id_norm,
        {{ hash_email('contact_email') }}       as email_sha256,   -- same macro/algorithm as RutaShip → joinable hashes
        email_domain,
        primary_country                         as country,
        created_at
    from {{ ref('stg_pay__accounts') }}
)

select
    *,
    {{ normalize_company_name('raw_name') }}                              as name_norm,
    email_domain in ('gmail.com', 'hotmail.com', 'yahoo.com', 'outlook.com') as is_personal_domain
from (select * from ship union all select * from pay)
