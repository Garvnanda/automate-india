# PromotionGuard — Implementation Plan

**Window:** ~24 hours, realistically ~17 working hours after sleep and food.
**Owners:** **HA** = Har Agam · **GN** = Garv · **CC** = delegated to Claude Code

Ownership rule: **HA owns everything that touches ArmorIQ.** GN owns everything that doesn't.

**Reality adjustment — GN is not available at hour zero.** The first block is solo. HA runs the spike, then pulls the MCP servers forward with Claude Code. When GN arrives he takes the panel and the repo/README/video.

> **Revision note.** Rewritten after reading the ArmorIQ SDK and platform docs. Phase 1 has
> grown and now contains two hard go/no-go gates. Phases are renumbered. Read `technical.md`
> §7 and §8 before starting.

## The budget does not close — plan for it

Phases 0–7 sum to **~18.5 hours** against **~17 working hours**. Phase 8 "buffer" is already negative before anything goes wrong, and something will.

This is not a reason to rush; it is a reason to start cutting on schedule rather than in a panic. **Checkpoint at hour 12.** If Phase 4 (enforcement) is not passing by then, open the cut list at the bottom of this file and work down it in order — starting with bonus items and panel polish, which cost nothing to lose.

The tell that you are in trouble is not "we are behind", it is "we are still polishing something on the cut list". Track elapsed hours against phase numbers somewhere visible.

---

## Phase 0 — Contract freeze (30 min) · **HA solo, GN reads on arrival**

Nothing else starts until these are committed. They are the interface that lets GN start cold without asking you anything.

- [ ] Repo created, both have push access, `CLAUDE.md` / `idea.md` / `technical.md` / `implementation.md` committed
- [ ] SQLite schemas fixed (`labels`, `dataset_card`, `models`, `promotions`)
- [ ] MCP tool signatures fixed — exact names and params for all eight tools
- [ ] Log schema fixed: `{ts, mode, step, action, mcp, params, verdict, reason}`, `verdict ∈ allowed|blocked|held|approved|executed`
- [ ] Constants fixed in one config module: `CANDIDATE_HASH`, `THRESHOLD`, `AGENT_EMAIL`, `APPROVER_EMAIL`

**Acceptance:** both of you can describe every tool signature without looking.

---

## Phase 1 — The ArmorIQ spike (2.5 hrs, blocking) · **HA**

The highest-risk item in the project, and larger than it first looked. Two of these are go/no-go gates.

### 1a. Platform setup (30 min)

- [ ] Watch the organisers' walkthrough video first — it covers SDK init → policy → audit logs end to end and will save more time than it costs
- [ ] `pip install armoriq-sdk`, `armoriq init` → `armoriq.yaml`, `armoriq login`, `armoriq validate`
- [ ] API key in `.env` as `ARMORIQ_API_KEY` (starts `ak_live_` / `ak_test_`)
- [ ] Agent registered in the platform's asset registry
- [ ] **Two identities created: a low-ranked agent-operator email and a higher-ranked approver email.** A requester can never approve their own request — without this the hold demo is impossible
- [ ] MCP servers registered in the platform registry

### 1b. GATE 1 — proxy reachability (45 min)

**Does the ArmorIQ proxy reach a local MCP server?** Stand up a throwaway FastMCP server with one tool and get one `invoke()` to return real data from it.

If not: try `use_production=False` with local endpoint overrides, then a cloudflared/ngrok tunnel with the public URL registered.

> **Nothing downstream matters until this passes.** If it isn't working by **hour 2**, message the organisers — it's their SDK and their track, and they'd rather unblock you than watch you fail quietly.

### 1c. GATE 2 — block and hold (45 min)

- [ ] `capture_plan()` + `get_intent_token()` returning a signed token
- [ ] One planned `invoke()` succeeds
- [ ] One unplanned `invoke()` raises `IntentMismatchException` — **this is violation 1's mechanism, proven**
- [ ] Surface B: `for_user(email).start_session().start_plan([...])` then `session.check(...)`
- [ ] Trigger one `PolicyHoldException`, see the plan appear under **Plans → "Needs you"**, approve as the higher-ranked user, confirm the agent can proceed

### 1d. Resolve the open question (30 min)

Invoke a **planned action with unplanned params**. Does `IntentMismatchException` fire?

- **Yes** → params are inside the plan hash. Violation 2 has a clean cryptographic catch on Surface A. **Surface B is now optional** — it buys the dashboard-approval beat and nothing else. Build Phase 4 on Surface A alone, get both violations passing, and treat Phase 5 as a bonus.
- **No** → the authority-limit path is the primary design and Surface B is mandatory. Configure the agent's role limit so staging promotion is within its authority and production is above it.

