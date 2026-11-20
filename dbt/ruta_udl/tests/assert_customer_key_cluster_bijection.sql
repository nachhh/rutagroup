-- Key ↔ cluster is 1:1 among present records: a cluster with two keys means the merge rule failed; a key in two
-- clusters means the split rule failed (two different companies would share an id).
{{ config(severity='error', group='udl_core') }}

select 'cluster_has_many_keys' as problem, c.cluster_id as id, count(distinct x.customer_key) as n
from {{ ref('int_customer_clusters') }} c
join {{ ref('int_customer_xwalk') }} x using (source_system, source_id)
group by c.cluster_id
having count(distinct x.customer_key) > 1
union all
select 'key_in_many_clusters', cast(x.customer_key as string), count(distinct c.cluster_id)
from {{ ref('int_customer_clusters') }} c
join {{ ref('int_customer_xwalk') }} x using (source_system, source_id)
group by x.customer_key
having count(distinct c.cluster_id) > 1
