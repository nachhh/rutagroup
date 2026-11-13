# Phase 2: dbt refresher on both engines (⏱ 1.5 h)

## Goal
Build staging → intermediate → marts in both projects. Every key dbt concept appears at least once
in code, with a comment explaining the choice.

## `ruta_ship` (Postgres ≈ Redshift)
| Model | Materialization | Why / concept |
|---|---|---|
| `stg_ship__shippers`, `__carriers`, `__lanes`, `__shipments` | `view` | Cheap 1:1 cleanup layer |
| `stg_ship__shipment_events` | `view` | |
| `int_shipments_enriched` | `ephemeral` | Inlined CTE, no object created |
| `fct_shipments` | `incremental`, `merge`, `unique_key=shipment_id`, 3-day lookback | Late status updates. `is_incremental()`, `on_schema_change='append_new_columns'` |
| `fct_shipment_events` | `incremental`, `append` (or `microbatch` on `event_ts`) | Immutable event log |
| `fct_shipment_lifecycle` | `table` | Accumulating snapshot rebuilt from events |
| `dim_shipper` | `table` | Built from the snapshot below |
| `snapshots/snap_shippers.yml` | snapshot, `timestamp` strategy on `updated_at` | **SCD2 the dbt way** |
| `mv_daily_lane_volume` | `materialized_view` | Show it exists; discuss refresh trade-offs |

**Physical design per engine** (from the Quiz 1 discussion): Postgres uses **indexes** (dbt `indexes=[{'columns': ['shipment_id'], 'unique': True}]`, a BRIN index on time columns).
Redshift has no indexes and uses `dist`/`sort` (dbt-redshift `dist='shipment_id'`, `sort='booked_at'`), written as comments next to the PG config.
BigQuery uses `partition_by`/`cluster_by`. `incremental_predicates` (to prune the MERGE target) works on all three.

## `ruta_udl` (BigQuery): BigQuery-native SQL showcase
| Model | BQ features used |
|---|---|
| `stg_pay__accounts` | `billing_contact.email` (STRUCT dot access), `UNNEST(addresses) WITH OFFSET`, `ARRAY_AGG(... ORDER BY ... LIMIT 1)[OFFSET(0)]` to pick the primary address, `REGEXP_REPLACE` to normalize tax_id, `SELECT * EXCEPT/REPLACE` |
| `stg_pay__invoices` | Invoice header + `JSON_VALUE(metadata, '$.shipment_ref')` (cross-product link!), `SAFE_CAST` |
| `stg_pay__invoice_lines` | `CROSS JOIN UNNEST(lines) AS l WITH OFFSET AS line_idx`. Explodes ARRAY<STRUCT> to one row per line |
| `stg_pay__payment_events` | Webhook JSON: `JSON_VALUE(payload,'$.type')`, `JSON_QUERY(payload,'$.data.method')`, `JSON_QUERY_ARRAY` for refunds, dedup with `QUALIFY ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY received_at DESC) = 1` |
| `int_subscriptions_scd2` | **SCD2 from a change log** via `LEAD(changed_at) OVER (PARTITION BY account_id ORDER BY changed_at)` → `valid_from/valid_to/is_current`. The alternative to dbt snapshots when the source already keeps history (a log/CDC feed) |
| `dim_date` | `UNNEST(GENERATE_DATE_ARRAY(...))` |
| `fct_invoice_lines` | **`incremental`, `incremental_strategy='insert_overwrite'`**, `partition_by={'field':'issued_date','data_type':'date'}`, `cluster_by=['account_id']`. Rebuilds only the last N partitions (late payments/corrections). The classic BQ cost pattern; compare with `merge` (scans the target) and `microbatch` |
| `fct_payments` | `incremental`, `merge` on `invoice_id` (payment status changes) |
| other marts | `table` with partition/cluster where it pays off. Comments explain cost/pruning |

