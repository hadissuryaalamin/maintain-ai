"""Authoritative request identity.

The demo API resolves these values from development headers. Tools receive this context
out-of-band; model-generated arguments can never set or replace it.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SecurityEvent, Tenant, User


@dataclass(frozen=True, slots=True)
class AuthContext:
    tenant_id: str
    user_id: str
    role: str = "technician"


class AuthenticationError(Exception):
    pass


WORK_ORDER_APPROVER_ROLES = frozenset({"technician", "manager"})


def can_approve_work_orders(context: AuthContext) -> bool:
    """Return whether the authenticated application role may approve draft work orders."""

    return context.role in WORK_ORDER_APPROVER_ROLES


def authenticate_demo_context(session: Session, tenant_id: str, user_id: str) -> AuthContext:
    """Validate the development identity headers against the database.

    This is deliberately isolated so OIDC/JWT verification can replace it without changing
    tool or repository authorization.
    """

    tenant = session.scalar(select(Tenant).where(Tenant.id == tenant_id))
    user = session.scalar(select(User).where(User.id == user_id, User.active.is_(True)))
    if tenant is None or user is None or user.tenant_id != tenant_id:
        session.add(
            SecurityEvent(
                id=str(uuid4()),
                tenant_id=tenant_id or None,
                user_id=user_id or None,
                event_type="authentication_failed",
                target_type="tenant_user_context",
                target_id=None,
                detail="Invalid or cross-tenant development identity headers.",
            )
        )
        session.flush()
        # Authentication exceptions abort the request dependency transaction. Persist this
        # isolated audit event before raising so the denial itself is not rolled back.
        session.commit()
        raise AuthenticationError("invalid authentication context")
    return AuthContext(tenant_id=tenant.id, user_id=user.id, role=user.role)


def log_security_event(
    session: Session,
    *,
    context: AuthContext | None,
    event_type: str,
    target_type: str | None,
    target_id: str | None,
    detail: str,
) -> None:
    session.add(
        SecurityEvent(
            id=str(uuid4()),
            tenant_id=context.tenant_id if context else None,
            user_id=context.user_id if context else None,
            event_type=event_type,
            target_type=target_type,
            target_id=target_id,
            detail=detail[:500],
        )
    )
    session.flush()
