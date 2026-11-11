"""Load RutaPay JSONL into BigQuery dataset `raw_pay` (works on the Sandbox and the free tier).

Why an explicit schema instead of `autodetect=True`?
  * Autodetect guesses: `metadata` would become a STRUCT whose fields depend on the sample, and
    later rows with new keys would fail. We want `metadata`/`payload` as the native JSON type
    (schemaless, queried with JSON_VALUE / JSON_QUERY) and `lines`/`addresses` as REPEATED RECORD
    (= ARRAY<STRUCT<...>>), which is the canonical BigQuery nested modeling pattern.
  * An explicit schema is a contract with the producer — a governance point.

Load jobs are free (and allowed even in the Sandbox, where DML/streaming are not). We load with
WRITE_TRUNCATE (replace), which is a load-job disposition, not DML.

Auth: Application Default Credentials (`gcloud auth application-default login`). No key files.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import bigquery
from google.cloud.bigquery import SchemaField as F

load_dotenv()
DATA = Path(__file__).resolve().parents[1] / "data" / "pay"
PROJECT = os.environ["GCP_PROJECT"]
LOCATION = os.getenv("BQ_LOCATION", "US")
DATASET = "raw_pay"

SCHEMAS = {
    "accounts": [
        F("account_id", "STRING", "REQUIRED"),
        F("legal_name", "STRING"),
        F("tax_id", "STRING"),
        F("billing_contact", "RECORD", fields=[          # STRUCT<name, email, phone>
            F("name", "STRING"),
            F("email", "STRING", description="PII"),
            F("phone", "STRING", description="PII"),
        ]),
        F("addresses", "RECORD", "REPEATED", fields=[    # ARRAY<STRUCT<...>>
            F("type", "STRING"), F("country", "STRING"), F("region", "STRING"),
            F("city", "STRING"), F("line1", "STRING", description="PII"), F("is_primary", "BOOL"),
        ]),
        F("tags", "STRING", "REPEATED"),                 # ARRAY<STRING>
        F("created_at", "TIMESTAMP"),
    ],
    "invoices": [
        F("invoice_id", "STRING", "REQUIRED"),
        F("account_id", "STRING"),
        F("invoice_number", "STRING"),
        F("currency", "STRING"),
        F("status", "STRING"),
        F("issued_at", "TIMESTAMP"),
        F("due_date", "DATE"),
        F("subtotal", "NUMERIC"),
        F("total", "NUMERIC"),
        F("lines", "RECORD", "REPEATED", fields=[
            F("line_no", "INT64"), F("sku", "STRING"), F("description", "STRING"),
            F("qty", "NUMERIC"), F("unit_amount", "NUMERIC"), F("tax_rate", "NUMERIC"),
        ]),
        F("metadata", "JSON"),                            # free-form: source, shipment_ref, discount{}
    ],
    "payment_events": [
        F("event_id", "STRING", "REQUIRED"),              # NOT unique: webhooks get redelivered
        F("received_at", "TIMESTAMP"),
        F("payload", "JSON"),                             # {type, data:{invoice_id, amount, method{}, refunds[]}}
    ],
    "subscription_changes": [
        F("account_id", "STRING", "REQUIRED"),
        F("plan_code", "STRING"),
        F("change_type", "STRING"),
        F("changed_at", "TIMESTAMP"),
    ],
}


def main():
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    ds = bigquery.Dataset(f"{PROJECT}.{DATASET}")
    ds.location = LOCATION
    client.create_dataset(ds, exists_ok=True)

    for table, schema in SCHEMAS.items():
        cfg = bigquery.LoadJobConfig(
            schema=schema,
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        with (DATA / f"{table}.jsonl").open("rb") as f:
            job = client.load_table_from_file(f, f"{PROJECT}.{DATASET}.{table}", job_config=cfg)
        job.result()
        t = client.get_table(f"{PROJECT}.{DATASET}.{table}")
        print(f"{DATASET}.{table:<22} {t.num_rows:>8} rows")


if __name__ == "__main__":
    main()
