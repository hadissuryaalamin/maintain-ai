"""Network-free rendering smoke test for the Streamlit surface."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_dashboard_renders_all_primary_surfaces_without_network_access() -> None:
    dashboard_path = Path(__file__).parents[1] / "dashboard" / "app.py"

    app = AppTest.from_file(str(dashboard_path)).run(timeout=15)

    assert not app.exception
    assert [item.value for item in app.title] == ["⚙️ Industrial AI Maintenance Operations Copilot"]
    assert [item.label for item in app.tabs] == [
        "Incident & approval",
        "Tool trace",
        "Telemetry dashboard",
    ]
    assert {item.label for item in app.button} >= {
        "Run preliminary diagnosis",
        "Load run",
        "Refresh analytics",
        "Check API",
    }
