-- grain: 1 row per shipment; milestone columns fill in over time → ACCUMULATING SNAPSHOT.
-- Rebuilt as a table (cheap at 69k rows). At 500M: incremental merge on the shipment ids touched by
-- new events + incremental_predicates to prune closed shipments (see quiz 1, Q5).
--
-- TEACHING SPLIT: this model exists to show the accumulating-snapshot pattern next to fct_shipments
-- (transaction fact). Here both have the SAME grain and the SAME inputs (stg_ship__shipments +
-- int_shipment_event_rollup), so in a real project they would be ONE model: fct_shipments would carry
-- the milestone columns below and be the accumulating snapshot itself.
--   * Smell to notice: current_milestone (derived from events) and fct_shipments.status (from the
--     source) are two definitions of "status" that can disagree. One model = one definition.
--   * A separate model IS justified when the grain differs (e.g. per shipment leg/stop) or the owner or
--     contract/SLA differs (ops milestones vs finance GMV).
{{ config(materialized='table', indexes=[{'columns': ['shipment_id'], 'unique': True}]) }}

select
    s.shipment_id,
    s.shipper_id,
    s.carrier_id,
    s.booked_at,
    e.picked_up_at,
    e.delivered_at,
    e.cancelled_at,
    s.promised_delivery_at,
    case
        when e.delivered_at is not null then 'delivered'
        when e.cancelled_at is not null then 'cancelled'
        when e.had_exception          then 'exception'
        when e.picked_up_at is not null then 'in_transit'
        else 'booked'
    end                                                                 as current_milestone,
    round(extract(epoch from e.picked_up_at - s.booked_at) / 3600.0, 1)  as hours_to_pickup,
    round(extract(epoch from e.delivered_at - e.picked_up_at) / 3600.0, 1) as hours_in_transit,
    round(extract(epoch from e.delivered_at - s.promised_delivery_at) / 3600.0, 1) as hours_late   -- negative = early
from {{ ref('stg_ship__shipments') }} s
left join {{ ref('int_shipment_event_rollup') }} e using (shipment_id)
