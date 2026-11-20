"""Versioned FastAPI routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.orchestrator import MaintenanceAgent
from app.api.dependencies import get_auth_context, get_session
from app.db.models import AgentRun, Machine, SensorReading
from app.db.repositories import MaintenanceRepository, TenantAccessDenied
from app.schemas.api import (
    AnalyticsSummary,
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    DiagnoseRequest,
    DiagnoseResponse,
    MachineSensors,
    MachineSummary,
    RunRecord,
    SensorPointOut,
    SensorSeries,
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


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _machine_summary(machine: Machine) -> MachineSummary:
    metadata = machine.metadata_json or {}
    return MachineSummary(
        id=machine.id,
        name=machine.name,
        model=machine.model,
        line=machine.line,
        status=machine.status,
        condition=_optional_str(metadata.get("condition")),
        active_alarm=machine.alarm_code,
        criticality=_optional_str(metadata.get("criticality")),
        hourly_downtime_cost=machine.hourly_downtime_cost,
        cost_currency=_optional_str(metadata.get("cost_currency")),
        last_status_at=_parse_timestamp(metadata.get("last_status_at")),
    )


def _sensor_point(reading: SensorReading) -> SensorPointOut:
    return SensorPointOut(
        value=None if reading.value is None else float(reading.value),
        quality=reading.quality,
        recorded_at=reading.recorded_at,
    )


def _machine_not_found(session: Session) -> HTTPException:
    # Persist the audit event written by the repository before the request unwinds.
    session.commit()
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found.")


@router.get("/machines", response_model=list[MachineSummary])
def list_machines(
    session: Annotated[Session, Depends(get_session)],
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> list[MachineSummary]:
    repository = MaintenanceRepository(session, context)
    return [_machine_summary(machine) for machine in repository.list_machines()]


@router.get("/machines/{machine_id}", response_model=MachineSummary)
def get_machine(
    machine_id: str,
    session: Annotated[Session, Depends(get_session)],
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> MachineSummary:
    try:
        machine = MaintenanceRepository(session, context).get_machine(machine_id)
    except TenantAccessDenied as exc:
        raise _machine_not_found(session) from exc
    return _machine_summary(machine)


@router.get("/machines/{machine_id}/sensors", response_model=MachineSensors)
def get_machine_sensors(
    machine_id: str,
    session: Annotated[Session, Depends(get_session)],
    context: Annotated[AuthContext, Depends(get_auth_context)],
    limit: Annotated[int, Query(ge=1, le=200)] = 12,
) -> MachineSensors:
    try:
        grouped = MaintenanceRepository(session, context).latest_sensor_readings(
            machine_id=machine_id, limit=limit
        )
    except TenantAccessDenied as exc:
        raise _machine_not_found(session) from exc
    series = []
    for metric, readings in grouped.items():
        points = [_sensor_point(reading) for reading in readings]
        series.append(
            SensorSeries(
                metric=metric,
                unit=readings[-1].unit if readings else "",
                latest=points[-1] if points else None,
                readings=points,
            )
        )
    return MachineSensors(machine_id=machine_id, series=series)
