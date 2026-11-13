"""Deterministic synthetic data for Ruta Group (seed 42).

Writes to ./data/ :
  ship/  (RutaShip, relational CSVs → Postgres "Redshift")
     shippers.csv, carriers.csv, lanes.csv, shipments.csv, shipment_events.csv
  pay/   (RutaPay, nested JSONL → BigQuery)
     accounts.jsonl, invoices.jsonl, payment_events.jsonl, subscription_changes.jsonl
  truth/ (ground truth for evaluating entity resolution; never loaded as a source)
     company_xref.csv

Design notes (the data is messy on purpose, each mess maps to a lesson):
  * One pool of real-world COMPANIES; some are RutaShip shippers, some RutaPay accounts, some both.
    IDs differ per product → entity resolution (Phase 4).
  * tax_id formats differ per product (and are sometimes null), names vary (suffixes, casing,
    typos), some contacts use personal emails → match keys are imperfect.
  * Decoy companies with near-identical names → false-positive traps for fuzzy matching.
  * Multi-product customers churn less → the business question has a real answer to find.
  * Multi-currency by country → FX normalization decision (Phase 4/5).
  * Customers on both products get freight invoices issued via RutaPay with metadata.shipment_ref:
    the FREIGHT line is pass-through money, NOT RutaPay revenue → metric-definition trap (Phase 5).
  * Webhook payment events are redelivered (duplicates) → QUALIFY dedup (Phase 2).
"""

from __future__ import annotations

import csv
import json
import math
import random
import string
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from faker import Faker

SEED = 42
rng = random.Random(SEED)
fake = Faker(["es_ES", "es_MX", "en_US"])
Faker.seed(SEED)

ROOT = Path(__file__).resolve().parents[1] / "data"
HIST_START = date(2025, 5, 1)
HIST_END = date(2026, 10, 31)

N_SHIP_ONLY, N_BOTH, N_PAY_ONLY, N_DECOYS = 750, 550, 550, 40

# country → (region, currency, units of local currency per 1 EUR, cities)
COUNTRIES = {
    "ES": ("iberia", "EUR", 1.0, ["Madrid", "Barcelona", "Valencia", "Sevilla", "Bilbao"]),
    "PT": ("iberia", "EUR", 1.0, ["Lisboa", "Porto", "Braga"]),
    "MX": ("mexico", "MXN", 20.0, ["CDMX", "Monterrey", "Guadalajara", "Puebla"]),
    "CO": ("andean", "COP", 4400.0, ["Bogotá", "Medellín", "Cali"]),
    "CL": ("southern_cone", "CLP", 1000.0, ["Santiago", "Valparaíso", "Concepción"]),
    "AR": ("southern_cone", "USD", 1.08, ["Buenos Aires", "Córdoba", "Rosario"]),
}
COUNTRY_WEIGHTS = [35, 8, 25, 12, 10, 10]

LEGAL_SUFFIX = {"ES": "S.L.", "PT": "Lda.", "MX": "S.A. de C.V.", "CO": "S.A.S.", "CL": "SpA", "AR": "S.R.L."}
NAME_HEADS = ["Transportes", "Logística", "Distribuciones", "Comercial", "Grupo", "Industrias",
              "Alimentos", "Textiles", "Ferretería", "Farmacéutica", "Importadora", "Exportadora"]

PLANS = {"starter": 49.0, "growth": 199.0, "scale": 799.0}  # EUR / month
TIER_TAKE_RATE = {"basic": 0.10, "pro": 0.08, "enterprise": 0.06}


# --------------------------------------------------------------------------- helpers
def rand_dt(start: date, end: date) -> datetime:
    span = (end - start).days
    d = start + timedelta(days=rng.randint(0, max(span, 0)))
    return datetime(d.year, d.month, d.day, rng.randint(6, 21), rng.randint(0, 59), rng.randint(0, 59))


def month_starts(start: date, end: date):
    d = date(start.year, start.month, 1)
    while d <= end:
        yield d
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)


