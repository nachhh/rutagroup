{#-
  grain: 1 row per ACCEPTED (shipper, account) match.
  Accepted = auto_merge pairs + steward 'match' decisions, minus steward 'no_match' decisions (humans override rules).
  1:1 constraint: a shipper maps to at most one account and vice versa → keep the MUTUAL best pair
  (highest confidence, then smallest name distance). Losers fall back to separate customers.
-#}
with decisions as (
    select cast(shipper_id as string) as shipper_id, account_id, decision, reviewer
    from {{ ref('seed_match_decisions') }}
),

accepted as (
    select p.shipper_id, p.account_id, p.match_rule, p.confidence, p.name_distance, 'rule' as decided_by
    from {{ ref('int_customer_pairs') }} p
    left join decisions d using (shipper_id, account_id)
    where p.routing = 'auto_merge' and coalesce(d.decision, '') != 'no_match'
    union all
    select d.shipper_id, d.account_id, 'steward_match', 1.0, null, concat('steward:', d.reviewer)
    from decisions d
    where d.decision = 'match'
)

select * from accepted
qualify row_number() over (partition by shipper_id order by confidence desc, name_distance) = 1
    and row_number() over (partition by account_id order by confidence desc, name_distance) = 1
