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
| `mcp/metrics_server.py` | `FastMCP` server (python `mcp` SDK). Tools: `list_metrics()`, `list_dimensions(metrics)`, `query_metrics(metrics, group_by, where, order_by, limit)` → subprocess `mf query ... --csv`. Resource: `ontology://ruta` (synonyms). Validates names against `semantic_manifest.json` |
| `agent/ask.py` | ~80 lines. MCP client (stdio) → passes tools to the LLM → tool-call loop → prints the answer + the metric query used. **Gemini free tier** (`google-genai`) or **Claude Haiku** (Anthropic SDK). Decided at the checkpoint |

## Acceptance criteria
- `uv run agent/ask.py "Do customers using both products churn less? Break it down by region"` returns
  an answer that calls `query_metrics` with `churn_rate` grouped by `customer__is_multi_product, customer__region`
- An ambiguous question ("how are clients doing?") resolves "clients" → Customer via ontology synonyms
- Unknown metric names are rejected by the server (a guardrail)

## 🧭 Checkpoint
Gemini vs Haiku. Claude will estimate the token cost per question before you choose.

## 🧠 Quiz 6: 4 questions on concepts only (text-to-SQL vs text-to-metric, context layer, MCP role, guardrails/evals)
