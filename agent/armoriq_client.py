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


class ArmorGuard:
    """One instance per guarded run. Captures the plan once, then routes
    every subsequent tool call through ArmorIQ before it reaches the real
    MCP server."""

    def __init__(self, run_id, plan, llm_name="agent"):
        self.run_id = run_id
        self.plan = plan
        self.client = ArmorIQClient(user_id=AGENT_EMAIL, agent_id=AGENT_ID)
        captured = self.client.capture_plan(llm=llm_name, prompt=plan["goal"], plan=plan)
        self.token = self.client.get_intent_token(captured, validity_seconds=3600)

    def call(self, mcp, action, params, step_index):
        """Execute one plan step through ArmorIQ. Returns the tool's result
        on success; raises on block/reject/timeout — callers catch and stop
        the run, same as they would for a real MCP error."""
        if action == "promote_model" and params.get("stage") == "production":
            return self._call_with_delegation(mcp, action, params, step_index)
        return self._call_direct(mcp, action, params, step_index)

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

    def _call_with_delegation(self, mcp, action, params, step_index):
        reason = f"promote_model to production exceeds staging-only authority (stage={params.get('stage')!r})"
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

        deadline = time.time() + DELEGATION_TIMEOUT_SECONDS
        status = "pending"
        while time.time() < deadline:
            time.sleep(DELEGATION_POLL_INTERVAL_SECONDS)
            status = self.client.get_delegation_status(delegation.delegation_id)
            if status in ("approved", "rejected"):
                break

        if status != "approved":
            reason = "delegation rejected" if status == "rejected" else "delegation approval timed out"
            log_event(self.run_id, "guarded", step_index, action, mcp, params, "blocked", reason)
            raise PolicyHoldException(f"promote_model to production not approved: {reason}")

        log_event(
            self.run_id, "guarded", step_index, action, mcp, params, "approved",
            f"approved by {APPROVER_EMAIL}",
        )

        result = self._call_direct(mcp, action, params, step_index)
        self.client.mark_delegation_executed(AGENT_EMAIL, delegation.delegation_id, self.token.plan_id)
        return result
