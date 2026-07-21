"""Explicit human approval service for state-changing tools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.db.models import AgentRun, ApprovalRequest, ToolCallEvent
from app.schemas.api import ApprovalDecisionResponse
from app.security.context import AuthContext, can_approve_work_orders, log_security_event
from app.tools.registry import ToolRegistry


class ApprovalNotFound(LookupError):
    pass


class ApprovalConflict(RuntimeError):
    pass


class ApprovalForbidden(PermissionError):
    pass


@dataclass(slots=True)
class ApprovalService:
    session: Session
    context: AuthContext
    registry: ToolRegistry

    async def decide(
        self, *, approval_id: str, approved: bool, idempotency_key: str
    ) -> ApprovalDecisionResponse:
        if not can_approve_work_orders(self.context):
            log_security_event(
                self.session,
                context=self.context,
                event_type="approval_role_denied",
                target_type="approval",
                target_id=approval_id,
                detail="Authenticated role is not allowed to decide work-order approvals.",
            )
            raise ApprovalForbidden("this role cannot decide work-order approvals")

        approval = self.session.scalar(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.id == approval_id,
                ApprovalRequest.tenant_id == self.context.tenant_id,
            )
            .with_for_update()
        )
        if approval is None:
            # Do not disclose whether an approval exists in another tenant.
            log_security_event(
                self.session,
                context=self.context,
                event_type="approval_access_denied",
                target_type="approval",
                target_id=approval_id,
                detail="Missing or cross-tenant approval decision attempt.",
            )
            raise ApprovalNotFound("approval request not found")

        if self.context.user_id != approval.user_id and self.context.role != "manager":
            log_security_event(
                self.session,
                context=self.context,
                event_type="approval_owner_denied",
                target_type="approval",
                target_id=approval_id,
                detail="Only the proposer or a tenant manager may decide this approval.",
            )
            raise ApprovalForbidden("only the proposer or a manager can decide this approval")

        if approval.status == "approved":
            return ApprovalDecisionResponse(
                approval_id=approval.id,
                status="approved",
                result=approval.result_json,
            )
        if approval.status == "rejected":
            if approved:
                raise ApprovalConflict("a rejected approval cannot later be approved")
            return ApprovalDecisionResponse(approval_id=approval.id, status="rejected")
        if approval.status != "pending":
            raise ApprovalConflict("approval is already being processed")

        decided_at = datetime.now(UTC)
        claim = cast(
            CursorResult[Any],
            self.session.execute(
                update(ApprovalRequest)
                .where(
                    ApprovalRequest.id == approval.id,
                    ApprovalRequest.tenant_id == self.context.tenant_id,
                    ApprovalRequest.status == "pending",
                )
                .values(
                    status="executing",
                    decision_by=self.context.user_id,
                    decided_at=decided_at,
                )
            ),
        )
        if claim.rowcount != 1:
            # The compare-and-swap is authoritative even where SELECT FOR UPDATE is ignored
            # (notably SQLite). Reload the winner's committed decision before responding.
            self.session.rollback()
            current = self.session.scalar(
                select(ApprovalRequest).where(
                    ApprovalRequest.id == approval_id,
                    ApprovalRequest.tenant_id == self.context.tenant_id,
                )
            )
            if current is None:
                raise ApprovalNotFound("approval request not found")
            if current.status == "approved":
                return ApprovalDecisionResponse(
                    approval_id=current.id,
                    status="approved",
                    result=current.result_json,
                )
            if current.status == "rejected" and not approved:
                return ApprovalDecisionResponse(approval_id=current.id, status="rejected")
            raise ApprovalConflict("approval is already being processed or decided")

        approval.status = "executing"
        approval.decision_by = self.context.user_id
        approval.decided_at = decided_at
        if not approved:
            approval.status = "rejected"
            self._set_run_status(approval.run_id, "rejected")
            self.session.flush()
            self.session.commit()
            return ApprovalDecisionResponse(approval_id=approval.id, status="rejected")

        approval.status = "executing"
        self.session.flush()
        invocation = await self.registry.execute(
            name=approval.tool_name,
            arguments=dict(approval.arguments_json),
            run_id=approval.run_id,
            approval_granted=True,
            idempotency_key=idempotency_key,
        )
        execution_event = ToolCallEvent(
            id=str(uuid4()),
            run_id=approval.run_id,
            tenant_id=self.context.tenant_id,
            user_id=self.context.user_id,
            agent_step=0,
            call_id=f"approval:{approval.id}",
            tool_name=approval.tool_name,
            arguments_json={
                "machine_id": approval.arguments_json.get("machine_id"),
                "priority": approval.arguments_json.get("priority"),
                "proposal": "[stored in approval request]",
            },
            result_preview="[tool result payload redacted by default]",
            status=invocation.status.value,
            error_category=(invocation.result.error.category if invocation.result.error else None),
            latency_ms=invocation.latency_ms,
        )
        self.session.add(execution_event)
        if not invocation.result.ok:
            approval.status = "pending"
            self.session.flush()
            # The API returns a conflict, which would otherwise roll back the observable failed
            # execution event and restored pending state.
            self.session.commit()
            message = (
                invocation.result.error.message
                if invocation.result.error
                else "approved action failed"
            )
            raise ApprovalConflict(message)

        approval.status = "approved"
        approval.result_json = invocation.result.data
        self._set_run_status(approval.run_id, "completed")
        self.session.flush()
        # Release the database claim before the HTTP layer updates the related run. This makes
        # repeated/concurrent confirmations observe the durable outcome instead of executing it.
        self.session.commit()
        return ApprovalDecisionResponse(
            approval_id=approval.id,
            status="approved",
            result=approval.result_json,
        )

    def _set_run_status(self, run_id: str, status: str) -> None:
        run = self.session.scalar(
            select(AgentRun).where(
                AgentRun.id == run_id,
                AgentRun.tenant_id == self.context.tenant_id,
            )
        )
        if run is not None:
            run.status = status
            run.completed_at = datetime.now(UTC)
