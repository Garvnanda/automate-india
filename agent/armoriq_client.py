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
from agent.runconfig import AUTHORITY_PARAMS


class ArmorGuard:
    """One instance per guarded run. Captures the plan once, then routes
    every subsequent tool call through ArmorIQ before it reaches the real
    MCP server."""

    def __init__(self, run_id, plan, llm_name="agent", hold_timeout=None):
        self.run_id = run_id
        self.plan = plan
        self.hold_timeout = hold_timeout or DELEGATION_TIMEOUT_SECONDS
        self.client = ArmorIQClient(user_id=AGENT_EMAIL, agent_id=AGENT_ID)
        captured = self.client.capture_plan(llm=llm_name, prompt=plan["goal"], plan=plan)
        self.token = self.client.get_intent_token(captured, validity_seconds=3600)
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
        if action not in self.planned_actions:
            return self._call_direct(mcp, action, params, step_index)

        escalation = self._escalation(action, params)
        if escalation:
            return self._call_with_delegation(mcp, action, params, step_index, escalation)
        return self._call_direct(mcp, action, params, step_index)

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

    def _call_direct(self, mcp, action, params, step_index):
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

    def _call_with_delegation(self, mcp, action, params, step_index, reason):
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

        result = self._call_direct(mcp, action, params, step_index)
        self.client.mark_delegation_executed(AGENT_EMAIL, delegation.delegation_id, self.token.plan_id)
        return result
