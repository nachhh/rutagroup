# 03: Governance as code

Governance written as files, so it can be reviewed, versioned, tested and enforced in CI.
Spec: [phase-3](../specs/phase-3-governance.md). Lineage with access levels: [dbt lineage](diagrams/dbt-lineage.md).

## 1. Concept → artifact

| Concept | Artifact in this repo | Enforced by |
|---|---|---|
| **Ownership / stewardship** | dbt `groups` with `owner`: `ship_domain`, `pay_domain`, `udl_core` ([ship](../dbt/ruta_ship/models/_groups.yml), [udl](../dbt/ruta_udl/models/_groups.yml)) and `+group` in `dbt_project.yml` | dbt (private refs) + gate R1 |
| **Data products** | `access: public` + enforced **contract** + PK constraint ([ship marts](../dbt/ruta_ship/models/marts/_marts.yml), [udl marts](../dbt/ruta_udl/models/marts/_marts.yml)) | dbt pre-build check + gate R2/R3/R5 |
| **Interfaces vs internals** | `access: private` on staging/intermediate, `protected` default on marts | dbt parse error on illegal `ref` |
| **Breaking changes** | **Model versions**: `dim_shipper` v1 (raw email, protected, `deprecation_date: 2026-12-31`) → v2 (`email_sha256`, public, `latest_version: 2`) | dbt (deprecation warnings to consumers) |
| **Integrity** | `constraints: [{type: primary_key}]`: **enforced in Postgres**, **informational in BigQuery/Redshift** | Postgres DDL; data tests everywhere |
| **Classification** | Column `config: {meta: {pii, classification}, tags: [pii]}` | gate R4 |
| **Policy enforcement (CI)** | [`scripts/check_governance.py`](../scripts/check_governance.py) over `manifest.json`, `make govern` | exit code 1 blocks the PR |
| **Least privilege (PG ≈ Redshift)** | Roles in [`setup_pg_roles.sql`](../scripts/setup_pg_roles.sql); dbt `+grants` per folder/model; schema `USAGE` via `on-run-end` | Postgres |
| **Static masking + pseudonymization** | [`macros/pii.sql`](../dbt/ruta_ship/macros/pii.sql): `mask_email()` (readable, redacted) and `hash_email()` (SHA-256, joinable) | SQL at build time |
| **Row-level security (PG)** | `dim_shipper_contacts` post-hooks: `ENABLE ROW LEVEL SECURITY` + policies per role | Postgres |
| **Owner-rights view (PG)** | `v_shipper_contacts_masked`: analysts read it without access to the base table | Postgres |
| **Column-level security (BQ)** | Policy tag `ruta_pii > email` on the **source** column `raw_pay.accounts.billing_contact.email` ([`setup_bq_governance.py`](../scripts/setup_bq_governance.py)) | BigQuery, even for the project Owner |
| **Dynamic masking (BQ)** | Data policy `email_sha256` (SHA256) on the same tag → *Masked Reader* | BigQuery (on-demand; not on Standard edition) |
| **Row-level security (BQ)** | `CREATE ROW ACCESS POLICY ... GRANT TO (...) FILTER USING (...)` (demo) | BigQuery |
| **Curated sharing (BQ)** | Authorized view `udl_share.v_monthly_revenue` → reads `udl_marts` | BigQuery dataset ACL |
| **Quality SLAs** | Tests + `severity`/`warn_if`/`error_if` + source freshness (Phase 2) | `dbt build`, `dbt source freshness` |
| **Lineage & discovery** | Exposures `udl_replication` (ship), `exec_dashboard` and `metrics_mcp_server` (udl); `persist_docs` pushes descriptions to BQ; `dbt docs` | dbt graph; OpenLineage via Airflow in Phase 7 |
| **Metric governance** | Metrics defined once in the semantic layer | Phase 5 |
| **Retention** | BQ partition expiration (`partition_expiration_days` in dbt config) / table expiration (`hours_to_expiration`); GDPR erasure is easier when PII is SCD1 (Phase 1 decision) | BigQuery |

## 2. The data product surface (decision 1A)

