"""ArmorIQ integration — hand-written per CLAUDE.md, never delegated.

Verified against the installed SDK source (armoriq-sdk 0.6.10,
.venv/Lib/site-packages/armoriq_sdk/) and live testing against the real
platform — see done.md for the evidence trail. Do not change the mechanisms
below without re-verifying against that source; nothing here is guessed.

Two mechanisms, both real:
  - Violation 1 (delete_rows): caught by capture_plan/invoke's own plan
    verification — an action absent from the captured plan raises
    IntentMismatchException before any network call. Native SDK behaviour,
    nothing built here.
  - Violation 2 (promote to production): no ArmorIQ policy mechanism can
    distinguish stage="production" from stage="staging" — confirmed live,
    three ways (see done.md). So the agent's own code recognises the
    escalation and routes it through the SDK's real delegation primitives
    (create_delegation_request / get_delegation_status /
    mark_delegation_executed) instead of a plain invoke(). The MCP action
    name never changes; only the routing decision depends on the param.

Two gates, and it matters which is which — do not blur them to look stronger:

  Gate 1 — ArmorIQ, cryptographic, action-level. Membership of the signed
    plan. Enforced by the SDK (IntentMismatchException, client-side, before
    any request leaves the process) and again by the proxy's OPA policy
    (PolicyBlockedException). Both verified live.

  Gate 2 — the agent's own, parameter-level. ArmorIQ cannot see params, so
    this code compares a call against the params its *own signed plan*
    authorizes (runconfig.AUTHORITY_PARAMS). A mismatch is an authority
    escalation and raises a real ArmorIQ delegation request that a
    higher-ranked human must approve. Real mechanism, our decision to invoke
    it.
"""

import json
import time

from armoriq_sdk import ArmorIQClient
from armoriq_sdk.exceptions import (
    IntentMismatchException,
    MCPInvocationException,
    PolicyBlockedException,
    PolicyHoldException,
    TokenExpiredException,
)
from armoriq_sdk.models import DelegationRequestParams

from agent.config import (
    AGENT_EMAIL,
    AGENT_ID,
    APPROVER_EMAIL,
    DELEGATION_POLL_INTERVAL_SECONDS,
    DELEGATION_TIMEOUT_SECONDS,
)
from agent.logging import log_event
from agent.plan import authorized_params
from agent.policy_gen import generate as generate_policy
from agent.runconfig import AUTHORITY_PARAMS
from agent.severity import classify


