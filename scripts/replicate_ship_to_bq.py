"""Replicate RutaShip's PUBLIC marts (Postgres ≈ Redshift) into BigQuery `ship_replica`. Run: make replicate

WHAT gets replicated is decided by governance, not by this script: it reads the `udl_replication` exposure from
dbt/ruta_ship/target/manifest.json, and refuses any node that isn't `access: public`. Protected/private models
(raw contacts, events) never leave Postgres.

Local path                         Real-world path (Redshift → BigQuery)
---------------------------------  ---------------------------------------------------------------------------
1. SELECT from Postgres            UNLOAD ('select ...') TO 's3://bucket/ship/<table>/' IAM_ROLE ... FORMAT PARQUET
2. Arrow table → Parquet in memory   (Redshift writes Parquet files in parallel, one per slice)
3. (skipped)                        Storage Transfer Service: S3 → GCS (scheduled, incremental by prefix/date)
4. BigQuery load job (Parquet)      bq load / LoadJobConfig from gs://... (load jobs are free), or BigLake/Omni
                                    external tables to query S3 in place (no copy, but less performant)
Each table is replaced (WRITE_TRUNCATE) = a full snapshot. Big facts would be replicated incrementally by
partition (UNLOAD ... WHERE updated_at >= <watermark>), then merged in BQ.

Why Parquet: columnar, typed (decimals, timestamps), compressed. CSV loses types and breaks on delimiters.
Naive PG timestamps are declared UTC so BigQuery stores TIMESTAMP (not DATETIME), consistent with RutaPay.
"""

import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()
ROOT = Path(__file__).resolve().parents[1]
PROJECT = os.environ["GCP_PROJECT"]
DATASET = "ship_replica"


def public_marts():
    manifest = json.loads((ROOT / "dbt/ruta_ship/target/manifest.json").read_text())
    exposure = next(e for e in manifest["exposures"].values() if e["name"] == "udl_replication")
    out = []
    for uid in exposure["depends_on"]["nodes"]:
        node = manifest["nodes"][uid]
        if node.get("access") != "public":
            raise SystemExit(f"refusing to replicate non-public model {node['name']} ({node.get('access')})")
        out.append((node["name"], node["relation_name"]))  # dim_shipper → "ship_marts"."dim_shipper_v2" (latest)
    return out


def to_arrow(cur, sql, loaded_at):
    cur.execute(sql)
    names = [d.name for d in cur.description]
    rows = cur.fetchall()
    arrays = []
    for i, _ in enumerate(names):
        arr = pa.array([r[i] for r in rows])
        if pa.types.is_timestamp(arr.type) and arr.type.tz is None:
            arr = arr.cast(pa.timestamp("us", tz="UTC"))
        arrays.append(arr)
    names.append("_replicated_at")
    arrays.append(pa.array([loaded_at] * len(rows), pa.timestamp("us", tz="UTC")))
    return pa.Table.from_arrays(arrays, names=names)


def main():
    dsn = (f"host={os.getenv('PG_HOST', 'localhost')} port={os.getenv('PG_PORT', '5432')} dbname={os.getenv('PG_DB', 'ruta')} "
           f"user={os.getenv('PG_USER', 'ruta')} password={os.getenv('PG_PASSWORD', 'ruta')}")
    bq = bigquery.Client(project=PROJECT)
    ds = bigquery.Dataset(f"{PROJECT}.{DATASET}")
    ds.location = os.getenv("BQ_LOCATION", "US")
    bq.create_dataset(ds, exists_ok=True)
    loaded_at = datetime.now(timezone.utc)

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for name, relation in public_marts():
            table = to_arrow(cur, f"select * from {relation}", loaded_at)
            buf = io.BytesIO()
            pq.write_table(table, buf)
            buf.seek(0)
            cfg = bigquery.LoadJobConfig(
                source_format=bigquery.SourceFormat.PARQUET,
                write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
                decimal_target_types=["NUMERIC", "BIGNUMERIC"],
            )
            bq.load_table_from_file(buf, f"{PROJECT}.{DATASET}.{name}", job_config=cfg).result()
            print(f"{relation:<38} → {DATASET}.{name:<24} {table.num_rows:>7} rows")


if __name__ == "__main__":
    main()
