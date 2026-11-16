# dbt lineage (Phase 2)

Materializations: 🟦 view · ⬜ ephemeral · 🟩 table · 🟧 incremental · 🟪 snapshot · 🟥 materialized view

Access (Phase 3): staging/intermediate are `private`; public data products are `fct_shipments`, `fct_shipment_lifecycle`,
`dim_shipper` v2, `dim_carrier`, `dim_lane` (ship) and `fct_invoice_lines`, `fct_payments`, `dim_date` (udl). Everything else is `protected`.

## ruta_ship (Postgres ≈ Redshift)

```mermaid
flowchart LR
  classDef view fill:#dbeafe,stroke:#3b82f6,color:#111
  classDef eph fill:#f3f4f6,stroke:#9ca3af,stroke-dasharray:4,color:#111
  classDef table fill:#dcfce7,stroke:#16a34a,color:#111
  classDef inc fill:#ffedd5,stroke:#ea580c,color:#111
  classDef snap fill:#ede9fe,stroke:#7c3aed,color:#111
  classDef mv fill:#fee2e2,stroke:#dc2626,color:#111

  src_shippers[(raw_ship.shippers)] --> stg_shippers[stg_ship__shippers]:::view
  src_shippers --> snap[snap_shippers<br/>timestamp strategy]:::snap
  snap --> dim_v1[dim_shipper v1<br/>raw email · protected · deprecated]:::table
  snap --> dim_v2[dim_shipper v2<br/>email_sha256 · PUBLIC]:::table
  stg_shippers --> contacts[dim_shipper_contacts<br/>PII · pii_reader · RLS]:::table --> masked[v_shipper_contacts_masked<br/>analyst]:::view
  src_shipments[(raw_ship.shipments)] --> stg_shipments[stg_ship__shipments]:::view
  src_events[(raw_ship.shipment_events)] --> stg_events[stg_ship__shipment_events]:::view
  src_carriers[(raw_ship.carriers)] --> stg_carriers[stg_ship__carriers]:::view --> dim_carrier[dim_carrier]:::table
  src_lanes[(raw_ship.lanes)] --> stg_lanes[stg_ship__lanes]:::view --> dim_lane[dim_lane]:::table

  stg_events --> rollup[int_shipment_event_rollup]:::eph
  stg_shipments --> fct_shipments[fct_shipments<br/>merge · 3d lookback]:::inc
  rollup --> fct_shipments
  stg_events --> fct_events[fct_shipment_events<br/>append · event_id watermark]:::inc
  stg_shipments --> lifecycle[fct_shipment_lifecycle<br/>accumulating snapshot]:::table
  rollup --> lifecycle
  stg_shipments --> mv[mv_daily_lane_volume]:::mv
  stg_lanes --> mv
```

## ruta_udl (BigQuery)

```mermaid
flowchart LR
  classDef view fill:#dbeafe,stroke:#3b82f6,color:#111
  classDef table fill:#dcfce7,stroke:#16a34a,color:#111
  classDef inc fill:#ffedd5,stroke:#ea580c,color:#111
  classDef seed fill:#fef9c3,stroke:#ca8a04,color:#111

  acc[(raw_pay.accounts<br/>STRUCT + ARRAY)] --> stg_acc[stg_pay__accounts<br/>UNNEST · ARRAY_AGG pick]:::view
  inv[(raw_pay.invoices<br/>lines ARRAY · metadata JSON)] --> stg_inv[stg_pay__invoices<br/>JSON_VALUE]:::view
  inv --> stg_lines[stg_pay__invoice_lines<br/>CROSS JOIN UNNEST]:::view
  pev[(raw_pay.payment_events<br/>payload JSON · dupes)] --> stg_pev[stg_pay__payment_events<br/>QUALIFY dedup]:::view
  sub[(raw_pay.subscription_changes)] --> stg_sub[stg_pay__subscription_changes]:::view
  stg_sub --> scd2[int_subscriptions_scd2<br/>LEAD → valid_from/to]:::view

  stg_lines --> fil[fct_invoice_lines<br/>insert_overwrite · 7d partitions]:::inc
  scd2 --> fil
  stg_pev --> fpay[fct_payments<br/>merge · recompute touched]:::inc
  stg_inv --> fpay
  scd2 --> mix[rpt_plan_mix_monthly<br/>PIVOT]:::table
  stg_inv --> nested[exp_account_invoices_nested<br/>ARRAY_AGG STRUCT]:::table
  dd[dim_date<br/>GENERATE_DATE_ARRAY]:::table
  s1[seed_region_map]:::seed
  s2[seed_plans]:::seed

  %% Phase 4: UDL
  rep[(ship_replica.*<br/>public marts from PG)] --> stg_shipv[stg_ship__shipper_versions]:::view
  rep --> stg_shp[stg_ship__shipments]:::view
  stg_shipv --> cand[int_customer_candidates]:::view
  stg_acc --> cand
  cand --> pairs[int_customer_pairs<br/>veto · score · route]:::view
  pairs --> matches[int_customer_matches]:::view
  sd[seed_match_decisions]:::seed --> matches
  pairs --> queue[int_customer_review_queue]:::view
  matches --> xwalk[int_customer_xwalk]:::view
  xwalk --> dimc[dim_customer<br/>timeline-merge SCD2]:::table
  scd2 --> dimc
  xwalk --> frev[fct_revenue<br/>EUR at month avg]:::table
  fil --> frev
  stg_shp --> frev
  fx[seed_fx_rates_monthly]:::seed --> frev
  frev --> fcm[fct_customer_monthly]:::table
  xwalk --> enr[fct_product_enrollment]:::table
  onto{{ontology YAML}} -. generates .-> kgn[kg_nodes]:::table
  onto -. generates .-> kge[kg_edges]:::table
  dimc --> kgn
  xwalk --> kge

  %% Phase 5: semantic layer
  stg_shp --> fus[fct_udl_shipments<br/>customer_key · EUR]:::table
  xwalk --> fus
  fx --> fus
  scd2 --> fcm
  spine[metricflow_time_spine]:::table
  sl{{semantic models + metrics<br/>_udl.yml · _metrics.yml}}
  dimc -. SCD2 dims .-> sl
  frev -.-> sl
  fus -.-> sl
  fcm -.-> sl
  enr -.-> sl
  spine -.-> sl
  sl --> sq[saved queries]
```
