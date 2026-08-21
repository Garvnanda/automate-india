"""jobs-mcp — mock. launch_run, get_run_status, read_metrics. No real training."""

import json
import sqlite3
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastmcp import FastMCP

from agent.config import REGISTRY_DB_PATH

mcp = FastMCP("jobs-mcp")

_RUNS: dict[str, dict] = {}
_LATEST_RUN_ID: str | None = None


@mcp.tool()
def launch_run(model_hash: str, split: str) -> dict:
    global _LATEST_RUN_ID

    conn = sqlite3.connect(REGISTRY_DB_PATH)
    row = conn.execute("SELECT metrics_json FROM models WHERE model_hash = ?", (model_hash,)).fetchone()
    conn.close()
    metrics = json.loads(row[0]) if row else {"accuracy": 0.5, "f1": 0.5}

    run_id = uuid.uuid4().hex[:12]
    _RUNS[run_id] = {"model_hash": model_hash, "split": split, "metrics": metrics}
    _LATEST_RUN_ID = run_id
    return {"run_id": run_id, "status": "complete"}


@mcp.tool()
def get_run_status(run_id: str) -> dict:
    if run_id not in _RUNS:
        return {"run_id": run_id, "status": "unknown"}
    return {"run_id": run_id, "status": "complete"}


@mcp.tool()
def read_metrics() -> dict:
    """Reads metrics for the most recently launched run — the fixed plan calls
    this with no params, so there is nothing to key a lookup on."""
    if _LATEST_RUN_ID is None:
        return {}
    return _RUNS[_LATEST_RUN_ID]["metrics"]


if __name__ == "__main__":
    mcp.run()
