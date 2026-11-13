-- grain: 1 row per shipper (CURRENT contact only: SCD1 by policy, PII history has no analytical value).
-- PROTECTED + granted only to pii_reader roles. Two Postgres-native controls on top of the grant:
--   * RLS (row-level security): pii_reader sees all rows, pii_reader_iberia only region = 'iberia'.
--     Redshift has the same idea: CREATE RLS POLICY ... ATTACH RLS POLICY ... TO ROLE.
--   * The table owner (dbt's user) bypasses RLS by default, which is why the demo uses SET ROLE.
-- Hooks re-apply the policies on every build because `table` materialization recreates the table.
{{ config(
    materialized='table',
    grants={'select': ['pii_reader', 'pii_reader_iberia']},
    post_hook=[
      "alter table {{ this }} enable row level security",
      "create policy all_rows on {{ this }} for select to pii_reader using (true)",
      "create policy iberia_only on {{ this }} for select to pii_reader_iberia using (region = 'iberia')",
    ],
) }}

select
    shipper_id,
    contact_email,
    contact_phone,
    region
from {{ ref('stg_ship__shippers') }}
