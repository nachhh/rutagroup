# Ontology (draft, finalized in Phase 4)

Classes are business concepts, not tables. Each maps to a public model (`maps_to`).

```mermaid
flowchart LR
  Customer((Customer))
  Shipment((Shipment))
  Carrier((Carrier))
  Lane((Lane))
  Region((Region))
  Invoice((Invoice))
  Payment((Payment))
  Plan((Plan))
  Product((Product))

  Customer -- books --> Shipment
  Carrier -- carries --> Shipment
  Shipment -- follows --> Lane
  Lane -- "origin / destination" --> Region
  Customer -- located_in --> Region
  Customer -- "subscribes_to (temporal)" --> Plan
  Customer -- uses --> Product
  Invoice -- billed_to --> Customer
  Invoice -- bills_for --> Shipment
  Payment -- settles --> Invoice
```

Synonyms (feed the NL agent): Customer ≈ client, account, shipper, cliente · Shipment ≈ load,
booking, envío · Invoice ≈ bill, factura · Plan ≈ tier, subscription.
