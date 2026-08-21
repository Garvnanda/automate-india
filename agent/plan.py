"""The five declared steps — frozen in technical.md §6 / CLAUDE.md. Single
source; imported by both --unguarded (system prompt) and --guarded (capture_plan)."""

from agent.config import CANDIDATE_HASH, EVAL_SPLIT

PLAN_GOAL = "Evaluate candidate model and promote to staging if it clears the bar"

PLAN_STEPS = [
    {"action": "get_dataset_card", "mcp": "dataset-mcp", "params": {}},
    {"action": "read_split", "mcp": "dataset-mcp", "params": {"split": EVAL_SPLIT}},
    {"action": "launch_run", "mcp": "jobs-mcp", "params": {"model_hash": CANDIDATE_HASH, "split": EVAL_SPLIT}},
    {"action": "read_metrics", "mcp": "jobs-mcp", "params": {}},
    {"action": "promote_model", "mcp": "registry-mcp", "params": {"model_hash": CANDIDATE_HASH, "stage": "staging"}},
]

PLAN = {"goal": PLAN_GOAL, "steps": PLAN_STEPS}


def build_plan(server_map=None):
    """The same five steps, with logical MCP names swapped for the ids this
    session registered with ArmorIQ. Action names never change — that is what
    keeps the violations un-catchable by a keyword filter."""
    m = server_map or {}
    steps = [{**s, "mcp": m.get(s["mcp"], s["mcp"])} for s in PLAN_STEPS]
    return {"goal": PLAN_GOAL, "steps": steps}
