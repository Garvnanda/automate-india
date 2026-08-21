# CLAUDE.md — PromotionGuard

Project context for Claude Code. Read this before touching anything.

---

## What this is

A hackathon submission for the **ArmorIQ track, Problem 1** (*"Autonomous, until it shouldn't be"*).

A single autonomous agent runs an ML model promotion pipeline end to end. ArmorIQ enforces that it can only do what its signed plan authorized. Two deliberate violations get caught — one hard-blocked, one held for human approval.

**~24 hour build. Ruthless scope discipline. Read `docs/idea.md` and `docs/technical.md` before proposing anything.**

Docs live in `docs/`: `STARTHERE.md` (map + orientation), `idea.md` (pitch), `technical.md` (design), `implementation.md` (schedule). This file stays at repo root so it auto-loads.

---

## Non-negotiable ground rules

1. **Never invent ArmorIQ SDK signatures.** The SDK is new (published mid-2026) and nothing in your training data is reliable about it. If you need an API you have not been shown, **stop and ask** rather than writing plausible-looking code. Verified signatures are in the section below; anything else must come from `docs.armoriq.ai`.
2. **Do not expand scope.** No MLflow, no real training, no drift detection, no `delegate()`, no multi-agent anything, no auth, no deployment. If a change adds a dependency, ask first.
3. **Two agent modes must stay behaviourally identical except for enforcement.** `--unguarded` and `--guarded` run the same reasoning, same prompts, same tool sequence. The *only* difference is whether calls route through ArmorIQ. If they diverge, the before/after demo is worthless.
4. **Every tool call emits a structured log line.** The schema is fixed in `agent/logging.py`. Do not change it without updating the panel.
5. **The destructive actions must actually be destructive.** In unguarded mode, rows really leave the database and a wrong promotion really lands in the registry. Never stub this out "for safety".
6. **Never run `git push`. Never create a PR.** Committing locally is fine and expected (see Conventions). Pushing is the human's call, always. When a phase's acceptance criterion passes and the work is committed, say so and say "good point to push" — then stop. Do not push, do not offer to push, do not push because a previous session pushed.
7. **Update `done.md` after every message.** Before ending a turn, re-check `done.md` against what was actually completed this turn — tick anything genuinely finished, leave everything else unticked. Never tick something that wasn't actually verified done in this session.
8. **README.md must work verbatim on a judge's clean machine.** They clone the repo and run exactly the commands in the README — nothing else. No hardcoded local paths, no reliance on globally-installed packages, `requirements.txt` kept in sync with every import actually used, `.env.example` kept in sync with every env var actually read. README grows with each batch instead of being written once at the end. When in doubt, verify by installing into a throwaway venv from a fresh copy of the repo and running the README steps for real — don't just eyeball it.

---

## Verified ArmorIQ facts

Copied from the official docs. Trust these over your own recollection.

### Install and config

```bash
pip install armoriq-sdk        # Python SDK + `armoriq` CLI
```

CLI commands: `armoriq init`, `login`, `validate`, `register`, `orgs`, `keys`, `status`, `logs`.
`armoriq init` produces `armoriq.yaml`, loadable via `ArmorIQClient.from_config("armoriq.yaml")`.

Env: `ARMORIQ_API_KEY` (must start with `ak_live_`, `ak_test_` or `ak_claw_`), optional `ARMORIQ_ENV` (`production` / `staging` / `local`), optional `IAP_ENDPOINT` / `PROXY_ENDPOINT` / `BACKEND_ENDPOINT` overrides.

### Client

```python
from armoriq_sdk import ArmorIQClient
client = ArmorIQClient()          # reads ARMORIQ_API_KEY
```

There is **no** `user_id` or `agent_id` parameter any more. Identity is resolved from the API key plus a per-request email.

### Surface A — stateless (blocks, no holds)

