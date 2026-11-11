# Phase 3: Governance → code (⏱ 45 min)

## Goal
For every governance concept, point to the exact file/config that implements it.
Deliverable: `docs/03_governance.md`, centered on a **concept → artifact** table.

## Implementation map
| Concept | Where it lives | File(s) |
|---|---|---|
| Ownership / stewardship | dbt `groups` (`ship_domain`, `pay_domain`, `udl_core`) with `owner`. `meta.owner` on models | `models/_groups.yml` |
| Data products / interfaces | **Model contracts** (`contract: {enforced: true}`), column `data_type`s, `constraints` (PK/FK/not_null; enforced in PG, informational in BQ) | `marts/_marts.yml` |
| Breaking changes | **Model versions** (`dim_customer` v1 → v2 renames `region` → `region_code`, `deprecation_date`) | `marts/_dim_customer.yml` |
| Access boundaries | `access: private / protected / public`. Only public marts may be consumed by the other project or the semantic layer | yml configs |
| Classification | Column `meta: {pii: true, classification: confidential\|internal\|public}` + `tags: ['pii']` | yml |
| Policy enforcement (CI) | `scripts/check_governance.py` reads `manifest.json` and fails if: a public model exposes an unmasked PII column, a public model has no contract or owner, or a mart has no PK test | script + `make govern` |
| Masking / least privilege, PG ("Redshift") | Roles `analyst`, `pii_reader`. `grants` config. Masked view uses a `mask_email()` macro. RLS policy by region (concept demo) | `macros/mask.sql`, `dbt_project.yml` grants |
| Masking, BQ (hands-on where free) | **Policy tags** (Data Catalog taxonomy, attached via dbt `policy_tags` column config) + **row access policy** + **authorized view**. **Dynamic data masking**: hands-on only if it's available without a paid edition, otherwise a snippet | `scripts/setup_bq_governance.py`, yml |
| Redshift equivalents | **Dynamic Data Masking** policies, RLS, Lake Formation for Spectrum | doc |
| Quality SLAs | tests + severity + source freshness (Phase 2) | |
| Lineage & discovery | `dbt docs`, **exposures** (`metrics_mcp_server`, `exec_dashboard`), manifest/catalog artifacts, OpenLineage via Airflow (Phase 7) | `models/_exposures.yml` |
| Metric governance | Metrics defined once in the semantic layer (Phase 5) | |
| Retention | `hours_to_expiration` / partition expiration in BQ (comment) | |

## Acceptance criteria
- Deliberately leak `contact_email` into a public mart: `make govern` fails with a clear message. Fix it and the check passes.
- A contract violation (wrong data type) fails `dbt build`.
- `analyst` role cannot read raw emails in PG; `pii_reader` can.

## 🧭 Checkpoint
Which models are `public`? This defines the UDL's "data product" surface.

## 🧠 Quiz 3: 5 questions (contract vs test, access levels, versions, policy tags vs authorized views, what "governance as code" buys you)
