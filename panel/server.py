"""Demo panel backend. Stdlib only — no framework, matching the project's
constraint on the frontend too.

Serves panel/index.html and four endpoints the page calls:
  GET  /api/state            current DB state (val row count, promotions)
  POST /api/reset            runs data/reset.py, returns new state
  GET  /api/run?mode=...     runs agent.main, streams its stdout as SSE
  GET  /api/ask?question=... streams the agent's answer token by token, SSE (agent/ask.py)

The panel never fakes anything: every trace pulse, lamp, and gauge move is
driven by a real line agent.main printed, in real time. Guarded runs need
`python -m agent.infra` running in another terminal first — same requirement
as running agent.main --guarded directly.

Usage:  python -m panel.server        (serves http://127.0.0.1:8080)
"""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import ask as ask_mod  # noqa: E402
from agent import infra  # noqa: E402
from agent.config import DATASET_DB_PATH, EVAL_SPLIT, REGISTRY_DB_PATH, SESSION_FILE  # noqa: E402
from agent.runconfig import RunConfig  # noqa: E402
from data.seed import seed  # noqa: E402
from panel import plan_preview  # noqa: E402


def cfg_from_query(query):
    """The judge's switch positions, as sent by the panel.

    Bank A rides through to agent.main as --config; Bank B is applied at seed
    time, because jobs-mcp reads whatever metrics were seeded. Invalid values
    raise and are reported rather than silently defaulted — a condition dial
    that quietly does nothing is worse than one that errors.
    """
    raw = (query.get("cfg") or [None])[0]
    return RunConfig.from_json(raw)


def seed_for(cfg):
    return seed(card=cfg.card, model_result=cfg.model_result, hash_match=cfg.hash_match,
                card_text=cfg.card_text)

PORT = int(os.environ.get("PORT", 8080))
PY = sys.executable


def same_origin(handler):
    """/api/run is a plain GET so EventSource can use it, and GET requests
    from other tabs execute server-side regardless of whether the attacker
    page can read the response — the classic localhost-CSRF shape. A page on
    any other origin open in the same browser could embed
    <img src="http://127.0.0.1:8080/api/run?mode=guarded&..."> and silently
    trigger a real destructive run. Browsers still send Origin/Referer on
    cross-origin requests (just not the full path), so reject anything that
    doesn't claim to come from this page. Same-origin XHR/fetch/EventSource
    calls always carry one of these; curl/direct requests carry neither and
    are allowed, matching how the CLI (agent.main) itself has no such gate.
    """
    origin = handler.headers.get("Origin") or handler.headers.get("Referer") or ""
    if not origin:
        return True
    host = handler.headers.get("Host", "")
    return host != "" and origin.split("://", 1)[-1].split("/", 1)[0] == host

# Guarded runs need the MCP servers tunneled and registered. The panel brings
# that up itself in a background thread so the whole demo is one command; the
# page polls this and only unlocks guarded mode once it says "ready".
INFRA = {"state": "off", "message": "enforcement session not started"}


def session_alive():
    """True only if .session.json points at a tunnel that still answers.

    agent.infra deletes the file on a clean exit, but a crash or a killed
    terminal leaves it behind pointing at a dead cloudflared URL — and a stale
    file would otherwise make the panel report "ready" and then fail every
    guarded run.

    A dead quick tunnel still resolves: Cloudflare's edge answers for the
    hostname and returns 5xx (530 "origin unreachable") because there is no
    tunnel behind it. So a 5xx means dead, while a live FastMCP origin answers
    HEAD with a 2xx/4xx of its own.
    """
    try:
        servers = json.loads(SESSION_FILE.read_text(encoding="utf-8"))["servers"]
        url = next(iter(servers.values()))["url"]
    except Exception:  # noqa: BLE001 — unreadable file is a dead file
        return False
    import urllib.error
    import urllib.request

    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=6)
        return True
    except urllib.error.HTTPError as e:
        return e.code < 500  # it answered for itself, not an edge error page
    except Exception:  # noqa: BLE001 — connection refused / DNS gone / timeout
        return False


def start_infra():
    if SESSION_FILE.exists():
        if session_alive():
            # somebody already ran `python -m agent.infra` — use theirs, don't
            # register a second session on top of it
            INFRA.update(state="ready", message="using the session already running", owned=False)
            return
        SESSION_FILE.unlink(missing_ok=True)

    INFRA.update(state="starting", message="starting MCP servers...", owned=True)

    def run():
        try:
            infra.bring_up(log=lambda m: INFRA.update(message=m.strip()))
            INFRA.update(state="ready", message="tunneled and registered with ArmorIQ")
        except Exception as e:  # noqa: BLE001 — surfaced to the page verbatim
            INFRA.update(state="error", message=str(e))

    threading.Thread(target=run, daemon=True).start()