def iso(dt: datetime | date | None) -> str | None:
    return dt.isoformat() if dt else None


def slugify(name: str) -> str:
    table = str.maketrans("áéíóúñü", "aeiounu")
    return "".join(c for c in name.lower().translate(table) if c.isalnum())[:18]


@dataclass
class Company:
    idx: int
    name: str              # canonical trade name, e.g. "Transportes García"
    country: str
    city: str
    tax_core: str          # canonical tax id, e.g. "B12345678"
    domain: str
    created: date
    in_ship: bool
    in_pay: bool
    churn_ship: date | None = None
    churn_pay: date | None = None
    shipper_id: int | None = None
    account_id: str | None = None
    pay_legal_name: str | None = None
    pay_tax_id: str | None = None
    contact_first: str = field(default_factory=fake.first_name)
    contact_last: str = field(default_factory=fake.last_name)

    @property
    def region(self):
        return COUNTRIES[self.country][0]

    @property
    def currency(self):
        return COUNTRIES[self.country][1]

    @property
    def fx(self):
        return COUNTRIES[self.country][2]


# --------------------------------------------------------------------------- companies
def make_companies() -> list[Company]:
    companies: list[Company] = []
    kinds = ["ship"] * N_SHIP_ONLY + ["both"] * N_BOTH + ["pay"] * N_PAY_ONLY
    rng.shuffle(kinds)
    used_tax: set[str] = set()
    for i, kind in enumerate(kinds):
        country = rng.choices(list(COUNTRIES), COUNTRY_WEIGHTS)[0]
        name = f"{rng.choice(NAME_HEADS)} {fake.last_name()}"
        if rng.random() < 0.3:
            name += f" {rng.choice(['Hermanos', 'del Norte', 'del Sur', 'Express', 'Global', 'Iberia', 'Andina'])}"
        while True:
            tax = rng.choice("ABCF") + "".join(rng.choices(string.digits, k=8))
            if tax not in used_tax:
                used_tax.add(tax)
                break
        c = Company(
            idx=i, name=name, country=country, city=rng.choice(COUNTRIES[country][3]),
            tax_core=tax, domain=f"{slugify(name)}.{country.lower() if country != 'ES' else 'es'}",
            created=rand_dt(date(2023, 1, 1), date(2026, 8, 31)).date(),
            in_ship=kind in ("ship", "both"), in_pay=kind in ("pay", "both"),
        )
        # Multi-product customers churn less (≈12% vs ≈30%): the "answer" to find later.
        p_churn = 0.12 if kind == "both" else 0.30
        start = max(c.created, HIST_START)
        if c.in_ship and rng.random() < p_churn:
            c.churn_ship = rand_dt(start + timedelta(days=60), HIST_END).date()
        if c.in_pay and rng.random() < p_churn:
            # correlated churn for multi-product customers
            c.churn_pay = (c.churn_ship + timedelta(days=rng.randint(-20, 40))) if c.churn_ship else \
                rand_dt(start + timedelta(days=60), HIST_END).date()
            c.churn_pay = min(c.churn_pay, HIST_END)
        companies.append(c)

    # Decoys: distinct companies whose names collide with existing ones (fuzzy-match traps).
    for j in range(N_DECOYS):
        base = rng.choice(companies)
        decoy = Company(
            idx=len(companies), name=base.name + rng.choice([" Hermanos", " Express", "s"]),
            country=base.country, city=base.city,
            tax_core=rng.choice("ABCF") + "".join(rng.choices(string.digits, k=8)),
            domain=f"{slugify(base.name)}{rng.randint(2, 99)}.com",
            created=rand_dt(date(2024, 1, 1), date(2026, 6, 30)).date(),
            in_ship=not base.in_ship or rng.random() < 0.5, in_pay=not base.in_pay or rng.random() < 0.5,
        )
        companies.append(decoy)
    return companies


# --------------------------------------------------------------------------- messy renderings
def ship_tax_id(c: Company) -> str | None:
    if rng.random() < 0.05:
        return None
    t = c.tax_core
    return rng.choice([f"{t[0]}-{t[1:8]}-{t[8]}", t.lower(), f"{t[0]} {t[1:]}", t])


