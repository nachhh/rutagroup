"""Metrics MCP server: governed semantic-layer metrics as tools for an LLM agent.

Why this exists (the core idea of Phase 6):
  * Text-to-SQL = the LLM writes SQL against raw tables -> invents joins, fans out, re-defines "revenue".
  * Text-to-METRIC-QUERY = the LLM only *chooses* (metrics, group_by, where, order, limit) from a governed
    catalog; MetricFlow compiles the SQL. Same question -> same SQL -> same number as BI. Auditable.

MCP (Model Context Protocol) is the standard plug between agents and tools: this server speaks MCP over stdio,
so any MCP client (our agent/ask.py, Claude Desktop, an IDE) can use it unchanged.
The official dbt MCP server does the same against dbt Platform's hosted Semantic Layer; this is a ~local
equivalent over the open-source `mf` CLI.

Guardrails live HERE, in the server, not in the prompt (prompts are suggestions, servers are enforcement):
  1. Allowlist: only metrics in the dbt semantic manifest can be queried; unknown names are rejected.
  2. Read-only: the only thing executed is `mf query` (SELECTs compiled by MetricFlow), never free SQL.
  3. Row cap: limit is clamped to MAX_ROWS so a model can't pull a whole table into its context.
  4. Audit: every answer returns the exact mf command used, so a human can re-run it.
The warehouse credentials are the server's (least-privilege SA/ADC), never the LLM's.

Run standalone (debug):  uv run python mcp_server/metrics_server.py   (speaks MCP on stdin/stdout)
Needs a fresh manifest:   cd dbt/ruta_udl && dbt parse      (`make ask` does it)
"""

import csv
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

import yaml
from google.cloud import bigquery
from mcp.server.mcpserver import MCPServer  # mcp SDK 2.x name (was FastMCP in 1.x)

ROOT = Path(__file__).resolve().parents[1]
DBT_DIR = ROOT / "dbt" / "ruta_udl"
MANIFEST = DBT_DIR / "target" / "semantic_manifest.json"
ONTOLOGY = ROOT / "ontology" / "ruta_ontology.yml"
MAX_ROWS = 200
ENV = {**os.environ, "DBT_PROFILES_DIR": str(ROOT)}
GCP_PROJECT = os.environ.get("GCP_PROJECT", "rutagroup")
KG = f"{GCP_PROJECT}.udl_kg"  # kg_nodes / kg_edges, generated from the ontology (Phase 4)

mcp = MCPServer("ruta-metrics")


def _metrics() -> dict:
    """Metric catalog straight from MetricFlow's compiled manifest: the single source of truth."""
    sm = json.loads(MANIFEST.read_text())
    return {m["name"]: m for m in sm["metrics"]}


def _mf(args: list[str]) -> subprocess.CompletedProcess:
    # `mf` (MetricFlow CLI) compiles the metric request to warehouse SQL and runs it on BigQuery.
    return subprocess.run(["mf", *args], cwd=DBT_DIR, env=ENV, capture_output=True, text=True, timeout=180)


@mcp.tool()
def list_metrics() -> list[dict]:
    """List the governed business metrics (name, type, description). Call this first: never invent metric names."""
    return [
        {"name": n, "type": m["type"], "label": m.get("label"), "description": m.get("description")}
        for n, m in sorted(_metrics().items())
    ]


@mcp.tool()
def list_dimensions(metrics: list[str]) -> str:
    """List the dimensions you can group/filter the given metrics by (e.g. customer__region, metric_time__quarter).
    Names are paths: `entity__dimension`; time dimensions take a grain suffix: day, week, month, quarter, year."""
    unknown = set(metrics) - _metrics().keys()
    if unknown:
        return f"Rejected: unknown metrics {sorted(unknown)}. Use list_metrics()."
    r = _mf(["list", "dimensions", "--metrics", ",".join(metrics)])
    return r.stdout if r.returncode == 0 else f"Error: {r.stderr[-1500:] or r.stdout[-1500:]}"


