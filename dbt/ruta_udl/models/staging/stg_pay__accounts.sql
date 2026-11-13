-- grain: 1 row per RutaPay account
with accounts as (
select
    a.account_id,
    a.legal_name,
    a.tax_id                                              as tax_id_raw,
    {{ normalize_tax_id('a.tax_id') }}                    as tax_id_normalized,   -- same macro as ruta_ship (adapter.dispatch)

    -- STRUCT field access with dot notation: billing_contact is STRUCT<name, email, phone>
    a.billing_contact.name                                as contact_name,
    lower(a.billing_contact.email)                        as contact_email,       -- PII
    split(lower(a.billing_contact.email), '@')[safe_offset(1)] as email_domain,   -- SAFE_OFFSET: null instead of error if no '@'
    a.billing_contact.phone                               as contact_phone,       -- PII

    -- PRIMARY ADDRESS (decision 2A). addresses is ARRAY<STRUCT>, shuffled in the source, so "first" is meaningless.
    -- A correlated subquery over UNNEST(...) + ARRAY_AGG(... ORDER BY ... LIMIT 1)[OFFSET(0)] picks the best element
    -- per row without exploding the table: is_primary first, then billing addresses, then original array position.
    (
        select array_agg(struct(addr.country, addr.region, addr.city)
                         order by addr.is_primary desc, addr.type = 'billing' desc, pos
                         limit 1)[offset(0)]
        from unnest(a.addresses) as addr with offset as pos
    )                                                     as primary_address,
    array_length(a.addresses)                             as address_count,
    -- distinct countries the account ships to/bills from: ARRAY subquery with DISTINCT
    array(select distinct addr.country from unnest(a.addresses) addr order by 1)  as address_countries,

    a.tags,                                               -- ARRAY<STRING> kept as-is
    'priority' in unnest(a.tags)                          as is_priority,         -- membership test on an array
    a.created_at
from {{ source('raw_pay', 'accounts') }} as a
)

-- Flatten the picked STRUCT into scalar columns: staging exposes flat, easily testable columns
-- (BigQuery can't compare STRUCT/ARRAY columns in set operations like EXCEPT DISTINCT, which dbt unit tests use).
select
    * except (primary_address),
    primary_address.country as primary_country,
    primary_address.region  as primary_region,
    primary_address.city    as primary_city
from accounts
