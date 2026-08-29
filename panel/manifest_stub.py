"""GN-side dev stand-in for HA's `tools/manifest.json` + `agent/severity.py`
(docs/implementation-HA.md §3.1/§3.2). Used only by `scripts/fake_stream.py`
and `panel/plan_preview.py` — both dev/preview tooling, never the real
enforcement path. Delete this once HA's real manifest + severity engine ship
and point both callers at his output instead.

Mechanical facts only, same discipline v3.md §2.2 asks of the real manifest:
what a tool reads/writes and who may call it — no verdicts baked in here.
Mirrors `agent/plan.py`'s STEP_LIBRARY/_ORDER (the one thing this module is
not allowed to disagree with, since that's the real plan the agent signs).
"""

from agent.config import CANDIDATE_HASH, EVAL_SPLIT

ACTION_MANIFEST = {
    "get_dataset_card": {"mcp": "dataset-mcp", "reads": ["dataset_card"], "writes": [],
                          "role": {"*": "reader"}, "reversibility": "reversible"},
    "read_split": {"mcp": "dataset-mcp", "reads": ["labels"], "writes": [],
                    "role": {"*": "reader"}, "reversibility": "reversible"},
    "launch_run": {"mcp": "jobs-mcp", "reads": [], "writes": ["metrics"],
                    "role": {"*": "operator"}, "reversibility": "reversible"},
    "read_metrics": {"mcp": "jobs-mcp", "reads": ["metrics"], "writes": [],
                      "role": {"*": "reader"}, "reversibility": "reversible"},
    "promote_model": {"mcp": "registry-mcp", "reads": [], "writes": ["promotions"],
                       "role": {"staging": "operator", "production": "release_manager"},
                       "reversibility": "compensable"},
    "delete_rows": {"mcp": "dataset-mcp", "reads": [], "writes": ["labels"],
                     "role": {"*": "data_owner"}, "reversibility": "irreversible"},
}

# Canonical order a plan is assembled in — same order as agent/plan.py's _ORDER.
ORDER = ("get_dataset_card", "read_split", "launch_run", "read_metrics", "promote_model")

ARGS_BY_ACTION = {
    "get_dataset_card": {},
    "read_split": {"split": EVAL_SPLIT},
    "launch_run": {"model_hash": CANDIDATE_HASH, "split": EVAL_SPLIT},
    "read_metrics": {},
    "promote_model": {"model_hash": CANDIDATE_HASH, "stage": "staging"},
    "delete_rows": {"where": "is_noisy=1"},
}

ROLE_RANK = {"reader": 0, "operator": 1, "release_manager": 2, "data_owner": 2}


def required_role(action, args):
    roles = ACTION_MANIFEST[action]["role"]
    stage = (args or {}).get("stage")
    return roles.get(stage, roles.get("*", "reader"))


def authority_delta(action, args, agent_role):
    need = required_role(action, args)
    return ROLE_RANK.get(need, 0) - ROLE_RANK.get(agent_role, 0)


def edges_for(steps):
    """Resource dependency: step B reads what step A wrote, or both touch the
    same resource — mechanical, straight from v3.md §4.2's own definition,
    not a policy decision."""
    edges = []
    for b in range(1, len(steps)):
        touched_b = set(steps[b]["reads"]) | set(steps[b]["writes"])
        for a in range(b - 1, -1, -1):
            touched_a = set(steps[a]["reads"]) | set(steps[a]["writes"])
            if touched_a & touched_b:
                edges.append({"from": a, "to": b, "resource": sorted(touched_a & touched_b)[0]})
                break
    return edges


def evidence_base_for(steps):
    """All reads by non-terminal steps — HA doc §3.2's stated simplification."""
    base = set()
    for st in steps[:-1]:
        base |= set(st["reads"])
    return sorted(base)
