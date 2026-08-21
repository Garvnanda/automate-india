"""Demo panel backend. Stdlib only — no framework, matching the project's
constraint on the frontend too.

Serves panel/index.html and three endpoints the page calls:
  GET  /api/state            current DB state (val row count, promotions)
  POST /api/reset            runs data/reset.py, returns new state
  GET  /api/run?mode=...     runs agent.main, streams its stdout as SSE

The panel never fakes anything: every trace pulse, lamp, and gauge move is
driven by a real line agent.main printed, in real time. Guarded runs need
`python -m agent.infra` running in another terminal first — same requirement
as running agent.main --guarded directly.

Usage:  python -m panel.server        (serves http://127.0.0.1:8080)
"""

import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.config import DATASET_DB_PATH, EVAL_SPLIT, REGISTRY_DB_PATH, SESSION_FILE  # noqa: E402
from data.seed import seed  # noqa: E402

PORT = 8080
PY = sys.executable


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
    return {"val_rows": val_rows, "promotions": promotions}


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
            return self._run(parse_qs(parsed.query))

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if urlparse(self.path).path == "/api/reset":
            n = seed()
            return self._json({"seeded": n, **current_state()})
        self.send_response(404)
        self.end_headers()

    def _sse(self, line):
        self.wfile.write(f"data: {line}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _run(self, query):
        mode = (query.get("mode") or ["unguarded"])[0]
        violation = (query.get("violation") or ["0"])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        if mode == "guarded" and not SESSION_FILE.exists():
            self._sse("ERROR: no .session.json — run `python -m agent.infra` first")
            self._sse("__END__")
            return

        seed()  # every run starts from a clean, comparable state

        args = [PY, "-u", "-m", "agent.main", f"--{mode}"]
        if violation in ("1", "2"):
            args += ["--force-violation", violation]
        if mode == "guarded" and violation == "2":
            args += ["--hold-timeout", (query.get("holdTimeout") or ["600"])[0]]

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


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"panel at http://127.0.0.1:{PORT}")
    print("guarded scenarios need `python -m agent.infra` running in another terminal")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
