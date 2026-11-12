# Star schema: UDL marts (BigQuery)

Facts carry the durable `customer_key`. They join to the SCD2 `dim_customer` **as of** the event time
(`valid_from <= event_ts < valid_to`). `dim_date` plays several roles.

```mermaid
erDiagram
  DIM_CUSTOMER ||--o{ FCT_SHIPMENTS : "customer_key (as-of)"
  DIM_CUSTOMER ||--o{ FCT_INVOICE_LINES : "customer_key (as-of)"
  DIM_CUSTOMER ||--o{ FCT_PAYMENTS : customer_key
  DIM_CUSTOMER ||--o{ FCT_CUSTOMER_MONTHLY : customer_key
  DIM_CARRIER  ||--o{ FCT_SHIPMENTS : carrier_id
  DIM_LANE     ||--o{ FCT_SHIPMENTS : lane_id
  DIM_DATE     ||--o{ FCT_SHIPMENTS : "booked_date, delivered_date"
  DIM_DATE     ||--o{ FCT_INVOICE_LINES : "issued_date, due_date"
  DIM_DATE     ||--o{ FCT_CUSTOMER_MONTHLY : month
  DIM_PLAN     ||--o{ FCT_INVOICE_LINES : plan_code
  FCT_SHIPMENTS ||--o{ FCT_SHIPMENT_EVENTS : shipment_id
  FCT_SHIPMENTS ||--|| FCT_SHIPMENT_LIFECYCLE : shipment_id
  FCT_INVOICE_LINES }o--|| FCT_PAYMENTS : invoice_id

  DIM_CUSTOMER {
    string customer_sk PK "surrogate, one per version"
    string customer_key "canonical, durable (Phase 4)"
    string legal_name "SCD1"
    string contact_email "SCD1, PII"
    string region "SCD2"
    string current_region "type 6 lite"
    string plan_code "SCD2 (Pay)"
    string ship_tier "SCD2 (Ship)"
    bool is_multi_product
    timestamp valid_from
    timestamp valid_to
    bool is_current
  }
  DIM_DATE {
    date date_day PK
    date month_start
    int year
    int iso_week
  }
  DIM_CARRIER {
    int carrier_id PK
    string carrier_name
    string mode
  }
  DIM_LANE {
    int lane_id PK
    string origin_region
    string dest_region
    int distance_km
  }
  DIM_PLAN {
    string plan_code PK
    numeric monthly_price_eur
    int tier_rank
  }
  FCT_SHIPMENTS {
    bigint shipment_id PK
    string customer_key FK
    int carrier_id FK
    int lane_id FK
    timestamp booked_at
    date booked_date FK
    date delivered_date FK
    string status
    numeric gmv_eur "additive"
    numeric booking_fee_eur "additive"
    bool is_on_time "ratio input"
  }
  FCT_SHIPMENT_EVENTS {
    bigint event_id PK
    bigint shipment_id FK
    string event_type
    timestamp event_ts
  }
  FCT_SHIPMENT_LIFECYCLE {
    bigint shipment_id PK
    timestamp booked_at
    timestamp picked_up_at
    timestamp delivered_at
    numeric hours_to_pickup
    numeric hours_to_deliver
  }
  FCT_INVOICE_LINES {
    string invoice_id PK "with line_no"
    int line_no PK
    string invoice_number "degenerate dim"
    string customer_key FK
    timestamp issued_at
    date issued_date FK "partition"
    date due_date FK
    string sku
    string revenue_type "subscription, txn_fee, freight_fee, pass_through"
    string plan_code FK
    numeric amount_eur "additive"
    string billed_legal_name "as issued (audit)"
  }
  FCT_PAYMENTS {
    string invoice_id PK
    string customer_key FK
    timestamp paid_at
    string method_type
    numeric amount_paid_eur
    numeric amount_refunded_eur
    bool is_late
  }
  FCT_CUSTOMER_MONTHLY {
    string customer_key PK "with month"
    date month PK
    numeric mrr_eur "semi-additive"
    int shipments
    numeric gmv_eur
    bool active_ship
    bool active_pay
  }
```
