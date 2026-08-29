"""Generate the ArmorIQ policy from the plan, instead of hand-writing it.

v2 registered a hand-written allow list: three logical servers, eight tool names,
typed into `agent/infra.py` before the event. It worked, and it was the weakest
claim in the project — a judge who noticed it could say the consequence of
failing the plan check was a lookup, and they would have been right.

This module walks (signed plan x manifest x granted role) and emits that same
registration policy as a derived artefact. Nothing about which tools exist is
decided here; what is decided is what *this run's plan* needs, which is why the
generated policy changes when the judge changes the plan and nothing else.

The text form goes on screen at the signing beat (docs/v3.md §2.9) — three
seconds of visible artefact that says the policy came out of the plan, seconds
ago, rather than out of a config file, weeks ago.
"""

from agent.severity import authority_delta, entry_for, evidence_base, load_manifest


def generate(plan, agent_role, manifest=None, server_map=None):
    """Return {"allow": [...], "deny": [...], "holds": [...], "text": "..."}.

    `allow` is every (server, action) the signed plan actually calls, in the
    session's registered ids. Anything the plan does not call is simply absent,
    and registration is fail-closed — so the plan is the allow list.

    `deny` is the tools whose blast radius against *this* plan is tampering and
    whose damage cannot be undone: there is no argument, and no approver, that
    makes them acceptable mid-run, so they are refused at the proxy as well as
    by plan membership. Note what this does NOT do: deny by name. A tool lands
    here only if the manifest's facts and this plan's evidence base put it here.
    """
    manifest = manifest or load_manifest()
    server_map = server_map or _infer_server_map(plan, manifest)
    evidence = evidence_base(plan, manifest)

    planned = []
    for step in plan.get("steps", []):
        key = (step.get("mcp"), step.get("action"))
        if key not in planned:
            planned.append(key)

    allow = [f"{mcp}.{action}" for mcp, action in planned]

    deny, holds = [], []
    for key, entry in manifest["tools"].items():
        logical, _, action = key.partition(".")
        mcp = server_map.get(logical, logical)
        if (mcp, action) in planned:
            # in the plan: the plan authorized it, and severity never runs on it
            continue
        writes = set(entry["writes"])
        if writes & evidence and not entry["inverse"]:
            deny.append(f"{mcp}.{action}")
        elif writes or authority_delta(mcp, action, _worst_args(entry), manifest, agent_role) > 0:
            holds.append(f"{mcp}.{action}")

    return {"allow": allow, "deny": deny, "holds": holds,
            "text": _render(plan, agent_role, evidence, allow, deny, holds)}


def _infer_server_map(plan, manifest):
    """{logical mcp: whatever id this plan's steps actually use}.

    A signed plan carries session-scoped ids (`jobs-mcp-bf8180`) while the
    manifest is keyed by logical name. Without this mapping every planned step
    fails the "already in the plan?" test below and lands in deny or hold —
    which is exactly the bug this function exists to close.
    """
    out = {}
    for step in plan.get("steps", []):
        key, _ = entry_for(step.get("mcp"), step.get("action"), manifest)
        if key:
            out[key.partition(".")[0]] = step.get("mcp")
    return out


def _worst_args(entry):
    """The argument shape that demands the most authority — a tool is only
    'within the agent's grant' if its most demanding form is."""
    for predicate in entry.get("authority", {}):
        key, _, value = predicate.partition("=")
        if key:
            return {key: value}
    return {}


def _render(plan, agent_role, evidence, allow, deny, holds):
    """Human-readable, and deliberately not JSON: it is read off a screen at
    demo distance, once, for three seconds."""
    lines = [
        "# generated policy",
        f"# derived from this run's signed plan ({len(plan.get('steps', []))} steps)"
        f" and the granted role `{agent_role}`",
        f"# evidence base: {', '.join(sorted(evidence)) or '(none)'}",
        "",
        "allow:   # every action the signed plan actually calls",
    ]
    lines += [f"  - {a}" for a in allow] or ["  (none)"]
    lines += ["", "deny:    # irreversible writes to the evidence this run is graded on"]
    lines += [f"  - {d}" for d in deny] or ["  (none)"]
    lines += ["", "hold:    # reachable, but not on the agent's own authority"]
    lines += [f"  - {h}" for h in holds] or ["  (none)"]
    return "\n".join(lines)


def demo():
    plan = {"steps": [
        {"action": "get_dataset_card", "mcp": "dataset-mcp", "params": {}},
        {"action": "read_split", "mcp": "dataset-mcp", "params": {"split": "val"}},
        {"action": "launch_run", "mcp": "jobs-mcp", "params": {}},
        {"action": "read_metrics", "mcp": "jobs-mcp", "params": {}},
        {"action": "promote_model", "mcp": "registry-mcp",
         "params": {"model_hash": "h", "stage": "staging"}},
    ]}

    p = generate(plan, "operator")
    assert p["allow"] == ["dataset-mcp.get_dataset_card", "dataset-mcp.read_split",
                          "jobs-mcp.launch_run", "jobs-mcp.read_metrics",
                          "registry-mcp.promote_model"], p["allow"]
    # delete_rows: irreversible write to `labels`, which step 2 read. Denied, and
    # the reason it is denied is this plan, not its name.
    assert p["deny"] == ["dataset-mcp.delete_rows"], p["deny"]

    # The same manifest against a plan that never reads the labels: the write is
    # no longer to evidence, so delete_rows drops out of deny and into hold.
    no_read = {"steps": [s for s in plan["steps"] if s["action"] != "read_split"]}
    q = generate(no_read, "operator")
    assert q["deny"] == [], q["deny"]
    assert "dataset-mcp.delete_rows" in q["holds"], q["holds"]

    # Authorize delete_rows up front and it is simply in the allow list — v2's
    # closer survives (docs/v3.md §2.6).
    authorized = {"steps": plan["steps"] + [
        {"action": "delete_rows", "mcp": "dataset-mcp", "params": {"row_ids": []}}]}
    r = generate(authorized, "operator")
    assert "dataset-mcp.delete_rows" in r["allow"] and r["deny"] == [], r

    # Session-scoped ids are what gets registered.
    s = generate(plan, "operator", server_map={"dataset-mcp": "dataset-mcp-bf8180"})
    assert "dataset-mcp-bf8180.delete_rows" in s["deny"], s["deny"]

    # A plan whose steps already carry session ids must not have its own steps
    # land in deny/hold — the map is inferred from the plan when none is given.
    sessioned = {"steps": [dict(st, mcp=f"{st['mcp']}-bf8180") for st in plan["steps"]]}
    t = generate(sessioned, "operator")
    assert t["deny"] == ["dataset-mcp-bf8180.delete_rows"], t["deny"]
    assert t["holds"] == [], t["holds"]
    assert all(a.endswith("-bf8180." + a.rpartition(".")[2]) for a in t["allow"]), t["allow"]

    print(p["text"])
    print()
    print("policy_gen: ALL CHECKS PASSED")


if __name__ == "__main__":
    demo()
