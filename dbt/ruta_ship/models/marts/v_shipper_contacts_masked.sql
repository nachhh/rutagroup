-- grain: 1 row per shipper. STATIC MASKING for analysts: they can't read dim_shipper_contacts, but they can
-- read this view. A Postgres view runs with its OWNER's privileges (unless security_invoker), so it acts like
-- a BigQuery AUTHORIZED VIEW: the view is allowed to read the base table, its readers are not.
{{ config(materialized='view', grants={'select': ['analyst', 'pii_reader']}) }}

select
    shipper_id,
    {{ mask_email('contact_email') }}     as contact_email_masked,
    region
from {{ ref('dim_shipper_contacts') }}
