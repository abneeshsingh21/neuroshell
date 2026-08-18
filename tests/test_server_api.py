import pytest
import server
from server import app, _dashboard_shell_name, _dashboard_history_count


def test_dashboard_helpers():
    shell_name = _dashboard_shell_name()
    assert isinstance(shell_name, str)
    assert len(shell_name) > 0

    count = _dashboard_history_count()
    assert isinstance(count, int)
    assert count >= 0


def test_server_endpoints():
    pytest.importorskip("httpx")
    from starlette.testclient import TestClient

    client = TestClient(app)
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert "commands" in data
    assert "shell" in data
    assert "cwd" in data


def test_cors_headers():
    pytest.importorskip("httpx")
    from starlette.testclient import TestClient

    client = TestClient(app)
    response = client.options(
        "/api/dashboard",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET"
        }
    )
    assert response.status_code == 200
