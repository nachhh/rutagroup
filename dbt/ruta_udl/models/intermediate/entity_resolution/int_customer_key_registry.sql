{#-
  grain: 1 row per (source record, key assignment). APPEND-ONLY LOG; current key = latest row per record.
  The only STATE in entity resolution: matching is recomputed every run, keys are assigned once and kept.

  Rules (specs/phase-7s2-extras.md):
    * A record KEEPS its key while its cluster doesn't change. Rows are never updated or deleted: churn,
      inactivity and source deletions are not identity events (a deleted record's last row = tombstone).
    * inherit: a new record joining a keyed cluster gets that key.
    * merge:   a cluster holding ≥2 keys keeps the OLDEST (first assigned earliest); the others are retired
               (→ customer_key_aliases).
    * split:   a key whose holders now sit in ≥2 clusters stays with the cluster that held it longest; the other
               cluster keeps its own oldest key or gets a new one.
    * new:     a cluster with no key gets one, minted once.

  Why full_refresh=false: a rebuild from scratch would re-run the migration and silently re-issue keys that
  consumers already stored. This table is state, like a snapshot: in CI clone/defer it from prod
  (`dbt clone` / `--defer`), never build it fresh.
-#}
-- merge WITHOUT unique_key → dbt-bigquery emits MERGE ... ON FALSE = plain INSERT (append-only log)
{{ config(
    materialized='incremental',
    incremental_strategy='merge',
    full_refresh=false,
    on_schema_change='fail',
    cluster_by=['source_system', 'source_id'],
) }}

with members as (                    -- every source record present TODAY, with today's cluster
    select source_system, source_id, cluster_id
    from {{ ref('int_customer_clusters') }}
),

history as (
    {% if is_incremental() %}
    select source_system, source_id, customer_key, assigned_at from {{ this }}
    {% else %}
    select cast(null as string) as source_system, cast(null as string) as source_id,
           cast(null as int64) as customer_key, cast(null as timestamp) as assigned_at
    limit 0
    {% endif %}
),

-- MIGRATION is decided by the DATA, not by is_incremental(): an empty registry = first adoption. So a bootstrap
-- `dbt run --empty` (creates the empty table that unit tests mocking `this` need) can't turn the first real run into
-- "everyone is new" with freshly minted keys.
first_load as (
    select count(*) = 0 as is_first from history
),

current_key as (                     -- the key each record holds now (incl. tombstones of deleted records)
    select * from history
    qualify row_number() over (partition by source_system, source_id order by assigned_at desc) = 1
),

key_age as (                         -- "oldest key wins" needs the first time each key was ever assigned
    select customer_key, min(assigned_at) as key_born_at from history group by customer_key
),

held as (                            -- present members + the key they hold (null = never seen before)
    select m.source_system, m.source_id, m.cluster_id, k.customer_key as held_key, k.assigned_at as held_since
    from members m
    left join current_key k using (source_system, source_id)
),

key_owner as (                       -- SPLIT rule: each held key belongs to ONE cluster: the one that held it longest
    select held_key as customer_key, cluster_id as owner_cluster
    from held
    where held_key is not null
    group by held_key, cluster_id
    -- QUALIFY over a GROUP BY: the window runs on the aggregated rows (min/count per key × cluster)
    qualify row_number() over (partition by held_key order by min(held_since), count(*) desc, cluster_id) = 1
),

survivor as (                        -- MERGE rule: among the keys a cluster owns, the oldest survives
    select o.owner_cluster as cluster_id, o.customer_key
    from key_owner o
    join key_age a using (customer_key)
    qualify row_number() over (partition by o.owner_cluster order by a.key_born_at, o.customer_key) = 1
),

minted as (                          -- NEW: clusters that own no key get one, minted ONCE per cluster
    select cluster_id,
        if((select is_first from first_load),
           farm_fingerprint(cluster_id),   -- MIGRATION: the old xwalk formula, so no existing key changes on adoption
           -- Salted with the run id: unique across runs (a split-off cluster may reuse an old anchor), deterministic
           -- within the run. Not GENERATE_UUID(): BigQuery may re-evaluate non-deterministic functions per CTE
           -- reference, which could hand one cluster two keys.
           farm_fingerprint(concat(cluster_id, '|', '{{ invocation_id }}'))) as customer_key
    from members
    where cluster_id not in (select cluster_id from survivor)
    group by cluster_id
),

target as (
    select h.source_system, h.source_id, h.cluster_id, h.held_key,
           coalesce(s.customer_key, n.customer_key) as customer_key,
           s.customer_key is not null                as cluster_had_key,
           o.owner_cluster                           as held_key_owner
    from held h
    left join survivor s using (cluster_id)
    left join minted n using (cluster_id)
    left join key_owner o on o.customer_key = h.held_key
)

select
    source_system,
    source_id,
    customer_key,
    cluster_id,
    case
        when (select is_first from first_load)    then 'migrated'
        when held_key is null and cluster_had_key then 'inherit'
        when held_key is null                     then 'new'
        when held_key_owner = cluster_id          then 'merge'   -- its key lost the oldest-key contest in its cluster
        else                                           'split'   -- its key stayed with another cluster
    end                                            as reason,
    held_key                                       as previous_key,
    current_timestamp()                            as assigned_at
from target
where held_key is null or held_key != customer_key  -- append only what changed: unchanged records add no row
