"""Score entity resolution against the generator's ground truth (data/truth/company_xref.csv). Run: make eval-er

In real life there is no truth file: you estimate precision by STEWARD SAMPLING (review N random auto-merges per
rule) and recall by checking known links (e.g. invoices whose metadata.shipment_ref points to a shipment of the
same customer). Here the synthetic truth lets us measure exactly.

  precision = correct merges / all merges        (false merges corrupt metrics: revenue lands on the wrong customer)
  recall    = correct merges / all true pairs    (missed merges under-count multi-product customers)
"""

import csv
import os
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from google.cloud import bigquery

load_dotenv()
ROOT = Path(__file__).resolve().parents[1]
P = os.environ["GCP_PROJECT"]

truth = set()
decoys = set()
with (ROOT / "data/truth/company_xref.csv").open() as f:
    for r in csv.DictReader(f):
        if r["shipper_id"] and r["account_id"]:
            truth.add((r["shipper_id"], r["account_id"]))
        if r["is_decoy"] == "True":
            decoys.update(x for x in (r["shipper_id"], r["account_id"]) if x)

bq = bigquery.Client(project=P)
matches = list(bq.query(f"select shipper_id, account_id, match_rule from `{P}.udl_intermediate.int_customer_matches`").result())
queue = list(bq.query(f"select shipper_id, account_id, routing, match_rule from `{P}.udl_intermediate.int_customer_review_queue`").result())

pred = {(m.shipper_id, m.account_id): m.match_rule for m in matches}
tp = {k for k in pred if k in truth}
fp = {k for k in pred if k not in truth}
fn = truth - set(pred)
in_queue = {(q.shipper_id, q.account_id) for q in queue}

precision = len(tp) / len(pred) if pred else 0
recall = len(tp) / len(truth)
print(f"true multi-product pairs: {len(truth)}   predicted merges: {len(pred)}")
print(f"precision {precision:.3f}   recall {recall:.3f}   F1 {2 * precision * recall / (precision + recall):.3f}")
print("merges by rule:     ", dict(Counter(pred.values())))
print("false merges by rule:", dict(Counter(pred[k] for k in fp)))
print(f"review queue: {len(queue)} pairs {dict(Counter(q.routing for q in queue))}; "
      f"of which true matches: {len(in_queue & truth)}")
print(f"missed (not merged): {len(fn)}  → waiting in review queue: {len(fn & in_queue)}, invisible to rules: {len(fn - in_queue)}")
print(f"decoy records merged by mistake: {sum(1 for s, a in fp if s in decoys or a in decoys)}")
