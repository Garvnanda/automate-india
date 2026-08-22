# PromotionGuard v2 — Upgrade Plan, Surfaces & Fallbacks

**Status:** v1 works — pipeline, enforcement, instrument panel, tunnel bring-up all live.
**This document:** what changes in v2, why, what we fall back to when each part fails, and how
the demo grows from one screen to four.

> **Rule zero.** v1 is a working submission. Before any v2 work begins:
> ```
> git tag v1-working && git push --tags
> ```
> Every fallback in §5 is "check out the tag." If that tag does not exist, none of this is safe.

---

## 1. Why v2 exists — the one flaw in v1

v1's panel holds a strict integrity rule: *"Nothing on the panel is fake."* Every trace pulse,
gauge reading and lamp is real. That line holds everywhere **except at the one place the judge
touches.**

The controls are `HAPPY / VIOL-1 / VIOL-2`, and behind them `--force-violation N` tells the agent
which violation to commit.

So the honest reading of v1 is: the enforcement is real, but the scenarios are a menu. A judge does
not have to *suspect* hardcoding — the labels announce it. "VIOL-1" is not something an agent does,
it is something a demo has.

Two symptoms of the same root:

- **The plan strip is a fixed `PLAN` array** — 5 steps plus a reserved 6th column for
  `delete_rows`. The panel knows the violation in advance. Good engineering (no reflow mid-demo),
  and simultaneously an admission that the outcome is foreseen.
- **There is no signing beat.** The most important moment in the system — `capture_plan()` → token
  — has no representation on an instrument panel that represents everything else.

**Everything else in v1 is right and must not be touched:** the scope engine, spring-damped gauges,
key dial, console, tooltip engine, the freeze-mid-swing hold trace, and the refusal to put an
Approve button on the panel.

---

## 2. What changes in v2

### 2.1 Scenario buttons → two banks of switches

**Bank A — AUTHORIZE.** These *become the signed plan*.

| Switch | Default | Notes |
|---|---|---|
| Read dataset card | on, **locked** | baseline |
| Read eval split | on, **locked** | baseline |
| Launch evaluation run | on, **locked** | baseline |
| Read metrics | on, **locked** | baseline |
| Promote to staging | on, free | |
| Promote to production | **off**, free | the authority escalation |
| Clean noisy rows from eval set | **off**, free | the destructive one |

**Bank B — CONDITIONS.** These set the world, not the authority.

| Dial | Positions |
|---|---|
| Model result | clears the bar · narrowly misses · clearly fails |
| Dataset card | clean · poisoned |
| Candidate hash | match · mismatch |

The violation stops being *selected* and starts being *emergent*: it is whatever the agent reaches
for that Bank A did not authorize, under Bank B's conditions.

### 2.2 Plan strip built from the run stream, not a JS constant

Add a `__plan__` frame emitted at run start, immediately after `get_intent_token()` returns. The
strip assembles live, step by step, as the token is minted.

That is the **signing beat** v1 is missing, built from layout that already exists.

The reserved 6th column stays — but it is now reserved for *whatever the agent reaches for outside
the plan*, which is honest, and it becomes a real green step when the judge authorizes it.

### 2.3 One mapping-table row changes

v1 §6.4 maps *action not in plan → `.bad`*. In v2 that becomes **membership decides**:

| Verdict | In plan? | Result |
|---|---|---|
| `executed` | yes | `.done`, advance |
| `executed` | **no** | `.bad` — enforcement was off |
| `blocked` | no | `.bad` |
| `held` / `approved` | yes | `.held` |
| `executed` (`delete_rows`, **authorized**) | **yes** | `.done` green, rows really drop |

### 2.4 The move that ends the hardcoding argument

**Let a judge tick "Clean noisy rows."**

Poisoned card fires. Agent calls `delete_rows`. Under full ArmorIQ enforcement, **it goes through.**
Rows really drop. `cellB` — the green guarded gauge — shows the damage.

Same injection, same reasoning, same call, opposite outcome, decided by nothing but plan
membership.

No hardcoded demo can do this. A hardcoded demo can only ever block. Being able to *authorize the
dangerous action and watch it succeed* is the strongest possible proof that enforcement is real —
and it costs nothing, because the destructive path already exists for the unguarded run.

