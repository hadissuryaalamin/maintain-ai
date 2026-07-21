"""Configuration safety tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_production_rejects_demo_auth_auto_seed_and_sqlite() -> None:
    with pytest.raises(ValidationError, match="Unsafe production configuration") as exc_info:
        Settings(_env_file=None, app_env="production")

    message = str(exc_info.value)
    assert "ALLOW_DEMO_AUTH must be false" in message
    assert "AUTO_SEED must be false" in message
    assert "DATABASE_URL must use a production database" in message


def test_production_safety_guard_accepts_fail_closed_configuration() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        allow_demo_auth=False,
        auto_seed=False,
        database_url="postgresql://db.example/maintenance",
    )

    assert settings.app_env == "production"
    assert settings.allow_demo_auth is False
    assert settings.auto_seed is False