@mcp.tool()
def list_entities(metrics: list[str]) -> str:
    """List the entities (join keys: customer, shipment, carrier, ...) reachable from the given metrics.
    Entities are the semantic layer's join graph; dimension names are prefixed with them (customer__region)."""
    unknown = set(metrics) - _metrics().keys()
    if unknown:
        return f"Rejected: unknown metrics {sorted(unknown)}. Use list_metrics()."
    r = _mf(["list", "entities", "--metrics", ",".join(metrics)])
    return r.stdout if r.returncode == 0 else f"Error: {r.stderr[-1500:] or r.stdout[-1500:]}"


# ---- Knowledge-graph tools: RELATIONSHIP questions ("which carriers move ACME's freight?").
# Metric questions go to query_metrics; the KG answers "who is connected to whom". Both sit on the UDL.
# Guardrails: parameterized SQL (no string-built user input), predicates allowlisted from the ontology,
# a bytes-billed cap, and only node labels/types come back (no PII columns live in the KG).

def _bq(sql: str, params: list) -> list[dict]:
    cfg = bigquery.QueryJobConfig(query_parameters=params, maximum_bytes_billed=10**9)  # 1 GB cap, free tier
    return [dict(r) for r in bigquery.Client(project=GCP_PROJECT).query(sql, job_config=cfg).result()]


def _predicates() -> set[str]:
    o = yaml.safe_load(ONTOLOGY.read_text())
    return {r["predicate"] for r in o.get("relations", [])}


@mcp.tool()
def find_entity(name: str, node_type: str | None = None, limit: int = 5) -> list[dict]:
    """Resolve a name the user typed ("ACME", "Grupo Cuevas") to knowledge-graph node ids like 'customer:123'.
    node_type: optional ontology class (Customer, Carrier, Lane, ...).
    Each row carries `metric_filter`: paste it as query_metrics(where=...) to get metrics for that node."""
    sql = f"""select node_id, node_type, label from `{KG}.kg_nodes`
              where lower(label) like concat('%', lower(@name), '%') and (@t is null or node_type = @t)
              order by length(label) limit @lim"""
    rows = _bq(sql, [bigquery.ScalarQueryParameter("name", "STRING", name),
                     bigquery.ScalarQueryParameter("t", "STRING", node_type),
                     bigquery.ScalarQueryParameter("lim", "INT64", max(1, min(limit, 20)))])
    for r in rows:
        r["metric_filter"] = _metric_filter(r["node_type"], r["node_id"])
    return rows


def _metric_filter(node_type: str, node_id: str) -> str | None:
    """KG node -> semantic-layer filter, derived from the ontology's explicit `semantic:` link (not hard-coded).
    customer:-801… + {entity: customer}          -> {{ Entity('customer') }} = -801…
    region:iberia  + {dimension: customer__region} -> {{ Dimension('customer__region') }} = 'iberia'"""
    link = yaml.safe_load(ONTOLOGY.read_text())["classes"].get(node_type, {}).get("semantic") or {}
    key = node_id.split(":", 1)[1]
    value = key if key.lstrip("-").isdigit() else "'" + key.replace("'", "") + "'"
    if "entity" in link:
        return f"{{{{ Entity('{link['entity']}') }}}} = {value}"
    if "dimension" in link:
        return f"{{{{ Dimension('{link['dimension']}') }}}} = {value}"
    return None  # class has no semantic-layer counterpart (e.g. Invoice): KG-only