```python
plan = {
    "goal": "...",
    "steps": [
        {"action": "read_split", "mcp": "dataset-mcp", "params": {"split": "val"}},
    ],
}
captured = client.capture_plan(llm="...", prompt="...", plan=plan)
token    = client.get_intent_token(captured, policy=None, validity_seconds=3600)

result = client.invoke("dataset-mcp", "read_split", token, {"split": "val"}, user_email="...")
```

`invoke(mcp, action, intent_token, params=None, merkle_proof=None, user_email=None)` returns
`{"success": bool, "data": any, "error": str, "execution_time_ms": int, "mcp": str, "action": str}`.

Raises `IntentMismatchException` (action not in plan), `TokenExpiredException`, `MCPInvocationException`.

### Surface B — session (this is where holds live)

```python
scope   = client.for_user("agent-operator@example.com")
session = scope.start_session()
session.start_plan([{"action": "read_split", "mcp": "dataset-mcp"}])
decision = session.check("read_split", {"split": "val"})
```

Per the docs: *"Sessions add policy enforcement, holds, and approval waiting."* `for_user(email)` is cheap — user context is cached for 5 minutes.

Exceptions to catch: `PolicyBlockedException`, `PolicyHoldException`, plus the three above and `ConfigurationException`.

### Policy shape

```python
policy = {
    "allow": ["jobs-mcp/*", "dataset-mcp/read_*"],
    "deny":  ["dataset-mcp/delete_*"],
    "allowed_tools": [...],
    "rate_limit": 100,
    "ip_whitelist": [...],
    "time_restrictions": {"allowed_hours": [...], "allowed_days": [...]},
    "priority": 50,
}
```

Globs are `mcp/action` — **action level, not parameter level**. Policies authored in the dashboard are stored org-side and apply automatically; they are *not* passed to the SDK. There is no `policy_id` parameter. Evaluation is priority-ordered, first match wins, **fail-closed if no policy matches**.

### How enforcement actually works

`invoke()` sends CSRG headers: `X-CSRG-Path` (e.g. `/steps/[0]/action`), `X-CSRG-Value-Digest` (SHA256 of the action value), `X-CSRG-Proof` (Merkle proof array). The proxy validates the proof against `plan_hash`, checks the CSRG path matches plan structure, verifies the value digest, verifies the Ed25519 signature — then routes to the MCP.

**Read that carefully: the documented digest is over the *action*, not the params.** See "The open question" below.

### How holds actually work

From the Plans Governance docs: when a tool call exceeds what an agent's policy allows on its own — *typically a monetary or authority limit* — ArmorIQ raises a **delegation request** rather than failing outright. The call carries requester context (email, role, amount). If it exceeds the requester's role limit, the plan is **held**. A human with a **higher-ranked role** approves or rejects from the dashboard. **A requester can never approve their own request.**

Consequence for us: **two platform identities are required.** One low-ranked email the agent runs as, one higher-ranked email to approve with. Set both up before writing agent code.

---

## The open question (resolve in the spike, before building)

Violation 2 is *the same action with different params* (`promote_model(stage="production")` instead of `stage="staging"`). The documented Merkle verification digests the **action**, and policy globs match **`mcp/action`**. Neither obviously catches a parameter change.

Test this explicitly in Phase 1, in this order:

1. **Preferred — authority limit.** Model production promotion as an authority escalation carrying an amount/role limit, so it trips the delegation-hold path natively. This is what the hold mechanism is *designed for*, and it gives us the approve-from-dashboard beat the track explicitly asks for.
2. **If params turn out to be in the plan hash** — verify by invoking a planned action with unplanned params and seeing whether `IntentMismatchException` fires. If it does, that is a clean cryptographic catch and worth showing alongside option 1.
3. **Fallback** — an OPA rule in Policy Studio conditioned on the param.

Do **not** fall back to splitting `promote_model` into `promote_to_production` as a separate action name. That makes the violation keyword-catchable and forfeits the whole point of the scenario.

