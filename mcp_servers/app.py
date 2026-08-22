"""All three MCP servers on one host, under three paths.

They stay three separate servers — separate modules, separate tool sets,
separate ArmorIQ registry entries and policies. They just share one origin.

That is not a cosmetic choice. An ArmorIQ intent token is bound to a single MCP
*domain* (verified live: `policy_validation.domain` is taken from the plan's
first step, and calls to any other domain fail closed against the default
block). One signed plan spanning dataset + jobs + registry therefore requires
all three to answer on the same host, so one tunnel fronts all of them.

Run:  python -m mcp_servers.app
"""

import contextlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from starlette.applications import Starlette
from starlette.routing import Mount

from agent.config import BUNDLE_PORT, MCP_HOST
from mcp_servers import dataset_mcp, jobs_mcp, registry_mcp

MOUNTS = [
    ("/dataset", dataset_mcp.mcp),
    ("/jobs", jobs_mcp.mcp),
    ("/registry", registry_mcp.mcp),
]

_apps = [(prefix, srv.http_app(path="/mcp", stateless_http=True)) for prefix, srv in MOUNTS]


@contextlib.asynccontextmanager
async def lifespan(app):
    """Each FastMCP app carries its own session-manager lifespan; mounting does
    not run them, so start all three explicitly."""
    async with contextlib.AsyncExitStack() as stack:
        for _, sub in _apps:
            await stack.enter_async_context(sub.lifespan(app))
        yield


class RequireSharedSecret:
    """Origin-side auth. Without this, the FastMCP origin behind the demo's
    cloudflared tunnel accepts requests from anyone who has the public URL —
    verified live: a direct POST with a correctly-shaped MCP call reaches
    delete_rows/promote_model with zero credential, completely bypassing
    ArmorIQ. Enforcement at the proxy means nothing if the origin behind it
    will also talk to whoever asks.

    The secret is registered with ArmorIQ per MCP server as api_key auth
    (agent/infra.py); confirmed live that the proxy then forwards it to the
    origin as a real `x-api-key` header on every legitimate invoke() — so
    this check costs the real demo path nothing and closes the direct-hit
    bypass for real.
    """

    def __init__(self, app, secret):
        self.app = app
        self.secret = secret

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        got = headers.get(b"x-api-key", b"").decode("utf-8", "replace")
        if got != self.secret:
            body = b'{"error":"missing or invalid x-api-key"}'
            await send({"type": "http.response.start", "status": 401,
                        "headers": [(b"content-type", b"application/json")]})
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


_secret = os.environ.get("MCP_SHARED_SECRET")
app = Starlette(
    routes=[Mount(prefix, app=sub) for prefix, sub in _apps],
    lifespan=lifespan,
)
if _secret:
    app = RequireSharedSecret(app, _secret)
else:
    print("WARNING: MCP_SHARED_SECRET not set — origin has no auth of its own; "
          "anyone with the tunnel URL can call every tool directly.", file=sys.stderr)


if __name__ == "__main__":
    uvicorn.run(app, host=MCP_HOST, port=BUNDLE_PORT, log_level="warning")
