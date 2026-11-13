"""Governance as code: a CI gate over dbt's manifest.json (run `make govern`; exit 1 = PR blocked).

dbt already compiles every governance fact into target/manifest.json (access, group/owner, contract,
constraints, column meta, tests). Policies become small, reviewable Python rules over that graph, the same
idea as tools like dbt-project-evaluator / dbt-checkpoint, but explicit so you can read every rule.

Rules for PUBLIC models (= data products, consumable by other projects, the semantic layer, agents):
  R1 must belong to a group (an accountable owner)
  R2 must have an enforced contract (a stable interface)
  R3 must have a description
  R4 must not expose raw PII: no column with meta.pii = true, and no PII-looking column name unless it is
     explicitly declared masked/pseudonymized (catches the "forgot to classify it" leak)
Rule for every MART (public or not):
  R5 must have a primary-key test: unique + not_null on one column, unique_combination_of_columns,
     or a primary_key constraint
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ["ruta_ship", "ruta_udl"]
PII_NAME = re.compile(r"(email|phone|contact_name|address|line1|iban|birth)", re.I)
SAFE_SUFFIX = re.compile(r"(_sha256|_hash|_domain|_masked)$", re.I)


def col_meta(col):
    # column meta may live at the top level or under config (dbt ≥ 1.10); merge both
    return {**col.get("meta", {}), **col.get("config", {}).get("meta", {})}


def pk_tested(uid, node, tests):
    if any(c.get("type") == "primary_key" for c in node.get("constraints", [])):
        return True
    if any(con.get("type") == "primary_key" for col in node["columns"].values() for con in col.get("constraints", [])):
        return True
    unique, not_null = set(), set()
    for t in tests.get(uid, []):
        name = t["test_metadata"]["name"]
        if name == "unique_combination_of_columns":
            return True
        if name == "unique":
            unique.add(t.get("column_name"))
        if name == "not_null":
            not_null.add(t.get("column_name"))
    return bool(unique & not_null)


def check(project):
    path = ROOT / "dbt" / project / "target" / "manifest.json"
    if not path.exists():
        sys.exit(f"{path} not found: run `dbt parse` in dbt/{project} first (make govern does it).")
    m = json.loads(path.read_text())

    tests = {}
    for n in m["nodes"].values():
        if n["resource_type"] == "test" and n.get("test_metadata") and n.get("attached_node"):
            tests.setdefault(n["attached_node"], []).append(n)

    violations, public = [], []
    for uid, n in m["nodes"].items():
        if n["resource_type"] != "model":
            continue
        name = n["name"] + (f" (v{n['version']})" if n.get("version") else "")
        is_mart = "marts" in n["fqn"]

        if n.get("access") == "public":
            public.append(name)
            if not n.get("group"):
                violations.append((name, "R1", "public model has no group/owner"))
            if not n.get("contract", {}).get("enforced"):
                violations.append((name, "R2", "public model has no enforced contract"))
            if not n.get("description"):
                violations.append((name, "R3", "public model has no description"))
            for cname, col in n["columns"].items():
                meta = col_meta(col)
                if meta.get("pii") is True:
                    violations.append((name, "R4", f"column `{cname}` is classified PII (meta.pii) in a public model"))
                elif PII_NAME.search(cname) and not SAFE_SUFFIX.search(cname) \
                        and not (meta.get("masked") or meta.get("pseudonymized")):
                    violations.append((name, "R4", f"column `{cname}` looks like PII but is not declared masked/pseudonymized"))

        if is_mart and not pk_tested(uid, n, tests):
            violations.append((name, "R5", "mart has no primary-key test (unique+not_null, unique combination, or PK constraint)"))

    return public, violations


def main():
    failed = False
    for project in PROJECTS:
        public, violations = check(project)
        print(f"\n[{project}] public data products: {', '.join(sorted(public)) or '(none)'}")
        if violations:
            failed = True
            for name, rule, msg in violations:
                print(f"  ❌ {rule} {name}: {msg}")
        else:
            print("  ✅ all governance rules pass")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
