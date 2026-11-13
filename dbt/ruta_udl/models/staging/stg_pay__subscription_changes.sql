-- grain: 1 row per subscription change (append-only change log)
-- SELECT * REPLACE: keep all columns but swap one expression in place (EXCEPT drops columns the same way)
select * replace (lower(plan_code) as plan_code, lower(change_type) as change_type)
from {{ source('raw_pay', 'subscription_changes') }}
