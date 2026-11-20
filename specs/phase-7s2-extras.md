# Phase 7s2: extras (step 2 of Phase 7)

## Goal
Small, self-contained improvements found while reviewing Phases 0–7. Each item states the problem, the fix, and
how it was verified.

## 1. `fct_shipments`: change detection on every input ✅
- **Problem:** the incremental filter only watched `shipments.updated_at`, but `delivered_at` / `had_exception`
  come from events. It relied on the source bumping `updated_at` when an event lands.
- **Fix:** re-read a shipment if its row changed **or** it has new events (same source-clock watermark);
  `-- depends_on:` hint for the ref inside `is_incremental()`. The reconciliation test checks both inputs.
- **Verified:** an `exception` event inserted without touching the shipment row was picked up incrementally.
  Details: [phase-2 spec](phase-2-dbt.md) decision 1 (revision), [docs/01](../docs/01_modeling.md).

## 2. Customer key registry (stable canonical keys) ✅
- **Problem:** `customer_key = FARM_FINGERPRINT(anchor)` (Pay account if any, else shipper) is recomputed on
  every build. When a ship-only customer later matches an account, its anchor and key change, breaking every
  consumer that stored the old key (BI, KG node ids, agent context, reverse-ETL).
- **Principle:** *recompute identity, persist keys.* Matching stays stateless (views, rebuilt every run); only the
  key assignment is state.

### Files
| File | Type | What |
|---|---|---|
| `int_customer_clusters` | view | Former xwalk logic: source record → `cluster_id` (the match cluster, = old anchor). No key |
| `int_customer_key_registry` | **incremental, append-only, `full_refresh: false`** | Log of key assignments: 1 row per (source record, key change). Current key = latest row per record |
| `int_customer_xwalk` | view | Same interface as before: `customer_key` now read from the registry |
| `customer_key_aliases` | public mart, contracted | 1 row per retired key → the key that replaced it today (transitive) |
| `tests/assert_customer_key_cluster_bijection.sql` | singular test | Each cluster has exactly one key and each key exactly one cluster |
| `tests/assert_customer_keys_never_reissued.sql` | singular test | A retired key is never held again |
| unit tests (`_entity_resolution.yml`) | dbt unit tests on the incremental model | merge, inherit, split, new |

### Registry table (`int_customer_key_registry`)
| Column | Type | Meaning |
|---|---|---|
| `source_system`, `source_id` | string | Immutable source record id (the registry's natural key) |
| `customer_key` | int64 | Key held from `assigned_at` on |
| `cluster_id` | string | Cluster at assignment time (audit) |
| `reason` | string | `migrated` · `new` · `inherit` · `merge` · `split` |
| `previous_key` | int64 | Key held before (null for `migrated`/`new`/`inherit`) |
| `assigned_at` | timestamp | When this assignment was made |

### Rules (decided 🧭)
1. **Records keep their key** unless their cluster changes. Rows are never updated or deleted: churn, inactivity
   and source deletions are not identity events (a deleted record's last row is a tombstone).
2. **Inherit:** a new record joining a keyed cluster gets that key.
3. **Merge → oldest key wins** (🧭: earliest first assignment; tiebreak smallest key). The losing key is retired and
   appears in `customer_key_aliases`.
4. **Split:** a key whose holders now sit in ≥2 clusters stays with the cluster that held it longest; the other
   cluster gets its own surviving key or a new one.
5. **Key format stays INT64** (🧭). First build = **migration**: `FARM_FINGERPRINT(cluster_id)`, the old formula, so
   no existing key changes. Later new keys: `FARM_FINGERPRINT(cluster_id || '|' || invocation_id)`, minted once
   per cluster per run and never recomputed. (`GENERATE_UUID()` is avoided: BigQuery may re-evaluate
   non-deterministic functions per CTE reference, which would hand one cluster two keys.)
6. The registry is **state**: `full_refresh: false`; in CI it must be cloned/deferred from prod, never built fresh.

### Acceptance criteria
- First build: all keys identical to the previous xwalk (reason `migrated`); downstream marts unchanged.
- Simulated steward `match` (two separate customers) → one `merge` row, oldest key survives, alias row present.
- Simulated steward `no_match` on an auto-merged pair → one `split` row, the other side keeps the key.
- Unit tests, bijection and never-reissued tests pass; `make govern` passes (alias mart is public + contracted).

## Status log
- ✅ Item 1 (commit f07f1c0).
- ✅ Item 2. Migration: 2,458 records `migrated`, keys identical to the old xwalk (checksum on xwalk, `dim_customer`,
  `fct_revenue`). Steward simulation: `match` → `merge` + 1 alias; `no_match` → `split`; reverting both → the re-merged
  side got its original key back (oldest wins), the split-off side a NEW key, and the old alias followed it. Test
  history dropped by hand afterwards (dbt can't, by design). `make udl`: 113 pass. `make govern` and `make eval-er`
  unchanged.
- ⚠️ Gotcha: a unit test that mocks `this` needs the table to EXIST. Bootstrap `dbt run --empty` (added to `make udl`),
  and decide migration by data (empty registry) instead of `is_incremental()`, or the bootstrap would make every key new.
- Known simplification: migrated keys share one birth time → merge tiebreak = smallest key (production: `created_at`).
