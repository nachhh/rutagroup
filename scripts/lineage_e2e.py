"""End-to-end lineage across BOTH dbt projects and BOTH clouds, generated from metadata (no hand-drawn arrows).

    make lineage   →   docs/diagrams/end-to-end-lineage.md   (Mermaid)

Why this exists: dbt's lineage stops at the project boundary. RutaShip (Postgres/"Redshift") and the UDL (BigQuery)
are two projects, and the hop between them is a Python replication script that dbt never sees. Stitching them
needs one explicit contract on each side, and both already exist:
  * ruta_ship exposure `udl_replication` = the models that get replicated (the script reads the same exposure);
  * ruta_udl source `ship_replica.<model name>` = where they land.
Same MODEL name on both sides (ruta_ship model `fct_shipments` ↔ ruta_udl source table `ship_replica.fct_shipments`)
→ we can draw the edge. It's a naming convention: renaming the source table silently breaks the edge. In production the same job is done by OpenLineage events
(Airflow provider + `dbt-ol`) collected in Marquez / DataHub / Dataplex; this script shows what that graph contains.

Level of detail: sources, PUBLIC models (the data products), semantic models → metrics, exposures (consumers).
Staging/intermediate models are collapsed: an edge A → B means "B depends on A through private models".
"""

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/diagrams/end-to-end-lineage.md"


def load(project):
    return json.loads((ROOT / "dbt" / project / "target" / "manifest.json").read_text())


def graph(m):
    """parents[uid] = direct upstream uids, for models/sources/exposures (tests and macros dropped)."""
    parents = {}
    for uid, n in {**m["nodes"], **m["exposures"]}.items():
        if n["resource_type"] in ("model", "exposure", "seed", "snapshot"):
            parents[uid] = [p for p in n["depends_on"].get("nodes", []) if p.split(".")[0] in ("model", "source", "seed", "snapshot")]
    return parents


def collapse(parents, keep):
    """For each kept node, its nearest kept ancestors (walk through non-kept nodes)."""
    out = {}
    for uid in keep:
        seen, stack, found = set(), list(parents.get(uid, [])), set()
        while stack:
            p = stack.pop()
            if p in seen:
                continue
            seen.add(p)
            if p in keep:
                found.add(p)
            else:
                stack.extend(parents.get(p, []))
        out[uid] = found
    return out


def node_id(uid):
    return re.sub(r"\W", "_", uid)  # Mermaid ids: letters, digits, underscore only


def main():
    lines = ["flowchart LR"]
    edges = set()
    labels = {}
    groups = defaultdict(list)

    for project, cloud in (("ruta_ship", "Postgres = Redshift"), ("ruta_udl", "BigQuery")):
        m = load(project)
        parents = graph(m)
        keep = {u for u, n in m["sources"].items()}
        keep |= {u for u, n in m["nodes"].items() if n["resource_type"] == "model" and n.get("access") == "public"
                 and n.get("is_latest_version") is not False}
        keep |= set(m["exposures"])
        for uid, ups in collapse(parents, keep).items():
            for up in ups:
                edges.add((up, uid))
        for uid in keep:
            n = m["sources"].get(uid) or m["nodes"].get(uid) or m["exposures"].get(uid)
            kind = n["resource_type"]
            name = f"{n['source_name']}.{n['name']}" if kind == "source" else n["name"]
            labels[uid] = name
            groups[f"{project} · {cloud} · {kind}s"].append(uid)

        # Semantic layer: semantic model (on a public model) → its metrics (one node listing them)
        if project == "ruta_udl":
            sm = json.loads((ROOT / "dbt/ruta_udl/target/semantic_manifest.json").read_text())
            mets = {x["name"]: x for x in sm["metrics"]}

            def models_of(name, seen=()):
                """Semantic models a metric reads: simple metrics name theirs; others recurse into their inputs."""
                tp = mets[name]["type_params"]
                if (tp.get("metric_aggregation_params") or {}).get("semantic_model"):
                    return {tp["metric_aggregation_params"]["semantic_model"]}
                inputs = [x["name"] for x in tp.get("metrics") or []]
                inputs += [tp[k]["name"] for k in ("numerator", "denominator") if tp.get(k)]
                c = tp.get("conversion_type_params") or {}
                inputs += [c[k]["name"] for k in ("base_measure", "conversion_measure", "base_metric", "conversion_metric")
                           if isinstance(c.get(k), dict)]
                cu = tp.get("cumulative_type_params") or {}
                if isinstance(cu.get("metric"), dict):
                    inputs.append(cu["metric"]["name"])
                return set().union(*[models_of(i, seen + (name,)) for i in inputs if i in mets and i not in seen]) if inputs else set()

            by_model = defaultdict(list)
            for name in mets:
                ms = models_of(name)
                key = next(iter(ms)) if len(ms) == 1 else "cross-model: " + " + ".join(sorted(ms))
                by_model[key].append(name)
                for model in ms:
                    edges.add((f"model.ruta_udl.{model}", f"metrics.{key}"))
            for model, mets in by_model.items():
                mid = f"metrics.{model}"
                labels[mid] = f"{model}: " + ", ".join(sorted(set(mets)))
                groups["semantic layer (MetricFlow metrics)"].append(mid)
                edges.add((mid, "exposure.ruta_udl.metrics_mcp_server"))

    # The cross-cloud stitch: ruta_ship exposure udl_replication → ruta_udl source ship_replica.<name>
    ship = load("ruta_ship")
    rep = next(e for e in ship["exposures"].values() if e["name"] == "udl_replication")
    for uid in rep["depends_on"]["nodes"]:
        name = ship["nodes"][uid]["name"]
        edges.add(("exposure.ruta_ship.udl_replication", f"source.ruta_udl.ship_replica.{name}"))
    labels["exposure.ruta_ship.udl_replication"] = "udl_replication (UNLOAD → S3 → GCS → BQ)"

    for g, uids in groups.items():
        lines.append(f'  subgraph {node_id(g)}["{g}"]')
        for u in sorted(set(uids)):
            shape = ('(["', '"])') if u.startswith("exposure") else ('[("', '")]') if u.startswith("source") else ('["', '"]')
            lines.append(f"    {node_id(u)}{shape[0]}{labels.get(u, u)}{shape[1]}")
        lines.append("  end")
    for a, b in sorted(edges):
        if a in labels and b in labels:
            lines.append(f"  {node_id(a)} --> {node_id(b)}")
    lines.append("  agent([agent/ask.py · Claude via MCP])")
    lines.append(f"  {node_id('exposure.ruta_udl.metrics_mcp_server')} --> agent")

    OUT.write_text(
        "# End-to-end lineage (generated)\n\n"
        "Generated by `make lineage` (scripts/lineage_e2e.py) from both `manifest.json` files, the semantic manifest and\n"
        "the exposures. Do not edit by hand. Staging/intermediate models are collapsed; sources are cylinders, consumers\n"
        "are pills. The cross-cloud edge comes from the `udl_replication` exposure ↔ the `ship_replica` sources.\n\n"
        "```mermaid\n" + "\n".join(lines) + "\n```\n"
    )
    print(f"wrote {OUT.relative_to(ROOT)}: {len(labels)} nodes, {len(edges)} edges")


if __name__ == "__main__":
    main()
