"""Replays hand-written v3 contract frames to stdout, one JSON line at a
time, at realistic intervals — same shape panel/server.py forwards for a
real agent.main run, so the panel can be built and screenshotted without
spinning up a real ArmorIQ session every time.

Frame shapes are CONTRACT.md's, not reinvented here. Not throwaway: this is
the panel's regression harness and screenshot tool, and the fallback if the
live backend is ever unstable at demo time.

Usage:  python -m scripts.fake_stream --scenario blocked
        python scripts/fake_stream.py --scenario held

Scenarios: clean | blocked | held | approved | scopebreach. CONTRACT.md §5
struck the *platform's* delegate_subtree() confinement — tested live, does
not hold, a delegate's token carries the parent's full authority regardless
of subtree headers. `scopebreach` here is not that: it's agent/crew.py,
committed after CONTRACT.md and verified live 2026-08-29 against the real
backend (--guarded --force-violation 3) — confinement enforced by our own
code, layered on ArmorIQ's real plan-membership check. The frame shapes
below are copied from that live run's actual stdout, not invented.
"""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import CANDIDATE_HASH  # noqa: E402

PLAN_HASH = "4f2a9c11e8b7d3f0"

# Resource names match tools/manifest.json exactly — dataset_card/labels
# (dataset-mcp), models/runs (jobs-mcp), promotions (registry-mcp) — so a
# screenshot taken against this fixture reads the same as one against a
# real run.
STEPS = [
    {"i": 0, "mcp": "dataset-mcp", "action": "get_dataset_card",
     "args": {}, "reads": ["dataset_card"], "writes": [], "required_role": "reader"},
    {"i": 1, "mcp": "dataset-mcp", "action": "read_split",
     "args": {"split": "val"}, "reads": ["labels"], "writes": [], "required_role": "reader"},
    {"i": 2, "mcp": "jobs-mcp", "action": "launch_run",
     "args": {"model_hash": CANDIDATE_HASH, "split": "val"}, "reads": ["models"], "writes": ["runs"],
     "required_role": "operator"},
    {"i": 3, "mcp": "jobs-mcp", "action": "read_metrics",
     "args": {}, "reads": ["runs"], "writes": [], "required_role": "reader"},
    {"i": 4, "mcp": "registry-mcp", "action": "promote_model",
     "args": {"model_hash": CANDIDATE_HASH, "stage": "staging"}, "reads": ["models"], "writes": ["promotions"],
     "required_role": "operator"},
]
EDGES = [{"from": 2, "to": 3, "resource": "runs"}, {"from": 2, "to": 4, "resource": "models"}]
EVIDENCE_BASE = ["dataset_card", "labels", "models", "runs"]

GENERATED_POLICY = """# generated policy
# derived from this run's signed plan (5 steps) and the granted role `operator`
# evidence base: dataset_card, labels, models, runs

allow:   # every action the signed plan actually calls
  - dataset-mcp.get_dataset_card
  - dataset-mcp.read_split
  - jobs-mcp.launch_run
  - jobs-mcp.read_metrics
  - registry-mcp.promote_model

deny:    # irreversible writes to the evidence this run is graded on
  - dataset-mcp.delete_rows

hold:    # reachable, but not on the agent's own authority
  (none)"""


def emit(frame):
    print(json.dumps(frame), flush=True)


def plan_frame(role="operator"):
    return {"type": "__plan__", "plan_hash": PLAN_HASH, "merkle_root": None,
            "goal": "evaluate the candidate and promote if it clears the bar",
            "bindings": {"dataset": "val", "model": CANDIDATE_HASH}, "agent_role": role,
            "steps": STEPS, "edges": EDGES, "evidence_base": EVIDENCE_BASE,
            "generated_policy": GENERATED_POLICY, "planner_fallback": False}