def current_state():
    import sqlite3

    with sqlite3.connect(DATASET_DB_PATH) as c:
        val_rows = c.execute(
            "SELECT COUNT(*) FROM labels WHERE split = ?", (EVAL_SPLIT,)
        ).fetchone()[0]
    with sqlite3.connect(REGISTRY_DB_PATH) as c:
        promotions = [
            {"model_hash": h, "stage": s, "promoted_at": t}
            for h, s, t in c.execute(
                "SELECT model_hash, stage, promoted_at FROM promotions ORDER BY id"
            )
        ]
    return {"val_rows": val_rows, "promotions": promotions, "infra": dict(INFRA)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet; the panel itself shows activity

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/" or parsed.path == "/index.html":
            html = (Path(__file__).parent / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return

        if parsed.path == "/api/state":
            return self._json(current_state())

        if parsed.path == "/api/run":
            if not same_origin(self):
                return self._json({"error": "cross-origin request refused"}, status=403)
            return self._run(parse_qs(parsed.query))

        if parsed.path == "/api/ask":
            if not same_origin(self):
                return self._json({"error": "cross-origin request refused"}, status=403)
            return self._ask(parse_qs(parsed.query))

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/reset":
            if not same_origin(self):
                return self._json({"error": "cross-origin request refused"}, status=403)
            try:
                cfg = cfg_from_query(parse_qs(parsed.query))
            except (ValueError, TypeError) as e:
                return self._json({"error": str(e)}, status=400)
            n = seed_for(cfg)
            return self._json({"seeded": n, **current_state()})

        if parsed.path == "/api/plan/preview":
            if not same_origin(self):
                return self._json({"error": "cross-origin request refused"}, status=403)
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
                frame = plan_preview.build_plan_frame(
                    body.get("authorized") or [], bool(body.get("promote_production")),
                    body.get("agent_role") or "operator")
            except (ValueError, TypeError, KeyError) as e:
                return self._json({"error": f"bad draft plan — {e}"}, status=400)
            return self._json(frame)

        self.send_response(404)
        self.end_headers()

    def _sse(self, line):
        self.wfile.write(f"data: {line}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _run(self, query):
        mode = (query.get("mode") or ["unguarded"])[0]
        violation = (query.get("violation") or ["0"])[0]
        fake = (query.get("fake") or [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        if fake:
            # v3 contract dev/screenshot path — scripts/fake_stream.py replays
            # hand-written frames over this same SSE endpoint. No DB, no infra,
            # no real agent involved.
            return self._stream_subprocess([PY, "-u", "scripts/fake_stream.py", "--scenario", fake])

        if mode == "guarded" and not SESSION_FILE.exists():
            self._sse(f"ERROR: enforcement session not ready — {INFRA['message']}")
            self._sse("__END__")
            return

        try:
            cfg = cfg_from_query(query)
        except (ValueError, TypeError) as e:
            self._sse(f"ERROR: bad configuration — {e}")
            self._sse("__END__")
            return

        if not cfg.plans_anything:
            self._sse("ERROR: nothing authorized — the plan would be empty")
            self._sse("__END__")
            return

        # every run starts from a clean, comparable state, under this run's
        # Bank B conditions
        seed_for(cfg)

        args = [PY, "-u", "-m", "agent.main", f"--{mode}", "--config", cfg.to_json()]
        if violation in ("1", "2"):
            args += ["--force-violation", violation]
        if mode == "guarded" and violation == "2":
            args += ["--hold-timeout", (query.get("holdTimeout") or ["600"])[0]]

        self._stream_subprocess(args)

    def _stream_subprocess(self, args):
        proc = subprocess.Popen(
            args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        try:
            for line in proc.stdout:
                line = line.rstrip("\n")
                if line.strip():
                    self._sse(line)
            proc.wait()
        except (BrokenPipeError, ConnectionResetError):
            proc.terminate()
            return

        self._sse(json.dumps({"__final_state__": current_state(), "exit_code": proc.returncode}))
        self._sse("__END__")

    def _ask(self, query):
        run_id = (query.get("run_id") or [None])[0]
        question = (query.get("question") or [""])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        try:
            for delta in ask_mod.ask_stream(run_id, question):
                self._sse(json.dumps({"delta": delta}))
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            self._sse(json.dumps({"error": str(e)}))
        except (BrokenPipeError, ConnectionResetError):
            return
        self._sse("__END__")


def main():
    if not DATASET_DB_PATH.exists():
        seed()

    if "--no-infra" not in sys.argv:
        start_infra()

    server = ThreadingHTTPServer((os.environ.get("HOST", "0.0.0.0"), PORT), Handler)
    print(f"panel at http://127.0.0.1:{PORT}")
    print("bringing up the enforcement session in the background — the page shows progress")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if INFRA.get("owned"):
            print("\nshutting down the enforcement session...")
            SESSION_FILE.unlink(missing_ok=True)
            infra.shutdown()


if __name__ == "__main__":
    main()
