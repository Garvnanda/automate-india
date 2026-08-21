# PromotionGuard

Hackathon submission — **ArmorIQ track, Problem 1**, *"Autonomous, until it shouldn't be"*.

An agent runs an ML model promotion pipeline end to end, unattended: read the dataset card,
pull the eval split, launch a run, read the metrics, promote the winner. Two things go wrong on
purpose — it tries to delete rows from the eval set it's graded on, and it tries to promote to
*production* instead of *staging*. Neither is catchable by a keyword filter; both are caught by
ArmorIQ before they execute. Full pitch in [`docs/idea.md`](docs/idea.md), design in
[`docs/technical.md`](docs/technical.md).

**Status:** build in progress. This README grows with each build batch — see the checklist below
for what's runnable right now vs. what's still coming.

---

## What you need before you start

- **Python 3.11+**
- **git**
- An **ArmorIQ platform account** — API key, and two identities (a low-ranked
  agent-operator email and a higher-ranked approver email). Needed from Batch 2 onward; not
  needed for the setup/verify steps below.
- An **OpenRouter API key** — needed from Batch 2 onward.

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

## Build status

- [x] **Batch 1** — MCP servers (`dataset-mcp`, `jobs-mcp`, `registry-mcp`), SQLite seed/reset,
      structured logging contract. Verified with `tests/test_mcp_servers.py`.
- [ ] **Batch 2** — ArmorIQ platform spike, agent core (`--unguarded`, `--force-violation`)
- [ ] **Batch 3** — ArmorIQ enforcement (`--guarded`), hold/approve/resume
- [ ] **Batch 4** — demo panel, `demo.sh`, evidence, video

Commands below get filled in as each batch lands — see `done.md` for the detailed, ticked
checklist behind this summary.

```bash
# coming in Batch 2/3:
python -m agent.main --unguarded
python -m agent.main --guarded
python -m agent.main --guarded --force-violation 1
python -m agent.main --guarded --force-violation 2
./demo.sh
```

## Repo layout

```
promotionguard/
├── README.md · CLAUDE.md · done.md
├── docs/          idea.md · technical.md · implementation.md · STARTHERE.md
├── requirements.txt · .env.example
├── agent/         config.py · logging.py · (main.py, plan.py, armoriq_client.py — Batch 2)
├── mcp_servers/   dataset_mcp.py · jobs_mcp.py · registry_mcp.py
├── data/          seed.py · reset.py · poisoned_card.txt
├── tests/         test_mcp_servers.py
├── panel/         (Batch 4)
└── evidence/      (Batch 3/4)
```

## Why a keyword filter doesn't catch either violation

- **Violation 1** arrives as documentation. The dataset card itself says noisy rows should be
  excluded before scoring — the agent that deletes them is following instructions, not doing
  anything that reads as an attack.
- **Violation 2** is the exact same call — `promote_model` — the agent was authorized to make
  seconds earlier for staging. One argument differs. There's no scary word to filter on.

Both are caught because ArmorIQ checks the *signed plan*, not the text of the call. Details in
[`docs/technical.md`](docs/technical.md) §7.
