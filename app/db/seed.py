"""Load the versioned synthetic fixture corpus into the relational schema."""

from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Incident, Machine, ManualChunk, SensorReading, Tenant, User


def _records(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    return list(payload["records"])


def _datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def seed_database(session: Session, data_path: Path, *, force: bool = False) -> dict[str, int]:
    """Seed synthetic records idempotently and return inserted/available counts."""

    existing = session.scalar(select(func.count()).select_from(Tenant)) or 0
    if existing and not force:
        return _counts(session)

    seed_path = data_path / "seed"
    for item in _records(seed_path / "tenants.json"):
        session.merge(Tenant(id=item["id"], name=item["name"]))
    session.flush()
    for item in _records(seed_path / "users.json"):
        session.merge(
            User(
                id=item["id"],
                tenant_id=item["tenant_id"],
                name=item["name"],
                role=item.get("role", "technician"),
            )
        )
    for item in _records(seed_path / "machines.json"):
        excluded = {
            "id",
            "tenant_id",
            "name",
            "model",
            "line",
            "status",
            "active_alarm",
            "hourly_downtime_cost",
        }
        session.merge(
            Machine(
                id=item["id"],
                tenant_id=item["tenant_id"],
                name=item["name"],
                model=item["model"],
                line=item["line"],
                status=item["status"],
                alarm_code=item.get("active_alarm"),
                hourly_downtime_cost=Decimal(str(item.get("hourly_downtime_cost", 0))),
                metadata_json={key: value for key, value in item.items() if key not in excluded},
            )
        )
    session.flush()
    if force:
        session.query(SensorReading).delete()
    for item in _records(seed_path / "sensor_readings.json"):
        session.add(
            SensorReading(
                tenant_id=item["tenant_id"],
                machine_id=item["machine_id"],
                metric=item["metric"],
                value=item.get("value"),
                unit=item["unit"],
                quality=item.get("quality", "good"),
                recorded_at=_datetime(item["timestamp"]),
            )
        )
    for item in _records(seed_path / "incidents.json"):
        session.merge(
            Incident(
                id=item["id"],
                tenant_id=item["tenant_id"],
                machine_id=item["machine_id"],
                title=item["title"],
                description=item["description"],
                resolution=item.get("resolution", ""),
                occurred_at=_datetime(item["occurred_at"]),
            )
        )
    _seed_manuals(session, data_path / "manuals")
    session.flush()
    return _counts(session)


def _seed_manuals(session: Session, manuals_path: Path) -> None:
    for document in _records(manuals_path / "manifest.json"):
        markdown = (manuals_path / document["path"]).read_text(encoding="utf-8-sig")
        sections = _markdown_sections(markdown)
        for manifest_section in document["sections"]:
            section_id = manifest_section["section_id"]
            content = sections.get(section_id, "")
            if not content:
                continue
            session.merge(
                ManualChunk(
                    id=f"{document['id']}:{section_id}",
                    tenant_id=document["tenant_id"],
                    machine_model=document["machine_model"],
                    title=document["title"],
                    section=manifest_section["heading"],
                    content=content,
                    source_reference=manifest_section["source_reference"],
                    is_adversarial_fixture=document.get("document_kind") == "adversarial_fixture",
                )
            )


def _markdown_sections(markdown: str) -> dict[str, str]:
    pattern = re.compile(r"^## \[([^]]+)]\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(markdown))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        sections[match.group(1)] = markdown[match.start() : end].strip()
    return sections


def _counts(session: Session) -> dict[str, int]:
    return {
        "tenants": session.scalar(select(func.count()).select_from(Tenant)) or 0,
        "users": session.scalar(select(func.count()).select_from(User)) or 0,
        "machines": session.scalar(select(func.count()).select_from(Machine)) or 0,
        "sensor_readings": session.scalar(select(func.count()).select_from(SensorReading)) or 0,
        "incidents": session.scalar(select(func.count()).select_from(Incident)) or 0,
        "manual_chunks": session.scalar(select(func.count()).select_from(ManualChunk)) or 0,
    }
