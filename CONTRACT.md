# CONTRACT — v3 frame layer

The interface between HA (`agent/`, `tools/`, `scripts/`, `plans/`) and GN (`panel/`).

**Frozen once, here.** If a field name has to change after Garv starts Phase 1, message him
*before* pushing. Everything in this file is what the panel may rely on; anything not in this file
does not exist.

---

## 0. Corrections to `docs/implementation-HA.md` / `implementation-GN.md`

Both docs were written against assumed paths and an assumed SDK capability. Real repo, real SDK:

| Doc says | Actually |
|---|---|
| `mcp/` | `mcp_servers/` |
| `POST /run?mode=...` | `GET /api/run?...` (SSE), already live in `panel/server.py` |
| Phase 5 — delegation / `SCOPEBREACH` | **struck out, see §5** |

**Additive rule (decided, non-negotiable).** Every frame below is *added*. Nothing v2 emits is
removed or reshaped. Today's panel keeps rendering through the whole of v3 — GN's own doc names
"breaking a working panel at hour 19" as the failure that actually loses this, and the additive
rule is how that is prevented structurally rather than by care.

So: `__plan__` gains fields, keeps every field it has. `log_event`'s JSONL line
(`{ts, mode, step, action, mcp, params, verdict, reason}`) is untouched — `__verdict__` is emitted
*alongside* it, not instead of it.

---

## 1. Transport

