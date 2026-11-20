"""Read-only machine and sensor endpoints used by the technician web app."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.models import SecurityEvent, SensorReading
from app.db.session import Database


def _denied_events(database: Database, target_id: str) -> int:
    with database.session() as session:
        return int(
            session.scalar(
                select(func.count())
                .select_from(SecurityEvent)
                .where(
                    SecurityEvent.event_type == "cross_tenant_access_denied",
                    SecurityEvent.target_id == target_id,
                )
            )
            or 0
        )


def test_list_machines_is_tenant_scoped(
    api_client: tuple[TestClient, Database],
    headers_a: dict[str, str],
    headers_b: dict[str, str],
) -> None:
    client, _ = api_client
    response_a = client.get("/api/v1/machines", headers=headers_a)
    response_b = client.get("/api/v1/machines", headers=headers_b)
    assert response_a.status_code == 200
    assert [item["id"] for item in response_a.json()] == ["A1", "A2"]
    assert [item["id"] for item in response_b.json()] == ["B1", "B2"]


def test_machine_summary_fields(
    api_client: tuple[TestClient, Database], headers_a: dict[str, str]
) -> None:
    client, _ = api_client
    response = client.get("/api/v1/machines/A2", headers=headers_a)
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Process Cooling Pump"
    assert body["model"] == "CP-200"
    assert body["condition"] == "warning"
    assert body["active_alarm"] == "VIB-HI"
    assert body["criticality"] == "medium"
    assert Decimal(str(body["hourly_downtime_cost"])) == Decimal("1800")
    assert body["cost_currency"] == "USD"
    assert body["last_status_at"].startswith("2026-07-20T10:15:00")


def test_cross_tenant_machine_is_404_and_audited(
    api_client: tuple[TestClient, Database], headers_b: dict[str, str]
) -> None:
    client, database = api_client
    before = _denied_events(database, "A2")
    response = client.get("/api/v1/machines/A2", headers=headers_b)
    assert response.status_code == 404
    assert response.json()["detail"] == "Machine not found."
    assert _denied_events(database, "A2") == before + 1


def test_sensors_grouped_and_limited(
    api_client: tuple[TestClient, Database], headers_a: dict[str, str]
) -> None:
    client, _ = api_client
    response = client.get("/api/v1/machines/A2/sensors?limit=3", headers=headers_a)
    assert response.status_code == 200
    body = response.json()
    assert body["machine_id"] == "A2"
    assert [series["metric"] for series in body["series"]] == ["suction_pressure", "vibration_rms"]
    for series in body["series"]:
        readings = series["readings"]
        assert len(readings) == 3
        times = [reading["recorded_at"] for reading in readings]
        assert times == sorted(times)
        assert series["latest"] == readings[-1]
        assert series["unit"]


def test_sensors_default_limit(
    api_client: tuple[TestClient, Database], headers_a: dict[str, str]
) -> None:
    client, _ = api_client
    body = client.get("/api/v1/machines/A2/sensors", headers=headers_a).json()
    assert all(len(series["readings"]) == 8 for series in body["series"])


def test_sensors_limit_bounds(
    api_client: tuple[TestClient, Database], headers_a: dict[str, str]
) -> None:
    client, _ = api_client
    assert client.get("/api/v1/machines/A2/sensors?limit=0", headers=headers_a).status_code == 422
    assert client.get("/api/v1/machines/A2/sensors?limit=201", headers=headers_a).status_code == 422


def test_sensors_cross_tenant_404(
    api_client: tuple[TestClient, Database], headers_b: dict[str, str]
) -> None:
    client, _ = api_client
    assert client.get("/api/v1/machines/A2/sensors", headers=headers_b).status_code == 404


def test_sensor_null_value_passes_through(
    api_client: tuple[TestClient, Database], headers_a: dict[str, str]
) -> None:
    client, database = api_client
    with database.session() as session:
        session.add(
            SensorReading(
                tenant_id="company-a",
                machine_id="A2",
                metric="vibration_rms",
                value=None,
                unit="mm/s",
                quality="missing",
                recorded_at=datetime(2026, 7, 20, 11, 0, tzinfo=UTC),
            )
        )
        session.commit()
    body = client.get("/api/v1/machines/A2/sensors", headers=headers_a).json()
    vibration = next(series for series in body["series"] if series["metric"] == "vibration_rms")
    assert vibration["latest"]["value"] is None
    assert vibration["latest"]["quality"] == "missing"


def test_machines_require_identity_headers(api_client: tuple[TestClient, Database]) -> None:
    client, _ = api_client
    assert client.get("/api/v1/machines").status_code == 422
