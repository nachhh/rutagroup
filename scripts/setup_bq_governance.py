"""BigQuery governance, hands-on and free (on-demand pricing). Run: make bq-governance (= `apply`), then `demo`.

  apply     1. Policy-tag TAXONOMY `ruta_pii` > tag `email`, with fine-grained access control activated.
            2. DATA POLICY (dynamic masking) on that tag: readers with *Masked Reader* see SHA256(value).
            3. Attach the tag to the SOURCE column raw_pay.accounts.billing_contact.email.
               Classify once at the source → every view on top (udl_staging.stg_pay__accounts) is enforced too.
            4. AUTHORIZED VIEW: dataset `udl_share` with an aggregated revenue view that is allowed to read
               udl_marts, so consumers get the view without any access to the underlying marts.
  demo      Walks the three column-security states for YOUR principal, then a ROW ACCESS POLICY:
              no role → Access Denied  |  Masked Reader → hashed  |  Fine-Grained Reader → raw
            Your principal keeps Fine-Grained Reader at the end, so later phases (entity resolution) can read emails.
  teardown  Removes the tag from the column, the data policy, the taxonomy and the share dataset.

Notes
  * Even the project OWNER is blocked by a policy tag until granted a reader role: column-level security
    is enforced separately from dataset/table IAM.
  * `make load-bq` (WRITE_TRUNCATE + explicit schema) REPLACES the schema and drops the tag → re-run `apply`.
    In production the tag would live in the load schema / Terraform, not in a one-off script.
  * In dbt, the same tag can be attached to a model column with
        columns: [{name: contact_email, policy_tags: ['projects/<p>/locations/us/taxonomies/<t>/policyTags/<id>']}]
    + persist_docs: {columns: true}. Not wired here because taxonomy ids are generated per project.
  * Redshift equivalents: column-level GRANTs, CREATE MASKING POLICY (dynamic data masking), CREATE RLS POLICY.
Auth: ADC (gcloud auth application-default login). No key files.
"""

import os
import subprocess
import sys
import time

import google.auth
from dotenv import load_dotenv
from google.auth.transport.requests import AuthorizedSession
from google.cloud import bigquery

load_dotenv()
PROJECT = os.environ["GCP_PROJECT"]
LOC = "us"  # policy tags must live in the same location as the datasets (US multi-region)
DC = f"https://datacatalog.googleapis.com/v1/projects/{PROJECT}/locations/{LOC}"
DP = f"https://bigquerydatapolicy.googleapis.com/v1/projects/{PROJECT}/locations/{LOC}"
TAXONOMY, TAG, POLICY_ID = "ruta_pii", "email", "email_sha256"

creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
http = AuthorizedSession(creds)
bq = bigquery.Client(project=PROJECT)


def call(method, url, **kw):
    r = http.request(method, url, **kw)
    if r.status_code >= 400:
        raise RuntimeError(f"{method} {url} → {r.status_code}: {r.text[:300]}")
    return r.json() if r.text else {}


def me():
    account = subprocess.run(["gcloud", "config", "get-value", "account"], capture_output=True, text=True).stdout.strip()
    return f"user:{account}"


def find_tag():
    tax = next((t for t in call("GET", f"{DC}/taxonomies").get("taxonomies", []) if t["displayName"] == TAXONOMY), None)
    if not tax:
        return None, None
    tag = next((p for p in call("GET", f"https://datacatalog.googleapis.com/v1/{tax['name']}/policyTags").get("policyTags", [])
                if p["displayName"] == TAG), None)
    return tax, tag


def set_email_tag(tag_name):
    """Rewrite the accounts schema with (or without) the policy tag on billing_contact.email."""
    table = bq.get_table(f"{PROJECT}.raw_pay.accounts")
    schema = []
    for f in table.schema:
        if f.name == "billing_contact":
            subs = [bigquery.SchemaField(s.name, s.field_type, s.mode, description=s.description,
                                         policy_tags=bigquery.PolicyTagList([tag_name] if tag_name else []))
                    if s.name == "email" else s for s in f.fields]
            f = bigquery.SchemaField(f.name, f.field_type, f.mode, fields=subs, description=f.description)
        schema.append(f)
    table.schema = schema
    bq.update_table(table, ["schema"])


