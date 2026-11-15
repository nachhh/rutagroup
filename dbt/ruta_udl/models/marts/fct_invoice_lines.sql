{#-
  grain: 1 row per invoice line. Transaction fact.

  INCREMENTAL / INSERT_OVERWRITE (decision 3A), the classic BigQuery cost pattern:
    * The table is PARTITIONED by issued_date. Each run recomputes only the last 7 days of partitions and
      REPLACES those partitions wholesale (no row-by-row matching, unlike MERGE, so no scan of the whole target).
    * `_dbt_max_partition` is a BigQuery scripting variable dbt declares in "dynamic" insert_overwrite mode:
      the max partition already in the table. Alternative: static `partitions=[...]` computed in Jinja (cheaper).
    * Every row of a replaced partition must be in the new select: insert_overwrite has no unique_key.
    * Safety net: monthly `--full-refresh` for corrections older than the window.
  CLUSTER BY account_id, revenue_type: sorts data within partitions → block pruning on common filters.
  Plan at issue time comes from an AS-OF join to the SCD2 subscriptions (Quiz 1 Q3).
-#}
{{ config(
    materialized='incremental',
    incremental_strategy='insert_overwrite',
    partition_by={'field': 'issued_date', 'data_type': 'date', 'granularity': 'day'},
    cluster_by=['account_id', 'revenue_type'],
    on_schema_change='append_new_columns',
) }}

with lines as (
    select * from {{ ref('stg_pay__invoice_lines') }}
    {% if is_incremental() %}
    -- Watermark computed explicitly. dbt's `_dbt_max_partition` scripting variable is NOT declared when the model has
    -- an ENFORCED CONTRACT (dbt-bigquery builds the temp table through a different path) → "Unrecognized name".
    -- Found in Phase 4: Phase 3 only ran this model with --full-refresh, which skips the incremental branch.
    where issued_date >= date_sub((select max(issued_date) from {{ this }}), interval {{ var('overwrite_lookback_days', 7) }} day)
    {% endif %}
)

select
    l.invoice_id,
    l.line_no,
    l.invoice_number,
    l.account_id,
    l.issued_at,
    l.issued_date,
    l.invoice_status,
    l.sku,
    l.revenue_type,
    coalesce(l.sku_plan_code, s.plan_code)          as plan_code,          -- as-of plan for fee lines
    l.currency,
    l.qty,
    l.unit_amount,
    l.net_amount,
    l.tax_rate,
    l.billed_legal_name,
    current_timestamp()                             as _dbt_loaded_at
from lines l
-- AS-OF JOIN AT DATE GRAIN (Phase 4, decision 4A). Billing works in days: an invoice issued at 02:00 for a plan that
-- started at 10:00 the same day belongs to that plan. Joining on timestamps left 20 fee lines without a plan.
-- At date grain two versions can overlap on a change day → QUALIFY picks one. Tie-break = business meaning:
-- prefer an ACTIVE version (a fee charged on the cancel day belongs to the plan being cancelled), then the latest.
-- The SCD2 itself stays truthful (timestamps untouched); only the join adopts billing's grain.
left join {{ ref('int_subscriptions_scd2') }} s
  on  s.account_id = l.account_id
  and l.issued_date between date(s.valid_from) and date(s.valid_to)
qualify row_number() over (partition by l.invoice_id, l.line_no order by s.plan_code is not null desc, s.valid_from desc) = 1
