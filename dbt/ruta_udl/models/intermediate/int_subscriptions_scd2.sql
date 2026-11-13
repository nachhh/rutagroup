{#-
  grain: 1 row per account × subscription version (SCD2), DERIVED FROM THE CHANGE LOG.

  Log-based SCD2 vs dbt snapshot (polling):
    * The change log records EVERY change, so no intermediate state is lost between runs.
    * Rebuildable from scratch at any time (pure function of the log), so no snapshot state to protect.
    * Needs the source to keep history (app change log, or CDC from the OLTP DB).
  LEAD() looks at the next change for the same account: its timestamp closes the current version.
-#}
with changes as (
    select * from {{ ref('stg_pay__subscription_changes') }}
)

select
    farm_fingerprint(concat(account_id, '|', cast(changed_at as string)))  as subscription_sk,   -- surrogate key per version
    account_id,
    if(change_type = 'cancel', null, plan_code)                            as plan_code,
    if(change_type = 'cancel', 'cancelled', 'active')                      as subscription_status,
    change_type,
    changed_at                                                             as valid_from,
    coalesce(lead(changed_at) over w, timestamp '9999-12-31')              as valid_to,         -- half-open [from, to)
    lead(changed_at) over w is null                                        as is_current
from changes
window w as (partition by account_id order by changed_at)   -- named WINDOW clause, reused by both LEADs
