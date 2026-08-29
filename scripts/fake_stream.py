"""Replays hand-written v3 contract frames to stdout, one JSON line at a
time, at realistic intervals — same shape panel/server.py forwards for a
real agent.main run, so the panel can be built and screenshotted against a
scenario the real severity engine doesn't exist yet to produce.

Frame shapes are CONTRACT.md's (docs/implementation-HA.md §1), not
reinvented here. Not throwaway: this is the panel's regression harness and
screenshot tool until HA's backend lands, and the fallback if it's ever
unstable at demo time.

Usage:  python -m scripts.fake_stream --scenario blocked
        python scripts/fake_stream.py --scenario held
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.config import CANDIDATE_HASH  # noqa: E402

PLAN_HASH = "4f2a9c11e8b7d3f0"
MERKLE_ROOT = "9c11e8b7d3f04f2a"

STEPS = [
    {"i": 0, "mcp": "dataset-mcp", "action": "get_dataset_card",
     "args": {}, "reads": ["dataset_card"], "writes": [], "required_role": "reader"},
    {"i": 1, "mcp": "dataset-mcp", "action": "read_split",
     "args": {"split": "val"}, "reads": ["labels"], "writes": [], "required_role": "reader"},
    {"i": 2, "mcp": "jobs-mcp", "action": "launch_run",
     "args": {"model_hash": CANDIDATE_HASH, "split": "val"}, "reads": ["metrics"], "writes": ["metrics"],
     "required_role": "operator"},
    {"i": 3, "mcp": "jobs-mcp", "action": "read_metrics",
     "args": {}, "reads": ["metrics"], "writes": [], "required_role": "reader"},
    {"i": 4, "mcp": "registry-mcp", "action": "promote_model",
     "args": {"model_hash": CANDIDATE_HASH, "stage": "staging"}, "reads": [], "writes": ["promotions"],
     "required_role": "operator"},
]
EDGES = [{"from": 0, "to": 1, "resource": "dataset_card"}, {"from": 1, "to": 2, "resource": "labels"},
          {"from": 2, "to": 3, "resource": "metrics"}, {"from": 3, "to": 4, "resource": "metrics"}]
EVIDENCE_BASE = ["labels", "dataset_card", "metrics"]

GENERATED_POLICY = """package promotionguard

allow[i] { input.step == i; input.action == data.plan.steps[i].action }
hold { input.axes.authority_delta > 0 }
block_hard { input.axes.reversibility == "irreversible"; input.axes.blast_radius == "tampering" }"""


def emit(frame):
    print(json.dumps(frame), flush=True)


def plan_frame(role="operator"):
    return {"type": "__plan__", "plan_hash": PLAN_HASH, "merkle_root": MERKLE_ROOT,
            "goal": "evaluate the candidate and promote if it clears the bar",
            "bindings": {"dataset": "eval_v3", "model": CANDIDATE_HASH}, "agent_role": role,
            "steps": STEPS, "edges": EDGES, "evidence_base": EVIDENCE_BASE,
            "generated_policy": GENERATED_POLICY}


def verdict(step_index, mcp, action, args, in_plan, v, axes, derivation,
            touches_evidence=None, delegate=None, approvable=False, call_id=None):
    return {"type": "__verdict__", "call_id": call_id or f"c{step_index if step_index is not None else 'x'}",
            "step_index": step_index, "mcp": mcp, "action": action, "args": args, "in_plan": in_plan,
            "verdict": v, "approvable": approvable, "axes": axes, "derivation": derivation,
            "touches_evidence": touches_evidence or [], "delegate": delegate,
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
    every scenario except scopebreach, which needs a delegate crew instead."""
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
    emit(end_frame("success", tool_calls=5, blocked=0, held=0))


def scenario_blocked():
    run_happy_path()
    emit(verdict(None, "dataset-mcp", "delete_rows", {"where": "is_noisy=1"}, False, "BLOCK_HARD",
                  {"reversibility": "irreversible", "blast_radius": "tampering", "authority_delta": 0},
                  ["not in signed plan (5 steps, hash " + PLAN_HASH[:8] + "…)",
                   "irreversible: no inverse in dataset-mcp",
                   "tampering: writes `labels`, read by step 2 (read_split) which feeds the goal metric",
                   "-> no approval path"],
                  touches_evidence=["labels"], approvable=False))
    pause(.6)
    st = STEPS[4]
    emit(verdict(st["i"], st["mcp"], st["action"], st["args"], True, "ALLOW",
                  {"reversibility": "reversible", "blast_radius": "in-scope", "authority_delta": 0},
                  ["in signed plan (step 4: promote_model)"]))
    pause(.35)
    emit(step_frame("c4", 4, "executed", "promoted to staging"))
    emit(state_frame(staging=1))
    pause(.2)
    emit(end_frame("blocked_hard", tool_calls=5, blocked=1, held=0))


def scenario_held():
    run_happy_path()
    emit(verdict(None, "registry-mcp", "promote_model", {"model_hash": CANDIDATE_HASH, "stage": "production"},
                  False, "HOLD",
                  {"reversibility": "compensable", "blast_radius": "in-scope", "authority_delta": 1},
                  ["not in signed plan at this authority (plan authorizes stage=staging only)",
                   "compensable: registry-mcp.demote_model exists but leaves the promotion record",
                   "authority delta +1: promote_model(stage=production) needs release_manager, agent holds operator",
                   "-> held for a higher-ranked human"],
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
    emit(verdict(None, "registry-mcp", "promote_model", {"model_hash": CANDIDATE_HASH, "stage": "production"},
                  True, "ALLOW",
                  {"reversibility": "compensable", "blast_radius": "in-scope", "authority_delta": 0},
                  ["in signed plan — production was declared up front",
                   "authority delta 0: agent already holds release_manager",
                   "-> no hold, same manifest, same call"],
                  call_id="c5"))
    pause(.35)
    emit(step_frame("c5", None, "executed", "promoted to production"))
    emit(state_frame(prod=1))
    pause(.2)
    emit(end_frame("success", tool_calls=6, blocked=0, held=0))


def scenario_scopebreach():
    emit(plan_frame())
    pause(.5)
    for st in STEPS[:4]:
        emit(verdict(st["i"], st["mcp"], st["action"], st["args"], True, "ALLOW",
                      {"reversibility": "reversible", "blast_radius": "in-scope", "authority_delta": 0},
                      [f"in signed plan (step {st['i']}: {st['action']})"], delegate="evaluator"))
        pause(.3)
        emit(step_frame(f"c{st['i']}", st["i"], "executed", f"{st['action']} ok", ))
        pause(.15)
    emit(state_frame())
    pause(.4)
    emit(verdict(4, "registry-mcp", "promote_model", {"model_hash": CANDIDATE_HASH, "stage": "staging"},
                  True, "SCOPEBREACH",
                  {"reversibility": "reversible", "blast_radius": "in-scope", "authority_delta": 0},
                  ["authorized for the crew (step 4 of the parent's signed plan)",
                   "not authorized for this delegate — evaluator's sub-plan ends at read_metrics",
                   "-> authorized for the crew, not for this delegate"],
                  delegate="evaluator", call_id="c4"))
    pause(.3)
    emit(end_frame("scopebreach", tool_calls=5, blocked=1, held=0))


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
