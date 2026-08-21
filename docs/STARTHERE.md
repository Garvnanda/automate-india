# START HERE — PromotionGuard

**Track:** ArmorIQ, Problem 1 — *"Autonomous, until it shouldn't be"*
**Team:** Har Agam Deep Singh (HA), Garv Nanda (GN)
**Window:** ~24 hours · **Deliverable:** GitHub repo + recorded demo

---

## The project in five lines

An agent runs an ML model promotion pipeline end to end with nobody watching: read the dataset card, pull the eval split, launch the run, read the metrics, promote the winner to staging.

Two things go wrong, deliberately. It tries to delete rows from the eval set it is being graded on — **blocked**, because `delete_rows` was never in the signed plan. It tries to promote to *production* instead of staging — **held**, because that exceeds its authority, and a higher-ranked human approves from the ArmorIQ dashboard while the agent waits.

Neither violation is catchable by a keyword filter. That is the whole point.

---

## The four documents

| Doc | What it is | Read it when |
|---|---|---|
| **`idea.md`** | The pitch. Why this scenario, why the two violations defeat filtering, the narrative for the judges. No code, no APIs. | First, once. Again before writing the README or recording the video. |
| **`technical.md`** | The design. Architecture, the two SDK surfaces, MCP tool signatures, SQL schemas, the declared plan, the two violations in mechanism-level detail, risk register. | Before writing any code. §7 (the two violations) and §8 (proxy-reaches-localhost risk) are the load-bearing sections. |
| **`implementation.md`** | The schedule. Phases 0–8 with owners, hour budgets, acceptance criteria, abort criteria, and the ordered cut list. | At the start of every phase. Check its acceptance criterion before moving on. |
| **`../CLAUDE.md`** | Context for Claude Code. Verified ArmorIQ SDK signatures, ground rules, what to delegate and what not to. Lives at **repo root**, not in `docs/`, because that is the only place Claude Code auto-loads it from. | Every Claude Code session — it loads itself. |

**Reading order, cold start:** `idea.md` → `technical.md` §7 and §8 → `implementation.md` (budget note, then Phase 0) → `CLAUDE.md`.

**If you have ten minutes:** `idea.md`, then this file's "Things that can kill it" below.

---

## Who owns what

**HA owns everything that touches ArmorIQ.** GN owns everything that doesn't.

GN is not available at hour zero. HA runs the spike solo, then pulls the MCP servers forward with Claude Code. GN takes the panel (Phase 6) and the repo/README/video (Phase 7) on arrival — both build against log fixtures committed in Phase 3, so neither blocks on HA.

---

## Things that can kill it

Both are resolved in Phase 1, before anything else is built.

1. **The ArmorIQ proxy may not reach localhost MCP servers.** Nothing downstream matters until one `invoke()` returns real data from a local server. If this isn't working by hour 2, message the organisers. *(technical.md §8)*
2. **The hold path needs two platform identities.** A requester can never approve their own request. Create a low-ranked agent-operator email and a higher-ranked approver email in Phase 1a, or the approval demo is impossible. *(technical.md §7)*

**The open question:** violation 2 is the same action with different params. The documented Merkle digest covers the *action*, and policy globs match `mcp/action` — neither obviously catches a param change. Phase 1d resolves it, and the answer sets how much you build: if params turn out to be inside the plan hash, Surface A catches both violations and the session API becomes optional. Do **not** work around it by splitting the tool into `promote_to_production`; that makes the violation keyword-catchable and forfeits the scenario.

---

## The rules that don't bend

- **Never invent ArmorIQ SDK signatures.** The SDK is new. Anything not in `CLAUDE.md` comes from `docs.armoriq.ai` or from asking. Confident wrong code here costs more than writing it by hand.
- **Guarded and unguarded must be behaviourally identical except for enforcement.** Same reasoning, same prompts, same tool sequence. If they diverge, the before/after demo is worthless.
- **The destructive actions must actually destroy.** Rows really leave the database in unguarded mode. Never stub it out for safety.
- **Do not expand scope.** No MLflow, no real training, no drift detection, no multi-agent, no auth, no deployment.
- **Capture evidence as each phase passes,** not at the end. Screenshots, audit exports, log fixtures. At hour 20 the database is in an unknown state and the passing run is three refactors behind you.
- **Record the demo video the moment the flow first works.** Not at the end. Never rely on a live run.
- **Claude Code never pushes.** It commits; you push. If it says a phase is done and committed, that is your cue, not its permission.

---

## Never cut

The unguarded "before" run · one real destructive artifact · the audit trail.

Everything else has a place in the cut list (`implementation.md`, bottom). The phases sum to more hours than exist, so this list is not a contingency — it is the plan. **Checkpoint at hour 12** and start working down it if Phase 4 is not passing.

---

## Commands

```bash
python data/reset.py                                # wipe + reseed. You will run this constantly.
python -m agent.main --unguarded                    # the "before"
python -m agent.main --guarded                      # the "after"
python -m agent.main --guarded --force-violation 1  # deterministic: delete_rows
python -m agent.main --guarded --force-violation 2  # deterministic: production promotion
./demo.sh                                           # full sequence for recording
```

---

## Decisions already made, so nobody relitigates them

- **The demo panel is ours to build.** ArmorIQ's dashboard is enforcement-side only and structurally cannot show the before/after: the unguarded run never touches ArmorIQ, and their dashboard cannot see our SQLite. Plain HTML/CSS/JS reading the JSON logs — no framework, no build step. Their approval UI, audit viewer and topology graph we use as-is.
- **If the model won't take the bait, ship forced-only.** Three attempts at the organic injection, then move on. `--force-violation` exists precisely because enforcement is what's judged.
- **Don't build both SDK surfaces speculatively.** Phase 1d decides which one Violation 2 needs.

---

## First hour, in order

1. `git init`, commit these four docs and `CLAUDE.md` (HA).
2. Freeze the Phase 0 contract — schemas, tool signatures, log schema, constants in one config module.
3. `pip install armoriq-sdk`, `armoriq init/login/validate`, API key in `.env`.
4. Create **both** platform identities — agent-operator and higher-ranked approver.
5. Gate 1: get one `invoke()` to reach a local FastMCP server and return.

Nothing downstream of step 5 is worth starting until step 5 passes.
