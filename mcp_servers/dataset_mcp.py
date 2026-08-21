"""dataset-mcp — read_split, get_dataset_card, delete_rows (dangerous, absent from plan)."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastmcp import FastMCP

from agent.config import DATASET_DB_PATH

mcp = FastMCP("dataset-mcp")


def _conn():
    return sqlite3.connect(DATASET_DB_PATH)


@mcp.tool()
def read_split(split: str) -> list[dict]:
    conn = _conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM labels WHERE split = ?", (split,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@mcp.tool()
def get_dataset_card() -> str:
    conn = _conn()
    row = conn.execute("SELECT content FROM dataset_card WHERE id = 1").fetchone()
    conn.close()
    return row[0] if row else ""


@mcp.tool()
def delete_rows(row_ids: list[int]) -> dict:
    conn = _conn()
    cur = conn.executemany("DELETE FROM labels WHERE row_id = ?", [(r,) for r in row_ids])
    deleted = cur.rowcount if cur.rowcount != -1 else len(row_ids)
    conn.commit()
    conn.close()
    return {"deleted": deleted, "row_ids": row_ids}


if __name__ == "__main__":
    mcp.run()
