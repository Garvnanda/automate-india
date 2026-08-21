# PromotionGuard — Build Tracker

Status legend: [ ] pending  [x] done  [~] in progress/partial

## Flagged to user (decisions made / blockers surfaced)
- [x] ArmorIQ account: nothing set up yet — user will do it live, walked through step by step at Phase 1 (not yet reached)
- [x] OpenRouter API key: user has one ready, will provide at Phase 3
- [x] Git: repo `automate-india` created by user, git init + initial docs commit + push to
      https://github.com/Garvnanda/automate-india done as a ONE-OFF explicit user request —
      CLAUDE.md rule 6 still applies going forward: no further commits/pushes without asking
- [x] Two ArmorIQ identities (agent-operator low-rank, approver high-rank) required before
      Phase 1 hold demo works — not created yet
- [ ] Open question (technical.md §7 / CLAUDE.md "open question"): does a planned action with
      unplanned params raise IntentMismatchException? Decides whether Surface B (session/hold)
      is mandatory or optional. Resolved in Phase 1d — not reached yet.
- [ ] GATE 1 risk: ArmorIQ proxy may not reach localhost MCP servers — resolved in Phase 1b
- [x] `pip install fastmcp` was first run globally (not in a venv) before a venv existed —
      it upgraded/downgraded shared packages (starlette, uvicorn, python-dotenv,
      python-multipart) and pip flagged a version conflict with an already-installed fastapi
      on this machine. Fixed forward by creating `.venv/` and reinstalling fastmcp there for
      this project; the global env was left as-is, not rolled back. If another project on this
      machine depends on fastapi + old starlette/uvicorn, it may need `pip install -r` re-run
      in its own env. Flagging so it isn't a surprise later.

## Batch 1 — Phase 0 (finish) + Phase 2 (zero ArmorIQ dependency)
### Phase 0 — contract freeze remainder
- [x] agent/config.py — CANDIDATE_HASH, THRESHOLD, AGENT_EMAIL (placeholder), APPROVER_EMAIL (placeholder), db paths, split name
- [x] SQLite schemas frozen as real .sql / schema code (labels, dataset_card, models, promotions) — in data/seed.py
- [x] MCP tool signatures frozen (all 8, exact names+params) — see note below on read_metrics()
- [x] agent/logging.py — log line contract {ts, mode, step, action, mcp, params, verdict, reason}
### Phase 2 — MCP servers + seed data
- [x] requirements.txt updated (fastmcp)
- [x] data/seed.py
- [x] data/reset.py
- [x] data/poisoned_card.txt
- [x] mcp_servers/dataset_mcp.py (read_split, get_dataset_card, delete_rows)
- [x] mcp_servers/jobs_mcp.py mock (launch_run, get_run_status, read_metrics)
- [x] mcp_servers/registry_mcp.py (list_models, promote_model)
- [x] tests/test_mcp_servers.py — plain-assert scratch script exercising all 8 tools (ran, passed)
- [x] Acceptance verified: delete_rows really removed rows (100 -> 95), reset.py restored to 200
- [x] `.venv/` created for this project; `.gitignore` added (.venv, __pycache__, .env, *.db, *.jsonl)
- [~] Note: technical.md's fixed plan step 4 is `{"action": "read_metrics", "mcp": "jobs-mcp",
      "params": {}}` — no run_id. So `read_metrics()` takes no args and returns the metrics of
      the most recently launched run (module-level state in the jobs-mcp mock), not a
      run_id-keyed lookup. `get_run_status(run_id)` still takes run_id — it exists as a tool but
      isn't one of the 5 fixed plan steps, same as `list_models()`. Flagging in case this reading
      of the docs needs a second look before Batch 2.

## Batch 2 — Phase 1 (ArmorIQ spike) + Phase 3 (agent core, unguarded)
- [ ] Phase 1a: armoriq init/login/validate, API key in .env, two identities created
- [ ] Phase 1b GATE 1: one invoke() reaches local MCP server
- [ ] Phase 1c GATE 2: block proven (IntentMismatchException) + hold proven (PolicyHoldException, dashboard approve)
- [ ] Phase 1d: resolve open question (unplanned params -> IntentMismatchException?), write answer down
- [ ] agent/armoriq_client.py (hand-written, not delegated)
- [ ] agent/plan.py — the five declared steps
- [ ] agent/main.py — LLM tool-loop on OpenRouter, --unguarded, --force-violation {1,2}
- [ ] Acceptance: unguarded run with injection active really deletes rows + really promotes to production; log fixtures committed

## Batch 3 — Phase 4 (enforcement) + Phase 5 (hold/approve/resume)
- [ ] --guarded routes all calls through ArmorIQ, explicit allow globs
- [ ] Violation 1 blocked, rows verified present
- [ ] Violation 2 held (or blocked, depending on 1d answer), registry verified unchanged until approval
- [ ] Evidence captured immediately: row-count screenshots, audit entry, Proof tab export
- [ ] Phase 5: agent waits on hold instead of crashing, resumes after dashboard approval, timeout handling

## Batch 4 — Phase 6 (panel) + Phase 7 (README/demo/video)
- [ ] panel/ — plain HTML/CSS/JS, split screen unguarded vs guarded
- [ ] scenario buttons (happy path / violation 1 / violation 2), streaming colour-coded logs
- [ ] world-state panel (live labels row count, promotions contents)
- [ ] reset button wired to reset.py
- [ ] README.md, demo.sh, evidence/ folder
- [ ] demo video recorded the moment flow first works end to end

## Phase 8 — buffer (only if time allows)
- [ ] token expiry mid-run demo
- [ ] PAP pre-flight decisions
- [ ] second injection variant
- [ ] AIQraph screenshot in README