def pay_tax_id(c: Company) -> str | None:
    if rng.random() < 0.08:
        return None
    return rng.choice([c.tax_core, f"{c.country}{c.tax_core}", f"{c.country} {c.tax_core}"])


def ship_name(c: Company) -> str:
    return f"{c.name} {LEGAL_SUFFIX[c.country]}"


def pay_name(c: Company) -> str:
    n = c.name
    r = rng.random()
    if r < 0.4:
        n = n.upper()
    elif r < 0.5:  # typo: drop a random character
        k = rng.randint(1, len(n) - 2)
        n = n[:k] + n[k + 1:]
    if rng.random() < 0.3:
        n += f", {LEGAL_SUFFIX[c.country].replace('.', '')}"
    return n


def email(c: Company, personal_rate: float) -> str:
    user = f"{slugify(c.contact_first)}.{slugify(c.contact_last)}"
    if rng.random() < personal_rate:
        return f"{user}{rng.randint(1, 99)}@{rng.choice(['gmail.com', 'hotmail.com', 'yahoo.com'])}"
    return f"{user}@{c.domain}"


# --------------------------------------------------------------------------- RutaShip
def build_ship(companies: list[Company]):
    carriers = [{"carrier_id": i, "carrier_name": f"{fake.last_name()} {rng.choice(['Cargo', 'Freight', 'Transportes', 'Logistics'])}",
                 "mode": rng.choices(["FTL", "LTL", "parcel"], [3, 4, 3])[0],
                 "reliability": round(rng.uniform(0.70, 0.97), 3)} for i in range(1, 61)]
    regions = sorted({v[0] for v in COUNTRIES.values()})
    lanes, lane_id = [], 1
    for o in regions:
        for d in regions:
            for _ in range(3 if o == d else 2):
                dist = rng.randint(50, 900) if o == d else rng.randint(800, 9000)
                lanes.append({"lane_id": lane_id, "origin_region": o, "dest_region": d, "distance_km": dist})
                lane_id += 1
    lanes_by_origin = {r: [l for l in lanes if l["origin_region"] == r] for r in regions}

    shippers, shipments, events = [], [], []
    sid, shp_id, ev_id = 1000, 1, 1
    for c in (x for x in companies if x.in_ship):
        c.shipper_id = sid
        sid += 1
        tier = rng.choices(list(TIER_TAKE_RATE), [5, 3, 1])[0]
        created_at = rand_dt(c.created, c.created)
        shippers.append({
            "shipper_id": c.shipper_id, "company_name": ship_name(c), "tax_id": ship_tax_id(c),
            "contact_email": email(c, 0.10), "contact_phone": fake.phone_number(),
            "country": c.country, "region": c.region, "tier": tier,
            "created_at": iso(created_at), "updated_at": iso(created_at + timedelta(days=rng.randint(0, 30))),
        })
        active_from = max(c.created, HIST_START)
        active_to = c.churn_ship or HIST_END
        days = (active_to - active_from).days
        if days <= 0:
            continue
        rate = rng.lognormvariate(math.log(0.10), 0.7)  # shipments per day
        n = min(int(days * rate), 400)
        for _ in range(n):
            booked = rand_dt(active_from, active_to)
            lane = rng.choice(lanes_by_origin[c.region])
            carrier = rng.choice(carriers)
            gmv_eur = round(rng.lognormvariate(math.log(900), 0.6) * (1 + lane["distance_km"] / 3000), 2)
            gmv = round(gmv_eur * c.fx, 2)
            transit_days = max(1, round(lane["distance_km"] / 600))
            promised = booked + timedelta(days=transit_days + 1)
            age = (datetime(HIST_END.year, HIST_END.month, HIST_END.day, 23) - booked).days
            r = rng.random()
            if r < 0.03:
                status = "cancelled"
            elif age < transit_days + 1:
                status = "in_transit"
            elif r < 0.05:
                status = "exception"
            else:
                status = "delivered"
            # timeline
            evs = [("booked", booked)]
            if status != "cancelled":
                pick = booked + timedelta(hours=rng.randint(4, 48))
                evs.append(("picked_up", pick))
                for k in range(rng.randint(0, 2)):
                    evs.append(("in_transit", pick + timedelta(hours=12 * (k + 1))))
                if status == "delivered":
                    late = rng.random() > carrier["reliability"]
                    delivered = promised + timedelta(hours=rng.randint(2, 72)) if late else \
                        promised - timedelta(hours=rng.randint(0, 20))
                    evs.append(("delivered", max(delivered, evs[-1][1] + timedelta(hours=1))))
                elif status == "exception":
                    evs.append(("exception", evs[-1][1] + timedelta(hours=rng.randint(6, 48))))
            else:
                evs.append(("cancelled", booked + timedelta(hours=rng.randint(1, 24))))
            shipments.append({
                "shipment_id": shp_id, "shipper_id": c.shipper_id, "carrier_id": carrier["carrier_id"],
                "lane_id": lane["lane_id"], "status": status, "gmv_amount": gmv,
                "booking_fee": round(gmv * TIER_TAKE_RATE[tier], 2), "currency": c.currency,
                "booked_at": iso(booked), "promised_delivery_at": iso(promised),
                "updated_at": iso(evs[-1][1]),
            })
            for et, ts in evs:
                events.append({"event_id": ev_id, "shipment_id": shp_id, "event_type": et, "event_ts": iso(ts)})
                ev_id += 1
            shp_id += 1
    for cr in carriers:
        cr.pop("reliability")  # hidden generator parameter, not a source column
    return shippers, carriers, lanes, shipments, events


