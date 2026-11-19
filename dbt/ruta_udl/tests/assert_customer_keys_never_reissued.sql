-- "Assign once, never reissue": a key retired by a merge must never be held again by any record.
-- If it were, consumers resolving it through customer_key_aliases would land on the wrong customer.
{{ config(severity='error', group='udl_core') }}

select a.retired_key, x.source_system, x.source_id
from {{ ref('customer_key_aliases') }} a
join {{ ref('int_customer_xwalk') }} x on x.customer_key = a.retired_key
