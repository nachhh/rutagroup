"""Load RutaShip CSVs into Postgres schema `raw_ship` (our stand-in for Redshift).

Real-world analogue: on Redshift you'd `COPY raw_ship.shipments FROM 's3://...' IAM_ROLE ... FORMAT CSV`.
Here we use Postgres `COPY ... FROM STDIN`, same idea: bulk load, not row-by-row INSERTs.

The DDL also notes the Redshift physical design we *would* use (DISTKEY/SORTKEY) — Postgres ignores
it, but it's the first thing a Redshift reviewer asks about.
"""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()
DATA = Path(__file__).resolve().parents[1] / "data" / "ship"

DDL = """
drop schema if exists raw_ship cascade;
create schema raw_ship;

-- Redshift: DISTSTYLE ALL (small dimension, replicated to every node)
create table raw_ship.carriers (
    carrier_id   integer primary key,
    carrier_name varchar(200),
    mode         varchar(20)
);

-- Redshift: DISTSTYLE ALL
create table raw_ship.lanes (
    lane_id       integer primary key,
    origin_region varchar(50),
    dest_region   varchar(50),
    distance_km   integer
);

-- Redshift: DISTKEY(shipper_id) to co-locate with shipments; SORTKEY(updated_at)
create table raw_ship.shippers (
    shipper_id    integer primary key,
    company_name  varchar(300),
    tax_id        varchar(50),
    contact_email varchar(300),   -- PII
    contact_phone varchar(100),   -- PII
    country       char(2),
    region        varchar(50),
    tier          varchar(20),
    created_at    timestamp,
    updated_at    timestamp
);

-- Redshift: DISTKEY(shipper_id) (joins to shippers stay node-local); SORTKEY(booked_at)
create table raw_ship.shipments (
    shipment_id          bigint primary key,
    shipper_id           integer,
    carrier_id           integer,
    lane_id              integer,
    status               varchar(20),
    gmv_amount           numeric(18, 2),
    booking_fee          numeric(18, 2),
    currency             char(3),
    booked_at            timestamp,
    promised_delivery_at timestamp,
    updated_at           timestamp
);

-- Redshift: DISTKEY(shipment_id); SORTKEY(event_ts) — event logs are range-scanned by time
create table raw_ship.shipment_events (
    event_id    bigint primary key,
    shipment_id bigint,
    event_type  varchar(30),
    event_ts    timestamp
);
"""

TABLES = ["carriers", "lanes", "shippers", "shipments", "shipment_events"]


def main():
    dsn = (f"host={os.getenv('PG_HOST', 'localhost')} port={os.getenv('PG_PORT', '5432')} "
           f"dbname={os.getenv('PG_DB', 'ruta')} user={os.getenv('PG_USER', 'ruta')} password={os.getenv('PG_PASSWORD', 'ruta')}")
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(DDL)
        for t in TABLES:
            path = DATA / f"{t}.csv"
            with path.open("rb") as f, cur.copy(f"copy raw_ship.{t} from stdin with (format csv, header true)") as cp:
                while chunk := f.read(1 << 20):
                    cp.write(chunk)
            cur.execute(f"select count(*) from raw_ship.{t}")
            print(f"raw_ship.{t:<16} {cur.fetchone()[0]:>8} rows")
        # A "loaded_at" marker for source freshness checks in dbt
        cur.execute("create table raw_ship._load_audit as select now() as loaded_at")


if __name__ == "__main__":
    main()
