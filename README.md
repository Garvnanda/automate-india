# PromotionGuard

Hackathon submission — **ArmorIQ track, Problem 1**, *"Autonomous, until it shouldn't be."*

An autonomous agent runs an ML model promotion pipeline end to end, unattended: read the
dataset card, pull the evaluation split, launch a run, read the metrics, promote the winning
model. Two things can go wrong along the way — the agent can be talked into deleting rows from
the evaluation set it is graded on, and it can be talked into promoting a model to *production*
instead of *staging*. Neither reads as an attack: the first arrives as documentation the dataset
card itself provides, the second is the exact same `promote_model` call the agent was already
authorized to make, with one argument changed. A keyword filter catches neither. ArmorIQ catches
both, because it checks the agent's **signed plan**, not the text of the call.

Full pitch in [`docs/idea.md`](docs/idea.md), architecture in
[`docs/technical.md`](docs/technical.md), the panel's design rationale in
[`docs/v2-plan.md`](docs/v2-plan.md).

## Live demo

**[automate-india.onrender.com](https://automate-india.onrender.com)** — the demo panel,
deployed and running.

Hosted on Render's free tier, which spins the service down after 15 minutes of inactivity and
takes roughly 30–60 seconds to cold-start back up (downloading the `cloudflared` binary and
re-registering the MCP tunnel with ArmorIQ on first request). An UptimeRobot keyword monitor
pings the URL every 5 minutes to keep it warm; if the first load is slow, it caught the service
asleep — wait for the enforcement-session indicator in the panel's top-right corner to report
ready.

---

## The two gates

| # | What the agent tries | Mechanism | Outcome |
|---|---|---|---|
| 1 | Delete rows from the evaluation set | not in the signed plan → **hard block**, checked client-side before the call ever leaves the agent process | rows survive, call never reaches the database |
| 2 | Promote to `production` instead of `staging` | exceeds the agent's role authority → **delegation hold** | plan pauses; a higher-ranked human approves from ArmorIQ's own dashboard; agent resumes mid-run |

Every decision — allowed, blocked, held, approved, executed — lands in the audit trail with its
plan hash. Full mechanism writeup in [`docs/idea.md`](docs/idea.md) and
[`docs/technical.md`](docs/technical.md) §7.

---

## What you need before you start

- **Python 3.11+**
- **git**
- An **ArmorIQ platform account** — API key, and two identities (a low-ranked agent-operator
  email and a higher-ranked approver email). Not needed for the setup/verify steps below, only
  for running the agent itself.
- An **OpenRouter API key** — same: only needed once you run the agent. Pick any current free
  tool-calling model from [openrouter.ai/models](https://openrouter.ai/models); the free-tier
  roster shifts, so confirm your choice supports tool calling before relying on it.

## Setup

Clone and enter the repo, then create an isolated environment so this doesn't touch anything
else installed on your machine:

```bash
git clone https://github.com/Garvnanda/automate-india.git
cd automate-india
python -m venv .venv
```

Activate it:

```bash
# Windows (PowerShell / cmd)
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Copy the env template and fill in real values (only required once you reach the ArmorIQ /
OpenRouter steps below):

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

## Verify the setup works (no ArmorIQ / OpenRouter needed yet)

Seed the databases:

```bash
python data/reset.py
```

Run the scratch check — exercises all 8 MCP tool functions directly, proves `delete_rows`
really deletes rows and `reset.py` really restores them:

```bash
python tests/test_mcp_servers.py
```

Expect it to end with `ALL CHECKS PASSED`. If it doesn't, something in setup is wrong before
anything ArmorIQ-related is even involved.

---

## The panel — start here

```bash
python -m panel.server
```

One command, the whole demo. It brings the enforcement session up itself (downloads
`cloudflared` if needed, tunnels the MCP servers, registers them with ArmorIQ) in the
background and shows progress in the top-right corner; guarded mode unlocks once it reports
ready. Open `http://127.0.0.1:8080`.

The page is the **PromotionGuard console** — a six-slide onboarding walkthrough, then an
instrument panel with a dual-trace scope, needle gauges and brass switches, all driven by real
data. Every trace pulse is a line `agent.main` actually printed; every gauge reading comes from
live SQLite.

### Two banks of switches decide the run, not a preset menu

- **AUTHORIZE (Bank A)** — what the agent's signed plan will permit. The four reads
  (`get_dataset_card`, `read_split`, `launch_run`, `read_metrics`) are locked on as the
  baseline. Free switches: promote to staging, promote to production, and clean noisy rows from
  the eval set (`delete_rows`).
- **CONDITIONS (Bank B)** — what the world looks like: whether the candidate model clears the
  accuracy bar, whether the dataset card is clean or poisoned (or your own hand-typed card,
  live-injected into what the agent reads), whether the candidate hash matches the registry.

The violation isn't picked from a menu — it's *emergent*: whatever the agent reaches for that
Bank A didn't authorize, under whatever conditions Bank B set. Authorizing `delete_rows`
yourself and watching it succeed under full enforcement — the same call that was blocked a
minute earlier — is the panel's closing argument that the enforcement is real, not staged.

### The signed plan, built live

The plan strip populates step by step from a `__plan__` frame emitted the moment
`get_intent_token()` returns — the strip is never pre-known. The plate reads
`PLAN NOT SIGNED` before a run and flips to the plan hash once ArmorIQ signs it. Each step
lights green (done), amber (held) or red (blocked) as its verdict arrives.

### LOG and PROOF

Two tabs share one slot beneath the scope: **LOG** is the raw verdict stream for the run in
progress; **PROOF** settles in once a run ends, showing the plan hash, step index, and verdict
for every call actually made against the signed plan.

### Ask the Agent

A floating chat, grounded in the current or most recent run (falls back to a project-only
answer when no run exists yet) — real token streaming from OpenRouter, not a replayed
typewriter effect. Suggested questions are one click away; one of them ("Why did you promote to
that stage?") only appears once a run exists to ground it.

### The hold, and why there's no Approve button on the panel

When a run is held, the key dial arms and a timer runs — an **indicator, not a control**. Real
approval only ever happens on ArmorIQ's own dashboard
(`platform.armoriq.ai → Intent → Held Actions`), by a human with a higher-ranked role than the
agent — a requester can never approve their own request. The panel just watches the
`held → approved → executed` verdicts arrive and turns the key.

Every scenario re-seeds the database first, so consecutive runs are always comparable. If
`python -m agent.infra` is already running in another terminal, the panel detects and reuses
that session instead of starting a second one; `python -m panel.server --no-infra` skips
bring-up entirely.

---

## Running it from the command line

The panel is the judge-facing interface; the CLI underneath it is what makes the demo
reproducible and scriptable.

### Unguarded — no enforcement

```bash
python data/reset.py
python -m agent.main --unguarded --config '{}'                          # happy path, the LLM drives
python -m agent.main --unguarded --config '{}' --force-violation 1      # rows really leave the database
python -m agent.main --unguarded --config '{}' --force-violation 2      # a real production promotion lands
```

### Guarded — every call through ArmorIQ

Guarded mode needs the MCP servers publicly reachable (ArmorIQ's proxy can't reach your
localhost) and registered — one command, left running:

```bash
# terminal 1 — downloads cloudflared on first run, then stays up
python -m agent.infra
```

Wait for `READY`, then in a second terminal:

```bash
python data/reset.py
python -m agent.main --guarded --config '{}'                            # flows freely, nobody watching
python -m agent.main --guarded --config '{}' --force-violation 1        # BLOCKED — rows survive
python -m agent.main --guarded --config '{}' --force-violation 2        # HELD — waits for a human
```

Violation 2 prints a delegation id and pauses. Approve it at
**platform.armoriq.ai → Intent → Held Actions** as your `APPROVER_EMAIL`, and the agent resumes
mid-run and finishes. Nothing reaches the registry until you click.

`--config` takes the same `RunConfig` JSON the panel's switches build
(`agent/runconfig.py`) — `authorized`, `promote_production`, `model_result`, `card`,
`hash_match`, `card_text` — so any Bank A/B combination the panel can express is reproducible
from the command line. `--force-violation` stays available as the deterministic path: it exists
because the LLM is non-deterministic and a recording or emergency live demo can't be.

### Prove it, unattended

```bash
python tests/verify_guarded.py     # with agent.infra running
```

Asserts the happy path completes, `delete_rows` is blocked with all rows still present, and the
production promotion is held with nothing written. Ends `ALL CHECKS PASSED`. Real captured runs
are in [`evidence/`](evidence/).

### One-command repro

```bash
./demo.sh
```

Walks the full sequence: unguarded damage → reset → guarded happy path → guarded violation 1
(blocked) → guarded violation 2 (held — approve it live when prompted). Guarded steps still need
`agent.infra` running in another terminal first.

---

## Repo layout

```
promotionguard/
├── README.md · CLAUDE.md · done.md
├── docs/          idea.md · technical.md · implementation.md · v2-plan.md · frontend.md · STARTHERE.md
├── requirements.txt · .env.example
├── agent/         config.py · runconfig.py · logging.py · plan.py · armoriq_client.py · ask.py · main.py · infra.py
├── mcp_servers/   dataset_mcp.py · jobs_mcp.py · registry_mcp.py · app.py (bundles all three)
├── data/          seed.py · reset.py · poisoned_card.txt · clean_card.txt
├── tests/         test_mcp_servers.py · verify_guarded.py
├── panel/         server.py · index.html
├── evidence/      logs/ · screenshots/ · README.md
└── demo.sh
```

## Why a keyword filter doesn't catch either violation

- **Violation 1** arrives as documentation. The dataset card itself says noisy rows should be
  excluded before scoring — the agent that deletes them is following instructions, not doing
  anything that reads as an attack.
- **Violation 2** is the exact same call — `promote_model` — the agent was authorized to make
  seconds earlier for staging. One argument differs. There's no scary word to filter on.

Both are caught because ArmorIQ checks the *signed plan*, not the text of the call. Details in
[`docs/technical.md`](docs/technical.md) §7.
