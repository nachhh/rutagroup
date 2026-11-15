-- grain: 1 row per pair a DATA STEWARD must decide. Stewardship workflow as code:
--   the steward reviews this list, records match / no_match in seeds/seed_match_decisions.csv (a reviewed PR),
--   and the next run applies it. Pairs where either side is already matched are resolved and drop out.
with matched as (select shipper_id, account_id from {{ ref('int_customer_matches') }})

select p.*
from {{ ref('int_customer_pairs') }} p
left join {{ ref('seed_match_decisions') }} d
  on cast(d.shipper_id as string) = p.shipper_id and d.account_id = p.account_id
where p.routing in ('review', 'review_conflict')
  and d.decision is null
  and p.shipper_id not in (select shipper_id from matched)
  and p.account_id not in (select account_id from matched)