| Project | Public (contracted interface) | Protected | Private |
|---|---|---|---|
| `ruta_ship` | `fct_shipments`, `fct_shipment_lifecycle`, `dim_shipper` (v2), `dim_carrier`, `dim_lane` | `fct_shipment_events`, `mv_daily_lane_volume`, `dim_shipper_contacts`, `v_shipper_contacts_masked`, `dim_shipper` v1 | staging, intermediate |
| `ruta_udl` | `fct_invoice_lines`, `fct_payments`, `dim_date` | `rpt_plan_mix_monthly`, `exp_account_invoices_nested` | staging, intermediate |

Rule of thumb: **public = what you're willing to support like an API.** Exactly the ship public set is replicated to
BigQuery (the `udl_replication` exposure), so private/protected models never leave their engine.

## 3. Contract vs test vs constraint

| | Contract | Constraint | Data test |
|---|---|---|---|
| Checks | Shape: column names, types, count | Integrity rule in DDL (PK, FK, not null) | Values: unique, not null, relationships, custom SQL |
| When | **Before** the build (fails fast, nothing written) | On write (Postgres) / never (BQ, Redshift) | **After** the build (bad data already in the table) |
| Example failure | `carrier_id INTEGER` vs contract `TEXT` → `data type mismatch` | Duplicate `shipment_id` → insert rejected in PG | `unique_fct_payments_invoice_id` fails |

Incremental models with a contract must set `on_schema_change` to `append_new_columns` or `fail`.

## 4. PII strategy (decision 2A)

```
raw_ship.shippers.contact_email
   ├── dim_shipper v2 (public)          email_sha256 + email_domain     pseudonymized, joinable, `internal`
   ├── dim_shipper_contacts (protected) raw email/phone                 pii_reader (all) / pii_reader_iberia (RLS)
   └── v_shipper_contacts_masked        j***@acme.com                   analyst
```

- **Masking ≠ pseudonymization.** A masked value is for humans and can't be joined. A hash is for machines: it's joinable
  across systems (Phase 4 entity resolution), but still **personal data** under GDPR, since anyone can hash candidate emails.
- **Dynamic masking happens on read, before your SQL.** Through the masked tag, `lower()` in `stg_pay__accounts` turns
  the base64 SHA-256 into garbage. Masked columns are for display, not for transformations or joins.
- **Classify at the source.** The BQ tag is on the raw column, so every view and model on top is protected, including
  views that nobody remembered to classify.

## 5. Demos (reproducible)

```bash
make pg-roles && make ship           # roles + grants + RLS
docker exec ruta_pg psql -U ruta -d ruta -c "set role analyst" -c "select * from ship_marts.dim_shipper_contacts"
#   → ERROR: permission denied           (analyst reads v_shipper_contacts_masked instead)
docker exec ruta_pg psql -U ruta -d ruta -c "set role pii_reader_iberia" -c "select count(*), count(distinct region) from ship_marts.dim_shipper_contacts"
#   → 596 | 1                            (RLS)

make govern                          # ✅ both projects
# leak contact_email into dim_shipper_v2 (sql + yml) → ❌ R4 ... looks like PII but is not declared masked/pseudonymized

make bq-governance                   # taxonomy, tag, data policy, authorized view
uv run python scripts/setup_bq_governance.py demo
#   no role → 403 Access Denied | Masked Reader → SHA-256 | Fine-Grained Reader → raw
#   row access policy → only EUR rows; dropping the LAST policy requires DROP ALL (BQ won't silently re-open the table)
```

## 6. Redshift equivalents

| Need | Postgres (here) | Redshift | BigQuery |
|---|---|---|---|
| Roles / grants | `CREATE ROLE`, `GRANT` | Same + RBAC system roles | IAM on project/dataset/table |
| Column security | Column `GRANT` / views | Column-level `GRANT` | Policy tags |
| Dynamic masking | (no native) | `CREATE MASKING POLICY ... ATTACH ... TO ROLE` | Data policies on policy tags |
| Row security | `CREATE POLICY` | `CREATE RLS POLICY ... ATTACH ... TO ROLE` | Row access policies |
| Share a slice | Owner-rights view | Views / datashares | Authorized views / datasets, Analytics Hub |
| Lake (S3/GCS) | n/a | Lake Formation for Spectrum | BigLake |
