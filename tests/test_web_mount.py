"""The built technician web app is served at /app only when a build exists."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.db.session import Database
from app.llm.demo_provider import DemoProvider
from app.main import create_app


def test_web_mounted_when_dist_exists(
    tmp_path: Path, settings: Settings, database: Database
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    application = create_app(
        settings=settings.model_copy(update={"web_dist_path": dist}),
        database=database,
        provider=DemoProvider(),
    )
    with TestClient(application) as client:
        response = client.get("/app/")
    assert response.status_code == 200
    assert 'id="root"' in response.text


def test_web_not_mounted_when_missing(
    tmp_path: Path, settings: Settings, database: Database
) -> None:
    application = create_app(
        settings=settings.model_copy(update={"web_dist_path": tmp_path / "nope"}),
        database=database,
        provider=DemoProvider(),
    )
    with TestClient(application) as client:
        assert client.get("/app/").status_code == 404
        assert client.get("/health").status_code == 200
