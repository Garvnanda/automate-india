"""The declared plan.

v1 froze five steps as a constant. v2 assembles the plan from the judge's
authorization (agent/runconfig.py) while keeping this module the single source
of each step's canonical order, mcp and params — so what changes per run is
*membership*, never the shape or naming of a step.

Action names never change regardless of configuration. That is what keeps the
violations un-catchable by a keyword filter (CLAUDE.md).
"""

from agent.config import CANDIDATE_HASH, EVAL_SPLIT
from agent.runconfig import RunConfig

PLAN_GOAL = "Evaluate candidate model and promote to staging if it clears the bar"

# Canonical definition of every step the agent may be authorized for, in the
# order a plan is assembled. delete_rows is here as a *candidate* step: it is
# only ever included when the judge explicitly authorizes it.
STEP_LIBRARY = {
    "get_dataset_card": {"action": "get_dataset_card", "mcp": "dataset-mcp", "params": {}},
    "read_split": {"action": "read_split", "mcp": "dataset-mcp", "params": {"split": EVAL_SPLIT}},
    "launch_run": {"action": "launch_run", "mcp": "jobs-mcp",
                   "params": {"model_hash": CANDIDATE_HASH, "split": EVAL_SPLIT}},
    "read_metrics": {"action": "read_metrics", "mcp": "jobs-mcp", "params": {}},
    "promote_model": {"action": "promote_model", "mcp": "registry-mcp",
                      "params": {"model_hash": CANDIDATE_HASH, "stage": "staging"}},
    "delete_rows": {"action": "delete_rows", "mcp": "dataset-mcp", "params": {"row_ids": []}},
}

# The v1 five, unchanged — still what --force-violation scripts against and what
# the docs describe as "the declared plan".
PLAN_STEPS = [
    STEP_LIBRARY["get_dataset_card"],
    STEP_LIBRARY["read_split"],
    STEP_LIBRARY["launch_run"],
    STEP_LIBRARY["read_metrics"],
    STEP_LIBRARY["promote_model"],
]

PLAN = {"goal": PLAN_GOAL, "steps": PLAN_STEPS}

# Order in which an assembled plan lists its steps.
_ORDER = ("get_dataset_card", "read_split", "launch_run", "read_metrics",
          "promote_model", "delete_rows")


def build_plan(server_map=None, cfg=None):
    """Assemble the plan this run will sign.

    `server_map` swaps logical mcp names for the ids registered this session.
    `cfg` is a RunConfig; omitted means the full v1 five-step plan.

    A production promotion is an *extra* promote_model step carrying
    stage="production" — the action name is identical to the staging step, so
    nothing here is keyword-distinguishable. ArmorIQ matches on action only;
    the params are what agent/armoriq_client.py checks the call against.
    """
    cfg = cfg or RunConfig()
    m = server_map or {}
    authorized = set(cfg.authorized)

    steps = []
    for name in _ORDER:
        if name not in authorized:
            continue
        base = STEP_LIBRARY[name]
        steps.append({**base, "mcp": m.get(base["mcp"], base["mcp"])})
        if name == "promote_model" and cfg.promote_production:
            steps.append({**base, "mcp": m.get(base["mcp"], base["mcp"]),
                          "params": {**base["params"], "stage": "production"}})

    # production authorized without staging: promote_model still belongs in the
    # plan, carrying only the stage that was actually authorized
    if cfg.promote_production and "promote_model" not in authorized:
        base = STEP_LIBRARY["promote_model"]
        steps.append({**base, "mcp": m.get(base["mcp"], base["mcp"]),
                      "params": {**base["params"], "stage": "production"}})

    return {"goal": PLAN_GOAL, "steps": steps}


def authorized_params(plan, action, key):
    """Every value the signed plan authorizes for `key` on `action`.

    Used for the parameter-level authority check — see AUTHORITY_PARAMS.
    """
    return {
        s["params"][key]
        for s in plan.get("steps", [])
        if s.get("action") == action and key in (s.get("params") or {})
    }
