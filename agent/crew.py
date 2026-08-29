"""Two delegates, carved out of one signed plan.

The violation this exists for: **the evaluator calls `promote_model`.**

  in the crew's signed plan?      yes — correct tool, correct argument
  in the evaluator's sub-plan?    no
  verdict:                        SCOPEBREACH

Flat plan membership says yes. A keyword filter says yes. A role check says yes,
because the crew holds the role. Only the delegation boundary says no.

**What is ours and what is ArmorIQ's — say this out loud, it is the whole
difference between a claim and an overclaim.** ArmorIQ signs the parent plan and
enforces membership of it; that is real, cryptographic and verified. The SDK also
offers `delegate_subtree()`, which mints a child token with a genuine Merkle
inclusion proof — but its confinement is **not enforced on this deployment**:
tested live 2026-08-29, a delegate scoped to `/steps/[0]` successfully invoked
`promote_model`, and one scoped to `/steps/[4]` successfully invoked `read_split`
(see CONTRACT.md §5). So the boundary below is enforced by *this code*, against
sub-plans derived from the parent's own signed steps. The hash chain we print is
ours and is honest about being ours. Never narrate it as the proxy's.

Sequential. Two delegates. No dynamic spawning, no concurrency — docs/v3.md §6.1.
"""

import hashlib
import json

from agent.severity import entry_for, load_manifest

EVALUATOR = "evaluator"
DEPLOYER = "deployer"


def split_plan(plan, manifest=None):
    """Carve the signed plan into sub-plans at the point it commits.

    Derived, not configured: the deployer is the terminal commit — the first step
    that writes to `promotions` and everything after it — and the evaluator is
    everything that produces the evidence for that decision. Change the plan and
    the split moves with it; nothing here names an action.

    Returns [{name, steps, indices}], skipping any delegate that got no steps.
    """
    manifest = manifest or load_manifest()
    steps = plan.get("steps", [])

    commit_at = None
    for i, step in enumerate(steps):
        _, entry = entry_for(step.get("mcp"), step.get("action"), manifest)
        if entry and "promotions" in entry["writes"]:
            commit_at = i
            break
    if commit_at is None:
        commit_at = len(steps)  # nothing commits: it is all evaluation

    crew = [
        {"name": EVALUATOR, "indices": list(range(commit_at))},
        {"name": DEPLOYER, "indices": list(range(commit_at, len(steps)))},
    ]
    for member in crew:
        member["steps"] = [steps[i] for i in member["indices"]]
        member["actions"] = {s["action"] for s in member["steps"]}
    return [m for m in crew if m["steps"]]


def delegation_hash(parent_plan_hash, member):
    """A stable id for this sub-plan, bound to the parent it was carved from.

    Ours, not the platform's: sha256 over the parent plan hash and the delegate's
    own steps. It makes the chain `plan_hash -> delegation_hash -> step_proof`
    verifiable by anyone who has the plan — which is the useful property — without
    claiming the proxy checked it, which it does not.
    """
    payload = json.dumps(
        {"parent": parent_plan_hash, "delegate": member["name"],
         "steps": [{"action": s["action"], "mcp": s["mcp"], "params": s.get("params", {})}
                   for s in member["steps"]]},
        sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def scope_breach(member, action, step_index, parent_steps, parent_plan_hash):
    """The verdict, with the derivation that makes it legible.

    Deliberately not routed through the severity matrix: this call is not
    dangerous, not irreversible and not an escalation — the crew holds every
    authority it needs. It is refused for one reason only, and the derivation
    says exactly that one reason.
    """
    in_crew = next((i for i, s in enumerate(parent_steps) if s["action"] == action), None)
    crew_line = (f"in the crew's signed plan (step {in_crew + 1}: {action})"
                 if in_crew is not None else f"{action} is in the crew's signed plan")
    scope = ", ".join(s["action"] for s in member["steps"])
    return {
        "step_index": step_index,
        "action": action,
        "in_plan": True,
        "verdict": "SCOPEBREACH",
        "approvable": False,
        "axes": {"reversibility": None, "blast_radius": None, "authority_delta": 0},
        "derivation": [
            crew_line,
            f"not in {member['name']}'s sub-plan ({len(member['steps'])} steps: {scope})",
            f"the crew's authority is not this delegate's authority",
            "-> authorized for the crew, not for this delegate",
        ],
        "touches_evidence": [],
        "delegate": member["name"],
        "delegation_hash": delegation_hash(parent_plan_hash, member),
    }


def demo():
    plan = {"steps": [
        {"action": "get_dataset_card", "mcp": "dataset-mcp", "params": {}},
        {"action": "read_split", "mcp": "dataset-mcp", "params": {"split": "val"}},
        {"action": "launch_run", "mcp": "jobs-mcp", "params": {}},
        {"action": "read_metrics", "mcp": "jobs-mcp", "params": {}},
        {"action": "promote_model", "mcp": "registry-mcp",
         "params": {"model_hash": "h", "stage": "staging"}},
    ]}
    crew = split_plan(plan)
    assert [m["name"] for m in crew] == ["evaluator", "deployer"], crew
    assert crew[0]["actions"] == {"get_dataset_card", "read_split", "launch_run", "read_metrics"}
    assert crew[1]["actions"] == {"promote_model"}, crew[1]["actions"]

    # the split is derived: a plan that commits earlier splits earlier, with no
    # edit here and none to the manifest
    early = {"steps": [plan["steps"][0], plan["steps"][4], plan["steps"][1]]}
    crew2 = split_plan(early)
    assert crew2[0]["actions"] == {"get_dataset_card"}, crew2[0]["actions"]
    assert crew2[1]["actions"] == {"promote_model", "read_split"}, crew2[1]["actions"]

    # a plan that never commits is all evaluator, and has no deployer at all
    reads_only = {"steps": plan["steps"][:4]}
    assert [m["name"] for m in split_plan(reads_only)] == ["evaluator"]

    v = scope_breach(crew[0], "promote_model", 4, plan["steps"], "b2683c49aa")
    assert v["verdict"] == "SCOPEBREACH" and v["approvable"] is False
    assert v["delegate"] == "evaluator"
    assert "step 5: promote_model" in v["derivation"][0], v["derivation"]
    assert "not in evaluator's sub-plan" in v["derivation"][1], v["derivation"]

    # the hash is bound to the parent: same sub-plan, different parent, different id
    a = delegation_hash("parent-a", crew[0])
    b = delegation_hash("parent-b", crew[0])
    assert a != b and len(a) == 64, (a, b)
    assert delegation_hash("parent-a", crew[0]) == a, "must be stable"

    for line in v["derivation"]:
        print(" ", line)
    print("crew: ALL CHECKS PASSED")


if __name__ == "__main__":
    demo()
