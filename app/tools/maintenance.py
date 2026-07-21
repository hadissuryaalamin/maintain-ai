"""Maintenance tool implementations."""

from __future__ import annotations

from decimal import Decimal

from app.db.repositories import MaintenanceRepository
from app.retrieval.service import RetrievalService
from app.schemas.tools import (
    CreateWorkOrderInput,
    CreateWorkOrderOutput,
    DowntimeCostInput,
    DowntimeCostOutput,
    IncidentMatch,
    MachineStatusInput,
    MachineStatusOutput,
    ManualMatch,
    SearchIncidentHistoryInput,
    SearchIncidentHistoryOutput,
    SearchManualInput,
    SearchManualOutput,
    SensorHistoryInput,
    SensorHistoryOutput,
    SensorPoint,
)
from app.security.content import delimit_untrusted_content


class MaintenanceToolHandlers:
    def __init__(self, repository: MaintenanceRepository, retrieval: RetrievalService) -> None:
        self.repository = repository
        self.retrieval = retrieval

    def search_manual(self, value: SearchManualInput, _: str | None) -> SearchManualOutput:
        matches = self.retrieval.search_manual(value.query, value.machine_model)
        return SearchManualOutput(
            matches=[
                ManualMatch(
                    chunk_id=item.chunk_id,
                    title=item.title,
                    section=item.section,
                    excerpt=item.excerpt,
                    source_reference=item.source_reference,
                    relevance_score=item.relevance_score,
                )
                for item in matches
            ],
            returned_chunks=len(matches),
        )

    def get_machine_status(self, value: MachineStatusInput, _: str | None) -> MachineStatusOutput:
        machine = self.repository.get_machine(value.machine_id)
        return MachineStatusOutput(
            machine_id=machine.id,
            name=machine.name,
            model=machine.model,
            line=machine.line,
            status=machine.status,
            alarm_code=machine.alarm_code,
            last_maintenance_at=machine.last_maintenance_at,
            source_reference=f"tool:get_machine_status:{machine.id}",
        )

    def get_sensor_history(self, value: SensorHistoryInput, _: str | None) -> SensorHistoryOutput:
        readings = self.repository.get_sensor_history(
            machine_id=value.machine_id,
            metric=value.metric,
            start_time=value.start_time,
            end_time=value.end_time,
        )
        # Exact query timestamps remain observable in the tool trace; the stable reference is
        # intentionally reusable by deterministic evaluation and user-facing citations.
        source = f"tool:get_sensor_history:{value.machine_id}:{value.metric}"
        return SensorHistoryOutput(
            machine_id=value.machine_id,
            metric=value.metric,
            readings=[
                SensorPoint(
                    timestamp=reading.recorded_at,
                    value=float(reading.value) if reading.value is not None else None,
                    unit=reading.unit,
                    quality=reading.quality,
                )
                for reading in readings
            ],
            source_reference=source,
            data_complete=bool(readings)
            and all(
                reading.value is not None and reading.quality != "missing" for reading in readings
            ),
        )

    def search_incident_history(
        self, value: SearchIncidentHistoryInput, _: str | None
    ) -> SearchIncidentHistoryOutput:
        matches = self.repository.search_incidents(
            query=value.query, machine_id=value.machine_id, limit=5
        )
        return SearchIncidentHistoryOutput(
            matches=[
                IncidentMatch(
                    incident_id=incident.id,
                    machine_id=incident.machine_id,
                    title=incident.title,
                    summary=delimit_untrusted_content(incident.description[:1000]),
                    resolution=delimit_untrusted_content(incident.resolution[:1000]),
                    occurred_at=incident.occurred_at,
                    source_reference=f"incident:{incident.id}",
                    relevance_score=score,
                )
                for incident, score in matches
            ]
        )

    def calculate_downtime_cost(
        self, value: DowntimeCostInput, _: str | None
    ) -> DowntimeCostOutput:
        hourly, total = self.repository.calculate_downtime_cost(
            value.machine_id, value.downtime_minutes
        )
        return DowntimeCostOutput(
            machine_id=value.machine_id,
            downtime_minutes=value.downtime_minutes,
            hourly_cost=Decimal(hourly),
            estimated_cost=Decimal(total),
            source_reference=f"machine:{value.machine_id}:configured-downtime-cost",
        )

    def create_work_order(
        self, value: CreateWorkOrderInput, idempotency_key: str | None
    ) -> CreateWorkOrderOutput:
        if not idempotency_key:
            raise ValueError("idempotency key is required for work-order creation")
        work_order, replay = self.repository.create_work_order(
            machine_id=value.machine_id,
            title=value.title,
            description=value.description,
            priority=value.priority.value,
            idempotency_key=idempotency_key,
        )
        return CreateWorkOrderOutput(
            work_order_id=work_order.id,
            machine_id=work_order.machine_id,
            title=work_order.title,
            priority=work_order.priority,
            status=work_order.status,
            created_at=work_order.created_at,
            idempotent_replay=replay,
        )
