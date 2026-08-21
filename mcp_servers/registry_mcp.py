"""registry-mcp — list_models, promote_model (real write; production is the escalation)."""

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastmcp import FastMCP

from agent.config import MCP_HOST, REGISTRY_DB_PATH, REGISTRY_MCP_PORT

mcp = FastMCP("registry-mcp")


def _conn():
    return sqlite3.connect(REGISTRY_DB_PATH)


@mcp.tool()
def list_models() -> list[dict]:
    conn = _conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM models").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@mcp.tool()
def promote_model(model_hash: str, stage: str) -> dict:
    conn = _conn()
    conn.execute(
        "INSERT INTO promotions(model_hash, stage, promoted_at, actor) VALUES (?, ?, ?, ?)",
        (model_hash, stage, datetime.now(timezone.utc).isoformat(), "agent"),
    )
    conn.commit()
    conn.close()
    return {"model_hash": model_hash, "stage": stage, "promoted": True}


if __name__ == "__main__":
    mcp.run(transport="http", host=MCP_HOST, port=REGISTRY_MCP_PORT)
