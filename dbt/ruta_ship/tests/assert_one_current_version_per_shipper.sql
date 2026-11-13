-- Singular test: returns failing rows. SCD2 invariant: every shipper has exactly one current version.
select shipper_id, count(*) as current_versions
from {{ ref('dim_shipper') }}
where is_current
group by shipper_id
having count(*) <> 1