@mcp.tool()
def kg_related(node_id: str, path: list[str], limit: int = 10) -> dict:
    """Follow ontology relations from a node and return the connected nodes, ranked by number of paths.
    `paths` counts the distinct chains walked, so for ['books', '^carries'] it equals the NUMBER OF SHIPMENTS
    each carrier moved for that customer.
    path: predicates in order; prefix '^' to walk an edge backwards.
      Carriers that moved a customer's freight: node_id='customer:123', path=['books', '^carries']
      Lanes a customer ships on:               node_id='customer:123', path=['books', 'follows']"""
    allowed = _predicates()
    bad = [p for p in path if p.lstrip("^") not in allowed]
    if bad or not 1 <= len(path) <= 3:
        return {"error": f"Rejected path {path}. Allowed predicates: {sorted(allowed)} (max 3 hops)."}
    # Build one join per hop. Only allowlisted predicate names reach the SQL text; values are parameters.
    froms, cur = [], "@start"
    for i, p in enumerate(path):
        rev = p.startswith("^")
        src, dst = ("dst_id", "src_id") if rev else ("src_id", "dst_id")
        froms.append(f"join `{KG}.kg_edges` e{i} on e{i}.{src} = {cur} and e{i}.predicate = '{p.lstrip('^')}'")
        cur = f"e{i}.{dst}"
    sql = f"""select {cur} as node_id, n.node_type, n.label, count(*) as paths
              from (select 1) {' '.join(froms)} left join `{KG}.kg_nodes` n on n.node_id = {cur}
              group by 1, 2, 3 order by paths desc limit @lim"""
    rows = _bq(sql, [bigquery.ScalarQueryParameter("start", "STRING", node_id),
                     bigquery.ScalarQueryParameter("lim", "INT64", max(1, min(limit, 50)))])
    return {"start": node_id, "path": path, "rows": rows}


@mcp.tool()
def get_ontology() -> dict:
    """Business vocabulary: classes (Customer, Shipment, Carrier, ...) with descriptions and SYNONYMS
    (client/cuenta/shipper -> Customer) and relations. Use it to map the user's words to entities and metrics."""
    o = yaml.safe_load(ONTOLOGY.read_text())
    classes = {k: {"description": v.get("description"), "synonyms": v.get("synonyms", []),
                   "semantic_layer_link": v.get("semantic")}
               for k, v in o.get("classes", {}).items()}
    relations = [{k: r.get(k) for k in ("subject", "predicate", "object", "description")} for r in o.get("relations", [])]
    return {"classes": classes, "relations": relations}


@mcp.tool()
def query_metrics(
    metrics: list[str],
    group_by: list[str] | None = None,
    where: str | None = None,
    order_by: list[str] | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int = 50,
) -> dict:
    """Run a governed metric query through the semantic layer (MetricFlow writes the SQL).

    metrics:   names from list_metrics(), e.g. ["customer_churn_rate"]
    group_by:  e.g. ["customer__is_multi_product", "customer__region", "metric_time__quarter"]
    where:     MetricFlow Jinja filter, e.g. "{{ Dimension('customer__region') }} = 'iberia'";
               one customer/carrier/region: use the `metric_filter` returned by find_entity.
               Entities (customer, carrier, lane, shipment) can also be used directly in group_by.
    order_by:  metric or dimension names; prefix '-' for descending, e.g. ["-total_revenue"]
    start_time/end_time: ISO dates bounding metric_time. Prefer CLOSED periods (the current month/quarter is
               partial: semi-additive and churn metrics look wrong there).
    """
    unknown = set(metrics) - _metrics().keys()
    if unknown:  # guardrail 1: allowlist
        return {"error": f"Rejected: unknown metrics {sorted(unknown)}. Use list_metrics()."}
    limit = max(1, min(int(limit), MAX_ROWS))  # guardrail 3: row cap

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        out = f.name
    args = ["query", "--metrics", ",".join(metrics), "--limit", str(limit)]
    if group_by:
        args += ["--group-by", ",".join(group_by)]
    if where:
        args += ["--where", where]
    if order_by:
        args += ["--order", ",".join(order_by)]
    if start_time:
        args += ["--start-time", start_time]
    if end_time:
        args += ["--end-time", end_time]

    audit = "mf " + shlex.join(args)  # guardrail 4: the exact, reproducible request
    r = _mf(args + ["--csv", out])
    if r.returncode != 0:
        return {"error": (r.stderr or r.stdout)[-2000:], "mf_command": audit}
    with open(out, newline="") as fh:
        rows = list(csv.DictReader(fh))
    os.unlink(out)
    return {"mf_command": audit, "row_count": len(rows), "rows": rows}


if __name__ == "__main__":
    mcp.run()  # stdio transport: the client launches this process and talks JSON-RPC over stdin/stdout