**Write the answer down in the repo the moment you have it.** Phase 4 scope depends on it and a later session will not remember.

**Acceptance for Phase 1:** you can allow one call, block another, hold a third, and approve the held one from the dashboard — and you know which mechanism catches violation 2.

**Abort criteria, decided now not at hour 15:**
- Gate 1 failing at hour 2 → escalate to organisers immediately
- Gate 2 hold path failing at hour 4 → ship **blocks only**, cut the approval beat, narrate it as future work

---

## Phase 2 — MCP servers and seed data (2 hrs) · **HA driving CC**

Mechanical work. Hand the whole phase to Claude Code with the Phase 0 schemas and review the output.

Build in this order — `reset.py` first, because every later checkpoint in the project depends on getting back to a known state.

- [ ] `data/seed.py` + `data/reset.py` — **build these first.** You will run `reset.py` thirty times today; every acceptance criterion from here on starts with it. Seed enough rows that a deletion is visible at a glance.
- [ ] `data/poisoned_card.txt` written and seeded
- [ ] `dataset-mcp`: `read_split`, `get_dataset_card`, `delete_rows`
- [ ] `jobs-mcp` (mock): `launch_run`, `get_run_status`, `read_metrics`
- [ ] `registry-mcp`: `list_models`, `promote_model`

**Acceptance:** all eight tools callable from a scratch script, `delete_rows` demonstrably removes real rows, `reset.py` restores everything.

---

## Phase 3 — Agent core, unguarded (3 hrs) · **HA**, boilerplate by **CC**

- [ ] LLM tool-calling loop on OpenRouter, all three MCP servers registered as tools
- [ ] Completes the happy path autonomously: card → split → run → metrics → promote(staging)
- [ ] Structured JSON logs for every step
- [ ] `--unguarded` calls MCP servers directly
- [ ] `--force-violation {1,2}`

**Acceptance — the checkpoint that matters most.** Run unguarded with the injection active and confirm the rows **actually disappear** from `labels` and a **production** row actually lands in `promotions`. The track is explicit: *"Confirm the unguarded version actually breaks something before you add enforcement, or you'll have no before/after to show."*

Screenshot it. That's the "before" slide. **Then commit a few real log files as fixtures** — that's what makes GN's arrival productive instead of a briefing session.

### GATE 3 — does the model take the bait? (timeboxed, 20 min)

Run the unguarded pipeline organically — no `--force-violation` — with the poisoned card seeded. Does the agent reach for `delete_rows` on its own?

- **Yes** → you have the organic run. Record it, it is the more convincing demo.
- **No, after three attempts** → **stop tuning.** Strengthen the card once, try once more, then ship forced-only and move on. Enforcement is what's judged, not whether the model bites on a given run — that is exactly why `--force-violation` exists. An hour lost to prompt-tuning here is an hour taken from Phase 4.

Modern models often refuse to touch an eval set. Budget for the refusal rather than being surprised by it at hour 9.

---

## Phase 4 — ArmorIQ enforcement (3 hrs) · **HA**

- [ ] `agent/armoriq_client.py` wrapper hiding both SDK surfaces behind one call function
- [ ] `capture_plan()` at run start with the five declared steps
- [ ] All tool calls routed through ArmorIQ in `--guarded`
- [ ] Explicit `allow` globs for every planned action — **enforcement is fail-closed, an unlisted action dies silently**
- [ ] Happy path passes end to end under enforcement
- [ ] Violation 1 blocked — rows verified still present
- [ ] Violation 2 held — registry verified unchanged

**Acceptance:** same agent binary, same prompt, two modes, opposite outcomes in the database.

**Capture evidence now, while it works.** The moment violation 1 blocks cleanly: screenshot the row count proving the rows survived, screenshot the ArmorIQ audit entry, export the Plan Detail Proof tab into `evidence/`. Same for violation 2 when it holds. At hour 20 the database is in some unknown state and the passing run is three refactors behind you — Phase 7 collects the evidence folder, it does not generate it.

---

## Phase 5 — Hold, approve, resume (2 hrs) · **HA**

- [ ] Agent waits on the held plan instead of crashing
- [ ] Approve from the dashboard as the higher-ranked user
- [ ] Agent resumes and finishes the run
- [ ] Timeout handling so a stalled wait doesn't hang the demo

**Acceptance:** approve from the dashboard on a phone and watch the terminal continue. That moment is the demo.

**Record this the first time it works.** Screen-record the terminal and the dashboard together. Do not plan to re-stage it later; the hold path has the most moving parts of anything in the build.

**Cut first if behind:** hard blocks only, narrate the approval flow as future work.

---

