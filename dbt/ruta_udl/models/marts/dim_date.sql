-- grain: 1 row per day. Role-playing date dimension (issued / due / paid / booked / month).
-- GENERATE_DATE_ARRAY builds the array of dates; UNNEST turns it into rows: no recursive CTE needed.
select
    d                                     as date_day,
    date_trunc(d, week(monday))           as week_start,
    date_trunc(d, month)                  as month_start,
    date_trunc(d, quarter)                as quarter_start,
    extract(year from d)                  as year,
    extract(isoweek from d)               as iso_week,
    format_date('%A', d)                  as day_name,
    extract(dayofweek from d) in (1, 7)   as is_weekend
from unnest(generate_date_array('2023-01-01', '2027-12-31')) as d
