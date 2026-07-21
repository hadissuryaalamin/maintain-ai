"""FastAPI application entry point."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import Settings, get_settings
from app.db.seed import seed_database
from app.db.session import Database, get_database
from app.llm.base import LLMProvider
from app.llm.factory import build_provider
from app.tools.registry import ToolRegistryFactory, build_tool_registry


def create_app(
    *,
    settings: Settings | None = None,
    database: Database | None = None,
    provider: LLMProvider | None = None,
    registry_factory: ToolRegistryFactory | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_database = database or get_database()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(
            level=getattr(logging, resolved_settings.log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        resolved_database.create_schema()
        if resolved_settings.auto_seed:
            with resolved_database.session() as session:
                seed_database(session, resolved_settings.data_path)
        application.state.settings = resolved_settings
        application.state.database = resolved_database
        application.state.provider = provider or build_provider(resolved_settings)
        application.state.registry_factory = registry_factory or build_tool_registry
        yield
        resolved_database.engine.dispose()

    application = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        description=(
            "Evidence-grounded industrial maintenance decision support. "
            "This application does not control physical equipment."
        ),
        lifespan=lifespan,
    )
    application.include_router(router)

    @application.middleware("http")
    async def request_context(request: Request, call_next: Any) -> Any:
        request_id = request.headers.get("X-Request-ID", str(uuid4()))[:128]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "maintenance-copilot"}

    @application.get("/")
    def root() -> dict[str, str]:
        return {
            "name": resolved_settings.app_name,
            "docs": "/docs",
            "health": "/health",
            "safety": "Decision support only; no machinery control.",
        }

    @application.exception_handler(Exception)
    async def controlled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        logging.getLogger(__name__).exception("Unhandled API error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "The request failed safely.", "category": "internal"},
        )

    return application


app = create_app()


def run() -> None:
    uvicorn.run(
        "app.main:app",
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "8000")),
        reload=False,
    )


if __name__ == "__main__":
    run()
