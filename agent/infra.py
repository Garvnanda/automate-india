"""Guarded-mode session bring-up.

The ArmorIQ proxy cannot reach 127.0.0.1 (it returns ECONNREFUSED against its
own loopback), so the MCP servers have to be publicly reachable before a
guarded run can work. This command:

  1. makes sure a cloudflared binary exists (downloading one if needed)
  2. starts all three MCP servers on one origin (mcp_servers/app.py)
  3. opens one public tunnel to it
  4. registers all three with ArmorIQ under session-unique ids
  5. writes .session.json and stays running until Ctrl-C

Two findings from live testing shape this, both non-obvious:

* One origin, not three. An intent token is bound to a single MCP *domain* —
  taken from the plan's first step — and calls to any other domain fail closed.
  Three tunnels meant the one signed plan could only ever reach one server.
  Same origin, three paths: all three policies match and one plan covers the run.

* Session-unique ids. POST /iap/sdk/register returns 500 when an existing MCP id
  is re-registered with a different URL, and cloudflared quick tunnels mint a new
  random URL on every start. Fresh ids return 200 every time.

Usage:  python -m agent.infra     (leave it running, then run agent.main --guarded)
"""

import atexit
import json
import os
import platform
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from datetime import datetime, timezone

from agent.config import (
    AGENT_EMAIL,
    AGENT_ID,
    ARMORIQ_API_KEY,
    BUNDLE_PORT,
    MCP_PATHS,
    SESSION_FILE,
    TOOLS_DIR,
)
from agent.severity import load_manifest

REGISTER_URL = "https://api.armoriq.ai/iap/sdk/register"
PROXY_URL = "https://proxy.armoriq.ai"
TUNNEL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

CLOUDFLARED_RELEASES = "https://github.com/cloudflare/cloudflared/releases/latest/download"

# Every action the agent may ever be authorized for must be listed: enforcement
# is fail-closed, so an unlisted action dies silently.
#
# delete_rows is in the allow list from v2 on, and that is a deliberate change.
# v1 also denied it here, belt-and-braces on top of the plan check. Verified
# live that the deny genuinely fires — an in-plan delete_rows came back
# "Tool 'delete_rows' denied by OPA: policy_constraints_not_satisfied" — which
# is exactly why it had to move: it would veto the judge's own authorization.
#
# So membership of the *signed plan* is now the only gate on delete_rows, which
# is the whole thesis stated honestly. Absent from the plan -> the SDK refuses
# it client-side before any request leaves the process. Present in the plan,
# because a judge ticked it -> it runs, and the rows really go. Being able to
# authorize the dangerous action and watch it succeed is the proof that
# enforcement is real; a hardcoded demo can only ever block.
# v3: the hand-written allow/deny lists that used to sit here are gone. What is
# registered now is only *which tools these servers expose*, read straight off
# tools/manifest.json — a fact about the servers, not a decision about what is
# permitted. The decision is made per run, from the signed plan, by
# agent/policy_gen.py, and handed to ArmorIQ at token-mint time.
def exposed_tools():
    """{logical mcp: [action, ...]} for every tool the manifest describes."""
    out = {}
    for key in load_manifest()["tools"]:
        logical, _, action = key.partition(".")
        out.setdefault(logical, []).append(action)
    return out

_children = []


def _spawn(cmd, **kw):
    p = subprocess.Popen(cmd, **kw)
    _children.append(p)
    return p


def shutdown():
    for p in _children:
        if p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass
    for p in _children:
        try:
            p.wait(timeout=5)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass


def cloudflared_asset():
    system, machine = platform.system().lower(), platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "amd64"
    if system == "windows":
        return f"cloudflared-windows-{arch}.exe", "cloudflared.exe"
    if system == "darwin":
        return f"cloudflared-darwin-{arch}.tgz", "cloudflared"
    return f"cloudflared-linux-{arch}", "cloudflared"


def ensure_cloudflared():
    """PATH first, then .tools/, else download it once."""
    found = shutil.which("cloudflared")
    if found:
        return found

    asset, local_name = cloudflared_asset()
    local = TOOLS_DIR / local_name
    if local.exists():
        return str(local)

    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    url = f"{CLOUDFLARED_RELEASES}/{asset}"
    print(f"cloudflared not found — downloading once from {url}")
    print("  (~55MB, saved to .tools/, gitignored, never downloaded again)")

    if asset.endswith(".tgz"):
        import tarfile
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".tgz", delete=False) as tmp:
            urllib.request.urlretrieve(url, tmp.name)
            tgz = tmp.name
        with tarfile.open(tgz) as tf:
            member = next(m for m in tf.getmembers() if m.name.endswith("cloudflared"))
            member.name = local_name
            tf.extract(member, TOOLS_DIR)
    else:
        urllib.request.urlretrieve(url, local)

    if platform.system().lower() != "windows":
        local.chmod(0o755)
    print(f"cloudflared ready at {local}")
    return str(local)


