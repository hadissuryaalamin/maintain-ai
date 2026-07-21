"""Application configuration loaded exclusively from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Model names and pricing are configuration, never business-logic constants. The demo
    provider is the safe offline default; production deployments should select ``openai``.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    app_name: str = "Industrial AI Maintenance Operations Copilot"
    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./maintenance_copilot.db"
    llm_provider: Literal["demo", "openai"] = "demo"
    openai_api_key: SecretStr | None = None
    openai_base_url: str | None = None
    default_model: str = "gpt-5.6-terra"
    small_model: str = "gpt-5.6-luna"
    demo_model: str = "demo-maintenance-v1"
    model_pricing_path: Path = Path("config/model_pricing.yaml")
    data_path: Path = Path("data")
    auto_seed: bool = True

    max_agent_steps: int = Field(default=6, ge=1, le=20)
    max_tool_calls: int = Field(default=10, ge=1, le=50)
    request_timeout_seconds: float = Field(default=45, gt=0, le=300)
    max_output_tokens: int = Field(default=1800, ge=256, le=32768)
    max_request_input_characters: int = Field(default=250000, ge=1000, le=2_000_000)
    max_provider_input_characters: int = Field(default=120000, ge=1000, le=4_000_000)
    provider_max_retries: int = Field(default=2, ge=0, le=5)
    history_message_limit: int = Field(default=8, ge=1, le=100)
    history_character_limit: int = Field(default=12000, ge=1000, le=200000)
    retrieval_chunk_limit: int = Field(default=4, ge=1, le=12)
    baseline_retrieval_chunk_limit: int = Field(default=12, ge=1, le=50)

    allow_demo_auth: bool = True
    store_prompt_preview: bool = False
    store_tool_payloads: bool = False
    log_level: str = "INFO"

    @model_validator(mode="after")
    def production_configuration_fails_closed(self) -> Settings:
        """Prevent the demo identity/database conveniences from becoming production defaults."""

        if self.app_env != "production":
            return self
        unsafe: list[str] = []
        if self.allow_demo_auth:
            unsafe.append("ALLOW_DEMO_AUTH must be false")
        if self.auto_seed:
            unsafe.append("AUTO_SEED must be false")
        if self.is_sqlite:
            unsafe.append("DATABASE_URL must use a production database, not SQLite")
        if unsafe:
            raise ValueError("Unsafe production configuration: " + "; ".join(unsafe))
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    """Test helper for environment-specific settings."""

    get_settings.cache_clear()