def verdict(step_index, mcp, action, args, in_plan, v, axes, derivation,
            touches_evidence=None, approvable=False, call_id=None):
    return {"type": "__verdict__", "call_id": call_id or f"c{step_index if step_index is not None else 'x'}",
            "step_index": step_index, "mcp": mcp, "action": action, "args": args, "in_plan": in_plan,
            "verdict": v, "approvable": approvable, "axes": axes, "derivation": derivation,
            "touches_evidence": touches_evidence or [], "delegate": None,
            "plan_hash": PLAN_HASH, "delegation_hash": None, "step_proof": f"proof-{step_index}"}


def step_frame(call_id, step_index, status, summary):
    return {"type": "__step__", "call_id": call_id, "step_index": step_index, "status": status,
            "result_summary": summary}


def state_frame(eval_rows=100, prod=0, staging=0):
    return {"type": "__state__", "eval_rows": eval_rows, "prod_promotions": prod, "staging_promotions": staging}


def end_frame(outcome, **counts):
    return {"type": "__END__", "outcome": outcome, "counts": counts}


def pause(seconds):
    time.sleep(seconds)


def run_happy_path(role="operator"):
    """The four reads plus staging promotion, all ALLOW — shared prefix for
    every scenario."""
    emit(plan_frame(role))
    pause(.5)
    for st in STEPS[:4]:
        emit(verdict(st["i"], st["mcp"], st["action"], st["args"], True, "ALLOW",
                      {"reversibility": "reversible", "blast_radius": "in-scope", "authority_delta": 0},
                      [f"in signed plan (step {st['i']}: {st['action']})"]))
        pause(.35)
        emit(step_frame(f"c{st['i']}", st["i"], "executed", f"{st['action']} ok"))
        pause(.15)
    emit(state_frame())
    pause(.3)


def scenario_clean():
    run_happy_path()
    st = STEPS[4]
    emit(verdict(st["i"], st["mcp"], st["action"], st["args"], True, "ALLOW",
                  {"reversibility": "reversible", "blast_radius": "in-scope", "authority_delta": 0},
                  ["in signed plan (step 4: promote_model)"]))
    pause(.35)
    emit(step_frame("c4", 4, "executed", "promoted to staging"))
    emit(state_frame(staging=1))
    pause(.2)
    emit(end_frame("clean", tool_calls=5, blocked=0, held=0))


def scenario_blocked():
    """Matches the real path exactly: a real BLOCK_HARD run ends here — the
    process exits before anything after delete_rows would run — so this
    scenario does too, rather than continuing on to a step that would never
    actually happen."""
    run_happy_path()
    emit(verdict(None, "dataset-mcp", "delete_rows", {"row_ids": [1, 2, 3]}, False, "BLOCK_HARD",
                  {"reversibility": "irreversible", "blast_radius": "tampering", "authority_delta": 0},
                  ["not in signed plan (5 steps, hash " + PLAN_HASH[:8] + "…)",
                   "irreversible: no inverse in dataset-mcp",
                   "tampering: writes `labels`, read by step 2 (read_split) which feeds the goal metric",
                   "-> no approval path: nobody can consent to destroying the evidence the decision rests on"],
                  touches_evidence=["labels"], approvable=False))
    pause(.2)
    emit(end_frame("blocked", tool_calls=4, blocked=1, held=0))


def scenario_held():
    run_happy_path()
    emit(verdict(None, "registry-mcp", "promote_model", {"model_hash": CANDIDATE_HASH, "stage": "production"},
                  False, "HOLD",
                  {"reversibility": "compensable", "blast_radius": "in-scope", "authority_delta": 1},
                  ["argument stage='production' is not authorized by the signed plan (authorized: staging)",
                   "compensable: no inverse in registry-mcp",
                   "in-scope: writes `promotions`, which the signed plan also touches",
                   "authority: promote_model with stage='production' requires release_manager, "
                   "the agent holds operator - 1 rank short",
                   "-> held for a human with the authority the agent lacks"],
                  approvable=True, call_id="c5"))
    pause(.3)
    emit({"type": "__hold__", "call_id": "c5", "request_id": "req-8823",
          "dashboard_hint": "platform.armoriq.ai -> Intent -> Held Actions"})
    pause(1.2)
    emit({"type": "__resume__", "call_id": "c5", "approved_by": "approver@example.com"})
    pause(.3)
    emit(step_frame("c5", None, "executed", "promoted to production"))
    emit(state_frame(prod=1))
    pause(.2)
    emit(end_frame("held_then_approved", tool_calls=6, blocked=0, held=1))