# --------------------------------------------------------------------------- RutaPay
def build_pay(companies: list[Company], shipments: list[dict]):
    ship_by_shipper: dict[int, list[dict]] = {}
    for s in shipments:
        ship_by_shipper.setdefault(s["shipper_id"], []).append(s)

    accounts, invoices, pay_events, sub_changes = [], [], [], []
    inv_no, evt_no = 100000, 1

    def new_event(payload: dict, received: datetime):
        nonlocal evt_no
        e = {"event_id": f"evt_{evt_no:07d}", "received_at": iso(received), "payload": payload}
        evt_no += 1
        pay_events.append(e)
        if rng.random() < 0.03:  # webhook redelivery: same event_id, later received_at
            pay_events.append({**e, "received_at": iso(received + timedelta(minutes=rng.randint(1, 600)))})

    def emit_invoice(c: Company, issued: datetime, lines: list[dict], metadata: dict):
        nonlocal inv_no
        inv_id = f"inv_{rng.getrandbits(48):012x}"
        inv_no += 1
        subtotal = sum(l["qty"] * l["unit_amount"] for l in lines)
        total = round(sum(l["qty"] * l["unit_amount"] * (1 + l["tax_rate"]) for l in lines), 2)
        due = (issued + timedelta(days=30)).date()
        # payment behaviour
        r = rng.random()
        if r < 0.02:
            status = "void"
        elif r < 0.10 and due > HIST_END - timedelta(days=45):
            status = "open"
        elif r < 0.14:
            status = "uncollectible"
        else:
            status = "paid"
        invoices.append({
            "invoice_id": inv_id, "account_id": c.account_id, "invoice_number": f"RP-{inv_no}",
            "currency": c.currency, "status": status, "issued_at": iso(issued), "due_date": iso(due),
            "subtotal": round(subtotal, 2), "total": total,
            "bill_to": {"legal_name": c.pay_legal_name, "tax_id": c.pay_tax_id},   # as printed on the document
            "lines": lines, "metadata": metadata,
        })
        method = rng.choices([{"type": "card", "brand": rng.choice(["visa", "mastercard", "amex"])},
                              {"type": "transfer"}, {"type": "sepa_debit"}], [5, 3, 2])[0]
        if status in ("paid", "uncollectible"):
            # a failed attempt first, sometimes
            if status == "uncollectible" or rng.random() < 0.08:
                new_event({"type": "payment.failed", "data": {"invoice_id": inv_id, "amount": total,
                           "currency": c.currency, "method": method,
                           "failure": {"code": rng.choice(["card_declined", "insufficient_funds"])}}},
                          issued + timedelta(days=rng.randint(1, 20), hours=rng.randint(0, 23)))
        if status == "paid":
            late = rng.random() < 0.2
            paid_at = datetime.combine(due, datetime.min.time()) + timedelta(days=rng.randint(1, 25)) if late \
                else issued + timedelta(days=rng.randint(0, 29), hours=rng.randint(0, 23))
            refunds = []
            if rng.random() < 0.03:
                refunds = [{"refund_id": f"re_{rng.getrandbits(32):08x}", "amount": round(total * rng.choice([0.1, 0.5, 1.0]), 2),
                            "reason": rng.choice(["duplicate", "requested_by_customer", "service_issue"])}]
            new_event({"type": "payment.succeeded", "data": {"invoice_id": inv_id, "amount": total,
                       "currency": c.currency, "method": method, "refunds": refunds}}, paid_at)

    for c in (x for x in companies if x.in_pay):
        c.account_id = f"acc_{rng.getrandbits(40):010x}"
        addresses = [{"type": "billing", "country": c.country, "region": c.region, "city": c.city,
                      "line1": fake.street_address(), "is_primary": rng.random() < 0.8}]
        for _ in range(rng.choices([0, 1, 2], [6, 3, 1])[0]):
            ct = rng.choice(list(COUNTRIES)) if rng.random() < 0.2 else c.country
            addresses.append({"type": "shipping", "country": ct, "region": COUNTRIES[ct][0],
                              "city": rng.choice(COUNTRIES[ct][3]), "line1": fake.street_address(), "is_primary": False})
        rng.shuffle(addresses)  # primary address is not always first → ARRAY_AGG/ORDER BY lesson
        c.pay_legal_name, c.pay_tax_id = pay_name(c), pay_tax_id(c)
        accounts.append({
            "account_id": c.account_id, "legal_name": c.pay_legal_name, "tax_id": c.pay_tax_id,
            "billing_contact": {"name": f"{c.contact_first} {c.contact_last}", "email": email(c, 0.15),
                                "phone": fake.phone_number()},
            "addresses": addresses,
            "tags": rng.sample(["smb", "ecommerce", "wholesale", "manufacturing", "retail", "priority", "partner"],
                               k=rng.randint(0, 3)),
            "created_at": iso(rand_dt(c.created, c.created)),
        })

        # subscription change log (append-only) → SCD2 via LEAD() in BigQuery
        start = max(c.created, HIST_START - timedelta(days=rng.randint(0, 200)))
        plan = rng.choices(list(PLANS), [5, 3, 1])[0]
        t = rand_dt(start, start)
        sub_changes.append({"account_id": c.account_id, "plan_code": plan, "change_type": "start", "changed_at": iso(t)})
        end = c.churn_pay or HIST_END
        while True:
            t = t + timedelta(days=rng.randint(90, 400))
            if t.date() >= end:
                break
            order = list(PLANS)
            i = order.index(plan)
            up = rng.random() < 0.65
            if up and i < 2:
                plan, ct = order[i + 1], "upgrade"
            elif not up and i > 0:
                plan, ct = order[i - 1], "downgrade"
            else:
                continue
            sub_changes.append({"account_id": c.account_id, "plan_code": plan, "change_type": ct, "changed_at": iso(t)})
        if c.churn_pay:
            sub_changes.append({"account_id": c.account_id, "plan_code": plan, "change_type": "cancel",
                                "changed_at": iso(rand_dt(c.churn_pay, c.churn_pay))})

        # monthly subscription invoices (+ transaction fee line)
        my_changes = [s for s in sub_changes if s["account_id"] == c.account_id]
        for m in month_starts(max(start, HIST_START), end):
            cur = [s for s in my_changes if s["changed_at"][:10] <= iso(m) and s["change_type"] != "cancel"]
            if not cur:
                continue
            p = cur[-1]["plan_code"]
            issued = datetime(m.year, m.month, 1, 2, 0, 0) + timedelta(minutes=rng.randint(0, 600))
            lines = [{"line_no": 1, "sku": f"SUB-{p.upper()}", "description": f"RutaPay {p} plan",
                      "qty": 1, "unit_amount": round(PLANS[p] * c.fx, 2), "tax_rate": 0.21 if c.country in ("ES", "PT") else 0.16}]
            n_tx = rng.randint(0, 120)
            if n_tx:
                lines.append({"line_no": 2, "sku": "FEE-TXN", "description": "Payment processing fees",
                              "qty": n_tx, "unit_amount": round(0.35 * c.fx, 2), "tax_rate": lines[0]["tax_rate"]})
            md = {"source": rng.choice(["billing_engine", "billing_engine", "api"])}
            if rng.random() < 0.05:
                md["discount"] = {"code": rng.choice(["WELCOME10", "LOYAL15", "PARTNER20"]), "pct": rng.choice([10, 15, 20])}
            emit_invoice(c, issued, lines, md)

        # multi-product customers: some freight invoices go out through RutaPay (cross-product link)
        if c.in_ship and c.shipper_id:
            for s in ship_by_shipper.get(c.shipper_id, []):
                if s["status"] != "delivered" or rng.random() > 0.35:
                    continue
                issued = datetime.fromisoformat(s["updated_at"]) + timedelta(hours=rng.randint(1, 72))
                if issued.date() > HIST_END:
                    continue
                lines = [{"line_no": 1, "sku": "FREIGHT", "description": "Freight (pass-through, collected for carrier)",
                          "qty": 1, "unit_amount": s["gmv_amount"], "tax_rate": 0.0},
                         {"line_no": 2, "sku": "FEE-PROC", "description": "Freight payment processing 2.5%",
                          "qty": 1, "unit_amount": round(s["gmv_amount"] * 0.025, 2), "tax_rate": 0.21 if c.country in ("ES", "PT") else 0.16}]
                emit_invoice(c, issued, lines, {"source": "rutaship_connector", "shipment_ref": f"SHP-{s['shipment_id']}"})

    return accounts, invoices, pay_events, sub_changes