def start_servers(shared_secret):
    """One process, all three MCP servers, one origin — see mcp_servers/app.py.

    MCP_SHARED_SECRET makes the origin itself check every request, not just
    the proxy in front of it — see RequireSharedSecret in mcp_servers/app.py
    for why that gap is real, not theoretical, once the tunnel is public.
    """
    env = os.environ.copy()
    env["MCP_SHARED_SECRET"] = shared_secret
    _spawn(
        [sys.executable, "-m", "mcp_servers.app"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    for name, path in MCP_PATHS.items():
        print(f"  {name} at 127.0.0.1:{BUNDLE_PORT}{path}")


def start_tunnel(cf, port, out, timeout=60):
    """Open one quick tunnel and capture the public URL it prints."""
    p = _spawn(
        [cf, "tunnel", "--url", f"http://127.0.0.1:{port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = p.stdout.readline()
        if not line:
            if p.poll() is not None:
                break
            continue
        m = TUNNEL_RE.search(line)
        if m:
            out[port] = m.group(0)
            # keep draining so the pipe never fills and blocks the tunnel
            threading.Thread(target=lambda: [None for _ in p.stdout], daemon=True).start()
            return
    out[port] = None


def register(servers, shared_secret):
    """Registers each server with api_key auth, not "none". Verified live
    (see the session's MCP-origin-auth probe) that ArmorIQ's proxy forwards
    this credential to the origin as a real X-API-Key header on every
    invoke() — so this is the same demo path, just no longer also reachable
    by anyone who has the tunnel URL and skips the proxy.
    """
    payload = {
        "version": "v1",
        "identity": {"api_key": ARMORIQ_API_KEY, "user_id": AGENT_EMAIL, "agent_id": AGENT_ID},
        "environment": "production",
        "proxy": {"url": PROXY_URL, "timeout": 30, "max_retries": 3},
        "mcp_servers": [
            {"id": s["id"], "url": s["url"],
             "auth": {"type": "api_key", "api_key": shared_secret}}
            for s in servers.values()
        ],
        "policy": {
            "allow": [
                f"{servers[logical]['id']}.{tool}"
                for logical, tools in exposed_tools().items()
                if logical in servers
                for tool in tools
            ],
            "deny": [],
        },
        "intent": {"ttl_seconds": 300, "require_csrg": True},
    }
    req = urllib.request.Request(
        REGISTER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {ARMORIQ_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def bring_up(log=print):
    """Everything up to READY: servers, tunnel, registration, .session.json.

    Returns the servers dict. Raises RuntimeError with a plain message on
    failure. Split out of main() so the demo panel can call it in a thread and
    offer a one-command launch — the CLI path below is unchanged.
    """
    if not ARMORIQ_API_KEY:
        raise RuntimeError("ARMORIQ_API_KEY is not set — copy .env.example to .env and fill it in.")

    cf = ensure_cloudflared()

    shared_secret = secrets.token_urlsafe(32)

    log("starting MCP servers...")
    start_servers(shared_secret)
    time.sleep(3)

    log("opening tunnel (this takes ~10s)...")
    urls = {}
    start_tunnel(cf, BUNDLE_PORT, urls)
    base = urls.get(BUNDLE_PORT)
    if not base:
        raise RuntimeError("tunnel failed — check your network and retry")
    log(f"  origin -> {base}")

    tag = uuid.uuid4().hex[:6]
    servers = {
        name: {"id": f"{name}-{tag}", "url": base + path, "port": BUNDLE_PORT}
        for name, path in MCP_PATHS.items()
    }

    log("registering with ArmorIQ...")
    result = register(servers, shared_secret)
    if not result.get("success"):
        raise RuntimeError(f"registration failed: {result}")

    # NOT set here: agent.infra and agent.main are always separate processes
    # (a second terminal, or a subprocess the panel spawns), so an env var set
    # in this process would never reach the one that actually calls invoke().
    # The secret travels via .session.json instead; agent/main.py applies it
    # to its own process's env at the same point it already reads that file.

    SESSION_FILE.write_text(
        json.dumps(
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "servers": servers,
                "mcp_shared_secret": shared_secret,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return servers


def main():
    atexit.register(shutdown)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *_: sys.exit(0))
        except (ValueError, OSError):
            pass

    try:
        servers = bring_up()
    except RuntimeError as e:
        raise SystemExit(str(e))

    print()
    print("READY — registered as:")
    for name, s in servers.items():
        print(f"  {s['id']}")
    print(f"\nsession written to {SESSION_FILE.name}")
    print("run guarded scenarios in another terminal, e.g.:")
    print("  python -m agent.main --guarded")
    print("\nCtrl-C to tear everything down.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        print("\nshutting down...")
        SESSION_FILE.unlink(missing_ok=True)
        shutdown()


if __name__ == "__main__":
    main()
