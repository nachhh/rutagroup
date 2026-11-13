-- grain: 1 row per month. Active accounts per plan, one column per plan → PIVOT.
-- Month-start as-of join to the SCD2 subscriptions, then PIVOT turns plan_code values into columns.
with months as (
    select month from unnest(generate_date_array('2025-05-01', '2026-10-01', interval 1 month)) as month
),
active as (
    select m.month, s.plan_code, s.account_id
    from months m
    join {{ ref('int_subscriptions_scd2') }} s
      on timestamp(m.month) >= s.valid_from and timestamp(m.month) < s.valid_to
    where s.plan_code is not null
)
select *
from active
pivot (count(account_id) for plan_code in ('starter', 'growth', 'scale'))
