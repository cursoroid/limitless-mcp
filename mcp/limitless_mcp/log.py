import functools
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import ValidationError

LOG_FILE = Path(os.environ.get("LOG_DIR", "logs")) / "tool-calls.jsonl"


def write_log(tool: str, params: dict, **fields) -> None:
    """One JSON line per tool call, to stderr (docker compose logs) and logs/tool-calls.jsonl."""
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "tool": tool, "params": params, **fields}
    line = json.dumps(entry, default=str)
    print(line, file=sys.stderr, flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(line + "\n")


def logged(fn):
    """Time and log every call; map exceptions to ToolErrors with a code prefix."""

    @functools.wraps(fn)
    def wrapper(**params):
        start = time.perf_counter()
        try:
            result = fn(**params)
        except ToolError as e:
            err = e
        except (ValueError, ValidationError) as e:
            err = ToolError(f"INVALID_INPUT: {e}")
        except psycopg.OperationalError:
            err = ToolError("DB_UNAVAILABLE: database unreachable, try again shortly")
        except psycopg.Error as e:
            err = ToolError(f"DB_ERROR: {type(e).__name__}")
        except Exception as e:
            err = ToolError(f"INTERNAL: {type(e).__name__}")
        else:
            ms = round((time.perf_counter() - start) * 1000)
            write_log(fn.__name__, params, ok=True, rows=getattr(result, "total", 1), result=result.model_dump(), ms=ms)
            return result
        write_log(fn.__name__, params, ok=False, error=str(err), ms=round((time.perf_counter() - start) * 1000))
        raise err

    return wrapper
