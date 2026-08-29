# v3 Implementation — Garv (panel rework + frame layer)

**Your scope:** the whole panel rework, the SSE frame layer that feeds it, the evidence tooling.
**Not your scope:** the severity engine, the planner, delegation logic. Those are HA's; you consume
their output and never recompute it in JS.

---

## 0. Before anything

HA tags `v2-final` and commits `CONTRACT.md`. **Read it before you write a line.** Every abort in
this document ends at `git checkout v2-final`, and every phase below is built against the contract,
not against HA's progress.

### 0.1 Build against a fake emitter from hour one

Your first task, before any UI work:

```
scripts/fake_stream.py  --scenario blocked|held|approved|scopebreach|clean
```

Replays hand-written frames in the contract's shapes at realistic intervals over the same SSE
endpoint. **This is not throwaway** — it becomes your regression harness, your screenshot tool, and
your fallback if HA's backend is unstable at hour 19. Forty-five minutes, and it decouples you
completely.

If you skip this you will spend the event blocked on someone else's commits. Do not skip it.

---

## 1. Rules that carry over from v1 and must not break

- **Nothing on the panel is fake.** One exception in v3: the ghost layer, which is permanently
  labelled `RECORDED` with its trace file path visible (§5).
- **No Approve button in our panel, ever.** Authority does not live in the process being governed.
  Approval happens on ArmorIQ's dashboard.
- Spring-damped gauges, key dial, raw console, tooltip engine, freeze-mid-swing hold trace — all
  survive untouched. You are adding surfaces, not replacing the instrument.
- Anything that can't be understood as a frozen screenshot is decoration and gets cut.

---

## 2. Phase 1 — verdicts with derivations (do this first, it's small and it's the whole thesis)

**Entry:** contract committed. Works entirely off `fake_stream.py`.

`INTENTMISMATCH` is a status code. Replace it everywhere with the `derivation` array from the
`__verdict__` frame, printed verbatim as sentences — console, tooltip, and the verdict card.

New verdict states to render (map from `verdict` + `approvable`):

| Verdict | Treatment |
|---|---|
| `ALLOW` | existing `.done` |
| `HOLD` | existing `.held`, key dial arms |
| `BLOCK` | existing `.bad` |
| `BLOCK_HARD` | **new** — `.bad` plus a distinct `NO APPROVAL PATH` annunciator. It must be visibly a different category from `BLOCK`, because that distinction is the project's best claim |
| `SCOPEBREACH` | Phase 6; render as `.bad` with the delegate name until then |
| `NOTED` | ships disabled; render as `.done` with a dim flag if it ever appears |

Also render `generated_policy` from the `__plan__` frame — a small monospace panel beside the plan
during signing. It's three seconds on screen and it's the artefact that proves the policy wasn't
written before the event.

**Gate:** all five verdicts render correctly from `fake_stream.py`, `BLOCK_HARD` is unmistakably
distinct from `BLOCK`, derivation text is readable at demo projector distance.

---

## 3. Phase 2 — ARM surface and the plan editor

**Entry:** Phase 1 gate green. Independent of HA's planner — build against a static draft plan JSON.

### 3.1 ARM (a panel state, not a route — same as v2)

- Goal text field + three preset buttons (`BASELINE / INJECTION / ESCALATION`).
- Resource bindings: dataset picker, model picker. **These two are the only required inputs.**
- Bank B condition dials, carried over from v2 unchanged: card clean/poisoned, model
  clears/misses/fails, hash match/mismatch.
- Role grant selector: `reader / operator / release_manager`. This drives closer A.
- Plate reads `NO PLAN`. RUN disabled until bindings resolve.

### 3.2 REVIEW — the editable draft

The draft plan is **editable, not a preview**: delete a step, add one from a tool palette built from
the manifest, reorder, change an argument. Changing `stage` from `staging` to `production` must
visibly update that step's required role *before* signing.

Edited plan POSTs back in `body.plan` and is signed verbatim. Plate: `PLAN NOT SIGNED` until the key
dial turns.

### 3.3 Guards

- RUN disabled with the reason on `.plate` if the plan is empty or bindings are unresolved.
- `planner_fallback: true` in `__plan__` lights a visible `PLANNER FALLBACK` lamp. Honest, and it
  keeps HA's fallback path from looking like a bug.

**Gate:** a plan can be edited and signed, the hash visibly changes after an edit, and an empty plan
cannot be run.

**Abort:** hide the goal field, presets only. The editor still works over the preset plan — you lose
almost nothing.

---

## 4. Phase 3 — the plan as a growing graph

**Entry:** Phase 2 gate green. This is your biggest piece; budget accordingly.

### 4.1 Non-negotiables

- Nodes and edges come **entirely from `__plan__.edges`**. Do not compute dependencies in JS — the
  edges are the severity engine's input, and if the panel derives its own version they will
  disagree on stage.
- Deterministic layered left-to-right layout, positions computed once at sign time and **frozen**.
  No physics, no reflow mid-run.
- `evidence_base` renders as a shaded region behind the subgraph that feeds the goal metric.
- ≤ 8 nodes. No animation over 600 ms.

### 4.2 Choreography