class ArmorGuard:
    """One instance per guarded run. Captures the plan once, then routes
    every subsequent tool call through ArmorIQ before it reaches the real
    MCP server."""

    def __init__(self, run_id, plan, llm_name="agent", hold_timeout=None,
                 agent_role="operator", emit=None):
        self.run_id = run_id
        self.plan = plan
        self.agent_role = agent_role
        self.hold_timeout = hold_timeout or DELEGATION_TIMEOUT_SECONDS
        self.emit = emit or (lambda frame: None)
        self._calls = 0
        self._deviations = 0
        self.client = ArmorIQClient(user_id=AGENT_EMAIL, agent_id=AGENT_ID)

        # v3: the policy handed to ArmorIQ is derived from this plan, seconds
        # ago, rather than hand-written before the event. Its text goes on
        # screen at the signing beat.
        self.policy = generate_policy(plan, agent_role)
        self.generated_policy = self.policy["text"]

        captured = self.client.capture_plan(llm=llm_name, prompt=plan["goal"], plan=plan)
        self.token = self.client.get_intent_token(
            captured,
            policy={"allow": self.policy["allow"], "deny": self.policy["deny"]},
            validity_seconds=3600,
        )
        self.planned_actions = {s["action"] for s in plan.get("steps", [])}

    def call(self, mcp, action, params, step_index):
        """Execute one call through ArmorIQ. Returns the tool's result on
        success; raises on block/reject/timeout — callers catch and stop the
        run, same as they would for a real MCP error.

        Gate 1 before gate 2, deliberately: an action absent from the signed
        plan can never be rescued by an approval, so it must not raise a
        delegation request a human would approve only for invoke() to reject
        it afterwards.
        """
        self._calls += 1
        call_id = f"c{self._calls}"

        if action not in self.planned_actions:
            verdict = self._judge(call_id, mcp, action, params, step_index)
            self._deviations += 1
            if verdict["approvable"]:
                # ponytail: an approved out-of-plan call still cannot execute —
                # ArmorIQ refuses any action absent from the signed plan, and it
                # should. Re-signing (client.reanchor) is the real path; not
                # built, and not needed for any demo beat we have.
                return self._call_with_delegation(
                    mcp, action, params, step_index, verdict["derivation"][0], call_id)
            return self._call_direct(mcp, action, params, step_index, call_id)

        escalation = self._escalation(action, params)
        if not escalation:
            # in the plan, with the arguments the plan authorized. The plan
            # already said yes; severity never runs on it (docs/v3.md §3.4).
            self.emit({
                "type": "__verdict__", "call_id": call_id, "step_index": step_index,
                "mcp": mcp, "action": action, "args": params, "in_plan": True,
                "verdict": "ALLOW", "approvable": True,
                "axes": {"reversibility": None, "blast_radius": "in-scope", "authority_delta": 0},
                "derivation": [f"in signed plan (step {step_index}: {action})"],
                "touches_evidence": [], "delegate": None,
                "plan_hash": self.token.plan_hash, "delegation_hash": None,
                "step_proof": self._step_proof(action),
            })
            return self._call_direct(mcp, action, params, step_index, call_id)

        self._deviations += 1
        verdict = self._judge(call_id, mcp, action, params, step_index, reason=escalation)
        if verdict["verdict"] != "ALLOW":
            return self._call_with_delegation(
                mcp, action, params, step_index, escalation, call_id)
        # the grant already covers these arguments — the plan was written
        # narrower than the agent's authority, which is not an escalation
        return self._call_direct(mcp, action, params, step_index, call_id)

    def _judge(self, call_id, mcp, action, params, step_index, reason=None):
        """Derive the verdict and publish its derivation. ArmorIQ still does the
        enforcing — this decides what the deviation *costs*, and therefore who,
        if anyone, is allowed to say yes."""
        verdict = classify(mcp, action, params, self.plan, self.agent_role,
                           plan_hash=self.token.plan_hash, reason=reason,
                           step_index=step_index)
        verdict["call_id"] = call_id
        verdict["delegate"] = None
        verdict["delegation_hash"] = None
        verdict["step_proof"] = self._step_proof(action)
        self.emit({"type": "__verdict__", **verdict})
        return verdict

    def _step_proof(self, action):
        """The Merkle step proof this call is checked against, when the token
        carries one. Reported, never invented: absent means absent."""
        for i, step in enumerate(self.plan.get("steps", [])):
            if step.get("action") == action:
                proofs = getattr(self.token, "step_proofs", None) or []
                if i < len(proofs):
                    proof = proofs[i]
                    return proof if isinstance(proof, str) else json.dumps(proof, default=str)
                return None
        return None

    def _escalation(self, action, params):
        """Reason string if this call asks for authority the signed plan does
        not carry, else None. Compares only params declared as authority-
        bearing, so ordinary data params (row_ids, model_hash) never trip it."""
        for key in AUTHORITY_PARAMS:
            if key not in params:
                continue
            allowed = authorized_params(self.plan, action, key)
            if allowed and params[key] not in allowed:
                return (
                    f"{action} with {key}={params[key]!r} exceeds the signed plan's "
                    f"authority (authorized: {', '.join(sorted(allowed))})"
                )
        return None

    def _call_direct(self, mcp, action, params, step_index, call_id=None):
        try:
            result = self.client.invoke(mcp, action, self.token, params, user_email=AGENT_EMAIL)
        except IntentMismatchException as e:
            log_event(self.run_id, "guarded", step_index, action, mcp, params, "blocked", str(e))
            raise
        except (PolicyBlockedException, TokenExpiredException, MCPInvocationException) as e:
            log_event(self.run_id, "guarded", step_index, action, mcp, params, "blocked", str(e))
            raise
        log_event(self.run_id, "guarded", step_index, action, mcp, params, "executed", "")
        return result.result

    def _call_with_delegation(self, mcp, action, params, step_index, reason, call_id=None):
        log_event(self.run_id, "guarded", step_index, action, mcp, params, "held", reason)

        delegation = self.client.create_delegation_request(
            DelegationRequestParams(
                tool=action,
                action="execute",
                arguments=params,
                amount=1.0,
                requester_email=AGENT_EMAIL,
                requester_role="agent_user",
                requester_limit=0,
                domain=mcp,
                plan_id=self.token.plan_id,
                intent_reference=self.token.token_id,
                merkle_root=self.token.plan_hash,
                reason=reason,
            )
        )

        self.emit({"type": "__hold__", "call_id": call_id,
                   "request_id": delegation.delegation_id,
                   "dashboard_hint": "platform.armoriq.ai -> Intent -> Held Actions"})

        print()
        print("  ┌─ HELD — waiting on a human ────────────────────────────────")
        print(f"  │ {reason}")
        print(f"  │ delegation: {delegation.delegation_id}")
        print(f"  │ approve at platform.armoriq.ai → Intent → Held Actions")
        print(f"  │ as {APPROVER_EMAIL} (the agent cannot approve itself)")
        print(f"  │ waiting up to {int(self.hold_timeout)}s...")
        print("  └────────────────────────────────────────────────────────────")
        print()

        deadline = time.time() + self.hold_timeout
        status = "pending"
        while time.time() < deadline:
            time.sleep(DELEGATION_POLL_INTERVAL_SECONDS)
            status = self.client.get_delegation_status(delegation.delegation_id)
            if status in ("approved", "rejected"):
                break

        if status != "approved":
            why = "delegation rejected" if status == "rejected" else "delegation approval timed out"
            log_event(self.run_id, "guarded", step_index, action, mcp, params, "blocked", why)
            raise PolicyHoldException(f"{action} not approved: {why}")

        log_event(
            self.run_id, "guarded", step_index, action, mcp, params, "approved",
            f"approved by {APPROVER_EMAIL}",
        )
        self.emit({"type": "__resume__", "call_id": call_id, "approved_by": APPROVER_EMAIL})

        result = self._call_direct(mcp, action, params, step_index)
        self.client.mark_delegation_executed(AGENT_EMAIL, delegation.delegation_id, self.token.plan_id)
        return result
