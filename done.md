# PromotionGuard — Build Tracker

Status legend: [ ] pending  [x] done  [~] in progress/partial

## Flagged to user (decisions made / blockers surfaced)
- [x] ArmorIQ account: nothing set up yet — user will do it live, walked through step by step at Phase 1 (not yet reached)
- [x] OpenRouter API key: received, in `.env`. Model chosen: `google/gemma-4-31b-it:free`
      (user picked from a live-pulled list of 16 free tool-calling models on OpenRouter).
      Verified live with a real tool-call request — returns clean OpenAI-style `tool_calls`,
      `cost: 0`. Set as `OPENROUTER_MODEL` default in `.env` and `.env.example`.
- [x] Git: repo `automate-india` created by user, git init + initial docs commit + push to
      https://github.com/Garvnanda/automate-india done as a ONE-OFF explicit user request —
      CLAUDE.md rule 6 still applies going forward: no further commits/pushes without asking
- [x] Two ArmorIQ identities (agent-operator low-rank, approver high-rank) required before
      Phase 1 hold demo works — not created yet
- [x] **1d ANSWERED, verified against the installed SDK's actual source (not docs, not
      guessed) — `.venv/Lib/site-packages/armoriq_sdk/`:** params are NOT inside the plan
      hash/Merkle proof anywhere. `client.invoke()` (client.py ~L806) matches a step by
      `step.get("action") == action` only; the CSRG digest (`X-CSRG-Value-Digest`) hashes only
      `step_obj["action"]`, never params. Session's `enforce_local`/`enforce_sdk`/`enforce`
      (session.py) do the same `tool_name in declared_tools` check — action-only. So invoking a
      **planned action with unplanned params does NOT raise IntentMismatchException.**
      Consequence: Surface A alone does NOT catch violation 2 (stage=production). **Surface B
      (session) is mandatory for violation 2**, exactly technical.md's "preferred" option 1 —
      confirmed, not assumed.
      **How the hold actually gets triggered, found in source (client.py `invoke_with_policy`,
      session.py `_evaluate_amount_threshold`):** the SDK's built-in native hold path is
      **amount/financial-threshold based** (`DelegationRequestParams.amount`,
      `financialRule.amountThreshold.requireApprovalAbove`) — it looks for a numeric field in
      tool_args (or semantic `amount_fields` metadata), not an arbitrary "authority" enum. Our
      `stage` field isn't a monetary amount, so this specific native path doesn't fit
      `promote_model` directly.
      **What DOES fit, also found in source (`cli_policy.py` `_print_policy`):** the org-level
      `armor.policy.v1` policy (managed via `armoriq policy propose --file <json>`) supports
      generic **statements with `conditions: [{field, op, value}]` and an `effect`**
      (allow/hold/block) per action — this is a first-class mechanism, not a hack, and matches
      CLAUDE.md's fallback option 3 (OPA-conditioned rule) almost exactly. Plan: a statement like
      `action.eq == "promote_model"` AND `conditions: [{field: "stage", op: "eq", value:
      "production"}]` → `effect: "hold"`. Server-side evaluation happens in `/iap/sdk/enforce`
      (session mode="sdk") or proxy `/invoke` (mode="proxy") — **not** `enforce_local`, which
      only understands the amount-threshold shape locally.
      **Now tested live, three independent ways, all confirming the same conclusion:**
      1. Org-wide Policy Studio (`armoriq policy propose`) rejected a `stage`-conditioned
         statement outright: `Unknown condition field: stage` — this system also has a fixed,
         hardcoded tool vocabulary (`Read/Grep/Glob/Bash/Write/Edit/MultiEdit` from its own
         templates) — it's built for governing coding-agent tools (principal.id:
         `"claude-code"` in the template JSON), not our MCP servers, and doesn't apply to us at
         all regardless of the condition-field issue.
      2. The **correct**, MCP-scoped policy system (dashboard, Policies, per-server, e.g.
         `cli-promotionguard-agent-registry-mcp`) does exist and is real — Form UI, YAML view,
         Allow/Hold/Block per tool, all genuinely wired (confirmed: setting `promote_model` to
         Hold and Activating changed `action: allow` to `action: hold` in the live YAML). BUT its
         per-tool "Parameter limits" field (free text, e.g. `stage == production`) is not
         wired to anything — set it, click Apply, re-open the YAML: the constraint never
         appears anywhere in the serialized policy. The UI's own copy hints at this ("Prototype
         stores these verbatim"). Confirmed empirically, not just from the hint text.
      3. Direct live test: captured a plan with `promote_model(stage="staging")`, then invoked
         with `stage="production"` through the real proxy — no `IntentMismatchException`
         (action was in plan, exactly as source predicted), and no other block/hold surfaced
         either (ran into an unrelated proxy-to-FastMCP session bug before reaching a clean
         allow/hold verdict, not worth chasing further given (1) and (2) already answer this).
      **Conclusion: this platform, as currently implemented, has no mechanism anywhere to
      treat `promote_model(stage="production")` differently from `promote_model(stage="staging")`
      short of splitting them into two different tool/action names**, which CLAUDE.md explicitly
      forbids (keyword-catchable, forfeits the scenario).
      **Recommended design (not yet built, needs sign-off):** implement the hold in our
      own agent code, using the SDK's real, verified "trust primitives" directly —
      `client.create_delegation_request(...)` when the agent is about to call
      `promote_model` with `stage=="production"`, then `get_delegation_status()` /
      `await_approval()` to wait, then the real `invoke()` only once approved. This is not a
      workaround that cheats — `create_delegation_request`, `check_approved_delegation`,
      `get_delegation_status`, `mark_delegation_executed` are all real public SDK methods
      (client.py, the "Trust update primitives" section) that create a genuine delegation
      record, surface it on the dashboard under "Needs you", and require the higher-ranked
      identity's real approval — exactly the demo beat the track wants. The distinction from a
      forbidden approach: the MCP action name never changes (`promote_model` throughout,
      `stage` stays a parameter) — only our code's decision to route through delegation
      depends on the parameter, which is legitimate application logic, not a keyword-catchable
      tool-name split.