| Moment | Behaviour |
|---|---|
| Signing | one node drops in per step as the merkle builds — this is v1's missing signing beat, made spatial |
| Executed | node fills, outgoing edge lights |
| Out-of-plan call | an **unattached node arrives from outside**, attempts to connect, fails, is ejected, derivation printed beside it |
| `BLOCK_HARD` | before ejection the node visibly reaches toward the shaded evidence region, using `touches_evidence` from the frame. **This single frame is the demo** — spend your polish here |
| `HOLD` | node pulses at the boundary, neither admitted nor ejected; key dial arms; trace freezes mid-swing as in v1 |
| approved | node snaps into place, execution resumes through it |

**Gate:** a full `fake_stream.py --scenario blocked` run reads correctly as a sequence of stills.
Screenshot every state and check it cold.

**Abort:** render the graph statically at sign time, no choreography. Still better than v2's strip.

---

## 5. Phase 4 — the ghost run

**Entry:** Phase 3 gate green, and `evidence/unguarded_trace.jsonl` exists from HA.

A dim second track replaying the recorded unguarded run beside the live one. At the injection the
tracks fork: ghost's row gauge drains to 60, the live gauge holds at 100.

### 5.1 Sync — the part that breaks if done naively

**Align on `step_index`. Never on wall clock.** The guarded run pauses at the hold for however long
the dashboard approval takes; a clock-aligned ghost runs away and the screen becomes noise.

- Ghost advances one step only when the live run *resolves* a step, any verdict.
- At a hold, the ghost freezes too, and renders its next step as a dimmed preview: *"unguarded,
  this is what happened next."*
- Where verdicts differ, draw the fork explicitly and hold it on screen.

### 5.2 Honesty

Permanent `RECORDED · UNGUARDED · <run id> · <timestamp>` label on the ghost layer with the trace
file path visible. The moment a judge suspects the ghost is fabricated, every real thing on the
panel is suspect too.

### 5.3 Kill switch

A **keyboard toggle** that freezes and hides the ghost layer, falling back to v2's static
before/after database view. Build the toggle when you build the layer, not when it desyncs on
stage.

**Gate:** ghost stays synchronised through a full hold → dashboard approval → resume cycle.

---

## 6. Phase 5 — PROOF surface

**Entry:** Phase 4 gate green.

Post-`__END__` state. Per call: `plan_hash → delegation_hash → step_proof → verdict → derivation`.
Built only from fields the frames already carry. **If a field isn't in the frame, render the chain
without it rather than faking it** — v1's honesty rule, unchanged.

**Gate:** any call in the run can be traced to its plan hash and its derivation in two clicks.

**Abort:** skip. A screenshot in `evidence/` covers it.

---

## 7. Phase 6 — delegation rings — DONE, verified live

The SDK's own `delegate_subtree()` doesn't confine (CONTRACT.md §5, tested live: a delegate's token
carries the parent's full authority regardless of subtree headers). `agent/crew.py` is the real
replacement — confinement enforced by our own code, layered on ArmorIQ's real plan-membership
check, honest about being ours. Built against that, not the SDK path this phase originally assumed.

Sub-plans render as enclosing regions around their subtrees (`renderDelegateRing`), keyed off
`delegate`/`__delegate__.steps` — never recomputed from anything else. The cross-scope block —
evaluator reaching into the deployer's step — renders as a purple-bordered node, `OUT OF SCOPE`,
sitting outside the ring; `SCOPEBREACH` gets its own class in `V3_CLASS`/`V3_CAT`, distinct purple
from `BLOCK_HARD`'s pink, same `NO APPROVAL PATH` lamp (both are `approvable:false`).

**Gate:** `fake_stream.py --scenario scopebreach` renders the evaluator's call crossing into the
deployer's region and being rejected — verified. **And**, beyond the original gate: verified live
through the actual browser panel against the real backend (`--guarded --force-violation 3` via
`GUARDED` + `REPLAY:SCOPE` + `RUN`) — real `__delegate__` frame, real `SCOPEBREACH`, `promotions`
table confirmed empty in `registry.db` after. See `done.md`'s "GN Phase 6" entry for the full trail,
including a stale-server-process bug the live test caught and fixed.

---

## 8. Ordering and abort clock

| Phase | You | Cumulative |
|---|---|---|
| 0 · fake emitter | 0.75 h | 0.75 |
| 1 · verdicts + derivations + policy panel | 1.5 h | 2.25 |
| 2 · ARM + plan editor | 2.5 h | 4.75 |
| 3 · graph + choreography | 3.0 h | 7.75 |
| 4 · ghost layer | 2.0 h | 9.75 |
| 5 · PROOF surface | 1.0 h | 10.75 |
| 6 · delegation rings | 1.0 h | 11.75 |

**Hard rule:** at **X−4 hours**, stop building and start screenshotting. At X−3, record the
deterministic video against `fake_stream.py` if the live backend is shaky — a recorded run of real
frames is still real.

**The failure that actually loses this:** breaking a working panel at hour 19. v2's own assessment
said so and it is still true. Every phase above is additive and independently revertable — keep it
that way, commit small, and never leave the panel in a non-rendering state overnight.
