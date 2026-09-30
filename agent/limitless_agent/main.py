# python -m limitless_agent.main              -> interactive
# python -m limitless_agent.main "question"   -> answer once and exit

import asyncio
import os
import sys

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")  # before pydantic_ai import

import httpx2
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.mcp import MCPToolset

MODEL = "anthropic:claude-sonnet-5-5"
REQUIRED_ENV = ("ANTHROPIC_API_KEY", "LIMITLESS_API_KEY", "MCP_URL")

SYSTEM_PROMPT = """\
You are an ERP assistant for plant controllers at a manufacturing company.
- Always answer from the tools. Never invent customers, SKUs, amounts or dates.
- Amounts are INR. Use lakh/crore: 1 lakh = 100000, 1 crore = 10000000, so ₹10L = 1000000.
- Cite IDs and SKUs for every record you mention.
- For critical stock, answer one line per SKU in this shape:
  BEARING_6205 (stock: 2, reorder: 5) - ORDER IMMEDIATELY
- If a tool returns an error, explain it plainly (e.g. the customer does not exist,
  the database is unavailable) and do not guess an answer.
- Be concise: short lists or tables, totals where useful.
"""


async def fail_on_401(response: httpx2.Response) -> None:
    # otherwise the MCP client swallows the 401 into a generic error
    if response.status_code == 401:
        response.raise_for_status()


def build_agent() -> Agent:
    http = httpx2.AsyncClient(
        headers={"X-API-Key": os.environ["LIMITLESS_API_KEY"]},
        event_hooks={"response": [fail_on_401]},
    )
    # "failed" = hand tool errors to Claude instead of retrying
    mcp = MCPToolset(os.environ["MCP_URL"], http_client=http, tool_error_behavior="failed")
    return Agent(MODEL, toolsets=[mcp], system_prompt=SYSTEM_PROMPT)


def find(exc: BaseException, kind: type):
    # pydantic-ai wraps errors (sometimes in ExceptionGroups), so dig for the real one
    todo, seen = [exc], set()
    while todo:
        e = todo.pop()
        if e is None or id(e) in seen:
            continue
        if isinstance(e, kind):
            return e
        seen.add(id(e))
        todo += [e.__cause__, e.__context__, *getattr(e, "exceptions", ())]
    return None


def explain(exc: BaseException) -> str:
    if err := find(exc, ModelHTTPError):
        if err.status_code in (401, 403):
            return "Anthropic rejected the API key. Check ANTHROPIC_API_KEY."
        return f"Anthropic API error (HTTP {err.status_code}). Try again shortly."
    if find(exc, ModelAPIError):
        return "Could not reach the Anthropic API. Check network access."
    if err := find(exc, httpx2.HTTPStatusError):
        if err.response.status_code == 401:
            return "MCP server rejected the API key. Check LIMITLESS_API_KEY."
        return f"MCP server error (HTTP {err.response.status_code})."
    if find(exc, httpx2.TransportError) or find(exc, OSError):
        return f"Cannot reach the MCP server at {os.environ['MCP_URL']}. Is it running?"
    return f"Unexpected error: {exc}"


async def repl(agent: Agent) -> None:
    history = []
    while True:
        try:
            question = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if question.lower() in ("exit", "quit"):
            return
        if not question:
            continue
        try:
            result = await agent.run(question, message_history=history)
        except Exception as exc:
            print(f"Error: {explain(exc)}\n")
            continue
        print(f"Agent: {result.output}\n")
        history = result.all_messages()


async def main(argv: list[str]) -> int:
    agent = build_agent()
    try:
        async with agent:
            if argv:
                print((await agent.run(" ".join(argv))).output)
            else:
                print("Limitless ERP agent. Ask a question, 'exit' or Ctrl-D to quit.")
                await repl(agent)
    except Exception as exc:
        print(f"Error: {explain(exc)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    if missing := [v for v in REQUIRED_ENV if not os.environ.get(v)]:
        sys.exit(f"Error: missing environment variables: {', '.join(missing)}")
    try:
        sys.exit(asyncio.run(main(sys.argv[1:])))
    except KeyboardInterrupt:
        sys.exit(130)