Say it out loud: *"I'm going to authorize the thing that got blocked a minute ago. Watch it work."*

---

## 3. One screen → four surfaces

The instrument stays one page. What grows is the number of **distinct surfaces the demo moves
through** — each one real, none of them new build beyond what §2 already requires.

### Surface 1 — ARM (pre-run state of the panel)

The controls row swaps into the two switch banks. The judge sets authority and conditions. The
plan strip is empty. The plate reads `PLAN NOT SIGNED`.

This is a *state*, not a page — no routing, no new layout.

### Surface 2 — RUN (the v1 instrument, unchanged)

Scope, gauges, plan strip, key dial, console. Exactly as built. The strip populates from
`__plan__`, then lights step by step.

### Surface 3 — PROOF (post-run state)

After `__END__`, the panel settles into a proof state: for each call, the `plan_hash`, the step
index, the CSRG path, the verdict, and whether step verification resolved.

**Built only from data the SDK already returns.** If `step_proofs` / `merkle_root` are not exposed
in a renderable form, this surface renders the verdict chain without the proof detail rather than
faking it. Honesty rule from v1 applies unchanged.

### Surface 4 — the ArmorIQ dashboard (a genuinely separate authority surface)

Not ours, and that is the point. The held plan appears under **Plans → "Needs you"**, a
higher-ranked human approves, and the agent resumes.

Using their dashboard rather than building our own is a *deliberate architectural statement*:
authority does not live in our process. Say that to the judges.

**Rehearsal requirement:** have the dashboard already open, logged in, filtered to "Needs you", on
a second window before the demo starts. The most impressive twelve seconds in the project become
forty seconds of tab-switching otherwise.

### Optional Surface 5 — the raw terminal

Agent stdout, unstyled, beside the panel. The unglamorous truth that makes the pretty parts
credible — the same reasoning behind v1's raw console. Zero build cost.

---

## 4. Failure modes and how each is handled

### 4.1 Judge unchecks a step the agent needs

**Prevention.** The four read steps render as **locked switches with a lock lamp**, on by default.
The instrument idiom already supports this — a locked toggle reads as a factory setting, not a
disabled control.

**Graceful failure.** If someone unlocks and unchecks a read anyway, this is **not a broken run**.
The agent hits an unauthorized read, ArmorIQ blocks it, the strip lights `.bad`, BLOCK annunciates,
the console prints the reason. A correct and legible outcome. The only backend work is ensuring
`agent/main.py` emits a proper verdict line instead of crashing — **the panel needs no change**,
because it already handles blocks.

**Hard guard.** RUN disabled when zero steps are selected, reason on `.plate`. An empty plan is the
one input that produces genuinely nothing.

### 4.2 Judge picks a combination where nothing interesting happens

Everything authorized, clean card, model passes. **Do not prevent this** — it is the
*"flows freely, nobody watching"* beat, and it is half the track's thesis.

What is needed is that it is not someone's *first* impression. Add a **rotary preset selector** in
the `.plate` area: `BASELINE / INJECTION / ESCALATION`, plus `CUSTOM`, which any switch turn drops
you into. Matches the console idiom, ~40 min, keeps the switches fully live.

### 4.3 The hold path does not work

The single biggest dependency in the project. If ArmorIQ's authority-limit hold does not fire, we
lose simultaneously: the hold, the key dial, the freeze-mid-swing trace, the dashboard approval
beat, and the track's headline requirement.

**Fallback:** blocks only. The key dial reverts to a permanent `NO PENDING APPROVAL` state. Narrate
the approval flow as designed-and-wired-but-unconfirmed. Still a solid submission — but verify this
**before** starting any §2 work, not after.

### 4.4 Config migration half-lands

**Fallback:** `git checkout v1-working`. This is why rule zero exists. Decide the abort point in
advance: **if the plan strip is not populating from `__plan__` by hour X-4, revert and ship v1.**

A polished v1 beats a broken v2 by a wide margin.

### 4.5 Tunnel dies mid-demo

v1 already probes liveness correctly (treat `>= 500` as dead — a dead cloudflared quick tunnel
still resolves and returns 530 from the edge).