Also covered: `PIVOT` (plan mix per month), `APPROX_COUNT_DISTINCT`, `SAFE_DIVIDE`,
`DATE_TRUNC`, and an `ARRAY_AGG(STRUCT(...))` going the other way (re-nesting for an API-style output).

## Tests (both projects)
- Generic: `unique`, `not_null`, `accepted_values`, `relationships`
- `dbt_utils.unique_combination_of_columns`, `expression_is_true`
- Singular: `tests/assert_invoice_total_equals_sum_of_lines.sql`
- **Unit test** (dbt ≥ 1.8): tax_id normalization and SCD2 validity windows, with mocked inputs
- `severity: warn` + `warn_if` / `error_if` thresholds, `store_failures` (both engines)
- Source **freshness** on `raw_ship.shipment_events` and `raw_pay.payment_events`

## Other concepts touched
`ref` vs `source`, seeds (`seed_plans.csv`, `seed_region_map.csv`), a macro (`normalize_tax_id`,
written cross-database with `adapter.dispatch`), `dbt build` vs `run` + `test`, selectors (`+fct_shipments`,
`tag:pii`, `state:modified+` with `--defer`), and `dbt docs generate`.

## Acceptance criteria
- `dbt build` passes in both projects
- At least: 1 incremental merge (PG), 1 append/microbatch (PG), 1 insert_overwrite (BQ), 1 snapshot (PG), 1 log-derived SCD2 (BQ), 1 unit test, 1 singular test
- Every BQ feature in the table above appears in at least one model

## Status log
- ✅ `ruta_ship` (PG): 44/44 on first build. `make day2` → snapshot +75 versions, events APPEND +1,291, shipments MERGE 1,360.
  The reconciliation test WARNed on the correction 5 days late (shipment 2), as designed. `--full-refresh -s fct_shipments+` fixed it.
- ✅ `ruta_udl` (BQ): 43 pass + 1 WARN. Second run: `insert_overwrite` processed 164.5 KiB (7 partitions), `fct_payments` MERGE touched 2 invoices.
  BQ on-demand bills a **10 MB minimum per table referenced**, which dominates at this scale.
- Unit test lesson: BQ can't compare ARRAY columns in EXCEPT (used by dbt unit tests) → flatten STRUCTs in staging, use `format: sql` for nested *inputs* only.
- ⚠️ Finding: 20 fee lines have no as-of plan. They were issued hours *before* the subscription start timestamp on the same day
  (billing compares dates; our join compares timestamps). Kept as `warn`; the fix is a Phase 4 checkpoint.
- Generator: invoices now carry `bill_to {legal_name, tax_id}` (document of record). RNG sequence unchanged.
- ✅ Quiz 2 done (4 questions). Follow-ups for Phase 7: Slim CI (`state:modified+ --defer`), `dbt clone`.

## 🧭 Decisions (settled)
1. `fct_shipments`: **merge** on `shipment_id`, 3-day lookback on `updated_at`. The lookback = worst expected *ingestion*
   delay (not shipment duration). The best practice is filtering on a load timestamp; mitigations are a periodic full refresh and reconciliation tests.
   `scripts/day2_ship.py` simulates a late arrival 2 days behind (caught) and one 5 days behind (missed).
2. Primary address: `is_primary` → first billing → any (`ARRAY_AGG ... ORDER BY ... LIMIT 1`).
3. `fct_invoice_lines`: `insert_overwrite` rebuilding the last **7 days** of partitions + a monthly full refresh.
4. Invoice total vs lines: singular test, €0.01 tolerance, `warn_if: ">0"`, `error_if: ">10"`.

## 🧭 Checkpoints (original)
1. Incremental strategy and lookback for `fct_shipments` (merge vs delete+insert)
2. Primary address rule for multi-address accounts
3. `insert_overwrite` lookback (how many partitions to rebuild) for `fct_invoice_lines`
4. Is a mismatch in invoice total vs sum of lines `warn` or `error`?

## 🧠 Quiz 2: 4 questions (incremental strategies + idempotency, UNNEST semantics, snapshots vs log SCD2, partition vs cluster + `--defer`)