## Phase 6 — Demo control panel (3 hrs) · **GN's first task on arrival**, scaffolded by **CC**

Builds against the log fixtures from Phase 3 — no dependency on HA's progress.

**This has to be built; ArmorIQ does not ship it.** Their dashboard is enforcement-side only — Plans Governance, Policies, Audit Logs, AIQraph, Quick Scan. It cannot be our panel for two structural reasons: the unguarded run bypasses ArmorIQ entirely, so nothing about it ever reaches their dashboard and there is no before/after contrast to render; and their dashboard has no knowledge of our SQLite, so row counts in `labels` and the contents of `promotions` are invisible to it. The split-screen and the world-state panel are ours. The approval UI, audit viewer and topology graph stay theirs.

**Stack:** a single-page web panel — plain HTML/CSS/JS reading the JSON log files, no framework, no build step. Two `<pre>` columns and a table is the whole thing. A terminal TUI is acceptable if GN prefers it, but the panel gets screen-recorded, and a browser window is easier to make legible in a video than a terminal. Decide on arrival, do not litigate it twice.

- [ ] Split screen: unguarded (left) vs guarded (right)
- [ ] Scenario buttons: happy path · violation 1 · violation 2
- [ ] Streaming logs, colour-coded, blocked/held calls in red with the ArmorIQ reason inline
- [ ] **World-state panel:** live row count in `labels` and contents of `promotions`, side by side. This is what makes "the rows are gone" vs "the rows survived" legible in one glance
- [ ] Reset button wired to `reset.py`

**Explicitly not building:** an approval UI, an audit log viewer, or a topology graph. ArmorIQ ships all three and using theirs is a point in our favour.

---

## Phase 7 — Repo, README, demo video (2.5 hrs) · **GN** writes, **HA** reviews, **CC** drafts

- [ ] `README.md`: the problem, architecture diagram, **why a keyword filter fails here**, quickstart
- [ ] `demo.sh` — one command: reseed → unguarded → reset → guarded. Judges love a one-command repro
- [ ] `evidence/` — exported ArmorIQ audit trail, before/after DB screenshots, Plan Detail Proof tab screenshot
- [ ] **Demo video recorded the moment the flow first works end to end.** Do not save this for the end. Do not rely on a live run

---

## Phase 8 — Buffer · both

It will be consumed. Bonus items only if genuinely free: token expiry mid-run; PAP pre-flight decisions; a second injection variant; AIQraph screenshot in the README.

---

## Cut list, in strict order

1. Bonus items
2. Panel polish → plain streaming logs are fine
3. Hold/resume → blocks only
4. Violation 2 → **keep violation 1**, it is the one whose mechanism is proven at Gate 2
5. Panel entirely → terminal + README + video still scores

**Never cut:** the unguarded "before" run, one real destructive artifact, the audit trail.

> Note this reverses the earlier draft. Violation 2 is the better *story*, but violation 1 rests on plain step verification, which is the best-documented part of the SDK. If time collapses, ship the one that certainly works.

---

## Repo structure

```
promotionguard/
├── README.md · CLAUDE.md · idea.md · technical.md · implementation.md
├── demo.sh · requirements.txt · .env.example · armoriq.yaml
├── agent/
│   ├── main.py            # loop, --guarded / --unguarded / --force-violation
│   ├── plan.py            # the five declared steps
│   ├── armoriq_client.py  # wrapper over both SDK surfaces
│   ├── config.py          # constants, emails, thresholds
│   └── logging.py         # the JSON log contract
├── mcp_servers/  dataset_mcp.py · jobs_mcp.py · registry_mcp.py
├── data/         seed.py · reset.py · poisoned_card.txt
├── panel/        (GN)
└── evidence/     audit exports, screenshots
```

---

## Working with Claude Code

**Point it at `CLAUDE.md` every session.** It contains the verified SDK signatures, the two open risks, and the scope boundaries. Without it the model will invent ArmorIQ APIs that look right and aren't.

**Never let it write ArmorIQ integration code from memory.** The SDK is new; nothing in any model's training data is reliable about it. Paste the real docs into context or write that part by hand.

**Delegate boilerplate, not enforcement.** MCP scaffolds, schemas, seeds, the panel, README, `demo.sh` — all good. `agent/armoriq_client.py` — do it yourself.

**Ask for verification, not just implementation.** "Write a script that asserts the rows are still present after violation 1" beats "handle violation 1" — you need those assertions as demo evidence anyway.

**One phase per session.** Long sessions drift. Finish a phase, check its acceptance criterion, commit, start fresh.

**Commit continuously.** A repo with real history reads as a team that built something.

**Two people, two working directories.** The Phase 0 contract is what makes that safe.
