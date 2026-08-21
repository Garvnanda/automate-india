"""Batch 1 acceptance check — run directly: python tests/test_mcp_servers.py

Exercises all 8 MCP tool functions, proves delete_rows really deletes and
reset.py really restores. Plain asserts, no framework.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.reset import seed
from agent.config import CANDIDATE_HASH, EVAL_SPLIT
from mcp_servers.dataset_mcp import read_split, get_dataset_card, delete_rows
from mcp_servers.jobs_mcp import launch_run, get_run_status, read_metrics
from mcp_servers.registry_mcp import list_models, promote_model


def main():
    n_seeded = seed()
    print(f"seeded {n_seeded} rows")

    val_rows = read_split(EVAL_SPLIT)
    assert len(val_rows) > 0, "read_split returned nothing"

    card = get_dataset_card()
    assert "is_noisy" in card, "dataset card missing injection text"

    run = launch_run(CANDIDATE_HASH, EVAL_SPLIT)
    assert run["status"] == "complete"
    status = get_run_status(run["run_id"])
    assert status["status"] == "complete"
    metrics = read_metrics()
    assert "accuracy" in metrics, f"no accuracy in metrics: {metrics}"
    print(f"run {run['run_id']} metrics: {metrics}")

    models = list_models()
    assert any(m["model_hash"] == CANDIDATE_HASH for m in models)

    promo = promote_model(CANDIDATE_HASH, "staging")
    assert promo["promoted"] is True

    before = len(read_split(EVAL_SPLIT))
    noisy_ids = [r["row_id"] for r in val_rows if r["is_noisy"] == 1][:5]
    assert noisy_ids, "no noisy rows in val split to delete"
    result = delete_rows(noisy_ids)
    assert result["deleted"] == len(noisy_ids), f"expected {len(noisy_ids)} deleted, got {result}"
    after = len(read_split(EVAL_SPLIT))
    assert after == before - len(noisy_ids), f"row count did not drop as expected: {before} -> {after}"
    print(f"delete_rows: {before} -> {after} rows (deleted {len(noisy_ids)})")

    restored = seed()
    assert restored == n_seeded, "reset did not restore original row count"
    print(f"reset restored {restored} rows")

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
