"""GN Phase 2 — live plan preview for the ARM/REVIEW surface.

Not the real ArmorIQ signing path. Every frame this returns carries
`"dev_preview": true` so the client can (and must) label it honestly —
v1's rule survives into v3: nothing on the panel pretends to be more real
than it is. This exists so the editable-plan surface has something to show
live, before HA's real planner/severity engine lands (docs/implementation-
GN.md Phase 2: "Independent of HA's planner — build against a static draft
plan JSON").
"""

import hashlib
import json

from panel.manifest_stub import ACTION_MANIFEST, ARGS_BY_ACTION, ORDER, authority_delta, edges_for, evidence_base_for, required_role

GENERATED_POLICY = """package promotionguard

allow[i] { input.step == i; input.action == data.plan.steps[i].action }
hold { input.axes.authority_delta > 0 }
block_hard { input.axes.reversibility == "irreversible"; input.axes.blast_radius == "tampering" }"""


def _step(action, args):
    m = ACTION_MANIFEST[action]
    return {"mcp": m["mcp"], "action": action, "args": args,
            "reads": m["reads"], "writes": m["writes"], "required_role": required_role(action, args)}


def build_plan_frame(authorized, promote_production, agent_role):
    """`authorized`: list of action names (Bank A). `promote_production`:
    whether a stage=production promote_model step is also in the draft.
    `agent_role`: reader | operator | release_manager. Mirrors
    agent/plan.py's build_plan() assembly rules exactly, so the preview
    never disagrees with what a real run would actually sign."""
    authorized = set(authorized or [])
    steps = []
    for name in ORDER:
        if name not in authorized:
            continue
        steps.append(_step(name, dict(ARGS_BY_ACTION[name])))
        if name == "promote_model" and promote_production:
            steps.append(_step(name, {**ARGS_BY_ACTION[name], "stage": "production"}))
    if promote_production and "promote_model" not in authorized:
        steps.append(_step("promote_model", {**ARGS_BY_ACTION["promote_model"], "stage": "production"}))
    if "delete_rows" in authorized:
        steps.append(_step("delete_rows", dict(ARGS_BY_ACTION["delete_rows"])))

    digest = hashlib.sha256(json.dumps(steps, sort_keys=True).encode()).hexdigest()[:16]
    for i, st in enumerate(steps):
        st["i"] = i
        st["authority_delta"] = authority_delta(st["action"], st["args"], agent_role)

    return {
        "type": "__plan__", "dev_preview": True,
        "plan_hash": digest, "merkle_root": None,
        "goal": "evaluate the candidate and promote if it clears the bar",
        "bindings": {"dataset": "eval_v3", "model": ARGS_BY_ACTION["launch_run"]["model_hash"]},
        "agent_role": agent_role,
        "steps": steps, "edges": edges_for(steps), "evidence_base": evidence_base_for(steps),
        "generated_policy": GENERATED_POLICY + f"\n# preview hash {digest} — recomputed live, not ArmorIQ's signature",
    }
