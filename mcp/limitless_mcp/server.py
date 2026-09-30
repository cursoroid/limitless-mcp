from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import ValidationError
from starlette.responses import JSONResponse

from limitless_mcp.auth import ApiKeyMiddleware
from limitless_mcp.log import logged, write_log
from limitless_mcp.tools import TOOLS


# FastMCP validates args before logged() runs, so bad input needs catching here
class LimitlessMCP(FastMCP):

    async def call_tool(self, name, arguments):
        try:
            return await super().call_tool(name, arguments)
        except ToolError as e:
            cause = e.__cause__
            if isinstance(cause, ValidationError):
                detail = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in cause.errors())
                err = ToolError(f"INVALID_INPUT: {detail}")
                write_log(name, arguments, ok=False, error=str(err))
                raise err from None
            if cause is None:  # unknown tool
                raise ToolError(f"NOT_FOUND: {e}") from None
            raise cause if isinstance(cause, ToolError) else e


# host=0.0.0.0 otherwise FastMCP rejects the agent's Host: mcp:8000 header
mcp = LimitlessMCP("limitless", stateless_http=True, host="0.0.0.0")
for fn in TOOLS:
    mcp.tool()(logged(fn))


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    return JSONResponse({"status": "ok"})


app = mcp.streamable_http_app()
app.add_middleware(ApiKeyMiddleware)
