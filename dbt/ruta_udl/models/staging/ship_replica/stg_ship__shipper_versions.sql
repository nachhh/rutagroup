-- grain: 1 row per shipper VERSION (SCD2), from the replicated dim_shipper v2.
-- ⚠️ Snapshot history starts at the FIRST `dbt snapshot` run, not at shipper creation (a snapshot can't see the past).
--    UDL assumption, documented: the first known version is back-dated to created_at.
select
    shipper_id,
    company_name,
    tax_id_normalized,
    email_sha256,
    email_domain,
    country,
    region,
    tier,
    created_at,
    if(row_number() over (partition by shipper_id order by valid_from) = 1, created_at, valid_from) as valid_from,
    valid_to,
    is_current
from {{ source('ship_replica', 'dim_shipper') }}
