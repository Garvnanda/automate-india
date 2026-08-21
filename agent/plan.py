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
