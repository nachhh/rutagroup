# Ontology (Phase 4, final)

Source of truth: [`ontology/ruta_ontology.yml`](../../ontology/ruta_ontology.yml). Classes are business concepts, not
tables; each `maps_to` a public data product (governance rule R6) and generates KG nodes. Relations generate KG edges.

```mermaid
flowchart LR
  Customer((Customer<br/>dim_customer))
  Shipment((Shipment<br/>fct_shipments))
  Carrier((Carrier<br/>dim_carrier))
  Lane((Lane<br/>dim_lane))
  Region((Region<br/>seed_region_map))
  Invoice((Invoice<br/>fct_invoice_lines))
  Payment((Payment<br/>fct_payments))
  Plan((Plan<br/>seed_plans))
  Product((Product<br/>fct_product_enrollment))

  Customer -- books --> Shipment
  Carrier -- carries --> Shipment
  Shipment -- follows --> Lane
  Lane -- originates_in --> Region
  Lane -- ends_in --> Region
  Customer -- located_in --> Region
  Customer -- "subscribes_to (temporal)" --> Plan
  Customer -- uses --> Product
  Invoice -- billed_to --> Customer
  Invoice -- "bills_for (cross-product)" --> Shipment
  Payment -- settles --> Invoice
```

| Class | Synonyms (feed the NL agent) |
|---|---|
| Customer | client, account, shipper, merchant, cliente, cuenta, empresa |
| Shipment | load, booking, envío, carga |
| Carrier | transporter, trucking company, transportista |
| Lane | route, corridor, ruta |
| Region | territory, market, región, zona |
| Invoice | bill, factura |
| Payment | collection, cobro, pago |
| Plan | tier, subscription, package |
| Product | line of business, producto |

KG size: ~122k nodes, ~270k edges (`udl_kg.kg_nodes`, `udl_kg.kg_edges`).
