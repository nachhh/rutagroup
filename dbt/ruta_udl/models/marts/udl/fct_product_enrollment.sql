-- grain: 1 row per customer × product (FACTLESS fact: coverage). "How many customers use both?" = count rows.
select
    x.customer_key,
    x.source_system                 as product,
    x.source_id                     as product_customer_id,
    datetime(c.created_at)          as enrolled_at,     -- UTC DATETIME: semantic-layer convention (see dim_customer)
    -- Event time for ship_to_pay_conversion (MetricFlow): null for ship rows. DATETIME (UTC), not TIMESTAMP, to work around a
    -- metricflow 0.213 BigQuery bug: the conversion window compares this column with CAST(base_time AS DATETIME).
    if(x.source_system = 'pay', datetime(c.created_at), null) as pay_enrolled_at
from {{ ref('int_customer_xwalk') }} x
join {{ ref('int_customer_candidates') }} c using (source_system, source_id)
