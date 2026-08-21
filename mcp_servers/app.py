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


app = Starlette(
    routes=[Mount(prefix, app=sub) for prefix, sub in _apps],
    lifespan=lifespan,
)


if __name__ == "__main__":
    uvicorn.run(app, host=MCP_HOST, port=BUNDLE_PORT, log_level="warning")
