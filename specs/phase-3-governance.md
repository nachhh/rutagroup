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

## Status log
- ✅ `ruta_ship`: groups, access, contracts + PK constraints (enforced in PG), `dim_shipper` v1/v2, contacts + RLS, masked view, grants. 56/56 pass.
- ✅ `ruta_udl`: groups, access, contracts, informational PK, exposures, `persist_docs`. 43 pass + 1 known WARN.
- ✅ `make govern` gate (R1–R5) caught real gaps on first run (missing descriptions, mart without PK test). Leak demo → R4.
- ✅ Contract violation demo → `data type mismatch` before build.
- ✅ Quiz 3 done (4 questions).
- ✅ BQ: tag on source column; no role → 403, Masked Reader → SHA-256, Fine-Grained Reader → raw. Row policy demo;
  dropping the last row policy needs `DROP ALL`. Authorized view in `udl_share`.
- Lesson: dynamic masking is applied on read, before SQL → `lower()` over a masked value is garbage.
- dbt ≥ 1.10: `access`, `group`, column `meta`/`tags` go under `config:`. Singular tests need `+group` to ref private models.

## 🧭 Decisions (settled)
1. **Public surface (A).** `ruta_ship`: public = `fct_shipments`, `fct_shipment_lifecycle`, `dim_shipper` (v2), `dim_carrier`, `dim_lane`
   (exactly what gets replicated to BQ). Protected = `fct_shipment_events`, `mv_daily_lane_volume`, `dim_shipper_contacts`, `dim_shipper` v1.
   Private = staging + intermediate. `ruta_udl`: public = `fct_invoice_lines`, `fct_payments`, `dim_date`; protected = `rpt_*`, `exp_*`.
2. **PII (A).** The public `dim_shipper` exposes `email_domain` + `email_sha256` (pseudonymized; reused as an entity-resolution key in Phase 4).
   Raw contacts live in protected `dim_shipper_contacts`, granted only to `pii_reader`. Analysts get `v_shipper_contacts_masked` (`mask_email()` macro).
3. **Versions (A).** `dim_shipper` v1 (raw `contact_email`, protected, `deprecation_date`) → v2 (`email_sha256`, public, `latest_version: 2`).
   This replaces the original `dim_customer` example: that model only arrives in Phase 4.
4. **BQ hands-on (all free on on-demand pricing):** a policy-tag taxonomy `pii` with tag `email`, attached at the **source**
   (`raw_pay.accounts.billing_contact.email`) so enforcement propagates through every view. **Dynamic data masking** (a SHA-256 data policy, *Masked Reader*)
   is available on on-demand (not on Standard-edition reservations), so it's hands-on. Plus a row access policy demo on `fct_invoice_lines`
   and an authorized view in a `udl_share` dataset. dbt's `policy_tags:` column config is shown as a snippet (taxonomy ids are generated per project).

## 🧠 Quiz 3: 4 questions (contract vs test, access levels + versions, policy tags vs authorized views, what "governance as code" buys you)
