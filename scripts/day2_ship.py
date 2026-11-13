"""Simulate "day 2" in RutaShip's source (Postgres raw_ship) to exercise dbt incrementals + snapshots.

What changes (each one teaches something):
  1. 60 shippers upgrade tier, 15 relocate (country/region)  → `dbt snapshot` opens new SCD2 versions.
  2. In-transit shipments get delivered (status + updated_at)  → fct_shipments MERGE updates rows.
  3. 300 new shipments booked + events                         → MERGE inserts rows; events APPEND.
  4. Two LATE-ARRIVING corrections (gmv fixed, but updated_at is OLD, e.g. replicated late):
       - one 2 days behind the fact's watermark → inside the 3-day lookback → CAUGHT
       - one 5 days behind                     → outside the lookback      → MISSED
         (the reconciliation test flags it; `--full-refresh` fixes it)

Run once after the first `dbt build`:  make day2   then: make snapshot ship
"""

import os
import random
from datetime import datetime, timedelta

import psycopg
from dotenv import load_dotenv

load_dotenv()
rng = random.Random(7)
DAY2 = datetime(2026, 11, 5, 10, 0, 0)


def main():
    dsn = (f"host={os.getenv('PG_HOST', 'localhost')} port={os.getenv('PG_PORT', '5432')} "
           f"dbname={os.getenv('PG_DB', 'ruta')} user={os.getenv('PG_USER', 'ruta')} password={os.getenv('PG_PASSWORD', 'ruta')}")
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("select max(updated_at) from ship_marts.fct_shipments")
        watermark = cur.fetchone()[0]
        if watermark is None:
            raise SystemExit("Run `make ship` first (fct_shipments must exist).")

        # 1. shipper changes → SCD2
        cur.execute("update raw_ship.shippers set tier = case tier when 'basic' then 'pro' else 'enterprise' end, "
                    "updated_at = %s where shipper_id in (select shipper_id from raw_ship.shippers "
                    "where tier <> 'enterprise' order by shipper_id limit 60)", (DAY2,))
        print(f"tier upgrades:         {cur.rowcount}")
        cur.execute("update raw_ship.shippers set country = 'ES', region = 'iberia', updated_at = %s "
                    "where shipper_id in (select shipper_id from raw_ship.shippers where region = 'mexico' "
                    "order by shipper_id desc limit 15)", (DAY2 + timedelta(hours=1),))
        print(f"relocations MX→ES:     {cur.rowcount}")

        cur.execute("select coalesce(max(event_id), 0) from raw_ship.shipment_events")
        next_ev = cur.fetchone()[0] + 1

        # 2. deliveries for in-transit shipments
        cur.execute("select shipment_id from raw_ship.shipments where status = 'in_transit'")
        in_transit = [r[0] for r in cur.fetchall()]
        for sid in in_transit:
            ts = DAY2 - timedelta(hours=rng.randint(1, 96))
            cur.execute("insert into raw_ship.shipment_events values (%s, %s, 'delivered', %s)", (next_ev, sid, ts))
            cur.execute("update raw_ship.shipments set status = 'delivered', updated_at = %s where shipment_id = %s", (ts, sid))
            next_ev += 1
        print(f"deliveries:            {len(in_transit)}")

        # 3. new bookings
        cur.execute("select max(shipment_id) from raw_ship.shipments")
        next_shp = cur.fetchone()[0] + 1
        cur.execute("select shipper_id, tier from raw_ship.shippers order by random() limit 300")
        take = {"basic": 0.10, "pro": 0.08, "enterprise": 0.06}
        for shipper_id, tier in cur.fetchall():
            booked = DAY2 - timedelta(hours=rng.randint(1, 100))
            gmv = round(rng.uniform(300, 3000), 2)
            cur.execute("insert into raw_ship.shipments values (%s,%s,%s,%s,'in_transit',%s,%s,'EUR',%s,%s,%s)",
                        (next_shp, shipper_id, rng.randint(1, 60), rng.randint(1, 36), gmv, round(gmv * take[tier], 2),
                         booked, booked + timedelta(days=3), booked))
            cur.execute("insert into raw_ship.shipment_events values (%s, %s, 'booked', %s)", (next_ev, next_shp, booked))
            next_ev += 1
            next_shp += 1
        print("new shipments:         300")

        # 4. late-arriving corrections (old updated_at)
        cur.execute("select shipment_id from raw_ship.shipments where status = 'delivered' and booked_at < '2026-06-01' "
                    "order by shipment_id limit 2")
        a, b = (r[0] for r in cur.fetchall())
        for sid, days_behind in ((a, 2), (b, 5)):
            cur.execute("update raw_ship.shipments set gmv_amount = gmv_amount + 100, updated_at = %s where shipment_id = %s",
                        (watermark - timedelta(days=days_behind), sid))
        print(f"late corrections:      shipment {a} (2 days behind watermark → caught), "
              f"shipment {b} (5 days behind → MISSED by lookback)")
        print(f"watermark was:         {watermark}")


if __name__ == "__main__":
    main()
