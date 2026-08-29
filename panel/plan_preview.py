"""GN Phase 2 — live plan preview for the ARM/REVIEW surface.

Was a dev stand-in (panel/manifest_stub.py) until HA's severity engine and
planner landed for real; now a thin wrapper over his actual functions —
`agent.severity`, `agent.policy_gen`, `agent.planner`, `agent.plan` — so the
preview can never disagree with what a real run signs. Nothing here
recomputes a dependency or a verdict; it calls the real ones and packages
the result.

Still not the real ArmorIQ signature — there is no network call here, no
capture_plan(), no token. Every frame carries `"dev_preview": true` and the
policy text says so too, so it can't get mistaken for the real signing beat
even if it reaches the same rendering code.
"""

import hashlib
import json

from agent.config import CANDIDATE_HASH, EVAL_SPLIT
from agent.plan import PLAN_GOAL, build_plan
from agent.planner import PlanInvalid, generate as generate_plan, normalize, validate
from agent.policy_gen import generate as generate_policy
from agent.runconfig import RunConfig
from agent.severity import annotate_steps, authority_delta, evidence_base, load_manifest, plan_edges


def _resolve_plan(authorized, promote_production, agent_role, goal, plan):
    """One plan dict, however the caller specified it — switches, a typed
    goal, or a panel-edited draft round-tripping back. Returns
    (plan, planner_fallback)."""
    if plan is not None:
        return validate(normalize(plan)), False
    if goal:
        return generate_plan(goal)
    cfg = RunConfig(authorized=authorized or [], promote_production=bool(promote_production),
                     agent_role=agent_role or "operator")
    return build_plan(None, cfg), False


def build_plan_frame(authorized=None, promote_production=False, agent_role="operator",
                      goal=None, plan=None):
    agent_role = agent_role or "operator"
    resolved, fallback = _resolve_plan(authorized, promote_production, agent_role, goal, plan)
    manifest = load_manifest()
    ann = annotate_steps(resolved, manifest)
    steps = []
    for st, a in zip(resolved["steps"], ann):
        steps.append({**a, "args": a["params"],
                      "authority_delta": authority_delta(a["mcp"], a["action"], a["params"],
                                                          manifest, agent_role)})

    digest = hashlib.sha256(json.dumps(resolved["steps"], sort_keys=True).encode()).hexdigest()[:16]
    policy = generate_policy(resolved, agent_role, manifest)

    return {
        "type": "__plan__", "dev_preview": True,
        "plan_hash": digest, "merkle_root": None,
        "goal": resolved.get("goal") or goal or PLAN_GOAL,
        "bindings": {"dataset": EVAL_SPLIT, "model": CANDIDATE_HASH},
        "agent_role": agent_role,
        "steps": steps, "edges": plan_edges(resolved, manifest),
        "evidence_base": sorted(evidence_base(resolved, manifest)),
        "generated_policy": policy["text"] +
            f"\n# preview hash {digest} — recomputed live, not ArmorIQ's signature",
        "planner_fallback": bool(fallback),
    }
