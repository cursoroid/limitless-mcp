import hmac
import os

from starlette.responses import JSONResponse


class ApiKeyMiddleware:
    # 401 unless X-API-Key matches. /health stays open for the docker healthcheck.

    def __init__(self, app):
        self.app = app
        self.key = os.environ["LIMITLESS_API_KEY"].encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] != "/health":
            sent = dict(scope["headers"]).get(b"x-api-key", b"")
            if not hmac.compare_digest(sent, self.key):
                return await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
        await self.app(scope, receive, send)
