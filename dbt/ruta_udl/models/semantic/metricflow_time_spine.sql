{#-
  grain: 1 row per day. MetricFlow's TIME SPINE: the calendar it joins to for cumulative windows, offsets
  (e.g. revenue vs same quarter last year) and filling empty periods (join_to_timespine / fill_nulls_with).
  GENERATE_DATE_ARRAY + UNNEST = a calendar without a recursive CTE.
-#}
{{ config(materialized='table') }}

select d as date_day
from unnest(generate_date_array('2022-01-01', '2028-12-31')) as d
