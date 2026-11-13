-- Singular test (decision 4A): header total must equal the sum of lines incl. tax, within €0.01 (rounding).
-- Thresholds: warn if any invoice is off, fail only if more than 10 are (systemic issue vs. rounding noise).
-- error_if is only evaluated when severity is 'error'.
{{ config(severity='error', warn_if='>0', error_if='>10', store_failures=true) }}

with lines as (
    select invoice_id, sum(qty * unit_amount * (1 + tax_rate)) as calc_total
    from {{ ref('stg_pay__invoice_lines') }}
    group by invoice_id
)
select i.invoice_id, i.total, round(l.calc_total, 2) as calc_total, abs(i.total - l.calc_total) as diff
from {{ ref('stg_pay__invoices') }} i
join lines l using (invoice_id)
where abs(i.total - l.calc_total) > 0.01