Every frame is one line of JSON on `agent.main`'s **stdout**, relayed verbatim by
`panel/server.py`'s SSE stream. A frame is an object with exactly one top-level key naming it.
Non-frame stdout lines (the JSONL log line, the agent's final message) keep flowing as they do
today; the panel already distinguishes them.

---

## 2. `__plan__` — once, the moment the plan is fixed

v2 fields (unchanged, still emitted): `steps[]` (`action`, `mcp`, `params`), `signed`, `plan_hash`,
`token_id`.

v3 adds:

```jsonc
{ "__plan__": {
    "steps": [
      { "action": "get_dataset_card", "mcp": "dataset-mcp", "params": {},
        "i": 0,                                   // NEW — step index, the sync key everywhere
        "reads": ["dataset_card"], "writes": [],  // NEW — from tools/manifest.json
        "required_role": "reader" }               // NEW — resolved against this step's own args
    ],
    "signed": true, "plan_hash": "b2683c49…", "token_id": "02f982cf…",
    "goal": "evaluate the candidate and promote if it clears the bar",   // NEW
    "bindings": { "dataset": "eval-split-v2", "model": "cand-v7-8f3a2b" }, // NEW
    "agent_role": "operator",                                            // NEW
    "edges": [ { "from": 0, "to": 1, "resource": "labels" } ],           // NEW
    "evidence_base": ["labels", "dataset_card", "metrics"],              // NEW
    "generated_policy": "<opa text, string>",                            // NEW
    "planner_fallback": false                                            // NEW
} }
```

`edges` and `evidence_base` are computed by the severity engine. **The panel must not recompute
dependencies in JS** — if it derives its own version the two will disagree on stage.

Unguarded runs emit the same frame with `signed:false`, `plan_hash:null`, `generated_policy:null`.
That difference is shown, never hidden.

---

## 3. `__verdict__` — one per tool call, before execution

```jsonc
{ "__verdict__": {
    "call_id": "c7",
    "step_index": 3,                 // null when out-of-plan
    "mcp": "dataset-mcp", "action": "delete_rows", "args": { "row_ids": [1,2] },
    "in_plan": false,
    "verdict": "BLOCK_HARD",         // ALLOW | HOLD | BLOCK | BLOCK_HARD | NOTED
    "approvable": false,
    "axes": { "reversibility": "irreversible",
              "blast_radius": "tampering",
              "authority_delta": 0 },
    "derivation": [
      "not in signed plan (5 steps, hash b2683c49…)",
      "irreversible: no inverse in dataset-mcp",
      "tampering: writes `labels`, read by step 2 (read_split) which feeds the goal metric",
      "-> no approval path"
    ],
    "touches_evidence": ["labels"],
    "plan_hash": "b2683c49…", "step_proof": "…"
} }
```

`derivation` is an ordered array of plain English sentences. **Printed verbatim.** A generalist
judge must be able to read the block and reconstruct the rule with nobody narrating.

`SCOPEBREACH` and `delegate` / `delegation_hash` are **not** in this contract — see §5.

Verdict → panel treatment:

| Verdict | Treatment |
|---|---|
| `ALLOW` | existing `.done` |
| `HOLD` | existing `.held`, key dial arms |
| `BLOCK` | existing `.bad` |
| `BLOCK_HARD` | **new** — `.bad` plus a distinct `NO APPROVAL PATH` annunciator. Must read as a different *category* from `BLOCK`; that distinction is the project's best claim |
| `NOTED` | ships disabled; `.done` with a dim flag if it ever appears |

---

## 4. The rest

| Frame | When | Fields |
|---|---|---|
| `__step__` | verdict resolved and executed | `call_id`, `step_index`, `status`, `result_summary` |
| `__hold__` | delegation request raised | `call_id`, `request_id`, `dashboard_hint` |
| `__resume__` | approval received | `call_id`, `approved_by` |
| `__state__` | **after every write** | `eval_rows`, `prod_promotions`, `staging_promotions` |
| `__END__` | run over | `outcome`, `counts` |

`__state__` after every write drives the gauges and the ghost divergence. Cheap to emit, and the
panel is blocked without it.

`__final_state__` (v2, synthesized by `panel/server.py`) stays exactly as it is.

---

## 5. Phase 5 (delegation / `SCOPEBREACH`) is struck — verified, not assumed

`docs/implementation-HA.md` §2 made this a blocking gate. It was run live against the real platform
on 2026-08-29 and **it failed.**

- `client.delegate_subtree()` (SDK 0.6.2, `client.py:1144`) works: real `trust_id`, `subtree_root`,
  a 5-element Merkle `inclusion_proof`, and a child token that auto-attaches
  `X-CSRG-Subtree-Path/Root/Parent-Root` on `invoke()`. Path format is `/steps/[N]`.
- **But the confinement is not enforced.** A delegate holding only `/steps/[0]`
  (`get_dataset_card`) successfully called `promote_model` and landed a real staging promotion.
  Mirrored: a delegate holding only `/steps/[4]` (`promote_model`) successfully called `read_split`.
- Control proves enforcement is otherwise alive: `delete_rows` on the same delegated token raised
  `IntentMismatchException`.

The delegated token carries the **parent's full authority**. The subtree headers are accepted and
ignored on this deployment.

**Therefore: GN does not build delegation rings. That phase never existed.** Whether we rebuild
scope confinement in our own code is parked until the severity engine's gate is green, and if it
ever ships it ships narrated as ours — the "cryptographically derived authority" claim in
`docs/v3.md` §6.3 is not available, because the proxy demonstrably ignores the proof.

---

## 6. Ownership

**HA:** `agent/`, `tools/`, `scripts/`, `plans/`, this file.
**GN:** `panel/index.html`, `panel/server.py`, `scripts/fake_stream.py`.

One shared edge: `panel/server.py` must forward new run-config fields to `agent.main` and relay
unknown frames untouched. HA does not edit `panel/`. GN does not recompute anything in JS that a
frame already carries.

Every abort in v3 ends at `git checkout v2-final` (tagged at `c0260e3`).

---

## 7. Amendments after Phases C–E (2026-08-29)

**7.1 Frames are type-keyed.** `{"type": "__verdict__", ...}` — matching
`scripts/fake_stream.py` and `handleVerdictV3`, not the nested `{"__verdict__": {...}}` shape
Phase B first emitted. Guarded runs emit the type-keyed `__plan__`; **unguarded runs keep emitting
the v2 nested `__plan__`**, because the v3 handler reports the plan as signed and in an unguarded
run nothing signed it.

**7.2 In-plan calls emit a verdict too.** `verdict: "ALLOW"`, `in_plan: true`, derivation
`["in signed plan (step N: action)"]`. Severity itself still only runs on deviations — the ALLOW
frame is so the panel can light steps as they resolve, not a judgement.

**7.3 Unguarded runs emit no `__verdict__` frames at all.** Nothing judged those calls. They emit
`__step__` and `__state__` only, which is everything the ghost needs.

**7.4 `__END__.outcome`** is one of `unguarded` | `clean` | `held_then_approved` | `blocked` |
`not_approved`. An unguarded run is never `clean`: that word is a claim about enforcement.

**7.5 `merkle_root` is null.** The SDK's `IntentToken` carries `plan_hash` and `step_proofs` and no
separate merkle root. Reporting null beats aliasing `plan_hash` into a second field and implying
two independently verified things.

**7.6 New agent flags** — `panel/server.py` should forward these when the ARM surface sends them:
`--goal "<text>"` (generate the plan) and `--plan '<json>'` or a path (sign an edited plan verbatim
after re-validation). `--config` gains `agent_role` (`reader|operator|release_manager|data_owner`).
An invalid plan exits with a one-line judge-readable reason on stderr, never a traceback.

**7.7 The ghost trace is `evidence/unguarded_trace.jsonl`**, produced by
`python -m scripts.record_unguarded`. Line 1 is a `__trace__` header (`run_id`, `recorded_at`,
`violation`, `frames`) for the permanent `RECORDED` label. Every replayable frame carries
`step_index`; the pre-run `__state__` carries `step_index: -1`, the world before step 0.
