-- Least-privilege roles for RutaShip ("Redshift" played by Postgres). Run once: make pg-roles
-- NOLOGIN group roles: humans/services would be LOGIN users granted these roles. The demo uses SET ROLE.
-- Object-level GRANTs are applied by dbt (`grants:` config); schema USAGE by the on-run-end hook.
--   analyst            → marts + masked contacts view, never raw PII
--   pii_reader         → everything analyst has + raw contacts (all regions)
--   pii_reader_iberia  → raw contacts, but row-level security limits it to region = 'iberia'
-- Redshift equivalent: CREATE ROLE + GRANT ROLE, RLS policies, and DYNAMIC DATA MASKING policies
--   (CREATE MASKING POLICY ... ATTACH MASKING POLICY ... ON t(col) TO ROLE analyst).
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'analyst')           then create role analyst nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'pii_reader')        then create role pii_reader nologin; end if;
  if not exists (select 1 from pg_roles where rolname = 'pii_reader_iberia') then create role pii_reader_iberia nologin; end if;
end $$;