# --------------------------------------------------------------------------- writers
def write_csv(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def write_jsonl(path: Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    companies = make_companies()
    shippers, carriers, lanes, shipments, events = build_ship(companies)
    accounts, invoices, pay_events, sub_changes = build_pay(companies, shipments)

    write_csv(ROOT / "ship/shippers.csv", shippers)
    write_csv(ROOT / "ship/carriers.csv", carriers)
    write_csv(ROOT / "ship/lanes.csv", lanes)
    write_csv(ROOT / "ship/shipments.csv", shipments)
    write_csv(ROOT / "ship/shipment_events.csv", events)
    write_jsonl(ROOT / "pay/accounts.jsonl", accounts)
    write_jsonl(ROOT / "pay/invoices.jsonl", invoices)
    write_jsonl(ROOT / "pay/payment_events.jsonl", pay_events)
    write_jsonl(ROOT / "pay/subscription_changes.jsonl", sub_changes)
    write_csv(ROOT / "truth/company_xref.csv", [
        {"company_idx": c.idx, "shipper_id": c.shipper_id, "account_id": c.account_id, "is_decoy": c.idx >= N_SHIP_ONLY + N_BOTH + N_PAY_ONLY}
        for c in companies])

    both = sum(1 for c in companies if c.shipper_id and c.account_id)
    print(f"companies={len(companies)} shippers={len(shippers)} accounts={len(accounts)} both={both}")
    print(f"carriers={len(carriers)} lanes={len(lanes)} shipments={len(shipments)} shipment_events={len(events)}")
    print(f"invoices={len(invoices)} payment_events={len(pay_events)} subscription_changes={len(sub_changes)}")


if __name__ == "__main__":
    main()
