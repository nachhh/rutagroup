-- grain: 1 row per customer × product (FACTLESS fact: coverage). "How many customers use both?" = count rows.
select
    x.customer_key,
    x.source_system                 as product,
    x.source_id                     as product_customer_id,
    c.created_at                    as enrolled_at
from {{ ref('int_customer_xwalk') }} x
join {{ ref('int_customer_candidates') }} c using (source_system, source_id)
