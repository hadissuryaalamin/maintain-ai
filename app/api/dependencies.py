"""HTTP dependency injection."""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import Settings
from app.security.context import (
    AuthContext,
    AuthenticationError,
    authenticate_demo_context,
)


def get_settings_from_app(request: Request) -> Settings:
    return request.app.state.settings


def get_session(request: Request) -> Generator[Session, None, None]:
    with request.app.state.database.session() as session:
        yield session


def get_auth_context(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    x_tenant_id: Annotated[str, Header(min_length=1, max_length=64, alias="X-Tenant-ID")],
    x_user_id: Annotated[str, Header(min_length=1, max_length=64, alias="X-User-ID")],
) -> AuthContext:
    settings: Settings = request.app.state.settings
    if not settings.allow_demo_auth:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Production identity adapter is not configured.",
        )
    try:
        return authenticate_demo_context(session, x_tenant_id, x_user_id)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication context.",
        ) from exc
