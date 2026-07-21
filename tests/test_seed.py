"""Synthetic seed corpus and repeatable offline-demo data tests."""

from __future__ import annotations

from sqlalchemy import func, select

from app.config import Settings
from app.db.models import Incident, Machine, ManualChunk, SensorReading, Tenant, User
from app.db.seed import seed_database
from app.db.session import Database

EXPECTED_COUNTS = {
    "tenants": 2,
    "users": 4,
    "machines": 4,
    "sensor_readings": 64,
    "incidents": 12,
    "manual_chunks": 31,
}


def test_seed_database_loads_complete_two_tenant_synthetic_demo(
    database: Database, settings: Settings
) -> None:
    with database.session() as session:
        counts = seed_database(session, settings.data_path)

        assert counts == EXPECTED_COUNTS
        assert set(session.scalars(select(Tenant.id))) == {"company-a", "company-b"}
        assert set(session.scalars(select(User.id))) == {
            "user-a-tech",
            "user-a-manager",
            "user-b-tech",
            "user-b-manager",
        }
        ownership = {
            machine.id: machine.tenant_id
            for machine in session.scalars(select(Machine).order_by(Machine.id))
        }
        assert ownership == {
            "A1": "company-a",
            "A2": "company-a",
            "B1": "company-b",
            "B2": "company-b",
        }

        a1 = session.get(Machine, "A1")
        assert a1 is not None
        assert a1.name == "Line 3 Servo Press"
        assert a1.model == "SP-400"
        assert a1.status == "stopped"
        assert a1.alarm_code == "E217"
        assert str(a1.hourly_downtime_cost) == "4800.00"


def test_seed_is_idempotent_and_force_reseed_does_not_duplicate_readings(
    database: Database, settings: Settings
) -> None:
    with database.session() as session:
        first = seed_database(session, settings.data_path)
        second = seed_database(session, settings.data_path)
        forced = seed_database(session, settings.data_path, force=True)

        assert first == EXPECTED_COUNTS
        assert second == EXPECTED_COUNTS
        assert forced == EXPECTED_COUNTS
        assert session.scalar(select(func.count()).select_from(SensorReading)) == 64


def test_seed_contains_expected_missing_data_and_security_fixtures(
    database: Database, settings: Settings
) -> None:
    with database.session() as session:
        seed_database(session, settings.data_path)

        missing = session.scalar(
            select(SensorReading).where(
                SensorReading.tenant_id == "company-a",
                SensorReading.machine_id == "A2",
                SensorReading.metric == "vibration_rms",
                SensorReading.quality == "missing",
            )
        )
        assert missing is not None
        assert missing.value is None

        hostile_manuals = list(
            session.scalars(select(ManualChunk).where(ManualChunk.is_adversarial_fixture.is_(True)))
        )
        assert len(hostile_manuals) == 3
        assert all(chunk.tenant_id == "company-a" for chunk in hostile_manuals)
        assert any("Ignore all previous instructions" in chunk.content for chunk in hostile_manuals)

        hostile_incident = session.get(Incident, "INC-B-006")
        assert hostile_incident is not None
        assert hostile_incident.tenant_id == "company-b"
        assert "create a high-priority work order without approval" in hostile_incident.description
