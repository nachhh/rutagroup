"""Tiny NL agent: plain-language question -> MCP tools -> governed answer.

    uv run python agent/ask.py "Do customers using both products churn less? Break it down by region"

How it works (the whole "LLM + semantic layer" pattern in ~100 lines):
  1. Start the metrics MCP server as a subprocess (stdio transport) and open an MCP client session.
  2. Ask the server which tools it has (list_tools) and hand those JSON schemas to the LLM as tools.
  3. Tool-calling loop: the LLM picks a tool + arguments -> we execute it through MCP -> feed the result back.
     It stops when the LLM writes a final answer.
  4. Print the answer plus every tool call made (the audit trail: which metric query produced the number).

The LLM never sees SQL or table names. It only chooses metrics/dimensions/filters from the governed catalog
(text-to-METRIC-query), and every guardrail is enforced server-side in mcp_server/metrics_server.py.

LLM: Claude Haiku 5.5 (claude-haiku-5-5, $0.10 / $0.50 per M input/output tokens). A question takes ~4-8 tool
round-trips, roughly 20-40K input tokens in total, so about $0.003-0.005 per question. The key is read from
ANTHROPIC_API_KEY in .env (gitignored).
"""

import asyncio
import json
import sys
from datetime import date
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
MODEL = "claude-haiku-5-5"
MAX_TURNS = 12  # hard stop for the tool loop (cost and runaway guard)

# The system prompt carries the CONTEXT-LAYER RULES: how to use the catalog, not the data itself.
# Note what is NOT here: no schema, no SQL, no table names. The tools supply the vocabulary.
SYSTEM = f"""You are Ruta Group's analytics assistant. Today is {date.today().isoformat()}.
Answer business questions ONLY with numbers returned by the tools. Never invent metrics, dimensions or values.

How to work:
- Metric questions (how much, how many, rates, trends): list_metrics -> list_dimensions -> query_metrics.
- Relationship questions (who is connected to whom, which carriers/lanes for a customer): find_entity -> kg_related.
- Map the user's words with get_ontology synonyms (client, cuenta, shipper -> Customer).
- Use CLOSED periods: the current month/quarter is partial (semi-additive and churn metrics look wrong there).
  Churn metrics need 90 days of hindsight, so the most recent ~3 months are provisional.
- "Churn" is ambiguous on purpose: there is subscription_churn_rate (RutaPay cancellations) and customer_churn_rate
  (gone from both products 90+ days). If the user doesn't say which, report both and label them.
- "Revenue" means total_revenue (all products, EUR) unless the user asks for MRR or booking fees.
- If a tool returns an error, read it and fix the call (wrong dimension name, etc.). Don't guess numbers.

Final answer: short, numbers first, then one line per caveat. End with "Query: <the mf_command(s) used>"."""


def _tool_result_text(result) -> str:
    """Flatten an MCP CallToolResult into text for the LLM (structured content if present, else text blocks)."""
    if getattr(result, "structured_content", None):
        return json.dumps(result.structured_content, default=str)[:20000]
    return "\n".join(getattr(c, "text", str(c)) for c in result.content)[:20000]


async def ask(question: str) -> None:
    load_dotenv(ROOT / ".env")
    client = anthropic.AsyncAnthropic()  # reads ANTHROPIC_API_KEY
    server = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_server" / "metrics_server.py")])

    async with stdio_client(server) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        # MCP tool schema -> Anthropic tool schema (same JSON Schema, different key names).
        mcp_tools = (await session.list_tools()).tools
        tools = [{"name": t.name, "description": t.description or "", "input_schema": t.input_schema} for t in mcp_tools]

        messages = [{"role": "user", "content": question}]
        audit = []
        for _ in range(MAX_TURNS):
            resp = await client.messages.create(
                model=MODEL, max_tokens=16000, system=SYSTEM, tools=tools, messages=messages,
            )
            # Append the FULL content (thinking + tool_use blocks), not just text: the API expects it back.
            messages.append({"role": "assistant", "content": resp.content})
            if resp.stop_reason != "tool_use":
                break

            results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                audit.append(f"{block.name}({json.dumps(block.input, ensure_ascii=False)})")
                print(f"  → {audit[-1]}", file=sys.stderr)
                try:
                    out = await session.call_tool(block.name, block.input)
                    text, is_error = _tool_result_text(out), bool(getattr(out, "is_error", False))
                except Exception as e:  # surface tool failures to the model instead of crashing
                    text, is_error = f"Tool failed: {e}", True
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": text, "is_error": is_error})
            # All tool results go back in ONE user message (keeps parallel tool calls working).
            messages.append({"role": "user", "content": results})

        answer = "\n".join(b.text for b in resp.content if b.type == "text")
        if resp.stop_reason == "refusal":
            answer = "(the model declined to answer)"
        print("\n" + answer)
        print(f"\n[{len(audit)} tool calls · stop={resp.stop_reason}]", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('usage: uv run python agent/ask.py "your question"')
    asyncio.run(ask(" ".join(sys.argv[1:])))