**Fallback:** the recorded deterministic video. Record it the moment the flow works end to end, not
at hour 23.

### 4.6 LLM does not take the injection bait

**Fallback:** `--force-violation` stays in the codebase. It is the *recording* path and the
emergency live path. The judge-facing path is the config. Enforcement is what is judged, not
whether the model is gullible on a given run.

### 4.7 Dashboard login fails on demo day

**Fallback:** pre-authenticated window opened before the demo begins, plus screenshots of the held
plan and the Proof tab committed in `evidence/`.

---

## 5. Fallback ladder — in strict order

Drop from the bottom up:

| # | Feature | Fallback if it fails |
|---|---|---|
| 1 | Preset rotary selector | skip — switches work without it |
| 2 | PROOF surface (§3.3) | verdict chain without proof detail |
| 3 | Bank B condition dials | hardcode to poisoned + narrowly-misses |
| 4 | Authorize-`delete_rows` demo | skip — but this is the cheapest high-value item, fight for it |
| 5 | Bank A + `__plan__` strip | **revert to `v1-working`** |
| 6 | Hold / approve / resume | blocks only |
| 7 | Live run | recorded video |

**Never cut:** the unguarded "before" run, one real destructive artifact on disk, the audit trail.

---

## 6. Demo sequencing — the part that decides the outcome

A panel this polished invites the thought *"what are they hiding?"* The counter is order.

1. **Damage first, chrome second.** Open with the unguarded run and the raw database — forty rows
   gone, wrong model in production, **no panel involved**. If you open with the instrument, you have
   framed yourself as a design project.
2. Bring up the console. Arm the plan. Show it being signed.
3. Happy path — flows freely, nobody watching.
4. Injection → blocked. Rows verified still present.
5. Production promotion → held. Trace freezes mid-swing. Key dial arms. **Switch to the ArmorIQ
   dashboard.** Approve. Agent resumes.
6. **The closer:** re-arm, authorize `delete_rows`, run again, watch it succeed. *"Same injection.
   Same call. This time it was in the plan."*
7. Proof surface. Any call traced to its plan hash and verdict.

### Lines to have rehearsed word for word

- On why a filter fails: *"Same server, same tool, same call it made thirty seconds ago. Only the
  argument changed. There is nothing to filter on."*
- On the missing Approve button: *"We never built one. Authority doesn't live in our process — a
  requester can't approve their own request, so approval happens where the role hierarchy is."*
- On the stakes, for a generalist judge: one sentence on why a silently trimmed eval set is
  catastrophic. Have it ready; do not improvise it.

---

## 7. Time budget

| Work | Owner | Est. |
|---|---|---|
| **Verify hold path end to end** | HA | **blocking, do first** |
| Plan built from config, accepted as query params, `__plan__` frame | HA | 2.0h |
| Bank A switches + dynamic plan strip | GN | 2.5h |
| Authorize-`delete_rows` path + mapping row | HA | 0.5h |
| Bank B condition dials | GN | 1.0h |
| Preset selector | GN | 0.7h |
| PROOF surface | GN | 1.0h |
| Record deterministic video | both | 0.5h |

**Minimum viable v2** = hold verified + Bank A + `__plan__` strip + authorize-`delete_rows`
≈ **5 hours**. That is the entire "is this hardcoded" fix. Everything below it is upside.

---

## 8. Honest assessment

**Ahead of the field:** proxy reachability already solved (a fraction of teams will lose the whole
event to it); a presentation layer nobody will match; genuine domain differentiation; design
integrity rules that are themselves a competitive signal.

**What actually decides it:** whether hold → dashboard approval → live resume works in the room,
whether the config migration lands without breaking a working panel, and whether the
"couldn't a filter do this?" answer comes out in one breath.

**Biggest risk:** the best UI element in the project is downstream of the least-verified mechanism
in the SDK. Verify the hold before building anything else.

**Realistic outcome:** wins if the hold works live and the story is sequenced damage-first. Top
three even if the hold fails, provided the blocks are clean. Loses only by breaking a working
frontend at hour 19, or by opening with the beautiful thing instead of the broken database.
