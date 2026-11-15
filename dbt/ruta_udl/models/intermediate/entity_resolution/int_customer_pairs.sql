{#-
  grain: 1 row per candidate (shipper, account) PAIR that shares at least one blocking key.

  1. BLOCKING: only compare plausible pairs. A UNION of cheap equi-joins (one per blocking key) instead of an
     OR-join, which BigQuery would execute as a cross join (here 1.4k × 1.1k is fine; at 10M × 10M it isn't).
  2. VETO first (decision 1A): two present, different tax ids = two legal entities → never auto-merge.
  3. SCORE: the strongest rule that fires, as a STRUCT<rule, confidence> (one CASE, two fields, no duplication).
  4. ROUTE: ≥ 0.8 auto_merge · 0.5–0.8 review · veto with any positive evidence → review_conflict.
-#}
with c as (select * from {{ ref('int_customer_candidates') }}),
s as (select * from c where source_system = 'ship'),
p as (select * from c where source_system = 'pay'),

blocked as (
    select s.source_id as shipper_id, p.source_id as account_id from s join p using (tax_id_norm)
    union distinct
    select s.source_id, p.source_id from s join p using (email_sha256)
    union distinct
    select s.source_id, p.source_id from s join p on s.email_domain = p.email_domain and not s.is_personal_domain
    union distinct
    select s.source_id, p.source_id from s join p
      on s.country = p.country and left(s.name_norm, 4) = left(p.name_norm, 4)        -- name prefix block
),

scored as (
    select
        b.shipper_id,
        b.account_id,
        s.name_norm                                         as ship_name_norm,
        p.name_norm                                         as pay_name_norm,
        s.tax_id_norm                                       as ship_tax_id,
        p.tax_id_norm                                       as pay_tax_id,
        edit_distance(s.name_norm, p.name_norm)             as name_distance,   -- Levenshtein distance (BQ native)
        s.tax_id_norm is not null and p.tax_id_norm is not null
            and s.tax_id_norm != p.tax_id_norm              as tax_conflict,
        case
            when s.tax_id_norm = p.tax_id_norm
                then struct('tax_id_exact' as rule, 1.0 as confidence)
            when s.email_sha256 = p.email_sha256 and not s.is_personal_domain
                then struct('email_exact', 0.95)
            when s.email_domain = p.email_domain and not s.is_personal_domain
                 and edit_distance(s.name_norm, p.name_norm) <= 2
                then struct('domain_and_name', 0.8)
            when s.country = p.country and edit_distance(s.name_norm, p.name_norm) <= 2
                then struct('name_only', 0.5)
        end                                                 as best
    from blocked b
    join s on s.source_id = b.shipper_id
    join p on p.source_id = b.account_id
)

select
    * except (best),
    best.rule                                               as match_rule,
    best.confidence,
    case
        when tax_conflict                then 'review_conflict'
        when best.confidence >= 0.8      then 'auto_merge'
        else                                  'review'
    end                                                     as routing
from scored
where best.rule is not null          -- no rule fired → not a candidate match at all
