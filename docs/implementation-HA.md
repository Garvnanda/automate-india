# v3 Implementation — Har Agam (core enforcement)

**Your scope:** tool manifest, severity engine, policy generation, planner, delegation.
**Not your scope:** anything that renders. If you find yourself editing CSS, stop.

> Paths below assume `agent/`, `mcp/`, `panel/`. Adjust to the actual repo once, at the top of
> Phase 0, and tell Garv.

---

## 0. Before anything

```
git tag v2-final && git push --tags
git checkout -b v3
```

Every abort in this document is `git checkout v2-final`. If the tag isn't pushed, nothing below is
safe to start.

---

## 1. The contract — freeze this first, share it with Garv, then never break it

This is the only thing that lets you two work in parallel. Commit it as `CONTRACT.md` in hour one.
Garv builds against these shapes with a fake emitter; you fill them in for real. **If you need to
change a field name after Phase 1 starts, message him before you push.**

### 1.1 `__plan__` frame — emitted once, immediately after the token is minted

```jsonc
{ "type": "__plan__",
  "plan_hash": "4f2a…",
  "merkle_root": "9c11…",
  "goal": "evaluate the candidate and promote if it clears the bar",
  "bindings": { "dataset": "eval_v3", "model": "cand-0917" },
  "agent_role": "operator",
  "steps": [
    { "i": 0, "mcp": "dataset-mcp", "action": "get_dataset_card",
      "args": {}, "reads": ["dataset_card"], "writes": [],
      "required_role": "reader" }
  ],
  "edges": [ { "from": 0, "to": 1, "resource": "labels" } ],
  "evidence_base": ["labels", "dataset_card", "metrics"],
  "generated_policy": "<opa text, string>" }
```

`edges` and `evidence_base` are computed by you (§3.2). Garv draws the graph from them — he must
not recompute dependencies in JS.

### 1.2 `__verdict__` frame — one per tool call, before execution

```jsonc
{ "type": "__verdict__",
  "call_id": "c7",
  "step_index": 3,              // null if out-of-plan
  "mcp": "dataset-mcp", "action": "delete_rows", "args": { "where": "is_noisy=1" },
  "in_plan": false,
  "verdict": "BLOCK_HARD",      // ALLOW | HOLD | BLOCK | BLOCK_HARD | SCOPEBREACH | NOTED
  "approvable": false,
  "axes": { "reversibility": "irreversible",
            "blast_radius": "tampering",
            "authority_delta": 0 },
  "derivation": [
    "not in signed plan (5 steps, hash 4f2a…)",
    "irreversible: no inverse in dataset-mcp",
    "tampering: writes `labels`, read by step 2 (read_split) which feeds the goal metric",
    "-> no approval path"
  ],
  "touches_evidence": ["labels"],
  "delegate": null,             // "evaluator" | "deployer" once Phase 5 lands
  "plan_hash": "4f2a…", "delegation_hash": null, "step_proof": "…" }
```

`derivation` is an ordered array of plain sentences. Garv prints them verbatim. **You are
responsible for them reading like English, not like log lines.** This is the single highest-value
20 minutes in the project — if a generalist judge can read the block and reconstruct the rule
without you speaking, you've won the exchange in §1.2 of v3.md.

### 1.3 Other frames

| Frame | When | Fields |
|---|---|---|
| `__step__` | verdict resolved and executed | `call_id`, `step_index`, `status`, `result_summary` |
| `__hold__` | delegation request raised | `call_id`, `request_id`, `dashboard_hint` |
| `__resume__` | approval received | `call_id`, `approved_by` |
| `__state__` | DB counters after any write | `eval_rows`, `prod_promotions`, `staging_promotions` |
| `__END__` | run over | `outcome`, `counts` |

`__state__` after **every** write is what drives the gauges and the ghost divergence. Cheap, and
Garv is blocked without it.

### 1.4 Run configuration — query params on the run endpoint

```
POST /run?mode=guarded|unguarded
  body: { goal, bindings, conditions:{card,result,hash}, agent_role, plan?, force_violation? }
```

`plan` present = use it verbatim (this is the edited plan coming back from the panel, and it is how
Phase 2 works at all). `plan` absent = generate.

---

## 2. Phase 0 — verify `delegate()` (blocking, do this before writing any code)

Same discipline v2 applied to the hold path, same reason: your most valuable feature is downstream
of your least-verified mechanism.

Write a 40-line throwaway script: capture a plan, delegate a two-step subset to a named sub-agent,
have the sub-agent call something inside its subset and something outside it, print both verdicts.

**Gate:** the out-of-subset call is refused with a distinguishable reason while the parent still
holds authority for it.

- **Pass** → Phase 5 stays in the plan.
- **Fail** → delete Phase 5 now, tell Garv immediately so he doesn't build rings, and reallocate
  those hours to Phases 1–4. Do not "come back to it later."

Timebox: **45 minutes.** If you can't answer the question in 45 minutes, that is a fail.

---

## 3. Phase 1 — severity engine (the MVP; nothing else ships without it)

**Entry:** contract committed, tag pushed.

### 3.1 `tools/manifest.json`

Every tool across all three MCPs. Fields exactly as v3.md §2.2: `reads`, `writes`, `inverse`,
`authority`. No verdicts, no severities, no action names in any conditional. If you catch yourself
writing `"delete_rows": {"verdict": ...}` you have rebuilt the thing we're attacking.

`authority` keys are argument predicates (`"stage=production"`) with `"*"` as default.

### 3.2 `agent/severity.py`

```python
def evidence_base(plan, manifest) -> set[str]
def blast_radius(action, args, plan, manifest) -> "tampering" | "in-scope" | "external"
def reversibility(action, manifest) -> "reversible" | "compensable" | "irreversible"
def authority_delta(action, args, manifest, agent_role) -> int
def classify(call, plan, manifest, agent_role) -> Verdict   # + derivation strings
```