**The answer decides how much you build.** If option 2 holds — params are inside the plan hash — Surface A catches both violations and **Surface B is not needed for enforcement**. Only build the session path if you still want the dashboard-approval beat, and only after the happy path and both blocks work. If option 1 is the answer, Surface B is mandatory and Violation 2 depends on it. Decide this at the end of Phase 1d and write the decision down; do not build both surfaces speculatively.

---

## The other risk that can kill the project

The ArmorIQ **Proxy routes requests to MCP servers**. Our MCP servers run on localhost. A hosted proxy may not be able to reach them.

Resolve in the first hour. Options in order of preference: `use_production=False` for local endpoints; a tunnel (cloudflared / ngrok) with the public URL registered in the platform's MCP registry; self-hosting per the platform docs.

**Nothing else matters until a single `invoke()` reaches a local MCP server and comes back.**

---

## Architecture

```
agent/main.py  ──▶ ArmorIQ (capture_plan → token → invoke/check)
                        │  allow → proxy → MCP server
                        │  block → IntentMismatchException / PolicyBlockedException
                        └─ hold → plan held → dashboard approval → resume

mcp_servers/dataset_mcp.py   read_split · get_dataset_card · delete_rows ⚠
mcp_servers/jobs_mcp.py      launch_run · get_run_status · read_metrics   (mock)
mcp_servers/registry_mcp.py  list_models · promote_model ⚠
```

The agent has **no direct path** to any MCP server in guarded mode.

## The declared plan (five steps, fixed)

```python
[
  {"action": "get_dataset_card", "mcp": "dataset-mcp",  "params": {}},
  {"action": "read_split",       "mcp": "dataset-mcp",  "params": {"split": "val"}},
  {"action": "launch_run",       "mcp": "jobs-mcp",     "params": {"model_hash": CANDIDATE, "split": "val"}},
  {"action": "read_metrics",     "mcp": "jobs-mcp",     "params": {}},
  {"action": "promote_model",    "mcp": "registry-mcp", "params": {"model_hash": CANDIDATE, "stage": "staging"}},
]
```

`delete_rows` is **deliberately absent**. That absence is what blocks violation 1.

## Repo layout

```
promotionguard/
├── README.md · CLAUDE.md · idea.md · technical.md · implementation.md
├── demo.sh · requirements.txt · .env.example · armoriq.yaml
├── agent/       main.py · plan.py · armoriq_client.py · logging.py
├── mcp_servers/ dataset_mcp.py · jobs_mcp.py · registry_mcp.py
├── data/        seed.py · reset.py · poisoned_card.txt
├── panel/       (Garv)
└── evidence/    audit exports, before/after screenshots
```

## Commands

```bash
python data/reset.py                                   # wipe + reseed. Run constantly.
python -m agent.main --unguarded                       # the "before"
python -m agent.main --guarded                         # the "after"
python -m agent.main --guarded --force-violation 1     # deterministic: delete_rows
python -m agent.main --guarded --force-violation 2     # deterministic: production promotion
./demo.sh                                              # full sequence for recording
```

## Conventions

- Python 3.11, FastMCP for MCP servers, SQLite (no ORM), OpenRouter for the LLM.
- Constants (`CANDIDATE_HASH`, `THRESHOLD`, emails) live in one config module. Never inline them.
- Log line: `{ts, mode, step, action, mcp, params, verdict, reason}` — `verdict` ∈ `allowed | blocked | held | approved | executed`.
- Commit after every phase. Small commits, real history.
- `--force-violation` exists because LLMs are non-deterministic and the demo cannot be. Enforcement is what's judged, not whether the model takes the bait on a given run.

## What to hand to Claude Code, and what not to

**Good to delegate:** MCP server scaffolds, SQLite schema and seeds, `reset.py`, the demo panel, README prose, `demo.sh`, tests and assertion scripts.

**Do not delegate:** the ArmorIQ integration itself. It is the least documented and most load-bearing part, and confident wrong code there costs more than writing it by hand.

**Always ask for verification, not just implementation.** "Write a script that asserts the rows are still present after violation 1" is worth more than "handle violation 1" — those assertions are the demo evidence.
