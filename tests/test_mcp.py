"""Read-only MCP adapter security regression tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import mcp_server
from app.db.session import Database


def test_local_fixed_identity_mcp_refuses_production_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        mcp_server,
        "get_settings",
        lambda: SimpleNamespace(app_env="production"),
    )

    with pytest.raises(RuntimeError, match="authenticated MCP gateway"):
        mcp_server.main()


@pytest.mark.asyncio
async def test_mcp_dispatch_is_tenant_scoped_and_read_only(
    seeded_database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCP_TENANT_ID", "company-a")
    monkeypatch.setenv("MCP_USER_ID", "user-a-tech")
    monkeypatch.setattr(mcp_server, "get_database", lambda: seeded_database)

    own_machine = await mcp_server._execute_read_only("get_machine_status", {"machine_id": "A1"})
    other_tenant = await mcp_server._execute_read_only("get_machine_status", {"machine_id": "B1"})
    state_change = await mcp_server._execute_read_only(
        "create_work_order",
        {
            "machine_id": "A1",
            "title": "Must not dispatch",
            "description": "MCP exposes read-only operations only.",
            "priority": "high",
        },
    )

    assert own_machine["ok"] is True
    assert own_machine["status"] == "succeeded"
    assert own_machine["data"]["machine_id"] == "A1"
    assert other_tenant["ok"] is False
    assert other_tenant["error"]["category"] == "tenant_access_denied"
    assert other_tenant["error"]["message"] == "Requested resource is not accessible."
    assert state_change == {
        "ok": False,
        "tool_name": "create_work_order",
        "data": None,
        "error": {
            "category": "access_denied",
            "message": "Tool is not available through the read-only MCP server.",
            "retryable": False,
        },
        "status": "rejected",
        "latency_ms": 0,
    }
