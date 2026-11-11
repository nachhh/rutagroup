# Source ERDs (raw layer)

## RutaShip: Postgres ≈ Redshift (`raw_ship`, relational / 3NF)

```mermaid
erDiagram
  SHIPPERS ||--o{ SHIPMENTS : books
  CARRIERS ||--o{ SHIPMENTS : moves
  LANES    ||--o{ SHIPMENTS : "routes via"
  SHIPMENTS ||--o{ SHIPMENT_EVENTS : emits

  SHIPPERS {
    int shipper_id PK
    string company_name
    string tax_id "messy format"
    string contact_email "PII"
    string country
    string region
    string tier
    timestamp created_at
    timestamp updated_at "drives SCD2 snapshot"
  }
  CARRIERS {
    int carrier_id PK
    string carrier_name
    string mode "FTL LTL parcel"
  }
  LANES {
    int lane_id PK
    string origin_region
    string dest_region
    int distance_km
  }
  SHIPMENTS {
    bigint shipment_id PK
    int shipper_id FK
    int carrier_id FK
    int lane_id FK
    string status
    numeric gmv_amount
    numeric booking_fee
    string currency
    timestamp booked_at
    timestamp promised_delivery_at
    timestamp updated_at
  }
  SHIPMENT_EVENTS {
    bigint event_id PK
    bigint shipment_id FK
    string event_type "booked picked_up in_transit delivered exception"
    timestamp event_ts
  }
```

## RutaPay: BigQuery (`raw_pay`, nested / document-style)

Nested fields are shown as separate "entities" for readability. In BQ they live *inside* the parent row.

```mermaid
erDiagram
  ACCOUNTS ||--o{ INVOICES : billed
  ACCOUNTS ||--o{ SUBSCRIPTION_CHANGES : "plan log"
  INVOICES ||--|{ INVOICE_LINES_nested : "lines ARRAY"
  ACCOUNTS ||--|{ ADDRESSES_nested : "addresses ARRAY"
  INVOICES ||--o{ PAYMENT_EVENTS : "paid by (via JSON payload)"

  ACCOUNTS {
    string account_id PK
    string legal_name
    string tax_id "different format than Ship"
    struct billing_contact "name, email PII, phone PII"
    array addresses "ARRAY of STRUCT"
    array tags "ARRAY of STRING"
    timestamp created_at
  }
  ADDRESSES_nested {
    string type "billing shipping"
    string country
    string region
    string city
  }
  INVOICES {
    string invoice_id PK
    string account_id FK
    string invoice_number "degenerate dim"
    string currency
    string status
    timestamp issued_at
    date due_date
    json metadata "shipment_ref, discount, source"
  }
  INVOICE_LINES_nested {
    int line_no
    string sku "SUB-* or FEE-*"
    numeric qty
    numeric unit_amount
    numeric tax_rate
  }
  PAYMENT_EVENTS {
    string event_id "dupes possible"
    timestamp received_at
    json payload "type, data.invoice_id, data.amount, data.method"
  }
  SUBSCRIPTION_CHANGES {
    string account_id FK
    string plan_code
    string change_type "start upgrade downgrade cancel"
    timestamp changed_at
  }
```

> **Cross-product links:** `INVOICES.metadata.shipment_ref` → `SHIPMENTS.shipment_id` (when Pay bills a
> Ship booking), and the *real-world* company behind `SHIPPERS` / `ACCOUNTS` (resolved in Phase 4).
