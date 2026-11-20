"""Tenant-scoped data access.

Every query containing customer data includes a tenant predicate. The model and caller do
not get a lower-level database handle, which keeps the boundary enforceable outside prompts.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Incident, Machine, SensorReading, WorkOrder
from app.security.content import contains_likely_prompt_injection
from app.security.context import AuthContext, log_security_event


class TenantResourceNotFound(LookupError):
    pass


class TenantAccessDenied(TenantResourceNotFound):
    pass


class IdempotencyConflict(RuntimeError):
    pass


def _terms(value: str) -> set[str]:
    return {part for part in re.findall(r"[a-z0-9_-]+", value.lower()) if len(part) > 1}


class MaintenanceRepository:
    def __init__(self, session: Session, context: AuthContext) -> None:
        self.session = session
        self.context = context

    def get_machine(self, machine_id: str) -> Machine:
        machine = self.session.scalar(
            select(Machine).where(
                Machine.id == machine_id, Machine.tenant_id == self.context.tenant_id
            )
        )
        if machine is not None:
            return machine

        # Audit every inaccessible identifier without issuing an unscoped existence query. This
        # intentionally makes missing and cross-tenant IDs indistinguishable to the caller.
        log_security_event(
            self.session,
            context=self.context,
            event_type="cross_tenant_access_denied",
            target_type="machine",
            target_id=machine_id,
            detail="Missing or cross-tenant machine lookup was denied.",
        )
        raise TenantAccessDenied("machine not found")

    def list_machines(self) -> list[Machine]:
        statement = (
            select(Machine).where(Machine.tenant_id == self.context.tenant_id).order_by(Machine.id)
        )
        return list(self.session.scalars(statement))

    def latest_sensor_readings(
        self, *, machine_id: str, limit: int
    ) -> dict[str, list[SensorReading]]:
        """Return the newest ``limit`` readings per metric, each list oldest-first."""
        self.get_machine(machine_id)
        metrics = self.session.scalars(
            select(SensorReading.metric)
            .where(
                SensorReading.tenant_id == self.context.tenant_id,
                SensorReading.machine_id == machine_id,
            )
            .distinct()
            .order_by(SensorReading.metric)
        )
        result: dict[str, list[SensorReading]] = {}
        for metric in list(metrics):
            newest_first = self.session.scalars(
                select(SensorReading)
                .where(
                    SensorReading.tenant_id == self.context.tenant_id,
                    SensorReading.machine_id == machine_id,
                    SensorReading.metric == metric,
                )
                .order_by(SensorReading.recorded_at.desc(), SensorReading.id.desc())
                .limit(limit)
            )
            result[metric] = list(reversed(list(newest_first)))
        return result

    def get_sensor_history(
        self,
        *,
        machine_id: str,
        metric: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[SensorReading]:
        self.get_machine(machine_id)
        statement: Select[tuple[SensorReading]] = (
            select(SensorReading)
            .where(
                SensorReading.tenant_id == self.context.tenant_id,
                SensorReading.machine_id == machine_id,
                SensorReading.metric == metric,
                SensorReading.recorded_at >= start_time,
                SensorReading.recorded_at <= end_time,
            )
            .order_by(SensorReading.recorded_at)
            .limit(1000)
        )
        return list(self.session.scalars(statement))

    def search_incidents(
        self, *, query: str, machine_id: str | None = None, limit: int = 5
    ) -> list[tuple[Incident, float]]:
        if machine_id is not None:
            self.get_machine(machine_id)
        statement = select(Incident).where(Incident.tenant_id == self.context.tenant_id)
        if machine_id is not None:
            statement = statement.where(Incident.machine_id == machine_id)
        candidates = list(self.session.scalars(statement.order_by(Incident.occurred_at.desc())))
        query_terms = _terms(query)
        scored: list[tuple[Incident, float]] = []
        for incident in candidates:
            searchable = (
                f"{incident.title} {incident.description} "
                f"{incident.resolution} {incident.machine_id}"
            )
            text_terms = _terms(searchable)
            overlap = len(query_terms & text_terms)
            score = overlap / max(len(query_terms), 1)
            if score > 0 or not query_terms:
                scored.append((incident, round(score, 4)))
        scored.sort(key=lambda item: (item[1], item[0].occurred_at), reverse=True)
        selected = scored[:limit]
        for incident, _ in selected:
            if contains_likely_prompt_injection(f"{incident.description} {incident.resolution}"):
                log_security_event(
                    self.session,
                    context=self.context,
                    event_type="prompt_injection_content_retrieved",
                    target_type="incident",
                    target_id=incident.id,
                    detail="Potential prompt injection was contained as untrusted evidence.",
                )
        return selected

    def calculate_downtime_cost(self, machine_id: str, minutes: int) -> tuple[Decimal, Decimal]:
        machine = self.get_machine(machine_id)
        hourly = Decimal(machine.hourly_downtime_cost)
        total = (hourly * Decimal(minutes) / Decimal(60)).quantize(Decimal("0.01"))
        return hourly, total

    def create_work_order(
        self,
        *,
        machine_id: str,
        title: str,
        description: str,
        priority: str,
        idempotency_key: str,
    ) -> tuple[WorkOrder, bool]:
        self.get_machine(machine_id)
        existing = self.session.scalar(
            select(WorkOrder).where(
                WorkOrder.tenant_id == self.context.tenant_id,
                WorkOrder.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if not _same_work_order(existing, machine_id, title, description, priority):
                raise IdempotencyConflict(
                    "idempotency key was already used for a different work order"
                )
            return existing, True
        work_order = WorkOrder(
            id=str(uuid4()),
            tenant_id=self.context.tenant_id,
            machine_id=machine_id,
            title=title,
            description=description,
            priority=priority,
            created_by=self.context.user_id,
            idempotency_key=idempotency_key,
        )
        try:
            with self.session.begin_nested():
                self.session.add(work_order)
                self.session.flush()
        except IntegrityError as exc:
            replay = self.session.scalar(
                select(WorkOrder).where(
                    WorkOrder.tenant_id == self.context.tenant_id,
                    WorkOrder.idempotency_key == idempotency_key,
                )
            )
            if replay is None:
                raise
            if not _same_work_order(replay, machine_id, title, description, priority):
                raise IdempotencyConflict(
                    "idempotency key was already used for a different work order"
                ) from exc
            return replay, True
        return work_order, False


def _same_work_order(
    work_order: WorkOrder,
    machine_id: str,
    title: str,
    description: str,
    priority: str,
) -> bool:
    return (
        work_order.machine_id == machine_id
        and work_order.title == title
        and work_order.description == description
        and work_order.priority == priority
    )
