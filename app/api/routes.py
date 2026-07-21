"""Versioned FastAPI routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.orchestrator import MaintenanceAgent
from app.api.dependencies import get_auth_context, get_session
from app.db.models import AgentRun
from app.schemas.api import (
    AnalyticsSummary,
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    DiagnoseRequest,
    DiagnoseResponse,
    RunRecord,
)
from app.security.approval import (
    ApprovalConflict,
    ApprovalForbidden,
    ApprovalNotFound,
    ApprovalService,
)
from app.security.context import AuthContext, log_security_event
from app.telemetry.service import TelemetryService

router = APIRouter(prefix="/api/v1")


@router.post("/incidents/diagnose", response_model=DiagnoseResponse)
async def diagnose_incident(
    payload: DiagnoseRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> DiagnoseResponse:
    settings = request.app.state.settings
    registry_settings = settings
    if payload.optimization_mode.value == "baseline":
        registry_settings = settings.model_copy(
            update={
                "retrieval_chunk_limit": settings.baseline_retrieval_chunk_limit,
            }
        )
    registry = request.app.state.registry_factory(session, context, registry_settings)
    telemetry = TelemetryService(session, context, settings)
    agent = MaintenanceAgent(
        session=session,
        context=context,
        settings=settings,
        provider=request.app.state.provider,
        registry=registry,
        telemetry=telemetry,
    )
    return await agent.diagnose(payload)


@router.post("/approvals/{approval_id}/confirm", response_model=ApprovalDecisionResponse)
async def decide_approval(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> ApprovalDecisionResponse:
    registry = request.app.state.registry_factory(session, context, request.app.state.settings)
    service = ApprovalService(session=session, context=context, registry=registry)
    try:
        decision = await service.decide(
            approval_id=approval_id,
            approved=payload.approved,
            idempotency_key=payload.idempotency_key,
        )
    except ApprovalNotFound as exc:
        session.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ApprovalForbidden as exc:
        session.commit()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ApprovalConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return decision


@router.get("/runs/{run_id}", response_model=RunRecord)
def get_run(
    run_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> RunRecord:
    run = session.scalar(
        select(AgentRun).where(AgentRun.id == run_id, AgentRun.tenant_id == context.tenant_id)
    )
    if run is None:
        log_security_event(
            session,
            context=context,
            event_type="run_access_denied",
            target_type="agent_run",
            target_id=run_id,
            detail="Missing or cross-tenant agent-run lookup was denied.",
        )
        session.commit()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    telemetry = TelemetryService(session, context, request.app.state.settings)
    return RunRecord(
        run_id=run.id,
        status=run.status,
        task_type=run.task_type,
        optimization_mode=run.optimization_mode,
        model=run.model,
        provider=run.provider,
        diagnostic=run.diagnostic_json,
        error_category=run.error_category,
        started_at=run.started_at,
        completed_at=run.completed_at,
        tool_trace=telemetry.tool_trace(run.id),
        usage=telemetry.usage_summary(run.id, model=run.model, provider=run.provider),
    )


@router.get("/analytics/summary", response_model=AnalyticsSummary)
def analytics_summary(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> AnalyticsSummary:
    return TelemetryService(session, context, request.app.state.settings).analytics()


@router.get("/analytics/runs", response_model=list[RunRecord])
def analytics_runs(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    context: Annotated[AuthContext, Depends(get_auth_context)],
    limit: int = 50,
) -> list[RunRecord]:
    bounded_limit = max(1, min(limit, 200))
    runs = list(
        session.scalars(
            select(AgentRun)
            .where(AgentRun.tenant_id == context.tenant_id)
            .order_by(AgentRun.started_at.desc())
            .limit(bounded_limit)
        )
    )
    telemetry = TelemetryService(session, context, request.app.state.settings)
    return [
        RunRecord(
            run_id=run.id,
            status=run.status,
            task_type=run.task_type,
            optimization_mode=run.optimization_mode,
            model=run.model,
            provider=run.provider,
            diagnostic=run.diagnostic_json,
            error_category=run.error_category,
            started_at=run.started_at,
            completed_at=run.completed_at,
            tool_trace=telemetry.tool_trace(run.id),
            usage=telemetry.usage_summary(run.id, model=run.model, provider=run.provider),
        )
        for run in runs
    ]