`evidence_base` = union of `reads` over steps whose output feeds the goal predicate. For our plan
that's every step before the terminal promote. Keep it simple: all reads by non-terminal steps.

Routing matrix straight from v3.md §2.4. `NOTED` implemented, **default off**.

### 3.3 `agent/policy_gen.py`

Walk (plan × manifest × role), emit the OPA constraints and hold thresholds you currently
hand-write, hand them to the SDK at capture time, and put the text in `__plan__.generated_policy`.

**Delete the hand-written policy file in the same commit.** If it still exists, someone will assume
it's live and the demo claim is dead.

### 3.4 Wire into the call path

Severity runs **only when plan membership fails**. In-plan calls flow untouched — this is what
keeps v2's authorize-`delete_rows` closer alive (v3.md §2.6).

### 3.5 Gate — do not proceed until all four are true

1. Unguarded run still destroys 40 rows and lands a production promotion.
2. Guarded run: `delete_rows` returns `BLOCK_HARD` with a four-line derivation, rows still 100.
3. Guarded run: production promotion returns `HOLD`, `approvable: true`, and the hold still fires
   on ArmorIQ's dashboard.
4. Granting `release_manager` changes the production verdict to `ALLOW` **with no edit to
   `manifest.json`.** This is closer A and it is your proof the manifest isn't a lookup table.

**Abort:** if (3) regresses — you broke the hold while rewriting the policy path —
`git checkout v2-final` and ship v2. That regression is the one unrecoverable outcome.

---

## 4. Phase 2 — generated plan

**Entry:** Phase 1 gate green.

### 4.1 `agent/planner.py`

Constrained generation against `manifest.json`. Temperature 0. The model may only emit
`(mcp, action, args)` triples that exist with schema-valid args.

Validation before returning: tools resolve, args valid, bindings resolved, at least one dataset
read, terminal state-changing action, DAG acyclic, ≤ 8 steps. One retry on failure.

### 4.2 `plans/cache/`

Three preset goal strings with their cached plans: `BASELINE`, `INJECTION`, `ESCALATION`. On
validation failure twice, load the nearest preset and set `"planner_fallback": true` in `__plan__`
so Garv can light the lamp. Honest, and unremarkable — a preset plan is still a signed plan.

### 4.3 Accept an edited plan

`POST /run` with `plan` present must sign exactly what it was given, after re-validating it. This
is the entire point of the editor: **the judge signs what's on screen.**

### 4.4 Gate

- Typed goal → valid plan → `__plan__` frame with correct `edges` and `evidence_base`.
- Panel-edited plan round-trips and signs, and the plan hash differs from the unedited one.
- Editing `stage` to `production` in the plan produces a run with **no hold at all** (v3.md §3.3).
- Killing the LLM mid-plan produces a preset fallback, not a stack trace.

**Abort:** presets only, editor still live over the preset plan. Costs you the typed-goal moment,
nothing else.

---

## 5. Phase 3 — support Garv's graph (small, do it inline)

You have almost nothing here beyond emitting `edges`, `evidence_base` and `touches_evidence`
correctly — which Phase 1 and 2 already require. Your job is to make sure the ejection frame has
what the animation needs: for an out-of-plan call, `touches_evidence` must list the exact resources
so he can point the rejected node at the shaded region.

**Gate:** Garv's graph renders your `edges` without JS-side recomputation.

---

## 6. Phase 4 — trace recorder (hand the output to Garv)

`scripts/record_unguarded.py`: run unguarded with a fixed seed and `--force-violation`, capture
every frame to `evidence/unguarded_trace.jsonl`, commit it.

Frames must carry `step_index` — Garv syncs on step index, never wall clock (v3.md §5.3). A trace
without step indices is useless to him.

**Gate:** trace replays through his ghost layer and forks at the injection.

---

## 7. Phase 5 — delegation (only if Phase 0 passed and 1–4 are green)

**Entry:** Phases 1–4 gates all green and stable for one full clean run. Not "mostly working."

Parent signs the full plan, then delegates two fixed sub-plans (evaluator / deployer, v3.md §6.1)
as proper subsets of the parent's merkle tree. **Sequential. Two delegates. No dynamic spawning, no
concurrency.**

Emit `delegate` and `delegation_hash` on every verdict from Phase 5 onward — Garv's rings key off
`delegate`.

**Gate:** the evaluator calling `promote_model(stage="staging")` returns `SCOPEBREACH` with the
derivation *"authorized for the crew, not for this delegate"*, and the trust chain
`plan_hash → delegation_hash → step_proof` prints for every call.

**Abort:** feature-flag it off (`DELEGATION=0`) and run single-agent. Because the flag is the abort,
build the flag on day one, not when you need it.

---

## 8. Ordering and abort clock

| Phase | You | Cumulative |
|---|---|---|
| 0 · verify `delegate()` | 0.75 h | 0.75 |
| 1 · manifest + severity + policy gen | 4.25 h | 5.0 |
| 2 · planner + cache + edited-plan intake | 2.0 h | 7.0 |
| 3 · graph support | 0.25 h | 7.25 |
| 4 · trace recorder | 0.5 h | 7.75 |
| 5 · delegation | 3.0 h | 10.75 |

**Hard rule:** at **X−4 hours** before the demo, stop building. Whatever is green is what ships.
If Phase 2 is not green at X−6, drop it to presets and go straight to Phase 4.

**The one thing that must be true at the end:** Phase 1's gate. Everything else is upside, and a
clean v3 stopping after Phase 1 beats a broken one that started Phase 5.
