# Phase 6: NL querying + MCP server + tiny agent (⏱ 45 min)

## Goal
Understand what "datos para LLMs / consultas en lenguaje natural" means in practice, and see an
agent use the semantic layer through **MCP** instead of writing raw SQL. Keep it simple: the agent
is documented in code comments only, with no extra docs or quiz for it.

## Concepts (chat intro + short section appended to `docs/05_semantic_layer.md`)
- **Text-to-SQL** (the LLM writes SQL against raw schemas): it hallucinates joins and definitions,
  and different questions produce different "revenue" numbers.
- **Text-to-metric-query** (the LLM selects `metrics / group_by / where / order` from a governed
  catalog, and the semantic layer compiles the SQL). This approach is deterministic, governed, and auditable.
- **Context layer** = what the agent gets as grounding: metric/dimension descriptions, ontology
  synonyms, entity relationships, sample values, and access rules.
- **MCP** (Model Context Protocol) is the standard way to expose tools/resources to agents. The
  official **dbt MCP server** exposes the dbt Semantic Layer (cloud), Discovery, and dbt CLI tools.
  Its SL tools need dbt Platform, so here we write a ~60-line local MCP server over MetricFlow
  that does the same thing.

## Files
| File | Content |
|---|---|
| `mcp_server/metrics_server.py` | `MCPServer` (python `mcp` SDK 2.x; was `FastMCP` in 1.x). Folder renamed from `mcp/` so it can't shadow the `mcp` package. Semantic-layer tools: `list_metrics()`, `list_dimensions(metrics)`, `list_entities(metrics)`, `query_metrics(metrics, group_by, where, order_by, start_time, end_time, limit)` → subprocess `mf query ... --csv`. Vocabulary: `get_ontology()` (a tool, not a resource, because plain tool-calling LLMs only see tools). KG (added): `find_entity(name, node_type)`, `kg_related(node_id, path)` over `udl_kg.kg_nodes/kg_edges` with parameterized SQL and allowlisted predicates. Validates metric names against `semantic_manifest.json` |
| `agent/ask.py` | ~80 lines. MCP client (stdio) → passes tools to the LLM → tool-call loop → prints the answer + the metric query used. **Claude Haiku 5.5** (`claude-haiku-5-5`, Anthropic SDK), decided at the checkpoint |

## Acceptance criteria
- `uv run agent/ask.py "Do customers using both products churn less? Break it down by region"` returns
  an answer that calls `query_metrics` with `customer_churn_rate` (+ `subscription_churn_rate`) grouped by `customer__is_multi_product, customer__region`
- An ambiguous question ("how are clients doing?") resolves "clients" → Customer via ontology synonyms
- Unknown metric names are rejected by the server (a guardrail)

## 🧭 Checkpoint: done
Claude Haiku 5.5 chosen: $0.10 / $0.50 per M tokens; a question uses ~4-6 tool round-trips, ≈ $0.003-0.005.

## Status log (2026-11-15)
- `make ask` on the business question: 4 tool calls, both churn metrics labelled, 2025 (closed period), caveats on
  small cells and selection bias, audit `mf` commands printed. ✅
- Relationship question (carriers for a customer + its revenue): `find_entity → kg_related → query_metrics` with
  `{{ Entity('customer') }} = <key>`. First run the agent **refused to guess** (no customer filter known); fixed by
  improving tool descriptions only. ✅
- Unknown metric (`churn`) and non-ontology KG predicates are rejected by the server. ✅
- **KG ↔ semantic-layer bridge made explicit:** ontology classes carry `semantic: {entity: customer}` /
  `{dimension: customer__region}`; `find_entity` returns a ready `metric_filter` derived from it; `make govern` rule
  **R7** fails if a link doesn't resolve in `semantic_manifest.json` (tested with a typo). Replaced the docstring hint.
- Phase-6 note: user asked for a 2-question concepts quiz (overrides "no quiz" for this phase).

## 🧠 Quiz 6: 2 questions (time-boxed): text-to-SQL vs text-to-metric-query; guardrails/evals
