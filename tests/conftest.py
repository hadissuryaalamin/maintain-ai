"""Shared deterministic fixtures for the maintenance copilot test suite."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.seed import seed_database
from app.db.session import Database
from app.llm.demo_provider import DemoProvider
from app.main import create_app
from app.security.context import AuthContext
from app.tools.registry import ToolRegistry, build_tool_registry

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    database_path = tmp_path / "copilot-test.db"
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite:///{database_path.as_posix()}",
        llm_provider="demo",
        data_path=PROJECT_ROOT / "data",
        model_pricing_path=PROJECT_ROOT / "config" / "model_pricing.yaml",
        auto_seed=False,
        request_timeout_seconds=1,
    )


@pytest.fixture
def database(settings: Settings) -> Iterator[Database]:
    value = Database(settings.database_url)
    value.create_schema()
    try:
        yield value
    finally:
        value.engine.dispose()


@pytest.fixture
def seeded_database(database: Database, settings: Settings) -> Database:
    with database.session() as seed_session:
        seed_database(seed_session, settings.data_path)
    return database


@pytest.fixture
def session(seeded_database: Database) -> Iterator[Session]:
    with seeded_database.session() as value:
        yield value


@pytest.fixture
def context_a() -> AuthContext:
    return AuthContext(tenant_id="company-a", user_id="user-a-tech", role="technician")


@pytest.fixture
def context_b() -> AuthContext:
    return AuthContext(tenant_id="company-b", user_id="user-b-tech", role="technician")


@pytest.fixture
def registry(session: Session, context_a: AuthContext, settings: Settings) -> ToolRegistry:
    return build_tool_registry(session, context_a, settings)


@pytest.fixture
def api_client(settings: Settings, database: Database) -> Iterator[tuple[TestClient, Database]]:
    app_settings = settings.model_copy(update={"auto_seed": True})
    application = create_app(
        settings=app_settings,
        database=database,
        provider=DemoProvider(),
    )
    with TestClient(application) as client:
        yield client, database


@pytest.fixture
def headers_a() -> dict[str, str]:
    return {"X-Tenant-ID": "company-a", "X-User-ID": "user-a-tech"}


@pytest.fixture
def headers_b() -> dict[str, str]:
    return {"X-Tenant-ID": "company-b", "X-User-ID": "user-b-tech"}