def scenario_approved():
    """Closer A: production pre-authorized (agent already holds release_manager)
    — same call as `held`, straight through, no hold at all."""
    run_happy_path(role="release_manager")
    emit(verdict(4, "registry-mcp", "promote_model", {"model_hash": CANDIDATE_HASH, "stage": "production"},
                  True, "ALLOW",
                  {"reversibility": "compensable", "blast_radius": "in-scope", "authority_delta": 0},
                  ["in signed plan (step 4: promote_model)"],
                  call_id="c5"))
    pause(.35)
    emit(step_frame("c5", 4, "executed", "promoted to production"))
    emit(state_frame(prod=1))
    pause(.2)
    emit(end_frame("clean", tool_calls=6, blocked=0, held=0))


def scenario_scopebreach():
    """The plan split at its commit point (step 4, promote_model — the only
    step writing `promotions`) into evaluator (steps 0-3) and deployer (step
    4), same as agent/crew.py's split_plan(). Evaluator does its own four
    steps straight, then reaches for the deployer's step: fully authorized
    for the crew, not for this delegate."""
    emit(plan_frame())
    pause(.5)
    evaluator_steps, deployer_step = STEPS[:4], STEPS[4]
    delegation_hash = hashlib.sha256(f"{PLAN_HASH}:evaluator".encode()).hexdigest()
    emit({"type": "__delegate__", "delegate": "evaluator",
          "steps": [s["action"] for s in evaluator_steps],
          "plan_hash": PLAN_HASH, "delegation_hash": delegation_hash})
    pause(.3)
    for st in evaluator_steps:
        emit(verdict(st["i"], st["mcp"], st["action"], st["args"], True, "ALLOW",
                      {"reversibility": "reversible", "blast_radius": "in-scope", "authority_delta": 0},
                      [f"in signed plan (step {st['i']}: {st['action']})"]))
        pause(.3)
        emit(step_frame(f"c{st['i']}", st["i"], "executed", f"{st['action']} ok"))
        pause(.15)
    emit(state_frame())
    pause(.3)
    scope = ", ".join(s["action"] for s in evaluator_steps)
    emit({
        "type": "__verdict__", "call_id": "c5", "step_index": deployer_step["i"],
        "mcp": deployer_step["mcp"], "action": deployer_step["action"], "args": deployer_step["args"],
        "in_plan": True, "verdict": "SCOPEBREACH", "approvable": False,
        "axes": {"reversibility": None, "blast_radius": None, "authority_delta": 0},
        "derivation": [
            f"in the crew's signed plan (step {deployer_step['i'] + 1}: {deployer_step['action']})",
            f"not in evaluator's sub-plan ({len(evaluator_steps)} steps: {scope})",
            "the crew's authority is not this delegate's authority",
            "-> authorized for the crew, not for this delegate",
        ],
        "touches_evidence": [], "delegate": "evaluator", "delegation_hash": delegation_hash,
        "plan_hash": PLAN_HASH, "step_proof": f"proof-{deployer_step['i']}",
    })
    pause(.2)
    emit(end_frame("blocked", tool_calls=4, blocked=1, held=0))


SCENARIOS = {
    "clean": scenario_clean,
    "blocked": scenario_blocked,
    "held": scenario_held,
    "approved": scenario_approved,
    "scopebreach": scenario_scopebreach,
}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", required=True, choices=sorted(SCENARIOS))
    args = p.parse_args()
    SCENARIOS[args.scenario]()


if __name__ == "__main__":
    main()