def apply():
    tax, tag = find_tag()
    if not tax:
        tax = call("POST", f"{DC}/taxonomies", json={
            "displayName": TAXONOMY, "description": "Personal data classification for Ruta Group",
            "activatedPolicyTypes": ["FINE_GRAINED_ACCESS_CONTROL"]})
    if not tag:
        tag = call("POST", f"https://datacatalog.googleapis.com/v1/{tax['name']}/policyTags",
                   json={"displayName": TAG, "description": "Email addresses (direct identifier)"})
    print(f"policy tag:     {TAXONOMY} > {TAG}")

    r = http.get(f"{DP}/dataPolicies/{POLICY_ID}")
    if r.status_code == 404:
        call("POST", f"{DP}/dataPolicies", json={
            "dataPolicyId": POLICY_ID, "dataPolicyType": "DATA_MASKING_POLICY",
            "policyTag": tag["name"], "dataMaskingPolicy": {"predefinedExpression": "SHA256"}})
    print(f"data policy:    {POLICY_ID} (masking rule SHA256)")

    set_email_tag(tag["name"])
    print("tagged column:  raw_pay.accounts.billing_contact.email")

    share = bigquery.Dataset(f"{PROJECT}.udl_share")
    share.location = "US"
    bq.create_dataset(share, exists_ok=True)
    view = bigquery.Table(f"{PROJECT}.udl_share.v_monthly_revenue")
    view.view_query = f"""
        select date_trunc(issued_date, month) as month, revenue_type, currency, sum(net_amount) as net_amount
        from `{PROJECT}.udl_marts.fct_invoice_lines`
        where revenue_type <> 'pass_through'
        group by 1, 2, 3"""
    bq.delete_table(view, not_found_ok=True)
    view = bq.create_table(view)
    marts = bq.get_dataset(f"{PROJECT}.udl_marts")
    entry = bigquery.AccessEntry(None, "view", view.reference.to_api_repr())
    if not any(e.entity_type == "view" and e.entity_id == entry.entity_id for e in marts.access_entries):
        marts.access_entries = [*marts.access_entries, entry]
        bq.update_dataset(marts, ["access_entries"])
    print("authorized view: udl_share.v_monthly_revenue → may read udl_marts (its readers need no access to udl_marts)")


def grant(resource_url, role, member):
    policy = call("POST", f"{resource_url}:getIamPolicy", json={})
    bindings = policy.get("bindings", [])
    b = next((b for b in bindings if b["role"] == role), None)
    if b is None:
        bindings.append({"role": role, "members": [member]})
    elif member not in b["members"]:
        b["members"].append(member)
    call("POST", f"{resource_url}:setIamPolicy", json={"policy": {**policy, "bindings": bindings}})


def revoke(resource_url, role, member):
    policy = call("POST", f"{resource_url}:getIamPolicy", json={})
    for b in policy.get("bindings", []):
        if b["role"] == role and member in b["members"]:
            b["members"].remove(member)
    policy["bindings"] = [b for b in policy.get("bindings", []) if b["members"]]
    call("POST", f"{resource_url}:setIamPolicy", json={"policy": policy})


def try_query(label, sql, expect_error=False, attempts=8):
    """IAM changes take up to a minute to propagate → retry until the expected outcome shows up."""
    for i in range(attempts):
        try:
            rows = [dict(r) for r in bq.query(sql).result()]
            if expect_error:
                raise PermissionError("still readable (propagating)")
            print(f"  {label}: {rows}")
            return
        except Exception as e:
            if expect_error and "ccess" in str(e):
                print(f"  {label}: ❌ {str(e).splitlines()[0][:140]}")
                return
            if i == attempts - 1:
                print(f"  {label}: (unexpected) {str(e)[:200]}")
                return
            time.sleep(10)


def demo():
    _, tag = find_tag()
    if not tag:
        sys.exit("Run `apply` first.")
    who = me()
    tag_url = f"https://datacatalog.googleapis.com/v1/{tag['name']}"
    pol_url = f"{DP}/dataPolicies/{POLICY_ID}"
    sql = f"select account_id, contact_email from `{PROJECT}.udl_staging.stg_pay__accounts` order by account_id limit 2"

    print("Column-level security on contact_email (through the dbt staging VIEW):")
    revoke(tag_url, "roles/datacatalog.categoryFineGrainedReader", who)
    revoke(pol_url, "roles/bigquerydatapolicy.maskedReader", who)
    try_query("1. no reader role       ", sql, expect_error=True)
    grant(pol_url, "roles/bigquerydatapolicy.maskedReader", who)
    try_query("2. Masked Reader        ", sql + " -- masked", attempts=10)
    grant(tag_url, "roles/datacatalog.categoryFineGrainedReader", who)
    revoke(pol_url, "roles/bigquerydatapolicy.maskedReader", who)
    try_query("3. Fine-Grained Reader  ", sql + " -- raw", attempts=10)

    print("Row access policy on udl_marts.fct_invoice_lines (only EUR rows for you):")
    t = f"`{PROJECT}.udl_marts.fct_invoice_lines`"
    count = f"select currency, count(*) as n from {t} group by 1 order by 1"
    bq.query(f"create or replace row access policy eur_only on {t} grant to ('{who}') filter using (currency = 'EUR')").result()
    print("  with policy:   ", [tuple(r) for r in bq.query(count).result()])
    # dropping the LAST policy needs DROP ALL: BQ refuses to silently re-open the table to everyone
    bq.query(f"drop all row access policies on {t}").result()
    print("  policy dropped:", [tuple(r) for r in bq.query(count).result()])
    print("  (once ANY row policy exists, principals not granted by some policy see zero rows)")


def teardown():
    tax, _ = find_tag()
    set_email_tag(None)
    http.delete(f"{DP}/dataPolicies/{POLICY_ID}")
    if tax:
        call("DELETE", f"https://datacatalog.googleapis.com/v1/{tax['name']}")
    bq.delete_dataset(f"{PROJECT}.udl_share", delete_contents=True, not_found_ok=True)
    print("removed tag, data policy, taxonomy and udl_share")


if __name__ == "__main__":
    {"apply": apply, "demo": demo, "teardown": teardown}[sys.argv[1] if len(sys.argv) > 1 else "apply"]()