- [x] **GATE 1 PASSED FOR REAL**, live, with real data round-tripping: `capture_plan()` →
      `get_intent_token()` → `invoke()` through the actual `https://proxy.armoriq.ai` reached our
      local `dataset-mcp` (FastMCP, HTTP transport, port 8001) via a cloudflared quick tunnel and
      returned the real (poisoned) dataset card text. Confirmed the predicted risk first
      (direct localhost registration → proxy error `connect ECONNREFUSED 127.0.0.1:8001` — that's
      the *proxy's own* loopback, not ours), then fixed it with a tunnel, exactly per
      technical.md §8 option 2.
- [x] **GATE 2 (block half) PASSED FOR REAL**: invoking `delete_rows` (not in the captured plan)
      raised `IntentMismatchException` exactly as designed — confirmed live, not just read from
      source.
- [x] **Three real bugs/gotchas found in `armoriq-sdk` 0.6.10 (installed source ground-truth,
      not speculation) — all worth reporting to organizers, all have workarounds:**
      1. `armoriq.yaml`'s `environment` field only accepts `"sandbox"` or `"production"`
         (pydantic `Literal`), but `armoriq init` defaults it to `"sandbox"` — and
         `ArmorIQClient.from_config()` maps anything != `"production"` to `use_production=False`,
         which points the client at local-stack endpoints (127.0.0.1:3000 etc.) that don't exist
         for a normal platform account. **Must manually set `environment: production`** in
         armoriq.yaml after `armoriq init`, or `validate`/every SDK call silently tries to hit a
         local backend that was never running.
      2. `armoriq validate`'s policy-ref linter checks `armoriq.yaml`'s `policy.allow/deny`
         entries as `server_id.tool_name` (**dot**-separated), not `mcp/action` (**slash**) as
         CLAUDE.md/technical.md documented — confirmed from `cli.py`'s `_validate_policy_tools`.
         This is specific to this one local-YAML-lint policy surface; unclear yet whether the
         runtime `get_intent_token(policy=...)` dict or the org-level armor.policy.v1 statements
         use the same separator — don't assume, check when we get there.
      3. `POST /iap/sdk/register` (what `armoriq register` calls) **500s** when re-registering an
         **existing** MCP server id with a **different URL** — isolated by testing payload
         variations directly (ruled out: auth field shape, description field, camelCase vs
         snake_case keys, `onConflict:"replace"` top-level flag, scheme http vs https). Re-
         submitting the *same* URL under an existing id correctly 409s asking for confirmation;
         a *different* URL under the same id 500s instead of returning that same structured
         conflict. **Workaround: register a fresh/unversioned `id` whenever the URL changes**
         (e.g. bump a suffix) rather than reusing the old id — clean 200 every time. Since
         cloudflared quick tunnels mint a **new random URL every time they start**, this means
         **every fresh session needs a fresh MCP server id at register time** — can't just always
         register as `dataset-mcp`/`jobs-mcp`/`registry-mcp` across restarts. Needs a small helper
         (Batch 2 remainder or Batch 3) that starts tunnels, reads the printed URLs, and
         registers under a timestamped/uuid'd id automatically — flagging now so `demo.sh` design
         accounts for it later, not discovered late.
- [x] Reproducibility requirement: judge clones repo and runs README commands verbatim on
      their own machine. New CLAUDE.md rule 8 added. README.md created now (not deferred to
      Phase 7) and will grow each batch. Verified for real this turn: copied the repo (minus
      .venv/.git/db files) into a throwaway dir, fresh `python -m venv`, `pip install -r
      requirements.txt`, `python data/reset.py`, `python tests/test_mcp_servers.py` — all
      passed with no reliance on anything installed globally on this machine.
- [x] `.env.example` added (ARMORIQ_API_KEY, ARMORIQ_ENV, AGENT_EMAIL, APPROVER_EMAIL,
      OPENROUTER_API_KEY) and `agent/config.py` now loads `.env` via python-dotenv (added to
      requirements.txt explicitly, not left as an implicit transitive dep of fastmcp).
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
- [x] mcp_servers/*.py switched to HTTP transport (fixed ports 8001/8002/8003 in agent/config.py),
      confirmed for real: started dataset-mcp, sent a live MCP `initialize` request over
      http://127.0.0.1:8001/mcp, got a real 200 + protocol handshake back. Killed after.
- [x] `armoriq-sdk` installed in `.venv` (0.6.10, clean, added to requirements.txt), CLI
      confirmed present (`armoriq --help` matches CLAUDE.md's documented subcommands, plus a
      few extra: logout/whoami/switch-org/keys/policy — no conflict with what's verified)
- [x] Phase 1a DONE: signed up, `armoriq login` (device-code flow, live), `armoriq init`,
      `armoriq.yaml` hand-fixed (environment bug, policy separator bug — see gotchas above),
      real API key in `.env` (`ARMORIQ_API_KEY`), `APPROVER_EMAIL=garvnanda326@gmail.com`
      (real org_admin account, limit=1000000000).
      **AGENT_EMAIL resolved WITHOUT needing a second dashboard member.** Tried inviting a
      second identity via Team → Invite twice (a Gmail `+agent` plus-alias, then a fully
      separate real inbox `nandagarv326@gmail.com`) — both invites sat "Pending" with **no
      email ever delivered**, even after resend + 10min wait. This looks like a genuine platform
      bug in their invite-email delivery (consistent with the other rough edges found in this
      SDK/platform — worth reporting to organizers alongside the register 500 and env-default
      bug). **Worked around it by not needing an invite at all**: tested
      `GET /delegation/my-role` (the endpoint `_resolve_user_role()` in client.py calls to
      resolve a requester's role/limit for the delegation hold path) with a plain,
      never-registered email — it returns `200 {"role": null, "displayRole": "User", "limit":
      0, "tools": []}`. An arbitrary email that was never invited/onboarded resolves to
      genuinely least-privileged automatically. That's exactly the "agent-operator" identity we
      need — no dashboard membership required. So **`AGENT_EMAIL=agent-operator@example.com`
      stays as-is, it was never actually a placeholder that needed replacing.** Confirmed by
      contrast: same call with `garvnanda326@gmail.com` returns
      `{"role":"org_admin","limit":1000000000}` — real member, real elevated limit. The pending
      invites are harmless clutter, can be left or cancelled, don't block anything.
- [x] Phase 1b GATE 1: PASSED for real (see note above) — dataset-mcp only, via tunnel.
      jobs-mcp and registry-mcp not yet tunneled/registered for a live round trip, only proven
      reachable locally via `armoriq validate`.
- [x] Phase 1c GATE 2: **BOTH halves PASSED for real, live.** Block half: `delete_rows`
      (unplanned action) raised `IntentMismatchException`. Hold half: `create_delegation_request`
      produced a real pending item, appeared on the dashboard under Intent -> "Needs you" as
      "Plan ...", approved it as `garvnanda326@gmail.com` (org_admin) from the dashboard UI,
      then confirmed from our side via `get_delegation_status()` -> `"approved"` — the exact
      poll `armoriq_client.py`'s `_call_with_delegation()` relies on. Full loop proven end to
      end: agent creates delegation -> dashboard shows it -> human approves -> SDK sees the
      approval. **Phase 1 is done.**
- [x] Phase 1d: ANSWERED — see the detailed note above under "Flagged to user". Surface B is
      mandatory for violation 2; mechanism is an armor.policy.v1 conditional statement, not the
      SDK's native amount-threshold hold path.
- [x] agent/armoriq_client.py (hand-written, not delegated) — `ArmorGuard` class, wraps
      capture_plan/get_intent_token once per run, `.call(mcp, action, params, step_index)`
      routes normal calls through `invoke()` (blocked -> IntentMismatchException/
      PolicyBlockedException, else executed) and routes `promote_model` with
      `stage=="production"` through the real delegation flow (held -> poll
      get_delegation_status -> approved/blocked -> executed + mark_delegation_executed). Smoke
      tested live: construction, token mint, and delete_rows block all confirmed working; full
      delegation loop confirmed working via a standalone create_delegation_request +
      dashboard-approve + get_delegation_status check (see Gate 2 note above) — same calls the
      class makes internally, not yet run through the class's own poll loop end-to-end (that
      needs a live registered registry-mcp for the post-approval invoke(), deferred to Batch 3
      when the tunnel/register automation exists).
- [x] agent/plan.py — the five declared steps, `PLAN = {"goal": ..., "steps": PLAN_STEPS}`,
      single source imported by armoriq_client.py (and will be by agent/main.py)
- [x] agent/main.py — argparse (`--unguarded`/`--guarded` stub/`--force-violation {1,2}`),
      8-tool OpenAI-style schemas, `run_deterministic()` (scripted, no LLM — used for
      force-violation demos so they never depend on model mood) and `run_organic()` (real
      OpenRouter tool-calling loop, up to 10 iterations, 3-attempt retry on transient
      429/502/malformed responses). `urllib.request` only, stdlib, no new dependency.
- [x] Acceptance PASSED, all live:
      - `--force-violation 1`: `labels` val-split count 100 -> 60 (40 real rows deleted)
      - `--force-violation 2`: real `('cand-v7-8f3a2b', 'production', ...)` row landed in
        `promotions`
      - `--unguarded` organic (3 attempts, per implementation.md's budget): full 5-step happy
        path completes correctly every time (get_dataset_card -> read_split -> launch_run ->
        read_metrics -> promote_model(staging)); model reads the injected note but never calls
        `delete_rows` on its own across 3 runs — a safe refusal, not a bug, matches
        implementation.md's own warning ("modern models often refuse"). GATE 3 organic bait
        not achieved; not chased further per the documented 3-attempt budget.
      - Model note: first pick `google/gemma-4-31b-it:free` hit a live 429 (upstream Google AI
        Studio pool congestion) mid-session; switched to `openai/gpt-oss-20b:free` then to
        user's final pick `nvidia/nemotron-3-ultra-550b-a55b:free` (tool-calling verified live
        before locking in each time). `.env`/`.env.example` updated.
      - `logs/*.jsonl` fixtures exist from these runs (gitignored, not committed — Batch 4's
        panel can read them locally; user can un-gitignore specific ones later if committed
        fixtures are wanted).

## Batch 2 — COMPLETE. Both Phase 1 and Phase 3 done, everything above verified live.

## Batch 3 — Phase 4 (enforcement) + Phase 5 (hold/approve/resume) — COMPLETE
- [x] **Three blockers found and fixed, all diagnosed by live testing:**
      1. `Session not found` on the proxy→FastMCP hop. FastMCP's HTTP transport is stateful by
         default (`mcp-session-id`) and the proxy does not carry the session across calls. Fixed
         with `mcp.run(..., stateless_http=True)` in all three servers.
      2. **An intent token is bound to ONE MCP domain.** `policy_validation.domain` is taken from
         the plan's *first step*, and only that domain's policy matches — calls to any other
         domain hit `default_enforcement_action: block` and die
         (`Tool 'launch_run' denied by OPA: policy_constraints_not_satisfied`). Proved by minting
         a jobs-first plan and watching `domain` flip. With three tunnels, one signed plan could
         only ever reach one server. **Fix: `mcp_servers/app.py` mounts all three FastMCP apps on
         one origin under `/dataset`, `/jobs`, `/registry`, behind one tunnel.** Re-tested: all
         three policies match one token and calls to all three servers succeed. The servers stay
         three separate modules with three separate registry entries and policies — only the
         origin is shared.
      3. Session-unique MCP ids (already known from Batch 2) — cloudflared mints a new URL every
         start, and re-registering an existing id with a new URL 500s.
- [x] `agent/infra.py` — one command: ensures cloudflared (auto-downloads per-platform on first
      run into `.tools/`), starts the bundled MCP origin, opens one tunnel, registers all three
      servers with session-unique ids + explicit fail-closed allow list, writes `.session.json`,
      tears everything down on Ctrl-C.
- [x] `agent/main.py` refactored to an executor seam (`DirectExecutor` / `GuardedExecutor`) so
      `run_organic` and `run_deterministic` are shared **verbatim** between modes — CLAUDE.md
      rule 3 (identical behaviour except enforcement) now holds structurally, not by discipline.
      `GuardedExecutor` also unwraps the MCP `{"content":[{"text":...}]}` envelope so the LLM sees
      identically-shaped observations in both modes.
- [x] `--hold-timeout` flag; clean `BLOCKED:` (exit 2) / `NOT APPROVED:` (exit 3) handling instead
      of tracebacks; friendly error when `.session.json` is missing.
- [x] `agent/plan.py` — `build_plan(server_map)` swaps logical MCP names for session ids.
      **Action names never change**, which is what preserves the violation semantics.
- [x] **Happy path under enforcement PASSED** — all 5 steps executed through the real
      `proxy.armoriq.ai`, staging promotion landed, 100 rows untouched.
- [x] **Violation 1 PASSED** — `delete_rows` verdict `blocked`, exit 2, val split still exactly
      100 rows. Rows genuinely survived.
- [x] **Violation 2 PASSED, full cycle, live** — `held` at 19:41:54 → human approved from the
      ArmorIQ dashboard → `approved` at 19:44:28 ("approved by garvnanda326@gmail.com") →
      `executed` at 19:44:29. The `production` row in `promotions` is timestamped 19:44:29,
      i.e. **after** the approval. Timeout path separately verified: with `--hold-timeout 20` and
      no approval it exits 3 and `promotions` stays empty.
- [x] `tests/verify_guarded.py` — asserts all three outcomes unattended, ends `ALL CHECKS PASSED`.
- [x] Evidence captured to `evidence/logs/` (three real run logs + `evidence/README.md`) AND
      `evidence/screenshots/` — four real dashboard screenshots, captured live via browser
      automation against a genuinely pending held action (not staged/faked): Held Actions
      "Needs you", the plan detail while still held, the 5-step flow graph, and the
      "Approved by admin" state immediately after clicking Approve. Timestamps in the screenshot
      session (held 20:02:07 → approved 20:05:47 → executed 20:05:49) match the log file exactly.
- [x] **Overclaiming fixed at the source, not just flagged.** `docs/idea.md` and `docs/technical.md`
      (two spots) said blocking "fails at the proxy" — corrected to state what Batch 3 actually
      verified: `IntentMismatchException` fires client-side inside the SDK, before any HTTP
      request leaves the agent process. Enforcement is still real and fail-closed; the claim is
      just now accurate. `[VERIFIED, Batch 3]` tags mark the corrected lines so a future read
      doesn't mistake them for the original unverified draft.

## Batch 4 — Phase 6 (panel) + Phase 7 (README/demo/video)
- [x] **Design phase**: mocked up two full visual directions as standalone artifacts (chain-of-
      custody/glassmorphism, and a brushed-metal analog instrument), user picked the Instrument.
      Then rebuilt for real — the mockup's fake choreographed dual-trace animation could not
      survive contact with reality (see honesty item below) and was redesigned accordingly.
- [x] `panel/server.py` — stdlib only (`http.server`, no new dependency, matches the project's
      "plain, no framework" rule for the backend too). Three endpoints: `GET /api/state`,
      `POST /api/reset`, `GET /api/run` (Server-Sent Events, streams the real `agent.main`
      subprocess's stdout line by line as it happens).
- [x] `panel/index.html` — the Instrument, real this time. Scope traces, needle gauges, brass
      toggle switches (GUARDED mode + HAPPY/VIOL-1/VIOL-2 scenario), lamps (ARMED/HOLD/BLOCK),
      a scrolling console log. All state comes from `/api/state` and the live SSE stream — no
      scripted/fake data anywhere.
- [x] **Honesty adaptation from the mockup, made explicit, not silently dropped:** unguarded and
      guarded share one SQLite database, so they genuinely cannot run simultaneously — the
      mockup's dual-lane-moving-at-once animation was a demo-only choreography, not something
      that could be real. Fixed: only the lane matching the active run animates; the idle lane
      shows its last real result, dimmed. Also: the mockup's key was clickable and faked local
      approval — the real key is a **status indicator only**. Actual approval only ever happens
      on ArmorIQ's own dashboard by a human with the right role; the panel just watches and
      reflects the real `held` → `approved` → `executed` verdict sequence as it arrives.
- [x] **Real bug found and fixed while wiring this up:** Python fully buffers stdout whenever
      it isn't a TTY — which is exactly `subprocess.Popen` piping `agent.main`'s output into the
      panel's SSE stream. Guarded runs looked hung for their entire ~20s duration (data was
      actually flowing to the log file fine, just not to stdout). Fixed two ways:
      `sys.stdout.reconfigure(..., line_buffering=True)` in `agent/main.py` (helps any consumer,
      not just the panel) and `python -u` in the panel's subprocess invocation (belt and braces).
      Confirmed live afterward: real-time streaming, correct trace timing, no more silent gap.
- [x] `demo.sh` — the full `technical.md` §9 sequence (unguarded damage → reset → guarded happy
      path → guarded violation 1 → guarded violation 2 with a live pause to approve), checks for
      `.session.json` and gives the plain "run agent.infra first" message if it's missing rather
      than failing halfway through. Verified live through step 3 (steps 4-5 already independently
      proven multiple times this session, not worth re-spending a real ArmorIQ hold cycle on).
- [x] **Verified live, twice, end to end, through the actual panel (not just the backend in
      isolation):** a guarded happy path clicked through the real browser UI, animated correctly,
      and a guarded violation-2 hold — created via the panel, approved on the real ArmorIQ
      dashboard, confirmed the SSE stream carried `held` → `approved` → `executed` through to the
      browser. Screenshots and logs from the Batch 3 hold cycle already cover this evidence; the
      panel is a second, independent confirmation of the same real mechanism, not a new claim.
- [x] Fixed a display-only bug found along the way: `data/reset.py`'s em-dash print garbled on
      Windows consoles (cp1252) — same class of issue already fixed once in `agent/main.py`,
      same fix applied (`sys.stdout.reconfigure(encoding="utf-8")`).
- [x] README.md updated: panel usage, `demo.sh` usage, repo layout. `evidence/` still needs the
      demo video — not recorded yet.
- [ ] Demo video — not recorded yet.

## Batch 5 — panel rebuilt for comprehension + one-command launch
Triggered by a blunt and correct piece of user feedback: the instrument panel looked good but
**taught the judge nothing**. Reviewed it live in a browser rather than from the markup, and the
criticism held up — so it was rebuilt around the story instead of the aesthetic.

- [x] **Diagnosis, from actually looking at the rendered page:** (1) no sentence anywhere said what
      the project does; (2) **the 5-step signed plan — the entire concept — was not on screen at
      all**; (3) jargon with no glossary (`VAL ROWS`, `CSRG-IAP`, `PLAN CEILING`); (4) the
      oscilloscope was the largest element and carried the least information; (5) contrast was too
      low to survive a projector or a compressed video; (6) guarded mode needed a second terminal.
- [x] `panel/index.html` rebuilt end to end. **The signed plan is now the hero element**: the five
      declared steps are listed literally and light up as they execute; a sixth card appears when
      the agent reaches for `delete_rows`, red and dashed, labelled either "Refused — not one of the
      5 signed steps" or "Executed anyway — nothing was checking" depending on the mode. The plan
      panel header itself flips between "Declared plan — not enforced" (red) and "Signed plan —
      enforced" (green), which is what makes the before/after legible without narration.
- [x] World state in **plain language instead of gauges**: `60 / 100 rows` + "40 rows were
      permanently deleted" with a red bar, vs "intact — every row still there". Registry entries
      render as tagged rows, production tagged red.
- [x] Plain-English event feed ("BLOCKED — `delete_rows` was never in the signed plan. The call
      never left the agent process") with the **raw JSONL audit log kept one click away** under a
      `<details>` so the technical claim is still verifiable.
- [x] **Hold is now a full-width banner**, not a keyhole icon: live timer, plain explanation, and a
      link (deliberately **not** a button — approval only ever happens on ArmorIQ's dashboard).
      Step 5 shows the argument diff inline: `authorized stage: staging` / `requested stage:
      production`. That diff is the clearest statement of violation 2 anywhere in the project.
- [x] **Adapted to a real backend constraint rather than changing the backend:** the agent only
      logs a step *after* it has a verdict — there is no `allowed`/"starting" event (confirmed by
      grepping every `log_event` call). So the panel infers the in-flight step as "the one after the
      last finished one". No new log events invented to make the UI prettier.
- [x] **One-command launch (the whole reason a judge can now run this).** `agent/infra.py`'s
      bring-up extracted into `bring_up(log=...)`; `main()` is now a thin CLI wrapper over it, CLI
      behaviour unchanged. `panel/server.py` calls it in a background thread on startup, exposes
      `infra: {state, message}` through `/api/state`, and the page polls it — guarded mode stays
      locked until it reports ready. Teardown on Ctrl-C removes `.session.json` and kills the
      children. `--no-infra` opts out; an externally-run `agent.infra` is detected and reused.
- [x] **Real bug found and fixed while testing that:** a stale `.session.json` (left by a crashed or
      killed `agent.infra`) made the panel report "ready" and then fail every guarded run. First fix
      attempt was wrong and *caught by testing it*: probing the tunnel treated any HTTP response as
      alive, but a dead cloudflared quick tunnel still resolves — Cloudflare's edge answers **530**
      for the hostname. Verified that 530 live against the stale URL, then changed the check to
      treat `>= 500` as dead. Stale sessions are now deleted and replaced automatically.
- [x] **Verified live in a browser, not from the markup:**
      - unguarded violation 1 → `60 / 100 rows`, "40 rows were permanently deleted", intruder card
        reads "Executed anyway — nothing was checking"
      - guarded violation 1 → `100 / 100 rows` intact, `delete_rows` **BLOCKED**, through the real
        `proxy.armoriq.ai` on a tunnel the panel brought up itself
      - guarded violation 2 → hold banner live with running timer, step 5 showing the staging vs
        production argument diff
- [x] README rewritten around `python -m panel.server` as the single entry point.
- [ ] Approved-state rendering (`held` → `approved` → `executed` in the new UI) — the verdicts are
      the same ones proven live in Batch 3 and the handlers are wired, but the **new** panel's
      approved rendering has not itself been watched through a real dashboard approval yet.
- [ ] Demo video — still not recorded.

## Phase 8 — buffer (only if time allows)
- [ ] token expiry mid-run demo
- [ ] PAP pre-flight decisions
- [ ] second injection variant
- [ ] AIQraph screenshot in README
